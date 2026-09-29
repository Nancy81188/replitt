"""Regression checks for monetary reports: incomplete conversion data must not look like zero."""
import secrets
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from business_reports import dashboard_charts
from database import Database
from ledger_reports import _load_lines


class _Connection:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, _parameters):
        return [self.row]


class _ReportDatabase:
    def __init__(self, row):
        self.row = row

    def connect(self):
        return _Connection(self.row)

    def _converted_amount(self, _amount, _from, _to, _day):
        raise ValueError("No historical exchange rate")


class ReportAccuracyTests(unittest.TestCase):
    def _row(self, **changes):
        row = {
            "code": "4111", "name_en": "Customer", "entry_number": "JV-1",
            "entry_date": "01-01-2025", "currency": "EUR", "debit": 100,
            "credit": 0, "line_currency": None, "amount": None,
            "amount_lbp": None, "amount_usd": None, "due_date": None,
            "invoice_due_date": None, "reference": None, "invoice_number": None,
        }
        row.update(changes)
        return row

    def test_missing_rate_cannot_make_converted_trial_balance_zero(self):
        db = _ReportDatabase(self._row())
        with self.assertRaisesRegex(ValueError, "Missing LBP equivalent or exchange rate for entry JV-1"):
            _load_lines(db, {"first_column": "LBP", "second_column": "none"})

        account_only = _load_lines(db, {"first_column": "account", "second_column": "none"})
        self.assertEqual(account_only[0]["signed"]["account"], Decimal("100"))
        self.assertIsNone(account_only[0]["signed"]["LBP"])

    def test_missing_stored_equivalent_cannot_make_ledger_zero(self):
        db = _ReportDatabase(self._row(line_currency="EUR", amount="100", amount_usd="110"))
        with self.assertRaisesRegex(ValueError, "Missing LBP equivalent or exchange rate for entry JV-1"):
            _load_lines(db, {"first_column": "LBP", "second_column": "none"})

    def test_account_currency_amount_is_usable_when_its_duplicate_equivalent_is_null(self):
        db = _ReportDatabase(self._row(currency="LBP", line_currency="LBP", amount="100"))
        lines = _load_lines(db, {"first_column": "LBP", "second_column": "none"})
        self.assertEqual(lines[0]["signed"]["LBP"], Decimal("100"))

    def test_cash_dashboard_uses_only_its_selected_currency(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "company.db")
            password = secrets.token_hex(16)
            db.initialize(password)
            user = db.user_for_token(db.login("admin", password)["token"])["id"]
            party = db.save_party({"kind": "customer", "name": "Cash Client"}, user)
            db.save_currency("GBP", "British Pound", user)
            db.save_exchange_rate({"date_from": "01-01-2026", "from_currency": "USD",
                                   "to_currency": "GBP", "rate": "0.8"}, user)
            db.add_payment({"kind": "customer_receipt", "payment_date": "10-01-2026",
                            "party_id": party["id"], "currency": "USD", "amount": 100,
                            "cash_account": "531"}, user)
            convert = db._converted_amount

            def no_lbp(amount, source, target, day):
                if target == "LBP":
                    raise ValueError("No LBP rate available")
                return convert(amount, source, target, day)

            with patch.object(db, "_converted_amount", side_effect=no_lbp):
                usd = dashboard_charts(db, {"basis": "USD", "year": 2026, "as_of": "11-01-2026"})
                gbp = dashboard_charts(db, {"basis": "GBP", "year": 2026, "as_of": "11-01-2026"})
            self.assertIn(["531", 100.0], usd["cash"])
            self.assertIn(["531", 80.0], gbp["cash"])


if __name__ == "__main__":
    unittest.main()