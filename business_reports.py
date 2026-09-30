"""Business reports: receivables / payables ageing, item sales by client, 3D sales analysis, top clients / suppliers."""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from database import display_date, iso_date

ZERO = Decimal("0")
BUCKETS = (30, 60, 90, 180)


def _d(value):
    try: return Decimal(str(value if value not in (None, "") else 0))
    except Exception: return ZERO


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _period(options):
    year = datetime.now().year
    start = iso_date(options["date_from"]) if options.get("date_from") else f"{year}-01-01"
    end = iso_date(options["date_to"]) if options.get("date_to") else f"{year}-12-31"
    if start > end: raise ValueError("Date From cannot be after Date To")
    return start, end


class _Converter:
    """Amounts in one basis currency (USD or LBP) at the rate of each document date, or kept in their own currency."""
    def __init__(self, db, basis):
        self.db = db; self.basis = (basis or "USD").upper(); self.cache = {}
    def __call__(self, amount, currency, day):
        if self.basis == currency: return _d(amount)
        key = (currency, day)
        if key not in self.cache: self.cache[key] = self.db._converted_amount(Decimal("1"), currency, self.basis, day)
        return _d(amount) * self.cache[key]


def _documents(db, kind, start, end, options):
    statuses = ("posted", "review") if options.get("include_review") else ("posted",)
    only = str(options.get("only_currency") or "").upper()
    with db.connect() as connection:
        invoices = [dict(r) for r in connection.execute("""SELECT i.*,p.name party_name,p.account_number FROM invoices i LEFT JOIN parties p ON p.id=i.party_id
            WHERE i.kind=? AND i.status<>'cancelled'""", (kind,))]
        items = {}
        for row in connection.execute("SELECT * FROM invoice_items ORDER BY id"): items.setdefault(row["invoice_id"], []).append(dict(row))
        catalogue = {r["sku"]: dict(r) for r in connection.execute("SELECT * FROM inventory_items")} if _has_table(connection, "inventory_items") else {}
    result = []
    for invoice in invoices:
        try: day = iso_date(invoice["invoice_date"])
        except ValueError: continue
        if not start <= day <= end or invoice["status"] not in statuses or (only and invoice["currency"] != only): continue
        invoice["iso_date"] = day; invoice["sign"] = -1 if invoice.get("doc_subtype") == "credit_note" else 1
        invoice["lines"] = items.get(invoice["id"], []); invoice["catalogue"] = catalogue
        result.append(invoice)
    return result


