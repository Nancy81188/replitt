"""Balance des comptes: one engine for the Trial Balance and the Statement of Account.

Options follow the BRAINS "Balance Des Comptes" screen: account range, currencies, branch,
dates, detailed account (statement), summary, all / non-zero accounts, order by description,
chapters / sub-chapters, ledger digit levels, balance-sheet or P&L only, carry forward
(report a nouveau), monthly, debit/credit/balance or balance format, and a 1st / 2nd column
currency (account currency, LBP or USD)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from database import display_date, iso_date

ZERO = Decimal("0")
CURRENCY_CHOICES = ("account", "LBP", "USD", "EUR", "AED")
CLASS_NAMES = {"1": "Capital accounts", "2": "Fixed assets", "3": "Inventory", "4": "Third-party accounts", "5": "Financial accounts",
               "6": "Expenses", "7": "Revenues", "8": "Special results", "9": "Analytical accounts"}


def _digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _key(code, fill="0"):
    return _digits(code).ljust(9, fill)[:12]


def _money(value, places="0.01"):
    return Decimal(str(value or 0)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on") if not isinstance(value, bool) else value


def _load_lines(db, options):
    conditions = []; parameters = []
    status = options.get("posting_status", "posted")
    # Cancelled invoices keep their original entry; the reversal entry cancels it out.
    if status == "posted": conditions.append("(e.source_type!='invoice' OR i.status IN ('posted','cancelled') OR i.status IS NULL)")
    elif status == "review": conditions.append("(e.source_type='invoice' AND i.status='review')")
    if options.get("branch_id"): conditions.append("e.branch_id=?"); parameters.append(int(options["branch_id"]))
    if options.get("exclude_closing", _truthy(options.get("profit_loss_only", False)) or _truthy(options.get("budget", False))):
        conditions.append("NOT (e.source_type='year_close' OR (e.voucher_type='05' AND e.description LIKE 'CLOSING 6&7 - %'))")
    if options.get("department_id"): conditions.append("j.department_id=?"); parameters.append(int(options["department_id"]))
    if options.get("project_id"): conditions.append("j.project_id=?"); parameters.append(int(options["project_id"]))
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with db.connect() as connection:
        rows = [dict(row) for row in connection.execute(f"""SELECT j.id,a.code,a.name_en,a.type account_type,e.id entry_id,e.entry_number,e.entry_date,
            e.description entry_description,COALESCE(j.description,'') line_description,e.currency,e.source_type,COALESCE(b.name,'Head Office') branch_name,
            CAST(j.debit AS REAL) debit,CAST(j.credit AS REAL) credit,j.line_currency,j.amount,j.amount_lbp,j.amount_usd,j.due_date,j.reference,
            COALESCE(p.name,'') party_name,i.invoice_number,i.due_date invoice_due_date,
            COALESCE(d.code,'') department_code,COALESCE(d.name,'') department_name,COALESCE(pr.code,'') project_code,COALESCE(pr.name,'') project_name
            FROM journal_lines j JOIN journal_entries e ON e.id=j.entry_id JOIN accounts a ON a.id=j.account_id
            LEFT JOIN invoices i ON i.id=e.source_id AND e.source_type IN ('invoice','journal_voucher')
            LEFT JOIN branches b ON b.id=e.branch_id LEFT JOIN parties p ON p.id=j.party_id
            LEFT JOIN departments d ON d.id=j.department_id LEFT JOIN projects pr ON pr.id=j.project_id{where}""", parameters)]
    low = _key(options.get("account_from") or "", "0") if _digits(options.get("account_from")) else None
    high = _key(options.get("account_to") or "", "9") if _digits(options.get("account_to")) else None
    currencies = [c.upper() for c in (options.get("currencies") or []) if c]
    bilan = _truthy(options.get("balance_sheet_only", False)); result = _truthy(options.get("profit_loss_only", False))
    kept = []; rate_cache = {}
    for row in rows:
        try: row["iso_date"] = iso_date(row["entry_date"])
        except ValueError: continue
        code_key = _key(row["code"])
        if low and code_key < low: continue
        if high and code_key > high: continue
        first = _digits(row["code"])[:1]
        if bilan and not result and first not in "12345": continue
        if result and not bilan and first not in "67": continue
        row["account_currency"] = (row.get("line_currency") or row["currency"] or "USD").upper()
        if currencies and row["account_currency"] not in currencies: continue
        signed = Decimal(str(row["debit"] or 0)) - Decimal(str(row["credit"] or 0))
        row["signed"] = {"entry": signed}
        # Amount in the account (line) currency, LBP and USD for every line.
        if row.get("line_currency") and row.get("amount") not in (None, ""):
            sign = 1 if signed >= 0 else -1
            row["signed"]["account"] = Decimal(str(row["amount"])) * sign
            row["signed"]["LBP"] = Decimal(str(row["amount_lbp"] or 0)) * sign
            row["signed"]["USD"] = Decimal(str(row["amount_usd"] or 0)) * sign
        else:
            row["signed"]["account"] = signed
            for target in ("LBP", "USD"):
                if row["currency"] == target: row["signed"][target] = signed; continue
                key = (row["currency"], target, row["iso_date"])
                if key not in rate_cache:
                    try: rate_cache[key] = db._converted_amount(Decimal("1"), row["currency"], target, row["iso_date"])
                    except ValueError: rate_cache[key] = None
                row["signed"][target] = signed * rate_cache[key] if rate_cache[key] is not None else ZERO
        for target in (options.get("first_column"),options.get("second_column")):
            if target in (None,"account","LBP","USD","none") or target in row["signed"]: continue
            if row["account_currency"] == target:
                row["signed"][target] = row["signed"]["account"]
            elif signed == ZERO:
                row["signed"][target] = ZERO
            else:
                key=(row["account_currency"],target,row["iso_date"])
                if key not in rate_cache:
                    rate_cache[key]=db._converted_amount(Decimal("1"),row["account_currency"],target,row["iso_date"])
                row["signed"][target]=row["signed"]["account"]*rate_cache[key]
        row["due"] = row.get("due_date") or row.get("invoice_due_date") or ""
        row["ref"] = row.get("reference") or (row.get("invoice_number") if row.get("invoice_number") and row["invoice_number"] != row["entry_number"] else "") or ""
        kept.append(row)
    return kept


def _column_value(row, column):
    return row["signed"]["account"] if column == "account" else row["signed"][column]


def build_account_report(db, options):
    options = dict(options or {})
    date_from = iso_date(options["date_from"]) if options.get("date_from") else "0000-01-01"
    date_to = iso_date(options["date_to"]) if options.get("date_to") else "9999-12-31"
    if date_from > date_to: raise ValueError("Date From cannot be after Date To")
    first = options.get("first_column", "account"); second = options.get("second_column", "LBP")
    available={"account",*db.currency_codes()}
    if first not in available: raise ValueError("Choose a valid 1st column currency")
    if second not in available|{"none"}: raise ValueError("Choose a valid 2nd column currency")
    if second == first: second = "none"
    columns = [first] + ([second] if second != "none" else [])
    detailed = _truthy(options.get("detailed", False)); summary = _truthy(options.get("summary", False))
    carry = _truthy(options.get("carry_forward", True)); monthly = _truthy(options.get("monthly", False))
    non_zero = _truthy(options.get("non_zero_only", False)); by_description = _truthy(options.get("order_by_description", False))
    balance_format = _truthy(options.get("balance_format", False)); by_due = _truthy(options.get("by_due_date", False))
    show_ref = _truthy(options.get("reference", False)); show_branch = _truthy(options.get("with_branch", False))
    show_dimensions = _truthy(options.get("with_department", False)); split = _truthy(options.get("split_by_department", False))
    split_projects = _truthy(options.get("split_by_project", False)); with_budget = _truthy(options.get("budget", False)) and not detailed
    if with_budget and (date_from == "0000-01-01" or date_to == "9999-12-31"): raise ValueError("Enter Date From and Date To for the budget comparison")
    chapters = _truthy(options.get("chapters", False)); sub_chapters = _truthy(options.get("sub_chapters", False))
    try: summary_digits = max(1, min(9, int(options.get("summary_digits") or 4)))
    except (TypeError, ValueError): summary_digits = 4
    lines = _load_lines(db, options)
    # When the 1st column is the account currency each currency is reported separately.
    def group_currency(row):
        currency = row["account_currency"] if first == "account" else first
        if split: currency += " | Department " + (f"{row['department_code']} {row['department_name']}" if row["department_code"] else "(none)")
        if split_projects: currency += " | Project " + (f"{row['project_code']} {row['project_name']}" if row["project_code"] else "(none)")
        return currency
    accounts = {}
    for row in lines:
        if row["iso_date"] > date_to: continue
        code = row["code"] if not summary else _digits(row["code"])[:summary_digits] or row["code"]
        key = (group_currency(row), code)
        account = accounts.setdefault(key, {"currency": key[0], "code": code, "name": row["name_en"], "opening": {c: ZERO for c in columns},
                                            "debit": {c: ZERO for c in columns}, "credit": {c: ZERO for c in columns}, "lines": [], "months": {}})
        if summary and not account.get("_named"): account["name"] = _parent_name(db, code) or account["name"]; account["_named"] = True
        if row["iso_date"] < date_from:
            for c in columns: account["opening"][c] += _column_value(row, c)
            continue
        for c in columns:
            value = _column_value(row, c)
            if value >= 0: account["debit"][c] += value
            else: account["credit"][c] += -value
        account["lines"].append(row)
        if monthly:
            month = account["months"].setdefault(row["iso_date"][:7], {"debit": {c: ZERO for c in columns}, "credit": {c: ZERO for c in columns}})
            for c in columns:
                value = _column_value(row, c)
                if value >= 0: month["debit"][c] += value
                else: month["credit"][c] += -value
    if not carry:
        for account in accounts.values(): account["opening"] = {c: ZERO for c in columns}
    for account in accounts.values():
        account["closing"] = {c: account["opening"][c] + account["debit"][c] - account["credit"][c] for c in columns}
    items = [a for a in accounts.values() if not (non_zero and all(abs(a["closing"][c]) < Decimal("0.005") for c in columns))
             and (a["lines"] or any(a["opening"][c] for c in columns))]
    items.sort(key=lambda a: (a["currency"], a["name"].casefold()) if by_description else (a["currency"], _key(a["code"])))
    label = {"account": "", **{code:f" ({code})" for code in db.currency_codes()}}
    def money_headers(prefix=""):
        result = []
        for c in columns:
            tail = label[c] if len(columns) > 1 or c != "account" else ""
            if balance_format: result += [f"{prefix}Debit Balance{tail}", f"{prefix}Credit Balance{tail}"]
            else: result += [f"Debit{tail}", f"Credit{tail}", f"Balance{tail}"]
        return result
    def money_cells(debit, credit):
        cells = []
        for c in columns:
            balance = debit[c] - credit[c]
            if balance_format: cells += [_money(balance) if balance > 0 else ZERO, _money(-balance) if balance < 0 else ZERO]
            else: cells += [_money(debit[c]), _money(credit[c]), _money(balance)]
        return cells
    sections = []
    currencies = sorted({a["currency"] for a in items})
    if with_budget and not currencies and not split and not split_projects:
        currencies = [first] if first != "account" else sorted({c.upper() for c in (options.get("currencies") or ["USD"])})
    for currency in currencies:
        group = [a for a in items if a["currency"] == currency]
        parts = currency.split(" | ", 1)
        heading_currency = currency if first == "account" else f"{parts[0]} equivalent" + (f" | {parts[1]}" if len(parts) > 1 else "")
        if detailed:
            for account in group:
                headers = ["Date", "Voucher", "Description"] + (["Reference"] if show_ref else []) + (["Due Date"] if by_due else []) + (["Branch"] if show_branch else []) + (["Department", "Project"] if show_dimensions else []) + money_headers()
                pad = len(headers) - len(money_headers())
                rows = []; totals = []
                opening_debit = {c: max(account["opening"][c], ZERO) for c in columns}; opening_credit = {c: max(-account["opening"][c], ZERO) for c in columns}
                if carry: rows.append(["", "", "Opening balance (carried forward)"] + [""] * (pad - 3) + money_cells(opening_debit, opening_credit)); totals.append(0)
                running = dict(account["opening"])
                ordered = sorted(account["lines"], key=lambda r: ((iso_date(r["due"]) if r["due"] else r["iso_date"]) if by_due else r["iso_date"], r["entry_number"], r["id"]))
                for row in ordered:
                    debit = {}; credit = {}
                    for c in columns:
                        value = _column_value(row, c); debit[c] = max(value, ZERO); credit[c] = max(-value, ZERO); running[c] += value
                    description = row["line_description"] or row["entry_description"] or ""
                    if row["party_name"] and row["party_name"] not in description: description = f"{description} - {row['party_name']}" if description else row["party_name"]
                    cells = []
                    for c in columns:
                        if balance_format: cells += [_money(running[c]) if running[c] > 0 else ZERO, _money(-running[c]) if running[c] < 0 else ZERO]
                        else: cells += [_money(debit[c]), _money(credit[c]), _money(running[c])]
                    rows.append([display_date(row["iso_date"]), row["entry_number"], description] + ([row["ref"]] if show_ref else []) +
                                ([display_date(row["due"]) if row["due"] else ""] if by_due else []) + ([row["branch_name"]] if show_branch else []) +
                                ([row["department_code"], row["project_code"]] if show_dimensions else []) + cells)
                total_debit = {c: account["debit"][c] + (opening_debit[c] if carry else ZERO) for c in columns}
                total_credit = {c: account["credit"][c] + (opening_credit[c] if carry else ZERO) for c in columns}
                rows.append(["", "", "TOTAL / CLOSING BALANCE"] + [""] * (pad - 3) + money_cells(total_debit, total_credit)); totals.append(len(rows) - 1)
                sections.append({"heading": f"{account['code']} - {account['name']}   |   {heading_currency}", "headers": headers, "rows": rows, "total_rows": totals})
            continue
        budget_currency = currency.split(" | ")[0] if first == "account" else first
        budgets = {}
        if with_budget:
            budgets = {_digits(code): value for code, value in db.budget_for_period(budget_currency, date_from, date_to, options.get("department_id"), options.get("project_id")).items() if value}
            known = {_digits(a["code"]) for a in group}
            for code in budgets:
                if code in known: continue
                # A budget on a parent account (e.g. 713) covers every sub-account under it.
                group.append({"currency": currency, "code": code, "name": (_parent_name(db, code) or code) + "  (budget group)", "opening": {c: ZERO for c in columns},
                              "debit": {c: ZERO for c in columns}, "credit": {c: ZERO for c in columns}, "closing": {c: ZERO for c in columns}, "lines": [], "months": {}, "budget_group": True})
            group.sort(key=lambda a: a["name"].casefold() if by_description else (_key(a["code"]), 0 if a.get("budget_group") else 1))
        def natural(account):
            movement = account["debit"][columns[0]] - account["credit"][columns[0]]
            return -movement if _digits(account["code"])[:1] == "7" else movement
        def budget_values(account):
            code = _digits(account["code"])
            if account.get("budget_group"):
                return budgets.get(code, ZERO), sum((natural(m) for m in group if not m.get("budget_group") and _digits(m["code"]).startswith(code)), ZERO)
            if summary: return sum((v for k, v in budgets.items() if k.startswith(code)), ZERO), natural(account)
            return budgets.get(code, ZERO), natural(account)
        def budget_cells(members, blank_when_none=True, prefix=None):
            if not with_budget: return []
            if prefix is not None:
                budget = sum((v for k, v in budgets.items() if k.startswith(prefix)), ZERO)
                actual = sum((natural(m) for m in group if not m.get("budget_group") and _digits(m["code"]).startswith(prefix)), ZERO)
            else:
                pairs = [budget_values(m) for m in members]
                if blank_when_none and not any(b for b, _a in pairs) and not any(m.get("budget_group") for m in members): return ["", "", "", ""]
                budget = sum((b for b, _a in pairs), ZERO); actual = sum((a for _b, a in pairs), ZERO)
            variance = actual - budget
            return [_money(budget), _money(actual), _money(variance), f"{(actual / budget * 100):.1f}%" if budget else ""]
        headers = ["Account", "Account Name"] + ([f"Opening{label[c]}" for c in columns] if carry else []) + money_headers() + \
                  ([f"Budget ({budget_currency})", "Actual (period)", "Variance", "Used %"] if with_budget else [])
        rows = []; totals = []
        chapter_levels = ([1] if chapters else []) + ([2] if sub_chapters else [])
        def balance_split(members):
            cells = []
            for c in columns:
                closings = [m["closing"][c] for m in members]
                cells += [_money(sum((v for v in closings if v > 0), ZERO)), _money(-sum((v for v in closings if v < 0), ZERO))]
            return cells
        def subtotal_row(prefix, members):
            debit = {c: sum((m["debit"][c] + (max(m["opening"][c], ZERO) if carry else ZERO) for m in members), ZERO) for c in columns}
            credit = {c: sum((m["credit"][c] + (max(-m["opening"][c], ZERO) if carry else ZERO) for m in members), ZERO) for c in columns}
            opening = [_money(sum((m["opening"][c] for m in members), ZERO)) for c in columns] if carry else []
            name = CLASS_NAMES.get(prefix, "") if len(prefix) == 1 else ""
            return [f"Total {prefix}", name] + opening + (balance_split(members) if balance_format else money_cells(debit, credit)) + budget_cells(members, prefix=prefix)
        previous = None
        for index, account in enumerate(group):
            if monthly:
                for month, values in sorted(account["months"].items()):
                    rows.append([account["code"], f"{account['name']}  |  {month[5:]}-{month[:4]}"] + ([""] * len(columns) if carry else []) + money_cells(values["debit"], values["credit"]))
            debit = {c: account["debit"][c] + (max(account["opening"][c], ZERO) if carry else ZERO) for c in columns}
            credit = {c: account["credit"][c] + (max(-account["opening"][c], ZERO) if carry else ZERO) for c in columns}
            rows.append([account["code"], account["name"]] + ([_money(account["opening"][c]) for c in columns] if carry else []) + money_cells(debit, credit) + budget_cells([account]))
            if monthly: totals.append(len(rows) - 1)
            next_code = _digits(group[index + 1]["code"]) if index + 1 < len(group) and not by_description else None
            for level in sorted(chapter_levels, reverse=True):
                prefix = _digits(account["code"])[:level]
                if next_code is None or next_code[:level] != prefix:
                    members = [m for m in group if _digits(m["code"])[:level] == prefix]
                    rows.append(subtotal_row(prefix, members)); totals.append(len(rows) - 1)
        grand_debit = {c: sum((a["debit"][c] + (max(a["opening"][c], ZERO) if carry else ZERO) for a in group), ZERO) for c in columns}
        grand_credit = {c: sum((a["credit"][c] + (max(-a["opening"][c], ZERO) if carry else ZERO) for a in group), ZERO) for c in columns}
        rows.append(["GRAND TOTAL", f"{sum(1 for a in group if not a.get('budget_group'))} account(s)"] + ([_money(sum((a["opening"][c] for a in group), ZERO)) for c in columns] if carry else [])
                    + (balance_split(group) if balance_format else money_cells(grand_debit, grand_credit)) + (["", "", "", ""] if with_budget else []))
        totals.append(len(rows) - 1)
        if with_budget:
            filler = [""] * (len(headers) - 6)
            for prefix, title in (("6", "Budget total - expenses (class 6)"), ("7", "Budget total - revenues (class 7)")):
                if any(_digits(a["code"])[:1] == prefix for a in group): rows.append(["", title] + filler + budget_cells([], prefix=prefix)); totals.append(len(rows) - 1)
        sections.append({"heading": f"Trial balance - {heading_currency}", "headers": headers, "rows": rows, "total_rows": totals})
    if not sections: sections = [{"heading": "No movements", "headers": ["Note"], "rows": [["No accounts match these options"]], "total_rows": []}]
    company = db.settings()
    title = ("Statement of Account" if options.get("statement") else "Detailed Accounts") if detailed else "Trial Balance (Balance des Comptes)"
    column_text = " / ".join("Account currency" if c == "account" else c for c in columns)
    meta = [f"Company: {company.get('company_name') or '-'}",
            f"Accounts: {options.get('account_from') or 'first'} to {options.get('account_to') or 'last'}   Currencies: {', '.join(options.get('currencies') or []) or 'All'}   Columns: {column_text}",
            f"Period: {display_date(date_from) if date_from != '0000-01-01' else 'beginning'} to {display_date(date_to) if date_to != '9999-12-31' else 'today'}"
            + ("   (with carried-forward opening balances)" if carry else ""),
            ("Department / project filter applied   " if options.get("department_id") or options.get("project_id") else "") + f"Printed: {display_date(options.get('print_date')) if options.get('print_date') else datetime.now().strftime('%d-%m-%Y')}"]
    return {"title": title, "meta": meta, "sections": sections, "account_count": len(items)}


def _parent_name(db, code):
    with db.connect() as connection:
        row = connection.execute("SELECT name_en FROM accounts WHERE code=?", (code,)).fetchone()
    return row["name_en"] if row else ""


def json_ready(value):
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, list): return [json_ready(v) for v in value]
    if isinstance(value, dict): return {k: json_ready(v) for k, v in value.items()}
    return value
