"""The preparation worksheet must agree with the quarterly VAT calculation."""
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from database import Database
from vat_return import _rounded_up, build_vat_return, export_sections, filing_worksheet
from pdf_import import _parse_invoice_text


class VATFilingWorksheetTest(unittest.TestCase):
    def test_payable_rounding_boundary_is_explicitly_an_unverified_estimate(self):
        for day, amount, expected in (
            ("2024-11-24", "9999.49", "9999"),
            ("2024-11-24", "9999.50", "10000"),
            ("2024-11-25", "0.01", "10000"),
            ("2024-11-25", "9999.99", "10000"),
            ("2024-11-25", "10000", "10000"),
            ("2024-11-25", "10000.01", "20000"),
            ("2026-03-31", "20000", "20000"),
            ("2026-03-31", "0", "0"),
            ("2026-03-31", "-100", "-100"),
        ):
            with self.subTest(day=day, amount=amount):
                self.assertEqual(_rounded_up(Decimal(amount), day), Decimal(expected))

    def test_document_date_and_currency_conversion_with_credit_and_payable(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            with db.connect() as connection:
                user_id = connection.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            for day, code, rate in (
                ("24-11-2024", "USD", "100"),
                ("25-11-2024", "USD", "200"),
                ("25-11-2024", "EUR", "300"),
            ):
                db.save_exchange_rate({"rate_date": day, "from_currency": code,
                                       "to_currency": "LBP", "rate": rate}, user_id)
            for number, day, code, vat in (
                ("USD-BEFORE", "24-11-2024", "USD", 11),
                ("USD-AFTER", "25-11-2024", "USD", 11),
                ("EUR-AFTER", "25-11-2024", "EUR", 11),
                ("LBP-AFTER", "25-11-2024", "LBP", 500),
            ):
                db.import_invoice({"invoice_number": number, "invoice_date": day,
                                   "party_name": "Buyer", "kind": "sale", "currency": code,
                                   "subtotal": 100, "vat": vat, "total": 100 + vat}, user_id)
            result = build_vat_return(db, 2024, 4, credit_brought_forward=100)
            converted = {doc["number"]: doc["vat_lbp"] for doc in result["documents"]}
            self.assertEqual(converted, {"USD-BEFORE": Decimal("1100"),
                                         "USD-AFTER": Decimal("2200"),
                                         "EUR-AFTER": Decimal("3300"),
                                         "LBP-AFTER": Decimal("500")})
            self.assertEqual(result["totals_lbp"]["sales"], Decimal("7100"))
            self.assertEqual(result["net_after_credit_lbp"], Decimal("7000"))
            self.assertEqual(result["payable_lbp"], Decimal("10000"))
            self.assertTrue(any("customs rate" in warning for warning in result["warnings"]))
            self.assertTrue(any("has not been verified" in warning for warning in result["warnings"]))
            _, meta, _ = export_sections(result)
            self.assertTrue(any("unverified worksheet estimate" in note for note in meta))
            notices, _ = filing_worksheet(result, {})
            self.assertTrue(any("has not been verified" in note for note in notices))

    def test_filing_values_and_employer_details(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            with db.connect() as connection:
                user_id = connection.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            db.import_invoice({"invoice_number": "SALE-1", "invoice_date": "15-03-2026",
                               "party_name": "Buyer", "kind": "sale", "currency": "LBP",
                               "subtotal": 1000000, "vat": 110000, "total": 1110000}, user_id)
            db.import_invoice({"invoice_number": "BUY-1", "invoice_date": "18-03-2026",
                               "party_name": "Supplier", "kind": "purchase", "currency": "LBP",
                               "subtotal": 200000, "vat": 22000, "total": 222000,
                               "vat_use": "taxable"}, user_id)
            result = build_vat_return(db, 2026, 1)
            notices, sections = filing_worksheet(result, {"company_name": "Test Company", "company_mof": "123",
                                                            "company_address": "Beirut", "company_phone": "01"})
            fields = dict(sections[0]["rows"])
            self.assertEqual(fields["Registered company name"], "Test Company")
            refs = {row[0]: row for section in (sections[2], sections[3], sections[5])
                    for row in section["rows"]}
            self.assertEqual(refs["A1"][3], 1000000)
            self.assertEqual(refs["A1"][4], 110000)
            self.assertEqual(refs["C1"][3], 200000)
            self.assertEqual(refs["C1"][4], 22000)
            self.assertEqual(refs["E1"][4], result["totals_lbp"]["net"])
            self.assertEqual(refs["F2"][4], result["payable_lbp"])
            self.assertTrue(any("not certified Ministry of Finance form box numbers" in note for note in notices))
            self.assertTrue(any("obtain the current issued Q1-2" in note for note in notices))
            self.assertTrue(any("NOT a completed Q11-2 supplement" in note for note in notices))
            self.assertEqual(sections[2]["headers"][0], "Internal ref.")
            self.assertIn("Q1-2 specimen", sections[2]["heading"])
            self.assertIn("Q11-2 specimen", sections[4]["heading"])
            self.assertEqual(sections[4]["rows"][2], ["Deduction ratio applied", "100.00%"])

    def test_specimen_inspired_worksheet_keeps_every_internal_ref_once_and_no_ministry_boxes(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            result = build_vat_return(db, 2026, 1)
            notices, sections = filing_worksheet(result, {})
            from vat_return import LINES
            refs = [row[0] for section in (sections[2], sections[3], sections[5])
                    for row in section["rows"]]
            self.assertCountEqual(refs, [number for number, _, _ in LINES] + ["F1", "F2", "F3", "F4"])
            self.assertEqual(len(refs), len(set(refs)))
            self.assertTrue(all(section["headers"][0] == "Internal ref."
                                for section in (sections[2], sections[3], sections[5])))
            self.assertTrue(any("marked 2010" in note for note in notices))
            self.assertTrue(any("No current issued-form box mapping" in note for note in notices))
            self.assertTrue(any("must not be used for filing" in note for note in notices))

    def test_mixed_use_deduction_offsets_output_vat_before_payable(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            with db.connect() as connection:
                user_id = connection.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            db.import_invoice({"invoice_number": "SALE-TAX", "invoice_date": "15-03-2026",
                               "party_name": "Buyer", "kind": "sale", "currency": "LBP",
                               "subtotal": 1000000, "vat": 110000, "total": 1110000}, user_id)
            db.import_invoice({"invoice_number": "SALE-EXEMPT", "invoice_date": "16-03-2026",
                               "party_name": "Buyer 2", "kind": "sale", "currency": "LBP",
                               "subtotal": 100000, "vat": 0, "total": 100000,
                               "vat_treatment": "exempt"}, user_id)
            db.import_invoice({"invoice_number": "BUY-MIXED", "invoice_date": "18-03-2026",
                               "party_name": "Supplier", "kind": "purchase", "currency": "LBP",
                               "subtotal": 100000, "vat": 11000, "total": 111000,
                               "vat_use": "mixed"}, user_id)

            result = build_vat_return(db, 2026, 1, credit_brought_forward=20000)
            self.assertEqual(result["deduction_ratio"], Decimal("0.9091"))
            self.assertEqual(result["totals_lbp"]["sales"], Decimal("110000"))
            self.assertEqual(result["totals_lbp"]["prorata"], Decimal("-999.90"))
            self.assertEqual(result["totals_lbp"]["total_input"], Decimal("10000.10"))
            self.assertEqual(result["totals_lbp"]["net"], Decimal("99999.90"))
            self.assertEqual(result["net_after_credit_lbp"], Decimal("79999.90"))
            self.assertEqual(result["payable_lbp"], Decimal("80000"))
            self.assertEqual(result["credit_carried_forward_lbp"], Decimal("0"))
            self.assertEqual(result["due_date"], "2026-04-30")

    def test_excess_input_vat_and_brought_forward_credit_carry_to_next_period(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            with db.connect() as connection:
                user_id = connection.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            db.import_invoice({"invoice_number": "SALE-1", "invoice_date": "15-03-2026",
                               "party_name": "Buyer", "kind": "sale", "currency": "LBP",
                               "subtotal": 1000000, "vat": 110000, "total": 1110000}, user_id)
            db.import_invoice({"invoice_number": "BUY-1", "invoice_date": "18-03-2026",
                               "party_name": "Supplier", "kind": "purchase", "currency": "LBP",
                               "subtotal": 2000000, "vat": 220000, "total": 2220000,
                               "vat_use": "taxable"}, user_id)

            result = build_vat_return(db, 2026, 1, credit_brought_forward=20000)
            self.assertEqual(result["totals_lbp"]["net"], Decimal("-110000"))
            self.assertEqual(result["net_after_credit_lbp"], Decimal("-130000"))
            self.assertEqual(result["payable_lbp"], Decimal("0"))
            self.assertEqual(result["credit_carried_forward_lbp"], Decimal("130000"))

    def test_refund_request_reduces_credit_and_flags_manual_eligibility_check(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            with db.connect() as connection:
                user_id = connection.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            db.import_invoice({"invoice_number": "SALE-Q2", "invoice_date": "15-05-2026",
                               "party_name": "Buyer", "kind": "sale", "currency": "LBP",
                               "subtotal": 1000000, "vat": 110000, "total": 1110000}, user_id)
            db.import_invoice({"invoice_number": "BUY-Q2", "invoice_date": "18-05-2026",
                               "party_name": "Supplier", "kind": "purchase", "currency": "LBP",
                               "subtotal": 2000000, "vat": 220000, "total": 2220000,
                               "vat_use": "taxable"}, user_id)

            result = build_vat_return(db, 2026, 2, refund_requested=10000)
            self.assertEqual(result["credit_carried_forward_lbp"], Decimal("100000"))
            self.assertEqual(result["refund_requested_lbp"], Decimal("10000"))
            self.assertTrue(any("Refund eligibility is not validated" in warning
                                for warning in result["warnings"]))

    def test_exports_do_not_label_internal_references_as_ministry_boxes(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            result = build_vat_return(db, 2026, 1)
            _, meta, sections = export_sections(result)
            self.assertTrue(any("not certified Ministry of Finance form box numbers" in note for note in meta))
            schedule_sections = [section for section in sections if section["headers"] and
                                section["headers"][0].startswith("Internal ref.")]
            self.assertTrue(schedule_sections)
            self.assertTrue(all("Box" not in section["headers"][0] for section in schedule_sections))

    def test_filtered_or_draft_inclusive_is_not_a_filing_worksheet(self):
        data = {"currency_filter": "USD", "include_review": False}
        with self.assertRaisesRegex(ValueError, "All Currencies"):
            filing_worksheet(data, {})
        data["currency_filter"] = "All"
        data["include_review"] = True
        with self.assertRaisesRegex(ValueError, "Review"):
            filing_worksheet(data, {})

    def test_exempt_purchase_preserves_declared_vat_and_reclasses_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            with db.connect() as connection:
                user_id = connection.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            invoice_id = db.create_manual_invoice(
                {"invoice_date": "19-03-2026", "party_name": "Supplier", "kind": "purchases",
                 "currency": "LBP", "vat_use": "exempt"},
                [{"description": "Supplies", "quantity": 1, "unit_price": 100000, "vat_rate": 11}], user_id)
            row = next(item for item in db.list_invoices() if item["id"] == invoice_id)
            self.assertEqual((float(row["vat"]), float(row["total"]), row["vat_recoverable"]), (11000, 111000, 0))
            report = build_vat_return(db, 2026, 1)
            self.assertEqual(report["totals_lbp"]["non_deductible"], 11000)
            self.assertEqual(report["totals_lbp"]["total_input"], 0)
            with db.connect() as connection:
                entries = connection.execute(
                    "SELECT source_type FROM journal_entries WHERE source_id=? AND source_type IN ('invoice','vat_reclass')",
                    (invoice_id,)).fetchall()
                self.assertEqual({r["source_type"] for r in entries}, {"invoice", "vat_reclass"})
                for entry in connection.execute(
                    "SELECT id FROM journal_entries WHERE source_id=? AND source_type IN ('invoice','vat_reclass')",
                    (invoice_id,)):
                    balance = connection.execute(
                        "SELECT SUM(CAST(debit AS REAL)-CAST(credit AS REAL)) FROM journal_lines WHERE entry_id=?",
                        (entry["id"],)).fetchone()[0]
                    self.assertAlmostEqual(balance, 0, places=2)
            replacement = db.replace_manual_invoice(
                invoice_id,
                {"invoice_date": "19-03-2026", "party_name": "Supplier", "kind": "purchases",
                 "currency": "LBP", "vat_use": "taxable"},
                [{"description": "Supplies", "quantity": 1, "unit_price": 100000, "vat_rate": 11}], user_id)
            updated = next(item for item in db.list_invoices() if item["id"] == replacement)
            self.assertEqual(updated["vat_recoverable"], 1)
            self.assertEqual(build_vat_return(db, 2026, 1)["totals_lbp"]["total_input"], 11000)

    def test_pdf_item_rows_are_suggestions_not_invented_totals(self):
        data = _parse_invoice_text("purchase.pdf", "ALPHA TRADING\nInvoice No: 45\n"
                                   "Date: 15/03/2026\nPanel A 2 50.00 100.00\n"
                                   "Bad row 4 50.00 100.00\nSubtotal: 100.00\nVAT: 11.00\nGrand Total: 111.00")
        self.assertEqual([(r["description"], r["quantity"], r["total"]) for r in data["items"]],
                         [("Panel A", 2.0, 100.0)])