def _has_table(connection, name):
    return bool(connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


# ---------------------------------------------------------------- receivables / payables ageing
def ageing(db, options):
    """Open invoices of each customer (receivables) or supplier (payables) by days overdue at a date."""
    kind = "sale" if options.get("side", "receivables") == "receivables" else "purchase"
    as_of = iso_date(options["date_to"]) if options.get("date_to") else datetime.now().strftime("%Y-%m-%d")
    try: limits = tuple(sorted({int(v) for v in str(options.get("buckets") or "").replace(" ", "").split(",") if v})) or BUCKETS
    except ValueError: raise ValueError("Buckets must be days separated by commas, for example 30,60,90,180")
    labels = ["Not due"] + [f"{a + 1}-{b} days" for a, b in zip((0,) + limits[:-1], limits)] + [f"Over {limits[-1]} days"]
    convert = _Converter(db, options.get("basis") or "USD"); basis = convert.basis; as_of_date = datetime.strptime(as_of, "%Y-%m-%d")
    with db.connect() as connection:
        invoices = [dict(r) for r in connection.execute("""SELECT i.id,i.invoice_number,i.invoice_date,i.due_date,i.currency,i.doc_subtype,i.party_id,p.name party_name,p.account_number,p.due_days,
            CAST(i.total AS REAL) total,CAST(COALESCE(i.amount_paid,'0') AS REAL) paid,
            (SELECT COALESCE(SUM(CAST(a.amount AS REAL)),0) FROM payment_allocations a JOIN payments x ON x.id=a.payment_id WHERE a.invoice_id=i.id) allocated
            FROM invoices i LEFT JOIN parties p ON p.id=i.party_id WHERE i.kind=? AND i.status IN ('posted','review')""", (kind,))]
        payment_kind = "customer_receipt" if kind == "sale" else "supplier_payment"
        payments = [dict(r) for r in connection.execute("""SELECT x.party_id,x.currency,x.payment_date,CAST(x.amount AS REAL) amount,
            (SELECT COALESCE(SUM(CAST(a.amount AS REAL)),0) FROM payment_allocations a WHERE a.payment_id=x.id) allocated FROM payments x WHERE x.kind=?""", (payment_kind,))]
    parties = {}
    for inv in invoices:
        try: day = iso_date(inv["invoice_date"])
        except ValueError: continue
        if day > as_of: continue
        sign = -1 if inv.get("doc_subtype") == "credit_note" else 1
        open_amount = _d(sign * inv["total"]) - _d(inv["paid"]) - _d(inv["allocated"])
        if abs(open_amount) < Decimal("0.01"): continue
        try: due = iso_date(inv["due_date"]) if inv.get("due_date") else (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=inv.get("due_days") or 0)).strftime("%Y-%m-%d")
        except ValueError: due = day
        days = (as_of_date - datetime.strptime(due, "%Y-%m-%d")).days
        index = 0 if days <= 0 else next((i + 1 for i, limit in enumerate(limits) if days <= limit), len(limits) + 1)
        value = convert(open_amount, inv["currency"], day)
        party = parties.setdefault(inv["party_id"], {"name": inv["party_name"] or "-", "account": inv.get("account_number") or "", "buckets": [ZERO] * len(labels), "unallocated": ZERO, "invoices": [], "due_by": ZERO})
        party["buckets"][index] += value
        if days >= 0: party["due_by"] += value
        party["invoices"].append([inv["invoice_number"], display_date(day), display_date(due), inv["currency"], _money(open_amount), max(days, 0), labels[index], _money(value)])
    for pay in payments:
        try: day = iso_date(pay["payment_date"])
        except ValueError: continue
        free = _d(pay["amount"]) - _d(pay["allocated"])
        if day > as_of or free <= 0 or pay["party_id"] not in parties: continue
        parties[pay["party_id"]]["unallocated"] += convert(free, pay["currency"], day)
    rows = []; totals = [ZERO] * len(labels); total_unallocated = ZERO
    for party in sorted(parties.values(), key=lambda p: -sum(p["buckets"], ZERO)):
        gross = sum(party["buckets"], ZERO); net = gross - party["unallocated"]; overdue = sum(party["buckets"][1:], ZERO)
        rows.append([party["name"], party["account"]] + [_money(v) for v in party["buckets"]] + [_money(gross), _money(party["unallocated"]), _money(net),
                    f"{(overdue / gross * 100):.0f}%" if gross > 0 else ""])
        totals = [a + b for a, b in zip(totals, party["buckets"])]; total_unallocated += party["unallocated"]
    grand = sum(totals, ZERO)
    rows.append(["TOTAL", f"{len(parties)} " + ("customer(s)" if kind == "sale" else "supplier(s)")] + [_money(v) for v in totals] +
                [_money(grand), _money(total_unallocated), _money(grand - total_unallocated), f"{(sum(totals[1:], ZERO) / grand * 100):.0f}%" if grand > 0 else ""])
    summary = [[label, _money(value), f"{(value / grand * 100):.1f}%" if grand else "0.0%"] for label, value in zip(labels, totals)]
    summary += [["TOTAL OPEN", _money(grand), "100.0%" if grand else "0.0%"], ["Less: receipts / payments not allocated", _money(total_unallocated), ""], ["NET BALANCE", _money(grand - total_unallocated), ""]]
    due_by = sum((party["due_by"] for party in parties.values()), ZERO)
    summary.append([f"Due by {display_date(as_of)}", _money(max(ZERO, due_by - total_unallocated)), "After unallocated receipts / payments"])
    who = "Customer" if kind == "sale" else "Supplier"
    sections = [{"heading": "Ageing summary", "headers": ["Age", f"Amount ({basis})", "% of open"], "rows": summary, "total_rows": [len(labels), len(labels) + 2]},
                {"heading": f"{'Receivables' if kind == 'sale' else 'Payables'} ageing by {who.lower()} at {display_date(as_of)} (days after the due date)",
                 "headers": [who, "Account"] + labels + ["Total Open", "Unallocated", "Net Due", "% Overdue"], "rows": rows, "total_rows": [len(rows) - 1]}]
    if options.get("detail", True):
        detail = []
        for party in sorted(parties.values(), key=lambda p: p["name"]):
            detail += [[party["name"]] + line for line in sorted(party["invoices"], key=lambda l: l[2])]
        sections.append({"heading": "Open documents", "headers": [who, "Document", "Date", "Due Date", "Currency", "Open Amount", "Days Overdue", "Bucket", f"Open ({basis})"],
                         "rows": detail or [["No open documents"] + [""] * 8], "total_rows": []})
    outlook = []
    for party in sorted(parties.values(), key=lambda p: p["name"]):
        outstanding = max(ZERO, party["due_by"] - party["unallocated"])
        outlook.append([party["name"], party["account"], _money(party["due_by"]), _money(party["unallocated"]), _money(outstanding)])
    outlook.append(["TOTAL", "", _money(due_by), _money(total_unallocated), _money(max(ZERO, due_by - total_unallocated))])
    sections.append({"heading": f"Expected {'collection' if kind == 'sale' else 'payment'} due by {display_date(as_of)} (based on recorded open invoices)",
                     "headers": [who, "Account", f"Invoice balance due by date ({basis})", "Unallocated", f"Expected due ({basis})"],
                     "rows": outlook, "total_rows": [len(outlook) - 1]})
    company = db.settings()
    meta = [f"Company: {company.get('company_name') or '-'}   Amounts in {basis} (converted at each document date)", f"Situation at {display_date(as_of)}"]
    return {"title": "Receivables Ageing" if kind == "sale" else "Payables Ageing", "meta": meta, "sections": sections}


