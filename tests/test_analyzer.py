import unittest

from propertyroi.analyzer import Analyzer, Assumptions, monthly_mortgage_payment
from propertyroi.estimator import RentEstimator
from propertyroi.models import Listing, Location, RentalComp, RentEstimate
from propertyroi.providers.base import DataProvider


class FakeProvider(DataProvider):
    def __init__(self, listings, comps):
        self._l = listings
        self._c = comps

    def search_listings(self, zip_code=None, max_price=None, min_beds=None, property_type=None):
        out = self._l
        if max_price is not None:
            out = [l for l in out if l.price <= max_price]
        return out

    def rental_comps(self, zip_code=None, property_type=None):
        return self._c


def mk_listing(price=200000, sqft=1500, beds=3):
    return Listing(id="L1", location=Location("10001"), price=price, beds=beds, baths=2, sqft=sqft)


def mk_comp(rent=2000, sqft=1500, beds=3):
    return RentalComp(id="c", location=Location("10001"), monthly_rent=rent, beds=beds, baths=2, sqft=sqft)


class TestMortgage(unittest.TestCase):
    def test_known_payment(self):
        # $100k @ 6% / 30yr ~= $599.55/mo
        pay = monthly_mortgage_payment(100000, 0.06, 30)
        self.assertAlmostEqual(pay, 599.55, delta=0.5)

    def test_zero_rate(self):
        self.assertAlmostEqual(monthly_mortgage_payment(120000, 0.0, 10), 1000.0, delta=0.01)

    def test_zero_principal(self):
        self.assertEqual(monthly_mortgage_payment(0, 0.05, 30), 0.0)


class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider([mk_listing()], [mk_comp() for _ in range(4)])
        self.analyzer = Analyzer(self.provider, RentEstimator())

    def test_metrics_populated(self):
        a = self.analyzer.analyze(mk_listing())
        self.assertGreater(a.gross_annual_rent, 0)
        self.assertGreater(a.cap_rate, 0)
        self.assertGreater(a.gross_yield, a.cap_rate)  # yield > cap (expenses)
        self.assertTrue(0 <= a.score <= 100)

    def test_one_percent_rule(self):
        # rent 2000 / price 150000 = 1.33% -> passes
        a = self.analyzer.analyze(mk_listing(price=150000))
        self.assertTrue(a.meets_one_percent_rule)
        # rent 2000 / price 400000 = 0.5% -> fails
        b = self.analyzer.analyze(mk_listing(price=400000))
        self.assertFalse(b.meets_one_percent_rule)

    def test_cheaper_property_scores_higher(self):
        cheap = self.analyzer.analyze(mk_listing(price=150000))
        pricey = self.analyzer.analyze(mk_listing(price=500000))
        self.assertGreater(cheap.score, pricey.score)

    def test_find_deals_sorted(self):
        provider = FakeProvider(
            [mk_listing(price=500000), mk_listing(price=150000)],
            [mk_comp() for _ in range(4)],
        )
        deals = Analyzer(provider, RentEstimator()).find_deals()
        self.assertEqual(len(deals), 2)
        self.assertGreaterEqual(deals[0].score, deals[1].score)

    def test_explicit_estimate_used(self):
        est = RentEstimate(monthly_rent=3000, low=2800, high=3200, confidence=0.9, comps_used=5)
        a = self.analyzer.analyze(mk_listing(), rent_estimate=est)
        self.assertEqual(a.gross_annual_rent, 3000 * 12)

    def test_assumptions_affect_cash_flow(self):
        low_down = Analyzer(self.provider, RentEstimator(), Assumptions(down_payment_pct=0.05))
        high_down = Analyzer(self.provider, RentEstimator(), Assumptions(down_payment_pct=0.50))
        a = low_down.analyze(mk_listing())
        b = high_down.analyze(mk_listing())
        # More down -> smaller loan -> higher cash flow.
        self.assertGreater(b.monthly_cash_flow, a.monthly_cash_flow)


if __name__ == "__main__":
    unittest.main()
