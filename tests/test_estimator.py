import math
import unittest

from propertyroi.estimator import RentEstimator, _haversine_miles
from propertyroi.models import Listing, Location, RentalComp


def L(zip_code="10001", beds=3, baths=2, sqft=1500, ptype="single_family", price=300000, lat=None, lon=None):
    return Listing(
        id="subject", location=Location(zip_code=zip_code, latitude=lat, longitude=lon),
        price=price, beds=beds, baths=baths, sqft=sqft, property_type=ptype,
    )


def C(cid, rent, zip_code="10001", beds=3, baths=2, sqft=1500, ptype="single_family", lat=None, lon=None):
    return RentalComp(
        id=cid, location=Location(zip_code=zip_code, latitude=lat, longitude=lon),
        monthly_rent=rent, beds=beds, baths=baths, sqft=sqft, property_type=ptype,
    )


class TestEstimator(unittest.TestCase):
    def test_no_comps_returns_zero_confidence(self):
        est = RentEstimator().estimate(L(), [])
        self.assertEqual(est.comps_used, 0)
        self.assertEqual(est.monthly_rent, 0.0)
        self.assertEqual(est.confidence, 0.0)

    def test_identical_comps_recovered(self):
        comps = [C(f"c{i}", 2000) for i in range(5)]
        est = RentEstimator().estimate(L(), comps)
        self.assertAlmostEqual(est.monthly_rent, 2000, delta=1)
        self.assertGreater(est.confidence, 0.8)
        self.assertEqual(est.comps_used, 5)

    def test_larger_subject_gets_higher_rent(self):
        comps = [C(f"c{i}", 2000, sqft=1000) for i in range(5)]
        small = RentEstimator().estimate(L(sqft=1000), comps).monthly_rent
        big = RentEstimator().estimate(L(sqft=2000), comps).monthly_rent
        self.assertGreater(big, small)

    def test_beds_tolerance_filters(self):
        # subject 3bd; comps at 1bd should be excluded with tolerance=1
        comps = [C(f"c{i}", 1200, beds=1, sqft=600) for i in range(4)]
        est = RentEstimator(beds_tolerance=1).estimate(L(beds=3), comps)
        self.assertEqual(est.comps_used, 0)

    def test_zip_filtering_without_coords(self):
        comps = [C("in", 2000, zip_code="10001"), C("out", 9000, zip_code="99999")]
        est = RentEstimator().estimate(L(zip_code="10001"), comps)
        self.assertEqual(est.comps_used, 1)
        self.assertAlmostEqual(est.monthly_rent, 2000, delta=1)

    def test_distance_filter_with_coords(self):
        subj = L(lat=40.0, lon=-73.0)
        near = C("near", 2000, lat=40.001, lon=-73.001)
        far = C("far", 2000, lat=45.0, lon=-80.0)
        est = RentEstimator(max_distance_miles=5).estimate(subj, [near, far])
        self.assertEqual(est.comps_used, 1)

    def test_band_ordering(self):
        comps = [C("a", 1800), C("b", 2000), C("c", 2200)]
        est = RentEstimator().estimate(L(), comps)
        self.assertLessEqual(est.low, est.monthly_rent)
        self.assertLessEqual(est.monthly_rent, est.high)

    def test_haversine_none_without_coords(self):
        self.assertIsNone(_haversine_miles(Location("1"), Location("2")))

    def test_haversine_known_distance(self):
        # ~ 69 miles per degree latitude near the equator
        d = _haversine_miles(Location("1", latitude=0, longitude=0),
                             Location("2", latitude=1, longitude=0))
        self.assertTrue(math.isclose(d, 69.0, rel_tol=0.02))


if __name__ == "__main__":
    unittest.main()