# ---------------------------------------------------------------- item sales by client / by item
def _line_values(invoice, line, convert):
    qty = _d(line.get("quantity")) * invoice["sign"]; ht = _d(line.get("subtotal")) * invoice["sign"]; vat = _d(line.get("vat")) * invoice["sign"]
    return qty, convert(ht, invoice["currency"], invoice["iso_date"]), convert(vat, invoice["currency"], invoice["iso_date"])


def _item_key(invoice, line):
    code = line.get("item_code") or ""
    item = invoice["catalogue"].get(code) if code else None
    return code or "-", (item["name"] if item else line.get("description") or "-"), (item.get("category") if item else "") or "(no category)", line.get("unit") or (item["unit"] if item else "")


def item_sales(db, options):
    """Quantities and amounts sold, by client then item (or by item then client)."""
    start, end = _period(options); convert = _Converter(db, options.get("basis")); basis = convert.basis
    by = options.get("group_by", "client"); data = {}
    for invoice in _documents(db, "sale", start, end, options):
        for line in invoice["lines"]:
            code, name, category, unit = _item_key(invoice, line); qty, ht, vat = _line_values(invoice, line, convert)
            outer, inner = ((invoice["party_name"] or "-", (code, name, unit)) if by == "client" else ((code, name, unit), invoice["party_name"] or "-"))
            cell = data.setdefault(outer, {}).setdefault(inner, [ZERO, ZERO, ZERO, 0]); cell[0] += qty; cell[1] += ht; cell[2] += vat; cell[3] += 1
    sections = []; grand = [ZERO, ZERO, ZERO]
    for outer in sorted(data, key=lambda k: -sum((v[1] for v in data[k].values()), ZERO)):
        rows = []; sub = [ZERO, ZERO, ZERO]
        for inner, (qty, ht, vat, count) in sorted(data[outer].items(), key=lambda pair: -pair[1][1]):
            label = [inner[0], inner[1], inner[2]] if by == "client" else [inner]
            rows.append(label + [qty.quantize(Decimal("0.001")), _money(ht / qty) if qty else "", _money(ht), _money(vat), _money(ht + vat), count])
            sub = [sub[0] + qty, sub[1] + ht, sub[2] + vat]
        width = 3 if by == "client" else 1
        rows.append(["TOTAL"] + [""] * (width - 1) + [sub[0].quantize(Decimal("0.001")), "", _money(sub[1]), _money(sub[2]), _money(sub[1] + sub[2]), ""])
        grand = [a + b for a, b in zip(grand, sub)]
        heading = f"Client: {outer}" if by == "client" else f"Item: {outer[0]} - {outer[1]}" + (f" ({outer[2]})" if outer[2] else "")
        headers = (["Item Code", "Item", "Unit"] if by == "client" else ["Client"]) + ["Quantity", "Avg Price HT", f"Sales HT ({basis})", "VAT", "TTC", "Lines"]
        sections.append({"heading": heading, "headers": headers, "rows": rows, "total_rows": [len(rows) - 1]})
    sections.insert(0, {"heading": "Totals", "headers": ["", f"Sales HT ({basis})", "VAT", "TTC"],
                        "rows": [[f"{len(data)} {'client(s)' if by == 'client' else 'item(s)'}", _money(grand[1]), _money(grand[2]), _money(grand[1] + grand[2])]], "total_rows": [0]})
    company = db.settings()
    meta = [f"Company: {company.get('company_name') or '-'}   Amounts in {basis}   Credit notes deducted", f"Period: {display_date(start)} to {display_date(end)}"]
    return {"title": "Item Sales by Client" if by == "client" else "Client Quantities by Item", "meta": meta, "sections": sections}


