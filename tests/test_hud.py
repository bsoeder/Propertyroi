import unittest

from propertyroi.providers.hud import HudFmrProvider

# Object-style basicdata (county/metro-level response).
FMR_OBJ = {
    "data": {
        "year": "2026",
        "basicdata": {
            "zip_code": "44107",
            "Efficiency": 900,
            "One-Bedroom": 1050,
            "Two-Bedroom": 1300,
            "Three-Bedroom": 1700,
            "Four-Bedroom": 2050,
            "county_name": "Cuyahoga County",
            "statename": "Ohio",
        },
    }
}

# List-style basicdata (small-area FMR), with a non-matching sibling ZIP.
FMR_LIST = {
    "data": {
        "basicdata": [
            {"zip_code": "00000", "Two-Bedroom": 1},
            {"zip_code": "78704", "One-Bedroom": 1400, "Two-Bedroom": 1800,
             "Three-Bedroom": 2300, "Four-Bedroom": 2800},
        ]
    }
}


class TestHudFmr(unittest.TestCase):
    def _provider(self, payload):
        p = HudFmrProvider(token="test-token")
        p._get = lambda zip_code: payload  # type: ignore
        return p

    def test_requires_token(self):
        import os
        old = os.environ.pop("HUD_API_TOKEN", None)
        try:
            with self.assertRaises(ValueError):
                HudFmrProvider(token=None)
        finally:
            if old is not None:
                os.environ["HUD_API_TOKEN"] = old

    def test_no_for_sale_listings(self):
        self.assertEqual(self._provider(FMR_OBJ).search_listings(zip_code="44107"), [])

    def test_object_basicdata_to_comps(self):
        comps = self._provider(FMR_OBJ).rental_comps(zip_code="44107")
        self.assertEqual(len(comps), 5)  # efficiency..4br
        by_beds = {c.beds: c for c in comps}
        self.assertEqual(by_beds[2].monthly_rent, 1300)
        self.assertEqual(by_beds[3].monthly_rent, 1700)
        self.assertEqual(by_beds[0].monthly_rent, 900)  # efficiency -> 0 beds
        # representative sizes are set so the comps estimator can scale
        self.assertGreater(by_beds[3].sqft, by_beds[1].sqft)
        self.assertEqual(comps[0].location.county, "Cuyahoga County")

    def test_list_basicdata_picks_matching_zip(self):
        comps = self._provider(FMR_LIST).rental_comps(zip_code="78704")
        rents = {c.beds: c.monthly_rent for c in comps}
        self.assertEqual(rents[1], 1400)
        self.assertEqual(rents[2], 1800)
        self.assertNotIn(1, [c.monthly_rent for c in comps])  # not the 00000 sibling

    def test_property_type_tagged(self):
        comps = self._provider(FMR_OBJ).rental_comps(zip_code="44107", property_type="condo")
        self.assertTrue(all(c.property_type == "condo" for c in comps))

    def test_no_zip_returns_empty(self):
        self.assertEqual(self._provider(FMR_OBJ).rental_comps(), [])

    def test_comps_feed_the_estimator(self):
        # End-to-end: HUD comps should produce a sane rent estimate for a subject.
        from propertyroi.estimator import RentEstimator
        from propertyroi.models import Listing, Location
        comps = self._provider(FMR_OBJ).rental_comps(zip_code="44107")
        subject = Listing(id="S", location=Location("44107"), price=200000,
                          beds=3, baths=2, sqft=1300)
        est = RentEstimator().estimate(subject, comps)
        self.assertGreater(est.monthly_rent, 1300)   # near/above the 3BR FMR
        self.assertLess(est.monthly_rent, 2100)
        self.assertGreater(est.comps_used, 0)


if __name__ == "__main__":
    unittest.main()
