"""Local assistance uses no API key or external request."""
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_service import read_invoice_pdf, suggest_account


class LocalAiTests(unittest.TestCase):
    def test_account_match_without_key(self):
        result=suggest_account("Office supplies", ["601100000 - Office supplies"])
        self.assertEqual(result["code"],"601100000")

    def test_text_pdf_without_key(self):
        from reportlab.pdfgen import canvas
        with TemporaryDirectory() as folder:
            path=Path(folder)/"invoice.pdf"
            paper=canvas.Canvas(str(path))
            for index,line in enumerate(("Acme Supplies","Invoice No: INV-42","Date: 20-09-2026",
                "Widget  2  10.00  20.00","Subtotal 20.00","VAT 2.20","Total TTC 22.20")):
                paper.drawString(40,750-index*25,line)
            paper.save()
            with patch("urllib.request.urlopen",side_effect=AssertionError("Cloud call")):
                result=read_invoice_pdf(path)
            self.assertEqual(result["invoice_number"],"INV-42")
            self.assertEqual(result["total"],22.2)
            self.assertEqual(result["items"][0]["description"],"Widget")


if __name__=="__main__":
    unittest.main()
