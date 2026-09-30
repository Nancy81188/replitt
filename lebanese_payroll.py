"""Lebanese payroll rules (salary tax, exemptions, NSSF) as effective-dated periods.

Sources checked September 2026: Budget Law 324/2024 (brackets art. 48, family deductions art. 49),
Decree 12966/2024 (transport LBP 450,000/day private sector), MoF decision 1195 (tax rounded up to
LBP 10,000 from 25-11-2024), NSSF memos (sickness & maternity ceiling 45M -> 90M from April 2024 ->
120M from August 2025; family allowance ceiling 12M -> 18M from July 2025 -> 28M from May 2026,
Decree 2923 / Memo 831 with allowances of 2,100,000 spouse and 1,155,000 per child, cap 7,875,000).
Every value stays editable in Tax & NSSF Settings; confirm with your accountant before filing."""
from __future__ import annotations

BRACKETS_2024 = [[360000000, .02], [900000000, .04], [1800000000, .07], [3600000000, .11], [7200000000, .15], [13500000000, .20], [None, .25]]

BASE = {"tax_brackets": BRACKETS_2024, "single_allowance": "450000000", "spouse_allowance": "225000000", "child_allowance": "45000000", "max_children_deduction": "5",
        "employee_nssf_rate": "0.03", "medical_rate": "0.08", "family_rate": "0.06", "end_service_rate": "0.085", "end_service_ceiling": "0",
        "transport_daily_exempt": "450000", "default_transport_days": "26", "schooling_annual_exempt": "6000000", "schooling_max_children": "3",
        "tax_rounding": "0", "minimum_wage": "18000000", "family_allowance_spouse": "0", "family_allowance_child": "0", "family_allowance_cap": "0", "family_allowance_max_children": "5"}

# (date_from, changes compared with the previous period)
PERIODS = [
    ("2024-01-01", {"employee_ceiling": "45000000", "medical_ceiling": "45000000", "family_ceiling": "12000000", "minimum_wage": "9000000"}),
    ("2024-04-01", {"employee_ceiling": "90000000", "medical_ceiling": "90000000", "minimum_wage": "18000000"}),
    ("2024-11-25", {"tax_rounding": "10000"}),
    ("2025-07-01", {"family_ceiling": "18000000", "minimum_wage": "28000000"}),
    ("2025-08-01", {"employee_ceiling": "120000000", "medical_ceiling": "120000000"}),
    ("2026-05-01", {"family_ceiling": "28000000", "family_allowance_spouse": "2100000", "family_allowance_child": "1155000", "family_allowance_cap": "7875000"}),
]


def official_periods():
    values = dict(BASE); result = []
    for index, (date_from, changes) in enumerate(PERIODS):
        values.update(changes)
        date_to = None
        if index + 1 < len(PERIODS):
            from datetime import datetime, timedelta
            date_to = (datetime.strptime(PERIODS[index + 1][0], "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        result.append({**values, "date_from": date_from, "date_to": date_to})
    return result
