"""Stage 3 screens (version 1.16): Import from Excel or PDF, Payment & Receipt, Purchases & Expenses."""
from __future__ import annotations

import mimetypes
import os
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from importer import read_customs_costs, read_expenses, read_invoices
from chart_extra import EXPENSE_VAT, PURCHASE_VAT, SALES_VAT
from pdf_import import read_invoice_pdf, read_invoice_pdf_pages
from report_export import export_excel, export_pdf

NAVY, GOLD, LIGHT = "#071b2e", "#c9a96a", "#f3f6f8"
PURCHASE_USES = {"Mixed (partial deduction)": "mixed", "Taxable sales only (100%)": "taxable", "Exempt sales only (0%)": "exempt"}
RED, MUTED = "#8B1E1E", "#5f6b76"
TYPES = {"Purchases": ("purchase", "purchases"), "Sales": ("sale", "sales"), "Expenses": ("purchase", "expenses"), "Assets": ("purchase", "assets")}
METHODS = ["Cash", "Cheque", "Bank Transfer", "Card", "Other"]


def _num(value, default=0.0):
    try: return float(str(value).replace(",", "")) if str(value).strip() else default
    except ValueError: return None


def _dd(value):
    text = str(value or "").strip()
    for pattern in ("%d-%m-%Y", "%Y-%m-%d", "%d%m%Y"):
        try: return datetime.strptime(text, pattern).strftime("%d-%m-%Y")
        except ValueError: pass
    return text


