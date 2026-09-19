"""PropertyROI - find for-sale properties and evaluate their rental potential.

Public API:
    from propertyroi import Analyzer, Assumptions, RentEstimator, JsonProvider
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

__version__ = "0.1.0"

__all__ = [
    "Analyzer",
    "Assumptions",
    "RentEstimator",
    "JsonProvider",
    "Listing",
    "Location",
    "RentalComp",
    "RentEstimate",
    "InvestmentAnalysis",
]
