"""Tests for version 1.12: payroll official reports, quarterly VAT, user expiry/permissions,
legal-document alerts, and a full standalone run including backup and restore."""
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from client import ApiClient
from database import Database
from payroll_reports import build_payroll_report, period_range
from report_export import export_sections_excel, export_sections_pdf
from server import run_server
import vat_return
import ledger_reports
import year_end
import inventory
from company_manager import CompanyManager
from database import utcnow


def new_db(folder, name="test.db"):
    db = Database(Path(folder) / name); db.initialize("secret")
    user = db.user_for_token(db.login("admin", "secret")["token"])
    return db, user["id"]


def cell(section, row, header):
    return section["rows"][row][section["headers"].index(header)]


class PayrollOfficialReportsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name)
        db, user = self.db, self.user
        self.employee = db.save_employee({"employee_number": "1000", "full_name": "Rami Employee", "currency": "LBP", "base_salary": "60000000",
            "marital_status": "married", "children": 2, "mof_number": "MOF-1", "nssf_number": "NSSF-1"}, user)
        self.manager = db.save_employee({"employee_number": "2000", "full_name": "Maya Manager", "currency": "USD", "base_salary": "3000",
            "employee_group": "manager"}, user)
        with db.connect() as connection:  # this test builds its own periods: keep one open period from the automatic Lebanese rules
            connection.execute("DELETE FROM payroll_settings WHERE date_from<>'2024-01-01'"); connection.execute("UPDATE payroll_settings SET date_to=NULL")
        first = db.payroll_settings_for("2025-01-01")
        first.update({"date_from": "01-01-2025", "employee_ceiling": "50000000", "medical_ceiling": "50000000", "family_ceiling": "20000000"})
        db.save_payroll_settings(first, user)
        second = dict(first); second.update({"date_from": "01-05-2025", "employee_ceiling": "140000000", "medical_ceiling": "140000000", "family_ceiling": "28000000"})
        db.save_payroll_settings(second, user)
        for month in range(1, 7):
            for employee in (self.employee, self.manager):
                extra = {}
                if month == 4 and employee is self.employee: extra = {"retro_salary": "60000000", "retro_from": "01-01-2025", "retro_to": "31-03-2025"}
                if month == 6: extra["thirteenth_month"] = "60000000" if employee is self.employee else "3000"
                if month == 3: extra.update({"transport": "2000000" if employee is self.employee else "50", "schooling": "1000000" if employee is self.employee else "0", "bonus": "0"})
                record = db.save_payroll({"employee_id": employee["id"], "period_date": f"28-{month:02d}-2025", **extra}, user)
                if month != 6 or employee is self.employee: db.post_payroll(record["id"], user)

    def tearDown(self): self.folder.cleanup()

    def test_effective_periods_chain_and_reject_overlap(self):
        periods = self.db.list_payroll_settings()
        self.assertEqual([(p["date_from"], p["date_to"]) for p in periods], [("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-04-30"), ("2025-05-01", None)])
        periods = periods[1:]
        middle = dict(periods[0]); middle.update({"date_from": "01-03-2025", "date_to": "31-05-2025"})
        with self.assertRaisesRegex(ValueError, "overlaps"): self.db.save_payroll_settings(middle, self.user)
        with self.assertRaisesRegex(ValueError, "decimal rate"): self.db.save_payroll_settings({**periods[1], "employee_nssf_rate": "3"}, self.user)

    def test_ceilings_follow_the_period_of_each_month(self):
        rows = {r["period_date"]: r for r in self.db.list_payroll() if r["employee_id"] == self.employee["id"]}
        self.assertEqual(float(rows["2025-04-28"]["employee_nssf"]), 1500000)  # 60M capped at the 50M ceiling; the retro months were already above it
        self.assertEqual(float(rows["2025-05-28"]["employee_nssf"]), 1800000)  # 60M under the new 140M ceiling
        self.assertGreater(float(rows["2025-04-28"]["retro_tax"]), 0)

    def test_r10_quarterly_separate_groups_nssf_and_rates(self):
        report = build_payroll_report(self.db, "R10", "quarterly", 2025, 2, "both")
        headings = [s["heading"] for s in report["sections"]]
        self.assertIn("Salary tax withheld - Employees", headings); self.assertIn("Salary tax withheld - Managers", headings)
        tax = report["sections"][headings.index("Salary tax withheld - Employees")]
        self.assertEqual(cell(tax, 0, "Months"), 3); self.assertEqual(cell(tax, 0, "Retro Salary"), 60000000)
        self.assertEqual(cell(tax, 0, "13th Salary"), 60000000); self.assertGreater(cell(tax, 0, "of which Retro Tax"), 0)
        nssf = report["sections"][headings.index("NSSF contributions - Employees")]
        self.assertEqual(cell(nssf, 0, "Employee NSSF (3%)"), 1500000 + 1800000 + 3600000)
        self.assertGreater(cell(nssf, 0, "Employer Medical"), 0); self.assertGreater(cell(nssf, 0, "Employer End-of-Service"), 0)
        managers = report["sections"][headings.index("Salary tax withheld - Managers")]
        self.assertEqual(cell(managers, 0, "Months"), 2)  # June manager payroll is still a draft
        with_drafts = build_payroll_report(self.db, "R10", "quarterly", 2025, 2, "manager", include_drafts=True)
        self.assertEqual(cell(with_drafts["sections"][0], 0, "Months"), 3)
        rates = report["sections"][-1]["rows"]
        self.assertEqual(rates[0][:2], ["01-01-2025", "30-04-2025"]); self.assertEqual(rates[1][:2], ["01-05-2025", "Open"])
        managers_usd = cell(managers, 0, "Gross")
        self.assertEqual(managers_usd, 2 * 3000 * 89500)  # converted to LBP

    def test_monthly_yearly_r5_r6_and_transport_schooling(self):
        march = build_payroll_report(self.db, "R10", "monthly", 2025, 3, "employee")
        self.assertEqual(cell(march["sections"][0], 0, "Transport"), 2000000); self.assertEqual(cell(march["sections"][0], 0, "Schooling"), 1000000)
        r5 = build_payroll_report(self.db, "R5", "yearly", 2025, 1, "employee")
        summary = r5["sections"][0]; items = {row[0]: row[1] for row in summary["rows"]}
        self.assertEqual(items["Number of employees"], 1); self.assertEqual(items["Retro Salary"], 60000000)
        r6 = build_payroll_report(self.db, "R6", "yearly", 2025, 1, "both")
        employee_sheet = next(s for s in r6["sections"] if "Rami Employee" in s["heading"])
        self.assertEqual(len(employee_sheet["rows"]), 7)  # six months + total
        self.assertIn("NSSF Family Allowance", employee_sheet["headers"])  # NSSF family allowance shown on the individual statement
        self.assertEqual(employee_sheet["rows"][3][employee_sheet["headers"].index("Retro Period")], "01-01-2025 to 31-03-2025")
        with self.assertRaisesRegex(ValueError, "Quarter"): period_range("quarterly", 2025, 5)

    def test_exports_to_excel_and_pdf(self):
        report = build_payroll_report(self.db, "R6", "yearly", 2025, 1, "both")
        xlsx = Path(self.folder.name) / "r6.xlsx"; pdf = Path(self.folder.name) / "r6.pdf"
        export_sections_excel(xlsx, report["title"], report["meta"], report["sections"]); export_sections_pdf(pdf, report["title"], report["meta"], report["sections"])
        sheet = load_workbook(xlsx).active
        self.assertEqual(sheet["A1"].value, report["title"])
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF")); self.assertGreater(pdf.stat().st_size, 3000)


class QuarterlyVatTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name)
        db, user = self.db, self.user
        db.save_exchange_rate({"date_from": "01-01-2025", "date_to": "31-12-2025", "from_currency": "USD", "to_currency": "LBP", "rate": "89500"}, user)
        def invoice(date, party, kind, currency, amount, status="posted"):
            return db.create_manual_invoice({"invoice_date": date, "party_name": party, "kind": kind, "currency": currency, "status": status},
                                            [{"description": "Line", "quantity": 1, "unit_price": amount, "vat_rate": 11}], user)
        self.sale = invoice("15-02-2025", "Client", "sales", "USD", 1000)
        self.purchase = invoice("20-02-2025", "Supplier", "purchases", "USD", 300)
        self.car = invoice("21-02-2025", "Car Dealer", "purchases", "USD", 200)
        self.lbp_sale = invoice("01-03-2025", "Local Client", "sales", "LBP", 8950000)
        self.review = invoice("10-03-2025", "Draft Client", "sales", "USD", 500, "review")
        db.add_expense({"expense_date": "05-03-2025", "description": "Supplies", "currency": "USD", "with_vat_subtotal": "100", "vat": "11"}, user)
        db.add_expense({"expense_date": "06-03-2025", "description": "Entertainment", "currency": "USD", "with_vat_subtotal": "100", "vat": "11", "vat_recoverable": False}, user)
        party = db.save_party({"kind": "supplier", "name": "Overseas Supplier"}, user)
        case = db.save_document_case({"case_type": "customs", "document_date": "12-03-2025", "party_id": party["id"], "currency": "USD", "supplier_invoice_amount": "1000", "import_vat": "121"}, user)
        for role in ("supplier_invoice", "customs_declaration", "broker_invoice"): db.add_case_attachment(case["id"], role, f"{role}.pdf", "application/pdf", b"%PDF", user)
        db.post_document_case(case["id"], user)
        db.set_vat_recoverable("invoice", self.car, False, user)

    def tearDown(self): self.folder.cleanup()

    def test_q1_lines_categories_non_deductible_and_lbp(self):
        result = vat_return.build_vat_return(self.db, 2025, 1)
        usd = result["per_currency"]["USD"]
        self.assertEqual(float(usd["sales"]["vat"]), 110); self.assertEqual(float(usd["purchases"]["vat"]), 33)
        self.assertEqual(float(usd["expenses"]["vat"]), 11); self.assertEqual(float(usd["customs"]["vat"]), 121)
        self.assertEqual(float(usd["non_deductible"]["vat"]), 22 + 11); self.assertEqual(float(usd["net"]["vat"]), 110 - 165)
        self.assertEqual(float(result["per_currency"]["LBP"]["sales"]["vat"]), 984500)
        self.assertEqual(result["totals_lbp"]["net"], (110 - 165) * 89500 + 984500)
        self.assertEqual(result["review_excluded"], 1)
        self.assertEqual(vat_return.build_vat_return(self.db, 2025, 1, include_review=True)["per_currency"]["USD"]["sales"]["vat"], 165)
        self.assertEqual(vat_return.build_vat_return(self.db, 2025, 1, currency="LBP")["currency_filter"], "LBP")

    def test_non_deductible_reclass_keeps_ledger_equal_to_return(self):
        balance = {row["code"]: row["closing_balance"] for row in self.db.trial_balance()}
        result = vat_return.build_vat_return(self.db, 2025, 1)
        self.assertAlmostEqual(balance["44210"] + balance["44216"], float(result["per_currency"]["USD"]["total_input"]["vat"]), places=2)
        self.assertAlmostEqual(sum(r["debit"] - r["credit"] for r in self.db.journal()), 0, places=2)
        self.db.set_vat_recoverable("invoice", self.car, True, self.user)
        self.assertEqual(float(vat_return.build_vat_return(self.db, 2025, 1)["per_currency"]["USD"]["purchases"]["vat"]), 55)
        with self.assertRaisesRegex(ValueError, "purchase and expense"): self.db.set_vat_recoverable("invoice", self.sale, False, self.user)

    def test_adjustments_lock_and_credit_carry_forward(self):
        vat_return.add_adjustment(self.db, {"year": 2025, "quarter": 1, "adjustment_type": "output", "currency": "USD", "amount": "10", "reason": "Late credit note"}, self.user, "admin")
        with self.assertRaisesRegex(ValueError, "reason"): vat_return.add_adjustment(self.db, {"year": 2025, "quarter": 1, "adjustment_type": "input", "currency": "USD", "amount": "5", "reason": ""}, self.user)
        saved = vat_return.save_return(self.db, 2025, 1, self.user, user_name="admin")
        self.assertEqual(saved["status"], "saved")
        self.assertEqual(saved["credit_carried_forward_lbp"], 45 * 89500 - 984500)
        with self.assertRaisesRegex(ValueError, "saved"): vat_return.add_adjustment(self.db, {"year": 2025, "quarter": 1, "adjustment_type": "output", "currency": "USD", "amount": "1", "reason": "Too late"}, self.user)
        self.db.create_manual_invoice({"invoice_date": "10-04-2025", "party_name": "Client", "kind": "sales", "currency": "USD", "status": "posted"},
                                      [{"description": "Q2", "quantity": 1, "unit_price": 1000, "vat_rate": 11}], self.user)
        q2 = vat_return.build_vat_return(self.db, 2025, 2)
        self.assertEqual(q2["credit_brought_forward_lbp"], saved["credit_carried_forward_lbp"])
        # MoF decision 1195: VAT due is rounded up to the nearest LBP 10,000 (from 25-11-2024)
        self.assertEqual(q2["payable_lbp"], 6810000); self.assertEqual(q2["net_after_credit_lbp"], 110 * 89500 - saved["credit_carried_forward_lbp"])
        self.db.create_manual_invoice({"invoice_date": "28-03-2025", "party_name": "Client", "kind": "sales", "currency": "USD", "status": "posted"},
                                      [{"description": "After filing", "quantity": 1, "unit_price": 10, "vat_rate": 11}], self.user)
        self.assertTrue(vat_return.build_vat_return(self.db, 2025, 1)["changed_since_saved"])
        vat_return.reopen_return(self.db, 2025, 1, self.user)
        self.assertEqual(vat_return.build_vat_return(self.db, 2025, 1)["status"], "not saved")

    def test_previous_fiscal_year_file_provides_q1_credit(self):
        other = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); previous, user = new_db(other.name, "2024.db")
        previous.create_manual_invoice({"invoice_date": "10-11-2024", "party_name": "Supplier", "kind": "purchases", "currency": "LBP", "status": "posted"},
                                       [{"description": "Stock", "quantity": 1, "unit_price": 100000000, "vat_rate": 11}], user)
        vat_return.save_return(previous, 2024, 4, user)
        result = vat_return.build_vat_return(self.db, 2025, 1, previous_year_db=previous)
        self.assertEqual(result["credit_brought_forward_lbp"], 11000000); self.assertIn("Q4 2024", result["credit_source"])
        manual = vat_return.build_vat_return(self.db, 2025, 1, credit_brought_forward="5000000")
        self.assertEqual(manual["credit_brought_forward_lbp"], 5000000); other.cleanup()

    def test_vat_exports(self):
        title, meta, sections = vat_return.export_sections(vat_return.build_vat_return(self.db, 2025, 1))
        xlsx = Path(self.folder.name) / "vat.xlsx"; pdf = Path(self.folder.name) / "vat.pdf"
        export_sections_excel(xlsx, title, meta, sections); export_sections_pdf(pdf, title, meta, sections)
        values = [c.value for row in load_workbook(xlsx).active.iter_rows() for c in row if c.value]
        self.assertIn("Credit carried forward to the next period", values); self.assertIn("Partial deduction right (Art. 31)", values)
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))


class UsersAlertsAndRatesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name)

    def tearDown(self): self.folder.cleanup()

    def test_new_users_expire_after_one_year_and_can_be_renewed(self):
        user = self.db.save_user({"username": "clerk", "password": "clerk123", "role": "accountant"}, self.user)
        self.assertEqual(user["expires_at"], (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"))
        self.assertIsNone(next(u for u in self.db.list_users() if u["username"] == "admin")["expires_at"])
        token = self.db.login("clerk", "clerk123")["token"]
        self.db.save_user({"id": user["id"], "username": "clerk", "role": "accountant", "expires_at": "01-01-2020"}, self.user)
        self.assertIsNone(self.db.user_for_token(token))
        with self.assertRaisesRegex(PermissionError, "expired on 01-01-2020"): self.db.login("clerk", "clerk123")
        renewed = self.db.save_user({"id": user["id"], "username": "clerk", "role": "accountant", "renew": True}, self.user)
        self.assertEqual(renewed["days_remaining"], 365); self.assertTrue(self.db.login("clerk", "clerk123"))

    def test_permissions_last_admin_and_validation(self):
        clerk = self.db.save_user({"username": "clerk", "password": "clerk123", "role": "accountant", "permissions": {"payroll": False, "vat": True}}, self.user)
        row = self.db.user_for_token(self.db.login("clerk", "clerk123")["token"])
        self.assertFalse(self.db.user_can(row, "payroll")); self.assertTrue(self.db.user_can(row, "vat"))
        with self.assertRaisesRegex(ValueError, "administrator must remain"):
            self.db.save_user({"id": 1, "username": "admin", "role": "viewer"}, self.user)
        with self.assertRaisesRegex(ValueError, "already used"): self.db.save_user({"username": "CLERK", "password": "another1", "role": "viewer"}, self.user)
        with self.assertRaisesRegex(ValueError, "6 characters"): self.db.save_user({"id": clerk["id"], "username": "clerk", "role": "viewer", "password": "123"}, self.user)

    def test_sessions_expire(self):
        token = self.db.login("admin", "secret")["token"]
        with self.db.connect() as db: db.execute("UPDATE sessions SET created_at=? WHERE token=?", ((datetime.now() - timedelta(hours=30)).astimezone().isoformat(), token))
        self.assertIsNone(self.db.user_for_token(token))

    def test_legal_document_alerts(self):
        party = self.db.save_party({"kind": "supplier", "name": "Supplier"}, self.user)
        today = datetime(2026, 9, 24)
        for kind, expiry in (("Contract", "01-09-2026"), ("MOF / VAT Certificate", "10-10-2026"), ("ID / Passport", "31-12-2027"), ("Other", "")):
            self.db.add_party_document(party["id"], {"document_type": kind, "expiry_date": expiry, "file_name": "f.pdf", "mime_type": "application/pdf"}, b"%PDF", self.user)
        alerts = self.db.legal_document_alerts(30, today.strftime("%d-%m-%Y"))
        self.assertEqual((alerts["expired"], alerts["expiring"]), (1, 1))
        self.assertEqual(alerts["items"][0]["document_type"], "Contract"); self.assertEqual(alerts["items"][0]["status"], "expired")

    def test_old_payroll_date_formats_are_migrated_and_displayed(self):
        employee = self.db.save_employee({"employee_number": "1000", "full_name": "Legacy", "currency": "LBP", "base_salary": "1000"}, self.user)
        with self.db.connect() as db:
            db.execute("DELETE FROM payroll_settings WHERE date_from<>'2024-01-01'"); db.execute("UPDATE payroll_settings SET date_from='01012025'")
            db.execute("""INSERT INTO payroll_records(payroll_number,employee_id,period_date,currency,retro_from,created_at)
                VALUES('PAY-OLD-1',?,'30062025','LBP','01-01-2025','x'),('PAY-OLD-2',?,'June 2025','LBP',NULL,'x')""", (employee["id"], employee["id"]))
        self.db.initialize("secret")
        periods = {r["payroll_number"]: r for r in self.db.list_payroll()}
        self.assertEqual(periods["PAY-OLD-1"]["period_date"], "2025-06-30"); self.assertEqual(periods["PAY-OLD-1"]["retro_from"], "2025-01-01")
        self.assertEqual(periods["PAY-OLD-2"]["period_date"], "June 2025")  # unreadable text is kept, not lost
        self.assertEqual(self.db.list_payroll_settings()[0]["date_from"], "2025-01-01")
        from desktop import safe_display_date
        self.assertEqual(safe_display_date("2025-06-30"), "30-06-2025"); self.assertEqual(safe_display_date("June 2025"), "June 2025")

    def test_stage1_party_numbers_invoice_numbers_search_and_dates(self):
        self.assertEqual(self.db.next_party_account_number("4111"), "411100001")
        self.db.save_party({"kind": "customer", "name": "A", "account_category": "client", "account_number": "4111"}, self.user)
        self.assertEqual(self.db.next_party_account_number("4111"), "411100002")
        with self.assertRaisesRegex(ValueError, "4 account digits"): self.db.next_party_account_number("41")
        self.assertEqual(self.db.next_invoice_number("sale", "15-03-2024"), "SAL-2024-000001")
        from desktop import auto_dash_date, row_matches_search
        self.assertEqual([auto_dash_date(v) for v in ("3", "311", "31122", "31122024", "31-12-2024")], ["3", "31-1", "31-12-2", "31-12-2024", "31-12-2024"])
        self.assertTrue(row_matches_search(("SAL-1", "31-12-2024", "1,250.00"), "1250 31122024"))
        self.assertFalse(row_matches_search(("SAL-1", "31-12-2024", "1,250.00"), "999"))

    def test_exchange_rate_lookup_is_chronological(self):
        self.db.save_exchange_rate({"date_from": "01-06-2025", "date_to": "01-06-2025", "from_currency": "AED", "to_currency": "LBP", "rate": "24000"}, self.user)
        self.db.save_exchange_rate({"date_from": "01-07-2025", "date_to": "01-07-2025", "from_currency": "AED", "to_currency": "LBP", "rate": "25000"}, self.user)
        self.assertEqual(self.db._converted_amount(1, "AED", "LBP", "30-06-2025"), 24000)
        self.assertEqual(self.db._converted_amount(1, "AED", "LBP", "2025-07-15"), 25000)


class BrainsStyleVoucherAndReportsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name)
        self.party = self.db.save_party({"kind": "customer", "name": "Client A", "account_category": "client", "account_number": "4111"}, self.user)
        self.voucher = self.db.save_journal_voucher({"entry_date": "20-02-2025", "description": "Receipt", "currency": "USD", "voucher_type": "02"}, [
            {"account_code": "531", "line_currency": "USD", "side": "D", "amount": "100"},
            {"account_code": "531", "line_currency": "LBP", "side": "D", "amount": "8950000"},
            {"account_code": self.party["account_number"], "line_currency": "USD", "side": "C", "amount": "200", "reference": "RC-1", "due_date": "28022025"}], self.user)

    def tearDown(self): self.folder.cleanup()

    def test_multi_currency_voucher_lines(self):
        lines = self.voucher["lines"]
        self.assertEqual(self.voucher["voucher"]["voucher_type"], "02")
        self.assertEqual([(l["line_currency"], l["debit"], l["credit"]) for l in lines], [("USD", 100, 0), ("LBP", 100, 0), ("USD", 0, 200)])
        self.assertEqual(lines[1]["amount_usd"], 100); self.assertEqual(lines[2]["amount_lbp"], 17900000); self.assertEqual(lines[2]["due_date"], "28-02-2025")
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            self.db.save_journal_voucher({"entry_date": "20-02-2025", "description": "Bad", "currency": "USD"}, [
                {"account_code": "531", "side": "D", "amount": "10"}, {"account_code": "531", "side": "C", "amount": "9"}], self.user)
        with self.assertRaisesRegex(ValueError, "EUR voucher can only"):
            self.db.save_journal_voucher({"entry_date": "20-02-2025", "description": "Bad", "currency": "EUR"}, [
                {"account_code": "531", "line_currency": "USD", "side": "D", "amount": "10"}, {"account_code": "531", "line_currency": "EUR", "side": "C", "amount": "10"}], self.user)

    def test_trial_balance_options(self):
        report = ledger_reports.build_account_report(self.db, {"date_from": "01-01-2025", "date_to": "31-12-2025", "first_column": "USD", "second_column": "LBP", "chapters": True})
        rows = report["sections"][0]["rows"]; grand = rows[-1]
        self.assertEqual(grand[0], "GRAND TOTAL"); self.assertEqual(grand[-3], grand[-2])  # LBP debit == credit
        self.assertIn("Total 5", [r[0] for r in rows])
        split = ledger_reports.build_account_report(self.db, {"first_column": "account", "second_column": "none", "balance_format": True})
        self.assertEqual({s["heading"] for s in split["sections"]}, {"Trial balance - LBP", "Trial balance - USD"})
        pnl = ledger_reports.build_account_report(self.db, {"profit_loss_only": True})
        self.assertEqual(pnl["sections"][0]["heading"], "No movements")

    def test_statement_with_opening_and_reference(self):
        self.db.save_journal_voucher({"entry_date": "05-03-2025", "description": "Invoice", "currency": "USD"}, [
            {"account_code": self.party["account_number"], "side": "D", "amount": "50"}, {"account_code": "713", "side": "C", "amount": "50"}], self.user)
        account = self.party["account_number"]
        statement = ledger_reports.build_account_report(self.db, {"detailed": True, "statement": True, "account_from": account, "account_to": account,
            "date_from": "01-03-2025", "date_to": "31-12-2025", "first_column": "USD", "second_column": "none", "reference": True})
        rows = statement["sections"][0]["rows"]
        self.assertEqual(rows[0][2], "Opening balance (carried forward)"); self.assertEqual(float(rows[0][-2]), 200)  # credit opening
        self.assertEqual(float(rows[-1][-1]), -150); self.assertEqual(statement["title"], "Statement of Account")

class DepartmentsProjectsBudgetTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name)
        db, user = self.db, self.user
        self.d1 = db.save_department({"name": "Sales"}, user); self.d2 = db.save_department({"name": "Site Works"}, user)
        db.save_party({"kind": "customer", "name": "Tower Client", "account_category": "client"}, user)
        self.project = db.save_project({"name": "Tower Fit-out", "party_name": "Tower Client", "start_date": "01012025"}, user)
        db.add_expense({"expense_date": "10-02-2025", "description": "Paint", "currency": "USD", "with_vat_subtotal": "300", "vat": "0", "department": "D02", "project": self.project["code"]}, user)
        db.add_expense({"expense_date": "12-02-2025", "description": "Paper", "currency": "USD", "with_vat_subtotal": "50", "vat": "0", "department": "D01"}, user)
        db.create_manual_invoice({"invoice_date": "20-02-2025", "party_name": "Tower Client", "kind": "sales", "currency": "USD", "status": "posted",
                                  "department": "D02", "project": self.project["code"], "expense_account": "713100000"}, [{"description": "Works", "quantity": 1, "unit_price": 1000}], user)
        db.save_journal_voucher({"entry_date": "25-02-2025", "description": "Site cost", "currency": "USD"}, [
            {"account_code": "601100000", "side": "D", "amount": "40", "department": "D02", "project": self.project["code"]}, {"account_code": "531", "side": "C", "amount": "40"}], user)

    def tearDown(self): self.folder.cleanup()

    def test_codes_validation_and_voucher_dimensions(self):
        self.assertEqual((self.d1["code"], self.d2["code"], self.project["code"]), ("D01", "D02", "P2025-001"))
        self.assertEqual(self.project["party_name"], "Tower Client")
        with self.assertRaisesRegex(ValueError, "already used"): self.db.save_department({"code": "D01", "name": "Other"}, self.user)
        with self.assertRaisesRegex(ValueError, "not found"):
            self.db.save_journal_voucher({"entry_date": "25-02-2025", "description": "x", "currency": "USD"}, [
                {"account_code": "531", "side": "D", "amount": "1", "department": "ZZ"}, {"account_code": "531", "side": "C", "amount": "1"}], self.user)
        voucher = [v for v in self.db.journal() if v["source_type"] == "journal_voucher"][0]
        lines = self.db.journal_voucher_detail(voucher["entry_id"])["lines"]
        self.assertEqual((lines[0]["department"], lines[0]["project"], lines[1]["department"]), ("D02", "P2025-001", None))

    def test_filters_and_split_by_department_or_project(self):
        project_only = ledger_reports.build_account_report(self.db, {"project_id": self.project["id"], "profit_loss_only": True, "first_column": "USD", "second_column": "none"})
        rows = {r[0]: r for r in project_only["sections"][0]["rows"]}
        self.assertEqual(float(rows["601100000"][-1]), 340); self.assertEqual(float(rows["713100000"][-1]), -1000)
        split = ledger_reports.build_account_report(self.db, {"split_by_department": True, "profit_loss_only": True, "first_column": "USD", "second_column": "none"})
        self.assertEqual(len(split["sections"]), 2); self.assertIn("D01 Sales", split["sections"][0]["heading"])
        detail = ledger_reports.build_account_report(self.db, {"detailed": True, "with_department": True, "account_from": "601100000", "account_to": "601100000", "first_column": "USD", "second_column": "none"})
        self.assertIn("Department", detail["sections"][0]["headers"])

    def test_budget_monthly_annual_parent_and_dimension_budgets(self):
        self.db.save_budget({"year": 2025, "currency": "USD", "lines": [{"account_code": "601100000", "annual": "2400"}, {"account_code": "713", "months": [0, 1200] + [0] * 10}]}, self.user)
        self.db.save_budget({"year": 2025, "currency": "USD", "project": self.project["code"], "lines": [{"account_code": "601100000", "annual": "1200"}]}, self.user)
        self.assertEqual(self.db.list_budgets(2025)[1]["months"][1], 1200)
        report = ledger_reports.build_account_report(self.db, {"date_from": "01-02-2025", "date_to": "28-02-2025", "budget": True, "carry_forward": False,
                                                               "profit_loss_only": True, "first_column": "USD", "second_column": "none"})
        rows = {r[0]: r for r in report["sections"][0]["rows"]}
        self.assertEqual([float(x) for x in rows["601100000"][-4:-1]], [200, 390, 190])
        self.assertEqual([float(x) for x in rows["713"][-4:-1]], [1200, 1000, -200]); self.assertEqual(rows["713"][-1], "83.3%")
        project = ledger_reports.build_account_report(self.db, {"date_from": "01-01-2025", "date_to": "31-12-2025", "budget": True, "carry_forward": False, "profit_loss_only": True,
                                                                "project_id": self.project["id"], "first_column": "USD", "second_column": "none"})
        rows = {r[0]: r for r in project["sections"][0]["rows"]}
        self.assertEqual([float(x) for x in rows["601100000"][-4:-1]], [1200, 340, -860])
        with self.assertRaisesRegex(ValueError, "Date From and Date To"): ledger_reports.build_account_report(self.db, {"budget": True})
        with self.assertRaisesRegex(ValueError, "negative"): self.db.save_budget({"year": 2025, "currency": "USD", "lines": [{"account_code": "531", "annual": "-5"}]}, self.user)

class Stage3PaymentsPurchasesExpensesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name)
        self.client_party = self.db.save_party({"kind": "customer", "name": "Client One", "account_category": "client"}, self.user)
        self.supplier = self.db.save_party({"kind": "supplier", "name": "Alpha Trading", "account_category": "supplier"}, self.user)

    def tearDown(self): self.folder.cleanup()

    def test_receipts_and_payments_numbering_edit_delete(self):
        receipt = self.db.add_payment({"kind": "customer_receipt", "party_id": self.client_party["id"], "payment_date": "10-03-2025", "currency": "USD", "amount": "100"}, self.user)
        payment = self.db.add_payment({"kind": "supplier_payment", "party_id": self.supplier["id"], "payment_date": "11-03-2025", "currency": "USD", "amount": "40", "payment_method": "Cheque"}, self.user)
        rows = {r["id"]: r for r in self.db.list_payments()}
        self.assertEqual((rows[receipt]["payment_number"], rows[payment]["payment_number"]), ("RV-2025-000001", "PV-2025-000001"))
        self.assertEqual(rows[receipt]["party_account"], self.client_party["account_number"])  # the customer's own account
        self.assertEqual(self.db.next_document_number("customer_receipt", "01-04-2025"), "RV-2025-000002")
        new_id = self.db.update_payment(receipt, {"party_id": self.client_party["id"], "payment_date": "10-03-2025", "currency": "USD", "amount": "150"}, self.user)
        edited = next(r for r in self.db.list_payments() if r["id"] == new_id)
        self.assertEqual((edited["payment_number"], edited["amount"]), ("RV-2025-000001", 150))
        self.assertEqual(len([e for e in self.db.journal() if e["entry_number"] == "RV-2025-000001"]), 2)
        self.db.delete_payment(payment, self.user)
        self.assertFalse([e for e in self.db.journal() if e["entry_number"] == "PV-2025-000001"])

    def test_expense_edit_delete_keeps_attachments(self):
        expense = self.db.add_expense({"expense_date": "05-03-2025", "description": "Rent", "currency": "USD", "with_vat_subtotal": "500", "vat": "55"}, self.user)
        self.db.add_expense_attachment(expense, "rent.pdf", "application/pdf", b"%PDF-1", self.user)
        new_id = self.db.update_expense(expense, {"expense_date": "05-03-2025", "description": "Rent March", "currency": "USD", "with_vat_subtotal": "600", "vat": "66"}, self.user)
        row = next(r for r in self.db.list_expenses() if r["id"] == new_id)
        self.assertEqual((row["expense_number"], row["total"], row["attachment_count"]), ("EXP-2025-000001", 666, 1))
        self.db.delete_expense(new_id, self.user)
        self.assertEqual(self.db.list_expenses(), []); self.assertAlmostEqual(sum(r["debit"] - r["credit"] for r in self.db.journal()), 0, places=2)

    def test_purchase_edit_keeps_pdf_and_landed_cost_reaches_vat(self):
        purchase = self.db.create_manual_invoice({"invoice_date": "15-03-2025", "party_name": "Alpha Trading", "kind": "purchases", "currency": "USD", "status": "posted", "invoice_number": "INV-457"},
                                                 [{"description": "Goods", "quantity": 1, "unit_price": 1000, "vat_rate": 11}], self.user)
        self.db.add_attachment(purchase, "inv.pdf", "application/pdf", b"%PDF-1", self.user)
        landed = self.db.add_landed_cost(purchase, {"freight": "120", "customs_duties": "200", "import_vat": "42.35", "customs_declaration_no": "D-778"}, self.user)
        new_id = self.db.replace_manual_invoice(purchase, {"invoice_date": "15-03-2025", "party_name": "Alpha Trading", "kind": "purchases", "currency": "USD", "status": "posted"},
                                                [{"description": "Goods", "quantity": 1, "unit_price": 1200, "vat_rate": 11}], self.user)
        rows = {r["id"]: r for r in self.db.list_invoices()}
        self.assertEqual((rows[new_id]["invoice_number"], rows[new_id]["attachment_count"], float(rows[new_id]["total"])), ("INV-457", 1, 1332))
        self.assertNotIn(purchase, rows)
        self.assertEqual([c["id"] for c in self.db.landed_costs(new_id)], [landed])
        result = vat_return.build_vat_return(self.db, 2025, 1)
        self.assertEqual(float(result["per_currency"]["USD"]["customs"]["vat"]), 42.35); self.assertEqual(float(result["per_currency"]["USD"]["purchases"]["vat"]), 132)
        with self.assertRaisesRegex(ValueError, "at least one"): self.db.add_landed_cost(new_id, {}, self.user)

    def test_failed_invoice_replacement_preserves_original(self):
        invoice = self.db.create_manual_invoice(
            {"invoice_date": "15-03-2025", "party_name": "Alpha Trading", "kind": "sales",
             "currency": "USD", "status": "posted", "invoice_number": "SAL-ORIGINAL"},
            [{"description": "Service", "quantity": 1, "unit_price": 100, "vat_rate": 11}], self.user)
        before = self.db.invoice_detail(invoice)
        with self.assertRaises(ValueError):
            self.db.replace_manual_invoice(invoice,
                {"invoice_date": "15-03-2025", "party_name": "Alpha Trading", "kind": "sales",
                 "currency": "USD", "status": "posted"},
                [{"description": "Service", "quantity": -1, "unit_price": 200, "vat_rate": 11}], self.user)
        after = self.db.invoice_detail(invoice)
        self.assertEqual(after["invoice"]["total"], before["invoice"]["total"])
        self.assertEqual(len(self.db.list_invoices()), 1)

    def test_pdf_and_excel_readers(self):
        from reportlab.pdfgen import canvas
        from openpyxl import Workbook
        from pdf_import import read_invoice_pdf
        from importer import read_expenses, read_customs_costs
        pdf = Path(self.folder.name) / "invoice.pdf"; c = canvas.Canvas(str(pdf)); y = 800
        for line in ["ALPHA TRADING SARL", "Invoice No: INV-2024-0457", "Date: 15/03/2024", "Subtotal: 1,000.00 USD", "VAT 11%: 110.00", "Grand Total: 1,110.00 USD"]:
            c.drawString(60, y, line); y -= 20
        c.save()
        data = read_invoice_pdf(pdf)
        self.assertEqual((data["invoice_number"], data["invoice_date"], data["currency"], data["subtotal"], data["vat"], data["total"]), ("INV-2024-0457", "15-03-2024", "USD", 1000, 110, 1110))
        self.assertEqual(data["party_name"], "ALPHA TRADING SARL")
        blank = Path(self.folder.name) / "scan.pdf"; c = canvas.Canvas(str(blank)); c.rect(10, 10, 100, 100); c.save()
        self.assertIn("scanned", read_invoice_pdf(blank)["notes"])
        wb = Workbook(); ws = wb.active; ws.append(["Date", "Description", "Currency", "Amount", "Without VAT", "VAT", "Reference"]); ws.append(["05-03-2025", "Rent", "USD", 500, 0, 55, "R-3"]); ws.append([None] * 7)
        wb.save(Path(self.folder.name) / "exp.xlsx")
        expenses = read_expenses(Path(self.folder.name) / "exp.xlsx")
        self.assertEqual(len(expenses), 1); self.assertEqual((expenses[0]["with_vat_subtotal"], expenses[0]["vat"], expenses[0]["reference"]), (500, 55, "R-3"))
        wb = Workbook(); ws = wb.active; ws.append(["Declaration No", "Freight", "Insurance", "Customs Duties", "Broker Fees", "VAT"]); ws.append(["D-1", 100, 10, 200, 50, 40]); ws.append(["", 20, 0, 0, 0, 2])
        wb.save(Path(self.folder.name) / "customs.xlsx")
        costs = read_customs_costs(Path(self.folder.name) / "customs.xlsx")
        self.assertEqual((costs["freight"], costs["customs_duties"], costs["import_vat"], costs["customs_declaration_no"]), (120, 200, 42, "D-1"))

class YearEndClosingTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); root = Path(self.folder.name)
        self.master = Database(root / "master.db"); self.master.initialize("secret")
        self.manager = CompanyManager(root / "master.db"); self.company = self.manager.list_companies()[0]["id"]  # the default company (no folder yet)
        self.db = self.manager.database(self.company, 2024); u = 1
        self.db.save_exchange_rate({"date_from": "01-01-2024", "date_to": "31-12-2024", "from_currency": "USD", "to_currency": "LBP", "rate": "89500"}, u)
        self.party = self.db.save_party({"kind": "customer", "name": "Client A", "account_category": "client"}, u)
        self.db.create_manual_invoice({"invoice_date": "15-03-2024", "party_name": "Client A", "kind": "sales", "currency": "USD", "status": "posted", "source_file": "Sales Invoice"},
                                      [{"description": "S", "quantity": 1, "unit_price": 1000}], u)
        self.db.create_manual_invoice({"invoice_date": "16-03-2024", "party_name": "Local", "kind": "sales", "currency": "LBP", "status": "posted"}, [{"description": "S", "quantity": 1, "unit_price": 8950000}], u)
        self.db.add_expense({"expense_date": "20-03-2024", "description": "Rent", "currency": "USD", "with_vat_subtotal": "300", "vat": "0"}, u)

    def tearDown(self): self.folder.cleanup()

    def test_close_as_journal_voucher_and_open_next_year(self):
        with self.db.connect() as db:  # an old-style closing that must be removed
            entry = db.execute("INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_at) VALUES('CLOSE-2024-USD','2024-12-31','old','year_close',2024,'USD',?)", (utcnow(),)).lastrowid
            db.execute("INSERT INTO journal_lines(entry_id,account_id,debit,credit) VALUES(?,(SELECT id FROM accounts WHERE code='121'),'5','0')", (entry,))
        result = self.manager.close_and_open_year(self.company, 2024, 1)
        self.assertEqual(result["removed_old_closing"], 1); self.assertEqual(sorted(result["opening_vouchers"]), ["OPEN-2025-LBP", "OPEN-2025-USD"])
        vouchers = {e["entry_number"]: e for e in self.db.journal() if e["source_type"] == "journal_voucher"}
        self.assertEqual(len({e["entry_id"] for e in vouchers.values()}), 2)
        detail = self.db.journal_voucher_detail(next(iter(vouchers.values()))["entry_id"])
        self.assertEqual(detail["voucher"]["voucher_type"], "05"); self.assertTrue(detail["voucher"]["description"].startswith("CLOSING 6&7 - 2024"))
        closed_pnl = self.db.profit_and_loss("2024-01-01", "2024-12-31")
        self.assertEqual({r["code"]: r["amount"] for r in closed_pnl if r["currency"] == "USD"}, {"601100000": 300, "713": 1000})
        pnl = ledger_reports.build_account_report(self.db, {"profit_loss_only": True, "first_column": "USD", "second_column": "none"})
        self.assertEqual(float(pnl["sections"][0]["rows"][-1][-1]), -1000 + 300 - 100)  # still shows the year's result
        next_year = self.manager.database(self.company, 2025)
        tb = ledger_reports.build_account_report(next_year, {"first_column": "account", "second_column": "LBP"})
        usd = next(s for s in tb["sections"] if s["heading"].endswith("USD"))["rows"]
        balances = {r[0]: (float(r[-4]), float(r[-1])) for r in usd}
        self.assertEqual(balances["138"], (-700, -62650000)); self.assertEqual(balances[self.party["account_number"]], (1110, 99345000))
        self.assertNotIn("713", balances); self.assertEqual(balances["GRAND TOTAL"], (0, 0))
        with self.assertRaisesRegex(ValueError, "already closed"): self.manager.close_and_open_year(self.company, 2024, 1)

    def test_delete_closing_reopen_and_provisional_opening(self):
        self.manager.close_and_open_year(self.company, 2024, 1)
        reopened = self.manager.reopen_year(self.company, 2024, 1)
        self.assertEqual((reopened["removed_closing_entries"], reopened["removed_opening_entries"]), (2, 2))
        self.assertFalse([e for e in self.db.journal() if e["source_type"] == "journal_voucher"])
        refreshed = self.manager.refresh_opening(self.company, 2024, 1)
        self.assertTrue(refreshed["provisional"])
        lines = {(e["currency"], e["account_code"]): e["debit"] - e["credit"] for e in self.manager.database(self.company, 2025).journal() if e["source_type"] == "opening"}
        self.assertEqual(lines[("USD", "138")], -700); self.assertEqual(lines[("LBP", "138")], -8950000)
        self.assertNotIn(("USD", "713"), lines)

class LebanesePayrollRulesTest(unittest.TestCase):
    """Worked examples under Budget Law 324/2024, Decree 12966/2024, MoF decision 1195 and the NSSF memos."""
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name)
        self.db.apply_lebanese_payroll_rules(self.user)
        self.single = self.db.save_employee({"employee_number": "1000", "full_name": "Single", "currency": "LBP", "base_salary": "89500000", "nssf_number": "1", "mof_number": "2"}, self.user)
        self.family = self.db.save_employee({"employee_number": "2000", "full_name": "Married", "currency": "USD", "base_salary": "2000", "marital_status": "married", "children": 3}, self.user)

    def tearDown(self): self.folder.cleanup()

    def calc(self, employee, date, **extra): return self.db.calculate_payroll({"employee_id": employee["id"], "period_date": date, **extra})

    def test_official_periods_and_published_example(self):
        periods = [(p["date_from"], p["medical_ceiling"], p["family_ceiling"], p["tax_rounding"]) for p in self.db.list_payroll_settings()]
        self.assertEqual(periods[1], ("2024-04-01", "90000000", "12000000", "0")); self.assertIn(("2026-05-01", "120000000", "28000000", "10000"), periods)
        result = self.calc(self.single, "30-04-2024")  # L'Orient Today worked example: LBP 1.074 bn a year, single
        self.assertEqual((result["income_tax_lbp"], result["employee_nssf_lbp"], result["compliance_notes"]), (1480000, 2685000, []))

    def test_exemptions_one_off_retro_and_rounding(self):
        transport = self.calc(self.single, "31-01-2025", transport="13500000", transport_days="22")
        self.assertEqual((transport["exempt_transport"], transport["income_tax_lbp"]), (9900000, 1630000))
        thirteenth = self.calc(self.single, "31-12-2025", thirteenth_month="89500000")
        self.assertEqual((thirteenth["regular_tax"], thirteenth["one_off_tax"], thirteenth["employee_nssf_lbp"]), (1480000, 3580000, 3600000))
        retro = self.calc(self.single, "31-05-2025", retro_salary="9000000", retro_from="01-01-2025", retro_to="31-03-2025")
        self.assertEqual((retro["retro_tax_lbp"], retro["employee_nssf_lbp"]), (360000, 2730000))  # NSSF uses the 90M ceiling of Jan-Mar 2025
        family = self.calc(self.family, "31-05-2026")
        self.assertEqual(family["income_tax_lbp"], 4960000); self.assertAlmostEqual(family["family_allowance"], 62.18, places=2)
        self.assertIn("NSSF number missing in the employee file", family["compliance_notes"])
        with self.assertRaisesRegex(ValueError, "Transport days"): self.calc(self.single, "31-01-2025", transport_days="40")

    def test_family_allowance_posting_balances(self):
        saved = self.db.save_payroll({"employee_id": self.family["id"], "period_date": "31-05-2026"}, self.user)
        self.assertEqual(json_notes := __import__("json").loads(saved["compliance_notes"]), json_notes)
        self.db.post_payroll(saved["id"], self.user)
        self.assertAlmostEqual(sum(r["debit"] - r["credit"] for r in self.db.journal()), 0, places=2)
        nssf = [r for r in self.db.journal() if r["account_code"] == "4431"]
        self.assertAlmostEqual(sum(r["debit"] for r in nssf), 62.18, places=2)

    def test_family_tax_deduction_halved_when_spouse_works(self):
        # The spouse deduction applies only to a dependent spouse; two working parents split only the child deduction.
        stay_home = self.db.save_employee({"employee_number": "3000", "full_name": "Home Spouse", "currency": "LBP",
            "base_salary": "120000000", "marital_status": "married", "children": 3, "spouse_works": False}, self.user)
        both_work = self.db.save_employee({"employee_number": "3100", "full_name": "Working Spouse", "currency": "LBP",
            "base_salary": "120000000", "marital_status": "married", "children": 3, "spouse_works": True}, self.user)
        home = self.calc(stay_home, "31-05-2026"); working = self.calc(both_work, "31-05-2026")
        self.assertGreater(working["income_tax_lbp"], home["income_tax_lbp"])  # smaller deduction -> more tax
        self.assertTrue(any("Child tax deduction split equally" in note for note in working["compliance_notes"]))
        self.assertFalse(any("Child tax deduction split equally" in note for note in home["compliance_notes"]))

    def test_end_of_service_exempt_for_foreign_or_over_64(self):
        lebanese = self.db.save_employee({"employee_number": "4000", "full_name": "Local Young", "currency": "LBP",
            "base_salary": "60000000", "nationality": "Lebanese", "birth_date": "01-01-1990"}, self.user)
        foreign = self.db.save_employee({"employee_number": "4100", "full_name": "Foreign Worker", "currency": "LBP",
            "base_salary": "60000000", "nationality": "Syrian", "birth_date": "01-01-1990"}, self.user)
        senior = self.db.save_employee({"employee_number": "4200", "full_name": "Senior Local", "currency": "LBP",
            "base_salary": "60000000", "nationality": "Lebanese", "birth_date": "01-01-1955"}, self.user)
        local = self.calc(lebanese, "31-05-2026")
        self.assertGreater(local["employer_end_service"], 0)  # Lebanese under 64 still owes the 8.5%
        foreign_calc = self.calc(foreign, "31-05-2026")
        self.assertEqual(foreign_calc["employer_end_service"], 0)
        self.assertTrue(any("end-of-service" in note and "foreign" in note for note in foreign_calc["compliance_notes"]))
        senior_calc = self.calc(senior, "31-05-2026")
        self.assertEqual(senior_calc["employer_end_service"], 0)
        self.assertTrue(any("end-of-service" in note and "over 64" in note for note in senior_calc["compliance_notes"]))

    def test_nssf_family_allowance_reported_on_statement(self):
        # A married employee with a non-working spouse and children receives the NSSF family allowance on the payslip.
        breadwinner = self.db.save_employee({"employee_number": "5000", "full_name": "Provider", "currency": "LBP",
            "base_salary": "60000000", "marital_status": "married", "children": 2, "spouse_works": False,
            "nssf_number": "NSSF-9", "mof_number": "MOF-9"}, self.user)
        result = self.calc(breadwinner, "31-05-2026")
        self.assertGreater(result["family_allowance"], 0)
        saved = self.db.save_payroll({"employee_id": breadwinner["id"], "period_date": "31-05-2026"}, self.user)
        self.db.post_payroll(saved["id"], self.user)
        r6 = build_payroll_report(self.db, "R6", "monthly", 2026, 5, "both")
        sheet = next(s for s in r6["sections"] if "Provider" in s["heading"])
        self.assertIn("NSSF Family Allowance", sheet["headers"])
        allowance_column = sheet["headers"].index("NSSF Family Allowance")
        self.assertGreater(sheet["rows"][0][allowance_column], 0)

