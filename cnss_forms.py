"""In-app CNSS form previews and filled copies using the user's supplied blanks."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class CNSSForm:
    key: str
    label: str
    filename: str
    kind: str


FORMS = (
    CNSSForm("cnss_termination_notice", "Employee leaving notice — ترك أجير", "cnss_termination_notice.pdf", "employee"),
    CNSSForm("cnss_r3_employee_registration", "R3-1 — Request to register employees", "cnss_r3_employee_registration.pdf", "employee"),
    CNSSForm("cnss_r3", "R3 — New employee registration", "cnss_r3.pdf", "employee"),
    CNSSForm("cnss_employment_declaration", "Employment declaration — تصريح باستخدام أجير", "cnss_employment_declaration.pdf", "employee"),
    CNSSForm("cnss_employee_use_notice", "Employee use notice — CNSS 41A", "cnss_employee_use_notice.pdf", "employee"),
    CNSSForm("cnss_contributions_monthly_quarterly", "Contributions payment — monthly / quarterly (CNSS 190A)", "cnss_contributions_monthly_quarterly.pdf", "period"),
    CNSSForm("cnss_contributions_yearly", "Contributions payment — yearly (CNSS 351)", "cnss_contributions_yearly.pdf", "yearly"),
    CNSSForm("cnss_annual_declaration", "Annual wage declaration — CNSS 386", "cnss_annual_declaration_by_month_or_quarter.pdf", "annual"),
)

FORM_BY_KEY = {item.key: item for item in FORMS}
FORM_BY_LABEL = {item.label: item.key for item in FORMS}

LEGACY_FORM_KEYS = {
    "R3": "cnss_r3",
    "R3-1": "cnss_r3_employee_registration",
    "NSSF-DUE": "cnss_contributions_monthly_quarterly",
    "NSSF-SETTLEMENT": "cnss_annual_declaration",
    "NSSF-ANNUAL": "cnss_contributions_yearly",
    "NSSF-HIRE-NEW": "cnss_employee_use_notice",
    "NSSF-HIRE-EXISTING": "cnss_employment_declaration",
    "NSSF-LEAVE": "cnss_termination_notice",
}


@dataclass(frozen=True)
class Overlay:
    page: int
    rect: tuple[float, float, float, float]
    key: str
    fontsize: float = 7.5
    align: str = "right"


def app_root() -> Path:
    """Return the unpacked asset root for source runs and PyInstaller builds."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def template_path(form_key: str, root: Path | None = None) -> Path:
    form = FORM_BY_KEY.get(form_key)
    if form is None:
        raise ValueError(f"Unknown CNSS form: {form_key}")
    path = (root or app_root()) / "Assets" / "payroll_forms" / form.filename
    if not path.is_file():
        raise FileNotFoundError(f"Supplied CNSS form template is missing: {path}")
    return path


def _value(source: Mapping[str, Any] | None, key: str) -> str:
    if not source:
        return ""
    raw = source.get(key)
    return "" if raw is None else str(raw).strip()


