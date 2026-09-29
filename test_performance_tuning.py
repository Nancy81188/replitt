"""Guards the database performance tuning: WAL journalling and the filter /
join indexes. These only speed the app up; they must never disappear or the
large-database slowness returns.
"""
import tempfile
import unittest
from pathlib import Path

from database import Database


REQUIRED_INDEXES = {
    "idx_invoices_party",
    "idx_invoices_kind",
    "idx_invoices_date",
    "idx_invoice_items_invoice",
    "idx_journal_entries_source",
    "idx_journal_lines_entry",
    "idx_journal_lines_account",
    "idx_stock_movements_item",
    "idx_payments_party",
    "idx_payroll_records_employee",
    "idx_audit_log_entity",
}


class PerformanceTuningTests(unittest.TestCase):
    def _fresh_db(self, folder):
        db = Database(Path(folder) / "perf.db")
        db.initialize("secret")
        return db

    def test_expected_indexes_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            db = self._fresh_db(folder)
            with db.connect() as conn:
                names = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    )
                }
            missing = REQUIRED_INDEXES - names
            self.assertFalse(
                missing, f"missing performance indexes: {sorted(missing)}"
            )

    def test_wal_journal_mode_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            db = self._fresh_db(folder)
            with db.connect() as conn:
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

    def test_foreign_keys_still_enforced(self):
        # The tuning must not weaken the existing foreign-key enforcement.
        with tempfile.TemporaryDirectory() as folder:
            db = self._fresh_db(folder)
            with db.connect() as conn:
                enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            self.assertEqual(enabled, 1)

    def test_index_used_for_invoice_lookup(self):
        # The query planner should pick an index (not a full scan) for a
        # typical invoice-by-party lookup once statistics are analysed.
        with tempfile.TemporaryDirectory() as folder:
            db = self._fresh_db(folder)
            with db.connect() as conn:
                plan = conn.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM invoice_items WHERE invoice_id=1"
                ).fetchall()
            plan_text = " ".join(str(tuple(row)) for row in plan).lower()
            self.assertIn("idx_invoice_items_invoice", plan_text)


if __name__ == "__main__":
    unittest.main()
