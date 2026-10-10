"""Metro-area -> ZIP code resolution.

Lets a search target a whole metro ("Austin, TX") instead of a single ZIP. The
metro -> ZIPs map is derived from the same market dataset the rankings use
(``data/zip_market_stats.csv``), so the two stay in sync; ``scripts/refresh_
rankings.py`` expands both with real ZIPs when you rebuild from live data.
"""

from __future__ import annotations

import csv
import os
from typing import Dict, List, Optional, Tuple

_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "zip_market_stats.csv")


def load_metros(path: Optional[str] = None) -> Dict[str, List[str]]:
    """metro name -> list of ZIP codes."""
    path = path or os.environ.get("PROPERTYROI_RANKINGS", _DATA)
    out: Dict[str, List[str]] = {}
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                metro = (r.get("metro") or "").strip()
                zp = str(r.get("zip") or r.get("zip_code") or "").strip()
                if metro and zp:
                    out.setdefault(metro, [])
                    if zp not in out[metro]:
                        out[metro].append(zp)
    except OSError:
        return {}
    return out


def list_metros(path: Optional[str] = None) -> List[str]:
    return sorted(load_metros(path))


def resolve(query: str, path: Optional[str] = None) -> Tuple[Optional[str], List[str]]:
    """Resolve a metro query (substring, case-insensitive) to (name, zips).

    Returns (None, []) if nothing matches. Prefers an exact (case-insensitive)
    match, else the first substring match.
    """
    if not query:
        return None, []
    metros = load_metros(path)
    q = query.strip().lower()
    for name, zips in metros.items():
        if name.lower() == q:
            return name, zips
    for name, zips in metros.items():
        if q in name.lower():
            return name, zips
    return None, []