def _date(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        year, month, day = text.split("-")
        return f"{day}/{month}/{year}"
    if re.fullmatch(r"\d{2}-\d{2}-\d{4}", text):
        return text.replace("-", "/")
    return text


def _amount(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def period_months(period_type: str, year: int, index: int) -> list[int]:
    kind = str(period_type or "").lower()
    if kind == "monthly":
        return [int(index)]
    if kind == "quarterly":
        first = (int(index) - 1) * 3 + 1
        return [first, first + 1, first + 2]
    return list(range(1, 13))


def _aggregate_filed_months(rows: Sequence[Mapping[str, Any]], months: Sequence[int], keys: Sequence[str]) -> tuple[dict[str, float], bool]:
    by_month = {int(row.get("month", 0)): row for row in rows if row.get("month") is not None}
    totals = {key: 0.0 for key in keys}
    complete = True
    for month in months:
        row = by_month.get(int(month), {})
        for key in keys:
            value = row.get(key)
            if value is None or value == "":
                complete = False
            else:
                try:
                    totals[key] += float(value)
                except (TypeError, ValueError):
                    complete = False
    return totals, complete


def _annual_report_bases(report: Mapping[str, Any] | None) -> dict[int, dict[str, float]]:
    """Collect per-month actual bases from the yearly NSSF report rows."""
    result: dict[int, dict[str, float]] = {}
    for row in _annual_report_rows(report):
        try:
            month = int(str(row[2]).split("-")[0])
            if month < 1 or month > 12:
                continue
            result.setdefault(month, {"sick": 0.0, "family": 0.0, "eos": 0.0})
            result[month]["sick"] += float(row[4] or 0)
            result[month]["family"] += float(row[7] or 0)
            result[month]["eos"] += float(row[9] or 0)
        except (TypeError, ValueError, IndexError):
            continue
    return result


def _annual_report_rows(report: Mapping[str, Any] | None) -> list[Sequence[Any]]:
    if not report:
        return []
    sections = report.get("sections") or []
    rows = sections[0].get("rows") if sections and isinstance(sections[0], Mapping) else []
    return [
        row for row in (rows or [])
        if isinstance(row, (list, tuple))
        and len(row) >= 10
        and not str(row[0]).upper().startswith("TOTAL")
    ]


def _annual_schedule_data(
    report: Mapping[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[int, float]]]:
    """Group the posted annual NSSF rows into employee/month branch bases."""
    branch_columns = {"sick": 4, "family": 7, "eos": 9}
    employees: dict[str, dict[str, Any]] = {}
    totals = {branch: {} for branch in branch_columns}

    for row_index, row in enumerate(_annual_report_rows(report), start=1):
        try:
            month = int(str(row[2]).split("-")[0])
            if month < 1 or month > 12:
                continue
        except (TypeError, ValueError):
            continue

        number = str(row[0] or "").strip()
        name = str(row[1] or "").strip()
        identity = number or name
        if not identity:
            identity = f"__unidentified_{row_index:05d}"
            name = f"Unidentified payroll row {row_index} - review"
        employee = employees.setdefault(identity, {
            "number": number,
            "name": name,
            "months": {},
        })
        month_values = employee["months"].setdefault(month, {})
        for branch, column in branch_columns.items():
            raw = row[column]
            if raw is None or raw == "":
                continue
            try:
                amount = float(raw)
            except (TypeError, ValueError):
                continue
            month_values[branch] = month_values.get(branch, 0.0) + amount
            totals[branch][month] = totals[branch].get(month, 0.0) + amount

    return employees, totals


def build_form_values(
    form_key: str,
    company: Mapping[str, Any] | None,
    employee: Mapping[str, Any] | None = None,
    report: Mapping[str, Any] | None = None,
    filed_wages: Sequence[Mapping[str, Any]] = (),
    *,
    year: int | None = None,
    period_type: str = "monthly",
    index: int = 1,
    payment_details: Mapping[str, Any] | None = None,
    settlement_report: Mapping[str, Any] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Create only values supported by saved company, employee, or payroll data.

    Missing filed wages and payment details stay blank rather than being treated
    as zero. The second return value is a user-facing list of incomplete fields.
    """
    if form_key not in FORM_BY_KEY:
        raise ValueError(f"Unknown CNSS form: {form_key}")

    values = {
        "company_name": _value(company, "company_name"),
        "company_nssf": _value(company, "company_nssf"),
        "company_mof": _value(company, "company_mof"),
        "company_address": _value(company, "company_address"),
        "company_phone": _value(company, "company_phone"),
        "company_email": _value(company, "company_email"),
        "employee_number": _value(employee, "employee_number"),
        "employee_name": _value(employee, "full_name"),
        "employee_father": _value(employee, "father_name"),
        "employee_mother": _value(employee, "mother_name"),
        "employee_nationality": _value(employee, "nationality"),
        "employee_birth_date": _date(_value(employee, "birth_date")),
        "employee_birth_place": _value(employee, "birth_place"),
        "employee_national_id": _value(employee, "national_id"),
        "employee_mof": _value(employee, "mof_number"),
        "employee_nssf": _value(employee, "nssf_number"),
        "employee_address": _value(employee, "address"),
        "employee_phone": _value(employee, "contact_number"),
        "employee_job": _value(employee, "job_title"),
        "employee_hire_date": _date(_value(employee, "hire_date")),
        "employee_leave_date": _date(_value(employee, "leave_date")),
        "employee_salary": _amount(_value(employee, "base_salary")),
        "employee_marital": _value(employee, "marital_status"),
        "employee_children": _value(employee, "children"),
        "employee_spouse_works": "Yes" if employee and bool(employee.get("spouse_works")) else "",
        "year": str(year or ""),
        "period_label": str((report or {}).get("period_label") or ""),
    }
    missing: list[str] = []
    form = FORM_BY_KEY[form_key]

    if form.kind == "employee":
        if not employee:
            missing.append("Select an employee to fill employee details.")
        for key, label in (
            ("company_name", "Company name"),
            ("company_nssf", "Employer NSSF number"),
        ):
            if not values[key]:
                missing.append(f"{label} is missing in Company Settings.")
        if employee:
            for key, label in (
                ("employee_name", "Employee name"),
                ("employee_national_id", "Employee national ID"),
                ("employee_nssf", "Employee NSSF number"),
            ):
                if not values[key]:
                    missing.append(f"{label} is missing in the employee file.")
        return values, missing

    if not report:
        missing.append("Generate or select a payroll period to load contribution totals.")
        return values, missing

    summary = report.get("summary") or {}
    values.update({
        "employee_count": str(report.get("payroll_employee_count") or report.get("employee_count") or 0),
        "sickness_wages": _amount(summary.get("sick_base")),
        "sickness_due": _amount(float(summary.get("employee") or 0) + float(summary.get("employer_sick") or 0)),
        "eos_wages": _amount(summary.get("eos_base")),
        "eos_due": _amount(summary.get("eos")),
        "family_wages": _amount(summary.get("family_base")),
        "family_due": _amount(summary.get("family")),
        "family_allowances_paid": _amount(summary.get("allowance")),
        "total_due": _amount(summary.get("total")),
        "net_due": _amount(summary.get("net")),
    })

    payment = dict(payment_details or {})
    months = period_months(period_type, int(year or 0), int(index))
    paid_totals, payment_amount_complete = _aggregate_filed_months(
        filed_wages, months, ("amount_paid",)
    )
    saved_paid = _amount(paid_totals["amount_paid"]) if payment_amount_complete else ""
    values["amount_paid"] = _amount(payment.get("amount_paid")) or saved_paid
    values["payment_date"] = _date(payment.get("payment_date"))
    values["receipt_number"] = _value(payment, "reference")
    values["payment_method"] = _value(payment, "method")
    if not values["company_name"]:
        missing.append("Company name is missing in Company Settings.")
    if not values["company_nssf"]:
        missing.append("Employer NSSF number is missing in Company Settings.")
    missing.append("Review the form's preprinted NSSF rates, wage classification, and filing period with the applicable CNSS instructions.")
    if form.kind in ("period", "yearly"):
        if not values["amount_paid"]:
            missing.append("No complete saved amount-paid record for this period; payment fields remain blank.")
        if not values["receipt_number"]:
            missing.append("NSSF receipt/document number is not stored for this period.")
        if not values["payment_date"]:
            missing.append("Actual payment date is not stored for this period.")
        if not values["payment_method"]:
            missing.append("Payment method is not stored for this period.")
        missing.append("Employee counts and amounts paid by individual branch are not stored; those branch cells remain blank.")
    if int(report.get("record_count") or 0) == 0:
        missing.append("There is no posted payroll in this period; contribution totals may be zero.")

    if form.kind == "annual":
        annual_bases = _annual_report_bases(report)
        filed_by_month = {
            int(row.get("month", 0)): row
            for row in filed_wages
            if row.get("month") is not None
        }
        filed_totals = {"sickness_wages": 0.0, "family_wages": 0.0, "end_service_wages": 0.0}
        filed_complete = True
        for month in range(1, 13):
            saved = filed_by_month.get(month, {})
            for source_key, target_key in (
                ("sickness_wages", "sick"),
                ("family_wages", "family"),
                ("end_service_wages", "eos"),
            ):
                value = saved.get(source_key)
                if value is None or value == "":
                    filed_complete = False
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    filed_complete = False
                    continue
                values[f"month_{month:02d}_{target_key}"] = _amount(numeric)
                filed_totals[source_key] += numeric
            actual = annual_bases.get(month, {})
            for target_key in ("sick", "family", "eos"):
                values[f"month_{month:02d}_actual_{target_key}"] = _amount(actual.get(target_key))
        for source_key, target_key in (
            ("sickness_wages", "sick"),
            ("family_wages", "family"),
            ("end_service_wages", "eos"),
        ):
            actual_total = sum(row.get(target_key, 0.0) for row in annual_bases.values())
            values[f"actual_total_{target_key}"] = _amount(actual_total)
            values[f"filed_total_{target_key}"] = _amount(filed_totals[source_key]) if filed_complete else ""
            values[f"settlement_wage_{target_key}"] = (
                _amount(actual_total - filed_totals[source_key]) if filed_complete else ""
            )
        if not filed_complete:
            absent = [
                f"{month:02d}"
                for month in range(1, 13)
                if month not in filed_by_month
                or any(filed_by_month[month].get(k) in (None, "") for k in (
                    "sickness_wages", "family_wages", "end_service_wages"
                ))
            ]
            missing.append("Filed monthly wage bases are incomplete; CNSS 386 settlement fields are left blank for months: " + ", ".join(absent))
        if not annual_bases:
            missing.append("No annual posted-payroll wage detail is available.")
        settlement_rows = (
            (settlement_report or {}).get("sections") or []
        )
        settlement_rows = settlement_rows[2].get("rows", []) if len(settlement_rows) > 2 else []
        settlement_row = next(
            (
                row for row in settlement_rows
                if isinstance(row, (list, tuple))
                and row
                and "Wage-base settlement difference" in str(row[0])
            ),
            None,
        )
        if settlement_row and len(settlement_row) > 1 and settlement_row[1] not in (None, "", "INCOMPLETE"):
            values["settlement_total"] = _amount(settlement_row[1])
        else:
            values["settlement_total"] = ""
            missing.append("Filed wages or saved rate data are incomplete; the annual settlement contribution total remains blank.")
        schedule_employees, _schedule_totals = _annual_schedule_data(report)
        if schedule_employees:
            missing.append("The attached employee/month schedule is a payroll-derived draft, not an official CNSS form. Blank cells mean no employee/month detail was reported; verify it against filed records.")
        else:
            missing.append("No employee-level posted payroll rows are available; the wage schedule was not attached.")

    return values, missing


def _overlay_fields(form_key: str, values: Mapping[str, str]) -> list[Overlay]:
    """Coordinates are measured on the displayed page orientation in the supplied PDFs."""
    fields: list[Overlay] = []

    def add(page: int, key: str, rect: tuple[float, float, float, float], fontsize: float = 7.5, align: str = "right"):
        fields.append(Overlay(page, rect, key, fontsize, align))

    # Employee notices share a consistent employer/employee section.
    if form_key in ("cnss_termination_notice", "cnss_employee_use_notice"):
        add(0, "company_name", (195, 187, 548, 201), 7.0)
        add(0, "company_nssf", (346, 207, 548, 221), 7.0)
        add(0, "company_mof", (45, 225, 260, 239), 7.0)
        add(0, "company_address", (140, 241, 548, 255), 6.5)
        add(0, "company_phone", (355, 259, 548, 273), 7.0)
        add(0, "employee_name", (180, 280, 548, 294), 7.0)
        add(0, "employee_father", (320, 299, 548, 313), 7.0)
        add(0, "employee_mother", (320, 317, 548, 331), 7.0)
        add(0, "employee_nationality", (350, 335, 548, 349), 7.0)
        add(0, "employee_nssf", (365, 353, 548, 367), 7.0)
        add(0, "employee_national_id", (45, 353, 300, 367), 7.0, "left")
        add(0, "employee_birth_date", (405, 371, 548, 385), 7.0, "center")
        add(0, "employee_birth_place", (45, 371, 300, 385), 7.0)
        add(0, "employee_hire_date", (385, 389, 548, 403), 7.0, "center")
        if form_key == "cnss_termination_notice":
            add(0, "employee_leave_date", (385, 407, 548, 421), 7.0, "center")
        add(0, "employee_job", (240, 426, 548, 440), 7.0)
        add(0, "employee_salary", (390, 444, 548, 458), 7.0, "center")
        return fields

    if form_key == "cnss_r3_employee_registration":
        add(0, "company_name", (285, 127, 550, 142), 7.0)
        add(0, "company_nssf", (345, 149, 550, 164), 7.0)
        add(0, "company_mof", (40, 149, 260, 164), 7.0, "left")
        add(0, "company_address", (205, 186, 550, 201), 6.5)
        add(0, "company_phone", (365, 207, 550, 222), 7.0)
        add(0, "company_email", (210, 226, 550, 241), 6.5)
        add(0, "employee_name", (230, 276, 550, 291), 7.0)
        add(0, "employee_phone", (45, 298, 240, 313), 7.0, "left")
        add(0, "employee_count", (275, 442, 320, 457), 8.0, "center")
        return fields

    if form_key == "cnss_r3":
        add(0, "company_name", (190, 78, 550, 94), 7.0)
        add(0, "company_nssf", (355, 98, 550, 113), 7.0)
        add(0, "company_mof", (45, 98, 250, 113), 7.0, "left")
        add(0, "employee_name", (220, 151, 550, 166), 7.0)
        add(0, "employee_father", (220, 169, 550, 184), 7.0)
        add(0, "employee_mother", (220, 187, 550, 202), 7.0)
        add(0, "employee_nationality", (350, 205, 550, 220), 7.0)
        add(0, "employee_birth_date", (395, 223, 550, 238), 7.0, "center")
        add(0, "employee_birth_place", (45, 223, 300, 238), 7.0)
        add(0, "employee_national_id", (280, 241, 550, 256), 7.0)
        add(0, "employee_nssf", (365, 259, 550, 274), 7.0)
        add(0, "employee_address", (145, 277, 550, 292), 6.5)
        add(0, "employee_phone", (365, 295, 550, 310), 7.0)
        add(0, "employee_job", (260, 313, 550, 328), 7.0)
        add(0, "employee_hire_date", (405, 331, 550, 346), 7.0, "center")
        add(0, "employee_salary", (365, 349, 550, 364), 7.0, "center")
        return fields

    if form_key == "cnss_employment_declaration":
        add(0, "company_name", (190, 100, 550, 116), 7.0)
        add(0, "company_nssf", (355, 119, 550, 134), 7.0)
        add(0, "company_mof", (45, 119, 250, 134), 7.0, "left")
        add(0, "company_address", (175, 150, 550, 165), 6.5)
        add(0, "company_phone", (360, 169, 550, 184), 7.0)
        add(0, "employee_name", (205, 205, 550, 220), 7.0)
        add(0, "employee_national_id", (270, 225, 550, 240), 7.0)
        add(0, "employee_nssf", (370, 244, 550, 259), 7.0)
        add(0, "employee_birth_date", (405, 263, 550, 278), 7.0, "center")
        add(0, "employee_nationality", (345, 282, 550, 297), 7.0)
        add(0, "employee_job", (250, 301, 550, 316), 7.0)
        add(0, "employee_hire_date", (405, 320, 550, 335), 7.0, "center")
        add(0, "employee_salary", (390, 339, 550, 354), 7.0, "center")
        # Page two is the employee declaration/attachment; only the shared identity
        # and employer details are repeated where the supplied blank provides fields.
        add(1, "company_name", (185, 72, 550, 88), 7.0)
        add(1, "employee_name", (185, 98, 550, 114), 7.0)
        add(1, "employee_nssf", (375, 118, 550, 133), 7.0)
        add(1, "employee_hire_date", (395, 138, 550, 153), 7.0, "center")
        return fields

    if form_key in ("cnss_contributions_monthly_quarterly", "cnss_contributions_yearly"):
        yearly = form_key == "cnss_contributions_yearly"
        add(0, "company_name", (650, 84 if yearly else 90, 810, 100 if yearly else 106), 7.0)
        add(0, "company_nssf", (650, 111 if yearly else 123, 810, 127 if yearly else 139), 7.0)
        add(0, "period_label", (310, 34, 535, 50), 7.0, "center")
        rows = (
            ("sickness", 222 if not yearly else 225),
            ("eos", 310 if not yearly else 307),
            ("family", 396 if not yearly else 389),
        )
        for key, y in rows:
            add(0, f"{key}_employee_count", (742, y, 769, y + 16), 6.5, "center")
            add(0, f"{key}_wages", (632, y, 735, y + 16), 6.5, "center")
            add(0, f"{key}_due", (488, y, 577, y + 16), 6.5, "center")
            add(0, f"{key}_paid", (382, y, 468, y + 16), 6.5, "center")
        total_y = 485 if not yearly else 455
        add(0, "total_due", (488, total_y, 578, total_y + 16), 7.0, "center")
        add(0, "family_allowances_paid", (488, total_y + 29, 578, total_y + 45), 7.0, "center")
        add(0, "net_due", (488, total_y + 56, 578, total_y + 72), 7.0, "center")
        add(0, "amount_paid", (235, 526 if not yearly else 500, 325, 543 if not yearly else 517), 7.0, "center")
        add(0, "payment_method", (225, 130 if yearly else 133, 326, 146 if yearly else 149), 6.5, "center")
        add(0, "receipt_number", (378, 130 if yearly else 133, 455, 146 if yearly else 149), 6.0, "center")
        add(0, "payment_date", (460, 130 if yearly else 133, 555, 146 if yearly else 149), 6.0, "center")
        return fields

    if form_key == "cnss_annual_declaration":
        add(0, "company_nssf", (45, 31, 290, 49), 7.0, "center")
        add(0, "company_name", (45, 73, 290, 89), 7.0)
        add(0, "year", (455, 78, 535, 94), 8.0, "center")
        # Section A: the twelve monthly figures are the values actually recorded
        # as filed. Unknown months remain blank and are reported to the user.
        row_y = 232.0
        row_step = 15.0
        for month in range(1, 13):
            y = row_y + (month - 1) * row_step
            add(0, f"month_{month:02d}_eos", (251, y, 360, y + 12.5), 6.5, "center")
            add(0, f"month_{month:02d}_family", (146, y, 246, y + 12.5), 6.5, "center")
            add(0, f"month_{month:02d}_sick", (39, y, 141, y + 12.5), 6.5, "center")
        # The totals line of section A, then the annual settlement comparison.
        add(0, "filed_total_eos", (251, 436, 360, 449), 6.5, "center")
        add(0, "filed_total_family", (146, 436, 246, 449), 6.5, "center")
        add(0, "filed_total_sick", (39, 436, 141, 449), 6.5, "center")
        add(0, "actual_total_eos", (251, 505, 360, 519), 6.5, "center")
        add(0, "actual_total_family", (146, 505, 246, 519), 6.5, "center")
        add(0, "actual_total_sick", (39, 505, 141, 519), 6.5, "center")
        add(0, "filed_total_eos", (251, 548, 360, 562), 6.5, "center")
        add(0, "filed_total_family", (146, 548, 246, 562), 6.5, "center")
        add(0, "filed_total_sick", (39, 548, 141, 562), 6.5, "center")
        add(0, "settlement_wage_eos", (251, 591, 360, 605), 6.5, "center")
        add(0, "settlement_wage_family", (146, 591, 246, 605), 6.5, "center")
        add(0, "settlement_wage_sick", (39, 591, 141, 605), 6.5, "center")
        add(0, "settlement_total", (36, 649, 141, 664), 7.0, "center")
        return fields

    return fields


def _visible_rect(page: Any, rect: tuple[float, float, float, float]) -> Any:
    """Convert displayed-page coordinates to PyMuPDF's unrotated page coordinates."""
    fitz = _fitz()
    return fitz.Rect(rect) * page.derotation_matrix


def _fitz():
    try:
        import pymupdf
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "CNSS form preview needs PyMuPDF and its native runtime library."
        ) from exc
    return pymupdf


def _display_text(value: Any) -> str:
    text = str(value)
    if not any("\u0600" <= char <= "\u06ff" for char in text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except ImportError:
        return text


def _insert_schedule_text(
    page: Any,
    rect: Any,
    value: Any,
    font: Path,
    fontsize: float,
    align: int,
) -> None:
    raw_text = str(value)
    has_arabic = any("\u0600" <= char <= "\u06ff" for char in raw_text)
    text = _display_text(raw_text)
    font_sizes = [fontsize, fontsize - 0.5, fontsize - 1.0, 5.0, 4.5, 4.0]
    for size in font_sizes:
        kwargs = {
            "rect": rect,
            "buffer": text,
            "fontsize": max(4.0, size),
            "fontname": "Amiri" if font.is_file() and has_arabic else "helv",
            "align": align,
            "color": (0, 0, 0),
            "overlay": True,
        }
        if font.is_file() and has_arabic:
            kwargs["fontfile"] = str(font)
        if page.insert_textbox(**kwargs) >= 0:
            return
    raise ValueError(f"Employee wage schedule value does not fit its cell: {str(value)[:80]}")


def _append_annual_employee_schedule(
    document: Any,
    report: Mapping[str, Any] | None,
    values: Mapping[str, Any],
    font: Path,
) -> int:
    fitz = _fitz()
    employees_by_id, branch_totals = _annual_schedule_data(report)
    if not employees_by_id:
        return 0

    employees = sorted(
        employees_by_id.values(),
        key=lambda item: (item["number"] or item["name"]).casefold(),
    )
    branches = (
        ("sick", "Sickness and maternity wage base (LBP)"),
        ("family", "Family allowance wage base (LBP)"),
        ("eos", "End-of-service wage base (LBP)"),
    )
    month_labels = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    columns = (60.0, 130.0, *([42.0] * 12), 92.0)
    left = 28.0
    row_limit = 25
    pages_per_branch = (len(employees) + row_limit - 1) // row_limit
    total_pages = len(branches) * pages_per_branch
    page_number = 0

    for branch, branch_label in branches:
        for chunk_number in range(pages_per_branch):
            page_number += 1
            start = chunk_number * row_limit
            page_employees = employees[start:start + row_limit]
            page = document.new_page(width=842, height=595)
            _insert_schedule_text(
                page, fitz.Rect(28, 17, 814, 38),
                "CNSS 386 - Payroll-derived Employee Schedule (Draft)",
                font, 13.0, fitz.TEXT_ALIGN_LEFT,
            )
            _insert_schedule_text(
                page, fitz.Rect(28, 39, 814, 55),
                "جدول الأجور السنوي للأجراء",
                font, 9.0, fitz.TEXT_ALIGN_RIGHT,
            )
            for rect, label in (
                ((28, 59, 84, 73), "Employer:"),
                ((385, 59, 462, 73), "CNSS No.:"),
                ((548, 59, 590, 73), "Year:"),
                ((652, 59, 732, 73), "Schedule:"),
            ):
                _insert_schedule_text(
                    page, fitz.Rect(rect), label, font, 7.0, fitz.TEXT_ALIGN_LEFT,
                )
            for rect, value in (
                ((86, 59, 380, 73), values.get("company_name", "")),
                ((464, 59, 540, 73), values.get("company_nssf", "")),
                ((592, 59, 630, 73), values.get("year", "")),
                ((734, 59, 814, 73), f"{page_number} of {total_pages}"),
            ):
                _insert_schedule_text(
                    page, fitz.Rect(rect), value, font, 7.0, fitz.TEXT_ALIGN_RIGHT,
                )
            _insert_schedule_text(
                page, fitz.Rect(28, 78, 814, 95), branch_label,
                font, 9.0, fitz.TEXT_ALIGN_LEFT,
            )

            y = 101.0
            header_height = 23.0
            headers = ("Employee No.", "Employee Name", *month_labels, "Annual total")
            x = left
            for width, label in zip(columns, headers):
                rect = fitz.Rect(x, y, x + width, y + header_height)
                page.draw_rect(
                    rect, color=(0.55, 0.59, 0.64), fill=(0.91, 0.93, 0.95),
                    width=0.45, overlay=True,
                )
                _insert_schedule_text(
                    page, fitz.Rect(rect.x0 + 2, rect.y0 + 2, rect.x1 - 2, rect.y1 - 2),
                    label, font, 6.5,
                    fitz.TEXT_ALIGN_CENTER,
                )
                x += width

            y += header_height
            row_height = 16.0

            def draw_row(cells: Sequence[Any], fill: tuple[float, float, float] | None = None):
                nonlocal y
                x = left
                for width, text in zip(columns, cells):
                    rect = fitz.Rect(x, y, x + width, y + row_height)
                    page.draw_rect(
                        rect, color=(0.70, 0.72, 0.75), fill=fill,
                        width=0.35, overlay=True,
                    )
                    _insert_schedule_text(
                        page, fitz.Rect(rect.x0 + 2, rect.y0 + 1, rect.x1 - 2, rect.y1 - 1),
                        text, font, 6.2,
                        fitz.TEXT_ALIGN_RIGHT if width == 130.0 else fitz.TEXT_ALIGN_CENTER,
                    )
                    x += width
                y += row_height

            for employee in page_employees:
                month_values = employee["months"]
                numeric_values = [
                    month_values[month][branch]
                    for month in range(1, 13)
                    if branch in month_values.get(month, {})
                ]
                cells = [
                    employee["number"],
                    employee["name"],
                    *[
                        _amount(month_values.get(month, {}).get(branch))
                        if branch in month_values.get(month, {}) else ""
                        for month in range(1, 13)
                    ],
                    _amount(sum(numeric_values)) if numeric_values else "",
                ]
                draw_row(cells)

            if chunk_number == pages_per_branch - 1:
                monthly_values = [
                    _amount(branch_totals[branch][month])
                    if month in branch_totals[branch] else ""
                    for month in range(1, 13)
                ]
                reported_total = sum(branch_totals[branch].values())
                draw_row(
                    ["TOTAL", "Reported payroll base", *monthly_values, _amount(reported_total)],
                    fill=(0.95, 0.95, 0.92),
                )

            note = (
                "Draft attachment, not an official CNSS form. Blank monthly cells mean no employee/month "
                "detail was present in the posted-payroll report. Verify against CNSS filed records."
            )
            _insert_schedule_text(
                page, fitz.Rect(28, 548, 814, 568), note,
                font, 6.4, fitz.TEXT_ALIGN_LEFT,
            )

    return total_pages


def filled_pdf_bytes(
    form_key: str,
    values: Mapping[str, Any],
    root: Path | None = None,
    *,
    annual_schedule_report: Mapping[str, Any] | None = None,
) -> bytes:
    """Return a filled copy in memory; the supplied blank template is never changed."""
    fitz = _fitz()
    source = template_path(form_key, root)
    font = (root or app_root()) / "Assets" / "fonts" / "Amiri-Regular.ttf"
    document = fitz.open(source)
    try:
        for field in _overlay_fields(form_key, values):
            text = values.get(field.key)
            if text is None or str(text).strip() == "":
                continue
            if field.page >= len(document):
                raise ValueError(f"Form mapping refers to missing page {field.page + 1}.")
            page = document[field.page]
            rect = _visible_rect(page, field.rect)
            if rect.is_empty or not page.rect.contains(fitz.Rect(field.rect)):
                raise ValueError(f"Form field '{field.key}' is outside the supplied template.")
            display = _display_text(text)
            inserted = False
            for font_size in (
                field.fontsize,
                field.fontsize - 0.5,
                field.fontsize - 1.0,
                5.0,
                4.5,
                4.0,
                3.5,
            ):
                kwargs = {
                    "rect": rect,
                    "buffer": display,
                    "fontsize": max(5.0, font_size),
                    "fontname": "Amiri" if font.is_file() else "helv",
                    "align": {
                        "left": fitz.TEXT_ALIGN_LEFT,
                        "center": fitz.TEXT_ALIGN_CENTER,
                        "right": fitz.TEXT_ALIGN_RIGHT,
                    }[field.align],
                    "color": (0, 0, 0),
                    "overlay": True,
                }
                if font.is_file():
                    kwargs["fontfile"] = str(font)
                remaining = page.insert_textbox(**kwargs)
                if remaining >= 0:
                    inserted = True
                    break
            if not inserted:
                raise ValueError(
                    f"Value for '{field.key}' is too long for its field on page {field.page + 1}."
                )
        if form_key == "cnss_annual_declaration" and annual_schedule_report:
            _append_annual_employee_schedule(document, annual_schedule_report, values, font)
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()
