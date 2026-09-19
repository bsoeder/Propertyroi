import unittest

from propertyroi.models import Listing, Location, RentalComp
from propertyroi.providers.base import DataProvider
from propertyroi.providers.combined import CombinedProvider
from propertyroi.providers.realtor import RealtorProvider
from propertyroi.providers.zillow import ZillowProvider


# --- Zillow -----------------------------------------------------------------
ZILLOW_SALE = {
    "props": [
        {"zpid": "1", "price": 350000, "bedrooms": 3, "bathrooms": 2,
         "livingArea": 1500, "propertyType": "SINGLE_FAMILY", "zipcode": "78704",
         "latitude": 30.2, "longitude": -97.7, "address": "1 Main St", "city": "Austin", "state": "TX"},
        {"zpid": "2", "price": None, "bedrooms": 2, "livingArea": 900},  # dropped: no price
    ]
}
ZILLOW_RENT = {
    "props": [
        {"zpid": "9", "price": 2100, "bedrooms": 3, "bathrooms": 2, "livingArea": 1450,
         "propertyType": "CONDO", "zipcode": "78704", "address": "9 Rent Rd"},
        {"zpid": "8", "price": 1800, "bedrooms": 2, "livingArea": 0},  # dropped: no sqft
    ]
}


class TestZillow(unittest.TestCase):
    def _provider(self, mapping):
        z = ZillowProvider(api_key="test")
        z._get = lambda path, params: mapping[params["status_type"]]  # type: ignore
        return z

    def test_search_listings_maps_and_filters(self):
        z = self._provider({"ForSale": ZILLOW_SALE, "ForRent": ZILLOW_RENT})
        listings = z.search_listings(zip_code="78704")
        self.assertEqual(len(listings), 1)  # None-price row dropped
        l = listings[0]
        self.assertIsInstance(l, Listing)
        self.assertEqual(l.id, "1")
        self.assertEqual(l.beds, 3)
        self.assertEqual(l.sqft, 1500)
        self.assertEqual(l.property_type, "single_family")
        self.assertIn("zillow.com", l.url)

    def test_max_price_and_min_beds(self):
        z = self._provider({"ForSale": ZILLOW_SALE, "ForRent": ZILLOW_RENT})
        self.assertEqual(len(z.search_listings(zip_code="78704", max_price=100000)), 0)
        self.assertEqual(len(z.search_listings(zip_code="78704", min_beds=4)), 0)

    def test_rental_comps_maps_and_filters(self):
        z = self._provider({"ForSale": ZILLOW_SALE, "ForRent": ZILLOW_RENT})
        comps = z.rental_comps(zip_code="78704")
        self.assertEqual(len(comps), 1)  # zero-sqft row dropped
        self.assertEqual(comps[0].monthly_rent, 2100)
        self.assertEqual(comps[0].property_type, "condo")

    def test_requires_key(self):
        import os
        old = os.environ.pop("RAPIDAPI_KEY", None)
        try:
            with self.assertRaises(ValueError):
                ZillowProvider(api_key=None)
        finally:
            if old is not None:
                os.environ["RAPIDAPI_KEY"] = old


# --- Realtor ----------------------------------------------------------------
REALTOR_SALE = {
    "data": {"home_search": {"results": [
        {"property_id": "p1", "list_price": 420000,
         "description": {"beds": 4, "baths": 3, "sqft": 2000, "type": "townhomes", "year_built": 2005},
         "location": {"address": {"postal_code": "78704", "city": "Austin", "state_code": "TX",
                                  "line": "5 Elm St", "coordinate": {"lat": 30.25, "lon": -97.76}}},
         "href": "https://realtor.com/p1"},
        {"property_id": "p2", "list_price": None,
         "description": {"beds": 2, "sqft": 800}},  # dropped: no price
    ]}}
}
REALTOR_RENT = {
    "data": {"home_search": {"results": [
        {"property_id": "r1", "list_price": 2500,
         "description": {"beds": 3, "baths": 2, "sqft": 1600, "type": "single_family"},
         "location": {"address": {"postal_code": "78704", "line": "7 Oak St"}}},
    ]}}
}


class TestRealtor(unittest.TestCase):
    def _provider(self, sale, rent):
        r = RealtorProvider(api_key="test")

        def fake_get(path, params):
            return sale if path == r.sale_path else rent
        r._get = fake_get  # type: ignore
        return r

    def test_results_walker_shapes(self):
        walk = RealtorProvider._results
        self.assertEqual(walk({"data": {"results": [1, 2]}}), [1, 2])
        self.assertEqual(walk({"properties": [3]}), [3])
        self.assertEqual(walk({"results": [4]}), [4])
        self.assertEqual(walk({"nope": 1}), [])

    def test_search_listings(self):
        r = self._provider(REALTOR_SALE, REALTOR_RENT)
        listings = r.search_listings(zip_code="78704")
        self.assertEqual(len(listings), 1)
        l = listings[0]
        self.assertEqual(l.id, "p1")
        self.assertEqual(l.beds, 4)
        self.assertEqual(l.sqft, 2000)
        self.assertEqual(l.property_type, "townhouse")
        self.assertEqual(l.location.latitude, 30.25)

    def test_rental_comps(self):
        r = self._provider(REALTOR_SALE, REALTOR_RENT)
        comps = r.rental_comps(zip_code="78704")
        self.assertEqual(len(comps), 1)
        self.assertEqual(comps[0].monthly_rent, 2500)
        self.assertEqual(comps[0].beds, 3)


# --- Combined ---------------------------------------------------------------
class _Stub(DataProvider):
    def __init__(self, listings, comps, boom=False):
        self._l, self._c, self._boom = listings, comps, boom

    def search_listings(self, **kw):
        if self._boom:
            raise RuntimeError("api down")
        return self._l

    def rental_comps(self, **kw):
        if self._boom:
            raise RuntimeError("api down")
        return self._c


def _mkL(addr, price=100000):
    return Listing(id=addr, location=Location("1", ), price=price, beds=3, baths=2, sqft=1500, address=addr)


def _mkC(addr, rent=2000):
    return RentalComp(id=addr, location=Location("1"), monthly_rent=rent, beds=3, baths=2, sqft=1500, address=addr)


class TestCombined(unittest.TestCase):
    def test_merges_and_dedups(self):
        a = _Stub([_mkL("1 A St"), _mkL("2 B St")], [_mkC("c1")])
        b = _Stub([_mkL("1 A St"), _mkL("3 C St")], [_mkC("c1"), _mkC("c2")])  # 1 A St dup
        combined = CombinedProvider([a, b])
        self.assertEqual(len(combined.search_listings()), 3)  # dedup by addr+price
        self.assertEqual(len(combined.rental_comps()), 2)     # dedup c1

    def test_skips_failing_source(self):
        good = _Stub([_mkL("1 A St")], [_mkC("c1")])
        bad = _Stub([], [], boom=True)
        combined = CombinedProvider([bad, good])
        self.assertEqual(len(combined.search_listings()), 1)

    def test_strict_raises(self):
        bad = _Stub([], [], boom=True)
        with self.assertRaises(RuntimeError):
            CombinedProvider([bad], strict=True).search_listings()

    def test_needs_a_provider(self):
        with self.assertRaises(ValueError):
            CombinedProvider([])


if __name__ == "__main__":
    unittest.main()
