"""Year-end: close classes 6 & 7 with a Journal Voucher (type 05) and open the next year (type 04).

Closing: every expense (6) and revenue (7) account is brought to zero, per currency, and the
net goes to 121 (profit, credit) or 125 (loss, debit). Each line keeps its LBP and USD values.
Opening: balance-sheet accounts (1-5) are carried forward, per currency, with the same LBP and
USD values and the customer / supplier on each line. If the source year is still open, its
provisional P&L is carried into 121 / 125 instead of the 6 / 7 accounts."""
from __future__ import annotations

import json
from decimal import Decimal

from database import utcnow

PROFIT_ACCOUNT = "138"  # Current Year Results - Profits
LOSS_ACCOUNT = "139"    # Current Year Results - Losses
ZERO = Decimal("0")
CENT = Decimal("0.01")


def _balances(db, date_to, classes):
    """{(currency, code): {"amount", "lbp", "usd", "name"}} of posted movements up to date_to."""
    from ledger_reports import _load_lines, _digits
    result = {}
    for row in _load_lines(db, {"posting_status": "posted"}):
        if row["iso_date"] > date_to or _digits(row["code"])[:1] not in classes: continue
        key = (row["account_currency"], row["code"])
        item = result.setdefault(key, {"amount": ZERO, "lbp": ZERO, "usd": ZERO, "name": row["name_en"]})
        item["amount"] += row["signed"]["account"]; item["lbp"] += row["signed"]["LBP"]; item["usd"] += row["signed"]["USD"]
    return {k: v for k, v in result.items() if abs(v["amount"]) >= CENT or abs(v["lbp"]) >= Decimal("1")}


def _rate(amount, other):
    return (abs(other) / abs(amount)) if amount else ZERO


def _insert_lines(db, database, entry_id, currency, lines):
    for code, amount, lbp, usd, description in lines:
        if not amount and not lbp: continue
        account = db.execute("SELECT id FROM accounts WHERE code=?", (code,)).fetchone()
        if not account: raise ValueError(f"Account {code} was not found in the chart of accounts")
        party = db.execute("SELECT id FROM parties WHERE account_number=?", (code,)).fetchone()
        value = abs(amount).quantize(CENT)
        rate_lbp = _rate(amount, lbp) if currency != "LBP" else Decimal("1")
        rate_usd = (_rate(usd, amount) if currency == "LBP" else _rate(amount, usd)) or Decimal("1")
        db.execute("""INSERT INTO journal_lines(entry_id,account_id,party_id,description,debit,credit,line_currency,amount,amount_lbp,amount_usd,rate_lbp,rate_usd)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (entry_id, account["id"], party["id"] if party else None, description,
            str(value if amount > 0 else ZERO), str(value if amount < 0 else ZERO), currency, str(value), str(abs(lbp).quantize(CENT)),
            str(abs(usd).quantize(Decimal("0.001"))), str(rate_lbp.quantize(Decimal("0.0001")) if rate_lbp else 1), str(rate_usd.quantize(Decimal("0.0001")))))


def closing_preview(database, year):
    """Lines of the closing vouchers without saving them."""
    year = int(year); balances = _balances(database, f"{year}-12-31", "67"); vouchers = {}
    for (currency, code), item in sorted(balances.items()):
        vouchers.setdefault(currency, []).append((code, -item["amount"], -item["lbp"], -item["usd"], item["name"]))
    result = {}
    for currency, lines in vouchers.items():
        net = sum((l[1] for l in lines), ZERO); net_lbp = sum((l[2] for l in lines), ZERO); net_usd = sum((l[3] for l in lines), ZERO)
        # Revenues (credit) closed with debits and expenses with credits: a positive net debit means profit.
        result_line = (PROFIT_ACCOUNT, -net, -net_lbp, -net_usd, "Result of the year - profit") if net > 0 else (LOSS_ACCOUNT, -net, -net_lbp, -net_usd, "Result of the year - loss")
        result[currency] = {"lines": lines + ([result_line] if net or net_lbp else []), "net_result": net}
    return result


def remove_closing(database, year, connection=None):
    """Delete every closing made by Saber for this year (old 'year_close' entries and closing vouchers)."""
    year = int(year)
    def run(db):
        ids = [r["id"] for r in db.execute("SELECT id FROM journal_entries WHERE source_type='year_close' AND (entry_number LIKE ? OR source_id=?)", (f"CLOSE-{year}-%", year))]
        ids += [r["id"] for r in db.execute("""SELECT id FROM journal_entries WHERE source_type='journal_voucher' AND voucher_type='05' AND description LIKE ?""", (f"CLOSING 6&7 - {year}%",))]
        for entry_id in ids: db.execute("DELETE FROM journal_entries WHERE id=?", (entry_id,))
        return len(ids)
    if connection is not None: return run(connection)
    with database.connect() as db: return run(db)


def close_year(database, year, user_id):
    year = int(year); results = {}; vouchers = []
    import inventory
    with database.connect() as db:
        existing = db.execute("SELECT status FROM fiscal_years WHERE year=?", (year,)).fetchone()
    if not (existing and existing["status"] == "closed"):
        with database.connect() as db: has_stock = db.execute("SELECT 1 FROM stock_documents LIMIT 1").fetchone()
        if has_stock: inventory.post_stock_variation(database, year, user_id)  # book the closing stock before closing 6 & 7
    preview = closing_preview(database, year)
    with database.connect() as db:
        existing = db.execute("SELECT status FROM fiscal_years WHERE year=?", (year,)).fetchone()
        if existing and existing["status"] == "closed": raise ValueError(f"Fiscal year {year} is already closed. Reopen it first to close it again.")
        removed = remove_closing(database, year, db)
        for currency, data in preview.items():
            number = database._next_number(db, "journal_entries", "entry_number", "JV", f"31-12-{year}")
            entry = db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,source_id,currency,created_by,created_at,voucher_type,branch_id)
                VALUES(?,?,?,?,?,?,?,?,?,(SELECT id FROM branches ORDER BY id LIMIT 1))""", (number, f"31-12-{year}", f"CLOSING 6&7 - {year} ({currency})", "journal_voucher", None,
                currency, user_id, utcnow(), "05")).lastrowid
            _insert_lines(db, database, entry, currency, [(c, a, l, u, f"Closing {year}") for c, a, l, u, _n in data["lines"]])
            vouchers.append(number); results[currency] = float(data["net_result"])
        db.execute("""INSERT INTO fiscal_years(year,status,opened_at,closed_at,closed_by,details) VALUES(?,'closed',?,?,?,?)
            ON CONFLICT(year) DO UPDATE SET status='closed',closed_at=excluded.closed_at,closed_by=excluded.closed_by,details=excluded.details""",
            (year, f"{year}-01-01T00:00:00", utcnow(), user_id, json.dumps({"net_results": results, "closing_vouchers": vouchers})))
        db.execute("INSERT OR IGNORE INTO fiscal_years(year,status,opened_at) VALUES(?,'open',?)", (year + 1, utcnow()))
        db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
            (user_id, "close", "fiscal_year", year, json.dumps({"closing_vouchers": vouchers, "net_results": results, "removed_old_closing": removed}), utcnow()))
    return {"closed_year": year, "opened_year": year + 1, "net_results": results, "closing_vouchers": vouchers, "removed_old_closing": removed}


