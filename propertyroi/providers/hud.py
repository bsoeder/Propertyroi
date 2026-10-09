"""HUD Fair Market Rents provider (free government rental data).

HUD publishes Fair Market Rents (FMR) — the 40th-percentile gross rent by area
and bedroom count — through a free REST API. It is an official, nationwide,
no-cost source of *rental* data (not for-sale listings), which makes it a great
free baseline for the rent estimator and for the long-term-rent input the STR
engine uses.

Get a free token at https://www.huduser.gov/portal/dataset/fmr-api.html and set
it as HUD_API_TOKEN. This provider turns the per-bedroom FMR figures for a ZIP
into synthetic rental comps (with representative sizes) that the comps estimator
can weigh like any other comps. It returns no for-sale listings, so combine it
with a listings source, e.g. ``--provider mvba,hud`` or ``rentcast,hud``.

Only the standard library is used.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import List, Optional

from ..models import Listing, Location, RentalComp
from .base import DataProvider

_BASE = "https://www.huduser.gov/hudapi/public/fmr/data"

# FMR bedroom buckets -> (beds, baths, representative sqft) for the comp.
_BUCKETS = [
    ("Efficiency", 0, 1.0, 500),
    ("One-Bedroom", 1, 1.0, 700),
    ("Two-Bedroom", 2, 1.5, 1000),
    ("Three-Bedroom", 3, 2.0, 1300),
    ("Four-Bedroom", 4, 2.5, 1600),
]

# Alternate key spellings seen in the API across versions.
_ALT_KEYS = {
    "Efficiency": ("Efficiency", "efficiency"),
    "One-Bedroom": ("One-Bedroom", "one-bedroom", "OneBedroom"),
    "Two-Bedroom": ("Two-Bedroom", "two-bedroom", "TwoBedroom"),
    "Three-Bedroom": ("Three-Bedroom", "three-bedroom", "ThreeBedroom"),
    "Four-Bedroom": ("Four-Bedroom", "four-bedroom", "FourBedroom"),
}


def _num(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


class HudFmrProvider(DataProvider):
    def __init__(
        self,
        token: Optional[str] = None,
        year: Optional[str] = None,
        timeout: float = 20.0,
    ):
        self.token = token or os.environ.get("HUD_API_TOKEN", "")
        if not self.token:
            raise ValueError(
                "HUD API token required (free). Set HUD_API_TOKEN or pass token=... "
                "— register at https://www.huduser.gov/portal/dataset/fmr-api.html"
            )
        self.year = year or os.environ.get("HUD_FMR_YEAR", "")
        self.timeout = timeout

    # -- fetch (mockable in tests) -----------------------------------------
    def _get(self, zip_code: str) -> dict:
        url = f"{_BASE}/{zip_code}"
        if self.year:
            url += f"?year={self.year}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    @staticmethod
    def _basicdata(payload: dict, zip_code: str) -> Optional[dict]:
        data = (payload or {}).get("data") or {}
        bd = data.get("basicdata")
        if isinstance(bd, dict):
            return bd
        if isinstance(bd, list) and bd:
            # Small-area FMR can return a list; prefer the entry for this ZIP.
            for row in bd:
                if isinstance(row, dict) and str(row.get("zip_code")) == str(zip_code):
                    return row
            return bd[0] if isinstance(bd[0], dict) else None
        return None

    @staticmethod
    def _rent_for(bd: dict, canonical: str) -> Optional[float]:
        for key in _ALT_KEYS[canonical]:
            if key in bd:
                v = _num(bd[key])
                if v is not None:
                    return v
        return None

    # -- public API --------------------------------------------------------
    def search_listings(
        self,
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
    ) -> List[Listing]:
        # HUD FMR is rental data only; it has no for-sale listings.
        return []

    def rental_comps(
        self,
        zip_code: Optional[str] = None,
        property_type: Optional[str] = None,
    ) -> List[RentalComp]:
        if not zip_code:
            return []
        bd = self._basicdata(self._get(zip_code), zip_code)
        if not bd:
            return []
        ptype = property_type or "single_family"
        out: List[RentalComp] = []
        for canonical, beds, baths, sqft in _BUCKETS:
            rent = self._rent_for(bd, canonical)
            if rent is None or rent <= 0:
                continue
            out.append(
                RentalComp(
                    id=f"FMR-{zip_code}-{beds}br",
                    location=Location(
                        zip_code=str(zip_code),
                        county=str(bd.get("county_name") or ""),
                        state=str(bd.get("statename") or bd.get("state") or ""),
                    ),
                    monthly_rent=rent,
                    beds=beds,
                    baths=baths,
                    sqft=sqft,
                    property_type=ptype,
                    address=f"HUD FMR {canonical} ({zip_code})",
                )
            )
        return out
