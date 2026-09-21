import unittest

from propertyroi.analyzer import Analyzer
from propertyroi.estimator import RentEstimator
from propertyroi.models import Listing, Location
from propertyroi.providers.base import DataProvider
from propertyroi.providers.mvba import MvbaProvider, _acres_from, _to_float

MVBA_HTML = """
<html><body>
<table>
  <tr><th>Account</th><th>County</th><th>Legal Description</th>
      <th>Property Address</th><th>Adjudged Value</th><th>Minimum Bid</th><th>Sale Date</th></tr>
  <tr><td>R12345</td><td>Fayette</td><td>ABST 100, 5.0 AC</td>
      <td>TBD County Rd 12</td><td>$40,000.00</td><td>$8,500.00</td><td>04/07/2026</td></tr>
  <tr><td>R67890</td><td>Fayette</td><td>LOT 3 BLK 2 SMITH ADDN</td>
      <td>123 Main St</td><td>$120,000</td><td>$15,000</td><td>04/07/2026</td></tr>
  <tr><td>R00000</td><td>Fayette</td><td>struck off</td>
      <td>n/a</td><td>$0</td><td></td><td>04/07/2026</td></tr>
</table>
</body></html>
"""

MVBA_JSON = {
    "data": [
        {"account": "A1", "county": "Bell", "legalDescription": "10 ACRES ABST 5",
         "situsAddress": "TBD FM 439", "adjudgedValue": 50000, "minimumBid": 6000,
         "saleDate": "2026-05-05"},
        {"account": "A2", "county": "Bell", "description": "no bid here",
         "address": "1 Nowhere", "adjudged": 10000},  # dropped: no min bid
    ]
}


class TestMvbaHelpers(unittest.TestCase):
    def test_to_float(self):
        self.assertEqual(_to_float("$8,500.00"), 8500.0)
        self.assertEqual(_to_float("5.0 AC"), 5.0)
        self.assertEqual(_to_float(1234), 1234.0)
        self.assertIsNone(_to_float("n/a"))
        self.assertIsNone(_to_float(None))

    def test_acres_from(self):
        self.assertEqual(_acres_from("ABST 100, 5.0 AC"), 5.0)
        self.assertEqual(_acres_from("10 ACRES ABST 5"), 10.0)
        self.assertIsNone(_acres_from("LOT 3 BLK 2"))