class LebaneseVatLawTest(unittest.TestCase):
    """Partial deduction (Art. 31), zero-rated and exempt supplies, reverse charge (Art. 40), Q4 adjustment and refund (Art. 30)."""
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name)
        self.db.save_exchange_rate({"date_from": "01-01-2025", "date_to": "31-12-2025", "from_currency": "USD", "to_currency": "LBP", "rate": "89500"}, self.user)

    def tearDown(self): self.folder.cleanup()

    def sale(self, date, amount, treatment="standard", rate=11):
        return self.db.create_manual_invoice({"invoice_date": date, "party_name": "Client", "kind": "sales", "currency": "USD", "status": "posted", "vat_treatment": treatment},
                                             [{"description": "S", "quantity": 1, "unit_price": amount, "vat_rate": rate}], self.user)

    def purchase(self, date, amount, use="mixed", treatment="standard", rate=11):
        return self.db.create_manual_invoice({"invoice_date": date, "party_name": "Supplier", "kind": "purchases", "currency": "USD", "status": "posted", "vat_use": use, "vat_treatment": treatment},
                                             [{"description": "P", "quantity": 1, "unit_price": amount, "vat_rate": rate}], self.user)

    def test_supply_types_and_partial_deduction(self):
        self.sale("10-02-2025", 6000); self.sale("11-02-2025", 2000, "zero_rated", 0); self.sale("12-02-2025", 2000, "exempt", 0)
        self.purchase("15-02-2025", 1000, "mixed"); self.purchase("16-02-2025", 500, "taxable"); self.purchase("17-02-2025", 300, "exempt")
        result = vat_return.build_vat_return(self.db, 2025, 1); usd = result["per_currency"]["USD"]
        self.assertEqual(result["deduction_ratio"], Decimal("0.8"))  # (6000 + 2000) / 10000
        self.assertEqual((usd["sales"]["base"], usd["sales_zero"]["base"], usd["sales_exempt"]["base"]), (6000, 2000, 2000))
        self.assertEqual(usd["prorata"]["vat"], Decimal("-22.00"))  # 20% of the 110 mixed-use VAT
        self.assertEqual(usd["total_input"]["vat"], Decimal("143.00"))  # 110 + 55 - 22 ; the 33 on exempt-use purchases is blocked
        self.assertEqual(usd["non_deductible"]["vat"], Decimal("55.00"))
        self.assertEqual(usd["net"]["vat"], Decimal("517.00"))
        self.db.save_vat_provisional_ratio(2025, "90", self.user)
        self.assertEqual(vat_return.build_vat_return(self.db, 2025, 1)["deduction_ratio"], Decimal("0.9"))
        with self.assertRaisesRegex(ValueError, "VAT treatment"): self.sale("10-02-2025", 1, "luxury")

    def test_q4_final_ratio_adjusts_the_year(self):
        self.db.save_vat_provisional_ratio(2025, "100", self.user)
        self.sale("10-02-2025", 5000); self.purchase("15-02-2025", 1000, "mixed")
        vat_return.save_return(self.db, 2025, 1, self.user)
        self.sale("10-11-2025", 1000, "exempt", 0)  # year turnover: 5000 taxable, 5000... ratio = 5000 / 6000
        self.sale("11-11-2025", 4000, "exempt", 0)
        q4 = vat_return.build_vat_return(self.db, 2025, 4)
        self.assertEqual(q4["deduction_ratio"], Decimal("0.5")); self.assertEqual(q4["ratio_source"], "final annual ratio")
        self.assertEqual(q4["totals_lbp"]["annual_adjustment"], -4922500)  # Q1 mixed VAT 110 USD = 9,845,000 LBP x (50% - 100%)
        self.assertEqual(q4["annual_adjustment_detail"][0]["ratio_applied"], Decimal("1"))

    def test_reverse_charge_refund_and_due_dates(self):
        self.purchase("10-05-2025", 1000, "taxable", "reverse_charge", 0)  # software from abroad, no VAT on the invoice
        usd = vat_return.build_vat_return(self.db, 2025, 2)["per_currency"]["USD"]
        self.assertEqual((usd["reverse_output"]["vat"], usd["purchases"]["vat"], usd["net"]["vat"]), (110, 110, 0))
        self.purchase("12-05-2025", 10000, "taxable")
        with self.assertRaisesRegex(ValueError, "cannot exceed"): vat_return.build_vat_return(self.db, 2025, 2, refund_requested="999999999999")
        result = vat_return.build_vat_return(self.db, 2025, 2, refund_requested="10000000")
        self.assertEqual(result["credit_carried_forward_lbp"], 1100 * 89500 - 10000000); self.assertTrue(result["warnings"])
        self.assertEqual(vat_return.due_date(2025, 1), "2025-04-20"); self.assertEqual(vat_return.due_date(2026, 1), "2026-04-30")

class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); root = Path(self.folder.name)
        self.master = Database(root / "master.db"); self.master.initialize("secret")
        self.manager = CompanyManager(root / "master.db"); self.company = self.manager.list_companies()[0]["id"]; self.db = self.manager.database(self.company, 2024); u = self.user = 1
        self.store = inventory.save_warehouse(self.db, {"name": "Site Store"}, u)
        self.hpl = inventory.save_item(self.db, {"name": "HPL Panel", "unit": "sheet", "sales_price": "120", "reorder_level": "80", "category": "Cladding"}, u)
        self.alu = inventory.save_item(self.db, {"name": "Aluminium Profile", "unit": "m", "sales_price": "15"}, u)
        inventory.save_document(self.db, {"doc_type": "opening", "doc_date": "01-01-2024", "warehouse_id": "MAIN"}, [{"sku": self.hpl["sku"], "quantity": 50, "unit_cost": 80}, {"sku": self.alu["sku"], "quantity": 200, "unit_cost": 8}], u)
        inventory.save_document(self.db, {"doc_type": "receipt", "doc_date": "10-02-2024", "warehouse_id": "MAIN"}, [{"sku": self.hpl["sku"], "quantity": 50, "unit_cost": 100}], u)
        self.db.save_party({"kind": "customer", "name": "Tower Client", "account_category": "client"}, u)
        self.invoice = self.db.create_manual_invoice({"invoice_date": "15-03-2024", "party_name": "Tower Client", "kind": "sales", "currency": "USD", "status": "posted"},
                                                     [{"description": "HPL", "quantity": 30, "unit_price": 120, "item_code": self.hpl["sku"]}], u)

    def tearDown(self): self.folder.cleanup()

    def item(self, sku): return next(i for i in inventory.list_items(self.db) if i["sku"] == sku)

    def test_codes_average_cost_and_invoice_issue(self):
        self.assertEqual((self.hpl["sku"], self.alu["sku"], self.store["code"]), ("ITM-00001", "ITM-00002", "WH01"))
        hpl = self.item("ITM-00001"); self.assertEqual((hpl["quantity"], hpl["average_cost"], hpl["stock_value"]), (70, 90, 6300))
        with self.assertRaisesRegex(ValueError, "Not enough stock"):
            self.db.create_manual_invoice({"invoice_date": "16-03-2024", "party_name": "Tower Client", "kind": "sales", "currency": "USD", "status": "posted"},
                                          [{"description": "HPL", "quantity": 500, "unit_price": 120, "item_code": "ITM-00001"}], self.user)
        self.assertEqual(len(self.db.list_invoices()), 1)  # the refused invoice is not kept
        self.db.delete_invoice(self.invoice, self.user); self.assertEqual(self.item("ITM-00001")["quantity"], 100)

    def test_sales_credit_note_returns_stock_as_receipt(self):
        # After the sale of 30, HPL is at 70 on hand (avg cost 90).
        self.assertEqual(self.item("ITM-00001")["quantity"], 70)
        credit = self.db.create_manual_invoice(
            {"invoice_date": "20-03-2024", "party_name": "Tower Client", "kind": "sales", "currency": "USD", "status": "posted",
             "doc_subtype": "credit_note", "invoice_number": self.db.next_invoice_number("credit_note", "20-03-2024"),
             "supplier_side": "C - Credit", "vat_side": "D - Debit", "expense_side": "D - Debit", "expense_account": "709000001"},
            [{"description": "HPL return", "quantity": 10, "unit_price": 120, "item_code": "ITM-00001"}], self.user)
        # The returned goods come back in: a Stock Receipt (not a second issue) valued at the average cost.
        stock = next(d for d in inventory.list_documents(self.db) if d.get("invoice_id") == credit)
        self.assertEqual(stock["doc_type"], "receipt")
        hpl = self.item("ITM-00001")
        self.assertEqual(hpl["quantity"], 80)  # 70 back up to 80
        self.assertEqual(hpl["average_cost"], 90)
        # Deleting the credit note removes the return movement again.
        self.db.delete_invoice(credit, self.user)
        self.assertEqual(self.item("ITM-00001")["quantity"], 70)

    def test_transfer_adjustment_fifo_and_negative_protection(self):
        inventory.save_document(self.db, {"doc_type": "transfer", "doc_date": "20-03-2024", "warehouse_id": "MAIN", "to_warehouse_id": "WH01"}, [{"sku": "ITM-00001", "quantity": 10}], self.user)
        with self.assertRaisesRegex(ValueError, "Not enough stock of ITM-00001 in WH01"):
            inventory.save_document(self.db, {"doc_type": "adjustment_out", "doc_date": "21-03-2024", "warehouse_id": "WH01"}, [{"sku": "ITM-00001", "quantity": 11}], self.user)
        inventory.save_document(self.db, {"doc_type": "adjustment_out", "doc_date": "21-03-2024", "warehouse_id": "WH01"}, [{"sku": "ITM-00001", "quantity": 2}], self.user)
        valuation = inventory.build_report(self.db, "valuation", {"date_to": "31-12-2024"})["sections"]
        self.assertEqual(float(valuation[0]["rows"][-1][6]), 68 * 90 + 1600); self.assertEqual(valuation[1]["heading"], "Value by warehouse")
        fifo = inventory.build_report(self.db, "valuation", {"date_to": "31-12-2024", "method": "fifo"})["sections"][0]["rows"][-1]
        self.assertEqual(float(fifo[6]), 18 * 80 + 50 * 100 + 1600)  # oldest layer (80) consumed first
        card = inventory.build_report(self.db, "stock_card", {"item_id": self.hpl["id"], "date_from": "01-01-2024", "date_to": "31-12-2024", "warehouse_id": self.store["id"]})["sections"][0]["rows"]
        self.assertEqual(float(card[-1][-2]), 8)
        margin = inventory.build_report(self.db, "margin", {"date_to": "31-12-2024"})["sections"][0]["rows"][0]
        self.assertEqual([float(x) for x in margin[2:6]], [30, 3600, 2700, 900])
        reorder = inventory.build_report(self.db, "reorder", {"date_to": "31-12-2024"})["sections"][0]["rows"]
        self.assertEqual(reorder[0][0], "ITM-00001")
        inventory.save_document(self.db, {"doc_type": "issue", "doc_date": "22-03-2024", "warehouse_id": "MAIN"}, [{"sku": "ITM-00001", "quantity": 55}], self.user)
        receipt = next(d for d in inventory.list_documents(self.db) if d["doc_type"] == "receipt")
        with self.assertRaisesRegex(ValueError, "cannot be deleted"): inventory.delete_document(self.db, receipt["id"], self.user)  # 60 on hand before, 55 already issued

    def test_stock_variation_and_next_year_opening(self):
        result = self.manager.close_and_open_year(self.company, 2024, self.user)
        variation = [(r["account_code"], r["debit"], r["credit"]) for r in self.db.journal() if (r["description"] or "").startswith("STOCK VARIATION")]
        self.assertEqual(variation, [("37", 7900.0, 0.0), ("6052", 0.0, 7900.0)])
        self.assertEqual(len(result["stock_openings"]), 1)
        next_year = self.manager.database(self.company, 2025)
        self.assertEqual([(i["sku"], i["quantity"], i["average_cost"]) for i in inventory.list_items(next_year)], [("ITM-00001", 70, 90), ("ITM-00002", 200, 8)])
        stock_line = next(r for r in ledger_reports.build_account_report(next_year, {"first_column": "USD", "second_column": "none"})["sections"][0]["rows"] if r[0] == "37")
        self.assertEqual(float(stock_line[-1]), 7900)
        inventory.save_document(next_year, {"doc_type": "receipt", "doc_date": "10-02-2025", "warehouse_id": "MAIN"}, [{"sku": "ITM-00001", "quantity": 10, "unit_cost": 100}], self.user)
        second = inventory.post_stock_variation(next_year, 2025, self.user)
        self.assertEqual((second["opening"], second["closing"]), (7900, 8900))

class ArabicPdfAndNssfTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name)
        self.db.save_settings({"company_nssf": "1234567"}, self.user)
        self.rami = self.db.save_employee({"employee_number": "1000", "full_name": "رامي الخوري", "currency": "LBP", "base_salary": "100000000", "nssf_number": "5550001", "mof_number": "1"}, self.user)
        self.maya = self.db.save_employee({"employee_number": "2000", "full_name": "Maya Haddad", "currency": "USD", "base_salary": "2000", "nssf_number": "5550002", "mof_number": "2"}, self.user)
        for employee in (self.rami, self.maya):
            for day in ("31-07-2025", "31-08-2025", "30-09-2025"):
                self.db.post_payroll(self.db.save_payroll({"employee_id": employee["id"], "period_date": day}, self.user)["id"], self.user)

    def tearDown(self): self.folder.cleanup()

    def test_rules_load_automatically_and_apply_by_month(self):
        self.assertGreaterEqual(len(self.db.list_payroll_settings()), 6)
        mid_november = self.db.calculate_payroll({"employee_id": self.rami["id"], "period_date": "15-11-2024"})
        self.assertEqual(mid_november["rules_date"], "2024-11-30"); self.assertEqual(mid_november["income_tax_lbp"] % 10000, 0)  # rounding from 25-11-2024 applies to November
        self.assertEqual(self.db.calculate_payroll({"employee_id": self.rami["id"], "period_date": "10-08-2025"})["ceilings"]["medical"], 120000000)
        custom = self.db.list_payroll_settings()[-1]; custom["medical_ceiling"] = "99000000"; self.db.save_payroll_settings(custom, self.user)
        self.db.initialize("secret"); self.assertEqual(self.db.list_payroll_settings()[-1]["medical_ceiling"], "99000000")  # never overwritten
        table = build_payroll_report(self.db, "CEILINGS", "yearly", 2025)["sections"][0]["rows"]
        self.assertEqual((table[6][2], table[7][2], table[6][3]), (90000000, 120000000, 18000000))

    def test_nssf_statement_monthly_ceilings_and_payment(self):
        result = build_payroll_report(self.db, "NSSF", "quarterly", 2025, 3)
        rows = {(r[1], r[2]): r for r in result["sections"][0]["rows"]}
        self.assertEqual(rows[("رامي الخوري", "07-2025")][4:7], [90000000, 2700000, 7200000])  # 90M ceiling in July
        self.assertEqual(rows[("رامي الخوري", "08-2025")][4:7], [100000000, 3000000, 8000000])  # 120M ceiling from August
        self.assertEqual(rows[("Maya Haddad", "07-2025")][3:6], [179000000, 90000000, 2700000])  # USD salary converted, exact LBP
        self.assertEqual(result["net_payable_lbp"], 145825000); self.assertIn("1234567", result["meta"][0])
        payment = self.db.record_nssf_payment({"amount": str(result["net_payable_lbp"]), "payment_date": "15-10-2025", "cash_account": "531", "reference": "NSSF-778", "period_label": result["period_label"]}, self.user)
        lines = [(r["account_code"], r["debit"], r["credit"]) for r in self.db.journal() if r["entry_number"] == payment["voucher"]]
        self.assertEqual(lines, [("4431", 145825000.0, 0.0), ("531", 0.0, 145825000.0)])

    def test_arabic_text_in_pdf(self):
        from report_export import shape_arabic, has_arabic, arabic_fonts, export_sections_pdf, export_invoice_pdf
        self.assertEqual(arabic_fonts(), ("Amiri", "Amiri-Bold"))
        self.assertTrue(has_arabic("شركة")); self.assertFalse(has_arabic("Company"))
        self.assertNotEqual(shape_arabic("الضريبة"), "الضريبة")  # letters joined and ordered right-to-left
        result = build_payroll_report(self.db, "NSSF", "quarterly", 2025, 3)
        path = Path(self.folder.name) / "nssf.pdf"; export_sections_pdf(path, result["title"], result["meta"], result["sections"])
        content = path.read_bytes(); self.assertTrue(content.startswith(b"%PDF")); self.assertIn(b"Amiri", content)
        invoice = Path(self.folder.name) / "invoice.pdf"
        export_invoice_pdf(invoice, {"invoice_number": "SAL-1", "invoice_date": "01-01-2025", "party_name": "شركة الأرز", "currency": "USD", "kind": "sale", "subtotal": 10, "vat": 1.1, "total": 11.1},
                           [{"description": "ألواح", "quantity": 1, "unit_price": 10, "subtotal": 10, "vat_rate": 11, "vat": 1.1, "total": 11.1}], company={"company_name": "إيكولوج"})
        self.assertIn(b"Amiri", invoice.read_bytes())

    def test_old_company_files_are_upgraded_when_opened(self):
        import sqlite3
        root = Path(self.folder.name) / "companies"; master = Database(Path(self.folder.name) / "master.db"); master.initialize("secret")
        manager = CompanyManager(Path(self.folder.name) / "master.db"); company = manager.create_company({"name": "Old Co", "year": 2024}, master)
        path = company["years"][0]["database"]; connection = sqlite3.connect(path)
        connection.execute("DROP TABLE stock_documents"); connection.execute("ALTER TABLE invoices DROP COLUMN vat_treatment"); connection.commit(); connection.close()
        database = CompanyManager(Path(self.folder.name) / "master.db").database(company["id"], 2024)
        database.create_manual_invoice({"invoice_date": "10-02-2024", "party_name": "X", "kind": "sales", "currency": "USD", "status": "posted"}, [{"description": "a", "quantity": 1, "unit_price": 10}], 1)
        self.assertEqual(inventory.list_documents(database), []); self.assertEqual(len(database.list_invoices()), 1)

