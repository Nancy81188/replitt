"""Lebanese quarterly VAT calculation and preparation schedules; internal refs only."""
from __future__ import annotations

import calendar
import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from database import display_date, iso_date, utcnow

ZERO = Decimal("0")
CENT = Decimal("0.01")
CATEGORIES = {"sales": "Sales", "purchases": "Purchases", "assets": "Fixed assets", "expenses": "Expenses", "customs": "Customs (import VAT)"}
ADJUSTMENT_TYPES = {"output": "Output VAT adjustment", "input": "Deductible VAT adjustment", "non_deductible": "Non-deductible VAT adjustment"}
# These A-F identifiers are internal schedule references, not Ministry form box numbers.
# The public Ministry specimen does not certify this mapping to its current issued form.
LINES = (
    ("A1", "sales", "Taxable supplies at 11% (base / output VAT)"),
    ("A2", "sales_zero", "Zero-rated supplies - exports & like transactions (Art. 19-21)"),
    ("A3", "sales_exempt", "Exempt supplies (Art. 16-17)"),
    ("A4", "sales_out", "Supplies outside the scope of VAT"),
    ("B1", "reverse_output", "VAT on services acquired from abroad (reverse charge, Art. 40)"),
    ("B2", "adj_output", "Output VAT adjustments"),
    ("B3", "total_output", "TOTAL OUTPUT VAT"),
    ("C1", "purchases", "Deductible VAT - local purchases of goods & services"),
    ("C2", "assets", "Deductible VAT - fixed assets"),
    ("C3", "expenses", "Deductible VAT - general expenses"),
    ("C4", "customs", "Deductible VAT - imports (customs)"),
    ("C5", "prorata", "Less: VAT not deductible under the partial deduction ratio (Art. 31)"),
    ("C6", "annual_adjustment", "Annual adjustment of the deduction ratio (Q4)"),
    ("C7", "adj_input", "Deductible VAT adjustments"),
    ("C8", "total_input", "TOTAL DEDUCTIBLE VAT"),
    ("D1", "non_deductible", "VAT not deductible (Art. 28 / 31, for information)"),
    ("E1", "net", "NET VAT FOR THE PERIOD (output VAT less deductible input VAT)"),
)
RATE = Decimal("0.11")
ARABIC = {"sales": "المبيعات الخاضعة للضريبة بمعدل 11%", "sales_zero": "العمليات المعفاة مع حق الحسم - التصدير (المواد 19-21)",
          "sales_exempt": "العمليات المعفاة (المادتان 16 و17)", "sales_out": "عمليات خارج نطاق الضريبة",
          "reverse_output": "الضريبة على الخدمات المستوردة من الخارج (المادة 40)", "adj_output": "تسويات الضريبة المستحقة", "total_output": "مجموع الضريبة المستحقة",
          "purchases": "الضريبة القابلة للحسم - المشتريات المحلية", "assets": "الضريبة القابلة للحسم - الأصول الثابتة", "expenses": "الضريبة القابلة للحسم - المصاريف العامة",
          "customs": "الضريبة القابلة للحسم - الاستيراد (الجمارك)", "prorata": "ينزل: الضريبة غير القابلة للحسم وفق نسبة الحسم الجزئي (المادة 31)",
          "annual_adjustment": "التسوية السنوية لنسبة الحسم (الفصل الرابع)", "adj_input": "تسويات الضريبة القابلة للحسم", "total_input": "مجموع الضريبة القابلة للحسم",
          "non_deductible": "ضريبة غير قابلة للحسم (للعلم)", "net": "صافي الضريبة عن الفترة", "credit_bf": "الرصيد الدائن المدور من الفترة السابقة",
          "payable": "الضريبة المتوجبة الدفع لوزارة المالية", "refund": "طلب استرداد الرصيد الدائن (المادة 30)", "credit_cf": "الرصيد الدائن المدور إلى الفترة التالية"}
ARABIC_TITLE = "التصريح الدوري عن الضريبة على القيمة المضافة"


def quarter_range(year, quarter):
    try: year = int(year); quarter = int(quarter)
    except (TypeError, ValueError) as exc: raise ValueError("Enter a valid year and quarter") from exc
    if year < 2000 or year > 2100 or quarter not in (1, 2, 3, 4): raise ValueError("Quarter must be Q1, Q2, Q3 or Q4")
    first = 3 * quarter - 2
    return date(year, first, 1).isoformat(), date(year, first + 2, calendar.monthrange(year, first + 2)[1]).isoformat()


def previous_quarter(year, quarter):
    return (int(year), int(quarter) - 1) if int(quarter) > 1 else (int(year) - 1, 4)


