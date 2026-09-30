"""Version 2.2 screens: sales documents (debit / credit notes, duplicate, preview, import), and helpers."""
from __future__ import annotations

import os
import tempfile
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

NAVY, GOLD, LIGHT = "#071b2e", "#c9a96a", "#f3f6f8"
TREATMENTS = {"Taxable": "standard", "Taxable 11%": "standard", "Zero-rated": "zero_rated", "Zero-rated (export)": "zero_rated", "Exempt": "exempt", "Exempt (Art. 16-17)": "exempt", "Out of scope": "out_of_scope"}


def _dd(value):
    text = str(value or "")
    return f"{text[8:10]}-{text[5:7]}-{text[:4]}" if len(text) >= 10 and text[4] == "-" else text


class V22Mixin:
    # ------------------------------------------------------------ sales documents
    def sales_doc_type_changed(self):
        if not self.sales_edit_id: self.refresh_sales_number()
        reverse=self.sales_doc_type.get()=="Credit Note"
        if reverse:
            self.sales_category_box["values"]=["Goods","Products / Services"]
            if self.sales_category.get()!="Goods": self.sales_category.set("Products / Services")
        else:
            self.sales_category_box["values"]=["Goods","Products","Services"]
            if self.sales_category.get()=="Products / Services": self.sales_category.set("Services")
        self.sales_revenue_caption.config(text="Discount Account" if reverse else "Revenue Account")
        self.sales_category_changed()
        self.sales_supplier_side.set("C - Credit" if reverse else "D - Debit")
        self.sales_vat_side.set("D - Debit" if reverse else "C - Credit")
        self.sales_expense_side.set("D - Debit" if reverse else "C - Credit")
        self.sales_mode_label.config(text=f"NEW {self.sales_doc_type.get().upper()}", bg="#8B1E1E" if self.sales_doc_type.get() == "Credit Note" else GOLD,
                                     fg="white" if self.sales_doc_type.get() == "Credit Note" else NAVY)

    def open_sales_by_number(self):
        self.search_open_sales(); values = list(self.sales_open_box["values"])
        if len(values) == 1: self.sales_open_choice.set(values[0]); self.open_sales_invoice()
        elif not values: messagebox.showwarning("Sales Invoice", f"No invoice number matches {self.sales_open_choice.get()}")
        else: self.sales_open_box.event_generate("<Down>")

    def duplicate_sales_invoice(self):
        if not self.sales_edit_id: return messagebox.showwarning("Sales Invoice", "Open the invoice to duplicate first (Find No.)")
        source = self.sales_no.get(); self.sales_edit_id = None
        self.sales_date.set(datetime.now().strftime("%d-%m-%Y")); self.sales_amount_paid.set("0"); self.refresh_sales_number()
        self.sales_mode_label.config(text=f"COPY OF {source}", bg=GOLD, fg=NAVY)
        messagebox.showinfo("Sales Invoice", f"A copy of {source} is ready as {self.sales_no.get()}. Change what you need and press Save.")

    def current_sales_document(self):
        self.update_sales_totals(); calc = getattr(self, "sales_calculation", None)
        if not calc or not calc["lines"]: raise ValueError("Add at least one line")
        treatment = TREATMENTS.get(self.sales_treatment.get(), "standard")
        currency = self.sales_currency.get()
        invoice = {"invoice_number": self.sales_no.get(), "invoice_date": self.sales_date.get(), "due_date": self.sales_due_date.get(), "party_name": self.sales_party.get(),
                   "currency": currency, "kind": "sale", "subtotal": calc["total_ht"], "vat": calc["vat"], "total": calc["grand_total"],
                   "gross_total": calc["total"], "discount": calc["discount"],
                   "invoice_discount_percent": self.sales_discount_percent.get(), "invoice_discount_amount": self.sales_discount_amount.get(),
                   "vat_treatment": treatment, "payment_method": self.sales_payment_method.get(), "amount_paid": self.sales_amount_paid.get(),
                   "doc_subtype": {"Credit Note": "credit_note", "Debit Note": "debit_note"}.get(self.sales_doc_type.get(), "invoice")}
        # Party identity block for the printed invoice (Code / Name / Address / MOF)
        party = getattr(self, "sales_customers", {}).get(self.sales_party.get()) or {}
        invoice["party_code"] = self.sales_supplier_account.get().split(" - ", 1)[0].strip() or (party.get("account_number") or "")
        invoice["party_address"] = party.get("address") or ""
        invoice["party_mof"] = party.get("mof_number") or party.get("tax_number") or ""
        # VAT 11% expressed in LBP using the exchange rate valid on the invoice date
        try:
            rates = self.sales_rates_for_date(self.client.exchange_rates(), self.sales_date.get())
            vat_lbp, _ = self.exchange_equivalents(float(calc["vat"] or 0), currency, rates)
            if currency == "LBP":
                invoice["vat_lbp"] = float(calc["vat"] or 0); invoice["lbp_rate"] = None
            elif vat_lbp is not None:
                invoice["vat_lbp"] = vat_lbp
                base_lbp, _ = self.exchange_equivalents(1.0, currency, rates)
                invoice["lbp_rate"] = base_lbp
        except Exception:
            pass
        return invoice, calc["lines"]

    def sales_invoice_pdf(self, mode):
        from report_export import export_invoice_pdf
        try: invoice, lines = self.current_sales_document()
        except ValueError as exc: return messagebox.showwarning("Sales Invoice", str(exc))
        try: company = self.client.settings()
        except Exception: company = {}
        if mode == "pdf":
            path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"{invoice['invoice_number'] or 'invoice'}.pdf", filetypes=[("PDF", "*.pdf")])
            if not path: return
        else:
            handle = tempfile.NamedTemporaryFile(prefix=f"{invoice['invoice_number'] or 'invoice'}_", suffix=".pdf", delete=False); handle.close(); path = handle.name
        try: export_invoice_pdf(path, invoice, lines, company.get("company_logo") or None, company)
        except Exception as exc: return messagebox.showerror("Sales Invoice", f"The PDF could not be made: {exc}")
        if mode == "pdf": return messagebox.showinfo("Sales Invoice", f"Saved: {path}")
        try:
            if os.name == "nt": os.startfile(path, "print" if mode == "print" else "open")
            else: raise RuntimeError("Preview and printing open in the Windows application")
        except Exception as exc: messagebox.showinfo("Sales Invoice", f"The PDF is ready: {path}\n{exc}")

    def save_invoice_template(self, kind):
        from importer import write_invoice_template
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile=f"Saber_{kind}_invoice_template.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path: return
        try: write_invoice_template(path, kind)
        except Exception as exc: return messagebox.showerror("Excel Template", str(exc))
        messagebox.showinfo("Excel Template", f"Template saved: {path}\nFill the blank Invoices sheet, then use Import Excel. Examples are on a separate sheet.")

    def import_sales_excel(self):
        import invoice_calc
        from importer import read_invoice_lines
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xlsm")])
        if not path: return
        try: invoices = read_invoice_lines(path, "sales")
        except Exception as exc: return messagebox.showerror("Import Sales", f"The Excel file could not be read: {exc}")
        if not invoices: return messagebox.showwarning("Import Sales", "The Invoices sheet is empty. Fill its rows and try again.")
        if not messagebox.askyesno("Import Sales", f"Import {len(invoices)} invoice(s) as drafts (Review status)?"): return
        done = 0; errors = []
        for invoice in invoices:
            treatment = TREATMENTS.get(invoice["vat_treatment"].strip().capitalize(), TREATMENTS.get(invoice["vat_treatment"], "standard"))
            try:
                calc = invoice_calc.calculate(invoice["lines"], zero_vat=treatment != "standard")
                header = {"invoice_number": invoice["invoice_number"], "invoice_date": invoice["invoice_date"], "party_name": invoice["party_name"], "kind": "sales",
                          "currency": invoice["currency"], "status": "review", "source_file": Path(path).name, "vat_treatment": treatment, "gross_before_discount": calc["total"]}
                self.client.create_manual_invoice(header, [{k: v for k, v in l.items() if k != "net"} for l in calc["lines"]]); done += 1
            except Exception as exc: errors.append(f"{invoice['invoice_number']}: {exc}")
        (messagebox.showwarning if errors else messagebox.showinfo)("Import Sales", f"{done} invoice(s) imported as drafts." + ("\n" + "\n".join(errors[:12]) if errors else ""))
        self.load_sales_customer_list(); self.load_invoices(); self.load_journal(); self.load_trial()

    def import_sales_pdf(self):
        from pdf_import import read_invoice_pdf
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not path: return
        data = read_invoice_pdf(path); self.new_sales_invoice(confirm=False)
        if data.get("invoice_date"): self.sales_date.set(data["invoice_date"])
        if data.get("party_name"): self.sales_party.set(data["party_name"])
        if data.get("currency"): self.sales_currency.set(data["currency"])
        first = self.sales_items[0]; first.update(description=f"As per {Path(path).name}", quantity=1, unit_price=data.get("subtotal") or data.get("total") or 0)
        self.recalculate_sales_item(first); self.sales_sheet.item(first["_iid"], values=self.sales_row_values(first)); self.update_sales_totals()
        messagebox.showinfo("Import PDF", f"{data.get('notes', '')}\nCheck the customer and the amount, then press Save.")

    # ------------------------------------------------------------ F2: the list that fits the field you are in
    def setup_context_f2(self):
        self.unbind_all("<F2>"); self.bind_all("<F2>", self.context_f2)
        parties = [(getattr(self, "sales_party_box", None), ("customer", "both")), (getattr(self, "purchase_form", {}).get("supplier_box"), ("supplier", "both")),
                   (getattr(self, "sd_party_box", None), None)]
        for form in getattr(self, "payment_forms", {}).values(): parties.append((form.get("party_box"), None))
        for state in (getattr(self, "statement_state", None),):
            if state: parties.append((state["vars"].get("party_box"), None))
        for box, kinds in parties:
            if box is not None: box._f2 = (lambda b=box, k=kinds: self.party_picker(b, k))
        items = [(getattr(self, "sales_sheet", None), self.sales_item_f2), (getattr(self, "stock_sheet", None) and self.stock_sheet.tree, self.stock_item_lookup),
                 (getattr(self, "sio_sheet", None) and self.sio_sheet.tree, lambda: self.item_picker(self.sio_pick))]
        if getattr(self, "purchase_form", None): items.append((self.purchase_form["items_sheet"].tree, self.purchase_item_lookup))
        for widget, action in items:
            if widget is not None: widget._f2 = action

    def context_f2(self, event=None):
        widget = self.focus_get()
        while widget is not None:
            action = getattr(widget, "_f2", None)
            if action: action(); return "break"
            widget = getattr(widget, "master", None)
        return self.open_active_account_lookup(event)

    def sales_item_f2(self):
        iid = self.sales_sheet.focus() or (self.sales_items[-1]["_iid"] if self.sales_items else None)
        if not iid: return
        def chosen(sku):
            item = self.sales_item_for(iid); product = self.item_by_code(sku)
            if not item or not product: return
            item.update(item_code=product["sku"], description=product["name"], unit=product.get("unit") or "", unit_price=product["sales_price"] or item.get("unit_price") or 0)
            if product.get("default_vat") not in (None,""): item["vat_rate"]=float(str(product["default_vat"]).replace("%","") or 11); item["_vat_typed"]=False
            self.recalculate_sales_item(item); self.sales_sheet.item(iid, values=self.sales_row_values(item)); self.update_sales_totals()
        self.item_picker(chosen)

    def party_picker(self, box, kinds=None):
        try: parties = self.client.parties()
        except Exception as exc: return messagebox.showerror("Customers / Suppliers", str(exc))
        parties = [p for p in parties if not kinds or p["kind"] in kinds]
        window = tk.Toplevel(self); window.title("Customers / Suppliers - F2"); window.geometry("700x420"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        search = tk.StringVar(); entry = tk.Entry(window, textvariable=search, width=40); entry.pack(padx=10, pady=8); entry.focus_set()
        tree = ttk.Treeview(window, columns=("name", "account", "kind", "currency"), show="headings"); tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for key, label, width in (("name", "Name", 300), ("account", "Account", 110), ("kind", "Type", 90), ("currency", "Currency", 70)): tree.heading(key, text=label); tree.column(key, width=width)
        def fill(*_a):
            tree.delete(*tree.get_children()); text = search.get().casefold()
            for p in parties:
                if not text or text in f'{p["name"]} {p.get("account_number") or ""} {p.get("tax_number") or ""}'.casefold():
                    tree.insert("", "end", iid=str(p["id"]), values=(p["name"], p.get("account_number") or "", p["kind"], p.get("currency") or ""))
        def choose(_e=None):
            if not tree.selection(): return
            party = next(p for p in parties if str(p["id"]) == tree.selection()[0]); window.destroy()
            label = next((v for v in box["values"] if str(v).split(" | ")[0] == party["name"]), party["name"])
            box.set(label); box.event_generate("<<ComboboxSelected>>")
        search.trace_add("write", fill); tree.bind("<Double-1>", choose); tree.bind("<Return>", choose); fill()

    # ------------------------------------------------------------ business reports (ageing, item sales, 3D, top)
    BUSINESS_REPORTS = {"Receivables Ageing (customers)": "receivables", "Payables Ageing (suppliers)": "payables", "Client Items: Qty & Value": "item_sales_client",
                        "Client Quantities by Item": "item_sales_item", "Sales Analysis (3D pivot)": "analysis", "Top Clients (HT + VAT = TTC)": "top_clients",
                        "Top Suppliers (HT + VAT = TTC)": "top_suppliers", "Financial Statements + Audit + Notes": "financial_statements"}

    def build_business_reports_page(self, nested):
        page = tk.Frame(nested, bg=LIGHT); nested.add(page, text="Business Reports"); self.business_reports_page=page
        year = getattr(self, "current_fiscal_year", datetime.now().year)
        self.br = {k: tk.StringVar(value=v) for k, v in (("report", "Receivables Ageing (customers)"), ("from", f"01-01-{year}"), ("to", f"31-12-{year}"), ("basis", "USD"),
                   ("only", "All currencies"), ("buckets", "30,60,90,180"), ("top", "20"), ("rows", "client"), ("columns", "month"), ("measure", "ht"), ("years", str(year)))}
        self.br_review = tk.BooleanVar(value=False)
        bar = tk.Frame(page, bg=LIGHT); bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Combobox(bar, textvariable=self.br["report"], values=list(self.BUSINESS_REPORTS), state="readonly", width=30).pack(side="left", padx=(0, 8))
        tk.Label(bar, text="From", bg=LIGHT).pack(side="left"); self.date_entry(bar, self.br["from"], 11).pack(side="left", padx=(4, 6))
        tk.Label(bar, text="As of", bg=LIGHT).pack(side="left"); self.date_entry(bar, self.br["to"], 11).pack(side="left", padx=(4, 6))
        self.action_button(bar, "Today", lambda: self.set_business_as_of(0)).pack(side="left", padx=2)
        self.action_button(bar, "+30 days", lambda: self.set_business_as_of(30)).pack(side="left", padx=(2, 6))
        tk.Label(bar, text="Amounts in", bg=LIGHT).pack(side="left"); ttk.Combobox(bar, textvariable=self.br["basis"], values=["USD", "LBP"], state="readonly", width=5).pack(side="left", padx=(4, 6))
        tk.Label(bar, text="Only", bg=LIGHT).pack(side="left"); ttk.Combobox(bar, textvariable=self.br["only"], values=["All currencies", "USD", "LBP", "EUR", "AED"], state="readonly", width=12).pack(side="left", padx=4)
        bar2 = tk.Frame(page, bg=LIGHT); bar2.pack(fill="x", padx=8, pady=2)
        tk.Label(bar2, text="Ageing buckets", bg=LIGHT).pack(side="left"); tk.Entry(bar2, textvariable=self.br["buckets"], width=13).pack(side="left", padx=(4, 8))
        tk.Label(bar2, text="Top", bg=LIGHT).pack(side="left"); tk.Entry(bar2, textvariable=self.br["top"], width=4).pack(side="left", padx=(4, 8))
        tk.Label(bar2, text="3D: rows", bg=LIGHT).pack(side="left"); ttk.Combobox(bar2, textvariable=self.br["rows"], values=["client", "item", "category"], state="readonly", width=8).pack(side="left", padx=2)
        tk.Label(bar2, text="columns", bg=LIGHT).pack(side="left"); ttk.Combobox(bar2, textvariable=self.br["columns"], values=["month", "quarter", "client", "item", "category"], state="readonly", width=8).pack(side="left", padx=2)
        tk.Label(bar2, text="measure", bg=LIGHT).pack(side="left"); ttk.Combobox(bar2, textvariable=self.br["measure"], values=["quantity", "ht", "vat", "ttc"], state="readonly", width=8).pack(side="left", padx=(2, 8))
        tk.Checkbutton(bar2, text="Include Review", variable=self.br_review, bg=LIGHT).pack(side="left", padx=4)
        fsbar = tk.Frame(page, bg=LIGHT); fsbar.pack(fill="x", padx=8, pady=3)
        tk.Label(fsbar, text="Financial statements - years", bg=LIGHT).pack(side="left")
        tk.Entry(fsbar, textvariable=self.br["years"], width=16).pack(side="left", padx=5)
        tk.Label(fsbar, text="Example: 2024,2025 or 2025 | full calendar years; posted entries", bg=LIGHT).pack(side="left", padx=5)
        tk.Button(fsbar, text="Edit Notes / Audit / Mapping", command=self.edit_financial_report, bg=NAVY, fg="white").pack(side="left", padx=5)
        bar3 = tk.Frame(page, bg=LIGHT); bar3.pack(fill="x", padx=8, pady=(2, 4))
        tk.Button(bar3, text="Show", command=self.run_business_report, bg=GOLD, fg=NAVY, border=0, padx=22, pady=5, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        for text, fmt in (("Print Preview", "preview"), ("Print", "print"), ("Excel", "xlsx"), ("PDF", "pdf")):
            tk.Button(bar3, text=text, command=lambda f=fmt: self.export_business_report(f), bg=NAVY, fg="white", border=0, padx=12, pady=5).pack(side="left", padx=2)
        tk.Label(bar3, text="Ageing shows invoice due dates, days overdue, and expected amounts due by the selected date.", bg=LIGHT, fg="#5f6b76").pack(side="left", padx=10)
        self.br_info = tk.Label(page, text="Choose a report and press Show.", bg=LIGHT, fg="#5f6b76", anchor="w"); self.br_info.pack(fill="x", padx=10)
        self.br_viewer = self.report_viewer(page, [170, 150, 110, 110, 110, 110, 110, 110, 110, 110, 110, 90])
        self.br_viewer.bind("<Double-1>", self.view_business_report_row)

    def view_business_report_row(self, _event=None):
        from tkinter.scrolledtext import ScrolledText
        selected = self.br_viewer.selection()
        if not selected: return
        values = self.br_viewer.item(selected[0], "values")
        window = tk.Toplevel(self); window.title("Report detail"); window.geometry("850x500")
        text = ScrolledText(window,wrap="word",font=("Segoe UI",11)); text.pack(fill="both",expand=True,padx=10,pady=10)
        text.insert("1.0", "\n\n".join(str(v) for v in values if str(v))); text.config(state="disabled")


    def set_business_as_of(self, days):
        from datetime import timedelta
        self.br["to"].set((datetime.now() + timedelta(days=days)).strftime("%d-%m-%Y"))
        if self.BUSINESS_REPORTS.get(self.br["report"].get()) in ("receivables", "payables"):
            self.run_business_report()

    def business_options(self):
        options = {k: v.get().strip() for k, v in self.br.items() if k not in ("report",)}
        options.update(date_from=options.pop("from"), date_to=options.pop("to"), include_review=self.br_review.get(),
                       only_currency="" if options.get("only") == "All currencies" else options.get("only"))
        options.pop("only", None); return options

    def run_business_report(self):
        self.business_result = None
        try: result = self.client.business_report(self.BUSINESS_REPORTS[self.br["report"].get()], self.business_options())
        except Exception as exc: return messagebox.showerror("Business Reports", str(exc))
        if self.BUSINESS_REPORTS[self.br["report"].get()] == "financial_statements":
            for index, width in enumerate([360, 260, 220, 160, 160]): self.br_viewer.column(f"c{index}",width=width)
        else:
            for index, width in enumerate([170, 150, 110, 110, 110]): self.br_viewer.column(f"c{index}",width=width)
        self.business_result = result; self.show_sections(self.br_viewer, result["sections"]); self.br_info.config(text=f'{result["title"]}  |  ' + "   ".join(result["meta"]), fg=NAVY)

    def export_business_report(self, mode):
        self.run_business_report()
        result = getattr(self, "business_result", None)
        if result: self.output_sections(result["title"], result["meta"], result["sections"], result["title"].replace(" ", "_").replace("(", "").replace(")", ""), mode)

    def edit_financial_report(self):
        from financial_statements import NARRATIVES, AUDIT, GROUPS, SUPPLEMENTS, years_from
        from tkinter.scrolledtext import ScrolledText
        try: years = years_from(self.br["years"].get())
        except Exception as exc: return messagebox.showerror("Financial Statements", str(exc))
        window = tk.Toplevel(self); window.title("Financial Statements - saved notes, audit draft and classification")
        window.geometry("1000x720")
        top = ttk.Frame(window); top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="Edit fiscal year").pack(side="left")
        selected = tk.StringVar(value=str(years[0]))
        selector = ttk.Combobox(top, textvariable=selected, values=[str(y) for y in years], state="readonly", width=8); selector.pack(side="left", padx=8)
        ttk.Label(top, text="Save each year before switching. Amounts use the selected report currency.").pack(side="left")
        notebook = ttk.Notebook(window); notebook.pack(fill="both", expand=True, padx=10, pady=5)
        text_fields = {}; entries = {}; state = {}; loaded = [None]
        for kind, definitions in (("notes",NARRATIVES),("audit",AUDIT)):
            page = ttk.Frame(notebook); notebook.add(page,text="Notes" if kind=="notes" else "Audit report DRAFT")
            inner = ttk.Notebook(page); inner.pack(fill="both", expand=True)
            text_fields[kind] = {}
            for index, (name, default) in enumerate(definitions.items(), 1):
                tab=ttk.Frame(inner); inner.add(tab,text=f"{'Note' if kind=='notes' else 'Section'} {index}")
                ttk.Label(tab,text=name,font=("Segoe UI",11,"bold")).pack(anchor="w",padx=8,pady=6)
                text=ScrolledText(tab,wrap="word",font=("Segoe UI",11)); text.pack(fill="both",expand=True,padx=6,pady=6)
                text_fields[kind][name]=(text,default)
        page=ttk.Frame(notebook); notebook.add(page,text="OCI and Cash Flow")
        ttk.Label(page,text="Cash flow: enter reviewed net totals. Positive = inflow, negative = outflow. Blank = review required.\nOCI is disclosure only; related asset/equity entries must already be posted.",wraplength=900).pack(anchor="w",padx=10,pady=10)
        for key,label in SUPPLEMENTS.items():
            row=ttk.Frame(page); row.pack(fill="x",padx=10,pady=8)
            ttk.Label(row,text=label,width=48).pack(side="left")
            variable=tk.StringVar(); entries[key]=variable; ttk.Entry(row,textvariable=variable,width=22).pack(side="left")
        page=ttk.Frame(notebook); notebook.add(page,text="Account mapping")
        ttk.Label(page,text="Optional overrides: one account or prefix = category per line. Longest prefix wins.\nExample: 4031 = noncurrent_liabilities. Review classifications and maturity before issuing.").pack(anchor="w",padx=10,pady=8)
        mapping=ScrolledText(page,height=10); mapping.pack(fill="both",expand=True,padx=10)
        ttk.Label(page,text="\n".join(f"{k}: {v}" for k,v in GROUPS.items()),wraplength=930).pack(anchor="w",padx=10,pady=8)
        def load():
            try: saved=self.client.financial_config(int(selected.get()))
            except Exception as exc:
                if loaded[0] is not None: selected.set(str(loaded[0]))
                return messagebox.showerror("Financial Statements",str(exc),parent=window)
            loaded[0]=int(selected.get()); state.clear(); state.update(saved)
            for kind,fields in text_fields.items():
                for name,(widget,default) in fields.items():
                    widget.delete("1.0","end"); widget.insert("1.0",saved.get(kind,{}).get(name) or default)
            saved_basis=saved.get("basis",self.br["basis"].get())
            for key,var in entries.items(): var.set(saved.get("supplements",{}).get(key,"") if saved_basis==self.br["basis"].get() else "")
            mapping.delete("1.0","end"); mapping.insert("1.0","\n".join(f"{k} = {v}" for k,v in saved.get("mapping",{}).items()))
        def save():
            try:
                if loaded[0] is None: raise ValueError("Load a fiscal year first")
                overrides={}
                for line in mapping.get("1.0","end").splitlines():
                    if not line.strip(): continue
                    code,category=line.split("=",1); overrides[code.strip()]=category.strip()
                cfg={kind:{name:widget.get("1.0","end-1c").strip() for name,(widget,_) in fields.items()} for kind,fields in text_fields.items()}
                cfg.update(mapping=overrides,supplements={k:v.get().strip() for k,v in entries.items()},basis=self.br["basis"].get())
                self.client.save_financial_config(loaded[0],cfg)
                self.business_result=None
                messagebox.showinfo("Financial Statements",f"Saved for {loaded[0]}. Journal entries were not changed.",parent=window)
            except Exception as exc: messagebox.showerror("Financial Statements",str(exc),parent=window)
        selector.bind("<<ComboboxSelected>>",lambda _e:load())
        ttk.Button(window,text="Save this year's report settings",command=save).pack(pady=10)
        load()

    # ------------------------------------------------------------ dashboard charts
    def build_dashboard_charts(self, parent):
        box = tk.Frame(parent, bg=LIGHT); box.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        bar = tk.Frame(box, bg=LIGHT); bar.pack(fill="x")
        self.dash_basis = tk.StringVar(value="USD")
        tk.Label(bar, text=f"Year {getattr(self, 'current_fiscal_year', '')} - charts in", bg=LIGHT, fg=NAVY, font=("Segoe UI", 10, "bold")).pack(side="left")
        box_basis = ttk.Combobox(bar, textvariable=self.dash_basis, values=["USD", "LBP"], state="readonly", width=5); box_basis.pack(side="left", padx=6)
        box_basis.bind("<<ComboboxSelected>>", lambda _e: self.load_dashboard_charts())
        grid = tk.Frame(box, bg=LIGHT); grid.pack(fill="both", expand=True, pady=(4, 0))
        self.dash_canvases = {}
        for index, key in enumerate(("months", "receivables", "top_clients", "cash")):
            canvas = tk.Canvas(grid, bg="white", highlightthickness=1, highlightbackground="#dfe6ee", height=190)
            canvas.grid(row=index // 2, column=index % 2, sticky="nsew", padx=4, pady=4); self.dash_canvases[key] = canvas
            canvas.bind("<Configure>", lambda _e: self.draw_dashboard_charts())
        for col in range(2): grid.grid_columnconfigure(col, weight=1)
        for row in range(2): grid.grid_rowconfigure(row, weight=1)

    def load_dashboard_charts(self):
        if not getattr(self, "dash_canvases", None): return
        try: self.dash_data = self.client.dashboard_charts(getattr(self, "current_fiscal_year", datetime.now().year), self.dash_basis.get())
        except Exception: self.dash_data = None
        self.draw_dashboard_charts()

    def draw_dashboard_charts(self):
        data = getattr(self, "dash_data", None)
        if not data or not getattr(self, "dash_canvases", None): return
        basis = data["basis"]
        self._bar_chart(self.dash_canvases["months"], f"Sales vs purchases & expenses by month (HT, {basis})", [m[0] for m in data["months"]],
                        [("Sales", "#1F6E8C", [m[1] for m in data["months"]]), ("Purchases", GOLD, [m[2] for m in data["months"]])])
        self._bar_chart(self.dash_canvases["receivables"], f"Receivables by age ({basis})", [r[0].replace(" days", "d") for r in data["receivables"]],
                        [("Open", "#8B1E1E", [r[1] for r in data["receivables"]])])
        self._hbar_chart(self.dash_canvases["top_clients"], f"Top 5 clients (TTC, {basis})", data["top_clients"], "#1F6E8C")
        self._hbar_chart(self.dash_canvases["cash"], f"Cash and bank balances ({basis})", data["cash"], "#2E7D5B")

    def _short(self, value):
        value = float(value); sign = "-" if value < 0 else ""; value = abs(value)
        return f"{sign}{value / 1e9:.1f}B" if value >= 1e9 else f"{sign}{value / 1e6:.1f}M" if value >= 1e6 else f"{sign}{value / 1e3:.1f}K" if value >= 1e4 else f"{sign}{value:,.0f}"

    def _bar_chart(self, canvas, title, labels, series):
        canvas.delete("all"); width = max(canvas.winfo_width(), 300); height = max(canvas.winfo_height(), 160)
        canvas.create_text(10, 8, anchor="nw", text=title, fill=NAVY, font=("Segoe UI", 9, "bold"))
        values = [v for _n, _c, vals in series for v in vals]; top = max([1.0] + [abs(v) for v in values])
        if not any(values): canvas.create_text(width / 2, height / 2, text="No data yet", fill="#8a96a3"); return
        left, bottom, chart_h = 40, height - 22, height - 60
        slot = (width - left - 10) / max(1, len(labels)); bar = max(4, min(22, slot / (len(series) + 1)))
        for step in range(4):
            y = bottom - chart_h * step / 3; canvas.create_line(left, y, width - 8, y, fill="#eef2f6")
            canvas.create_text(left - 4, y, anchor="e", text=self._short(top * step / 3), fill="#8a96a3", font=("Segoe UI", 7))
        for i, label in enumerate(labels):
            x0 = left + i * slot + (slot - bar * len(series)) / 2
            for j, (_name, color, vals) in enumerate(series):
                h = chart_h * max(0, vals[i]) / top; canvas.create_rectangle(x0 + j * bar, bottom - h, x0 + (j + 1) * bar - 1, bottom, fill=color, outline="")
            canvas.create_text(left + i * slot + slot / 2, bottom + 9, text=label, fill="#5f6b76", font=("Segoe UI", 7))
        for j, (name, color, vals) in enumerate(series):
            x = width - 170 + j * 85; canvas.create_rectangle(x, 11, x + 10, 19, fill=color, outline=""); canvas.create_text(x + 14, 15, anchor="w", text=f"{name} {self._short(sum(vals))}", font=("Segoe UI", 7), fill=NAVY)

    def _hbar_chart(self, canvas, title, rows, color):
        canvas.delete("all"); width = max(canvas.winfo_width(), 300); height = max(canvas.winfo_height(), 160)
        canvas.create_text(10, 8, anchor="nw", text=title, fill=NAVY, font=("Segoe UI", 9, "bold"))
        if not rows: canvas.create_text(width / 2, height / 2, text="No data yet", fill="#8a96a3"); return
        top = max([1.0] + [abs(v) for _l, v in rows]); line_h = min(26, (height - 36) / len(rows)); label_w = 150
        for i, (label, value) in enumerate(rows):
            y = 32 + i * line_h; w = (width - label_w - 70) * abs(value) / top
            canvas.create_text(10, y + line_h / 2, anchor="w", text=str(label)[:24], fill=NAVY, font=("Segoe UI", 8))
            canvas.create_rectangle(label_w, y + 4, label_w + w, y + line_h - 4, fill=color if value >= 0 else "#8B1E1E", outline="")
            canvas.create_text(label_w + w + 6, y + line_h / 2, anchor="w", text=self._short(value), fill="#5f6b76", font=("Segoe UI", 8))

    # ------------------------------------------------------------ bank reconciliation
    def build_bank_rec_page(self, page):
        year = getattr(self, "current_fiscal_year", datetime.now().year)
        self.bk = {k: tk.StringVar(value=v) for k, v in (("account", ""), ("currency", "USD"), ("from", f"01-01-{year}"), ("to", f"31-12-{year}"), ("balance", ""), ("post_account", "6739 - Bank Commissions & Other Charges"))}
        bar = tk.Frame(page, bg=LIGHT); bar.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(bar, text="Bank account", bg=LIGHT, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.bk_account_box = ttk.Combobox(bar, textvariable=self.bk["account"], state="readonly", width=30); self.bk_account_box.pack(side="left", padx=(4, 8))
        ttk.Combobox(bar, textvariable=self.bk["currency"], values=getattr(self, "currency_codes", ["USD", "LBP", "EUR", "AED"]), state="readonly", width=5).pack(side="left", padx=4)
        tk.Label(bar, text="From", bg=LIGHT).pack(side="left"); self.date_entry(bar, self.bk["from"], 11).pack(side="left", padx=(4, 6))
        tk.Label(bar, text="To", bg=LIGHT).pack(side="left"); self.date_entry(bar, self.bk["to"], 11).pack(side="left", padx=(4, 6))
        tk.Label(bar, text="Statement ending balance", bg=LIGHT).pack(side="left"); tk.Entry(bar, textvariable=self.bk["balance"], width=12).pack(side="left", padx=4)
        tk.Button(bar, text="Show", command=self.load_bank_rec, bg=GOLD, fg=NAVY, border=0, padx=14, pady=5, font=("Segoe UI", 9, "bold")).pack(side="left", padx=6)
        bar2 = tk.Frame(page, bg=LIGHT); bar2.pack(fill="x", padx=8, pady=2)
        for text, command in (("Import Statement (Excel / CSV)", self.import_bank_statement), ("Auto Match", self.bank_auto_match), ("Match Selected", self.bank_match_selected),
                              ("Unmatch", self.bank_unmatch), ("Delete Statement Line", self.bank_delete_line)):
            tk.Button(bar2, text=text, command=command, bg=NAVY if text != "Delete Statement Line" else "#8B1E1E", fg="white", border=0, padx=10, pady=5).pack(side="left", padx=2)
        tk.Label(bar2, text="Book to", bg=LIGHT).pack(side="left", padx=(8, 2)); tk.Entry(bar2, textvariable=self.bk["post_account"], width=20).pack(side="left")
        tk.Button(bar2, text="Post Line", command=self.bank_post_line, bg=GOLD, fg=NAVY, border=0, padx=10, pady=5).pack(side="left", padx=4)
        tk.Button(bar, text="Report", command=lambda: self.bank_report("preview"), bg=NAVY, fg="white", border=0, padx=10, pady=5).pack(side="left", padx=2)
        self.bk_info = tk.Label(page, text="Choose the bank account and press Show. Match each statement line (left) with its book line (right).", bg=LIGHT, fg=NAVY, anchor="w", font=("Segoe UI", 9, "bold"))
        self.bk_info.pack(fill="x", padx=10, pady=(2, 2))
        panes = tk.Frame(page, bg=LIGHT); panes.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.bk_trees = {}
        for index, (key, title, columns) in enumerate((("statement", "Bank statement", (("date", "Date", 85), ("ref", "Reference", 90), ("desc", "Description", 190), ("amount", "Amount", 95), ("match", "Matched", 95))),
                                                       ("books", "Books (account movements)", (("date", "Date", 85), ("voucher", "Voucher", 115), ("desc", "Description", 180), ("amount", "Amount", 95), ("match", "Matched", 70))))):
            frame = tk.LabelFrame(panes, text=title, bg=LIGHT, padx=4, pady=2); frame.grid(row=0, column=index, sticky="nsew", padx=3)
            tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", selectmode="browse")
            for col, label, width in columns: tree.heading(col, text=label); tree.column(col, width=width, anchor="e" if col == "amount" else "w")
            scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview); tree.configure(yscrollcommand=scroll.set)
            tree.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
            tree.tag_configure("matched", foreground="#2E7D5B"); tree.tag_configure("open", foreground="#8B1E1E"); self.bk_trees[key] = tree
        for col in range(2): panes.grid_columnconfigure(col, weight=1)
        panes.grid_rowconfigure(0, weight=1)
        try: self.bk_account_box["values"] = [f'{a["code"]} - {a["name_en"]}' for a in self.client.accounts() if str(a["code"]).startswith(("511", "512", "519", "53"))]
        except Exception: pass

    def _bank_params(self):
        account = self.bk["account"].get().split(" - ", 1)[0].strip()
        if not account: raise ValueError("Choose the bank account")
        return account, self.bk["currency"].get(), self.bk["from"].get().strip(), self.bk["to"].get().strip()

    def load_bank_rec(self):
        try: account, currency, start, end = self._bank_params(); data = self.client.bank_lines(account, currency, start, end, self.bk["balance"].get().strip() or None)
        except Exception as exc: return messagebox.showerror("Bank Reconciliation", str(exc))
        self.bank_data = data; books = {b["id"]: b for b in data["books"]}
        tree = self.bk_trees["statement"]; tree.delete(*tree.get_children())
        for s in data["statement"]:
            book = books.get(s["journal_line_id"]); tree.insert("", "end", iid=str(s["id"]), values=(_dd(s["line_date"]), s.get("reference") or "", s.get("description") or "", f'{float(s["amount"]):,.2f}',
                book["entry_number"] if book else ("matched" if s["journal_line_id"] else "")), tags=("matched" if s["journal_line_id"] else "open",))
        tree = self.bk_trees["books"]; tree.delete(*tree.get_children())
        for b in data["books"]:
            tree.insert("", "end", iid=str(b["id"]), values=(_dd(b["iso_date"]), b["entry_number"], b.get("description") or "", f'{float(b["amount"]):,.2f}', "Yes" if b.get("statement_id") else ""),
                        tags=("matched" if b.get("statement_id") else "open",))
        r = data["report"]; diff = r.get("difference")
        self.bk_info.config(text=f'Book balance {r["book_balance"]:,.2f}   Expected bank balance {r["expected"]:,.2f}   Matched {r["matched"]} of {r["statement_count"]} statement line(s)' +
                            (f'   DIFFERENCE {diff:,.2f}' if diff is not None else "   (enter the statement ending balance to check the difference)"),
                            fg="#2E7D5B" if diff is not None and abs(diff) < 0.005 else NAVY if diff is None else "#8B1E1E")

    def import_bank_statement(self):
        import bank_rec
        try: account, currency, _start, _end = self._bank_params()
        except ValueError as exc: return messagebox.showwarning("Bank Reconciliation", str(exc))
        path = filedialog.askopenfilename(filetypes=[("Bank statement", "*.xlsx *.xlsm *.csv")])
        if not path: return
        try:
            rows = [{**row, "amount": str(row["amount"])} for row in bank_rec.read_statement_file(path)]
            added = self.client.bank_action("import", {"account": account, "currency": currency, "rows": rows})["added"]
        except Exception as exc: return messagebox.showerror("Bank Reconciliation", f"The statement could not be read: {exc}")
        messagebox.showinfo("Bank Reconciliation", f"{added} statement line(s) imported. Press Auto Match."); self.load_bank_rec()

    def bank_auto_match(self):
        try: account, currency, start, end = self._bank_params(); matched = self.client.bank_action("auto-match", {"account": account, "currency": currency, "from": start, "to": end})["matched"]
        except Exception as exc: return messagebox.showerror("Bank Reconciliation", str(exc))
        messagebox.showinfo("Bank Reconciliation", f"{matched} line(s) matched automatically (same amount, dates within 5 days)."); self.load_bank_rec()

    def bank_match_selected(self):
        s = self.bk_trees["statement"].selection(); b = self.bk_trees["books"].selection()
        if not s or not b: return messagebox.showwarning("Bank Reconciliation", "Select one statement line (left) and one book line (right)")
        try: self.client.bank_action("match", {"statement_id": s[0], "journal_line_id": b[0]})
        except Exception as exc: return messagebox.showerror("Bank Reconciliation", str(exc))
        self.load_bank_rec()

    def bank_unmatch(self):
        s = self.bk_trees["statement"].selection()
        if not s: return messagebox.showwarning("Bank Reconciliation", "Select a matched statement line")
        self.client.bank_action("unmatch", {"statement_id": s[0]}); self.load_bank_rec()

    def bank_delete_line(self):
        s = self.bk_trees["statement"].selection()
        if not s or not messagebox.askyesno("Bank Reconciliation", "Delete the selected statement line?"): return
        self.client.bank_action("delete", {"statement_id": s[0]}); self.load_bank_rec()

    def bank_post_line(self):
        s = self.bk_trees["statement"].selection()
        if not s: return messagebox.showwarning("Bank Reconciliation", "Select the statement line to book (bank charges, interest...)")
        try: voucher = self.client.bank_action("post", {"statement_id": s[0], "account_code": self.bk["post_account"].get()})["voucher"]
        except Exception as exc: return messagebox.showerror("Bank Reconciliation", str(exc))
        messagebox.showinfo("Bank Reconciliation", f"Booked as {voucher} and matched."); self.load_bank_rec(); self.load_journal(); self.load_trial()

    def bank_report(self, mode):
        if not getattr(self, "bank_data", None): self.load_bank_rec()
        data = getattr(self, "bank_data", None)
        if data: report = data["report"]; self.output_sections(report["title"], report["meta"], report["sections"], "Bank_Reconciliation", mode)

