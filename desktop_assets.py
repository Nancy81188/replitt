"""Assets & Depreciation: 1. asset accounts with depreciation %, 2. data entry (existing form + category), 3. monthly depreciation table."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

NAVY, GOLD, LIGHT, RED = "#102A43", "#B78B45", "#F4F7FA", "#8B1E1E"


def _dd(value):
    text = str(value or "")
    return f"{text[8:10]}-{text[5:7]}-{text[:4]}" if len(text) >= 10 and text[4] == "-" else text


class AssetsMixin:
    # ------------------------------------------------------------ 1. asset accounts
    def build_asset_accounts_page(self, page):
        self.ac_vars = {k: tk.StringVar() for k in ("account_code", "name", "annual_rate", "depreciation_account", "accumulated_account")}
        form = tk.LabelFrame(page, text="Asset account (category) and its yearly depreciation %", bg=LIGHT, padx=8, pady=6); form.pack(fill="x", padx=8, pady=8)
        for index, (key, label, width) in enumerate((("account_code", "Asset account No.", 14), ("name", "Name (category)", 26), ("annual_rate", "Depreciation % / year", 8),
                                                     ("depreciation_account", "Depreciation expense account", 14), ("accumulated_account", "Accumulated depreciation account", 14))):
            tk.Label(form, text=label, bg=LIGHT).grid(row=index // 3, column=(index % 3) * 2, sticky="w", padx=4, pady=3)
            self.account_search_box(form, self.ac_vars[key], width).grid(row=index // 3, column=(index % 3) * 2 + 1, sticky="w", padx=4, pady=3) if "account" in key \
                else tk.Entry(form, textvariable=self.ac_vars[key], width=width).grid(row=index // 3, column=(index % 3) * 2 + 1, sticky="w", padx=4, pady=3)
        bar = tk.Frame(form, bg=LIGHT); bar.grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))
        tk.Button(bar, text="Save Account", command=self.save_asset_account, bg=GOLD, fg=NAVY, border=0, padx=14, pady=5, font=("Segoe UI", 9, "bold")).pack(side="left", padx=2)
        tk.Button(bar, text="New", command=lambda: [v.set("") for v in self.ac_vars.values()], bg=NAVY, fg="white", border=0, padx=12, pady=5).pack(side="left", padx=2)
        tk.Button(bar, text="Delete", command=self.delete_asset_account, bg=RED, fg="white", border=0, padx=12, pady=5).pack(side="left", padx=2)
        tk.Label(bar, text="Example: 2244 Vehicles 20% - expense 681 - accumulated 2824. Double-click a line to change it.", bg=LIGHT, fg="#5f6b76").pack(side="left", padx=10)
        self.ac_tree = self.table(page, [("code", "Asset Account", 110), ("name", "Name", 230), ("rate", "Depreciation %", 110), ("years", "Useful Life", 90),
                                         ("dep", "Expense Account", 120), ("acc", "Accumulated Account", 140)])
        self.ac_tree.bind("<Double-1>", lambda _e: self.edit_asset_account())
        self.load_asset_accounts()

    def load_asset_accounts(self):
        try: self.asset_categories_rows = self.client.asset_categories()
        except Exception: self.asset_categories_rows = []
        if hasattr(self, "ac_tree"):
            self.ac_tree.delete(*self.ac_tree.get_children())
            for c in self.asset_categories_rows:
                rate = float(c["annual_rate"]); self.ac_tree.insert("", "end", iid=c["account_code"], values=(c["account_code"], c["name"], f"{rate:g}%", f"{100 / rate:g} years",
                                                                                                            c["depreciation_account"], c["accumulated_account"]))
        labels = [f'{c["account_code"]} - {c["name"]} ({float(c["annual_rate"]):g}%)' for c in self.asset_categories_rows]
        for name in ("asset_category_box", "dt_account_box"):
            box = getattr(self, name, None)
            if box is not None and box.winfo_exists(): box["values"] = (["All accounts"] if name == "dt_account_box" else []) + labels

    def save_asset_account(self):
        try: self.client.save_asset_category({k: v.get().strip() for k, v in self.ac_vars.items()})
        except Exception as exc: return messagebox.showerror("Asset accounts", str(exc))
        [v.set("") for v in self.ac_vars.values()]; self.load_asset_accounts()

    def edit_asset_account(self):
        selected = self.ac_tree.selection()
        row = next((c for c in self.asset_categories_rows if c["account_code"] == (selected[0] if selected else None)), None)
        if row: [self.ac_vars[k].set(str(row[k])) for k in self.ac_vars]

    def delete_asset_account(self):
        code = self.ac_vars["account_code"].get().split(" - ", 1)[0].strip()
        if not code or not messagebox.askyesno("Asset accounts", f"Delete asset account {code}?"): return
        try: self.client.save_asset_category({"account_code": code, "delete": True})
        except Exception as exc: return messagebox.showerror("Asset accounts", str(exc))
        [v.set("") for v in self.ac_vars.values()]; self.load_asset_accounts()

    # ------------------------------------------------------------ 2. data entry: choose the category
    def add_asset_category_selector(self, page):
        bar = tk.Frame(page, bg="#e8eef4"); bar.pack(fill="x", padx=8, pady=(6, 0), before=page.winfo_children()[0])
        tk.Label(bar, text="Asset account (category)", bg="#e8eef4", fg=NAVY, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 4), pady=4)
        self.asset_category = tk.StringVar()
        self.asset_category_box = ttk.Combobox(bar, textvariable=self.asset_category, state="readonly", width=40); self.asset_category_box.pack(side="left", pady=4)
        self.asset_category_box.bind("<<ComboboxSelected>>", lambda _e: self.asset_category_chosen())
        tk.Label(bar, text="fills the accounts, the depreciation % and the useful life", bg="#e8eef4", fg="#5f6b76").pack(side="left", padx=8)
        self.load_asset_accounts()

    def asset_category_chosen(self):
        code = self.asset_category.get().split(" - ", 1)[0]
        row = next((c for c in getattr(self, "asset_categories_rows", []) if c["account_code"] == code), None)
        if not row: return
        fields = getattr(self, "asset_fields", {}); rate = float(row["annual_rate"])
        for key, value in (("asset_account", row["account_code"]), ("depreciation_account", row["depreciation_account"]), ("accumulated_account", row["accumulated_account"]),
                           ("useful_months", str(round(1200 / rate)))):
            if key in fields: fields[key].set(value)
        if hasattr(self, "asset_rate"): self.asset_rate.set(f"{rate:g}")

    # ------------------------------------------------------------ 3. monthly depreciation table
    def build_depreciation_table_page(self, page):
        year = getattr(self, "current_fiscal_year", datetime.now().year); month = datetime.now().month if str(datetime.now().year) == str(year) else 12
        self.dt_month = tk.StringVar(value=f"{28 if month == 2 else 30 if month in (4, 6, 9, 11) else 31:02d}-{month:02d}-{year}"); self.dt_account = tk.StringVar(value="All accounts")
        bar = tk.Frame(page, bg=LIGHT); bar.pack(fill="x", padx=8, pady=8)
        tk.Label(bar, text="Month (any date of the month)", bg=LIGHT).pack(side="left"); self.date_entry(bar, self.dt_month, 11).pack(side="left", padx=(4, 10))
        tk.Label(bar, text="Account", bg=LIGHT).pack(side="left")
        self.dt_account_box = ttk.Combobox(bar, textvariable=self.dt_account, state="readonly", width=34); self.dt_account_box.pack(side="left", padx=(4, 8))
        tk.Button(bar, text="Show", command=self.load_depreciation_table, bg=GOLD, fg=NAVY, border=0, padx=16, pady=5, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
        bar2 = tk.Frame(page, bg=LIGHT); bar2.pack(fill="x", padx=8, pady=(0, 4))
        tk.Button(bar2, text="Post Entry for Selected Account", command=self.post_depreciation_entry, bg=GOLD, fg=NAVY, border=0, padx=12, pady=5).pack(side="left", padx=(0, 3))
        tk.Button(bar2, text="Post All Accounts", command=lambda: self.post_depreciation_entry(all_accounts=True), bg=GOLD, fg=NAVY, border=0, padx=12, pady=5).pack(side="left", padx=3)
        for text, mode in (("Print Preview", "preview"), ("Excel", "xlsx"), ("PDF", "pdf")):
            tk.Button(bar2, text=text, command=lambda m=mode: self.export_depreciation_table(m), bg=NAVY, fg="white", border=0, padx=10, pady=5).pack(side="left", padx=2)
        self.dt_info = tk.Label(page, text="Each asset account shows its assets, then one depreciation entry per account (Dr expense / Cr accumulated).", bg=LIGHT, fg=NAVY, anchor="w")
        self.dt_info.pack(fill="x", padx=10)
        self.dt_tree = ttk.Treeview(page, columns=("code", "name", "date", "value", "old", "current", "total", "net", "posted"), show="headings")
        for key, label, width in (("code", "Asset / Account", 100), ("name", "Name", 160), ("date", "Purchase Date", 100), ("value", "Value", 95), ("old", "Old Deprec.", 92),
                                  ("current", "Deprec. (month)", 110), ("total", "Total Deprec.", 105), ("net", "Net Value", 95), ("posted", "Entry", 88)):
            self.dt_tree.heading(key, text=label); self.dt_tree.column(key, width=width, minwidth=60, stretch=False, anchor="w" if key in ("code", "name", "date", "posted") else "e")
        self.dt_tree.tag_configure("group", background="#dfe6ee", font=("Segoe UI", 9, "bold")); self.dt_tree.tag_configure("total", background="#c9d6e3", font=("Segoe UI", 9, "bold"))
        scroll = ttk.Scrollbar(page, orient="horizontal", command=self.dt_tree.xview); self.dt_tree.configure(xscrollcommand=scroll.set)
        scroll.pack(side="bottom", fill="x", padx=8); self.dt_tree.pack(fill="both", expand=True, padx=8, pady=(4, 2))
        self.load_asset_accounts()

    def _dt_account(self):
        value = self.dt_account.get()
        return None if not value or value == "All accounts" else value.split(" - ", 1)[0]

    def load_depreciation_table(self):
        try: data = self.client.asset_depreciation(self.dt_month.get().strip(), self._dt_account())
        except Exception as exc: return messagebox.showerror("Depreciation", str(exc))
        self.depreciation_data = data; tree = self.dt_tree; tree.delete(*tree.get_children()); money = lambda v: f"{float(v):,.2f}"
        grand = {k: 0.0 for k in ("value", "old", "current", "total", "net")}
        for g in data["groups"]:
            tree.insert("", "end", iid=f"g{g['account']}", values=(g["account"], f"{g['name']} - {float(g['rate'] or 0):g}% / year", "", "", "", "", "", "", ""), tags=("group",))
            for a in g["assets"]:
                tree.insert("", "end", values=(a["code"], a["name"], _dd(a["acquired_on"]), money(a["value"]), money(a["old"]), money(a["current"]), money(a["total"]), money(a["net"]),
                                               "Posted" if a["posted"] else ("-" if not float(a["current"]) else "To post")))
            tree.insert("", "end", iid=f"t{g['account']}", values=(f"Total {g['account']}", f"Entry: Dr {g['depreciation_account']} / Cr {g['accumulated_account']}", "", money(g["value"]),
                                                                   money(g["old"]), money(g["current"]), money(g["total"]), money(g["net"]), f"{float(g['to_post']):,.2f} to post" if float(g["to_post"]) else "Posted"), tags=("total",))
            for k in grand: grand[k] += float(g[k])
        if data["groups"]: tree.insert("", "end", values=("TOTAL", "All asset accounts", "", *[money(grand[k]) for k in ("value", "old", "current", "total", "net")], ""), tags=("total",))
        self.dt_info.config(text=f"Depreciation of {_dd(data['month'])[3:]}: {len(data['groups'])} account(s), {sum(len(g['assets']) for g in data['groups'])} asset(s), "
                                 f"month {grand['current']:,.2f}, net value {grand['net']:,.2f}. The net value never goes below zero.")

    def post_depreciation_entry(self, all_accounts=False):
        data = getattr(self, "depreciation_data", None)
        if not data: self.load_depreciation_table(); data = getattr(self, "depreciation_data", None)
        if not data: return
        if all_accounts: accounts = [g["account"] for g in data["groups"] if float(g["to_post"]) > 0]
        else:
            selected = self.dt_tree.selection(); iid = selected[0] if selected else ""
            accounts = [iid[1:]] if iid[:1] in ("g", "t") else ([self._dt_account()] if self._dt_account() else [])
        if not accounts: return messagebox.showwarning("Depreciation", "Select an account line (grey) or choose the account, or nothing is left to post")
        done = []
        for account in accounts:
            try: result = self.client.post_asset_depreciation(account, self.dt_month.get().strip()); done.append(f"{account}: {result['voucher']} ({result['amount']:,.2f})")
            except Exception as exc: done.append(f"{account}: {exc}")
        messagebox.showinfo("Depreciation", "\n".join(done)); self.load_depreciation_table(); self.load_journal(); self.load_trial()

    def export_depreciation_table(self, mode):
        data = getattr(self, "depreciation_data", None)
        if not data: self.load_depreciation_table(); data = getattr(self, "depreciation_data", None)
        if not data: return
        sections = []
        for g in data["groups"]:
            rows = [[a["code"], a["name"], _dd(a["acquired_on"]), a["value"], a["old"], a["current"], a["total"], a["net"], "Posted" if a["posted"] else ""] for a in g["assets"]]
            rows.append([f"Total {g['account']}", f"Dr {g['depreciation_account']} / Cr {g['accumulated_account']}", "", g["value"], g["old"], g["current"], g["total"], g["net"], ""])
            sections.append({"heading": f"{g['account']} - {g['name']} ({float(g['rate'] or 0):g}% per year)", "headers": ["Asset", "Name", "Date of Purchase", "Value", "Old Depreciation",
                             "Depreciation (month)", "Total Depreciation", "Net Value", "Entry"], "rows": rows, "total_rows": [len(rows) - 1]})
        self.output_sections("Monthly Depreciation Table", [f"Month: {_dd(data['month'])[3:]}"], sections, "Depreciation_Table", mode)
