"""Desktop screens added in version 1.12: payroll official reports, quarterly VAT return,
user expiry and permissions, legal-document alerts, and friendly error handling."""
from __future__ import annotations

import tkinter as tk
import traceback
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

from report_export import export_sections_excel, export_sections_pdf
import vat_return as vat_rules

NAVY, GOLD, LIGHT = "#071b2e", "#c9a96a", "#f3f6f8"
RED, AMBER, MUTED = "#8B1E1E", "#8a5a00", "#5f6b76"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _user_date(value):
    text = str(value or "").strip()
    for pattern in ("%d-%m-%Y", "%d%m%Y", "%Y-%m-%d", "%Y%m%d"):
        try: return datetime.strptime(text, pattern)
        except ValueError: pass
    raise ValueError("Date must use DD-MM-YYYY")


def _display(value):
    text = str(value or "")
    return f"{text[8:10]}-{text[5:7]}-{text[:4]}" if len(text) == 10 and text[4] == "-" else text


def _fmt(value):
    if isinstance(value, bool) or value is None: return "" if value is None else str(value)
    if isinstance(value, (int, float)):
        return f"{value:,.0f}" if abs(value - round(value)) < 1e-9 else f"{value:,.2f}"
    return str(value)


class FinalFeaturesMixin:
    # ------------------------------------------------------------ errors and session
    def report_callback_exception(self, exc_type, exc, tb):
        """Show a clear message instead of a silent failure or a raw traceback."""
        traceback.print_exception(exc_type, exc, tb)
        if exc_type.__name__ == "SessionExpired": return
        messagebox.showerror("Saber Accounting", f"Something went wrong: {exc}\n\nYour saved data is safe. Please try again; if this continues, restart the application.")

    def session_ended(self):
        if getattr(self, "_session_notice", False): return
        self._session_notice = True
        def back_to_login():
            self.client = None; self.current_user = None; self.login_screen()
            messagebox.showinfo("Saber Accounting", "Your session has ended or your account is no longer active. Please sign in again.")
            self._session_notice = False
        self.after(0, back_to_login)

    def can_use(self, module):
        user = getattr(self, "current_user", None) or {}
        return user.get("role") == "admin" or bool((user.get("permissions") or {}).get(module, True))

    def status_bar(self):
        user = self.current_user or {}
        bar = tk.Frame(self, bg=NAVY); bar.pack(fill="x", side="bottom")
        expires = user.get("expires_at")
        validity = f"Account valid until {_display(expires)}" if expires else "Account without expiry"
        text = f"Signed in: {user.get('username', '')}   |   Role: {str(user.get('role', '')).title()}   |   {validity}"
        tk.Label(bar, text=text, bg=NAVY, fg="white", font=("Segoe UI", 8)).pack(side="left", padx=12, pady=3)
        if expires:
            try:
                days = (datetime.strptime(expires, "%Y-%m-%d").date() - datetime.now().date()).days
                if days <= 30: tk.Label(bar, text=f"Account expires in {days} day(s) - ask the administrator to renew", bg=NAVY, fg=GOLD, font=("Segoe UI", 8, "bold")).pack(side="left", padx=8)
            except ValueError: pass

    def scrollable_page(self, parent):
        """A notebook page with a vertical scrollbar for long forms."""
        outer = tk.Frame(parent, bg=LIGHT)
        canvas = tk.Canvas(outer, bg=LIGHT, highlightthickness=0); scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=LIGHT); window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.configure(yscrollcommand=scroll.set); canvas.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        # The program-wide wheel handler scrolls this page. (It used to bind and then UNBIND the wheel
        # for the whole program when the mouse left the page, which stopped scrolling everywhere.)
        canvas._saber_scroll_page = True
        return outer, inner

    # ------------------------------------------------------------ legal document alerts
    def show_document_alerts(self, startup=False):
        try: result = self.client.document_alerts(30)
        except Exception as exc:
            if not startup: messagebox.showerror("Legal Document Alerts", str(exc))
            return
        items = result.get("items", [])
        if hasattr(self, "alerts_button"):
            self.alerts_button.config(text=f"Document Alerts ({len(items)})" if items else "Document Alerts",
                                      bg=RED if result.get("expired") else GOLD if items else NAVY, fg="white" if result.get("expired") or not items else NAVY)
        if startup and not items: return
        window = tk.Toplevel(self); window.title("Legal Document Alerts"); window.configure(bg=LIGHT); window.geometry("900x420"); window.transient(self)
        headline = (f"{result.get('expired', 0)} expired and {result.get('expiring', 0)} expiring within {result.get('days', 30)} days"
                    if items else "No expired or expiring legal documents")
        tk.Label(window, text=headline, bg=LIGHT, fg=RED if result.get("expired") else NAVY, font=("Segoe UI", 12, "bold")).pack(pady=(12, 4))
        tk.Label(window, text="Renew these documents and upload the new copy from Customers / Suppliers > Legal Documents.", bg=LIGHT, fg=MUTED).pack()
        frame = tk.Frame(window, bg=LIGHT); frame.pack(fill="both", expand=True, padx=10, pady=10)
        columns = (("status", "Status", 110), ("party", "Customer / Supplier", 230), ("type", "Document", 190), ("expiry", "Expiry Date", 100), ("days", "Days", 70), ("file", "File", 170))
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings")
        for key, label, width in columns: tree.heading(key, text=label); tree.column(key, width=width, anchor="w")
        tree.tag_configure("expired", foreground=RED); tree.tag_configure("soon", foreground=AMBER)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview); tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        for row in items:
            days = row["days_remaining"]
            tree.insert("", "end", values=(row["status"].title(), row["party_name"], row["document_type"], row["expiry_date"],
                "expired" if days < 0 else days, row["file_name"]), tags=("expired" if days < 0 else "soon",))
        self.action_button(window, "Close", window.destroy).pack(pady=(0, 10))

    # ------------------------------------------------------------ payroll official reports
    def build_payroll_reports_page(self, page):
        controls = tk.Frame(page, bg=LIGHT); controls.pack(fill="x", padx=10, pady=8)
        now = datetime.now()
        self.pr_report = tk.StringVar(value="R10 - Quarterly withholding"); self.pr_period_type = tk.StringVar(value="Quarterly")
        self.pr_year = tk.StringVar(value=str(getattr(self, "current_fiscal_year", now.year))); self.pr_index = tk.StringVar(value=f"Q{(now.month - 1) // 3 + 1}")
        self.pr_group = tk.StringVar(value="Employees and Managers (separate)"); self.pr_drafts = tk.BooleanVar(value=False)
        reports = ["R10 - Quarterly withholding", "R5 - Annual employer declaration", "R6 - Individual annual statement",
                   "NSSF - Contributions statement (payment)", "SETTLEMENT - NSSF annual reconciliation", "CEILINGS - NSSF ceilings by month"]
        tk.Label(controls, text="Report", bg=LIGHT).grid(row=0, column=0, padx=4, sticky="w")
        report_box=ttk.Combobox(controls, textvariable=self.pr_report, values=reports, state="readonly", width=31); report_box.grid(row=0, column=1, padx=4)
        tk.Label(controls, text="Period", bg=LIGHT).grid(row=0, column=2, padx=4, sticky="w")
        period_box = ttk.Combobox(controls, textvariable=self.pr_period_type, values=["Monthly", "Quarterly", "Yearly"], state="readonly", width=18); period_box.grid(row=0, column=3, padx=4)
        tk.Label(controls, text="Year", bg=LIGHT).grid(row=0, column=4, padx=4, sticky="w")
        tk.Entry(controls, textvariable=self.pr_year, width=7).grid(row=0, column=5, padx=4)
        self.pr_index_box = ttk.Combobox(controls, textvariable=self.pr_index, state="readonly", width=11); self.pr_index_box.grid(row=0, column=6, padx=4)
        tk.Label(controls, text="Group", bg=LIGHT).grid(row=1, column=0, padx=4, pady=6, sticky="w")
        ttk.Combobox(controls, textvariable=self.pr_group, values=["Employees and Managers (separate)", "Employees only", "Managers only"], state="readonly", width=31).grid(row=1, column=1, padx=4, pady=6)
        tk.Checkbutton(controls, text="Include draft payroll (preview only)", variable=self.pr_drafts, bg=LIGHT).grid(row=1, column=2, columnspan=3, sticky="w", padx=4)
        buttons = tk.Frame(controls, bg=LIGHT); buttons.grid(row=1, column=5, columnspan=4, sticky="e")
        tk.Button(buttons, text="Generate", command=self.generate_payroll_report, bg=GOLD, fg=NAVY, border=0, padx=16, pady=6, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
        self.action_button(buttons, "Export Excel", lambda: self.export_payroll_report("xlsx")).pack(side="left", padx=3)
        self.action_button(buttons, "Export PDF", lambda: self.export_payroll_report("pdf")).pack(side="left", padx=3)
        self.action_button(buttons, "Employee List / Edit", lambda:self.payroll_notebook.select(self.payroll_employees_page)).pack(side="left",padx=3)
        self.action_button(buttons, "Filed NSSF Wages", self.edit_nssf_filed_wages).pack(side="left",padx=3)
        self.nssf_pay_button = tk.Button(buttons, text="Record NSSF Payment", command=self.record_nssf_payment, bg=GOLD, fg=NAVY, border=0, padx=12, pady=6, font=("Segoe UI", 9, "bold"))
        self.nssf_pay_button.pack(side="left", padx=3)
        forms=tk.Frame(controls,bg=LIGHT); forms.grid(row=2,column=0,columnspan=9,sticky="w",pady=(0,5))
        for label,code in (("CNSS Contributions Form","NSSF-DUE"),("CNSS Annual Settlement Form","NSSF-SETTLEMENT"),
                           ("CNSS Annual Employee Declaration","NSSF-ANNUAL")):
            self.action_button(forms,label,lambda key=code:self.download_payroll_form(key)).pack(side="left",padx=3)
        def refresh_index(*_args):
            kind = self.pr_period_type.get()
            if kind in ("Monthly", "Auto (employee count)"):
                self.pr_index_box.config(values=MONTHS, state="readonly")
                if self.pr_index.get() not in MONTHS: self.pr_index.set(MONTHS[now.month - 1])
            elif kind == "Quarterly":
                self.pr_index_box.config(values=["Q1", "Q2", "Q3", "Q4"], state="readonly")
                if self.pr_index.get() not in ("Q1", "Q2", "Q3", "Q4"): self.pr_index.set(f"Q{(now.month - 1) // 3 + 1}")
            else:
                self.pr_index_box.config(values=["Full year"], state="disabled"); self.pr_index.set("Full year")
        def refresh_report(_event=None):
            if self.pr_report.get().startswith("NSSF -"):
                period_box.config(values=["Auto (employee count)", "Monthly", "Quarterly", "Yearly"])
                self.pr_period_type.set("Auto (employee count)")
            else:
                period_box.config(values=["Monthly", "Quarterly", "Yearly"])
                if self.pr_period_type.get() == "Auto (employee count)": self.pr_period_type.set("Quarterly")
            refresh_index()
        report_box.bind("<<ComboboxSelected>>", refresh_report)
        period_box.bind("<<ComboboxSelected>>", refresh_index); refresh_report()
        self.pr_info = tk.Label(page, text="Choose a report and period, then press Generate. Official figures use posted payroll, converted to LBP.", bg=LIGHT, fg=MUTED, anchor="w", justify="left")
        self.pr_info.pack(fill="x", padx=12)
        self.pr_tree = self.report_viewer(page)
        self.payroll_report_result = None

    def report_viewer(self, parent, widths=None):
        frame = tk.Frame(parent, bg=LIGHT); frame.pack(fill="both", expand=True, padx=10, pady=8)
        columns = [f"c{i}" for i in range(20)]
        tree = ttk.Treeview(frame, columns=columns, show="", selectmode="browse")
        widths = list(widths or []) + [None] * 20
        for index, column in enumerate(columns): tree.column(column, width=widths[index] or (190 if index == 1 else 115), anchor="w", stretch=False)
        tree.tag_configure("section", background=NAVY, foreground="white", font=("Segoe UI", 9, "bold"))
        tree.tag_configure("header", background="#dfe6ee", foreground=NAVY, font=("Segoe UI", 8, "bold"))
        tree.tag_configure("total", background="#e8edf2", font=("Segoe UI", 9, "bold"))
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview); xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew"); yscroll.grid(row=0, column=1, sticky="ns"); xscroll.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1); frame.grid_columnconfigure(0, weight=1)
        return tree

    def show_sections(self, tree, sections):
        tree.delete(*tree.get_children())
        for section in sections:
            # A heading is longer than one column: spread it over the first columns.
            text = section["heading"]; parts = []
            for index in range(20):
                if not text: break
                size = max(4, int(int(tree.column(f"c{index}", "width")) / 8.6))
                if len(text) > size and " " in text[:size]: size = text[:size].rindex(" ") + 1  # break between words
                parts.append(text[:size]); text = text[size:]
            tree.insert("", "end", values=parts, tags=("section",))
            tree.insert("", "end", values=section["headers"], tags=("header",))
            totals = set(section.get("total_rows") or [])
            for index, row in enumerate(section["rows"]):
                tree.insert("", "end", values=[_fmt(value) for value in row], tags=("total",) if index in totals else ())
            tree.insert("", "end", values=[""])

    def payroll_report_parameters(self):
        report = self.pr_report.get().split(" ", 1)[0].upper()
        period = self.pr_period_type.get().lower()
        try: year = int(self.pr_year.get().strip())
        except ValueError: raise ValueError("Enter the year as four digits, for example 2025")
        if period in ("monthly", "auto (employee count)"): index = MONTHS.index(self.pr_index.get()) + 1
        elif period == "quarterly": index = int(self.pr_index.get().lstrip("Q"))
        else: index = 1
        group = {"Employees only": "employee", "Managers only": "manager"}.get(self.pr_group.get(), "both")
        return report, "auto" if period == "auto (employee count)" else period, year, index, group

    def generate_payroll_report(self):
        try:
            report, period, year, index, group = self.payroll_report_parameters()
            result = self.client.payroll_report(report, period, year, index, group, self.pr_drafts.get())
        except Exception as exc: return messagebox.showerror("Payroll Reports", str(exc))
        self.payroll_report_result = result
        self.show_sections(self.pr_tree, result["sections"])
        note = f"{result['title']}  |  {result['period_label']}  |  {result['record_count']} payroll record(s)"
        if not result["record_count"]:
            note += "  |  No posted payroll in this period. Post payroll records, or tick 'Include draft payroll' to preview."
        if result.get("report") == "NSSF": note += (f"  |  {result['employee_count']} employee(s) in period, "
            f"{result['payroll_employee_count']} with payroll  |  Net payable: {result['net_payable_lbp']:,.0f} LBP")
        if result.get("report") == "SETTLEMENT" and not result.get("complete"):
            note += "  |  Add the filed wage bases and payments for every month to complete the settlement."
        self.pr_info.config(text=note, fg=RED if not result["record_count"] else NAVY)

    def edit_nssf_filed_wages(self):
        try:
            year=int(self.pr_year.get().strip()); records={row["month"]:row for row in self.client.nssf_filed_wages(year)}
        except Exception as exc: return messagebox.showerror("NSSF Filed Wages",str(exc))
        window=tk.Toplevel(self); window.title(f"NSSF filed wages and payments - {year}")
        window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        window.geometry(f"{min(1000,self.winfo_screenwidth())}x{min(600,self.winfo_screenheight()-80)}")
        outer,form=self.scrollable_page(window); outer.pack(fill="both",expand=True)
        columns=("Month","Sickness filed (LBP)","Family filed (LBP)","End of service filed (LBP)","NSSF paid (LBP)")
        for col,title in enumerate(columns):
            tk.Label(form,text=title,bg=LIGHT,fg=NAVY,font=("Segoe UI",9,"bold")).grid(row=0,column=col,padx=5,pady=7)
        fields={}
        for month in range(1,13):
            record=records.get(month,{})
            tk.Label(form,text=f"{month:02d}-{year}",bg=LIGHT).grid(row=month,column=0,padx=5,pady=5)
            fields[month]={}
            for col,key in enumerate(("sickness_wages","family_wages","end_service_wages","amount_paid"),1):
                value=record.get(key)
                variable=tk.StringVar(value="" if value is None else str(value)); fields[month][key]=variable
                tk.Entry(form,textvariable=variable,width=21).grid(row=month,column=col,padx=5,pady=5)
        tk.Label(form,text="Enter 0 when nothing was filed or paid. Leave blank only when unknown; blank months keep the settlement incomplete.",
            bg=LIGHT,fg=MUTED,wraplength=850,justify="left").grid(row=13,column=0,columnspan=5,sticky="w",padx=10,pady=8)
        def save():
            try:
                for month in range(1,13):
                    item={"year":year,"month":month,**{key:var.get().strip() for key,var in fields[month].items()}}
                    self.client.save_nssf_filed_wages(item)
            except Exception as exc: return messagebox.showerror("NSSF Filed Wages",f"Check month {month:02d}: {exc}",parent=window)
            window.destroy()
            if self.pr_report.get().startswith("SETTLEMENT"): self.generate_payroll_report()
        self.action_button(window,"Save 12 Months",save).pack(pady=8)

    def record_nssf_payment(self):
        result = getattr(self, "payroll_report_result", None)
        if not result or result.get("report") != "NSSF": return messagebox.showwarning("NSSF Payment", "Generate 'NSSF - Contributions statement' for the period first")
        window = tk.Toplevel(self); window.title("Record NSSF Payment"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        values = {"amount": tk.StringVar(value=f'{result["net_payable_lbp"]:.0f}'), "payment_date": tk.StringVar(value=datetime.now().strftime("%d-%m-%Y") if str(datetime.now().year) == str(getattr(self, "current_fiscal_year", datetime.now().year)) else _display(result["date_to"])),
                  "cash_account": tk.StringVar(value="531"), "reference": tk.StringVar()}
        for row, (key, label) in enumerate((("amount", "Amount paid (LBP)"), ("payment_date", "Payment date"), ("cash_account", "Paid from (cash / bank account)"), ("reference", "NSSF receipt number"))):
            tk.Label(window, text=label, bg=LIGHT).grid(row=row, column=0, sticky="w", padx=10, pady=5)
            (self.date_entry(window, values[key], 24) if key == "payment_date" else self.account_search_box(window, values[key], 22) if key == "cash_account" else tk.Entry(window, textvariable=values[key], width=26)).grid(row=row, column=1, padx=10, pady=5)
        def save():
            try: saved = self.client.record_nssf_payment({**{k: v.get().strip() for k, v in values.items()}, "currency": "LBP", "period_label": result["period_label"]})
            except Exception as exc: return messagebox.showerror("NSSF Payment", str(exc), parent=window)
            window.destroy(); messagebox.showinfo("NSSF Payment", f'Payment voucher {saved["voucher"]} saved: Dr NSSF payable / Cr cash {saved["amount"]:,.0f} LBP')
            self.load_journal(); self.load_trial()
        self.action_button(window, "Save Payment", save).grid(row=4, column=0, columnspan=2, pady=10)

    def export_payroll_report(self, format_name):
        result = getattr(self, "payroll_report_result", None)
        if not result: return messagebox.showwarning("Payroll Reports", "Generate the report first")
        name = f"{result['report']}_{result['period_label'].split(' (')[0].replace(' ', '_')}"
        self.save_sections(result["title"], result["meta"], result["sections"], name, format_name)

    def save_sections(self, title, meta, sections, name, format_name):
        extension = ".xlsx" if format_name == "xlsx" else ".pdf"
        path = filedialog.asksaveasfilename(defaultextension=extension, initialfile=name + extension,
            filetypes=[("Excel workbook", "*.xlsx")] if format_name == "xlsx" else [("PDF document", "*.pdf")])
        if not path: return
        try: (export_sections_excel if format_name == "xlsx" else export_sections_pdf)(path, title, meta, sections)
        except PermissionError: return messagebox.showerror(title, "The file could not be saved. Close it if it is open in Excel or a PDF viewer, then try again.")
        except Exception as exc: return messagebox.showerror(title, f"The file could not be saved: {exc}")
        messagebox.showinfo(title, f"Saved successfully:\n{path}")

    PERIOD_FIELDS = (("date_from", "Date From", 90), ("date_to", "Date To", 90), ("employee_ceiling", "Employee Ceiling", 115), ("medical_ceiling", "Sickness Ceiling", 115),
                     ("family_ceiling", "Family Ceiling", 110), ("end_service_ceiling", "EOS Ceiling", 95), ("employee_nssf_rate", "Employee %", 80), ("medical_rate", "Employer Sick. %", 100),
                     ("family_rate", "Family %", 70), ("end_service_rate", "EOS %", 65))

    def build_payroll_periods_panel(self, parent, row):
        """NSSF ceilings and rates by period (Date From - Date To), edited directly like a spreadsheet."""
        from desktop_brains import EditableSheet
        frame = tk.LabelFrame(parent, text="NSSF ceilings and rates by period - double-click a cell to change it (ceilings in LBP / month, rates in %)", bg=LIGHT, padx=6, pady=4)
        frame.grid(row=row, column=0, columnspan=6, padx=10, pady=6, sticky="ew")
        bar = tk.Frame(frame, bg=LIGHT); bar.pack(fill="x")
        self.action_button(bar, "Add Period", self.add_payroll_period).pack(side="left", padx=(0, 3))
        tk.Button(bar, text="Delete Period", command=self.delete_payroll_period, bg=RED, fg="white", border=0, padx=10, pady=5).pack(side="left", padx=3)
        tk.Button(bar, text="Save Periods", command=self.save_payroll_periods, bg=GOLD, fg=NAVY, border=0, padx=14, pady=5, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
        tk.Label(bar, text="A new Date From ends the previous period the day before. Leave Date To empty for 'until further notice'.", bg=LIGHT, fg=MUTED).pack(side="left", padx=8)
        self.periods_sheet = EditableSheet(self, frame, [("line", "#", 35, "center")] + [(k, l, w, "e" if "ceiling" in k or "rate" in k else "center") for k, l, w in self.PERIOD_FIELDS],
                                           [k for k, _l, _w in self.PERIOD_FIELDS], self.payroll_period_changed, height=6)
        self.payroll_periods_tree = self.periods_sheet.tree
        self.payroll_periods_tree.bind("<Button-3>", lambda _e: self.load_selected_payroll_period())
        self.load_payroll_periods()

    def period_display(self, row):
        row["_display"] = {}
        for key, _label, _w in self.PERIOD_FIELDS:
            value = row.get(key)
            if key.startswith("date"): row["_display"][key] = _display(value) if value else ("Open" if key == "date_to" else "")
            elif key.endswith("rate"): row["_display"][key] = f"{float(value or 0) * 100:g}%"
            else: row["_display"][key] = "No ceiling" if not float(value or 0) else f"{float(value):,.0f}"

    def load_payroll_periods(self):
        if not hasattr(self, "periods_sheet"): return
        try: rows = self.client.payroll_settings_list()
        except Exception: return
        self.payroll_period_rows = {row["date_from"]: row for row in rows}; self.periods_sheet.clear()
        for row in rows:
            item = {"original_from": row["date_from"], **{k: row.get(k) for k, _l, _w in self.PERIOD_FIELDS}}; self.period_display(item); self.periods_sheet.insert(item)

    def payroll_period_changed(self, iid, key, text):
        row = self.periods_sheet.rows[iid]; text = text.strip()
        try:
            if key.startswith("date"):
                if key == "date_to" and text.lower() in ("", "open"): row[key] = None
                else: row[key] = _user_date(text).strftime("%Y-%m-%d")
            elif key.endswith("rate"):
                value = float(text.replace("%", "").replace(",", "")); row[key] = str(value / 100 if value > 1 or "%" in text or value == 1 else value)
            else:
                value = float(text.replace(",", "") or 0); row[key] = str(int(value)) if value == int(value) else str(value)
        except ValueError: messagebox.showwarning("NSSF periods", "Dates as DD-MM-YYYY, rates like 3 or 3%, ceilings as numbers"); return False
        self.period_display(row)

    def add_payroll_period(self):
        rows = self.periods_sheet.ordered(); last = dict(rows[-1]) if rows else {}
        item = {**{k: last.get(k) for k, _l, _w in self.PERIOD_FIELDS}, "original_from": None, "date_from": datetime.now().strftime("%Y-%m-01"), "date_to": None}
        self.period_display(item); iid = self.periods_sheet.insert(item); self.after(30, lambda: self.periods_sheet.edit(iid, "date_from"))

    def delete_payroll_period(self):
        iid, row = self.periods_sheet.selected()
        if not row: return messagebox.showwarning("NSSF periods", "Select a period first")
        if not row.get("original_from"): self.periods_sheet.delete_selected(); return
        if not messagebox.askyesno("NSSF periods", f"Delete the period starting {_display(row['original_from'])}? The previous period is extended to cover it."): return
        try: self.client.delete_payroll_period(row["original_from"])
        except Exception as exc: return messagebox.showerror("NSSF periods", str(exc))
        self.load_payroll_periods()

    def save_payroll_periods(self):
        rows = sorted(self.periods_sheet.ordered(), key=lambda r: r["date_from"] or "")
        if len({r["date_from"] for r in rows}) != len(rows): return messagebox.showwarning("NSSF periods", "Two periods start on the same date")
        # All periods are saved together, so Date From / Date To can be changed freely (for example split a period
        # into 01-05-2025 - 30-06-2025): the whole list is checked for overlaps and gaps before anything is saved.
        try:
            self.client.save_payroll_periods([{"original_from": row.get("original_from"), **{k: row.get(k) for k, _l, _w in self.PERIOD_FIELDS}} for row in rows])
        except Exception as exc: return messagebox.showerror("NSSF periods", f"{exc}\n\nNothing was saved; correct the periods and press Save Periods again.")
        self.load_payroll_periods(); messagebox.showinfo("NSSF periods", f"{len(rows)} period(s) saved. Each payroll uses the ceilings of its own month.")

    def load_selected_payroll_period(self):
        iid, row = self.periods_sheet.selected() if hasattr(self, "periods_sheet") else (None, None)
        if not row: return
        self.payroll_period.set(_display(row["date_from"])); self.load_payroll_settings()

    # ------------------------------------------------------------ quarterly VAT return
    def build_vat_return(self):
        page = self.vat_tab; now = datetime.now()
        controls = tk.Frame(page, bg=LIGHT); controls.pack(fill="x", padx=10, pady=8)
        self.vat_year = tk.StringVar(value=str(getattr(self, "current_fiscal_year", now.year))); self.vat_quarter = tk.StringVar(value=f"Q{(now.month - 1) // 3 + 1}")
        self.vat_currency = tk.StringVar(value="All Currencies"); self.vat_include_review = tk.BooleanVar(value=False); self.vat_credit_override = tk.StringVar()
        tk.Label(controls, text="Year", bg=LIGHT).pack(side="left"); tk.Entry(controls, textvariable=self.vat_year, width=7).pack(side="left", padx=4)
        tk.Label(controls, text="Quarter", bg=LIGHT).pack(side="left", padx=(6, 0))
        ttk.Combobox(controls, textvariable=self.vat_quarter, values=["Q1", "Q2", "Q3", "Q4"], state="readonly", width=5).pack(side="left", padx=4)
        tk.Label(controls, text="Currency", bg=LIGHT).pack(side="left", padx=(6, 0))
        ttk.Combobox(controls, textvariable=self.vat_currency, values=["All Currencies", "USD", "EUR", "LBP", "AED"], state="readonly", width=13).pack(side="left", padx=4)
        tk.Checkbutton(controls, text="Include Review documents", variable=self.vat_include_review, bg=LIGHT).pack(side="left", padx=6)
        tk.Button(controls, text="Generate", command=self.load_vat_return, bg=GOLD, fg=NAVY, border=0, padx=16, pady=6, font=("Segoe UI", 9, "bold")).pack(side="left", padx=4)
        law = tk.Frame(page, bg=LIGHT); law.pack(fill="x", padx=10, pady=(0, 4))
        self.vat_ratio = tk.StringVar(); self.vat_refund = tk.StringVar()
        tk.Label(law, text="Credit B/F (LBP, optional)", bg=LIGHT).pack(side="left"); tk.Entry(law, textvariable=self.vat_credit_override, width=13).pack(side="left", padx=(4, 12))
        tk.Label(law, text="Provisional deduction % for the year (Art. 31)", bg=LIGHT).pack(side="left"); tk.Entry(law, textvariable=self.vat_ratio, width=7).pack(side="left", padx=4)
        self.action_button(law, "Save %", self.save_vat_ratio).pack(side="left", padx=(0, 12))
        tk.Label(law, text="Refund requested (LBP, Art. 30)", bg=LIGHT).pack(side="left"); tk.Entry(law, textvariable=self.vat_refund, width=13).pack(side="left", padx=4)
        actions = tk.Frame(page, bg=LIGHT); actions.pack(fill="x", padx=10)
        self.action_button(actions, "Save Return (lock quarter)", self.save_vat_return).pack(side="left", padx=3)
        if (self.current_user or {}).get("role") == "admin":
            tk.Button(actions, text="Reopen Saved Return", command=self.reopen_vat_return, bg=RED, fg="white", border=0, padx=14, pady=7).pack(side="left", padx=3)
        self.action_button(actions, "Export Excel", lambda: self.export_vat_return("xlsx")).pack(side="left", padx=3)
        self.action_button(actions, "Export PDF", lambda: self.export_vat_return("pdf")).pack(side="left", padx=3)
        self.vat_headline = tk.Label(page, text="Choose the year and quarter, then press Generate.", bg=LIGHT, fg=NAVY, font=("Segoe UI", 11, "bold"), anchor="w", justify="left")
        self.vat_headline.pack(fill="x", padx=12, pady=(8, 0))
        self.vat_note = tk.Label(page, text="", bg=LIGHT, fg=MUTED, anchor="w", justify="left"); self.vat_note.pack(fill="x", padx=12)
        nested = ttk.Notebook(page); nested.pack(fill="both", expand=True, padx=10, pady=8)
        summary = tk.Frame(nested, bg=LIGHT); documents = tk.Frame(nested, bg=LIGHT); adjustments = tk.Frame(nested, bg=LIGHT); history = tk.Frame(nested, bg=LIGHT)
        nested.add(summary, text="VAT Return"); nested.add(documents, text="Supporting Documents"); nested.add(adjustments, text="Manual Adjustments"); nested.add(history, text="Saved Returns")
        self.vat_summary_tree = self.report_viewer(summary, [55, 390, 330, 115, 115, 125])
        self.vat_documents_tree = self.table(documents, [("date", "Date", 90), ("number", "Document", 120), ("party", "Customer / Supplier", 200), ("category", "Category", 140),
            ("deductible", "Deductible", 80), ("currency", "Currency", 70), ("base", "Base", 110), ("vat", "VAT", 100), ("rate", "LBP Rate", 90), ("vat_lbp", "VAT (LBP)", 120), ("status", "Status", 75)])
        form = tk.Frame(adjustments, bg=LIGHT); form.pack(fill="x", padx=10, pady=8)
        self.vat_adj_type = tk.StringVar(value="Output VAT"); self.vat_adj_currency = tk.StringVar(value="LBP"); self.vat_adj_amount = tk.StringVar(); self.vat_adj_reason = tk.StringVar()
        ttk.Combobox(form, textvariable=self.vat_adj_type, values=["Output VAT", "Deductible VAT", "Non-deductible VAT"], state="readonly", width=18).pack(side="left", padx=3)
        ttk.Combobox(form, textvariable=self.vat_adj_currency, values=getattr(self, "currency_codes", ["LBP", "USD", "EUR", "AED"]), state="readonly", width=6).pack(side="left", padx=3)
        tk.Label(form, text="Amount (+/-)", bg=LIGHT).pack(side="left"); tk.Entry(form, textvariable=self.vat_adj_amount, width=14).pack(side="left", padx=3)
        tk.Label(form, text="Reason", bg=LIGHT).pack(side="left"); tk.Entry(form, textvariable=self.vat_adj_reason, width=38).pack(side="left", padx=3)
        self.action_button(form, "Add Adjustment", self.add_vat_adjustment).pack(side="left", padx=3)
        tk.Button(form, text="Delete Selected", command=self.delete_vat_adjustment, bg=RED, fg="white", border=0, padx=12, pady=7).pack(side="left", padx=3)
        self.vat_adjustments_tree = self.table(adjustments, [("type", "Type", 190), ("currency", "Currency", 70), ("amount", "Amount", 110), ("amount_lbp", "Amount (LBP)", 130),
            ("reason", "Reason", 300), ("by", "Entered by", 100), ("at", "Entered at", 140)])
        self.vat_history_tree = self.table(history, [("period", "Quarter", 90), ("net", "Net VAT (LBP)", 140), ("bf", "Credit B/F", 130), ("payable", "Payable", 130),
            ("cf", "Credit C/F", 130), ("by", "Saved by", 100), ("at", "Saved at", 150)])
        self.vat_return_result = None

    def vat_parameters(self):
        try: year = int(self.vat_year.get().strip())
        except ValueError: raise ValueError("Enter the year as four digits, for example 2025")
        quarter = int(self.vat_quarter.get().lstrip("Q"))
        currency = None if self.vat_currency.get() == "All Currencies" else self.vat_currency.get()
        credit = self.vat_credit_override.get().strip().replace(",", "") or None
        if credit is not None:
            try: float(credit)
            except ValueError: raise ValueError("Credit brought forward must be a number in LBP, or left empty")
        self._vat_refund_value = self.vat_refund.get().strip().replace(",", "") or None
        if self._vat_refund_value is not None:
            try: float(self._vat_refund_value)
            except ValueError: raise ValueError("Refund requested must be a number in LBP, or left empty")
        return year, quarter, currency, credit

    def load_vat_return(self):
        if not hasattr(self, "vat_summary_tree"): return
        try:
            year, quarter, currency, credit = self.vat_parameters()
            result = self.client.vat_return(year, quarter, currency, self.vat_include_review.get(), credit, self._vat_refund_value)
            history = self.client.vat_returns()
        except Exception as exc: return messagebox.showerror("Quarterly VAT", str(exc))
        self.vat_return_result = result
        title, meta, sections = vat_rules.export_sections(result)
        self.show_sections(self.vat_summary_tree, [s for s in sections if s["heading"] not in ("Supporting documents", "Manual adjustments")])
        payable = result["payable_lbp"]; credit_cf = result["credit_carried_forward_lbp"]
        outcome = f"VAT PAYABLE: {payable:,.0f} LBP" if payable else f"CREDIT CARRIED FORWARD: {credit_cf:,.0f} LBP" if credit_cf else "NIL RETURN: 0 LBP"
        if result.get("provisional_ratio") is not None and not self.vat_ratio.get().strip(): self.vat_ratio.set(f'{float(result["provisional_ratio"]) * 100:g}')
        self.vat_headline.config(text=f"Q{quarter} {year}  |  {outcome}  |  Deduction {float(result.get('deduction_ratio', 1)) * 100:.2f}%  |  Due {_display(result.get('due_date'))}  |  {result['status'].title()}",
                                 fg=RED if result["changed_since_saved"] else NAVY)
        notes = [f"Credit brought forward: {result['credit_brought_forward_lbp']:,.0f} LBP ({result['credit_source']})", f"Deduction ratio: {result.get('ratio_source', '')}"] + [f"Check: {w}" for w in result.get("warnings", [])]
        if result["review_excluded"]: notes.append(f"{result['review_excluded']} document(s) in Review status are not included")
        if result["skipped"]: notes.append(f"{len(result['skipped'])} document(s) have an unreadable date: {', '.join(map(str, result['skipped'][:5]))}")
        if result["changed_since_saved"]: notes.append("Documents changed after this return was saved - review and save again")
        if result["currency_filter"] != "All": notes.append("Currency filter active: payable/credit totals cover this currency only")
        self.vat_note.config(text="   |   ".join(notes))
        self.vat_documents_tree.delete(*self.vat_documents_tree.get_children())
        for d in result["documents"]:
            self.vat_documents_tree.insert("", "end", values=(_display(d["date"]), d["number"], d["party"], f'{vat_rules.CATEGORIES[d["category"]]} ({d.get("treatment", "standard").replace("_", " ")})', d.get("deductible_share") or ("Yes" if d["recoverable"] else "No"),
                d["currency"], _fmt(d["base"]), _fmt(d["vat"]), _fmt(d["lbp_rate"]), _fmt(d["vat_lbp"]), d["status"]))
        self.vat_adjustment_rows = {str(a["id"]): a for a in result["adjustments"]}
        self.vat_adjustments_tree.delete(*self.vat_adjustments_tree.get_children())
        for a in result["adjustments"]:
            self.vat_adjustments_tree.insert("", "end", iid=str(a["id"]), values=(vat_rules.ADJUSTMENT_TYPES[a["adjustment_type"]], a["currency"], _fmt(float(a["amount"])),
                _fmt(a.get("amount_lbp", "")), a["reason"], a.get("created_by_name") or "", str(a["created_at"])[:16].replace("T", " ")))
        self.vat_history_tree.delete(*self.vat_history_tree.get_children())
        for row in history:
            self.vat_history_tree.insert("", "end", values=(f"Q{row['quarter']} {row['year']}", _fmt(float(row["net_lbp"])), _fmt(float(row["credit_brought_forward_lbp"])),
                _fmt(float(row["payable_lbp"])), _fmt(float(row["credit_carried_forward_lbp"])), row.get("saved_by_name") or "", str(row["saved_at"])[:16].replace("T", " ")))

    def add_vat_adjustment(self):
        try:
            year, quarter, _currency, _credit = self.vat_parameters()
            kind = {"Output VAT": "output", "Deductible VAT": "input", "Non-deductible VAT": "non_deductible"}[self.vat_adj_type.get()]
            amount = self.vat_adj_amount.get().strip().replace(",", "")
            if not amount: raise ValueError("Enter the adjustment amount (use a minus sign to reduce VAT)")
            self.client.add_vat_adjustment({"year": year, "quarter": quarter, "adjustment_type": kind, "currency": self.vat_adj_currency.get(),
                                            "amount": amount, "reason": self.vat_adj_reason.get().strip()})
        except Exception as exc: return messagebox.showerror("VAT Adjustment", str(exc))
        self.vat_adj_amount.set(""); self.vat_adj_reason.set(""); self.load_vat_return()

    def delete_vat_adjustment(self):
        selected = self.vat_adjustments_tree.selection()
        if not selected: return messagebox.showwarning("VAT Adjustment", "Select an adjustment first")
        record = getattr(self, "vat_adjustment_rows", {}).get(selected[0])
        if not record or not messagebox.askyesno("VAT Adjustment", f"Delete the adjustment '{record['reason']}'?"): return
        try: self.client.delete_vat_adjustment(record["id"])
        except Exception as exc: return messagebox.showerror("VAT Adjustment", str(exc))
        self.load_vat_return()

    def save_vat_return(self):
        try: year, quarter, _currency, credit = self.vat_parameters()
        except Exception as exc: return messagebox.showerror("Quarterly VAT", str(exc))
        if not messagebox.askyesno("Save VAT Return", f"Save the Q{quarter} {year} return for all currencies? Adjustments for this quarter will be locked, "
                                   "and the credit carried forward will be used by the next quarter."): return
        try: result = self.client.save_vat_return(year, quarter, credit, self._vat_refund_value)
        except Exception as exc: return messagebox.showerror("Quarterly VAT", str(exc))
        self.vat_currency.set("All Currencies"); self.load_vat_return()
        messagebox.showinfo("Quarterly VAT", f"Q{quarter} {year} saved. Payable: {result['payable_lbp']:,.0f} LBP   Credit carried forward: {result['credit_carried_forward_lbp']:,.0f} LBP")

    def save_vat_ratio(self):
        try: year = int(self.vat_year.get().strip()); saved = self.client.save_vat_ratio(year, self.vat_ratio.get().strip())
        except Exception as exc: return messagebox.showerror("Deduction ratio", str(exc))
        messagebox.showinfo("Deduction ratio", f"Provisional deduction ratio for {year}: {float(saved) * 100:.2f}%. Q4 always uses the final annual ratio." if saved is not None
                            else f"No provisional ratio for {year}: Q1-Q3 use the year-to-date turnover.")
        self.load_vat_return()

    def reopen_vat_return(self):
        try: year, quarter, _currency, _credit = self.vat_parameters()
        except Exception as exc: return messagebox.showerror("Quarterly VAT", str(exc))
        if not messagebox.askyesno("Reopen VAT Return", f"Reopen Q{quarter} {year}? It will need to be saved again after changes."): return
        try: self.client.reopen_vat_return(year, quarter)
        except Exception as exc: return messagebox.showerror("Quarterly VAT", str(exc))
        self.load_vat_return()

    def export_vat_return(self, format_name):
        result = getattr(self, "vat_return_result", None)
        if not result: return messagebox.showwarning("Quarterly VAT", "Generate the return first")
        title, meta, sections = vat_rules.export_sections(result)
        self.save_sections(title, meta, sections, f"VAT_Return_Q{result['quarter']}_{result['year']}", format_name)

    def toggle_selected_invoice_vat(self):
        selected = self.invoice_tree.selection()
        if not selected: return messagebox.showwarning("VAT Deductibility", "Select a purchase or expense row first")
        row = getattr(self, "invoice_rows", {}).get(selected[0])
        if not row: return
        if row.get("kind") != "purchase": return messagebox.showwarning("VAT Deductibility", "Only purchase and expense VAT can be marked non-deductible")
        recoverable = bool(row.get("vat_recoverable", 1))
        action = "NON-DEDUCTIBLE (the VAT becomes part of the cost)" if recoverable else "DEDUCTIBLE again"
        if not messagebox.askyesno("VAT Deductibility", f"Mark the VAT of {row['invoice_number']} ({float(row.get('vat') or 0):,.2f} {row['currency']}) as {action}?"): return
        try: self.client.set_vat_recoverable("invoice", row["id"], not recoverable)
        except Exception as exc: return messagebox.showerror("VAT Deductibility", str(exc))
        self.load_invoices(); self.load_journal(); self.load_trial()

    # ------------------------------------------------------------ users: expiry and permissions
    def build_users_page(self, users):
        form = tk.Frame(users, bg=LIGHT); form.pack(fill="x", padx=10, pady=10)
        self.user_name = tk.StringVar(); self.user_password = tk.StringVar(); self.user_role = tk.StringVar(value="accountant"); self.user_language = tk.StringVar(value="en")
        self.user_expiry = tk.StringVar(value=(datetime.now() + timedelta(days=365)).strftime("%d-%m-%Y"))
        self.user_active = tk.BooleanVar(value=True); self.user_payroll = tk.BooleanVar(value=True); self.user_vat = tk.BooleanVar(value=True); self.edit_user_id = None
        fields = (("Username", self.user_name, 16, ""), ("Password", self.user_password, 14, "*"))
        for column, (label, var, width, show) in enumerate(fields):
            tk.Label(form, text=label, bg=LIGHT).grid(row=0, column=column * 2, padx=4, sticky="w")
            tk.Entry(form, textvariable=var, width=width, show=show).grid(row=0, column=column * 2 + 1, padx=4)
        tk.Label(form, text="Role", bg=LIGHT).grid(row=0, column=4, padx=4, sticky="w")
        ttk.Combobox(form, textvariable=self.user_role, values=["admin", "accountant", "viewer"], state="readonly", width=11).grid(row=0, column=5, padx=4)
        tk.Label(form, text="Language", bg=LIGHT).grid(row=0, column=6, padx=4, sticky="w")
        ttk.Combobox(form, textvariable=self.user_language, values=["en", "ar", "fr"], state="readonly", width=5).grid(row=0, column=7, padx=4)
        tk.Label(form, text="Valid until", bg=LIGHT).grid(row=1, column=0, padx=4, pady=6, sticky="w")
        self.date_entry(form, self.user_expiry, 12).grid(row=1, column=1, padx=4, pady=6, sticky="w")
        tk.Checkbutton(form, text="Active", variable=self.user_active, bg=LIGHT).grid(row=1, column=2, sticky="w")
        tk.Checkbutton(form, text="Payroll access", variable=self.user_payroll, bg=LIGHT).grid(row=1, column=3, sticky="w")
        tk.Checkbutton(form, text="VAT access", variable=self.user_vat, bg=LIGHT).grid(row=1, column=4, sticky="w")
        buttons = tk.Frame(form, bg=LIGHT); buttons.grid(row=1, column=5, columnspan=4, sticky="w")
        self.action_button(buttons, "Save User", self.add_user).pack(side="left", padx=3)
        self.action_button(buttons, "Renew 1 Year", self.renew_selected_user).pack(side="left", padx=3)
        self.action_button(buttons, "New / Clear", self.clear_user_form).pack(side="left", padx=3)
        tk.Label(users, text="Roles: Admin = everything; Accountant = enter and post; Viewer = read only. New non-admin users are valid for 1 year; "
                 "leave 'Valid until' empty for no expiry. Payroll and VAT access can be removed per user.", bg=LIGHT, fg=MUTED, wraplength=1050, justify="left").pack(fill="x", padx=12)
        self.users_tree = self.table(users, [("id", "ID", 50), ("username", "Username", 160), ("role", "Role", 95), ("language", "Language", 70), ("status", "Status", 80),
            ("expires", "Valid Until", 95), ("days", "Days Left", 75), ("payroll", "Payroll", 65), ("vat", "VAT", 55)])
        self.users_tree.tag_configure("expired", foreground=RED); self.users_tree.tag_configure("soon", foreground=AMBER)
        self.users_tree.bind("<Double-1>", lambda _event: self.edit_selected_user())

    def clear_user_form(self):
        self.edit_user_id = None; self.user_name.set(""); self.user_password.set(""); self.user_role.set("accountant"); self.user_active.set(True)
        self.user_payroll.set(True); self.user_vat.set(True)
        self.user_expiry.set((datetime.now() + timedelta(days=365)).strftime("%d-%m-%Y"))

    def fill_users_tree(self, users):
        self.user_rows = {str(row["id"]): row for row in users}
        self.users_tree.delete(*self.users_tree.get_children())
        for row in users:
            days = row.get("days_remaining"); tag = "expired" if row.get("status") == "expired" else "soon" if days is not None and days <= 30 else ""
            permissions = row.get("permissions") or {}
            self.users_tree.insert("", "end", iid=str(row["id"]), values=(row["id"], row["username"], row["role"], row["language"], str(row.get("status", "")).title(),
                _display(row.get("expires_at")) or "No expiry", "" if days is None else days, "Yes" if row["role"] == "admin" or permissions.get("payroll", True) else "No",
                "Yes" if row["role"] == "admin" or permissions.get("vat", True) else "No"), tags=(tag,) if tag else ())

    def user_payload(self):
        expiry = self.user_expiry.get().strip()
        if expiry: _user_date(expiry)
        return {"id": self.edit_user_id, "username": self.user_name.get().strip(), "password": self.user_password.get(), "role": self.user_role.get(),
                "language": self.user_language.get(), "active": self.user_active.get(), "expires_at": expiry,
                "permissions": {"payroll": self.user_payroll.get(), "vat": self.user_vat.get()}}

    def add_user(self):
        try: payload = self.user_payload(); saved = self.client.save_user(payload)
        except Exception as exc: return messagebox.showerror("Users", str(exc))
        self.clear_user_form(); self.load_settings_pages()
        messagebox.showinfo("Users", f"User {saved['username']} saved. Valid until: {_display(saved.get('expires_at')) or 'no expiry'}")

    def renew_selected_user(self):
        selected = self.users_tree.selection()
        if not selected: return messagebox.showwarning("Users", "Select a user to renew")
        row = self.user_rows.get(selected[0])
        try:
            saved = self.client.save_user({"id": row["id"], "username": row["username"], "role": row["role"], "language": row["language"],
                                           "active": True, "permissions": row.get("permissions") or {}, "renew": True})
        except Exception as exc: return messagebox.showerror("Users", str(exc))
        self.load_settings_pages(); messagebox.showinfo("Users", f"{saved['username']} renewed until {_display(saved.get('expires_at'))}")

    def edit_selected_user(self):
        selected = self.users_tree.selection()
        if not selected: return
        row = self.user_rows.get(selected[0])
        if not row: return
        self.edit_user_id = row["id"]; self.user_name.set(row["username"]); self.user_role.set(row["role"]); self.user_language.set(row["language"])
        self.user_password.set(""); self.user_active.set(bool(row["active"])); self.user_expiry.set(_display(row.get("expires_at")))
        permissions = row.get("permissions") or {}; self.user_payroll.set(permissions.get("payroll", True)); self.user_vat.set(permissions.get("vat", True))
