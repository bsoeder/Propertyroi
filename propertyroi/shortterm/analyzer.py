"""Short-term rental analysis across multiple strategies.

Given a for-sale listing, the STR analyzer prices it under a chosen strategy (see
:mod:`propertyroi.shortterm.strategies`) and reports the metrics an STR investor
cares about: gross revenue, operating expenses, NOI, cash-on-cash return, cap
rate (for purchases), monthly cash flow, implied ADR / RevPAN, and a composite
STR score with a regulation-risk adjustment.

Revenue comes from one of two sources, best first:
  1. an explicit ADR (average daily rate) + occupancy you supply, or
  2. a fallback: the property's estimated long-term monthly rent (from the
     comps estimator) scaled by the strategy's revenue multiple.

The fallback is a transparent heuristic — flagged with lower confidence — so the
tool is useful before you have AirDNA-grade STR comps. Feed real ADR/occupancy
for a real underwrite.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional

from ..analyzer import monthly_mortgage_payment
from ..estimator import RentEstimator
from ..models import Listing
from ..providers.base import DataProvider
from .strategies import STRATEGIES, StrStrategy, get_strategy

_REG_PENALTY = {"low": 1.0, "medium": 0.9, "high": 0.75}


@dataclass
class StrAssumptions:
    """Global STR financial assumptions (strategy-independent)."""

    mortgage_rate: float = 0.075        # STR purchase loans run a bit higher
    loan_term_years: int = 30
    closing_cost_pct: float = 0.03
    str_insurance_rate: float = 0.008   # annual, as % of price (higher than LTR)
    property_tax_rate: float = 0.011    # fallback when listing has no tax figure
    furnish_per_bed: float = 5000.0     # furnishing capex per bedroom
    furnish_min: float = 8000.0         # floor for furnishing a whole unit
    deposit_months: float = 3.0         # arbitrage: first + last + security

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StrAnalysis:
    """Result of analyzing one listing under one STR strategy."""

    listing: Listing
    strategy_key: str
    strategy_name: str
    regulation_risk: str
    assumptions: dict = field(default_factory=dict)

    # Revenue
    occupancy: float = 0.0
    adr: float = 0.0                 # implied or supplied average daily rate
    revpan: float = 0.0             # revenue per available night (gross/365)
    gross_annual_revenue: float = 0.0
    revenue_source: str = ""        # "adr+occupancy" | "ltr-multiple"
    ltr_monthly_rent: float = 0.0   # the long-term rent used for the fallback/lease

    # Costs
    management: float = 0.0
    variable_opex: float = 0.0
    property_tax: float = 0.0
    insurance: float = 0.0
    hoa: float = 0.0
    operating_expenses: float = 0.0
    net_operating_income: float = 0.0

    # Capital / financing
    furnishing: float = 0.0
    debt_or_lease_annual: float = 0.0
    cash_invested: float = 0.0

    # Returns
    annual_cash_flow: float = 0.0
    monthly_cash_flow: float = 0.0
    cash_on_cash: float = 0.0
    cap_rate: Optional[float] = None   # None for lease-based (no asset owned)
    confidence: float = 0.0
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "listing": self.listing.to_dict(),
            "strategy": {
                "key": self.strategy_key,
                "name": self.strategy_name,
                "regulation_risk": self.regulation_risk,
            },
            "assumptions": self.assumptions,
            "revenue": {
                "occupancy": round(self.occupancy, 4),
                "adr": round(self.adr, 2),
                "revpan": round(self.revpan, 2),
                "gross_annual_revenue": round(self.gross_annual_revenue, 2),
                "source": self.revenue_source,
                "ltr_monthly_rent": round(self.ltr_monthly_rent, 2),
            },
            "metrics": {
                "management": round(self.management, 2),
                "variable_opex": round(self.variable_opex, 2),
                "property_tax": round(self.property_tax, 2),
                "insurance": round(self.insurance, 2),
                "hoa": round(self.hoa, 2),
                "operating_expenses": round(self.operating_expenses, 2),
                "net_operating_income": round(self.net_operating_income, 2),
                "furnishing": round(self.furnishing, 2),
                "debt_or_lease_annual": round(self.debt_or_lease_annual, 2),
                "cash_invested": round(self.cash_invested, 2),
                "annual_cash_flow": round(self.annual_cash_flow, 2),
                "monthly_cash_flow": round(self.monthly_cash_flow, 2),
                "cash_on_cash": round(self.cash_on_cash, 4),
                "cap_rate": round(self.cap_rate, 4) if self.cap_rate is not None else None,
                "confidence": round(self.confidence, 3),
                "score": round(self.score, 1),
            },
        }


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class StrAnalyzer:
    def __init__(
        self,
        provider: DataProvider,
        estimator: Optional[RentEstimator] = None,
        assumptions: Optional[StrAssumptions] = None,
    ):
        self.provider = provider
        self.estimator = estimator or RentEstimator()
        self.assumptions = assumptions or StrAssumptions()

    # -- long-term rent helper (for the fallback + arbitrage lease cost) ----
    def _ltr_monthly(self, listing: Listing) -> tuple:
        comps = self.provider.rental_comps(
            zip_code=listing.location.zip_code, property_type=listing.property_type
        )
        est = self.estimator.estimate(listing, comps)
        return est.monthly_rent, est.confidence

    # -- single analysis ----------------------------------------------------
    def analyze(
        self,
        listing: Listing,
        strategy: str = "vacation",
        adr: Optional[float] = None,
        occupancy: Optional[float] = None,
        ltr_monthly: Optional[float] = None,
    ) -> StrAnalysis:
        strat: StrStrategy = get_strategy(strategy)
        a = self.assumptions
        occ = occupancy if occupancy is not None else strat.typical_occupancy
        occ = _clamp(occ, 0.0, 1.0)

        # Long-term rent: always needed for the lease cost (arbitrage) and for
        # the revenue fallback. Compute it unless caller supplied it.
        ltr_conf = 0.6
        if ltr_monthly is None:
            ltr_monthly, ltr_conf = self._ltr_monthly(listing)

        # --- revenue ---
        if adr is not None and adr > 0:
            gross = adr * 365 * occ
            revenue_source = "adr+occupancy"
            confidence = 0.9
            adr_val = adr
        else:
            gross_at_typical = ltr_monthly * 12 * strat.revenue_multiple
            scale = (occ / strat.typical_occupancy) if strat.typical_occupancy else 1.0
            gross = gross_at_typical * scale
            adr_val = gross / (365 * occ) if occ > 0 else 0.0
            revenue_source = "ltr-multiple"
            # Multiple-based estimates are inherently rougher than real ADR.
            confidence = _clamp(0.65 * (ltr_conf if ltr_conf else 0.5))

        res = StrAnalysis(
            listing=listing,
            strategy_key=strat.key,
            strategy_name=strat.name,
            regulation_risk=strat.regulation_risk,
            assumptions=a.to_dict(),
            occupancy=occ,
            adr=adr_val,
            revpan=gross / 365 if gross else 0.0,
            gross_annual_revenue=gross,
            revenue_source=revenue_source,
            ltr_monthly_rent=ltr_monthly,
            confidence=confidence,
        )

        # --- operating costs ---
        res.management = gross * strat.mgmt_rate
        res.variable_opex = gross * strat.opex_rate
        price = listing.price
        if strat.lease_based:
            res.property_tax = 0.0
            res.insurance = 600.0          # STR contents / liability policy, flat
            res.hoa = 0.0
        else:
            res.property_tax = (
                listing.property_tax_annual
                if listing.property_tax_annual is not None
                else price * a.property_tax_rate
            )
            res.insurance = price * a.str_insurance_rate
            res.hoa = listing.hoa_monthly * 12
        res.operating_expenses = (
            res.management + res.variable_opex + res.property_tax + res.insurance + res.hoa
        )
        res.net_operating_income = gross - res.operating_expenses

        # --- capital & financing ---
        res.furnishing = max(a.furnish_min, listing.beds * a.furnish_per_bed)
        if strat.lease_based:
            lease_annual = ltr_monthly * 12
            res.debt_or_lease_annual = lease_annual
            res.cash_invested = res.furnishing + ltr_monthly * a.deposit_months
            res.cap_rate = None
        else:
            down = strat.down_payment_pct
            loan = price * (1 - down)
            res.debt_or_lease_annual = monthly_mortgage_payment(
                loan, a.mortgage_rate, a.loan_term_years
            ) * 12
            res.cash_invested = price * (down + a.closing_cost_pct) + res.furnishing
            res.cap_rate = res.net_operating_income / price if price else 0.0

        res.annual_cash_flow = res.net_operating_income - res.debt_or_lease_annual
        res.monthly_cash_flow = res.annual_cash_flow / 12
        res.cash_on_cash = (
            res.annual_cash_flow / res.cash_invested if res.cash_invested else 0.0
        )
        res.score = self._score(res, strat)
        return res

    # -- scoring ------------------------------------------------------------
    def _score(self, r: StrAnalysis, strat: StrStrategy) -> float:
        coc = _clamp(r.cash_on_cash / 0.20)              # 20% CoC -> full marks (STR)
        cash = _clamp(r.monthly_cash_flow / 1500.0)      # up to ~$1,500/mo
        if r.cap_rate is None:                           # lease-based: no asset/cap
            raw = 0.6 * coc + 0.4 * cash
        else:
            cap = _clamp(r.cap_rate / 0.10)              # 10% cap -> full marks
            raw = 0.5 * coc + 0.3 * cash + 0.2 * cap
        reg = _REG_PENALTY.get(r.regulation_risk, 0.85)
        conf = 0.6 + 0.4 * r.confidence
        return 100.0 * raw * reg * conf

    # -- compare all strategies on one listing ------------------------------
    def compare(
        self,
        listing: Listing,
        adr: Optional[float] = None,
        occupancy: Optional[float] = None,
    ) -> List[StrAnalysis]:
        # Estimate LTR once and reuse across strategies.
        ltr_monthly, _ = self._ltr_monthly(listing)
        out = [
            self.analyze(listing, key, adr=adr, occupancy=occupancy, ltr_monthly=ltr_monthly)
            for key in STRATEGIES
        ]
        out.sort(key=lambda x: x.score, reverse=True)
        return out

    # -- scan a market for one strategy -------------------------------------
    def find_deals(
        self,
        strategy: str = "vacation",
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
        adr: Optional[float] = None,
        occupancy: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[StrAnalysis]:
        listings = self.provider.search_listings(
            zip_code=zip_code, max_price=max_price,
            min_beds=min_beds, property_type=property_type,
        )
        out = [self.analyze(l, strategy, adr=adr, occupancy=occupancy) for l in listings]
        out.sort(key=lambda x: x.score, reverse=True)
        return out[:limit] if limit else out


def best_strategy(analyses: List[StrAnalysis]) -> Optional[StrAnalysis]:
    """Highest-scoring analysis from a compare() result (already sorted)."""
    return analyses[0] if analyses else None
