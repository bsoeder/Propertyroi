import unittest

from propertyroi.models import Listing, Location, RentalComp
from propertyroi.providers.base import DataProvider
from propertyroi.shortterm import STRATEGIES, StrAnalyzer, get_strategy, strategy_keys


class FakeProvider(DataProvider):
    """Returns fixed listings and comps so the LTR estimate is deterministic."""

    def __init__(self, listings, rent=2000, sqft=1500, beds=3):
        self._l = listings
        self._c = [
            RentalComp(id=f"c{i}", location=Location("10001"), monthly_rent=rent,
                       beds=beds, baths=2, sqft=sqft)
            for i in range(5)
        ]

    def search_listings(self, **kw):
        return self._l

    def rental_comps(self, **kw):
        return self._c


def mk(price=300000, beds=3, sqft=1500):
    return Listing(id="S1", location=Location("10001"), price=price, beds=beds,
                   baths=2, sqft=sqft)


class TestStrategies(unittest.TestCase):
    def test_catalog(self):
        self.assertIn("vacation", strategy_keys())
        self.assertIn("arbitrage", strategy_keys())
        self.assertEqual(len(STRATEGIES), 5)

    def test_get_strategy(self):
        self.assertEqual(get_strategy("midterm").key, "midterm")
        with self.assertRaises(ValueError):
            get_strategy("nope")

    def test_arbitrage_is_lease_based(self):
        self.assertTrue(get_strategy("arbitrage").lease_based)
        self.assertFalse(get_strategy("vacation").lease_based)


class TestStrAnalyzer(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider([mk()])
        self.a = StrAnalyzer(self.provider)

    def test_adr_revenue(self):
        r = self.a.analyze(mk(), "vacation", adr=200, occupancy=0.70)
        self.assertEqual(r.revenue_source, "adr+occupancy")
        self.assertAlmostEqual(r.gross_annual_revenue, 200 * 365 * 0.70, places=2)
        self.assertEqual(r.adr, 200)
        self.assertGreater(r.confidence, 0.8)

    def test_ltr_multiple_fallback(self):
        # LTR estimate ~2000/mo; vacation multiple 3.0 at typical occupancy.
        r = self.a.analyze(mk(), "vacation")
        self.assertEqual(r.revenue_source, "ltr-multiple")
        self.assertAlmostEqual(r.ltr_monthly_rent, 2000, delta=60)
        self.assertAlmostEqual(r.gross_annual_revenue, r.ltr_monthly_rent * 12 * 3.0, delta=5)

    def test_occupancy_scales_revenue(self):
        base = self.a.analyze(mk(), "vacation")  # typical occ 0.65
        hi = self.a.analyze(mk(), "vacation", occupancy=0.80)
        self.assertGreater(hi.gross_annual_revenue, base.gross_annual_revenue)

    def test_purchase_has_cap_rate_and_capital(self):
        r = self.a.analyze(mk(price=300000), "vacation")
        self.assertIsNotNone(r.cap_rate)
        # cash invested = down(20%)+closing(3%) of price + furnishing
        self.assertGreater(r.cash_invested, 300000 * 0.23)
        self.assertGreater(r.furnishing, 0)

    def test_arbitrage_no_cap_rate_low_capital(self):
        r = self.a.analyze(mk(price=300000), "arbitrage")
        self.assertIsNone(r.cap_rate)
        # No purchase: capital is furnishing + deposits only (far below a down payment).
        self.assertLess(r.cash_invested, 50000)
        # "Debt" is the annual lease, ~ LTR x 12.
        self.assertAlmostEqual(r.debt_or_lease_annual, r.ltr_monthly_rent * 12, delta=5)

    def test_owner_occupied_low_down(self):
        r = self.a.analyze(mk(price=300000), "owner_occupied")
        # 5% down + 3% closing -> cash invested well under a 20% down deal.
        self.assertLess(r.cash_invested, 300000 * 0.15)

    def test_compare_returns_all_sorted(self):
        results = self.a.compare(mk())
        self.assertEqual(len(results), len(STRATEGIES))
        scores = [r.score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_find_deals_ranked(self):
        provider = FakeProvider([mk(price=500000), mk(price=150000)])
        deals = StrAnalyzer(provider).find_deals(strategy="vacation")
        self.assertEqual(len(deals), 2)
        self.assertGreaterEqual(deals[0].score, deals[1].score)

    def test_to_dict_shape(self):
        d = self.a.analyze(mk(), "metro").to_dict()
        self.assertIn("strategy", d)
        self.assertIn("revenue", d)
        self.assertIn("metrics", d)
        self.assertEqual(d["strategy"]["key"], "metro")
        self.assertEqual(d["strategy"]["regulation_risk"], "high")


if __name__ == "__main__":
    unittest.main()
