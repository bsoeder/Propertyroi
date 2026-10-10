"""Data providers for PropertyROI."""

from .base import DataProvider
from .combined import CombinedProvider
from .csv_provider import CsvProvider
from .json_provider import JsonProvider

__all__ = ["DataProvider", "JsonProvider", "CsvProvider", "CombinedProvider"]

# Live providers are imported lazily so a missing API key never breaks import.
for _name, _mod, _cls in (
    ("ZillowProvider", ".zillow", "ZillowProvider"),
    ("RealtorProvider", ".realtor", "RealtorProvider"),
    ("MvbaProvider", ".mvba", "MvbaProvider"),
    ("HudFmrProvider", ".hud", "HudFmrProvider"),
):
    try:  # pragma: no cover - optional imports
        _module = __import__(f"propertyroi.providers{_mod}", fromlist=[_cls])
        globals()[_name] = getattr(_module, _cls)
        __all__.append(_name)
    except Exception:  # pragma: no cover
        pass