# ---------------------------------------------------------------- 3D sales analysis (rows x columns x measure)
def sales_analysis(db, options):
    """Pivot of sales: rows = client / item / category, columns = month / quarter / client, measure = quantity / HT / VAT / TTC."""
    start, end = _period(options); convert = _Converter(db, options.get("basis")); basis = convert.basis
    rows_by = options.get("rows", "client"); cols_by = options.get("columns", "month"); measure = options.get("measure", "ht")
    if rows_by == cols_by: raise ValueError("Rows and columns must be different")
    cube = {}; columns = set()
    def dim(kind, invoice, line):
        code, name, category, _unit = _item_key(invoice, line); day = invoice["iso_date"]
        return {"client": invoice["party_name"] or "-", "item": f"{code} - {name}" if code != "-" else name, "category": category,
                "month": day[:7], "quarter": f"{day[:4]}-Q{(int(day[5:7]) - 1) // 3 + 1}"}[kind]
    for invoice in _documents(db, "sale", start, end, options):
        for line in invoice["lines"]:
            qty, ht, vat = _line_values(invoice, line, convert)
            value = {"quantity": qty, "ht": ht, "vat": vat, "ttc": ht + vat}[measure]
            r, c = dim(rows_by, invoice, line), dim(cols_by, invoice, line); columns.add(c)
            cube[(r, c)] = cube.get((r, c), ZERO) + value
    columns = sorted(columns); row_keys = sorted({r for r, _c in cube}, key=lambda r: -sum((cube.get((r, c), ZERO) for c in columns), ZERO))
    label = lambda c: f"{calendar.month_abbr[int(c[5:7])]} {c[:4]}" if cols_by == "month" else c
    fmt = (lambda v: v.quantize(Decimal("0.001"))) if measure == "quantity" else _money
    table = [[r] + [fmt(cube.get((r, c), ZERO)) for c in columns] + [fmt(sum((cube.get((r, c), ZERO) for c in columns), ZERO))] for r in row_keys]
    total = sum((cube.values()), ZERO)
    table.append(["TOTAL"] + [fmt(sum((cube.get((r, c), ZERO) for r in row_keys), ZERO)) for c in columns] + [fmt(total)])
    for row in table[:-1]: row.append(f"{(Decimal(str(row[-1])) / total * 100):.1f}%" if total else "")
    table[-1].append("100%")
    names = {"client": "Client", "item": "Item", "category": "Category", "month": "Month", "quarter": "Quarter"}
    measure_name = {"quantity": "Quantity", "ht": f"Sales HT ({basis})", "vat": f"VAT ({basis})", "ttc": f"Sales TTC ({basis})"}[measure]
    sections = [{"heading": f"{measure_name} by {names[rows_by].lower()} and {names[cols_by].lower()}", "headers": [names[rows_by]] + [label(c) for c in columns] + ["Total", "Share"],
                 "rows": table if row_keys else [["No sales in this period"]], "total_rows": [len(table) - 1] if row_keys else []}]
    company = db.settings()
    meta = [f"Company: {company.get('company_name') or '-'}   Measure: {measure_name}   Credit notes deducted", f"Period: {display_date(start)} to {display_date(end)}"]
    return {"title": "Sales Analysis (3D)", "meta": meta, "sections": sections}


