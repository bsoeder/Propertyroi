"""Short-term rental (STR) analysis engine.

Prices a property under multiple STR strategies (vacation-rental market, metro,
midterm, rental arbitrage, owner-occupied house-hack) — a split from the general
long-term ROI engine in :mod:`propertyroi.longterm`.

    from propertyroi.shortterm import StrAnalyzer, StrAssumptions, STRATEGIES
"""

from .analyzer import StrAnalysis, StrAnalyzer, StrAssumptions, best_strategy
from .strategies import STRATEGIES, StrStrategy, get_strategy, strategy_keys

__all__ = [
    "StrAnalyzer",
    "StrAnalysis",
    "StrAssumptions",
    "best_strategy",
    "STRATEGIES",
    "StrStrategy",
    "get_strategy",
    "strategy_keys",
]
