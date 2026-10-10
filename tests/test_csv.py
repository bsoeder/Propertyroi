import os
import tempfile
import unittest

from propertyroi.providers.csv_provider import CsvProvider

REDFIN = (
    "SALE TYPE,PROPERTY TYPE,ADDRESS,CITY,STATE OR PROVINCE,ZIP OR POSTAL CODE,"
    "PRICE,BEDS,BATHS,SQUARE FEET,YEAR BUILT,HOA/MONTH,URL,MLS#,LATITUDE,LONGITUDE\n"
    "MLS Listing,Single Family Residential,1 Main St,Lakewood,OH,44107,"
    "199000,3,2,1500,1960,0,https://redfin.com/1,MLS111,41.48,-81.79\n"
    "MLS Listing,Condo/Co-op,2 Lake Ave,Lakewood,OH,44107-1234,"
    "\"$275,000\",2,1.5,1100,2005,250,https://redfin.com/2,MLS222,41.49,-81.80\n"
    "MLS Listing,Vacant Land,TBD Rural Rd,Lakewood,OH,44107,"
    "45000,,,,,,https://redfin.com/3,MLS333,,\n"
    "MLS Listing,Single Family Residential,Bad Row,Lakewood,OH,44107,"
    ",4,3,2000,1990,0,https://redfin.com/4,MLS444,,\n"  # dropped: no price
)


class TestCsvProvider(unittest.TestCase):
    def _provider(self, text=REDFIN):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return CsvProvider(path=path)

    def test_requires_path(self):
        old = os.environ.pop("PROPERTYROI_CSV", None)
        try:
            with self.assertRaises(ValueError):
                CsvProvider(path=None)
        finally:
            if old is not None:
                os.environ["PROPERTYROI_CSV"] = old

    def test_missing_file(self):
        with self.assertRaises(ValueError):
            CsvProvider(path="/no/such/file.csv")

    def test_parses_redfin_export(self):
        p = self._provider()
        listings = p.search_listings()
        self.assertEqual(len(listings), 3)  # no-price row dropped
        by_id = {l.id: l for l in listings}
        sfr = by_id["MLS111"]
        self.assertEqual(sfr.price, 199000)
        self.assertEqual(sfr.beds, 3)
        self.assertEqual(sfr.sqft, 1500)
        self.assertEqual(sfr.property_type, "single_family")
        self.assertEqual(sfr.location.zip_code, "44107")
        self.assertEqual(sfr.location.latitude, 41.48)
        self.assertEqual(sfr.source, "csv")

    def test_money_and_zip_cleanup(self):
        p = self._provider()
        condo = next(l for l in p.search_listings() if l.id == "MLS222")
        self.assertEqual(condo.price, 275000)          # "$275,000" parsed
        self.assertEqual(condo.property_type, "condo")  # Condo/Co-op
        self.assertEqual(condo.location.zip_code, "44107")  # 44107-1234 trimmed
        self.assertEqual(condo.hoa_monthly, 250)

    def test_land_type(self):
        p = self._provider()
        land = next(l for l in p.search_listings() if l.id == "MLS333")
        self.assertEqual(land.property_type, "land")

    def test_filters(self):
        p = self._provider()
        self.assertEqual(len(p.search_listings(max_price=100000)), 1)  # only land @45k
        self.assertEqual(len(p.search_listings(min_beds=3)), 1)         # only the 3BR
        self.assertEqual(len(p.search_listings(property_type="condo")), 1)

    def test_no_rental_comps(self):
        self.assertEqual(self._provider().rental_comps(), [])

    def test_header_not_first_row(self):
        text = "Exported from Redfin on 2026-01-01\n\n" + REDFIN
        p = self._provider(text)
        self.assertEqual(len(p.search_listings()), 3)  # header auto-detected


if __name__ == "__main__":
    unittest.main()
