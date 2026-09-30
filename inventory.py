"""Inventory: items, warehouses, stock documents, weighted-average / FIFO costing, reports and the
year-end stock variation voucher of the Lebanese chart (6051 opening stock / 6052 closing stock / 37 stock).

Accounting follows the periodic method of the Lebanese chart of accounts: purchases stay in 601, and the
stock value is booked at the period end by a 'STOCK VARIATION' Journal Voucher (type 06)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal

from database import display_date, iso_date, utcnow

ZERO = Decimal("0")
DOC_TYPES = {"opening": ("OPN", "Opening Stock", 1), "receipt": ("GRN", "Stock Receipt", 1), "issue": ("GIN", "Stock Issue", -1),
             "adjustment_in": ("ADJ", "Adjustment +", 1), "adjustment_out": ("ADJ", "Adjustment -", -1), "transfer": ("TRF", "Transfer", 0)}
STOCK_ACCOUNT, OPENING_ACCOUNT, CLOSING_ACCOUNT = "37", "6051", "6052"


def _d(value):
    try: return Decimal(str(value if value not in (None, "") else 0).replace(",", ""))
    except Exception as exc: raise ValueError(f"'{value}' is not a number") from exc


def migrate(db):
    """Called from Database.initialize: inventory tables and columns."""
    db.execute("""CREATE TABLE IF NOT EXISTS warehouses (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)""")
    db.execute("""CREATE TABLE IF NOT EXISTS stock_documents (
        id INTEGER PRIMARY KEY, number TEXT NOT NULL UNIQUE, doc_type TEXT NOT NULL, doc_date TEXT NOT NULL, warehouse_id INTEGER NOT NULL,
        to_warehouse_id INTEGER, party_id INTEGER, invoice_id INTEGER, reference TEXT, notes TEXT, created_by INTEGER, created_at TEXT NOT NULL)""")
    item_columns = {row["name"] for row in db.execute("PRAGMA table_info(inventory_items)")}
    for column, definition in (("category", "TEXT"), ("reorder_level", "TEXT NOT NULL DEFAULT '0'"), ("sales_price", "TEXT NOT NULL DEFAULT '0'"),
                               ("active", "INTEGER NOT NULL DEFAULT 1"), ("notes", "TEXT"), ("barcode", "TEXT"), ("created_at", "TEXT")):
        if column not in item_columns: db.execute(f"ALTER TABLE inventory_items ADD COLUMN {column} {definition}")
    movement_columns = {row["name"] for row in db.execute("PRAGMA table_info(stock_movements)")}
    for column, definition in (("warehouse_id", "INTEGER"), ("document_id", "INTEGER"), ("movement_type", "TEXT"), ("sales_price", "TEXT"), ("line_no", "INTEGER")):
        if column not in movement_columns: db.execute(f"ALTER TABLE stock_movements ADD COLUMN {column} {definition}")
    db.execute("CREATE TABLE IF NOT EXISTS item_categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL, parent_id INTEGER, UNIQUE(name,parent_id))")
    db.execute("CREATE TABLE IF NOT EXISTS item_units (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
    db.execute("""CREATE TABLE IF NOT EXISTS physical_counts (id INTEGER PRIMARY KEY, number TEXT NOT NULL UNIQUE, count_date TEXT NOT NULL, warehouse_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft', lines TEXT NOT NULL, adjustment_numbers TEXT, notes TEXT, created_by INTEGER, created_at TEXT NOT NULL)""")
    item_columns = {row["name"] for row in db.execute("PRAGMA table_info(inventory_items)")}
    for column in ("subcategory", "supplier_id", "location"):
        if column not in item_columns: db.execute(f"ALTER TABLE inventory_items ADD COLUMN {column} TEXT")
    if "default_vat" not in item_columns: db.execute("ALTER TABLE inventory_items ADD COLUMN default_vat TEXT NOT NULL DEFAULT '11'")
    if "cost_account" not in item_columns: db.execute("ALTER TABLE inventory_items ADD COLUMN cost_account TEXT")
    for unit in ("unit", "piece", "sheet", "m", "m2", "kg", "box", "roll", "set"): db.execute("INSERT OR IGNORE INTO item_units(name) VALUES(?)", (unit,))
    db.execute("INSERT OR IGNORE INTO warehouses(code,name) VALUES('MAIN','Main Store')")
    db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('inventory_currency','USD')")
    db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('inventory_method','average')")
    db.execute("UPDATE stock_movements SET warehouse_id=(SELECT id FROM warehouses WHERE code='MAIN') WHERE warehouse_id IS NULL")


def settings(database):
    values = database.settings()
    return {"currency": values.get("inventory_currency", "USD"), "method": values.get("inventory_method", "average")}


def save_settings(database, item, user_id):
    currency = str(item.get("currency") or "USD").upper(); method = str(item.get("method") or "average").lower()
    if currency not in database.currency_codes() or method not in ("average", "fifo"): raise ValueError("Choose a listed currency and Average or FIFO")
    with database.connect() as db:
        for key, value in (("inventory_currency", currency), ("inventory_method", method)):
            db.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    return settings(database)


# ---------------------------------------------------------------- master data
def list_warehouses(database):
    with database.connect() as db: return [dict(r) for r in db.execute("SELECT * FROM warehouses ORDER BY code")]


def save_warehouse(database, item, user_id):
    name = str(item.get("name") or "").strip(); code = str(item.get("code") or "").strip().upper()
    if not name: raise ValueError("Warehouse name is required")
    with database.connect() as db:
        if not code:
            numbers = [int(r["code"][2:]) for r in db.execute("SELECT code FROM warehouses WHERE code GLOB 'WH[0-9]*'") if r["code"][2:].isdigit()]
            code = f"WH{max(numbers, default=0) + 1:02d}"
        if db.execute("SELECT 1 FROM warehouses WHERE code=? AND id<>?", (code, int(item.get("id") or 0))).fetchone(): raise ValueError(f"Warehouse code {code} is already used")
        if item.get("id"): db.execute("UPDATE warehouses SET code=?,name=?,active=? WHERE id=?", (code, name, 1 if item.get("active", True) else 0, int(item["id"]))); saved = int(item["id"])
        else: saved = db.execute("INSERT INTO warehouses(code,name,active) VALUES(?,?,?)", (code, name, 1 if item.get("active", True) else 0)).lastrowid
    return next(w for w in list_warehouses(database) if w["id"] == saved)


def save_item(database, item, user_id):
    name = str(item.get("name") or "").strip(); sku = str(item.get("sku") or "").strip().upper()
    if not name: raise ValueError("Item name is required")
    reorder = _d(item.get("reorder_level")); price = _d(item.get("sales_price"))
    if reorder < 0 or price < 0: raise ValueError("Reorder level and sales price cannot be negative")
    with database.connect() as db:
        if not sku:
            numbers = [int(r["sku"][4:]) for r in db.execute("SELECT sku FROM inventory_items WHERE sku GLOB 'ITM-[0-9]*'") if r["sku"][4:].isdigit()]
            sku = f"ITM-{max(numbers, default=0) + 1:05d}"
        if db.execute("SELECT 1 FROM inventory_items WHERE sku=? AND id<>?", (sku, int(item.get("id") or 0))).fetchone(): raise ValueError(f"Item code {sku} is already used")
        supplier = item.get("supplier_id")
        if not supplier and str(item.get("supplier_name") or "").strip():
            row = db.execute("SELECT id FROM parties WHERE name=? ORDER BY id LIMIT 1", (str(item["supplier_name"]).strip(),)).fetchone(); supplier = row["id"] if row else None
        unit = str(item.get("unit") or "unit").strip() or "unit"; db.execute("INSERT OR IGNORE INTO item_units(name) VALUES(?)", (unit,))
        default_vat = "0" if str(item.get("default_vat") or "11").strip() in ("0", "0.0", "0%") else "11"
        cost_account = str(item.get("cost_account") or "").split(" - ", 1)[0].strip() or None
        values = (sku, name, unit, str(item.get("category") or "").strip() or None, str(reorder), str(price),
                  1 if item.get("active", True) else 0, str(item.get("notes") or "").strip() or None, str(item.get("barcode") or "").strip() or None,
                  str(item.get("subcategory") or "").strip() or None, str(supplier) if supplier else None, str(item.get("location") or "").strip() or None, default_vat, cost_account)
        if item.get("id"):
            db.execute("UPDATE inventory_items SET sku=?,name=?,unit=?,category=?,reorder_level=?,sales_price=?,active=?,notes=?,barcode=?,subcategory=?,supplier_id=?,location=?,default_vat=?,cost_account=? WHERE id=?", values + (int(item["id"]),)); saved = int(item["id"])
        else:
            saved = db.execute("INSERT INTO inventory_items(sku,name,unit,category,reorder_level,sales_price,active,notes,barcode,subcategory,supplier_id,location,default_vat,cost_account,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values + (utcnow(),)).lastrowid
        db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)", (user_id, "save", "inventory_item", saved, json.dumps({"sku": sku}), utcnow()))
    return next(i for i in list_items(database) if i["id"] == saved)


# ---------------------------------------------------------------- costing engine
def _movements(database, date_to=None, exclude_document_id=None):
    with database.connect() as db:
        rows = [dict(r) for r in db.execute("""SELECT m.*,d.number,d.doc_type,d.doc_date,d.reference,d.party_id,d.invoice_id,p.name party_name,w.code warehouse_code
            FROM stock_movements m JOIN stock_documents d ON d.id=m.document_id LEFT JOIN parties p ON p.id=d.party_id LEFT JOIN warehouses w ON w.id=m.warehouse_id
            ORDER BY d.doc_date,d.id,m.id""")]
    return [r for r in rows if (not date_to or r["doc_date"] <= date_to) and r["document_id"] != exclude_document_id]


def run_costing(database, date_to=None, method=None, callback=None, exclude_document_id=None):
    """Replays every movement in date order. Returns per-item {qty, value, by_warehouse, last_date}.

    Average: each receipt re-weights the cost; issues leave at the running average.
    FIFO: issues consume the oldest receipt layers first. Transfers move quantity only."""
    method = method or settings(database)["method"]; state = {}
    for row in _movements(database, date_to, exclude_document_id):
        item = state.setdefault(row["item_id"], {"qty": ZERO, "value": ZERO, "layers": [], "by_warehouse": {}, "last_date": None, "last_out": None})
        qty = _d(row["quantity"]); cost = _d(row["unit_cost"])
        item["by_warehouse"][row["warehouse_id"]] = item["by_warehouse"].get(row["warehouse_id"], ZERO) + qty
        item["last_date"] = row["doc_date"]
        if row["doc_type"] == "transfer":
            unit = (item["value"] / item["qty"]) if item["qty"] else ZERO
            if callback: callback(row, unit, ZERO)
            continue
        if qty > 0:
            item["qty"] += qty; item["value"] += qty * cost; item["layers"].append([qty, cost]); issued_cost = cost
        else:
            out = -qty
            if method == "fifo":
                remaining = out; total = ZERO
                while remaining > 0 and item["layers"]:
                    layer = item["layers"][0]; take = min(layer[0], remaining); total += take * layer[1]; layer[0] -= take; remaining -= take
                    if layer[0] <= 0: item["layers"].pop(0)
                if remaining > 0: total += remaining * ((item["value"] / item["qty"]) if item["qty"] else ZERO)
                issued_cost = total / out if out else ZERO
            else:
                issued_cost = (item["value"] / item["qty"]) if item["qty"] else ZERO
                if method != "fifo":
                    for layer in item["layers"]: layer[1] = issued_cost
            item["qty"] -= out; item["value"] -= out * issued_cost; item["last_out"] = row["doc_date"]
            if item["qty"] <= 0: item["value"] = ZERO; item["layers"] = []
        if callback: callback(row, issued_cost, qty * issued_cost)
    for item in state.values():
        item["avg"] = (item["value"] / item["qty"]) if item["qty"] > 0 else ZERO
    return state


def list_items(database, date_to=None, include_inactive=True):
    state = run_costing(database, iso_date(date_to) if date_to else None)
    with database.connect() as db:
        items = [dict(r) for r in db.execute("SELECT i.*,p.name supplier_name FROM inventory_items i LEFT JOIN parties p ON p.id=CAST(i.supplier_id AS INTEGER) ORDER BY i.sku")]
        last = {r["item_id"]: r["party_name"] for r in db.execute("""SELECT m.item_id,p.name party_name FROM stock_movements m JOIN stock_documents d ON d.id=m.document_id
            JOIN parties p ON p.id=d.party_id WHERE d.doc_type='receipt' ORDER BY d.doc_date,d.id""")}
    for item in items:
        item["supplier_name"] = item.get("supplier_name") or last.get(item["id"]) or ""
        data = state.get(item["id"], {})
        item["quantity"] = float(data.get("qty", ZERO)); item["average_cost"] = float(data.get("avg", ZERO)); item["stock_value"] = float(data.get("value", ZERO))
        item["reorder_level"] = float(_d(item.get("reorder_level"))); item["sales_price"] = float(_d(item.get("sales_price")))
    return [i for i in items if include_inactive or i["active"]]


# ---------------------------------------------------------------- stock documents
def next_number(database, doc_type, date):
    prefix = DOC_TYPES[doc_type][0]; year = iso_date(date)[:4]
    with database.connect() as db:
        numbers = [int(r["number"].rsplit("-", 1)[-1]) for r in db.execute("SELECT number FROM stock_documents WHERE number LIKE ?", (f"{prefix}-{year}-%",)) if r["number"].rsplit("-", 1)[-1].isdigit()]
    return f"{prefix}-{year}-{max(numbers, default=0) + 1:06d}"


def save_document(database, header, lines, user_id, document_id=None):
    doc_type = str(header.get("doc_type") or "").lower()
    if doc_type not in DOC_TYPES: raise ValueError("Choose the document type")
    date = iso_date(header.get("doc_date"), "Date"); database._assert_period_open(date)
    if not isinstance(lines, list) or not lines: raise ValueError("Add at least one item line")
    with database.connect() as db:
        warehouse = db.execute("SELECT * FROM warehouses WHERE id=? OR code=?", (int(header["warehouse_id"]) if str(header.get("warehouse_id") or "").isdigit() else -1, str(header.get("warehouse_id") or "MAIN"))).fetchone()
        if not warehouse: raise ValueError("Choose the warehouse")
        target = None
        if doc_type == "transfer":
            target = db.execute("SELECT * FROM warehouses WHERE id=? OR code=?", (int(header["to_warehouse_id"]) if str(header.get("to_warehouse_id") or "").isdigit() else -1, str(header.get("to_warehouse_id") or ""))).fetchone()
            if not target or target["id"] == warehouse["id"]: raise ValueError("Choose a different destination warehouse for the transfer")
        items = {}; normalized = []
        for index, line in enumerate(lines, 1):
            code = str(line.get("sku") or "").strip().upper()
            item = db.execute("SELECT * FROM inventory_items WHERE sku=? OR id=?", (code, int(line["item_id"]) if str(line.get("item_id") or "").isdigit() else -1)).fetchone()
            if not item: raise ValueError(f"Line {index}: item {code or line.get('item_id')} was not found")
            qty = _d(line.get("quantity")); cost = _d(line.get("unit_cost"))
            if qty <= 0: raise ValueError(f"Line {index}: quantity must be above zero")
            if cost < 0: raise ValueError(f"Line {index}: unit cost cannot be negative")
            if DOC_TYPES[doc_type][2] > 0 and not cost and doc_type != "adjustment_in": raise ValueError(f"Line {index}: enter the unit cost of {item['sku']}")
            normalized.append((item, qty, cost, _d(line.get("sales_price")))); items[item["id"]] = items.get(item["id"], ZERO) + qty
    # Stock may not go negative: check the quantity available in the warehouse on the document date.
    if DOC_TYPES[doc_type][2] <= 0:
        state = run_costing(database, date) if not document_id else _state_without(database, date, document_id)
        for item_id, qty in items.items():
            available = state.get(item_id, {}).get("by_warehouse", {}).get(warehouse["id"], ZERO)
            if qty > available:
                sku = next(n[0]["sku"] for n in normalized if n[0]["id"] == item_id)
                raise ValueError(f"Not enough stock of {sku} in {warehouse['code']} on {display_date(date)}: available {available:,.3f}, requested {qty:,.3f}")
    with database.connect() as db:
        if document_id:
            old = db.execute("SELECT * FROM stock_documents WHERE id=?", (int(document_id),)).fetchone()
            if not old: raise KeyError("Stock document not found")
            database._assert_period_open(old["doc_date"]); number = old["number"]
            db.execute("DELETE FROM stock_movements WHERE document_id=?", (int(document_id),))
            db.execute("""UPDATE stock_documents SET doc_type=?,doc_date=?,warehouse_id=?,to_warehouse_id=?,party_id=?,reference=?,notes=? WHERE id=?""",
                (doc_type, date, warehouse["id"], target["id"] if target else None, header.get("party_id") or None, header.get("reference") or None, header.get("notes") or None, int(document_id)))
            saved = int(document_id)
        else:
            number = str(header.get("number") or "").strip() or next_number(database, doc_type, date)
            saved = db.execute("""INSERT INTO stock_documents(number,doc_type,doc_date,warehouse_id,to_warehouse_id,party_id,invoice_id,reference,notes,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (number, doc_type, date, warehouse["id"], target["id"] if target else None, header.get("party_id") or None,
                header.get("invoice_id") or None, header.get("reference") or None, header.get("notes") or None, user_id, utcnow())).lastrowid
        sign = DOC_TYPES[doc_type][2]
        for position, (item, qty, cost, price) in enumerate(normalized, 1):
            if doc_type == "transfer":
                for warehouse_id, signed in ((warehouse["id"], -qty), (target["id"], qty)):
                    db.execute("""INSERT INTO stock_movements(item_id,movement_date,quantity,unit_cost,source_type,source_id,warehouse_id,document_id,movement_type,line_no)
                        VALUES(?,?,?,?,?,?,?,?,?,?)""", (item["id"], date, str(signed), "0", "stock", saved, warehouse_id, saved, doc_type, position))
            else:
                db.execute("""INSERT INTO stock_movements(item_id,movement_date,quantity,unit_cost,source_type,source_id,warehouse_id,document_id,movement_type,sales_price,line_no)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (item["id"], date, str(qty * sign), str(cost), "stock", saved, warehouse["id"], saved, doc_type, str(price), position))
        db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
            (user_id, "save", "stock_document", saved, json.dumps({"number": number, "type": doc_type, "lines": len(normalized)}), utcnow()))
    return get_document(database, saved)