def _money(value):
    try: return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception: return ZERO


def _lbp(value):
    return Decimal(str(value or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _documents(db, start, end, currency, include_review):
    statuses = ("posted", "review") if include_review else ("posted",)
    documents = []; skipped = []; review_excluded = 0
    with db.connect() as connection:
        invoices = [dict(row) for row in connection.execute("""SELECT i.*,p.name party_name FROM invoices i
            LEFT JOIN parties p ON p.id=i.party_id WHERE i.status NOT IN ('cancelled','deleted')""")]
        expenses = [dict(row) for row in connection.execute("SELECT * FROM expenses")]
    for row in invoices:
        try: day = iso_date(row["invoice_date"])
        except ValueError: skipped.append(row["invoice_number"]); continue
        if not start <= day <= end or (currency and row["currency"] != currency): continue
        if row["status"] not in statuses:
            if row["status"] == "review": review_excluded += 1
            continue
        if row["kind"] == "sale": category = "sales"
        elif row.get("source_file") == "Customs Case": category = "customs"
        elif row.get("entry_type") == "assets": category = "assets"
        elif row.get("entry_type") == "expenses": category = "expenses"
        else: category = "purchases"
        documents.append({"source": "invoice", "id": row["id"], "date": day, "number": row["invoice_number"], "party": row.get("party_name") or "",
            "category": category, "currency": row["currency"], "base": _money(row.get("deductible_subtotal") or row.get("subtotal")),
            "exempt": _money(row.get("non_deductible_subtotal")), "vat": _money(row.get("vat")), "status": row["status"],
            "recoverable": category == "sales" or bool(int(row.get("vat_recoverable") if row.get("vat_recoverable") is not None else 1)),
            "treatment": row.get("vat_treatment") or "standard", "use": row.get("vat_use") or "mixed"})
        if row.get("doc_subtype") == "credit_note":  # a credit note reduces the supplies and the VAT of the period
            documents[-1].update(base=-documents[-1]["base"], exempt=-documents[-1]["exempt"], vat=-documents[-1]["vat"])
    for row in expenses:
        try: day = iso_date(row["expense_date"])
        except ValueError: skipped.append(f"EXP-{row['id']}"); continue
        if not start <= day <= end or (currency and row["currency"] != currency): continue
        documents.append({"source": "expense", "id": row["id"], "date": day, "number": row.get("reference") or f"EXP-{row['id']}",
            "party": row.get("description") or "", "category": "expenses", "currency": row["currency"],
            "base": _money(row.get("with_vat_subtotal") or row.get("subtotal")), "exempt": _money(row.get("without_vat_subtotal")),
            "vat": _money(row.get("vat")), "status": "posted", "recoverable": bool(int(row.get("vat_recoverable") if row.get("vat_recoverable") is not None else 1)),
            "treatment": "standard", "use": row.get("vat_use") or "mixed"})
    documents.sort(key=lambda item: (item["date"], item["category"], str(item["number"])))
    return documents, skipped, review_excluded


def list_adjustments(db, year, quarter):
    with db.connect() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM vat_adjustments WHERE year=? AND quarter=? ORDER BY id", (int(year), int(quarter)))]


def saved_return(db, year, quarter):
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM vat_returns WHERE year=? AND quarter=?", (int(year), int(quarter))).fetchone()
    return dict(row) if row else None


def list_saved_returns(db):
    with db.connect() as connection:
        return [dict(row) for row in connection.execute("""SELECT id,year,quarter,net_lbp,credit_brought_forward_lbp,payable_lbp,
            credit_carried_forward_lbp,saved_at,saved_by_name FROM vat_returns ORDER BY year DESC,quarter DESC""")]


def _rounded_up(value, day):
    """Legacy worksheet estimate: 10,000 LBP ceiling from 25-11-2024.

    The cited MoF decision 1195 has not been verified as a VAT payable rule.
    Do not treat this estimate as a filing instruction.
    """
    if value <= 0 or day < "2024-11-25": return _lbp(value)
    step = Decimal("10000")
    return (Decimal(value) / step).to_integral_value(rounding="ROUND_CEILING") * step


def due_date(year, quarter):
    """20 days after the quarter; one month after it from 2026 (Budget Law 2026, Art. 51)."""
    from datetime import timedelta
    end = date.fromisoformat(quarter_range(year, quarter)[1])
    if int(year) >= 2026:
        month = end.month % 12 + 1; year_due = end.year + (1 if end.month == 12 else 0)
        return date(year_due, month, min(end.day, calendar.monthrange(year_due, month)[1])).isoformat()
    return (end + timedelta(days=20)).isoformat()


def _classify(doc):
    """Where a document goes on the return, and how much of its VAT is output, fully / partially deductible or blocked."""
    base = doc["base"]; exempt = doc["exempt"]; vat = doc["vat"]
    if doc["category"] == "sales":
        treatment = doc["treatment"]
        if treatment == "zero_rated": return {"sales_zero": base + exempt, "sales": vat}
        if treatment == "exempt": return {"sales_exempt": base + exempt, "sales": vat}
        if treatment == "out_of_scope": return {"sales_out": base + exempt}
        return {"sales_base": base, "sales": vat, "sales_exempt": exempt}
    result = {}
    if doc["treatment"] == "reverse_charge":
        vat = vat if vat else ((base + exempt) * RATE).quantize(CENT, rounding=ROUND_HALF_UP)
        result["reverse_output"] = vat
    if not doc["recoverable"] or doc["use"] == "exempt": result["blocked"] = vat
    else: result[doc["category"]] = vat; result["mixed" if doc["use"] == "mixed" else "full"] = vat  # "export" and "taxable" uses are fully deductible
    return result


def _turnover(db, start, end, include_review, rates):
    """Turnover in LBP for the partial deduction ratio: (taxable + zero-rated) / (taxable + zero-rated + exempt)."""
    documents, _skipped, _review = _documents(db, start, end, None, include_review)
    taxable = ZERO; exempt = ZERO
    for doc in documents:
        if doc["category"] != "sales": continue
        parts = _classify(doc); rate = rates(doc["currency"], doc["date"])
        taxable += (parts.get("sales_base", ZERO) + parts.get("sales_zero", ZERO)) * rate
        exempt += parts.get("sales_exempt", ZERO) * rate
    return taxable, exempt


def _ratio(taxable, exempt):
    total = taxable + exempt
    return Decimal("1") if total <= 0 or exempt <= 0 else (taxable / total).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def build_vat_return(db, year, quarter, currency=None, include_review=False, previous_year_db=None, credit_brought_forward=None, refund_requested=None):
    start, end = quarter_range(year, quarter)
    currency = str(currency).upper() if currency and str(currency).upper() not in ("ALL", "ALL CURRENCIES") else None
    documents, skipped, review_excluded = _documents(db, start, end, currency, include_review)
    rates = {}
    def rate_of(code, day):
        if code == "LBP": return Decimal("1")
        key = (code, day)
        if key not in rates: rates[key] = db._converted_amount(Decimal("1"), code, "LBP", day)
        return rates[key]
    to_lbp = lambda amount, code, day: _lbp(Decimal(amount) * rate_of(code, day))
    # ---- partial deduction ratio (Art. 31): provisional for Q1-Q3, final annual ratio in Q4
    year_start = f"{int(year)}-01-01"; year_end = f"{int(year)}-12-31"
    ytd_taxable, ytd_exempt = _turnover(db, year_start, end, include_review, rate_of)
    provisional = db.vat_provisional_ratio(year)
    if int(quarter) == 4:
        final_taxable, final_exempt = _turnover(db, year_start, year_end, include_review, rate_of)
        ratio = _ratio(final_taxable, final_exempt); ratio_source = "final annual ratio"
    elif provisional is not None: ratio = provisional; ratio_source = "provisional ratio set for the year"
    else: ratio = _ratio(ytd_taxable, ytd_exempt); ratio_source = "year-to-date turnover"
    per_currency = {}; warnings = []
    def bucket(code):
        keys = [key for _, key, _ in LINES] + ["blocked", "mixed", "full"]
        return per_currency.setdefault(code, {key: {"base": ZERO, "vat": ZERO, "vat_lbp": ZERO, "count": 0} for key in keys})
    for doc in documents:
        doc["lbp_rate"] = rate_of(doc["currency"], doc["date"]); doc["vat_lbp"] = to_lbp(doc["vat"], doc["currency"], doc["date"])
        parts = _classify(doc); values = bucket(doc["currency"])
        if doc["category"] == "sales":
            if doc["treatment"] in ("zero_rated", "exempt") and doc["vat"]: warnings.append(f"{doc['number']}: {doc['treatment'].replace('_', ' ')} sale shows VAT {doc['vat']:,.2f}")
            for key, base_key in (("sales", "sales_base"), ("sales_zero", "sales_zero"), ("sales_exempt", "sales_exempt"), ("sales_out", "sales_out")):
                if base_key in parts: values[key]["base"] += parts[base_key]; values[key]["count"] += 1
            if parts.get("sales"): values["sales"]["vat"] += parts["sales"]; values["sales"]["vat_lbp"] += to_lbp(parts["sales"], doc["currency"], doc["date"])
            doc["deductible_share"] = ""
            continue
        base = doc["base"] + doc["exempt"]
        for key, value in parts.items():
            line = values[key]; line["vat"] += value; line["vat_lbp"] += to_lbp(value, doc["currency"], doc["date"]); line["count"] += 1
            if key in ("purchases", "assets", "expenses", "customs", "reverse_output", "blocked"): line["base"] += base
        doc["deductible_share"] = "0%" if "blocked" in parts else (f"{ratio * 100:.2f}%" if doc["use"] == "mixed" else "100%")
    if any(doc["currency"] != "LBP" for doc in documents):
        warnings.append("Foreign-currency VAT uses the saved document-date accounting rate as an estimate. Decree 11230/2023 distinguishes imports (customs rate), professional customers (then-Sayrafa rate), telecom invoices and airport/port fees; it also addresses VAT actually collected at a higher value. Verify the applicable current rate, tax-point date and deductible VAT on each document before filing.")
    adjustments = list_adjustments(db, year, quarter)
    for adjustment in adjustments:
        if currency and adjustment["currency"] != currency: continue
        amount = _money(adjustment["amount"]); amount_lbp = to_lbp(amount, adjustment["currency"], end)
        adjustment["amount_lbp"] = amount_lbp
        key = {"output": "adj_output", "input": "adj_input", "non_deductible": "non_deductible"}[adjustment["adjustment_type"]]
        line = bucket(adjustment["currency"])[key]; line["vat"] += amount; line["vat_lbp"] += amount_lbp; line["count"] += 1
    for values in per_currency.values():
        for field in ("vat", "vat_lbp"):
            values["prorata"][field] = -(values["mixed"][field] * (1 - ratio)).quantize(CENT, rounding=ROUND_HALF_UP)
            values["non_deductible"][field] += values["blocked"][field] - values["prorata"][field]
            values["total_output"][field] = values["sales"][field] + values["reverse_output"][field] + values["adj_output"][field]
            values["total_input"][field] = sum((values[k][field] for k in ("purchases", "assets", "expenses", "customs", "prorata", "adj_input")), ZERO)
            values["net"][field] = values["total_output"][field] - values["total_input"][field]
        values["non_deductible"]["base"] += values["blocked"]["base"]
        values["total_output"]["base"] = values["sales"]["base"]
        values["total_input"]["base"] = sum((values[k]["base"] for k in ("purchases", "assets", "expenses", "customs")), ZERO)
    totals_lbp = {key: sum((values[key]["vat_lbp"] for values in per_currency.values()), ZERO) for _, key, _ in LINES}
    # ---- Q4: adjust Q1-Q3 to the final annual ratio (Art. 32 adjustment of deductions)
    annual_adjustment = ZERO; adjustment_detail = []
    if int(quarter) == 4 and not currency:
        for previous_q in (1, 2, 3):
            previous = build_vat_return(db, year, previous_q, None, include_review, previous_year_db, None)
            mixed = sum((values["mixed"]["vat_lbp"] for values in previous["per_currency"].values()), ZERO)
            saved = saved_return(db, year, previous_q)
            applied = Decimal(str(saved["deduction_ratio"])) if saved and saved.get("deduction_ratio") not in (None, "") else previous["deduction_ratio"]
            change = (mixed * (ratio - applied)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            if mixed: adjustment_detail.append({"quarter": previous_q, "mixed_vat_lbp": mixed, "ratio_applied": applied, "adjustment_lbp": change})
            annual_adjustment += change
        totals_lbp["annual_adjustment"] = annual_adjustment
        totals_lbp["total_input"] += annual_adjustment; totals_lbp["net"] -= annual_adjustment; totals_lbp["non_deductible"] -= annual_adjustment
    source = "none"
    if credit_brought_forward not in (None, ""):
        credit_bf = _lbp(credit_brought_forward); source = "manual"
    else:
        credit_bf = ZERO; previous_year, previous_q = previous_quarter(year, quarter)
        for candidate in ([db] if previous_year == int(year) else [previous_year_db, db]):
            if candidate is None: continue
            try: previous = saved_return(candidate, previous_year, previous_q)
            except Exception: previous = None
            if previous:
                credit_bf = _lbp(previous["credit_carried_forward_lbp"]); source = f"Q{previous_q} {previous_year} saved return"; break
    net_after_credit = totals_lbp["net"] - credit_bf
    payable = _rounded_up(net_after_credit, end) if net_after_credit > 0 else ZERO
    if net_after_credit > 0 and end >= "2024-11-25":
        warnings.append("Payable is estimated by rounding up to LBP 10,000; the cited MoF decision 1195 has not been verified as a VAT payable rule. Confirm the current filing/payment rounding with the VAT Directorate before filing.")
    credit = -net_after_credit if net_after_credit < 0 else ZERO
    refund = _lbp(refund_requested) if refund_requested not in (None, "") else ZERO
    if refund < 0: raise ValueError("The refund requested cannot be negative")
    if refund > credit: raise ValueError(f"The refund requested cannot exceed the credit of {credit:,.0f} LBP")
    if refund:
        warnings.append("Refund eligibility is not validated. MoF guidance permits semiannual requests after Q2 or annual requests after year-end; quarterly requests require qualifying exporter status and are limited by the export proportion (Art. 30).")
    credit_cf = credit - refund
    saved = saved_return(db, year, quarter)
    changed = bool(saved) and (_lbp(saved["net_lbp"]) != _lbp(totals_lbp["net"]) or _lbp(saved["credit_brought_forward_lbp"]) != credit_bf)
    return {"year": int(year), "quarter": int(quarter), "date_from": start, "date_to": end, "due_date": due_date(year, quarter), "currency_filter": currency or "All",
        "include_review": bool(include_review), "per_currency": per_currency, "totals_lbp": totals_lbp,
        "deduction_ratio": ratio, "ratio_source": ratio_source, "ytd_turnover_lbp": {"taxable": ytd_taxable, "exempt": ytd_exempt}, "annual_adjustment_detail": adjustment_detail,
        "credit_brought_forward_lbp": credit_bf, "credit_source": source, "net_after_credit_lbp": net_after_credit,
        "payable_lbp": payable, "refund_requested_lbp": refund, "credit_carried_forward_lbp": credit_cf, "documents": documents, "adjustments": adjustments,
        "skipped": skipped, "review_excluded": review_excluded, "warnings": warnings, "saved": saved, "changed_since_saved": changed,
        "status": "saved" if saved and not changed else "changed after saving" if changed else "not saved"}


def _ensure_not_saved(db, year, quarter):
    if saved_return(db, year, quarter):
        raise ValueError(f"The Q{int(quarter)} {int(year)} VAT return is saved. An administrator must reopen it before it can be changed")


def add_adjustment(db, item, user_id, user_name=""):
    year = int(item.get("year") or 0); quarter = int(item.get("quarter") or 0); quarter_range(year, quarter)
    kind = str(item.get("adjustment_type") or "").lower()
    if kind not in ADJUSTMENT_TYPES: raise ValueError("Choose Output, Deductible or Non-deductible VAT adjustment")
    currency = str(item.get("currency") or "LBP").upper()
    if currency not in db.currency_codes(): raise ValueError(f"Currency {currency} is not set up (Security / Backup / Rates > Exchange Rates)")
    try: amount = Decimal(str(item.get("amount") or "").replace(",", ""))
    except Exception as exc: raise ValueError("Adjustment amount must be a number (use a minus sign to reduce)") from exc
    if not amount: raise ValueError("Adjustment amount cannot be zero")
    reason = str(item.get("reason") or "").strip()
    if len(reason) < 3: raise ValueError("Enter the reason for the adjustment")
    _ensure_not_saved(db, year, quarter)
    with db.connect() as connection:
        adjustment_id = connection.execute("""INSERT INTO vat_adjustments(year,quarter,currency,adjustment_type,amount,reason,created_by,created_by_name,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)""", (year, quarter, currency, kind, str(amount.quantize(CENT)), reason, user_id, user_name, utcnow())).lastrowid
        connection.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
            (user_id, "create", "vat_adjustment", adjustment_id, json.dumps({"year": year, "quarter": quarter, "type": kind, "amount": str(amount), "reason": reason}), utcnow()))
    return adjustment_id


def delete_adjustment(db, adjustment_id, user_id):
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM vat_adjustments WHERE id=?", (int(adjustment_id),)).fetchone()
    if not row: raise KeyError("Adjustment not found")
    _ensure_not_saved(db, row["year"], row["quarter"])
    with db.connect() as connection:
        connection.execute("DELETE FROM vat_adjustments WHERE id=?", (int(adjustment_id),))
        connection.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
            (user_id, "delete", "vat_adjustment", int(adjustment_id), json.dumps(dict(row)), utcnow()))
    return {"deleted": int(adjustment_id)}


def save_return(db, year, quarter, user_id, previous_year_db=None, credit_brought_forward=None, user_name="", refund_requested=None):
    result = build_vat_return(db, year, quarter, None, False, previous_year_db, credit_brought_forward, refund_requested)
    snapshot = json.dumps(json_ready({k: result[k] for k in ("per_currency", "totals_lbp", "credit_source", "review_excluded")}))
    with db.connect() as connection:
        connection.execute("""INSERT INTO vat_returns(year,quarter,net_lbp,credit_brought_forward_lbp,payable_lbp,credit_carried_forward_lbp,snapshot,saved_by,saved_by_name,saved_at)
            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(year,quarter) DO UPDATE SET net_lbp=excluded.net_lbp,
            credit_brought_forward_lbp=excluded.credit_brought_forward_lbp,payable_lbp=excluded.payable_lbp,
            credit_carried_forward_lbp=excluded.credit_carried_forward_lbp,snapshot=excluded.snapshot,saved_by=excluded.saved_by,
            saved_by_name=excluded.saved_by_name,saved_at=excluded.saved_at""",
            (int(year), int(quarter), str(result["totals_lbp"]["net"]), str(result["credit_brought_forward_lbp"]), str(result["payable_lbp"]),
             str(result["credit_carried_forward_lbp"]), snapshot, user_id, user_name, utcnow()))
        connection.execute("UPDATE vat_returns SET refund_requested_lbp=?,deduction_ratio=? WHERE year=? AND quarter=?",
            (str(result["refund_requested_lbp"]), str(result["deduction_ratio"]), int(year), int(quarter)))
        connection.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
            (user_id, "save", "vat_return", json.dumps({"year": int(year), "quarter": int(quarter), "payable_lbp": str(result["payable_lbp"]),
             "credit_carried_forward_lbp": str(result["credit_carried_forward_lbp"])}), utcnow()))
    return build_vat_return(db, year, quarter, None, False, previous_year_db, credit_brought_forward, refund_requested)


