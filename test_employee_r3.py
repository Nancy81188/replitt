"""Employee registration fields must survive edits and upgrades of company files."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from database import Database
from payroll_reports import build_nssf_statement, build_nssf_settlement, nssf_declaration_period


class EmployeeRegistrationTest(unittest.TestCase):
    def test_nssf_declaration_frequency_counts_roster_at_selected_month(self):
        employees = [{"hire_date": "2026-01-01", "leave_date": None, "active": 1} for _ in range(9)]
        self.assertEqual(nssf_declaration_period(employees, 2026, 4), ("quarterly", 2, 9))
        employees.append({"hire_date": "2026-05-01", "leave_date": None, "active": 1})
        self.assertEqual(nssf_declaration_period(employees, 2026, 4), ("quarterly", 2, 9))
        self.assertEqual(nssf_declaration_period(employees, 2026, 5), ("monthly", 5, 10))
        employees[-1]["leave_date"] = "2026-05-31"
        self.assertEqual(nssf_declaration_period(employees, 2026, 6), ("quarterly", 2, 9))

    def test_nssf_2026_ceiling_change_and_manual_sickness_override(self):
        with TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            with db.connect() as connection:
                user_id = connection.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            db.apply_lebanese_payroll_rules(user_id)
            april = db.payroll_settings_for("2026-04-30")
            may = db.payroll_settings_for("2026-05-31")
            self.assertEqual((april["family_ceiling"], may["family_ceiling"]), ("18000000", "28000000"))
            override = {**may, "date_from": "01-05-2026", "medical_ceiling": "130000000"}
            db.save_payroll_settings(override, user_id)
            self.assertEqual(db.payroll_settings_for("2026-04-30")["medical_ceiling"], april["medical_ceiling"])
            self.assertEqual(db.payroll_settings_for("2026-05-31")["medical_ceiling"], "130000000")
            self.assertEqual(db.payroll_settings_for("2026-05-31")["family_ceiling"], "28000000")
            employee = db.save_employee({"full_name": "Nour Test", "currency": "LBP", "base_salary": "150000000"}, user_id)
            april_pay = db.calculate_payroll({"employee_id": employee["id"], "period_date": "30-04-2026"})
            may_pay = db.calculate_payroll({"employee_id": employee["id"], "period_date": "31-05-2026"})
            self.assertEqual(april_pay["employer_medical"], 9600000)
            self.assertEqual(may_pay["employer_medical"], 10400000)
            self.assertEqual((april_pay["employer_family"], may_pay["employer_family"]), (1080000, 1680000))

    def test_registration_fields_are_saved_and_preserved_on_edit(self):
        with TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            with db.connect() as connection:
                user_id = connection.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            employee = db.save_employee({"full_name": "Maya Haddad", "nationality": "Lebanese",
                "father_name": "Joseph", "mother_name": "Lina", "birth_date": "15-06-1992",
                "birth_place": "Jounieh"}, user_id)
            self.assertEqual(employee["birth_date"], "1992-06-15")
            updated = db.save_employee({**employee, "nationality": "French"}, user_id)
            self.assertEqual(updated["nationality"], "French")
            self.assertEqual(updated["mother_name"], "Lina")
            db.initialize("secret12345")
            self.assertEqual(db.list_employees()[0]["birth_place"], "Jounieh")
            with self.assertRaisesRegex(ValueError, "Leaving date cannot be before starting date"):
                db.save_employee({"full_name":"Invalid dates", "hire_date":"01-05-2026", "leave_date":"30-04-2026"}, user_id)

    def test_nssf_roster_counts_employees_without_payroll(self):
        with TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            with db.connect() as connection:
                user_id = connection.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            for number in ("100000001", "100000002"):
                db.save_employee({"employee_number": number, "full_name": "Same Name",
                                  "hire_date": "01-01-2025"}, user_id)
            db.save_employee({"employee_number": "100000003", "full_name": "New Hire",
                              "hire_date": "01-01-2026"}, user_id)
            report = build_nssf_statement(db, "yearly", 2025)
            self.assertEqual(report["employee_count"], 2)
            self.assertEqual(report["payroll_employee_count"], 0)
            self.assertEqual(len(report["sections"][1]["rows"]), 2)
            automatic = build_nssf_statement(db, "auto", 2025, 5)
            self.assertEqual((automatic["declaration_period"], automatic["date_from"], automatic["date_to"]),
                             ("quarterly", "2025-04-01", "2025-06-30"))

    def test_nssf_settlement_requires_filed_months_and_reconciles_saved_wages(self):
        with TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            db.initialize("secret12345")
            with db.connect() as connection:
                user_id = connection.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            employee = db.save_employee({"full_name": "Nadia Ali", "base_salary": "20000000"}, user_id)
            payroll = db.save_payroll({"employee_id": employee["id"], "period_date": "31-01-2025"}, user_id)
            db.post_payroll(payroll["id"], user_id)
            self.assertFalse(build_nssf_settlement(db, 2025)["complete"])
            for month in range(1, 13):
                db.save_nssf_filed_wages({"year": 2025, "month": month, "sickness_wages": "0",
                    "family_wages": "0", "end_service_wages": "0", "amount_paid": "0"}, user_id)
            report = build_nssf_settlement(db, 2025)
            self.assertTrue(report["complete"])
            self.assertGreater(report["sections"][0]["rows"][0][7], 0)
            self.assertEqual(report["sections"][2]["rows"][2][1], report["sections"][2]["rows"][0][1])


if __name__ == "__main__":
    unittest.main()
