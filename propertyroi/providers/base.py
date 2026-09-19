"""Data provider interface.

A provider supplies two things the analyzer needs:
  * listings that are for sale, and
  * rental comps used to estimate rent.

Concrete providers implement these against a data source: bundled sample JSON,
a local file, or a real estate API (Zillow/RentCast/Realtor/etc.). Keeping this
behind an interface lets the rest of the app stay source-agnostic and lets the
accuracy tester swap in fixtures.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import Listing, RentalComp


class DataProvider(ABC):
    @abstractmethod
    def search_listings(
        self,
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
    ) -> List[Listing]:
        """Return for-sale listings matching the given filters."""

    @abstractmethod
    def rental_comps(
        self,
        zip_code: Optional[str] = None,
        property_type: Optional[str] = None,
    ) -> List[RentalComp]:
        """Return rental comps usable for estimating rent in the area."""
