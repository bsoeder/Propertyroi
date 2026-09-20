"""Accuracy evaluator for the rent estimator.

Given a labeled data set — properties whose *actual* monthly rent is known — the
tester runs the estimator (using every *other* property as a comp, i.e.
leave-one-out) and compares predictions to ground truth. It reports the standard
regression accuracy metrics an appraiser or data scientist would expect:

    MAE   - mean absolute error (dollars)
    RMSE  - root mean squared error (dollars, penalizes big misses)
    MAPE  - mean absolute percentage error
    Median APE
    R^2   - coefficient of determination vs. predicting the mean
    Within X%  - share of predictions within 5% / 10% / 20% of actual
    Bias  - mean signed error (are we systematically high or low?)
    Coverage - share of subjects the estimator could price at all

This lets you quantify how good the rental-potential model is and track it as you
change the algorithm or feed in real data.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence

from .estimator import RentEstimator
from .models import Listing, RentalComp


@dataclass
class LabeledProperty:
    """A property with both its physical attributes and its known actual rent."""

    listing: Listing
    actual_rent: float

    @staticmethod
    def from_dict(d: dict) -> "LabeledProperty":
        return LabeledProperty(
            listing=Listing.from_dict(d),
            actual_rent=float(d["actual_rent"]),
        )

    def as_comp(self) -> RentalComp:
        l = self.listing
        return RentalComp(
            id=l.id,
            location=l.location,
            monthly_rent=self.actual_rent,
            beds=l.beds,
            baths=l.baths,
            sqft=l.sqft,
            property_type=l.property_type,
            address=l.address,
        )


@dataclass
class Prediction:
    id: str
    actual: float
    predicted: float
    error: float          # predicted - actual
    abs_error: float
    pct_error: float      # abs_error / actual
    confidence: float
    comps_used: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AccuracyReport:
    n: int
    coverage: float
    mae: float
    rmse: float
    mape: float
    median_ape: float
    r2: float
    bias: float
    within_5pct: float
    within_10pct: float
    within_20pct: float
    predictions: List[Prediction]

    def to_dict(self, include_predictions: bool = True) -> dict:
        d = {
            "n": self.n,
            "coverage": round(self.coverage, 4),
            "mae": round(self.mae, 2),
            "rmse": round(self.rmse, 2),
            "mape": round(self.mape, 4),
            "median_ape": round(self.median_ape, 4),
            "r2": round(self.r2, 4),
            "bias": round(self.bias, 2),
            "within_5pct": round(self.within_5pct, 4),
            "within_10pct": round(self.within_10pct, 4),
            "within_20pct": round(self.within_20pct, 4),
        }
        if include_predictions:
            d["predictions"] = [p.to_dict() for p in self.predictions]
        return d

    def summary(self) -> str:
        lines = [
            "Rent Estimator Accuracy Report",
            "=" * 34,
            f"Samples priced        : {self.n}",
            f"Coverage              : {self.coverage:.0%}",
            f"MAE                   : ${self.mae:,.0f}/mo",
            f"RMSE                  : ${self.rmse:,.0f}/mo",
            f"MAPE                  : {self.mape:.1%}",
            f"Median APE            : {self.median_ape:.1%}",
            f"R^2                   : {self.r2:.3f}",
            f"Bias (pred - actual)  : ${self.bias:,.0f}/mo",
            f"Within  5%            : {self.within_5pct:.0%}",
            f"Within 10%            : {self.within_10pct:.0%}",
            f"Within 20%            : {self.within_20pct:.0%}",
        ]
        return "\n".join(lines)


class AccuracyTester:
    """Leave-one-out evaluation of a :class:`RentEstimator`."""

    def __init__(self, estimator: Optional[RentEstimator] = None):
        self.estimator = estimator or RentEstimator()

    def evaluate(self, labeled: Sequence[LabeledProperty]) -> AccuracyReport:
        total = len(labeled)
        preds: List[Prediction] = []

        for i, subject in enumerate(labeled):
            # Leave-one-out: every other labeled property is a comp.
            comps = [lp.as_comp() for j, lp in enumerate(labeled) if j != i]
            est = self.estimator.estimate(subject.listing, comps)
            if est.comps_used == 0 or est.monthly_rent <= 0:
                continue  # not covered
            err = est.monthly_rent - subject.actual_rent
            abs_err = abs(err)
            pct = abs_err / subject.actual_rent if subject.actual_rent else 0.0
            preds.append(
                Prediction(
                    id=subject.listing.id,
                    actual=subject.actual_rent,
                    predicted=est.monthly_rent,
                    error=round(err, 2),
                    abs_error=round(abs_err, 2),
                    pct_error=round(pct, 4),
                    confidence=est.confidence,
                    comps_used=est.comps_used,
                )
            )

        return self._aggregate(preds, total)

    def _aggregate(self, preds: List[Prediction], total: int) -> AccuracyReport:
        n = len(preds)
        if n == 0:
            return AccuracyReport(0, 0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, preds)

        actuals = [p.actual for p in preds]
        errors = [p.error for p in preds]
        abs_errors = [p.abs_error for p in preds]
        apes = [p.pct_error for p in preds]

        mae = sum(abs_errors) / n
        rmse = math.sqrt(sum(e * e for e in errors) / n)
        mape = sum(apes) / n
        median_ape = sorted(apes)[n // 2] if n % 2 else (
            (sorted(apes)[n // 2 - 1] + sorted(apes)[n // 2]) / 2
        )
        bias = sum(errors) / n

        mean_actual = sum(actuals) / n
        ss_res = sum(e * e for e in errors)
        ss_tot = sum((a - mean_actual) ** 2 for a in actuals)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        within_5 = sum(1 for p in apes if p <= 0.05) / n
        within_10 = sum(1 for p in apes if p <= 0.10) / n
        within_20 = sum(1 for p in apes if p <= 0.20) / n

        return AccuracyReport(
            n=n,
            coverage=n / total if total else 0.0,
            mae=mae,
            rmse=rmse,
            mape=mape,
            median_ape=median_ape,
            r2=r2,
            bias=bias,
            within_5pct=within_5,
            within_10pct=within_10,
            within_20pct=within_20,
            predictions=preds,
        )


def load_labeled(path: str) -> List[LabeledProperty]:
    with open(path) as f:
        return [LabeledProperty.from_dict(d) for d in json.load(f)]
