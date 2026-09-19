"""RentCast API provider (optional, real data).

This shows how to plug a live real-estate data source into PropertyROI. RentCast
(https://www.rentcast.io) exposes sale listings and long-term rental listings
that map cleanly onto our models. It requires an API key, so this provider is
never used by default — the CLI falls back to the bundled sample data unless you
explicitly select it and set RENTCAST_API_KEY.

Only stdlib networking is used (urllib), so there are no extra dependencies. If
the network is unavailable the provider raises a clear error rather than
silently returning nothing.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import List, Optional

from ..models import Listing, Location, RentalComp
from .base import DataProvider

_BASE = "https://api.rentcast.io/v1"


class RentCastProvider(DataProvider):
    def __init__(self, api_key: Optional[str] = None, timeout: float = 20.0):
        self.api_key = api_key or os.environ.get("RENTCAST_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "RentCast API key required. Set RENTCAST_API_KEY or pass api_key=..."
            )
        self.timeout = timeout

    def _get(self, path: str, params: dict) -> list:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{_BASE}/{path}?{qs}"
        req = urllib.request.Request(url, headers={"X-Api-Key": self.api_key, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode())
        return data if isinstance(data, list) else data.get("data", data)

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

    def search_listings(
        self,
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
    ) -> List[Listing]:
        rows = self._get("listings/sale", {"zipCode": zip_code, "limit": 100, "status": "Active"})
        out: List[Listing] = []
        for r in rows:
            price = r.get("price")
            if price is None:
                continue
            if max_price is not None and price > max_price:
                continue
            beds = int(r.get("bedrooms") or 0)
            if min_beds is not None and beds < min_beds:
                continue
            ptype = self._map_type(r.get("propertyType"))
            if property_type and ptype != property_type:
                continue
            out.append(
                Listing(
                    id=str(r.get("id") or r.get("formattedAddress")),
                    location=Location(
                        zip_code=str(r.get("zipCode") or zip_code or ""),
                        city=r.get("city", ""),
                        state=r.get("state", ""),
                        latitude=r.get("latitude"),
                        longitude=r.get("longitude"),
                    ),
                    price=float(price),
                    beds=beds,
                    baths=float(r.get("bathrooms") or 0),
                    sqft=int(r.get("squareFootage") or 0),
                    property_type=ptype,
                    year_built=r.get("yearBuilt"),
                    address=r.get("formattedAddress", ""),
                    property_tax_annual=(r.get("taxAssessments") or {}).get("annualAmount")
                    if isinstance(r.get("taxAssessments"), dict) else None,
                )
            )
        return out

    def rental_comps(
        self,
        zip_code: Optional[str] = None,
        property_type: Optional[str] = None,
    ) -> List[RentalComp]:
        rows = self._get("listings/rental/long-term", {"zipCode": zip_code, "limit": 100, "status": "Active"})
        out: List[RentalComp] = []
        for r in rows:
            rent = r.get("price")
            sqft = r.get("squareFootage")
            if not rent or not sqft:
                continue
            ptype = self._map_type(r.get("propertyType"))
            if property_type and ptype != property_type:
                continue
            out.append(
                RentalComp(
                    id=str(r.get("id") or r.get("formattedAddress")),
                    location=Location(
                        zip_code=str(r.get("zipCode") or zip_code or ""),
                        city=r.get("city", ""),
                        state=r.get("state", ""),
                        latitude=r.get("latitude"),
                        longitude=r.get("longitude"),
                    ),
                    monthly_rent=float(rent),
                    beds=int(r.get("bedrooms") or 0),
                    baths=float(r.get("bathrooms") or 0),
                    sqft=int(sqft),
                    property_type=ptype,
                    address=r.get("formattedAddress", ""),
                )
            )
        return out