def _state_without(database, date, document_id):
    return run_costing(database, date, exclude_document_id=int(document_id))


def get_document(database, document_id):
    with database.connect() as db:
        doc = db.execute("""SELECT d.*,w.code warehouse_code,w.name warehouse_name,t.code to_warehouse_code,p.name party_name FROM stock_documents d
            JOIN warehouses w ON w.id=d.warehouse_id LEFT JOIN warehouses t ON t.id=d.to_warehouse_id LEFT JOIN parties p ON p.id=d.party_id WHERE d.id=?""", (int(document_id),)).fetchone()
        if not doc: raise KeyError("Stock document not found")
        lines = [dict(r) for r in db.execute("""SELECT m.*,i.sku,i.name,i.unit FROM stock_movements m JOIN inventory_items i ON i.id=m.item_id
            WHERE m.document_id=? ORDER BY m.line_no,m.id""", (int(document_id),))]
    doc = dict(doc)
    if doc["doc_type"] == "transfer": lines = [l for l in lines if _d(l["quantity"]) > 0]
    for line in lines: line["quantity"] = float(abs(_d(line["quantity"]))); line["unit_cost"] = float(_d(line["unit_cost"])); line["sales_price"] = float(_d(line.get("sales_price")))
    doc["lines"] = lines
    return doc