class Version22Test(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name)
        self.client_party = self.db.save_party({"kind": "customer", "name": "Client A", "account_category": "client"}, self.user)
        self.db.save_party({"kind": "supplier", "name": "Supplier A", "account_category": "supplier"}, self.user)

    def tearDown(self): self.folder.cleanup()

    def test_calculation_tafqeet_and_accounts(self):
        import invoice_calc, tafqeet
        result = invoice_calc.calculate([{"quantity": 10, "unit_price": 120}, {"quantity": 1, "unit_price": 300, "discount_percent": 10}], invoice_discount_percent=10)
        self.assertEqual((result["total"], result["discount"], result["total_ht"], result["vat"], result["grand_total"]), (1470, 147, 1323, 145.53, 1468.53))
        self.assertEqual(invoice_calc.calculate([{"quantity": 5, "unit_price": 150}], zero_vat=True)["vat"], 0)
        words = tafqeet.amount_in_words(1332, "USD")
        self.assertEqual(words["en"], "One thousand three hundred thirty-two US Dollars only"); self.assertTrue(words["ar"].startswith("فقط ألف وثلاثمئة"))
        codes = {a["code"] for a in self.db.list_accounts()}
        self.assertTrue({"44210", "44211", "44216", "4427", "6311", "6312", "6313", "6315", "6316", "6319", "4411", "4431", "138", "139", "601800001"}.issubset(codes))
        self.assertEqual(self.db.default_payroll_account_map()["commission"], "6313")

    def test_credit_note_allocation_and_vat(self):
        import invoice_calc
        calc = invoice_calc.calculate([{"description": "Panels", "quantity": 10, "unit_price": 100}])
        invoice = self.db.create_manual_invoice({"invoice_date": "10-02-2026", "party_name": "Client A", "kind": "sales", "currency": "USD", "status": "posted"}, calc["lines"], self.user)
        note = invoice_calc.calculate([{"description": "Return", "quantity": 1, "unit_price": 100}])
        credit = self.db.create_manual_invoice({"invoice_date": "12-02-2026", "party_name": "Client A", "kind": "sales", "currency": "USD", "status": "posted", "doc_subtype": "credit_note",
            "invoice_number": self.db.next_invoice_number("credit_note", "12-02-2026"), "supplier_side": "C - Credit", "vat_side": "D - Debit", "expense_side": "D - Debit",
            "expense_account": "719000001"}, note["lines"], self.user)
        rows = {r["id"]: r for r in self.db.list_invoices()}
        self.assertEqual((rows[credit]["invoice_number"], rows[credit]["doc_subtype"]), ("CN-2026-000001", "credit_note"))
        self.assertEqual(rows[credit]["expense_account"],"719000001")
        self.assertIn("709000001",{account["code"] for account in self.db.list_accounts()})
        credit_lines = {row["account_code"]: (float(row["debit"]),float(row["credit"])) for row in self.db.journal() if row["source_id"]==credit}
        self.assertEqual(credit_lines[rows[credit]["supplier_account"]], (0,111))
        self.assertEqual(credit_lines[rows[credit]["expense_account"]], (100,0))
        self.assertEqual(credit_lines[rows[credit]["vat_account"]], (11,0))
        vat = vat_return.build_vat_return(self.db, 2026, 1)["per_currency"]["USD"]["sales"]["vat"]
        self.assertEqual(float(vat), 110 - 11)  # the credit note reduces the output VAT
        payment = self.db.add_payment({"kind": "customer_receipt", "party_id": self.client_party["id"], "payment_date": "20-02-2026", "currency": "USD", "amount": "500"}, self.user)
        self.db.save_allocations(payment, [{"invoice_id": invoice, "amount": 500}], self.user)
        open_items = {d["id"]: d["open_amount"] for d in self.db.open_documents(self.client_party["id"])}
        self.assertEqual((open_items[invoice], open_items[credit]), (610, -111))
        with self.assertRaisesRegex(ValueError, "more than the payment"): self.db.save_allocations(payment, [{"invoice_id": invoice, "amount": 600}], self.user)

    def test_landed_cost_accounts_and_closing_to_138(self):
        purchase = self.db.create_manual_invoice({"invoice_date": "15-03-2026", "party_name": "Supplier A", "kind": "purchases", "currency": "USD", "status": "posted"},
                                                 [{"description": "Goods", "quantity": 1, "unit_price": 1000, "vat_rate": 11}], self.user)
        self.db.add_landed_cost(purchase, {"freight": "120", "customs_duties": "200", "import_vat": "35"}, self.user)
        balances = {r["code"]: r["closing_balance"] for r in self.db.trial_balance()}
        self.assertEqual((balances["601800001"], balances["601800003"], balances["44210"]), (120, 200, 110 + 35))
        self.db.create_manual_invoice({"invoice_date": "20-03-2026", "party_name": "Client A", "kind": "sales", "currency": "USD", "status": "posted"}, [{"description": "S", "quantity": 1, "unit_price": 2000}], self.user)
        result = year_end.close_year(self.db, 2026, self.user)
        closing = [r for r in self.db.journal() if (r["description"] or "").startswith("CLOSING 6&7")]
        self.assertTrue(closing); self.assertIn("138", {r["account_code"] for r in closing}); self.assertEqual(result["net_results"]["USD"], 680)

    def test_items_categories_physical_count_and_templates(self):
        from importer import write_invoice_template, read_invoice_lines
        inventory.save_category(self.db, {"kind": "subcategory", "name": "HPL", "parent": "Cladding"}, self.user)
        inventory.save_category(self.db, {"kind": "unit", "name": "panel"}, self.user)
        data = inventory.list_categories(self.db); self.assertEqual(data["categories"][0]["subcategories"], ["HPL"]); self.assertIn("panel", data["units"])
        item = inventory.find_or_create_item(self.db, "HPL Panel 8mm", "panel", None, self.user)
        self.assertEqual(inventory.find_or_create_item(self.db, "hpl panel 8mm", "panel", None, self.user)["id"], item["id"])  # found, not duplicated
        inventory.save_item(self.db, {**item, "category": "Cladding", "subcategory": "HPL", "supplier_name": "Supplier A"}, self.user)
        inventory.save_document(self.db, {"doc_type": "receipt", "doc_date": "01-03-2026", "warehouse_id": "MAIN"}, [{"sku": item["sku"], "quantity": 40, "unit_cost": 80}], self.user)
        count = inventory.save_count(self.db, {"count_date": "31-03-2026", "warehouse_id": 1}, [{"item_id": item["id"], "sku": item["sku"], "counted": 37}], self.user, post=True)
        self.assertEqual(count["status"], "posted"); self.assertEqual(inventory.list_items(self.db)[0]["quantity"], 37)
        report = inventory.build_report(self.db, "valuation", {"date_to": "31-12-2026", "subcategory": "HPL", "supplier_id": inventory.list_items(self.db)[0]["supplier_id"]})
        self.assertEqual(report["sections"][0]["rows"][0][0], item["sku"])
        path = Path(self.folder.name) / "sales.xlsx"; write_invoice_template(path, "sales")
        invoices = read_invoice_lines(path, "sales")
        self.assertEqual(invoices, [])
        from openpyxl import load_workbook
        workbook = load_workbook(path)
        try:
            self.assertEqual(workbook.sheetnames, ["Invoices", "Examples", "How to fill"])
            self.assertEqual(workbook["Examples"]["A2"].value, "INV-001")
            worksheet = workbook["Invoices"]
            worksheet.append(["INV-101", "25-09-2026", "Client A", "USD", "", "Service", 1, "job", 100, 0, 11, "Taxable"])
            workbook.save(path)
        finally: workbook.close()
        invoices = read_invoice_lines(path, "sales")
        self.assertEqual([(i["invoice_number"], len(i["lines"])) for i in invoices], [("INV-101", 1)])

class DeleteYearTest(unittest.TestCase):
    def test_delete_last_year_and_redo_the_opening(self):
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); root = Path(folder.name)
        master = Database(root / "master.db"); master.initialize("secret"); manager = CompanyManager(root / "master.db")
        company = manager.list_companies()[0]["id"]; db = manager.database(company, 2024)
        db.create_manual_invoice({"invoice_date": "15-03-2024", "party_name": "C", "kind": "sales", "currency": "USD", "status": "posted"}, [{"description": "S", "quantity": 1, "unit_price": 1000}], 1)
        manager.close_and_open_year(company, 2024, 1)
        next_year = manager.database(company, 2025)
        next_year.create_manual_invoice({"invoice_date": "10-02-2025", "party_name": "C", "kind": "sales", "currency": "USD", "status": "posted"}, [{"description": "wrong", "quantity": 1, "unit_price": 5}], 1)
        with self.assertRaisesRegex(ValueError, "Only the last fiscal year"): manager.delete_year(company, 2024, 1)
        result = manager.delete_year(company, 2025, 1); self.assertEqual((result["deleted_year"], result["reopened_year"]), (2025, 2024))
        with self.assertRaisesRegex(ValueError, "only fiscal year"): manager.delete_year(company, 2024, 1)
        years = [y["year"] for y in manager.list_companies()[0]["years"]]
        self.assertEqual(years, [2024]); self.assertEqual(manager.year_status(company, 2024), "open")
        # 2.9.20: company files live in companies/<Company Name>/ (the deleted-years copies too)
        self.assertTrue(list((manager.company_folder(manager.list_companies()[0]) / "deleted_years").glob("2025_deleted_*.db")))
        self.assertFalse([e for e in db.journal() if (e["description"] or "").startswith("CLOSING 6&7")])
        manager.close_and_open_year(company, 2024, 1)
        fresh = manager.database(company, 2025)
        self.assertEqual(len(fresh.list_invoices()), 0)  # the deleted 2025 data is gone, the new opening is there
        self.assertTrue([e for e in fresh.journal() if e["source_type"] == "opening"])
        folder.cleanup()

class InventoryAgeingTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name); u = self.user
        self.hpl = inventory.save_item(self.db, {"name": "HPL Panel", "category": "Cladding", "sales_price": "120"}, u)
        self.alu = inventory.save_item(self.db, {"name": "Aluminium Profile", "category": "Profiles", "sales_price": "15"}, u)
        self.old = inventory.save_item(self.db, {"name": "Old Sealant", "category": "Chemicals", "sales_price": "9"}, u)
        for day, item, qty, cost in (("05-01-2025", self.hpl, 50, 80), ("10-06-2026", self.hpl, 50, 100), ("01-09-2026", self.alu, 200, 8), ("01-12-2024", self.old, 30, 5)):
            inventory.save_document(self.db, {"doc_type": "receipt", "doc_date": day, "warehouse_id": "MAIN"}, [{"sku": item["sku"], "quantity": qty, "unit_cost": cost}], u)
        inventory.save_document(self.db, {"doc_type": "issue", "doc_date": "20-07-2026", "warehouse_id": "MAIN"}, [{"sku": self.hpl["sku"], "quantity": 30}], u)

    def tearDown(self): self.folder.cleanup()

    def test_ageing_buckets_by_receipt_date(self):
        report = inventory.build_report(self.db, "ageing", {"date_to": "26-09-2026"})
        summary = {row[0]: float(row[1]) for row in report["sections"][0]["rows"]}
        self.assertEqual((summary["0-30 days"], summary["91-180 days"], summary["Over 365 days"], summary["TOTAL STOCK"]), (1600, 4500, 1950, 8050))
        rows = {row[0]: row for row in report["sections"][1]["rows"]}
        self.assertEqual(rows[self.hpl["sku"]][6], 256)  # (20 x 629 + 50 x 108) / 70 days
        self.assertEqual([row[0] for row in report["sections"][2]["rows"]], [self.hpl["sku"], self.old["sku"]])
        fifo = inventory.build_report(self.db, "ageing", {"date_to": "26-09-2026", "method": "fifo"})
        self.assertEqual(float({r[0]: r for r in fifo["sections"][1]["rows"]}[self.hpl["sku"]][5]), 20 * 80 + 50 * 100)
        custom = inventory.build_report(self.db, "ageing", {"date_to": "26-09-2026", "buckets": "90,365"})
        self.assertEqual([r[0] for r in custom["sections"][0]["rows"]], ["0-90 days", "91-365 days", "Over 365 days", "TOTAL STOCK"])
        with self.assertRaisesRegex(ValueError, "buckets"): inventory.build_report(self.db, "ageing", {"buckets": "a,b"})

    def test_summary_and_valuation_by_category(self):
        summary = {row[0]: row[1] for row in inventory.build_report(self.db, "summary", {"date_to": "26-09-2026"})["sections"][0]["rows"]}
        self.assertEqual(float(summary["Stock value at cost (USD)"]), 8050)
        self.assertEqual(float(summary["Slow-moving stock value (no issue for 90 days)"]), 150)  # new arrivals are not slow
        valuation = inventory.build_report(self.db, "valuation", {"date_to": "26-09-2026"})["sections"][0]["rows"]
        self.assertIn("Subtotal Cladding", [r[0] for r in valuation]); self.assertEqual(float(valuation[-1][6]), 8050)

