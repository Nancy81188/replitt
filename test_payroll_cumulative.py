"""Cumulative withholding and the annual schooling tax exemption."""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from database import Database


class CumulativePayrollTest(unittest.TestCase):
    def test_variable_pay_uses_prior_withholding(self):
        with TemporaryDirectory() as folder:
            db=Database(Path(folder)/"company.db"); db.initialize("secret12345")
            with db.connect() as c: user=c.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            db.apply_lebanese_payroll_rules(user)
            rules=db.payroll_settings_for("2026-06-30")
            db.save_payroll_settings({**rules,"tax_rounding":"0"},user)
            employee=db.save_employee({"full_name":"Variable pay","base_salary":"120000000",
                "currency":"LBP","hire_date":"01-01-2026"},user)
            first=db.save_payroll({"employee_id":employee["id"],"period_date":"31-05-2026"},user)
            second=db.calculate_payroll({"employee_id":employee["id"],"period_date":"30-06-2026",
                "salary":"200000000"})
            elapsed=Decimal(2)/12
            brackets=[[Decimal(str(ceiling))*elapsed if ceiling is not None else None,rate]
                      for ceiling,rate in rules["tax_brackets"]]
            expected=db._progressive_tax(Decimal(320000000)-Decimal(rules["single_allowance"])*elapsed,brackets)
            self.assertAlmostEqual(second["income_tax_lbp"],float(expected)-float(first["income_tax_lbp"]),delta=0.02)

    def test_schooling_exemption_is_annual_remaining_balance(self):
        with TemporaryDirectory() as folder:
            db=Database(Path(folder)/"company.db"); db.initialize("secret12345")
            with db.connect() as c: user=c.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            db.apply_lebanese_payroll_rules(user)
            employee=db.save_employee({"full_name":"Parent","base_salary":"50000000","children":1,
                "currency":"LBP"},user)
            first=db.save_payroll({"employee_id":employee["id"],"period_date":"31-01-2026",
                "schooling":"5000000"},user)
            second=db.calculate_payroll({"employee_id":employee["id"],"period_date":"28-02-2026",
                "schooling":"5000000"})
            self.assertEqual(float(first["exempt_schooling"]),5000000)
            self.assertEqual(second["exempt_schooling"],1000000)


if __name__=="__main__":
    unittest.main()
