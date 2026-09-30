"""Coverage for configurable currencies and the stock ageing report."""
import secrets
import tempfile
import unittest
from pathlib import Path

from database import Database
from inventory import build_report, save_document, save_item
from ledger_reports import build_account_report


class CurrencyAgeingTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "company.db")
        password = secrets.token_hex(16)
        self.db.initialize(password)
        self.user = self.db.user_for_token(self.db.login("admin", password)["token"])["id"]

    def tearDown(self):
        self.folder.cleanup()

    def test_new_currency_and_trial_balance_columns(self):
        self.db.save_currency("GBP", "British Pound", self.user)
        self.db.save_exchange_rate({"date_from": "01-09-2026", "from_currency": "USD",
                                    "to_currency": "GBP", "rate": "0.8"}, self.user)
        self.db.import_invoice({"invoice_number": "DEMO-1", "invoice_date": "20-09-2026",
                                "party_name": "Example", "kind": "sale", "currency": "USD",
                                "subtotal": 100, "vat": 11, "total": 111}, self.user)
        for first, second in (("EUR", "AED"), ("GBP", "USD")):
            result = build_account_report(self.db, {"first_column": first, "second_column": second,
                                                     "date_from": "01-09-2026", "date_to": "30-09-2026"})
            self.assertTrue(any(first in str(header) for section in result["sections"]
                                for header in section["headers"]))
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.db.save_currency("GBP", "Other", self.user)

    def test_stock_ageing_buckets_and_warehouse(self):
        save_item(self.db, {"sku": "DEMO", "name": "Example Item", "unit": "unit"}, self.user)
        save_document(self.db, {"doc_type": "receipt", "doc_date": "01-01-2026", "warehouse_id": "MAIN"},
                      [{"sku": "DEMO", "quantity": 10, "unit_cost": 2}], self.user)
        section = build_report(self.db, "ageing", {"date_to": "26-09-2026"})["sections"][1]
        item = next(row for row in section["rows"] if row[0] == "DEMO")
        self.assertEqual((item[4], item[5], item[13]), (10, 20, 20))
        warehouse = build_report(self.db, "ageing", {"date_to": "26-09-2026", "warehouse_id": 1})["sections"][1]
        self.assertEqual(next(row for row in warehouse["rows"] if row[0] == "DEMO")[4], 10)

    def test_stock_card_item_range(self):
        first = save_item(self.db, {"sku": "A-001", "name": "First"}, self.user)
        save_item(self.db, {"sku": "B-002", "name": "Second"}, self.user)
        last = save_item(self.db, {"sku": "C-003", "name": "Last"}, self.user)
        result = build_report(self.db, "stock_card", {"item_id": first["id"], "item_to_id": last["id"],
                                                      "date_from": "01-01-2026", "date_to": "26-09-2026"})
        self.assertEqual(len(result["sections"]), 4)
        self.assertIn("B-002", result["sections"][1]["heading"])
        self.assertEqual(result["sections"][-1]["heading"], "Total closing stock by unit")
        valuation = build_report(self.db, "valuation", {"item_id": first["id"], "item_to_id": last["id"],
                                                     "include_zero": True, "date_to": "26-09-2026"})
        self.assertTrue(any(row[0] == "B-002" for row in valuation["sections"][0]["rows"]))
        self.assertEqual(valuation["sections"][-1]["heading"], "Total stock quantity by unit")
        with self.assertRaisesRegex(ValueError, "before Item To"):
            build_report(self.db, "stock_card", {"item_id": last["id"], "item_to_id": first["id"]})



if __name__ == "__main__":
    unittest.main()
