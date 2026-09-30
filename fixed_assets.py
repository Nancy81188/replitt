"""Straight-line fixed asset register and auditable depreciation postings."""
import calendar
import json
from decimal import ROUND_CEILING
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def migrate(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS fixed_assets (
            id INTEGER PRIMARY KEY, asset_code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            acquired_on TEXT NOT NULL, start_on TEXT NOT NULL, currency TEXT NOT NULL,
            cost TEXT NOT NULL, residual TEXT NOT NULL DEFAULT '0', useful_months INTEGER NOT NULL,
            frequency TEXT NOT NULL DEFAULT 'monthly', asset_account TEXT NOT NULL,
            depreciation_account TEXT NOT NULL, accumulated_account TEXT NOT NULL,
            invoice_id INTEGER, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fixed_asset_postings (
            id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES fixed_assets(id),
            period_end TEXT NOT NULL, amount TEXT NOT NULL, entry_id INTEGER REFERENCES journal_entries(id),
            UNIQUE(asset_id, period_end)
        );
    """)
    if "annual_rate" not in {row[1] for row in db.execute("PRAGMA table_info(fixed_assets)")}:
        db.execute("ALTER TABLE fixed_assets ADD COLUMN annual_rate TEXT")


def _iso(value):
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try: return datetime.strptime(str(value), fmt).date().isoformat()
        except ValueError: pass
    raise ValueError("Asset dates must use DD-MM-YYYY")


def _money(value, label):
    try: number=Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError): raise ValueError(f"{label} must be a number")
    if not number.is_finite() or number<0: raise ValueError(f"{label} cannot be negative")
    return number


def list_assets(database):
    with database.connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM fixed_assets WHERE status='active' ORDER BY asset_code")]


def save_asset(database, payload, asset_id=None, user_id=None):
    name=str(payload.get("name") or "").strip(); code=str(payload.get("asset_code") or "").strip()
    if not name or not code: raise ValueError("Enter asset code and name")
    acquired=_iso(payload.get("acquired_on")); start=_iso(payload.get("start_on"))
    if start<acquired: raise ValueError("Depreciation start cannot be before purchase date")
    cost=_money(payload.get("cost"),"Cost"); residual=_money(payload.get("residual") or 0,"Residual value")
    if cost<=0 or residual>=cost: raise ValueError("Cost must exceed residual value")
    try: months=int(payload.get("useful_months"))
    except (ValueError, TypeError): raise ValueError("Useful life must be a whole number of months")
    if months<1 or months>1200: raise ValueError("Useful life must be between 1 and 1200 months")
    annual_rate=None
    if payload.get("annual_rate") not in (None, ""):
        annual_rate=_money(payload["annual_rate"],"Annual amortisation rate")
        if not 0<annual_rate<=100: raise ValueError("Annual amortisation rate must be above 0 and at most 100%")
        monthly=cost*annual_rate/Decimal(1200)
        months=int(((cost-residual)/monthly).to_integral_value(rounding=ROUND_CEILING))
        if months>1200: raise ValueError("Annual rate is too small to amortise the asset within 100 years")
    currency=str(payload.get("currency") or "USD").upper(); frequency=str(payload.get("frequency") or "monthly").lower()
    if currency not in ("USD","LBP","EUR","AED") or frequency not in ("monthly","yearly"):
        raise ValueError("Choose a supported currency and monthly or yearly posting")
    accounts=[str(payload.get(k) or "").split(" - ",1)[0].strip() for k in ("asset_account","depreciation_account","accumulated_account")]
    with database.connect() as db:
        invoice_id=payload.get("invoice_id") or None
        if invoice_id:
            try: invoice_id=int(invoice_id)
            except (ValueError, TypeError): raise ValueError("Purchase invoice ID must be a number")
            invoice=db.execute("SELECT kind,entry_type,currency FROM invoices WHERE id=? AND status<>'cancelled'",(invoice_id,)).fetchone()
            if not invoice or invoice["kind"]!="purchase" or invoice["entry_type"]!="assets":
                raise ValueError("Choose an existing Assets purchase invoice")
            if invoice["currency"]!=currency: raise ValueError("Asset currency must match the purchase invoice")
        for account in accounts:
            if not db.execute("SELECT 1 FROM accounts WHERE code=?",(account,)).fetchone():
                raise ValueError(f"Account {account} was not found")
        values=(code,name,acquired,start,currency,str(cost),str(residual),months,frequency,*accounts,invoice_id,str(annual_rate) if annual_rate else None)
        action="update" if asset_id else "create"
        if asset_id:
            if not db.execute("SELECT 1 FROM fixed_assets WHERE id=? AND status='active'",(asset_id,)).fetchone(): raise KeyError(asset_id)
            if db.execute("SELECT 1 FROM fixed_asset_postings WHERE asset_id=?",(asset_id,)).fetchone():
                raise ValueError("This asset has posted depreciation; reverse those vouchers before changing the schedule")
            db.execute("""UPDATE fixed_assets SET asset_code=?,name=?,acquired_on=?,start_on=?,currency=?,cost=?,residual=?,useful_months=?,frequency=?,
                asset_account=?,depreciation_account=?,accumulated_account=?,invoice_id=?,annual_rate=? WHERE id=?""",values+(asset_id,))
        else:
            db.execute("""INSERT INTO fixed_assets(asset_code,name,acquired_on,start_on,currency,cost,residual,useful_months,frequency,
                asset_account,depreciation_account,accumulated_account,invoice_id,annual_rate,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",values)
            asset_id=db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,datetime('now'))",
                   (user_id,action,"fixed_asset",asset_id,json.dumps({"code":code,"name":name})))
        return dict(db.execute("SELECT * FROM fixed_assets WHERE id=?",(asset_id,)).fetchone())


def schedule(database, asset_id):
    with database.connect() as db:
        asset=db.execute("SELECT * FROM fixed_assets WHERE id=? AND status='active'",(asset_id,)).fetchone()
        if not asset: raise KeyError(asset_id)
        postings={row["period_end"]:dict(row) for row in db.execute("SELECT * FROM fixed_asset_postings WHERE asset_id=?",(asset_id,))}
    depreciable=Decimal(asset["cost"])-Decimal(asset["residual"]); months=asset["useful_months"]
    start=date.fromisoformat(asset["start_on"]); amounts=[]; assigned=Decimal("0")
    for index in range(months):
        total_month=start.year*12+start.month-1+index
        year,month=divmod(total_month,12); month+=1
        end=date(year,month,calendar.monthrange(year,month)[1]).isoformat()
        if asset["annual_rate"]:
            monthly=Decimal(asset["cost"])*Decimal(asset["annual_rate"])/Decimal(1200)
            cumulative=min(depreciable,(monthly*Decimal(index+1)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP))
            if index==months-1: cumulative=depreciable
            amount=cumulative-assigned
        else:
            amount=(depreciable*Decimal(index+1)/months).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)-assigned
        assigned+=amount; amounts.append((end,amount))
    if asset["frequency"]=="yearly":
        grouped={}
        for end,amount in amounts: grouped[end[:4]]=grouped.get(end[:4],Decimal("0"))+amount
        amounts=[(max(end for end,_ in amounts if end.startswith(year)),amount) for year,amount in grouped.items()]
    accumulated=Decimal("0"); rows=[]
    for end,amount in amounts:
        accumulated+=amount
        rows.append({"period_end":end,"amount":str(amount),"accumulated":str(accumulated),"net_book_value":str(Decimal(asset["cost"])-accumulated),
                     "posted":end in postings,"entry_id":postings.get(end,{}).get("entry_id")})
    return rows