def list_documents(database):
    with database.connect() as db:
        return [dict(r) for r in db.execute("""SELECT d.id,d.number,d.doc_type,d.doc_date,w.code warehouse_code,t.code to_warehouse_code,p.name party_name,d.reference,d.invoice_id,
            (SELECT COUNT(DISTINCT line_no) FROM stock_movements m WHERE m.document_id=d.id) lines FROM stock_documents d JOIN warehouses w ON w.id=d.warehouse_id
            LEFT JOIN warehouses t ON t.id=d.to_warehouse_id LEFT JOIN parties p ON p.id=d.party_id ORDER BY d.doc_date DESC,d.id DESC""")]


def delete_document(database, document_id, user_id):
    doc = get_document(database, document_id); database._assert_period_open(doc["doc_date"])
    if DOC_TYPES[doc["doc_type"]][2] > 0:  # removing stock that was already issued afterwards would make it negative
        _check_after_removal(database, document_id)
    with database.connect() as db:
        db.execute("DELETE FROM stock_movements WHERE document_id=?", (int(document_id),)); db.execute("DELETE FROM stock_documents WHERE id=?", (int(document_id),))
        db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)", (user_id, "delete", "stock_document", int(document_id), json.dumps({"number": doc["number"]}), utcnow()))
    return {"deleted": int(document_id)}


def _check_after_removal(database, document_id):
    balances = {}
    for row in _movements(database, exclude_document_id=int(document_id)):
        key = (row["item_id"], row["warehouse_id"]); balances[key] = balances.get(key, ZERO) + _d(row["quantity"])
        if balances[key] < 0: raise ValueError(f"This document cannot be deleted: the stock issued later ({row['number']} on {display_date(row['doc_date'])}) would become negative")


def issue_for_invoice(database, invoice_id, lines, user_id):
    """Move stock for the item lines of an invoice, linked to that invoice.

    A normal sale takes goods out (Stock Issue) and a purchase brings them in (Stock Receipt).
    A credit note reverses that movement: a sales credit note (goods returned by the customer)
    brings the goods back in (Receipt), and a purchase credit note (goods returned to the supplier)
    sends them back out (Issue)."""
    with database.connect() as db:
        invoice = db.execute("SELECT * FROM invoices WHERE id=?", (int(invoice_id),)).fetchone()
        for old in db.execute("SELECT id FROM stock_documents WHERE invoice_id=?", (int(invoice_id),)).fetchall():
            db.execute("DELETE FROM stock_movements WHERE document_id=?", (old["id"],)); db.execute("DELETE FROM stock_documents WHERE id=?", (old["id"],))
    stock_lines = [{"sku": l.get("item_code") or l.get("sku"), "quantity": l.get("quantity"), "sales_price": l.get("unit_price")} for l in lines if l.get("item_code") or l.get("sku")]
    if not stock_lines or not invoice: return None
    returned = str((invoice["doc_subtype"] if "doc_subtype" in invoice.keys() else "") or "").endswith("credit_note")
    issue = (invoice["kind"] == "sale") != returned  # a credit note reverses the normal direction
    doc_type = "issue" if issue else "receipt"
    header = {"doc_type": doc_type, "doc_date": invoice["invoice_date"], "warehouse_id": lines[0].get("warehouse") or "MAIN",
              "party_id": invoice["party_id"], "invoice_id": int(invoice_id), "reference": invoice["invoice_number"], "notes": f"Invoice {invoice['invoice_number']}"}
    source_lines = [l for l in lines if l.get("item_code") or l.get("sku")]
    if doc_type == "receipt":
        if invoice["kind"] != "sale":
            # Purchase receipt: value the goods at the purchase price on the invoice line.
            for line, source in zip(stock_lines, source_lines): line["unit_cost"] = source.get("unit_price")
        else:
            # Sales credit note (goods returned by the customer): bring them back at the current average cost.
            state = run_costing(database, iso_date(invoice["invoice_date"]))
            with database.connect() as db:
                for line in stock_lines:
                    found = db.execute("SELECT id FROM inventory_items WHERE sku=?", (str(line["sku"] or "").strip().upper(),)).fetchone()
                    average = state.get(found["id"], {}).get("avg", ZERO) if found else ZERO
                    line["unit_cost"] = float(average) if average and float(average) > 0 else float(_d(line.get("sales_price")))
    return save_document(database, header, stock_lines, user_id)


def remove_invoice_documents(db, invoice_id):
    for old in db.execute("SELECT id FROM stock_documents WHERE invoice_id=?", (int(invoice_id),)).fetchall():
        db.execute("DELETE FROM stock_movements WHERE document_id=?", (old["id"],)); db.execute("DELETE FROM stock_documents WHERE id=?", (old["id"],))


# ---------------------------------------------------------------- reports
def _names(database):
    with database.connect() as db:
        items = {r["id"]: dict(r) for r in db.execute("SELECT * FROM inventory_items")}
        warehouses = {r["id"]: dict(r) for r in db.execute("SELECT * FROM warehouses")}
    return items, warehouses


