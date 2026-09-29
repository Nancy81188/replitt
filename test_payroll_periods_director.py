"""Tax & NSSF periods saved as one list (edit Date From / To, split 01-05-2025 - 30-06-2025), director
remuneration (not taxable, own posting account) and the family allocation (manual amount, own account)."""
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from database import Database


class PayrollPeriodsDirectorTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self.folder.name) / "p.db"); self.db.initialize("secret")
        self.user = self.db.user_for_token(self.db.login("admin", "secret")["token"])["id"]
        self.db.apply_lebanese_payroll_rules(self.user)
        self.employee = self.db.save_employee({"employee_number": "1000", "full_name": "Emp", "currency": "LBP", "base_salary": "50000000",
                                               "nssf_number": "1", "mof_number": "1"}, self.user)

    def tearDown(self): self.folder.cleanup()

    def periods(self):
        return [{"original_from": r["date_from"], "date_from": r["date_from"], "date_to": r["date_to"],
                 **{f: r[f] for f in Database.PERIOD_VALUE_FIELDS}} for r in self.db.list_payroll_settings()]

    def test_split_a_period_for_may_june_2025(self):
        rows = self.periods()
        before = next(r for r in rows if r["date_from"] == "2024-11-25")
        before["date_to"] = "2025-04-30"
        rows.append({**{f: before[f] for f in Database.PERIOD_VALUE_FIELDS}, "original_from": None,
                     "date_from": "01-05-2025", "date_to": "30-06-2025", "family_ceiling": "18000000"})
        self.db.save_payroll_periods(rows, self.user)
        may = self.db.payroll_settings_for("15-05-2025"); april = self.db.payroll_settings_for("15-04-2025")
        self.assertEqual((may["date_from"], may["date_to"], Decimal(may["family_ceiling"])), ("2025-05-01", "2025-06-30", Decimal("18000000")))
        self.assertEqual((april["date_to"], Decimal(april["family_ceiling"])), ("2025-04-30", Decimal("12000000")))
        self.assertEqual(may["tax_brackets"], april["tax_brackets"])  # other settings copied from the period it came from
        self.assertEqual(self.db.payroll_settings_for("15-07-2025")["date_from"], "2025-07-01")

    def test_change_date_from_and_date_to_of_an_existing_period(self):
        rows = self.periods()
        july = next(r for r in rows if r["date_from"] == "2025-07-01"); june = next(r for r in rows if r["date_to"] == "2025-06-30")
        july["date_from"] = "01-06-2025"; june["date_to"] = "31-05-2025"
        self.db.save_payroll_periods(rows, self.user)
        self.assertEqual(self.db.payroll_settings_for("15-06-2025")["date_from"], "2025-06-01")
        self.assertFalse([r for r in self.db.list_payroll_settings() if r["date_from"] == "2025-07-01"])

    def test_overlaps_and_gaps_are_refused_and_nothing_is_saved(self):
        rows = self.periods(); count = len(rows)
        next(r for r in rows if r["date_from"] == "2024-11-25")["date_to"] = "2025-08-15"
        with self.assertRaisesRegex(ValueError, "overlaps"): self.db.save_payroll_periods(rows, self.user)
        rows = self.periods(); next(r for r in rows if r["date_from"] == "2024-11-25")["date_to"] = "2025-04-30"
        with self.assertRaisesRegex(ValueError, "Nothing covers 01-05-2025 to 30-06-2025"): self.db.save_payroll_periods(rows, self.user)
        self.assertEqual(len(self.db.list_payroll_settings()), count)

    def test_director_remuneration_is_not_taxed_and_posts_to_its_account(self):
        base = self.db.calculate_payroll({"employee_id": self.employee["id"], "period_date": "31-03-2026"})
        with_director = self.db.calculate_payroll({"employee_id": self.employee["id"], "period_date": "31-03-2026", "director_remuneration": "20000000"})
        self.assertEqual(with_director["income_tax"], base["income_tax"])
        self.assertEqual(with_director["employee_nssf"], base["employee_nssf"])
        self.assertEqual(with_director["gross_salary"], base["gross_salary"] + 20000000)
        self.assertEqual(with_director["net_salary"], base["net_salary"] + 20000000)
        saved = self.db.save_payroll({"employee_id": self.employee["id"], "period_date": "31-03-2026", "director_remuneration": "20000000"}, self.user)
        posted = self.db.post_payroll(saved["id"], self.user)
        with self.db.connect() as db:
            lines = db.execute("SELECT a.code,j.debit,j.credit FROM journal_lines j JOIN accounts a ON a.id=j.account_id WHERE j.entry_id=?", (posted["journal_entry_id"],)).fetchall()
        self.assertIn(("6316", Decimal("20000000"), Decimal("0")), [(r["code"], Decimal(r["debit"]), Decimal(r["credit"])) for r in lines])
        self.assertAlmostEqual(sum(float(r["debit"]) for r in lines), sum(float(r["credit"]) for r in lines), places=2)

    def test_family_allocation_manual_amount_and_own_account(self):
        calc = self.db.calculate_payroll({"employee_id": self.employee["id"], "period_date": "31-05-2026", "family_allowance_override": "1500000"})
        self.assertEqual(calc["family_allowance"], 1500000.0)
        settings = self.db.payroll_settings_for("31-05-2026")
        mapping = {**settings["employee_account_map"], "family_allowance": "4432"}
        self.db.save_payroll_settings({**settings, "date_from": "01-05-2026", "date_to": "", "employee_account_map": mapping}, self.user)
        saved = self.db.save_payroll({"employee_id": self.employee["id"], "period_date": "31-05-2026", "family_allowance_override": "1500000"}, self.user)
        posted = self.db.post_payroll(saved["id"], self.user)
        with self.db.connect() as db:
            lines = {r["code"]: (Decimal(r["debit"]), Decimal(r["credit"])) for r in db.execute(
                "SELECT a.code,j.debit,j.credit FROM journal_lines j JOIN accounts a ON a.id=j.account_id WHERE j.entry_id=?", (posted["journal_entry_id"],))}
        self.assertEqual(lines["4432"], (Decimal("1500000"), Decimal("0")))


if __name__ == "__main__":
    unittest.main()