def post_period(database, asset_id, period_end, user_id, fiscal_year=None):
    asset=next((item for item in list_assets(database) if item["id"]==int(asset_id)),None)
    if not asset: raise KeyError(asset_id)
    row=next((item for item in schedule(database,asset_id) if item["period_end"]==_iso(period_end)),None)
    if not row: raise ValueError("Choose a period in the asset amortisation schedule")
    if fiscal_year is not None and int(row["period_end"][:4])!=int(fiscal_year):
        raise ValueError(f"Select fiscal year {row['period_end'][:4]} before posting this amortisation")
    if row["posted"]: raise ValueError("This amortisation period was already posted")
    previous=[item for item in schedule(database,asset_id) if item["period_end"]<row["period_end"] and not item["posted"]]
    if previous: raise ValueError("Post earlier amortisation periods first")
    amount=Decimal(row["amount"])
    if amount<=0: raise ValueError("This period has no amount to post")
    date_text=datetime.strptime(row["period_end"],"%Y-%m-%d").strftime("%d-%m-%Y")
    voucher=database.save_journal_voucher({"entry_date":date_text,"description":f"Asset amortisation {asset['asset_code']} - {row['period_end']}",
        "currency":asset["currency"],"voucher_type":"06"},[
        {"account_code":asset["depreciation_account"],"debit":str(amount)},
        {"account_code":asset["accumulated_account"],"credit":str(amount)}],user_id)
    with database.connect() as db:
        db.execute("INSERT INTO fixed_asset_postings(asset_id,period_end,amount,entry_id) VALUES(?,?,?,?)",
                   (asset_id,row["period_end"],str(amount),voucher["voucher"]["id"]))
    return voucher


