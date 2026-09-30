import hashlib
import unittest

import pymupdf

from cnss_forms import (
    FORMS,
    _overlay_fields,
    build_form_values,
    filled_pdf_bytes,
    template_path,
)


COMPANY = {
    "company_name": "Test Company",
    "company_nssf": "123456",
    "company_mof": "987654",
    "company_address": "Beirut",
    "company_phone": "01-123456",
}


def sample_report():
    return {
        "period_label": "September 2026",
        "record_count": 1,
        "employee_count": 1,
        "payroll_employee_count": 1,
        "summary": {
            "sick_base": 20000000,
            "employee": 1700000,
            "employer_sick": 1800000,
            "eos_base": 20000000,
            "eos": 1200000,
            "family_base": 20000000,
            "family": 900000,
            "allowance": 300000,
            "total": 5600000,
            "net": 5300000,
        },
        "sections": [{
            "rows": [[
                "123456", "Test Employee", "09-2026", 20000000, 20000000, 1700000,
                1800000, 20000000, 900000, 20000000, 1200000, 5600000, 300000, 5300000,
            ]]
        }],
    }


class CNSSFormsTests(unittest.TestCase):
    def test_all_eight_supplied_templates_are_packaged_pdfs(self):
        self.assertEqual(len(FORMS), 8)
        for form in FORMS:
            with self.subTest(form=form.key):
                path = template_path(form.key)
                self.assertTrue(path.is_file())
                self.assertTrue(path.read_bytes().startswith(b"%PDF"))

    def test_missing_payment_receipt_data_stays_blank(self):
        values, missing = build_form_values(
            "cnss_contributions_monthly_quarterly",
            COMPANY,
            report=sample_report(),
            filed_wages=[{
                "year": 2026, "month": 9, "sickness_wages": 20_000_000,
                "family_wages": 20_000_000, "end_service_wages": 20_000_000,
                "amount_paid": None,
            }],
            year=2026,
            period_type="monthly",
            index=9,
        )
        self.assertEqual(values["amount_paid"], "")
        self.assertEqual(values["payment_date"], "")
        self.assertEqual(values["receipt_number"], "")
        self.assertEqual(values["sickness_due"], "3,500,000")
        self.assertTrue(any("amount-paid record" in item for item in missing))
        self.assertTrue(any("rates" in item for item in missing))

    def test_annual_form_leaves_unknown_filed_months_blank(self):
        values, missing = build_form_values(
            "cnss_annual_declaration",
            COMPANY,
            report=sample_report(),
            filed_wages=[],
            year=2026,
            period_type="yearly",
        )
        self.assertEqual(values.get("month_01_sick", ""), "")
        self.assertEqual(values.get("filed_total_sick", ""), "")
        self.assertTrue(any("incomplete" in item for item in missing))

    def test_annual_settlement_total_uses_the_saved_rate_review(self):
        filed = [{
            "year": 2026, "month": month,
            "sickness_wages": 20_000_000,
            "family_wages": 20_000_000,
            "end_service_wages": 20_000_000,
            "amount_paid": 5_300_000,
        } for month in range(1, 13)]
        settlement = {
            "sections": [{}, {}, {"rows": [[
                "Wage-base settlement difference at each month's saved rates", 1250000,
            ]]}],
        }
        values, _missing = build_form_values(
            "cnss_annual_declaration",
            COMPANY,
            report=sample_report(),
            filed_wages=filed,
            year=2026,
            period_type="yearly",
            settlement_report=settlement,
        )
        self.assertEqual(values["settlement_total"], "1,250,000")
        self.assertEqual(values["filed_total_sick"], "240,000,000")

    def test_annual_employee_schedule_is_appended_for_all_three_branches(self):
        source = template_path("cnss_annual_declaration")
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        values = {
            field.key: "123"
            for field in _overlay_fields("cnss_annual_declaration", {})
        }
        report = sample_report()
        annual_row = report["sections"][0]["rows"][0]
        report["sections"][0]["rows"] = [
            [annual_row[0], annual_row[1], f"{month:02d}-2026", *annual_row[3:]]
            for month in range(1, 13)
        ]
        result = filled_pdf_bytes(
            "cnss_annual_declaration",
            values,
            annual_schedule_report=report,
        )
        output = pymupdf.open(stream=result, filetype="pdf")
        original = pymupdf.open(source)
        try:
            self.assertEqual(len(output), len(original) + 3)
            schedule_text = "\n".join(page.get_text() for page in output[len(original):])
            self.assertIn("Employee Schedule", schedule_text)
            self.assertIn("Test Employee", schedule_text)
            self.assertIn("Sickness and maternity wage base", schedule_text)
            self.assertIn("Family allowance wage base", schedule_text)
            self.assertIn("End-of-service wage base", schedule_text)
            self.assertIn("240,000,000", schedule_text)
        finally:
            output.close()
            original.close()
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)

    def test_annual_employee_schedule_keeps_employees_after_page_breaks(self):
        rows = [
            [
                f"{number:04d}", f"Employee {number}", "06-2026",
                10_000_000, 10_000_000, 800_000, 900_000,
                10_000_000, 500_000, 10_000_000, 600_000, 2_800_000,
                200_000, 2_600_000,
            ]
            for number in range(1, 27)
        ]
        report = {"sections": [{"rows": rows}]}
        values = {
            field.key: "123"
            for field in _overlay_fields("cnss_annual_declaration", {})
        }
        result = filled_pdf_bytes(
            "cnss_annual_declaration",
            values,
            annual_schedule_report=report,
        )
        output = pymupdf.open(stream=result, filetype="pdf")
        try:
            self.assertEqual(len(output), 1 + 6)
            schedule_text = "\n".join(page.get_text() for page in output[1:])
            self.assertIn("Employee 25", schedule_text)
            self.assertIn("Employee 26", schedule_text)
        finally:
            output.close()

    def test_filled_copies_preserve_templates_and_include_overlay_text(self):
        for form in FORMS:
            with self.subTest(form=form.key):
                source = template_path(form.key)
                before = hashlib.sha256(source.read_bytes()).hexdigest()
                values = {field.key: "123" for field in _overlay_fields(form.key, {})}
                result = filled_pdf_bytes(form.key, values)
                output = pymupdf.open(stream=result, filetype="pdf")
                original = pymupdf.open(source)
                try:
                    self.assertEqual(len(output), len(original))
                    self.assertTrue(any("123" in page.get_text() for page in output))
                finally:
                    output.close()
                    original.close()
                after = hashlib.sha256(source.read_bytes()).hexdigest()
                self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()