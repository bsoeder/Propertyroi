"""Nationwide ZIP-level ROI rankings.

Ranks ZIP codes by rental ROI using two market inputs per ZIP: a typical home
value and a typical monthly rent. Gross yield (annual rent / price) and an
estimated cap rate (applying the long-term expense assumptions) are the core
signals — the ZIPs where rents are high relative to prices rise to the top.

Data comes from a CSV with columns: zip, city, state, metro, median_price,
median_rent (plus optional as_of). The bundled ``data/zip_market_stats.csv`` is
a representative snapshot so the rankings work out of the box;
``scripts/refresh_rankings.py`` rebuilds it from free national sources — Zillow's
ZHVI research CSV (home values) and HUD Fair Market Rents (rents).

This ranks *markets*, not individual deals — it's where to look, not what to buy.
"""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass
from typing import List, Optional

from .analyzer import Assumptions

_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "zip_market_stats.csv")


@dataclass
class ZipRanking:
    zip_code: str
    city: str
    state: str
    metro: str
    median_price: float
    median_rent: float      # monthly
    gross_yield: float      # annual rent / price
    cap_rate: float         # NOI / price (using long-term expense assumptions)
    rent_to_price: float    # monthly rent / price (the "1% rule" number)
    monthly_cash_flow: float  # at a standard financing assumption
    score: float            # 0..100
    as_of: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("gross_yield", "cap_rate", "rent_to_price"):
            d[k] = round(d[k], 4)
        d["median_price"] = round(self.median_price, 2)
        d["median_rent"] = round(self.median_rent, 2)
        d["monthly_cash_flow"] = round(self.monthly_cash_flow, 2)
        d["score"] = round(self.score, 1)
        return d


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class RankingEngine:
    def __init__(self, path: Optional[str] = None, assumptions: Optional[Assumptions] = None):
        self.path = path or os.environ.get("PROPERTYROI_RANKINGS", _DATA)
        self.assumptions = assumptions or Assumptions()
        self.rows = self._load()

    def _load(self) -> List[dict]:
        out = []
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                try:
                    price = float(str(r["median_price"]).replace(",", "").replace("$", ""))
                    rent = float(str(r["median_rent"]).replace(",", "").replace("$", ""))
                except (KeyError, ValueError):
                    continue
                if price <= 0 or rent <= 0:
                    continue
                out.append({
                    "zip": str(r.get("zip") or r.get("zip_code") or "").strip(),
                    "city": (r.get("city") or "").strip(),
                    "state": (r.get("state") or "").strip(),
                    "metro": (r.get("metro") or "").strip(),
                    "price": price, "rent": rent,
                    "as_of": (r.get("as_of") or "").strip(),
                })
        return out

    def _rank_row(self, r: dict) -> ZipRanking:
        a = self.assumptions
        price, rent = r["price"], r["rent"]
        gross_annual = rent * 12
        eff = gross_annual * (1 - a.vacancy_rate)
        opex = eff * a.operating_expense_ratio + price * a.property_tax_rate
        noi = eff - opex
        # Standard financing for a comparable cash-flow signal across ZIPs.
        from .analyzer import monthly_mortgage_payment
        loan = price * (1 - a.down_payment_pct)
        debt = monthly_mortgage_payment(loan, a.mortgage_rate, a.loan_term_years) * 12
        cash_flow_month = (noi - debt) / 12

        gross_yield = gross_annual / price
        cap_rate = noi / price
        rent_to_price = rent / price
        # Score: gross yield dominates (10% -> full marks), with a cap-rate blend.
        score = 100.0 * (0.7 * _clamp(gross_yield / 0.10) + 0.3 * _clamp(cap_rate / 0.07))
        return ZipRanking(
            zip_code=r["zip"], city=r["city"], state=r["state"], metro=r["metro"],
            median_price=price, median_rent=rent, gross_yield=gross_yield,
            cap_rate=cap_rate, rent_to_price=rent_to_price,
            monthly_cash_flow=cash_flow_month, score=score, as_of=r["as_of"],
        )

    def rank(
        self,
        limit: Optional[int] = 25,
        state: Optional[str] = None,
        metro: Optional[str] = None,
        max_price: Optional[float] = None,
        min_price: Optional[float] = None,
    ) -> List[ZipRanking]:
        rows = self.rows
        if state:
            rows = [r for r in rows if r["state"].lower() == state.lower()]
        if metro:
            m = metro.lower()
            rows = [r for r in rows if m in r["metro"].lower()]
        if max_price is not None:
            rows = [r for r in rows if r["price"] <= max_price]
        if min_price is not None:
            rows = [r for r in rows if r["price"] >= min_price]
        ranked = [self._rank_row(r) for r in rows]
        ranked.sort(key=lambda x: x.score, reverse=True)
        return ranked[:limit] if limit else ranked

    def as_of(self) -> str:
        return self.rows[0]["as_of"] if self.rows else ""
