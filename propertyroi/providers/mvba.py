"""MVBA delinquent-tax land/property sale provider (live HTTP fetch).

MVBA (McCreary, Veselka, Bragg & Allen, P.C.) runs Texas delinquent property
*tax sales* and publishes per-county bid sheets at mvbataxsales.com /
mvbalaw.com. These are auction listings — often raw land — with fields like
county, account/cause number, legal description (acreage), situs address,
*adjudged value*, and *minimum bid*. They are not residential rentals, so this
provider yields for-sale `Listing`s marked ``source="mvba"`` /
``property_type="land"`` and returns no rental comps.

Because MVBA/county pages are frequently PDF or HTML tables (and their exact
markup varies by county), this provider fetches a configurable URL and parses
either a JSON feed or HTML ``<table>`` rows, mapping columns to our model by
fuzzy header name. Set the source URL explicitly:

    export MVBA_SALES_URL="https://www.mvbataxsales.com/...county.../listings"
    python -m propertyroi scan --provider mvba

Only stdlib networking (urllib) and HTML parsing (html.parser) are used.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from html.parser import HTMLParser
from typing import List, Optional

from ..models import Listing, Location, RentalComp
from .base import DataProvider

_ACRE_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:ac\b|acre)", re.IGNORECASE)
_NUM_RE = re.compile(r"[-+]?[\d,]+(?:\.\d+)?")


def _to_float(v) -> Optional[float]:
    """Parse a money/number string like '$1,250.00' or '5.0 AC' to float."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = _NUM_RE.search(str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _acres_from(text: str) -> Optional[float]:
    """Pull an acreage figure out of a legal description / size string."""
    if not text:
        return None
    m = _ACRE_RE.search(str(text))
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


class _TableParser(HTMLParser):
    """Collect every HTML table as a list of rows, each a list of cell texts."""

    def __init__(self):
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self._rows: Optional[List[List[str]]] = None
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table" and self._rows is not None:
            if self._rows:
                self.tables.append(self._rows)
            self._rows = None
        elif tag == "tr" and self._row is not None:
            self._rows.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join(" ".join(self._cell).split()))
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


# Header keywords -> our logical field name. First match wins. Keywords are
# compared after stripping spaces/punctuation, so "Minimum Bid" and "minimumBid"
# both match "minimumbid".
_FIELD_KEYWORDS = [
    ("min_bid", ("minimumbid", "minbid", "openingbid", "startingbid")),
    ("adjudged", ("adjudged", "judgmentvalue", "appraised", "marketvalue")),
    ("acres", ("acre", "acreage")),
    ("address", ("address", "situs", "location", "property")),
    ("legal", ("legal", "description", "abstract")),
    ("county", ("county",)),
    ("sale_date", ("saledate", "date")),
    ("account", ("account", "cause", "suit", "parcel", "geoid")),
]


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _match_field(header: str) -> Optional[str]:
    h = _normalize(header)
    for field, keys in _FIELD_KEYWORDS:
        if any(k in h for k in keys):
            return field
    return None


class MvbaProvider(DataProvider):
    def __init__(self, url: Optional[str] = None, timeout: float = 25.0):
        self.url = url or os.environ.get("MVBA_SALES_URL", "")
        if not self.url:
            raise ValueError(
                "MVBA source URL required. Set MVBA_SALES_URL or pass url=... "
                "(e.g. a county tax-sale listing page or JSON feed)."
            )
        self.timeout = timeout

    # -- fetch (mockable in tests) -----------------------------------------
    def _fetch(self) -> tuple:
        req = urllib.request.Request(self.url, headers={"Accept": "application/json, text/html"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8", errors="replace")
        return body, ctype

    # -- parsing -----------------------------------------------------------
    def _parse(self, body: str, content_type: str = "") -> List[Listing]:
        stripped = body.lstrip()
        is_json = "json" in content_type.lower() or stripped[:1] in ("{", "[")
        if is_json:
            return self._parse_json(json.loads(body))
        return self._parse_html(body)

    def _row_to_listing(self, rec: dict, idx: int) -> Optional[Listing]:
        price = _to_float(rec.get("min_bid"))
        if price is None or price <= 0:
            return None
        legal = str(rec.get("legal") or "")
        acres = _to_float(rec.get("acres")) or _acres_from(legal) or _acres_from(rec.get("address") or "")
        account = str(rec.get("account") or "").strip()
        return Listing(
            id=account or f"MVBA-{idx}",
            location=Location(
                zip_code=str(rec.get("zip") or ""),
                city=str(rec.get("city") or ""),
                state=str(rec.get("state") or "TX"),
                county=str(rec.get("county") or ""),
            ),
            price=price,
            beds=0,
            baths=0.0,
            sqft=0,
            property_type="land",
            address=str(rec.get("address") or legal or "").strip(),
            source="mvba",
            lot_acres=acres,
            adjudged_value=_to_float(rec.get("adjudged")),
            sale_date=str(rec.get("sale_date") or ""),
            url=self.url,
        )

    def _parse_json(self, data) -> List[Listing]:
        rows = data if isinstance(data, list) else (
            data.get("data") or data.get("results") or data.get("properties") or []
        )
        # Normalize JSON keys onto our logical field names.
        out: List[Listing] = []
        for i, raw in enumerate(rows):
            if not isinstance(raw, dict):
                continue
            rec = {}
            for k, v in raw.items():
                field = _match_field(str(k))
                if field and field not in rec:
                    rec[field] = v
            # Preserve a few passthrough keys if present verbatim.
            for key in ("zip", "city", "state"):
                if key in raw:
                    rec[key] = raw[key]
            listing = self._row_to_listing(rec, i)
            if listing:
                out.append(listing)
        return out

    def _parse_html(self, body: str) -> List[Listing]:
        parser = _TableParser()
        parser.feed(body)
        out: List[Listing] = []
        idx = 0
        for table in parser.tables:
            if len(table) < 2:
                continue
            header = table[0]
            col_field = {c: _match_field(h) for c, h in enumerate(header)}
            if "min_bid" not in col_field.values():
                continue  # not a bid-sheet table
            for row in table[1:]:
                rec = {}
                for c, cell in enumerate(row):
                    field = col_field.get(c)
                    if field and field not in rec:
                        rec[field] = cell
                listing = self._row_to_listing(rec, idx)
                if listing:
                    out.append(listing)
                    idx += 1
        return out

    # -- public API --------------------------------------------------------
    def search_listings(
        self,
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
    ) -> List[Listing]:
        # property_type filter: MVBA yields land, so a residential-only filter
        # legitimately returns nothing.
        if property_type and property_type != "land":
            return []
        body, ctype = self._fetch()
        listings = self._parse(body, ctype)
        out = []
        for l in listings:
            if max_price is not None and l.price > max_price:
                continue
            if zip_code and l.location.zip_code and l.location.zip_code != zip_code:
                continue
            out.append(l)
        return out

    def rental_comps(
        self,
        zip_code: Optional[str] = None,
        property_type: Optional[str] = None,
    ) -> List[RentalComp]:
        # MVBA tax sales carry no rental data.
        return []