# ---------------------------------------------------------------- top clients / suppliers
def top_parties(db, options):
    """Ranking of clients (sales) or suppliers (purchases and expenses): HT + VAT = TTC, share and number of documents."""
    start, end = _period(options); convert = _Converter(db, options.get("basis")); basis = convert.basis
    side = options.get("side", "clients"); kind = "sale" if side == "clients" else "purchase"
    try: limit = max(1, min(500, int(options.get("top") or 20)))
    except ValueError: raise ValueError("Top must be a number")
    totals = {}
    for invoice in _documents(db, kind, start, end, options):
        ht = convert(_d(invoice["subtotal"]) * invoice["sign"], invoice["currency"], invoice["iso_date"])
        vat = convert(_d(invoice["vat"]) * invoice["sign"], invoice["currency"], invoice["iso_date"])
        row = totals.setdefault(invoice["party_name"] or "-", {"account": invoice.get("account_number") or "", "ht": ZERO, "vat": ZERO, "count": 0, "last": ""})
        row["ht"] += ht; row["vat"] += vat; row["count"] += 1; row["last"] = max(row["last"], invoice["iso_date"])
    if side == "suppliers" and options.get("include_expenses", True):
        with db.connect() as connection: expenses = [dict(r) for r in connection.execute("SELECT * FROM expenses")]
        for e in expenses:
            try: day = iso_date(e["expense_date"])
            except ValueError: continue
            if not start <= day <= end: continue
            row = totals.setdefault(f"(expense) {e['description']}", {"account": "", "ht": ZERO, "vat": ZERO, "count": 0, "last": ""})
            row["ht"] += convert(_d(e["with_vat_subtotal"]) + _d(e["without_vat_subtotal"]), e["currency"], day); row["vat"] += convert(_d(e["vat"]), e["currency"], day)
            row["count"] += 1; row["last"] = max(row["last"], day)
    ranked = sorted(totals.items(), key=lambda pair: -(pair[1]["ht"] + pair[1]["vat"]))
    grand_ht = sum((v["ht"] for _k, v in ranked), ZERO); grand_vat = sum((v["vat"] for _k, v in ranked), ZERO); grand = grand_ht + grand_vat
    rows = []; cumulative = ZERO
    for rank, (name, v) in enumerate(ranked[:limit], 1):
        ttc = v["ht"] + v["vat"]; cumulative += ttc
        rows.append([rank, name, v["account"], _money(v["ht"]), _money(v["vat"]), _money(ttc), f"{(ttc / grand * 100):.1f}%" if grand else "", f"{(cumulative / grand * 100):.1f}%" if grand else "",
                     v["count"], display_date(v["last"])])
    others = ranked[limit:]
    if others:
        o_ht = sum((v["ht"] for _k, v in others), ZERO); o_vat = sum((v["vat"] for _k, v in others), ZERO)
        rows.append(["", f"Others ({len(others)})", "", _money(o_ht), _money(o_vat), _money(o_ht + o_vat), f"{((o_ht + o_vat) / grand * 100):.1f}%" if grand else "", "100.0%", sum(v["count"] for _k, v in others), ""])
    rows.append(["", "TOTAL", "", _money(grand_ht), _money(grand_vat), _money(grand), "100%", "", sum(v["count"] for _k, v in ranked), ""])
    who = "Client" if side == "clients" else "Supplier"
    sections = [{"heading": f"Top {limit} {who.lower()}s - {'sales' if side == 'clients' else 'purchases and expenses'} {display_date(start)} to {display_date(end)}",
                 "headers": ["Rank", who, "Account", f"HT ({basis})", "VAT", "TTC", "Share", "Cumulative", "Documents", "Last Document"], "rows": rows, "total_rows": [len(rows) - 1]}]
    company = db.settings()
    meta = [f"Company: {company.get('company_name') or '-'}   Amounts in {basis}   HT + VAT = TTC   Credit notes deducted", f"Period: {display_date(start)} to {display_date(end)}"]
    return {"title": f"Top {who}s", "meta": meta, "sections": sections}


