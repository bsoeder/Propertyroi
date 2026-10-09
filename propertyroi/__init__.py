"""PropertyROI - find for-sale properties and evaluate their rental potential.

Two analysis engines share one data/estimation core:

    propertyroi.longterm   - general / long-term (buy-and-hold) ROI
    propertyroi.shortterm  - short-term rental, with multiple strategies

Public API:
    from propertyroi.longterm import RoiAnalyzer, RoiAssumptions
    from propertyroi.shortterm import StrAnalyzer, StrAssumptions, STRATEGIES
    from propertyroi import JsonProvider, RentEstimator
    from propertyroi.tester import AccuracyTester, load_labeled
"""

from .analyzer import Analyzer, Assumptions
from .estimator import RentEstimator
from .models import (
    InvestmentAnalysis,
    Listing,
    Location,
    RentalComp,
    RentEstimate,
)
from .providers import JsonProvider

__version__ = "0.2.0"

__all__ = [
    # shared core
    "RentEstimator",
    "JsonProvider",
    "Listing",
    "Location",
    "RentalComp",
    "RentEstimate",
    "InvestmentAnalysis",
    # long-term engine (also exported from propertyroi.longterm)
    "Analyzer",
    "Assumptions",
]
