"""Realtor.com data provider (via RapidAPI).

Realtor.com has no free public API, and scraping realtor.com directly violates
its Terms of Service. The supported way to get its data programmatically is
through a third-party RapidAPI marketplace endpoint. This provider targets the
widely used "us-real-estate" RapidAPI host by default; both the host and the
endpoint paths are configurable so you can adapt it to whichever Realtor.com
RapidAPI listing you subscribed to (their response shapes differ).

Requires an API key. Set RAPIDAPI_KEY (or pass api_key=...). Never used by
default.

    export RAPIDAPI_KEY=your_key
    python -m propertyroi scan --zip 78704 --provider realtor

Only stdlib networking (urllib) is used. Response parsing is defensive: it walks
several common nesting shapes so minor schema differences do not break it.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import List, Optional

from ..models import Listing, Location, RentalComp
from .base import DataProvider


class RealtorProvider(DataProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        host: Optional[str] = None,
        sale_path: Optional[str] = None,
        rent_path: Optional[str] = None,
        timeout: float = 25.0,
    ):
        self.api_key = api_key or os.environ.get("RAPIDAPI_KEY", "")
        if not self.api_key:
            raise ValueError(
                "RapidAPI key required for Realtor. Set RAPIDAPI_KEY or pass api_key=..."
            )
        self.host = host or os.environ.get("REALTOR_RAPIDAPI_HOST", "us-real-estate.p.rapidapi.com")
        self.sale_path = sale_path or os.environ.get("REALTOR_SALE_PATH", "v2/for-sale")
        self.rent_path = rent_path or os.environ.get("REALTOR_RENT_PATH", "v2/for-rent")
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
    def _results(data: dict) -> List[dict]:
        """Walk the common Realtor.com RapidAPI nesting shapes to the results list."""
        if not isinstance(data, dict):
            return data if isinstance(data, list) else []
        for path in (
            ("data", "home_search", "results"),
            ("data", "results"),
            ("home_search", "results"),
            ("properties",),
            ("listings",),
            ("results",),
            ("data",),
        ):
            node = data
            ok = True
            for key in path:
                if isinstance(node, dict) and key in node:
                    node = node[key]
                else:
                    ok = False
                    break
            if ok and isinstance(node, list):
                return node
        return []

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

    def _extract_common(self, r: dict):
        """Pull shared fields from a result dict across schema variants."""
        desc = r.get("description") or {}
        loc = r.get("location") or {}
        addr = loc.get("address") or r.get("address") or {}
        coord = addr.get("coordinate") or r.get("coordinate") or {}

        beds = self._num(desc.get("beds") if desc else r.get("beds"))
        baths = self._num(desc.get("baths") if desc else r.get("baths"))
        sqft = self._num(desc.get("sqft") if desc else r.get("sqft") or r.get("building_size"))
        ptype = desc.get("type") if desc else r.get("prop_type") or r.get("type")
        year = desc.get("year_built") if desc else r.get("year_built")

        zip_code = str(addr.get("postal_code") or r.get("postal_code") or "")
        city = addr.get("city") or ""
        state = addr.get("state_code") or addr.get("state") or ""
        line = addr.get("line") or r.get("address_line") or ""

        return {
            "id": str(r.get("property_id") or r.get("listing_id") or r.get("id") or line),
            "beds": int(beds or 0),
            "baths": baths or 0.0,
            "sqft": int(sqft or 0),
            "ptype": self._map_type(ptype),
            "year": year,
            "location": Location(
                zip_code=zip_code,
                city=city,
                state=state,
                latitude=self._num(coord.get("lat")),
                longitude=self._num(coord.get("lon")),
            ),
            "address": line,
            "url": r.get("href") or r.get("rdc_web_url") or "",
        }

    def search_listings(
        self,
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
    ) -> List[Listing]:
        data = self._get(self.sale_path, {
            "zipcode": zip_code, "postal_code": zip_code,
            "limit": 100, "offset": 0, "sort": "newest",
        })
        out: List[Listing] = []
        for r in self._results(data):
            c = self._extract_common(r)
            price = self._num(
                (r.get("list_price"))
                or (r.get("price"))
                or ((r.get("description") or {}).get("list_price"))
            )
            if price is None:
                continue
            if max_price is not None and price > max_price:
                continue
            if min_beds is not None and c["beds"] < min_beds:
                continue
            if property_type and c["ptype"] != property_type:
                continue
            out.append(
                Listing(
                    id=c["id"], location=c["location"], price=price,
                    beds=c["beds"], baths=c["baths"], sqft=c["sqft"],
                    property_type=c["ptype"], year_built=c["year"],
                    address=c["address"], url=c["url"],
                )
            )
        return out

    def rental_comps(
        self,
        zip_code: Optional[str] = None,
        property_type: Optional[str] = None,
    ) -> List[RentalComp]:
        data = self._get(self.rent_path, {
            "zipcode": zip_code, "postal_code": zip_code,
            "limit": 100, "offset": 0, "sort": "newest",
        })
        out: List[RentalComp] = []
        for r in self._results(data):
            c = self._extract_common(r)
            rent = self._num(
                r.get("list_price")
                or r.get("price")
                or ((r.get("description") or {}).get("list_price"))
            )
            if not rent or c["sqft"] <= 0:
                continue
            if property_type and c["ptype"] != property_type:
                continue
            out.append(
                RentalComp(
                    id=c["id"], location=c["location"], monthly_rent=rent,
                    beds=c["beds"], baths=c["baths"], sqft=c["sqft"],
                    property_type=c["ptype"], address=c["address"],
                )
            )
        return out