def reopen_year(database, year, user_id):
    year = int(year)
    with database.connect() as db:
        removed = remove_closing(database, year, db)
        db.execute("""INSERT INTO fiscal_years(year,status,opened_at) VALUES(?,'open',?)
            ON CONFLICT(year) DO UPDATE SET status='open',closed_at=NULL,closed_by=NULL,details=NULL""", (year, f"{year}-01-01T00:00:00"))
        db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
            (user_id, "reopen", "fiscal_year", year, json.dumps({"removed_closing_entries": removed}), utcnow()))
    return {"year": year, "status": "open", "removed_closing_entries": removed}


def opening_lines(source, source_year):
    """Balance-sheet balances at the end of source_year, per currency, ready for the opening voucher."""
    end = f"{int(source_year)}-12-31"; balances = _balances(source, end, "12345"); pnl = _balances(source, end, "67")
    per_currency = {}
    for (currency, code), item in sorted(balances.items()):
        per_currency.setdefault(currency, {}); per_currency[currency][code] = [item["amount"], item["lbp"], item["usd"]]
    for (currency, _code), item in pnl.items():  # provisional result when the source year is not closed yet
        target = PROFIT_ACCOUNT if item["amount"] < 0 else LOSS_ACCOUNT
        bucket = per_currency.setdefault(currency, {}).setdefault(target, [ZERO, ZERO, ZERO])
        bucket[0] += item["amount"]; bucket[1] += item["lbp"]; bucket[2] += item["usd"]
    for currency, accounts in per_currency.items():
        profit = accounts.get(PROFIT_ACCOUNT); loss = accounts.get(LOSS_ACCOUNT)
        if profit and loss and pnl:  # keep one result line per currency
            merged = [profit[i] + loss[i] for i in range(3)]; accounts.pop(PROFIT_ACCOUNT); accounts.pop(LOSS_ACCOUNT)
            accounts[PROFIT_ACCOUNT if merged[0] < 0 else LOSS_ACCOUNT] = merged
    return {c: [(code, *v) for code, v in sorted(a.items()) if abs(v[0]) >= CENT or abs(v[1]) >= 1] for c, a in per_currency.items()}


def post_opening(source, target, year, user_id):
    """Replace the opening vouchers of `year` in the target database with the balances of year-1."""
    year = int(year); lines = opening_lines(source, year - 1); vouchers = []
    with target.connect() as db:
        for row in db.execute("SELECT id FROM journal_entries WHERE source_type='opening' AND entry_number LIKE ?", (f"OPEN-{year}-%",)).fetchall():
            db.execute("DELETE FROM journal_entries WHERE id=?", (row["id"],))
        for currency, items in lines.items():
            if not items: continue
            number = f"OPEN-{year}-{currency}"
            entry = db.execute("""INSERT INTO journal_entries(entry_number,entry_date,description,source_type,currency,created_by,created_at,branch_id,voucher_type)
                VALUES(?,?,?,?,?,?,?,(SELECT id FROM branches ORDER BY id LIMIT 1),'04')""", (number, f"01-01-{year}", f"Opening balances {year} ({currency})", "opening", currency, user_id, utcnow())).lastrowid
            _insert_lines(db, target, entry, currency, [(code, amount, lbp, usd, f"Opening {year}") for code, amount, lbp, usd in items])
            vouchers.append(number)
    return vouchers
