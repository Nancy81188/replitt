"""Local OCR is opt-in by runtime availability and never posts extracted data."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop_stage3 import Stage3Mixin
from desktop_v22 import V22Mixin
from chart_extra import EXPENSE_VAT, PURCHASE_VAT, SALES_VAT
from pdf_import import _ocr_pdf_pages, _parse_invoice_text, read_invoice_pdf, read_invoice_pdf_pages, suggest_invoice_type


class OcrPageTests(unittest.TestCase):
    def test_ocr_uses_selected_pages_and_both_installed_languages(self):
        class FakeImage:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        class FakeBitmap:
            def __init__(self):
                self.image = FakeImage()

            def to_pil(self):
                return self.image

            def close(self):
                pass

        class FakePage:
            def __init__(self):
                self.bitmap = FakeBitmap()
                self.render_calls = []
                self.closed = False

            def render(self, **kwargs):
                self.render_calls.append(kwargs)
                return self.bitmap

            def close(self):
                self.closed = True

        class FakeDocument:
            def __init__(self):
                self.pages = [FakePage(), FakePage()]
                self.closed = False

            def __len__(self):
                return len(self.pages)

            def __getitem__(self, index):
                return self.pages[index]

            def close(self):
                self.closed = True

        document = FakeDocument()
        alternate_text = "Invoice No: 25\nDate: 15/03/2026\nTotal USD 100.00"
        image_to_string = Mock(side_effect=["فاتورة Invoice No 25", alternate_text])
        pytess = types.SimpleNamespace(tesseract_cmd="")
        pypdfium = types.ModuleType("pypdfium2")
        pypdfium.PdfDocument = Mock(return_value=document)
        pytesseract = types.ModuleType("pytesseract")
        pytesseract.pytesseract = pytess
        pytesseract.get_languages = Mock(return_value=["eng", "ara"])
        pytesseract.image_to_string = image_to_string

        with patch.dict(sys.modules, {"pypdfium2": pypdfium, "pytesseract": pytesseract}):
            result = _ocr_pdf_pages("scanned.pdf", [1])

        self.assertEqual(result, [alternate_text])
        self.assertEqual(document.pages[0].render_calls, [])
        self.assertEqual(document.pages[1].render_calls, [{"scale": 2.0}])
        self.assertEqual(image_to_string.call_args_list[0].kwargs["lang"], "eng+ara")
        self.assertEqual(image_to_string.call_args_list[0].kwargs["config"], "--psm 6")
        self.assertEqual(image_to_string.call_args_list[1].kwargs["lang"], "eng")
        self.assertEqual(image_to_string.call_args_list[1].kwargs["config"], "--psm 4")
        self.assertEqual(image_to_string.call_count, 2)
        self.assertTrue(document.pages[1].bitmap.image.closed)
        self.assertTrue(document.closed)

    def test_scanned_pdf_ocr_result_is_a_review_suggestion(self):
        extracted = ("Invoice No: 45\nDate: 15/03/2026\nSupplier Co\n"
                     "Subtotal: 100.00\nVAT: 11.00\nGrand Total: 111.00")
        with patch("pdf_import.pdf_text", return_value=""), patch(
                "pdf_import._ocr_pdf", return_value=extracted) as ocr:
            result = read_invoice_pdf("scan.pdf")

        ocr.assert_called_once()
        self.assertEqual(result["invoice_number"], "45")
        self.assertEqual(result["invoice_date"], "15-03-2026")
        self.assertEqual(result["total"], 111.0)
        self.assertTrue(result["ocr_used"])
        self.assertIn("please check", result["notes"])

    def test_incomplete_nonempty_text_layer_falls_back_to_ocr(self):
        text_layer = "Supplier Company address and registration information, but no invoice fields."
        extracted = ("Invoice No: INV-45\nDate: 15/03/2026\nSupplier Co\n"
                     "Subtotal: 100.00\nVAT: 11.00\nGrand Total: 111.00")
        with patch("pdf_import.pdf_text", return_value=text_layer), patch(
                "pdf_import._ocr_pdf", return_value=extracted) as ocr:
            result = read_invoice_pdf("weak-text-layer.pdf")

        ocr.assert_called_once()
        self.assertEqual((result["invoice_number"], result["invoice_date"], result["total"]),
                         ("INV-45", "15-03-2026", 111.0))
        self.assertTrue(result["ocr_used"])
        self.assertIn("Local English/Arabic OCR suggestion", result["notes"])

    def test_arabic_scanned_invoice_amounts_are_review_suggestions(self):
        extracted = ("فاتورة رقم: 45\nالتاريخ: 15/03/2026\nشركة المورد\n"
                     "المجموع الفرعي: ١٠٠٫٠٠\nضريبة القيمة المضافة: ١١٫٠٠\n"
                     "المجموع الكلي: ١١١٫٠٠")
        with patch("pdf_import.pdf_text", return_value=""), patch(
                "pdf_import._ocr_pdf", return_value=extracted):
            result = read_invoice_pdf("arabic-scan.pdf")

        self.assertEqual(result["invoice_number"], "45")
        self.assertEqual(result["invoice_date"], "15-03-2026")
        self.assertEqual((result["subtotal"], result["vat"], result["total"]), (100.0, 11.0, 111.0))
        self.assertTrue(result["ocr_used"])
        self.assertIn("Local English/Arabic OCR suggestion - please check", result["notes"])

        # Reading a PDF only returns a preview; even a complete OCR row cannot post itself.
        client = types.SimpleNamespace(import_invoices=Mock())
        screen = types.SimpleNamespace(
            import_sheet=types.SimpleNamespace(ordered=lambda: [row]),
            import_type=types.SimpleNamespace(get=lambda: "Purchases"),
            import_mode="pdf", client=client,
        )
        row = {**result, "line": "1", "party_name": "شركة المورد", "currency": "LBP"}
        client.import_invoices.assert_not_called()
        # Missing values cannot be filled from the other two amounts during import.
        row["vat"] = None
        with patch("desktop_stage3.messagebox.showwarning") as warning:
            Stage3Mixin.send_import(screen)
        self.assertIn("type 0 if none", warning.call_args.args[1])
        client.import_invoices.assert_not_called()

    def test_invoice_number_labels_and_arabic_digits_from_pdf_text(self):
        for header, expected in (
            ("رقم الفاتورة: ١٢٣", "123"),
            ("فاتورة رقم: ٤٥٦", "456"),
            ("N° Facture: F-2026/007", "F-2026/007"),
            ("Invoice No: INV-2026-31", "INV-2026-31"),
        ):
            with self.subTest(header=header):
                text = f"{header}\nDate: 15/03/2026\nSupplier Co\nTotal: 100"
                self.assertEqual(_parse_invoice_text("invoice.pdf", text)["invoice_number"], expected)

    def test_invoice_number_before_label_in_reordered_pdf_text(self):
        text = "734 Jul 8, 2026 Jul 8, 2026INVOICE NO.: ISSUE DATE: DUE DATE:"

        self.assertEqual(
            _parse_invoice_text("reordered-header.pdf", text)["invoice_number"], "734"
        )

    def test_bcc_invoice_fields_with_month_date_and_lbp_vat_conversion(self):
        text = (
            "Invoice will be considered approved after review.\n"
            "Invoice: BC-2026-17\nDate: 12 Mar 2026\n"
            "Sub Total: 200.00\n"
            "VAT: 10.00 LBP: 900,000.00\n"
            "The Sum of USD Two Hundred Ten USD And Zero /100 USD 210.00"
        )

        parsed = _parse_invoice_text("bcc-invoice.pdf", text)

        self.assertEqual(parsed["invoice_number"], "BC-2026-17")
        self.assertEqual(parsed["invoice_date"], "12-03-2026")
        self.assertEqual(parsed["currency"], "USD")
        self.assertEqual((parsed["subtotal"], parsed["vat"], parsed["total"]),
                         (200.0, 10.0, 210.0))

    def test_invoice_currency_and_vat_ignore_lbp_translation_line(self):
        text = (
            "Invoice No: INV-43\nDate: 22 Jan 2026\n"
            "Total Before VAT USD 1,000.00\n"
            "110.00USDVAT 11%VAT LBP: 9,900,000\n"
            "Total USD 1,110.00"
        )

        parsed = _parse_invoice_text("mixed-currency.pdf", text)

        self.assertEqual(parsed["invoice_date"], "22-01-2026")
        self.assertEqual(parsed["currency"], "USD")
        self.assertEqual((parsed["subtotal"], parsed["vat"], parsed["total"]),
                         (1000.0, 110.0, 1110.0))

    def test_reference_date_and_tax_summary_survive_scan_format(self):
        text = (
            "Ref NB# ECO-22-24\nDate: 26-Jun-24\n"
            "Total $ 25,120.00\nVAT 11% $ 2,763.20\n"
            "Grand Total $ 27,883.20\n"
            "Bank Account Currency: LBP"
        )

        parsed = _parse_invoice_text("variation-order.pdf", text)

        self.assertEqual(parsed["invoice_number"], "ECO-22-24")
        self.assertEqual(parsed["invoice_date"], "26-06-2024")
        self.assertEqual(parsed["currency"], "USD")
        self.assertEqual((parsed["subtotal"], parsed["vat"], parsed["total"]),
                         (25120.0, 2763.2, 27883.2))
        self.assertIn("document reference suggested", parsed["notes"].casefold())

    def test_unlabelled_total_is_not_subtotal_without_vat_grand_total_sequence(self):
        text = "Invoice No: INV-44\nDate: 27/06/2024\nTotal: 100.00\nGrand Total: 111.00"

        parsed = _parse_invoice_text("invoice.pdf", text)

        self.assertIsNone(parsed["subtotal"])

    def test_arabic_amount_label_variants_and_rtl_number_first_rows(self):
        text = ("فاتورة رقم 45\nالتاريخ 15/03/2026\n"
                "١٬٢٠٠٫٥٠ : الإجمالي قبل الضريبة\n"
                "١٣٢٫٠٥ : الضريبة على القيمة المضافة\n"
                "١٬٣٣٢٫٥٥ : إجمالي الفاتورة")
        parsed = _parse_invoice_text("arabic.pdf", text)
        self.assertEqual((parsed["subtotal"], parsed["vat"], parsed["total"]),
                         (1200.5, 132.05, 1332.55))
        self.assertEqual(_parse_invoice_text(
            "arabic.pdf", text.replace("إجمالي الفاتورة", "المبلغ المستحق"))["total"], 1332.55)

    def test_arabic_item_rows_with_arabic_digits_are_parsed(self):
        text = ("فاتورة رقم 45\nالتاريخ 15/03/2026\n"
                "قهوة عربية ٢ ١٠٠٫٠٠ ٢٠٠٫٠٠")

        parsed = _parse_invoice_text("arabic.pdf", text)

        self.assertEqual(parsed["items"], [{
            "description": "قهوة عربية",
            "quantity": 2.0,
            "unit_price": 100.0,
            "total": 200.0,
            "unit": "unit",
        }])

    def test_arabic_missing_amounts_and_tax_rate_are_not_inferred(self):
        header = "فاتورة رقم 45\nالتاريخ 15/03/2026\n"
        subtotal_vat = _parse_invoice_text(
            "arabic.pdf", header + "المجموع الفرعي: 100\nضريبة القيمة المضافة: 11")
        subtotal_total = _parse_invoice_text(
            "arabic.pdf", header + "المجموع الفرعي: 100\nضريبة القيمة المضافة ١١٪\nالإجمالي: 111")
        subtotal_total_no_vat = _parse_invoice_text(
            "arabic.pdf", header + "المجموع الفرعي: 100\nالإجمالي: 111")
        self.assertIsNone(subtotal_vat["total"])
        self.assertEqual((subtotal_vat["subtotal"], subtotal_vat["vat"]), (100.0, 11.0))
        self.assertIsNone(subtotal_total["vat"])
        self.assertIsNone(subtotal_total_no_vat["vat"])
        self.assertIn("VAT amount not found", subtotal_total["notes"])
        self.assertEqual(subtotal_total["total"], 111.0)
        self.assertEqual(_parse_invoice_text(
            "arabic.pdf", header + "المجموع قبل الضريبة: 100\nقيمة الضريبة: 11")["total"], None)
        self.assertIsNone(_parse_invoice_text(
            "arabic.pdf", header + "الإجمالي الخاضع للضريبة: 100\nقيمة الضريبة: 11")["total"])
        self.assertIsNone(_parse_invoice_text(
            "arabic.pdf", header + "رقم التسجيل الضريبة: 123456\nالمجموع الفرعي: 100\nالإجمالي: 111")["vat"])

    def test_arabic_ocr_inconsistent_amounts_clear_vat_suggestion(self):
        extracted = ("فاتورة رقم 45\nالتاريخ 15/03/2026\n"
                     "المجموع الفرعي: 100\nضريبة القيمة المضافة: 12\nالمجموع الكلي: 111")
        with patch("pdf_import.pdf_text", return_value=""), patch(
                "pdf_import._ocr_pdf", return_value=extracted):
            result = read_invoice_pdf("arabic-scan.pdf")
        self.assertEqual((result["subtotal"], result["total"]), (100.0, 111.0))
        self.assertIsNone(result["vat"])
        self.assertIn("suggestion cleared", result["notes"])

    def test_multi_page_reader_ocr_marks_suggested_text(self):
        fake_pypdf = types.ModuleType("pypdf")

        class BlankPage:
            def extract_text(self):
                return ""

        fake_pypdf.PdfReader = lambda _path: types.SimpleNamespace(pages=[BlankPage()])
        text = "Invoice No: 45\nDate: 15/03/2026\nSupplier Co\nSubtotal: 100.00\nGrand Total: 100.00"
        with patch.dict(sys.modules, {"pypdf": fake_pypdf}), patch(
                "pdf_import._ocr_pdf_pages", return_value=[text]):
            results = read_invoice_pdf_pages(Path("scan.pdf"))

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ocr_used"])
        self.assertIn("Local OCR suggestion", results[0]["notes"])

    def test_multi_page_reader_ocr_retries_nonempty_but_incomplete_text(self):
        fake_pypdf = types.ModuleType("pypdf")

        class WeakTextPage:
            def extract_text(self):
                return "Supplier address and document footer with no recognized invoice fields."

        fake_pypdf.PdfReader = lambda _path: types.SimpleNamespace(pages=[WeakTextPage()])
        extracted = ("Invoice No: 46\nDate: 16/03/2026\nSupplier Co\n"
                     "Subtotal: 200.00\nVAT: 22.00\nGrand Total: 222.00")
        with patch.dict(sys.modules, {"pypdf": fake_pypdf}), patch(
                "pdf_import._ocr_pdf_pages", return_value=[extracted]) as ocr:
            results = read_invoice_pdf_pages(Path("weak-text-layer.pdf"))

        ocr.assert_called_once_with(Path("weak-text-layer.pdf"), [0])
        self.assertEqual(len(results), 1)
        self.assertEqual((results[0]["invoice_number"], results[0]["total"]), ("46", 222.0))
        self.assertTrue(results[0]["ocr_used"])
        self.assertIn("Local OCR suggestion", results[0]["notes"])

    def test_multi_page_reader_keeps_reference_warning_after_ocr_refresh(self):
        fake_pypdf = types.ModuleType("pypdf")

        class WeakTextPage:
            def extract_text(self):
                return "Supplier address and bank details with no recognized total."

        fake_pypdf.PdfReader = lambda _path: types.SimpleNamespace(pages=[WeakTextPage()])
        extracted = (
            "Ref NB# ECO-22-24\nDate: 26-Jun-24\n"
            "Total $ 25,120.00\nVAT 11% $ 2,763.20\n"
            "Grand Total $ 27,883.20\nBank Account Currency: LBP"
        )
        with patch.dict(sys.modules, {"pypdf": fake_pypdf}), patch(
                "pdf_import._ocr_pdf_pages", return_value=[extracted]):
            results = read_invoice_pdf_pages(Path("variation-order.pdf"))

        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual((row["invoice_number"], row["invoice_date"]),
                         ("ECO-22-24", "26-06-2024"))
        self.assertEqual(row["currency"], "USD")
        self.assertEqual((row["subtotal"], row["vat"], row["total"]),
                         (25120.0, 2763.2, 27883.2))
        self.assertIn("document reference suggested", row["notes"].casefold())

    def test_inconsistent_ocr_vat_is_flagged_before_review(self):
        extracted = ("Invoice No: 45\nDate: 15/03/2026\nSupplier Co\n"
                     "Subtotal: 100.00\nVAT 1196: 0\nGrand Total: 111.00")
        with patch("pdf_import.pdf_text", return_value=""), patch(
                "pdf_import._ocr_pdf", return_value=extracted):
            result = read_invoice_pdf("scan.pdf")

        self.assertTrue(result["ocr_used"])
        self.assertIsNone(result["vat"])
        self.assertIn("do not reconcile", result["notes"])
        self.assertIn("suggestion cleared", result["notes"])
        self.assertIn("before posting", result["notes"])

    def test_tax_rate_and_registration_number_are_not_vat_amounts(self):
        extracted = ("Invoice No: 45\nDate: 15/03/2026\nSupplier Co\nVAT Number: 123456\n"
                     "Subtotal: 100.00\nVAT 11%\nGrand Total: 111.00")
        with patch("pdf_import.pdf_text", return_value=""), patch(
                "pdf_import._ocr_pdf", return_value=extracted):
            result = read_invoice_pdf("scan.pdf")

        self.assertIsNone(result["vat"])
        self.assertEqual(result["total"], 111.0)
        self.assertIn("VAT amount not found", result["notes"])
        self.assertEqual(_parse_invoice_text("invoice.pdf", extracted.replace("VAT 11%", "VAT 11%: 11.00"))["vat"], 11.0)

    def test_missing_pdf_amounts_are_not_inferred_from_a_rate_or_other_fields(self):
        header = "Invoice No: 45\nDate: 15/03/2026\nSupplier Co\n"
        without_total = _parse_invoice_text("invoice.pdf", header + "Subtotal: 100.00\nVAT: 11.00")
        hyphenated_subtotal = _parse_invoice_text("invoice.pdf", header + "Sub-total: 100.00\nVAT: 11.00")
        before_vat_total = _parse_invoice_text("invoice.pdf", header + "Total HT: 100.00\nVAT: 11.00")
        without_vat = _parse_invoice_text("invoice.pdf", header + "Subtotal: 100.00\nGrand Total: 111.00")

        self.assertIsNone(without_total["total"])
        self.assertIsNone(hyphenated_subtotal["total"])
        self.assertIsNone(before_vat_total["total"])
        self.assertIsNone(without_vat["vat"])
        self.assertIn("not found: total", without_total["notes"])

    def test_pdf_import_requires_explicit_vat_and_reconciled_totals(self):
        row = {"line": "1", "invoice_number": "45", "invoice_date": "15-03-2026",
               "party_name": "Supplier Co", "currency": "USD", "source": "scan.pdf - Page 1",
               "subtotal": 100.0, "vat": None, "total": 111.0}
        screen = types.SimpleNamespace(
            import_sheet=types.SimpleNamespace(ordered=lambda: [row]),
            import_type=types.SimpleNamespace(get=lambda: "Purchases"), import_mode="pdf",
        )
        with patch("desktop_stage3.messagebox.showwarning") as warning:
            Stage3Mixin.send_import(screen)
            self.assertIn("type 0 if none", warning.call_args.args[1])
            row["vat"] = 0.0
            warning.reset_mock()
            Stage3Mixin.send_import(screen)
            self.assertIn("do not reconcile", warning.call_args.args[1])
            row["total"] = 100.0
            row["invoice_date"] = ""
            warning.reset_mock()
            Stage3Mixin.send_import(screen)
            self.assertIn("invoice number, date", warning.call_args.args[1])

        row["invoice_date"] = "15-03-2026"
        row.update(supplier_account="4011",vat_account="44216",expense_account="601100000",expense_no_vat_account="601100001",entry_type="Purchases",_path=__file__)
        screen.import_replace = types.SimpleNamespace(get=lambda: False)
        screen.import_sheet.clear=Mock()
        screen.client = types.SimpleNamespace(import_invoices=Mock(return_value={"imported": 1, "errors": [], "ids": [42]}),upload_attachment=Mock())
        screen.load_dashboard = screen.load_invoices = screen.load_journal = screen.load_trial = screen.load_transactions = Mock()
        with patch("desktop_stage3.messagebox.askyesno",return_value=True), \
             patch("desktop_stage3.messagebox.showinfo") as info, \
             patch("desktop_stage3.messagebox.showwarning") as warning, \
             patch("desktop_stage3.messagebox.showerror") as error:
            Stage3Mixin.send_import(screen)
            info.assert_called_once()
            warning.assert_not_called()
            error.assert_not_called()
        sent = screen.client.import_invoices.call_args.args[0][0]
        self.assertEqual((sent["vat"], sent["total"]), (0.0, 100.0))
        self.assertEqual((sent["supplier_account"],sent["vat_account"],sent["expense_account"],sent["expense_no_vat_account"]),
                          ("4011","44216","601100000","601100001"))

    def test_pdf_type_suggestions_require_unambiguous_document_clues(self):
        self.assertEqual(suggest_invoice_type("Office rent for March\nTotal: 100"),"Expenses")
        self.assertEqual(suggest_invoice_type("Fixed asset: office furniture\nTotal: 100"),"Assets")
        self.assertEqual(suggest_invoice_type("بضاعة للبيع\nTotal: 100"),"Purchases")
        self.assertEqual(suggest_invoice_type("Électricité\nTotal: 100"),"Expenses")
        self.assertEqual(suggest_invoice_type("Invoice for a laptop\nTotal: 100"),"")
        self.assertEqual(suggest_invoice_type("Office rent and raw materials\nTotal: 100"),"")
        self.assertEqual(_parse_invoice_text("asset.pdf","Invoice No: 1\nOffice furniture\nTotal: 100")["suggested_type"],"Assets")

    def test_pdf_upload_shows_a_type_suggestion_for_each_document(self):
        screen=types.SimpleNamespace(import_type=types.SimpleNamespace(get=lambda:"Purchases"),
            currency=types.SimpleNamespace(get=lambda:"USD"),file_label=Mock(),populate_import_preview=Mock())
        documents=[{"file":"batch.pdf","page_range":"Page 1","suggested_type":"Assets",
                    "invoice_number":"A-1","invoice_date":"15-03-2026","party_name":"Supplier",
                    "subtotal":100.0,"vat":11.0,"total":111.0,"notes":"Read from PDF - please check"},
                   {"file":"batch.pdf","page_range":"Page 2","suggested_type":"",
                    "invoice_number":"B-2","invoice_date":"15-03-2026","party_name":"Supplier",
                    "subtotal":100.0,"vat":11.0,"total":111.0,"notes":"Read from PDF - please check"}]
        with patch("desktop_stage3.filedialog.askopenfilenames",return_value=("batch.pdf",)), \
             patch("desktop_stage3.read_invoice_pdf_pages",return_value=documents):
            Stage3Mixin.choose_import_pdfs(screen)
        self.assertEqual([r["entry_type"] for r in screen.import_rows],["Assets",""])
        self.assertIn("Suggested Type: Assets",screen.import_rows[0]["notes"])
        self.assertIn("choose Purchases",screen.import_rows[1]["notes"])
        screen.populate_import_preview.assert_called_once()

    def test_mixed_pdf_types_route_assets_to_register_review_without_posting(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/"invoices.pdf"; pdf.write_bytes(b"%PDF-demo")
            base={"invoice_date":"15-03-2026","party_name":"Supplier","currency":"USD",
                  "subtotal":100.0,"vat":11.0,"total":111.0,"source":"invoices.pdf - Page 1",
                  "_path":str(pdf),"vat_account":"44216","expense_no_vat_account":"601100001"}
            rows=[
                {**base,"line":"001","invoice_number":"GOODS-1","entry_type":"Purchases","expense_account":"601100000","supplier_account":""},
                {**base,"line":"002","invoice_number":"ASSET-1","entry_type":"Assets","expense_account":"231000001","supplier_account":""},
                {**base,"line":"003","invoice_number":"RENT-1","entry_type":"Expenses","expense_account":"6261","supplier_account":"531"},
            ]
            client=types.SimpleNamespace(import_invoices=Mock(return_value={"imported":2,"errors":[],"ids":[11,12]}),
                add_expense=Mock(return_value={"expense_id":13}),upload_attachment=Mock(),upload_expense_attachment=Mock())
            screen=types.SimpleNamespace(import_sheet=types.SimpleNamespace(ordered=lambda:rows,clear=Mock()),
                import_type=types.SimpleNamespace(get=lambda:"Purchases"),import_mode="pdf",
                import_replace=types.SimpleNamespace(get=lambda:False),client=client)
            screen.start_import_asset_review=Mock()
            screen.load_dashboard=screen.load_invoices=screen.load_journal=screen.load_trial=screen.load_transactions=Mock()
            with patch("desktop_stage3.messagebox.askyesno",return_value=True) as confirm, \
                 patch("desktop_stage3.messagebox.showinfo") as info, \
                 patch("desktop_stage3.messagebox.showwarning") as warning:
                Stage3Mixin.send_import(screen)
            self.assertIn("will create one fixed-asset register item",confirm.call_args.args[1])
            warning.assert_not_called(); info.assert_not_called()
            screen.start_import_asset_review.assert_called_once_with(rows[1])
            client.import_invoices.assert_not_called()
            client.add_expense.assert_not_called()
            client.upload_attachment.assert_not_called()
            client.upload_expense_attachment.assert_not_called()

    def test_pdf_type_or_paid_account_must_be_chosen_before_posting(self):
        row={"line":"001","invoice_number":"1","invoice_date":"15-03-2026","party_name":"Supplier",
             "subtotal":100.0,"vat":0.0,"total":100.0,"entry_type":"","supplier_account":"","expense_account":""}
        screen=types.SimpleNamespace(import_sheet=types.SimpleNamespace(ordered=lambda:[row]),
            import_type=types.SimpleNamespace(get=lambda:"Purchases"),import_mode="pdf",
            import_replace=types.SimpleNamespace(get=lambda:False),
            client=types.SimpleNamespace(import_invoices=Mock(),add_expense=Mock()))
        with patch("desktop_stage3.messagebox.showwarning") as warning:
            Stage3Mixin.send_import(screen)
            self.assertIn("choose a Type",warning.call_args.args[1])
            row["entry_type"]="Assets"; Stage3Mixin.send_import(screen)
            self.assertIn("class 2",warning.call_args.args[1])
            row["entry_type"]="Expenses"; row["expense_account"]="6261"; Stage3Mixin.send_import(screen)
            self.assertIn("payment account",warning.call_args.args[1])
            row["supplier_account"]="4011"; Stage3Mixin.send_import(screen)
            self.assertIn("class 5",warning.call_args.args[1])
        screen.client.import_invoices.assert_not_called()
        screen.client.add_expense.assert_not_called()

    def test_changing_pdf_type_resets_incompatible_accounts(self):
        row={"entry_type":"Purchases","supplier_account":"4011","vat_account":PURCHASE_VAT,
             "expense_account":"601100000","subtotal":100.0,"vat":11.0,"total":111.0}
        screen=types.SimpleNamespace(import_mode="pdf",import_sheet=types.SimpleNamespace(rows={"1":row}))
        Stage3Mixin.import_cell_changed(screen,"1","entry_type","Sales")
        self.assertEqual((row["supplier_account"],row["vat_account"],row["expense_account"]),
                         ("",SALES_VAT,"713"))
        row["supplier_account"]="4111"
        Stage3Mixin.import_cell_changed(screen,"1","entry_type","Expenses")
        self.assertEqual((row["supplier_account"],row["vat_account"],row["expense_account"]),
                         ("",EXPENSE_VAT,"601100000"))
        row["supplier_account"]="531"
        Stage3Mixin.import_cell_changed(screen,"1","entry_type","Assets")
        self.assertEqual((row["supplier_account"],row["vat_account"],row["expense_account"]),
                         ("",PURCHASE_VAT,""))

    def test_asset_row_in_partial_import_is_reviewed_before_any_batch_posting(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/"invoice.pdf"; pdf.write_bytes(b"%PDF-demo")
            base={"invoice_date":"15-03-2026","party_name":"Supplier","currency":"USD",
                  "subtotal":100.0,"vat":11.0,"total":111.0,"source":"invoice.pdf - Page 1",
                  "_path":str(pdf),"vat_account":PURCHASE_VAT,"expense_no_vat_account":"601100001"}
            purchase={**base,"line":"001","invoice_number":"P-1","entry_type":"Purchases","expense_account":"601100000","supplier_account":""}
            asset={**base,"line":"002","invoice_number":"A-1","entry_type":"Assets","expense_account":"231000001","supplier_account":""}
            expense={**base,"line":"003","invoice_number":"E-1","entry_type":"Expenses","expense_account":"6261","supplier_account":"531"}
            rows=[purchase,asset,expense]; retained=[]
            sheet=types.SimpleNamespace(ordered=lambda:rows,clear=Mock(),
                                        insert=lambda row:retained.append(row))
            client=types.SimpleNamespace(import_invoices=Mock(return_value={"imported":1,"ids":[21],
                "errors":[{"index":1,"invoice_number":"A-1","error":"invalid account"}]}),
                add_expense=Mock(return_value={"expense_id":22}),
                upload_attachment=Mock(side_effect=OSError("disk full")),upload_expense_attachment=Mock())
            screen=types.SimpleNamespace(import_sheet=sheet,import_type=types.SimpleNamespace(get=lambda:"Purchases"),
                import_mode="pdf",import_replace=types.SimpleNamespace(get=lambda:False),
                client=client)
            screen.start_import_asset_review=Mock()
            screen.load_dashboard=screen.load_invoices=screen.load_journal=screen.load_trial=screen.load_transactions=Mock()
            with patch("desktop_stage3.messagebox.askyesno",return_value=True), \
                 patch("desktop_stage3.messagebox.showwarning") as warning:
                Stage3Mixin.send_import(screen)
            screen.start_import_asset_review.assert_called_once_with(asset)
            self.assertEqual(retained,[])
            client.import_invoices.assert_not_called()
            client.add_expense.assert_not_called()
            client.upload_attachment.assert_not_called()
            client.upload_expense_attachment.assert_not_called()
            warning.assert_not_called()

    def test_expense_import_uses_accounts_selected_in_preview(self):
        row={"line":"001","invoice_number":"EXP-1","invoice_date":"15-03-2026","party_name":"Office expense",
             "currency":"USD","subtotal":100.0,"vat":11.0,"total":111.0,
             "supplier_account":"532","vat_account":"44216","expense_account":"6261",
             "expense_no_vat_account":"601100001","_expense":{"without_vat_subtotal":0}}
        screen=types.SimpleNamespace(import_sheet=types.SimpleNamespace(ordered=lambda:[row],clear=Mock()),
                                     import_type=types.SimpleNamespace(get=lambda:"Expenses"),import_mode="excel",
                                     import_replace=types.SimpleNamespace(get=lambda:False),
                                     client=types.SimpleNamespace(add_expense=Mock(return_value={"expense_id":1})))
        screen.load_dashboard=screen.load_invoices=screen.load_journal=screen.load_trial=screen.load_transactions=Mock()
        with patch("desktop_stage3.messagebox.showinfo"),patch("desktop_stage3.messagebox.showwarning") as warning, \
             patch("desktop_stage3.messagebox.showerror") as error:
            Stage3Mixin.send_import(screen)
            warning.assert_not_called(); error.assert_not_called()
        sent=screen.client.add_expense.call_args.args[0]
        self.assertEqual((sent["payment_account"],sent["vat_account"],sent["expense_account"],sent["expense_without_vat_account"]),
                         ("532","44216","6261","601100001"))

    def test_pdf_forms_require_vat_and_do_not_recalculate_it_from_a_rate(self):
        class Field:
            def __init__(self, value):
                self.value = value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value

        screen = types.SimpleNamespace(
            purchase_form={"pdf_vat_review": True, "vat_typed": True,
                           "vars": {key: Field(value) for key, value in
                                    (("vat", ""), ("taxable", "100"), ("exempt", "0"), ("rate", "11"), ("currency", "USD"))},
                           "items_sheet": types.SimpleNamespace(ordered=lambda: []),
                           "discount_summary": Mock(), "gross_summary": Mock(), "total": Mock()},
            expense_form={"pdf_vat_review": True, "vat_typed": True,
                          "vars": {key: Field(value) for key, value in
                                   (("vat", ""), ("with_vat", "100"), ("without_vat", "0"), ("currency", "USD"))},
                          "total": Mock()},
            purchase_discount=lambda _amount: 0,
        )
        Stage3Mixin.purchase_amounts_changed(screen, "taxable")
        Stage3Mixin.expense_amounts_changed(screen, "with_vat")
        self.assertEqual(screen.purchase_form["vars"]["vat"].get(), "")
        self.assertEqual(screen.expense_form["vars"]["vat"].get(), "")
        with self.assertRaisesRegex(ValueError, "Confirm VAT"):
            Stage3Mixin.purchase_payload(screen)
        with self.assertRaisesRegex(ValueError, "Confirm VAT"):
            Stage3Mixin.expense_payload(screen)

    def test_missing_ocr_runtime_keeps_manual_entry_path(self):
        with patch("pdf_import.pdf_text", return_value=""), patch(
                "pdf_import._ocr_pdf", side_effect=RuntimeError("Tesseract is missing")):
            result = read_invoice_pdf("scan.pdf")

        self.assertFalse(result["ocr_used"])
        self.assertIn("scanned", result["notes"])
        self.assertIn("manual", result["notes"])
        self.assertIn("OCR unavailable", result["notes"])

    def test_asset_purchase_form_requires_asset_account_for_taxable_and_exempt_lines(self):
        class Field:
            def __init__(self, value): self.value=value
            def get(self): return self.value
            def set(self, value): self.value=value
        values={"type":"Assets","account":"601100000","vat_account":"44210",
                "supplier":"Supplier","number":"A-1","date":"15-03-2026","due":"",
                "currency":"USD","taxable":"100","exempt":"20","vat":"11","rate":"11"}
        form={"pdf_vat_review":False,"vars":{key:Field(value) for key,value in values.items()},
              "supplier_map":{},"items_sheet":types.SimpleNamespace(ordered=lambda:[]),
              "department":Field(""),"project":Field(""),"use":Field("Mixed (partial deduction)"),
              "reverse":Field(False),"discount_percent":Field("0"),"discount_amount":Field("0")}
        screen=types.SimpleNamespace(purchase_form=form,purchase_items_changed=lambda:None,
                                     purchase_discount=lambda _amount:0,dimension_code=lambda _value:"")
        with self.assertRaisesRegex(ValueError,"class 2"):
            Stage3Mixin.purchase_payload(screen)
        form["vars"]["account"].set("231000001")
        invoice,lines=Stage3Mixin.purchase_payload(screen)
        self.assertEqual(invoice["expense_account"],"231000001")
        self.assertEqual(invoice["expense_no_vat_account"],"231000001")
        self.assertEqual(lines[0]["non_deductible_subtotal"],20.0)
        form["vars"]["type"].set("Purchases")
        with self.assertRaisesRegex(ValueError,"class 6"):
            Stage3Mixin.purchase_payload(screen)
        form["vars"]["type"].set("Assets")
        item={"item_code":"ITEM-1","name":"Machine","quantity":1,"unit_cost":100,
              "discount_percent":0,"unit":"unit"}
        form["vars"]["exempt"].set("0")
        form["items_sheet"].ordered=lambda:[item]
        form["warehouse"]=Field("MAIN")
        screen.inventory_rows=[{"sku":"ITEM-1","cost_account":"601100000"}]
        invoice,lines=Stage3Mixin.purchase_payload(screen)
        self.assertEqual(invoice["expense_account"],"231000001")
        self.assertNotIn("expense_account",lines[0])

    def test_single_pdf_forms_warn_before_saving_against_suggested_type(self):
        purchase_client=types.SimpleNamespace(create_manual_invoice=Mock())
        purchase=types.SimpleNamespace(purchase_form={"pdf_suggested_type":"Assets",
            "vars":{"type":types.SimpleNamespace(get=lambda:"Purchases")}},
            purchase_payload=lambda:({"kind":"purchases"},[{"description":"item"}]),client=purchase_client)
        expense_client=types.SimpleNamespace(add_expense=Mock())
        expense=types.SimpleNamespace(expense_form={"pdf_suggested_type":"Assets"},
            expense_payload=lambda:{"description":"item"},client=expense_client)
        with patch("desktop_stage3.messagebox.askyesno",return_value=False) as confirmation:
            Stage3Mixin.save_purchase(purchase)
            Stage3Mixin.save_expense(expense)
        self.assertEqual(confirmation.call_count,2)
        self.assertIn("Assets",confirmation.call_args.args[1])
        purchase_client.create_manual_invoice.assert_not_called()
        expense_client.add_expense.assert_not_called()

    def test_single_pdf_uploads_show_suggested_type_without_changing_the_selected_type(self):
        class Field:
            def __init__(self, value=""): self.value=value
            def get(self): return self.value
            def set(self, value): self.value=value
        purchase_vars={key:Field(value) for key,value in
                       (("type","Purchases"),("vat",""),("number",""),("date","15-03-2026"),
                        ("currency","USD"),("taxable",""),("supplier",""))}
        purchase=types.SimpleNamespace(purchase_form={"id":None,"vars":purchase_vars,
            "items_sheet":types.SimpleNamespace(ordered=lambda:[]),"pdf_label":Mock()},
            fiscal_today=lambda:"15-03-2026",purchase_amounts_changed=Mock())
        purchase.add_purchase_pdf_items=lambda data: Stage3Mixin.add_purchase_pdf_items(purchase,data)
        expense_vars={key:Field(value) for key,value in
                      (("vat",""),("reference",""),("date","15-03-2026"),
                       ("currency","USD"),("description",""),("with_vat",""))}
        expense=types.SimpleNamespace(expense_form={"id":None,"vars":expense_vars,"pdf_label":Mock()},
            fiscal_today=lambda:"15-03-2026",expense_amounts_changed=Mock())
        data={"suggested_type":"Assets","vat":11,"invoice_number":"A-1",
              "invoice_date":"15-03-2026","currency":"USD","subtotal":100,
              "party_name":"Supplier","notes":"Read from PDF - please check"}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "asset.pdf"; path.write_bytes(b"%PDF-1.4\n")
            with patch("desktop_stage3.filedialog.askopenfilename",return_value=str(path)), \
                 patch("desktop_stage3.read_invoice_pdf",return_value=data), \
                 patch("desktop_stage3.simpledialog.askstring",return_value=None):
                Stage3Mixin.choose_purchase_pdf(purchase)
                Stage3Mixin.choose_expense_pdf(expense)
        self.assertEqual(purchase_vars["type"].get(),"Purchases")
        self.assertEqual(purchase_vars["number"].get(),"A-1")
        self.assertEqual(purchase.purchase_form["pdf_suggested_type"],"Assets")
        self.assertEqual(expense.expense_form["pdf_suggested_type"],"Assets")
        self.assertIn("Suggested Type: Assets",purchase.purchase_form["pdf_label"].config.call_args.kwargs["text"])
        self.assertIn("Suggested Type: Assets",expense.expense_form["pdf_label"].config.call_args.kwargs["text"])

    def test_purchase_pdf_upload_creates_inventory_items_immediately_and_saves_pdf_with_invoice(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "goods.pdf"; path.write_bytes(b"%PDF-1.4\nsample")
            rows = []
            client = types.SimpleNamespace(
                find_or_create_item=Mock(side_effect=lambda name, unit, sku, supplier:
                    {"sku": "ITM-00001", "name": name, "unit": unit}),
                create_manual_invoice=Mock(return_value={"invoice_id": 92}),
                upload_attachment=Mock(),
            )
            form = {"id": None, "pdf": None, "pdf_label": Mock(),
                    "items_sheet": types.SimpleNamespace(ordered=lambda: rows),
                    "vars": {"supplier": types.SimpleNamespace(get=lambda: ""),
                             "number": types.SimpleNamespace(get=lambda: "", set=Mock()),
                             "date": types.SimpleNamespace(get=lambda: "", set=Mock()),
                             "vat": types.SimpleNamespace(set=Mock()),
                             "currency": types.SimpleNamespace(set=Mock()),
                             "taxable": types.SimpleNamespace(get=lambda: "", set=Mock())}}
            screen = types.SimpleNamespace(
                purchase_form=form, client=client, load_inventory=Mock(),
                purchase_item_line=lambda row: rows.append(row),
                purchase_amounts_changed=Mock(), fiscal_today=lambda: "15-03-2026",
                purchase_payload=Mock(return_value=({"invoice_number": "SUP-42"}, [{"item_code": "ITM-00001"}])),
                new_purchase=Mock(), load_purchases=Mock(), load_invoices=Mock(),
                load_journal=Mock(), load_trial=Mock(),
            )
            screen.add_purchase_pdf_items=lambda data: Stage3Mixin.add_purchase_pdf_items(screen,data)
            data = {"invoice_number": "SUP-42", "items": [
                {"description": "Blue pens", "quantity": 2, "unit_price": 10, "unit": "box"}],
                "subtotal": 20, "vat": 0, "notes": "Read from PDF - please check"}
            with patch("desktop_stage3.filedialog.askopenfilename", return_value=str(path)), \
                 patch("desktop_stage3.read_invoice_pdf", return_value=data):
                Stage3Mixin.choose_purchase_pdf(screen)
            self.assertEqual(rows[0]["item_code"], "ITM-00001")
            self.assertEqual(rows[0]["name"], "Blue pens")
            self.assertEqual(client.find_or_create_item.call_args.args[:2], ("Blue pens", "box"))
            self.assertEqual(form["pdf"], str(path))
            self.assertIn("PDF attaches when you press Save", form["pdf_label"].config.call_args.kwargs["text"])
            with patch("desktop_stage3.messagebox.showinfo"):
                Stage3Mixin.save_purchase(screen)
            client.create_manual_invoice.assert_called_once()
            client.upload_attachment.assert_called_once_with(92, path.name, "application/pdf", path.read_bytes())

    def test_purchase_pdf_without_readable_rows_asks_for_item_name(self):
        rows = []
        screen = types.SimpleNamespace(
            purchase_form={"items_sheet": types.SimpleNamespace(ordered=lambda: rows),
                           "vars": {"supplier": types.SimpleNamespace(get=lambda: "")}},
            client=types.SimpleNamespace(find_or_create_item=Mock(return_value={
                "sku": "ITM-00002", "name": "Paper", "unit": "unit"})),
            purchase_item_line=lambda row: rows.append(row), load_inventory=Mock(),
        )
        with patch("desktop_stage3.simpledialog.askstring", return_value="Paper"):
            note = Stage3Mixin.add_purchase_pdf_items(screen, {"items": [], "subtotal": 50})
        self.assertEqual((rows[0]["name"], rows[0]["unit_cost"]), ("Paper", 50))
        self.assertIn("1 item(s)", note)
        self.assertEqual(screen.client.find_or_create_item.call_count, 1)

    def test_purchase_attachment_failure_retries_only_attachment_not_invoice(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "goods.pdf"; path.write_bytes(b"%PDF-1.4\nsample")
            client = types.SimpleNamespace(
                create_manual_invoice=Mock(return_value={"invoice_id": 92}),
                upload_attachment=Mock(side_effect=[OSError("offline"), {"attachment_id": 7}]),
                attachments=Mock(return_value=[]),
            )
            form = {"id": None, "pdf": str(path), "pdf_label": Mock(),
                    "pdf_suggested_type": "", "vars": {}}
            screen = types.SimpleNamespace(
                purchase_form=form, client=client,
                purchase_payload=Mock(return_value=({"invoice_number": "SUP-42"}, [{"item_code": "ITM-00001"}])),
                new_purchase=Mock(), load_purchases=Mock(), load_invoices=Mock(),
                load_journal=Mock(), load_trial=Mock(),
            )
            with patch("desktop_stage3.messagebox.showwarning") as warning, \
                 patch("desktop_stage3.messagebox.showinfo"):
                Stage3Mixin.save_purchase(screen)
                self.assertEqual(form["pdf_pending_invoice_id"], 92)
                self.assertIn("SAVED", warning.call_args.args[1])
                Stage3Mixin.save_purchase(screen)
            client.create_manual_invoice.assert_called_once()
            screen.purchase_payload.assert_called_once()
            self.assertEqual(client.upload_attachment.call_count, 2)
            screen.new_purchase.assert_called_once()

    def test_purchase_attachment_retry_detects_pdf_already_saved_after_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "goods.pdf"; path.write_bytes(b"%PDF-1.4\nsample")
            content = path.read_bytes()
            client = types.SimpleNamespace(
                create_manual_invoice=Mock(return_value={"invoice_id": 92}),
                upload_attachment=Mock(side_effect=TimeoutError("response lost")),
                attachments=Mock(return_value=[{"id": 7, "file_name": path.name, "size": len(content)}]),
                download_attachment=Mock(return_value={"content": content}),
            )
            form = {"id": None, "pdf": str(path), "pdf_label": Mock(), "vars": {}}
            screen = types.SimpleNamespace(
                purchase_form=form, client=client,
                purchase_payload=Mock(return_value=({"invoice_number": "SUP-42"}, [{"item_code": "ITM-00001"}])),
                new_purchase=Mock(), load_purchases=Mock(), load_invoices=Mock(),
                load_journal=Mock(), load_trial=Mock(),
            )
            with patch("desktop_stage3.messagebox.showwarning"), patch("desktop_stage3.messagebox.showinfo"):
                Stage3Mixin.save_purchase(screen)
                Stage3Mixin.save_purchase(screen)
            client.create_manual_invoice.assert_called_once()
            client.upload_attachment.assert_called_once()
            client.download_attachment.assert_called_once_with(7)
            screen.new_purchase.assert_called_once()

    def test_adding_pdf_to_existing_purchase_attaches_immediately(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "goods.pdf"; path.write_bytes(b"%PDF-1.4\nsample")
            client = types.SimpleNamespace(upload_attachment=Mock())
            form = {"id": 92, "pdf": None, "pdf_label": Mock()}
            screen = types.SimpleNamespace(purchase_form=form, client=client, load_purchases=Mock())
            with patch("desktop_stage3.filedialog.askopenfilename", return_value=str(path)):
                Stage3Mixin.choose_purchase_pdf(screen)
            client.upload_attachment.assert_called_once_with(92, path.name, "application/pdf", path.read_bytes())
            self.assertIsNone(form["pdf"])

    def test_sales_pdf_previews_keep_the_read_invoice_number_after_date_refresh(self):
        class Field:
            def __init__(self, value="", on_set=None):
                self.value, self.on_set = value, on_set
            def get(self): return self.value
            def set(self, value):
                self.value = value
                if self.on_set: self.on_set()

        number = Field()
        date = Field(on_set=lambda: number.set("AUTO-FROM-DATE"))
        screen = types.SimpleNamespace(
            sales_no=number, sales_date=date, sales_party=Field(), sales_currency=Field(),
            sales_items=[{"_iid": "first"}], sales_sheet=Mock(),
            new_sales_invoice=Mock(side_effect=lambda confirm=False: number.set("AUTO-NEW")),
            recalculate_sales_item=Mock(), sales_row_values=Mock(return_value=("line",)),
            update_sales_totals=Mock(),
        )
        data = {"invoice_number": "SUP-42", "invoice_date": "15-03-2026",
                "party_name": "Supplier Co", "currency": "USD", "subtotal": 100, "notes": "Please check"}
        with patch("desktop_v22.filedialog.askopenfilename", return_value="sales.pdf"), \
             patch("pdf_import.read_invoice_pdf", return_value=data), \
             patch("desktop_v22.messagebox.showinfo"):
            V22Mixin.import_sales_pdf(screen)
        self.assertEqual(number.get(), "SUP-42")

        screen.run_ai_task = lambda _worker, show: show(data)
        with patch("desktop_stage3.filedialog.askopenfilename", return_value="sales.pdf"), \
             patch("desktop_stage3.messagebox.showinfo"):
            Stage3Mixin.ai_read_sales_pdf(screen)
        self.assertEqual(number.get(), "SUP-42")

        # An unreadable number must not overwrite the generated draft number.
        data["invoice_number"] = ""
        with patch("desktop_v22.filedialog.askopenfilename", return_value="sales.pdf"), \
             patch("pdf_import.read_invoice_pdf", return_value=data), \
             patch("desktop_v22.messagebox.showinfo"):
            V22Mixin.import_sales_pdf(screen)
        self.assertEqual(number.get(), "AUTO-FROM-DATE")


if __name__ == "__main__":
    unittest.main()