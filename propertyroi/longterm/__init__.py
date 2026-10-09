"""General / long-term ROI analysis engine.

This is the buy-and-hold, long-term-rental side of PropertyROI — gross yield,
cap rate, cash flow, cash-on-cash, the 1% rule, and (for tax-sale land) the land
metrics. It is the counterpart to the short-term rental engine in
:mod:`propertyroi.shortterm`.

The implementation lives in :mod:`propertyroi.analyzer`; this package is the
stable public entry point for the long-term side and gives the core types
long-term-specific aliases.

    from propertyroi.longterm import RoiAnalyzer, RoiAssumptions
"""

from ..analyzer import Analyzer, Assumptions, monthly_mortgage_payment
from ..estimator import RentEstimator
from ..models import InvestmentAnalysis

# Long-term-flavored aliases (the classes are shared with propertyroi.analyzer).
RoiAnalyzer = Analyzer
RoiAssumptions = Assumptions

__all__ = [
    "RoiAnalyzer",
    "RoiAssumptions",
    "Analyzer",
    "Assumptions",
    "InvestmentAnalysis",
    "RentEstimator",
    "monthly_mortgage_payment",
]
