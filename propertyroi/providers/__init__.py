"""Data providers for PropertyROI."""

from .base import DataProvider
from .json_provider import JsonProvider

__all__ = ["DataProvider", "JsonProvider"]

# RentCastProvider is imported lazily to avoid requiring an API key at import time.
try:  # pragma: no cover - optional import
    from .rentcast import RentCastProvider  # noqa: F401

    __all__.append("RentCastProvider")
except Exception:  # pragma: no cover
    pass
