"""File-backed provider.

Reads listings and rental comps from JSON files. Used for the bundled sample
data set and for any exported real data you drop on disk. This is also what the
CLI uses by default so the whole tool runs with zero network access.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

from ..models import Listing, RentalComp
from .base import DataProvider

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")


class JsonProvider(DataProvider):
    def __init__(
        self,
        listings_path: Optional[str] = None,
        comps_path: Optional[str] = None,
    ):
        self.listings_path = listings_path or os.path.join(_DATA_DIR, "sample_listings.json")
        self.comps_path = comps_path or os.path.join(_DATA_DIR, "sample_comps.json")
        self._listings = self._load_listings()
        self._comps = self._load_comps()

    def _load_listings(self) -> List[Listing]:
        with open(self.listings_path) as f:
            return [Listing.from_dict(d) for d in json.load(f)]

    def _load_comps(self) -> List[RentalComp]:
        with open(self.comps_path) as f:
            return [RentalComp.from_dict(d) for d in json.load(f)]

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
        out = []
        for c in self._comps:
            if zip_code and c.location.zip_code != zip_code:
                continue
            if property_type and c.property_type != property_type:
                continue
            out.append(c)
        return out
