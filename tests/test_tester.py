import os
import unittest

from propertyroi.estimator import RentEstimator
from propertyroi.models import Listing, Location
from propertyroi.tester import AccuracyTester, LabeledProperty, load_labeled


def labeled(cid, rent, sqft=1500, beds=3, zip_code="10001"):
    return LabeledProperty(
        listing=Listing(id=cid, location=Location(zip_code), price=0, beds=beds, baths=2, sqft=sqft),
        actual_rent=rent,
    )


class TestTester(unittest.TestCase):
    def test_empty_report(self):
        report = AccuracyTester().evaluate([])
        self.assertEqual(report.n, 0)
        self.assertEqual(report.coverage, 0.0)

    def test_perfect_when_consistent(self):
        # Rent exactly proportional to sqft -> estimator should nail it.
        data = [labeled(f"p{i}", 2000 + i * 100, sqft=1000 + i * 50) for i in range(8)]
        report = AccuracyTester().evaluate(data)
        self.assertEqual(report.n, 8)
        self.assertLess(report.mape, 0.15)
        self.assertGreater(report.within_20pct, 0.5)

    def test_metrics_ranges(self):
        data = [labeled(f"p{i}", 1800 + (i % 3) * 200) for i in range(9)]
        report = AccuracyTester().evaluate(data)
        self.assertGreaterEqual(report.within_5pct, 0)
        self.assertLessEqual(report.within_5pct, 1)
        self.assertLessEqual(report.within_5pct, report.within_10pct)
        self.assertLessEqual(report.within_10pct, report.within_20pct)
        self.assertGreaterEqual(report.mae, 0)
        self.assertGreaterEqual(report.rmse, report.mae - 1e-9)  # RMSE >= MAE

    def test_leave_one_out_excludes_self(self):
        # If self were included, a unique outlier would be predicted perfectly.
        data = [labeled("normal1", 2000), labeled("normal2", 2000),
                labeled("normal3", 2000), labeled("outlier", 5000)]
        report = AccuracyTester().evaluate(data)
        outlier = next(p for p in report.predictions if p.id == "outlier")
        # Predicted from the *other* comps (~2000), so error should be large.
        self.assertGreater(outlier.abs_error, 1000)

    def test_bundled_eval_data_accuracy(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "eval_labeled.json")
        report = AccuracyTester().evaluate(load_labeled(path))
        self.assertGreater(report.n, 0)
        self.assertEqual(report.coverage, 1.0)
        # The synthetic data has a real signal; estimator should be decent.
        self.assertLess(report.mape, 0.15)
        self.assertGreater(report.r2, 0.7)

    def test_summary_is_string(self):
        report = AccuracyTester().evaluate([labeled(f"p{i}", 2000) for i in range(4)])
        self.assertIn("Accuracy Report", report.summary())


if __name__ == "__main__":
    unittest.main()