class Stage3Mixin:
    def ai_key_for_session(self):
        key=getattr(self,"_ai_api_key",None) or os.environ.get("SABER_AI_API_KEY","")
        if not key:
            key=simpledialog.askstring("AI assistance", "Enter your OpenAI API key (kept only for this session):", show="*", parent=self)
            if key: self._ai_api_key=key.strip()
        return key.strip() if key else None

    def run_ai_task(self, work, success):
        key=self.ai_key_for_session()
        if not key: return
        if not messagebox.askyesno("AI assistance", "This sends the selected description or first PDF page to OpenAI. API usage may be charged. Continue?"):
            return
        def run():
            try: result=work(key)
            except Exception as exc:
                error=str(exc); self.after(0,lambda:messagebox.showerror("AI assistance",error)); return
            self.after(0,lambda:success(result))
        threading.Thread(target=run,daemon=True,name="SaberAIAssist").start()

    # ================================================================ Import
    def build_import(self):
        page = self.import_tab; self.import_rows = []; self.import_mode = "excel"
        bar = tk.Frame(page, bg=LIGHT); bar.pack(fill="x", padx=10, pady=8)
        self.import_type = tk.StringVar(value="Purchases"); self.currency = tk.StringVar(value="USD"); self.import_replace = tk.BooleanVar(value=False)
        tk.Label(bar, text="Default Type", bg=LIGHT, font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Combobox(bar, textvariable=self.import_type, values=list(TYPES), state="readonly", width=11).pack(side="left", padx=(4, 10))
        tk.Label(bar, text="Default currency", bg=LIGHT).pack(side="left")
        ttk.Combobox(bar, textvariable=self.currency, values=self.currency_codes, state="readonly", width=6).pack(side="left", padx=(4, 10))
        tk.Button(bar, text="Choose Excel File", command=self.choose_import, bg=NAVY, fg="white", border=0, padx=14, pady=7).pack(side="left", padx=3)
        tk.Button(bar, text="Choose PDF Invoice(s)", command=self.choose_import_pdfs, bg=NAVY, fg="white", border=0, padx=14, pady=7).pack(side="left", padx=3)
        tk.Label(bar, text="Show", bg=LIGHT).pack(side="left", padx=(12, 2))
        ttk.Combobox(bar, textvariable=self.import_view_currency, values=["All Currencies"]+self.currency_codes, state="readonly", width=13).pack(side="left")
        tk.Button(bar, text="Apply", command=self.populate_import_preview, bg=GOLD, fg=NAVY, border=0, padx=10, pady=5).pack(side="left", padx=4)
        self.file_label = tk.Label(page, text="No file selected. Excel: one invoice per row. PDF: each file becomes one invoice and is attached to it.", bg=LIGHT, fg=MUTED, anchor="w")
        self.file_label.pack(fill="x", padx=12)
        tk.Label(page,text="PDF: review each row's Type (double-click to choose). Account cells: F2 / Down / right-click searches the chart; Tab saves.",
                 bg=LIGHT,fg=MUTED,anchor="w").pack(fill="x",padx=12,pady=(2,0))
        tk.Label(page, text="Select preview rows with Ctrl / Shift, choose a VAT A/C below, then apply it to the selection.",
                 bg=LIGHT, fg=MUTED, anchor="w").pack(fill="x", padx=12)
        from desktop_brains import EditableSheet
        columns = [("line", "#", 40, "center"), ("invoice_number", "Invoice No.", 110, "w"), ("invoice_date", "Date", 90, "center"), ("party_name", "Customer / Supplier", 200, "w"),
                   ("entry_type", "Type (review)", 120, "w"), ("currency", "Currency", 65, "center"), ("subtotal", "Before VAT", 105, "e"), ("vat", "VAT", 90, "e"), ("vat_account", "VAT A/C", 120, "w"),
                   ("total", "Total", 105, "e"), ("supplier_account", "Party / Paid A/C", 135, "w"), ("expense_account", "Cost / Revenue A/C", 140, "w"),
                   ("expense_no_vat_account", "No-VAT A/C", 120, "w"),
                   ("source", "Source", 150, "w"), ("notes", "Check", 230, "w")]
        bottom = tk.Frame(page, bg=LIGHT); bottom.pack(side="bottom", fill="x", padx=10, pady=8)
        tk.Checkbutton(bottom, text="Replace ALL previous invoices (a safety backup is made first)", variable=self.import_replace, bg=LIGHT, fg=RED).pack(side="left")
        tk.Button(bottom, text="Import", command=self.send_import, bg=GOLD, fg=NAVY, font=("Segoe UI", 10, "bold"), border=0, padx=26, pady=8).pack(side="right")
        tk.Button(bottom, text="Remove Row", command=lambda: self.import_sheet.delete_selected(), bg=RED, fg="white", border=0, padx=12, pady=8).pack(side="right", padx=6)
        self.import_status = tk.Label(bottom, text="", bg=LIGHT, fg=NAVY, font=("Segoe UI", 9, "bold")); self.import_status.pack(side="right", padx=10)
        tk.Button(bottom, text="Apply VAT A/C to selected", command=self.apply_selected_import_vat_account,
                  bg=NAVY, fg="white", border=0, padx=10, pady=8).pack(side="left", padx=(12, 3))
        self.import_bulk_vat_account = tk.StringVar()
        self.account_search_box(bottom, self.import_bulk_vat_account, 16).pack(side="left", padx=3)
        self.import_sheet = EditableSheet(self, page, columns, ["invoice_number", "invoice_date", "party_name", "entry_type", "currency", "subtotal", "vat",
            "vat_account", "total", "supplier_account", "expense_account", "expense_no_vat_account"], self.import_cell_changed, height=12,
            lookup_columns=("vat_account","supplier_account","expense_account","expense_no_vat_account"), lookup_groups=True,
            choices_by_column={"entry_type":list(TYPES)}, selectmode="extended")
        self.import_tree = self.import_sheet.tree

    def apply_selected_import_vat_account(self):
        selected = [iid for iid in self.import_tree.get_children() if iid in self.import_tree.selection()]
        if not selected:
            return messagebox.showwarning("Import", "Select the preview rows to change (Ctrl / Shift for multiple rows)")
        try:
            account = self.resolve_import_account(self.import_bulk_vat_account.get())
            if not account:
                raise ValueError("Choose a VAT account before applying it")
        except ValueError as exc:
            return messagebox.showwarning("Import", str(exc))
        if not messagebox.askyesno("Apply VAT account",
                                   f"Set VAT A/C {account} on {len(selected)} selected preview row(s)?\n"
                                   "Other rows and already imported invoices will not change."):
            return
        for iid in selected:
            row = self.import_sheet.rows[iid]
            row["vat_account"] = account
            row["_vat_account_chosen"] = True
            self.import_sheet.refresh(iid)
        self.import_bulk_vat_account.set(account)

    def resolve_import_account(self, text):
        value=str(text or "").strip()
        if not value: return ""
        code=value.split(" - ",1)[0].strip()
        if code.replace(".","").isdigit(): return code
        names=getattr(self,"_all_accounts",None)
        if names is None:
            names={str(row["code"]):row["name_en"] for row in self.client.accounts()}
            self._all_accounts=names
        from desktop import row_matches_search
        matches=[account for account,name in names.items() if row_matches_search((account,name),value)]
        if len(matches)==1: return matches[0]
        raise ValueError("Choose one account from the list (F2 / right-click), or enter its number")

    def import_cell_changed(self, iid, key, text):
        row = self.import_sheet.rows[iid]
        if key == "entry_type":
            if text not in TYPES: messagebox.showwarning("Import","Choose Purchases, Expenses, Assets or Sales"); return False
            row[key] = text
            if self.import_mode == "pdf":
                if not row.get("_vat_account_chosen") and row.get("vat_account") in (PURCHASE_VAT,EXPENSE_VAT,SALES_VAT):
                    row["vat_account"] = EXPENSE_VAT if text=="Expenses" else SALES_VAT if text=="Sales" else PURCHASE_VAT
                cost_code=str(row.get("expense_account") or "").split(" - ",1)[0].strip()
                required_cost_class={"Assets":"2","Sales":"7","Purchases":"6","Expenses":"6"}[text]
                if not cost_code.startswith(required_cost_class):
                    row["expense_account"] = "" if text=="Assets" else "713" if text=="Sales" else "601100000"
                party_code=str(row.get("supplier_account") or "").split(" - ",1)[0].strip()
                required_party_prefix={"Assets":"40","Purchases":"40","Sales":"41","Expenses":"5"}[text]
                if party_code and not party_code.startswith(required_party_prefix):
                    row["supplier_account"] = ""
        elif key in ("vat_account","supplier_account","expense_account","expense_no_vat_account"):
            try: row[key]=self.resolve_import_account(text)
            except ValueError as exc: messagebox.showwarning("Import",str(exc)); return False
            if key == "vat_account": row["_vat_account_chosen"] = True
        elif key in ("subtotal", "vat", "total"):
            value = _num(text, None)
            if value is None and text.strip(): messagebox.showwarning("Import", "Enter a number"); return False
            row[key] = value
            if self.import_mode != "pdf" and key in ("subtotal", "vat") and row.get("subtotal") is not None and row.get("vat") is not None:
                row["total"] = round(row["subtotal"] + row["vat"], 2)
        elif key == "currency":
            if text.upper() not in self.currency_codes: messagebox.showwarning("Import", "Choose a currency from Settings"); return False
            row[key] = text.upper()
        elif key == "invoice_date": row[key] = _dd(text)
        else: row[key] = text
        row["_display"] = {k: (f"{row[k]:,.2f}" if isinstance(row.get(k), (int, float)) else "") for k in ("subtotal", "vat", "total")}

    def choose_import(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xlsm")])
        if not path: return
        kind, entry_type = TYPES[self.import_type.get()]
        try:
            if entry_type == "expenses":
                rows = [{"invoice_number": r["reference"], "invoice_date": r["expense_date"], "party_name": r["description"], "currency": r["currency"],
                         "subtotal": r["with_vat_subtotal"] + r["without_vat_subtotal"], "vat": r["vat"], "total": r["with_vat_subtotal"] + r["without_vat_subtotal"] + r["vat"],
                         "source": f"Excel row {r['source_row']}", "_expense": r} for r in read_expenses(path)]
            else:
                rows = [{**r, "source": f"Excel row {r['source_row']}"} for r in read_invoices(path, default_currency=self.currency.get(), default_kind=kind,allowed_currencies=self.currency_codes)]
        except Exception as exc: return messagebox.showerror("Import", f"The Excel file could not be read: {exc}")
        self.import_mode = "excel"; self.import_rows = rows; self.file_label.config(text=f"Excel: {path}", fg=NAVY); self.populate_import_preview()

    def choose_import_pdfs(self):
        paths = filedialog.askopenfilenames(filetypes=[("PDF invoices", "*.pdf")])
        if not paths: return
        rows = []
        for path in paths:
            try: documents=read_invoice_pdf_pages(path)
            except Exception as exc:
                messagebox.showerror("Import PDF",f"{Path(path).name}: {exc}")
                continue
            for data in documents:
                suggested = "Sales" if self.import_type.get()=="Sales" else data.get("suggested_type") or ""
                type_note = (f"Suggested Type: {suggested}; review before import" if suggested else
                             "Type not clear from PDF; choose Purchases, Expenses or Assets")
                rows.append({"invoice_number": data.get("invoice_number") or "", "invoice_date": data.get("invoice_date") or "",
                         "party_name": data.get("party_name") or "", "currency": data.get("currency") or self.currency.get(),
                          "subtotal": data.get("subtotal"), "vat": data.get("vat"), "total": data.get("total"),
                          "entry_type": suggested, "source": f'{data["file"]} - {data["page_range"]}',
                          "notes": (data.get("notes", "") + "; " + type_note).strip("; "), "_path": path})
        self.import_mode = "pdf"; self.import_rows = rows
        self.file_label.config(text=f"{len(paths)} PDF file(s). Confirm each Type and amount; VAT 0 if none. Expenses are paid transactions.", fg=NAVY); self.populate_import_preview()

    def populate_import_preview(self):
        self.import_sheet.clear(); selected = self.import_view_currency.get()
        rows = [r for r in self.import_rows if selected == "All Currencies" or r.get("currency") == selected]
        for row in rows[:2000]:
            expense=row.get("_expense") or {}
            entry_type=row.get("entry_type") if self.import_mode=="pdf" else self.import_type.get()
            if self.import_mode!="pdf": row["entry_type"]=entry_type
            row.setdefault("supplier_account", expense.get("payment_account") or ("531" if expense else ""))
            row.setdefault("vat_account", expense.get("vat_account") or (EXPENSE_VAT if entry_type=="Expenses" else SALES_VAT if entry_type=="Sales" else PURCHASE_VAT))
            row.setdefault("expense_account", expense.get("expense_account") or ("" if self.import_mode=="pdf" and entry_type=="Assets" else "713" if entry_type=="Sales" else "601100000"))
            row.setdefault("expense_no_vat_account", expense.get("expense_without_vat_account") or "601100001")
            row.setdefault("notes", row.get("currency_issue") or ""); self.import_cell_changed_display(row); self.import_sheet.insert(row)
        self.import_status.config(text=f"{len(rows)} row(s) — review each Type ({selected})" if self.import_mode=="pdf" else
                                  f"{len(rows)} row(s) ready as {self.import_type.get()} ({selected})")

    def import_cell_changed_display(self, row):
        row["_display"] = {k: (f"{float(row[k]):,.2f}" if row.get(k) not in (None, "") else "") for k in ("subtotal", "vat", "total")}

    def send_import(self):
        rows = self.import_sheet.ordered()
        if not rows: return messagebox.showwarning("Import", "Choose an Excel or PDF file first")
        kind, entry_type = TYPES[self.import_type.get()]
        missing = [r["line"] for r in rows if not r.get("party_name") or r.get("total") in (None, "")]
        if missing: return messagebox.showwarning("Import", f"Row(s) {', '.join(missing[:10])}: enter the customer/supplier and the total")
        if self.import_mode == "pdf":
            incomplete = [str(r["line"]) for r in rows if not r.get("invoice_number") or not r.get("invoice_date")
                          or r.get("subtotal") in (None, "") or r.get("vat") in (None, "")]
            if incomplete:
                return messagebox.showwarning("Import", f"PDF row(s) {', '.join(incomplete[:10])}: enter invoice number, date, subtotal and VAT (type 0 if none) before importing")
            inconsistent = [str(r["line"]) for r in rows if abs(r["subtotal"] + r["vat"] - r["total"]) > max(0.05, abs(r["total"]) * 0.005)]
            if inconsistent:
                return messagebox.showwarning("Import", f"PDF row(s) {', '.join(inconsistent[:10])}: subtotal, VAT and total do not reconcile. Correct the amounts before importing")
            uncategorized = [str(r["line"]) for r in rows if r.get("entry_type") not in TYPES]
            if uncategorized:
                return messagebox.showwarning("Import",f"PDF row(s) {', '.join(uncategorized[:10])}: choose a Type for each row before importing")
            assets = [str(r["line"]) for r in rows if r["entry_type"]=="Assets" and not str(r.get("expense_account") or "").startswith("2")]
            if assets:
                return messagebox.showwarning("Import",f"PDF asset row(s) {', '.join(assets[:10])}: select a class 2 fixed-asset account in Cost / Revenue A/C")
            wrong_cost = [str(r["line"]) for r in rows if r["entry_type"]!="Assets" and not
                          str(r.get("expense_account") or "").startswith("7" if r["entry_type"]=="Sales" else "6")]
            if wrong_cost:
                return messagebox.showwarning("Import",f"PDF row(s) {', '.join(wrong_cost[:10])}: choose a cost/revenue account matching the selected Type (class 6 for Purchases/Expenses, class 7 for Sales)")
            wrong_party = [str(r["line"]) for r in rows if r.get("supplier_account") and r["entry_type"]!="Expenses" and not
                           str(r["supplier_account"]).startswith("41" if r["entry_type"]=="Sales" else "40")]
            if wrong_party:
                return messagebox.showwarning("Import",f"PDF row(s) {', '.join(wrong_party[:10])}: choose a matching party account (class 40 for Purchases/Assets, class 41 for Sales)")
            unpaid = [str(r["line"]) for r in rows if r["entry_type"]=="Expenses" and
                      not str(r.get("supplier_account") or "").split(" - ",1)[0].strip().startswith("5")]
            if unpaid:
                return messagebox.showwarning("Import",f"PDF expense row(s) {', '.join(unpaid[:10])}: choose a class 5 cash/bank payment account in Party / Paid A/C. Expenses post as paid; use Purchases for unpaid invoices")
            if self.import_replace.get() and any(r["entry_type"]=="Expenses" for r in rows):
                return messagebox.showwarning("Import","Replace ALL previous invoices cannot be used with PDF expense rows. Uncheck Replace to import paid expenses")
            counts = ", ".join(f"{label}: {sum(r['entry_type']==label for r in rows)}" for label in TYPES if any(r["entry_type"]==label for r in rows))
            if not messagebox.askyesno("Confirm PDF types",f"Review the Type of every PDF row before posting.\n{counts}\n\nExpenses are recorded as PAID from the selected payment account; Purchases are supplier invoices and Assets require a fixed-asset account.\n\nAre these types and accounts correct?"):
                return
        if self.import_replace.get() and not messagebox.askyesno("Replace previous data", "ALL previous invoices will be removed and replaced. A safety backup is made first. Continue?"): return
        done = 0; errors = []; completed = []
        try:
            expense_rows = [r for r in rows if r.get("entry_type")=="Expenses"] if self.import_mode=="pdf" else rows if entry_type=="expenses" else []
            if self.import_mode == "excel" and entry_type != "expenses":
                items = [{**{k: v for k, v in r.items() if not k.startswith("_") and k not in ("line", "source", "notes")}, "entry_type": entry_type, "kind": kind} for r in rows]
                result = self.client.import_invoices(items, replace_existing=self.import_replace.get()); done = result["imported"]
                errors = [f"{e.get('invoice_number')}: {e['error']}" for e in result["errors"]]
                failed={e["index"] for e in result["errors"]}
                completed.extend(r for index,r in enumerate(rows) if index not in failed)
            elif self.import_mode == "pdf":
                invoice_rows = [r for r in rows if r["entry_type"]!="Expenses"]
                items=[]
                for r in invoice_rows:
                    row_kind,row_type=TYPES[r["entry_type"]]
                    items.append({"invoice_number": r["invoice_number"], "invoice_date": r["invoice_date"], "party_name": r["party_name"],
                                  "kind": row_kind, "entry_type": row_type, "currency": r["currency"], "subtotal": r["subtotal"], "vat": r["vat"],
                                  "total": r["total"], "source_file": r["source"],
                                  "supplier_account": r.get("supplier_account") or "", "vat_account": r.get("vat_account") or "",
                                  "expense_account": r.get("expense_account") or "", "expense_no_vat_account": r.get("expense_no_vat_account") or ""})
                if items:
                    result=self.client.import_invoices(items, replace_existing=self.import_replace.get())
                    done+=result["imported"]
                    errors += [f"{e.get('invoice_number')}: {e['error']}" for e in result["errors"]]
                    failed={e["index"] for e in result["errors"]}
                    successful_rows=[r for index,r in enumerate(invoice_rows) if index not in failed]
                    completed.extend(successful_rows)
                    if len(result["ids"]) != len(successful_rows):
                        errors.append("The service did not return every posted invoice ID. Check posted invoices and attach missing PDFs manually; do not re-import those rows")
                    for r, invoice_id in zip(successful_rows,result["ids"]):
                        try:
                            self.client.upload_attachment(invoice_id, Path(r["_path"]).name, "application/pdf", Path(r["_path"]).read_bytes())
                        except Exception as exc: errors.append(f"{r['line']}: invoice POSTED (ID {invoice_id}), PDF attachment failed: {exc}. Attach it manually; do not re-import")
            for r in expense_rows:
                try:
                    item = dict(r.get("_expense") or {}); vat = r.get("vat") or 0
                    base = r.get("subtotal") if r.get("subtotal") is not None else r["total"] - vat
                    without = float(item.get("without_vat_subtotal") or 0)
                    item.update(expense_date=r["invoice_date"], description=r["party_name"], currency=r["currency"], reference=r.get("invoice_number") or "",
                                with_vat_subtotal=round(base - without, 2), without_vat_subtotal=without, vat=vat,
                                payment_account=r.get("supplier_account") or item.get("payment_account"),
                                expense_account=r.get("expense_account") or item.get("expense_account"),
                                expense_without_vat_account=r.get("expense_no_vat_account") or item.get("expense_without_vat_account"),
                                vat_account=r.get("vat_account") or item.get("vat_account"))
                    expense_id = self.client.add_expense(item)["expense_id"]; done += 1; completed.append(r)
                except Exception as exc:
                    errors.append(f"{r['line']}: expense not imported: {exc}")
                    continue
                if r.get("_path"):
                    try: self.client.upload_expense_attachment(expense_id, Path(r["_path"]).name, "application/pdf", Path(r["_path"]).read_bytes())
                    except Exception as exc: errors.append(f"{r['line']}: expense POSTED (ID {expense_id}), PDF attachment failed: {exc}. Attach it manually; do not re-import")
        except Exception as exc:
            return messagebox.showerror("Import",f"{exc}\n\nThe import result may be uncertain. Check posted invoices before retrying, to avoid duplicates.")
        remaining = [r for r in rows if id(r) not in {id(item) for item in completed}]
        message = f"{done} {'PDF document(s)' if self.import_mode=='pdf' else self.import_type.get().lower()} imported." + (f"\n\n{len(errors)} issue(s):\n" + "\n".join(errors[:12]) if errors else "")
        if remaining and done: message += f"\n\n{len(remaining)} unfinished row(s) kept in the preview for correction."
        (messagebox.showwarning if errors else messagebox.showinfo)("Import", message)
        if done:
            self.import_sheet.clear()
            for row in remaining: self.import_sheet.insert(row)
            self.import_rows = remaining
            if remaining and self.import_replace.get(): self.import_replace.set(False)
        self.load_dashboard(); self.load_invoices(); self.load_journal(); self.load_trial(); self.load_transactions()

    # ================================================================ Payment & Receipt
    def build_transactions(self):
        nested = ttk.Notebook(self.transactions_tab); nested.pack(fill="both", expand=True, padx=8, pady=8)
        self.payment_forms = {}
        for kind, title in (("customer_receipt", "Add Customer Receipt"), ("supplier_payment", "Add Supplier Payment")):
            page = tk.Frame(nested, bg=LIGHT); nested.add(page, text=title); self.payment_forms[kind] = self.build_payment_form(page, kind)
        bank_page = tk.Frame(nested, bg=LIGHT); nested.add(bank_page, text="Bank Reconciliation"); self.build_bank_rec_page(bank_page)
        self.load_transactions()

    def build_payment_form(self, page, kind):
        form = {"kind": kind, "id": None, "vars": {k: tk.StringVar() for k in ("number", "date", "party", "currency", "amount", "method", "cash_account", "reference", "description", "bank_commission", "exchange_difference")}}
        v = form["vars"]; v["date"].set(self.fiscal_today()); v["currency"].set("USD"); v["method"].set("Cash"); v["cash_account"].set("531")
        form["department"] = tk.StringVar(); form["project"] = tk.StringVar()
        box = tk.LabelFrame(page, text="Customer Receipt (RV)" if kind == "customer_receipt" else "Supplier Payment (PV)", bg=LIGHT, padx=8, pady=6); box.pack(fill="x", padx=8, pady=6)
        row = tk.Frame(box, bg=LIGHT); row.pack(fill="x")
        tk.Label(row, text="Number", bg=LIGHT, font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Entry(row, textvariable=v["number"], width=16, state="readonly", readonlybackground="white", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(4, 10))
        tk.Label(row, text="Date", bg=LIGHT).pack(side="left"); self.date_entry(row, v["date"], 11).pack(side="left", padx=(4, 10))
        tk.Label(row, text="Customer" if kind == "customer_receipt" else "Supplier", bg=LIGHT).pack(side="left")
        form["type"] = tk.StringVar(value="All")
        tk.Label(row, text="Type", bg=LIGHT).pack(side="left", padx=(0, 2))
        type_box = ttk.Combobox(row, textvariable=form["type"], values=["All", "client", "supplier", "asset_supplier", "other_payable"], state="readonly", width=13)
        type_box.pack(side="left", padx=(0, 8)); type_box.bind("<<ComboboxSelected>>", lambda _e: self.payment_type_changed(form))
        form["party_box"] = ttk.Combobox(row, textvariable=v["party"], width=24); form["party_box"].pack(side="left", padx=(4, 10))
        form["party_box"].bind("<KeyRelease>", lambda e: self.filter_payment_parties(form, e)); form["party_box"].bind("<<ComboboxSelected>>", lambda _e: self.payment_party_chosen(form))
        tk.Label(row, text="Currency", bg=LIGHT).pack(side="left")
        ttk.Combobox(row, textvariable=v["currency"], values=self.currency_codes, state="readonly", width=6).pack(side="left", padx=(4, 10))
        tk.Label(row, text="Amount", bg=LIGHT, font=("Segoe UI", 9, "bold")).pack(side="left"); tk.Entry(row, textvariable=v["amount"], width=14, font=("Segoe UI", 10, "bold")).pack(side="left", padx=4)
        row2 = tk.Frame(box, bg=LIGHT); row2.pack(fill="x", pady=(6, 0))
        tk.Label(row2, text="Method", bg=LIGHT).pack(side="left"); ttk.Combobox(row2, textvariable=v["method"], values=METHODS, state="readonly", width=13).pack(side="left", padx=(4, 10))
        tk.Label(row2, text="Cash / Bank Account", bg=LIGHT).pack(side="left")
        form["cash_box"] = ttk.Combobox(row2, textvariable=v["cash_account"], width=26, state="readonly"); form["cash_box"].pack(side="left", padx=(4, 10))
        tk.Label(row2, text="Ref. / Cheque", bg=LIGHT).pack(side="left"); tk.Entry(row2, textvariable=v["reference"], width=14).pack(side="left", padx=(4, 10))
        tk.Label(row2, text="Description", bg=LIGHT).pack(side="left"); tk.Entry(row2, textvariable=v["description"], width=22).pack(side="left", padx=4)
        row_fx = tk.Frame(box, bg=LIGHT); row_fx.pack(fill="x", pady=(6, 0))
        tk.Label(row_fx, text="Bank Commission (A/C 673900000)", bg=LIGHT).pack(side="left"); tk.Entry(row_fx, textvariable=v["bank_commission"], width=12).pack(side="left", padx=(4, 10))
        tk.Label(row_fx, text="Exchange Difference", bg=LIGHT).pack(side="left"); tk.Entry(row_fx, textvariable=v["exchange_difference"], width=12).pack(side="left", padx=(4, 10))
        tk.Label(row_fx, text="(+ gain / - loss)", bg=LIGHT, fg=MUTED).pack(side="left")
        row3 = tk.Frame(box, bg=LIGHT); row3.pack(fill="x", pady=(6, 0))
        self.dimension_selectors(row3, form["department"], form["project"])
        form["balance"] = tk.Label(row3, text="", bg=LIGHT, fg=NAVY, font=("Segoe UI", 9, "bold")); form["balance"].pack(side="left", padx=10)
        alloc = tk.LabelFrame(page, text="Allocation - which invoices this " + ("receipt settles" if kind == "customer_receipt" else "payment settles"), bg=LIGHT, padx=6, pady=2)
        alloc.pack(fill="x", padx=8, pady=(0, 4))
        bar = tk.Frame(alloc, bg=LIGHT); bar.pack(fill="x")
        self.action_button(bar, "Auto Allocate (oldest first)", lambda: self.auto_allocate(form)).pack(side="left", padx=(0, 4))
        self.action_button(bar, "Clear Allocation", lambda: self.clear_allocation(form)).pack(side="left", padx=4)
        form["alloc_info"] = tk.Label(bar, text="Choose the customer / supplier to see the open invoices", bg=LIGHT, fg=MUTED); form["alloc_info"].pack(side="left", padx=8)
        from desktop_brains import EditableSheet
        form["alloc_sheet"] = EditableSheet(self, alloc, [("line", "#", 35, "center"), ("number", "Document", 140, "w"), ("date", "Date", 90, "center"), ("type", "Type", 90, "w"),
            ("currency", "Cur.", 50, "center"), ("total", "Total", 110, "e"), ("open", "Open", 110, "e"), ("allocate", "Allocate", 110, "e")], ["allocate"],
            lambda iid, key, text: self.allocation_changed(form, iid, text), height=4)
        buttons = tk.Frame(box, bg=LIGHT); buttons.pack(fill="x", pady=(6, 0))
        self.action_button(buttons, "New", lambda: self.new_payment(form)).pack(side="left", padx=(0, 3))
        tk.Button(buttons, text="Save", command=lambda: self.save_payment(form), bg=GOLD, fg=NAVY, border=0, padx=18, pady=7, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
        tk.Button(buttons, text="Delete", command=lambda: self.delete_payment(form), bg=RED, fg="white", border=0, padx=12, pady=7).pack(side="left", padx=3)
        tk.Label(buttons, text="Double-click a line in the list to edit it.", bg=LIGHT, fg=MUTED).pack(side="left", padx=10)
        find_bar = tk.Frame(page, bg=LIGHT); find_bar.pack(fill="x", padx=8, pady=(4, 0))
        tk.Label(find_bar, text="Find", bg=LIGHT, font=("Segoe UI", 9, "bold")).pack(side="left")
        form["find"] = tk.StringVar()
        find_entry = tk.Entry(find_bar, textvariable=form["find"], width=32); find_entry.pack(side="left", padx=(4, 6))
        find_entry.bind("<KeyRelease>", lambda _e: self.filter_payments(form))
        tk.Button(find_bar, text="Clear", command=lambda: (form["find"].set(""), self.filter_payments(form)), bg=LIGHT, border=0, fg=NAVY).pack(side="left")
        form["tree"] = self.table(page, [("number", "Number", 125), ("date", "Date", 90), ("party", "Customer" if kind == "customer_receipt" else "Supplier", 210), ("currency", "Currency", 65),
            ("amount", "Amount", 110), ("method", "Method", 100), ("cash", "Cash / Bank", 90), ("reference", "Reference", 110), ("description", "Description", 200), ("dims", "Dep. / Project", 110)])
        form["tree"].bind("<Double-1>", lambda _e: self.edit_payment(form))
        return form

    def filter_payment_parties(self, form, event=None):
        typed = form["vars"]["party"].get().strip().casefold()
        kind = form["type"].get() if form.get("type") else "All"
        def cat(p): return (p.get("account_category") or ("client" if p.get("kind") == "customer" else "supplier"))
        result = [name for name, p in form.get("party_map", {}).items()
                  if (kind in ("All", "") or cat(p) == kind) and (not typed or typed in name.casefold())]
        form["party_box"]["values"] = result
        if typed and result and event is not None and getattr(event, "keysym", "") not in ("Up", "Down", "Return", "Escape", "Tab"):
            form["party_box"].after_idle(lambda: form["party_box"].event_generate("<Down>"))

    def payment_type_changed(self, form):
        form["vars"]["party"].set(""); self.filter_payment_parties(form)
        if "alloc_sheet" in form: form["alloc_sheet"].clear(); form["alloc_info"].config(text="Choose the customer / supplier to see the open invoices")
        form["balance"].config(text="")

    def load_open_documents(self, form, party, existing=None):
        sheet = form["alloc_sheet"]; sheet.clear(); existing = {a["invoice_id"]: a["amount"] for a in (existing or [])}
        try: documents = self.client.open_documents(party["id"])
        except Exception: documents = []
        known = {d["id"] for d in documents}
        for invoice_id, amount in existing.items():
            if invoice_id not in known:
                row = next((r for r in self.client.invoices() if r["id"] == invoice_id), None)
                if row: documents.append({"id": row["id"], "invoice_number": row["invoice_number"], "invoice_date": row["invoice_date"], "kind": row["kind"], "doc_subtype": row.get("doc_subtype"),
                                          "currency": row["currency"], "total": float(row["total"] or 0), "open_amount": 0.0})
        for d in documents:
            expected_kind = ("supplier_payment" if d.get("doc_subtype") == "credit_note" else "customer_receipt") if d["kind"] == "sale" else ("customer_receipt" if d.get("doc_subtype") == "credit_note" else "supplier_payment")
            if expected_kind != form["kind"] and d["id"] not in existing: continue
            open_amount = float(d["open_amount"]) + float(existing.get(d["id"], 0))
            row = {"invoice_id": d["id"], "expected_kind": expected_kind, "number": d["invoice_number"], "date": _dd(d["invoice_date"]), "type": {"credit_note": "Credit note", "debit_note": "Debit note"}.get(d.get("doc_subtype"), "Sale" if d["kind"] == "sale" else "Purchase"),
                   "currency": d["currency"], "total": d["total"], "open": open_amount, "allocate": float(existing.get(d["id"], 0))}
            row["_display"] = {"total": f'{d["total"]:,.2f}', "open": f"{open_amount:,.2f}", "allocate": f'{row["allocate"]:,.2f}' if row["allocate"] else ""}
            sheet.insert(row)
        self.update_allocation_info(form)

    def allocation_changed(self, form, iid, text):
        row = form["alloc_sheet"].rows[iid]; value = _num(text, 0.0)
        if value is None or value < 0: messagebox.showwarning("Allocation", "Enter a positive amount"); return False
        if value > abs(row["open"]) + 0.005: messagebox.showwarning("Allocation", f"{row['number']} is open for {row['open']:,.2f} only"); return False
        row["allocate"] = value; row["_display"]["allocate"] = f"{value:,.2f}" if value else ""; self.update_allocation_info(form)

    def update_allocation_info(self, form):
        rows = form["alloc_sheet"].ordered(); allocated = sum(r["allocate"] for r in rows); amount = _num(form["vars"]["amount"].get()) or 0
        form["alloc_info"].config(text=f"{len(rows)} open document(s)   Allocated: {allocated:,.2f} of {amount:,.2f}   Unallocated (on account): {amount - allocated:,.2f}",
                                  fg="#8B1E1E" if allocated > amount + 0.005 else NAVY)

    def auto_allocate(self, form):
        remaining = _num(form["vars"]["amount"].get()) or 0
        if remaining <= 0: return messagebox.showwarning("Allocation", "Enter the amount first")
        for iid in form["alloc_sheet"].tree.get_children():
            row = form["alloc_sheet"].rows[iid]
            if row["currency"] != form["vars"]["currency"].get() or row["expected_kind"] != form["kind"] or abs(row["open"]) < 0.01: row["allocate"] = 0
            else: row["allocate"] = round(min(remaining, abs(row["open"])), 2); remaining -= row["allocate"]
            row["_display"]["allocate"] = f'{row["allocate"]:,.2f}' if row["allocate"] else ""; form["alloc_sheet"].refresh(iid)
        self.update_allocation_info(form)

    def clear_allocation(self, form):
        for iid, row in form["alloc_sheet"].rows.items(): row["allocate"] = 0; row["_display"]["allocate"] = ""; form["alloc_sheet"].refresh(iid)
        self.update_allocation_info(form)

    def payment_party_chosen(self, form):
        party = form.get("party_map", {}).get(form["vars"]["party"].get())
        if not party: return
        self.load_open_documents(form, party)
        if party.get("currency"): form["vars"]["currency"].set(party["currency"])
        account = party.get("account_number")
        if not account: form["balance"].config(text=""); return
        try:
            report = self.client.account_report({"account_from": account, "account_to": account, "first_column": "account", "second_column": "none", "carry_forward": False, "posting_status": "all"})
            balances = []
            for section in report["sections"]:
                grand = section["rows"][-1] if section["rows"] else None
                if grand and grand[0] == "GRAND TOTAL" and abs(float(grand[-1] or 0)) > 0.004:
                    balances.append(f'{section["heading"].rsplit(" - ", 1)[-1]} {float(grand[-1]):,.2f}')
            form["balance"].config(text=f"Account {account}   Balance: " + ("   ".join(balances) if balances else "0.00") + "   (+ owes you / - you owe)")
        except Exception: form["balance"].config(text=f"Account {account}")

    def new_payment(self, form):
        form["id"] = None; v = form["vars"]
        for key in ("party", "amount", "reference", "description", "bank_commission", "exchange_difference"): v[key].set("")
        if "alloc_sheet" in form: form["alloc_sheet"].clear(); form["alloc_info"].config(text="Choose the customer / supplier to see the open invoices")
        v["date"].set(self.fiscal_today()); v["method"].set("Cash"); form["department"].set("(none)"); form["project"].set("(none)"); form["balance"].config(text="")
        try: v["number"].set(self.client.next_document_number(form["kind"], v["date"].get()))
        except Exception: v["number"].set("")

    def payment_payload(self, form):
        v = form["vars"]; party = form.get("party_map", {}).get(v["party"].get())
        if not party: raise ValueError("Choose the customer / supplier from the list")
        amount = _num(v["amount"].get(), None)
        if not amount or amount <= 0: raise ValueError("Enter an amount above zero")
        datetime.strptime(v["date"].get().strip(), "%d-%m-%Y")
        return {"kind": form["kind"], "party_id": party["id"], "payment_date": v["date"].get().strip(), "currency": v["currency"].get(), "amount": amount,
                "cash_account": v["cash_account"].get().split(" - ", 1)[0].strip() or "531", "reference": v["reference"].get().strip(), "description": v["description"].get().strip(),
                "payment_method": v["method"].get(), "department": self.dimension_code(form["department"].get()), "project": self.dimension_code(form["project"].get()),
                "bank_commission": _num(v["bank_commission"].get(), 0.0) or 0.0, "exchange_difference": _num(v["exchange_difference"].get(), 0.0) or 0.0}

    def save_payment(self, form):
        try: payload = self.payment_payload(form)
        except ValueError as exc: return messagebox.showwarning("Payment & Receipt", str(exc) if "time data" not in str(exc) else "Date must be DD-MM-YYYY")
        incompatible = next((r for r in form["alloc_sheet"].ordered() if r["allocate"] and r["expected_kind"] != form["kind"]), None)
        if incompatible:
            direction = "outgoing payment/refund" if incompatible["expected_kind"] == "supplier_payment" else "incoming receipt/refund"
            return messagebox.showwarning("Payment & Receipt", f"{incompatible['number']} requires an {direction}. A credit-note offset needs a separate journal adjustment.")
        allocations = [{"invoice_id": r["invoice_id"], "amount": r["allocate"]} for r in form["alloc_sheet"].ordered() if r["allocate"]]
        if sum(a["amount"] for a in allocations) > payload["amount"] + 0.005: return messagebox.showwarning("Payment & Receipt", "The allocation is more than the amount")
        try:
            payment_id = self.client.update_payment(form["id"], payload) if form["id"] else self.client.add_payment(payload)["payment_id"]
            if allocations: self.client.save_allocations(payment_id, allocations)
        except Exception as exc: return messagebox.showerror("Payment & Receipt", str(exc))
        number = form["vars"]["number"].get()
        messagebox.showinfo("Payment & Receipt", f"{'Receipt' if form['kind'] == 'customer_receipt' else 'Payment'} {number} saved")
        self.load_transactions(); self.new_payment(form); self.load_journal(); self.load_trial()

    def edit_payment(self, form):
        selected = form["tree"].selection()
        if not selected: return
        row = form.get("rows", {}).get(selected[0])
        if not row: return
        form["id"] = row["id"]; v = form["vars"]
        label = next((name for name, p in form.get("party_map", {}).items() if p["id"] == row["party_id"]), row["party_name"])
        for key, value in (("number", row.get("payment_number") or ""), ("date", _dd(row["payment_date"])), ("party", label), ("currency", row["currency"]), ("amount", f'{row["amount"]:g}'),
                           ("method", row.get("payment_method") or "Cash"), ("cash_account", row["cash_account"]), ("reference", row.get("reference") or ""), ("description", row.get("description") or ""),
                           ("bank_commission", f'{row.get("bank_commission") or 0:g}' if (row.get("bank_commission") or 0) else ""), ("exchange_difference", f'{row.get("exchange_difference") or 0:g}' if (row.get("exchange_difference") or 0) else "")):
            v[key].set(value)
        lists = self.dimension_lists()
        form["department"].set(next((f'{d["code"]} - {d["name"]}' for d in lists["departments"] if d["code"] == row.get("department")), "(none)"))
        form["project"].set(next((f'{p["code"]} - {p["name"]}' for p in lists["projects"] if p["code"] == row.get("project")), "(none)"))
        form["balance"].config(text=f"Editing {row.get('payment_number') or ''}")
        party = next((p for p in form.get("party_map", {}).values() if p["id"] == row["party_id"]), None)
        if party:
            try: existing = self.client.payment_allocations(row["id"])
            except Exception: existing = []
            self.load_open_documents(form, party, existing)

    def delete_payment(self, form):
        if not form["id"]: return messagebox.showwarning("Payment & Receipt", "Double-click a saved line to open it first")
        if not messagebox.askyesno("Payment & Receipt", f"Delete {form['vars']['number'].get()} and its journal entry?"): return
        try: self.client.delete_payment(form["id"])
        except Exception as exc: return messagebox.showerror("Payment & Receipt", str(exc))
        self.load_transactions(); self.new_payment(form); self.load_journal(); self.load_trial()

    def load_transactions(self):
        if hasattr(self, "payment_forms") and all(f["tree"].winfo_exists() for f in self.payment_forms.values()):
            try: payments = self.client.payments(); parties = self.client.parties()
            except Exception as exc: return messagebox.showerror("Payment & Receipt", str(exc))
            for kind, form in self.payment_forms.items():
                # clients and suppliers are both available in receipts and payments (refunds, advances, settlements)
                form["party_map"] = {f'{p["name"]} | {p.get("account_number") or ""}': p for p in parties}
                if not getattr(self, "_cash_accounts", None):
                    try: self._cash_accounts = [f'{a["code"]} - {a["name_en"]}' for a in self.client.accounts() if str(a["code"]).startswith(("511", "512", "519", "53"))]
                    except Exception: self._cash_accounts = ["531 - Cash"]
                form["cash_box"]["values"] = self._cash_accounts
                if not form["vars"]["cash_account"].get() or form["vars"]["cash_account"].get() == "531":
                    form["vars"]["cash_account"].set(next((a for a in self._cash_accounts if a.startswith("531")), self._cash_accounts[0] if self._cash_accounts else "531"))
                form["party_box"]["values"] = list(form["party_map"])
                rows = [r for r in payments if r["kind"] == kind]; form["rows"] = {str(r["id"]): r for r in rows}
                self.filter_payments(form)
                if not form["id"] and not form["vars"]["number"].get(): self.new_payment(form)
        if hasattr(self, "purchase_form"): self.load_purchases()
        if hasattr(self, "expense_form"): self.load_expenses()

    def _payment_tree_values(self, r):
        return (r.get("payment_number") or f"#{r['id']}", _dd(r["payment_date"]), r["party_name"], r["currency"], f'{r["amount"]:,.2f}',
                r.get("payment_method") or "", r["cash_account"], r.get("reference") or "", r.get("description") or "", " / ".join(x for x in (r.get("department"), r.get("project")) if x))

    def filter_payments(self, form):
        from desktop import row_matches_search
        needle = (form["find"].get() if form.get("find") else "").strip()
        form["tree"].delete(*form["tree"].get_children())
        for r in form.get("rows", {}).values():
            values = self._payment_tree_values(r)
            if not row_matches_search(values, needle): continue
            form["tree"].insert("", "end", iid=str(r["id"]), values=values)

    # ================================================================ Purchases & Expenses
    def build_purchases_expenses(self):
        nested = ttk.Notebook(self.purchases_tab); nested.pack(fill="both", expand=True, padx=8, pady=8)
        self.purchase_notebook=nested
        purchases_outer=tk.Frame(nested,bg=LIGHT)
        purchase_totals=tk.Frame(purchases_outer,bg=LIGHT); purchase_totals.pack(side="bottom",fill="x")
        purchase_costs=tk.Frame(nested,bg=LIGHT)
        expenses_outer, expenses = self.scrollable_page(nested)
        nested.add(purchases_outer, text="Purchase Invoice")
        self.purchase_invoice_page=purchases_outer
        nested.add(purchase_costs,text="Cost on Purchase")
        assets_page=tk.Frame(nested,bg=LIGHT); nested.add(assets_page,text="Assets & Amortisation")
        nested.add(expenses_outer, text="Expenses")
        self.build_purchases_page(purchases_outer,purchase_totals,purchase_costs); self.build_expenses_page(expenses)
        self.build_assets_page(assets_page)
        self.load_purchases(); self.load_expenses()

    def build_assets_page(self,page):
        self.asset_edit_id=None
        defaults={"asset_code":"","name":"","acquired_on":self.fiscal_today(),"start_on":self.fiscal_today(),
                  "currency":"USD","cost":"","residual":"0","useful_months":"60","frequency":"monthly",
                  "asset_account":"","depreciation_account":"","accumulated_account":"","invoice_id":""}
        self.asset_fields={key:tk.StringVar(value=value) for key,value in defaults.items()}
        self.asset_rate=tk.StringVar(value="20")
        sections=[("1. Purchase details",[[ ("Asset code","asset_code"),("Description","name"),("Currency","currency")],
            [("Purchase date","acquired_on"),("Purchase value","cost"),("Purchase invoice ID","invoice_id")],
            [("Asset account","asset_account")]]),
            ("2. Amortisation settings",[[ ("Amortisation start","start_on"),("Residual value","residual"),("Annual rate %","rate")],
            [("Useful life (months)","useful_months"),("Post","frequency")],
            [("Amortisation expense","depreciation_account"),("Accumulated amortisation","accumulated_account")]])]
        for title,layout in sections:
            fields=tk.LabelFrame(page,text=title,bg=LIGHT,padx=10,pady=5); fields.pack(fill="x",padx=8,pady=(4,0))
            for row,items in enumerate(layout):
              for index,(label,key) in enumerate(items):
                column=index*2
                tk.Label(fields,text=label,bg=LIGHT).grid(row=row,column=column,sticky="w",padx=4,pady=5)
                if key in ("asset_account","depreciation_account","accumulated_account"):
                    widget=self.account_search_box(fields,self.asset_fields[key],17)
                elif key in ("acquired_on","start_on"): widget=self.date_entry(fields,self.asset_fields[key],12)
                elif key in ("currency","frequency"):
                    widget=ttk.Combobox(fields,textvariable=self.asset_fields[key],state="readonly",width=14,
                        values=["USD","LBP","EUR","AED"] if key=="currency" else ["monthly","yearly"])
                elif key=="rate": widget=tk.Entry(fields,textvariable=self.asset_rate,width=12)
                else: widget=tk.Entry(fields,textvariable=self.asset_fields[key],width=20)
                widget.grid(row=row,column=column+1,sticky="ew",padx=(2,12),pady=5)
                fields.grid_columnconfigure(column+1,weight=1)
        self.asset_rate.trace_add("write",self.asset_rate_changed)
        for key in ("cost","residual"):
            self.asset_fields[key].trace_add("write",self.asset_rate_changed)
        actions=tk.Frame(page,bg=LIGHT); actions.pack(fill="x",padx=8,pady=4)
        self.action_button(actions,"Record Asset Purchase",self.open_asset_purchase).pack(side="left",padx=3)
        for label,command in (("Annual Rollforward",self.show_asset_rollforward),("New",self.new_asset),("Save",self.save_asset_entry),("Delete",self.delete_asset_entry),
                              ("Post selected period",self.post_asset_period),("Refresh",self.load_assets)):
            self.action_button(actions,label,command).pack(side="left",padx=3)
        tk.Label(actions,text="Posted periods stay in the journal; review the schedule before posting.",bg=LIGHT,fg=MUTED).pack(side="left",padx=12)
        lists=tk.Frame(page,bg=LIGHT); lists.pack(fill="both",expand=True,padx=8,pady=4)
        self.asset_list=ttk.Treeview(lists,columns=("code","name","purchase","cost","currency","previous","yearly","cumulative","net"),show="headings",height=5)
        for key,title,width in (("code","Asset",90),("name","Description",150),("purchase","Purchase date",105),("cost","Purchase value",100),("currency","Currency",70),
                                ("previous","Old amort.",100),("yearly","Yearly amort.",105),("cumulative","Cumulative amort.",120),("net","Net value",100)):
            self.asset_list.heading(key,text=title); self.asset_list.column(key,width=width,stretch=key=="name")
        self.asset_list.pack(fill="x"); self.asset_list.bind("<<TreeviewSelect>>",lambda _e:self.select_asset())
        self.asset_schedule_tree=ttk.Treeview(lists,columns=("date","amount","accumulated","net","status"),show="headings")
        for key,title,width in (("date","Period end",120),("amount","Amortisation",130),("accumulated","Accumulated",130),("net","Net book value",130),("status","Status",85)):
            self.asset_schedule_tree.heading(key,text=title); self.asset_schedule_tree.column(key,width=width)
        self.asset_schedule_tree.pack(fill="both",expand=True,pady=(8,0))
        self.load_assets()

    def new_asset(self):
        self.asset_edit_id=None
        self.asset_rate.set("20")
        for key,var in self.asset_fields.items():
            var.set({"acquired_on":self.fiscal_today(),"start_on":self.fiscal_today(),"currency":"USD","residual":"0",
                     "useful_months":"60","frequency":"monthly"}.get(key,""))
        self.asset_schedule_tree.delete(*self.asset_schedule_tree.get_children())

    def load_assets(self):
        try: self.asset_rows=self.client.fixed_assets()
        except Exception as exc: return messagebox.showerror("Assets",str(exc))
        self.asset_list.delete(*self.asset_list.get_children())
        year=str(self.current_fiscal_year)
        for asset in self.asset_rows:
            try: periods=self.client.asset_schedule(asset["id"])
            except Exception as exc: return messagebox.showerror("Assets",str(exc))
            previous=sum(float(p["amount"]) for p in periods if p["period_end"][:4]<year)
            yearly=sum(float(p["amount"]) for p in periods if p["period_end"][:4]==year)
            cost=float(asset["cost"]); accumulated=min(cost,previous+yearly)
            self.asset_list.insert("","end",iid=str(asset["id"]),values=(asset["asset_code"],asset["name"],_dd(asset["acquired_on"]),
                f"{cost:,.2f}",asset["currency"],f"{previous:,.2f}",f"{yearly:,.2f}",f"{accumulated:,.2f}",f"{max(0,cost-accumulated):,.2f}"))

    def show_asset_rollforward(self):
        year=int(self.current_fiscal_year)
        try: report=self.client.asset_rollforward(year)
        except Exception as exc: return messagebox.showerror("Fixed Asset Rollforward",str(exc))
        window=tk.Toplevel(self); window.title(f"Fixed Asset Register & Depreciation Rollforward — {year}")
        window.configure(bg=LIGHT); window.transient(self)
        title=f"Fixed Asset Register & Depreciation Rollforward — {year}"
        tk.Label(window,text=title,bg=LIGHT,fg=NAVY,font=("Segoe UI",14,"bold")).pack(anchor="w",padx=14,pady=(12,4))
        tk.Label(window,text="Posted depreciation is shown separately from the unposted schedule; amounts remain in each asset's currency.",
                 bg=LIGHT,fg=MUTED,wraplength=1250,justify="left").pack(anchor="w",padx=14,pady=(0,8))
        headers=("Asset code","Description","Currency","Opening cost","Additions","Closing cost","Opening accumulated depreciation",
                 "Depreciation posted","Closing accumulated depreciation","Closing net book value","Unposted schedule")
        keys=("asset_code","name","currency","opening_cost","additions","closing_cost","opening_accumulated","depreciation_posted",
              "closing_accumulated","closing_net_book_value","unposted_scheduled")
        container=tk.Frame(window,bg=LIGHT); container.pack(fill="both",expand=True,padx=12,pady=4)
        tree=ttk.Treeview(container,columns=keys,show="headings")
        vertical=ttk.Scrollbar(container,orient="vertical",command=tree.yview)
        horizontal=ttk.Scrollbar(container,orient="horizontal",command=tree.xview)
        tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        for key,label in zip(keys,headers):
            tree.heading(key,text=label)
            tree.column(key,width=100 if key in ("currency","asset_code") else 145,
                        minwidth=82,stretch=key in ("name",))
        tree.grid(row=0,column=0,sticky="nsew"); vertical.grid(row=0,column=1,sticky="ns")
        horizontal.grid(row=1,column=0,sticky="ew")
        container.grid_rowconfigure(0,weight=1); container.grid_columnconfigure(0,weight=1)
        for index,row in enumerate(report["items"]):
            values=tuple(row.get(key,"") if key in ("asset_code","name","currency") else f'{float(row.get(key) or 0):,.2f}' for key in keys)
            tree.insert("","end",iid=f"asset-{index}",values=values)
        total_lines=[]
        for currency,amounts in report["totals"].items():
            total_lines.append(f'{currency}: Opening cost {float(amounts["opening_cost"]):,.2f} · Additions {float(amounts["additions"]):,.2f} · '
                f'Depreciation posted {float(amounts["depreciation_posted"]):,.2f} · Closing net book value {float(amounts["closing_net_book_value"]):,.2f} · '
                f'Unposted schedule {float(amounts["unposted_scheduled"]):,.2f}')
        tk.Label(window,text="\n".join(total_lines) if total_lines else "No active fixed assets for this year.",
                 bg=LIGHT,fg=NAVY,wraplength=1350,justify="left",anchor="w").pack(fill="x",padx=14,pady=8)
        controls=tk.Frame(window,bg=LIGHT); controls.pack(fill="x",padx=12,pady=(0,10))
        def save_report(kind):
            suffix=".xlsx" if kind=="Excel" else ".pdf"
            path=filedialog.asksaveasfilename(parent=window,defaultextension=suffix,
                filetypes=[("Excel workbook","*.xlsx")] if kind=="Excel" else [("PDF report","*.pdf")],
                initialfile=f"Fixed_Asset_Rollforward_{year}{suffix}")
            if not path: return
            try:
                rows=[[row.get(key,"") if key in ("asset_code","name","currency") else float(row.get(key) or 0) for key in keys]
                      for row in report["items"]]
                (export_excel if kind=="Excel" else export_pdf)(path,title,headers,rows)
            except Exception as exc: return messagebox.showerror("Fixed Asset Rollforward",str(exc),parent=window)
            messagebox.showinfo("Fixed Asset Rollforward",f"Report saved to:\n{path}",parent=window)
        self.action_button(controls,"Export Excel",lambda:save_report("Excel")).pack(side="left",padx=4)
        self.action_button(controls,"Export PDF",lambda:save_report("PDF")).pack(side="left",padx=4)
        self.action_button(controls,"Close",window.destroy).pack(side="right",padx=4)
        self.fit_dialog(window,1450,680,min_width=920,min_height=460)

    def select_asset(self):
        selected=self.asset_list.selection()
        if not selected: return
        self.asset_edit_id=int(selected[0]); asset=next(row for row in self.asset_rows if row["id"]==self.asset_edit_id)
        for key,var in self.asset_fields.items():
            value=asset.get(key) or ""
            var.set(_dd(value) if key in ("acquired_on","start_on") and value else str(value))
        self.asset_rate.set(str(asset.get("annual_rate") or f'{1200/int(asset["useful_months"]):g}'))
        self.asset_schedule_tree.delete(*self.asset_schedule_tree.get_children())
        try: rows=self.client.asset_schedule(self.asset_edit_id)
        except Exception as exc: return messagebox.showerror("Assets",str(exc))
        for row in rows: self.asset_schedule_tree.insert("","end",iid=row["period_end"],values=(_dd(row["period_end"]),row["amount"],row["accumulated"],row["net_book_value"],"Posted" if row["posted"] else "Draft"))

    def save_asset_entry(self):
        payload={key:var.get().strip() for key,var in self.asset_fields.items()}
        payload["annual_rate"]=self.asset_rate.get().strip()
        if not payload["invoice_id"]: payload["invoice_id"]=None
        try: asset=self.client.save_asset(payload,self.asset_edit_id)
        except Exception as exc: return messagebox.showerror("Assets",str(exc))
        self.load_assets(); self.asset_list.selection_set(str(asset["id"])); self.select_asset()
        messagebox.showinfo("Assets",f"Asset {asset['asset_code']} saved")

    def asset_rate_changed(self,*_args):
        try:
            rate=float(self.asset_rate.get())
            if not 0<rate<=100: return
            import math
            try:
                cost=float(self.asset_fields["cost"].get().replace(",",""))
                residual=float(self.asset_fields["residual"].get().replace(",",""))
                months=math.ceil((cost-residual)*1200/(cost*rate)) if 0<=residual<cost else math.ceil(1200/rate)
            except (ValueError,ZeroDivisionError): months=math.ceil(1200/rate)
            self.asset_fields["useful_months"].set(str(months))
        except ValueError: pass

    def open_asset_purchase(self):
        self.purchase_form["vars"]["type"].set("Assets")
        self.purchase_notebook.select(self.purchase_invoice_page)

    def delete_asset_entry(self):
        if not self.asset_edit_id: return messagebox.showwarning("Assets","Select an asset first")
        if not messagebox.askyesno("Assets","Delete this unposted asset from the register?"): return
        try: self.client.delete_asset(self.asset_edit_id)
        except Exception as exc: return messagebox.showerror("Assets",str(exc))
        self.new_asset(); self.load_assets()

    def post_asset_period(self):
        selected=self.asset_schedule_tree.selection()
        if not self.asset_edit_id or not selected: return messagebox.showwarning("Assets","Select an asset and an amortisation period")
        period=selected[0]
        if not messagebox.askyesno("Assets",f"Post amortisation for {period} to the journal?"): return
        try: self.client.post_asset_period(self.asset_edit_id,period)
        except Exception as exc: return messagebox.showerror("Assets",str(exc))
        self.select_asset(); self.load_journal(); self.load_trial()

    # ---- purchases
    def build_purchases_page(self, page, totals_parent=None, cost_parent=None):
        f = {"id": None, "pdf": None, "vars": {k: tk.StringVar() for k in ("supplier", "number", "date", "due", "currency", "type", "taxable", "exempt", "rate", "vat", "account", "vat_account")}}
        v = f["vars"]; v["date"].set(self.fiscal_today()); v["currency"].set("USD"); v["type"].set("Purchases"); v["rate"].set("11"); v["account"].set("601100000"); v["vat_account"].set("44210")
        f["department"] = tk.StringVar(); f["project"] = tk.StringVar(); f["vat_typed"] = False; self.purchase_form = f
        f["use"] = tk.StringVar(value="Mixed (partial deduction)"); f["reverse"] = tk.BooleanVar(value=False)
        f["discount_percent"] = tk.StringVar(value="0"); f["discount_amount"] = tk.StringVar(value="0"); f["discount_mode"] = "percent"
        box = tk.LabelFrame(page, text="Purchase Invoice", bg=LIGHT, padx=6, pady=2); box.pack(fill="x", padx=8, pady=(2, 1))
        actions = tk.Frame(box, bg=LIGHT); actions.pack(side="right", anchor="ne", padx=(10, 0))
        fields = tk.Frame(box, bg=LIGHT); fields.pack(side="left", fill="x", expand=True)
        r1 = tk.Frame(fields, bg=LIGHT); r1.pack(fill="x")
        tk.Label(r1, text="Supplier", bg=LIGHT, font=("Segoe UI", 9, "bold")).pack(side="left")
        f["supplier_box"] = ttk.Combobox(r1, textvariable=v["supplier"], width=22); f["supplier_box"].pack(side="left", padx=(4, 8))
        f["supplier_box"].bind("<KeyRelease>", lambda _e: self.filter_suppliers()); f["supplier_box"].bind("<<ComboboxSelected>>", lambda _e: self.purchase_supplier_chosen())
        tk.Label(r1, text="Supplier Invoice No.", bg=LIGHT).pack(side="left"); tk.Entry(r1, textvariable=v["number"], width=14).pack(side="left", padx=(4, 8))
        tk.Label(r1, text="Date", bg=LIGHT).pack(side="left"); self.date_entry(r1, v["date"], 11).pack(side="left", padx=(4, 8))
        tk.Label(r1, text="Due", bg=LIGHT).pack(side="left"); self.date_entry(r1, v["due"], 11).pack(side="left", padx=(4, 8))
        ttk.Combobox(r1, textvariable=v["currency"], values=self.currency_codes, state="readonly", width=5).pack(side="left", padx=4)
        ttk.Combobox(r1, textvariable=v["type"], values=["Purchases", "Assets"], state="readonly", width=9).pack(side="left", padx=4)
        accounts_row = tk.Frame(fields, bg=LIGHT); accounts_row.pack(fill="x", pady=(2, 0))
        tk.Label(accounts_row, text="Cost / Asset A/C", bg=LIGHT).pack(side="left"); self.account_search_box(accounts_row, v["account"], 18).pack(side="left", padx=(4, 12))
        tk.Label(accounts_row, text="VAT A/C", bg=LIGHT).pack(side="left"); self.account_search_box(accounts_row, v["vat_account"], 14).pack(side="left", padx=4)
        totals_box = tk.LabelFrame(totals_parent or page, text="Purchase totals", bg="#dfe6ee", padx=10, pady=4)
        r2 = tk.Frame(totals_box, bg="#dfe6ee"); r2.pack(fill="x", pady=(2, 4))
        for label, key, width in (("Taxable Amount", "taxable", 12), ("Exempt Amount", "exempt", 11), ("VAT %", "rate", 5), ("VAT", "vat", 11)):
            tk.Label(r2, text=label, bg="#dfe6ee").pack(side="left"); entry = tk.Entry(r2, textvariable=v[key], width=width); entry.pack(side="left", padx=(4, 8))
            entry.bind("<KeyRelease>", lambda e, k=key: self.purchase_amounts_changed(k))
        f["total"] = tk.Label(r2, text="Total: 0.00", bg="#dfe6ee", fg=NAVY, font=("Segoe UI", 10, "bold")); f["total"].pack(side="left", padx=6)
        summary = tk.Frame(totals_box, bg="#dfe6ee"); summary.pack(fill="x", padx=8)
        tk.Label(summary,text="Total before discount",bg="#dfe6ee").pack(side="left")
        f["gross_summary"] = tk.Label(summary,text="0.00",bg="#dfe6ee",fg=NAVY,width=13,anchor="e"); f["gross_summary"].pack(side="left",padx=(2,16))
        tk.Label(summary,text="Discount %",bg="#dfe6ee").pack(side="left")
        percent_entry=tk.Entry(summary,textvariable=f["discount_percent"],width=6); percent_entry.pack(side="left",padx=4)
        tk.Label(summary,text="or amount",bg="#dfe6ee").pack(side="left")
        amount_entry=tk.Entry(summary,textvariable=f["discount_amount"],width=10); amount_entry.pack(side="left",padx=4)
        percent_entry.bind("<KeyRelease>",lambda _e:self.purchase_discount_changed("percent"))
        amount_entry.bind("<KeyRelease>",lambda _e:self.purchase_discount_changed("amount"))
        f["discount_summary"] = tk.Label(summary,text="Total HT: 0.00",bg="#dfe6ee",fg=NAVY,font=("Segoe UI",9,"bold")); f["discount_summary"].pack(side="right",padx=8)
        r3 = tk.Frame(fields, bg=LIGHT); r3.pack(fill="x", pady=(2, 0))
        self.dimension_selectors(r3, f["department"], f["project"])
        tk.Label(r3, text="VAT use", bg=LIGHT).pack(side="left")
        use_box = ttk.Combobox(r3, textvariable=f["use"], values=list(PURCHASE_USES), state="readonly", width=23)
        use_box.pack(side="left", padx=(4, 6))
        use_box.bind("<<ComboboxSelected>>", lambda _e: self.purchase_amounts_changed("use"))
        tk.Label(r3, text="Mixed prorates input VAT by taxable / total use.", bg=LIGHT, fg=MUTED).pack(side="left", padx=4)
        tk.Checkbutton(r3, text="Reverse charge", variable=f["reverse"], bg=LIGHT).pack(side="left")
        find = tk.Frame(page, bg=LIGHT); find.pack(fill="x", padx=8, pady=(0, 2), before=box); f["find"] = tk.StringVar()
        tk.Label(find, text="Find purchase (No., supplier, date)", bg=LIGHT, font=("Segoe UI", 9, "bold")).pack(side="left")
        f["find_box"] = ttk.Combobox(find, textvariable=f["find"], width=48); f["find_box"].pack(side="left", padx=6)
        f["find_box"].bind("<<ComboboxSelected>>", lambda _e: self.purchase_found()); f["find_box"].bind("<KeyRelease>", lambda _e: self.filter_found_purchases())
        f["find_box"].bind("<Return>", lambda _e: self.purchase_found())
        self.action_button(find, "Import Excel", self.import_purchases_excel).pack(side="left", padx=(12, 3))
        self.action_button(find, "Excel Template", lambda: self.save_invoice_template("purchases")).pack(side="left", padx=3)
        items = tk.LabelFrame(page, text="Purchase Invoice Items · F2 to find an item · double-click a cell to edit", bg=LIGHT, padx=6, pady=2)
        items.pack(fill="both",expand=True,padx=8,pady=2,after=box)
        if totals_parent is not None: totals_box.pack(fill="x", padx=8, pady=(2,4))
        else: totals_box.pack(fill="x", padx=8, pady=(2,4), after=items)
        wh = tk.Frame(items, bg=LIGHT); wh.pack(fill="x"); f["warehouse"] = tk.StringVar()
        tk.Label(wh, text="Warehouse", bg=LIGHT).pack(side="left"); f["warehouse_box"] = ttk.Combobox(wh, textvariable=f["warehouse"], state="readonly", width=20); f["warehouse_box"].pack(side="left", padx=4)
        self.action_button(wh, "Add Item Line", lambda: self.purchase_item_line()).pack(side="left", padx=6)
        tk.Button(wh, text="Delete Line", command=lambda: (f["items_sheet"].delete_selected(), self.purchase_items_changed()), bg="#8B1E1E", fg="white", border=0, padx=10, pady=5).pack(side="left", padx=2)
        from desktop_brains import EditableSheet
        f["items_sheet"] = EditableSheet(self, items, [("line", "#", 35, "center"), ("item_code", "Item", 125, "w"), ("name", "Description", 410, "w"), ("quantity", "Qty", 70, "e"),
            ("unit", "Unit", 60, "center"), ("unit_cost", "Unit Price", 95, "e"), ("discount_percent", "Discount %", 85, "e"), ("total", "Net", 105, "e")],
            ["item_code", "name", "quantity", "unit", "unit_cost", "discount_percent"], self.purchase_item_changed, height=12)
        f["items_sheet"].tree.bind("<F2>", lambda _e: self.purchase_item_lookup())
        f["items_sheet"].tree.master.pack_configure(expand=True,fill="both")
        r4 = tk.Frame(actions, bg=LIGHT); r4.pack(anchor="e", pady=(2, 0))
        r5 = tk.Frame(actions, bg=LIGHT); r5.pack(anchor="e", pady=(3, 0))
        f["pdf_label"] = tk.Label(r5, text="No PDF", bg=LIGHT, fg=MUTED)
        self.action_button(r4, "New", self.new_purchase).pack(side="left", padx=(0, 3))
        tk.Button(r4, text="Save", command=self.save_purchase, bg=GOLD, fg=NAVY, border=0, padx=18, pady=6, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
        tk.Button(r4, text="Delete", command=self.delete_purchase, bg=RED, fg="white", border=0, padx=12, pady=6).pack(side="left", padx=3)
        self.action_button(r5, "Upload PDF", self.choose_purchase_pdf).pack(side="left", padx=3)
        self.action_button(r5, "AI Read PDF", self.ai_read_purchase_pdf).pack(side="left", padx=3)
        self.action_button(r5, "Attachments", lambda: self.purchase_attachments()).pack(side="left", padx=3)
        f["pdf_label"].pack(side="left", padx=8)
        cost = tk.LabelFrame(cost_parent or page, text="Cost on Purchase (customs / freight / insurance) for the selected purchase", bg=LIGHT, padx=8, pady=4); cost.pack(fill="x", padx=8, pady=3)
        f["lc"] = {k: tk.StringVar() for k in ("freight", "insurance", "customs_duties", "broker_fees", "other_costs", "import_vat", "customs_declaration_no", "party_name")}
        f["lc"]["party_name"].set("Lebanese Customs")
        import chart_extra
        f["lc_accounts"] = {key: tk.StringVar(value=code) for key, code in chart_extra.LANDED_COST_ACCOUNTS.items()}
        c1 = tk.Frame(cost, bg=LIGHT); c1.pack(fill="x")
        for label, key, width in (("Freight", "freight", 9), ("Insurance", "insurance", 9), ("Customs Duties", "customs_duties", 10), ("Broker Fees", "broker_fees", 9),
                                  ("Other", "other_costs", 8), ("Import VAT", "import_vat", 9)):
            tk.Label(c1, text=label, bg=LIGHT).pack(side="left"); tk.Entry(c1, textvariable=f["lc"][key], width=width).pack(side="left", padx=(3, 7))
        c2 = tk.Frame(cost, bg=LIGHT); c2.pack(fill="x", pady=(4, 0))
        tk.Label(c2, text="Declaration No.", bg=LIGHT).pack(side="left"); tk.Entry(c2, textvariable=f["lc"]["customs_declaration_no"], width=14).pack(side="left", padx=(3, 8))
        tk.Label(c2, text="Paid to", bg=LIGHT).pack(side="left"); f["lc_party_box"] = ttk.Combobox(c2, textvariable=f["lc"]["party_name"], width=28); f["lc_party_box"].pack(side="left", padx=(3, 8))
        tk.Button(c2, text="Add Cost on Purchase", command=self.save_landed_cost, bg=GOLD, fg=NAVY, border=0, padx=12, pady=5, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
        self.action_button(c2, "Edit Cost Accounts", self.edit_landed_cost_accounts).pack(side="left", padx=3)
        self.action_button(c2, "Import Customs Excel", self.import_customs_excel).pack(side="left", padx=3)
        self.action_button(c2, "Attach Customs PDF", self.attach_customs_pdf).pack(side="left", padx=3)
        f["lc_label"] = tk.Label(c2, text="", bg=LIGHT, fg=NAVY); f["lc_label"].pack(side="left", padx=8)
        f["tree"] = ttk.Treeview(page, columns=[f"c{i}" for i in range(12)])  # kept hidden: the Find box replaces the list
        f["tree"].bind("<<TreeviewSelect>>", lambda _e: self.purchase_selected())

    def purchase_item_line(self, row=None):
        f = self.purchase_form; row = row or {"item_code": "", "name": "", "quantity": 1, "unit": "", "unit_cost": 0, "discount_percent": 0}
        self.purchase_item_total(row); iid = f["items_sheet"].insert(row); f["items_sheet"].tree.selection_set(iid); f["items_sheet"].tree.focus(iid); return iid

    def purchase_item_total(self, row):
        qty = _num(row.get("quantity")) or 0; cost = _num(row.get("unit_cost")) or 0; percent = _num(row.get("discount_percent")) or 0
        row["total"] = round(qty * cost * (1 - percent / 100), 2)
        row["_display"] = {"quantity": f"{qty:g}", "unit_cost": f"{cost:,.4f}", "discount_percent": f"{percent:g}" if percent else "", "total": f'{row["total"]:,.2f}'}

    def purchase_item_changed(self, iid, key, text):
        row = self.purchase_form["items_sheet"].rows[iid]
        if key in ("item_code", "name"):
            item = self.item_by_code(text) if key == "item_code" else next((i for i in getattr(self, "inventory_rows", []) if i["name"].casefold() == text.strip().casefold()), None)
            if item: row.update(item_code=item["sku"], name=item["name"], unit=item["unit"], unit_cost=row.get("unit_cost") or item["average_cost"])
            elif key == "item_code" and text: messagebox.showwarning("Purchases", f"Item {text} was not found. Type the item name instead: a new item is created on saving."); return False
            else: row[key] = text.strip()
        elif key == "unit": row["unit"] = text.strip()
        else:
            value = _num(text, None)
            if value is None or value < 0: messagebox.showwarning("Purchases", "Enter a positive number"); return False
            row[key] = value
        self.purchase_item_total(row); self.purchase_items_changed()

    def purchase_items_changed(self):
        f = self.purchase_form; rows = [r for r in f["items_sheet"].ordered() if (r.get("item_code") or r.get("name")) and _num(r.get("quantity"))]
        if rows: f["vars"]["taxable"].set(f'{sum(r["total"] for r in rows):.2f}'); self.purchase_amounts_changed("taxable")

    def purchase_discount_changed(self, mode):
        self.purchase_form["discount_mode"] = mode
        self.purchase_amounts_changed("discount")

    def purchase_discount(self, taxable):
        f=self.purchase_form
        percent=_num(f["discount_percent"].get(),0)
        amount=_num(f["discount_amount"].get(),0)
        if percent is None or amount is None or percent<0 or percent>100 or amount<0:
            raise ValueError("Discount must be between 0% and 100%, or a positive amount")
        if f["discount_mode"]=="percent":
            amount=round(taxable*percent/100,2)
            f["discount_amount"].set(f"{amount:.2f}")
        else:
            if amount>taxable: raise ValueError("Discount cannot exceed taxable amount")
            f["discount_percent"].set(f"{amount/taxable*100:.4f}" if taxable else "0")
        return amount

    def purchase_item_lookup(self):
        iid, row = self.purchase_form["items_sheet"].selected()
        if not row: return
        window = tk.Toplevel(self); window.title("Items - F2"); window.geometry("640x420"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        search = tk.StringVar(); entry = tk.Entry(window, textvariable=search, width=40); entry.pack(padx=10, pady=8); entry.focus_set()
        tree = ttk.Treeview(window, columns=("sku", "name", "unit", "cost"), show="headings"); tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for key, label, width in (("sku", "Code", 100), ("name", "Item", 300), ("unit", "Unit", 70), ("cost", "Average Cost", 100)): tree.heading(key, text=label); tree.column(key, width=width)
        def fill(*_a):
            tree.delete(*tree.get_children()); text = search.get().casefold()
            for i in getattr(self, "inventory_rows", []):
                if i["active"] and (not text or text in f'{i["sku"]} {i["name"]} {i.get("category") or ""}'.casefold()): tree.insert("", "end", values=(i["sku"], i["name"], i["unit"], f'{i["average_cost"]:,.4f}'))
        def choose(_e=None):
            if tree.selection(): self.purchase_item_changed(iid, "item_code", tree.item(tree.selection()[0], "values")[0]); self.purchase_form["items_sheet"].refresh(iid); window.destroy()
        search.trace_add("write", fill); tree.bind("<Double-1>", choose); tree.bind("<Return>", choose); fill()

    def filter_found_purchases(self):
        from desktop import row_matches_search
        f = self.purchase_form; typed = f["find"].get().strip(); choices = list(f.get("find_map", {}))
        f["find_box"]["values"] = [c for c in choices if row_matches_search((c,),typed)]

    def purchase_found(self):
        f = self.purchase_form; invoice_id = f.get("find_map", {}).get(f["find"].get())
        if not invoice_id:
            matches=list(f["find_box"]["values"])
            if len(matches)==1: f["find"].set(matches[0]); invoice_id=f.get("find_map",{}).get(matches[0])
        if not invoice_id: return
        f["tree"].selection_set(str(invoice_id)); self.edit_purchase(); self.purchase_selected()
        f["items_sheet"].clear()
        try: lines = self.client.invoice_items(invoice_id)
        except Exception: lines = []
        for line in lines:
            if line.get("item_code"):
                row = {"item_code": line["item_code"], "name": line["description"], "quantity": float(line["quantity"]), "unit": line.get("unit") or "", "unit_cost": float(line["unit_price"]),
                       "discount_percent": float(line.get("discount_percent") or 0)}
                self.purchase_item_line(row)

    def import_purchases_excel(self):
        from importer import read_invoice_lines
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xlsm")])
        if not path: return
        try: invoices = read_invoice_lines(path, "purchases")
        except Exception as exc: return messagebox.showerror("Import Purchases", f"The Excel file could not be read: {exc}")
        if not messagebox.askyesno("Import Purchases", f"Import {len(invoices)} purchase invoice(s)? Items that do not exist are created automatically."): return
        done = 0; created = 0; errors = []
        for invoice in invoices:
            try:
                lines = []
                for line in invoice["lines"]:
                    before = len(getattr(self, "inventory_rows", []))
                    item = self.client.find_or_create_item(line["description"], line.get("unit") or "unit", line.get("item_code") or None)
                    if not self.item_by_code(item["sku"]): created += 1
                    cost = line["unit_price"] * (1 - (line.get("discount_percent") or 0) / 100)
                    lines.append({"item_code": item["sku"], "description": item["name"], "quantity": line["quantity"], "unit": line.get("unit") or item.get("unit"), "unit_price": round(cost, 4),
                                  "vat_rate": line.get("vat_rate", 11), "discount_percent": line.get("discount_percent") or 0, "warehouse": invoice.get("warehouse") or "MAIN"})
                self.client.create_manual_invoice({"invoice_number": invoice["invoice_number"], "invoice_date": invoice["invoice_date"], "party_name": invoice["party_name"], "kind": "purchases",
                                                   "currency": invoice["currency"], "status": "posted", "source_file": Path(path).name}, lines); done += 1
                self.load_inventory()
            except Exception as exc: errors.append(f"{invoice['invoice_number']}: {exc}")
        (messagebox.showwarning if errors else messagebox.showinfo)("Import Purchases", f"{done} purchase(s) imported and received into stock; {created} new item(s) created." + ("\n" + "\n".join(errors[:12]) if errors else ""))
        self.load_purchases(); self.load_invoices(); self.load_journal(); self.load_trial()

    def filter_suppliers(self):
        f = self.purchase_form; typed = f["vars"]["supplier"].get().strip().casefold(); names = list(f.get("supplier_map", {}))
        f["supplier_box"]["values"] = [n for n in names if typed in n.casefold()] if typed else names

    def purchase_supplier_chosen(self):
        f = self.purchase_form; party = f.get("supplier_map", {}).get(f["vars"]["supplier"].get())
        if party and party.get("currency"): f["vars"]["currency"].set(party["currency"])

    def purchase_amounts_changed(self, key):
        f = self.purchase_form; v = f["vars"]
        if key == "vat": f["vat_typed"] = True
        if key in ("taxable", "rate") and not f.get("pdf_vat_review"): f["vat_typed"] = False
        taxable = _num(v["taxable"].get()) or 0; exempt = _num(v["exempt"].get()) or 0; rate = _num(v["rate"].get()) or 0
        try: discount=self.purchase_discount(taxable)
        except ValueError as exc:
            f["discount_summary"].config(text=str(exc),fg=RED); return
        if not f["vat_typed"] and not f.get("pdf_vat_review"): v["vat"].set(f"{(taxable-discount) * rate / 100:.2f}" if taxable else "")
        vat = _num(v["vat"].get()) or 0
        rows=[r for r in f["items_sheet"].ordered() if (r.get("item_code") or r.get("name"))] if "items_sheet" in f else []
        line_discount=sum(round((_num(r.get("quantity")) or 0)*(_num(r.get("unit_cost")) or 0)*(_num(r.get("discount_percent")) or 0)/100,2) for r in rows)
        f["gross_summary"].config(text=f"{taxable+exempt+line_discount:,.2f}")
        f["discount_summary"].config(text=f"−{discount+line_discount:,.2f}  |  Total HT: {taxable+exempt-discount:,.2f}",fg=NAVY)
        f["total"].config(text=f"TOTAL TTC: {taxable+exempt-discount+vat:,.2f} {v['currency'].get()}")

    def new_purchase(self):
        f = self.purchase_form; v = f["vars"]; f["id"] = None; f["pdf"] = None; f["pdf_pending_invoice_id"] = None
        f["vat_typed"] = False; f["pdf_vat_review"] = False; f["pdf_suggested_type"] = ""
        for key in ("supplier", "number", "due", "taxable", "exempt", "vat"): v[key].set("")
        v["date"].set(self.fiscal_today()); v["rate"].set("11"); v["type"].set("Purchases"); v["account"].set("601100000"); f["department"].set("(none)"); f["project"].set("(none)")
        f["use"].set("Mixed (partial deduction)"); f["reverse"].set(False)
        f["discount_mode"]="percent"; f["discount_percent"].set("0"); f["discount_amount"].set("0")
        f["pdf_label"].config(text="No PDF", fg=MUTED); f["total"].config(text="TOTAL TTC: 0.00"); f["tree"].selection_remove(*f["tree"].selection())
        f["items_sheet"].clear(); f["find"].set("")

    def choose_purchase_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF invoice", "*.pdf"), ("Images", "*.png *.jpg *.jpeg")])
        if not path: return
        f = self.purchase_form
        try:
            size = Path(path).stat().st_size
            if not size or size > 15 * 1024 * 1024:
                raise ValueError("Choose a non-empty file smaller than 15 MB")
        except (OSError, ValueError) as exc:
            return messagebox.showerror("Purchase PDF", f"Could not select this file: {exc}")
        if f.get("id"):
            try:
                self.client.upload_attachment(f["id"], Path(path).name, mimetypes.guess_type(path)[0] or "application/pdf", Path(path).read_bytes())
            except Exception as exc:
                return messagebox.showerror("Purchase PDF", f"Could not confirm the PDF attached to purchase {f['id']}: {exc}\nCheck Attachments before trying again.")
            f["pdf"] = None
            f["pdf_label"].config(text=f"{Path(path).name} attached to purchase {f['id']}", fg=NAVY)
            self.load_purchases()
            return
        v = f["vars"]
        f["pdf"] = path; f["pdf_suggested_type"] = ""
        if path.lower().endswith(".pdf"):
            data = read_invoice_pdf(path)
            f["pdf_suggested_type"] = data.get("suggested_type") or ""
            if not f["id"]:
                f["pdf_vat_review"] = True
                f["vat_typed"] = True
                v["vat"].set(f'{data["vat"]:.2f}' if data.get("vat") is not None else "")
                if data.get("invoice_number") and not v["number"].get(): v["number"].set(data["invoice_number"])
                elif not v["number"].get():
                    typed = simpledialog.askstring(
                        "Purchase invoice number",
                        "The PDF number could not be read. Enter the invoice number as printed, or leave it for later.",
                        parent=self,
                    )
                    if str(typed or "").strip(): v["number"].set(typed.strip())
                if data.get("invoice_date"): v["date"].set(data["invoice_date"])
                elif v["date"].get() == self.fiscal_today(): v["date"].set("")
                if data.get("currency"): v["currency"].set(data["currency"])
                if data.get("subtotal") and not v["taxable"].get(): v["taxable"].set(f'{data["subtotal"]:.2f}')
                if data.get("party_name") and not v["supplier"].get(): v["supplier"].set(data["party_name"])
                item_note = self.add_purchase_pdf_items(data)
                self.purchase_amounts_changed("none")
            suggestion=f["pdf_suggested_type"]
            f["pdf_label"].config(text=f"{Path(path).name}: {data.get('notes', '')}" +
                                  (f"; Suggested Type: {suggestion} (review before Save)" if suggestion else
                                   "; Type unclear; review Purchases vs Assets before Save") +
                                  f"; {item_note}; PDF attaches when you press Save", fg=NAVY)
        else:
            item_note = self.add_purchase_pdf_items({"items": [], "subtotal": None})
            f["pdf_label"].config(text=f"{Path(path).name}: {item_note}; attachment saves with purchase on Save", fg=NAVY)

    def add_purchase_pdf_items(self, data):
        """Create inventory records at upload time; only reviewed lines enter the invoice on Save."""
        f = self.purchase_form
        if f["items_sheet"].ordered():
            return "existing item lines kept; review them before Save"
        items = data.get("items") or []
        if not items:
            name = simpledialog.askstring(
                "Purchase PDF item",
                "No readable item row was found. Enter the item name to create it in Inventory now, or Cancel to enter it manually later.",
                parent=self,
            )
            if not str(name or "").strip():
                return "no item created; enter an item name and upload again"
            items = [{"description": name.strip(), "quantity": 1, "unit_price": data.get("subtotal") or 0, "unit": "unit"}]
        party = f.get("supplier_map", {}).get(f["vars"]["supplier"].get())
        created = 0
        for row in items:
            try:
                item = self.client.find_or_create_item(
                    row["description"], row.get("unit") or "unit", None, party["id"] if party else None,
                )
            except Exception as exc:
                messagebox.showerror("Purchase PDF item", f"{created} item(s) added; could not create {row['description']}: {exc}")
                break
            self.purchase_item_line({
                "item_code": item["sku"], "name": item["name"], "quantity": row["quantity"],
                "unit": item["unit"], "unit_cost": row["unit_price"], "discount_percent": 0,
            })
            created += 1
        if created:
            self.load_inventory()
        return f"{created} item(s) created or matched in Inventory; review quantity and price before Save"

    def ai_read_purchase_pdf(self):
        path=filedialog.askopenfilename(filetypes=[("PDF invoice","*.pdf")])
        if not path: return
        try:
            size = Path(path).stat().st_size
            if not size or size > 15 * 1024 * 1024:
                raise ValueError("Choose a non-empty PDF smaller than 15 MB")
        except (OSError, ValueError) as exc:
            return messagebox.showerror("Purchase PDF", f"Could not select this file: {exc}")
        from ai_service import read_invoice_pdf as read_ai_pdf
        def show(data):
            f=self.purchase_form; v=f["vars"]; f["pdf"]=path
            for key,source in (("number","invoice_number"),("date","invoice_date"),("currency","currency"),("supplier","party_name")):
                if data.get(source): v[key].set(data[source])
            if data.get("subtotal") is not None: v["taxable"].set(f'{data["subtotal"]:.2f}')
            if data.get("vat") is not None: v["vat"].set(f'{data["vat"]:.2f}'); f["vat_typed"]=True
            if data.get("items"):
                if f["items_sheet"].ordered() and not messagebox.askyesno("AI PDF preview", "Replace the current purchase item lines with the suggested lines?"):
                    return
                f["items_sheet"].clear()
            item_note = self.add_purchase_pdf_items(data)
            self.purchase_amounts_changed("none")
            f["pdf_label"].config(text=f"AI preview of page 1: {Path(path).name} — {item_note}; PDF attaches on Save",fg=NAVY)
        self.run_ai_task(lambda key:read_ai_pdf(path,key),show)

    def ai_read_sales_pdf(self):
        path=filedialog.askopenfilename(filetypes=[("PDF invoice","*.pdf")])
        if not path: return
        from ai_service import read_invoice_pdf as read_ai_pdf
        def show(data):
            self.new_sales_invoice(confirm=False)
            if data.get("invoice_date"): self.sales_date.set(data["invoice_date"])
            if data.get("invoice_number"): self.sales_no.set(str(data["invoice_number"]).strip())
            if data.get("party_name"): self.sales_party.set(data["party_name"])
            if data.get("currency"): self.sales_currency.set(data["currency"])
            line=self.sales_items[0]
            line.update(description=f"As per {Path(path).name}",quantity=1,unit_price=data.get("subtotal") or data.get("total") or 0)
            if data.get("subtotal") and data.get("vat") is not None:
                line["vat_rate"]=round(data["vat"] / data["subtotal"]*100,4)
            self.recalculate_sales_item(line)
            self.sales_sheet.item(line["_iid"],values=self.sales_row_values(line))
            self.update_sales_totals()
            messagebox.showinfo("AI PDF preview",f"Read page 1 of {Path(path).name}. Check the customer, VAT, amounts and invoice number before Save.")
        self.run_ai_task(lambda key:read_ai_pdf(path,key),show)

    def purchase_payload(self):
        f = self.purchase_form; v = f["vars"]
        if f.get("pdf_vat_review") and not v["vat"].get().strip():
            raise ValueError("Confirm VAT from the PDF before saving; type 0 if there is no VAT")
        asset_account = v["account"].get().split(" - ", 1)[0].strip()
        if v["type"].get() == "Assets" and not asset_account.startswith("2"):
            raise ValueError("Assets require a class 2 fixed-asset account in Cost / Asset A/C")
        if v["type"].get() == "Purchases" and asset_account and not asset_account.startswith("6"):
            raise ValueError("Purchases require a class 6 purchase cost account; choose Assets for a fixed-asset account")
        self.purchase_items_changed()
        if not v["supplier"].get().strip(): raise ValueError("Choose or type the supplier")
        taxable = _num(v["taxable"].get()); exempt = _num(v["exempt"].get()); vat = _num(v["vat"].get()); rate = _num(v["rate"].get())
        if None in (taxable, exempt, vat, rate) or min(taxable, exempt, vat) < 0: raise ValueError("Amounts must be positive numbers")
        if not taxable and not exempt: raise ValueError("Enter the taxable or exempt amount")
        discount=self.purchase_discount(taxable)
        net_taxable=round(taxable-discount,2)
        party = f.get("supplier_map", {}).get(v["supplier"].get())
        invoice = {"invoice_number": v["number"].get().strip(), "invoice_date": v["date"].get().strip(), "due_date": v["due"].get().strip(), "party_name": party["name"] if party else v["supplier"].get().strip(),
                   "kind": "assets" if v["type"].get() == "Assets" else "purchases", "currency": v["currency"].get(), "status": "posted", "source_file": "Purchase Invoice",
                   "expense_account": asset_account or "601100000", "vat_account": v["vat_account"].get().split(" - ", 1)[0].strip() or "442660000",
                   "department": self.dimension_code(f["department"].get()), "project": self.dimension_code(f["project"].get()),
                   "vat_use": PURCHASE_USES.get(f["use"].get(), "mixed"), "vat_treatment": "reverse_charge" if f["reverse"].get() else "standard",
                   "invoice_discount_percent": f["discount_percent"].get(), "invoice_discount_amount": str(discount), "gross_before_discount": str(taxable+exempt)}
        if party and party.get("account_number"): invoice["supplier_account"] = party["account_number"]
        if v["type"].get() == "Assets": invoice["expense_no_vat_account"] = asset_account
        stock = [r for r in f["items_sheet"].ordered() if (r.get("item_code") or r.get("name")) and _num(r.get("quantity"))]
        if stock:
            lines = []; warehouse = (f["warehouse"].get() or "MAIN").split(" - ", 1)[0]
            for r in stock:
                code = r.get("item_code")
                if not code:
                    item = self.client.find_or_create_item(r["name"], r.get("unit") or "unit", None, party["id"] if party else None); code = item["sku"]
                cost = (_num(r["unit_cost"]) or 0) * (1 - (_num(r.get("discount_percent")) or 0) / 100)
                cost *= net_taxable/taxable if taxable else 1
                item_row = next((i for i in getattr(self, "inventory_rows", []) if i.get("sku") == code), None)
                line = {"item_code": code, "description": r.get("name") or code, "quantity": _num(r["quantity"]), "unit": r.get("unit") or "", "unit_price": round(cost, 6),
                              "discount_percent": _num(r.get("discount_percent")) or 0, "vat_rate": rate, "warehouse": warehouse}
                if item_row and item_row.get("cost_account") and v["type"].get() != "Assets": line["expense_account"] = item_row["cost_account"]
                lines.append(line)
            remaining_subtotal=net_taxable; remaining_vat=vat
            for index,line in enumerate(lines):
                subtotal=(round(line["quantity"]*line["unit_price"],2) if index<len(lines)-1 else remaining_subtotal)
                line["deductible_subtotal"]=subtotal
                line_vat=(round(subtotal*rate/100,2) if index<len(lines)-1 else remaining_vat)
                line["vat"]=line_vat
                remaining_subtotal=round(remaining_subtotal-subtotal,2); remaining_vat=round(remaining_vat-line_vat,2)
            if any(line["deductible_subtotal"]<0 or line["vat"]<0 for line in lines):
                raise ValueError("Item totals do not match the purchase amount and VAT. Check the item lines")
            if exempt: lines.append({"description": "Exempt part", "quantity": 1, "unit_price": exempt, "deductible_subtotal": 0, "non_deductible_subtotal": exempt, "vat_rate": 0, "vat": 0})
            return invoice, lines
        line = {"description": f"Supplier invoice {invoice['invoice_number']}".strip(), "quantity": 1, "unit_price": net_taxable, "deductible_subtotal": net_taxable,
                "non_deductible_subtotal": exempt, "vat_rate": rate, "vat": vat}
        return invoice, [line]

    def save_purchase(self):
        f = self.purchase_form
        pending_id = f.get("pdf_pending_invoice_id")
        if pending_id and f.get("id") == pending_id and f.get("pdf"):
            try:
                content = Path(f["pdf"]).read_bytes()
                attachments = self.client.attachments(pending_id)
                matching = (a for a in attachments if a["file_name"] == Path(f["pdf"]).name and a["size"] == len(content))
                if not any(self.client.download_attachment(a["id"])["content"] == content for a in matching):
                    self.client.upload_attachment(pending_id, Path(f["pdf"]).name,
                                                  mimetypes.guess_type(f["pdf"])[0] or "application/pdf", content)
            except Exception as exc:
                return messagebox.showwarning("Purchases",
                    f"Purchase {pending_id} is already SAVED; PDF is not confirmed attached: {exc}\n"
                    "Press Save to retry ONLY the PDF, or check Attachments. Do not create the invoice again.")
            self.new_purchase(); self.load_purchases(); self.load_invoices(); self.load_journal(); self.load_trial()
            return messagebox.showinfo("Purchases", f"PDF attached to the already saved purchase {pending_id}; invoice was not posted again.")
        if pending_id:
            f["pdf_pending_invoice_id"] = None
        try:
            pdf_content = Path(f["pdf"]).read_bytes() if f.get("pdf") else None
            if pdf_content is not None and (not pdf_content or len(pdf_content) > 15 * 1024 * 1024):
                raise ValueError("PDF must be non-empty and smaller than 15 MB")
        except (OSError, ValueError) as exc:
            return messagebox.showerror("Purchases", f"PDF cannot be read; purchase not saved: {exc}")
        try: invoice, lines = self.purchase_payload()
        except ValueError as exc: return messagebox.showwarning("Purchases", str(exc))
        suggestion=f.get("pdf_suggested_type")
        if suggestion and suggestion != f["vars"]["type"].get():
            if not messagebox.askyesno("Review PDF type",
                    f"This PDF suggests {suggestion}, but the form is set to {f['vars']['type'].get()}.\n"
                    "A paid Expense belongs in Expenses; an unpaid supplier bill belongs in Purchases. "
                    "Confirm the type and accounts before posting.\n\nSave with the selected type anyway?"):
                return
        try:
            invoice_id = self.client.replace_invoice(f["id"], invoice, lines) if f["id"] else self.client.create_manual_invoice(invoice, lines)["invoice_id"]
        except Exception as exc:
            return messagebox.showerror("Purchases", f"{exc}\nIf the result is uncertain, check the purchase list before retrying.")
        if pdf_content is not None:
            try:
                self.client.upload_attachment(invoice_id, Path(f["pdf"]).name,
                                              mimetypes.guess_type(f["pdf"])[0] or "application/pdf", pdf_content)
            except Exception as exc:
                f["id"] = invoice_id
                f["pdf_pending_invoice_id"] = invoice_id
                f["pdf_label"].config(text=f"Purchase {invoice_id} SAVED, PDF not attached; press Save to retry PDF only", fg=RED)
                self.load_purchases(); self.load_invoices(); self.load_journal(); self.load_trial()
                return messagebox.showwarning("Purchases",
                    f"Purchase {invoice_id} is SAVED, but the PDF attachment failed: {exc}\n"
                    "Press Save again to retry ONLY the PDF; the purchase and its items will not be posted twice.")
        messagebox.showinfo("Purchases", "Purchase invoice saved" + (" with its PDF" if f["pdf"] else ""))
        self.new_purchase(); self.load_purchases(); self.load_invoices(); self.load_journal(); self.load_trial()

    def purchase_rows_list(self):
        try: rows = self.client.invoices()
        except Exception: return []
        return [r for r in rows if r["kind"] == "purchase" and r.get("entry_type") in ("purchases", "assets") and r.get("status") != "cancelled"]

    def load_purchases(self):
        f = getattr(self, "purchase_form", None)
        if not f or not f["tree"].winfo_exists(): return
        try: parties = self.client.parties()
        except Exception: parties = []
        f["supplier_map"] = {f'{p["name"]} | {p.get("account_number") or ""}': p for p in parties if p["kind"] in ("supplier", "both")}
        f["supplier_box"]["values"] = list(f["supplier_map"])
        f["lc_party_map"] = {f'{p["name"]} | {p.get("account_number") or ""}': p for p in parties
                             if (p.get("account_category") in ("supplier", "asset_supplier", "other_payable")) or p["kind"] in ("supplier", "both")}
        if f.get("lc_party_box"): f["lc_party_box"]["values"] = list(f["lc_party_map"])
        rows = self.purchase_rows_list(); lists = self.dimension_lists()
        departments = {d["id"]: d["code"] for d in lists["departments"]}; projects = {p["id"]: p["code"] for p in lists["projects"]}
        landed = {}
        for r in rows:
            if r.get("description") and str(r.get("description")).startswith("Landed cost of"): continue
        customs = [r for r in rows if (r.get("description") or "").startswith("Landed cost of")]
        f["rows"] = {str(r["id"]): r for r in rows if not (r.get("description") or "").startswith("Landed cost of")}
        for r in customs:
            key = (r.get("description") or "").split("Landed cost of ", 1)[-1].split(" (", 1)[0]
            landed[key] = landed.get(key, 0) + float(r.get("total") or 0)
        f["find_map"] = {f'{r["invoice_number"]} | {_dd(r["invoice_date"])} | {r.get("party_name") or ""} | {float(r.get("total") or 0):,.2f} {r["currency"]}': r["id"] for r in f["rows"].values()}
        f["find_box"]["values"] = list(f["find_map"])
        try: f["warehouse_box"]["values"] = [f'{w["code"]} - {w["name"]}' for w in self.client.warehouses() if w["active"]]
        except Exception: pass
        if not f["warehouse"].get() and f["warehouse_box"]["values"]: f["warehouse"].set(f["warehouse_box"]["values"][0])
        f["tree"].delete(*f["tree"].get_children())
        for r in f["rows"].values():
            f["tree"].insert("", "end", iid=str(r["id"]), values=(r["invoice_number"], _dd(r["invoice_date"]), r.get("party_name") or "", (r.get("entry_type") or "").title(), r["currency"],
                f'{float(r.get("deductible_subtotal") or 0):,.2f}', f'{float(r.get("non_deductible_subtotal") or 0):,.2f}', f'{float(r.get("vat") or 0):,.2f}', f'{float(r.get("total") or 0):,.2f}',
                f'{landed.get(r["invoice_number"], 0):,.2f}' if landed.get(r["invoice_number"]) else "", r.get("attachment_count") or "",
                " / ".join(x for x in (departments.get(r.get("department_id")), projects.get(r.get("project_id"))) if x)))

    def selected_purchase(self):
        selected = self.purchase_form["tree"].selection()
        return self.purchase_form.get("rows", {}).get(selected[0]) if selected else None

    def purchase_selected(self):
        row = self.selected_purchase(); f = self.purchase_form
        if not row: f["lc_label"].config(text=""); return
        try: costs = self.client.landed_costs(row["id"])
        except Exception: costs = []
        total = sum(c["total"] for c in costs)
        f["lc_label"].config(text=f"{row['invoice_number']}: {len(costs)} cost line(s), {total:,.2f} {row['currency']}" if costs else f"{row['invoice_number']}: no cost on purchase yet")

    def edit_purchase(self):
        row = self.selected_purchase(); f = self.purchase_form; v = f["vars"]
        if not row: return
        if row.get("status") in ("deleted","cancelled"):
            return messagebox.showwarning("Purchases","Deleted or cancelled purchases cannot be edited")
        f["id"] = row["id"]; f["pdf"] = None; f["vat_typed"] = True
        discount=_num(row.get("invoice_discount_amount")) or 0
        net_taxable=float(row.get("deductible_subtotal") or 0)
        gross_taxable=round(net_taxable+discount,2)
        f["discount_mode"]="amount"; f["discount_amount"].set(f"{discount:.2f}")
        f["discount_percent"].set(str(row.get("invoice_discount_percent") or "0"))
        f["items_sheet"].clear()
        try: saved_items=self.client.invoice_detail(row["id"]).get("items",[])
        except Exception: saved_items=[]
        factor=net_taxable/gross_taxable if gross_taxable else 1
        for item in saved_items:
            if not item.get("item_code"): continue
            line_percent=_num(item.get("discount_percent")) or 0
            unit_cost=float(item.get("unit_price") or 0)/max((1-line_percent/100)*factor,0.000001)
            self.purchase_item_line({"item_code":item["item_code"],"name":item.get("description") or "", "quantity":_num(item.get("quantity")) or 1,
                                     "unit":item.get("unit") or "", "unit_cost":unit_cost,"discount_percent":line_percent})
        label = next((n for n, p in f.get("supplier_map", {}).items() if p["name"] == row.get("party_name")), row.get("party_name") or "")
        for key, value in (("supplier", label), ("number", row["invoice_number"]), ("date", _dd(row["invoice_date"])), ("due", _dd(row.get("due_date")) if row.get("due_date") else ""),
                           ("currency", row["currency"]), ("type", "Assets" if row.get("entry_type") == "assets" else "Purchases"), ("taxable", f'{gross_taxable:.2f}'),
                           ("exempt", f'{float(row.get("non_deductible_subtotal") or 0):.2f}'), ("vat", f'{float(row.get("vat") or 0):.2f}'), ("account", row.get("expense_account") or ""),
                           ("vat_account", row.get("vat_account") or "")):
            v[key].set(value)
        taxable = float(row.get("deductible_subtotal") or 0); v["rate"].set(f'{float(row.get("vat") or 0) / taxable * 100:g}' if taxable else "11")
        lists = self.dimension_lists()
        f["department"].set(next((f'{d["code"]} - {d["name"]}' for d in lists["departments"] if d["id"] == row.get("department_id")), "(none)"))
        f["project"].set(next((f'{p["code"]} - {p["name"]}' for p in lists["projects"] if p["id"] == row.get("project_id")), "(none)"))
        f["use"].set(next((k for k, val in PURCHASE_USES.items() if val == (row.get("vat_use") or "mixed")), "Mixed (partial deduction)")); f["reverse"].set(row.get("vat_treatment") == "reverse_charge")
        f["pdf_label"].config(text=f"Editing {row['invoice_number']} ({row.get('attachment_count') or 0} document(s) attached)", fg=NAVY); self.purchase_amounts_changed("none")

    def delete_purchase(self):
        row = self.selected_purchase() if not self.purchase_form["id"] else self.purchase_form["rows"].get(str(self.purchase_form["id"]))
        if not row: return messagebox.showwarning("Purchases", "Select a purchase first")
        if not messagebox.askyesno("Purchases", f"Mark purchase {row['invoice_number']} DELETED? Its number stays in the invoice list; the journal entry is removed."): return
        try: self.client.delete_invoice(row["id"])
        except Exception as exc: return messagebox.showerror("Purchases", str(exc))
        self.new_purchase(); self.load_purchases(); self.load_invoices(); self.load_journal(); self.load_trial()

    def purchase_attachments(self):
        row = self.selected_purchase()
        if not row: return messagebox.showwarning("Purchases", "Select a purchase first")
        self.invoice_rows = {**getattr(self, "invoice_rows", {}), str(row["id"]): row}
        self.invoice_tree.selection_set(()) if hasattr(self, "invoice_tree") else None
        self.show_attachments_for(row["id"], row["invoice_number"])

    def show_attachments_for(self, invoice_id, number):
        try: items = self.client.attachments(invoice_id)
        except Exception as exc: return messagebox.showerror("Attachments", str(exc))
        if not items: return messagebox.showinfo("Attachments", f"No documents attached to {number}")
        window = tk.Toplevel(self); window.title(f"Documents - {number}"); window.configure(bg=LIGHT); window.geometry("600x300"); window.transient(self)
        tree = ttk.Treeview(window, columns=("file", "size", "uploaded"), show="headings")
        for key, label, width in (("file", "File", 300), ("size", "Size", 90), ("uploaded", "Uploaded", 170)): tree.heading(key, text=label); tree.column(key, width=width)
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        for item in items: tree.insert("", "end", iid=str(item["id"]), values=(item["file_name"], f'{item["size"] / 1024:,.0f} KB', str(item["uploaded_at"])[:16]))
        def download():
            if not tree.selection(): return
            record = next(i for i in items if str(i["id"]) == tree.selection()[0]); path = filedialog.asksaveasfilename(initialfile=record["file_name"], parent=window)
            if path: Path(path).write_bytes(self.client.download_attachment(record["id"])["content"])
        self.action_button(window, "Download Selected", download).pack(pady=(0, 8))

    def landed_cost_payload(self):
        f = self.purchase_form; item = {k: v.get().strip() for k, v in f["lc"].items()}
        for key in ("freight", "insurance", "customs_duties", "broker_fees", "other_costs", "import_vat"):
            if _num(item[key]) is None: raise ValueError(f"{key.replace('_', ' ').title()} must be a number")
        party = f.get("lc_party_map", {}).get(f["lc"]["party_name"].get().strip())
        if party: item["party_id"] = party["id"]; item["party_name"] = party["name"]
        item["cost_accounts"] = {key: var.get().split(" - ", 1)[0].strip() for key, var in f["lc_accounts"].items()}
        return item

    def edit_landed_cost_accounts(self):
        import chart_extra
        window = tk.Toplevel(self); window.title("Cost on Purchase Accounts"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        tk.Label(window, text="Default accounts are filled in. Edit an account when this purchase needs a different posting.", bg=LIGHT, fg=NAVY).pack(anchor="w", padx=12, pady=10)
        for key, var in self.purchase_form["lc_accounts"].items():
            row = tk.Frame(window, bg=LIGHT); row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=key.replace("_", " ").title(), width=18, anchor="w", bg=LIGHT).pack(side="left")
            self.account_search_box(row, var, 24).pack(side="left")
        self.action_button(window, "Restore defaults", lambda: [var.set(chart_extra.LANDED_COST_ACCOUNTS[key]) for key, var in self.purchase_form["lc_accounts"].items()]).pack(side="left", padx=12, pady=12)
        self.action_button(window, "Done", window.destroy).pack(side="right", padx=12, pady=12)

    def save_landed_cost(self):
        row = self.selected_purchase()
        if not row: return messagebox.showwarning("Cost on Purchase", "Select the purchase invoice in the list first")
        try: item = self.landed_cost_payload(); self.client.add_landed_cost(row["id"], item)
        except Exception as exc: return messagebox.showerror("Cost on Purchase", str(exc))
        for var in self.purchase_form["lc"].values(): var.set("")
        self.purchase_form["lc"]["party_name"].set("Lebanese Customs")
        messagebox.showinfo("Cost on Purchase", f"Cost on purchase added to {row['invoice_number']}. Import VAT goes to the VAT return as customs VAT.")
        self.load_purchases(); self.purchase_form["tree"].selection_set(str(row["id"])); self.load_invoices(); self.load_journal(); self.load_trial()

    def import_customs_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xlsm")])
        if not path: return
        try: costs = read_customs_costs(path)
        except Exception as exc: return messagebox.showerror("Cost on Purchase", f"The Excel file could not be read: {exc}")
        for key, value in costs.items():
            if key in self.purchase_form["lc"] and value not in (None, "", 0): self.purchase_form["lc"][key].set(f"{value:.2f}" if isinstance(value, float) else str(value))
        messagebox.showinfo("Cost on Purchase", "Amounts filled from the Excel file. Check them, select the purchase, then press 'Add Cost on Purchase'.")

    def attach_customs_pdf(self):
        row = self.selected_purchase()
        if not row: return messagebox.showwarning("Cost on Purchase", "Select the purchase invoice first")
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf"), ("Images", "*.png *.jpg *.jpeg")])
        if not path: return
        try:
            costs = self.client.landed_costs(row["id"]); target = costs[-1]["id"] if costs else row["id"]
            self.client.upload_attachment(target, Path(path).name, mimetypes.guess_type(path)[0] or "application/pdf", Path(path).read_bytes())
        except Exception as exc: return messagebox.showerror("Cost on Purchase", str(exc))
        messagebox.showinfo("Cost on Purchase", f"Customs document attached to {'the cost on purchase' if costs else row['invoice_number']}"); self.load_purchases()

    # ---- expenses
    def build_expenses_page(self, page):
        f = {"id": None, "pdf": None, "vars": {k: tk.StringVar() for k in ("date", "description", "category", "currency", "with_vat", "without_vat", "vat", "account", "no_vat_account",
                                                                          "vat_account", "payment_account", "reference")}}
        v = f["vars"]; v["date"].set(self.fiscal_today()); v["currency"].set("USD"); v["category"].set("General")
        v["account"].set("601100000"); v["no_vat_account"].set("601100001"); v["vat_account"].set("44216"); v["payment_account"].set("531")
        f["department"] = tk.StringVar(); f["project"] = tk.StringVar(); f["non_deductible"] = tk.BooleanVar(value=False); f["vat_typed"] = False; self.expense_form = f
        f["use"] = tk.StringVar(value="Mixed (partial deduction)")
        box = tk.LabelFrame(page, text="Expense", bg=LIGHT, padx=8, pady=5); box.pack(fill="x", padx=8, pady=6)
        r1 = tk.Frame(box, bg=LIGHT); r1.pack(fill="x")
        f["number_label"] = tk.Label(r1, text="New expense", bg=LIGHT, fg=NAVY, font=("Segoe UI", 9, "bold")); f["number_label"].pack(side="left", padx=(0, 10))
        tk.Label(r1, text="Date", bg=LIGHT).pack(side="left"); self.date_entry(r1, v["date"], 11).pack(side="left", padx=(4, 8))
        tk.Label(r1, text="Description", bg=LIGHT, font=("Segoe UI", 9, "bold")).pack(side="left"); tk.Entry(r1, textvariable=v["description"], width=32).pack(side="left", padx=(4, 8))
        tk.Label(r1, text="Category", bg=LIGHT).pack(side="left"); tk.Entry(r1, textvariable=v["category"], width=13).pack(side="left", padx=(4, 8))
        ttk.Combobox(r1, textvariable=v["currency"], values=self.currency_codes, state="readonly", width=5).pack(side="left", padx=4)
        tk.Label(r1, text="Reference", bg=LIGHT).pack(side="left"); tk.Entry(r1, textvariable=v["reference"], width=13).pack(side="left", padx=4)
        r2 = tk.Frame(box, bg=LIGHT); r2.pack(fill="x", pady=(5, 0))
        for label, key, width in (("With VAT (before VAT)", "with_vat", 12), ("Without VAT", "without_vat", 11), ("VAT", "vat", 10)):
            tk.Label(r2, text=label, bg=LIGHT).pack(side="left"); entry = tk.Entry(r2, textvariable=v[key], width=width); entry.pack(side="left", padx=(4, 8))
            entry.bind("<KeyRelease>", lambda e, k=key: self.expense_amounts_changed(k))
        f["total"] = tk.Label(r2, text="Total: 0.00", bg=LIGHT, fg=NAVY, font=("Segoe UI", 10, "bold")); f["total"].pack(side="left", padx=6)
        tk.Checkbutton(r2, text="VAT not deductible", variable=f["non_deductible"], bg=LIGHT).pack(side="left", padx=8)
        r3 = tk.Frame(box, bg=LIGHT); r3.pack(fill="x", pady=(5, 0))
        for label, key in (("Expense A/C (626-69)", "account"), ("No-VAT A/C", "no_vat_account"), ("VAT A/C", "vat_account"), ("Paid from", "payment_account")):
            tk.Label(r3, text=label, bg=LIGHT).pack(side="left")
            if key in ("account", "no_vat_account", "payment_account"):
                box_widget = ttk.Combobox(r3, textvariable=v[key], width=24 if key == "account" else 14); box_widget.pack(side="left", padx=(4, 8)); f[f"{key}_box"] = box_widget
            else: self.account_search_box(r3, v[key], 9).pack(side="left", padx=(4, 8))
        tk.Button(r3, text="Suggest A/C", command=self.suggest_expense_account,
                  bg=GOLD, fg=NAVY, border=0).pack(side="left", padx=4)
        tk.Button(r3, text="AI Suggest A/C", command=self.ai_suggest_expense_account,
                  bg=NAVY, fg="white", border=0).pack(side="left", padx=4)
        r4 = tk.Frame(box, bg=LIGHT); r4.pack(fill="x", pady=(5, 0))
        self.dimension_selectors(r4, f["department"], f["project"])
        tk.Label(r4, text="VAT used for", bg=LIGHT).pack(side="left"); ttk.Combobox(r4, textvariable=f["use"], values=list(PURCHASE_USES), state="readonly", width=24).pack(side="left", padx=4)
        f["pdf_label"] = tk.Label(r4, text="No PDF", bg=LIGHT, fg=MUTED); f["pdf_label"].pack(side="left", padx=6)
        r5 = tk.Frame(box, bg=LIGHT); r5.pack(fill="x", pady=(5, 0))
        self.action_button(r5, "New", self.new_expense).pack(side="left", padx=(0, 3))
        tk.Button(r5, text="Save", command=self.save_expense, bg=GOLD, fg=NAVY, border=0, padx=18, pady=6, font=("Segoe UI", 9, "bold")).pack(side="left", padx=3)
        tk.Button(r5, text="Delete", command=self.delete_expense, bg=RED, fg="white", border=0, padx=12, pady=6).pack(side="left", padx=3)
        self.action_button(r5, "Upload PDF", self.choose_expense_pdf).pack(side="left", padx=3)
        self.action_button(r5, "Attachments", self.expense_attachments_window).pack(side="left", padx=3)
        self.action_button(r5, "Import Expenses Excel", self.import_expenses_excel).pack(side="left", padx=3)
        f["tree"] = ttk.Treeview(page, columns=[f"c{i}" for i in range(12)])  # kept hidden: the Find box replaces the list
        find = tk.Frame(page, bg=LIGHT); find.pack(fill="x", padx=8, pady=(0, 4), before=box); f["find"] = tk.StringVar()
        tk.Label(find, text="Find expense (No., description, date)", bg=LIGHT, font=("Segoe UI", 9, "bold")).pack(side="left")
        f["find_box"] = ttk.Combobox(find, textvariable=f["find"], width=50); f["find_box"].pack(side="left", padx=6)
        f["find_box"].bind("<<ComboboxSelected>>", lambda _e: self.expense_found())
        f["find_box"].bind("<KeyRelease>", lambda _e: self.filter_found_expenses())
        f["find_box"].bind("<Return>", lambda _e: self.expense_found())

    def expense_amounts_changed(self, key):
        f = self.expense_form; v = f["vars"]
        if key == "vat": f["vat_typed"] = True
        if key == "with_vat" and not f.get("pdf_vat_review"): f["vat_typed"] = False
        base = _num(v["with_vat"].get()) or 0
        if not f["vat_typed"] and not f.get("pdf_vat_review"): v["vat"].set(f"{base * 0.11:.2f}" if base else "")
        total = base + (_num(v["without_vat"].get()) or 0) + (_num(v["vat"].get()) or 0)
        f["total"].config(text=f"Total: {total:,.2f} {v['currency'].get()}")

    def new_expense(self):
        f = self.expense_form; v = f["vars"]; f["id"] = None; f["pdf"] = None; f["vat_typed"] = False; f["pdf_vat_review"] = False; f["pdf_suggested_type"] = ""
        for key in ("description", "with_vat", "without_vat", "vat", "reference"): v[key].set("")
        v["date"].set(self.fiscal_today()); f["non_deductible"].set(False); f["department"].set("(none)"); f["project"].set("(none)")
        f["pdf_label"].config(text="No PDF", fg=MUTED); f["total"].config(text="Total: 0.00"); f["number_label"].config(text="New expense")

    def choose_expense_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf"), ("Images", "*.png *.jpg *.jpeg")])
        if not path: return
        f = self.expense_form; v = f["vars"]; f["pdf"] = path; f["pdf_suggested_type"] = ""
        if path.lower().endswith(".pdf") and not f["id"]:
            data = read_invoice_pdf(path)
            f["pdf_suggested_type"] = data.get("suggested_type") or ""
            f["pdf_vat_review"] = True
            f["vat_typed"] = True
            v["vat"].set(f'{data["vat"]:.2f}' if data.get("vat") is not None else "")
            if data.get("invoice_number") and not v["reference"].get(): v["reference"].set(data["invoice_number"])
            if data.get("invoice_date"): v["date"].set(data["invoice_date"])
            elif v["date"].get() == self.fiscal_today(): v["date"].set("")
            if data.get("currency"): v["currency"].set(data["currency"])
            if data.get("party_name") and not v["description"].get(): v["description"].set(data["party_name"])
            if data.get("subtotal") and not v["with_vat"].get(): v["with_vat"].set(f'{data["subtotal"]:.2f}')
            self.expense_amounts_changed("none")
            suggestion=f["pdf_suggested_type"]
            f["pdf_label"].config(text=f"{Path(path).name}: {data.get('notes', '')}" +
                                  (f"; Suggested Type: {suggestion} (review before Save)" if suggestion else
                                   "; Type unclear; confirm this is a paid Expense before Save"), fg=NAVY)
        else: f["pdf_label"].config(text=Path(path).name, fg=NAVY)

    def expense_payload(self):
        v = self.expense_form["vars"]; f = self.expense_form
        if f.get("pdf_vat_review") and not v["vat"].get().strip():
            raise ValueError("Confirm VAT from the PDF before saving; type 0 if there is no VAT")
        if not v["description"].get().strip(): raise ValueError("Enter the expense description")
        amounts = {k: _num(v[k].get()) for k in ("with_vat", "without_vat", "vat")}
        if None in amounts.values() or min(amounts.values()) < 0: raise ValueError("Amounts must be positive numbers")
        if not amounts["with_vat"] and not amounts["without_vat"]: raise ValueError("Enter the expense amount")
        return {"expense_date": v["date"].get().strip(), "description": v["description"].get().strip(), "category": v["category"].get().strip(), "currency": v["currency"].get(),
                "with_vat_subtotal": amounts["with_vat"], "without_vat_subtotal": amounts["without_vat"], "vat": amounts["vat"], "reference": v["reference"].get().strip(),
                "expense_account": v["account"].get().split(" - ", 1)[0].strip(), "expense_without_vat_account": v["no_vat_account"].get().split(" - ", 1)[0].strip(),
                "vat_account": v["vat_account"].get().split(" - ", 1)[0].strip(), "payment_account": v["payment_account"].get().split(" - ", 1)[0].strip(),
                "vat_recoverable": not f["non_deductible"].get(), "department": self.dimension_code(f["department"].get()), "project": self.dimension_code(f["project"].get()),
                "vat_use": PURCHASE_USES.get(f["use"].get(), "mixed")}

    def save_expense(self):
        f = self.expense_form
        try: payload = self.expense_payload()
        except ValueError as exc: return messagebox.showwarning("Expenses", str(exc))
        suggestion=f.get("pdf_suggested_type")
        if suggestion and suggestion != "Expenses":
            if not messagebox.askyesno("Review PDF type",
                    f"This PDF suggests {suggestion}, but this form records a PAID Expense.\n"
                    "Confirm it was paid and is not a supplier invoice or a capital asset.\n\nSave as a paid Expense anyway?"):
                return
        try:
            expense_id = self.client.update_expense(f["id"], payload) if f["id"] else self.client.add_expense(payload)["expense_id"]
            if f["pdf"]: self.client.upload_expense_attachment(expense_id, Path(f["pdf"]).name, mimetypes.guess_type(f["pdf"])[0] or "application/pdf", Path(f["pdf"]).read_bytes())
        except Exception as exc: return messagebox.showerror("Expenses", str(exc))
        messagebox.showinfo("Expenses", "Expense saved" + (" with its PDF" if f["pdf"] else ""))
        self.new_expense(); self.load_expenses(); self.load_journal(); self.load_trial(); self.load_profit_loss()

    def load_expenses(self):
        f = getattr(self, "expense_form", None)
        if not f or not f["tree"].winfo_exists(): return
        try: rows = self.client.expenses()
        except Exception: rows = []
        lists = self.dimension_lists(); departments = {d["id"]: d["code"] for d in lists["departments"]}; projects = {p["id"]: p["code"] for p in lists["projects"]}
        f["rows"] = {str(r["id"]): r for r in rows}; f["tree"].delete(*f["tree"].get_children())
        f["find_map"] = {f'{r.get("expense_number") or r["id"]} | {_dd(r["expense_date"])} | {r["description"]} | {r["total"]:,.2f} {r["currency"]}': r["id"] for r in rows}; f["find_box"]["values"] = list(f["find_map"])
        if not getattr(self, "_expense_accounts", None):
            try:
                accounts = self.client.accounts()
                def in_range(code): code = str(code); return code[:3] in ("626", "627", "628", "629") or code[:2] in ("63", "64", "65", "66", "67", "68", "69")
                self._expense_accounts = [f'{a["code"]} - {a["name_en"]}' for a in accounts if in_range(a["code"]) and str(a["code"]).isdigit()]
                self._cash_accounts = self._cash_accounts if getattr(self, "_cash_accounts", None) else [f'{a["code"]} - {a["name_en"]}' for a in accounts if str(a["code"]).startswith(("511", "512", "519", "53"))]
            except Exception: self._expense_accounts = []
        f["account_box"]["values"] = self._expense_accounts; f["no_vat_account_box"]["values"] = self._expense_accounts; f["payment_account_box"]["values"] = getattr(self, "_cash_accounts", [])
        for r in rows:
            f["tree"].insert("", "end", iid=str(r["id"]), values=(r.get("expense_number") or f"EXP-{r['id']}", _dd(r["expense_date"]), r["description"], r.get("category") or "", r["currency"],
                f'{r.get("with_vat_subtotal") or 0:,.2f}', f'{r.get("without_vat_subtotal") or 0:,.2f}', f'{r["vat"]:,.2f}', f'{r["total"]:,.2f}',
                "Yes" if r.get("vat_recoverable", 1) else "NO", r.get("attachment_count") or "", " / ".join(x for x in (departments.get(r.get("department_id")), projects.get(r.get("project_id"))) if x)))

    def suggest_expense_account(self):
        from ai_mapper import suggest_account
        form = self.expense_form["vars"]
        suggestion = suggest_account(form["description"].get(), getattr(self, "_expense_accounts", []))
        if not suggestion:
            messagebox.showinfo("Account suggestion", "Enter a more specific expense description and choose an account manually.")
            return
        if messagebox.askyesno("Account suggestion",
                               f"Use {suggestion['code']} - {suggestion['name']}?\nPlease verify the account before saving."):
            form["account"].set(suggestion["code"])

    def ai_suggest_expense_account(self):
        from ai_service import suggest_account
        form=self.expense_form["vars"]
        description=form["description"].get().strip()
        accounts=list(getattr(self,"_expense_accounts",[]))
        def show(suggestion):
            if messagebox.askyesno("AI account suggestion",f"{suggestion['code']} - {suggestion['name']}\n{suggestion['reason']}\n\nUse this account?"):
                form["account"].set(suggestion["code"])
        self.run_ai_task(lambda key:suggest_account(description,accounts,key),show)

    def filter_found_expenses(self):
        from desktop import row_matches_search
        f=self.expense_form
        f["find_box"]["values"]=[label for label in f.get("find_map",{}) if row_matches_search((label,),f["find"].get())]

    def expense_found(self):
        f = self.expense_form; expense_id = f.get("find_map", {}).get(f["find"].get())
        if not expense_id:
            matches=list(f["find_box"]["values"])
            if len(matches)==1: f["find"].set(matches[0]); expense_id=f.get("find_map",{}).get(matches[0])
        if expense_id: f["tree"].selection_set(str(expense_id)); self.edit_expense()

    def edit_expense(self):
        f = self.expense_form; selected = f["tree"].selection()
        if not selected: return
        r = f["rows"][selected[0]]; v = f["vars"]; f["id"] = r["id"]; f["pdf"] = None; f["vat_typed"] = True
        for key, value in (("date", _dd(r["expense_date"])), ("description", r["description"]), ("category", r.get("category") or ""), ("currency", r["currency"]),
                           ("with_vat", f'{r.get("with_vat_subtotal") or 0:.2f}'), ("without_vat", f'{r.get("without_vat_subtotal") or 0:.2f}'), ("vat", f'{r["vat"]:.2f}'),
                           ("reference", r.get("reference") or ""), ("account", r["expense_account"]), ("no_vat_account", r.get("expense_without_vat_account") or "601100001"),
                           ("vat_account", r["vat_account"]), ("payment_account", r["payment_account"])):
            v[key].set(value)
        f["non_deductible"].set(not r.get("vat_recoverable", 1)); lists = self.dimension_lists()
        f["use"].set(next((k for k, val in PURCHASE_USES.items() if val == (r.get("vat_use") or "mixed")), "Mixed (partial deduction)"))
        f["department"].set(next((f'{d["code"]} - {d["name"]}' for d in lists["departments"] if d["id"] == r.get("department_id")), "(none)"))
        f["project"].set(next((f'{p["code"]} - {p["name"]}' for p in lists["projects"] if p["id"] == r.get("project_id")), "(none)"))
        f["number_label"].config(text=f"Editing {r.get('expense_number') or r['id']}"); f["pdf_label"].config(text=f"{r.get('attachment_count') or 0} document(s) attached", fg=NAVY)
        self.expense_amounts_changed("none")

    def delete_expense(self):
        f = self.expense_form; selected = f["tree"].selection()
        target = f["id"] or (f["rows"][selected[0]]["id"] if selected else None)
        if not target: return messagebox.showwarning("Expenses", "Select an expense first")
        if not messagebox.askyesno("Expenses", "Delete this expense and its journal entry?"): return
        try: self.client.delete_expense(target)
        except Exception as exc: return messagebox.showerror("Expenses", str(exc))
        self.new_expense(); self.load_expenses(); self.load_journal(); self.load_trial()

    def expense_attachments_window(self):
        f = self.expense_form; selected = f["tree"].selection()
        target = f["id"] or (f["rows"][selected[0]]["id"] if selected else None)
        if not target: return messagebox.showwarning("Expenses", "Select an expense first")
        try: items = self.client.expense_attachments(target)
        except Exception as exc: return messagebox.showerror("Expenses", str(exc))
        if not items: return messagebox.showinfo("Expenses", "No documents attached to this expense")
        window = tk.Toplevel(self); window.title("Expense documents"); window.configure(bg=LIGHT); window.geometry("560x280"); window.transient(self)
        tree = ttk.Treeview(window, columns=("file", "size"), show="headings"); tree.heading("file", text="File"); tree.heading("size", text="Size"); tree.pack(fill="both", expand=True, padx=8, pady=8)
        for item in items: tree.insert("", "end", iid=str(item["id"]), values=(item["file_name"], f'{item["size"] / 1024:,.0f} KB'))
        def download():
            if not tree.selection(): return
            record = next(i for i in items if str(i["id"]) == tree.selection()[0]); path = filedialog.asksaveasfilename(initialfile=record["file_name"], parent=window)
            if path: Path(path).write_bytes(self.client.download_expense_attachment(record["id"])["content"])
        self.action_button(window, "Download Selected", download).pack(pady=(0, 8))

    def import_expenses_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xlsm")])
        if not path: return
        try: rows = read_expenses(path)
        except Exception as exc: return messagebox.showerror("Expenses", f"The Excel file could not be read: {exc}")
        if not rows: return messagebox.showwarning("Expenses", "No expense rows were found")
        if not messagebox.askyesno("Expenses", f"Import {len(rows)} expense(s) from this file?"): return
        done = 0; errors = []
        for row in rows:
            try: self.client.add_expense(row); done += 1
            except Exception as exc: errors.append(f"Row {row['source_row']}: {exc}")
        (messagebox.showwarning if errors else messagebox.showinfo)("Expenses", f"{done} expense(s) imported." + ("\n" + "\n".join(errors[:12]) if errors else ""))
        self.load_expenses(); self.load_journal(); self.load_trial()