def delete_asset(database, asset_id, user_id=None):
    with database.connect() as db:
        if db.execute("SELECT 1 FROM fixed_asset_postings WHERE asset_id=?",(asset_id,)).fetchone():
            raise ValueError("Posted assets cannot be deleted; reverse their journal vouchers first")
        if not db.execute("SELECT 1 FROM fixed_assets WHERE id=? AND status='active'",(asset_id,)).fetchone(): raise KeyError(asset_id)
        db.execute("UPDATE fixed_assets SET status='deleted' WHERE id=?",(asset_id,))
        db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,datetime('now'))",
                   (user_id,"delete","fixed_asset",asset_id,"{}"))
    return {"deleted":int(asset_id)}


def check_carry_forward(source,target_year):
    assets=list_assets(source)
    for asset in assets:
        prior=[row for row in schedule(source,asset["id"]) if row["period_end"][:4]<str(target_year)]
        if any(not row["posted"] for row in prior):
            raise ValueError(f"Post earlier amortisation periods for {asset['asset_code']} before creating {target_year}")
    return assets


def carry_forward(source, target, target_year):
    """Continue active asset schedules in the next fiscal-year database."""
    assets=check_carry_forward(source,target_year)
    with target.connect() as db:
        for asset in assets:
            values=(asset["asset_code"],asset["name"],asset["acquired_on"],asset["start_on"],asset["currency"],
                    asset["cost"],asset["residual"],asset["useful_months"],asset["frequency"],asset["asset_account"],
                    asset["depreciation_account"],asset["accumulated_account"],None,asset["annual_rate"],asset["created_at"])
            new_id=db.execute("""INSERT INTO fixed_assets(asset_code,name,acquired_on,start_on,currency,cost,residual,useful_months,frequency,
                asset_account,depreciation_account,accumulated_account,invoice_id,annual_rate,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",values).lastrowid
            for row in schedule(source,asset["id"]):
                if row["posted"] and row["period_end"][:4]<str(target_year):
                    db.execute("INSERT INTO fixed_asset_postings(asset_id,period_end,amount,entry_id) VALUES(?,?,?,NULL)",
                               (new_id,row["period_end"],row["amount"]))


# ---------------------------------------------------------------- asset accounts (categories) with depreciation %
def _migrate_categories(db):
    db.execute("""CREATE TABLE IF NOT EXISTS asset_categories (account_code TEXT PRIMARY KEY, name TEXT NOT NULL, annual_rate TEXT NOT NULL,
        depreciation_account TEXT NOT NULL, accumulated_account TEXT NOT NULL, updated_at TEXT)""")


def list_categories(database):
    with database.connect() as db:
        _migrate_categories(db)
        return [dict(r) for r in db.execute("SELECT * FROM asset_categories ORDER BY account_code")]


def save_category(database, payload, user_id=None):
    code = str(payload.get("account_code") or "").split(" - ", 1)[0].strip(); name = str(payload.get("name") or "").strip()
    if not code or not name: raise ValueError("Enter the asset account number and its name")
    rate = _money(payload.get("annual_rate"), "Depreciation %")
    if rate <= 0 or rate > 100: raise ValueError("The depreciation % must be between 0 and 100 per year")
    dep = str(payload.get("depreciation_account") or "").split(" - ", 1)[0].strip(); acc = str(payload.get("accumulated_account") or "").split(" - ", 1)[0].strip()
    if not dep or not acc: raise ValueError("Enter the depreciation expense account and the accumulated depreciation account")
    with database.connect() as db:
        _migrate_categories(db)
        for label, value in (("Asset account", code), ("Depreciation expense account", dep), ("Accumulated depreciation account", acc)):
            if not db.execute("SELECT 1 FROM accounts WHERE code=?", (value,)).fetchone(): raise ValueError(f"{label} {value} is not in the chart of accounts")
        db.execute("""INSERT INTO asset_categories(account_code,name,annual_rate,depreciation_account,accumulated_account,updated_at) VALUES(?,?,?,?,?,?)
            ON CONFLICT(account_code) DO UPDATE SET name=excluded.name,annual_rate=excluded.annual_rate,depreciation_account=excluded.depreciation_account,
            accumulated_account=excluded.accumulated_account,updated_at=excluded.updated_at""", (code, name, str(rate), dep, acc, datetime.now().isoformat()))
    return list_categories(database)


def delete_category(database, account_code):
    with database.connect() as db:
        _migrate_categories(db)
        if db.execute("SELECT 1 FROM fixed_assets WHERE asset_account=? AND status='active'", (account_code,)).fetchone():
            raise ValueError("Assets still use this account; move or delete them first")
        db.execute("DELETE FROM asset_categories WHERE account_code=?", (account_code,))
    return list_categories(database)


def _month_end(value):
    day = date.fromisoformat(_iso(value)); return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1]).isoformat()


def monthly_table(database, month, account_code=None):
    """Depreciation table of one month: for every asset, grouped by asset account - purchase date, value, depreciation before
    the month, depreciation of the month, total depreciation and net value (never below zero / the residual value)."""
    end = _month_end(month); categories = {c["account_code"]: c for c in list_categories(database)}
    groups = {}
    for asset in list_assets(database):
        if asset.get("status", "active") != "active" or asset["acquired_on"] > end: continue
        if account_code and asset["asset_account"] != account_code: continue
        rows = schedule(database, asset["id"]); cost = Decimal(str(asset["cost"])); residual = Decimal(str(asset.get("residual") or 0))
        before = sum((Decimal(r["amount"]) for r in rows if r["period_end"] < end), Decimal("0"))
        current_row = next((r for r in rows if r["period_end"] == end), None); current = Decimal(current_row["amount"]) if current_row else Decimal("0")
        before = min(before, cost - residual); current = max(Decimal("0"), min(current, cost - residual - before))  # net value never below the residual / zero
        total = before + current
        group = groups.setdefault(asset["asset_account"], {"account": asset["asset_account"], "name": categories.get(asset["asset_account"], {}).get("name", ""),
                                                           "rate": categories.get(asset["asset_account"], {}).get("annual_rate", asset.get("annual_rate") or ""),
                                                           "depreciation_account": asset["depreciation_account"], "accumulated_account": asset["accumulated_account"],
                                                           "currency": asset["currency"], "assets": []})
        group["assets"].append({"id": asset["id"], "code": asset["asset_code"], "name": asset["name"], "acquired_on": asset["acquired_on"], "value": cost,
                                "old": before, "current": current, "total": total, "net": cost - total, "posted": bool(current_row and current_row["posted"]), "currency": asset["currency"]})
    for group in groups.values():
        for key in ("value", "old", "current", "total", "net"): group[key] = sum((a[key] for a in group["assets"]), Decimal("0"))
        group["to_post"] = sum((a["current"] for a in group["assets"] if not a["posted"]), Decimal("0"))
    return {"month": end, "groups": [groups[k] for k in sorted(groups)]}


def post_category_month(database, account_code, month, user_id, fiscal_year=None):
    """One depreciation entry per asset account for the month: Dr depreciation expense / Cr accumulated depreciation."""
    table = monthly_table(database, month, account_code)
    if not table["groups"]: raise ValueError("No asset in this account for this month")
    group = table["groups"][0]; end = table["month"]
    if fiscal_year is not None and int(end[:4]) != int(fiscal_year): raise ValueError(f"Select fiscal year {end[:4]} before posting this depreciation")
    pending = [a for a in group["assets"] if not a["posted"] and a["current"] > 0]
    if not pending: raise ValueError("The depreciation of this account for this month is already posted (or is zero)")
    late = []
    for asset in pending:
        earlier = [r for r in schedule(database, asset["id"]) if r["period_end"] < end and not r["posted"] and Decimal(r["amount"]) > 0]
        if earlier: late.append(asset["code"])
    if late: raise ValueError("Post the earlier months first for: " + ", ".join(late))
    amount = sum((a["current"] for a in pending), Decimal("0"))
    voucher = database.save_journal_voucher({"entry_date": datetime.strptime(end, "%Y-%m-%d").strftime("%d-%m-%Y"),
        "description": f"Depreciation {group['name'] or account_code} ({account_code}) - {end[:7]}", "currency": group["currency"], "voucher_type": "06"},
        [{"account_code": group["depreciation_account"], "debit": str(amount)}, {"account_code": group["accumulated_account"], "credit": str(amount)}], user_id)
    with database.connect() as db:
        for asset in pending:
            db.execute("INSERT OR IGNORE INTO fixed_asset_postings(asset_id,period_end,amount,entry_id) VALUES(?,?,?,?)", (asset["id"], end, str(asset["current"]), voucher["voucher"]["id"]))
    return {"voucher": voucher["voucher"]["entry_number"], "amount": float(amount), "assets": len(pending)}
