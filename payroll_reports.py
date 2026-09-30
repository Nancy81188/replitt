"""Lebanese payroll official reports (R5, R6, R10) built from saved payroll records.

Every figure is taken from the payroll records as they were calculated, so each month keeps
the tax brackets, NSSF rates and ceilings that were effective on its own period date.
Official amounts are shown in LBP; records kept in another currency are converted with the
exchange rate of their payroll period.
"""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

REPORTS = {
    "R10": "R10 - Quarterly Salary Tax Withholding Return | التصريح الفصلي عن الضريبة المقتطعة على الرواتب والأجور",
    "R5": "R5 - Annual Salary Tax Declaration (Employer Summary) | التصريح السنوي عن الرواتب والأجور",
    "R6": "R6 - Individual Annual Salary Statement | البيان الإفرادي السنوي للأجير",
}
PERIOD_TYPES = ("monthly", "quarterly", "yearly")
GROUPS = {"employee": "Employees", "manager": "Managers"}
COMPONENTS = (("salary", "Salary"), ("transport", "Transport"), ("overtime", "Overtime"), ("commission", "Commission"),
              ("retro_salary", "Retro Salary"), ("schooling", "Schooling"), ("bonus", "Bonus"), ("thirteenth_month", "13th Salary"))
MONEY_FIELDS = tuple(key for key, _ in COMPONENTS) + ("gross_salary", "taxable_salary", "nssf_base", "employee_nssf",
    "employer_medical", "employer_family", "employer_end_service", "net_salary", "retro_tax", "family_allowance")
ZERO = Decimal("0")


def period_range(period_type, year, index=1):
    period_type = str(period_type or "").lower()
    if period_type not in PERIOD_TYPES: raise ValueError("Period must be Monthly, Quarterly or Yearly")
    try: year = int(year); index = int(index or 1)
    except (TypeError, ValueError) as exc: raise ValueError("Enter a valid year and period") from exc
    if year < 2000 or year > 2100: raise ValueError("Enter a valid year")
    if period_type == "monthly":
        if not 1 <= index <= 12: raise ValueError("Month must be between 1 and 12")
        start, end = date(year, index, 1), date(year, index, calendar.monthrange(year, index)[1])
        label = f"{calendar.month_name[index]} {year}"
    elif period_type == "quarterly":
        if not 1 <= index <= 4: raise ValueError("Quarter must be between 1 and 4")
        first = 3 * index - 2
        start, end = date(year, first, 1), date(year, first + 2, calendar.monthrange(year, first + 2)[1])
        label = f"Q{index} {year} ({calendar.month_abbr[first]} - {calendar.month_abbr[first + 2]})"
    else:
        start, end = date(year, 1, 1), date(year, 12, 31); label = f"Year {year}"
    return start.isoformat(), end.isoformat(), label


