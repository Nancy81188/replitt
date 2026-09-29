"""Coverage for configurable currencies and the stock ageing report."""
import secrets
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from database import Database
from inventory import build_report, carry_forward, list_warehouses, run_costing, save_document, save_item, save_settings, save_warehouse
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

    def test_warehouse_costs_reconcile_after_transfer_and_new_receipt(self):
        item = save_item(self.db, {"sku": "LAYER", "name": "Layered stock"}, self.user)
        main = next(w["id"] for w in list_warehouses(self.db) if w["code"] == "MAIN")
        second = save_warehouse(self.db, {"code": "WH2", "name": "Second Store"}, self.user)["id"]
        def doc(kind, date, warehouse, quantity, cost=0, destination=None):
            return save_document(self.db, {"doc_type": kind, "doc_date": date, "warehouse_id": warehouse,
                                            "to_warehouse_id": destination},
                                 [{"sku": "LAYER", "quantity": quantity, "unit_cost": cost}], self.user)
        doc("receipt", "01-01-2026", main, 10, 2)
        doc("transfer", "02-01-2026", main, 6, destination=second)
        doc("receipt", "03-01-2026", main, 10, 8)
        doc("issue", "04-01-2026", second, 2)
        for method, expected, issue_cost in (
            ("fifo", {main: 88, second: 8}, 2),
            ("average", {main: 70, second: 20}, 5),
        ):
            with self.subTest(method=method):
                movements = []
                state = run_costing(self.db, "2026-01-04", method, lambda row, unit, value: movements.append((row, unit, value)))[item["id"]]
                self.assertEqual(state["qty"], 18)
                self.assertEqual(state["by_warehouse"], {main: 14, second: 4})
                self.assertEqual(state["warehouse_value"], expected)
                self.assertEqual(state["value"], sum(expected.values()))
                self.assertEqual(next(unit for row, unit, _ in movements if row["doc_type"] == "issue"), issue_cost)
                transfer_units = [unit for row, unit, _ in movements if row["doc_type"] == "transfer"]
                self.assertEqual(transfer_units, [2, 2])
                self.assertEqual(sum((value for row, _, value in movements if row["doc_type"] != "transfer"), 0),
                                 state["value"])
                report = build_report(self.db, "valuation", {"date_to": "04-01-2026", "method": method})
                by_wh = {row[0]: row[2] for row in report["sections"][1]["rows"]}
                self.assertEqual(by_wh, {"MAIN": expected[main], "WH2": expected[second]})
                self.assertEqual(report["sections"][0]["rows"][-1][6], sum(by_wh.values()))
                for wid, code in ((main, "MAIN"), (second, "WH2")):
                    filtered = build_report(self.db, "valuation", {"date_to": "04-01-2026", "method": method, "warehouse_id": wid})
                    self.assertEqual(filtered["sections"][0]["rows"][-1][6], expected[wid])
                analysis = build_report(self.db, "analysis3d", {"date_to": "04-01-2026", "method": method, "measure": "value"})
                headers = analysis["sections"][0]["headers"]
                totals = analysis["sections"][0]["rows"][-1]
                self.assertEqual(totals[headers.index("MAIN")], expected[main])
                self.assertEqual(totals[headers.index("WH2")], expected[second])
                self.assertEqual(totals[-1], sum(by_wh.values()))
                summary = build_report(self.db, "summary", {"date_to": "04-01-2026", "method": method})
                summary_wh = {row[0]: row[2] for row in summary["sections"][2]["rows"]}
                self.assertEqual(summary_wh, {"MAIN": expected[main], "WH2": expected[second]})
                health = build_report(self.db, "health", {"date_to": "04-01-2026", "method": method,
                                                           "warehouse_id": second})
                self.assertTrue(any(row[6] == expected[second] for section in health["sections"]
                                    for row in section["rows"] if len(row) > 6 and row[1] == "LAYER"))
                supplier = build_report(self.db, "supplier_stock", {"date_to": "04-01-2026", "method": method,
                                                                     "warehouse_id": second})
                self.assertEqual(supplier["sections"][0]["rows"][-1][5], expected[second])
                card = build_report(self.db, "stock_card", {"date_to": "04-01-2026", "date_from": "01-01-2026",
                                                             "method": method, "item_id": item["id"], "warehouse_id": second})
                self.assertEqual(card["sections"][0]["rows"][-1][-1], expected[second])
                if method == "average":
                    self.assertTrue(any("revaluation" in row[2] for row in card["sections"][0]["rows"]))
                if method == "fifo":
                    aged = build_report(self.db, "ageing", {"date_to": "04-01-2026", "method": method,
                                                              "warehouse_id": second})
                    self.assertEqual(next(row for row in aged["sections"][1]["rows"] if row[0] == "LAYER")[5], expected[second])

    def test_warehouse_rounding_keeps_displayed_total_in_balance(self):
        item = save_item(self.db, {"sku": "CENT", "name": "Fractional cost"}, self.user)
        second = save_warehouse(self.db, {"code": "WH2", "name": "Second Store"}, self.user)["id"]
        for warehouse in ("MAIN", second):
            save_document(self.db, {"doc_type": "receipt", "doc_date": "01-01-2026", "warehouse_id": warehouse},
                          [{"sku": "CENT", "quantity": 1, "unit_cost": "0.005"}], self.user)
        report = build_report(self.db, "valuation", {"date_to": "01-01-2026", "method": "fifo"})
        self.assertEqual(report["sections"][0]["rows"][-1][6], sum((row[2] for row in report["sections"][1]["rows"]), 0))
        self.assertEqual(report["sections"][0]["rows"][-1][6], Decimal("0.01"))
        for row in report["sections"][1]["rows"]:
            wh = next(w["id"] for w in list_warehouses(self.db) if w["code"] == row[0])
            filtered = build_report(self.db, "valuation", {"date_to": "01-01-2026", "method": "fifo", "warehouse_id": wh})
            self.assertEqual(filtered["sections"][0]["rows"][-1][6], row[2])
            card = build_report(self.db, "stock_card", {"date_to": "01-01-2026", "date_from": "01-01-2026",
                                                         "method": "fifo", "warehouse_id": wh, "item_id": item["id"]})
            self.assertEqual(card["sections"][0]["rows"][-1][-1], row[2])

    def test_zero_cost_fifo_layer_survives_year_end_opening(self):
        item = save_item(self.db, {"sku": "FREE", "name": "Free and paid stock"}, self.user)
        save_settings(self.db, {"currency": "USD", "method": "fifo"}, self.user)
        save_document(self.db, {"doc_type": "adjustment_in", "doc_date": "01-12-2025", "warehouse_id": "MAIN"},
                      [{"sku": "FREE", "quantity": 2, "unit_cost": 0}], self.user)
        save_document(self.db, {"doc_type": "receipt", "doc_date": "02-12-2025", "warehouse_id": "MAIN"},
                      [{"sku": "FREE", "quantity": 2, "unit_cost": 10}], self.user)
        target = Database(Path(self.folder.name) / "next-year.db")
        target.initialize(secrets.token_hex(16))
        save_settings(target, {"currency": "USD", "method": "fifo"}, self.user)
        carry_forward(self.db, target, 2026, self.user)
        opening = run_costing(target, "2026-01-01", "fifo")[item["id"]]
        self.assertEqual((opening["qty"], opening["value"]), (4, 20))
        self.assertEqual([(layer[0], layer[1]) for layer in opening["warehouse_layers"][1]],
                         [(2, 0), (2, 10)])



if __name__ == "__main__":
    unittest.main()
