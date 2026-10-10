"""CSV file provider — load real listings with no API key.

Redfin and Realtor.com both let you **download your search results as a CSV**
for free from their website (Redfin: the "Download All" link under a search).
This provider reads such a CSV so you can analyze real for-sale listings with no
API key at all. Columns are mapped by fuzzy header name, so Redfin's export works
out of the box and other exports usually do too.

It supplies for-sale listings only (no rental comps), so pair it with a rentals
source for rent estimates, e.g. ``--provider csv,hud``.

Set the file path with PROPERTYROI_CSV (or pass path=...).
"""

from __future__ import annotations

import csv
import os
import re
from typing import List, Optional

from ..models import Listing, Location, RentalComp
from .base import DataProvider


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _num(v) -> Optional[float]:
    if v is None:
        return None
    m = re.search(r"[-+]?[\d,]+(?:\.\d+)?", str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


# Logical field -> normalized header keywords. Matching is exact-first (so
# "propertytype" beats the substring "type" in "saletype"), then substring for
# any columns/fields still unmapped.
_FIELDS = [
    ("price", ("price", "listprice", "currentprice")),
    ("beds", ("beds", "bedrooms")),
    ("baths", ("baths", "bathrooms")),
    ("sqft", ("squarefeet", "sqft", "livingarea", "buildingsize")),
    ("zip", ("ziporpostalcode", "zipcode", "zip", "postalcode")),
    ("city", ("city",)),
    ("state", ("stateorprovince", "state", "statecode")),
    ("address", ("address", "line", "streetaddress")),
    ("property_type", ("propertytype", "proptype", "type")),
    ("year_built", ("yearbuilt",)),
    ("hoa", ("hoamonth", "hoamonthly", "hoa")),
    ("lat", ("latitude",)),
    ("lon", ("longitude", "lng")),
    ("url", ("url", "listingurl")),
    ("id", ("mls", "mlsnumber", "listingid", "propertyid")),
]


def _map_type(t: Optional[str]) -> str:
    t = (t or "").lower()
    if "condo" in t or "co-op" in t or "coop" in t:
        return "condo"
    if "town" in t:
        return "townhouse"
    if "multi" in t or "duplex" in t or "2-4" in t or "apartment" in t:
        return "multi_family"
    if "land" in t or "lot" in t:
        return "land"
    return "single_family"


class CsvProvider(DataProvider):
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get("PROPERTYROI_CSV", "")
        if not self.path:
            raise ValueError(
                "CSV path required. Set PROPERTYROI_CSV or pass path=... "
                "(e.g. a Redfin/Realtor 'Download All' export)."
            )
        if not os.path.exists(self.path):
            raise ValueError(f"CSV file not found: {self.path}")
        self._listings = self._load()

    def _header_map(self, header: List[str]) -> dict:
        norm = [_normalize(c) for c in header]
        col_field: dict = {}
        used = set()

        def assign(match):
            for i, n in enumerate(norm):
                if i in col_field:
                    continue
                for field, keys in _FIELDS:
                    if field in used:
                        continue
                    if match(n, keys):
                        col_field[i] = field
                        used.add(field)
                        break

        assign(lambda n, keys: any(k == n for k in keys))         # exact first
        assign(lambda n, keys: any(k in n for k in keys))         # then substring
        return col_field

    def _load(self) -> List[Listing]:
        out: List[Listing] = []
        with open(self.path, newline="", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            return out
        # Find the header row (the one that maps a price column).
        header_idx = 0
        for i, row in enumerate(rows[:5]):
            cm = self._header_map(row)
            if "price" in cm.values():
                header_idx = i
                break
        col_field = self._header_map(rows[header_idx])
        for n, row in enumerate(rows[header_idx + 1:]):
            rec = {}
            for i, cell in enumerate(row):
                field = col_field.get(i)
                if field and field not in rec and cell not in (None, ""):
                    rec[field] = cell
            price = _num(rec.get("price"))
            if price is None or price <= 0:
                continue
            out.append(
                Listing(
                    id=str(rec.get("id") or rec.get("address") or f"CSV-{n}"),
                    location=Location(
                        zip_code=str(rec.get("zip") or "").split("-")[0].strip(),
                        city=str(rec.get("city") or ""),
                        state=str(rec.get("state") or ""),
                        latitude=_num(rec.get("lat")),
                        longitude=_num(rec.get("lon")),
                    ),
                    price=price,
                    beds=int(_num(rec.get("beds")) or 0),
                    baths=_num(rec.get("baths")) or 0.0,
                    sqft=int(_num(rec.get("sqft")) or 0),
                    property_type=_map_type(rec.get("property_type")),
                    year_built=int(_num(rec.get("year_built"))) if _num(rec.get("year_built")) else None,
                    address=str(rec.get("address") or ""),
                    hoa_monthly=_num(rec.get("hoa")) or 0.0,
                    url=str(rec.get("url") or ""),
                    source="csv",
                )
            )
        return out

    def search_listings(
        self,
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
    ) -> List[Listing]:
        out = []
        for l in self._listings:
            if zip_code and l.location.zip_code != zip_code:
                continue
            if max_price is not None and l.price > max_price:
                continue
            if min_beds is not None and l.beds < min_beds:
                continue
            if property_type and l.property_type != property_type:
                continue
            out.append(l)
        return out

    def rental_comps(
        self,
        zip_code: Optional[str] = None,
        property_type: Optional[str] = None,
    ) -> List[RentalComp]:
        # A for-sale CSV has no rental data; pair with hud for rents.
        return []
