"""Departments, projects and budgets (version 1.15)."""
from __future__ import annotations

import tkinter as tk
import calendar
from collections import defaultdict
from datetime import datetime
from tkinter import messagebox, ttk

from desktop_brains import EditableSheet

NAVY, GOLD, LIGHT = "#071b2e", "#c9a96a", "#f3f6f8"
RED, MUTED = "#8B1E1E", "#5f6b76"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
NONE = "(none)"


def _num(value):
    try: return float(str(value or 0).replace(",", ""))
    except ValueError: return None


class DimensionsMixin:
    # ------------------------------------------------------------ shared lists
    def dimension_lists(self, refresh=False):
        if refresh or not getattr(self, "_dimensions", None):
            try: departments = self.client.departments(); projects = self.client.projects()
            except Exception: departments, projects = [], []
            self._dimensions = {"departments": departments, "projects": projects}
        return self._dimensions

    def department_choices(self, include_all=False):
        items = [f'{d["code"]} - {d["name"]}' for d in self.dimension_lists()["departments"] if d["active"]]
        return (["All"] if include_all else [NONE]) + items

    def project_choices(self, include_all=False):
        items = [f'{p["code"]} - {p["name"]}' for p in self.dimension_lists()["projects"] if p["active"] and p["status"] != "cancelled"]
        return (["All"] if include_all else [NONE]) + items

    @staticmethod
    def dimension_code(value):
        text = str(value or "").strip()
        return "" if text in ("", NONE, "All") else text.split(" - ", 1)[0].strip()

    def dimension_selectors(self, parent, department_var, project_var, include_all=False):
        dep_group = tk.Frame(parent, bg=LIGHT); dep_group.pack(side="left")
        project_group = tk.Frame(parent, bg=LIGHT); project_group.pack(side="left")
        self._dimension_groups.append((dep_group, project_group, department_var, project_var, include_all))
        tk.Label(dep_group, text="Department", bg=LIGHT).pack(side="left")
        department = ttk.Combobox(dep_group, textvariable=department_var, values=self.department_choices(include_all), state="readonly", width=20); department.pack(side="left", padx=(4, 10))
        tk.Label(project_group, text="Project", bg=LIGHT).pack(side="left")
        project = ttk.Combobox(project_group, textvariable=project_var, values=self.project_choices(include_all), state="readonly", width=21); project.pack(side="left", padx=(4, 10))
        def refresh(_event=None):
            self.dimension_lists(refresh=True); department["values"] = self.department_choices(include_all); project["values"] = self.project_choices(include_all)
        department.bind("<Button-1>", refresh, add="+"); project.bind("<Button-1>", refresh, add="+")
        if not department_var.get(): department_var.set("All" if include_all else NONE)
        if not project_var.get(): project_var.set("All" if include_all else NONE)
        if not self.show_department.get(): dep_group.pack_forget()
        if not self.show_project.get(): project_group.pack_forget()
        return department, project

    def toggle_dimensions(self):
        for dep_group, project_group, department, project, include_all in self._dimension_groups:
            for group, visible, variable in ((dep_group, self.show_department.get(), department),
                                              (project_group, self.show_project.get(), project)):
                if not group.winfo_exists(): continue
                if visible:
                    if not group.winfo_manager(): group.pack(side="left")
                else:
                    if include_all: variable.set("All")
                    group.pack_forget()
        for sheet in self._dimension_sheets:
            if sheet.tree.winfo_exists(): sheet.set_dimension_visibility(self.show_department.get(), self.show_project.get())

    # ------------------------------------------------------------ settings pages
    def build_dimensions_pages(self, nested):
        departments = tk.Frame(nested, bg=LIGHT); projects = tk.Frame(nested, bg=LIGHT)
        nested.add(departments, text="Departments"); nested.add(projects, text="Projects")
        for page, label, variable in ((departments, "Show Department in all sheets", self.show_department),
                                      (projects, "Show Project in all sheets", self.show_project)):
            tk.Checkbutton(page, text=label, variable=variable,
                           command=self.toggle_dimensions, bg=LIGHT, fg=NAVY,
                           font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(8, 0))
        self.dep_id = None; self.dep_code = tk.StringVar(); self.dep_name = tk.StringVar(); self.dep_active = tk.BooleanVar(value=True)
        form = tk.Frame(departments, bg=LIGHT); form.pack(fill="x", padx=10, pady=10)
        tk.Label(form, text="Code (blank = automatic)", bg=LIGHT).pack(side="left"); tk.Entry(form, textvariable=self.dep_code, width=10).pack(side="left", padx=(4, 10))
        tk.Label(form, text="Department Name", bg=LIGHT).pack(side="left"); tk.Entry(form, textvariable=self.dep_name, width=30).pack(side="left", padx=(4, 10))
        tk.Checkbutton(form, text="Active", variable=self.dep_active, bg=LIGHT).pack(side="left", padx=4)
        self.action_button(form, "New", self.new_department).pack(side="left", padx=3)
        tk.Button(form, text="Save", command=self.save_department, bg=GOLD, fg=NAVY, border=0, padx=16, pady=7, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
        self.departments_tree = self.table(departments, [("code", "Code", 90), ("name", "Department", 300), ("active", "Active", 70)])
        self.departments_tree.bind("<Double-1>", lambda _e: self.edit_department())
        self.proj_id = None
        self.proj_vars = {k: tk.StringVar() for k in ("code", "name", "party", "start_date", "end_date", "notes")}; self.proj_status = tk.StringVar(value="open"); self.proj_active = tk.BooleanVar(value=True)
        form = tk.LabelFrame(projects, text="Project", bg=LIGHT, padx=8, pady=6); form.pack(fill="x", padx=10, pady=10)
        entries = (("code", "Code (blank = automatic)", 12), ("name", "Project Name", 30), ("start_date", "Start Date", 11), ("end_date", "End Date", 11), ("notes", "Notes", 30))
        for index, (key, label, width) in enumerate(entries):
            tk.Label(form, text=label, bg=LIGHT).grid(row=index // 3, column=(index % 3) * 2, sticky="w", padx=4, pady=3)
            widget = self.date_entry(form, self.proj_vars[key], width) if key.endswith("date") else tk.Entry(form, textvariable=self.proj_vars[key], width=width)
            widget.grid(row=index // 3, column=(index % 3) * 2 + 1, sticky="w", padx=4, pady=3)
        tk.Label(form, text="Customer", bg=LIGHT).grid(row=1, column=4, sticky="w", padx=4)
        self.proj_party_box = ttk.Combobox(form, textvariable=self.proj_vars["party"], width=28); self.proj_party_box.grid(row=1, column=5, sticky="w", padx=4)
        tk.Label(form, text="Status", bg=LIGHT).grid(row=2, column=0, sticky="w", padx=4)
        ttk.Combobox(form, textvariable=self.proj_status, values=["open", "on hold", "completed", "cancelled"], state="readonly", width=12).grid(row=2, column=1, sticky="w", padx=4)
        tk.Checkbutton(form, text="Active", variable=self.proj_active, bg=LIGHT).grid(row=2, column=2, sticky="w")
        buttons = tk.Frame(form, bg=LIGHT); buttons.grid(row=2, column=3, columnspan=3, sticky="w")
        self.action_button(buttons, "New", self.new_project).pack(side="left", padx=3)
        tk.Button(buttons, text="Save", command=self.save_project, bg=GOLD, fg=NAVY, border=0, padx=16, pady=7, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
        self.projects_tree = self.table(projects, [("code", "Code", 95), ("name", "Project", 230), ("party", "Customer", 180), ("start", "Start", 90), ("end", "End", 90), ("status", "Status", 90), ("active", "Active", 60)])
        self.projects_tree.bind("<Double-1>", lambda _e: self.edit_project())
        self.load_dimensions_pages()

    def load_dimensions_pages(self):
        if not hasattr(self, "departments_tree"): return
        lists = self.dimension_lists(refresh=True)
        self.departments_tree.delete(*self.departments_tree.get_children())
        for d in lists["departments"]: self.departments_tree.insert("", "end", iid=str(d["id"]), values=(d["code"], d["name"], "Yes" if d["active"] else "No"))
        self.projects_tree.delete(*self.projects_tree.get_children())
        for p in lists["projects"]:
            self.projects_tree.insert("", "end", iid=str(p["id"]), values=(p["code"], p["name"], p.get("party_name") or "", self._dd(p.get("start_date")), self._dd(p.get("end_date")), p["status"].title(), "Yes" if p["active"] else "No"))
        try: self.proj_party_box["values"] = [p["name"] for p in self.client.parties() if p["kind"] in ("customer", "both")]
        except Exception: pass

    @staticmethod
    def _dd(value):
        text = str(value or "")
        return f"{text[8:10]}-{text[5:7]}-{text[:4]}" if len(text) == 10 and text[4] == "-" else text

    def new_department(self): self.dep_id = None; self.dep_code.set(""); self.dep_name.set(""); self.dep_active.set(True)

    def edit_department(self):
        selected = self.departments_tree.selection()
        if not selected: return
        d = next(d for d in self.dimension_lists()["departments"] if str(d["id"]) == selected[0])
        self.dep_id = d["id"]; self.dep_code.set(d["code"]); self.dep_name.set(d["name"]); self.dep_active.set(bool(d["active"]))

    def save_department(self):
        try: saved = self.client.save_department({"id": self.dep_id, "code": self.dep_code.get(), "name": self.dep_name.get(), "active": self.dep_active.get()})
        except Exception as exc: return messagebox.showerror("Departments", str(exc))
        self.new_department(); self.load_dimensions_pages(); messagebox.showinfo("Departments", f'Department {saved["code"]} - {saved["name"]} saved')

    def new_project(self):
        self.proj_id = None; [v.set("") for v in self.proj_vars.values()]; self.proj_status.set("open"); self.proj_active.set(True)

    def edit_project(self):
        selected = self.projects_tree.selection()
        if not selected: return
        p = next(p for p in self.dimension_lists()["projects"] if str(p["id"]) == selected[0]); self.proj_id = p["id"]
        for key, value in (("code", p["code"]), ("name", p["name"]), ("party", p.get("party_name") or ""), ("start_date", self._dd(p.get("start_date"))),
                           ("end_date", self._dd(p.get("end_date"))), ("notes", p.get("notes") or "")): self.proj_vars[key].set(value)
        self.proj_status.set(p["status"]); self.proj_active.set(bool(p["active"]))

    def save_project(self):
        payload = {key: var.get().strip() for key, var in self.proj_vars.items()}
        payload.update(id=self.proj_id, party_name=payload.pop("party"), status=self.proj_status.get(), active=self.proj_active.get())
        try: saved = self.client.save_project(payload)
        except Exception as exc: return messagebox.showerror("Projects", str(exc))
        self.new_project(); self.load_dimensions_pages(); messagebox.showinfo("Projects", f'Project {saved["code"]} - {saved["name"]} saved')

    # ------------------------------------------------------------ budget page
    def build_budget_page(self, nested):
        page = tk.Frame(nested, bg=LIGHT); nested.add(page, text="Budget")
        year = getattr(self, "current_fiscal_year", datetime.now().year)
        self.budget_year = tk.StringVar(value=str(year)); self.budget_currency = tk.StringVar(value="USD")
        self.budget_department = tk.StringVar(value=NONE); self.budget_project = tk.StringVar(value=NONE); self.budget_upto = tk.StringVar(value="Dec")
        bar = tk.Frame(page, bg=LIGHT); bar.pack(fill="x", padx=10, pady=8)
        tk.Label(bar, text="Year", bg=LIGHT).pack(side="left"); tk.Entry(bar, textvariable=self.budget_year, width=6).pack(side="left", padx=(4, 10))
        tk.Label(bar, text="Currency", bg=LIGHT).pack(side="left")
        ttk.Combobox(bar, textvariable=self.budget_currency, values=self.currency_codes, state="readonly", width=6).pack(side="left", padx=(4, 10))
        self.dimension_selectors(bar, self.budget_department, self.budget_project)
        tk.Button(bar, text="Load", command=self.load_budget, bg=GOLD, fg=NAVY, border=0, padx=14, pady=6, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
        tk.Button(bar, text="Save Budget", command=self.save_budget, bg=NAVY, fg="white", border=0, padx=14, pady=6).pack(side="left", padx=3)
        self.budget_projection_mode=tk.StringVar(value="Monthly")
        ttk.Combobox(bar,textvariable=self.budget_projection_mode,values=["Monthly","Yearly"],state="readonly",width=9).pack(side="left",padx=3)
        self.action_button(bar,"Project from Actual",self.project_budget).pack(side="left",padx=3)
        forecast_bar=tk.Frame(page,bg=LIGHT); forecast_bar.pack(fill="x",padx=10,pady=(0,5))
        self.budget_forecast_year=tk.StringVar(value=str(year)); self.budget_forecast_horizon=tk.StringVar(value="Quarter (3 months)")
        tk.Label(forecast_bar,text="Actual report year",bg=LIGHT).pack(side="left")
        tk.Entry(forecast_bar,textvariable=self.budget_forecast_year,width=6).pack(side="left",padx=(4,10))
        tk.Label(forecast_bar,text="Project ahead",bg=LIGHT).pack(side="left")
        ttk.Combobox(forecast_bar,textvariable=self.budget_forecast_horizon,
                     values=["Quarter (3 months)","6 Months","Yearly (12 months)"],state="readonly",width=21).pack(side="left",padx=(4,10))
        self.action_button(forecast_bar,"Year & Future Forecast",self.budget_year_forecast).pack(side="left",padx=3)
        for label,mode in (("Excel","xlsx"),("PDF","pdf"),("Print","print")):
            self.action_button(forecast_bar,label,lambda fmt=mode:self.export_budget_forecast(fmt)).pack(side="left",padx=2)
        tk.Label(forecast_bar,text="Company-wide actuals; trailing 3 complete months estimate the future.",bg=LIGHT,fg=MUTED).pack(side="left",padx=10)
        long_bar=tk.Frame(page,bg=LIGHT); long_bar.pack(fill="x",padx=10,pady=(0,5))
        self.budget_long_target=tk.StringVar(value=""); self.budget_long_growth=tk.StringVar(value="0"); self.budget_long_growth_by_year=tk.StringVar(value="")
        tk.Label(long_bar,text="5-Year Projection to date (DD-MM-YYYY)",bg=LIGHT).pack(side="left")
        tk.Entry(long_bar,textvariable=self.budget_long_target,width=12).pack(side="left",padx=(4,10))
        tk.Label(long_bar,text="Growth % per year",bg=LIGHT).pack(side="left")
        tk.Entry(long_bar,textvariable=self.budget_long_growth,width=7).pack(side="left",padx=(4,10))
        tk.Label(long_bar,text="Per-year % (e.g. 2027=10, 2028=5)",bg=LIGHT).pack(side="left")
        tk.Entry(long_bar,textvariable=self.budget_long_growth_by_year,width=22).pack(side="left",padx=(4,10))
        self.action_button(long_bar,"5-Year Projection",self.budget_long_term_projection).pack(side="left",padx=3)
        tk.Label(long_bar,text="Uses the Actual report year above as the base year; a saved budget for a future year wins over the growth %.",bg=LIGHT,fg=MUTED).pack(side="left",padx=10)
        tools = tk.Frame(page, bg=LIGHT); tools.pack(fill="x", padx=10)
        self.action_button(tools, "Add Account", self.add_budget_line).pack(side="left", padx=(0, 3))
        tk.Button(tools, text="Delete Line", command=self.delete_budget_line, bg=RED, fg="white", border=0, padx=12, pady=7).pack(side="left", padx=3)
        self.action_button(tools, "Spread Annual over 12 Months", self.spread_budget_line).pack(side="left", padx=3)
        tk.Label(tools, text="Compare up to", bg=LIGHT).pack(side="left", padx=(20, 4))
        ttk.Combobox(tools, textvariable=self.budget_upto, values=MONTHS, state="readonly", width=5).pack(side="left")
        tk.Button(tools, text="Budget vs Actual", command=self.budget_vs_actual, bg=GOLD, fg=NAVY, border=0, padx=14, pady=6, font=("Segoe UI", 9, "bold")).pack(side="left", padx=6)
        tk.Label(page, text="Type an account number (F2 to search), then either an Annual amount or the monthly amounts. An annual budget alone is spread evenly over the year. "
                 "Leave Department and Project as (none) for the company budget.", bg=LIGHT, fg=MUTED, wraplength=1100, justify="left").pack(fill="x", padx=12, pady=(4, 0))
        columns = [("line", "#", 40, "center"), ("account", "Account", 105, "w"), ("account_name", "Account Name", 190, "w"), ("annual", "Annual", 105, "e")] + \
                  [(m.lower(), m, 78, "e") for m in MONTHS] + [("total", "Months Total", 105, "e")]
        self.budget_sheet = EditableSheet(self, page, columns, ["account", "annual"] + [m.lower() for m in MONTHS], self.budget_cell_changed, height=7, lookup_column="account")
        self.budget_total_label = tk.Label(page, text="", bg=LIGHT, fg=NAVY, font=("Segoe UI", 10, "bold")); self.budget_total_label.pack(anchor="e", padx=14)
        self.budget_viewer = self.report_viewer(page)
        self.budget_viewer.configure(height=7)

    def budget_row(self, code="", name="", annual=0.0, months=None):
        row = {"account": code, "account_name": name, "annual": annual, **{m.lower(): v for m, v in zip(MONTHS, months or [0.0] * 12)}}
        return self.format_budget_row(row)

    def format_budget_row(self, row):
        total = sum(_num(row[m.lower()]) or 0 for m in MONTHS); row["total"] = f"{total:,.2f}"
        row["_display"] = {"annual": f"{_num(row['annual']) or 0:,.2f}", **{m.lower(): (f"{_num(row[m.lower()]):,.2f}" if _num(row[m.lower()]) else "") for m in MONTHS}}
        return row

    def budget_cell_changed(self, iid, key, text):
        row = self.budget_sheet.rows[iid]
        if key == "account":
            code = text.split(" - ", 1)[0].strip(); account = self.account_by_code(code) if code else None
            if code and not account: messagebox.showwarning("Budget", f"Account {code} was not found. Press F2 in the cell to search."); return False
            row["account"] = code; row["account_name"] = account["name_en"] if account else ""
        else:
            value = _num(text)
            if value is None or value < 0: messagebox.showwarning("Budget", "Enter a positive number"); return False
            row[key] = value
        self.format_budget_row(row); self.update_budget_total()

    def update_budget_total(self):
        rows = self.budget_sheet.ordered(); annual = sum(_num(r["annual"]) or 0 for r in rows); months = sum(sum(_num(r[m.lower()]) or 0 for m in MONTHS) for r in rows)
        self.budget_total_label.config(text=f"Total annual: {annual:,.2f}    Total of months: {months:,.2f} {self.budget_currency.get()}")

    def add_budget_line(self):
        iid = self.budget_sheet.insert(self.budget_row()); self.budget_sheet.tree.selection_set(iid); self.budget_sheet.tree.focus(iid)
        self.after(30, lambda: self.budget_sheet.edit(iid, "account"))

    def delete_budget_line(self):
        if not self.budget_sheet.delete_selected(): return messagebox.showwarning("Budget", "Select a line first")
        self.update_budget_total()

    def spread_budget_line(self):
        iid, row = self.budget_sheet.selected()
        if not row: return messagebox.showwarning("Budget", "Select a line first")
        annual = _num(row["annual"]) or 0
        if not annual: return messagebox.showwarning("Budget", "Enter the Annual amount first")
        share = round(annual / 12, 2)
        for index, month in enumerate(MONTHS): row[month.lower()] = share if index < 11 else round(annual - share * 11, 2)
        self.format_budget_row(row); self.budget_sheet.refresh(iid); self.update_budget_total()

    def budget_filters(self):
        try: year = int(self.budget_year.get())
        except ValueError: raise ValueError("Enter the budget year, for example 2025")
        return year, self.budget_currency.get(), self.dimension_code(self.budget_department.get()), self.dimension_code(self.budget_project.get())

    def load_budget(self):
        try: year, currency, department, project = self.budget_filters(); lines = self.client.budgets(year, currency, department or None, project or None)
        except Exception as exc: return messagebox.showerror("Budget", str(exc))
        self.budget_sheet.clear()
        for line in lines: self.budget_sheet.insert(self.budget_row(line["account_code"], line["account_name"], line["annual"], line["months"]))
        if not lines: self.budget_sheet.insert(self.budget_row())
        self.update_budget_total()

    def project_budget(self):
        try: target_year,currency,_department,_project=self.budget_filters()
        except Exception as exc: return messagebox.showerror("Budget Projection",str(exc))
        source_year=int(self.current_fiscal_year)
        if target_year<source_year or target_year>source_year+1:
            return messagebox.showwarning("Budget Projection",f"Choose {source_year} or {source_year+1} as the budget year")
        now=datetime.now(); last_month=min(12,now.month if source_year==now.year else 12)
        if source_year==now.year: last_month=max(0,now.month-1)  # complete months only
        if last_month<1: return messagebox.showwarning("Budget Projection","No complete actual month is available yet")
        actual=defaultdict(dict); names={}
        try:
            for month in range(1,last_month+1):
                last=calendar.monthrange(source_year,month)[1]
                rows=self.client.profit_loss(f"{source_year}-{month:02d}-01",f"{source_year}-{month:02d}-{last:02d}",currency)
                for row in rows:
                    if row["type"] not in ("income","expense"): continue
                    actual[row["code"]][month]=max(0,float(row["amount"])); names[row["code"]]=row["name_en"]
        except Exception as exc: return messagebox.showerror("Budget Projection",str(exc))
        if not actual: return messagebox.showwarning("Budget Projection","No posted income or expense data to project")
        if self.budget_sheet.ordered() and not messagebox.askyesno("Budget Projection","Replace the current draft budget rows with the projection? Nothing is saved until you press Save Budget."):
            return
        self.budget_sheet.clear(); mode=self.budget_projection_mode.get()
        for code,values in sorted(actual.items()):
            average=sum(values.get(month,0) for month in range(1,last_month+1))/last_month
            months=[]
            for month in range(1,13):
                if target_year==source_year and month<=last_month: amount=values.get(month,0)
                elif mode=="Monthly" and month in values: amount=values[month]
                else: amount=average
                months.append(round(amount,2))
            self.budget_sheet.insert(self.budget_row(code,names[code],round(sum(months),2),months))
        self.update_budget_total()
        messagebox.showinfo("Budget Projection",f"Draft based on {source_year} actual months 1–{last_month}. {mode} projection; review each account before saving.")

    def budget_year_forecast(self):
        from financial_projection import HORIZONS, completed_months, future_months, month_range, trailing_average
        try:
            year=int(self.budget_forecast_year.get())
            last=completed_months(year)
            future=future_months(year,last,HORIZONS[self.budget_forecast_horizon.get()])
        except (ValueError,KeyError) as exc: return messagebox.showwarning("Budget Forecast",str(exc))
        currency=self.budget_currency.get(); actual=defaultdict(dict); names={}; types={}
        try:
            for month in range(1,last+1):
                rows=self.client.profit_loss(*month_range(year,month),currency)
                for row in rows:
                    if row["type"] not in ("income","expense"): continue
                    code=row["code"]; actual[code][month]={"amount":float(row["amount"])}
                    names[code]=row["name_en"]; types[code]=row["type"]
        except Exception as exc: return messagebox.showerror("Budget Forecast",str(exc))
        if not actual: return messagebox.showwarning("Budget Forecast","No posted income or expense actuals in the report year")
        summary=[]; detail=[]
        for code,months in sorted(actual.items()):
            year_actual=sum(values["amount"] for values in months.values())
            monthly=trailing_average(months,last,"amount")
            projected=round(monthly*len(future),2)
            summary.append([code,names[code],types[code].title(),round(year_actual,2),projected,round(year_actual+projected,2)])
            for future_year,future_month in future:
                detail.append([f"{future_year}-{future_month:02d}",code,names[code],types[code].title(),round(monthly,2)])
        start=f"{future[0][0]}-{future[0][1]:02d}"; end=f"{future[-1][0]}-{future[-1][1]:02d}"
        self.budget_forecast_result={"title":f"Budget actual {year} and {self.budget_forecast_horizon.get()} forecast",
            "meta":[f"Currency: {currency}",f"Actual: Jan–{last:02d} {year}",f"Forecast: {start} to {end}","Forecast uses each account's last 3 complete months; company-wide actuals."],
            "sections":[{"heading":"Account actuals and forecast","headers":["Account","Account Name","Type","Actual year to date","Forecast period","Actual + forecast"],"rows":summary,"total_rows":[]},
                        {"heading":"Projected months","headers":["Month","Account","Account Name","Type","Amount"],"rows":detail,"total_rows":[]}]}
        self.show_sections(self.budget_viewer,self.budget_forecast_result["sections"])

    def budget_long_term_projection(self):
        from financial_projection import long_term_projection
        try: base_year=int(self.budget_forecast_year.get())
        except ValueError: return messagebox.showwarning("5-Year Projection","Enter the base year in \"Actual report year\", for example 2026")
        try: target_date=datetime.strptime(self.budget_long_target.get().strip(),"%d-%m-%Y").strftime("%Y-%m-%d")
        except ValueError: return messagebox.showwarning("5-Year Projection","Enter the target date as DD-MM-YYYY, for example 31-12-2030")
        growth_rate=(_num(self.budget_long_growth.get()) or 0)/100
        try: growth_by_year=self._parse_growth_by_year(self.budget_long_growth_by_year.get())
        except ValueError as exc: return messagebox.showwarning("5-Year Projection",str(exc))
        currency=self.budget_currency.get()
        try: actual_rows=self.client.profit_loss(f"01-01-{base_year}",f"31-12-{base_year}",currency)
        except Exception as exc: return messagebox.showerror("5-Year Projection",str(exc))
        base_values={}; names={}; types={}
        for row in actual_rows:
            if row["type"] not in ("income","expense"): continue
            base_values[row["code"]]=float(row["amount"]); names[row["code"]]=row["name_en"]; types[row["code"]]=row["type"]
        if not base_values: return messagebox.showwarning("5-Year Projection",f"No posted income or expense actuals in {base_year} to project from")
        budget_by_year={}
        try:
            for year in range(base_year+1,int(target_date[:4])+1):
                saved=self.client.budgets(year,currency)
                lines={line["account_code"]:_num(line["annual"]) or 0 for line in saved if line.get("account_code") in base_values}
                if lines: budget_by_year[year]=lines
        except Exception: pass  # a saved-budget lookup failure just falls back to the growth rate
        try: projection=long_term_projection(base_values,base_year,target_date,growth_rate,budget_by_year,growth_by_year=growth_by_year)
        except ValueError as exc: return messagebox.showwarning("5-Year Projection",str(exc))
        net_rows=[]; detail=[]
        for entry in projection:
            income=sum(v for c,v in entry["values"].items() if types.get(c)=="income")
            expense=sum(v for c,v in entry["values"].items() if types.get(c)=="expense")
            net_rows.append([entry["year"],entry["date_to"],entry["source"].title(),round(income,2),round(expense,2),round(income-expense,2)])
            for code,amount in sorted(entry["values"].items()):
                detail.append([entry["year"],entry["date_to"],code,names.get(code,code),types.get(code,"").title(),entry["source"].title(),round(amount,2)])
        self.budget_forecast_result={"title":f"Budget {base_year} to {target_date[8:10]}-{target_date[5:7]}-{target_date[0:4]} (5-Year Projection)",
            "meta":[f"Currency: {currency}",f"Base year actuals: {base_year}",f"Target date: {self.budget_long_target.get().strip()}",
                    f"Growth rate: {growth_rate*100:.2f}% per year where no saved budget exists for that year"]+(["Per-year growth overrides: "+", ".join(f"{y}={r*100:.2f}%" for y,r in sorted(growth_by_year.items()))] if growth_by_year else []),
            "sections":[{"heading":"Net income / expense by year","headers":["Year","Up to","Source","Income","Expense","Net"],"rows":net_rows,"total_rows":[]},
                        {"heading":"By account","headers":["Year","Up to","Account","Account Name","Type","Source","Amount"],"rows":detail,"total_rows":[]}]}
        self.show_sections(self.budget_viewer,self.budget_forecast_result["sections"])

    def export_budget_forecast(self,mode):
        if not getattr(self,"budget_forecast_result",None): self.budget_year_forecast()
        result=getattr(self,"budget_forecast_result",None)
        if result: self.output_sections(result["title"],result["meta"],result["sections"],"Budget_Year_Forecast",mode)

    def save_budget(self):
        try: year, currency, department, project = self.budget_filters()
        except Exception as exc: return messagebox.showerror("Budget", str(exc))
        lines = [{"account_code": r["account"], "annual": _num(r["annual"]) or 0, "months": [_num(r[m.lower()]) or 0 for m in MONTHS]} for r in self.budget_sheet.ordered() if r["account"]]
        for r in lines:
            if r["annual"] and any(r["months"]) and abs(sum(r["months"]) - r["annual"]) > 0.01:
                if not messagebox.askyesno("Budget", f"Account {r['account_code']}: the months add up to {sum(r['months']):,.2f}, not the annual {r['annual']:,.2f}. The monthly amounts will be used. Continue?"): return
        try: self.client.save_budget({"year": year, "currency": currency, "department": department, "project": project, "lines": lines})
        except Exception as exc: return messagebox.showerror("Budget", str(exc))
        self.load_budget(); messagebox.showinfo("Budget", f"Budget {year} ({currency}) saved for {len(lines)} account(s)")

    def budget_vs_actual(self):
        try: year, currency, department, project = self.budget_filters()
        except Exception as exc: return messagebox.showerror("Budget", str(exc))
        month = MONTHS.index(self.budget_upto.get()) + 1
        import calendar
        options = {"date_from": f"01-01-{year}", "date_to": f"{calendar.monthrange(year, month)[1]:02d}-{month:02d}-{year}", "first_column": currency, "second_column": "none",
                   "budget": True, "carry_forward": False, "profit_loss_only": True, "department": department, "project": project, "posting_status": "posted"}
        try: result = self.client.account_report(options)
        except Exception as exc: return messagebox.showerror("Budget", str(exc))
        self.budget_result = result; self.show_sections(self.budget_viewer, result["sections"])

    # ------------------------------------------------------------ balance panel additions
    def add_dimension_options(self, state, parent):
        box = tk.Frame(parent, bg=LIGHT); box.pack(fill="x", pady=(4, 0)); flags_row = tk.Frame(parent, bg=LIGHT); flags_row.pack(fill="x")
        state["vars"]["department"] = tk.StringVar(value="All"); state["vars"]["project"] = tk.StringVar(value="All")
        self.dimension_selectors(box, state["vars"]["department"], state["vars"]["project"], include_all=True); state["dimension_row"] = box
        for name, label in (("with_department", "Show Department / Project"), ("split_by_department", "Split by Department"),
                            ("split_by_project", "Split by Project"), ("budget", "Compare with Budget")):
            state["flags"][name] = tk.BooleanVar(value=False); tk.Checkbutton(flags_row, text=label, variable=state["flags"][name], bg=LIGHT).pack(side="left", padx=4)
