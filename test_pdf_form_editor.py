import hashlib
import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

try:
    from pypdf import PdfReader
    from reportlab.pdfgen import canvas
except ImportError:
    PdfReader = None
    canvas = None

from pdf_form_editor import TextOverlay, save_pdf
from desktop import SaberApp
from desktop_final import FinalFeaturesMixin


@unittest.skipIf(PdfReader is None or canvas is None, "pypdf and reportlab are required for PDF editor tests")
class PDFFormEditorSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "sample_template.pdf"
        self._create_sample()
        self.source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_sample(self):
        document = canvas.Canvas(str(self.source), pagesize=(612, 792))
        document.drawString(50, 747, "Generated sample worksheet")
        document.acroForm.textfield(
            name="employee_name", x=50, y=687, width=210, height=25, value=""
        )
        document.showPage()
        document.drawString(50, 747, "Second sample page")
        document.showPage()
        document.save()

    def test_fills_widget_and_overlay_on_multiple_pages_without_mutating_source(self):
        destination = self.root / "sample_filled.pdf"
        overlay = TextOverlay(1, (50, 90, 290, 115), "department", "")

        result = save_pdf(
            self.source,
            destination,
            {"employee_name": "Ada Example", "department": "Payroll"},
            [overlay],
        )

        self.assertEqual(result, destination.resolve())
        self.assertTrue(destination.is_file())
        self.assertEqual(
            hashlib.sha256(self.source.read_bytes()).hexdigest(), self.source_hash
        )
        filled = PdfReader(str(destination))
        self.assertEqual(filled.get_fields()["employee_name"]["/V"], "Ada Example")
        self.assertIn("Payroll", filled.pages[1].extract_text())
        self.assertEqual(len(filled.pages), 2)

    def test_rejects_overwriting_source(self):
        with self.assertRaises(ValueError):
            save_pdf(self.source, self.source, {"employee_name": "No overwrite"})
        self.assertEqual(
            hashlib.sha256(self.source.read_bytes()).hexdigest(), self.source_hash
        )

    def test_rejects_overlay_outside_page(self):
        with self.assertRaises(ValueError):
            save_pdf(
                self.source,
                self.root / "invalid.pdf",
                overlays=[TextOverlay(1, (600, 780, 620, 810), "out_of_bounds", "x")],
            )


class PDFFormEditorIntegrationTests(unittest.TestCase):
    def test_legacy_payroll_form_shortcut_opens_cnss_form_for_selected_employee(self):
        open_cnss_form = Mock()
        employee_tree = Mock()
        employee_tree.selection.return_value = ("employee-17",)
        app = types.SimpleNamespace(
            employee_tree=employee_tree,
            open_cnss_form=open_cnss_form,
        )

        SaberApp.download_payroll_form(app, "R3")

        open_cnss_form.assert_called_once_with("R3", "employee-17")

    def test_generated_report_opens_in_editor_with_exported_pdf(self):
        editor = types.SimpleNamespace()
        exporter = Mock(side_effect=lambda path, *_args: Path(path).write_bytes(b"%PDF-1.4\nreport"))
        with patch("desktop_final.export_sections_pdf", exporter), \
             patch("pdf_form_editor.open_pdf_form_editor", return_value=editor) as open_editor:
            FinalFeaturesMixin.edit_sections_pdf(types.SimpleNamespace(), "Tax worksheet", {}, [], "tax")
        self.assertEqual(open_editor.call_args.args[1].read_bytes(), b"%PDF-1.4\nreport")
        editor._owned_tempdir.cleanup()


if __name__ == "__main__":
    unittest.main()