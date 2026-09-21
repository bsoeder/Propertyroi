"""Core data models for PropertyROI.

These are plain dataclasses (stdlib only) that represent the domain objects the
rest of the package works with: a property that is *for sale*, a *rental comp*
(a nearby unit that is currently rented or listed for rent), the *rent estimate*
produced for a subject property, and the full *investment analysis* that layers
ROI metrics on top of the rent estimate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

PropertyType = str  # "single_family" | "condo" | "townhouse" | "multi_family"


@dataclass
class Location:
    """A geographic point plus the postal identifiers used to match comps."""

    zip_code: str
    city: str = ""
    state: str = ""
    county: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Listing:
    """A property that is for sale."""

    id: str
    location: Location
    price: float
    beds: int
    baths: float
    sqft: int
    property_type: PropertyType = "single_family"
    year_built: Optional[int] = None
    address: str = ""
    hoa_monthly: float = 0.0
    property_tax_annual: Optional[float] = None
    url: str = ""
    # Land / tax-sale fields (populated by the MVBA provider; None for residential).
    source: str = ""                     # e.g. "mvba", "realtor", "zillow"
    lot_acres: Optional[float] = None    # parcel size in acres (land)
    adjudged_value: Optional[float] = None  # court-adjudged value at a tax sale
    sale_date: str = ""                  # tax-sale date, if applicable

    @property
    def is_land(self) -> bool:
        """True for raw-land / tax-sale parcels (no habitable structure)."""
        return self.property_type == "land" or self.source == "mvba"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["location"] = self.location.to_dict()
        d["is_land"] = self.is_land
        return d

    @staticmethod
    def from_dict(d: dict) -> "Listing":
        loc = d.get("location", {})
        return Listing(
            id=str(d["id"]),
            location=Location(**loc),
            price=float(d["price"]),
            beds=int(d["beds"]),
            baths=float(d["baths"]),
            sqft=int(d["sqft"]),
            property_type=d.get("property_type", "single_family"),
            year_built=d.get("year_built"),
            address=d.get("address", ""),
            hoa_monthly=float(d.get("hoa_monthly", 0.0)),
            property_tax_annual=d.get("property_tax_annual"),
            url=d.get("url", ""),
            source=d.get("source", ""),
            lot_acres=d.get("lot_acres"),
            adjudged_value=d.get("adjudged_value"),
            sale_date=d.get("sale_date", ""),
        )


@dataclass
class RentalComp:
    """A comparable unit whose actual/asking monthly rent is known."""

    id: str
    location: Location
    monthly_rent: float
    beds: int
    baths: float
    sqft: int
    property_type: PropertyType = "single_family"
    address: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["location"] = self.location.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> "RentalComp":
        loc = d.get("location", {})
        return RentalComp(
            id=str(d["id"]),
            location=Location(**loc),
            monthly_rent=float(d["monthly_rent"]),
            beds=int(d["beds"]),
            baths=float(d["baths"]),
            sqft=int(d["sqft"]),
            property_type=d.get("property_type", "single_family"),
            address=d.get("address", ""),
        )


@dataclass
class RentEstimate:
    """The output of the rent estimator for a single subject property."""

    monthly_rent: float
    low: float
    high: float
    confidence: float  # 0..1
    comps_used: int
    method: str = "comps"
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InvestmentAnalysis:
    """Investment metrics derived from a listing and its rent estimate."""

    listing: Listing
    rent_estimate: RentEstimate
    assumptions: dict = field(default_factory=dict)

    # Computed metrics (filled by the analyzer).
    gross_annual_rent: float = 0.0
    effective_gross_income: float = 0.0
    operating_expenses: float = 0.0
    net_operating_income: float = 0.0
    gross_yield: float = 0.0          # annual rent / price
    cap_rate: float = 0.0             # NOI / price
    monthly_cash_flow: float = 0.0    # after mortgage + expenses
    annual_cash_flow: float = 0.0
    cash_on_cash: float = 0.0         # annual cash flow / cash invested
    cash_invested: float = 0.0
    meets_one_percent_rule: bool = False
    score: float = 0.0                # composite ranking score 0..100 (primary)

    # Land / tax-sale metrics (computed for land listings; 0 for residential).
    is_land: bool = False
    discount_to_adjudged: float = 0.0  # 1 - price/adjudged_value (higher = better)
    price_per_acre: float = 0.0
    land_score: float = 0.0            # 0..100 land-specific score
    rental_score: float = 0.0         # 0..100 rental score (kept alongside land)

    def to_dict(self) -> dict:
        return {
            "listing": self.listing.to_dict(),
            "rent_estimate": self.rent_estimate.to_dict(),
            "assumptions": self.assumptions,
            "metrics": {
                "gross_annual_rent": round(self.gross_annual_rent, 2),
                "effective_gross_income": round(self.effective_gross_income, 2),
                "operating_expenses": round(self.operating_expenses, 2),
                "net_operating_income": round(self.net_operating_income, 2),
                "gross_yield": round(self.gross_yield, 4),
                "cap_rate": round(self.cap_rate, 4),
                "monthly_cash_flow": round(self.monthly_cash_flow, 2),
                "annual_cash_flow": round(self.annual_cash_flow, 2),
                "cash_on_cash": round(self.cash_on_cash, 4),
                "cash_invested": round(self.cash_invested, 2),
                "meets_one_percent_rule": self.meets_one_percent_rule,
                "score": round(self.score, 1),
                # Land metrics (side by side with rental metrics).
                "is_land": self.is_land,
                "discount_to_adjudged": round(self.discount_to_adjudged, 4),
                "price_per_acre": round(self.price_per_acre, 2),
                "land_score": round(self.land_score, 1),
                "rental_score": round(self.rental_score, 1),
            },
        }