def build_report(database, report, options):
    options = dict(options or {}); inv = settings(database); method = options.get("method") or inv["method"]; currency = inv["currency"]
    date_to = iso_date(options["date_to"]) if options.get("date_to") else datetime.now().strftime("%Y-%m-%d")
    date_from = iso_date(options["date_from"]) if options.get("date_from") else f"{date_to[:4]}-01-01"
    warehouse = options.get("warehouse_id"); warehouse = int(warehouse) if str(warehouse or "").isdigit() else None
    items, warehouses = _names(database); company = database.settings(); sections = []
    first_item=items.get(int(options["item_id"])) if options.get("item_id") else None
    last_item=items.get(int(options["item_to_id"])) if options.get("item_to_id") else first_item
    if options.get("item_id") and not first_item: raise ValueError("Choose a valid Item From")
    if options.get("item_to_id") and not last_item: raise ValueError("Choose a valid Item To")
    if first_item and last_item and first_item["sku"]>last_item["sku"]: raise ValueError("Item From must be before Item To")
    filters = [f"{label}: {options[key]}" for key, label in (("category", "Category"), ("subcategory", "Subcategory"), ("unit", "Unit"), ("supplier_name", "Supplier")) if options.get(key)]
    wanted = lambda item_id: not options.get("item_id") or int(options["item_id"]) == item_id
    category = str(options.get("category") or "").strip(); subcategory = str(options.get("subcategory") or "").strip()
    unit_filter = str(options.get("unit") or "").strip(); supplier_filter = str(options.get("supplier_id") or "").strip()
    listed = {i["id"]: i for i in list_items(database)} if supplier_filter else {}
    def in_category(item_id):
        item = items[item_id]
        if first_item and not (first_item["sku"]<=item["sku"]<=last_item["sku"]): return False
        if category and (item.get("category") or "") != category: return False
        if subcategory and (item.get("subcategory") or "") != subcategory: return False
        if unit_filter and (item.get("unit") or "") != unit_filter: return False
        if supplier_filter:
            data = listed.get(item_id, {})
            if str(item.get("supplier_id") or "") != supplier_filter and data.get("supplier_name") != options.get("supplier_name"): return False
        return True
    if report in ("turnover", "supplier_stock", "count_variances"):
        return additional_inventory_report(database, report, options, items, warehouses, in_category, currency, method, date_from, date_to, warehouse, company)
    if report == "analysis3d":
        return inventory_analysis(database, options, items, warehouses, in_category, currency, method, date_from, date_to, warehouse, company)
    if report == "health":
        return inventory_health(database, options, items, in_category, currency, method, date_to, warehouse, company)
    if report == "valuation":
        state = run_costing(database, date_to, method)
        headers = ["Item Code", "Item", "Category", "Unit", "Quantity", f"Unit Cost ({currency})", f"Stock Value ({currency})", "Sales Price", "Value at Sales Price", "Reorder Level", "Status"]
        rows = []; total = ZERO; sales_total = ZERO; quantities_by_unit = {}
        for item_id, item in sorted(items.items(), key=lambda pair: pair[1]["sku"]):
            if not in_category(item_id): continue
            data = state.get(item_id, {"qty": ZERO, "avg": ZERO, "by_warehouse": {}})
            qty = data["by_warehouse"].get(warehouse, ZERO) if warehouse else data["qty"]
            if not qty and not options.get("include_zero"): continue
            value = (qty * data["avg"]).quantize(Decimal("0.01")); price = _d(item.get("sales_price")); reorder = _d(item.get("reorder_level"))
            total += value; sales_total += qty * price
            quantities_by_unit[item["unit"]]=quantities_by_unit.get(item["unit"],ZERO)+qty
            rows.append([item["sku"], item["name"], item.get("category") or "", item["unit"], qty, data["avg"].quantize(Decimal("0.0001")), value, price, (qty * price).quantize(Decimal("0.01")), reorder,
                         "Reorder" if reorder and qty <= reorder else "OK"])
        # group by category with a subtotal per category
        grouped = []; totals_index = []
        for name in sorted({r[2] or "(no category)" for r in rows}):
            members = [r for r in rows if (r[2] or "(no category)") == name]
            grouped += members
            grouped.append([f"Subtotal {name}", f"{len(members)} item(s)", "", "", sum((m[4] for m in members), ZERO), "", sum((m[6] for m in members), ZERO), "",
                            sum((m[8] for m in members), ZERO), "", ""]); totals_index.append(len(grouped) - 1)
        count = len(rows); rows = grouped
        rows.append(["TOTAL", f"{count} item(s)", "", "", "", "", total, "", sales_total.quantize(Decimal("0.01")), "", ""])
        title = "Stock Valuation"; sections.append({"heading": f"Stock valuation at {display_date(date_to)} - {'weighted average' if method != 'fifo' else 'FIFO'}" + (f" - {warehouses[warehouse]['code']}" if warehouse else " - all warehouses"),
                                                     "headers": headers, "rows": rows, "total_rows": totals_index + [len(rows) - 1]})
        if not warehouse and len(warehouses) > 1:
            by_wh = [[w["code"], w["name"], sum((data["by_warehouse"].get(wid, ZERO) * data["avg"] for data in state.values()), ZERO).quantize(Decimal("0.01"))] for wid, w in warehouses.items()]
            sections.append({"heading": "Value by warehouse", "headers": ["Warehouse", "Name", f"Value ({currency})"], "rows": by_wh, "total_rows": []})
        sections.append({"heading":"Total stock quantity by unit", "headers":["Unit","Total stock quantity"],
                         "rows":[[unit,quantity] for unit,quantity in sorted(quantities_by_unit.items())],"total_rows":[]})
    elif report == "stock_card":
        first = items.get(int(options.get("item_id") or 0))
        if not first: raise ValueError("Choose Stock Card Item From")
        last = items.get(int(options.get("item_to_id") or options["item_id"]))
        if not last: raise ValueError("Choose a valid Stock Card Item To")
        if first["sku"] > last["sku"]: raise ValueError("Stock Card Item From must be before Item To")
        selected = [item_id for item_id, item in sorted(items.items(), key=lambda pair: pair[1]["sku"])
                    if first["sku"] <= item["sku"] <= last["sku"] and in_category(item_id)]
        cards = {item_id: {"opening_qty": ZERO, "opening_value": ZERO, "lines": []} for item_id in selected}
        def record(row, unit, value):
            card = cards.get(row["item_id"])
            if card is None or (warehouse and row["warehouse_id"] != warehouse): return
            qty = _d(row["quantity"]); cost_value = qty * (_d(row["unit_cost"]) if qty > 0 and row["doc_type"] != "transfer" else unit)
            if row["doc_date"] < date_from:
                card["opening_qty"] += qty; card["opening_value"] += cost_value; return
            card["lines"].append([display_date(row["doc_date"]), row["number"], DOC_TYPES[row["doc_type"]][1], row.get("warehouse_code") or "", row.get("party_name") or row.get("reference") or "",
                                  qty if qty > 0 else "", -qty if qty < 0 else "", (unit if qty < 0 or row["doc_type"] == "transfer" else _d(row["unit_cost"])).quantize(Decimal("0.0001")), cost_value.quantize(Decimal("0.01"))])
        run_costing(database, date_to, method, record)
        card_totals={}
        for item_id in selected:
            card = cards[item_id]; qty_balance = card["opening_qty"]; value_balance = card["opening_value"]
            rows = [["", "", "Opening balance", "", "", "", "", "", value_balance.quantize(Decimal("0.01")), qty_balance, value_balance.quantize(Decimal("0.01"))]]
            total_in = ZERO; total_out = ZERO
            for line in card["lines"]:
                qty = _d(line[5] or 0) - _d(line[6] or 0); qty_balance += qty; value_balance += line[8]
                total_in += _d(line[5] or 0); total_out += _d(line[6] or 0)
                rows.append(line + [qty_balance, value_balance.quantize(Decimal("0.01"))])
            rows.append(["", "", "TOTAL / CLOSING", "", "", total_in, total_out, "", "", qty_balance, value_balance.quantize(Decimal("0.01"))])
            item = items[item_id]
            unit=item["unit"]; card_totals[unit]=card_totals.get(unit,ZERO)+qty_balance
            sections.append({"heading": f"{item['sku']} - {item['name']} ({item['unit']}) | {display_date(date_from)} to {display_date(date_to)}" + (f" - {warehouses[warehouse]['code']}" if warehouse else ""),
                             "headers": ["Date", "Document", "Type", "Warehouse", "Party / Reference", "In", "Out", f"Unit Cost ({currency})", "Value", "Balance Qty", "Balance Value"],
                             "rows": rows, "total_rows": [0, len(rows) - 1]})
        title = "Stock Cards" if options.get("item_to_id") else "Stock Card"
        sections.append({"heading":"Total closing stock by unit", "headers":["Unit","Total closing quantity"],
                         "rows":[[unit,quantity] for unit,quantity in sorted(card_totals.items())],"total_rows":[]})
    elif report == "movements":
        rows = []
        def record(row, unit, value):
            if row["doc_date"] < date_from or not wanted(row["item_id"]) or not in_category(row["item_id"]) or (warehouse and row["warehouse_id"] != warehouse): return
            if options.get("doc_type") and row["doc_type"] != options["doc_type"]: return
            qty = _d(row["quantity"]); unit_cost = _d(row["unit_cost"]) if qty > 0 and row["doc_type"] != "transfer" else unit
            rows.append([display_date(row["doc_date"]), row["number"], DOC_TYPES[row["doc_type"]][1], items[row["item_id"]]["sku"], items[row["item_id"]]["name"], row.get("warehouse_code") or "",
                         row.get("party_name") or "", qty, unit_cost.quantize(Decimal("0.0001")), (qty * unit_cost).quantize(Decimal("0.01"))])
        run_costing(database, date_to, method, record); title = "Stock Movements"
        sections.append({"heading": f"Movements {display_date(date_from)} to {display_date(date_to)}", "headers": ["Date", "Document", "Type", "Item Code", "Item", "Warehouse", "Party", "Quantity (+in / -out)", "Unit Cost", "Value"],
                         "rows": rows or [["No movements"] + [""] * 9], "total_rows": []})
    elif report == "margin":
        sold = {}
        def record(row, unit, value):
            if row["doc_type"] != "issue" or row["doc_date"] < date_from or not in_category(row["item_id"]): return
            data = sold.setdefault(row["item_id"], {"qty": ZERO, "cost": ZERO, "sales": ZERO})
            qty = -_d(row["quantity"]); data["qty"] += qty; data["cost"] += qty * unit; data["sales"] += qty * _d(row.get("sales_price"))
        run_costing(database, date_to, method, record)
        rows = []; totals = [ZERO, ZERO, ZERO]
        for item_id, data in sorted(sold.items(), key=lambda pair: -pair[1]["sales"]):
            margin = data["sales"] - data["cost"]; totals[0] += data["sales"]; totals[1] += data["cost"]; totals[2] += margin
            rows.append([items[item_id]["sku"], items[item_id]["name"], data["qty"], data["sales"].quantize(Decimal("0.01")), data["cost"].quantize(Decimal("0.01")), margin.quantize(Decimal("0.01")),
                         f"{(margin / data['sales'] * 100):.1f}%" if data["sales"] else ""])
        rows.append(["TOTAL", "", "", totals[0].quantize(Decimal("0.01")), totals[1].quantize(Decimal("0.01")), totals[2].quantize(Decimal("0.01")), f"{(totals[2] / totals[0] * 100):.1f}%" if totals[0] else ""])
        title = "Sales Margin (Cost of Goods Sold)"
        sections.append({"heading": f"Items issued {display_date(date_from)} to {display_date(date_to)} - sales at invoice price, cost at {'FIFO' if method == 'fifo' else 'weighted average'}",
                         "headers": ["Item Code", "Item", "Quantity Sold", f"Sales ({currency})", "Cost of Goods Sold", "Gross Margin", "Margin %"], "rows": rows, "total_rows": [len(rows) - 1]})
    elif report == "ageing":
        return ageing_report(database, options, items, warehouses, in_category, currency, method, date_to, company)
    elif report == "summary":
        return summary_report(database, options, items, warehouses, in_category, currency, method, date_to, company)
    elif report in ("reorder", "slow"):
        state = run_costing(database, date_to, method); rows = []
        cutoff = (datetime.strptime(date_to, "%Y-%m-%d") - timedelta(days=int(options.get("days") or 90))).strftime("%Y-%m-%d")
        for item_id, item in sorted(items.items(), key=lambda pair: pair[1]["sku"]):
            if not item["active"] or not in_category(item_id): continue
            data = state.get(item_id, {"qty": ZERO, "avg": ZERO, "last_out": None, "value": ZERO}); reorder = _d(item.get("reorder_level"))
            if report == "reorder" and reorder > 0 and data["qty"] <= reorder:
                rows.append([item["sku"], item["name"], item["unit"], data["qty"], reorder, max(ZERO, reorder * 2 - data["qty"]), data["avg"].quantize(Decimal("0.0001"))])
            if report == "slow" and data["qty"] > 0 and (not data.get("last_out") or data["last_out"] < cutoff):
                rows.append([item["sku"], item["name"], item["unit"], data["qty"], data["value"].quantize(Decimal("0.01")), display_date(data.get("last_out")) if data.get("last_out") else "never sold"])
        if report == "reorder":
            title = "Reorder Report"; sections.append({"heading": f"Items at or below their reorder level on {display_date(date_to)}", "headers": ["Item Code", "Item", "Unit", "On Hand", "Reorder Level", "Suggested Order", "Unit Cost"],
                                                          "rows": rows or [["No item below its reorder level"] + [""] * 6], "total_rows": []})
        else:
            title = "Slow-moving Stock"; sections.append({"heading": f"Items in stock with no issue since {display_date(cutoff)} ({int(options.get('days') or 90)} days)",
                                                          "headers": ["Item Code", "Item", "Unit", "On Hand", f"Value ({currency})", "Last Issue"], "rows": rows or [["No slow-moving items"] + [""] * 5], "total_rows": []})
    else: raise ValueError("Unknown inventory report")
    meta = [f"Company: {company.get('company_name') or '-'}   Inventory currency: {currency}   Costing: {'FIFO' if method == 'fifo' else 'Weighted average'}",
            f"Period: {display_date(date_from)} to {display_date(date_to)}" + (("   Filters: " + ", ".join(filters)) if filters else "")]
    return {"title": title, "meta": meta, "sections": sections}


