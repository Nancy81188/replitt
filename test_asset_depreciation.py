"""Asset accounts with a depreciation %, monthly depreciation table, one entry per account and month."""
import tempfile
import unittest
from pathlib import Path

import fixed_assets
from database import Database


class AssetDepreciationTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self.folder.name) / "a.db"); self.db.initialize("secret-password-1"); self.user = 1
        fixed_assets.save_category(self.db, {"account_code": "2244", "name": "Vehicles", "annual_rate": "20", "depreciation_account": "681", "accumulated_account": "2824"}, self.user)
        for code, name, day, cost in (("FA-1", "Pickup truck", "15-01-2026", "12000"), ("FA-2", "Van", "01-03-2026", "6000")):
            fixed_assets.save_asset(self.db, {"asset_code": code, "name": name, "acquired_on": day, "start_on": day, "currency": "USD", "cost": cost, "residual": "0", "useful_months": "60",
                                              "annual_rate": "20", "asset_account": "2244", "depreciation_account": "681", "accumulated_account": "2824"}, user_id=self.user)

    def tearDown(self): self.folder.cleanup()

    def test_monthly_table_and_one_entry_per_account(self):
        group = fixed_assets.monthly_table(self.db, "31-03-2026")["groups"][0]
        rows = {a["code"]: a for a in group["assets"]}
        self.assertEqual([float(rows["FA-1"][k]) for k in ("value", "old", "current", "total", "net")], [12000, 400, 200, 600, 11400])
        self.assertEqual((float(rows["FA-2"]["current"]), float(group["to_post"])), (100, 300))
        with self.assertRaisesRegex(ValueError, "earlier months"): fixed_assets.post_category_month(self.db, "2244", "31-03-2026", self.user)
        for month in ("31-01-2026", "28-02-2026"): fixed_assets.post_category_month(self.db, "2244", month, self.user)
        result = fixed_assets.post_category_month(self.db, "2244", "31-03-2026", self.user)
        self.assertEqual((result["amount"], result["assets"]), (300, 2))
        lines = [(r["account_code"], r["debit"], r["credit"]) for r in self.db.journal() if r["entry_number"] == result["voucher"]]
        self.assertEqual(sorted(lines), [("2824", 0.0, 300.0), ("681", 300.0, 0.0)])
        with self.assertRaisesRegex(ValueError, "already posted"): fixed_assets.post_category_month(self.db, "2244", "31-03-2026", self.user)

    def test_net_value_never_negative_and_validation(self):
        late = fixed_assets.monthly_table(self.db, "31-12-2035")["groups"][0]
        self.assertTrue(all(float(a["net"]) >= 0 and float(a["current"]) == 0 for a in late["assets"]))
        with self.assertRaisesRegex(ValueError, "between 0 and 100"): fixed_assets.save_category(self.db, {"account_code": "2244", "name": "X", "annual_rate": "150", "depreciation_account": "681", "accumulated_account": "2824"})
        with self.assertRaisesRegex(ValueError, "not in the chart"): fixed_assets.save_category(self.db, {"account_code": "9999999", "name": "X", "annual_rate": "10", "depreciation_account": "681", "accumulated_account": "2824"})
        with self.assertRaisesRegex(ValueError, "still use"): fixed_assets.delete_category(self.db, "2244")


if __name__ == "__main__":
    unittest.main()
