"""Payroll-tab UI for previewing and exporting the supplied CNSS forms."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from cnss_forms import (
    FORMS,
    FORM_BY_KEY,
    FORM_BY_LABEL,
    LEGACY_FORM_KEYS,
    build_form_values,
    filled_pdf_bytes,
)


class CNSSFormsMixin:
    def build_cnss_forms_page(self, parent):
        self.cnss_form_label_var = tk.StringVar(value=FORMS[5].label)
        self.cnss_employee_var = tk.StringVar()
        self.cnss_period_type_var = tk.StringVar(value="Monthly")
        self.cnss_period_index_var = tk.StringVar()
        self.cnss_year_var = tk.StringVar(value=str(getattr(self, "current_fiscal_year", datetime.now().year)))
        self.cnss_payment_date_var = tk.StringVar()
        self.cnss_payment_amount_var = tk.StringVar()
        self.cnss_payment_reference_var = tk.StringVar()
        self.cnss_payment_method_var = tk.StringVar()
        self.cnss_employee_by_display = {}
        self.cnss_filled_pdf = None
        self.cnss_last_saved_path = None
        self.cnss_preview_photos = []

        controls = ttk.Frame(parent, padding=(10, 8))
        controls.pack(fill="x")
        ttk.Label(controls, text="CNSS form").grid(row=0, column=0, padx=4, pady=4, sticky="w")
        self.cnss_form_combo = ttk.Combobox(
            controls, textvariable=self.cnss_form_label_var,
            values=[item.label for item in FORMS], state="readonly", width=56,
        )
        self.cnss_form_combo.grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        self.cnss_form_combo.bind("<<ComboboxSelected>>", self._cnss_form_changed)

        ttk.Label(controls, text="Employee").grid(row=0, column=2, padx=4, pady=4, sticky="w")
        self.cnss_employee_combo = ttk.Combobox(
            controls, textvariable=self.cnss_employee_var, state="readonly", width=30,
        )
        self.cnss_employee_combo.grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        self.cnss_employee_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self.refresh_cnss_form_preview()
        )

        ttk.Label(controls, text="Period").grid(row=1, column=0, padx=4, pady=4, sticky="w")
        self.cnss_period_combo = ttk.Combobox(
            controls, textvariable=self.cnss_period_type_var,
            values=["Monthly", "Quarterly", "Yearly"], state="readonly", width=14,
        )
        self.cnss_period_combo.grid(row=1, column=1, padx=4, pady=4, sticky="w")
        self.cnss_period_combo.bind("<<ComboboxSelected>>", self._cnss_period_changed)
        ttk.Label(controls, text="Year").grid(row=1, column=2, padx=4, pady=4, sticky="w")
        self.cnss_year_entry = ttk.Entry(controls, textvariable=self.cnss_year_var, width=10)
        self.cnss_year_entry.grid(row=1, column=3, padx=4, pady=4, sticky="w")
        self.cnss_year_entry.bind("<Return>", self._cnss_period_changed)
        self.cnss_year_entry.bind("<FocusOut>", self._cnss_period_changed)
        ttk.Label(controls, text="Month / quarter").grid(row=1, column=4, padx=4, pady=4, sticky="w")
        self.cnss_period_index_combo = ttk.Combobox(
            controls, textvariable=self.cnss_period_index_var, state="readonly", width=15,
        )
        self.cnss_period_index_combo.grid(row=1, column=5, padx=4, pady=4, sticky="w")
        self.cnss_period_index_combo.bind("<<ComboboxSelected>>", self._cnss_period_changed)

        payment = ttk.LabelFrame(parent, text="Payment details (filled from saved data when available)")
        payment.pack(fill="x", padx=10, pady=(0, 5))
        for col, (label, variable, width) in enumerate((
            ("Amount paid (LBP)", self.cnss_payment_amount_var, 16),
            ("Payment date", self.cnss_payment_date_var, 14),
            ("Receipt / document no.", self.cnss_payment_reference_var, 20),
        )):
            ttk.Label(payment, text=label).grid(row=0, column=col * 2, padx=5, pady=5, sticky="w")
            ttk.Entry(payment, textvariable=variable, width=width).grid(
                row=0, column=col * 2 + 1, padx=5, pady=5, sticky="w"
            )
        ttk.Label(payment, text="Method").grid(row=0, column=6, padx=5, pady=5, sticky="w")
        self.cnss_payment_method_combo = ttk.Combobox(
            payment, textvariable=self.cnss_payment_method_var,
            values=["", "Cheque", "Bank transfer", "Cash", "Unpaid"],
            state="readonly", width=18,
        )
        self.cnss_payment_method_combo.grid(row=0, column=7, padx=5, pady=5, sticky="w")
        self.cnss_payment_frame = payment

        notes = ttk.LabelFrame(parent, text="Missing data and review notes")
        notes.pack(fill="x", padx=10, pady=(0, 5))
        notes.columnconfigure(0, weight=1)
        self.cnss_notes_text = tk.Text(
            notes, height=3, wrap="word", borderwidth=0, highlightthickness=0,
            padx=6, pady=4, state="disabled",
        )
        notes_scroll = ttk.Scrollbar(notes, orient="vertical", command=self.cnss_notes_text.yview)
        self.cnss_notes_text.configure(yscrollcommand=notes_scroll.set)
        self.cnss_notes_text.grid(row=0, column=0, sticky="ew")
        notes_scroll.grid(row=0, column=1, sticky="ns")
        self._show_cnss_notes(["Select a form or refresh the preview to see missing-data notes."])

        toolbar = ttk.Frame(parent, padding=(10, 2))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Auto-fill / Refresh preview", command=self.refresh_cnss_form_preview).pack(side="left")
        self.cnss_save_button = ttk.Button(toolbar, text="Save filled copy…", command=self.save_cnss_form, state="disabled")
        self.cnss_save_button.pack(side="left", padx=6)
        self.cnss_print_button = ttk.Button(toolbar, text="Print last saved copy", command=self.print_cnss_form, state="disabled")
        self.cnss_print_button.pack(side="left")
        self.cnss_status = ttk.Label(
            toolbar,
            text="Review copy only. Confirm every value and current CNSS instructions before filing.",
            foreground="#8b2d20",
        )
        self.cnss_status.pack(side="left", padx=12, fill="x", expand=True)

        preview_frame = ttk.Frame(parent)
        preview_frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.cnss_preview_canvas = tk.Canvas(preview_frame, background="#737373", highlightthickness=0)
        vbar = ttk.Scrollbar(preview_frame, orient="vertical", command=self.cnss_preview_canvas.yview)
        hbar = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.cnss_preview_canvas.xview)
        self.cnss_preview_canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.cnss_preview_canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.cnss_preview_canvas.bind("<Configure>", self._cnss_preview_resized)
        self.payroll_notebook.bind("<<NotebookTabChanged>>", self._cnss_tab_activated, add="+")

        self._refresh_cnss_period_options()
        self._update_cnss_form_controls()

    def refresh_cnss_employee_options(self):
        rows = getattr(self, "employee_rows", []) or []
        options = []
        self.cnss_employee_by_display = {}
        for employee in rows:
            display = f'{employee.get("employee_number") or ""} — {employee.get("full_name") or ""}'.strip(" —")
            options.append(display)
            self.cnss_employee_by_display[display] = employee
        self.cnss_employee_combo.configure(values=options)
        if self.cnss_employee_var.get() not in self.cnss_employee_by_display:
            self.cnss_employee_var.set("")

    def open_cnss_form(self, form_key=None, employee_id=None):
        if not hasattr(self, "cnss_forms_page"):
            return
        was_active = self.payroll_notebook.select() == str(self.cnss_forms_page)
        key = LEGACY_FORM_KEYS.get(str(form_key), form_key)
        if key in FORM_BY_KEY:
            self.cnss_form_label_var.set(FORM_BY_KEY[key].label)
        if employee_id is not None:
            employee = next(
                (row for row in getattr(self, "employee_rows", [])
                 if str(row.get("id")) == str(employee_id)),
                None,
            )
            if employee:
                display = f'{employee.get("employee_number") or ""} — {employee.get("full_name") or ""}'.strip(" —")
                self.cnss_employee_var.set(display)
        self._cnss_force_refresh = True
        self.payroll_notebook.select(self.cnss_forms_page)
        self._update_cnss_form_controls()
        if was_active:
            self._cnss_force_refresh = False
            self.refresh_cnss_form_preview()

    def _cnss_tab_activated(self, _event=None):
        if self.payroll_notebook.select() != str(self.cnss_forms_page):
            return
        if getattr(self, "_cnss_force_refresh", False) or not self.cnss_filled_pdf:
            self._cnss_force_refresh = False
            self.after_idle(self.refresh_cnss_form_preview)

    def _selected_cnss_form(self):
        return FORM_BY_LABEL.get(self.cnss_form_label_var.get())

    def _show_cnss_notes(self, items):
        if not hasattr(self, "cnss_notes_text"):
            return
        notes = list(items or [])
        if not notes:
            notes = ["No missing data was detected. Review every value before filing."]
        self.cnss_notes_text.configure(state="normal")
        self.cnss_notes_text.delete("1.0", tk.END)
        self.cnss_notes_text.insert("1.0", "\n".join(f"• {item}" for item in notes))
        self.cnss_notes_text.configure(state="disabled")

    def _cnss_form_changed(self, _event=None):
        self.cnss_payment_amount_var.set("")
        self.cnss_payment_date_var.set("")
        self.cnss_payment_reference_var.set("")
        self.cnss_payment_method_var.set("")
        self._update_cnss_form_controls()
        self.refresh_cnss_form_preview()

    def _cnss_period_changed(self, _event=None):
        self.cnss_payment_amount_var.set("")
        self.cnss_payment_date_var.set("")
        self.cnss_payment_reference_var.set("")
        self.cnss_payment_method_var.set("")
        self._refresh_cnss_period_options()
        self._update_cnss_form_controls()
        if self._selected_cnss_form():
            self.refresh_cnss_form_preview()

    def _refresh_cnss_period_options(self):
        kind = self.cnss_period_type_var.get()
        if kind == "Monthly":
            values = [f"{month:02d}" for month in range(1, 13)]
            default = f"{datetime.now().month:02d}"
        elif kind == "Quarterly":
            values = ["Q1", "Q2", "Q3", "Q4"]
            default = f"Q{(datetime.now().month - 1) // 3 + 1}"
        else:
            values = ["Full year"]
            default = "Full year"
        self.cnss_period_index_combo.configure(values=values)
        if self.cnss_period_index_var.get() not in values:
            self.cnss_period_index_var.set(default)

    def _update_cnss_form_controls(self):
        key = self._selected_cnss_form()
        form = FORM_BY_KEY.get(key)
        if not form:
            return
        employee_state = "readonly" if form.kind == "employee" else "disabled"
        self.cnss_employee_combo.configure(state=employee_state)
        if form.kind == "period":
            self.cnss_period_combo.configure(values=["Monthly", "Quarterly"], state="readonly")
            if self.cnss_period_type_var.get() not in ("Monthly", "Quarterly"):
                self.cnss_period_type_var.set("Monthly")
            self._refresh_cnss_period_options()
        else:
            self.cnss_period_type_var.set("Yearly")
            self.cnss_period_combo.configure(values=["Yearly"], state="disabled")
        self.cnss_period_index_combo.configure(state="readonly" if form.kind == "period" else "disabled")
        self.cnss_year_entry.configure(state="normal" if form.kind != "employee" else "disabled")
        payment_state = "normal" if form.kind in ("period", "yearly") else "disabled"
        for child in self.cnss_payment_frame.winfo_children():
            try:
                child.configure(state=payment_state)
            except tk.TclError:
                pass
        try:
            self.cnss_payment_method_combo.configure(state="readonly" if payment_state == "normal" else "disabled")
        except tk.TclError:
            pass

    def _cnss_preview_resized(self, _event=None):
        if getattr(self, "cnss_filled_pdf", None):
            self.after_idle(self._display_cnss_pdf)

    def refresh_cnss_form_preview(self):
        key = self._selected_cnss_form()
        if not key:
            return
        form = FORM_BY_KEY[key]
        company = self.client.settings()
        employee = self.cnss_employee_by_display.get(self.cnss_employee_var.get())
        report = None
        settlement_report = None
        settlement_error = None
        filed = []
        year = None
        period_type = self.cnss_period_type_var.get().lower()
        index_text = self.cnss_period_index_var.get()
        try:
            if form.kind != "employee":
                year = int(self.cnss_year_var.get().strip())
                if not 1900 <= year <= 2200:
                    raise ValueError("Enter a valid year.")
                if form.kind == "period":
                    index = int(index_text) if period_type == "monthly" else int(index_text[1:])
                    report = self.client.payroll_report("NSSF", period_type, year, index, "both", False)
                else:
                    period_type = "yearly"
                    report = self.client.payroll_report("NSSF", "yearly", year, 1, "both", False)
                    if form.kind == "annual":
                        try:
                            settlement_report = self.client.payroll_report(
                                "SETTLEMENT", "yearly", year, 1, "both", False
                            )
                        except Exception as exc:
                            settlement_error = exc
                filed = self.client.nssf_filed_wages(year)
            payment_details = {
                "amount_paid": self.cnss_payment_amount_var.get().strip(),
                "payment_date": self.cnss_payment_date_var.get().strip(),
                "reference": self.cnss_payment_reference_var.get().strip(),
                "method": self.cnss_payment_method_var.get().strip(),
            }
            values, missing = build_form_values(
                key, company, employee, report, filed,
                year=year, period_type=period_type, index=(int(index_text) if period_type == "monthly" and index_text.isdigit() else int(index_text[1:]) if period_type == "quarterly" and index_text.startswith("Q") else 1),
                payment_details=payment_details,
                settlement_report=settlement_report,
            )
            if settlement_error:
                missing.append(f"Annual settlement total could not be loaded: {settlement_error}")
            self.cnss_filled_pdf = filled_pdf_bytes(
                key,
                values,
                annual_schedule_report=report if form.kind == "annual" else None,
            )
            self._display_cnss_pdf()
            source = "Company and employee records" if form.kind == "employee" else f"Posted payroll — {report.get('period_label', '')}"
            self.cnss_status.configure(text=f"{form.label} · {source} · Review-only copy.")
            self._show_cnss_notes(missing)
            self.cnss_save_button.configure(state="normal")
            self.cnss_print_button.configure(state="normal" if self.cnss_last_saved_path else "disabled")
            self.cnss_current_values = values
            self.cnss_current_form_key = key
        except Exception as exc:
            self.cnss_filled_pdf = None
            self.cnss_save_button.configure(state="disabled")
            self.cnss_status.configure(text=f"Could not fill this form: {exc}")
            self._show_cnss_notes([f"Preview failed: {exc}"])
            messagebox.showerror("CNSS Forms", str(exc), parent=self)

    def _display_cnss_pdf(self):
        if not self.cnss_filled_pdf or not self.cnss_preview_canvas.winfo_exists():
            return
        try:
            import pymupdf
            document = pymupdf.open(stream=self.cnss_filled_pdf, filetype="pdf")
        except Exception as exc:
            self.cnss_status.configure(text=f"Could not render this form: {exc}")
            return
        canvas = self.cnss_preview_canvas
        canvas.delete("all")
        self.cnss_preview_photos = []
        width = max(100, canvas.winfo_width() - 36)
        y = 14
        rendered_width = 0
        for page in document:
            scale = min(1.25, width / page.rect.width)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            image = tk.PhotoImage(data=pix.tobytes("ppm"))
            self.cnss_preview_photos.append(image)
            canvas.create_image(14, y, image=image, anchor="nw")
            canvas.create_rectangle(14, y, 14 + pix.width, y + pix.height, outline="#333333")
            rendered_width = max(rendered_width, pix.width)
            y += pix.height + 16
        document.close()
        canvas.configure(scrollregion=(0, 0, max(width, rendered_width + 28), y))
        if self.cnss_last_saved_path:
            self.cnss_print_button.configure(state="normal")

    def save_cnss_form(self):
        if not self.cnss_filled_pdf:
            return messagebox.showwarning("CNSS Forms", "Preview the filled form first.", parent=self)
        form = FORM_BY_KEY[self.cnss_current_form_key]
        target = filedialog.asksaveasfilename(
            parent=self,
            title="Save filled CNSS review copy",
            defaultextension=".pdf",
            initialfile=f"{form.key}_{self.cnss_year_var.get().strip() or 'filled'}.pdf",
            filetypes=[("PDF files", "*.pdf")],
        )
        if not target:
            return
        try:
            Path(target).write_bytes(self.cnss_filled_pdf)
        except Exception as exc:
            return messagebox.showerror("CNSS Forms", f"Could not save the filled copy: {exc}", parent=self)
        self.cnss_last_saved_path = Path(target)
        self.cnss_print_button.configure(state="normal" if sys.platform == "win32" else "disabled")
        messagebox.showinfo(
            "CNSS Forms",
            f"Filled review copy saved to:\n{target}\n\nReview every entry with the current CNSS instructions. This does not file or pay anything.",
            parent=self,
        )

    def print_cnss_form(self):
        if sys.platform != "win32":
            return messagebox.showerror("CNSS Forms", "Printing from this tab is supported only on Windows.", parent=self)
        if not self.cnss_last_saved_path or not self.cnss_last_saved_path.is_file():
            return messagebox.showwarning("CNSS Forms", "Save a filled copy first.", parent=self)
        try:
            import os
            os.startfile(str(self.cnss_last_saved_path), "print")
        except Exception as exc:
            messagebox.showerror("CNSS Forms", f"Could not print the saved copy: {exc}", parent=self)