# ---------------------------------------------------------------- year end
def stock_value(database, date_to, method=None):
    state = run_costing(database, iso_date(date_to), method)
    return sum((data["value"] for data in state.values()), ZERO).quantize(Decimal("0.01"))


def post_stock_variation(database, year, user_id):
    """Periodic method: cancel the opening stock (Dr 6051 / Cr 37) and book the closing stock (Dr 37 / Cr 6052)."""
    year = int(year); inv = settings(database); currency = inv["currency"]
    with database.connect() as db:
        for row in db.execute("SELECT id FROM journal_entries WHERE source_type='journal_voucher' AND voucher_type='06' AND description LIKE ?", (f"STOCK VARIATION - {year}%",)).fetchall():
            db.execute("DELETE FROM journal_entries WHERE id=?", (row["id"],))
    # The stock already in the ledger (account 37 at year end, before this voucher) is cancelled; the counted closing stock replaces it.
    opening = _ledger_stock(database, f"{year}-12-31", currency); closing = stock_value(database, f"{year}-12-31")
    if not opening and not closing: return {"year": year, "opening": 0.0, "closing": 0.0, "voucher": None}
    lines = []
    if opening > 0: lines += [{"account_code": OPENING_ACCOUNT, "line_currency": currency, "side": "D", "amount": str(opening)}, {"account_code": STOCK_ACCOUNT, "line_currency": currency, "side": "C", "amount": str(opening)}]
    elif opening < 0: lines += [{"account_code": STOCK_ACCOUNT, "line_currency": currency, "side": "D", "amount": str(-opening)}, {"account_code": OPENING_ACCOUNT, "line_currency": currency, "side": "C", "amount": str(-opening)}]
    if closing: lines += [{"account_code": STOCK_ACCOUNT, "line_currency": currency, "side": "D", "amount": str(closing)}, {"account_code": CLOSING_ACCOUNT, "line_currency": currency, "side": "C", "amount": str(closing)}]
    voucher = database.save_journal_voucher({"entry_date": f"31-12-{year}", "description": f"STOCK VARIATION - {year}: opening {opening:,.2f} / closing {closing:,.2f} {currency}",
                                             "currency": currency, "voucher_type": "06"}, lines, user_id)
    return {"year": year, "opening": float(opening), "closing": float(closing), "variation": float(closing - opening), "voucher": voucher["voucher"]["entry_number"]}


def _ledger_stock(database, date_to, currency):
    from ledger_reports import _load_lines, _digits
    column = currency if currency in ("LBP", "USD") else "account"
    total = sum((row["signed"][column] for row in _load_lines(database, {"posting_status": "posted"})
                 if _digits(row["code"]).startswith(STOCK_ACCOUNT) and row["iso_date"] <= date_to and (column != "account" or row["account_currency"] == currency)), ZERO)
    return total.quantize(Decimal("0.01"))


def _opening_value(database, year):
    value = stock_value(database, f"{int(year) - 1}-12-31")
    with database.connect() as db:
        rows = db.execute("""SELECT m.quantity,m.unit_cost FROM stock_movements m JOIN stock_documents d ON d.id=m.document_id
            WHERE d.doc_type='opening' AND d.doc_date>=? AND d.doc_date<=?""", (f"{int(year)}-01-01", f"{int(year)}-12-31")).fetchall()
    return (value + sum((_d(r["quantity"]) * _d(r["unit_cost"]) for r in rows), ZERO)).quantize(Decimal("0.01"))


def carry_forward(source, target, year, user_id):
    """New fiscal-year file: copy items and warehouses, and post the closing stock of year-1 as its Opening Stock."""
    year = int(year); state = run_costing(source, f"{year - 1}-12-31")
    with source.connect() as src: items = [dict(r) for r in src.execute("SELECT * FROM inventory_items")]; warehouses = [dict(r) for r in src.execute("SELECT * FROM warehouses")]
    with target.connect() as db:
        for w in warehouses: db.execute("INSERT OR IGNORE INTO warehouses(id,code,name,active) VALUES(?,?,?,?)", (w["id"], w["code"], w["name"], w["active"]))
        for i in items:
            db.execute("""INSERT INTO inventory_items(id,sku,name,unit,quantity,average_cost,category,reorder_level,sales_price,active,notes,barcode,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET sku=excluded.sku,name=excluded.name,unit=excluded.unit,category=excluded.category,reorder_level=excluded.reorder_level,sales_price=excluded.sales_price,active=excluded.active""",
                (i["id"], i["sku"], i["name"], i["unit"], "0", "0", i.get("category"), i.get("reorder_level") or "0", i.get("sales_price") or "0", i.get("active", 1), i.get("notes"), i.get("barcode"), i.get("created_at")))
        for old in db.execute("SELECT id FROM stock_documents WHERE doc_type='opening' AND number LIKE ?", (f"OPN-{year}-%",)).fetchall():
            db.execute("DELETE FROM stock_movements WHERE document_id=?", (old["id"],)); db.execute("DELETE FROM stock_documents WHERE id=?", (old["id"],))
    created = []
    by_warehouse = {}
    for item_id, data in state.items():
        for warehouse_id, qty in data["by_warehouse"].items():
            if qty > 0: by_warehouse.setdefault(warehouse_id, []).append({"item_id": item_id, "quantity": qty, "unit_cost": data["avg"].quantize(Decimal("0.0001"))})
    for warehouse_id, lines in by_warehouse.items():
        doc = save_document(target, {"doc_type": "opening", "doc_date": f"01-01-{year}", "warehouse_id": warehouse_id, "notes": f"Closing stock of {year - 1}"}, lines, user_id)
        created.append(doc["number"])
    return created


# ---------------------------------------------------------------- categories, units
def list_categories(database):
    with database.connect() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM item_categories ORDER BY name")]
        units = [r["name"] for r in db.execute("SELECT name FROM item_units ORDER BY name")]
        for name in {r["category"] for r in db.execute("SELECT DISTINCT category FROM inventory_items WHERE category IS NOT NULL AND category<>''")}:
            if not any(c["name"] == name and not c["parent_id"] for c in rows): rows.append({"id": None, "name": name, "parent_id": None})
    top = [c for c in rows if not c["parent_id"]]
    return {"categories": [{"id": c["id"], "name": c["name"], "subcategories": [s["name"] for s in rows if s["parent_id"] and s["parent_id"] == c["id"]]} for c in sorted(top, key=lambda c: c["name"])],
            "units": units}


def save_category(database, item, user_id):
    name = str(item.get("name") or "").strip(); kind = str(item.get("kind") or "category")
    if not name: raise ValueError("Enter the name")
    with database.connect() as db:
        if kind == "unit": db.execute("INSERT OR IGNORE INTO item_units(name) VALUES(?)", (name,))
        elif kind == "subcategory":
            parent = str(item.get("parent") or "").strip()
            if not parent: raise ValueError("Choose the category of the subcategory")
            db.execute("INSERT OR IGNORE INTO item_categories(name,parent_id) VALUES(?,NULL)", (parent,))
            parent_id = db.execute("SELECT id FROM item_categories WHERE name=? AND parent_id IS NULL", (parent,)).fetchone()["id"]
            db.execute("INSERT OR IGNORE INTO item_categories(name,parent_id) VALUES(?,?)", (name, parent_id))
        else:
            if not db.execute("SELECT 1 FROM item_categories WHERE name=? AND parent_id IS NULL", (name,)).fetchone(): db.execute("INSERT INTO item_categories(name,parent_id) VALUES(?,NULL)", (name,))
    return list_categories(database)


def find_or_create_item(database, name, unit="unit", code=None, user_id=None, supplier_id=None):
    """Used by the purchase import: an item that does not exist yet is created automatically."""
    with database.connect() as db:
        row = db.execute("SELECT * FROM inventory_items WHERE (sku=? AND ?<>'') OR lower(name)=lower(?) ORDER BY id LIMIT 1", (str(code or "").upper(), str(code or ""), str(name or ""))).fetchone()
    if row: return dict(row)
    return save_item(database, {"sku": code or "", "name": name, "unit": unit or "unit", "supplier_id": supplier_id}, user_id)


