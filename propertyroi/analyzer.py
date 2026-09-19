"""Investment analysis and deal ranking.

The analyzer connects a data provider to the rent estimator and turns a raw
listing + rent estimate into an :class:`InvestmentAnalysis` with the metrics a
rental investor actually cares about: yield, cap rate, cash flow,
cash-on-cash return, the 1% rule, and a single composite score for ranking.

All financial assumptions live in :class:`Assumptions` so they are explicit and
easy to tune. Nothing here is investment advice — it is a transparent model.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional

from .estimator import RentEstimator
from .models import InvestmentAnalysis, Listing, RentEstimate
from .providers.base import DataProvider


@dataclass
class Assumptions:
    """Financial assumptions used to compute ROI metrics."""

    down_payment_pct: float = 0.25       # 25% down
    mortgage_rate: float = 0.07          # 7% annual interest
    loan_term_years: int = 30
    vacancy_rate: float = 0.05           # 5% of gross rent lost to vacancy
    operating_expense_ratio: float = 0.35  # maintenance, mgmt, insurance, etc.
    property_tax_rate: float = 0.011     # used when a listing has no tax figure
    closing_cost_pct: float = 0.03       # % of price paid at closing

    def to_dict(self) -> dict:
        return asdict(self)


def monthly_mortgage_payment(principal: float, annual_rate: float, years: int) -> float:
    """Standard amortized monthly payment."""
    if principal <= 0:
        return 0.0
    r = annual_rate / 12.0
    n = years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


class Analyzer:
    def __init__(
        self,
        provider: DataProvider,
        estimator: Optional[RentEstimator] = None,
        assumptions: Optional[Assumptions] = None,
    ):
        self.provider = provider
        self.estimator = estimator or RentEstimator()
        self.assumptions = assumptions or Assumptions()

    # -- single-listing analysis -------------------------------------------
    def analyze(self, listing: Listing, rent_estimate: Optional[RentEstimate] = None) -> InvestmentAnalysis:
        a = self.assumptions
        if rent_estimate is None:
            comps = self.provider.rental_comps(
                zip_code=listing.location.zip_code,
                property_type=listing.property_type,
            )
            rent_estimate = self.estimator.estimate(listing, comps)

        analysis = InvestmentAnalysis(listing=listing, rent_estimate=rent_estimate, assumptions=a.to_dict())

        monthly_rent = rent_estimate.monthly_rent
        gross_annual = monthly_rent * 12
        effective_gross = gross_annual * (1 - a.vacancy_rate)

        # Annual property tax: use listing figure if present, else estimate.
        tax_annual = listing.property_tax_annual
        if tax_annual is None:
            tax_annual = listing.price * a.property_tax_rate

        hoa_annual = listing.hoa_monthly * 12
        opex = effective_gross * a.operating_expense_ratio + tax_annual + hoa_annual
        noi = effective_gross - opex

        # Financing.
        loan = listing.price * (1 - a.down_payment_pct)
        mortgage_monthly = monthly_mortgage_payment(loan, a.mortgage_rate, a.loan_term_years)
        annual_debt_service = mortgage_monthly * 12

        annual_cash_flow = noi - annual_debt_service
        cash_invested = listing.price * (a.down_payment_pct + a.closing_cost_pct)

        analysis.gross_annual_rent = gross_annual
        analysis.effective_gross_income = effective_gross
        analysis.operating_expenses = opex
        analysis.net_operating_income = noi
        analysis.gross_yield = gross_annual / listing.price if listing.price else 0.0
        analysis.cap_rate = noi / listing.price if listing.price else 0.0
        analysis.annual_cash_flow = annual_cash_flow
        analysis.monthly_cash_flow = annual_cash_flow / 12
        analysis.cash_invested = cash_invested
        analysis.cash_on_cash = annual_cash_flow / cash_invested if cash_invested else 0.0
        analysis.meets_one_percent_rule = (monthly_rent / listing.price) >= 0.01 if listing.price else False
        analysis.score = self._score(analysis)
        return analysis

    # -- ranking score ------------------------------------------------------
    def _score(self, a: InvestmentAnalysis) -> float:
        """Composite 0..100 score blending the key return metrics.

        Weighted so that cash-on-cash and cap rate dominate, with a bonus for
        the 1% rule and a penalty when the rent estimate is low-confidence.
        """
        # Normalize each metric onto a rough 0..1 scale against target levels.
        coc = _clamp(a.cash_on_cash / 0.12)     # 12% CoC -> full marks
        cap = _clamp(a.cap_rate / 0.08)         # 8% cap  -> full marks
        yld = _clamp(a.gross_yield / 0.10)      # 10% gross yield -> full marks
        cash = _clamp((a.monthly_cash_flow + 200) / 700)  # -$200..$500 -> 0..1
        one_pct = 1.0 if a.meets_one_percent_rule else 0.0

        raw = 0.35 * coc + 0.25 * cap + 0.15 * yld + 0.15 * cash + 0.10 * one_pct
        # Scale by estimate confidence so speculative estimates rank lower.
        conf = 0.6 + 0.4 * a.rent_estimate.confidence
        return 100.0 * raw * conf

    # -- market scan --------------------------------------------------------
    def find_deals(
        self,
        zip_code: Optional[str] = None,
        max_price: Optional[float] = None,
        min_beds: Optional[int] = None,
        property_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[InvestmentAnalysis]:
        """Search listings and return analyses ranked best-first by score."""
        listings = self.provider.search_listings(
            zip_code=zip_code,
            max_price=max_price,
            min_beds=min_beds,
            property_type=property_type,
        )
        analyses = [self.analyze(l) for l in listings]
        analyses.sort(key=lambda x: x.score, reverse=True)
        return analyses[:limit] if limit else analyses


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))
