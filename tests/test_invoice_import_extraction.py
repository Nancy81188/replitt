import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from importer import read_expenses, read_invoices
from pdf_import import _parse_invoice_text


class InvoiceExtractionTests(unittest.TestCase):
    def test_pdf_does_not_invent_vat(self):
        parsed = _parse_invoice_text("example.pdf", "Acme Supplies\nInvoice No: 123\nDate: 20/09/2026\nSubtotal 100.00\nTotal TTC 100.00\n")
        self.assertIsNone(parsed["vat"])
        self.assertEqual(parsed["total"], 100.0)

    def test_pdf_reads_split_and_item(self):
        parsed = _parse_invoice_text("example.pdf", "Acme Supplies\nInvoice No: 123\nDate: 20/09/2026\nWidget  2  10.00  20.00\nDeductible amount 15.00\nNon deductible amount 5.00\nSubtotal 20.00\nVAT 2.20\nTotal TTC 22.20\n")
        self.assertEqual(parsed["deductible"], 15.0)
        self.assertEqual(parsed["non_deductible"], 5.0)
        self.assertEqual(parsed["items"][0]["description"], "Widget")

    def test_excel_expense_uses_explicit_ttc(self):
        from openpyxl import Workbook
        with TemporaryDirectory() as directory:
            path = Path(directory) / "expenses.xlsx"
            book = Workbook()
            book.active.append(["Date", "Description", "Supplier", "Amount", "Without VAT", "TTC", "Items"])
            book.active.append(["20-09-2026", "Stationery", "Acme", 100, 20, 120, "Paper"])
            book.save(path)
            row = read_expenses(path)[0]
            self.assertEqual(row["vat"], 0)
            self.assertEqual(row["supplier"], "Acme")
            self.assertEqual(row["items"], "Paper")


if __name__ == "__main__":
    unittest.main()
