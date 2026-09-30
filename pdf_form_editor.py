"""Reusable desktop editor for already-downloaded official PDF form templates.

The editor works on a copy only. It is a worksheet/review aid, not an official
filing or submission facility.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


REVIEW_NOTICE = (
    "Worksheet / review copy only. Review all entries and the completed form "
    "against current official instructions. This editor does not submit or "
    "file anything with an authority."
)


def _optional_pymupdf():
    try:
        import fitz
    except (ImportError, OSError):
        # Some systems have the Python package but not its native runtime
        # library (for example, a missing libstdc++ on Linux).
        return None
    return fitz


def _pypdf_modules():
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import simpleSplit
    except ImportError as exc:
        raise RuntimeError(
            "PDF editing requires PyMuPDF, or the fallback packages pypdf and "
            "reportlab. Install those packages in the application environment."
        ) from exc
    return PdfReader, PdfWriter, canvas, simpleSplit


@dataclass
class TextOverlay:
    """A typed text placement for a PDF template without an editable widget.

    ``page_index`` is zero-based and ``rect`` is in PDF points, with origin at
    the page's upper-left. ``key`` identifies the value supplied to save_pdf.
    """

    page_index: int
    rect: tuple[float, float, float, float]
    key: str
    value: str = ""


def save_pdf(
    source_path: os.PathLike[str] | str,
    destination_path: os.PathLike[str] | str,
    values: Mapping[str, Any] | None = None,
    overlays: Sequence[TextOverlay] | None = None,
) -> Path:
    """Fill AcroForm widgets and/or draw typed overlays into a separate PDF.

    The source is opened read-only and never saved or modified. Values are
    indexed by widget field name or ``TextOverlay.key``.
    """

    fitz = _optional_pymupdf()
    if fitz is None:
        return _save_pdf_pypdf(source_path, destination_path, values, overlays)
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"PDF form template was not found: {source}")
    if source == destination:
        raise ValueError("Save the filled form to a different file; the source is protected.")
    if destination.suffix.lower() != ".pdf":
        raise ValueError("The filled copy must have a .pdf filename.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    supplied = values or {}
    overlay_fields = overlays or ()
    if any(item.page_index < 0 for item in overlay_fields):
        raise ValueError("An overlay refers to a page outside the PDF.")

    document = fitz.open(str(source))
    try:
        if any(item.page_index >= len(document) for item in overlay_fields):
            raise ValueError("An overlay refers to a page outside the PDF.")
        for page_number, page in enumerate(document):
            widgets = page.widgets()
            if widgets:
                for widget in widgets:
                    field_name = widget.field_name
                    if field_name not in supplied:
                        continue
                    value = supplied[field_name]
                    if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                        widget.field_value = "Yes" if bool(value) else "Off"
                    else:
                        widget.field_value = "" if value is None else str(value)
                    widget.update()

            for overlay in overlay_fields:
                if overlay.page_index != page_number:
                    continue
                if not 0 <= overlay.page_index < len(document):
                    raise ValueError(f"Overlay page index is out of range: {overlay.page_index}")
                raw_rect = fitz.Rect(overlay.rect)
                if raw_rect.is_empty or not page.rect.contains(raw_rect):
                    raise ValueError(
                        f"Overlay '{overlay.key}' must fit within page {page_number + 1}."
                    )
                text = supplied.get(overlay.key, overlay.value)
                if text is None or str(text) == "":
                    continue
                page.insert_textbox(
                    raw_rect,
                    str(text),
                    fontname="helv",
                    fontsize=max(6, min(12, raw_rect.height * 0.7)),
                    color=(0, 0, 0),
                    overlay=True,
                )
        document.save(str(destination), garbage=4, deflate=True)
    finally:
        document.close()
    return destination


def _save_pdf_pypdf(source_path, destination_path, values=None, overlays=None) -> Path:
    """PyMuPDF-independent writer fallback for systems missing its native libs."""

    PdfReader, PdfWriter, canvas, simple_split = _pypdf_modules()
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"PDF form template was not found: {source}")
    if source == destination:
        raise ValueError("Save the filled form to a different file; the source is protected.")
    if destination.suffix.lower() != ".pdf":
        raise ValueError("The filled copy must have a .pdf filename.")
    supplied = values or {}
    overlay_fields = overlays or ()
    reader = PdfReader(str(source))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF templates are not supported by the fallback editor.")
    if any(item.page_index < 0 or item.page_index >= len(reader.pages) for item in overlay_fields):
        raise ValueError("An overlay refers to a page outside the PDF.")
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    for page_number, page in enumerate(writer.pages):
        fields = {}
        for annotation_ref in page.get("/Annots", ()):
            annotation = annotation_ref.get_object()
            parent = annotation.get("/Parent")
            parent = parent.get_object() if parent else None
            name = annotation.get("/T") or (parent.get("/T") if parent else None)
            if name is None or str(name) not in supplied:
                continue
            name = str(name)
            value = supplied[name]
            field_type = annotation.get("/FT") or (parent.get("/FT") if parent else None)
            if field_type == "/Btn":
                if bool(value):
                    appearance = annotation.get("/AP")
                    appearance = appearance.get_object() if appearance else {}
                    normal = appearance.get("/N") if appearance else None
                    normal = normal.get_object() if normal else {}
                    states = normal.keys() if normal else ()
                    value = next((str(state) for state in states if str(state) != "/Off"), "/Yes")
                else:
                    value = "/Off"
            fields[name] = str(value)
        if fields:
            writer.update_page_form_field_values(page, fields, auto_regenerate=True)

        matching = [item for item in overlay_fields if item.page_index == page_number]
        if not matching:
            continue
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        buffer = tempfile.SpooledTemporaryFile()
        overlay_canvas = canvas.Canvas(buffer, pagesize=(width, height))
        for overlay in matching:
            x0, y0, x1, y1 = map(float, overlay.rect)
            if x1 <= x0 or y1 <= y0 or x0 < 0 or y0 < 0 or x1 > width or y1 > height:
                raise ValueError(
                    f"Overlay '{overlay.key}' must fit within page {page_number + 1}."
                )
            text = supplied.get(overlay.key, overlay.value)
            if text is None or str(text) == "":
                continue
            font_size = max(6, min(12, (y1 - y0) * 0.7))
            overlay_canvas.setFont("Helvetica", font_size)
            lines = simple_split(
                str(text), "Helvetica", font_size, max(1, x1 - x0 - 4)
            )
            line_y = height - y0 - font_size
            for line in lines:
                if line_y < height - y1:
                    break
                overlay_canvas.drawString(x0 + 2, line_y, line)
                line_y -= font_size * 1.15
        overlay_canvas.save()
        buffer.seek(0)
        overlay_page = PdfReader(buffer).pages[0]
        page.merge_page(overlay_page)
        buffer.close()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        writer.write(output)
    return destination


class PDFFormEditor:
    """A Tkinter Toplevel PDF form editor that can be opened from any app frame.

    Usage: ``PDFFormEditor(parent, downloaded_pdf_path)``.
    """

    def __init__(self, parent: Any, source_path: os.PathLike[str] | str):
        try:
            import tkinter as tk
            from tkinter import messagebox, simpledialog, ttk
        except ImportError as exc:
            raise RuntimeError("PDF form editing requires the standard Tkinter desktop library.") from exc
        self.tk = tk
        self.messagebox = messagebox
        self.simpledialog = simpledialog
        self.ttk = ttk
        self.fit = _optional_pymupdf()
        self.source = Path(source_path).expanduser().resolve()
        if not self.source.is_file():
            raise FileNotFoundError(f"PDF form template was not found: {self.source}")
        try:
            if self.fit is not None:
                self.document = self.fit.open(str(self.source))
            else:
                PdfReader, _, _, _ = _pypdf_modules()
                self.document = PdfReader(str(self.source))
                if self.document.is_encrypted:
                    raise ValueError("Encrypted PDF templates are not supported.")
                if not shutil.which("pdftoppm"):
                    raise RuntimeError(
                        "PDF preview requires the Poppler 'pdftoppm' executable when "
                        "PyMuPDF's native runtime is unavailable."
                    )
                self._render_dir = tempfile.TemporaryDirectory(prefix="pdf-form-preview-")
        except Exception as exc:
            raise ValueError(f"Could not open the PDF form template: {exc}") from exc
        if not len(self.document.pages if self.fit is None else self.document):
            self.document.close()
            raise ValueError("The selected PDF contains no pages.")

        self.window = tk.Toplevel(parent)
        self.window.title(f"Review PDF form — {self.source.name}")
        self.window.geometry("1050x760")
        self.window.minsize(650, 450)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.zoom = 1.0
        self.page_gap = 18
        self.margin = 18
        self.overlays: list[TextOverlay] = []
        self.variables: dict[str, Any] = {}
        self.widget_controls: dict[str, tuple[int, Any, Any]] = {}
        self.overlay_controls: dict[str, tuple[int, Any]] = {}
        self.rendered_pages: list[tuple[int, int, float]] = []

        toolbar = ttk.Frame(self.window, padding=(8, 6))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Fit width", command=self.fit_width).pack(side="left")
        ttk.Button(toolbar, text="−", width=3, command=lambda: self.set_zoom(self.zoom / 1.15)).pack(side="left", padx=(8, 2))
        ttk.Button(toolbar, text="+", width=3, command=lambda: self.set_zoom(self.zoom * 1.15)).pack(side="left")
        page_count = len(self.document.pages) if self.fit is None else len(self.document)
        self.page_label = ttk.Label(toolbar, text=f"{page_count} page(s)")
        self.page_label.pack(side="left", padx=12)
        ttk.Button(toolbar, text="Save filled COPY…", command=self.save_copy).pack(side="right")
        ttk.Button(toolbar, text="Print…", command=self.print_copy).pack(side="right", padx=6)
        ttk.Label(self.window, text=REVIEW_NOTICE, wraplength=1000, foreground="#8b2d20").pack(
            fill="x", padx=10, pady=(0, 5)
        )

        body = ttk.Frame(self.window)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, background="#777777", highlightthickness=0)
        self.vbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self._canvas_click)
        self.window.bind("<MouseWheel>", self._mouse_wheel)
        self.window.bind("<Button-4>", lambda event: self.canvas.yview_scroll(-1, "units"))
        self.window.bind("<Button-5>", lambda event: self.canvas.yview_scroll(1, "units"))
        self.window.bind("<Control-s>", lambda _event: self.save_copy())
        self._resize_after = None
        self.window.after(100, self.fit_width)

    def _mouse_wheel(self, event):
        if self.window.winfo_exists():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_canvas_resize(self, _event):
        if self._resize_after is not None:
            self.window.after_cancel(self._resize_after)
        self._resize_after = self.window.after(160, self.fit_width)

    def fit_width(self):
        self.window.update_idletasks()
        available = max(100, self.canvas.winfo_width() - self.margin * 2)
        page_width, _ = self._page_size(0)
        self.zoom = min(3.0, max(0.25, available / page_width))
        self._render()

    def set_zoom(self, zoom):
        self.zoom = min(4.0, max(0.2, float(zoom)))
        self._render()

    def _render(self):
        if not self.window.winfo_exists():
            return
        self.canvas.delete("all")
        self.widget_controls.clear()
        self.overlay_controls.clear()
        self.rendered_pages = []
        y = self.margin
        page_count = len(self.document.pages) if self.fit is None else len(self.document)
        for page_number in range(page_count):
            page = self.document.pages[page_number] if self.fit is None else self.document[page_number]
            scale = self.zoom
            page_width, page_height = self._page_size(page_number)
            if self.fit is not None:
                pixmap = page.get_pixmap(matrix=self.fit.Matrix(scale, scale), alpha=False)
                image = self.tk.PhotoImage(data=pixmap.tobytes("ppm"))
                image_width, image_height = pixmap.width, pixmap.height
            else:
                image_width = max(1, int(page_width * scale))
                image_height = max(1, int(page_height * scale))
                prefix = Path(self._render_dir.name) / f"page-{page_number + 1}"
                try:
                    subprocess.run(
                        [
                            shutil.which("pdftoppm"),
                            "-f", str(page_number + 1),
                            "-l", str(page_number + 1),
                            "-singlefile",
                            "-scale-to-x", str(image_width),
                            "-scale-to-y", "-1",
                            str(self.source),
                            str(prefix),
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                    image = self.tk.PhotoImage(file=str(prefix) + ".ppm")
                except Exception as exc:
                    self.messagebox.showerror(
                        "Could not render PDF page",
                        f"Poppler could not render page {page_number + 1}: {exc}",
                        parent=self.window,
                    )
                    return
            x = self.margin
            self.canvas.create_image(x, y, image=image, anchor="nw")
            # Retain each image for Tk's image lifetime.
            setattr(self, f"_page_image_{page_number}", image)
            self.canvas.create_rectangle(
                x, y, x + image_width, y + image_height, outline="#333333"
            )
            self.rendered_pages.append((x, y, scale))
            self._add_existing_widget_controls(page_number, page, x, y, scale)
            self._add_overlay_controls(page_number, x, y, scale)
            y += image_height + self.page_gap
        self.canvas.configure(
            scrollregion=(0, 0, max(self.canvas.winfo_width(), 1000), y)
        )

    def _page_size(self, page_number):
        if self.fit is not None:
            rect = self.document[page_number].rect
            return float(rect.width), float(rect.height)
        page = self.document.pages[page_number]
        return float(page.mediabox.width), float(page.mediabox.height)

    def _page_widgets(self, page_number, page):
        if self.fit is not None:
            return [
                {
                    "name": widget.field_name,
                    "type": widget.field_type,
                    "value": widget.field_value,
                    "rect": widget.rect,
                    "options": widget.choice_values,
                }
                for widget in (page.widgets() or ())
            ]
        result = []
        page_height = self._page_size(page_number)[1]
        for annotation_ref in page.get("/Annots", ()):
            annotation = annotation_ref.get_object()
            parent = annotation.get("/Parent")
            parent = parent.get_object() if parent else None
            name = annotation.get("/T") or (parent.get("/T") if parent else None)
            field_type = annotation.get("/FT") or (parent.get("/FT") if parent else None)
            if name is None:
                continue
            raw = annotation.get("/Rect")
            if not raw or len(raw) != 4:
                continue
            x0, y0, x1, y1 = map(float, raw)
            options = annotation.get("/Opt") or (
                parent.get("/Opt") if parent else ()
            ) or ()
            options = [
                str(item.get_object()[1] if isinstance(item, (list, tuple)) else item)
                for item in options
            ]
            value = annotation.get("/V")
            if value is None and parent:
                value = parent.get("/V")
            result.append(
                {
                    "name": str(name),
                    "type": str(field_type),
                    "value": str(value or ""),
                    "rect": (x0, page_height - y1, x1, page_height - y0),
                    "options": options,
                }
            )
        return result

    def _control_value(self, name, initial):
        if name not in self.variables:
            self.variables[name] = self.tk.StringVar(value="" if initial is None else str(initial))
        return self.variables[name]

    def _add_existing_widget_controls(self, page_number, page, x, y, scale):
        for widget in self._page_widgets(page_number, page):
            widget_type = widget["type"]
            if self.fit is not None:
                is_text = widget_type == self.fit.PDF_WIDGET_TYPE_TEXT
                is_checkbox = widget_type == self.fit.PDF_WIDGET_TYPE_CHECKBOX
                is_choice = widget_type in (
                    self.fit.PDF_WIDGET_TYPE_COMBOBOX,
                    self.fit.PDF_WIDGET_TYPE_LISTBOX,
                )
            else:
                is_text = widget_type == "/Tx"
                is_checkbox = widget_type == "/Btn"
                is_choice = widget_type == "/Ch"
            if not (is_text or is_checkbox or is_choice):
                continue
            rect = widget["rect"]
            if self.fit is not None:
                name = widget["name"] or f"field_{page_number}_{int(rect.x0)}_{int(rect.y0)}"
                rect_values = (rect.x0, rect.y0, rect.x1, rect.y1)
            else:
                name = widget["name"] or f"field_{page_number}"
                rect_values = rect
            variable = self._control_value(name, widget["value"])
            left_pt, top_pt, right_pt, bottom_pt = rect_values
            left, top = x + left_pt * scale, y + top_pt * scale
            width, height = max(42, (right_pt - left_pt) * scale), max(20, (bottom_pt - top_pt) * scale)
            if is_checkbox:
                control = self.ttk.Checkbutton(
                    self.canvas, variable=variable, onvalue="Yes", offvalue=""
                )
                if str(variable.get()).lower() not in ("", "off", "no", "0"):
                    variable.set("Yes")
                else:
                    variable.set("")
            elif is_choice and widget["options"]:
                control = self.ttk.Combobox(
                    self.canvas, textvariable=variable, values=widget["options"], state="normal"
                )
            else:
                control = self.ttk.Entry(self.canvas, textvariable=variable)
            window_id = self.canvas.create_window(
                left, top, window=control, anchor="nw", width=width, height=height
            )
            self.widget_controls[name] = (page_number, variable, window_id)

    def _add_overlay_controls(self, page_number, x, y, scale):
        for overlay in self.overlays:
            if overlay.page_index != page_number:
                continue
            variable = self._control_value(overlay.key, overlay.value)
            x0, y0, x1, y1 = overlay.rect
            entry = self.ttk.Entry(self.canvas, textvariable=variable)
            window_id = self.canvas.create_window(
                x + x0 * scale,
                y + y0 * scale,
                window=entry,
                anchor="nw",
                width=max(50, (x1 - x0) * scale),
                height=max(20, (y1 - y0) * scale),
            )
            self.overlay_controls[overlay.key] = (page_number, window_id)

    def _canvas_click(self, event):
        # Clicks inside a field belong to its Entry/Checkbutton; other page
        # clicks add a new typed text field for templates without widgets.
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        for page_number, (page_x, page_y, scale) in enumerate(self.rendered_pages):
            page_width, page_height = self._page_size(page_number)
            if page_x <= x <= page_x + page_width * scale and page_y <= y <= page_y + page_height * scale:
                local_x = (x - page_x) / scale
                local_y = (y - page_y) / scale
                key = self.simpledialog.askstring(
                    "Add text field",
                    "Field name (use this name to identify the typed value):",
                    parent=self.window,
                )
                if not key:
                    return
                if key in self.variables:
                    self.messagebox.showerror("Duplicate field", f"A field named '{key}' already exists.", parent=self.window)
                    return
                width = min(180.0, page_width - local_x)
                height = min(24.0, page_height - local_y)
                overlay = TextOverlay(page_number, (local_x, local_y, local_x + width, local_y + height), key)
                self.overlays.append(overlay)
                self._render()
                return

    def _current_values(self):
        return {name: variable.get() for name, variable in self.variables.items()}

    def save_copy(self):
        from tkinter import filedialog

        destination = filedialog.asksaveasfilename(
            parent=self.window,
            title="Save filled review copy",
            defaultextension=".pdf",
            initialfile=f"{self.source.stem}_filled.pdf",
            filetypes=[("PDF files", "*.pdf")],
        )
        if not destination:
            return
        try:
            save_pdf(self.source, destination, self._current_values(), self.overlays)
        except Exception as exc:
            self.messagebox.showerror("Could not save filled copy", str(exc), parent=self.window)
            return
        self.last_saved_path = Path(destination)
        self.messagebox.showinfo(
            "Filled copy saved",
            f"Review copy saved to:\n{destination}\n\n{REVIEW_NOTICE}",
            parent=self.window,
        )

    def print_copy(self):
        if sys.platform != "win32":
            self.messagebox.showerror(
                "Print unavailable",
                "Printing this PDF from the editor is supported only on Windows.",
                parent=self.window,
            )
            return
        if not hasattr(self, "last_saved_path") or not self.last_saved_path.is_file():
            self.messagebox.showwarning(
                "Save a copy first", "Save a filled review copy before printing.", parent=self.window
            )
            return
        try:
            os.startfile(str(self.last_saved_path), "print")
        except Exception as exc:
            self.messagebox.showerror("Could not print PDF", str(exc), parent=self.window)

    def close(self):
        try:
            self.document.close()
        finally:
            if hasattr(self, "_render_dir"):
                self._render_dir.cleanup()
            self.window.destroy()
            if getattr(self, "_owned_tempdir", None):
                self._owned_tempdir.cleanup()


def open_pdf_form_editor(parent: Any, source_path: os.PathLike[str] | str) -> PDFFormEditor:
    """Convenience integration function for opening an editor window."""

    return PDFFormEditor(parent, source_path)