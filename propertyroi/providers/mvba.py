"""MVBA delinquent-tax land/property sale provider (live HTTP fetch).

MVBA (McCreary, Veselka, Bragg & Allen, P.C.) runs Texas delinquent property
*tax sales* and publishes them at mvbalaw.com/tax-sales/. That page is a
**county index**: each upcoming sale links to a per-county **bid sheet** (usually
a PDF) whose rows are the individual tracts — often raw land — with fields like
county, account/cause number, legal description (acreage), situs address,
*adjudged value*, and *minimum bid*.

This provider fetches a URL you point it at and adapts to what it finds:

* a **bid sheet** — an HTML ``<table>``, a JSON feed, or a **PDF** — is parsed
  into land ``Listing``s (``source="mvba"`` / ``property_type="land"``); or
* an **index page** (like ``/tax-sales/``) is crawled: it follows the county
  bid-sheet links and parses each one.

Columns are mapped by fuzzy header name so the same code handles counties whose
sheets differ slightly. Listings carry no rental comps.

    export MVBA_SALES_URL="https://mvbalaw.com/tax-sales/"
    python -m propertyroi scan --provider mvba

PDF bid sheets require the optional ``pdfplumber`` dependency
(``pip install pdfplumber``); it is imported lazily, so HTML/JSON sources work
without it. Everything else uses only the standard library.
"""

from __future__ import annotations

import io
import json
import os
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import List, Optional

from ..models import Listing, Location, RentalComp
from .base import DataProvider

_ACRE_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:ac\b|acre)", re.IGNORECASE)
_NUM_RE = re.compile(r"[-+]?[\d,]+(?:\.\d+)?")
_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


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


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


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


def _match_field(header: str) -> Optional[str]:
    h = _normalize(header)
    for field, keys in _FIELD_KEYWORDS:
        if any(k in h for k in keys):
            return field
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


class MvbaProvider(DataProvider):
    def __init__(
        self,
        url: Optional[str] = None,
        timeout: float = 25.0,
        crawl: bool = True,
        max_sheets: int = 40,
    ):
        self.url = url or os.environ.get("MVBA_SALES_URL", "")
        if not self.url:
            raise ValueError(
                "MVBA source URL required. Set MVBA_SALES_URL or pass url=... "
                "(e.g. https://mvbalaw.com/tax-sales/ or a county bid sheet)."
            )
        self.timeout = timeout
        self.crawl = crawl
        self.max_sheets = max_sheets

    # -- fetch (mockable in tests) -----------------------------------------
    def _fetch(self, url: Optional[str] = None) -> tuple:
        """Return (raw_bytes, content_type) for a URL."""
        target = url or self.url
        req = urllib.request.Request(
            target, headers={"Accept": "application/json, text/html, application/pdf"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            data = resp.read()
        return data, ctype

    # -- dispatch ----------------------------------------------------------
    @staticmethod
    def _is_pdf(data: bytes, ctype: str, url: str) -> bool:
        return (
            "pdf" in ctype.lower()
            or url.lower().split("?")[0].endswith(".pdf")
            or data[:5] == b"%PDF-"
        )

    def _parse(self, data: bytes, ctype: str, url: str, allow_crawl: bool) -> List[Listing]:
        if self._is_pdf(data, ctype, url):
            return self._parse_pdf(data, url)
        text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
        stripped = text.lstrip()
        if "json" in ctype.lower() or stripped[:1] in ("{", "["):
            return self._parse_json(json.loads(text), url)
        # HTML: first try to read a bid table on this page itself.
        listings = self._parse_html(text, url)
        if listings or not allow_crawl:
            return listings
        # Otherwise treat it as a county index and crawl the bid-sheet links.
        return self._crawl_index(text, url)

    # -- shared table row mapping ------------------------------------------
    def _row_to_listing(self, rec: dict, idx: int, url: str) -> Optional[Listing]:
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
            url=url,
        )

    def _ingest_table(self, table: List[List], out: List[Listing], idx: int, url: str) -> int:
        """Map one header+rows table into land listings, appended to `out`."""
        if len(table) < 2:
            return idx
        header = table[0]
        col_field = {c: _match_field(h) for c, h in enumerate(header)}
        if "min_bid" not in col_field.values():
            return idx  # not a bid-sheet table
        for row in table[1:]:
            rec = {}
            for c, cell in enumerate(row):
                field = col_field.get(c)
                if field and field not in rec and cell not in (None, ""):
                    rec[field] = cell
            listing = self._row_to_listing(rec, idx, url)
            if listing:
                out.append(listing)
                idx += 1
        return idx

    # -- per-format parsers ------------------------------------------------
    def _parse_json(self, data, url: str) -> List[Listing]:
        rows = data if isinstance(data, list) else (
            data.get("data") or data.get("results") or data.get("properties") or []
        )
        out: List[Listing] = []
        for i, raw in enumerate(rows):
            if not isinstance(raw, dict):
                continue
            rec = {}
            for k, v in raw.items():
                field = _match_field(str(k))
                if field and field not in rec:
                    rec[field] = v
            for key in ("zip", "city", "state"):
                if key in raw:
                    rec[key] = raw[key]
            listing = self._row_to_listing(rec, i, url)
            if listing:
                out.append(listing)
        return out

    def _parse_html(self, body: str, url: str) -> List[Listing]:
        parser = _TableParser()
        parser.feed(body)
        out: List[Listing] = []
        idx = 0
        for table in parser.tables:
            idx = self._ingest_table(table, out, idx, url)
        return out

    def _parse_pdf(self, data: bytes, url: str) -> List[Listing]:
        try:
            import pdfplumber  # optional dependency
        except ImportError as e:
            raise ValueError(
                "This MVBA source is a PDF bid sheet. Install pdfplumber "
                "(pip install pdfplumber) to parse PDF sources."
            ) from e
        out: List[Listing] = []
        idx = 0
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                for table in (page.extract_tables() or []):
                    # Normalize None cells to "" so mapping is uniform.
                    norm = [[("" if c is None else str(c)) for c in row] for row in table]
                    idx = self._ingest_table(norm, out, idx, url)
        return out

    # -- index crawling ----------------------------------------------------
    def _bid_sheet_links(self, html: str, base: str) -> List[str]:
        """Absolute URLs on an index page that look like county bid sheets."""
        seen = set()
        links: List[str] = []
        for href in _HREF_RE.findall(html):
            absu = urllib.parse.urljoin(base, href)
            low = absu.lower()
            if absu == base or absu.rstrip("/") == base.rstrip("/"):
                continue
            if (
                low.split("?")[0].endswith(".pdf")
                or "taxupload" in low
                or "bidsheet" in low
                or "bid-sheet" in low
                or ("tax" in low and "sale" in low and low != base.lower())
            ):
                if absu not in seen:
                    seen.add(absu)
                    links.append(absu)
        return links[: self.max_sheets]

    def _crawl_index(self, html: str, base: str) -> List[Listing]:
        out: List[Listing] = []
        for link in self._bid_sheet_links(html, base):
            try:
                data, ctype = self._fetch(link)
                # Do not recurse into further indexes (allow_crawl=False).
                out.extend(self._parse(data, ctype, link, allow_crawl=False))
            except Exception:
                continue  # skip a broken/blocked sheet, keep the rest
        return out

    # -- public API --------------------------------------------------------
    def search_listings(
        self,
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
    ) -> List[Listing]:
        if property_type and property_type != "land":
            return []
        data, ctype = self._fetch()
        listings = self._parse(data, ctype, self.url, allow_crawl=self.crawl)
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