# ---------------------------------------------------------------- physical inventory
def count_sheet(database, warehouse_id, date):
    """System quantity of every active item in a warehouse on a date, ready for counting."""
    date = iso_date(date); state = run_costing(database, date); warehouse = int(warehouse_id)
    return [{"item_id": i["id"], "sku": i["sku"], "name": i["name"], "unit": i["unit"], "category": i.get("category") or "", "location": i.get("location") or "",
             "system_qty": float(state.get(i["id"], {}).get("by_warehouse", {}).get(warehouse, ZERO)), "unit_cost": float(state.get(i["id"], {}).get("avg", ZERO))}
            for i in list_items(database, include_inactive=False)]


def save_count(database, header, lines, user_id, count_id=None, post=False):
    date = iso_date(header.get("count_date"), "Count date"); warehouse = int(header.get("warehouse_id") or 0)
    if not warehouse: raise ValueError("Choose the warehouse")
    stock = {row["item_id"]: row for row in count_sheet(database, warehouse, date)}
    clean = []
    for line in lines or []:
        if line.get("counted") in (None, ""): continue
        counted = _d(line["counted"])
        if counted < 0: raise ValueError(f"{line.get('sku')}: the counted quantity cannot be negative")
        item_id = int(line["item_id"])
        if item_id not in stock: raise ValueError(f"Item {item_id} is not on the stock sheet")
        clean.append({"item_id": item_id, "sku": line.get("sku"), "counted": str(counted),
                      "system_qty": str(stock[item_id]["system_qty"]), "unit_cost": str(stock[item_id]["unit_cost"])})
    with database.connect() as db:
        if count_id:
            row = db.execute("SELECT * FROM physical_counts WHERE id=?", (int(count_id),)).fetchone()
            if not row: raise KeyError("Count not found")
            if row["status"] == "posted": raise ValueError("This count is already posted to the stock")
            db.execute("UPDATE physical_counts SET count_date=?,warehouse_id=?,lines=?,notes=? WHERE id=?", (date, warehouse, json.dumps(clean), header.get("notes"), int(count_id))); saved = int(count_id)
        else:
            numbers = [int(r["number"].rsplit("-", 1)[-1]) for r in db.execute("SELECT number FROM physical_counts WHERE number LIKE ?", (f"PHC-{date[:4]}-%",)) if r["number"].rsplit("-", 1)[-1].isdigit()]
            saved = db.execute("INSERT INTO physical_counts(number,count_date,warehouse_id,lines,notes,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                (f"PHC-{date[:4]}-{max(numbers, default=0) + 1:06d}", date, warehouse, json.dumps(clean), header.get("notes"), user_id, utcnow())).lastrowid
    if post:
        system = {l["item_id"]: l for l in count_sheet(database, warehouse, date)}; gains = []; losses = []
        for line in clean:
            difference = _d(line["counted"]) - _d(system.get(line["item_id"], {}).get("system_qty", 0))
            if difference > 0: gains.append({"item_id": line["item_id"], "quantity": difference, "unit_cost": system.get(line["item_id"], {}).get("unit_cost", 0) or 0})
            elif difference < 0: losses.append({"item_id": line["item_id"], "quantity": -difference})
        numbers = []
        with database.connect() as db: number = db.execute("SELECT number FROM physical_counts WHERE id=?", (saved,)).fetchone()["number"]
        if gains: numbers.append(save_document(database, {"doc_type": "adjustment_in", "doc_date": date, "warehouse_id": warehouse, "reference": number, "notes": f"Physical count {number}"}, gains, user_id)["number"])
        if losses: numbers.append(save_document(database, {"doc_type": "adjustment_out", "doc_date": date, "warehouse_id": warehouse, "reference": number, "notes": f"Physical count {number}"}, losses, user_id)["number"])
        with database.connect() as db: db.execute("UPDATE physical_counts SET status='posted',adjustment_numbers=? WHERE id=?", (", ".join(numbers), saved))
    return get_count(database, saved)


def get_count(database, count_id):
    with database.connect() as db:
        row = db.execute("SELECT c.*,w.code warehouse_code FROM physical_counts c JOIN warehouses w ON w.id=c.warehouse_id WHERE c.id=?", (int(count_id),)).fetchone()
    if not row: raise KeyError("Count not found")
    result = dict(row); result["lines"] = json.loads(result["lines"] or "[]"); return result


def list_counts(database):
    with database.connect() as db:
        return [dict(r) for r in db.execute("SELECT c.id,c.number,c.count_date,c.status,c.adjustment_numbers,w.code warehouse_code FROM physical_counts c JOIN warehouses w ON w.id=c.warehouse_id ORDER BY c.id DESC")]


# ---------------------------------------------------------------- ageing and summary
def inventory_analysis(database, options, items, warehouses, in_category, currency, method, date_from, date_to, warehouse, company):
    """Pivot items/categories/suppliers against warehouses or months, by quantity or cost value."""
    row_dim = options.get("rows") or "item"; col_dim = options.get("columns") or "warehouse"; measure = options.get("measure") or "quantity"
    if row_dim not in ("item", "category", "supplier") or col_dim not in ("warehouse", "month") or measure not in ("quantity", "value"):
        raise ValueError("Choose Item, Category or Supplier, Warehouse or Month, and Quantity or Value")
    with database.connect() as db:
        suppliers = {str(r["id"]): r["name"] for r in db.execute("SELECT id,name FROM parties")}
    def group(item):
        if row_dim == "item": return f"{item['sku']} - {item['name']}"
        if row_dim == "category": return item.get("category") or "(No category)"
        return suppliers.get(str(item.get("supplier_id") or ""), "(No supplier)")
    pivot = {}; columns = set()
    def add(item_id, column, quantity, unit_cost):
        item = items.get(item_id)
        if not item or not in_category(item_id): return
        if options.get("item_id") and item_id != int(options["item_id"]): return
        value = quantity if measure == "quantity" else quantity * unit_cost
        label = group(item); cell = pivot.setdefault(label, {}); cell[column] = cell.get(column, ZERO) + value
        columns.add(column)
    if col_dim == "warehouse":
        state = run_costing(database, date_to, method)
        for item_id, data in state.items():
            for warehouse_id, qty in data["by_warehouse"].items():
                if warehouse and warehouse != warehouse_id: continue
                add(item_id, warehouses[warehouse_id]["code"], qty, data["avg"])
        for warehouse_id, name in warehouses.items():
            if not warehouse or warehouse == warehouse_id: columns.add(name["code"])
    else:
        def record(row, unit, value):
            if row["doc_date"] < date_from or row["doc_type"] == "transfer" or (warehouse and warehouse != row["warehouse_id"]): return
            add(row["item_id"], row["doc_date"][:7], _d(row["quantity"]), unit)
        run_costing(database, date_to, method, record)
    ordered = sorted(columns); rows = []; totals = [ZERO] * len(ordered)
    for label, values in sorted(pivot.items()):
        amounts = [values.get(col, ZERO) for col in ordered]
        totals = [a + b for a, b in zip(totals, amounts)]
        rows.append([label] + [v.quantize(Decimal("0.01")) if measure == "value" else v for v in amounts] + [sum(amounts, ZERO)])
    rows.append(["TOTAL"] + [v.quantize(Decimal("0.01")) if measure == "value" else v for v in totals] + [sum(totals, ZERO)])
    return {"title": "Inventory Analysis (3D)", "meta": [f"Company: {company.get('company_name') or '-'}", f"Rows: {row_dim.title()}   Columns: {col_dim.title()}   Measure: {measure.title()} ({currency} cost value when applicable)", f"From {display_date(date_from)} to {display_date(date_to)}"],
            "sections": [{"heading": "Stock at To Date" if col_dim == "warehouse" else "Net stock movement during period (receipts less issues)", "headers": [row_dim.title()] + ordered + ["Total"], "rows": rows, "total_rows": [len(rows) - 1]}]}


def inventory_health(database, options, items, in_category, currency, method, date_to, warehouse, company):
    """List actionable stock issues with value at cost and item master data."""
    try: days = int(options.get("days") or 90)
    except ValueError as exc: raise ValueError("Slow-moving days must be a whole number") from exc
    if days < 1: raise ValueError("Slow-moving days must be at least 1")
    cutoff = (datetime.strptime(date_to, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    state = run_costing(database, date_to, method); rows = []; totals = {}
    for item_id, item in sorted(items.items(), key=lambda pair: pair[1]["sku"]):
        if not item["active"] or not in_category(item_id): continue
        data = state.get(item_id, {}); qty = data.get("by_warehouse", {}).get(warehouse, ZERO) if warehouse else data.get("qty", ZERO)
        reorder = _d(item.get("reorder_level")); issues = []
        if qty < 0: issues.append("Negative stock")
        if reorder > 0 and qty <= reorder: issues.append("Reorder")
        if qty > 0 and not data.get("avg", ZERO): issues.append("Missing unit cost")
        if qty > 0 and not item.get("supplier_id"): issues.append("No supplier")
        if qty > 0 and (not data.get("last_out") or data["last_out"] < cutoff): issues.append(f"No issue in {days} days")
        if not issues: continue
        value = (qty * data.get("avg", ZERO)).quantize(Decimal("0.01"))
        for issue in issues:
            rows.append([issue, item["sku"], item["name"], item.get("category") or "", qty, reorder, value, display_date(data["last_out"]) if data.get("last_out") else "Never"])
            count, amount = totals.get(issue, (0, ZERO)); totals[issue] = (count + 1, amount + value)
    summary = [[issue, count, value.quantize(Decimal("0.01"))] for issue, (count, value) in sorted(totals.items())]
    return {"title": "Inventory Health", "meta": [f"Company: {company.get('company_name') or '-'}", f"As of {display_date(date_to)}   Slow-moving threshold: {days} days"],
            "sections": [{"heading": "Action summary", "headers": ["Issue", "Items", f"Stock Value ({currency})"], "rows": summary or [["No inventory exceptions", 0, ZERO]], "total_rows": []},
                         {"heading": "Items to review (an item may appear for more than one issue)", "headers": ["Issue", "Item Code", "Item", "Category", "On Hand", "Reorder Level", f"Value ({currency})", "Last Issue"],
                          "rows": rows or [["No inventory exceptions"] + [""] * 7], "total_rows": []}]}


def additional_inventory_report(database, report, options, items, warehouses, in_category, currency, method, date_from, date_to, warehouse, company):
    """Turnover, stock by supplier, and saved physical count differences."""
    selected = lambda item_id: item_id in items and in_category(item_id) and (not options.get("item_id") or int(options["item_id"]) == item_id)
    money = lambda value: Decimal(value).quantize(Decimal("0.01"))
    meta = [f"Company: {company.get('company_name') or '-'}   Currency: {currency}", f"From {display_date(date_from)} to {display_date(date_to)}"]
    if report == "count_variances":
        with database.connect() as db:
            counts = [dict(row) for row in db.execute("SELECT number,count_date,warehouse_id,status,lines FROM physical_counts WHERE count_date BETWEEN ? AND ? ORDER BY count_date,number", (date_from, date_to))]
        rows = []; total = ZERO
        for count in counts:
            if warehouse and count["warehouse_id"] != warehouse: continue
            snapshot = {row["item_id"]: row for row in count_sheet(database, count["warehouse_id"], count["count_date"])}
            if count["status"] == "posted":
                with database.connect() as db:
                    adjustments = db.execute("""SELECT m.item_id,m.quantity FROM stock_movements m JOIN stock_documents d ON d.id=m.document_id
                        WHERE d.reference=? AND d.doc_date=? AND d.warehouse_id=? AND d.notes=?""",
                        (count["number"], count["count_date"], count["warehouse_id"], f"Physical count {count['number']}")).fetchall()
                for change in adjustments:
                    if change["item_id"] in snapshot: snapshot[change["item_id"]]["system_qty"] -= float(change["quantity"])
            for line in json.loads(count["lines"]):
                item_id = int(line["item_id"])
                if not selected(item_id): continue
                system = _d(line.get("system_qty") if line.get("system_qty") is not None else snapshot.get(item_id, {}).get("system_qty"))
                counted = _d(line["counted"]); difference = counted - system
                if not difference: continue
                cost = _d(line.get("unit_cost") if line.get("unit_cost") is not None else snapshot.get(item_id, {}).get("unit_cost"))
                value = money(difference * cost); total += value
                rows.append([count["number"], display_date(count["count_date"]), warehouses[count["warehouse_id"]]["code"], items[item_id]["sku"], items[item_id]["name"], system, counted, difference, value, count["status"]])
        rows.append(["TOTAL", "", "", "", "", "", "", "", money(total), ""])
        return {"title": "Physical Count Variances", "meta": meta, "sections": [{"heading": "Saved counts with differences", "headers": ["Count", "Date", "Warehouse", "Item Code", "Item", "Stock on Hand", "Counted", "Difference", f"Variance ({currency})", "Status"], "rows": rows, "total_rows": [len(rows)-1]}]}
    state = run_costing(database, date_to, method)
    if report == "turnover":
        issued = {}
        for row in _movements(database, date_to):
            item_id = row["item_id"]
            if date_from <= row["doc_date"] <= date_to and row["doc_type"] == "issue" and selected(item_id) and (not warehouse or row["warehouse_id"] == warehouse):
                issued[item_id] = issued.get(item_id, ZERO) - _d(row["quantity"])
        rows = []; period_days = (datetime.strptime(date_to, "%Y-%m-%d") - datetime.strptime(date_from, "%Y-%m-%d")).days + 1
        for item_id, item in sorted(items.items(), key=lambda pair: pair[1]["sku"]):
            if not selected(item_id): continue
            data = state.get(item_id, {}); on_hand = data.get("by_warehouse", {}).get(warehouse, ZERO) if warehouse else data.get("qty", ZERO)
            sold = issued.get(item_id, ZERO)
            if not sold and not on_hand and not options.get("include_zero"): continue
            days = (on_hand / sold * Decimal(period_days)).quantize(Decimal("0.1")) if sold else "-"
            rows.append([item["sku"], item["name"], item["unit"], sold, on_hand, days, money(on_hand * data.get("avg", ZERO))])
        return {"title": "Stock Turnover", "meta": meta, "sections": [{"heading": "Issues during period and stock at To Date (coverage at the period's issue rate)", "headers": ["Item Code", "Item", "Unit", "Issued", "On Hand", "Coverage Days", f"On-hand Value ({currency})"], "rows": rows, "total_rows": []}]}
    with database.connect() as db:
        suppliers = {str(row["id"]): row["name"] for row in db.execute("SELECT id,name FROM parties")}
    groups = {}
    for item_id, item in items.items():
        if not selected(item_id): continue
        data = state.get(item_id, {}); qty = data.get("by_warehouse", {}).get(warehouse, ZERO) if warehouse else data.get("qty", ZERO)
        if not qty and not options.get("include_zero"): continue
        name = suppliers.get(str(item.get("supplier_id") or ""), "(No supplier)")
        groups.setdefault(name, []).append([item["sku"], item["name"], item["unit"], qty, money(qty * data.get("avg", ZERO))])
    rows = []; totals = []
    for name, members in sorted(groups.items()):
        rows.extend([[name, *member] for member in sorted(members)])
        rows.append([f"Subtotal {name}", "", "", "", sum((member[3] for member in members), ZERO), money(sum((member[4] for member in members), ZERO))]); totals.append(len(rows)-1)
    rows.append(["TOTAL", "", "", "", sum((member[3] for members in groups.values() for member in members), ZERO), money(sum((member[4] for members in groups.values() for member in members), ZERO))]); totals.append(len(rows)-1)
    return {"title": "Stock by Supplier", "meta": meta, "sections": [{"heading": f"On-hand stock at {display_date(date_to)} by item supplier", "headers": ["Supplier", "Item Code", "Item", "Unit", "On Hand", f"Value ({currency})"], "rows": rows, "total_rows": totals}]}

AGEING_BUCKETS = (30, 60, 90, 180, 365)


def fifo_layers(database, date_to):
    """Stock still on hand, split into the receipts it came from (FIFO): {item_id: [[qty, unit_cost, receipt_date], ...]}."""
    layers = {}
    for row in _movements(database, date_to):
        if row["doc_type"] == "transfer": continue
        qty = _d(row["quantity"]); item = layers.setdefault(row["item_id"], [])
        if qty > 0: item.append([qty, _d(row["unit_cost"]), row["doc_date"]])
        else:
            remaining = -qty
            while remaining > 0 and item:
                take = min(item[0][0], remaining); item[0][0] -= take; remaining -= take
                if item[0][0] <= 0: item.pop(0)
    return {k: [l for l in v if l[0] > 0] for k, v in layers.items()}


def _buckets(options):
    try: values = sorted({int(v) for v in str(options.get("buckets") or "").replace(" ", "").split(",") if v})
    except ValueError: raise ValueError("Ageing buckets must be days separated by commas, for example 30,60,90,180,365")
    return tuple(v for v in values if v > 0) or AGEING_BUCKETS


def _bucket_labels(limits):
    labels = []; start = 0
    for limit in limits: labels.append(f"{start}-{limit} days"); start = limit + 1
    return labels + [f"Over {limits[-1]} days"]


def _ageing_data(database, options, items, in_category, method, date_to):
    limits = _buckets(options); as_of = datetime.strptime(date_to, "%Y-%m-%d")
    state = run_costing(database, date_to, method); layers = fifo_layers(database, date_to)
    warehouse = options.get("warehouse_id"); warehouse = int(warehouse) if str(warehouse or "").isdigit() else None
    result = []
    for item_id, item in sorted(items.items(), key=lambda pair: pair[1]["sku"]):
        data = state.get(item_id); remaining = layers.get(item_id, [])
        if not data or data["qty"] <= 0 or not in_category(item_id) or (options.get("item_id") and int(options["item_id"]) != item_id) or not remaining: continue
        on_hand = data["by_warehouse"].get(warehouse, ZERO) if warehouse else data["qty"]
        if on_hand <= 0: continue
        share = on_hand / data["qty"]  # a warehouse's stock is aged like the item's stock
        unit_cost = data["avg"]
        buckets = [[ZERO, ZERO] for _ in range(len(limits) + 1)]; weighted_age = ZERO; oldest = None
        for qty, layer_cost, day in remaining:
            age = (as_of - datetime.strptime(day, "%Y-%m-%d")).days; qty = qty * share
            index = next((i for i, limit in enumerate(limits) if age <= limit), len(limits))
            value = qty * (layer_cost if method == "fifo" else unit_cost)
            buckets[index][0] += qty; buckets[index][1] += value; weighted_age += qty * age
            oldest = day if oldest is None or day < oldest else oldest
        total_qty = sum((b[0] for b in buckets), ZERO); total_value = sum((b[1] for b in buckets), ZERO)
        result.append({"item": item, "qty": total_qty, "value": total_value, "buckets": buckets, "avg_age": int(weighted_age / total_qty) if total_qty else 0,
                       "oldest": oldest, "last_out": data.get("last_out"), "last_in": remaining[-1][2] if remaining else None})
    return limits, result


def ageing_report(database, options, items, warehouses, in_category, currency, method, date_to, company):
    """Stock ageing: how long the stock on hand has been waiting, by receipt date (FIFO), valued at cost."""
    limits, data = _ageing_data(database, options, items, in_category, method, date_to)
    labels = _bucket_labels(limits); money = lambda v: Decimal(v).quantize(Decimal("0.01"))
    headers = ["Item Code", "Item", "Category", "Unit", "On Hand", f"Value ({currency})", "Avg Age (days)", "Oldest Receipt", "Last Issue"] + labels + [f"% over {limits[-2] if len(limits) > 1 else limits[-1]} days"]
    risk_from = len(limits) - 1 if len(limits) > 1 else len(limits)
    rows = []; totals = []; grand = [ZERO] * (len(labels)); grand_qty = ZERO; grand_value = ZERO
    for name in sorted({(d["item"].get("category") or "(no category)") for d in data}):
        members = [d for d in data if (d["item"].get("category") or "(no category)") == name]; sub = [ZERO] * len(labels)
        for d in members:
            values = [b[1] for b in d["buckets"]]; old_share = sum(values[risk_from:], ZERO) / d["value"] * 100 if d["value"] else ZERO
            rows.append([d["item"]["sku"], d["item"]["name"], name, d["item"]["unit"], d["qty"].quantize(Decimal("0.001")), money(d["value"]), d["avg_age"],
                         display_date(d["oldest"]) if d["oldest"] else "", display_date(d["last_out"]) if d.get("last_out") else "never"] + [money(v) for v in values] + [f"{old_share:.0f}%"])
            sub = [a + b for a, b in zip(sub, values)]
        sub_value = sum(sub, ZERO)
        rows.append([f"Subtotal {name}", f"{len(members)} item(s)", "", "", "", money(sub_value), "", "", ""] + [money(v) for v in sub] +
                    [f"{(sum(sub[risk_from:], ZERO) / sub_value * 100):.0f}%" if sub_value else ""]); totals.append(len(rows) - 1)
        grand = [a + b for a, b in zip(grand, sub)]; grand_value += sub_value; grand_qty += sum((d["qty"] for d in members), ZERO)
    rows.append(["TOTAL", f"{len(data)} item(s)", "", "", "", money(grand_value), "", "", ""] + [money(v) for v in grand] +
                [f"{(sum(grand[risk_from:], ZERO) / grand_value * 100):.0f}%" if grand_value else ""]); totals.append(len(rows) - 1)
    summary = [[label, money(value), f"{(value / grand_value * 100):.1f}%" if grand_value else "0.0%", sum(1 for d in data if d["buckets"][index][1] > 0)]
               for index, (label, value) in enumerate(zip(labels, grand))]
    summary.append(["TOTAL STOCK", money(grand_value), "100.0%" if grand_value else "0.0%", len(data)])
    old = sorted([d for d in data if sum((b[1] for b in d["buckets"][risk_from:]), ZERO) > 0], key=lambda d: -sum((b[1] for b in d["buckets"][risk_from:]), ZERO))
    risk = [[d["item"]["sku"], d["item"]["name"], d["item"].get("category") or "", money(sum((b[1] for b in d["buckets"][risk_from:]), ZERO)), d["avg_age"],
             display_date(d["last_out"]) if d.get("last_out") else "never"] for d in old[:25]]
    threshold = limits[-2] if len(limits) > 1 else limits[-1]
    sections = [{"heading": "Ageing summary", "headers": ["Age of stock", f"Value ({currency})", "% of stock value", "Items"], "rows": summary, "total_rows": [len(summary) - 1]},
                {"heading": f"Stock ageing by item at {display_date(date_to)} (by receipt date, first in - first out)", "headers": headers,
                 "rows": rows if data else [["No stock on hand"] + [""] * (len(headers) - 1)], "total_rows": totals if data else []},
                {"heading": f"Stock older than {threshold} days - review for slow-moving or obsolete items", "headers": ["Item Code", "Item", "Category", f"Value over {threshold} days", "Avg Age (days)", "Last Issue"],
                 "rows": risk or [["No stock older than this"] + [""] * 5], "total_rows": []}]
    meta = [f"Company: {company.get('company_name') or '-'}   Inventory currency: {currency}   Costing: {'FIFO' if method == 'fifo' else 'Weighted average'}",
            f"Stock ageing as of {display_date(date_to)}   Buckets: {', '.join(labels)}" + (f"   Warehouse: {warehouses[int(options['warehouse_id'])]['code']}" if str(options.get('warehouse_id') or '').isdigit() else "")]
    return {"title": "Stock Ageing Report", "meta": meta, "sections": sections}


def summary_report(database, options, items, warehouses, in_category, currency, method, date_to, company):
    """One-page inventory summary: key figures, value by category and warehouse, top items, ageing."""
    state = run_costing(database, date_to, method); money = lambda v: Decimal(v).quantize(Decimal("0.01"))
    rows = [(item_id, items[item_id], data) for item_id, data in state.items() if data["qty"] > 0 and item_id in items and in_category(item_id)]
    total_value = sum((d["value"] for _i, _it, d in rows), ZERO); sales_value = sum((d["qty"] * _d(it.get("sales_price")) for _i, it, d in rows), ZERO)
    below = [it for _i, it, d in rows if _d(it.get("reorder_level")) > 0 and d["qty"] <= _d(it.get("reorder_level"))]
    cutoff = (datetime.strptime(date_to, "%Y-%m-%d") - timedelta(days=int(options.get("days") or 90))).strftime("%Y-%m-%d")
    limits, ageing = _ageing_data(database, options, items, in_category, method, date_to)
    # slow-moving: in stock for longer than the period AND nothing issued during it (new arrivals are not slow)
    slow = [(a["item"], state[a["item"]["id"]]) for a in ageing if a["oldest"] and a["oldest"] < cutoff and (not a.get("last_out") or a["last_out"] < cutoff)]
    old_value = sum((sum((b[1] for b in a["buckets"][len(limits) - 1:]), ZERO) for a in ageing), ZERO)
    kpis = [["Items in stock", len(rows)], [f"Stock value at cost ({currency})", money(total_value)], [f"Stock value at sales price ({currency})", money(sales_value)],
            ["Potential gross margin", money(sales_value - total_value)], ["Items at or below reorder level", len(below)],
            [f"Slow-moving stock value (no issue for {int(options.get('days') or 90)} days)", money(sum((d['value'] for _it, d in slow), ZERO))],
            [f"Stock value older than {limits[-2] if len(limits) > 1 else limits[-1]} days", money(old_value)],
            ["Share of old stock in total value", f"{(old_value / total_value * 100):.1f}%" if total_value else "0.0%"]]
    by_category = {}
    for _i, it, d in rows: by_category.setdefault(it.get("category") or "(no category)", [0, ZERO]); by_category[it.get("category") or "(no category)"][0] += 1; by_category[it.get("category") or "(no category)"][1] += d["value"]
    category_rows = [[name, count, money(value), f"{(value / total_value * 100):.1f}%" if total_value else ""] for name, (count, value) in sorted(by_category.items(), key=lambda p: -p[1][1])]
    warehouse_rows = []
    for warehouse_id, warehouse in warehouses.items():
        value = sum((d["by_warehouse"].get(warehouse_id, ZERO) * d["avg"] for _i, _it, d in rows), ZERO)
        if value: warehouse_rows.append([warehouse["code"], warehouse["name"], money(value), f"{(value / total_value * 100):.1f}%" if total_value else ""])
    top = sorted(rows, key=lambda r: -r[2]["value"])[:10]
    top_rows = [[it["sku"], it["name"], it.get("category") or "", d["qty"].quantize(Decimal("0.001")), money(d["avg"]), money(d["value"]), f"{(d['value'] / total_value * 100):.1f}%" if total_value else ""] for _i, it, d in top]
    labels = _bucket_labels(limits); age_totals = [sum((a["buckets"][i][1] for a in ageing), ZERO) for i in range(len(labels))]
    sections = [{"heading": "Key figures", "headers": ["Indicator", "Value"], "rows": kpis, "total_rows": [1]},
                {"heading": "Stock value by category", "headers": ["Category", "Items", f"Value ({currency})", "% of value"], "rows": category_rows or [["-", "", "", ""]], "total_rows": []},
                {"heading": "Stock value by warehouse", "headers": ["Warehouse", "Name", f"Value ({currency})", "% of value"], "rows": warehouse_rows or [["-", "", "", ""]], "total_rows": []},
                {"heading": "Top 10 items by value", "headers": ["Item Code", "Item", "Category", "On Hand", "Unit Cost", f"Value ({currency})", "% of value"], "rows": top_rows or [["-"] + [""] * 6], "total_rows": []},
                {"heading": "Ageing of the stock", "headers": ["Age of stock", f"Value ({currency})", "% of value"],
                 "rows": [[label, money(value), f"{(value / total_value * 100):.1f}%" if total_value else ""] for label, value in zip(labels, age_totals)], "total_rows": []}]
    if below: sections.append({"heading": "Items to reorder", "headers": ["Item Code", "Item", "On Hand", "Reorder Level"],
                               "rows": [[it["sku"], it["name"], state[it["id"]]["qty"].quantize(Decimal("0.001")), _d(it.get("reorder_level"))] for it in below], "total_rows": []})
    meta = [f"Company: {company.get('company_name') or '-'}   Inventory currency: {currency}   Costing: {'FIFO' if method == 'fifo' else 'Weighted average'}", f"Situation at {display_date(date_to)}"]
    return {"title": "Inventory Summary", "meta": meta, "sections": sections}
