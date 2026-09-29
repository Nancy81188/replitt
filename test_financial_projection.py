import unittest
from datetime import datetime

from financial_projection import completed_months, future_months, month_range, trailing_average, long_term_projection


class FinancialProjectionTest(unittest.TestCase):
    def test_completed_year_and_cross_year_forecast(self):
        today=datetime(2026,9,27)
        self.assertEqual(completed_months(2026,today),8)
        self.assertEqual(completed_months(2025,today),12)
        self.assertEqual(future_months(2026,8,6),[(2026,9),(2026,10),(2026,11),(2026,12),(2027,1),(2027,2)])
        self.assertEqual(future_months(2025,12,3),[(2026,1),(2026,2),(2026,3)])
        self.assertEqual(month_range(2024,2),("2024-02-01","2024-02-29"))

    def test_trailing_average_includes_zero_activity_months(self):
        self.assertEqual(trailing_average({6:{"amount":30},8:{"amount":60}},8,"amount"),30)
        self.assertEqual(trailing_average({},0,"amount"),0)

    def test_long_term_projection_compounds_growth_by_full_years(self):
        rows=long_term_projection({"sales":100000},2026,"2029-12-31",growth_rate=0.10)
        self.assertEqual([r["year"] for r in rows],[2027,2028,2029])
        self.assertEqual([r["source"] for r in rows],["growth","growth","growth"])
        self.assertAlmostEqual(rows[0]["values"]["sales"],110000)
        self.assertAlmostEqual(rows[1]["values"]["sales"],121000)
        self.assertAlmostEqual(rows[2]["values"]["sales"],133100)
        self.assertEqual(rows[-1]["fraction"],1.0)

    def test_long_term_projection_prorates_partial_final_year(self):
        rows=long_term_projection({"sales":100000},2026,"2028-06-30",growth_rate=0.0)
        self.assertEqual(rows[-1]["date_to"],"2028-06-30")
        self.assertLess(rows[-1]["fraction"],0.51)
        self.assertGreater(rows[-1]["fraction"],0.49)
        self.assertAlmostEqual(rows[-1]["values"]["sales"],100000*rows[-1]["fraction"],delta=5)

    def test_long_term_projection_prefers_saved_budget_over_growth(self):
        rows=long_term_projection({"sales":100000},2026,"2029-12-31",growth_rate=0.10,budget_by_year={2028:{"sales":500000}})
        by_year={r["year"]:r for r in rows}
        self.assertEqual(by_year[2028]["source"],"budget")
        self.assertEqual(by_year[2028]["values"]["sales"],500000.0)
        self.assertEqual(by_year[2027]["source"],"growth")
        self.assertEqual(by_year[2029]["source"],"growth")

    def test_long_term_projection_uses_per_year_growth_overrides(self):
        # 2027 grows +10%, 2028 +5% (per-year override), 2029 falls back to the default 20%
        rows=long_term_projection({"sales":100000},2026,"2029-12-31",growth_rate=0.20,
                                  growth_by_year={2027:0.10,2028:0.05})
        by_year={r["year"]:r for r in rows}
        self.assertAlmostEqual(by_year[2027]["values"]["sales"],110000)          # 100000 * 1.10
        self.assertAlmostEqual(by_year[2028]["values"]["sales"],115500)          # * 1.05
        self.assertAlmostEqual(by_year[2029]["values"]["sales"],138600)          # * 1.20 default
        self.assertEqual(by_year[2027]["growth_rate"],0.10)
        self.assertEqual(by_year[2029]["growth_rate"],0.20)

    def test_per_year_growth_saved_budget_still_wins(self):
        rows=long_term_projection({"sales":100000},2026,"2029-12-31",growth_rate=0.10,
                                  budget_by_year={2028:{"sales":500000}},growth_by_year={2027:0.30})
        by_year={r["year"]:r for r in rows}
        self.assertAlmostEqual(by_year[2027]["values"]["sales"],130000)          # per-year override applied
        self.assertEqual(by_year[2028]["source"],"budget")                        # saved budget still wins
        self.assertEqual(by_year[2028]["values"]["sales"],500000.0)

    def test_long_term_projection_rejects_bad_horizon(self):
        with self.assertRaisesRegex(ValueError,"at least one year"):
            long_term_projection({"sales":1},2026,"2026-12-31",growth_rate=0.1)
        with self.assertRaisesRegex(ValueError,"more than 5 years"):
            long_term_projection({"sales":1},2026,"2032-12-31",growth_rate=0.1)
        with self.assertRaises(ValueError):
            long_term_projection({"sales":1},2026,"not-a-date",growth_rate=0.1)


if __name__=="__main__": unittest.main()