class TestMvbaProvider(unittest.TestCase):
    def _provider(self, body, ctype=""):
        p = MvbaProvider(url="https://example.com/sale")
        data = body if isinstance(body, bytes) else body.encode()
        p._fetch = lambda url=None: (data, ctype)  # type: ignore
        return p

    def test_html_parsing_and_land_fields(self):
        p = self._provider(MVBA_HTML, "text/html")
        listings = p.search_listings()
        self.assertEqual(len(listings), 2)  # zero-bid row dropped
        first = listings[0]
        self.assertIsInstance(first, Listing)
        self.assertEqual(first.id, "R12345")
        self.assertEqual(first.property_type, "land")
        self.assertEqual(first.source, "mvba")
        self.assertTrue(first.is_land)
        self.assertEqual(first.price, 8500.0)
        self.assertEqual(first.adjudged_value, 40000.0)
        self.assertEqual(first.lot_acres, 5.0)
        self.assertEqual(first.location.county, "Fayette")
        self.assertEqual(first.sale_date, "04/07/2026")

    def test_json_parsing(self):
        import json as _json
        p = MvbaProvider(url="https://example.com/feed.json")
        p._fetch = lambda url=None: (_json.dumps(MVBA_JSON).encode(), "application/json")  # type: ignore
        listings = p.search_listings()
        self.assertEqual(len(listings), 1)  # no-bid row dropped
        l = listings[0]
        self.assertEqual(l.price, 6000.0)
        self.assertEqual(l.adjudged_value, 50000.0)
        self.assertEqual(l.lot_acres, 10.0)
        self.assertEqual(l.location.county, "Bell")

    def test_max_price_filter(self):
        p = self._provider(MVBA_HTML, "text/html")
        cheap = p.search_listings(max_price=10000)
        self.assertEqual(len(cheap), 1)
        self.assertEqual(cheap[0].id, "R12345")

    def test_residential_filter_returns_nothing(self):
        p = self._provider(MVBA_HTML, "text/html")
        self.assertEqual(p.search_listings(property_type="single_family"), [])

    def test_no_rental_comps(self):
        p = self._provider(MVBA_HTML, "text/html")
        self.assertEqual(p.rental_comps(), [])

    def test_index_crawl_follows_bid_sheet_links(self):
        # An index page with no bid table, linking to a county bid sheet.
        index_html = """
        <html><body><h1>Upcoming Tax Sales</h1>
          <a href="/wp-content/TaxUploads/FayetteBidSheet.html">Fayette County</a>
          <a href="/about">About us</a>
        </body></html>
        """
        base = "https://mvbalaw.com/tax-sales/"
        sheet_url = "https://mvbalaw.com/wp-content/TaxUploads/FayetteBidSheet.html"

        p = MvbaProvider(url=base)

        def fake_fetch(url=None):
            u = url or base
            if u == base:
                return index_html.encode(), "text/html"
            if u == sheet_url:
                return MVBA_HTML.encode(), "text/html"
            raise AssertionError(f"unexpected fetch {u}")

        p._fetch = fake_fetch  # type: ignore
        listings = p.search_listings()
        self.assertEqual(len(listings), 2)  # parsed from the crawled sheet
        self.assertEqual(listings[0].id, "R12345")
        self.assertEqual(listings[0].url, sheet_url)

    def test_bid_sheet_link_extraction(self):
        p = MvbaProvider(url="https://mvbalaw.com/tax-sales/")
        html = ('<a href="/wp-content/TaxUploads/x.pdf">a</a>'
                '<a href="https://mvbalaw.com/tax-sales/">self</a>'
                '<a href="/privacy">no</a>'
                '<a href="/county-tax-sale-info">yes</a>')
        links = p._bid_sheet_links(html, "https://mvbalaw.com/tax-sales/")
        self.assertIn("https://mvbalaw.com/wp-content/TaxUploads/x.pdf", links)
        self.assertIn("https://mvbalaw.com/county-tax-sale-info", links)
        self.assertNotIn("https://mvbalaw.com/privacy", links)
        self.assertNotIn("https://mvbalaw.com/tax-sales/", links)  # skip self

    def test_pdf_without_pdfplumber_raises_clear_error(self):
        import builtins
        p = MvbaProvider(url="https://mvbalaw.com/sheet.pdf")
        p._fetch = lambda url=None: (b"%PDF-1.4 fake", "application/pdf")  # type: ignore
        real_import = builtins.__import__

        def no_pdfplumber(name, *a, **k):
            if name == "pdfplumber":
                raise ImportError("no pdfplumber")
            return real_import(name, *a, **k)

        builtins.__import__ = no_pdfplumber
        try:
            with self.assertRaises(ValueError) as ctx:
                p.search_listings()
            self.assertIn("pdfplumber", str(ctx.exception))
        finally:
            builtins.__import__ = real_import

    def test_ingest_table_shared_mapping(self):
        p = MvbaProvider(url="https://x/y")
        table = [
            ["Account", "County", "Legal Description", "Adjudged Value", "Minimum Bid"],
            ["R1", "Bell", "3.0 AC ABST 9", "$30,000", "$5,000"],
        ]
        out = []
        p._ingest_table(table, out, 0, "https://x/y")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].price, 5000.0)
        self.assertEqual(out[0].adjudged_value, 30000.0)
        self.assertEqual(out[0].lot_acres, 3.0)

    def test_requires_url(self):
        import os
        old = os.environ.pop("MVBA_SALES_URL", None)
        try:
            with self.assertRaises(ValueError):
                MvbaProvider(url=None)
        finally:
            if old is not None:
                os.environ["MVBA_SALES_URL"] = old


class _StaticMvba(DataProvider):
    """Serve fixed land listings without network."""

    def __init__(self, listings):
        self._l = listings

    def search_listings(self, **kw):
        return self._l

    def rental_comps(self, **kw):
        return []


class TestLandAnalysis(unittest.TestCase):
    def _land(self, price, adjudged, acres):
        return Listing(
            id="L", location=Location("", county="Fayette"), price=price,
            beds=0, baths=0, sqft=0, property_type="land", source="mvba",
            lot_acres=acres, adjudged_value=adjudged,
        )

    def test_discount_and_per_acre(self):
        provider = _StaticMvba([self._land(8500, 40000, 5.0)])
        a = Analyzer(provider, RentEstimator()).analyze(provider.search_listings()[0])
        self.assertTrue(a.is_land)
        self.assertAlmostEqual(a.discount_to_adjudged, 1 - 8500 / 40000, places=4)
        self.assertAlmostEqual(a.price_per_acre, 1700.0, places=1)
        self.assertGreater(a.land_score, 0)
        # Primary score is the land score for land listings.
        self.assertEqual(a.score, a.land_score)

    def test_bigger_discount_scores_higher(self):
        prov = _StaticMvba([])
        analyzer = Analyzer(prov, RentEstimator())
        small = analyzer.analyze(self._land(35000, 40000, 5.0)).land_score
        big = analyzer.analyze(self._land(5000, 40000, 5.0)).land_score
        self.assertGreater(big, small)

    def test_land_metrics_in_dict(self):
        prov = _StaticMvba([])
        a = Analyzer(prov, RentEstimator()).analyze(self._land(8500, 40000, 5.0))
        m = a.to_dict()["metrics"]
        self.assertTrue(m["is_land"])
        self.assertIn("discount_to_adjudged", m)
        self.assertIn("price_per_acre", m)
        self.assertIn("land_score", m)
        self.assertIn("rental_score", m)


if __name__ == "__main__":
    unittest.main()
