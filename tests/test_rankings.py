import os
import tempfile
import unittest

from propertyroi import metros
from propertyroi.rankings import RankingEngine

CSV = (
    "zip,city,state,metro,median_price,median_rent,as_of\n"
    "48201,Detroit,MI,\"Detroit, MI\",90000,1300,test\n"
    "44101,Cleveland,OH,\"Cleveland, OH\",110000,1250,test\n"
    "78704,Austin,TX,\"Austin, TX\",550000,2000,test\n"
    "78745,Austin,TX,\"Austin, TX\",480000,1900,test\n"
    "94110,San Francisco,CA,\"San Francisco, CA\",1300000,3300,test\n"
)


class RankBase(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write(CSV)
        self.addCleanup(os.remove, self.path)


class TestRankings(RankBase):
    def test_ranks_by_yield(self):
        rows = RankingEngine(path=self.path).rank()
        self.assertEqual(rows[0].zip_code, "48201")   # Detroit: highest yield
        self.assertEqual(rows[-1].zip_code, "94110")  # SF: lowest yield
        # gross yield = rent*12/price
        self.assertAlmostEqual(rows[0].gross_yield, 1300 * 12 / 90000, places=4)
        self.assertGreater(rows[0].score, rows[-1].score)

    def test_sorted_descending(self):
        rows = RankingEngine(path=self.path).rank()
        scores = [r.score for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_filters(self):
        e = RankingEngine(path=self.path)
        self.assertEqual(len(e.rank(state="TX")), 2)
        self.assertEqual(len(e.rank(metro="Austin")), 2)
        self.assertEqual(len(e.rank(max_price=200000)), 2)  # Detroit + Cleveland
        self.assertEqual(len(e.rank(limit=1)), 1)

    def test_to_dict(self):
        d = RankingEngine(path=self.path).rank(limit=1)[0].to_dict()
        for k in ("zip_code", "metro", "gross_yield", "cap_rate", "rent_to_price", "score"):
            self.assertIn(k, d)

    def test_cap_below_yield(self):
        r = RankingEngine(path=self.path).rank(limit=1)[0]
        self.assertLess(r.cap_rate, r.gross_yield)  # expenses reduce cap below gross

    def test_bundled_dataset_loads(self):
        e = RankingEngine()  # the shipped data/zip_market_stats.csv
        self.assertGreater(len(e.rank(limit=0)), 100)
        self.assertEqual(e.rank(limit=5)[0].score, max(r.score for r in e.rank(limit=0)))


class TestMetros(RankBase):
    def test_load_and_group(self):
        m = metros.load_metros(self.path)
        self.assertEqual(sorted(m["Austin, TX"]), ["78704", "78745"])

    def test_resolve_exact_and_substring(self):
        name, zips = metros.resolve("austin", self.path)
        self.assertEqual(name, "Austin, TX")
        self.assertEqual(len(zips), 2)
        name, zips = metros.resolve("Detroit, MI", self.path)
        self.assertEqual(zips, ["48201"])

    def test_resolve_unknown(self):
        name, zips = metros.resolve("Nowhereville", self.path)
        self.assertIsNone(name)
        self.assertEqual(zips, [])

    def test_bundled_metros(self):
        self.assertIn("Austin, TX", metros.list_metros())
        self.assertGreater(len(metros.list_metros()), 30)


if __name__ == "__main__":
    unittest.main()
