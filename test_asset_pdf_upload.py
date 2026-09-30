"""Focused tests for conservative PDF-to-fixed-asset prefill."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop_stage3 import Stage3Mixin
from pdf_import import _parse_invoice_text, _warn_on_invoice_total_mismatch, asset_pdf_details


class AssetPdfPrefillTests(unittest.TestCase):
    def test_single_unambiguous_invoice_item_prefills_register_values(self):
        parsed = _parse_invoice_text(
            "laptop.pdf",
            "Invoice No: A-1\nDate: 15-03-2026\nUSD\n"
            "Office laptop 1 1500 1500\nSubtotal: 1500\nVAT: 165\nTotal: 1665",
        )

        self.assertEqual(
            asset_pdf_details(parsed),
            {"name": "Office laptop", "acquired_on": "15-03-2026", "currency": "USD", "cost": 1500.0},
        )

    def test_total_is_not_used_as_asset_cost_without_explicit_zero_vat(self):
        parsed = _parse_invoice_text("scan.pdf", "Asset: Generator\nTotal: 2,000")
        self.assertEqual(
            asset_pdf_details(parsed),
            {"name": "Generator", "acquired_on": "", "currency": "", "cost": None},
        )

    def test_grand_total_is_only_cost_candidate_when_vat_is_explicitly_zero(self):
        parsed = _parse_invoice_text("asset.pdf", "Asset: Generator\nUSD\nVAT: 0\nTotal: 2,000")
        self.assertEqual(parsed["acquisition_cost"], 2000.0)
        self.assertEqual(asset_pdf_details(parsed)["cost"], 2000.0)

    def test_mismatched_ocr_totals_clear_asset_cost_suggestion(self):
        parsed = {"subtotal": 100.0, "vat": 11.0, "total": 120.0, "acquisition_cost": 100.0, "notes": ""}
        _warn_on_invoice_total_mismatch(parsed)
        self.assertIsNone(parsed["vat"])
        self.assertIsNone(parsed["acquisition_cost"])

    def test_dollar_sign_alone_is_not_treated_as_usd(self):
        parsed = _parse_invoice_text("asset.pdf", "Asset: Generator\n$ 2,000\nTotal: 2,000")
        self.assertEqual(asset_pdf_details(parsed)["currency"], "")

    @patch("desktop_stage3.messagebox.askyesno", return_value=True)
    def test_assets_preview_routes_to_register_review_not_invoice_import(self, _confirm):
        asset_row = {"entry_type": "Assets", "line": "1", "expense_account": "231000001"}
        screen = object.__new__(Stage3Mixin)
        screen.import_mode = "pdf"
        screen.import_sheet = Mock()
        screen.import_sheet.ordered.return_value = [asset_row]
        screen.start_import_asset_review = Mock()

        screen.send_import()

        screen.start_import_asset_review.assert_called_once_with(asset_row)
        self.assertFalse(hasattr(screen, "client"))

    def test_attachment_retry_helper_only_uploads_pdf_and_never_saves_asset(self):
        screen = object.__new__(Stage3Mixin)
        screen.client = Mock()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "asset.pdf"
            content = b"%PDF-1.4\nretry"
            path.write_bytes(content)
            Stage3Mixin.upload_asset_pdf(screen, 42, path)

        screen.client.upload_asset_attachment.assert_called_once_with(
            42, "asset.pdf", "application/pdf", content
        )
        screen.client.save_asset.assert_not_called()


if __name__ == "__main__":
    unittest.main()