def reopen_return(db, year, quarter, user_id):
    if not saved_return(db, year, quarter): raise ValueError("This VAT return has not been saved")
    with db.connect() as connection:
        connection.execute("DELETE FROM vat_returns WHERE year=? AND quarter=?", (int(year), int(quarter)))
        connection.execute("INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)",
            (user_id, "reopen", "vat_return", json.dumps({"year": int(year), "quarter": int(quarter)}), utcnow()))
    return {"reopened": True}


def export_sections(result):
    """Export an internal VAT calculation schedule plus supporting documents."""
    title = f"Quarterly VAT Calculation Schedule - Q{result['quarter']} {result['year']} | {ARABIC_TITLE}"
    ratio = Decimal(str(result.get("deduction_ratio", 1)))
    meta = [f"Period: {display_date(result['date_from'])} to {display_date(result['date_to'])}   Due date: {display_date(result['due_date'])}   Currency filter: {result['currency_filter']}",
            f"Partial deduction ratio (Art. 31): {ratio * 100:.2f}% ({result.get('ratio_source', '')})   Status: {result['status']}",
            "Internal schedule references only: A-F labels are not certified Ministry of Finance form box numbers.",
            "Conversion uses saved accounting rates at each document date; the legally applicable tax-point/rate can differ (Decree 11230/2023). The 10,000 LBP payable ceiling from 25-11-2024 is an unverified worksheet estimate, not a certified VAT filing rule."]
    if result["review_excluded"]: meta.append(f"Note: {result['review_excluded']} document(s) in Review status are excluded from this return")
    for warning in result.get("warnings", []): meta.append("Check: " + warning)
    keys = [key for _, key, _ in LINES]; totals_index = [keys.index(k) for k in ("total_output", "total_input", "net")]
    no_base = ("adj_output", "adj_input", "net", "prorata", "annual_adjustment", "total_output")
    sections = []
    for code, values in sorted(result["per_currency"].items()):
        rows = [[number, label, ARABIC.get(key, ""), values[key]["base"] if key not in no_base else "", values[key]["vat"] if key not in ("sales_zero", "sales_exempt", "sales_out") else "",
                 values[key]["vat_lbp"] if key not in ("sales_zero", "sales_exempt", "sales_out") else ""] for number, key, label in LINES if key in values]
        sections.append({"heading": f"VAT calculation by currency - {code}", "headers": ["Internal ref.", "Description", "البيان", f"Base ({code})", f"VAT ({code})", "VAT (LBP)"],
                         "rows": rows, "total_rows": totals_index})
    totals = result["totals_lbp"]
    summary = [[number, label, ARABIC.get(key, ""), totals.get(key, ZERO)] for number, key, label in LINES if key not in ("sales_zero", "sales_exempt", "sales_out")]
    summary += [["F1", f"Credit brought forward ({result['credit_source']})", ARABIC["credit_bf"], result["credit_brought_forward_lbp"]],
                ["F2", "VAT PAYABLE TO THE MINISTRY OF FINANCE", ARABIC["payable"], result["payable_lbp"]],
                ["F3", "Refund of VAT credit requested (Art. 30)", ARABIC["refund"], result.get("refund_requested_lbp", ZERO)],
                ["F4", "Credit carried forward to the next period", ARABIC["credit_cf"], result["credit_carried_forward_lbp"]]]
    labels = [row[1] for row in summary]
    sections.append({"heading": "VAT calculation summary - all currencies in LBP | ملخص احتساب الضريبة", "headers": ["Internal ref.", "Description", "البيان", "Amount (LBP)"], "rows": summary,
                     "total_rows": [labels.index(l) for l in ("TOTAL OUTPUT VAT", "TOTAL DEDUCTIBLE VAT", "NET VAT FOR THE PERIOD (output VAT less deductible input VAT)", "VAT PAYABLE TO THE MINISTRY OF FINANCE", "Credit carried forward to the next period")]})
    turnover = result.get("ytd_turnover_lbp", {})
    ratio_rows = [["Taxable and zero-rated turnover (LBP, year to date)", turnover.get("taxable", ZERO)], ["Exempt turnover (LBP, year to date)", turnover.get("exempt", ZERO)],
                  ["Deduction ratio applied", f"{ratio * 100:.2f}%"], ["Basis", result.get("ratio_source", "")]]
    for item in result.get("annual_adjustment_detail", []):
        ratio_rows.append([f"Q{item['quarter']}: mixed-use VAT {item['mixed_vat_lbp']:,.0f} LBP at {Decimal(str(item['ratio_applied'])) * 100:.2f}%", item["adjustment_lbp"]])
    sections.append({"heading": "Partial deduction right (Art. 31)", "headers": ["Item", "Value"], "rows": ratio_rows, "total_rows": [2]})
    detail = [[display_date(d["date"]), d["number"], d["party"], CATEGORIES[d["category"]], d.get("treatment", "standard").replace("_", " "),
               d.get("deductible_share", ""), d["currency"], d["base"], d["vat"], d["lbp_rate"], d["vat_lbp"], d["status"]] for d in result["documents"]]
    sections.append({"heading": "Supporting documents", "headers": ["Date", "Document", "Customer / Supplier", "Category", "VAT Treatment", "Deductible",
                     "Currency", "Base", "VAT", "LBP Rate", "VAT (LBP)", "Status"], "rows": detail or [["No documents in this quarter"] + [""] * 11], "total_rows": []})
    if result["adjustments"]:
        sections.append({"heading": "Manual adjustments", "headers": ["Type", "Currency", "Amount", "Amount (LBP)", "Reason", "Entered by", "Entered at"],
            "rows": [[ADJUSTMENT_TYPES[a["adjustment_type"]], a["currency"], _money(a["amount"]), a.get("amount_lbp", ""), a["reason"],
                      a.get("created_by_name") or "", str(a["created_at"])[:16].replace("T", " ")] for a in result["adjustments"]], "total_rows": []})
    return title, meta, sections


