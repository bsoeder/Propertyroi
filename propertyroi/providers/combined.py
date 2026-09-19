"""Combined provider: merge listings and comps from several sources.

Lets you pull for-sale listings and rental comps from Zillow *and* Realtor.com
(and any other provider) at once. Listings are de-duplicated by (zip, address,
price); comps by (zip, address, rent). If one source errors (e.g. a transient
API failure) the others still return, so a single flaky endpoint does not sink
the whole search.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from ..models import Listing, RentalComp
from .base import DataProvider


class CombinedProvider(DataProvider):
    def __init__(self, providers: Sequence[DataProvider], strict: bool = False):
        if not providers:
            raise ValueError("CombinedProvider needs at least one provider.")
        self.providers = list(providers)
        self.strict = strict  # if True, re-raise provider errors instead of skipping

    def _gather(self, method: str, *args, **kwargs) -> list:
        rows: list = []
        for p in self.providers:
            try:
                rows.extend(getattr(p, method)(*args, **kwargs))
            except Exception:
                if self.strict:
                    raise
                # otherwise skip this source and keep going
        return rows

    def search_listings(
        self,
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
    ) -> List[Listing]:
        rows: List[Listing] = self._gather(
            "search_listings",
            zip_code=zip_code, max_price=max_price,
            min_beds=min_beds, property_type=property_type,
        )
        seen = set()
        out: List[Listing] = []
        for l in rows:
            key = (l.location.zip_code, l.address.lower().strip(), round(l.price))
            if key in seen:
                continue
            seen.add(key)
            out.append(l)
        return out

    def rental_comps(
        self,
        zip_code: Optional[str] = None,
        property_type: Optional[str] = None,
    ) -> List[RentalComp]:
        rows: List[RentalComp] = self._gather(
            "rental_comps", zip_code=zip_code, property_type=property_type
        )
        seen = set()
        out: List[RentalComp] = []
        for c in rows:
            key = (c.location.zip_code, c.address.lower().strip(), round(c.monthly_rent))
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out