class BusinessReportsTest(unittest.TestCase):
    def setUp(self):
        import invoice_calc
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db, self.user = new_db(self.folder.name); u = self.user
        for name in ("Client A", "Client B"): self.db.save_party({"kind": "customer", "name": name, "account_category": "client"}, u)
        self.db.save_party({"kind": "supplier", "name": "Supplier S", "account_category": "supplier"}, u)
        def sale(day, party, lines, due=None, subtype="invoice"):
            calc = invoice_calc.calculate(lines); head = {"invoice_date": day, "party_name": party, "kind": "sales", "currency": "USD", "status": "posted", "due_date": due, "doc_subtype": subtype}
            if subtype == "credit_note": head.update(supplier_side="C - Credit", vat_side="D - Debit", expense_side="D - Debit", invoice_number="CN-1")
            return self.db.create_manual_invoice(head, calc["lines"], u)
        self.first = sale("10-03-2026", "Client A", [{"description": "HPL Panel", "quantity": 10, "unit": "sheet", "unit_price": 120}], "10-04-2026")
        sale("15-05-2026", "Client A", [{"description": "HPL Panel", "quantity": 5, "unit": "sheet", "unit_price": 120}, {"description": "Installation", "quantity": 1, "unit_price": 300}], "15-06-2026")
        sale("20-08-2026", "Client B", [{"description": "HPL Panel", "quantity": 2, "unit": "sheet", "unit_price": 110}], "19-10-2026")
        sale("25-08-2026", "Client A", [{"description": "HPL Panel", "quantity": 1, "unit": "sheet", "unit_price": 120}], subtype="credit_note")
        self.db.create_manual_invoice({"invoice_date": "01-09-2026", "party_name": "Supplier S", "kind": "purchases", "currency": "USD", "status": "posted"}, [{"description": "Goods", "quantity": 1, "unit_price": 2000}], u)
        payment = self.db.add_payment({"kind": "customer_receipt", "party_id": self.db.list_parties()[0]["id"], "payment_date": "01-05-2026", "currency": "USD", "amount": "500"}, u)
        self.db.save_allocations(payment, [{"invoice_id": self.first, "amount": 400}], u)
        self.options = {"date_from": "01-01-2026", "date_to": "26-09-2026", "basis": "USD"}

    def tearDown(self): self.folder.cleanup()

    def test_receivables_ageing(self):
        import business_reports
        report = business_reports.build(self.db, "receivables", self.options)
        rows = {r[0]: r for r in report["sections"][1]["rows"]}
        self.assertEqual([float(x) for x in rows["Client A"][2:8]], [0, 0, -133.2, 0, 1931, 0])  # 932 + 999 in 91-180 days, credit note 31-60
        self.assertEqual((float(rows["Client A"][9]), float(rows["Client A"][10])), (100, 1697.8))  # 100 received and not allocated
        self.assertEqual(float(rows["Client B"][2]), 244.2)  # not due yet

    def test_item_sales_3d_and_top(self):
        import business_reports
        by_client = business_reports.build(self.db, "item_sales_client", self.options)
        client_a = next(s for s in by_client["sections"] if s["heading"] == "Client: Client A")
        self.assertEqual((client_a["rows"][0][1], float(client_a["rows"][0][3])), ("HPL Panel", 14))  # 10 + 5 - 1 returned
        by_item = business_reports.build(self.db, "item_sales_item", self.options)
        self.assertIn("Item: - - HPL Panel (sheet)", [s["heading"] for s in by_item["sections"]])
        cube = business_reports.build(self.db, "analysis", {**self.options, "rows": "client", "columns": "quarter", "measure": "quantity"})["sections"][0]
        self.assertEqual(cube["headers"][1:4], ["2026-Q1", "2026-Q2", "2026-Q3"]); self.assertEqual(float(cube["rows"][-1][-2]), 17)  # 10 + 5 + 1 installation + 2 - 1 returned
        top = business_reports.build(self.db, "top_clients", self.options)["sections"][0]["rows"]
        self.assertEqual((top[0][1], float(top[0][3]), float(top[0][4]), float(top[0][5])), ("Client A", 1980, 217.8, 2197.8))
        suppliers = business_reports.build(self.db, "top_suppliers", self.options)["sections"][0]["rows"]
        self.assertEqual(float(suppliers[0][5]), 2220)
        with self.assertRaisesRegex(ValueError, "different"): business_reports.build(self.db, "analysis", {**self.options, "rows": "client", "columns": "client"})

    def test_delete_payroll_period_extends_previous(self):
        periods = self.db.list_payroll_settings(); last = periods[-1]["date_from"]
        after = self.db.delete_payroll_period(last, self.user)
        self.assertEqual(len(after), len(periods) - 1); self.assertIsNone(after[-1]["date_to"])

class NewCurrencyTest(unittest.TestCase):
    def test_payroll_and_vat_adjustment_in_a_new_currency(self):
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); db, user = new_db(folder.name)
        db.save_currency("SAR", "Saudi Riyal", user)
        db.save_exchange_rate({"date_from": "01-01-2026", "date_to": "31-12-2026", "from_currency": "SAR", "to_currency": "USD", "rate": "0.2667"}, user)
        employee = db.save_employee({"employee_number": "1000", "full_name": "E", "currency": "SAR", "base_salary": "5000", "nssf_number": "1", "mof_number": "2"}, user)
        result = db.calculate_payroll({"employee_id": employee["id"], "period_date": "28-02-2026"})  # LBP -> USD -> SAR
        self.assertEqual((result["income_tax_lbp"], result["employee_nssf"]), (2880000, 150))
        self.assertTrue(vat_return.add_adjustment(db, {"year": 2026, "quarter": 1, "adjustment_type": "output", "currency": "SAR", "amount": "5", "reason": "test"}, user))
        with self.assertRaisesRegex(ValueError, "not set up"): vat_return.add_adjustment(db, {"year": 2026, "quarter": 1, "adjustment_type": "output", "currency": "XYZ", "amount": "5", "reason": "test"}, user)
        folder.cleanup()

class BankReconciliationTest(unittest.TestCase):
    def test_import_match_post_and_difference(self):
        import bank_rec, business_reports
        from openpyxl import Workbook
        folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); db, user = new_db(folder.name)
        client = db.save_party({"kind": "customer", "name": "Client A", "account_category": "client"}, user)
        supplier = db.save_party({"kind": "supplier", "name": "Sup", "account_category": "supplier"}, user)
        db.add_payment({"kind": "customer_receipt", "party_id": client["id"], "payment_date": "05-03-2026", "currency": "USD", "amount": "1000", "cash_account": "512"}, user)
        db.add_payment({"kind": "supplier_payment", "party_id": supplier["id"], "payment_date": "10-03-2026", "currency": "USD", "amount": "400", "cash_account": "512"}, user)
        db.add_payment({"kind": "customer_receipt", "party_id": client["id"], "payment_date": "30-03-2026", "currency": "USD", "amount": "250", "cash_account": "512"}, user)
        book = Workbook(); sheet = book.active; sheet.append(["Date", "Description", "Reference", "Debit", "Credit"])
        for row in (["06-03-2026", "Transfer Client A", "TRF1", None, 1000], ["12-03-2026", "Cheque 101", "101", 400, None], ["31-03-2026", "Bank charges", "", 15, None]): sheet.append(row)
        path = Path(folder.name) / "statement.xlsx"; book.save(path)
        rows = bank_rec.read_statement_file(path); self.assertEqual([float(r["amount"]) for r in rows], [1000, -400, -15])
        self.assertEqual(bank_rec.add_statement_lines(db, "512", "USD", rows, user), 3)
        self.assertEqual(bank_rec.auto_match(db, "512", "USD", "2026-03-01", "2026-03-31"), 2)
        report = bank_rec.reconciliation(db, "512", "USD", "2026-03-01", "2026-03-31", "585")
        self.assertEqual((report["book_balance"], report["expected"], report["difference"]), (850, 585, 0))  # 850 - 250 not yet at the bank - 15 charges
        charges = next(l for l in bank_rec.statement_lines(db, "512", "2026-03-01", "2026-03-31") if not l["journal_line_id"])
        self.assertTrue(bank_rec.post_statement_line(db, charges["id"], "6739", user).startswith("JV-"))
        after = bank_rec.reconciliation(db, "512", "USD", "2026-03-01", "2026-03-31", "585")
        self.assertEqual((after["book_balance"], after["matched"], after["difference"]), (835, 3, 0))
        with self.assertRaisesRegex(ValueError, "bank or cash"): bank_rec.add_statement_lines(db, "4111", "USD", rows, user)
        charts = business_reports.dashboard_charts(db, {"year": 2026})
        self.assertEqual(charts["cash"][0], ["512", 835.0]); self.assertEqual(len(charts["months"]), 12)
        folder.cleanup()

class StandaloneEndToEndTest(unittest.TestCase):
    """Runs the embedded data service exactly as the installed app does and drives it through the API."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); cls.database = Path(cls.folder.name) / "SaberAccounting" / "saber.db"
        cls.database.parent.mkdir(parents=True)
        probe = socket.socket(); probe.bind(("127.0.0.1", 0)); cls.port = probe.getsockname()[1]; probe.close()
        threading.Thread(target=run_server, kwargs={"host": "127.0.0.1", "port": cls.port, "database": str(cls.database), "admin_password": "admin123"}, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.port}"
        for _ in range(100):
            try: ApiClient(cls.url).login("admin", "admin123"); break
            except Exception: time.sleep(0.1)

    @classmethod
    def tearDownClass(cls): cls.folder.cleanup()

    def admin(self):
        api = ApiClient(self.url); api.login("admin", "admin123")
        company = api.companies()[0]; api.select_company_year(company["id"], company["years"][0]["year"]); return api

    def test_full_workflow_permissions_backup_and_restore(self):
        api = self.admin(); year = api.fiscal_year
        employee = api.save_employee({"employee_number": "3000", "full_name": "E2E Employee", "currency": "LBP", "base_salary": "50000000"})
        for month in (1, 2, 3):
            api.post_payroll(api.save_payroll({"employee_id": employee["id"], "period_date": f"28-{month:02d}-{year}"})["id"])
        r10 = api.payroll_report("R10", "quarterly", year, 1, "employee")
        self.assertEqual(r10["record_count"], 3)
        api.create_manual_invoice({"invoice_date": f"10-02-{year}", "party_name": "E2E Client", "kind": "sales", "currency": "LBP", "status": "posted"},
                                  [{"description": "Service", "quantity": 1, "unit_price": 10000000, "vat_rate": 11}])
        self.assertEqual(api.vat_return(year, 1)["payable_lbp"], 1100000)
        api.save_user({"username": "nopay", "password": "nopay123", "role": "accountant", "permissions": {"payroll": False, "vat": True}})
        limited = ApiClient(self.url); session = limited.login("nopay", "nopay123"); limited.select_company_year(api.company_id, year)
        self.assertFalse(session["permissions"]["payroll"]); self.assertEqual(session["expires_at"], (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"))
        with self.assertRaisesRegex(RuntimeError, "permission to use Payroll"): limited.payroll()
        self.assertEqual(limited.vat_return(year, 1)["payable_lbp"], 1100000)
        users = {u["username"]: u for u in api.users()}
        api.save_user({"id": users["nopay"]["id"], "username": "nopay", "role": "accountant", "expires_at": "01-01-2020"})
        with self.assertRaisesRegex(RuntimeError, "expired"): ApiClient(self.url).login("nopay", "nopay123")
        expired_calls = []; limited.on_unauthorized = lambda: expired_calls.append(True)
        with self.assertRaises(RuntimeError): limited.vat_returns()
        self.assertEqual(expired_calls, [True])
        backup = api.create_backup()["path"]
        api.create_manual_invoice({"invoice_date": f"11-02-{year}", "party_name": "After Backup", "kind": "sales", "currency": "LBP", "status": "posted"},
                                  [{"description": "Service", "quantity": 1, "unit_price": 20000000, "vat_rate": 11}])
        self.assertEqual(api.vat_return(year, 1)["payable_lbp"], 3300000)
        result = api.restore_backup(Path(backup).name)
        self.assertTrue(result["safety_backup"])
        self.assertEqual(api.vat_return(year, 1)["payable_lbp"], 1100000)
        self.assertEqual(api.payroll_report("R10", "quarterly", year, 1, "employee")["record_count"], 3)
        bad = Path(backup).parent / "saber_accounting_broken.db"; bad.write_bytes(b"not a database")
        with self.assertRaisesRegex(RuntimeError, "not a valid"): api.restore_backup(bad.name)
        connection = sqlite3.connect(str(self.database))
        try: self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally: connection.close()


if __name__ == "__main__": unittest.main()
