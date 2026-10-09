"""Short-term rental (STR) strategies.

The strategy catalog is inspired by the framework in Avery Carl's *Short-Term
Rental, Long-Term Wealth* — the idea that STR is not one thing but several
distinct plays, each with its own revenue profile, cost structure, capital
requirement, and regulatory exposure. This module captures each as a tunable set
of assumptions so the STR analyzer can price the *same* property under *different*
strategies and let you compare them.

The numbers here are transparent, defensible defaults — not investment advice and
not market data. Override them (or feed real ADR/occupancy) for a specific deal.
Every field is documented so you can see exactly what each strategy assumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class StrStrategy:
    """One short-term-rental playbook and its economic assumptions."""

    key: str
    name: str
    description: str

    # Revenue model -------------------------------------------------------
    # STR annual gross revenue as a multiple of the property's long-term
    # monthly rent x 12, evaluated at `typical_occupancy`. Used only when no
    # explicit ADR/occupancy is supplied. A vacation rental in a leisure market
    # grosses far more than long-term rent; a midterm (30+ day) rental only a
    # little more.
    revenue_multiple: float
    typical_occupancy: float          # 0..1 nightly/period occupancy

    # Operating costs (as a share of gross revenue) ----------------------
    mgmt_rate: float                  # property / co-host management
    opex_rate: float                  # cleaning, supplies, utilities, upkeep

    # Capital & financing -------------------------------------------------
    lease_based: bool = False         # arbitrage: you lease, not buy
    owner_occupied: bool = False      # house-hack: owner-occupant financing
    down_payment_pct: float = 0.20    # for purchase strategies

    # Context -------------------------------------------------------------
    regulation_risk: str = "medium"   # low | medium | high
    notes: str = ""


# The catalog. Keys are stable identifiers used by the CLI/API.
STRATEGIES: Dict[str, StrStrategy] = {
    "vacation": StrStrategy(
        key="vacation",
        name="Vacation-rental market",
        description=(
            "Avery Carl's core play: a nightly rental in an established "
            "destination/leisure market (lake, beach, ski, national park) with "
            "STR-friendly regulation. Highest revenue multiple, moderate "
            "occupancy, higher management load."
        ),
        revenue_multiple=3.0,
        typical_occupancy=0.65,
        mgmt_rate=0.20,
        opex_rate=0.18,
        down_payment_pct=0.20,
        regulation_risk="low",
        notes="Buy where STR is the established use, not your metro backyard.",
    ),
    "metro": StrStrategy(
        key="metro",
        name="Metro / urban STR",
        description=(
            "Nightly rentals in a city for business travelers and events. "
            "Higher, steadier occupancy but materially higher regulatory risk "
            "(permits, bans, primary-residence rules)."
        ),
        revenue_multiple=2.2,
        typical_occupancy=0.72,
        mgmt_rate=0.22,
        opex_rate=0.18,
        down_payment_pct=0.25,
        regulation_risk="high",
        notes="Check the local ordinance before anything else.",
    ),
    "midterm": StrStrategy(
        key="midterm",
        name="Midterm rental (30+ day)",
        description=(
            "Furnished 30+ day stays for traveling nurses, relocations, and "
            "corporate housing. Modest revenue uplift over long-term rent, but "
            "high stable occupancy, low turnover cost, and little STR "
            "regulation exposure."
        ),
        revenue_multiple=1.35,
        typical_occupancy=0.90,
        mgmt_rate=0.10,
        opex_rate=0.12,
        down_payment_pct=0.25,
        regulation_risk="low",
        notes="The low-regulation, low-volatility STR option.",
    ),
    "arbitrage": StrStrategy(
        key="arbitrage",
        name="Rental arbitrage",
        description=(
            "Lease a unit long-term and sublet it short-term (with landlord "
            "permission). No purchase: capital is furnishing plus deposits, and "
            "the 'debt service' is your monthly lease. Low capital, no "
            "appreciation, highest operational/regulatory risk."
        ),
        revenue_multiple=2.2,
        typical_occupancy=0.70,
        mgmt_rate=0.20,
        opex_rate=0.16,
        lease_based=True,
        regulation_risk="high",
        notes="Needs a lease that explicitly permits subletting as STR.",
    ),
    "owner_occupied": StrStrategy(
        key="owner_occupied",
        name="Owner-occupied / house-hack",
        description=(
            "Live in the property and STR part of it (a room, a basement unit) "
            "or the whole place while you travel. Owner-occupant financing means "
            "a low down payment; revenue is partial so the multiple is lower."
        ),
        revenue_multiple=1.8,
        typical_occupancy=0.55,
        mgmt_rate=0.15,
        opex_rate=0.16,
        owner_occupied=True,
        down_payment_pct=0.05,
        regulation_risk="medium",
        notes="Owner-occupancy often sidesteps the strictest STR rules.",
    ),
}


def get_strategy(key: str) -> StrStrategy:
    try:
        return STRATEGIES[key]
    except KeyError:
        raise ValueError(
            f"Unknown STR strategy '{key}'. Choose from: {', '.join(STRATEGIES)}"
        ) from None


def strategy_keys() -> List[str]:
    return list(STRATEGIES)
