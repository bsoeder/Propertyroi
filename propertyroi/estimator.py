"""Comparable-based rent estimation.

The estimator predicts a subject property's monthly rent from a pool of rental
comps. It is deliberately transparent (no black-box ML): every comp is scored
for similarity to the subject, its rent is adjusted toward the subject's
characteristics, and the final estimate is a similarity-weighted blend. This
makes results explainable and easy to evaluate for accuracy.

Algorithm
---------
1. Filter comps to a candidate set (same property type when possible, beds
   within a tolerance, non-trivial sqft).
2. For each candidate compute a *similarity weight* from feature distance
   (beds, baths, sqft, geographic proximity / same zip).
3. Adjust each comp's rent toward the subject:
     - a sqft component using the comp's rent-per-sqft, and
     - a whole-unit component (the comp's raw rent),
   blended so small sqft gaps do not overpower the estimate.
4. The estimate is the weighted mean of adjusted rents; the low/high band and a
   confidence score come from the weighted spread and the amount of support.
"""

from __future__ import annotations

import math
import statistics
from typing import List, Optional, Sequence

from .models import Listing, RentalComp, RentEstimate, Location


def _haversine_miles(a: Location, b: Location) -> Optional[float]:
    """Great-circle distance in miles, or None if coordinates are missing."""

    if None in (a.latitude, a.longitude, b.latitude, b.longitude):
        return None
    r = 3958.8  # Earth radius, miles
    lat1, lon1, lat2, lon2 = map(
        math.radians, [a.latitude, a.longitude, b.latitude, b.longitude]
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class RentEstimator:
    """Estimate monthly rent for a subject property using rental comps."""

    def __init__(
        self,
        beds_tolerance: int = 1,
        max_distance_miles: float = 5.0,
        min_comps: int = 3,
        sqft_blend: float = 0.6,
    ):
        """
        Parameters
        ----------
        beds_tolerance   : include comps whose bedroom count is within this many
                           of the subject.
        max_distance_miles: when coordinates exist, drop comps farther than this.
        min_comps        : below this many candidates confidence is penalized.
        sqft_blend       : 0..1 weight on the sqft-scaled rent vs. the comp's raw
                           rent when adjusting a comp to the subject.
        """
        self.beds_tolerance = beds_tolerance
        self.max_distance_miles = max_distance_miles
        self.min_comps = min_comps
        self.sqft_blend = sqft_blend

    # -- candidate selection ------------------------------------------------
    def _candidates(self, subject: Listing, comps: Sequence[RentalComp]) -> List[RentalComp]:
        same_zip = subject.location.zip_code
        out: List[RentalComp] = []
        for c in comps:
            if c.sqft <= 0 or c.monthly_rent <= 0:
                continue
            if abs(c.beds - subject.beds) > self.beds_tolerance:
                continue
            dist = _haversine_miles(subject.location, c.location)
            if dist is not None and dist > self.max_distance_miles:
                continue
            # If no coordinates, fall back to same-zip matching. Keep other-zip
            # comps only when we cannot confirm zip (so we never starve the pool).
            if dist is None and c.location.zip_code and same_zip:
                if c.location.zip_code != same_zip:
                    continue
            out.append(c)
        return out

    # -- similarity weight --------------------------------------------------
    def _weight(self, subject: Listing, comp: RentalComp) -> float:
        # Feature distances normalized to roughly comparable scales.
        bed_d = abs(comp.beds - subject.beds)
        bath_d = abs(comp.baths - subject.baths)
        sqft_d = abs(comp.sqft - subject.sqft) / max(subject.sqft, 1)
        type_d = 0.0 if comp.property_type == subject.property_type else 1.0

        geo = _haversine_miles(subject.location, comp.location)
        geo_d = (geo / self.max_distance_miles) if geo is not None else (
            0.0 if comp.location.zip_code == subject.location.zip_code else 0.5
        )

        # Weighted feature distance -> Gaussian-style similarity in (0, 1].
        d = (
            1.0 * bed_d
            + 0.5 * bath_d
            + 2.0 * sqft_d
            + 1.0 * type_d
            + 1.0 * geo_d
        )
        return math.exp(-d)

    # -- per-comp adjustment ------------------------------------------------
    def _adjusted_rent(self, subject: Listing, comp: RentalComp) -> float:
        """Adjust a comp's rent toward the subject's size."""
        rent_per_sqft = comp.monthly_rent / comp.sqft
        sqft_scaled = rent_per_sqft * subject.sqft
        raw = comp.monthly_rent
        # Blend: mostly size-scaled, partly the comp's whole-unit rent so that a
        # single tiny/huge comp cannot dominate via ppsf extrapolation.
        est = self.sqft_blend * sqft_scaled + (1 - self.sqft_blend) * raw
        # Small bedroom nudge: ~4% of rent per bedroom difference.
        est *= 1.0 + 0.04 * (subject.beds - comp.beds)
        return max(est, 0.0)

    # -- public API ---------------------------------------------------------
    def estimate(self, subject: Listing, comps: Sequence[RentalComp]) -> RentEstimate:
        cands = self._candidates(subject, comps)
        if not cands:
            return RentEstimate(
                monthly_rent=0.0,
                low=0.0,
                high=0.0,
                confidence=0.0,
                comps_used=0,
                method="comps",
                notes="No comparable rentals found for subject.",
            )

        weights = [self._weight(subject, c) for c in cands]
        adjusted = [self._adjusted_rent(subject, c) for c in cands]
        wsum = sum(weights) or 1e-9

        point = sum(w * a for w, a in zip(weights, adjusted)) / wsum

        # Weighted standard deviation for the band.
        var = sum(w * (a - point) ** 2 for w, a in zip(weights, adjusted)) / wsum
        std = math.sqrt(var)

        low = max(point - std, 0.0)
        high = point + std

        # Confidence: more comps + tighter spread + closer matches -> higher.
        n = len(cands)
        support = min(1.0, n / max(self.min_comps, 1))
        rel_spread = std / point if point > 0 else 1.0
        tightness = 1.0 / (1.0 + rel_spread)          # 1 when spread is 0
        avg_sim = statistics.mean(weights)            # 0..1
        confidence = max(0.0, min(1.0, 0.5 * support + 0.3 * tightness + 0.2 * avg_sim))

        return RentEstimate(
            monthly_rent=round(point, 2),
            low=round(low, 2),
            high=round(high, 2),
            confidence=round(confidence, 3),
            comps_used=n,
            method="comps",
            notes=f"Weighted blend of {n} comps (sqft_blend={self.sqft_blend}).",
        )
