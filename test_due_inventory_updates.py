"""Due terms and new stock report checks."""
import secrets
import tempfile
import unittest
from pathlib import Path

from business_reports import ageing
from database import Database
from inventory import build_report, save_count, save_document, save_item


class DueAndInventoryTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "test.db")
        password = secrets.token_hex(16)
        self.db.initialize(password)
        self.user = self.db.user_for_token(self.db.login("admin", password)["token"])["id"]

    def tearDown(self):
        self.folder.cleanup()

    def test_party_terms_and_invoice_override(self):
        for category in ("client", "supplier"):
            name = "Example " + category
            party = self.db.save_party({"name": name, "account_category": category, "due_days": 30}, self.user)
            kind = "sale" if category == "client" else "purchase"
            invoice_id = self.db.import_invoice({"invoice_number": category, "invoice_date": "01-09-2026",
                "party_name": name, "kind": kind, "currency": "USD", "subtotal": 100, "vat": 11, "total": 111}, self.user)
            with self.db.connect() as db:
                due = db.execute("SELECT due_date FROM invoices WHERE id=?", (invoice_id,)).fetchone()["due_date"]
            self.assertEqual(due, "01-10-2026")
            self.assertEqual(party["due_days"], 30)
            self.db.import_invoice({"invoice_number": category + "-special", "invoice_date": "01-09-2026",
                "due_date": "10-09-2026", "party_name": name, "kind": kind, "currency": "USD",
                "subtotal": 100, "vat": 11, "total": 111}, self.user)
        with self.db.connect() as db:
            self.assertEqual(db.execute("SELECT due_date FROM invoices WHERE invoice_number='client-special'").fetchone()[0], "10-09-2026")
        result = ageing(self.db, {"side": "receivables", "date_to": "26-09-2026"})
        self.assertTrue(any("client" in str(section["rows"]) for section in result["sections"]))
        current = result["sections"][-1]["rows"][-1][-1]
        future = ageing(self.db, {"side": "receivables", "date_to": "26-10-2026"})["sections"][-1]["rows"][-1][-1]
        self.assertEqual((current, future), (111, 222))
        with self.assertRaisesRegex(ValueError, "Due days"):
            self.db.save_party({"name": "Wrong", "due_days": -1}, self.user)

    def test_stock_reports_and_count_snapshot(self):
        item = save_item(self.db, {"sku": "DEMO", "name": "Widget"}, self.user)
        save_document(self.db, {"doc_type": "receipt", "doc_date": "01-09-2026", "warehouse_id": "MAIN"},
                      [{"sku": "DEMO", "quantity": 10, "unit_cost": 2}], self.user)
        for name in ("turnover", "supplier_stock"):
            result = build_report(self.db, name, {"date_from": "01-09-2026", "date_to": "26-09-2026", "item_id": item["id"]})
            self.assertTrue(any("DEMO" in str(section["rows"]) for section in result["sections"]))
        save_count(self.db, {"count_date": "20-09-2026", "warehouse_id": 1},
                   [{"item_id": item["id"], "sku": "DEMO", "counted": 8}], self.user, post=True)
        result = build_report(self.db, "count_variances", {"date_from": "01-09-2026", "date_to": "26-09-2026"})
        row = result["sections"][0]["rows"][0]
        self.assertEqual((row[5], row[6], row[7], row[8]), (10, 8, -2, -4))
        by_warehouse = build_report(self.db, "analysis3d", {"date_from": "01-09-2026", "date_to": "26-09-2026",
                                                              "rows": "item", "columns": "warehouse", "measure": "quantity"})
        self.assertEqual(by_warehouse["sections"][0]["rows"][0][1], 8)
        by_month = build_report(self.db, "analysis3d", {"date_from": "01-09-2026", "date_to": "26-09-2026",
                                                          "rows": "category", "columns": "month", "measure": "value"})
        self.assertEqual(by_month["sections"][0]["rows"][0][1], 16)
        health = build_report(self.db, "health", {"date_to": "26-09-2026", "days": "30"})
        self.assertTrue(any(row[0] == "No supplier" for row in health["sections"][0]["rows"]))

    def test_daily_exchange_rate_is_average_of_entries(self):
        data = {"date_from": "20-09-2026", "from_currency": "EUR", "to_currency": "USD"}
        self.db.save_exchange_rate({**data, "rate": "1.10"}, self.user)
        self.db.save_exchange_rate({**data, "rate": "1.20"}, self.user)
        with self.db.connect() as db:
            day = db.execute("SELECT rate FROM exchange_rates WHERE rate_date='20-09-2026' AND from_currency='EUR' AND to_currency='USD'").fetchone()[0]
            derived = db.execute("SELECT rate FROM exchange_rates WHERE rate_date='20-09-2026' AND from_currency='EUR' AND to_currency='LBP'").fetchone()[0]
        self.assertEqual(float(day), 1.15)
        self.assertAlmostEqual(float(derived), 1.15 * 89500)
        with self.db.connect() as db:
            samples = db.execute("SELECT COUNT(*) FROM exchange_rate_samples WHERE rate_date='20-09-2026' AND from_currency='EUR' AND to_currency='USD'").fetchone()[0]
        self.assertEqual(samples, 2)


if __name__ == "__main__":
    unittest.main()
