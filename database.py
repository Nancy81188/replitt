from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import os
import sqlite3
import tempfile
import threading
import urllib.request
from contextlib import closing, contextmanager
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

from lebanese_accounts import DEFAULT_LEBANESE_ACCOUNTS, LEBANESE_ACCOUNTS

EXPENSE_ACCOUNT_9 = "601100000"
VAT_ACCOUNT_9 = "44210"  # VAT on purchases (was 442660000)
EXPENSE_NO_VAT_ACCOUNT_9 = "601100001"
SESSION_HOURS = 24
USER_VALIDITY_DAYS = 365
PERMISSION_MODULES = ("payroll", "vat")

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','accountant','viewer')), language TEXT NOT NULL DEFAULT 'en', active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts (
 key TEXT PRIMARY KEY, failed_count INTEGER NOT NULL, first_failed_at TEXT NOT NULL, locked_until TEXT
);
CREATE TABLE IF NOT EXISTS parties (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('customer','supplier','both')),
 name TEXT NOT NULL, tax_number TEXT, mof_number TEXT, address TEXT, contact_number TEXT,
 currency TEXT NOT NULL DEFAULT 'USD', account_number TEXT, account_category TEXT, due_days INTEGER NOT NULL DEFAULT 0, UNIQUE(kind,name)
);
CREATE TABLE IF NOT EXISTS branches (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS accounts (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name_en TEXT NOT NULL, name_ar TEXT, name_fr TEXT,
 type TEXT NOT NULL CHECK(type IN ('asset','liability','equity','income','expense')), parent_id INTEGER REFERENCES accounts(id), active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS invoices (
 id INTEGER PRIMARY KEY, invoice_number TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('sale','purchase')),
 invoice_date TEXT, party_id INTEGER REFERENCES parties(id), currency TEXT NOT NULL, exchange_rate TEXT NOT NULL DEFAULT '1',
 subtotal TEXT, vat TEXT, total TEXT, status TEXT NOT NULL DEFAULT 'posted', currency_issue TEXT NOT NULL DEFAULT '',
 deductible_subtotal TEXT NOT NULL DEFAULT '0', non_deductible_subtotal TEXT NOT NULL DEFAULT '0',
 supplier_account TEXT NOT NULL DEFAULT '4011', vat_account TEXT NOT NULL DEFAULT '442660000', expense_account TEXT NOT NULL DEFAULT '601100000',
 entry_type TEXT NOT NULL DEFAULT 'purchase', debit_override TEXT, credit_override TEXT,
 supplier_side TEXT NOT NULL DEFAULT 'C', vat_side TEXT NOT NULL DEFAULT 'D', expense_side TEXT NOT NULL DEFAULT 'D',
 expense_no_vat_account TEXT NOT NULL DEFAULT '601100001', expense_no_vat_side TEXT NOT NULL DEFAULT 'D',
 source_file TEXT, source_row INTEGER, due_date TEXT, payment_status TEXT NOT NULL DEFAULT 'unpaid',
 amount_paid TEXT NOT NULL DEFAULT '0', payment_method TEXT, description TEXT, branch_id INTEGER REFERENCES branches(id), cancelled_at TEXT, cancellation_reason TEXT,
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoice_items (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
 description TEXT NOT NULL, quantity TEXT NOT NULL, unit_price TEXT NOT NULL,
 subtotal TEXT NOT NULL, deductible_subtotal TEXT NOT NULL DEFAULT '0', non_deductible_subtotal TEXT NOT NULL DEFAULT '0',
 vat_rate TEXT NOT NULL, vat TEXT NOT NULL, total TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoice_attachments (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
 file_name TEXT NOT NULL, mime_type TEXT NOT NULL, content BLOB NOT NULL,
 uploaded_by INTEGER REFERENCES users(id), uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS party_documents (
 id INTEGER PRIMARY KEY, party_id INTEGER NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
 document_type TEXT NOT NULL, issue_date TEXT, expiry_date TEXT, notes TEXT,
 file_name TEXT NOT NULL, mime_type TEXT NOT NULL, content BLOB NOT NULL,
 uploaded_by INTEGER REFERENCES users(id), uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_cases (
 id INTEGER PRIMARY KEY, case_number TEXT NOT NULL UNIQUE,
 case_type TEXT NOT NULL CHECK(case_type IN ('purchase','expense','customs')),
 document_date TEXT NOT NULL, party_id INTEGER REFERENCES parties(id), currency TEXT NOT NULL DEFAULT 'USD',
 reference TEXT, description TEXT, customs_declaration_no TEXT, broker_name TEXT,
 supplier_invoice_amount TEXT NOT NULL DEFAULT '0', freight TEXT NOT NULL DEFAULT '0', insurance TEXT NOT NULL DEFAULT '0',
 customs_duties TEXT NOT NULL DEFAULT '0', import_vat TEXT NOT NULL DEFAULT '0', broker_fees TEXT NOT NULL DEFAULT '0',
 total TEXT NOT NULL DEFAULT '0', status TEXT NOT NULL DEFAULT 'draft', invoice_id INTEGER REFERENCES invoices(id),
 supplier_account TEXT, expense_account TEXT, vat_account TEXT, branch_id INTEGER REFERENCES branches(id),
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_attachments (
 id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES document_cases(id) ON DELETE CASCADE,
 document_role TEXT NOT NULL, file_name TEXT NOT NULL, mime_type TEXT NOT NULL, content BLOB NOT NULL,
 uploaded_by INTEGER REFERENCES users(id), uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal_entries (
 id INTEGER PRIMARY KEY, entry_number TEXT NOT NULL UNIQUE, entry_date TEXT, description TEXT, source_type TEXT,
 source_id INTEGER, currency TEXT NOT NULL, branch_id INTEGER REFERENCES branches(id), created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal_lines (
 id INTEGER PRIMARY KEY, entry_id INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
 account_id INTEGER NOT NULL REFERENCES accounts(id), party_id INTEGER REFERENCES parties(id), description TEXT, debit TEXT NOT NULL DEFAULT '0', credit TEXT NOT NULL DEFAULT '0'
);
CREATE TABLE IF NOT EXISTS inventory_items (
 id INTEGER PRIMARY KEY, sku TEXT NOT NULL UNIQUE, name TEXT NOT NULL, unit TEXT NOT NULL DEFAULT 'unit', quantity TEXT NOT NULL DEFAULT '0', average_cost TEXT NOT NULL DEFAULT '0'
);
CREATE TABLE IF NOT EXISTS stock_movements (
 id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES inventory_items(id), movement_date TEXT NOT NULL,
 quantity TEXT NOT NULL, unit_cost TEXT NOT NULL, source_type TEXT, source_id INTEGER
);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), action TEXT NOT NULL, entity TEXT NOT NULL,
 entity_id INTEGER, details TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fiscal_years (
 id INTEGER PRIMARY KEY, year INTEGER NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'open',
 opened_at TEXT NOT NULL, closed_at TEXT, closed_by INTEGER REFERENCES users(id), details TEXT
);
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('customer_receipt','supplier_payment')),
 party_id INTEGER NOT NULL REFERENCES parties(id), payment_date TEXT NOT NULL, currency TEXT NOT NULL,
 amount TEXT NOT NULL, cash_account TEXT NOT NULL, party_account TEXT NOT NULL,
 reference TEXT, description TEXT, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS expenses (
 id INTEGER PRIMARY KEY, expense_date TEXT NOT NULL, description TEXT NOT NULL, category TEXT,
 currency TEXT NOT NULL, subtotal TEXT NOT NULL, vat TEXT NOT NULL, total TEXT NOT NULL,
 with_vat_subtotal TEXT NOT NULL DEFAULT '0', without_vat_subtotal TEXT NOT NULL DEFAULT '0',
 expense_account TEXT NOT NULL, expense_without_vat_account TEXT NOT NULL DEFAULT '601100001', vat_account TEXT NOT NULL, payment_account TEXT NOT NULL,
 expense_side TEXT NOT NULL DEFAULT 'D', expense_without_vat_side TEXT NOT NULL DEFAULT 'D',
 vat_side TEXT NOT NULL DEFAULT 'D', payment_side TEXT NOT NULL DEFAULT 'C',
 reference TEXT, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exchange_rates (
 id INTEGER PRIMARY KEY, rate_date TEXT NOT NULL, from_currency TEXT NOT NULL, to_currency TEXT NOT NULL,
 rate TEXT NOT NULL, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL,
 UNIQUE(rate_date,from_currency,to_currency)
);
CREATE TABLE IF NOT EXISTS exchange_rate_samples (
 id INTEGER PRIMARY KEY, rate_date TEXT NOT NULL, from_currency TEXT NOT NULL, to_currency TEXT NOT NULL,
 rate TEXT NOT NULL, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS currencies (
 code TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS employees (
 id INTEGER PRIMARY KEY, employee_number TEXT NOT NULL UNIQUE, full_name TEXT NOT NULL,
 national_id TEXT, mof_number TEXT, nssf_number TEXT, address TEXT, contact_number TEXT,
 nationality TEXT, father_name TEXT, mother_name TEXT, birth_date TEXT, birth_place TEXT,
 marital_status TEXT NOT NULL DEFAULT 'single', spouse_works INTEGER NOT NULL DEFAULT 0, children INTEGER NOT NULL DEFAULT 0, employee_group TEXT NOT NULL DEFAULT 'employee',
 hire_date TEXT, leave_date TEXT, job_title TEXT, branch_id INTEGER REFERENCES branches(id),
 currency TEXT NOT NULL DEFAULT 'LBP', base_salary TEXT NOT NULL DEFAULT '0',
 salary_account TEXT, payable_account TEXT, active INTEGER NOT NULL DEFAULT 1,
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nssf_filed_wages (
 year INTEGER NOT NULL, month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
 sickness_wages TEXT, family_wages TEXT, end_service_wages TEXT, amount_paid TEXT,
 note TEXT, updated_by INTEGER REFERENCES users(id), updated_at TEXT NOT NULL,
 PRIMARY KEY(year,month)
);
CREATE TABLE IF NOT EXISTS payroll_settings (
 id INTEGER PRIMARY KEY, date_from TEXT NOT NULL, date_to TEXT,
 tax_brackets TEXT NOT NULL, single_allowance TEXT NOT NULL DEFAULT '450000000',
 spouse_allowance TEXT NOT NULL DEFAULT '225000000', child_allowance TEXT NOT NULL DEFAULT '45000000',
 employee_nssf_rate TEXT NOT NULL DEFAULT '0.03', medical_rate TEXT NOT NULL DEFAULT '0.11',
 end_service_rate TEXT NOT NULL DEFAULT '0.085', family_rate TEXT NOT NULL DEFAULT '0.06',
 employee_ceiling TEXT NOT NULL DEFAULT '0', medical_ceiling TEXT NOT NULL DEFAULT '0',
 family_ceiling TEXT NOT NULL DEFAULT '0', end_service_ceiling TEXT NOT NULL DEFAULT '0',
 salary_account TEXT NOT NULL DEFAULT '621100001', salary_payable_account TEXT NOT NULL DEFAULT '421100001',
 payroll_tax_account TEXT NOT NULL DEFAULT '443100001', nssf_payable_account TEXT NOT NULL DEFAULT '447100001',
 employee_account_map TEXT NOT NULL DEFAULT '{}', manager_account_map TEXT NOT NULL DEFAULT '{}',
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL,
 UNIQUE(date_from)
);
CREATE TABLE IF NOT EXISTS payroll_records (
 id INTEGER PRIMARY KEY, payroll_number TEXT NOT NULL UNIQUE, employee_id INTEGER NOT NULL REFERENCES employees(id),
 period_date TEXT NOT NULL, currency TEXT NOT NULL, salary TEXT NOT NULL DEFAULT '0',
 transport TEXT NOT NULL DEFAULT '0', overtime TEXT NOT NULL DEFAULT '0', commission TEXT NOT NULL DEFAULT '0', retro_salary TEXT NOT NULL DEFAULT '0', retro_from TEXT, retro_to TEXT,
 schooling TEXT NOT NULL DEFAULT '0', bonus TEXT NOT NULL DEFAULT '0', thirteenth_month TEXT NOT NULL DEFAULT '0',
 gross_salary TEXT NOT NULL DEFAULT '0', taxable_salary TEXT NOT NULL DEFAULT '0', income_tax TEXT NOT NULL DEFAULT '0', income_tax_lbp TEXT NOT NULL DEFAULT '0',
 nssf_base TEXT NOT NULL DEFAULT '0', employee_nssf TEXT NOT NULL DEFAULT '0', employer_medical TEXT NOT NULL DEFAULT '0',
 employer_end_service TEXT NOT NULL DEFAULT '0', employer_family TEXT NOT NULL DEFAULT '0', net_salary TEXT NOT NULL DEFAULT '0',
 reference TEXT, notes TEXT, status TEXT NOT NULL DEFAULT 'draft', journal_entry_id INTEGER REFERENCES journal_entries(id),
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL, UNIQUE(employee_id,period_date)
);
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS expense_attachments (
 id INTEGER PRIMARY KEY, expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
 file_name TEXT NOT NULL, mime_type TEXT NOT NULL, content BLOB NOT NULL, uploaded_by INTEGER, uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vat_settings (
 year INTEGER PRIMARY KEY, provisional_ratio TEXT, updated_by INTEGER, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS departments (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT
);
CREATE TABLE IF NOT EXISTS projects (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, party_id INTEGER REFERENCES parties(id),
 start_date TEXT, end_date TEXT, status TEXT NOT NULL DEFAULT 'open', notes TEXT, active INTEGER NOT NULL DEFAULT 1, created_at TEXT
);
CREATE TABLE IF NOT EXISTS budgets (
 id INTEGER PRIMARY KEY, year INTEGER NOT NULL, currency TEXT NOT NULL, account_code TEXT NOT NULL,
 department_id INTEGER NOT NULL DEFAULT 0, project_id INTEGER NOT NULL DEFAULT 0, month INTEGER NOT NULL DEFAULT 0 CHECK(month BETWEEN 0 AND 12),
 amount TEXT NOT NULL, updated_by INTEGER, updated_at TEXT,
 UNIQUE(year,currency,account_code,department_id,project_id,month)
);
CREATE TABLE IF NOT EXISTS vat_adjustments (
 id INTEGER PRIMARY KEY, year INTEGER NOT NULL, quarter INTEGER NOT NULL CHECK(quarter BETWEEN 1 AND 4),
 currency TEXT NOT NULL, adjustment_type TEXT NOT NULL CHECK(adjustment_type IN ('output','input','non_deductible')),
 amount TEXT NOT NULL, reason TEXT NOT NULL, created_by INTEGER, created_by_name TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vat_returns (
 id INTEGER PRIMARY KEY, year INTEGER NOT NULL, quarter INTEGER NOT NULL CHECK(quarter BETWEEN 1 AND 4),
 net_lbp TEXT NOT NULL, credit_brought_forward_lbp TEXT NOT NULL DEFAULT '0', payable_lbp TEXT NOT NULL DEFAULT '0',
 credit_carried_forward_lbp TEXT NOT NULL DEFAULT '0', snapshot TEXT NOT NULL,
 saved_by INTEGER, saved_by_name TEXT, saved_at TEXT NOT NULL, UNIQUE(year,quarter)
);
"""

LEGACY_ACCOUNT_MAP = {
    "1100": DEFAULT_LEBANESE_ACCOUNTS["accounts_receivable"],
    "2100": DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"],
    "2200": DEFAULT_LEBANESE_ACCOUNTS["vat_payable"],
    "1300": DEFAULT_LEBANESE_ACCOUNTS["vat_receivable"],
    "4100": DEFAULT_LEBANESE_ACCOUNTS["sales"],
    "5100": DEFAULT_LEBANESE_ACCOUNTS["purchases"],
    "9999": DEFAULT_LEBANESE_ACCOUNTS["import_variance"],
}
def utcnow():
    return datetime.now(timezone.utc).isoformat()

def parse_ts(value):
    """Parse a stored ISO timestamp into an aware UTC datetime.
    Timestamps without an explicit offset are assumed to be UTC. Returns None if unparseable.
    Comparing timestamps as datetimes (not as text) avoids the timezone-offset bug where
    two ISO strings with different offsets sort incorrectly as plain strings."""
    if value in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def iso_date(value, field="Date"):
    """Accept DD-MM-YYYY, DDMMYYYY, YYYY-MM-DD or YYYYMMDD and return YYYY-MM-DD."""
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d%m%Y", "%Y%m%d", "%d/%m/%Y"):
        try: return datetime.strptime(text, pattern).strftime("%Y-%m-%d")
        except ValueError: pass
    raise ValueError(f"{field} must use DD-MM-YYYY")

def display_date(value):
    try: return datetime.strptime(iso_date(value), "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError: return str(value or "")

def parse_permissions(value):
    try: data = json.loads(value or "{}") if isinstance(value, str) else dict(value or {})
    except (TypeError, ValueError): data = {}
    return {module: bool(data.get(module, True)) for module in PERMISSION_MODULES}

def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{digest.hex()}"

def verify_password(password, encoded):
    salt_hex, digest_hex = encoded.split(":", 1)
    candidate = hash_password(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
    return hmac.compare_digest(candidate, digest_hex)

class Database:
    _locks = {}
    _locks_guard = threading.Lock()

    def __init__(self, path, pooled=False):
        self.path = str(Path(path))
        self._transaction = threading.local()
        # pooled=True (used by the running data service) keeps ONE open SQLite connection for this
        # file and reuses it for every request instead of opening, configuring and closing a new
        # connection each time. All access is already serialised by the per-file lock below, so
        # the results are identical; only the per-request overhead disappears.
        self.pooled = pooled; self._pooled_connection = None; self._pooled_identity = None
        with self._locks_guard:
            self._lock = self._locks.setdefault(str(Path(path).resolve()), threading.RLock())

    def _file_identity(self):
        try:
            info = os.stat(self.path); return (info.st_dev, info.st_ino)
        except OSError:
            return None

    def _open_connection(self):
        connection = sqlite3.connect(self.path, check_same_thread=not self.pooled)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        # Performance PRAGMAs: WAL keeps reads fast while writing, NORMAL
        # sync is safe under WAL, and a larger page cache / memory temp
        # store cut disk churn. These only speed things up; the data and
        # every existing behaviour are unchanged.
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("PRAGMA cache_size=-16000")  # ~16 MB page cache
        return connection

    def release(self):
        """Close the kept-open connection (before the file is moved, deleted or replaced)."""
        with self._lock:
            connection, self._pooled_connection, self._pooled_identity = self._pooled_connection, None, None
            if connection is not None:
                try: connection.close()
                except Exception: pass

    @contextmanager
    def connect(self):
        with self._lock:
            active = getattr(self._transaction, "connection", None)
            if active is not None:
                yield active
                return
            if self.pooled:
                identity = self._file_identity()
                if self._pooled_connection is not None and (identity is None or identity != self._pooled_identity):
                    self.release()  # the file was replaced or removed: never keep using a stale handle
                if self._pooled_connection is None:
                    self._pooled_connection = self._open_connection(); self._pooled_identity = self._file_identity()
                connection = self._pooled_connection
            else:
                connection = self._open_connection()
            self._transaction.connection = connection
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                self._transaction.connection = None
                if not self.pooled: connection.close()

    # Bump whenever initialize(), SCHEMA, seed accounts or its migration helpers change.
    STARTUP_SCHEMA_VERSION = "1"

    @staticmethod
    def _startup_schema_signature(db):
        # Metadata only: no invoice, journal or other business rows are scanned.
        rows = db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
        return hashlib.sha256(json.dumps([tuple(row) for row in rows]).encode("utf-8")).hexdigest()

    def initialize_if_needed(self, admin_password):
        """Prepare a file once per schema revision, including restored older files.

        The marker lives in the database, not process memory. Failed migrations never
        stamp it. Explicit initialize() remains available for full repair/reseeding.
        """
        with self._lock:
            with self.connect() as db:
                table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_settings'").fetchone()
                version = db.execute("SELECT value FROM app_settings WHERE key='startup_schema_version'").fetchone() if table else None
                signature = db.execute("SELECT value FROM app_settings WHERE key='startup_schema_signature'").fetchone() if table else None
                current = self._startup_schema_signature(db) if signature else None
            if version and version["value"] == self.STARTUP_SCHEMA_VERSION and signature and signature["value"] == current:
                return
            self.initialize(admin_password)

    def initialize(self, admin_password):
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.executemany("INSERT OR IGNORE INTO currencies(code,name) VALUES(?,?)",
                           (("USD","US Dollar"),("LBP","Lebanese Pound"),("EUR","Euro"),("AED","UAE Dirham")))
            invoice_columns = {row["name"] for row in db.execute("PRAGMA table_info(invoices)")}
            if "currency_issue" not in invoice_columns:
                db.execute("ALTER TABLE invoices ADD COLUMN currency_issue TEXT NOT NULL DEFAULT ''")
            account_columns = {
                "supplier_account": DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"],
                "vat_account": DEFAULT_LEBANESE_ACCOUNTS["vat_receivable"],
                "expense_account": DEFAULT_LEBANESE_ACCOUNTS["purchases"],
            }
            for column, default_code in account_columns.items():
                if column not in invoice_columns:
                    db.execute(
                        f"ALTER TABLE invoices ADD COLUMN {column} "
                        f"TEXT NOT NULL DEFAULT '{default_code}'"
                    )
            lifecycle_columns = {
                "due_date": "TEXT",
                "payment_status": "TEXT NOT NULL DEFAULT 'unpaid'",
                "amount_paid": "TEXT NOT NULL DEFAULT '0'",
                "payment_method": "TEXT",
                "cancelled_at": "TEXT",
                "cancellation_reason": "TEXT",
                "entry_type": "TEXT NOT NULL DEFAULT 'purchase'",
                "debit_override": "TEXT",
                "credit_override": "TEXT",
                "supplier_side": "TEXT NOT NULL DEFAULT 'C'",
                "vat_side": "TEXT NOT NULL DEFAULT 'D'",
                "expense_side": "TEXT NOT NULL DEFAULT 'D'",
                "expense_no_vat_account": "TEXT NOT NULL DEFAULT '601100001'",
                "expense_no_vat_side": "TEXT NOT NULL DEFAULT 'D'",
                "deductible_subtotal": "TEXT NOT NULL DEFAULT '0'",
                "non_deductible_subtotal": "TEXT NOT NULL DEFAULT '0'",
                "description": "TEXT",
                "branch_id": "INTEGER REFERENCES branches(id)",
            }
            for column, definition in lifecycle_columns.items():
                if column not in invoice_columns:
                    db.execute(f"ALTER TABLE invoices ADD COLUMN {column} {definition}")
            item_columns={row["name"] for row in db.execute("PRAGMA table_info(invoice_items)")}
            if "item_code" not in item_columns: db.execute("ALTER TABLE invoice_items ADD COLUMN item_code TEXT")
            for column in ("deductible_subtotal","non_deductible_subtotal"):
                if column not in item_columns: db.execute(f"ALTER TABLE invoice_items ADD COLUMN {column} TEXT NOT NULL DEFAULT '0'")
            journal_line_columns={row["name"] for row in db.execute("PRAGMA table_info(journal_lines)")}
            if "description" not in journal_line_columns: db.execute("ALTER TABLE journal_lines ADD COLUMN description TEXT")
            journal_columns={row["name"] for row in db.execute("PRAGMA table_info(journal_entries)")}
            if "branch_id" not in journal_columns: db.execute("ALTER TABLE journal_entries ADD COLUMN branch_id INTEGER REFERENCES branches(id)")
            db.execute("INSERT OR IGNORE INTO branches(name) VALUES('Head Office')")
            db.execute("UPDATE invoices SET branch_id=(SELECT id FROM branches WHERE name='Head Office') WHERE branch_id IS NULL")
            db.execute("UPDATE journal_entries SET branch_id=(SELECT id FROM branches WHERE name='Head Office') WHERE branch_id IS NULL")
            db.execute("UPDATE invoices SET deductible_subtotal=subtotal WHERE CAST(deductible_subtotal AS REAL)=0 AND CAST(non_deductible_subtotal AS REAL)=0 AND CAST(subtotal AS REAL)<>0")
            db.execute("UPDATE invoice_items SET deductible_subtotal=subtotal WHERE CAST(deductible_subtotal AS REAL)=0 AND CAST(non_deductible_subtotal AS REAL)=0 AND CAST(subtotal AS REAL)<>0")
            expense_columns={row["name"] for row in db.execute("PRAGMA table_info(expenses)")}
            for column,definition in (("with_vat_subtotal","TEXT NOT NULL DEFAULT '0'"),("without_vat_subtotal","TEXT NOT NULL DEFAULT '0'"),("expense_without_vat_account","TEXT NOT NULL DEFAULT '601100001'"),("expense_side","TEXT NOT NULL DEFAULT 'D'"),("expense_without_vat_side","TEXT NOT NULL DEFAULT 'D'"),("vat_side","TEXT NOT NULL DEFAULT 'D'"),("payment_side","TEXT NOT NULL DEFAULT 'C'")):
                if column not in expense_columns: db.execute(f"ALTER TABLE expenses ADD COLUMN {column} {definition}")
            db.execute("UPDATE expenses SET with_vat_subtotal=subtotal WHERE CAST(with_vat_subtotal AS REAL)=0 AND CAST(without_vat_subtotal AS REAL)=0 AND CAST(subtotal AS REAL)<>0")
            party_columns={row["name"] for row in db.execute("PRAGMA table_info(parties)")}
            if "account_number" not in party_columns:
                db.execute("ALTER TABLE parties ADD COLUMN account_number TEXT")
            for column in ("mof_number","address","contact_number"):
                if column not in party_columns: db.execute(f"ALTER TABLE parties ADD COLUMN {column} TEXT")
            if "account_category" not in party_columns: db.execute("ALTER TABLE parties ADD COLUMN account_category TEXT")
            if "due_days" not in party_columns: db.execute("ALTER TABLE parties ADD COLUMN due_days INTEGER NOT NULL DEFAULT 0")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_parties_account_number ON parties(account_number) WHERE account_number IS NOT NULL")
            employee_columns={row["name"] for row in db.execute("PRAGMA table_info(employees)")}
            if "spouse_works" not in employee_columns: db.execute("ALTER TABLE employees ADD COLUMN spouse_works INTEGER NOT NULL DEFAULT 0")
            if "employee_group" not in employee_columns: db.execute("ALTER TABLE employees ADD COLUMN employee_group TEXT NOT NULL DEFAULT 'employee'")
            payroll_columns={row["name"] for row in db.execute("PRAGMA table_info(payroll_records)")}
            if "income_tax_lbp" not in payroll_columns: db.execute("ALTER TABLE payroll_records ADD COLUMN income_tax_lbp TEXT NOT NULL DEFAULT '0'")
            if "retro_salary" not in payroll_columns: db.execute("ALTER TABLE payroll_records ADD COLUMN retro_salary TEXT NOT NULL DEFAULT '0'")
            if "retro_from" not in payroll_columns: db.execute("ALTER TABLE payroll_records ADD COLUMN retro_from TEXT")
            if "retro_to" not in payroll_columns: db.execute("ALTER TABLE payroll_records ADD COLUMN retro_to TEXT")
            payroll_setting_columns={row["name"] for row in db.execute("PRAGMA table_info(payroll_settings)")}
            for column,default in (("transport_daily_exempt","450000"),("default_transport_days","26"),("schooling_annual_exempt","6000000"),("schooling_max_children","3"),
                                   ("schooling_public_child","0"),("schooling_public_cap","0"),("schooling_private_child","0"),("schooling_private_cap","0"),
                                   ("tax_rounding","0"),("minimum_wage","0"),("max_children_deduction","5"),("family_allowance_spouse","0"),("family_allowance_child","0"),
                                   ("family_allowance_cap","0"),("family_allowance_max_children","5")):
                if column not in payroll_setting_columns: db.execute(f"ALTER TABLE payroll_settings ADD COLUMN {column} TEXT NOT NULL DEFAULT '{default}'")
            payroll_record_columns={row["name"] for row in db.execute("PRAGMA table_info(payroll_records)")}
            for column in ("transport_days","exempt_transport","exempt_schooling","family_allowance","regular_tax","one_off_tax","compliance_notes","director_remuneration"):
                if column not in payroll_record_columns: db.execute(f"ALTER TABLE payroll_records ADD COLUMN {column} TEXT")
            if "employee_account_map" not in payroll_setting_columns: db.execute("ALTER TABLE payroll_settings ADD COLUMN employee_account_map TEXT NOT NULL DEFAULT '{}'")
            if "manager_account_map" not in payroll_setting_columns: db.execute("ALTER TABLE payroll_settings ADD COLUMN manager_account_map TEXT NOT NULL DEFAULT '{}'")
            if "retro_tax" not in payroll_columns: db.execute("ALTER TABLE payroll_records ADD COLUMN retro_tax TEXT NOT NULL DEFAULT '0'")
            db.execute("""UPDATE OR IGNORE payroll_records SET period_date=substr(period_date,7,4)||'-'||substr(period_date,4,2)||'-'||substr(period_date,1,2)
                WHERE period_date GLOB '??-??-????'""")
            # Older versions saved payroll dates exactly as typed (DD-MM-YYYY, DDMMYYYY...). Store them as YYYY-MM-DD.
            for table,column in (("payroll_settings","date_from"),("payroll_settings","date_to"),("payroll_records","period_date"),
                                 ("payroll_records","retro_from"),("payroll_records","retro_to")):
                for row in db.execute(f"SELECT id,{column} value FROM {table} WHERE {column} IS NOT NULL AND {column}<>''").fetchall():
                    try: fixed=iso_date(row["value"])
                    except ValueError: continue
                    if fixed!=row["value"]: db.execute(f"UPDATE OR IGNORE {table} SET {column}=? WHERE id=?",(fixed,row["id"]))
            document_columns={row["name"] for row in db.execute("PRAGMA table_info(party_documents)")}
            if "active" not in document_columns:  # "applies to this party" tick; existing documents stay active
                db.execute("ALTER TABLE party_documents ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
            line_columns={row["name"] for row in db.execute("PRAGMA table_info(journal_lines)")}
            for column in ("line_currency","amount","amount_lbp","amount_usd","rate_lbp","rate_usd","due_date","reference"):
                if column not in line_columns: db.execute(f"ALTER TABLE journal_lines ADD COLUMN {column} TEXT")
            for column in ("department_id","project_id"):
                if column not in line_columns: db.execute(f"ALTER TABLE journal_lines ADD COLUMN {column} INTEGER")
            for table in ("invoices","expenses"):
                columns={row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
                for column in ("department_id","project_id"):
                    if column not in columns: db.execute(f"ALTER TABLE {table} ADD COLUMN {column} INTEGER")
            payment_columns={row["name"] for row in db.execute("PRAGMA table_info(payments)")}
            for column,definition in (("payment_number","TEXT"),("payment_method","TEXT"),("department_id","INTEGER"),("project_id","INTEGER"),
                                      ("bank_commission","TEXT NOT NULL DEFAULT '0'"),("commission_account","TEXT"),
                                      ("exchange_difference","TEXT NOT NULL DEFAULT '0'"),("exchange_account","TEXT")):
                if column not in payment_columns: db.execute(f"ALTER TABLE payments ADD COLUMN {column} {definition}")
            expense_cols={row["name"] for row in db.execute("PRAGMA table_info(expenses)")}
            if "expense_number" not in expense_cols: db.execute("ALTER TABLE expenses ADD COLUMN expense_number TEXT")
            invoice_cols={row["name"] for row in db.execute("PRAGMA table_info(invoices)")}
            if "linked_invoice_id" not in invoice_cols: db.execute("ALTER TABLE invoices ADD COLUMN linked_invoice_id INTEGER")
            if "vat_treatment" not in invoice_cols: db.execute("ALTER TABLE invoices ADD COLUMN vat_treatment TEXT NOT NULL DEFAULT 'standard'")
            if "vat_use" not in invoice_cols: db.execute("ALTER TABLE invoices ADD COLUMN vat_use TEXT NOT NULL DEFAULT 'mixed'")
            expense_cols={row["name"] for row in db.execute("PRAGMA table_info(expenses)")}
            if "vat_use" not in expense_cols: db.execute("ALTER TABLE expenses ADD COLUMN vat_use TEXT NOT NULL DEFAULT 'mixed'")
            return_cols={row["name"] for row in db.execute("PRAGMA table_info(vat_returns)")}
            if "refund_requested_lbp" not in return_cols: db.execute("ALTER TABLE vat_returns ADD COLUMN refund_requested_lbp TEXT NOT NULL DEFAULT '0'")
            if "deduction_ratio" not in return_cols: db.execute("ALTER TABLE vat_returns ADD COLUMN deduction_ratio TEXT")
            entry_columns={row["name"] for row in db.execute("PRAGMA table_info(journal_entries)")}
            if "voucher_type" not in entry_columns: db.execute("ALTER TABLE journal_entries ADD COLUMN voucher_type TEXT NOT NULL DEFAULT '01'")
            import inventory
            inventory.migrate(db)
            import fixed_assets
            fixed_assets.migrate(db)
            import bank_rec
            bank_rec.migrate(db)
            employee_cols={row["name"] for row in db.execute("PRAGMA table_info(employees)")}
            for column in ("nationality","father_name","mother_name","birth_date","birth_place"):
                if column not in employee_cols: db.execute(f"ALTER TABLE employees ADD COLUMN {column} TEXT")
            import chart_extra
            chart_extra.ensure_accounts(db)
            item_cols={row["name"] for row in db.execute("PRAGMA table_info(invoice_items)")}
            for column,definition in (("unit","TEXT"),("discount_percent","TEXT"),("discount_amount","TEXT"),("gross_amount","TEXT")):
                if column not in item_cols: db.execute(f"ALTER TABLE invoice_items ADD COLUMN {column} {definition}")
            inv_cols={row["name"] for row in db.execute("PRAGMA table_info(invoices)")}
            for column,definition in (("doc_subtype","TEXT NOT NULL DEFAULT 'invoice'"),("invoice_discount_percent","TEXT"),("invoice_discount_amount","TEXT"),("gross_before_discount","TEXT"),("notes","TEXT")):
                if column not in inv_cols: db.execute(f"ALTER TABLE invoices ADD COLUMN {column} {definition}")
            db.execute("""CREATE TABLE IF NOT EXISTS payment_allocations (id INTEGER PRIMARY KEY, payment_id INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
                invoice_id INTEGER NOT NULL, amount TEXT NOT NULL, created_at TEXT NOT NULL)""")
            # new default posting accounts for payroll (only where the old defaults were never changed)
            for row in db.execute("SELECT id,employee_account_map,manager_account_map FROM payroll_settings").fetchall():
                for column,new_map in (("employee_account_map",chart_extra.PAYROLL_MAP),("manager_account_map",chart_extra.MANAGER_PAYROLL_MAP)):
                    try: current=json.loads(row[column] or "{}")
                    except ValueError: current={}
                    if not current or current==chart_extra.OLD_PAYROLL_MAP: db.execute(f"UPDATE payroll_settings SET {column}=? WHERE id=?",(json.dumps(new_map),row["id"]))
            db.execute("""UPDATE payroll_settings SET payroll_tax_account='4411',nssf_payable_account='4431',salary_account='6311'
                WHERE payroll_tax_account='443100001' AND nssf_payable_account='447100001'""")
            user_columns={row["name"] for row in db.execute("PRAGMA table_info(users)")}
            if "expires_at" not in user_columns: db.execute("ALTER TABLE users ADD COLUMN expires_at TEXT")
            if "permissions" not in user_columns: db.execute("ALTER TABLE users ADD COLUMN permissions TEXT NOT NULL DEFAULT '{}'")
            if "created_at" not in user_columns: db.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
            invoice_columns={row["name"] for row in db.execute("PRAGMA table_info(invoices)")}
            if "vat_recoverable" not in invoice_columns: db.execute("ALTER TABLE invoices ADD COLUMN vat_recoverable INTEGER NOT NULL DEFAULT 1")
            expense_columns={row["name"] for row in db.execute("PRAGMA table_info(expenses)")}
            if "vat_recoverable" not in expense_columns: db.execute("ALTER TABLE expenses ADD COLUMN vat_recoverable INTEGER NOT NULL DEFAULT 1")
            db.execute("INSERT OR IGNORE INTO users(username,password_hash,role) VALUES(?,?,?)", ("admin", hash_password(admin_password), "admin"))
            db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('base_currency','USD')")
            db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('backup_interval_hours','24')")
            db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('last_scheduled_backup','')")
            default_brackets=json.dumps([[360000000,.02],[900000000,.04],[1800000000,.07],[3600000000,.11],[7200000000,.15],[13500000000,.20],[None,.25]])
            db.execute("""INSERT OR IGNORE INTO payroll_settings(date_from,date_to,tax_brackets,created_at)
                VALUES('2025-01-01',NULL,?,?)""",(default_brackets,utcnow()))
            db.executemany("""INSERT INTO accounts(code,name_en,name_ar,name_fr,type)
                VALUES(?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET
                name_en=excluded.name_en,name_ar=excluded.name_ar,name_fr=excluded.name_fr,type=excluded.type""",
                [row[:5] for row in LEBANESE_ACCOUNTS])
            for code, _name_en, _name_ar, _name_fr, _type, parent_code in LEBANESE_ACCOUNTS:
                if parent_code:
                    db.execute("UPDATE accounts SET parent_id=(SELECT id FROM accounts WHERE code=?) WHERE code=?",
                               (parent_code, code))
            for old_code, new_code in LEGACY_ACCOUNT_MAP.items():
                old = db.execute("SELECT id FROM accounts WHERE code=?", (old_code,)).fetchone()
                new = db.execute("SELECT id FROM accounts WHERE code=?", (new_code,)).fetchone()
                if old and new and old["id"] != new["id"]:
                    db.execute("UPDATE journal_lines SET account_id=? WHERE account_id=?", (new["id"], old["id"]))
                    db.execute("DELETE FROM accounts WHERE id=?", (old["id"],))
            db.execute("UPDATE invoices SET supplier_account=? WHERE supplier_account='2100'",
                       (DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"],))
            db.execute("UPDATE invoices SET vat_account=? WHERE vat_account='1300'",
                       (DEFAULT_LEBANESE_ACCOUNTS["vat_receivable"],))
            db.execute("UPDATE invoices SET expense_account=? WHERE expense_account='5100'",
                       (DEFAULT_LEBANESE_ACCOUNTS["purchases"],))
            db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,(SELECT id FROM accounts WHERE code='6011'))",
                       (EXPENSE_ACCOUNT_9,"General Expenses - 9 Digit","expense"))
            db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,(SELECT id FROM accounts WHERE code='4426.6'))",
                       ("442660000","VAT Receivable - 9 Digit","asset"))
            db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,(SELECT id FROM accounts WHERE code='6011'))",
                       (EXPENSE_NO_VAT_ACCOUNT_9,"Expenses without VAT - 9 Digit","expense"))
            db.execute("UPDATE invoices SET expense_account=? WHERE expense_account='6011'",(EXPENSE_ACCOUNT_9,))
            db.execute("UPDATE invoices SET vat_account=? WHERE vat_account='4426.6'",(VAT_ACCOUNT_9,))
            db.execute("UPDATE invoices SET entry_type=kind WHERE entry_type IS NULL OR entry_type='' OR (entry_type='purchase' AND kind='sale')")
            db.execute("UPDATE invoices SET entry_type='purchases' WHERE entry_type IN ('purchase','expense_without_vat')")
            db.execute("UPDATE invoices SET entry_type='sales' WHERE entry_type='sale'")
            suppliers=db.execute("SELECT id,name,account_number FROM parties WHERE kind IN ('supplier','both') ORDER BY id").fetchall()
            for supplier in suppliers:
                account_number=supplier["account_number"] or f"4011{supplier['id']:05d}"
                db.execute("UPDATE parties SET account_number=? WHERE id=?",(account_number,supplier["id"]))
                db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,(SELECT id FROM accounts WHERE code='4011'))",
                    (account_number,f"Supplier - {supplier['name']}","liability"))
                db.execute("UPDATE invoices SET supplier_account=? WHERE party_id=? AND kind='purchase' AND supplier_account='4011'",
                    (account_number,supplier["id"]))
            # Performance indexes on the columns used for filtering and joins.
            # Placed at the very end of initialize so every table (including
            # those created by later migrations) already exists. Without these
            # SQLite falls back to full-table scans, which get slow as
            # invoices / journal lines / payments grow. IF NOT EXISTS makes
            # this idempotent and it applies to every company database.
            for index_sql in (
                "CREATE INDEX IF NOT EXISTS idx_invoices_party ON invoices(party_id)",
                "CREATE INDEX IF NOT EXISTS idx_invoices_kind ON invoices(kind)",
                "CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date)",
                "CREATE INDEX IF NOT EXISTS idx_invoices_branch ON invoices(branch_id)",
                "CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice ON invoice_items(invoice_id)",
                "CREATE INDEX IF NOT EXISTS idx_invoice_attachments_invoice ON invoice_attachments(invoice_id)",
                "CREATE INDEX IF NOT EXISTS idx_party_documents_party ON party_documents(party_id)",
                "CREATE INDEX IF NOT EXISTS idx_case_attachments_case ON case_attachments(case_id)",
                "CREATE INDEX IF NOT EXISTS idx_document_cases_party ON document_cases(party_id)",
                "CREATE INDEX IF NOT EXISTS idx_document_cases_invoice ON document_cases(invoice_id)",
                "CREATE INDEX IF NOT EXISTS idx_journal_entries_source ON journal_entries(source_type,source_id)",
                "CREATE INDEX IF NOT EXISTS idx_journal_entries_date ON journal_entries(entry_date)",
                "CREATE INDEX IF NOT EXISTS idx_journal_entries_branch ON journal_entries(branch_id)",
                "CREATE INDEX IF NOT EXISTS idx_journal_lines_entry ON journal_lines(entry_id)",
                "CREATE INDEX IF NOT EXISTS idx_journal_lines_account ON journal_lines(account_id)",
                "CREATE INDEX IF NOT EXISTS idx_journal_lines_party ON journal_lines(party_id)",
                "CREATE INDEX IF NOT EXISTS idx_stock_movements_item ON stock_movements(item_id)",
                "CREATE INDEX IF NOT EXISTS idx_stock_movements_source ON stock_movements(source_type,source_id)",
                "CREATE INDEX IF NOT EXISTS idx_payments_party ON payments(party_id)",
                "CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date)",
                "CREATE INDEX IF NOT EXISTS idx_payment_allocations_payment ON payment_allocations(payment_id)",
                "CREATE INDEX IF NOT EXISTS idx_payment_allocations_invoice ON payment_allocations(invoice_id)",
                "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date)",
                "CREATE INDEX IF NOT EXISTS idx_payroll_records_employee ON payroll_records(employee_id)",
                "CREATE INDEX IF NOT EXISTS idx_payroll_records_period ON payroll_records(period_date)",
                "CREATE INDEX IF NOT EXISTS idx_employees_active ON employees(active)",
                "CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity,entity_id)",
                "CREATE INDEX IF NOT EXISTS idx_budgets_year ON budgets(year)",
            ):
                db.execute(index_sql)
            # Refresh the query planner statistics so it actually uses the
            # indexes above.
            db.execute("ANALYZE")
        self._auto_lebanese_payroll_rules()
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES('startup_schema_version',?)",
                       (self.STARTUP_SCHEMA_VERSION,))
            db.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES('startup_schema_signature',?)",
                       (self._startup_schema_signature(db),))

    def _auto_lebanese_payroll_rules(self):
        """If the Tax & NSSF settings were never filled in (all NSSF ceilings are 0), load the official Lebanese
        periods automatically so the 2024-2026 ceilings apply month by month without any manual step."""
        with self.connect() as db:
            rows=db.execute("SELECT employee_ceiling,medical_ceiling,family_ceiling FROM payroll_settings").fetchall()
            done=db.execute("SELECT value FROM app_settings WHERE key='lebanese_payroll_rules_auto'").fetchone()
        unconfigured=not rows or all(Decimal(str(r["employee_ceiling"] or 0))==0 and Decimal(str(r["medical_ceiling"] or 0))==0 and Decimal(str(r["family_ceiling"] or 0))==0 for r in rows)
        if done or not unconfigured: return
        self.apply_lebanese_payroll_rules(None)
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO app_settings(key,value) VALUES('lebanese_payroll_rules_auto',?)",(utcnow(),))

    @staticmethod
    def month_end(value):
        """Payroll is monthly: the rules of a month are those in force on its last day."""
        day=datetime.strptime(iso_date(value),"%Y-%m-%d")
        import calendar
        return day.replace(day=calendar.monthrange(day.year,day.month)[1]).strftime("%Y-%m-%d")

    @staticmethod
    def user_is_expired(user, today=None):
        expires=user["expires_at"] if "expires_at" in user.keys() else None
        if not expires: return False
        today=today or datetime.now().strftime("%Y-%m-%d")
        return str(expires) < today

    def login(self, username, password, remote_addr=None):
        """Authenticate with a persistent 15-minute lockout and audit every denial."""
        username=str(username or "").strip(); now=datetime.now(timezone.utc)
        keys=["user:"+username.casefold()]
        if remote_addr: keys.append("ip:"+str(remote_addr))
        with self.connect() as db:
            attempts={row["key"]:row for row in db.execute(
                f"SELECT * FROM login_attempts WHERE key IN ({','.join('?' for _ in keys)})",keys)}
            locked=any(row["locked_until"] and (parse_ts(row["locked_until"]) or now)>now for row in attempts.values())
            user = db.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
            if locked:
                db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                           (user["id"] if user else None,"login_blocked","auth",json.dumps({"username":username,"remote_addr":remote_addr}),utcnow()))
                return {"rate_limited": True}
            if not user or not verify_password(password, user["password_hash"]):
                for key in keys:
                    previous=attempts.get(key)
                    first=parse_ts(previous["first_failed_at"]) if previous else None
                    count=(previous["failed_count"]+1) if first and now-first<timedelta(minutes=15) else 1
                    limit=5 if key.startswith("user:") else 30
                    until=(now+timedelta(minutes=15)).isoformat() if count>=limit else None
                    db.execute("INSERT INTO login_attempts(key,failed_count,first_failed_at,locked_until) VALUES(?,?,?,?) "
                               "ON CONFLICT(key) DO UPDATE SET failed_count=excluded.failed_count,first_failed_at=excluded.first_failed_at,locked_until=excluded.locked_until",
                               (key,count,previous["first_failed_at"] if first and now-first<timedelta(minutes=15) else utcnow(),until))
                db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                           (user["id"] if user else None,"login_failed","auth",json.dumps({"username":username,"remote_addr":remote_addr}),utcnow()))
                return None
            db.execute("DELETE FROM login_attempts WHERE key=?",(keys[0],))
            if self.user_is_expired(user):
                raise PermissionError(f"This account expired on {display_date(user['expires_at'])}. Ask the administrator to renew it.")
            token = secrets.token_urlsafe(32)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=SESSION_HOURS)
            stale = [row["token"] for row in db.execute("SELECT token,created_at FROM sessions")
                     if (parse_ts(row["created_at"]) or datetime.now(timezone.utc)) < cutoff]
            for stale_token in stale:
                db.execute("DELETE FROM sessions WHERE token=?", (stale_token,))
            db.execute("INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)", (token, user["id"], utcnow()))
            return {"token": token, "username": user["username"], "role": user["role"], "language": user["language"],
                "expires_at": user["expires_at"], "permissions": parse_permissions(user["permissions"]) if user["role"]!="admin" else {m:True for m in PERMISSION_MODULES}}

    def user_for_token(self, token):
        if not token: return None
        with self.connect() as db:
            row=db.execute("""SELECT u.*, s.created_at AS session_created_at FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token=? AND u.active=1""", (token,)).fetchone()
        if not row: return None
        created=parse_ts(row["session_created_at"])
        if created is None or (datetime.now(timezone.utc)-created) > timedelta(hours=SESSION_HOURS): return None
        if self.user_is_expired(row): return None
        return row

    def user_can(self, user, module):
        if not user: return False
        if user["role"]=="admin": return True
        return parse_permissions(user["permissions"] if "permissions" in user.keys() else "{}").get(module, True)

    def list_users(self):
        today=datetime.now().date()
        with self.connect() as db:
            rows=[dict(row) for row in db.execute("SELECT id,username,role,language,active,expires_at,permissions FROM users ORDER BY username")]
        for row in rows:
            row["permissions"]=parse_permissions(row.get("permissions"))
            if row.get("expires_at"):
                row["days_remaining"]=(datetime.strptime(row["expires_at"],"%Y-%m-%d").date()-today).days
                row["status"]="expired" if row["days_remaining"]<0 else "active"
            else:
                row["days_remaining"]=None; row["status"]="active"
            if not row["active"]: row["status"]="disabled"
        return rows

    def save_user(self, item, acting_user_id):
        username=str(item.get("username") or "").strip(); role=str(item.get("role") or "viewer").strip()
        language=str(item.get("language") or "en").strip(); password=str(item.get("password") or "")
        active=1 if item.get("active",True) else 0; user_id=item.get("id")
        if not username or role not in ("admin","accountant","viewer") or language not in ("en","ar","fr"):
            raise ValueError("Enter a valid username, role, and language")
        if password and len(password)<6: raise ValueError("Password must contain at least 6 characters")
        permissions=json.dumps(parse_permissions(item.get("permissions")))
        one_year=(datetime.now()+timedelta(days=USER_VALIDITY_DAYS)).strftime("%Y-%m-%d")
        with self.connect() as db:
            existing=db.execute("SELECT * FROM users WHERE id=?",(int(user_id),)).fetchone() if user_id else None
            if user_id and not existing: raise ValueError("User was not found")
            clash=db.execute("SELECT id FROM users WHERE lower(username)=lower(?) AND id<>?",(username,int(user_id or 0))).fetchone()
            if clash: raise ValueError(f"Username '{username}' is already used")
            if item.get("renew"): expires=one_year
            elif "expires_at" in item: expires=iso_date(item["expires_at"],"Expiry date") if str(item.get("expires_at") or "").strip() else None
            elif existing: expires=existing["expires_at"]
            else: expires=None if role=="admin" else one_year
            if existing and existing["role"]=="admin" and (role!="admin" or not active):
                admins=db.execute("SELECT COUNT(*) n FROM users WHERE role='admin' AND active=1 AND id<>?",(int(user_id),)).fetchone()["n"]
                if not admins: raise ValueError("At least one active administrator must remain")
            if user_id:
                db.execute("UPDATE users SET username=?,role=?,language=?,active=?,expires_at=?,permissions=? WHERE id=?",
                    (username,role,language,active,expires,permissions,int(user_id)))
                if password: db.execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(password),int(user_id)))
                if not active or password: db.execute("DELETE FROM sessions WHERE user_id=?",(int(user_id),))
                saved_id=int(user_id)
            else:
                if not password: raise ValueError("Password is required for a new user")
                saved_id=db.execute("INSERT INTO users(username,password_hash,role,language,active,expires_at,permissions,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (username,hash_password(password),role,language,active,expires,permissions,utcnow())).lastrowid
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (acting_user_id,"save","user",saved_id,json.dumps({"username":username,"role":role,"active":active,"expires_at":expires,"permissions":json.loads(permissions)}),utcnow()))
        return next(row for row in self.list_users() if row["id"]==saved_id)

    def _account_id(self, db, code):
        row = db.execute("SELECT id FROM accounts WHERE code=?", (code,)).fetchone()
        return row["id"]

    def _entry_type(self,item):
        value=str(item.get("entry_type") or item.get("kind") or "purchases").strip().lower().replace(" ","_")
        aliases={"sale":"sales","purchase":"purchases","expense_without_vat":"expenses"}
        value=aliases.get(value,value)
        if value not in ("assets","expenses","purchases","sales"):
            raise ValueError("Type must be Assets, Expenses, Purchases, or Sales")
        return value

    def _side(self,value,default):
        side=str(value or default).strip().upper()[:1]
        if side not in ("D","C"): raise ValueError("Account side must be D or C")
        return side

    def _line_for_side(self,code,amount,side):
        return (code,amount,Decimal("0")) if side=="D" else (code,Decimal("0"),amount)

    def _branch_id(self,db,item):
        value=item.get("branch_id") if isinstance(item,dict) else None
        if value:
            row=db.execute("SELECT id FROM branches WHERE id=? AND active=1",(int(value),)).fetchone()
            if not row: raise ValueError("Branch was not found")
            return row["id"]
        name=str(item.get("branch") or "Head Office").strip() if isinstance(item,dict) else "Head Office"
        db.execute("INSERT OR IGNORE INTO branches(name) VALUES(?)",(name,))
        return db.execute("SELECT id FROM branches WHERE name=?",(name,)).fetchone()["id"]

    def _ensure_party_account(self, db, party):
        if party["kind"] not in ("customer","supplier","both"): return None
        category=(party["account_category"] or ("client" if party["kind"]=="customer" else "supplier")) if "account_category" in party.keys() else ("client" if party["kind"]=="customer" else "supplier")
        prefix={"client":"4111","supplier":"4011","asset_supplier":"4031","other_payable":"4619"}.get(category,"4011")
        account_number=party["account_number"]
        if not account_number:
            last=db.execute("SELECT account_number FROM parties WHERE account_number LIKE ? AND length(account_number)=9 ORDER BY CAST(account_number AS INTEGER) DESC LIMIT 1",(prefix+"%",)).fetchone()
            next_suffix=(int(last["account_number"][4:])+1) if last else 1
            if next_suffix>99999: raise ValueError(f"No account numbers remain under prefix {prefix}")
            account_number=f"{prefix}{next_suffix:05d}"
        db.execute("UPDATE parties SET account_number=? WHERE id=?",(account_number,party["id"]))
        parent="4111" if party["kind"]=="customer" else "4011"
        label={"client":"Client","supplier":"Supplier","asset_supplier":"Asset Supplier","other_payable":"Other Payable"}.get(category,"Supplier")
        account_type="asset" if party["kind"]=="customer" else "liability"
        db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,(SELECT id FROM accounts WHERE code=?))",
            (account_number,f"{label} - {party['name']}",account_type,parent))
        return account_number

    def _date_year(self, value):
        text = str(value or "").strip()
        for pattern in ("%d-%m-%Y", "%d%m%Y", "%Y-%m-%d", "%Y%m%d"):
            try: return datetime.strptime(text, pattern).year
            except ValueError: pass
        raise ValueError("Date must use DD-MM-YYYY")

    def _assert_period_open(self, value):
        year = self._date_year(value)
        with self.connect() as db:
            row = db.execute("SELECT status FROM fiscal_years WHERE year=?", (year,)).fetchone()
        if row and row["status"] == "closed":
            raise ValueError(f"Fiscal year {year} is closed; entries cannot be added or changed")

    def next_invoice_number(self, kind="sale", invoice_date=None):
        prefix = {"sale":"SAL","sales":"SAL","credit_note":"CN","debit_note":"DN","supplier_credit_note":"SCN","supplier_debit_note":"SDN"}.get(str(kind).lower(),"PUR")
        year = str(invoice_date or datetime.now().year)
        if "-" in year:
            year = year[-4:] if year[:4].isdigit() is False else year[:4]
        if not year.isdigit() or len(year) != 4:
            year = str(datetime.now().year)
        pattern = f"{prefix}-{year}-%"
        with self.connect() as db:
            values = [row["invoice_number"] for row in db.execute(
                "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ?", (pattern,))]
        sequence = 1
        for value in values:
            try: sequence = max(sequence, int(value.rsplit("-", 1)[-1]) + 1)
            except (TypeError, ValueError): pass
        return f"{prefix}-{year}-{sequence:06d}"

    backup_folder = None   # set by CompanyManager: backups/<company>/<year>
    backup_label = None    # "<company>_<year>"

    def _backups_dir(self):
        return Path(self.backup_folder) if self.backup_folder else Path(self.path).parent / "backups"

    def backup(self, kind="backup"):
        """Consistent copy of this company-year file (SQLite backup API, safe while others are writing).
        Stored in backups/<company>/<year>/<company>_<year>_<date>_<time>.db"""
        source = Path(self.path)
        if not source.exists(): return None
        folder = self._backups_dir(); folder.mkdir(parents=True, exist_ok=True)
        label = self.backup_label or "saber_accounting"
        target = folder / f"{label}_{datetime.now():%Y-%m-%d_%H%M%S}{'_' + kind if kind != 'backup' else ''}.db"
        if target.exists(): target = folder / f"{target.stem}_{datetime.now():%f}.db"
        with self._lock:
            source_connection = sqlite3.connect(str(source)); target_connection = sqlite3.connect(str(target))
            try: source_connection.backup(target_connection)
            finally: target_connection.close(); source_connection.close()
        return str(target)

    @staticmethod
    def _validate_backup_file(path):
        try:
            connection=sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True)
            try:
                if connection.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise ValueError("Backup file is damaged")
                tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            finally: connection.close()
        except sqlite3.DatabaseError as exc: raise ValueError("Selected file is not a valid Saber Accounting backup") from exc
        if not {"accounts","journal_entries","invoices"}.issubset(tables): raise ValueError("Selected file is not a Saber Accounting backup")

    def _backup_files(self):
        folders=[self._backups_dir()]
        legacy=Path(self.path).parent/"backups"
        if legacy.resolve()!=folders[0].resolve(): folders.append(legacy)
        files={}
        for index,folder in enumerate(folders):
            if not folder.exists(): continue
            for path in folder.glob("*.db" if index==0 else "saber_accounting_*.db"): files.setdefault(path.name,path)
        return files

    def list_backups(self):
        files=self._backup_files()
        return [{"name":path.name,"size":path.stat().st_size,"modified":datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                 "kind":"safety" if "_safety" in path.stem else "older version" if path.name.startswith("saber_accounting_") and self.backup_label else "backup"}
                for path in sorted(files.values(),key=lambda p:p.stat().st_mtime,reverse=True)]

    def backup_path(self, name):
        path=self._backup_files().get(Path(str(name)).name)
        if not path or not path.exists(): raise ValueError("Backup was not found")
        return path

    def restore_backup(self, name, user_id):
        source=self.backup_path(name).resolve()
        self._validate_backup_file(source)
        safety=self.backup("safety")
        with self._lock:
            self.release()  # nobody may read or write this file while it is being replaced
            source_connection=sqlite3.connect(str(source)); target_connection=sqlite3.connect(self.path)
            try: source_connection.backup(target_connection)
            finally: target_connection.close(); source_connection.close()
        with self.connect() as db:
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                (user_id,"restore","database",json.dumps({"backup":source.name,"safety_backup":safety}),utcnow()))
        return {"restored":source.name,"safety_backup":safety}

    def settings(self):
        with self.connect() as db: return {row["key"]:row["value"] for row in db.execute("SELECT key,value FROM app_settings")}

    def currencies(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT code,name FROM currencies ORDER BY CASE code WHEN 'USD' THEN 0 WHEN 'LBP' THEN 1 WHEN 'EUR' THEN 2 WHEN 'AED' THEN 3 ELSE 4 END,code")]

    def currency_codes(self):
        return {item["code"] for item in self.currencies()}

    def save_currency(self, code, name, user_id):
        code=str(code or "").strip().upper(); name=str(name or "").strip()
        if not re.fullmatch(r"[A-Z]{3}",code): raise ValueError("Currency code must be three letters")
        if not name or len(name)>80: raise ValueError("Enter a currency name up to 80 characters")
        with self.connect() as db:
            if db.execute("SELECT 1 FROM currencies WHERE code=?",(code,)).fetchone(): raise ValueError(f"Currency {code} already exists")
            db.execute("INSERT INTO currencies(code,name) VALUES(?,?)",(code,name))
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                       (user_id,"create","currency",json.dumps({"code":code,"name":name}),utcnow()))
        return {"code":code,"name":name}

    def save_settings(self, values, user_id):
        allowed={"base_currency","backup_interval_hours","company_name","company_address","company_phone","company_mof","company_nssf","company_email","company_website","company_logo","company_vat_registered","company_vat_date"}
        if str(values.get("base_currency") or "USD") not in self.currency_codes(): raise ValueError("Invalid base currency")
        try: hours=int(values.get("backup_interval_hours",24))
        except Exception as exc: raise ValueError("Backup interval must be a number") from exc
        if hours<1 or hours>720: raise ValueError("Backup interval must be between 1 and 720 hours")
        with self.connect() as db:
            for key in allowed:
                if key in values: db.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(values[key])))
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                (user_id,"update","settings",json.dumps({key:values[key] for key in allowed if key in values}),utcnow()))
        return self.settings()

    def maybe_scheduled_backup(self):
        settings=self.settings(); hours=int(settings.get("backup_interval_hours","24")); last=settings.get("last_scheduled_backup","")
        try: due=(datetime.now(timezone.utc)-datetime.fromisoformat(last)).total_seconds()>=hours*3600
        except Exception: due=True
        if due:
            path=self.backup()
            with self.connect() as db:
                db.execute("INSERT INTO app_settings(key,value) VALUES('last_scheduled_backup',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(utcnow(),))
            return path
        return None

    def clear_invoices(self, user_id, make_backup=True):
        with self.connect() as db:
            if db.execute("SELECT 1 FROM payment_allocations LIMIT 1").fetchone():
                raise ValueError("Invoice replacement is blocked while payments are allocated to existing invoices")
            if db.execute("SELECT 1 FROM stock_documents WHERE invoice_id IS NOT NULL LIMIT 1").fetchone():
                raise ValueError("Invoice replacement is blocked while stock documents are linked to invoices")
            if db.execute("SELECT 1 FROM vat_returns LIMIT 1").fetchone():
                raise ValueError("Invoice replacement is blocked after a quarterly VAT return has been saved")
            if db.execute("SELECT 1 FROM fiscal_years WHERE status='closed' LIMIT 1").fetchone():
                raise ValueError("Invoice replacement is blocked while a fiscal year is closed")
            if db.execute("SELECT 1 FROM invoices WHERE CAST(COALESCE(amount_paid,'0') AS REAL)>0 LIMIT 1").fetchone():
                raise ValueError("Invoice replacement is blocked while existing invoices have payments recorded")
        backup_path = self.backup("safety") if make_backup else None
        with self.connect() as db:
            entry_ids = [r["id"] for r in db.execute("SELECT id FROM journal_entries WHERE source_type IN ('invoice','invoice_reversal','vat_reclass') AND (source_type!='vat_reclass' OR entry_number LIKE 'VATND-INV-%')")]
            if entry_ids:
                marks = ",".join("?" for _ in entry_ids)
                db.execute(f"DELETE FROM journal_lines WHERE entry_id IN ({marks})", entry_ids)
                db.execute(f"DELETE FROM journal_entries WHERE id IN ({marks})", entry_ids)
            deleted = db.execute("SELECT COUNT(*) n FROM invoices").fetchone()["n"]
            db.execute("DELETE FROM invoices")
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)", (user_id,"replace","invoice_import",json.dumps({"deleted":deleted,"backup":backup_path}),utcnow()))
            return {"deleted": deleted, "backup": backup_path}

    def import_invoice(self, item, user_id):
        # No uniqueness constraint is applied to invoice numbers: duplicates are intentionally retained.
        self._assert_period_open(item.get("invoice_date"))
        with self.connect() as db:
            entry_type=self._entry_type(item); kind="sale" if entry_type=="sales" else "purchase"
            party_kind = "customer" if kind == "sale" else "supplier"
            db.execute("INSERT OR IGNORE INTO parties(kind,name,currency) VALUES(?,?,?)", (party_kind, item.get("party_name") or "Unspecified", item.get("currency", "USD")))
            party = db.execute("SELECT * FROM parties WHERE kind=? AND name=?", (party_kind, item.get("party_name") or "Unspecified")).fetchone()
            raw_subtotal=Decimal(str(item.get("subtotal") or 0))
            deductible=Decimal(str(item.get("deductible_subtotal") if item.get("deductible_subtotal") not in (None,"") else raw_subtotal))
            non_deductible=Decimal(str(item.get("non_deductible_subtotal") or 0)); subtotal=deductible+non_deductible
            vat = Decimal(str(item.get("vat") or 0)); total = Decimal(str(item.get("total") or subtotal + vat))
            currency_issue = str(item.get("currency_issue") or "")
            requested_status=str(item.get("status") or "").strip().lower()
            status=requested_status if requested_status in ("posted","review") else ("posted" if total == subtotal + vat and not currency_issue.startswith(("conflicting:", "unsupported:")) else "review")
            default_party_account=DEFAULT_LEBANESE_ACCOUNTS["accounts_receivable"] if kind=="sale" else DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"]
            supplier_account = str(item.get("supplier_account") or default_party_account).strip()
            party_account=self._ensure_party_account(db,party)
            if kind=="purchase" and (not item.get("supplier_account") or supplier_account==DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"]):
                supplier_account=party_account
            elif kind=="sale" and not item.get("supplier_account") and item.get("source_file")=="Sales Invoice":
                supplier_account=party_account
            import chart_extra
            default_vat = chart_extra.SALES_VAT if kind=="sale" else chart_extra.EXPORT_VAT if item.get("vat_use")=="export" else \
                chart_extra.EXPENSE_VAT if self._entry_type(item)=="expenses" else chart_extra.PURCHASE_VAT
            vat_account = str(item.get("vat_account") or default_vat).strip()
            expense_account = str(item.get("expense_account") or (DEFAULT_LEBANESE_ACCOUNTS["sales"] if kind=="sale" else EXPENSE_ACCOUNT_9)).strip()
            expense_no_vat_account=str(item.get("expense_no_vat_account") or EXPENSE_NO_VAT_ACCOUNT_9).strip()
            supplier_side=self._side(item.get("supplier_side"),"D" if kind=="sale" else "C")
            vat_side=self._side(item.get("vat_side"),"C" if kind=="sale" else "D")
            expense_side=self._side(item.get("expense_side"),"C" if kind=="sale" else "D")
            expense_no_vat_side=self._side(item.get("expense_no_vat_side"),"D")
            account_definitions = [
                (supplier_account, "Client Account" if kind=="sale" else "Supplier Account", "asset" if kind=="sale" else "liability"),
                (vat_account, "Output VAT Account" if kind=="sale" else "VAT Account", "liability" if kind=="sale" else "asset"),
                (expense_account, "Sales Revenue Account" if kind=="sale" else ("Asset Account" if entry_type=="assets" else "Expense Account"), "income" if kind=="sale" else ("asset" if entry_type=="assets" else "expense")),
                (expense_no_vat_account,"Expenses without VAT","expense"),
            ]
            for code, name, account_type in account_definitions:
                db.execute(
                    "INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",
                    (code, name, account_type),
                )
            due_date = self._invoice_due_date(item, party)
            amount_paid = Decimal(str(item.get("amount_paid") or 0))
            if amount_paid < 0 or amount_paid > total:
                raise ValueError("Amount paid must be between zero and invoice total")
            payment_status = "paid" if amount_paid == total and total > 0 else "partial" if amount_paid > 0 else "unpaid"
            debit_override=item.get("debit"); credit_override=item.get("credit")
            cur = db.execute("""INSERT INTO invoices(invoice_number,kind,invoice_date,party_id,currency,exchange_rate,subtotal,deductible_subtotal,non_deductible_subtotal,vat,total,status,currency_issue,supplier_account,vat_account,expense_account,entry_type,debit_override,credit_override,supplier_side,vat_side,expense_side,expense_no_vat_account,expense_no_vat_side,source_file,source_row,due_date,payment_status,amount_paid,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                str(item["invoice_number"]), kind, item.get("invoice_date"), party["id"], item.get("currency", "USD"),
                str(item.get("exchange_rate", 1)), str(subtotal),str(deductible),str(non_deductible),str(vat), str(total),
                status, currency_issue, supplier_account, vat_account, expense_account,entry_type,
                None if debit_override in (None,"") else str(Decimal(str(debit_override))),None if credit_override in (None,"") else str(Decimal(str(credit_override))),
                supplier_side,vat_side,expense_side,expense_no_vat_account,expense_no_vat_side,
                item.get("source_file"), item.get("source_row"), due_date, payment_status, str(amount_paid), user_id, utcnow()))
            invoice_id = cur.lastrowid
            branch_id=self._branch_id(db,item)
            db.execute("UPDATE invoices SET payment_method=?,description=?,branch_id=? WHERE id=?",(str(item.get("payment_method") or "").strip() or None,str(item.get("description") or "").strip() or None,branch_id,invoice_id))
            entry_number = f"INV-{invoice_id}"
            entry = db.execute("INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,branch_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (entry_number, item.get("invoice_date"), f"{entry_type.replace('_',' ').title()} {item['invoice_number']}", "invoice", invoice_id, item.get("currency", "USD"),branch_id, user_id, utcnow()))
            if kind == "sale":
                lines = [self._line_for_side(supplier_account,total,self._side(item.get("supplier_side"),"D")),
                         self._line_for_side(expense_account,subtotal,self._side(item.get("expense_side"),"C")),
                         self._line_for_side(vat_account,vat,self._side(item.get("vat_side"),"C"))]
            else:
                splits=item.get("expense_splits")
                if splits:
                    expense_lines=[]
                    for acct,amt in splits:
                        code=str(acct).strip(); value=Decimal(str(amt))
                        if not value: continue
                        db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(code,"Expense Account","expense"))
                        expense_lines.append(self._line_for_side(code,value,expense_side))
                    lines = expense_lines+[self._line_for_side(expense_no_vat_account,non_deductible,expense_no_vat_side),self._line_for_side(vat_account,vat,vat_side),self._line_for_side(supplier_account,total,supplier_side)]
                else:
                    lines = [self._line_for_side(expense_account,deductible,expense_side),self._line_for_side(expense_no_vat_account,non_deductible,expense_no_vat_side),self._line_for_side(vat_account,vat,vat_side),self._line_for_side(supplier_account,total,supplier_side)]
            lines=[line for line in lines if Decimal(str(line[1])) or Decimal(str(line[2]))]
            difference = sum(x[1] for x in lines) - sum(x[2] for x in lines)
            if kind=="sale" and any(item.get(key) for key in ("supplier_side","expense_side","vat_side")) and difference:
                raise ValueError("Sales posting accounts are unbalanced. Check their Debit/Credit selections.")
            if difference > 0:
                lines.append((DEFAULT_LEBANESE_ACCOUNTS["import_variance"], 0, difference))
            elif difference < 0:
                lines.append((DEFAULT_LEBANESE_ACCOUNTS["import_variance"], -difference, 0))
            for code, debit, credit in lines:
                db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,debit,credit) VALUES(?,?,?,?,?)", (entry.lastrowid, self._account_id(db, code), party["id"], str(debit), str(credit)))
            debit_total = sum(x[1] for x in lines); credit_total = sum(x[2] for x in lines)
            if debit_total != credit_total:
                raise ValueError(f"Unbalanced journal entry for invoice {item['invoice_number']}")
            treatment,use=self._vat_classification(item,kind)
            db.execute("UPDATE invoices SET vat_treatment=?,vat_use=? WHERE id=?",(treatment,use,invoice_id))
            department_id,project_id=self._dimension_ids(db,item)
            if department_id or project_id:
                db.execute("UPDATE invoices SET department_id=?,project_id=? WHERE id=?",(department_id,project_id,invoice_id))
                db.execute("UPDATE journal_lines SET department_id=?,project_id=? WHERE entry_id=?",(department_id,project_id,entry.lastrowid))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)", (user_id, "import", "invoice", invoice_id, json.dumps({"source_file": item.get("source_file"), "source_row": item.get("source_row")}), utcnow()))
            return invoice_id

    def create_manual_invoice(self, item, line_items, user_id):
        if not isinstance(line_items, list) or not line_items:
            raise ValueError("Add at least one invoice item")
        normalized = []
        deductible_total = Decimal("0"); non_deductible_total=Decimal("0")
        vat_total = Decimal("0"); expense_splits={}
        for index, line in enumerate(line_items, start=1):
            description = str(line.get("description") or "").strip()
            if not description:
                raise ValueError(f"Item {index}: description is required")
            try:
                quantity = Decimal(str(line.get("quantity") or 0))
                unit_price = Decimal(str(line.get("unit_price") or 0))
                vat_rate = Decimal(str(line.get("vat_rate") if line.get("vat_rate") not in (None, "") else 11))
            except Exception as exc:
                raise ValueError(f"Item {index}: invalid quantity, price, or VAT rate") from exc
            if quantity <= 0 or unit_price < 0 or vat_rate < 0:
                raise ValueError(f"Item {index}: values cannot be negative and quantity must be above zero")
            calculated_subtotal = (quantity * unit_price).quantize(Decimal("0.01"))
            supplied_deductible=line.get("deductible_subtotal") if line.get("deductible_subtotal") not in (None,"") else line.get("subtotal")
            deductible=calculated_subtotal if supplied_deductible in (None,"") else Decimal(str(supplied_deductible)).quantize(Decimal("0.01"))
            non_deductible=Decimal(str(line.get("non_deductible_subtotal") or 0)).quantize(Decimal("0.01")); subtotal=deductible+non_deductible
            if min(deductible,non_deductible) < 0:
                raise ValueError(f"Item {index}: total before VAT cannot be negative")
            supplied_vat = line.get("vat")
            vat = (deductible * vat_rate / Decimal("100")).quantize(Decimal("0.01")) if supplied_vat in (None, "") else Decimal(str(supplied_vat)).quantize(Decimal("0.01"))
            if vat < 0:
                raise ValueError(f"Item {index}: VAT cannot be negative")
            total = subtotal + vat
            line_expense_account=str(line.get("expense_account") or "").split(" - ",1)[0].strip() or None
            normalized.append((description, quantity, unit_price, subtotal,deductible,non_deductible,vat_rate,vat,total,str(line.get("item_code") or "").strip() or None))
            deductible_total+=deductible; non_deductible_total+=non_deductible
            vat_total += vat
            if line_expense_account and deductible:
                expense_splits[line_expense_account]=expense_splits.get(line_expense_account,Decimal("0"))+deductible
        invoice = dict(item)
        if not str(invoice.get("invoice_number") or "").strip():
            invoice["invoice_number"] = self.next_invoice_number(invoice.get("kind", "sale"), invoice.get("invoice_date"))
        invoice["deductible_subtotal"]=float(deductible_total); invoice["non_deductible_subtotal"]=float(non_deductible_total)
        invoice["subtotal"] = float(deductible_total+non_deductible_total)
        invoice["vat"] = float(vat_total)
        invoice["total"] = float(deductible_total+non_deductible_total+vat_total)
        # per-item cost-account routing: split the expense side by each line's own account, remainder on the invoice default
        if expense_splits and self._entry_type(invoice)!="sales":
            default_account=str(invoice.get("expense_account") or EXPENSE_ACCOUNT_9).strip()
            routed=sum(expense_splits.values()); remainder=deductible_total-routed
            splits=[(acct,amount) for acct,amount in expense_splits.items()]
            if remainder>Decimal("0.005") or remainder<Decimal("-0.005"):
                splits.append((default_account,remainder))
            invoice["expense_splits"]=[(acct,str(amount)) for acct,amount in splits if amount]
        if self._entry_type(invoice)!="sales":
            raw_lines=[self._line_for_side(invoice.get("expense_account") or EXPENSE_ACCOUNT_9,deductible_total,self._side(invoice.get("expense_side"),"D")),
                self._line_for_side(invoice.get("expense_no_vat_account") or EXPENSE_NO_VAT_ACCOUNT_9,non_deductible_total,self._side(invoice.get("expense_no_vat_side"),"D")),
                self._line_for_side(invoice.get("vat_account") or VAT_ACCOUNT_9,vat_total,self._side(invoice.get("vat_side"),"D")),
                self._line_for_side(invoice.get("supplier_account") or DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"],deductible_total+non_deductible_total+vat_total,self._side(invoice.get("supplier_side"),"C"))]
            debit=sum(Decimal(str(line[1])) for line in raw_lines); credit=sum(Decimal(str(line[2])) for line in raw_lines)
            if abs(debit-credit)>=Decimal("0.005"):
                needed=f"Credit {debit-credit}" if debit>credit else f"Debit {credit-debit}"
                raise ValueError(f"Journal Voucher is unbalanced. Total Debit {debit}; Total Credit {credit}; Remaining {needed}")
        invoice_id = self.import_invoice(invoice, user_id)
        with self.connect() as db:
            if str(invoice.get("source_file") or "")=="Journal Voucher":
                db.execute("UPDATE journal_entries SET source_type='journal_voucher' WHERE source_type='invoice' AND source_id=?",(invoice_id,))
            db.executemany("""INSERT INTO invoice_items(invoice_id,description,quantity,unit_price,subtotal,deductible_subtotal,non_deductible_subtotal,vat_rate,vat,total,item_code)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""", [
                (invoice_id,description,str(quantity),str(unit_price),str(subtotal),str(deductible),str(non_deductible),str(vat_rate),str(vat),str(total),item_code)
                for description,quantity,unit_price,subtotal,deductible,non_deductible,vat_rate,vat,total,item_code in normalized
            ])
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id, "manual_entry", "invoice", invoice_id, json.dumps({"items": len(normalized)}), utcnow()))
        self._store_invoice_format(invoice_id, item, line_items)
        if any(line.get("item_code") for line in line_items):
            import inventory
            try: inventory.issue_for_invoice(self, invoice_id, line_items, user_id)
            except Exception:
                self.delete_invoice(invoice_id, user_id); raise
        return invoice_id

    def delete_invoice(self,invoice_id,user_id):
        with self.connect() as db:
            invoice=db.execute("SELECT * FROM invoices WHERE id=?",(int(invoice_id),)).fetchone()
            if not invoice: raise KeyError(invoice_id)
            self._assert_period_open(invoice["invoice_date"])
            details=dict(invoice)
            db.execute("DELETE FROM journal_entries WHERE source_type IN ('invoice','journal_voucher') AND source_id=?",(int(invoice_id),))
            db.execute("DELETE FROM journal_entries WHERE source_type='vat_reclass' AND entry_number=?",(f"VATND-INV-{int(invoice_id)}",))
            import inventory
            inventory.remove_invoice_documents(db,invoice_id)
            db.execute("DELETE FROM invoices WHERE id=?",(int(invoice_id),))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"delete","invoice",int(invoice_id),json.dumps({"invoice_number":details.get("invoice_number"),"party_id":details.get("party_id"),"total":details.get("total")}),utcnow()))
        return {"deleted":int(invoice_id)}

    def mark_invoice_deleted(self, invoice_id, user_id):
        """Retain the document number and history while removing its accounting effect."""
        with self.connect() as db:
            invoice=db.execute("SELECT * FROM invoices WHERE id=?",(int(invoice_id),)).fetchone()
            if not invoice: raise KeyError(invoice_id)
            if invoice["status"]=="deleted": raise ValueError("Invoice is already deleted")
            self._assert_period_open(invoice["invoice_date"])
            if db.execute("SELECT 1 FROM payment_allocations WHERE invoice_id=? LIMIT 1",(int(invoice_id),)).fetchone():
                raise ValueError("Invoice has allocated payments. Remove the allocation before deleting it")
            if db.execute("SELECT 1 FROM invoices WHERE linked_invoice_id=? AND status NOT IN ('cancelled','deleted') LIMIT 1",(int(invoice_id),)).fetchone():
                raise ValueError("Invoice has linked documents. Resolve them before deleting it")
            import inventory
            inventory.remove_invoice_documents(db,invoice_id)
            db.execute("DELETE FROM journal_entries WHERE source_type IN ('invoice','journal_voucher','invoice_reversal') AND source_id=?",(int(invoice_id),))
            db.execute("DELETE FROM journal_entries WHERE source_type='vat_reclass' AND entry_number=?",(f"VATND-INV-{int(invoice_id)}",))
            db.execute("UPDATE invoices SET status='deleted',cancelled_at=?,cancellation_reason='Deleted' WHERE id=?",(utcnow(),int(invoice_id)))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                       (user_id,"mark_deleted","invoice",int(invoice_id),json.dumps({"invoice_number":invoice["invoice_number"]}),utcnow()))
        return {"deleted":int(invoice_id),"invoice_number":invoice["invoice_number"]}

    def delete_journal_voucher(self,entry_id,user_id):
        with self.connect() as db:
            entry=db.execute("SELECT * FROM journal_entries WHERE id=?",(int(entry_id),)).fetchone()
            if not entry: raise KeyError(entry_id)
            self._assert_period_open(entry["entry_date"])
            invoice=None
            if entry["source_id"]:
                invoice=db.execute("SELECT id,source_file FROM invoices WHERE id=?",(entry["source_id"],)).fetchone()
            if entry["source_type"]!="journal_voucher" and (not invoice or invoice["source_file"]!="Journal Voucher"):
                raise ValueError("Only Journal Voucher entries can be deleted here")
            details={"entry_number":entry["entry_number"],"description":entry["description"]}
            if invoice: db.execute("DELETE FROM invoices WHERE id=?",(invoice["id"],))
            db.execute("DELETE FROM journal_entries WHERE id=?",(int(entry_id),))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"delete","journal_voucher",int(entry_id),json.dumps(details),utcnow()))
        return {"deleted":int(entry_id)}

    def delete_opening_voucher(self,entry_id,user_id):
        with self.connect() as db:
            entry=db.execute("SELECT * FROM journal_entries WHERE id=?",(int(entry_id),)).fetchone()
            if not entry: raise KeyError(entry_id)
            if entry["source_type"]!="opening": raise ValueError("Only opening vouchers can be deleted here")
            details={"entry_number":entry["entry_number"],"description":entry["description"]}
            db.execute("DELETE FROM journal_entries WHERE id=?",(int(entry_id),))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"delete","opening_voucher",int(entry_id),json.dumps(details),utcnow()))
        return {"deleted":int(entry_id)}

    def save_journal_voucher(self,item,lines,user_id,entry_id=None):
        date=str(item.get("entry_date") or "").strip(); self._assert_period_open(date)
        description=str(item.get("description") or "").strip() or f"Journal Voucher {str(item.get('entry_number') or '').strip() or 'Entry'}"
        currency=str(item.get("currency") or "USD").upper()
        if not date or not description or currency not in self.currency_codes(): raise ValueError("Enter voucher date, description, and currency")
        if not isinstance(lines,list) or len(lines)<2: raise ValueError("Journal Voucher requires at least two lines")
        normalized=[]; total_debit=Decimal("0"); total_credit=Decimal("0")
        voucher_type=str(item.get("voucher_type") or "01").strip()[:2] or "01"
        for index,line in enumerate(lines,1):
            code=str(line.get("account_code") or "").split(" - ",1)[0].strip()
            doe_basis=str(item.get("doe_basis") or "").upper() if voucher_type=="07" else ""
            extra=self._doe_line_amounts(line,code,doe_basis,currency,index) if doe_basis else self._voucher_line_amounts(line,currency,date,index)
            if extra: debit,credit=extra["debit"],extra["credit"]
            else:
                try: debit=Decimal(str(line.get("debit") or 0)); credit=Decimal(str(line.get("credit") or 0))
                except Exception as exc: raise ValueError(f"Line {index}: Debit and Credit must be numbers") from exc
            if not code or min(debit,credit)<0 or (debit>0 and credit>0) or (debit==0 and credit==0): raise ValueError(f"Line {index}: choose an account and enter either Debit or Credit")
            normalized.append((code,str(line.get("description") or "").strip(),debit,credit,extra,line)); total_debit+=debit; total_credit+=credit
        if abs(total_debit-total_credit)>=Decimal("0.005"): raise ValueError(f"Journal Voucher is unbalanced. Debit {total_debit}; Credit {total_credit}; Remaining {abs(total_debit-total_credit)}")
        if voucher_type=="07":
            from chart_extra import EXCHANGE_GAIN_ACCOUNT, EXCHANGE_LOSS_ACCOUNT
            # A DOE voucher revalues one or more class 4/5 accounts (Automatic DOE posts one voucher per
            # currency with all its accounts) against exchange gain 7751 (credit) / loss 6751 (debit).
            affected=[(code,debit,credit) for code,_desc,debit,credit,_extra,_raw in normalized if code.startswith(("4","5"))]
            offsets=[(code,debit,credit) for code,_desc,debit,credit,_extra,_raw in normalized if code in (EXCHANGE_GAIN_ACCOUNT,EXCHANGE_LOSS_ACCOUNT)]
            if not affected or not offsets or len(affected)+len(offsets)!=len(normalized):
                raise ValueError("DOE needs class 4 or 5 accounts and the exchange gain (7751) or loss (6751) account only")
            for code,debit,credit in offsets:
                if (code==EXCHANGE_GAIN_ACCOUNT and not credit) or (code==EXCHANGE_LOSS_ACCOUNT and not debit):
                    raise ValueError("DOE gains credit 7751 and losses debit 6751")
        with self.connect() as db:
            branch_id=self._branch_id(db,item)
            if entry_id:
                existing=db.execute("SELECT * FROM journal_entries WHERE id=? AND source_type='journal_voucher'",(int(entry_id),)).fetchone()
                if not existing: raise KeyError(entry_id)
                self._assert_period_open(existing["entry_date"]); voucher_number=str(item.get("entry_number") or existing["entry_number"]).strip()
                duplicate=db.execute("SELECT 1 FROM journal_entries WHERE entry_number=? AND id<>?",(voucher_number,int(entry_id))).fetchone()
                if duplicate: raise ValueError("Voucher number already exists")
                db.execute("UPDATE journal_entries SET entry_number=?,entry_date=?,description=?,currency=?,branch_id=?,voucher_type=? WHERE id=?",(voucher_number,date,description,currency,branch_id,voucher_type,int(entry_id)))
                db.execute("DELETE FROM journal_lines WHERE entry_id=?",(int(entry_id),)); saved_id=int(entry_id); action="update"
            else:
                voucher_number=str(item.get("entry_number") or "").strip()
                if not voucher_number:
                    year=self._date_year(date); prefix=f"JV-{year}-"; row=db.execute("SELECT entry_number FROM journal_entries WHERE entry_number LIKE ? ORDER BY entry_number DESC LIMIT 1",(prefix+"%",)).fetchone()
                    sequence=int(row["entry_number"].rsplit("-",1)[-1])+1 if row else 1; voucher_number=f"{prefix}{sequence:06d}"
                if db.execute("SELECT 1 FROM journal_entries WHERE entry_number=?",(voucher_number,)).fetchone(): raise ValueError("Voucher number already exists")
                saved_id=db.execute("INSERT INTO journal_entries(entry_number,entry_date,description,source_type,currency,branch_id,created_by,created_at,voucher_type) VALUES(?,?,?,?,?,?,?,?,?)",(voucher_number,date,description,"journal_voucher",currency,branch_id,user_id,utcnow(),voucher_type)).lastrowid; action="create"
            for code,line_description,debit,credit,extra,raw_line in normalized:
                department_id,project_id=self._dimension_ids(db,{"department":raw_line.get("department") or item.get("department"),"project":raw_line.get("project") or item.get("project"),
                    "department_id":raw_line.get("department_id") or item.get("department_id"),"project_id":raw_line.get("project_id") or item.get("project_id")})
                account=db.execute("SELECT id FROM accounts WHERE code=?",(code,)).fetchone()
                if not account: raise ValueError(f"Account {code} was not found")
                party=db.execute("SELECT id FROM parties WHERE account_number=?",(code,)).fetchone()
                db.execute("""INSERT INTO journal_lines(entry_id,account_id,party_id,description,debit,credit,line_currency,amount,amount_lbp,amount_usd,rate_lbp,rate_usd,due_date,reference)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(saved_id,account["id"],party["id"] if party else None,line_description,str(debit),str(credit),
                    *( (extra["line_currency"],str(extra["amount"]),str(extra["amount_lbp"]),str(extra["amount_usd"]),str(extra["rate_lbp"]),str(extra["rate_usd"]),extra["due_date"],extra["reference"]) if extra else (None,)*8 )))
                if department_id or project_id:
                    db.execute("UPDATE journal_lines SET department_id=?,project_id=? WHERE id=last_insert_rowid()",(department_id,project_id))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",(user_id,action,"journal_voucher",saved_id,json.dumps({"entry_number":voucher_number,"debit":str(total_debit),"credit":str(total_credit)}),utcnow()))
        return self.journal_voucher_detail(saved_id)

    def suggested_rates(self,currency,date=None):
        """BRAINS convention: LBP rate = LBP for 1 unit; USD rate = USD for 1 unit (for LBP lines: LBP per 1 USD)."""
        currency=str(currency or "USD").upper(); day=date or datetime.now().strftime("%d-%m-%Y")
        usd_lbp=self._converted_amount(Decimal("1"),"USD","LBP",day)
        if currency=="LBP": return {"currency":"LBP","rate_lbp":Decimal("1"),"rate_usd":usd_lbp}
        if currency=="USD": return {"currency":"USD","rate_lbp":usd_lbp,"rate_usd":Decimal("1")}
        return {"currency":currency,"rate_lbp":self._converted_amount(Decimal("1"),currency,"LBP",day),"rate_usd":self._converted_amount(Decimal("1"),currency,"USD",day)}

    def doe_candidates_usd(self, posting_date):
        """Class 4/5 balances kept in LBP or another non-USD currency, with their USD equivalent (carrying USD)
        as of a date, for a DOE in the USD books. USD accounts need no USD DOE and are not listed."""
        day=iso_date(posting_date)
        normal="CASE WHEN e.entry_date GLOB '??-??-????' THEN substr(e.entry_date,7,4)||'-'||substr(e.entry_date,4,2)||'-'||substr(e.entry_date,1,2) ELSE e.entry_date END"
        with self.connect() as db:
            lines=[dict(row) for row in db.execute(f"""SELECT a.code,a.name_en,e.currency voucher_currency,e.voucher_type,e.source_type,
                e.entry_date,COALESCE(j.line_currency,e.currency) line_currency,j.amount,j.amount_usd,j.debit,j.credit
                FROM journal_lines j JOIN journal_entries e ON e.id=j.entry_id JOIN accounts a ON a.id=j.account_id
                LEFT JOIN invoices i ON e.source_type='invoice' AND i.id=e.source_id
                WHERE (a.code LIKE '4%' OR a.code LIKE '5%') AND {normal}<=?
                AND (e.source_type!='invoice' OR i.status='posted') ORDER BY a.code,e.id,j.id""",(day,))]
        accounts={}
        for line in lines:
            code=line["code"]; item=accounts.setdefault(code,{"name":line["name_en"],"currencies":set(),"balance":Decimal("0"),"carrying_usd":Decimal("0")})
            signed=Decimal("1") if Decimal(str(line["debit"] or 0))>0 else Decimal("-1")
            doe=line["source_type"]=="journal_voucher" and line["voucher_type"]=="07"
            native=Decimal(str(line["amount"] or 0)) if line["amount"] not in (None,"") else abs(Decimal(str(line["debit"] or 0))-Decimal(str(line["credit"] or 0)))
            if line["amount_usd"] not in (None,""): usd=Decimal(str(line["amount_usd"]))
            elif line["voucher_currency"]=="USD": usd=abs(Decimal(str(line["debit"] or 0))-Decimal(str(line["credit"] or 0)))
            else: usd=self._converted_amount(native,line["line_currency"],"USD",line["entry_date"]) if native else Decimal("0")
            item["carrying_usd"]+=signed*usd
            if doe: continue  # DOE lines only move equivalents, never the account's own balance
            if native<=0: continue
            item["currencies"].add(line["line_currency"]); item["balance"]+=signed*native
        results=[]; skipped=[]; rates={}
        for code,item in sorted(accounts.items()):
            if len(item["currencies"])!=1:
                if len(item["currencies"])>1: skipped.append(code)
                continue
            currency=next(iter(item["currencies"]))
            if currency=="USD" or not item["balance"]: continue
            if currency not in rates: rates[currency]=Decimal(str(self.suggested_rates(currency,posting_date)["rate_usd"]))
            results.append({"account":code,"name":item["name"],"currency":currency,"balance":str(item["balance"]),"carrying_usd":str(item["carrying_usd"]),
                            "suggested_rate":str(rates[currency])})
        return {"items":results,"skipped_accounts":skipped,"basis":"USD"}

    def doe_candidates(self, posting_date, basis="LBP"):
        if str(basis or "LBP").upper()=="USD": return self.doe_candidates_usd(posting_date)
        """Foreign class 4/5 balances and their original LBP carrying amounts as of a date.

        Local-currency activity is ignored except prior DOE corrections. Accounts with
        multiple foreign currencies are excluded because their DOE corrections cannot
        be assigned to one currency without an explicit allocation.
        """
        day=iso_date(posting_date)
        normal="CASE WHEN e.entry_date GLOB '??-??-????' THEN substr(e.entry_date,7,4)||'-'||substr(e.entry_date,4,2)||'-'||substr(e.entry_date,1,2) ELSE e.entry_date END"
        with self.connect() as db:
            lines=[dict(row) for row in db.execute(f"""SELECT a.code,a.name_en,e.currency voucher_currency,e.voucher_type,e.source_type,
                e.entry_date,COALESCE(j.line_currency,e.currency) line_currency,j.amount,j.amount_lbp,j.debit,j.credit
                FROM journal_lines j JOIN journal_entries e ON e.id=j.entry_id JOIN accounts a ON a.id=j.account_id
                LEFT JOIN invoices i ON e.source_type='invoice' AND i.id=e.source_id
                WHERE (a.code LIKE '4%' OR a.code LIKE '5%') AND {normal}<=?
                AND (e.source_type!='invoice' OR i.status='posted') ORDER BY a.code,e.id,j.id""",(day,))]
        groups={}; doe_corrections={}; currencies_by_account={}
        for line in lines:
            code=line["code"]; currency=line["line_currency"]
            signed=Decimal("1") if Decimal(str(line["debit"] or 0))>0 else Decimal("-1")
            if currency=="LBP":
                if line["source_type"]=="journal_voucher" and line["voucher_type"]=="07" and line["voucher_currency"]=="LBP":
                    doe_corrections[code]=doe_corrections.get(code,Decimal("0"))+Decimal(str(line["debit"] or 0))-Decimal(str(line["credit"] or 0))
                continue
            native=Decimal(str(line["amount"] or 0)) if line["amount"] not in (None,"") else abs(Decimal(str(line["debit"] or 0))-Decimal(str(line["credit"] or 0)))
            if native<=0: continue
            key=(code,currency); currencies_by_account.setdefault(code,set()).add(currency)
            item=groups.setdefault(key,{"account":code,"name":line["name_en"],"currency":currency,"balance":Decimal("0"),"carrying_lbp":Decimal("0")})
            item["balance"]+=signed*native
            if line["amount_lbp"] not in (None,""):
                item["carrying_lbp"]+=signed*Decimal(str(line["amount_lbp"]))
            else:
                item["carrying_lbp"]+=signed*self._converted_amount(native,currency,"LBP",line["entry_date"])
        results=[]; skipped=[]; rates={}
        for (account,currency),item in sorted(groups.items()):
            if len(currencies_by_account[account])>1:
                if account not in skipped: skipped.append(account)
                continue
            if not item["balance"]: continue
            item["carrying_lbp"]+=doe_corrections.get(account,Decimal("0"))
            if currency not in rates: rates[currency]=Decimal(str(self.suggested_rates(currency,posting_date)["rate_lbp"]))
            results.append({**item,"balance":str(item["balance"]),"carrying_lbp":str(item["carrying_lbp"]),"suggested_rate":str(rates[currency])})
        return {"items":results,"skipped_accounts":skipped}

    def _doe_line_amounts(self,line,code,basis,voucher_currency,index):
        """DOE line that changes ONLY the equivalent of the revaluation currency (LBP or USD books).

        - LBP DOE: the class 4/5 line is an LBP correction (as before) and the USD equivalent is left alone.
        - USD DOE: the class 4/5 line keeps its own currency with amount 0 (the foreign / LBP balance does
          not change) and only its USD equivalent moves.
        - The gain 7751 / loss 6751 line is in the revaluation currency only."""
        from chart_extra import EXCHANGE_GAIN_ACCOUNT, EXCHANGE_LOSS_ACCOUNT
        if basis not in ("LBP","USD"): raise ValueError("DOE can be revalued in LBP or USD")
        if voucher_currency!=basis: raise ValueError(f"A {basis} DOE voucher must be in {basis}")
        try: debit=Decimal(str(line.get("debit") or 0)); credit=Decimal(str(line.get("credit") or 0))
        except Exception as exc: raise ValueError(f"Line {index}: Debit and Credit must be numbers") from exc
        value=(debit or credit).quantize(Decimal("0.01"))
        zero=Decimal("0"); offset=code in (EXCHANGE_GAIN_ACCOUNT,EXCHANGE_LOSS_ACCOUNT)
        native=str(line.get("native_currency") or basis).upper()
        if offset or basis=="LBP": line_currency=basis if offset else "LBP"; amount=value
        else: line_currency=native; amount=zero
        return {"debit":value if debit else zero,"credit":value if credit else zero,"line_currency":line_currency,"amount":amount,
                "amount_lbp":value if basis=="LBP" else zero,"amount_usd":value if basis=="USD" else zero,"rate_lbp":zero,"rate_usd":zero,
                "due_date":None,"reference":str(line.get("reference") or "").strip() or None}

    def _voucher_line_amounts(self,line,voucher_currency,date,index):
        """Lines entered like BRAINS: currency, D/C, amount in the account currency and LBP / USD rates."""
        if line.get("amount") in (None,"") or not line.get("side"): return None
        side=str(line.get("side")).strip().upper()[:1]
        if side not in ("D","C"): raise ValueError(f"Line {index}: D/C must be D or C")
        currency=str(line.get("line_currency") or voucher_currency).upper()
        if currency not in self.currency_codes(): raise ValueError(f"Line {index}: invalid currency")
        try:
            amount=Decimal(str(line.get("amount")).replace(",","")); suggested=self.suggested_rates(currency,date)
            rate_lbp=Decimal(str(line.get("rate_lbp") or suggested["rate_lbp"]).replace(",","")); rate_usd=Decimal(str(line.get("rate_usd") or suggested["rate_usd"]).replace(",",""))
        except Exception as exc: raise ValueError(f"Line {index}: amount and rates must be numbers") from exc
        if amount<=0 or rate_lbp<=0 or rate_usd<=0: raise ValueError(f"Line {index}: amount and rates must be above zero")
        amount_lbp=(amount*rate_lbp).quantize(Decimal("0.01")); amount_usd=((amount/rate_usd) if currency=="LBP" else amount*rate_usd).quantize(Decimal("0.001"))
        if currency==voucher_currency: value=amount
        elif voucher_currency=="USD": value=amount_usd
        elif voucher_currency=="LBP": value=amount_lbp
        else: raise ValueError(f"Line {index}: a {voucher_currency} voucher can only contain {voucher_currency} lines. Use a USD or LBP voucher to mix currencies")
        value=value.quantize(Decimal("0.01"))
        due=str(line.get("due_date") or "").strip()
        return {"debit":value if side=="D" else Decimal("0"),"credit":value if side=="C" else Decimal("0"),"line_currency":currency,"amount":amount,
                "amount_lbp":amount_lbp,"amount_usd":amount_usd,"rate_lbp":rate_lbp,"rate_usd":rate_usd,"due_date":display_date(due) if due else None,
                "reference":str(line.get("reference") or "").strip() or None}

    def journal_voucher_detail(self,entry_id):
        with self.connect() as db:
            entry=db.execute("SELECT * FROM journal_entries WHERE id=? AND source_type='journal_voucher'",(int(entry_id),)).fetchone()
            if not entry: raise KeyError(entry_id)
            lines=[dict(row) for row in db.execute("""SELECT a.code account_code,a.name_en account_name,COALESCE(j.description,'') description,
                CAST(j.debit AS REAL) debit,CAST(j.credit AS REAL) credit,j.line_currency,CAST(j.amount AS REAL) amount,CAST(j.amount_lbp AS REAL) amount_lbp,
                CAST(j.amount_usd AS REAL) amount_usd,CAST(j.rate_lbp AS REAL) rate_lbp,CAST(j.rate_usd AS REAL) rate_usd,j.due_date,j.reference,
                d.code department,pr.code project
                FROM journal_lines j JOIN accounts a ON a.id=j.account_id LEFT JOIN departments d ON d.id=j.department_id LEFT JOIN projects pr ON pr.id=j.project_id
                WHERE j.entry_id=? ORDER BY j.id""",(int(entry_id),))]
        return {"voucher":dict(entry),"lines":lines}

    def update_invoice(self, invoice_id, item, user_id):
        result=self._update_invoice_base(invoice_id, item, user_id)
        with self.connect() as db:
            row=db.execute("SELECT kind,vat_recoverable,status FROM invoices WHERE id=?",(int(invoice_id),)).fetchone()
        if row and row["kind"]=="purchase" and not row["vat_recoverable"] and row["status"] not in ("cancelled","deleted"):
            self.set_vat_recoverable("invoice",invoice_id,False,user_id)
        return result

    def _update_invoice_base(self, invoice_id, item, user_id):
        required = ("invoice_number", "invoice_date", "party_name", "kind", "currency")
        missing = [field for field in required if not str(item.get(field) or "").strip()]
        if missing:
            raise ValueError("Missing fields: " + ", ".join(missing))
        self._assert_period_open(item.get("invoice_date"))
        entry_type=self._entry_type(item); kind = "sale" if entry_type=="sales" else "purchase"
        currency = str(item["currency"]).upper()
        if currency not in self.currency_codes():
            raise ValueError("Currency must be USD, EUR, LBP, or AED")
        try:
            raw_subtotal=Decimal(str(item.get("subtotal") or 0))
            deductible=Decimal(str(item.get("deductible_subtotal") if item.get("deductible_subtotal") not in (None,"") else raw_subtotal))
            non_deductible=Decimal(str(item.get("non_deductible_subtotal") or 0)); subtotal=deductible+non_deductible
            vat = Decimal(str(item.get("vat") or 0))
            total = Decimal(str(item.get("total") or 0))
        except Exception as exc:
            raise ValueError("Before VAT, VAT, and Total must be valid numbers") from exc
        if min(subtotal, vat, total) < 0:
            raise ValueError("Amounts cannot be negative")
        if total != subtotal + vat:
            raise ValueError("Total must equal Before VAT plus VAT")
        supplier_account = str(item.get("supplier_account") or DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"]).strip()
        import chart_extra
        vat_account = str(item.get("vat_account") or (chart_extra.SALES_VAT if str(item.get("kind","")).lower() in ("sale","sales") else chart_extra.EXPENSE_VAT if self._entry_type(item)=="expenses" else chart_extra.PURCHASE_VAT)).strip()
        expense_account = str(item.get("expense_account") or EXPENSE_ACCOUNT_9).strip()
        expense_no_vat_account=str(item.get("expense_no_vat_account") or EXPENSE_NO_VAT_ACCOUNT_9).strip()
        supplier_side=self._side(item.get("supplier_side"),"C"); vat_side=self._side(item.get("vat_side"),"D"); expense_side=self._side(item.get("expense_side"),"D"); expense_no_vat_side=self._side(item.get("expense_no_vat_side"),"D")
        debit_override=Decimal(str(item.get("debit") or 0)); credit_override=Decimal(str(item.get("credit") or 0))
        if debit_override<0 or credit_override<0: raise ValueError("D and C cannot be negative")
        status = str(item.get("status") or "posted").strip().lower()
        if status not in ("posted", "review"):
            raise ValueError("Status must be posted or review")
        due_date = None
        amount_paid = Decimal(str(item.get("amount_paid") or 0))
        if amount_paid < 0 or amount_paid > total:
            raise ValueError("Amount paid must be between zero and invoice total")
        payment_status = "paid" if amount_paid == total and total > 0 else "partial" if amount_paid > 0 else "unpaid"
        with self.connect() as db:
            existing = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not existing:
                raise KeyError(invoice_id)
            if existing["status"] in ("cancelled","deleted"):
                raise ValueError("Cancelled or deleted invoices cannot be edited")
            party_kind = "customer" if kind == "sale" else "supplier"
            party_name = str(item["party_name"]).strip()
            db.execute("INSERT OR IGNORE INTO parties(kind,name,currency) VALUES(?,?,?)", (party_kind, party_name, currency))
            party = db.execute("SELECT * FROM parties WHERE kind=? AND name=?", (party_kind, party_name)).fetchone()
            due_date = self._invoice_due_date(item, party)
            party_account = self._ensure_party_account(db, party)
            if kind == "purchase" and supplier_account == DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"] and party_account:
                supplier_account = party_account
            elif kind == "sale" and (not item.get("supplier_account") or supplier_account==DEFAULT_LEBANESE_ACCOUNTS["accounts_receivable"]):
                supplier_account = party_account
            for code, name, account_type in (
                (supplier_account, "Client Account" if kind=="sale" else "Supplier Account", "asset" if kind=="sale" else "liability"),
                (vat_account, "Output VAT Account" if kind=="sale" else "VAT Account", "liability" if kind=="sale" else "asset"),
                (expense_account, "Sales Revenue Account" if kind=="sale" else ("Asset Account" if entry_type=="assets" else "Expense Account"), "income" if kind=="sale" else ("asset" if entry_type=="assets" else "expense")),
                (expense_no_vat_account,"Expenses without VAT","expense"),
            ):
                db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)", (code, name, account_type))
            branch_id=self._branch_id(db,item)
            db.execute("""UPDATE invoices SET invoice_number=?,kind=?,invoice_date=?,party_id=?,currency=?,
                subtotal=?,deductible_subtotal=?,non_deductible_subtotal=?,vat=?,total=?,status=?,supplier_account=?,vat_account=?,expense_account=?,entry_type=?,
                debit_override=?,credit_override=?,supplier_side=?,vat_side=?,expense_side=?,expense_no_vat_account=?,expense_no_vat_side=?,due_date=?,payment_status=?,amount_paid=?,payment_method=?,description=?,branch_id=? WHERE id=?""",
                (str(item["invoice_number"]).strip(), kind, str(item["invoice_date"]).strip(), party["id"], currency,
                 str(subtotal),str(deductible),str(non_deductible),str(vat), str(total), status, supplier_account, vat_account, expense_account,
                 entry_type,str(debit_override),str(credit_override),supplier_side,vat_side,expense_side,expense_no_vat_account,expense_no_vat_side,due_date, payment_status, str(amount_paid),str(item.get("payment_method") or "").strip() or None,str(item.get("description") or "").strip() or None,branch_id, invoice_id))
            entry = db.execute("SELECT id FROM journal_entries WHERE source_type IN ('invoice','journal_voucher') AND source_id=?", (invoice_id,)).fetchone()
            description = f"{entry_type.replace('_',' ').title()} {str(item['invoice_number']).strip()}"
            if entry:
                entry_id = entry["id"]
                db.execute("DELETE FROM journal_lines WHERE entry_id=?", (entry_id,))
                db.execute("UPDATE journal_entries SET entry_date=?,description=?,currency=?,branch_id=? WHERE id=?",
                           (str(item["invoice_date"]).strip(), description, currency,branch_id, entry_id))
            else:
                created = db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,branch_id,created_by,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (f"INV-{invoice_id}", str(item["invoice_date"]).strip(), description,
                    "invoice", invoice_id, currency,branch_id, user_id, utcnow()))
                entry_id = created.lastrowid
            if kind == "sale":
                lines = [(supplier_account, total, Decimal("0")), (expense_account, Decimal("0"), subtotal), (vat_account, Decimal("0"), vat)]
            else:
                lines=[self._line_for_side(expense_account,deductible,expense_side),self._line_for_side(expense_no_vat_account,non_deductible,expense_no_vat_side),self._line_for_side(vat_account,vat,vat_side),self._line_for_side(supplier_account,total,supplier_side)]
            lines=[line for line in lines if Decimal(str(line[1])) or Decimal(str(line[2]))]
            difference=sum(line[1] for line in lines)-sum(line[2] for line in lines)
            if difference>0: lines.append((DEFAULT_LEBANESE_ACCOUNTS["import_variance"],Decimal("0"),difference))
            elif difference<0: lines.append((DEFAULT_LEBANESE_ACCOUNTS["import_variance"],-difference,Decimal("0")))
            for code, debit, credit in lines:
                db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,debit,credit) VALUES(?,?,?,?,?)",
                           (entry_id, self._account_id(db, code), party["id"], str(debit), str(credit)))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                       (user_id, "update", "invoice", invoice_id, json.dumps({"fields": sorted(item.keys())}), utcnow()))
            row = db.execute("""SELECT i.id,i.invoice_number,i.invoice_date,p.name party_name,i.kind,i.currency,
                i.subtotal,i.deductible_subtotal,i.non_deductible_subtotal,i.vat,i.total,i.status,i.currency_issue,i.supplier_account,i.vat_account,
                i.expense_account,i.entry_type,i.debit_override,i.credit_override,i.supplier_side,i.vat_side,i.expense_side,i.expense_no_vat_account,i.expense_no_vat_side,i.source_row,i.due_date,i.payment_status,i.amount_paid,
                CAST(i.total AS REAL)-CAST(i.amount_paid AS REAL) outstanding
                FROM invoices i LEFT JOIN parties p ON p.id=i.party_id WHERE i.id=?""",
                (invoice_id,)).fetchone()
            return dict(row)

    def add_invoice_item(self, invoice_id, line, user_id):
        description = str(line.get("description") or "").strip()
        if not description:
            raise ValueError("Description is required")
        try:
            quantity = Decimal(str(line.get("quantity") or 0))
            unit_price = Decimal(str(line.get("unit_price") or 0))
            subtotal = Decimal(str(line.get("subtotal") if line.get("subtotal") not in (None, "") else quantity * unit_price))
            vat_rate = Decimal(str(line.get("vat_rate") if line.get("vat_rate") not in (None, "") else 11))
            vat = Decimal(str(line.get("vat") if line.get("vat") not in (None, "") else subtotal * vat_rate / Decimal("100")))
        except Exception as exc:
            raise ValueError("Invalid item amount") from exc
        if quantity <= 0 or min(unit_price, subtotal, vat, vat_rate) < 0:
            raise ValueError("Item values cannot be negative and quantity must be above zero")
        subtotal = subtotal.quantize(Decimal("0.01")); vat = vat.quantize(Decimal("0.01"))
        total = subtotal + vat
        with self.connect() as db:
            row = db.execute("""SELECT i.*,p.name party_name FROM invoices i
                LEFT JOIN parties p ON p.id=i.party_id WHERE i.id=?""", (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            invoice = dict(row)
        updated_values = {
            "invoice_number": invoice["invoice_number"], "invoice_date": invoice["invoice_date"],
            "party_name": invoice["party_name"], "kind": invoice["kind"], "entry_type":invoice.get("entry_type") or invoice["kind"], "currency": invoice["currency"],
            "subtotal": str(Decimal(str(invoice["subtotal"] or 0)) + subtotal),
            "deductible_subtotal":str(Decimal(str(invoice.get("deductible_subtotal") or 0))+subtotal),
            "non_deductible_subtotal":str(Decimal(str(invoice.get("non_deductible_subtotal") or 0))),
            "vat": str(Decimal(str(invoice["vat"] or 0)) + vat),
            "total": str(Decimal(str(invoice["total"] or 0)) + total),
            "supplier_account": invoice["supplier_account"], "vat_account": invoice["vat_account"],
            "expense_account": invoice["expense_account"], "status": "posted",
            "expense_no_vat_account":invoice.get("expense_no_vat_account",EXPENSE_NO_VAT_ACCOUNT_9),
            "supplier_side":invoice.get("supplier_side","C"),"vat_side":invoice.get("vat_side","D"),"expense_side":invoice.get("expense_side","D"),"expense_no_vat_side":invoice.get("expense_no_vat_side","D"),"payment_method":invoice.get("payment_method",""),
            "due_date": invoice.get("due_date"), "amount_paid": invoice.get("amount_paid", 0),"debit":invoice.get("debit",0),"credit":invoice.get("credit",0),
        }
        updated = self.update_invoice(invoice_id, updated_values, user_id)
        with self.connect() as db:
            db.execute("""INSERT INTO invoice_items(invoice_id,description,quantity,unit_price,subtotal,deductible_subtotal,non_deductible_subtotal,vat_rate,vat,total)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (invoice_id,description,str(quantity),str(unit_price),str(subtotal),str(subtotal),"0",str(vat_rate),str(vat),str(total)))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                       (user_id, "add_item", "invoice", invoice_id, json.dumps({"description": description}), utcnow()))
        return updated

    def cancel_invoice(self, invoice_id, reason, user_id):
        reason = str(reason or "").strip()
        if not reason:
            raise ValueError("Cancellation reason is required")
        with self.connect() as db:
            invoice = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not invoice:
                raise KeyError(invoice_id)
            if invoice["status"] in ("cancelled","deleted"):
                raise ValueError("Cancelled or deleted invoices cannot be cancelled again")
            self._assert_period_open(invoice["invoice_date"])
            original = db.execute("SELECT * FROM journal_entries WHERE source_type IN ('invoice','journal_voucher') AND source_id=?", (invoice_id,)).fetchone()
            if not original:
                raise ValueError("Invoice journal entry was not found")
            reverse = db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?)""", (f"REV-{invoice_id}", invoice["invoice_date"],
                f"Cancellation of invoice {invoice['invoice_number']}", "invoice_reversal", invoice_id,
                invoice["currency"], user_id, utcnow()))
            lines = db.execute("SELECT account_id,party_id,debit,credit FROM journal_lines WHERE entry_id=?", (original["id"],)).fetchall()
            for line in lines:
                db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,debit,credit) VALUES(?,?,?,?,?)",
                    (reverse.lastrowid, line["account_id"], line["party_id"], line["credit"], line["debit"]))
            db.execute("UPDATE invoices SET status='cancelled',cancelled_at=?,cancellation_reason=? WHERE id=?",
                       (utcnow(), reason, invoice_id))
            db.execute("DELETE FROM journal_entries WHERE source_type='vat_reclass' AND entry_number=?",(f"VATND-INV-{int(invoice_id)}",))
            import inventory
            inventory.remove_invoice_documents(db,invoice_id)
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                       (user_id,"cancel","invoice",invoice_id,json.dumps({"reason":reason}),utcnow()))
        return self.get_invoice(invoice_id)

    def duplicate_invoice(self, invoice_id, user_id):
        with self.connect() as db:
            row = db.execute("""SELECT i.*,p.name party_name FROM invoices i
                LEFT JOIN parties p ON p.id=i.party_id WHERE i.id=?""", (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            source = dict(row)
            items = [dict(item) for item in db.execute("SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id", (invoice_id,))]
        new_number = self.next_invoice_number(source["kind"], source["invoice_date"])
        payload = {key:source.get(key) for key in ("invoice_date","party_name","kind","entry_type","currency","exchange_rate",
            "subtotal","vat","total","supplier_account","vat_account","expense_account","expense_no_vat_account","supplier_side","vat_side","expense_side","expense_no_vat_side","due_date","payment_method")}
        payload.update({"debit":source.get("debit_override"),"credit":source.get("credit_override")})
        payload.update({"invoice_number":new_number,"amount_paid":0,"source_file":"Duplicated invoice","source_row":None})
        new_id = self.import_invoice(payload, user_id)
        if items:
            with self.connect() as db:
                db.executemany("""INSERT INTO invoice_items(invoice_id,description,quantity,unit_price,subtotal,deductible_subtotal,non_deductible_subtotal,vat_rate,vat,total)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""", [(new_id,item["description"],item["quantity"],item["unit_price"],item["subtotal"],
                    item.get("deductible_subtotal",item["subtotal"]),item.get("non_deductible_subtotal",0),item["vat_rate"],item["vat"],item["total"]) for item in items])
                db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                    (user_id,"duplicate","invoice",new_id,json.dumps({"source_invoice_id":invoice_id}),utcnow()))
        return self.get_invoice(new_id)

    def get_invoice(self, invoice_id):
        rows = self.list_invoices(limit=100000)
        row = next((item for item in rows if item["id"] == invoice_id), None)
        if not row:
            raise KeyError(invoice_id)
        return row

    def invoice_detail(self, invoice_id):
        invoice=self.get_invoice(invoice_id)
        with self.connect() as db:
            items=[dict(row) for row in db.execute("SELECT description,quantity,unit_price,subtotal,deductible_subtotal,non_deductible_subtotal,vat_rate,vat,total,item_code,unit,discount_percent,discount_amount,gross_amount FROM invoice_items WHERE invoice_id=? ORDER BY id",(invoice_id,))]
        return {"invoice":invoice,"items":items}

    def add_attachment(self, invoice_id, file_name, mime_type, content, user_id):
        if not file_name or not content:
            raise ValueError("Attachment file is required")
        if len(content) > 15 * 1024 * 1024:
            raise ValueError("Attachment cannot exceed 15 MB")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM invoices WHERE id=?", (invoice_id,)).fetchone():
                raise KeyError(invoice_id)
            result = db.execute("""INSERT INTO invoice_attachments(invoice_id,file_name,mime_type,content,uploaded_by,uploaded_at)
                VALUES(?,?,?,?,?,?)""", (invoice_id,file_name,mime_type or "application/octet-stream",content,user_id,utcnow()))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"attach","invoice",invoice_id,json.dumps({"file_name":file_name}),utcnow()))
            return result.lastrowid

    def list_attachments(self, invoice_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,file_name,mime_type,length(content) size,uploaded_at
                FROM invoice_attachments WHERE invoice_id=? ORDER BY id DESC""", (invoice_id,))]

    def get_attachment(self, attachment_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM invoice_attachments WHERE id=?", (attachment_id,)).fetchone()
            if not row: raise KeyError(attachment_id)
            return dict(row)

    @staticmethod
    def _document_date(value, label):
        text=str(value or "").strip()
        if not text: return None
        try: return display_date(iso_date(text))
        except ValueError: raise ValueError(f"{label} must be a date (DD-MM-YYYY)")

    def _document_fields(self,item):
        issue=self._document_date(item.get("issue_date"),"Issue date"); expiry=self._document_date(item.get("expiry_date"),"Expiry date")
        if issue and expiry and iso_date(expiry)<iso_date(issue): raise ValueError("Expiry date cannot be before the issue date")
        active=item.get("active",True); active=1 if str(active).strip().lower() not in ("0","false","no","") else 0
        return str(item.get("document_type") or "Other").strip() or "Other",issue,expiry,str(item.get("notes") or "").strip(),active

    def add_party_document(self,party_id,item,content,user_id):
        """Save a customer / supplier legal document. The file is optional: the type, the "applies" tick and
        the issue / expiry dates can be saved on their own and the scanned copy uploaded later."""
        file_name=str(item.get("file_name") or "").strip() if content else ""
        content=content or b""
        if len(content)>15*1024*1024: raise ValueError("Document cannot exceed 15 MB")
        document_type,issue,expiry,notes,active=self._document_fields(item)
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM parties WHERE id=?",(int(party_id),)).fetchone(): raise KeyError(party_id)
            result=db.execute("""INSERT INTO party_documents(party_id,document_type,issue_date,expiry_date,notes,file_name,mime_type,content,uploaded_by,uploaded_at,active)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(int(party_id),document_type,issue,expiry,notes,file_name,
                str(item.get("mime_type") or "application/octet-stream") if content else "",content,user_id,utcnow(),active))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"attach","party",int(party_id),json.dumps({"document_type":document_type,"file_name":file_name,"issue_date":issue,"expiry_date":expiry,"active":bool(active)}),utcnow()))
            return result.lastrowid

    def update_party_document(self,document_id,item,content,user_id):
        """Change a saved legal document: type, applies tick, issue / expiry dates, notes and (optionally) a new file."""
        document_type,issue,expiry,notes,active=self._document_fields(item)
        if content and len(content)>15*1024*1024: raise ValueError("Document cannot exceed 15 MB")
        with self.connect() as db:
            row=db.execute("SELECT party_id FROM party_documents WHERE id=?",(int(document_id),)).fetchone()
            if not row: raise KeyError(document_id)
            db.execute("UPDATE party_documents SET document_type=?,issue_date=?,expiry_date=?,notes=?,active=? WHERE id=?",
                (document_type,issue,expiry,notes,active,int(document_id)))
            if content:
                db.execute("UPDATE party_documents SET file_name=?,mime_type=?,content=?,uploaded_by=?,uploaded_at=? WHERE id=?",
                    (str(item.get("file_name") or "document").strip(),str(item.get("mime_type") or "application/octet-stream"),content,user_id,utcnow(),int(document_id)))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"update","party_document",int(document_id),json.dumps({"party_id":row["party_id"],"document_type":document_type,"issue_date":issue,"expiry_date":expiry,"active":bool(active),"new_file":bool(content)}),utcnow()))
            return int(document_id)

    def list_party_documents(self,party_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,party_id,document_type,issue_date,expiry_date,notes,file_name,mime_type,length(content) size,uploaded_at,active
                FROM party_documents WHERE party_id=? ORDER BY id DESC""",(int(party_id),))]

    def get_party_document(self,document_id):
        with self.connect() as db:
            row=db.execute("SELECT * FROM party_documents WHERE id=?",(int(document_id),)).fetchone()
            if not row: raise KeyError(document_id)
            return dict(row)

    def next_document_case_number(self,case_type,document_date):
        kind=str(case_type or "purchase").lower(); prefix={"purchase":"PUR","expense":"EXP","customs":"CUS"}.get(kind)
        if not prefix: raise ValueError("Case type must be Purchase, Expense, or Customs")
        year=datetime.now().year
        for pattern in ("%d-%m-%Y","%Y-%m-%d","%d%m%Y"):
            try: year=datetime.strptime(str(document_date),pattern).year; break
            except ValueError: pass
        with self.connect() as db:
            rows=db.execute("SELECT case_number FROM document_cases WHERE case_number LIKE ?",(f"{prefix}-{year}-%",)).fetchall()
        sequences=[]
        for row in rows:
            try: sequences.append(int(str(row["case_number"]).rsplit("-",1)[-1]))
            except ValueError: pass
        return f"{prefix}-{year}-{max(sequences,default=0)+1:06d}"

    def save_document_case(self,item,user_id):
        case_type=str(item.get("case_type") or "purchase").lower()
        if case_type not in ("purchase","expense","customs"): raise ValueError("Invalid document case type")
        document_date=str(item.get("document_date") or "").strip(); self._assert_period_open(document_date)
        party_id=int(item.get("party_id") or 0)
        currency=str(item.get("currency") or "USD").upper()
        if currency not in self.currency_codes(): raise ValueError("Invalid currency")
        amounts={key:Decimal(str(item.get(key) or 0)) for key in ("supplier_invoice_amount","freight","insurance","customs_duties","import_vat","broker_fees")}
        if min(amounts.values())<0: raise ValueError("Case amounts cannot be negative")
        if case_type!="customs":
            amounts["freight"]=amounts["insurance"]=amounts["customs_duties"]=amounts["broker_fees"]=Decimal("0")
        total=sum(amounts.values())
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM parties WHERE id=?",(party_id,)).fetchone(): raise ValueError("Choose a customer or supplier")
            case_number=str(item.get("case_number") or "").strip() or self.next_document_case_number(case_type,document_date)
            result=db.execute("""INSERT INTO document_cases(case_number,case_type,document_date,party_id,currency,reference,description,customs_declaration_no,broker_name,
                supplier_invoice_amount,freight,insurance,customs_duties,import_vat,broker_fees,total,status,supplier_account,expense_account,vat_account,branch_id,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(case_number,case_type,document_date,party_id,currency,str(item.get("reference") or ""),str(item.get("description") or ""),
                str(item.get("customs_declaration_no") or ""),str(item.get("broker_name") or ""),*[str(amounts[key]) for key in ("supplier_invoice_amount","freight","insurance","customs_duties","import_vat","broker_fees")],
                str(total),"draft",str(item.get("supplier_account") or ""),str(item.get("expense_account") or EXPENSE_ACCOUNT_9),str(item.get("vat_account") or VAT_ACCOUNT_9),self._branch_id(db,item),user_id,utcnow()))
            case_id=result.lastrowid
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",(user_id,"create","document_case",case_id,json.dumps({"case_number":case_number,"type":case_type}),utcnow()))
        return self.document_case(case_id)

    def add_case_attachment(self,case_id,role,file_name,mime_type,content,user_id):
        if not file_name or not content: raise ValueError("Choose a document file")
        if len(content)>15*1024*1024: raise ValueError("Document cannot exceed 15 MB")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM document_cases WHERE id=?",(int(case_id),)).fetchone(): raise KeyError(case_id)
            return db.execute("INSERT INTO case_attachments(case_id,document_role,file_name,mime_type,content,uploaded_by,uploaded_at) VALUES(?,?,?,?,?,?,?)",
                (int(case_id),str(role or "other"),str(file_name),str(mime_type or "application/octet-stream"),content,user_id,utcnow())).lastrowid

    def list_document_cases(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT c.*,p.name party_name,COALESCE(b.name,'Head Office') branch_name,
                (SELECT COUNT(*) FROM case_attachments a WHERE a.case_id=c.id) attachment_count
                FROM document_cases c LEFT JOIN parties p ON p.id=c.party_id LEFT JOIN branches b ON b.id=c.branch_id ORDER BY c.id DESC""")]

    def document_case(self,case_id):
        row=next((row for row in self.list_document_cases() if row["id"]==int(case_id)),None)
        if not row: raise KeyError(case_id)
        return row

    def list_case_attachments(self,case_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,document_role,file_name,mime_type,length(content) size,uploaded_at FROM case_attachments WHERE case_id=? ORDER BY id",(int(case_id),))]

    def get_case_attachment(self,attachment_id):
        with self.connect() as db:
            row=db.execute("SELECT * FROM case_attachments WHERE id=?",(int(attachment_id),)).fetchone()
            if not row: raise KeyError(attachment_id)
            return dict(row)

    def post_document_case(self,case_id,user_id):
        case=self.document_case(case_id)
        if case["status"]=="posted": raise ValueError("Document case is already posted")
        attachments=self.list_case_attachments(case_id)
        required={"purchase":{"supplier_invoice"},"expense":{"expense_document"},"customs":{"supplier_invoice","customs_declaration","broker_invoice"}}[case["case_type"]]
        missing=required-{row["document_role"] for row in attachments}
        if missing: raise ValueError("Attach required document(s): "+", ".join(sorted(missing)))
        base=Decimal(str(case["supplier_invoice_amount"]))+Decimal(str(case["freight"]))+Decimal(str(case["insurance"]))+Decimal(str(case["customs_duties"]))+Decimal(str(case["broker_fees"]))
        vat=Decimal(str(case["import_vat"])); items=[]
        components=(("Supplier invoice",case["supplier_invoice_amount"]),("Freight",case["freight"]),("Insurance",case["insurance"]),("Customs duties",case["customs_duties"]),("Customs broker fees",case["broker_fees"]))
        for description,amount in components:
            if Decimal(str(amount)):
                items.append({"description":description,"quantity":1,"unit_price":amount,"deductible_subtotal":amount,"vat_rate":0,"vat":0})
        if not items: raise ValueError("Enter an amount before posting")
        party=next(row for row in self.list_parties() if row["id"]==case["party_id"])
        invoice={"invoice_number":case["reference"] or case["case_number"],"invoice_date":case["document_date"],"party_name":party["name"],
            "kind":"expenses" if case["case_type"]=="expense" else "purchases","currency":case["currency"],"supplier_account":case["supplier_account"],
            "expense_account":case["expense_account"],"vat_account":case["vat_account"],"status":"posted","branch_id":case["branch_id"],
            "source_file":f'{case["case_type"].title()} Case',"description":case["description"]}
        if vat:
            items[0]["vat"]=str(vat); items[0]["vat_rate"]=str((vat/base*Decimal("100")) if base else 0)
        invoice_id=self.create_manual_invoice(invoice,items,user_id)
        with self.connect() as db:
            db.execute("UPDATE document_cases SET status='posted',invoice_id=? WHERE id=?",(invoice_id,int(case_id)))
            for row in db.execute("SELECT * FROM case_attachments WHERE case_id=?",(int(case_id),)):
                db.execute("INSERT INTO invoice_attachments(invoice_id,file_name,mime_type,content,uploaded_by,uploaded_at) VALUES(?,?,?,?,?,?)",
                    (invoice_id,row["file_name"],row["mime_type"],row["content"],user_id,utcnow()))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",(user_id,"post","document_case",int(case_id),json.dumps({"invoice_id":invoice_id}),utcnow()))
        return self.document_case(case_id)

    def invoice_history(self, invoice_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT l.id,l.action,l.details,l.created_at,u.username
                FROM audit_log l LEFT JOIN users u ON u.id=l.user_id
                WHERE l.entity='invoice' AND l.entity_id=? ORDER BY l.id DESC""", (invoice_id,))]

    def profit_and_loss(self, from_date=None, to_date=None, currency=None):
        # The year-end closing brings 6 & 7 to zero; the P&L must show the year before closing.
        conditions = ["a.type IN ('income','expense')", "NOT (e.source_type='year_close' OR (e.voucher_type='05' AND e.description LIKE 'CLOSING 6&7 - %'))"]
        parameters = []
        normalized_date = """CASE WHEN e.entry_date GLOB '??-??-????'
            THEN substr(e.entry_date,7,4)||'-'||substr(e.entry_date,4,2)||'-'||substr(e.entry_date,1,2)
            ELSE e.entry_date END"""
        if from_date: conditions.append(f"{normalized_date}>=?"); parameters.append(from_date)
        if to_date: conditions.append(f"{normalized_date}<=?"); parameters.append(to_date)
        if currency: conditions.append("e.currency=?"); parameters.append(currency)
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(f"""SELECT e.currency,a.code,a.name_en,a.type,
                SUM(CAST(j.debit AS REAL)) debit,SUM(CAST(j.credit AS REAL)) credit
                FROM journal_lines j JOIN journal_entries e ON e.id=j.entry_id JOIN accounts a ON a.id=j.account_id
                WHERE {' AND '.join(conditions)} GROUP BY e.currency,a.id ORDER BY e.currency,a.code""", parameters)]
        for row in rows:
            row["amount"] = (row["credit"] - row["debit"]) if row["type"] == "income" else (row["debit"] - row["credit"])
        return rows

    def close_fiscal_year(self, year, user_id):
        """Close classes 6 & 7 with a 'CLOSING 6&7' Journal Voucher (type 05) per currency."""
        import year_end
        return year_end.close_year(self, year, user_id)

    def list_fiscal_years(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM fiscal_years ORDER BY year DESC")]

    def reopen_fiscal_year(self,year,user_id):
        """Delete every closing of this year (old and new style) and open it again."""
        import year_end
        return year_end.reopen_year(self, year, user_id)

    def list_parties(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,kind,name,tax_number,mof_number,address,contact_number,currency,account_number,due_days,COALESCE(account_category,CASE WHEN kind='customer' THEN 'client' ELSE 'supplier' END) account_category FROM parties ORDER BY name,kind")]

    @staticmethod
    def _invoice_due_date(item, party):
        explicit = str(item.get("due_date") or "").strip()
        if explicit: return display_date(iso_date(explicit))
        days = int(party["due_days"] or 0)
        return display_date((datetime.strptime(iso_date(item["invoice_date"]), "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d"))

    def list_branches(self):
        with self.connect() as db: return [dict(row) for row in db.execute("SELECT id,name,active FROM branches WHERE active=1 ORDER BY name")]

    def save_branch(self,item,user_id):
        name=str(item.get("name") or "").strip()
        if not name: raise ValueError("Branch name is required")
        with self.connect() as db:
            db.execute("INSERT INTO branches(name,active) VALUES(?,1) ON CONFLICT(name) DO UPDATE SET active=1",(name,))
            row=db.execute("SELECT id,name,active FROM branches WHERE name=?",(name,)).fetchone()
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",(user_id,"save","branch",row["id"],json.dumps({"name":name}),utcnow()))
            return dict(row)

    def save_party(self, item, user_id):
        name=str(item.get("name") or "").strip(); category=str(item.get("account_category") or item.get("kind") or "client").strip().lower().replace(" ","_")
        if category not in ("client","customer","supplier","asset_supplier","other_payable","both"): raise ValueError("Invalid client/supplier account type")
        kind="customer" if category in ("client","customer") else "both" if category=="both" else "supplier"
        category="client" if category=="customer" else category
        currency=str(item.get("currency") or "USD").upper(); tax_number=str(item.get("tax_number") or "").strip() or None
        mof_number=str(item.get("mof_number") or "").strip() or None; address=str(item.get("address") or "").strip() or None; contact_number=str(item.get("contact_number") or "").strip() or None
        requested_account=str(item.get("account_number") or "").strip() or None
        try: due_days=int(str(item.get("due_days") if item.get("due_days") not in (None, "") else 0).strip())
        except ValueError as exc: raise ValueError("Due days must be a whole number") from exc
        if not 0 <= due_days <= 3650: raise ValueError("Due days must be between 0 and 3650")
        if requested_account and (not requested_account.isdigit() or len(requested_account) not in (4,9)): raise ValueError("Enter the first 4 digits for automatic numbering, or the full 9-digit account number")
        if not name or kind not in ("customer","supplier","both") or currency not in self.currency_codes():
            raise ValueError("Enter a valid name, type, and currency")
        with self.connect() as db:
            if requested_account and len(requested_account)==4:
                prefix=requested_account
                last=db.execute("SELECT account_number FROM parties WHERE account_number LIKE ? AND length(account_number)=9 ORDER BY CAST(account_number AS INTEGER) DESC LIMIT 1",(prefix+"%",)).fetchone()
                next_suffix=(int(last["account_number"][4:])+1) if last else 1
                if next_suffix>99999: raise ValueError(f"No account numbers remain under prefix {prefix}")
                requested_account=f"{prefix}{next_suffix:05d}"
            party_id=item.get("id")
            if party_id:
                if not db.execute("SELECT 1 FROM parties WHERE id=?",(int(party_id),)).fetchone(): raise KeyError(party_id)
                duplicate=db.execute("SELECT 1 FROM parties WHERE kind=? AND name=? AND id<>?",(kind,name,int(party_id))).fetchone()
                if duplicate: raise ValueError("A customer/supplier with this name and type already exists")
                if requested_account and db.execute("SELECT 1 FROM parties WHERE account_number=? AND id<>?",(requested_account,int(party_id))).fetchone(): raise ValueError("Account number already exists")
                db.execute("UPDATE parties SET kind=?,name=?,tax_number=?,mof_number=?,address=?,contact_number=?,currency=?,account_number=COALESCE(?,account_number),account_category=?,due_days=? WHERE id=?",(kind,name,tax_number,mof_number,address,contact_number,currency,requested_account,category,due_days,int(party_id)))
                row=db.execute("SELECT * FROM parties WHERE id=?",(int(party_id),)).fetchone()
            else:
                db.execute("""INSERT INTO parties(kind,name,tax_number,mof_number,address,contact_number,currency,due_days) VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(kind,name) DO UPDATE SET tax_number=excluded.tax_number,mof_number=excluded.mof_number,address=excluded.address,contact_number=excluded.contact_number,currency=excluded.currency,due_days=excluded.due_days""",
                    (kind,name,tax_number,mof_number,address,contact_number,currency,due_days))
                row=db.execute("SELECT * FROM parties WHERE kind=? AND name=?",(kind,name)).fetchone()
                db.execute("UPDATE parties SET account_category=? WHERE id=?",(category,row["id"])); row=db.execute("SELECT * FROM parties WHERE id=?",(row["id"],)).fetchone()
                if requested_account:
                    if db.execute("SELECT 1 FROM parties WHERE account_number=? AND id<>?",(requested_account,row["id"])).fetchone(): raise ValueError("Account number already exists")
                    db.execute("UPDATE parties SET account_number=? WHERE id=?",(requested_account,row["id"])); row=db.execute("SELECT * FROM parties WHERE id=?",(row["id"],)).fetchone()
            account_number=self._ensure_party_account(db,row)
            if account_number: row=db.execute("SELECT * FROM parties WHERE id=?",(row["id"],)).fetchone()
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"save","party",row["id"],json.dumps({"name":name,"kind":kind}),utcnow()))
            return dict(row)

    def add_payment(self, item, user_id):
        kind=str(item.get("kind") or "").strip(); date=str(item.get("payment_date") or "").strip()
        self._assert_period_open(date)
        if kind not in ("customer_receipt","supplier_payment"): raise ValueError("Invalid payment type")
        try: amount=Decimal(str(item.get("amount") or 0))
        except Exception as exc: raise ValueError("Invalid payment amount") from exc
        if amount<=0: raise ValueError("Payment amount must be above zero")
        currency=str(item.get("currency") or "USD").upper()
        cash_account=str(item.get("cash_account") or "531").strip()
        try: commission=Decimal(str(item.get("bank_commission") or 0))
        except Exception as exc: raise ValueError("Invalid bank commission amount") from exc
        if commission<0: raise ValueError("Bank commission cannot be negative")
        try: exchange_diff=Decimal(str(item.get("exchange_difference") or 0))
        except Exception as exc: raise ValueError("Invalid exchange difference amount") from exc
        import chart_extra
        commission_account=str(item.get("commission_account") or chart_extra.BANK_COMMISSION_ACCOUNT).split(" - ",1)[0].strip() or chart_extra.BANK_COMMISSION_ACCOUNT
        if not commission_account.isdigit() or len(commission_account)!=9 or not commission_account.startswith("6739"):
            raise ValueError("Bank commission account must be a 9-digit 6739 account")
        party_account=str(item.get("party_account") or (DEFAULT_LEBANESE_ACCOUNTS["accounts_receivable"] if kind=="customer_receipt" else DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"])).strip()
        party_id=int(item.get("party_id"))
        with self.connect() as db:
            party=db.execute("SELECT * FROM parties WHERE id=?",(party_id,)).fetchone()
            if not party: raise KeyError(party_id)
            supplier_account=self._ensure_party_account(db,party)
            if kind=="supplier_payment" and party_account==DEFAULT_LEBANESE_ACCOUNTS["accounts_payable"] and supplier_account:
                party_account=supplier_account
            if kind=="customer_receipt" and party_account==DEFAULT_LEBANESE_ACCOUNTS["accounts_receivable"] and supplier_account:
                party_account=supplier_account
            number=str(item.get("payment_number") or "").strip() or self._next_payment_number(db,kind,date)
            if db.execute("SELECT 1 FROM payments WHERE payment_number=?",(number,)).fetchone(): raise ValueError(f"Number {number} is already used")
            department_id,project_id=self._dimension_ids(db,item)
            db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(cash_account,"Cash / Bank Account","asset"))
            db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(party_account,"Party Control Account","asset" if kind=="customer_receipt" else "liability"))
            if commission: db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(commission_account,"Bank Commissions","expense"))
            if exchange_diff:
                db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(chart_extra.EXCHANGE_GAIN_ACCOUNT,"Gain on Exchange Difference","income"))
                db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(chart_extra.EXCHANGE_LOSS_ACCOUNT,"Loss on Exchange Difference","expense"))
            result=db.execute("""INSERT INTO payments(kind,party_id,payment_date,currency,amount,cash_account,party_account,reference,description,bank_commission,commission_account,exchange_difference,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(kind,party_id,date,currency,str(amount),cash_account,party_account,
                str(item.get("reference") or "").strip(),str(item.get("description") or "").strip(),str(commission),commission_account,str(exchange_diff),user_id,utcnow()))
            payment_id=result.lastrowid
            db.execute("UPDATE payments SET payment_number=?,payment_method=?,department_id=?,project_id=? WHERE id=?",
                (number,str(item.get("payment_method") or "Cash").strip(),department_id,project_id,payment_id))
            entry=db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",(number,date,str(item.get("description") or (("Receipt from " if kind=="customer_receipt" else "Payment to ")+party["name"])).strip(),"payment",payment_id,currency,user_id,utcnow()))
            party_settlement=amount+exchange_diff
            if kind=="customer_receipt": lines=[(cash_account,amount-commission,Decimal("0")),(party_account,Decimal("0"),party_settlement)]
            else: lines=[(party_account,party_settlement,Decimal("0")),(cash_account,Decimal("0"),amount+commission)]
            if commission: lines.append((commission_account,commission,Decimal("0")))
            balance=sum(d for _c,d,_cr in lines)-sum(cr for _c,_d,cr in lines)
            if balance>0: lines.append((chart_extra.EXCHANGE_GAIN_ACCOUNT,Decimal("0"),balance))
            elif balance<0: lines.append((chart_extra.EXCHANGE_LOSS_ACCOUNT,-balance,Decimal("0")))
            lines=[(code,debit,credit) for code,debit,credit in lines if Decimal(str(debit)) or Decimal(str(credit))]
            for code,debit,credit in lines:
                db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,debit,credit,department_id,project_id) VALUES(?,?,?,?,?,?,?)",
                    (entry.lastrowid,self._account_id(db,code),party_id,str(debit),str(credit),department_id,project_id))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"create","payment",payment_id,json.dumps({"kind":kind,"number":number,"amount":str(amount),"currency":currency}),utcnow()))
            return payment_id

    def list_payments(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT x.id,x.kind,x.payment_number,x.payment_date,x.party_id,p.name party_name,x.currency,
                CAST(x.amount AS REAL) amount,x.cash_account,x.party_account,x.reference,x.description,x.payment_method,
                CAST(x.bank_commission AS REAL) bank_commission,x.commission_account,CAST(x.exchange_difference AS REAL) exchange_difference,
                d.code department,pr.code project
                FROM payments x JOIN parties p ON p.id=x.party_id LEFT JOIN departments d ON d.id=x.department_id LEFT JOIN projects pr ON pr.id=x.project_id
                ORDER BY x.id DESC""")]

    def add_expense(self, item, user_id):
        date=str(item.get("expense_date") or "").strip(); self._assert_period_open(date)
        description=str(item.get("description") or "").strip()
        if not description: raise ValueError("Expense description is required")
        legacy=Decimal(str(item.get("subtotal") or 0)); with_vat=Decimal(str(item.get("with_vat_subtotal") if item.get("with_vat_subtotal") not in (None,"") else legacy)); without_vat=Decimal(str(item.get("without_vat_subtotal") or 0)); subtotal=with_vat+without_vat
        vat=Decimal(str(item.get("vat") or 0)); total=subtotal+vat
        if min(with_vat,without_vat,vat)<0 or total<=0: raise ValueError("Expense amounts must be valid")
        currency=str(item.get("currency") or "USD").upper(); expense_account=str(item.get("expense_account") or EXPENSE_ACCOUNT_9).strip()
        expense_without_vat_account=str(item.get("expense_without_vat_account") or EXPENSE_NO_VAT_ACCOUNT_9).strip()
        import chart_extra
        vat_account=str(item.get("vat_account") or chart_extra.EXPENSE_VAT).strip(); payment_account=str(item.get("payment_account") or "531").strip()
        expense_side=self._side(item.get("expense_side"),"D"); expense_without_vat_side=self._side(item.get("expense_without_vat_side"),"D")
        vat_side=self._side(item.get("vat_side"),"D"); payment_side=self._side(item.get("payment_side"),"C")
        with self.connect() as db:
            for code,name,typ in ((expense_account,"Expense with VAT","expense"),(expense_without_vat_account,"Expense without VAT","expense"),(vat_account,"VAT Receivable","asset"),(payment_account,"Cash / Bank Account","asset")):
                db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(code,name,typ))
            result=db.execute("""INSERT INTO expenses(expense_date,description,category,currency,subtotal,with_vat_subtotal,without_vat_subtotal,vat,total,expense_account,expense_without_vat_account,vat_account,payment_account,expense_side,expense_without_vat_side,vat_side,payment_side,reference,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(date,description,str(item.get("category") or "").strip(),currency,str(subtotal),str(with_vat),str(without_vat),str(vat),str(total),expense_account,expense_without_vat_account,vat_account,payment_account,expense_side,expense_without_vat_side,vat_side,payment_side,str(item.get("reference") or "").strip(),user_id,utcnow()))
            expense_id=result.lastrowid
            number=str(item.get("expense_number") or "").strip() or self._next_number(db,"expenses","expense_number","EXP",date)
            db.execute("UPDATE expenses SET expense_number=? WHERE id=?",(number,expense_id))
            entry=db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",(number if not db.execute("SELECT 1 FROM journal_entries WHERE entry_number=?",(number,)).fetchone() else f"EXP-{expense_id}",date,description,"expense",expense_id,currency,user_id,utcnow()))
            lines=[self._line_for_side(expense_account,with_vat,expense_side),self._line_for_side(expense_without_vat_account,without_vat,expense_without_vat_side),self._line_for_side(vat_account,vat,vat_side),self._line_for_side(payment_account,total,payment_side)]
            difference=sum(Decimal(str(line[1]))-Decimal(str(line[2])) for line in lines)
            if difference>0: lines.append((DEFAULT_LEBANESE_ACCOUNTS["import_variance"],Decimal("0"),difference))
            elif difference<0: lines.append((DEFAULT_LEBANESE_ACCOUNTS["import_variance"],-difference,Decimal("0")))
            for code,debit,credit in lines:
                if Decimal(str(debit or credit)):
                    db.execute("INSERT INTO journal_lines(entry_id,account_id,debit,credit) VALUES(?,?,?,?)",(entry.lastrowid,self._account_id(db,code),str(debit),str(credit)))
            db.execute("UPDATE expenses SET vat_use=? WHERE id=?",(self._vat_classification(item,"purchase")[1],expense_id))
            department_id,project_id=self._dimension_ids(db,item)
            if department_id or project_id:
                db.execute("UPDATE expenses SET department_id=?,project_id=? WHERE id=?",(department_id,project_id,expense_id))
                db.execute("UPDATE journal_lines SET department_id=?,project_id=? WHERE entry_id=?",(department_id,project_id,entry.lastrowid))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"create","expense",expense_id,json.dumps({"total":str(total),"currency":currency}),utcnow()))
        if str(item.get("vat_recoverable",True)).strip().lower() in ("0","false","no"):
            self.set_vat_recoverable("expense",expense_id,False,user_id)
        return expense_id

    def list_expenses(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,expense_date,description,category,currency,
                CAST(subtotal AS REAL) subtotal,CAST(with_vat_subtotal AS REAL) with_vat_subtotal,CAST(without_vat_subtotal AS REAL) without_vat_subtotal,CAST(vat AS REAL) vat,CAST(total AS REAL) total,
                expense_account,expense_without_vat_account,vat_account,payment_account,expense_side,expense_without_vat_side,vat_side,payment_side,reference,vat_recoverable,
                expense_number,department_id,project_id,vat_use,(SELECT COUNT(*) FROM expense_attachments a WHERE a.expense_id=expenses.id) attachment_count FROM expenses ORDER BY id DESC""")]

    def save_exchange_rate(self, item, user_id):
        date_from=str(item.get("date_from") or item.get("rate_date") or "").strip(); date_to=str(item.get("date_to") or date_from).strip()
        self._date_year(date_from); self._date_year(date_to)
        def parsed(value):
            for pattern in ("%d-%m-%Y","%Y-%m-%d"):
                try: return datetime.strptime(value,pattern).date()
                except ValueError: pass
            raise ValueError("Date must use DD-MM-YYYY")
        start=parsed(date_from); end=parsed(date_to)
        if end<start: raise ValueError("Date To cannot be before Date From")
        if (end-start).days>3660: raise ValueError("Exchange-rate period cannot exceed 10 years")
        source=str(item.get("from_currency") or "").upper(); target=str(item.get("to_currency") or "").upper()
        rate=Decimal(str(item.get("rate") or 0))
        if source not in self.currency_codes() or target not in self.currency_codes() or source==target or rate<=0:
            raise ValueError("Enter two different currencies and a positive rate")
        with self.connect() as db:
            rows=[]; current=start
            while current<=end:
                rows.append((current.strftime("%d-%m-%Y"),source,target,str(rate),user_id,utcnow())); current+=timedelta(days=1)
            db.executemany("INSERT INTO exchange_rate_samples(rate_date,from_currency,to_currency,rate,created_by,created_at) VALUES(?,?,?,?,?,?)", rows)
            averaged=[]
            for rate_date,_,_,_,_,_ in rows:
                values=[Decimal(sample["rate"]) for sample in db.execute("SELECT rate FROM exchange_rate_samples WHERE rate_date=? AND from_currency=? AND to_currency=?",(rate_date,source,target))]
                averaged.append((rate_date,source,target,str(sum(values)/len(values)),user_id,utcnow()))
            db.executemany("""INSERT INTO exchange_rates(rate_date,from_currency,to_currency,rate,created_by,created_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(rate_date,from_currency,to_currency) DO UPDATE SET rate=excluded.rate,
                created_by=excluded.created_by,created_at=excluded.created_at""",averaged)
            if (source,target) in (("EUR","USD"),("USD","LBP")):
                derived=[]
                for rate_date,_,_,_,_,_ in rows:
                    eur_usd=next((Decimal(x[3]) for x in averaged if x[0]==rate_date),None) if (source,target)==("EUR","USD") else None
                    usd_lbp=next((Decimal(x[3]) for x in averaged if x[0]==rate_date),None) if (source,target)==("USD","LBP") else None
                    if eur_usd is None:
                        found=db.execute("SELECT rate FROM exchange_rates WHERE rate_date=? AND from_currency='EUR' AND to_currency='USD'",(rate_date,)).fetchone()
                        eur_usd=Decimal(str(found["rate"])) if found else Decimal("1")
                    if usd_lbp is None:
                        found=db.execute("SELECT rate FROM exchange_rates WHERE rate_date=? AND from_currency='USD' AND to_currency='LBP'",(rate_date,)).fetchone()
                        usd_lbp=Decimal(str(found["rate"])) if found else Decimal("89500")
                    derived.append((rate_date,"EUR","LBP",str(eur_usd*usd_lbp),user_id,utcnow()))
                db.executemany("""INSERT INTO exchange_rates(rate_date,from_currency,to_currency,rate,created_by,created_at)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(rate_date,from_currency,to_currency) DO UPDATE SET rate=excluded.rate,
                    created_by=excluded.created_by,created_at=excluded.created_at""",derived)
        return {"date_from":date_from,"date_to":date_to,"days":len(rows),"calculation":"average of manually entered daily rates"}

    def list_exchange_rates(self):
        loaded=self.settings().get("exchange_history_loaded_through","")
        expected=(datetime.now().date()-datetime(2024,1,1).date()).days+1
        with self.connect() as db:
            eur_days=db.execute("SELECT COUNT(DISTINCT rate_date) count FROM exchange_rates WHERE from_currency='EUR' AND to_currency='USD'").fetchone()["count"]
        if loaded!=datetime.now().date().isoformat() or eur_days<expected: self.sync_historical_exchange_rates()
        self._ensure_automatic_rates()
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT r.id,r.rate_date,r.from_currency,r.to_currency,CAST(r.rate AS REAL) rate,r.created_at,
                (SELECT COUNT(*) FROM exchange_rate_samples s WHERE s.rate_date=r.rate_date AND s.from_currency=r.from_currency AND s.to_currency=r.to_currency) samples
                FROM exchange_rates r ORDER BY r.id DESC""")]

    def _ensure_automatic_rates(self):
        today=datetime.now().strftime("%d-%m-%Y")
        with self.connect() as db:
            db.execute("""INSERT INTO exchange_rates(rate_date,from_currency,to_currency,rate,created_at)
                VALUES(?,?,?,?,?) ON CONFLICT(rate_date,from_currency,to_currency) DO NOTHING""",
                (today,"USD","LBP","89500",utcnow()))
            exists=db.execute("SELECT 1 FROM exchange_rates WHERE rate_date=? AND from_currency='EUR' AND to_currency='USD'",(today,)).fetchone()
        if exists: return
        try:
            request=urllib.request.Request("https://api.frankfurter.app/latest?from=EUR&to=USD",headers={"User-Agent":"SaberAccounting/1.4"})
            with urllib.request.urlopen(request,timeout=5) as response: eur_usd=Decimal(str(json.loads(response.read().decode("utf-8"))["rates"]["USD"]))
            eur_lbp=(eur_usd*Decimal("89500")).quantize(Decimal("0.01"))
            with self.connect() as db:
                for source,target,rate in (("EUR","USD",eur_usd),("EUR","LBP",eur_lbp)):
                    db.execute("""INSERT INTO exchange_rates(rate_date,from_currency,to_currency,rate,created_at)
                        VALUES(?,?,?,?,?) ON CONFLICT(rate_date,from_currency,to_currency) DO NOTHING""",
                        (today,source,target,str(rate),utcnow()))
        except Exception:
            pass

    def sync_historical_exchange_rates(self):
        start=datetime(2024,1,1).date(); end=datetime.now().date(); collected={}
        previous=None
        for year in range(start.year,end.year+1):
            year_start=max(start,datetime(year,1,1).date()); year_end=min(end,datetime(year,12,31).date())
            url=f"https://api.frankfurter.app/{year_start.isoformat()}..{year_end.isoformat()}?from=EUR&to=USD"
            try:
                request=urllib.request.Request(url,headers={"User-Agent":"SaberAccounting/1.5"})
                with urllib.request.urlopen(request,timeout=10) as response: payload=json.loads(response.read().decode("utf-8"))
                for rate_date,values in payload.get("rates",{}).items(): collected[rate_date]=Decimal(str(values["USD"]))
            except Exception:
                continue
        if collected: previous=collected[min(collected)]
        else:
            try:
                request=urllib.request.Request("https://api.frankfurter.app/latest?from=EUR&to=USD",headers={"User-Agent":"SaberAccounting/1.5"})
                with urllib.request.urlopen(request,timeout=5) as response: previous=Decimal(str(json.loads(response.read().decode("utf-8"))["rates"]["USD"]))
            except Exception: previous=Decimal("1")
        rows=[]; current=start
        while current<=end:
            if current.isoformat() in collected: previous=collected[current.isoformat()]
            display=current.strftime("%d-%m-%Y"); eur_lbp=(previous*Decimal("89500")).quantize(Decimal("0.01"))
            rows.extend(((display,"USD","LBP","89500",utcnow()),(display,"EUR","USD",str(previous),utcnow()),(display,"EUR","LBP",str(eur_lbp),utcnow())))
            current+=timedelta(days=1)
        with self.connect() as db:
            db.executemany("""INSERT INTO exchange_rates(rate_date,from_currency,to_currency,rate,created_at)
                VALUES(?,?,?,?,?) ON CONFLICT(rate_date,from_currency,to_currency) DO NOTHING""",rows)
            db.execute("INSERT INTO app_settings(key,value) VALUES('exchange_history_loaded_through',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(end.isoformat(),))
        return {"from":start.isoformat(),"to":end.isoformat(),"days":(end-start).days+1,"rates":len(rows)}

    def restore_euro_rates(self):
        with self.connect() as db:
            db.execute("DELETE FROM exchange_rate_samples WHERE from_currency='EUR' AND to_currency IN ('USD','LBP')")
            db.execute("DELETE FROM exchange_rates WHERE from_currency='EUR' AND to_currency IN ('USD','LBP')")
            db.execute("DELETE FROM app_settings WHERE key='exchange_history_loaded_through'")
        return self.sync_historical_exchange_rates()

    def professional_dashboard(self):
        """Aggregate dashboard figures in SQLite instead of loading every expense and invoice."""
        metrics={}
        def metric(code):
            return metrics.setdefault(code,{"currency":code,"sales":0.0,"purchases":0.0,
                "expenses":0.0,"profit":0.0,"receivables":0.0,"payables":0.0,"overdue":0})
        with self.connect() as db:
            invoice_rows=db.execute("""SELECT kind,currency,
                SUM(CAST(subtotal AS REAL)) subtotal,
                SUM(CAST(total AS REAL)-CAST(COALESCE(amount_paid,'0') AS REAL)) outstanding
                FROM invoices WHERE status NOT IN ('cancelled','deleted')
                GROUP BY kind,currency""").fetchall()
            expense_rows=db.execute("""SELECT currency,SUM(CAST(subtotal AS REAL)) subtotal
                FROM expenses GROUP BY currency""").fetchall()
            # Preserve the existing DD-MM-YYYY due date interpretation.
            overdue_rows=db.execute("""SELECT currency,COUNT(*) overdue FROM invoices
                WHERE status NOT IN ('cancelled','deleted')
                  AND CAST(total AS REAL)>CAST(COALESCE(amount_paid,'0') AS REAL)
                  AND due_date GLOB '??-??-????'
                  AND substr(due_date,7,4)||'-'||substr(due_date,4,2)||'-'||substr(due_date,1,2)<?
                GROUP BY currency""",(datetime.now().strftime("%Y-%m-%d"),)).fetchall()
            monthly=[dict(row) for row in db.execute("""SELECT substr(CASE WHEN invoice_date GLOB '??-??-????' THEN substr(invoice_date,7,4)||'-'||substr(invoice_date,4,2)||'-'||substr(invoice_date,1,2) ELSE invoice_date END,1,7) month,
                currency,kind,SUM(CAST(subtotal AS REAL)) amount FROM invoices WHERE status NOT IN ('cancelled','deleted') GROUP BY month,currency,kind ORDER BY month""")]
        for row in invoice_rows:
            values=metric(row["currency"]); amount=float(row["subtotal"] or 0)
            outstanding=float(row["outstanding"] or 0)
            if row["kind"]=="sale":
                values["sales"]+=amount; values["receivables"]+=outstanding
            else:
                values["purchases"]+=amount; values["payables"]+=outstanding
        for row in expense_rows:
            metric(row["currency"])["expenses"]+=float(row["subtotal"] or 0)
        for row in overdue_rows:
            metric(row["currency"])["overdue"]=int(row["overdue"])
        for values in metrics.values():
            values["profit"]=values["sales"]-values["purchases"]-values["expenses"]
        return {"metrics":list(metrics.values()),"monthly":monthly}

    def _converted_amount(self, amount, source, target, rate_date):
        amount=Decimal(str(amount or 0)); source=str(source or "USD").upper(); target=str(target or source).upper()
        if source==target: return amount
        try: target_key=iso_date(rate_date).replace("-","")
        except ValueError: target_key=datetime.now().strftime("%Y%m%d")
        sortable="""CASE WHEN rate_date GLOB '??-??-????' THEN substr(rate_date,7,4)||substr(rate_date,4,2)||substr(rate_date,1,2)
            ELSE replace(rate_date,'-','') END"""
        def find_rate(frm,to):
            with self.connect() as rate_db:
                row=rate_db.execute(f"SELECT rate FROM exchange_rates WHERE from_currency=? AND to_currency=? AND {sortable}<=? ORDER BY {sortable} DESC,id DESC LIMIT 1",(frm,to,target_key)).fetchone()
                if row: return Decimal(str(row["rate"]))
                row=rate_db.execute(f"SELECT rate FROM exchange_rates WHERE from_currency=? AND to_currency=? AND {sortable}<=? ORDER BY {sortable} DESC,id DESC LIMIT 1",(to,frm,target_key)).fetchone()
                return Decimal("1")/Decimal(str(row["rate"])) if row and Decimal(str(row["rate"])) else None
        direct=find_rate(source,target)
        if direct is not None: return amount*direct
        usd_rates={"USD":Decimal("1"),"LBP":Decimal("1")/Decimal("89500"),
                   "EUR":find_rate("EUR","USD") or Decimal("1"),
                   "AED":Decimal("1")/Decimal("3.6725")}
        if source in usd_rates and target in usd_rates:
            to_usd=find_rate(source,"USD") or usd_rates[source]
            from_usd=find_rate("USD",target)
            if from_usd is None: from_usd=Decimal("1")/usd_rates[target]
            return amount*to_usd*from_usd
        # any other currency goes through USD (for example LBP -> USD -> SAR for payroll paid in SAR)
        first=find_rate(source,"USD") if source!="USD" else Decimal("1")
        if first is None and source in usd_rates: first=usd_rates[source]
        second=find_rate("USD",target) if target!="USD" else Decimal("1")
        if second is None and target in usd_rates: second=Decimal("1")/usd_rates[target]
        if first is not None and second is not None: return amount*first*second
        raise ValueError(f"No exchange rate available for {source} to {target} on {rate_date}")

    def statement_of_account(self, party_id, from_date=None, to_date=None, currency=None, include_opening=True, display_currency=None, branch_id=None):
        normalized_date = """CASE
            WHEN i.invoice_date GLOB '??-??-????'
                THEN substr(i.invoice_date,7,4)||'-'||substr(i.invoice_date,4,2)||'-'||substr(i.invoice_date,1,2)
            ELSE i.invoice_date END"""
        filters = ["i.party_id=?"]
        parameters = [party_id]
        if currency:
            filters.append("i.currency=?"); parameters.append(currency)
        if branch_id:
            filters.append("i.branch_id=?"); parameters.append(int(branch_id))
        if to_date:
            filters.append(f"{normalized_date} <= ?"); parameters.append(to_date)
        with self.connect() as db:
            party = db.execute("SELECT id,kind,name,currency FROM parties WHERE id=?", (party_id,)).fetchone()
            if not party:
                raise KeyError(party_id)
            rows = [dict(row) for row in db.execute(f"""SELECT i.id,i.invoice_number,i.invoice_date,i.kind,
                i.currency,i.total,i.branch_id FROM invoices i WHERE {' AND '.join(filters)}
                ORDER BY {normalized_date},i.id""", parameters)]
        opening = {}
        items = []
        for row in rows:
            normalized = row["invoice_date"]
            try:
                normalized = datetime.strptime(normalized, "%d-%m-%Y").strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                pass
            amount = Decimal(str(row["total"] or 0))
            output_currency=(display_currency or row["currency"]).upper()
            amount=self._converted_amount(amount,row["currency"],output_currency,normalized)
            debit = amount if row["kind"] == "sale" else Decimal("0")
            credit = amount if row["kind"] == "purchase" else Decimal("0")
            if from_date and normalized < from_date:
                if include_opening:
                    opening[output_currency] = opening.get(output_currency, Decimal("0")) + debit - credit
                continue
            items.append({**row, "source_currency":row["currency"],"currency":output_currency,
                          "description": f"{row['kind'].title()} invoice {row['invoice_number']}",
                          "debit": float(debit), "credit": float(credit)})
        balances = dict(opening)
        for row in items:
            code = row["currency"]
            balances[code] = balances.get(code, Decimal("0")) + Decimal(str(row["debit"])) - Decimal(str(row["credit"]))
            row["balance"] = float(balances[code])
        return {"party": dict(party), "opening": {key: float(value) for key,value in opening.items()}, "items": items}

    def list_invoices(self, limit=500):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT i.id,i.invoice_number,i.invoice_date,p.name party_name,i.kind,i.entry_type,i.currency,i.subtotal,i.deductible_subtotal,i.non_deductible_subtotal,i.vat,i.total,
                CASE WHEN i.status='deleted' THEN 0 ELSE COALESCE(CAST(i.debit_override AS REAL),CASE WHEN i.kind='sale' THEN CAST(i.total AS REAL) ELSE 0 END) END debit,
                CASE WHEN i.status='deleted' THEN 0 ELSE COALESCE(CAST(i.credit_override AS REAL),CASE WHEN i.kind='purchase' THEN CAST(i.total AS REAL) ELSE 0 END) END credit,
                i.status,i.currency_issue,i.supplier_account,i.vat_account,i.expense_account,i.expense_no_vat_account,
                i.supplier_side,i.vat_side,i.expense_side,i.expense_no_vat_side,i.source_row,
                i.due_date,i.payment_status,CAST(i.amount_paid AS REAL) amount_paid,i.payment_method,i.description,i.branch_id,COALESCE(b.name,'Head Office') branch_name,
                CAST(i.total AS REAL)-CAST(i.amount_paid AS REAL) outstanding,i.cancelled_at,i.cancellation_reason,
                (SELECT COUNT(*) FROM invoice_attachments x WHERE x.invoice_id=i.id) attachment_count,i.vat_recoverable,i.department_id,i.project_id,i.vat_treatment,i.vat_use,
                i.doc_subtype,i.invoice_discount_percent,i.invoice_discount_amount,i.notes
                FROM invoices i LEFT JOIN parties p ON p.id=i.party_id LEFT JOIN branches b ON b.id=i.branch_id ORDER BY i.id DESC LIMIT ?""", (limit,))]

    def list_accounts(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT a.code,a.name_en,a.name_ar,a.name_fr,a.type,
                p.code parent_code FROM accounts a LEFT JOIN accounts p ON p.id=a.parent_id
                ORDER BY CASE WHEN instr(a.code,'.')>0 THEN replace(a.code,'.','') ELSE a.code END""")]

    def next_party_account_number(self,prefix):
        """Next free 9-digit customer/supplier account under a 4-digit prefix (e.g. 4111 -> 411100007)."""
        prefix="".join(character for character in str(prefix or "") if character.isdigit())
        if len(prefix)!=4: raise ValueError("Enter the first 4 account digits")
        with self.connect() as db:
            used=[int(row["value"]) for row in db.execute("""SELECT account_number value FROM parties WHERE length(account_number)=9 AND account_number LIKE ?
                UNION SELECT code FROM accounts WHERE length(code)=9 AND code GLOB '[0-9]*' AND code LIKE ?""",(prefix+"%",prefix+"%")) if str(row["value"]).isdigit()]
        number=max(used,default=int(prefix+"00000"))+1
        if number>int(prefix+"99999"): raise ValueError(f"No account numbers remain under prefix {prefix}")
        return str(number).zfill(9)

    def next_account_number(self,prefix):
        prefix="".join(character for character in str(prefix or "") if character.isdigit())
        if len(prefix)!=4: raise ValueError("Enter the first 4 account digits")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM accounts WHERE code=?",(prefix,)).fetchone(): raise ValueError("The 4-digit parent account was not found")
            values=[int(row["code"]) for row in db.execute("SELECT code FROM accounts WHERE length(code)=9 AND code GLOB '[0-9]*' AND code LIKE ?",(prefix+"%",))]
        return str(max(values,default=int(prefix+"00000"))+1).zfill(9)

    def save_account(self,item,user_id):
        code=str(item.get("code") or "").strip(); name=str(item.get("name_en") or "").strip()
        account_type=str(item.get("type") or "expense").strip().lower(); parent=str(item.get("parent_code") or "").strip() or None
        if not name or account_type not in ("asset","liability","equity","income","expense"): raise ValueError("Enter a valid account name and type")
        with self.connect() as db:
            if len(code)==4 and code.isdigit():
                parent=parent or code; code=""
            parent_id=None
            if parent:
                row=db.execute("SELECT id FROM accounts WHERE code=?",(parent,)).fetchone()
                if not row: raise ValueError("Parent account was not found")
                parent_id=row["id"]
            if not code:
                prefix="".join(character for character in (parent or "") if character.isdigit())
                if prefix and len(prefix)<9:
                    if len(prefix)==4: code=self.next_account_number(prefix)
                    else:
                        values=[int(row["code"]) for row in db.execute("SELECT code FROM accounts WHERE length(code)=9 AND code GLOB '[0-9]*' AND code LIKE ?",(prefix+"%",))]
                        code=str(max(values,default=int(prefix+"0"*(9-len(prefix))))+1).zfill(9)
                else:
                    values=[int(row["code"]) for row in db.execute("SELECT code FROM accounts WHERE length(code)=9 AND code GLOB '[0-9]*'")]
                    code=str(max(values,default=100000000)+1).zfill(9)
            if len(code)!=9 or not code.isdigit(): raise ValueError("Enter a 4-digit prefix for automatic numbering, a full 9-digit number, or leave it blank")
            if db.execute("SELECT 1 FROM accounts WHERE code=?",(code,)).fetchone(): raise ValueError(f"Account {code} already exists; duplicate accounts are not allowed")
            db.execute("INSERT INTO accounts(code,name_en,type,parent_id) VALUES(?,?,?,?)",(code,name,account_type,parent_id))
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                (user_id,"save","account",json.dumps({"code":code,"name":name}),utcnow()))
        return {"code":code,"name_en":name,"type":account_type,"parent_code":parent}

    def rename_account(self,code,name,user_id):
        code=str(code or "").strip(); name=str(name or "").strip()
        if not name: raise ValueError("Account name is required")
        with self.connect() as db:
            row=db.execute("SELECT code FROM accounts WHERE code=?",(code,)).fetchone()
            if not row: raise KeyError(code)
            db.execute("UPDATE accounts SET name_en=? WHERE code=?",(name,code))
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                (user_id,"rename","account",json.dumps({"code":code,"name":name}),utcnow()))
        return {"code":code,"name_en":name}

    def dashboard(self):
        with self.connect() as db:
            rows = db.execute("""SELECT kind,currency,SUM(CAST(subtotal AS REAL)) subtotal,
                SUM(CAST(vat AS REAL)) vat,SUM(CAST(total AS REAL)) total,COUNT(*) count,
                SUM(CASE WHEN kind='sale' THEN CAST(total AS REAL) ELSE 0 END) debit,
                SUM(CASE WHEN kind='purchase' THEN CAST(total AS REAL) ELSE 0 END) credit
                FROM invoices WHERE status NOT IN ('cancelled','deleted') GROUP BY kind,currency""").fetchall()
            return [dict(r) for r in rows]

    def journal(self, from_date=None, to_date=None, currency=None, limit=5000, branch_id=None):
        """Return journal lines with a running balance per account and currency."""
        conditions = []
        parameters = []
        normalized_date = """CASE
            WHEN e.entry_date GLOB '??-??-????'
                THEN substr(e.entry_date,7,4)||'-'||substr(e.entry_date,4,2)||'-'||substr(e.entry_date,1,2)
            ELSE e.entry_date END"""
        if from_date:
            conditions.append(f"{normalized_date} >= ?")
            parameters.append(from_date)
        if to_date:
            conditions.append(f"{normalized_date} <= ?")
            parameters.append(to_date)
        if currency:
            conditions.append("e.currency = ?")
            parameters.append(currency)
        if branch_id:
            conditions.append("e.branch_id=?"); parameters.append(int(branch_id))
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        parameters.append(int(limit))
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(f"""SELECT e.id entry_id,e.entry_number,e.entry_date,
                e.description,e.source_type,e.source_id,e.voucher_type,e.currency,e.branch_id,COALESCE(b.name,'Head Office') branch_name,a.code account_code,a.name_en account_name,
                CASE WHEN e.source_type='payroll' THEN 'Payroll' WHEN e.source_type='expense' THEN 'Expenses'
                     WHEN e.source_type='journal_voucher' AND e.voucher_type='07' THEN 'DOE'
                     WHEN e.source_type='journal_voucher' THEN 'Journal Vouchers' WHEN e.source_type IN ('opening','year_close') THEN 'Opening / Closing'
                     WHEN e.source_type='invoice' AND i.kind='sale' THEN 'Sales'
                     WHEN e.source_type='invoice' AND COALESCE(i.entry_type,i.kind)='expenses' THEN 'Expenses'
                     WHEN e.source_type='invoice' THEN 'Purchases' ELSE 'Other' END journal_category,
                COALESCE(p.name,'') party_name,COALESCE(j.description,'') line_description,CAST(j.debit AS REAL) debit,CAST(j.credit AS REAL) credit,j.id line_id
                FROM journal_lines j JOIN journal_entries e ON e.id=j.entry_id
                JOIN accounts a ON a.id=j.account_id LEFT JOIN parties p ON p.id=j.party_id LEFT JOIN branches b ON b.id=e.branch_id
                LEFT JOIN invoices i ON e.source_type='invoice' AND i.id=e.source_id
                {where_clause}
                ORDER BY {normalized_date},e.id,j.id LIMIT ?""", parameters)]
        balances = {}
        for row in rows:
            key = (row["currency"], row["account_code"])
            balances[key] = balances.get(key, Decimal("0")) + Decimal(str(row["debit"] or 0)) - Decimal(str(row["credit"] or 0))
            row["balance"] = float(balances[key])
            row.pop("line_id", None)
        return rows

    def trial_balance(self, from_date=None, to_date=None, account_code=None, include_subaccounts=True, account_from=None, account_to=None, branch_id=None, posting_status="posted"):
        conditions = []
        parameters = []
        normalized_date = """CASE
            WHEN e.entry_date GLOB '??-??-????'
                THEN substr(e.entry_date,7,4)||'-'||substr(e.entry_date,4,2)||'-'||substr(e.entry_date,1,2)
            ELSE e.entry_date END"""
        if to_date:
            conditions.append(f"{normalized_date} <= ?")
            parameters.append(to_date)
        if account_code:
            conditions.append("a.code LIKE ?" if include_subaccounts else "a.code=?")
            parameters.append(str(account_code)+"%" if include_subaccounts else str(account_code))
        if account_from:
            conditions.append("CAST(REPLACE(a.code,'.','') AS INTEGER)>=?"); parameters.append(int(''.join(c for c in str(account_from) if c.isdigit())))
        if account_to:
            conditions.append("CAST(REPLACE(a.code,'.','') AS INTEGER)<=?"); parameters.append(int(''.join(c for c in str(account_to) if c.isdigit())))
        if branch_id: conditions.append("e.branch_id=?"); parameters.append(int(branch_id))
        if posting_status=="posted": conditions.append("(e.source_type!='invoice' OR i.status='posted')")
        elif posting_status=="review": conditions.append("(e.source_type='invoice' AND i.status='review')")
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.connect() as db:
            raw=[dict(r) for r in db.execute(f"""SELECT a.code,a.name_en,e.currency,e.entry_date,
                CAST(j.debit AS REAL) debit,CAST(j.credit AS REAL) credit
                FROM journal_lines j JOIN accounts a ON a.id=j.account_id JOIN journal_entries e ON e.id=j.entry_id
                LEFT JOIN invoices i ON e.source_type='invoice' AND i.id=e.source_id
                {where_clause} ORDER BY e.currency,a.code""",parameters)]
        totals={}
        for row in raw:
            key=(row["code"],row["name_en"],row["currency"])
            item=totals.setdefault(key,{"code":row["code"],"name_en":row["name_en"],"currency":row["currency"],
                "opening":0.0,"debit":0.0,"credit":0.0,"balance":0.0,"closing_balance":0.0,
                "usd_opening":0.0,"usd_debit":0.0,"usd_credit":0.0,"usd_balance":0.0,"usd_closing_balance":0.0,
                "lbp_opening":0.0,"lbp_debit":0.0,"lbp_credit":0.0,"lbp_balance":0.0,"lbp_closing_balance":0.0})
            date=str(row["entry_date"] or "")
            try: date=datetime.strptime(date,"%d-%m-%Y").strftime("%Y-%m-%d")
            except ValueError: pass
            debit=Decimal(str(row["debit"] or 0)); credit=Decimal(str(row["credit"] or 0))
            usd_d=self._converted_amount(debit,row["currency"],"USD",date); usd_c=self._converted_amount(credit,row["currency"],"USD",date)
            lbp_d=self._converted_amount(debit,row["currency"],"LBP",date); lbp_c=self._converted_amount(credit,row["currency"],"LBP",date)
            if from_date and date<from_date:
                item["opening"]+=float(debit-credit); item["usd_opening"]+=float(usd_d-usd_c); item["lbp_opening"]+=float(lbp_d-lbp_c)
                continue
            for field,value in (("debit",debit),("credit",credit),("usd_debit",usd_d),("usd_credit",usd_c),("lbp_debit",lbp_d),("lbp_credit",lbp_c)): item[field]+=float(value)
        for item in totals.values():
            item["balance"]=item["debit"]-item["credit"]
            item["usd_balance"]=item["usd_debit"]-item["usd_credit"]
            item["lbp_balance"]=item["lbp_debit"]-item["lbp_credit"]
            item["closing_balance"]=item["opening"]+item["balance"]
            item["usd_closing_balance"]=item["usd_opening"]+item["usd_balance"]
            item["lbp_closing_balance"]=item["lbp_opening"]+item["lbp_balance"]
        return list(totals.values())

    def general_ledger(self, account_code=None, from_date=None, to_date=None, currency=None):
        rows=self.journal(None,to_date,currency,limit=20000)
        if account_code: rows=[row for row in rows if row["account_code"]==str(account_code)]
        opening={}; items=[]; balances={}
        for row in rows:
            normalized=str(row["entry_date"] or "")
            try: normalized=datetime.strptime(normalized,"%d-%m-%Y").strftime("%Y-%m-%d")
            except ValueError: pass
            key=(row["currency"],row["account_code"])
            movement=Decimal(str(row["debit"] or 0))-Decimal(str(row["credit"] or 0))
            if from_date and normalized<from_date:
                opening[key]=opening.get(key,Decimal("0"))+movement; continue
            balances[key]=balances.get(key,opening.get(key,Decimal("0")))+movement
            row["balance"]=float(balances[key]); items.append(row)
        return {"opening":[{"currency":k[0],"account_code":k[1],"amount":float(v)} for k,v in opening.items()],"items":items}

    def balance_sheet(self, to_date=None, currency=None):
        conditions=["a.type IN ('asset','liability','equity')"]
        parameters=[]
        normalized_date="""CASE WHEN e.entry_date GLOB '??-??-????'
            THEN substr(e.entry_date,7,4)||'-'||substr(e.entry_date,4,2)||'-'||substr(e.entry_date,1,2)
            ELSE e.entry_date END"""
        if to_date: conditions.append(f"{normalized_date}<=?"); parameters.append(to_date)
        if currency: conditions.append("e.currency=?"); parameters.append(currency)
        with self.connect() as db:
            rows=[dict(row) for row in db.execute(f"""SELECT e.currency,a.code,a.name_en,a.type,
                SUM(CAST(j.debit AS REAL)) debit,SUM(CAST(j.credit AS REAL)) credit,
                SUM(CAST(j.debit AS REAL)-CAST(j.credit AS REAL)) balance
                FROM journal_lines j JOIN journal_entries e ON e.id=j.entry_id JOIN accounts a ON a.id=j.account_id
                WHERE {' AND '.join(conditions)} GROUP BY e.currency,a.id ORDER BY e.currency,a.type,a.code""",parameters)]
        pnl=self.profit_and_loss(None,to_date,currency)
        current_results={}
        for row in pnl:
            current_results.setdefault(row["currency"],Decimal("0"))
            amount=Decimal(str(row["amount"] or 0))
            current_results[row["currency"]]+=amount if row["type"]=="income" else -amount
        for code,result in current_results.items():
            if result:
                rows.append({"currency":code,"code":"13","name_en":"Current Year Net Result","type":"equity",
                    "debit":float(-result) if result<0 else 0.0,"credit":float(result) if result>0 else 0.0,"balance":float(-result)})
        return rows

    def cash_flow(self,from_date=None,to_date=None,currency=None):
        rows=self.journal(from_date,to_date,currency,limit=50000)
        cash_rows=[row for row in rows if str(row["account_code"]).startswith(("51","53"))]
        grouped={}
        for row in cash_rows:
            source=row.get("source_type") or "other"
            category={"invoice":"Operating - Invoices","expense":"Operating - Expenses","payroll":"Operating - Payroll",
                "payment":"Operating - Receipts / Payments","opening":"Opening Balance","year_close":"Year Closing"}.get(source,"Other Cash Movement")
            key=(row["currency"],category); item=grouped.setdefault(key,{"currency":row["currency"],"category":category,"inflow":0.0,"outflow":0.0,"net":0.0})
            movement=float(row["debit"] or 0)-float(row["credit"] or 0)
            if movement>=0: item["inflow"]+=movement
            else: item["outflow"]+=-movement
            item["net"]+=movement
        return sorted(grouped.values(),key=lambda row:(row["currency"],row["category"]))

    def aging_report(self,as_of_date=None,kind=None,currency=None):
        as_of=datetime.now().date()
        if as_of_date:
            parsed=False
            for pattern in ("%Y-%m-%d","%d-%m-%Y"):
                try: as_of=datetime.strptime(as_of_date,pattern).date(); parsed=True; break
                except ValueError: pass
            if not parsed: raise ValueError("As of Date must be DD-MM-YYYY")
        invoice_day="CASE WHEN i.invoice_date GLOB '??-??-????' THEN substr(i.invoice_date,7,4)||'-'||substr(i.invoice_date,4,2)||'-'||substr(i.invoice_date,1,2) ELSE i.invoice_date END"
        conditions=["i.status='posted'","CAST(i.total AS REAL)>CAST(i.amount_paid AS REAL)",f"{invoice_day}<=?"] ; parameters=[as_of.isoformat()]
        if kind in ("sale","purchase"): conditions.append("i.kind=?"); parameters.append(kind)
        if currency: conditions.append("i.currency=?"); parameters.append(currency)
        with self.connect() as db:
            rows=[dict(row) for row in db.execute(f"""SELECT i.id,i.invoice_number,i.invoice_date,i.due_date,i.kind,i.currency,p.name party_name,p.account_number,
                CAST(i.total AS REAL)-CAST(i.amount_paid AS REAL) outstanding FROM invoices i LEFT JOIN parties p ON p.id=i.party_id
                WHERE {' AND '.join(conditions)} ORDER BY p.name,i.due_date,i.invoice_date""",parameters)]
        for row in rows:
            raw=row.get("due_date") or row.get("invoice_date"); due=as_of
            for pattern in ("%d-%m-%Y","%Y-%m-%d"):
                try: due=datetime.strptime(str(raw),pattern).date(); break
                except ValueError: pass
            days=max(0,(as_of-due).days); row["days_overdue"]=days
            row["bucket"]="Current" if days==0 else "1-30" if days<=30 else "31-60" if days<=60 else "61-90" if days<=90 else "Over 90"
        return rows

    def comparative_reports(self,from_date,to_date,currency=None):
        start=datetime.strptime(from_date,"%Y-%m-%d"); end=datetime.strptime(to_date,"%Y-%m-%d")
        try: prior_start=start.replace(year=start.year-1).strftime("%Y-%m-%d")
        except ValueError: prior_start=start.replace(year=start.year-1,day=28).strftime("%Y-%m-%d")
        try: prior_end=end.replace(year=end.year-1).strftime("%Y-%m-%d")
        except ValueError: prior_end=end.replace(year=end.year-1,day=28).strftime("%Y-%m-%d")
        current=self.profit_and_loss(from_date,to_date,currency); prior=self.profit_and_loss(prior_start,prior_end,currency)
        combined={}
        for label,rows in (("current",current),("prior",prior)):
            for row in rows:
                key=(row["currency"],row["code"],row["name_en"],row["type"]); item=combined.setdefault(key,{"currency":row["currency"],"code":row["code"],"name_en":row["name_en"],"type":row["type"],"current":0.0,"prior":0.0,"variance":0.0})
                item[label]+=float(row["amount"] or 0)
        for row in combined.values(): row["variance"]=row["current"]-row["prior"]
        return {"from_date":from_date,"to_date":to_date,"prior_from":prior_start,"prior_to":prior_end,"items":sorted(combined.values(),key=lambda row:(row["currency"],row["code"]))}

    def vat_report(self, from_date=None, to_date=None, currency=None):
        normalized="""CASE WHEN invoice_date GLOB '??-??-????'
            THEN substr(invoice_date,7,4)||'-'||substr(invoice_date,4,2)||'-'||substr(invoice_date,1,2)
            ELSE invoice_date END"""
        conditions=["status NOT IN ('cancelled','deleted')"]; parameters=[]
        if from_date: conditions.append(f"{normalized}>=?"); parameters.append(from_date)
        if to_date: conditions.append(f"{normalized}<=?"); parameters.append(to_date)
        if currency: conditions.append("currency=?"); parameters.append(currency)
        with self.connect() as db:
            invoice_rows=[dict(row) for row in db.execute(f"""SELECT currency,kind,COUNT(*) invoices,
                SUM(CAST(subtotal AS REAL)) subtotal,SUM(CAST(vat AS REAL)) vat,SUM(CAST(total AS REAL)) total
                FROM invoices WHERE {' AND '.join(conditions)} GROUP BY currency,kind ORDER BY currency,kind""",parameters)]
            expense_conditions=[]; expense_parameters=[]
            expense_date="""CASE WHEN expense_date GLOB '??-??-????'
                THEN substr(expense_date,7,4)||'-'||substr(expense_date,4,2)||'-'||substr(expense_date,1,2)
                ELSE expense_date END"""
            if from_date: expense_conditions.append(f"{expense_date}>=?"); expense_parameters.append(from_date)
            if to_date: expense_conditions.append(f"{expense_date}<=?"); expense_parameters.append(to_date)
            if currency: expense_conditions.append("currency=?"); expense_parameters.append(currency)
            where=" WHERE "+" AND ".join(expense_conditions) if expense_conditions else ""
            expenses=[dict(row) for row in db.execute(f"""SELECT currency,COUNT(*) invoices,SUM(CAST(subtotal AS REAL)) subtotal,
                SUM(CAST(vat AS REAL)) vat,SUM(CAST(total AS REAL)) total FROM expenses{where} GROUP BY currency""",expense_parameters)]
        for row in expenses: invoice_rows.append({**row,"kind":"expense"})
        totals={}
        for row in invoice_rows:
            totals.setdefault(row["currency"],{"sales_vat":0.0,"purchase_vat":0.0,"expense_vat":0.0})
            key="sales_vat" if row["kind"]=="sale" else "purchase_vat" if row["kind"]=="purchase" else "expense_vat"
            totals[row["currency"]][key]+=float(row["vat"] or 0)
        summary=[]
        for code,value in totals.items():
            recoverable=value["purchase_vat"]+value["expense_vat"]
            summary.append({"currency":code,**value,"recoverable_vat":recoverable,"vat_payable":value["sales_vat"]-recoverable})
        return {"items":invoice_rows,"summary":summary}

    # Payroll is deliberately settings-driven.  Rates and ceilings are effective-dated so
    # a Lebanese statutory change does not rewrite previously calculated payroll periods.
    def list_employees(self, include_inactive=True):
        with self.connect() as db:
            where="" if include_inactive else "WHERE e.active=1"
            return [dict(row) for row in db.execute(f"""SELECT e.*,b.name branch_name
                FROM employees e LEFT JOIN branches b ON b.id=e.branch_id {where}
                ORDER BY e.employee_number""")]

    def nssf_filed_wages(self,year):
        year=int(year)
        if year<2000 or year>2100: raise ValueError("Enter a valid year")
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM nssf_filed_wages WHERE year=? ORDER BY month",(year,))]

    def save_nssf_filed_wages(self,item,user_id):
        year=int(item.get("year")); month=int(item.get("month"))
        if year<2000 or year>2100 or month<1 or month>12: raise ValueError("Enter a valid year and month")
        values=[]
        for key in ("sickness_wages","family_wages","end_service_wages","amount_paid"):
            raw=str(item.get(key) or "").strip().replace(",","")
            if raw:
                amount=Decimal(raw)
                if not amount.is_finite() or amount<0: raise ValueError(f"{key.replace('_',' ')} must be zero or positive")
                values.append(str(amount))
            else: values.append(None)
        with self.connect() as db:
            db.execute("""INSERT INTO nssf_filed_wages(year,month,sickness_wages,family_wages,end_service_wages,amount_paid,note,updated_by,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(year,month) DO UPDATE SET sickness_wages=excluded.sickness_wages,
                family_wages=excluded.family_wages,end_service_wages=excluded.end_service_wages,amount_paid=excluded.amount_paid,
                note=excluded.note,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                (year,month,*values,str(item.get("note") or "").strip(),user_id,utcnow()))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"update","nssf_filed_wages",None,json.dumps({"year":year,"month":month}),utcnow()))
        return next(row for row in self.nssf_filed_wages(year) if row["month"]==month)

    def next_employee_number(self, prefix="1000"):
        prefix="".join(ch for ch in str(prefix or "1000") if ch.isdigit())[:4]
        if len(prefix)!=4: raise ValueError("Employee prefix must contain 4 digits")
        with self.connect() as db:
            row=db.execute("""SELECT employee_number FROM employees
                WHERE employee_number LIKE ? AND length(employee_number)=9
                ORDER BY CAST(employee_number AS INTEGER) DESC LIMIT 1""",(prefix+"%",)).fetchone()
        suffix=int(row["employee_number"][4:])+1 if row else 1
        if suffix>99999: raise ValueError(f"No employee numbers remain under prefix {prefix}")
        return f"{prefix}{suffix:05d}"

    def save_employee(self,item,user_id):
        name=str(item.get("full_name") or "").strip()
        if not name: raise ValueError("Employee name is required")
        number="".join(ch for ch in str(item.get("employee_number") or "") if ch.isdigit())
        if len(number)==4: number=self.next_employee_number(number)
        elif not number: number=self.next_employee_number("1000")
        elif len(number)!=9: raise ValueError("Employee number must contain 9 digits (or enter a 4-digit prefix)")
        currency=str(item.get("currency") or "LBP").upper()
        if currency not in self.currency_codes(): raise ValueError("Invalid employee currency")
        children=max(0,int(item.get("children") or 0)); spouse_works=1 if item.get("spouse_works",False) else 0; active=1 if item.get("active",True) else 0
        employee_group=str(item.get("employee_group") or "employee").lower()
        if employee_group not in ("employee","manager"): raise ValueError("Employee group must be Employee or Manager")
        hire_date=iso_date(item["hire_date"],"Starting date") if item.get("hire_date") else None
        leave_date=iso_date(item["leave_date"],"Leaving date") if item.get("leave_date") else None
        if hire_date and leave_date and leave_date<hire_date: raise ValueError("Leaving date cannot be before starting date")
        employee_id=item.get("id")
        values=(number,name,str(item.get("national_id") or "").strip(),str(item.get("mof_number") or "").strip(),
            str(item.get("nssf_number") or "").strip(),str(item.get("address") or "").strip(),str(item.get("contact_number") or "").strip(),
            str(item.get("nationality") or "").strip(),str(item.get("father_name") or "").strip(),str(item.get("mother_name") or "").strip(),
            iso_date(item["birth_date"]) if item.get("birth_date") else None,str(item.get("birth_place") or "").strip(),
            str(item.get("marital_status") or "single").lower(),spouse_works,children,employee_group,
            hire_date,leave_date,
            str(item.get("job_title") or "").strip(),int(item["branch_id"]) if item.get("branch_id") else None,currency,
            str(Decimal(str(item.get("base_salary") or 0))),item.get("salary_account") or "621100001",
            item.get("payable_account") or "421100001",active)
        with self.connect() as db:
            if employee_id:
                db.execute("""UPDATE employees SET employee_number=?,full_name=?,national_id=?,mof_number=?,nssf_number=?,address=?,contact_number=?,
                    nationality=?,father_name=?,mother_name=?,birth_date=?,birth_place=?,
                    marital_status=?,spouse_works=?,children=?,employee_group=?,hire_date=?,leave_date=?,job_title=?,branch_id=?,currency=?,base_salary=?,salary_account=?,payable_account=?,active=? WHERE id=?""",
                    values+(int(employee_id),)); saved_id=int(employee_id); action="update"
            else:
                saved_id=db.execute("""INSERT INTO employees(employee_number,full_name,national_id,mof_number,nssf_number,address,contact_number,
                    nationality,father_name,mother_name,birth_date,birth_place,
                    marital_status,spouse_works,children,employee_group,hire_date,leave_date,job_title,branch_id,currency,base_salary,salary_account,payable_account,active,created_by,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",values+(user_id,utcnow())).lastrowid; action="create"
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,action,"employee",saved_id,json.dumps({"employee_number":number,"name":name}),utcnow()))
        return next(row for row in self.list_employees() if row["id"]==saved_id)

    def payroll_settings_for(self,period_date=None):
        try: target=iso_date(period_date) if period_date else datetime.now().strftime("%Y-%m-%d")
        except ValueError: target=datetime.now().strftime("%Y-%m-%d")
        with self.connect() as db:
            row=db.execute("""SELECT * FROM payroll_settings WHERE date_from<=? AND (date_to IS NULL OR date_to='' OR date_to>=?)
                ORDER BY date_from DESC LIMIT 1""",(target,target)).fetchone()
            if not row: row=db.execute("SELECT * FROM payroll_settings ORDER BY date_from DESC LIMIT 1").fetchone()
            official_auto=db.execute("SELECT value FROM app_settings WHERE key='lebanese_payroll_rules_auto'").fetchone()
        result=dict(row) if row else {}
        # Older auto-seeded company databases predate the schooling decree dates.
        # Apply published values in memory, keeping saved user settings untouched.
        schooling_keys=("schooling_public_child","schooling_public_cap","schooling_private_child","schooling_private_cap")
        if result and official_auto and all(Decimal(str(result.get(key) or 0))==0 for key in schooling_keys):
            import lebanese_payroll
            effective=[period for period in lebanese_payroll.official_periods() if period["date_from"]<=target]
            if effective:
                result.update({key:effective[-1][key] for key in schooling_keys})
                result["schooling_rules_date"]=effective[-1]["date_from"]
        if result:
            result["tax_brackets"]=json.loads(result["tax_brackets"])
            defaults=self.default_payroll_account_map()
            for key in ("employee_account_map","manager_account_map"):
                try: result[key]={**defaults,**json.loads(result.get(key) or "{}")}
                except (TypeError,ValueError): result[key]=dict(defaults)
        return result

    @staticmethod
    def default_payroll_account_map():
        import chart_extra
        return dict(chart_extra.PAYROLL_MAP)

    def list_payroll_settings(self):
        with self.connect() as db:
            rows=[dict(row) for row in db.execute("SELECT * FROM payroll_settings ORDER BY date_from")]
        for row in rows:
            row["tax_brackets"]=json.loads(row["tax_brackets"])
            for key in ("employee_account_map","manager_account_map"):
                try: row[key]=json.loads(row.get(key) or "{}")
                except (TypeError,ValueError): row[key]={}
        return rows

    def save_payroll_settings(self,item,user_id):
        if not str(item.get("date_from") or "").strip(): raise ValueError("Settings Date From is required")
        date_from=iso_date(item.get("date_from"),"Date From")
        date_to=iso_date(item.get("date_to"),"Date To") if str(item.get("date_to") or "").strip() else None
        if date_to and date_to<date_from: raise ValueError("Date To cannot be before Date From")
        if not isinstance(item.get("tax_brackets"),list) or not item.get("tax_brackets"): raise ValueError("At least one tax bracket is required")
        for field in ("employee_nssf_rate","medical_rate","end_service_rate","family_rate"):
            if item.get(field) not in (None,""):
                try: rate=Decimal(str(item.get(field)))
                except Exception as exc: raise ValueError(f"{field.replace('_',' ').title()} must be a number such as 0.03") from exc
                if rate<0 or rate>=1: raise ValueError(f"{field.replace('_',' ').title()} must be a decimal rate between 0 and 1 (3% = 0.03)")
        for field in ("employee_ceiling","medical_ceiling","family_ceiling","end_service_ceiling","single_allowance","spouse_allowance","child_allowance"):
            if item.get(field) not in (None,""):
                try: value=Decimal(str(item.get(field)).replace(",",""))
                except Exception as exc: raise ValueError(f"{field.replace('_',' ').title()} must be a number") from exc
                if value<0: raise ValueError(f"{field.replace('_',' ').title()} cannot be negative")
                item[field]=str(value)
        with self.connect() as db:
            later=db.execute("""SELECT date_from FROM payroll_settings WHERE date_from>? ORDER BY date_from LIMIT 1""",(date_from,)).fetchone()
            if later and (date_to is None or date_to>=later["date_from"]):
                if date_to is None: date_to=(datetime.strptime(later["date_from"],"%Y-%m-%d")-timedelta(days=1)).strftime("%Y-%m-%d")
                else: raise ValueError(f"This period overlaps the settings that start on {display_date(later['date_from'])}")
            closing=(datetime.strptime(date_from,"%Y-%m-%d")-timedelta(days=1)).strftime("%Y-%m-%d")
            db.execute("""UPDATE payroll_settings SET date_to=? WHERE date_from<? AND (date_to IS NULL OR date_to='' OR date_to>=?)""",(closing,date_from,date_from))
        item=dict(item); item["date_from"]=date_from; item["date_to"]=date_to
        brackets=item.get("tax_brackets")
        if not isinstance(brackets,list) or not brackets: raise ValueError("At least one tax bracket is required")
        fields=("single_allowance","spouse_allowance","child_allowance","employee_nssf_rate","medical_rate","end_service_rate","family_rate",
            "employee_ceiling","medical_ceiling","family_ceiling","end_service_ceiling","salary_account","salary_payable_account","payroll_tax_account","nssf_payable_account")
        values=[str(item.get(field) if item.get(field) is not None else self.payroll_settings_for(date_from).get(field,"0")) for field in fields]
        with self.connect() as db:
            db.execute("""INSERT INTO payroll_settings(date_from,date_to,tax_brackets,single_allowance,spouse_allowance,child_allowance,
                employee_nssf_rate,medical_rate,end_service_rate,family_rate,employee_ceiling,medical_ceiling,family_ceiling,end_service_ceiling,
                salary_account,salary_payable_account,payroll_tax_account,nssf_payable_account,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(date_from) DO UPDATE SET date_to=excluded.date_to,tax_brackets=excluded.tax_brackets,
                single_allowance=excluded.single_allowance,spouse_allowance=excluded.spouse_allowance,child_allowance=excluded.child_allowance,
                employee_nssf_rate=excluded.employee_nssf_rate,medical_rate=excluded.medical_rate,end_service_rate=excluded.end_service_rate,
                family_rate=excluded.family_rate,employee_ceiling=excluded.employee_ceiling,medical_ceiling=excluded.medical_ceiling,
                family_ceiling=excluded.family_ceiling,end_service_ceiling=excluded.end_service_ceiling,salary_account=excluded.salary_account,
                salary_payable_account=excluded.salary_payable_account,payroll_tax_account=excluded.payroll_tax_account,nssf_payable_account=excluded.nssf_payable_account""",
                (date_from,item.get("date_to") or None,json.dumps(brackets),*values,user_id,utcnow()))
            for key in ("employee_account_map","manager_account_map"):
                mapping={**self.default_payroll_account_map(),**(item.get(key) or {})}
                db.execute(f"UPDATE payroll_settings SET {key}=? WHERE date_from=?",(json.dumps(mapping),date_from))
            for key in ("transport_daily_exempt","default_transport_days","schooling_annual_exempt","schooling_max_children",
                        "schooling_public_child","schooling_public_cap","schooling_private_child","schooling_private_cap","tax_rounding","minimum_wage","max_children_deduction","family_allowance_spouse","family_allowance_child","family_allowance_cap","family_allowance_max_children"):
                if item.get(key) not in (None,""):
                    try: value=str(Decimal(str(item[key]).replace(",","")))
                    except Exception as exc: raise ValueError(f"{key.replace('_',' ').title()} must be a number") from exc
                    db.execute(f"UPDATE payroll_settings SET {key}=? WHERE date_from=?",(value,date_from))
        return self.payroll_settings_for(date_from)

    def apply_lebanese_payroll_rules(self,user_id):
        """Replace the effective-dated payroll settings with the official Lebanese periods (2024 onward), keeping the posting accounts."""
        import lebanese_payroll
        current=self.payroll_settings_for(None)
        maps={k:current.get(k) for k in ("employee_account_map","manager_account_map")}
        accounts={k:current.get(k) for k in ("salary_account","salary_payable_account","payroll_tax_account","nssf_payable_account") if current.get(k)}
        with self.connect() as db: db.execute("DELETE FROM payroll_settings")
        for period in lebanese_payroll.official_periods():
            self.save_payroll_settings({**period,**accounts,**maps},user_id)
        with self.connect() as db:
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",(user_id,"apply","payroll_rules",json.dumps({"periods":len(lebanese_payroll.PERIODS)}),utcnow()))
        return self.list_payroll_settings()

    @staticmethod
    def _progressive_tax(annual_taxable,brackets):
        remaining=max(Decimal("0"),annual_taxable); previous=Decimal("0"); tax=Decimal("0")
        for ceiling,rate in brackets:
            upper=Decimal(str(ceiling)) if ceiling is not None else None
            band=remaining if upper is None else min(remaining,max(Decimal("0"),upper-previous))
            tax+=band*Decimal(str(rate)); remaining-=band
            if remaining<=0: break
            if upper is not None: previous=upper
        return tax

    def calculate_payroll(self,item):
        """Monthly payroll under the Lebanese rules effective on the payroll date.

        - Recurring pay (salary, overtime, commission and the taxable part of transport / schooling) is taxed
          on the annualised basis: tax(12 x monthly - family deductions) / 12.
        - Bonus and 13th salary are one-off income: tax(annual regular + one-off) - tax(annual regular).
        - Retroactive salary is taxed as if paid in its own months (Retro From / To), and its NSSF uses the
          ceiling of each of those months.
        - Transport is exempt up to the daily amount x days worked; schooling up to the annual limit.
        - NSSF: employee and employer shares on the monthly ceilings of the period; end of service has no ceiling.
        - Tax is rounded up to the rounding amount (LBP 10,000 from 25-11-2024) and converted to the salary currency."""
        employee_id=int(item.get("employee_id") or 0); period=str(item.get("period_date") or "").strip()
        if not employee_id or not period: raise ValueError("Select an employee and payroll period")
        period=iso_date(period,"Payroll period")
        with self.connect() as db: employee=db.execute("SELECT * FROM employees WHERE id=?",(employee_id,)).fetchone()
        if not employee: raise ValueError("Employee was not found")
        rules_date=self.month_end(period); settings=self.payroll_settings_for(rules_date); D=Decimal
        def setting(name,default="0"):
            try: return D(str(settings.get(name) if settings.get(name) not in (None,"") else default))
            except Exception: return D(default)
        money={}
        # Director remuneration is paid with the payroll but is NOT subject to salary tax (and not to NSSF);
        # it is part of gross and net pay and is posted to its own account.
        for name in ("salary","transport","overtime","commission","retro_salary","schooling","bonus","thirteenth_month","director_remuneration"):
            raw=item.get(name) if item.get(name) not in (None,"") else (employee["base_salary"] if name=="salary" else 0)
            try: money[name]=D(str(raw).replace(",",""))
            except Exception as exc: raise ValueError(f"{name.replace('_',' ').title()} must be a number") from exc
            if money[name]<0: raise ValueError(f"{name.replace('_',' ').title()} cannot be negative")
        # The selected date identifies a payroll month. Prorate a monthly base salary
        # when the employee joined or left during that month; an edited salary is the actual amount.
        month_start=rules_date[:8]+"01"
        month_days=(datetime.strptime(rules_date,"%Y-%m-%d")-datetime.strptime(month_start,"%Y-%m-%d")).days+1
        active_start=max(month_start,iso_date(employee["hire_date"]) if employee["hire_date"] else month_start)
        active_end=min(rules_date,iso_date(employee["leave_date"]) if employee["leave_date"] else rules_date)
        worked_days=max(0,(datetime.strptime(active_end,"%Y-%m-%d")-datetime.strptime(active_start,"%Y-%m-%d")).days+1)
        if not worked_days: raise ValueError("Employee did not work in the selected payroll month")
        work_fraction=D(worked_days)/D(month_days)
        tax_days=max(0,(30 if active_end==rules_date else min(int(active_end[-2:]),30))-min(int(active_start[-2:]),30)+1)
        tax_fraction=D(tax_days)/D(30)
        base_salary=D(str(employee["base_salary"] or 0))
        if worked_days<month_days and money["salary"]==base_salary:
            money["salary"]=(base_salary*work_fraction).quantize(D("0.01"))
        currency=employee["currency"]; brackets=settings.get("tax_brackets",[]); notes=[]
        if worked_days<month_days:
            notes.append(f"Partial payroll: {worked_days}/{month_days} calendar days; base salary and tax bands/deductions prorated")
        to_lbp=lambda value,day=period: self._converted_amount(value,currency,"LBP",day)
        from_lbp=lambda value,day=period: self._converted_amount(value,"LBP",currency,day)
        try: days=int(D(str(item.get("transport_days") if item.get("transport_days") not in (None,"") else setting("default_transport_days","26"))))
        except Exception as exc: raise ValueError("Transport days must be a whole number") from exc
        if days<0 or days>31: raise ValueError("Transport days must be between 0 and 31")
        exempt_transport_lbp=min(to_lbp(money["transport"]),setting("transport_daily_exempt")*days)
        children=int(employee["children"] or 0)
        schooling_limit=setting("schooling_annual_exempt") if min(children,int(setting("schooling_max_children","3")))>0 else D("0")
        with self.connect() as db:
            past_schooling=db.execute("""SELECT period_date,currency,exempt_schooling FROM payroll_records
                WHERE employee_id=? AND period_date>=? AND period_date<?""",
                (employee_id,period[:4]+"-01-01",month_start)).fetchall()
        already_exempt=sum((self._converted_amount(D(str(row["exempt_schooling"] or 0)),row["currency"],"LBP",row["period_date"])
                            for row in past_schooling),D("0"))
        exempt_schooling_lbp=min(to_lbp(money["schooling"]),max(D("0"),schooling_limit-already_exempt))
        taxable_transport_lbp=to_lbp(money["transport"])-exempt_transport_lbp; taxable_schooling_lbp=to_lbp(money["schooling"])-exempt_schooling_lbp
        if taxable_transport_lbp>0: notes.append(f"Transport above the exempt {int(setting('transport_daily_exempt')):,} LBP x {days} days is taxed")
        if taxable_schooling_lbp>0: notes.append("Schooling above the exempt annual limit is taxed")
        allowance=setting("single_allowance")
        married=employee["marital_status"] in ("married","spouse"); spouse_works=married and bool(int(employee["spouse_works"] or 0))
        # The personal deduction belongs to each employee. A spouse deduction applies
        # only for a dependent spouse; when both parents work, split only the child deduction.
        dependent_spouse_deduction=setting("spouse_allowance") if married and not spouse_works else D("0")
        child_deduction=setting("child_allowance")*min(children,int(setting("max_children_deduction","5")))
        if spouse_works and child_deduction:
            child_deduction/=2
            notes.append("Child tax deduction split equally because both spouses work")
        allowance+=dependent_spouse_deduction+child_deduction
        if children>int(setting("max_children_deduction","5")): notes.append(f"Family deduction limited to {int(setting('max_children_deduction','5'))} children")
        regular_lbp=to_lbp(money["salary"]+money["overtime"]+money["commission"])+taxable_transport_lbp+taxable_schooling_lbp
        tax=lambda annual: self._progressive_tax(max(D("0"),annual-allowance),brackets)
        annual_regular=regular_lbp*12/tax_fraction
        regular_tax=tax(annual_regular)*tax_fraction/12
        one_off_lbp=to_lbp(money["bonus"]+money["thirteenth_month"])
        one_off_tax=(tax(annual_regular+one_off_lbp/tax_fraction)-tax(annual_regular))*tax_fraction
        retro_tax=D("0"); retro_months=[]
        if money["retro_salary"]:
            start=iso_date(item.get("retro_from") or period,"Retro From"); end=iso_date(item.get("retro_to") or period,"Retro To")
            if end<start: raise ValueError("Retro To cannot be before Retro From")
            y,m=int(start[:4]),int(start[5:7])
            while (y,m)<=(int(end[:4]),int(end[5:7])):
                retro_months.append(self.month_end(f"{y}-{m:02d}-01")); m+=1
                if m>12: y,m=y+1,1
            share=money["retro_salary"]/len(retro_months)
            for month in retro_months:
                month_settings=self.payroll_settings_for(month); month_brackets=month_settings.get("tax_brackets",brackets)
                month_allowance=D(str(month_settings.get("single_allowance") or 0))
                if married and not spouse_works:
                    month_allowance+=D(str(month_settings.get("spouse_allowance") or 0))
                month_children=min(children,int(month_settings.get("max_children_deduction") or 5))
                month_child_allowance=D(str(month_settings.get("child_allowance") or 0))*month_children
                month_allowance+=month_child_allowance/2 if spouse_works else month_child_allowance
                monthly=lambda annual: self._progressive_tax(max(D("0"),annual-month_allowance),month_brackets)/12
                retro_tax+=monthly((regular_lbp+to_lbp(share,month))*12)-monthly(regular_lbp*12)
        # Salary tax withholding is cumulative across payrolls saved this year.
        # Retros use the separate prior-period treatment above.
        if not money["retro_salary"]:
            with self.connect() as db:
                previous=db.execute("""SELECT * FROM payroll_records
                    WHERE employee_id=? AND period_date>=? AND period_date<? ORDER BY period_date""",
                    (employee_id,period[:4]+"-01-01",month_start)).fetchall()
            if previous:
                prior_base=D("0"); prior_withheld=D("0")
                for record in previous:
                    gross=sum((D(str(record[key] or 0)) for key in
                        ("salary","transport","overtime","commission","schooling","bonus","thirteenth_month")),D("0"))
                    exempt=D(str(record["exempt_transport"] or 0))+D(str(record["exempt_schooling"] or 0))
                    prior_base+=self._converted_amount(max(D("0"),gross-exempt),record["currency"],"LBP",record["period_date"])
                    prior_withheld+=D(str(record["income_tax_lbp"] or 0))
                elapsed=D(len(previous))+tax_fraction
                bands=[[D(str(ceiling))*elapsed/12 if ceiling is not None else None,rate] for ceiling,rate in brackets]
                def cumulative(base):
                    return self._progressive_tax(max(D("0"),prior_base+base-allowance*elapsed/12),bands)
                base_due=cumulative(regular_lbp)
                full_due=cumulative(regular_lbp+one_off_lbp)
                regular_tax=max(D("0"),base_due-prior_withheld)
                one_off_tax=max(D("0"),full_due-base_due)
                notes.append(f"Cumulative tax includes {len(previous)} earlier payroll(s) this year")
        rounding=setting("tax_rounding")
        def rounded(value):
            value=max(D("0"),value)
            if rounding>0 and value>0: return ((value/rounding).to_integral_value(rounding="ROUND_CEILING"))*rounding
            return value.quantize(D("0.01"))
        income_tax_lbp=rounded(regular_tax+one_off_tax+retro_tax)
        retro_tax_lbp=min(income_tax_lbp,max(D("0"),retro_tax).quantize(D("0.01")))
        income_tax=from_lbp(income_tax_lbp).quantize(D("0.01")); retro_tax_value=from_lbp(retro_tax_lbp).quantize(D("0.01"))
        taxable_lbp=max(D("0"),annual_regular-allowance)*tax_fraction/12+one_off_lbp
        # NSSF: salary, overtime, commission, bonus and 13th this month; retroactive salary in its own months.
        base_lbp=to_lbp(money["salary"]+money["overtime"]+money["commission"]+money["bonus"]+money["thirteenth_month"])
        def contribution(ceiling_name,rate_name,base,month_settings):
            limit=D(str(month_settings.get(ceiling_name) or 0)); capped=min(base,limit) if limit>0 else base
            return capped*D(str(month_settings.get(rate_name) or 0))
        totals={name:contribution(ceiling,rate,base_lbp,settings) for name,ceiling,rate in (("employee","employee_ceiling","employee_nssf_rate"),("medical","medical_ceiling","medical_rate"),
                ("family","family_ceiling","family_rate"),("end_service","end_service_ceiling","end_service_rate"))}
        if money["retro_salary"]:
            share=money["retro_salary"]/len(retro_months)
            for month in retro_months:
                month_settings=self.payroll_settings_for(month); regular_month=to_lbp(money["salary"]+money["overtime"]+money["commission"],month); extra=to_lbp(share,month)
                for name,ceiling,rate in (("employee","employee_ceiling","employee_nssf_rate"),("medical","medical_ceiling","medical_rate"),("family","family_ceiling","family_rate"),("end_service","end_service_ceiling","end_service_rate")):
                    totals[name]+=contribution(ceiling,rate,regular_month+extra,month_settings)-contribution(ceiling,rate,regular_month,month_settings)
        # Employer end-of-service (8.5%) is not due for foreign employees (not covered by the scheme) or for
        # employees over 64 (past the end-of-service retirement age) - confirm eligibility with your accountant.
        age=None
        if employee["birth_date"]:
            try:
                birth=iso_date(str(employee["birth_date"]),"Date of birth")
                age=int(period[:4])-int(birth[:4])-(1 if period[5:]<birth[5:] else 0)
            except Exception: age=None
        nationality=str(employee["nationality"] or "").strip().lower()
        lebanese_terms=("lebanese","lebanon","lb","\u0644\u0628\u0646\u0627\u0646\u064a","\u0644\u0628\u0646\u0627\u0646\u064a\u0629","\u0644\u0628\u0646\u0627\u0646")
        is_foreign=bool(nationality) and not any(term in nationality for term in lebanese_terms)
        if totals["end_service"]>0 and (is_foreign or (age is not None and age>64)):
            totals["end_service"]=D("0")
            reason="foreign national" if is_foreign else "over 64"
            notes.append(f"Employer end-of-service (8.5%) exempted: employee is {reason} (confirm eligibility with your accountant)")
        nssf={name:(value.quantize(D("0.01")),from_lbp(value).quantize(D("0.01"))) for name,value in totals.items()}
        # NSSF family allowances paid with the salary on behalf of the NSSF (not taxable, offset against NSSF dues).
        allowance_lbp=D("0")
        if setting("family_allowance_cap")>0 or setting("family_allowance_child")>0:
            if employee["marital_status"] in ("married","spouse") and not int(employee["spouse_works"] or 0): allowance_lbp+=setting("family_allowance_spouse")
            allowance_lbp+=setting("family_allowance_child")*min(children,int(setting("family_allowance_max_children","5")))
            if setting("family_allowance_cap")>0: allowance_lbp=min(allowance_lbp,setting("family_allowance_cap"))
        family_allowance=from_lbp(allowance_lbp).quantize(D("0.01"))
        override=str(item.get("family_allowance_override") if item.get("family_allowance_override") is not None else "").replace(",","").strip()
        if override:
            try: family_allowance=D(override).quantize(D("0.01"))
            except Exception as exc: raise ValueError("Family Allocation must be a number") from exc
            if family_allowance<0: raise ValueError("Family Allocation cannot be negative")
            notes.append("Family allocation entered manually for this payroll")
        if money["director_remuneration"]: notes.append("Director remuneration is not subject to salary tax or NSSF (as configured); confirm with your accountant")
        minimum=setting("minimum_wage")
        if minimum>0 and to_lbp(money["salary"])<minimum: notes.append(f"Salary is below the minimum wage of {int(minimum):,} LBP for this period")
        if not str(employee["nssf_number"] or "").strip(): notes.append("NSSF number missing in the employee file")
        if not str(employee["mof_number"] or "").strip(): notes.append("MOF (tax) number missing in the employee file")
        gross=sum(money.values(),D("0"))
        net=(gross-income_tax-nssf["employee"][1]+family_allowance).quantize(D("0.01"))
        salary_base=money["salary"]+money["overtime"]+money["commission"]+money["retro_salary"]+money["bonus"]+money["thirteenth_month"]
        return {**{k:float(v) for k,v in money.items()},"gross_salary":float(gross),"taxable_salary":float(from_lbp(taxable_lbp).quantize(D("0.01"))),
            "income_tax":float(income_tax),"income_tax_lbp":float(income_tax_lbp),"nssf_base":float(salary_base),"employee_nssf":float(nssf["employee"][1]),
            "employee_nssf_lbp":float(nssf["employee"][0]),"employer_medical":float(nssf["medical"][1]),"employer_end_service":float(nssf["end_service"][1]),
            "employer_family":float(nssf["family"][1]),"net_salary":float(net),"currency":currency,"retro_tax":float(retro_tax_value),"retro_tax_lbp":float(retro_tax_lbp),
            "regular_tax":float(from_lbp(rounded(regular_tax)).quantize(D("0.01"))),"one_off_tax":float(from_lbp(max(D("0"),one_off_tax)).quantize(D("0.01"))),
            "worked_days":worked_days,"calendar_days":month_days,"transport_days":days,"exempt_transport":float(from_lbp(exempt_transport_lbp).quantize(D("0.01"))),"exempt_schooling":float(from_lbp(exempt_schooling_lbp).quantize(D("0.01"))),
            "family_allowance":float(family_allowance),"family_deduction_lbp":float(allowance),
            "annualized_recurring_lbp":float(annual_regular),"annualized_taxable_lbp":float(max(D("0"),annual_regular-allowance)),
            "compliance_notes":notes,"period_date":period,
            "settings_period":{"date_from":settings.get("date_from"),"date_to":settings.get("date_to")},"rules_date":rules_date,
            "ceilings":{"medical":float(D(str(settings.get("medical_ceiling") or 0))),"family":float(D(str(settings.get("family_ceiling") or 0)))}}

    def list_payroll(self,period_from=None,period_to=None):
        conditions=[]; values=[]
        if period_from: conditions.append("p.period_date>=?"); values.append(iso_date(period_from))
        if period_to: conditions.append("p.period_date<=?"); values.append(iso_date(period_to))
        where=" WHERE "+" AND ".join(conditions) if conditions else ""
        with self.connect() as db:
            return [dict(row) for row in db.execute(f"""SELECT p.*,e.employee_number,e.full_name FROM payroll_records p
                JOIN employees e ON e.id=p.employee_id{where} ORDER BY p.period_date DESC,p.payroll_number DESC""",values)]

    def save_payroll(self,item,user_id):
        calc=self.calculate_payroll(item); employee_id=int(item["employee_id"]); period=calc["period_date"]
        self._assert_period_open(period)
        retro_from=iso_date(item["retro_from"],"Retro From") if item.get("retro_from") else None
        retro_to=iso_date(item["retro_to"],"Retro To") if item.get("retro_to") else None
        if calc["retro_salary"] and (not retro_from or not retro_to): raise ValueError("Enter Retro From and Retro To dates for the retroactive salary")
        if retro_from and retro_to and retro_to<retro_from: raise ValueError("Retro To cannot be before Retro From")
        number=str(item.get("payroll_number") or "").strip()
        with self.connect() as db:
            if not number:
                prefix=f"PAY-{period[:7].replace('-','')}-"; row=db.execute("SELECT payroll_number FROM payroll_records WHERE payroll_number LIKE ? ORDER BY payroll_number DESC LIMIT 1",(prefix+"%",)).fetchone()
                number=f"{prefix}{(int(row['payroll_number'].rsplit('-',1)[-1])+1 if row else 1):06d}"
            fields=("salary","transport","overtime","commission","retro_salary","schooling","bonus","thirteenth_month","director_remuneration","gross_salary","taxable_salary","income_tax","income_tax_lbp",
                "nssf_base","employee_nssf","employer_medical","employer_end_service","employer_family","net_salary","retro_tax",
                "transport_days","exempt_transport","exempt_schooling","family_allowance","regular_tax","one_off_tax","compliance_notes")
            values=[json.dumps(calc[field]) if field=="compliance_notes" else str(calc[field]) for field in fields]
            existing=db.execute("SELECT id,status FROM payroll_records WHERE employee_id=? AND period_date=?",(employee_id,period)).fetchone()
            if existing and existing["status"]=="posted": raise ValueError("Posted payroll cannot be changed")
            if existing:
                db.execute(f"UPDATE payroll_records SET payroll_number=?,currency=?,{','.join(field+'=?' for field in fields)},retro_from=?,retro_to=?,reference=?,notes=? WHERE id=?",
                    (number,calc["currency"],*values,retro_from,retro_to,item.get("reference"),item.get("notes"),existing["id"])); saved_id=existing["id"]
            else:
                columns=",".join(fields); marks=",".join("?" for _ in fields)
                saved_id=db.execute(f"INSERT INTO payroll_records(payroll_number,employee_id,period_date,currency,{columns},retro_from,retro_to,reference,notes,created_by,created_at) VALUES(?,?,?,?,{marks},?,?,?,?,?,?)",
                    (number,employee_id,period,calc["currency"],*values,retro_from,retro_to,item.get("reference"),item.get("notes"),user_id,utcnow())).lastrowid
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"save","payroll",saved_id,json.dumps({"payroll_number":number}),utcnow()))
        return next(row for row in self.list_payroll() if row["id"]==saved_id)

    def post_payroll(self,payroll_id,user_id):
        with self.connect() as db:
            record=db.execute("""SELECT p.*,e.full_name,e.salary_account employee_salary_account,
                e.payable_account employee_payable_account,e.branch_id,e.employee_group FROM payroll_records p
                JOIN employees e ON e.id=p.employee_id WHERE p.id=?""",(int(payroll_id),)).fetchone()
            if not record: raise KeyError("Payroll record not found")
            if record["status"]=="posted": raise ValueError("Payroll is already posted")
            self._assert_period_open(record["period_date"])
            settings=self.payroll_settings_for(record["period_date"])
            mapping=dict(settings["manager_account_map"] if record["employee_group"]=="manager" else settings["employee_account_map"])
            salary_account=record["employee_salary_account"] or mapping["salary"]
            payable_account=record["employee_payable_account"] or mapping["payable"]
            mapping["salary"]=salary_account; mapping["payable"]=payable_account
            tax_account=mapping["tax"]; nssf_account=mapping["nssf"]
            employer_expense="621100002"
            component_names={"salary":"Salaries and Wages","transport":"Transportation","overtime":"Overtime","commission":"Commission","retro_salary":"Retroactive Salary","schooling":"Schooling Allowance","bonus":"Bonus","thirteenth_month":"13th Salary","director_remuneration":"Director Remuneration"}
            required=[(mapping[key],name,"expense") for key,name in component_names.items()]
            required+=((salary_account,"Salaries and Wages","expense"),(employer_expense,"Employer NSSF Contributions","expense"),
                (payable_account,"Salaries Payable","liability"),(tax_account,"Payroll Tax Payable","liability"),(nssf_account,"NSSF Payable","liability"))
            for code,name,kind in required:
                db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(code,name,kind))
            gross=Decimal(record["gross_salary"]); net=Decimal(record["net_salary"]); tax=Decimal(record["income_tax"])
            employee_nssf=Decimal(record["employee_nssf"])
            employer_nssf=sum((Decimal(record[name]) for name in ("employer_medical","employer_end_service","employer_family")),Decimal("0"))
            number=f'PAYJV-{record["payroll_number"]}'
            entry_id=db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,branch_id,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",(number,display_date(record["period_date"]),f'Payroll - {record["full_name"]}',"payroll",record["id"],record["currency"],record["branch_id"],user_id,utcnow())).lastrowid
            lines=[(mapping[key],Decimal(str(record[key] or 0)),Decimal("0")) for key in component_names]
            family_allowance=Decimal(str(record["family_allowance"] or 0)) if "family_allowance" in record.keys() else Decimal("0")
            # Family allocation: its own posting account when one is set; otherwise offset on the NSSF account (as before).
            family_account=str(mapping.get("family_allowance") or "").strip() or nssf_account
            if family_account!=nssf_account: db.execute("INSERT OR IGNORE INTO accounts(code,name_en,type) VALUES(?,?,?)",(family_account,"Family Allocation","asset"))
            lines+=((employer_expense,employer_nssf,Decimal("0")),(payable_account,Decimal("0"),net),(tax_account,Decimal("0"),tax),(nssf_account,Decimal("0"),employee_nssf+employer_nssf),(family_account,family_allowance,Decimal("0")))
            for code,debit,credit in lines:
                if not debit and not credit: continue
                db.execute("INSERT INTO journal_lines(entry_id,account_id,description,debit,credit) VALUES(?,?,?,?,?)",
                    (entry_id,self._account_id(db,code),f'Payroll {record["payroll_number"]}',str(debit),str(credit)))
            db.execute("UPDATE payroll_records SET status='posted',journal_entry_id=? WHERE id=?",(entry_id,record["id"]))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"post","payroll",record["id"],json.dumps({"payroll_number":record["payroll_number"],"journal_entry":number}),utcnow()))
        return next(row for row in self.list_payroll() if row["id"]==int(payroll_id))

    # ---------------------------------------------------------------- legal documents
    def legal_document_alerts(self, days=30, today=None):
        """Expired and soon-to-expire legal documents of customers and suppliers."""
        today=datetime.strptime(iso_date(today),"%Y-%m-%d").date() if today else datetime.now().date()
        with self.connect() as db:
            rows=[dict(row) for row in db.execute("""SELECT d.id,d.party_id,p.name party_name,p.kind party_kind,d.document_type,
                d.issue_date,d.expiry_date,d.file_name,d.notes FROM party_documents d JOIN parties p ON p.id=d.party_id
                WHERE d.expiry_date IS NOT NULL AND d.expiry_date<>'' AND COALESCE(d.active,1)=1""")]  # untick "applies" to stop the alert
        alerts=[]
        for row in rows:
            try: expiry=datetime.strptime(iso_date(row["expiry_date"]),"%Y-%m-%d").date()
            except ValueError: continue
            remaining=(expiry-today).days
            if remaining>int(days): continue
            row["days_remaining"]=remaining; row["expiry_date"]=expiry.strftime("%d-%m-%Y")
            row["status"]="expired" if remaining<0 else "expires today" if remaining==0 else "expiring soon"
            alerts.append(row)
        alerts.sort(key=lambda row:row["days_remaining"])
        return {"items":alerts,"expired":sum(1 for row in alerts if row["days_remaining"]<0),
            "expiring":sum(1 for row in alerts if row["days_remaining"]>=0),"days":int(days)}

    # ---------------------------------------------------------------- VAT recoverability
    def set_vat_recoverable(self, source, document_id, recoverable, user_id):
        """Mark purchase/expense VAT as deductible or non-deductible.

        Non-deductible VAT is a cost, so a reclassification entry moves it from the VAT
        receivable account to the expense/asset account; marking it deductible again removes it."""
        source=str(source or "").lower(); document_id=int(document_id); recoverable=1 if recoverable else 0
        if source not in ("invoice","expense"): raise ValueError("VAT status can only be changed on invoices or expenses")
        with self.connect() as db:
            if source=="invoice":
                row=db.execute("SELECT * FROM invoices WHERE id=?",(document_id,)).fetchone()
                if not row: raise KeyError("Invoice not found")
                if row["kind"]!="purchase": raise ValueError("Only purchase and expense VAT can be non-deductible")
                if row["status"]=="cancelled": raise ValueError("Cancelled invoices cannot be changed")
                date=row["invoice_date"]; vat=Decimal(str(row["vat"] or 0)); cost_account=row["expense_account"]; vat_account=row["vat_account"]
                number=row["invoice_number"]; currency=row["currency"]; branch_id=row["branch_id"]; party_id=row["party_id"]
            else:
                row=db.execute("SELECT * FROM expenses WHERE id=?",(document_id,)).fetchone()
                if not row: raise KeyError("Expense not found")
                date=row["expense_date"]; vat=Decimal(str(row["vat"] or 0)); cost_account=row["expense_account"]; vat_account=row["vat_account"]
                number=row["reference"] or f"EXP-{document_id}"; currency=row["currency"]; branch_id=None; party_id=None
        self._assert_period_open(date)
        with self.connect() as db:
            table="invoices" if source=="invoice" else "expenses"
            old=db.execute("SELECT id FROM journal_entries WHERE source_type='vat_reclass' AND entry_number=?",(f"VATND-{source[:3].upper()}-{document_id}",)).fetchone()
            if old:
                db.execute("DELETE FROM journal_lines WHERE entry_id=?",(old["id"],)); db.execute("DELETE FROM journal_entries WHERE id=?",(old["id"],))
            db.execute(f"UPDATE {table} SET vat_recoverable=? WHERE id=?",(recoverable,document_id))
            if not recoverable and vat>0:
                entry=db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,branch_id,created_by,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",(f"VATND-{source[:3].upper()}-{document_id}",date,f"Non-deductible VAT {number}","vat_reclass",document_id,currency,branch_id,user_id,utcnow())).lastrowid
                for code,debit,credit in ((cost_account,vat,Decimal("0")),(vat_account,Decimal("0"),vat)):
                    db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,description,debit,credit) VALUES(?,?,?,?,?,?)",
                        (entry,self._account_id(db,code),party_id,"Non-deductible VAT reclassification",str(debit),str(credit)))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"vat_status",source,document_id,json.dumps({"vat_recoverable":recoverable,"vat":str(vat)}),utcnow()))
        return {"source":source,"id":document_id,"vat_recoverable":recoverable}

    # ---------------------------------------------------------------- departments, projects, budgets
    def _dimension_ids(self, db, item):
        """Resolve a department / project given by id, code or name. Blank means none."""
        result = []
        for table, key in (("departments", "department"), ("projects", "project")):
            value = item.get(f"{key}_id") or item.get(key)
            if value in (None, "", 0, "0", "None"): result.append(None); continue
            text = str(value).split(" - ", 1)[0].strip()
            row = db.execute(f"SELECT id FROM {table} WHERE id=? OR code=? OR lower(name)=lower(?)", (int(text) if text.isdigit() and not text.startswith("0") and len(text) < 6 else -1, text, text)).fetchone()
            if not row: raise ValueError(f"{key.title()} '{text}' was not found")
            result.append(row["id"])
        return tuple(result)

    def list_departments(self, include_inactive=True):
        with self.connect() as db:
            where = "" if include_inactive else " WHERE active=1"
            return [dict(row) for row in db.execute(f"SELECT * FROM departments{where} ORDER BY code")]

    def save_department(self, item, user_id):
        name = str(item.get("name") or "").strip(); code = str(item.get("code") or "").strip().upper()
        if not name: raise ValueError("Department name is required")
        with self.connect() as db:
            if not code:
                numbers = [int(r["code"][1:]) for r in db.execute("SELECT code FROM departments WHERE code GLOB 'D[0-9]*'") if r["code"][1:].isdigit()]
                code = f"D{max(numbers, default=0) + 1:02d}"
            clash = db.execute("SELECT id FROM departments WHERE code=? AND id<>?", (code, int(item.get("id") or 0))).fetchone()
            if clash: raise ValueError(f"Department code {code} is already used")
            active = 1 if item.get("active", True) else 0
            if item.get("id"):
                db.execute("UPDATE departments SET code=?,name=?,active=? WHERE id=?", (code, name, active, int(item["id"]))); saved = int(item["id"])
            else:
                saved = db.execute("INSERT INTO departments(code,name,active,created_at) VALUES(?,?,?,?)", (code, name, active, utcnow())).lastrowid
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id, "save", "department", saved, json.dumps({"code": code, "name": name}), utcnow()))
            return dict(db.execute("SELECT * FROM departments WHERE id=?", (saved,)).fetchone())

    def list_projects(self, include_inactive=True):
        with self.connect() as db:
            where = "" if include_inactive else " WHERE p.active=1"
            return [dict(row) for row in db.execute(f"""SELECT p.*,c.name party_name FROM projects p LEFT JOIN parties c ON c.id=p.party_id{where} ORDER BY p.code""")]

    def save_project(self, item, user_id):
        name = str(item.get("name") or "").strip(); code = str(item.get("code") or "").strip().upper()
        if not name: raise ValueError("Project name is required")
        status = str(item.get("status") or "open").lower()
        if status not in ("open", "on hold", "completed", "cancelled"): raise ValueError("Status must be Open, On Hold, Completed or Cancelled")
        start = iso_date(item["start_date"], "Start date") if str(item.get("start_date") or "").strip() else None
        end = iso_date(item["end_date"], "End date") if str(item.get("end_date") or "").strip() else None
        if start and end and end < start: raise ValueError("End date cannot be before start date")
        with self.connect() as db:
            if not code:
                year = (start or datetime.now().strftime("%Y"))[:4]
                numbers = [int(r["code"].rsplit("-", 1)[-1]) for r in db.execute("SELECT code FROM projects WHERE code LIKE ?", (f"P{year}-%",)) if r["code"].rsplit("-", 1)[-1].isdigit()]
                code = f"P{year}-{max(numbers, default=0) + 1:03d}"
            clash = db.execute("SELECT id FROM projects WHERE code=? AND id<>?", (code, int(item.get("id") or 0))).fetchone()
            if clash: raise ValueError(f"Project code {code} is already used")
            party = item.get("party_id")
            if not party and str(item.get("party_name") or "").strip():
                row = db.execute("SELECT id FROM parties WHERE name=? ORDER BY id LIMIT 1", (str(item["party_name"]).strip(),)).fetchone()
                if not row: raise ValueError(f"Customer '{item['party_name']}' was not found")
                party = row["id"]
            values = (code, name, int(party) if party else None, start, end, status, str(item.get("notes") or "").strip() or None, 1 if item.get("active", True) else 0)
            if item.get("id"):
                db.execute("UPDATE projects SET code=?,name=?,party_id=?,start_date=?,end_date=?,status=?,notes=?,active=? WHERE id=?", values + (int(item["id"]),)); saved = int(item["id"])
            else:
                saved = db.execute("INSERT INTO projects(code,name,party_id,start_date,end_date,status,notes,active,created_at) VALUES(?,?,?,?,?,?,?,?,?)", values + (utcnow(),)).lastrowid
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id, "save", "project", saved, json.dumps({"code": code, "name": name}), utcnow()))
        return next(p for p in self.list_projects() if p["id"] == saved)

    def list_budgets(self, year, currency="USD", department=None, project=None):
        with self.connect() as db:
            department_id, project_id = self._dimension_ids(db, {"department": department, "project": project})
            rows = [dict(row) for row in db.execute("""SELECT b.account_code,b.month,CAST(b.amount AS REAL) amount,a.name_en account_name,a.type account_type
                FROM budgets b LEFT JOIN accounts a ON a.code=b.account_code WHERE b.year=? AND b.currency=? AND b.department_id=? AND b.project_id=?
                ORDER BY b.account_code,b.month""", (int(year), str(currency).upper(), department_id or 0, project_id or 0))]
        accounts = {}
        for row in rows:
            item = accounts.setdefault(row["account_code"], {"account_code": row["account_code"], "account_name": row["account_name"] or "", "account_type": row["account_type"],
                                                               "annual": 0.0, "months": [0.0] * 12})
            if row["month"]: item["months"][row["month"] - 1] = row["amount"]
            else: item["annual"] = row["amount"]
        for item in accounts.values():
            if not item["annual"]: item["annual"] = round(sum(item["months"]), 2)
        return list(accounts.values())

    def save_budget(self, item, user_id):
        year = int(item.get("year") or 0); currency = str(item.get("currency") or "USD").upper()
        if year < 2000 or year > 2100: raise ValueError("Enter a valid budget year")
        if currency not in self.currency_codes(): raise ValueError("Invalid budget currency")
        lines = item.get("lines")
        if not isinstance(lines, list): raise ValueError("Budget lines are missing")
        with self.connect() as db:
            department_id, project_id = self._dimension_ids(db, {"department": item.get("department"), "project": item.get("project")})
            department_id = department_id or 0; project_id = project_id or 0
            db.execute("DELETE FROM budgets WHERE year=? AND currency=? AND department_id=? AND project_id=?", (year, currency, department_id, project_id))
            saved = 0
            for index, line in enumerate(lines, 1):
                code = str(line.get("account_code") or "").split(" - ", 1)[0].strip()
                if not code: continue
                if not db.execute("SELECT 1 FROM accounts WHERE code=?", (code,)).fetchone(): raise ValueError(f"Line {index}: account {code} was not found")
                months = [Decimal(str(v or 0).replace(",", "")) for v in (line.get("months") or [0] * 12)][:12]
                annual = Decimal(str(line.get("annual") or 0).replace(",", ""))
                if any(v < 0 for v in months) or annual < 0: raise ValueError(f"Line {index}: budget amounts cannot be negative")
                if any(months):
                    for month, value in enumerate(months, 1):
                        if value: db.execute("INSERT INTO budgets(year,currency,account_code,department_id,project_id,month,amount,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                                             (year, currency, code, department_id, project_id, month, str(value), user_id, utcnow()))
                elif annual:
                    db.execute("INSERT INTO budgets(year,currency,account_code,department_id,project_id,month,amount,updated_by,updated_at) VALUES(?,?,?,?,?,0,?,?,?)",
                               (year, currency, code, department_id, project_id, str(annual), user_id, utcnow()))
                else: continue
                saved += 1
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
                (user_id, "save", "budget", json.dumps({"year": year, "currency": currency, "department_id": department_id, "project_id": project_id, "accounts": saved}), utcnow()))
        return self.list_budgets(year, currency, department_id or None, project_id or None)

    def budget_for_period(self, currency, date_from, date_to, department_id=None, project_id=None):
        """Budget per account for a date range. Annual budgets are spread evenly over 12 months."""
        start = iso_date(date_from); end = iso_date(date_to); result = {}
        months = []; year, month = int(start[:4]), int(start[5:7])
        while (year, month) <= (int(end[:4]), int(end[5:7])):
            months.append((year, month)); month += 1
            if month > 12: year, month = year + 1, 1
        with self.connect() as db:
            for year, month in months:
                for row in db.execute("""SELECT account_code,month,amount FROM budgets WHERE year=? AND currency=? AND (month=? OR month=0)
                        AND department_id=? AND project_id=?""", (year, str(currency).upper(), month, department_id or 0, project_id or 0)):
                    value = Decimal(str(row["amount"])) / (12 if row["month"] == 0 else 1)
                    result[row["account_code"]] = result.get(row["account_code"], Decimal("0")) + value
        return result

    # ---------------------------------------------------------------- numbering helpers
    def _next_number(self, db, table, column, prefix, date):
        try: year = self._date_year(date)
        except ValueError: year = datetime.now().year
        pattern = f"{prefix}-{year}-"
        numbers = [int(row["value"].rsplit("-", 1)[-1]) for row in db.execute(f"SELECT {column} value FROM {table} WHERE {column} LIKE ?", (pattern + "%",))
                   if str(row["value"]).rsplit("-", 1)[-1].isdigit()]
        return f"{pattern}{max(numbers, default=0) + 1:06d}"

    def _next_payment_number(self, db, kind, date):
        return self._next_number(db, "payments", "payment_number", "RV" if kind == "customer_receipt" else "PV", date)

    def next_document_number(self, kind, date=None):
        date = date or datetime.now().strftime("%d-%m-%Y")
        with self.connect() as db:
            if kind in ("customer_receipt", "supplier_payment"): return self._next_payment_number(db, kind, date)
            if kind == "expense": return self._next_number(db, "expenses", "expense_number", "EXP", date)
            if kind == "purchase": return self.next_invoice_number("purchase", date)
        raise ValueError("Unknown document type")

    # ---------------------------------------------------------------- receipts and payments: edit / delete
    def _remove_entries(self, db, source_type, source_id, extra_numbers=()):
        db.execute("DELETE FROM journal_entries WHERE source_type=? AND source_id=?", (source_type, int(source_id)))
        for number in extra_numbers: db.execute("DELETE FROM journal_entries WHERE entry_number=?", (number,))

    def delete_payment(self, payment_id, user_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM payments WHERE id=?", (int(payment_id),)).fetchone()
            if not row: raise KeyError("Payment not found")
        self._assert_period_open(row["payment_date"])
        with self.connect() as db:
            self._remove_entries(db, "payment", payment_id); db.execute("DELETE FROM payments WHERE id=?", (int(payment_id),))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id, "delete", "payment", int(payment_id), json.dumps({"number": row["payment_number"], "amount": row["amount"]}), utcnow()))
        return {"deleted": int(payment_id)}

    def update_payment(self, payment_id, item, user_id):
        return self._safe_replacement("payment", payment_id, item, user_id)

    def _replace_payment_on_stage(self, payment_id, item, user_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM payments WHERE id=?", (int(payment_id),)).fetchone()
            if not row: raise KeyError("Payment not found")
        item = {**item, "kind": row["kind"], "payment_number": row["payment_number"]}
        self._assert_period_open(row["payment_date"])
        self.delete_payment(payment_id, user_id)
        return self.add_payment(item, user_id)

    def _safe_replacement(self, kind, record_id, item, user_id):
        """Validate destructive edits on a snapshot; publish only a complete result."""
        with self._lock, tempfile.TemporaryDirectory() as directory:
            stage_path=Path(directory)/"edited.db"
            with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(stage_path)) as stage:
                source.backup(stage)
            stage_db=Database(stage_path)
            operation=stage_db._replace_payment_on_stage if kind=="payment" else stage_db._replace_expense_on_stage
            new_id=operation(record_id,item,user_id)
            self.backup("safety")
            with closing(sqlite3.connect(stage_path)) as source, closing(sqlite3.connect(self.path)) as target:
                source.backup(target)
            return new_id

    # ---------------------------------------------------------------- expenses: edit / delete / attachments
    def delete_expense(self, expense_id, user_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM expenses WHERE id=?", (int(expense_id),)).fetchone()
            if not row: raise KeyError("Expense not found")
        self._assert_period_open(row["expense_date"])
        with self.connect() as db:
            self._remove_entries(db, "expense", expense_id, (f"VATND-EXP-{int(expense_id)}",)); db.execute("DELETE FROM expenses WHERE id=?", (int(expense_id),))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id, "delete", "expense", int(expense_id), json.dumps({"number": row["expense_number"], "total": row["total"]}), utcnow()))
        return {"deleted": int(expense_id)}

    def update_expense(self, expense_id, item, user_id):
        return self._safe_replacement("expense", expense_id, item, user_id)

    def _replace_expense_on_stage(self, expense_id, item, user_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM expenses WHERE id=?", (int(expense_id),)).fetchone()
            if not row: raise KeyError("Expense not found")
            files = [dict(r) for r in db.execute("SELECT file_name,mime_type,content FROM expense_attachments WHERE expense_id=?", (int(expense_id),))]
        self._assert_period_open(row["expense_date"])
        self.delete_expense(expense_id, user_id)
        new_id = self.add_expense({**item, "expense_number": row["expense_number"]}, user_id)
        for f in files: self.add_expense_attachment(new_id, f["file_name"], f["mime_type"], f["content"], user_id)
        return new_id

    def add_expense_attachment(self, expense_id, file_name, mime_type, content, user_id):
        if not file_name or not content: raise ValueError("Attachment file is required")
        if len(content) > 15 * 1024 * 1024: raise ValueError("Attachment cannot exceed 15 MB")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM expenses WHERE id=?", (int(expense_id),)).fetchone(): raise KeyError("Expense not found")
            return db.execute("INSERT INTO expense_attachments(expense_id,file_name,mime_type,content,uploaded_by,uploaded_at) VALUES(?,?,?,?,?,?)",
                (int(expense_id), file_name, mime_type or "application/octet-stream", content, user_id, utcnow())).lastrowid

    def list_expense_attachments(self, expense_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,file_name,mime_type,length(content) size,uploaded_at FROM expense_attachments WHERE expense_id=? ORDER BY id DESC", (int(expense_id),))]

    def get_expense_attachment(self, attachment_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM expense_attachments WHERE id=?", (int(attachment_id),)).fetchone()
        if not row: raise KeyError("Attachment not found")
        return dict(row)

    # ---------------------------------------------------------------- invoices: edit keeping attachments, landed cost
    def replace_manual_invoice(self, invoice_id, item, line_items, user_id):
        """Replace an invoice and its linked records in one transaction."""
        with self.connect() as db:
            old = db.execute("SELECT * FROM invoices WHERE id=?", (int(invoice_id),)).fetchone()
            if not old: raise KeyError("Invoice not found")
            if old["status"] in ("deleted","cancelled"): raise ValueError("Deleted or cancelled invoices cannot be edited")
            files = [dict(r) for r in db.execute("SELECT file_name,mime_type,content FROM invoice_attachments WHERE invoice_id=?", (int(invoice_id),))]
            linked = [r["id"] for r in db.execute("SELECT id FROM invoices WHERE linked_invoice_id=?", (int(invoice_id),))]
            self._assert_period_open(old["invoice_date"])
            item = {**item, "invoice_number": item.get("invoice_number") or old["invoice_number"]}
            import inventory
            inventory.remove_invoice_documents(db, invoice_id)
            new_id = self.create_manual_invoice(item, line_items, user_id)
            for f in files:
                db.execute("INSERT INTO invoice_attachments(invoice_id,file_name,mime_type,content,uploaded_by,uploaded_at) VALUES(?,?,?,?,?,?)",
                    (new_id, f["file_name"], f["mime_type"], f["content"], user_id, utcnow()))
            for linked_id in linked: db.execute("UPDATE invoices SET linked_invoice_id=? WHERE id=?", (new_id, linked_id))
            if not old["vat_recoverable"]: db.execute("UPDATE invoices SET vat_recoverable=0 WHERE id=?", (new_id,))
            if not old["vat_recoverable"]: self.set_vat_recoverable("invoice", new_id, False, user_id)
            self.delete_invoice(invoice_id, user_id)
            return new_id

    def add_landed_cost(self, purchase_id, item, user_id):
        """Customs / freight / insurance on a purchase, booked as a linked 'Customs Case' invoice so import VAT reaches the VAT return."""
        with self.connect() as db:
            purchase = db.execute("SELECT i.*,p.name party_name FROM invoices i LEFT JOIN parties p ON p.id=i.party_id WHERE i.id=?", (int(purchase_id),)).fetchone()
        if not purchase or purchase["kind"] != "purchase": raise ValueError("Choose a purchase invoice first")
        components = (("freight", "Freight"), ("insurance", "Insurance"), ("customs_duties", "Customs duties"), ("broker_fees", "Customs broker fees"), ("other_costs", "Other landed costs"))
        lines = []
        for key, label in components:
            try: amount = Decimal(str(item.get(key) or 0).replace(",", ""))
            except Exception as exc: raise ValueError(f"{label} must be a number") from exc
            if amount < 0: raise ValueError(f"{label} cannot be negative")
            if amount: lines.append({"description": f"{label} - {purchase['invoice_number']}", "quantity": 1, "unit_price": str(amount), "deductible_subtotal": str(amount), "vat_rate": 0, "vat": 0})
        try: import_vat = Decimal(str(item.get("import_vat") or 0).replace(",", ""))
        except Exception as exc: raise ValueError("Import VAT must be a number") from exc
        if not lines and not import_vat: raise ValueError("Enter at least one landed-cost amount")
        if not lines: lines.append({"description": f"Import VAT - {purchase['invoice_number']}", "quantity": 1, "unit_price": "0", "deductible_subtotal": "0", "vat_rate": 0, "vat": 0})
        lines[0]["vat"] = str(import_vat)
        import chart_extra
        cost_accounts = {**chart_extra.LANDED_COST_ACCOUNTS, **(item.get("cost_accounts") or {})}
        with self.connect() as db:
            for key, _label in components:
                code = str(cost_accounts[key]).split(" - ", 1)[0].strip()
                account = db.execute("SELECT type FROM accounts WHERE code=? AND active=1", (code,)).fetchone()
                if not code.isdigit() or len(code) != 9 or not account or account["type"] != "expense":
                    raise ValueError(f"{key.replace('_', ' ').title()} needs an active 9-digit expense account")
                cost_accounts[key] = code
        declaration = str(item.get("customs_declaration_no") or "").strip()
        supplier_account=None; party_name=str(item.get("party_name") or "Lebanese Customs").strip()
        if str(item.get("party_id") or "").strip():
            with self.connect() as db:
                chosen=db.execute("SELECT * FROM parties WHERE id=?",(int(item["party_id"]),)).fetchone()
            if chosen:
                party_name=chosen["name"]
                supplier_account=chosen["account_number"] or None
        invoice = {"invoice_number": declaration or f"LC-{purchase['invoice_number']}", "invoice_date": item.get("date") or purchase["invoice_date"],
                   "party_name": party_name, "kind": "purchases", "currency": item.get("currency") or purchase["currency"],
                   "expense_account": purchase["expense_account"], "status": "posted", "source_file": "Customs Case",
                   "description": f"Landed cost of {purchase['invoice_number']} ({purchase['party_name'] or ''})" + (f" - declaration {declaration}" if declaration else ""),
                   "department_id": purchase["department_id"], "project_id": purchase["project_id"]}
        if supplier_account: invoice["supplier_account"]=supplier_account
        invoice_id = self.create_manual_invoice(invoice, lines, user_id)
        # each cost goes to its own 9-digit 6018 account (freight, insurance, duties, broker, other)
        with self.connect() as db:
            db.execute("UPDATE invoices SET linked_invoice_id=? WHERE id=?", (int(purchase_id), invoice_id))
            entry = db.execute("SELECT id FROM journal_entries WHERE source_type='invoice' AND source_id=?", (invoice_id,)).fetchone()
            cost_account = self._account_id(db, purchase["expense_account"])
            parts = [(cost_accounts[key], Decimal(str(item.get(key) or 0).replace(",", ""))) for key, _label in components]
            parts = [(code, amount) for code, amount in parts if amount]
            if entry and parts:
                line = db.execute("SELECT * FROM journal_lines WHERE entry_id=? AND account_id=? AND CAST(debit AS REAL)>0 ORDER BY id LIMIT 1", (entry["id"], cost_account)).fetchone()
                if line:
                    db.execute("DELETE FROM journal_lines WHERE id=?", (line["id"],))
                    for code, amount in parts:
                        db.execute("INSERT INTO journal_lines(entry_id,account_id,party_id,description,debit,credit,department_id,project_id) VALUES(?,?,?,?,?,?,?,?)",
                            (entry["id"], self._account_id(db, code), line["party_id"], f"Cost on purchase {purchase['invoice_number']}", str(amount), "0", line["department_id"], line["project_id"]))
        return invoice_id

    def landed_costs(self, purchase_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT i.id,i.invoice_number,i.invoice_date,p.name party_name,i.currency,CAST(i.subtotal AS REAL) subtotal,
                CAST(i.vat AS REAL) vat,CAST(i.total AS REAL) total FROM invoices i LEFT JOIN parties p ON p.id=i.party_id WHERE i.linked_invoice_id=? AND i.status NOT IN ('cancelled','deleted') ORDER BY i.id""", (int(purchase_id),))]

    # ---------------------------------------------------------------- Lebanese VAT classification
    SALE_TREATMENTS = ("standard", "zero_rated", "exempt", "out_of_scope")
    PURCHASE_TREATMENTS = ("standard", "reverse_charge")
    VAT_USES = ("taxable", "mixed", "exempt", "export")

    def _vat_classification(self, item, kind):
        """VAT treatment of a sale (standard 11% / zero-rated / exempt / out of scope) or purchase (standard / reverse charge),
        and for purchases what the input VAT is used for (taxable sales only, mixed = partial deduction, exempt sales only)."""
        treatment = str(item.get("vat_treatment") or "standard").lower().replace(" ", "_").replace("-", "_")
        treatment = {"taxable": "standard", "zero": "zero_rated", "export": "zero_rated", "outside": "out_of_scope"}.get(treatment, treatment)
        allowed = self.SALE_TREATMENTS if kind in ("sale", "sales") else self.PURCHASE_TREATMENTS
        if treatment not in allowed: raise ValueError("VAT treatment must be one of: " + ", ".join(t.replace("_", " ") for t in allowed))
        use = str(item.get("vat_use") or "mixed").lower()
        if use not in self.VAT_USES: raise ValueError("VAT use must be taxable, mixed, exempt or export")
        return treatment, use

    def set_vat_classification(self, source, document_id, treatment=None, use=None, user_id=None):
        source = str(source or "").lower(); document_id = int(document_id)
        table = {"invoice": "invoices", "expense": "expenses"}.get(source)
        if not table: raise ValueError("VAT classification can only be changed on invoices or expenses")
        with self.connect() as db:
            row = db.execute(f"SELECT * FROM {table} WHERE id=?", (document_id,)).fetchone()
            if not row: raise KeyError("Document not found")
        self._assert_period_open(row["invoice_date"] if table == "invoices" else row["expense_date"])
        kind = row["kind"] if table == "invoices" else "purchase"
        current = {"vat_treatment": row["vat_treatment"] if table == "invoices" else "standard", "vat_use": row["vat_use"]}
        new_treatment, new_use = self._vat_classification({"vat_treatment": treatment or current["vat_treatment"], "vat_use": use or current["vat_use"]}, kind)
        with self.connect() as db:
            if table == "invoices": db.execute("UPDATE invoices SET vat_treatment=?,vat_use=? WHERE id=?", (new_treatment, new_use, document_id))
            else: db.execute("UPDATE expenses SET vat_use=? WHERE id=?", (new_use, document_id))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id, "vat_classification", source, document_id, json.dumps({"vat_treatment": new_treatment, "vat_use": new_use}), utcnow()))
        return {"source": source, "id": document_id, "vat_treatment": new_treatment, "vat_use": new_use}

    def vat_provisional_ratio(self, year):
        with self.connect() as db:
            row = db.execute("SELECT provisional_ratio FROM vat_settings WHERE year=?", (int(year),)).fetchone()
        return Decimal(str(row["provisional_ratio"])) if row and row["provisional_ratio"] not in (None, "") else None

    def save_vat_provisional_ratio(self, year, ratio, user_id):
        if ratio in (None, ""):
            with self.connect() as db: db.execute("DELETE FROM vat_settings WHERE year=?", (int(year),))
            return None
        try: value = Decimal(str(ratio).replace("%", "").replace(",", ""))
        except Exception as exc: raise ValueError("The deduction ratio must be a percentage, for example 85") from exc
        if value > 1: value = value / 100
        if value < 0 or value > 1: raise ValueError("The deduction ratio must be between 0% and 100%")
        with self.connect() as db:
            db.execute("""INSERT INTO vat_settings(year,provisional_ratio,updated_by,updated_at) VALUES(?,?,?,?)
                ON CONFLICT(year) DO UPDATE SET provisional_ratio=excluded.provisional_ratio,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                (int(year), str(value), user_id, utcnow()))
        return value

    # ---------------------------------------------------------------- NSSF payment
    def record_nssf_payment(self, item, user_id):
        """Payment of the NSSF statement: Dr NSSF payable / Cr cash or bank (payment voucher, type 03)."""
        try: amount = Decimal(str(item.get("amount") or 0).replace(",", ""))
        except Exception as exc: raise ValueError("Enter the amount paid") from exc
        if amount <= 0: raise ValueError("The amount paid must be above zero")
        currency = str(item.get("currency") or "LBP").upper(); date = str(item.get("payment_date") or datetime.now().strftime("%d-%m-%Y"))
        cash = str(item.get("cash_account") or "531").split(" - ", 1)[0].strip()
        settings = self.payroll_settings_for(iso_date(date))
        try: payable = json.loads(settings.get("employee_account_map") or "{}").get("nssf") if isinstance(settings.get("employee_account_map"), str) else (settings.get("employee_account_map") or {}).get("nssf")
        except ValueError: payable = None
        payable = payable or "4431"
        period = str(item.get("period_label") or "").strip(); reference = str(item.get("reference") or "").strip()
        voucher = self.save_journal_voucher({"entry_date": date, "description": f"NSSF payment {period}".strip() + (f" - receipt {reference}" if reference else ""),
                                             "currency": currency, "voucher_type": "03"},
            [{"account_code": payable, "line_currency": currency, "side": "D", "amount": str(amount), "reference": reference},
             {"account_code": cash, "line_currency": currency, "side": "C", "amount": str(amount), "reference": reference}], user_id)
        return {"voucher": voucher["voucher"]["entry_number"], "amount": float(amount), "currency": currency}

    # ---------------------------------------------------------------- invoice format, notes, allocations
    def _store_invoice_format(self, invoice_id, item, line_items):
        """Unit, line discount and invoice discount (for the printed invoice), and invoice / debit note / credit note."""
        subtype = str(item.get("doc_subtype") or "invoice").lower()
        if subtype not in ("invoice", "credit_note", "debit_note"): raise ValueError("Document must be an invoice, a debit note or a credit note")
        with self.connect() as db:
            ids = [row["id"] for row in db.execute("SELECT id FROM invoice_items WHERE invoice_id=? ORDER BY id", (int(invoice_id),))]
            for item_id, line in zip(ids, line_items):
                db.execute("UPDATE invoice_items SET unit=?,discount_percent=?,discount_amount=?,gross_amount=? WHERE id=?",
                    (str(line.get("unit") or "") or None, str(line.get("discount_percent") or 0), str(line.get("discount_amount") or 0), str(line.get("gross_amount") or ""), item_id))
            db.execute("UPDATE invoices SET doc_subtype=?,invoice_discount_percent=?,invoice_discount_amount=?,gross_before_discount=?,notes=? WHERE id=?",
                (subtype, str(item.get("invoice_discount_percent") or 0), str(item.get("invoice_discount_amount") or 0), str(item.get("gross_before_discount") or ""),
                 str(item.get("notes") or "") or None, int(invoice_id)))

    def open_documents(self, party_id):
        """Invoices of a customer / supplier with what is still unpaid (after amounts paid and allocations)."""
        with self.connect() as db:
            rows = [dict(r) for r in db.execute("""SELECT i.id,i.invoice_number,i.invoice_date,i.kind,i.doc_subtype,i.currency,CAST(i.total AS REAL) total,
                CAST(COALESCE(i.amount_paid,'0') AS REAL) paid,(SELECT COALESCE(SUM(CAST(a.amount AS REAL)),0) FROM payment_allocations a WHERE a.invoice_id=i.id) allocated
                FROM invoices i WHERE i.party_id=? AND i.status NOT IN ('cancelled','deleted') ORDER BY i.id""", (int(party_id),))]
        for row in rows:
            sign = -1 if row.get("doc_subtype") == "credit_note" else 1
            row["open_amount"] = round(sign * row["total"] - row["paid"] - row["allocated"], 2)
        return [r for r in rows if abs(r["open_amount"]) >= 0.01]

    def save_allocations(self, payment_id, allocations, user_id):
        with self.connect() as db:
            payment = db.execute("SELECT * FROM payments WHERE id=?", (int(payment_id),)).fetchone()
            if not payment: raise KeyError("Payment not found")
            db.execute("DELETE FROM payment_allocations WHERE payment_id=?", (int(payment_id),))
            total = Decimal("0")
            for entry in allocations or []:
                amount = Decimal(str(entry.get("amount") or 0).replace(",", ""))
                if amount <= 0: continue
                invoice = db.execute("SELECT * FROM invoices WHERE id=?", (int(entry["invoice_id"]),)).fetchone()
                if not invoice or invoice["party_id"] != payment["party_id"]: raise ValueError("Allocate only to documents of the same customer / supplier")
                if invoice["currency"] != payment["currency"]: raise ValueError(f"{invoice['invoice_number']} is in {invoice['currency']}; the payment is in {payment['currency']}")
                total += amount
                db.execute("INSERT INTO payment_allocations(payment_id,invoice_id,amount,created_at) VALUES(?,?,?,?)", (int(payment_id), invoice["id"], str(amount), utcnow()))
            if total > Decimal(str(payment["amount"])) + Decimal("0.005"): raise ValueError(f"Allocated {total:,.2f} is more than the payment {Decimal(str(payment['amount'])):,.2f}")
        return self.payment_allocations(payment_id)

    def payment_allocations(self, payment_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT a.invoice_id,i.invoice_number,i.invoice_date,CAST(a.amount AS REAL) amount FROM payment_allocations a
                JOIN invoices i ON i.id=a.invoice_id WHERE a.payment_id=? ORDER BY a.id""", (int(payment_id),))]

    PERIOD_VALUE_FIELDS=("employee_ceiling","medical_ceiling","family_ceiling","end_service_ceiling","employee_nssf_rate","medical_rate","family_rate","end_service_rate")

    def save_payroll_periods(self, periods, user_id):
        """Save the whole list of Tax & NSSF periods at once (edit Date From / Date To, ceilings and rates).

        Periods are checked together: sorted by Date From, no two on the same date, no overlap and no gap
        (an empty Date To closes the day before the next period; the last period may stay open). Every
        other setting of a period (tax brackets, allowances, posting accounts) is kept from the period it
        was edited from, or copied from the period that covered its new Date From."""
        if not isinstance(periods,list) or not periods: raise ValueError("At least one period is required")
        with self.connect() as db:
            existing={row["date_from"]:dict(row) for row in db.execute("SELECT * FROM payroll_settings ORDER BY date_from")}
        if not existing: raise ValueError("Load the payroll settings first")
        def covering(day):
            best=None
            for start,row in sorted(existing.items()):
                if start<=day: best=row
            return best or next(iter(sorted(existing.items())))[1]
        cleaned=[]
        for index,period in enumerate(periods,1):
            if not str(period.get("date_from") or "").strip(): raise ValueError(f"Period {index}: Date From is required")
            date_from=iso_date(period.get("date_from"),f"Period {index} Date From")
            text_to=str(period.get("date_to") or "").strip()
            date_to=iso_date(text_to,f"Period {index} Date To") if text_to and text_to.lower()!="open" else None
            base=dict(existing.get(str(period.get("original_from") or ""),None) or covering(date_from))
            for field in self.PERIOD_VALUE_FIELDS:
                if period.get(field) in (None,""): continue
                try: value=Decimal(str(period[field]).replace(",","").replace("%",""))
                except Exception as exc: raise ValueError(f"Period {index}: {field.replace('_',' ')} must be a number") from exc
                if value<0: raise ValueError(f"Period {index}: {field.replace('_',' ')} cannot be negative")
                if field.endswith("rate") and value>=1: raise ValueError(f"Period {index}: {field.replace('_',' ')} must be a decimal rate (3% = 0.03)")
                base[field]=str(value)
            base["date_from"]=date_from; base["date_to"]=date_to; cleaned.append(base)
        cleaned.sort(key=lambda row:row["date_from"])
        for current,following in zip(cleaned,cleaned[1:]):
            if current["date_from"]==following["date_from"]: raise ValueError(f"Two periods start on {display_date(current['date_from'])}")
            day_before=(datetime.strptime(following["date_from"],"%Y-%m-%d")-timedelta(days=1)).strftime("%Y-%m-%d")
            if not current["date_to"]: current["date_to"]=day_before
            if current["date_to"]<current["date_from"]: raise ValueError(f"The period from {display_date(current['date_from'])} ends before it starts")
            if current["date_to"]>=following["date_from"]:
                raise ValueError(f"The period {display_date(current['date_from'])} - {display_date(current['date_to'])} overlaps the period starting {display_date(following['date_from'])}")
            if current["date_to"]<day_before:
                raise ValueError(f"Nothing covers {display_date((datetime.strptime(current['date_to'],'%Y-%m-%d')+timedelta(days=1)).strftime('%Y-%m-%d'))} to {display_date(day_before)}: "
                                 "change a Date From / Date To or add a period for those days")
        if cleaned[-1]["date_to"] and cleaned[-1]["date_to"]<cleaned[-1]["date_from"]: raise ValueError("The last period ends before it starts")
        with self.connect() as db:
            columns=[row["name"] for row in db.execute("PRAGMA table_info(payroll_settings)") if row["name"]!="id"]
            db.execute("DELETE FROM payroll_settings")
            for row in cleaned:
                row.setdefault("created_by",user_id); row.setdefault("created_at",utcnow())
                db.execute(f"INSERT INTO payroll_settings({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",[row.get(column) for column in columns])
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",(user_id,"save","payroll_periods",
                json.dumps([{"from":r["date_from"],"to":r["date_to"],**{f:r.get(f) for f in self.PERIOD_VALUE_FIELDS}} for r in cleaned]),utcnow()))
        return self.list_payroll_settings()

    def delete_payroll_period(self, date_from, user_id):
        """Remove one Tax & NSSF period; the period before it is extended to cover the gap."""
        date_from=iso_date(date_from,"Date From")
        with self.connect() as db:
            rows=[dict(r) for r in db.execute("SELECT id,date_from,date_to FROM payroll_settings ORDER BY date_from")]
            if len(rows)<=1: raise ValueError("At least one period must remain")
            target=next((r for r in rows if r["date_from"]==date_from),None)
            if not target: raise ValueError("Period not found")
            index=rows.index(target); db.execute("DELETE FROM payroll_settings WHERE id=?",(target["id"],))
            if index>0: db.execute("UPDATE payroll_settings SET date_to=? WHERE id=?",(target["date_to"],rows[index-1]["id"]))
            db.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",(user_id,"delete","payroll_period",json.dumps({"date_from":date_from}),utcnow()))
        return self.list_payroll_settings()
