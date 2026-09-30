"""PDF invoices in different layouts are read correctly (number, date, currency, HT, VAT, TTC, supplier)."""
import shutil
import tempfile
import unittest
from pathlib import Path

import pdf_import


def _make_pdfs(folder):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import arabic_reshaper
    from bidi.algorithm import get_display
    font = Path(__file__).resolve().parent / "Assets" / "fonts" / "Amiri-Regular.ttf"
    pdfmetrics.registerFont(TTFont("AmiriTest", str(font)))
    def simple(name, lines):
        c = canvas.Canvas(str(folder / name)); y = 800
        for line in lines: c.setFont("Helvetica", 10); c.drawString(50, y, line); y -= 18
        c.save()
    simple("en.pdf", ["ALPHA TRADING SARL", "Beirut - Lebanon  VAT No 123456", "TAX INVOICE", "Invoice No: INV-2026-0457", "Date: 15/03/2026", "Bill to: ECOLOGE LEBANON SARL",
                      "Item  Description          Qty  Unit Price   Amount", "HPL-8  HPL Panel 8mm         10   120.00   1,200.00", "ALU-1  Aluminium profile     20    15.00     300.00",
                      "Subtotal: 1,500.00 USD", "VAT 11%: 165.00", "Grand Total: 1,665.00 USD"])
    simple("fr.pdf", ["SOCIETE BETA SAL", "FACTURE N° F-2026/118", "Date : 02/04/2026", "Client : ECOLOGE LEBANON SARL", "Designation            Qte   P.U.     Montant",
                      "Colle speciale          5    40,00    200,00", "Total HT : 200,00 EUR", "TVA 11% : 22,00 EUR", "Total TTC : 222,00 EUR"])
    simple("lbp.pdf", ["GAMMA STATIONERY", "Invoice # 7781", "Date: 20-05-2026", "Office supplies", "Total before VAT: 4,500,000 L.L.", "VAT 11%: 495,000 L.L.", "Total: 4,995,000 L.L."])
    c = canvas.Canvas(str(folder / "ar.pdf")); y = 800
    for label, value in (("شركة دلتا للتجارة ش.م.م", ""), ("فاتورة رقم", "5521"), ("التاريخ", "10/06/2026"), ("المجموع قبل الضريبة", "800.00 USD"),
                         ("الضريبة على القيمة المضافة", "88.00"), ("المجموع", "888.00 USD")):
        c.setFont("AmiriTest", 11); c.drawRightString(550, y, get_display(arabic_reshaper.reshape(label)))
        if value: c.setFont("Helvetica", 10); c.drawString(300, y, value)
        y -= 20
    c.save()


class PdfFormatsTest(unittest.TestCase):
    EXPECTED = {"en.pdf": ("INV-2026-0457", "15-03-2026", "USD", 1500, 165, 1665, "ALPHA TRADING SARL"),
                "fr.pdf": ("F-2026/118", "02-04-2026", "EUR", 200, 22, 222, "SOCIETE BETA SAL"),
                "lbp.pdf": ("7781", "20-05-2026", "LBP", 4500000, 495000, 4995000, "GAMMA STATIONERY"),
                "ar.pdf": ("5521", "10-06-2026", "USD", 800, 88, 888, "شركة دلتا للتجارة ش.م.م")}

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp()); _make_pdfs(cls.folder)

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.folder, ignore_errors=True)

    def test_layouts(self):
        for name, (number, day, currency, ht, vat, ttc, party) in self.EXPECTED.items():
            with self.subTest(name):
                result = pdf_import.read_invoice_pdf(self.folder / name)
                self.assertEqual((result["invoice_number"], result["invoice_date"], result["currency"], result["party_name"]), (number, day, currency, party))
                self.assertEqual([round(float(result[k]), 2) for k in ("subtotal", "vat", "total")], [ht, vat, ttc])
        self.assertEqual(len(pdf_import.read_invoice_pdf(self.folder / "en.pdf")["items"]), 2)

    def test_normalization(self):
        self.assertEqual(pdf_import.normalize_invoice_text("Total HT : 1.234,56 EUR"), "Total HT : 1,234.56 EUR")
        self.assertEqual(pdf_import.normalize_invoice_text("ﺍﻟﻤﺠﻤﻮﻉ"), "المجموع")  # presentation forms -> normal letters
        self.assertEqual(pdf_import.normalize_invoice_text("المجموع\n888.00 USD"), "المجموع : 888.00 USD")


if __name__ == "__main__":
    unittest.main()