def filing_worksheet(result, company):
    """Auto-fill a filing preparation sheet from the same quarterly VAT calculation.

    Sections follow the subjects of the public Q1-2 and Q11-2 specimens,
    not their box layout. A-F references remain internal worksheet references.
    """
    if result.get("currency_filter") != "All" or result.get("include_review"):
        raise ValueError("The filing worksheet requires All Currencies and excludes Review documents")
    totals = result["totals_lbp"]
    company_fields = (
        ("Registered company name", company.get("company_name")),
        ("Ministry of Finance / VAT number", company.get("company_mof")),
        ("Registered address", company.get("company_address")),
        ("Contact phone", company.get("company_phone")),
    )
    company_rows = [[label, str(value).strip() if value else "MISSING - complete in Settings"] for label, value in company_fields]
    missing = [label for label, value in company_fields if not str(value or "").strip()]
    worksheet = [
        ["Tax period", f"Q{result['quarter']} {result['year']}"],
        ["Period from", display_date(result["date_from"])],
        ["Period to", display_date(result["date_to"])],
        ["Filing due date", display_date(result["due_date"])],
        ["Deduction ratio", f"{Decimal(str(result['deduction_ratio'])) * 100:.2f}% ({result['ratio_source']})"],
        ["Source", "Posted invoices, expenses, customs and approved VAT adjustments"],
        ["Return state", result["status"]],
    ]
    bases = {}
    for doc in result["documents"]:
        parts = _classify(doc)
        if doc["category"] == "sales":
            for key in ("sales_base", "sales_zero", "sales_exempt", "sales_out"):
                bases[key] = bases.get(key, ZERO) + _lbp(parts.get(key, ZERO) * doc["lbp_rate"])
        else:
            key = doc["category"] if doc["recoverable"] and doc["use"] != "exempt" else "non_deductible"
            bases[key] = bases.get(key, ZERO) + _lbp((doc["base"] + doc["exempt"]) * doc["lbp_rate"])
    lines = [[number, label, ARABIC.get(key, ""), bases.get("sales_base" if key == "sales" else key, ""),
              totals.get(key, ZERO)] for number, key, label in LINES
             if key not in ("sales_zero", "sales_exempt", "sales_out")]
    # Taxable/exempt turnover is a base, not output tax. Convert each document
    # separately at its own historical LBP rate, rather than using a current rate.
    for number, key, label in (("A2", "sales_zero", "Zero-rated supplies (LBP)"),
                               ("A3", "sales_exempt", "Exempt supplies (LBP)"),
                               ("A4", "sales_out", "Outside scope supplies (LBP)")):
        lines.append([number, label, ARABIC.get(key, ""), bases.get(key, ZERO), ""])
    lines += [
        ["F1", "Credit brought forward", ARABIC["credit_bf"], "", result["credit_brought_forward_lbp"]],
        ["F2", "Amount payable", ARABIC["payable"], "", result["payable_lbp"]],
        ["F3", "Refund requested", ARABIC["refund"], "", result["refund_requested_lbp"]],
        ["F4", "Credit carried forward", ARABIC["credit_cf"], "", result["credit_carried_forward_lbp"]],
    ]
    by_ref = {line[0]: line for line in lines}
    headers = ["Internal ref.", "Description", "البيان", "Base (LBP)", "VAT / balance (LBP)"]
    def group(heading, refs, total_refs=()):
        rows = [by_ref[ref] for ref in refs]
        return {"heading": heading, "headers": headers, "rows": rows,
                "total_rows": [index for index, row in enumerate(rows) if row[0] in total_refs]}
    turnover = result.get("ytd_turnover_lbp", {})
    ratio = Decimal(str(result["deduction_ratio"]))
    notices = [
        "Preparation worksheet inspired by the sections of the Ministry's published Q1-2 and Q11-2 specimens (marked 2010), NOT a copy of either form.",
        "A-F references are internal and are not certified Ministry of Finance form box numbers. No current issued-form box mapping has been verified.",
        "The published specimens must not be used for filing; obtain the current issued Q1-2 and, where applicable, Q11-2 from the VAT Directorate and compare all amounts and schedules manually.",
        "The partial-deduction section is a calculation review, NOT a completed Q11-2 supplement; the published supplement asks for purchase, expense and asset use breakdowns not reproduced here.",
        "No electronic filing or submission is performed by this software.",
    ]
    if missing: notices.append("Missing employer information: " + ", ".join(missing))
    if result["review_excluded"]: notices.append(f"{result['review_excluded']} Review document(s) excluded; resolve before filing.")
    if result.get("changed_since_saved"): notices.append("Saved return changed: review and save it again.")
    if result.get("skipped"): notices.append(f"{len(result['skipped'])} document(s) skipped due to unreadable dates.")
    notices += ["Check: " + warning for warning in result.get("warnings", [])]
    return notices, [
        {"heading": "Taxpayer / المكلف (published Q1-2 specimen)", "headers": ["Field", "Value"], "rows": company_rows, "total_rows": []},
        {"heading": "Tax period / الفترة الضريبية (published Q1-2 specimen)", "headers": ["Field", "Value"], "rows": worksheet, "total_rows": []},
        group("Revenue and output VAT / الإيرادات والضريبة المستحقة (published Q1-2 specimen)",
              ("A1", "A2", "A3", "A4", "B1", "B2", "B3"), ("B3",)),
        group("Purchases, expenses and deductible VAT / المشتريات والأعباء (published Q1-2 specimen)",
              ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "D1"), ("C8",)),
        {"heading": "Partial-deduction review / حق الحسم الجزئي (Q11-2 specimen subject, not its boxes)",
         "headers": ["Internal calculation", "Value"],
         "rows": [["Taxable and zero-rated turnover (LBP, year to date)", turnover.get("taxable", ZERO)],
                  ["Exempt turnover (LBP, year to date)", turnover.get("exempt", ZERO)],
                  ["Deduction ratio applied", f"{ratio * 100:.2f}%"],
                  ["Ratio basis", result["ratio_source"]]],
         "total_rows": [2]},
        group("VAT balance and credit / الرصيد الضريبي (published Q1-2 specimen)",
              ("E1", "F1", "F2", "F3", "F4"), ("E1", "F2", "F4")),
    ]


def json_ready(value):
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, list): return [json_ready(v) for v in value]
    if isinstance(value, dict): return {k: json_ready(v) for k, v in value.items()}
    return value