def _lbp(value):
    return Decimal(str(value or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _rate_text(value):
    rate = Decimal(str(value or 0)) * 100
    return f"{rate.normalize():f}%"


def _ceiling_text(value):
    amount = Decimal(str(value or 0))
    return "No ceiling" if amount <= 0 else amount.quantize(Decimal("1"))


def _load_records(db, start, end, include_drafts):
    status = "" if include_drafts else " AND p.status='posted'"
    with db.connect() as connection:
        rows = [dict(row) for row in connection.execute(f"""SELECT p.*,e.employee_number,e.full_name,e.mof_number,e.nssf_number,
            e.national_id,e.marital_status,e.spouse_works,e.children,e.employee_group,e.job_title,e.hire_date,e.leave_date
            FROM payroll_records p JOIN employees e ON e.id=p.employee_id
            WHERE p.period_date>=? AND p.period_date<=?{status}
            ORDER BY e.employee_number,p.period_date""", (start, end))]
    cache = {}
    for row in rows:
        key = (row["currency"], row["period_date"])
        if key not in cache: cache[key] = db._converted_amount(Decimal("1"), row["currency"], "LBP", row["period_date"])
        rate = cache[key]; row["lbp_rate"] = rate
        lbp = {field: _lbp(Decimal(str(row.get(field) or 0)) * rate) for field in MONEY_FIELDS}
        stored_tax_lbp = Decimal(str(row.get("income_tax_lbp") or 0))
        lbp["income_tax"] = _lbp(stored_tax_lbp if stored_tax_lbp or row["currency"] == "LBP" else Decimal(str(row.get("income_tax") or 0)) * rate)
        lbp["family_deductions"] = max(ZERO, lbp["gross_salary"] - lbp["taxable_salary"])
        lbp["employer_total"] = lbp["employer_medical"] + lbp["employer_family"] + lbp["employer_end_service"]
        lbp["nssf_total"] = lbp["employer_total"] + lbp["employee_nssf"]
        row["lbp"] = lbp
    return rows


def _group_keys(group):
    group = str(group or "both").lower()
    if group in ("both", "all", "separate"): return ["employee", "manager"]
    if group not in GROUPS: raise ValueError("Group must be Employees, Managers or Both")
    return [group]


def _employee_totals(records):
    employees = {}
    for row in records:
        item = employees.setdefault(row["employee_id"], {"row": row, "months": set(), "totals": {}})
        item["months"].add(row["period_date"][:7])
        for key, value in row["lbp"].items(): item["totals"][key] = item["totals"].get(key, ZERO) + value
    return list(employees.values())


def _sum(items, key):
    return sum((item["totals"].get(key, ZERO) for item in items), ZERO)


def _family_text(row):
    status = "Married" if str(row.get("marital_status") or "").lower() in ("married", "spouse") else "Single"
    spouse = ", spouse works" if status == "Married" and int(row.get("spouse_works") or 0) else ""
    return f"{status}{spouse}, {int(row.get('children') or 0)} child(ren)"


def _settings_section(db, start, end):
    with db.connect() as connection:
        rows = [dict(row) for row in connection.execute("""SELECT * FROM payroll_settings
            WHERE date_from<=? AND (date_to IS NULL OR date_to='' OR date_to>=?) ORDER BY date_from""", (end, start))]
    headers = ["Effective From", "Effective To", "Employee Rate", "Employee Ceiling", "Medical Rate", "Medical Ceiling",
               "Family Rate", "Family Ceiling", "End-of-Service Rate", "End-of-Service Ceiling"]
    body = []
    for row in rows:
        body.append([_display(row["date_from"]), _display(row.get("date_to")) or "Open", _rate_text(row["employee_nssf_rate"]), _ceiling_text(row["employee_ceiling"]),
            _rate_text(row["medical_rate"]), _ceiling_text(row["medical_ceiling"]), _rate_text(row["family_rate"]), _ceiling_text(row["family_ceiling"]),
            _rate_text(row["end_service_rate"]), _ceiling_text(row["end_service_ceiling"])])
    return {"heading": "NSSF rates and ceilings applied (monthly ceilings in LBP, by effective date)", "headers": headers, "rows": body, "total_rows": []}, rows


def _display(value):
    text = str(value or "")
    return f"{text[8:10]}-{text[5:7]}-{text[:4]}" if len(text) == 10 and text[4] == "-" else text


def _employee_rate_label(settings_rows):
    rates = sorted({_rate_text(row["employee_nssf_rate"]) for row in settings_rows})
    return f"Employee NSSF ({' / '.join(rates)})" if rates else "Employee NSSF"


def _nssf_section(label, items, employee_label):
    headers = ["Emp. No.", "Employee Name", "NSSF No.", "Salary Subject to NSSF", employee_label, "Employer Medical",
               "Employer Family", "Employer End-of-Service", "Total Employer", "Total NSSF"]
    fields = ("nssf_base", "employee_nssf", "employer_medical", "employer_family", "employer_end_service", "employer_total", "nssf_total")
    rows = [[item["row"]["employee_number"], item["row"]["full_name"], item["row"].get("nssf_number") or ""] + [item["totals"][f] for f in fields] for item in items]
    rows.append(["TOTAL", f"{len(items)} {label.lower()}", ""] + [_sum(items, f) for f in fields])
    return {"heading": f"NSSF contributions - {label}", "headers": headers, "rows": rows, "total_rows": [len(rows) - 1]}


def _r10_sections(label, items):
    headers = ["Emp. No.", "Employee Name", "MOF No.", "Months"] + [name for _, name in COMPONENTS] + ["Gross", "Deductions & Exemptions", "Taxable", "Income Tax", "of which Retro Tax"]
    fields = [key for key, _ in COMPONENTS] + ["gross_salary", "family_deductions", "taxable_salary", "income_tax", "retro_tax"]
    rows = [[item["row"]["employee_number"], item["row"]["full_name"], item["row"].get("mof_number") or "", len(item["months"])] + [item["totals"][f] for f in fields] for item in items]
    rows.append(["TOTAL", f"{len(items)} {label.lower()}", "", ""] + [_sum(items, f) for f in fields])
    return [{"heading": f"Salary tax withheld - {label}", "headers": headers, "rows": rows, "total_rows": [len(rows) - 1]}]


def _r5_sections(label, items):
    summary = [[name, _sum(items, key)] for key, name in COMPONENTS]
    summary += [["Total gross salaries and benefits", _sum(items, "gross_salary")], ["Family deductions and exempt allowances", _sum(items, "family_deductions")],
        ["Total taxable income", _sum(items, "taxable_salary")], ["Salary tax withheld", _sum(items, "income_tax")],
        ["of which tax on retroactive salary", _sum(items, "retro_tax")], ["Employee NSSF withheld", _sum(items, "employee_nssf")],
        ["Employer NSSF contributions", _sum(items, "employer_total")], ["Number of employees", len(items)]]
    headers = ["Emp. No.", "Employee Name", "MOF No.", "NSSF No.", "Family Status", "Months", "Gross", "Deductions & Exemptions", "Taxable", "Income Tax"]
    fields = ("gross_salary", "family_deductions", "taxable_salary", "income_tax")
    rows = [[item["row"]["employee_number"], item["row"]["full_name"], item["row"].get("mof_number") or "", item["row"].get("nssf_number") or "",
             _family_text(item["row"]), len(item["months"])] + [item["totals"][f] for f in fields] for item in items]
    rows.append(["TOTAL", f"{len(items)} {label.lower()}", "", "", "", ""] + [_sum(items, f) for f in fields])
    return [{"heading": f"Declaration summary - {label}", "headers": ["Item", "Amount (LBP)"], "rows": summary, "total_rows": [8, 10, 11]},
            {"heading": f"Employee schedule - {label}", "headers": headers, "rows": rows, "total_rows": [len(rows) - 1]}]


def _r6_sections(label, records, employee_label):
    sections = []
    headers = ["Month"] + [name for _, name in COMPONENTS] + ["Retro Period", "Gross", "Taxable", "Income Tax", "Retro Tax", employee_label, "NSSF Family Allowance", "Net Salary", "Status"]
    fields = [key for key, _ in COMPONENTS]
    tail = ("gross_salary", "taxable_salary", "income_tax", "retro_tax", "employee_nssf", "family_allowance", "net_salary")
    by_employee = {}
    for row in records: by_employee.setdefault(row["employee_id"], []).append(row)
    for rows in by_employee.values():
        first = rows[0]; body = []
        for row in rows:
            retro = f"{_display(row.get('retro_from'))} to {_display(row.get('retro_to'))}" if row.get("retro_from") else ""
            body.append([row["period_date"][5:7] + "-" + row["period_date"][:4]] + [row["lbp"][f] for f in fields] + [retro] + [row["lbp"][f] for f in tail] + [row["status"]])
        totals = ["TOTAL"] + [sum((row["lbp"][f] for row in rows), ZERO) for f in fields] + [""] + [sum((row["lbp"][f] for row in rows), ZERO) for f in tail] + [""]
        body.append(totals)
        heading = (f"{label[:-1] if label.endswith('s') else label} {first['employee_number']} - {first['full_name']} | MOF {first.get('mof_number') or '-'} | "
                   f"NSSF {first.get('nssf_number') or '-'} | {_family_text(first)}")
        sections.append({"heading": heading, "headers": headers, "rows": body, "total_rows": [len(body) - 1]})
    return sections


def build_payroll_report(db, report="R10", period_type="quarterly", year=None, index=1, group="both", include_drafts=False):
    report = str(report or "R10").upper()
    if report == "NSSF": return build_nssf_statement(db, period_type, year, index, include_drafts)
    if report == "SETTLEMENT": return build_nssf_settlement(db, year or date.today().year)
    if report == "CEILINGS": return build_ceilings_by_month(db, year or date.today().year)
    if report not in REPORTS: raise ValueError("Report must be R5, R6, R10, NSSF or CEILINGS")
    start, end, label = period_range(period_type, year or date.today().year, index)
    records = _load_records(db, start, end, bool(include_drafts))
    settings_section, settings_rows = _settings_section(db, start, end)
    employee_label = _employee_rate_label(settings_rows)
    company = db.settings()
    sections = []; summary = {}
    for key in _group_keys(group):
        group_label = GROUPS[key]
        group_records = [row for row in records if (row.get("employee_group") or "employee") == key]
        items = _employee_totals(group_records)
        summary[key] = {"employees": len(items), "gross": float(_sum(items, "gross_salary")), "income_tax": float(_sum(items, "income_tax")),
                        "retro_tax": float(_sum(items, "retro_tax")), "employee_nssf": float(_sum(items, "employee_nssf")), "employer_nssf": float(_sum(items, "employer_total"))}
        if not items:
            sections.append({"heading": f"{group_label}", "headers": ["Note"], "rows": [[f"No {'posted ' if not include_drafts else ''}payroll for {group_label.lower()} in {label}"]], "total_rows": []})
            continue
        if report == "R10": sections += _r10_sections(group_label, items)
        elif report == "R5": sections += _r5_sections(group_label, items)
        else: sections += _r6_sections(group_label, group_records, employee_label)
        sections.append(_nssf_section(group_label, items, employee_label))
    if len(summary) > 1:
        combined = [["Employees and managers", sum(v["employees"] for v in summary.values()), sum(v["gross"] for v in summary.values()),
                     sum(v["income_tax"] for v in summary.values()), sum(v["retro_tax"] for v in summary.values()),
                     sum(v["employee_nssf"] for v in summary.values()), sum(v["employer_nssf"] for v in summary.values())]]
        rows = [[GROUPS[k], v["employees"], v["gross"], v["income_tax"], v["retro_tax"], v["employee_nssf"], v["employer_nssf"]] for k, v in summary.items()] + combined
        sections.append({"heading": "Grand total", "headers": ["Group", "Employees", "Gross", "Income Tax", "Retro Tax", employee_label, "Employer NSSF"],
                         "rows": [[r[0], r[1]] + [_lbp(x) for x in r[2:]] for r in rows], "total_rows": [len(rows) - 1]})
    sections.append(settings_section)
    meta = [f"Company: {company.get('company_name') or '-'}   MOF No.: {company.get('company_mof') or '-'}",
            f"Period: {label} ({_display(start)} to {_display(end)})   Amounts in LBP",
            "Source: " + ("posted and draft payroll (draft figures are not final)" if include_drafts else "posted payroll only")]
    return {"report": report, "title": REPORTS[report], "period_label": label, "date_from": start, "date_to": end,
            "meta": meta, "sections": sections, "summary": summary, "record_count": len(records)}


def json_ready(result):
    """Convert Decimals for the JSON API."""
    def convert(value):
        if isinstance(value, Decimal): return float(value)
        if isinstance(value, list): return [convert(v) for v in value]
        if isinstance(value, dict): return {k: convert(v) for k, v in value.items()}
        return value
    return convert(result)


# ---------------------------------------------------------------- NSSF contributions statement (payment)
NSSF_TITLE = "NSSF Contributions Statement | بيان الاشتراكات المتوجبة للصندوق الوطني للضمان الاجتماعي"


def _month_end(iso):
    year, month = int(iso[:4]), int(iso[5:7])
    return f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def nssf_declaration_period(employees, year, month):
    """Pick the declaration period from the roster at the selected month's end.

    Nine or fewer employees use a quarter; ten or more use a month. An
    employee who left earlier or has not yet joined is not counted.
    """
    year, month = int(year), int(month)
    end = _month_end(f"{year}-{month:02d}-01")
    def saved_date(value):
        value = str(value or "")
        return value[6:] + "-" + value[3:5] + "-" + value[:2] if len(value) == 10 and value[2:3] == "-" else value
    count = sum((not employee.get("hire_date") or saved_date(employee["hire_date"]) <= end)
                and (not employee.get("leave_date") or saved_date(employee["leave_date"]) >= end)
                and (employee.get("active", True) or bool(employee.get("leave_date")))
                for employee in employees)
    return ("quarterly", (month - 1) // 3 + 1, count) if count < 10 else ("monthly", month, count)


def build_nssf_statement(db, period_type="monthly", year=None, index=1, include_drafts=False):
    """Per employee: salary subject to NSSF, capped bases and contributions by branch (sickness & maternity
    employee + employer, family allowances, end of service), NSSF family allowances already paid, and the
    net amount to pay to the NSSF. Bases are the ones of each payroll month (monthly ceilings)."""
    auto = str(period_type or "").lower() == "auto"
    employee_count_at_selection = None
    if auto:
        period_type, index, employee_count_at_selection = nssf_declaration_period(
            db.list_employees(), year or date.today().year, index)
    start, end, label = period_range(period_type, year or date.today().year, index)
    if auto: label += f" | Auto: {employee_count_at_selection} employee(s), {period_type} declaration"
    records = _load_records(db, start, end, bool(include_drafts)); company = db.settings()
    rows = []; payroll_employee_ids = {row["employee_id"] for row in records}
    company_employees = db.list_employees()
    current_employee_count = sum(bool(employee["active"]) for employee in company_employees)
    def stored_date(value):
        value=str(value or "")
        return value[6:]+"-"+value[3:5]+"-"+value[:2] if len(value)==10 and value[2:3]=="-" else value
    period_employees = [employee for employee in company_employees
                        if (not employee.get("hire_date") or stored_date(employee["hire_date"]) <= end)
                        and (not employee.get("leave_date") or stored_date(employee["leave_date"]) >= start)]
    roster = [[employee["employee_number"],employee["full_name"],employee.get("nssf_number") or "MISSING",
               employee.get("nationality") or "MISSING",employee.get("hire_date") or "-",employee.get("leave_date") or "-",
               "Yes" if employee["id"] in payroll_employee_ids else "No"] for employee in period_employees]
    totals = {k: ZERO for k in ("salary", "sick_base", "employee", "employer_sick", "family_base", "family", "eos_base", "eos", "total", "allowance", "net")}
    rates_seen = {}
    for row in records:
        settings = db.payroll_settings_for(_month_end(row["period_date"])); lbp = row["lbp"]
        rate = lambda name: Decimal(str(settings.get(name) or 0))
        allowance = _lbp(Decimal(str(row.get("family_allowance") or 0)) * row["lbp_rate"])
        subject = lbp["nssf_base"]
        if Decimal(str(row.get("retro_salary") or 0)):
            # retroactive pay uses the ceilings of its own months: take the bases from the saved contributions
            base = lambda amount, name: _lbp(amount / rate(name)) if rate(name) else ZERO
            values = {"salary": subject, "sick_base": base(lbp["employee_nssf"], "employee_nssf_rate"), "employee": lbp["employee_nssf"],
                      "employer_sick": lbp["employer_medical"], "family_base": base(lbp["employer_family"], "family_rate"), "family": lbp["employer_family"],
                      "eos_base": base(lbp["employer_end_service"], "end_service_rate"), "eos": lbp["employer_end_service"], "allowance": allowance}
        else:
            # contributions are paid in LBP: capped base of the month x rate, computed directly in LBP
            capped = lambda ceiling: min(subject, Decimal(str(settings.get(ceiling) or 0))) if Decimal(str(settings.get(ceiling) or 0)) > 0 else subject
            sick = capped("medical_ceiling"); employee_base = capped("employee_ceiling"); family = capped("family_ceiling"); eos = capped("end_service_ceiling")
            values = {"salary": subject, "sick_base": sick, "employee": _lbp(employee_base * rate("employee_nssf_rate")), "employer_sick": _lbp(sick * rate("medical_rate")),
                      "family_base": family, "family": _lbp(family * rate("family_rate")), "eos_base": eos, "eos": _lbp(eos * rate("end_service_rate")), "allowance": allowance}
        values["total"] = values["employee"] + values["employer_sick"] + values["family"] + values["eos"]; values["net"] = values["total"] - allowance
        for key, value in values.items(): totals[key] += value
        rates_seen[_month_end(row["period_date"])[:7]] = (settings.get("medical_ceiling"), settings.get("family_ceiling"), settings.get("employee_nssf_rate"), settings.get("medical_rate"),
                                                          settings.get("family_rate"), settings.get("end_service_rate"))
        rows.append([row.get("nssf_number") or "-", row["full_name"], row["period_date"][5:7] + "-" + row["period_date"][:4]] + [values[k] for k in
                    ("salary", "sick_base", "employee", "employer_sick", "family_base", "family", "eos_base", "eos", "total", "allowance", "net")])
    rows.sort(key=lambda r: (r[1], r[2][3:] + r[2][:2]))
    rows.append(["TOTAL | المجموع", f"{len(payroll_employee_ids)} employee(s)", ""] + [totals[k] for k in ("salary", "sick_base", "employee", "employer_sick", "family_base", "family", "eos_base", "eos", "total", "allowance", "net")])
    def rate_label(position):
        labels=sorted({_rate_text(values[position]) for values in rates_seen.values()})
        return " / ".join(labels) if labels else "saved rate"
    headers = ["NSSF No. | رقم الضمان", "Employee | الأجير", "Month | الشهر", "Salary subject | الأجر الخاضع", "Sickness base | أساس المرض", f"Employee {rate_label(2)} | حصة الأجير",
               f"Employer {rate_label(3)} | صاحب العمل", "Family base | أساس العائلية", f"Family {rate_label(4)} | العائلية", "EOS base | أساس نهاية الخدمة", f"EOS {rate_label(5)} | نهاية الخدمة",
               "Total | المجموع", "Allowances | تعويضات مدفوعة", "Net due | الصافي"]
    summary = [[f"Sickness & maternity - employee share ({rate_label(2)})", "المرض والأمومة - حصة الأجير", totals["employee"]],
               [f"Sickness & maternity - employer share ({rate_label(3)})", "المرض والأمومة - حصة صاحب العمل", totals["employer_sick"]],
               ["Sickness & maternity - total", "مجموع المرض والأمومة", totals["employee"] + totals["employer_sick"]],
               ["Family allowances branch", "فرع التعويضات العائلية", totals["family"]],
               ["End-of-service indemnity branch", "فرع تعويض نهاية الخدمة", totals["eos"]],
               ["TOTAL CONTRIBUTIONS", "مجموع الاشتراكات", totals["total"]],
               ["Less: family allowances paid to employees on behalf of the NSSF", "ينزل: التعويضات العائلية المدفوعة عن الصندوق", totals["allowance"]],
               ["NET AMOUNT PAYABLE TO THE NSSF (LBP)", "الصافي المتوجب دفعه للصندوق (ل.ل.)", totals["net"]]]
    ceilings = [[month[5:] + "-" + month[:4], _ceiling_text(v[0]), _ceiling_text(v[1]), _rate_text(v[2]), _rate_text(v[3]), _rate_text(v[4]), _rate_text(v[5])] for month, v in sorted(rates_seen.items())]
    sections = [{"heading": f"Employees - {label} | الأجراء", "headers": headers, "rows": rows if len(rows) > 1 else [["No payroll in this period"] + [""] * 13], "total_rows": [len(rows) - 1] if len(rows) > 1 else []},
                {"heading": f"Company employee list - {len(period_employees)} in period, {len(payroll_employee_ids)} with payroll | لائحة الأجراء",
                 "headers": ["Emp. No.","Employee Name","NSSF No.","Nationality","Hire Date","Leave Date","Payroll in period"],
                 "rows": roster or [["No employees in this period"]+[""]*6],"total_rows": []},
                {"heading": "Payment summary | خلاصة الدفع", "headers": ["Branch", "الفرع", "Amount (LBP)"], "rows": summary, "total_rows": [2, 5, 7]},
                {"heading": "Monthly ceilings and rates applied | السقوف والنسب المعتمدة شهرياً", "headers": ["Month", "Sickness ceiling", "Family ceiling", "Employee", "Employer sickness", "Family", "End of service"],
                 "rows": ceilings or [["-"] * 7], "total_rows": []}]
    meta = [f"Employer: {company.get('company_name') or '-'}   Employer NSSF No.: {company.get('company_nssf') or '-'}   MOF No.: {company.get('company_mof') or '-'}",
            f"Current active employees: {current_employee_count}   In selected period: {len(period_employees)}   With payroll: {len(payroll_employee_ids)}",
            f"Period: {label} ({_display(start)} to {_display(end)})   Amounts in LBP   Source: " + ("posted and draft payroll" if include_drafts else "posted payroll")]
    return {"report": "NSSF", "title": NSSF_TITLE, "period_label": label, "date_from": start, "date_to": end, "meta": meta, "sections": sections,
            "declaration_period": period_type, "declaration_employee_count": employee_count_at_selection,
            "record_count": len(records), "employee_count": len(period_employees), "active_employee_count": current_employee_count,
            "payroll_employee_count": len(payroll_employee_ids), "net_payable_lbp": totals["net"], "summary": {k: v for k, v in totals.items()}}


def build_nssf_settlement(db,year):
    """Reconcile annual posted payroll with wages previously filed at the NSSF.

    Missing filed wages/payments remain missing: never treat an unknown filing as zero.
    This is a review worksheet, not an official submission or a posting instruction.
    """
    year=int(year)
    statement=build_nssf_statement(db,"yearly",year,include_drafts=False)
    filed={row["month"]:row for row in db.nssf_filed_wages(year)}
    actual={month:{"sick":ZERO,"family":ZERO,"eos":ZERO,"net":ZERO} for month in range(1,13)}
    for row in statement["sections"][0]["rows"][:-1]:
        month=int(row[2][:2]); total=actual[month]
        for key,column in (("sick",4),("family",7),("eos",9),("net",13)): total[key]+=Decimal(str(row[column]))
    lines=[]; payments=[]; missing=[]; wage_difference=ZERO; amount_paid=ZERO
    for month in range(1,13):
        data=filed.get(month,{})
        values=[data.get(field) for field in ("sickness_wages","family_wages","end_service_wages","amount_paid")]
        if any(value is None for value in values): missing.append(month)
        rates=db.payroll_settings_for(_month_end(f"{year}-{month:02d}-01"))
        rate=lambda key: Decimal(str(rates.get(key) or 0))
        if all(value is not None for value in values[:3]):
            difference=_lbp((actual[month]["sick"]-Decimal(values[0]))*(rate("employee_nssf_rate")+rate("medical_rate"))
                +(actual[month]["family"]-Decimal(values[1]))*rate("family_rate")
                +(actual[month]["eos"]-Decimal(values[2]))*rate("end_service_rate"))
            wage_difference+=difference
        else: difference="MISSING FILED WAGES"
        if values[3] is not None: amount_paid+=Decimal(values[3])
        lines.append([f"{month:02d}-{year}",actual[month]["sick"],values[0] if values[0] is not None else "MISSING",
                      actual[month]["family"],values[1] if values[1] is not None else "MISSING",
                      actual[month]["eos"],values[2] if values[2] is not None else "MISSING",
                      difference])
        payments.append([f"{month:02d}-{year}",actual[month]["net"],values[3] if values[3] is not None else "MISSING"])
    complete=not missing
    summary=[["Annual NSSF net contribution from posted payroll",statement["net_payable_lbp"]],
             ["Payments entered from filed NSSF declarations",amount_paid if complete else "INCOMPLETE"],
             ["Balance after entered payments",statement["net_payable_lbp"]-amount_paid if complete else "INCOMPLETE"],
             ["Wage-base settlement difference at each month's saved rates",wage_difference if complete else "INCOMPLETE"]]
    meta=statement["meta"]+["Annual settlement review: compare actual payroll with amounts filed and paid outside the application.",
        "Enter all 12 months of filed wage bases and payments; a blank is unknown, not zero."]
    if missing: meta.append("Incomplete months: "+", ".join(str(month) for month in missing))
    return {"report":"SETTLEMENT","title":f"NSSF Annual Settlement Review {year}","period_label":f"Year {year}",
            "date_from":f"{year}-01-01","date_to":f"{year}-12-31","record_count":statement["record_count"],
            "employee_count":statement["employee_count"],"complete":complete,"meta":meta,"summary":{},
            "sections":[{"heading":"Monthly payroll vs filed wage bases (LBP)",
                "headers":["Month","Actual sickness base","Filed sickness base","Actual family base","Filed family base",
                           "Actual EOS base","Filed EOS base","Wage settlement difference"],
                "rows":lines,"total_rows":[]},
                {"heading":"Monthly NSSF contribution and payment (LBP)",
                 "headers":["Month","Payroll NSSF net","Payments filed"],"rows":payments,"total_rows":[]},
                {"heading":"Annual settlement review","headers":["Item","Amount (LBP)"],"rows":summary,"total_rows":[2,3]}]}


def build_ceilings_by_month(db, year):
    """The NSSF ceilings and rates of every month of a year (as used by payroll: the rules on the last day of the month)."""
    year = int(year); rows = []
    for month in range(1, 13):
        day = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"; s = db.payroll_settings_for(day)
        rows.append([f"{calendar.month_name[month]} {year}", _ceiling_text(s.get("employee_ceiling")), _ceiling_text(s.get("medical_ceiling")), _ceiling_text(s.get("family_ceiling")),
                     _rate_text(s.get("employee_nssf_rate")), _rate_text(s.get("medical_rate")), _rate_text(s.get("family_rate")), _rate_text(s.get("end_service_rate")),
                     _ceiling_text(s.get("tax_rounding")) if Decimal(str(s.get("tax_rounding") or 0)) else "-", _display(s.get("date_from"))])
    headers = ["Month | الشهر", "Employee ceiling", "Sickness & maternity ceiling", "Family allowances ceiling", "Employee", "Employer sickness", "Family", "End of service", "Tax rounding", "Rules from"]
    return {"report": "CEILINGS", "title": f"NSSF Ceilings by Month {year} | سقوف الضمان الاجتماعي الشهرية", "period_label": str(year), "meta": ["Monthly ceilings in LBP (the rules in force on the last day of each month)"],
            "sections": [{"heading": f"Year {year}", "headers": headers, "rows": rows, "total_rows": []}], "record_count": 12, "summary": {}}
