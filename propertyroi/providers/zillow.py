"""Zillow data provider (via RapidAPI).

Zillow does not offer a free public listings API — its old public API was
retired, and scraping zillow.com directly violates its Terms of Service and is
actively blocked. The supported way to get Zillow data programmatically is
through a third-party RapidAPI marketplace endpoint that mirrors it. This
provider targets the widely used "zillow-com1" RapidAPI host by default; the host
is configurable so you can point it at whichever Zillow RapidAPI listing you have
subscribed to.

Requires an API key. Set RAPIDAPI_KEY (or pass api_key=...). Never used by
default — the CLI falls back to bundled sample data unless you select it.

    export RAPIDAPI_KEY=your_key
    python -m propertyroi scan --zip 78704 --provider zillow

Only stdlib networking (urllib) is used, so there are no extra dependencies.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import List, Optional

from ..models import Listing, Location, RentalComp
from .base import DataProvider


class ZillowProvider(DataProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        host: Optional[str] = None,
        timeout: float = 25.0,
    ):
        self.api_key = api_key or os.environ.get("RAPIDAPI_KEY", "")
        if not self.api_key:
            raise ValueError(
                "RapidAPI key required for Zillow. Set RAPIDAPI_KEY or pass api_key=..."
            )
        # Override with ZILLOW_RAPIDAPI_HOST if you subscribed to a different one.
        self.host = host or os.environ.get("ZILLOW_RAPIDAPI_HOST", "zillow-com1.p.rapidapi.com")
        self.timeout = timeout

    def _get(self, path: str, params: dict) -> dict:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"https://{self.host}/{path}?{qs}"
        req = urllib.request.Request(
            url,
            headers={
                "X-RapidAPI-Key": self.api_key,
                "X-RapidAPI-Host": self.host,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    @staticmethod
    def _map_type(t: Optional[str]) -> str:
        t = (t or "").lower()
        if "condo" in t:
            return "condo"
        if "town" in t:
            return "townhouse"
        if "multi" in t or "duplex" in t or "apartment" in t:
            return "multi_family"
        return "single_family"

    @staticmethod
    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _search(self, zip_code, status_type, home_type=None) -> List[dict]:
        """Call propertyExtendedSearch and return the raw prop dicts."""
        data = self._get(
            "propertyExtendedSearch",
            {
                "location": zip_code,
                "status_type": status_type,   # "ForSale" | "ForRent"
                "home_type": home_type,       # e.g. "Houses" (optional)
            },
        )
        props = data.get("props") or data.get("results") or []
        return props if isinstance(props, list) else []

    def search_listings(
        self,
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
    ) -> List[Listing]:
        rows = self._search(zip_code, "ForSale")
        out: List[Listing] = []
        for r in rows:
            price = self._num(r.get("price"))
            if price is None:
                continue
            if max_price is not None and price > max_price:
                continue
            beds = int(self._num(r.get("bedrooms")) or 0)
            if min_beds is not None and beds < min_beds:
                continue
            ptype = self._map_type(r.get("propertyType") or r.get("homeType"))
            if property_type and ptype != property_type:
                continue
            sqft = int(self._num(r.get("livingArea") or r.get("area")) or 0)
            out.append(
                Listing(
                    id=str(r.get("zpid") or r.get("id") or r.get("address")),
                    location=Location(
                        zip_code=str(r.get("zipcode") or zip_code or ""),
                        city=r.get("city", ""),
                        state=r.get("state", ""),
                        latitude=self._num(r.get("latitude")),
                        longitude=self._num(r.get("longitude")),
                    ),
                    price=price,
                    beds=beds,
                    baths=self._num(r.get("bathrooms")) or 0.0,
                    sqft=sqft,
                    property_type=ptype,
                    year_built=r.get("yearBuilt"),
                    address=r.get("address", ""),
                    url=(f"https://www.zillow.com/homedetails/{r.get('zpid')}_zpid/"
                         if r.get("zpid") else ""),
                )
            )
        return out

    def rental_comps(
        self,
        zip_code: Optional[str] = None,
        property_type: Optional[str] = None,
    ) -> List[RentalComp]:
        rows = self._search(zip_code, "ForRent")
        out: List[RentalComp] = []
        for r in rows:
            rent = self._num(r.get("price"))
            sqft = int(self._num(r.get("livingArea") or r.get("area")) or 0)
            if not rent or sqft <= 0:
                continue
            ptype = self._map_type(r.get("propertyType") or r.get("homeType"))
            if property_type and ptype != property_type:
                continue
            out.append(
                RentalComp(
                    id=str(r.get("zpid") or r.get("id") or r.get("address")),
                    location=Location(
                        zip_code=str(r.get("zipcode") or zip_code or ""),
                        city=r.get("city", ""),
                        state=r.get("state", ""),
                        latitude=self._num(r.get("latitude")),
                        longitude=self._num(r.get("longitude")),
                    ),
                    monthly_rent=rent,
                    beds=int(self._num(r.get("bedrooms")) or 0),
                    baths=self._num(r.get("bathrooms")) or 0.0,
                    sqft=sqft,
                    property_type=ptype,
                    address=r.get("address", ""),
                )
            )
        return out