REPORTS = {"receivables": lambda db, o: ageing(db, {**o, "side": "receivables"}), "payables": lambda db, o: ageing(db, {**o, "side": "payables"}),
           "item_sales_client": lambda db, o: item_sales(db, {**o, "group_by": "client"}), "item_sales_item": lambda db, o: item_sales(db, {**o, "group_by": "item"}),
           "analysis": sales_analysis, "top_clients": lambda db, o: top_parties(db, {**o, "side": "clients"}), "top_suppliers": lambda db, o: top_parties(db, {**o, "side": "suppliers"})}


def build(db, report, options):
    if report not in REPORTS: raise ValueError("Unknown report")
    return REPORTS[report](db, dict(options or {}))


def dashboard_charts(db, options):
    """Data for the dashboard charts: sales vs purchases by month, receivables by age, top 5 clients, cash and bank."""
    year = int(options.get("year") or datetime.now().year); convert = _Converter(db, options.get("basis")); basis = convert.basis
    start, end = f"{year}-01-01", f"{year}-12-31"; months = [[ZERO, ZERO] for _ in range(12)]
    for index, kind in enumerate(("sale", "purchase")):
        for invoice in _documents(db, kind, start, end, {}):
            months[int(invoice["iso_date"][5:7]) - 1][index] += convert(_d(invoice["subtotal"]) * invoice["sign"], invoice["currency"], invoice["iso_date"])
    with db.connect() as connection: expenses = [dict(r) for r in connection.execute("SELECT expense_date,currency,with_vat_subtotal,without_vat_subtotal FROM expenses")]
    for e in expenses:
        try: day = iso_date(e["expense_date"])
        except ValueError: continue
        if start <= day <= end: months[int(day[5:7]) - 1][1] += convert(_d(e["with_vat_subtotal"]) + _d(e["without_vat_subtotal"]), e["currency"], day)
    receivables = ageing(db, {"side": "receivables", "date_to": options.get("as_of") or datetime.now().strftime("%d-%m-%Y"), "basis": basis, "detail": False})
    buckets = [[row[0], float(row[1])] for row in receivables["sections"][0]["rows"][:6]]
    top = top_parties(db, {"side": "clients", "date_from": f"01-01-{year}", "date_to": f"31-12-{year}", "basis": basis, "top": 5})["sections"][0]["rows"]
    top = [[row[1], float(row[5])] for row in top if row[0] != ""]
    from ledger_reports import _load_lines, _digits
    cash = {}
    column = basis if basis in ("USD", "LBP") else "USD"
    for line in _load_lines(db, {"posting_status": "posted"}):
        code = _digits(line["code"])
        if code.startswith(("51", "53")) and line["iso_date"] <= end: cash[line["code"]] = cash.get(line["code"], ZERO) + line["signed"][column]
    return {"basis": basis, "year": year, "months": [[calendar.month_abbr[i + 1], float(m[0]), float(m[1])] for i, m in enumerate(months)],
            "receivables": buckets, "top_clients": top, "cash": sorted([[code, float(v)] for code, v in cash.items() if abs(v) >= Decimal("0.01")], key=lambda x: -abs(x[1]))[:6]}

