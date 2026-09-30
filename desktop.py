from __future__ import annotations

import os
import tkinter as tk
import sys
import traceback
import mimetypes
import time
import json
from urllib.request import urlopen
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from client import ApiClient
from i18n import tr
from report_export import export_excel, export_invoice_pdf, export_pdf, print_rows
from desktop_final import FinalFeaturesMixin
from desktop_brains import BrainsScreensMixin
from desktop_dimensions import DimensionsMixin
from desktop_stage3 import Stage3Mixin
from desktop_inventory import InventoryMixin
from desktop_v22 import V22Mixin

NAVY, GOLD, LIGHT = "#102A43", "#B78B45", "#F4F7FA"
SALE_TREATMENTS={"Taxable 11%":"standard","Zero-rated (export)":"zero_rated","Exempt (Art. 16-17)":"exempt","Out of scope":"out_of_scope"}
PURCHASE_USES={"Mixed (partial deduction)":"mixed","Taxable sales only (100%)":"taxable","Exempt sales only (0%)":"exempt"}

def resource_path(relative_path):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    path = base / relative_path
    if not path.exists() and relative_path.startswith("assets/"):
        alternative = base / "Assets" / relative_path[len("assets/"):]
        if alternative.exists(): return alternative
    return path

def row_matches_search(values, query):
    """Return True when every search term appears somewhere in the row.

    Amounts match with or without thousands separators (1250 finds 1,250.00) and dates match
    with or without dashes (31122024 finds 31-12-2024)."""
    terms = str(query or "").casefold().split()
    if not terms:
        return True
    searchable = " ".join("" if value is None else str(value) for value in values).casefold()
    searchable = f"{searchable} {searchable.replace(',', '')} {searchable.replace('-', '').replace('/', '')}"
    return all(term in searchable or term.replace(",", "") in searchable for term in terms)

def auto_dash_date(text):
    """Turn typed digits into DD-MM-YYYY as the user types: 3112 -> 31-12, 31122024 -> 31-12-2024."""
    digits = "".join(ch for ch in str(text or "") if ch.isdigit())[:8]
    if len(digits) <= 2: return digits
    if len(digits) <= 4: return f"{digits[:2]}-{digits[2:]}"
    return f"{digits[:2]}-{digits[2:4]}-{digits[4:]}"

def sortable_date(value):
    text=str(value or "").strip()
    for pattern in ("%d-%m-%Y","%Y-%m-%d"):
        try: return datetime.strptime(text,pattern)
        except ValueError: pass
    return datetime.min

def parse_user_date(value):
    text=str(value or "").strip()
    for pattern in ("%d-%m-%Y","%d%m%Y","%Y-%m-%d","%Y%m%d"):
        try: return datetime.strptime(text,pattern)
        except ValueError: pass
    raise ValueError("Date must contain 8 digits: DDMMYYYY")

def formatted_user_date(value):
    return parse_user_date(value).strftime("%d-%m-%Y")

def safe_display_date(value):
    """Show a saved date as DD-MM-YYYY; keep the original text if it is in another format."""
    try: return formatted_user_date(value)
    except (ValueError, TypeError): return "" if value is None else str(value)

def natural_sort_value(value):
    text=str(value or "").strip()
    try: return (0,float(text.replace(",","")))
    except ValueError: return (1,text.casefold())

class SaberApp(V22Mixin, InventoryMixin, Stage3Mixin, DimensionsMixin, BrainsScreensMixin, FinalFeaturesMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Saber Accounting 2.9.23")
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1180, screen_width)}x{min(720, screen_height)}")
        self.minsize(min(760, screen_width), min(480, screen_height))
        if sys.platform == "win32":
            try: self.state("zoomed")
            except tk.TclError: pass
        self.configure(bg=LIGHT)
        self.language = tk.StringVar(value="en")
        self.client = None
        self.current_user = None
        self.last_activity = time.monotonic()
        self.import_rows = []
        self.sales_items = []
        self.manual_items = []
        self.view_currency = tk.StringVar(value="All Currencies")
        self.dashboard_base_currency=tk.StringVar(value="All Currencies")
        self.dashboard_display_currency=tk.StringVar(value="Original")
        self.import_view_currency = tk.StringVar(value="All Currencies")
        self.trial_from_date = tk.StringVar()
        self.trial_to_date = tk.StringVar()
        self.trial_account = tk.StringVar(); self.trial_account_from=tk.StringVar(); self.trial_account_to=tk.StringVar(); self.trial_scope=tk.StringVar(value="Detailed Trial Balance"); self.trial_display_currency=tk.StringVar(value="USD + LBP")
        self.trial_posting_status=tk.StringVar(value="Posted Only")
        self.invoice_account_search=tk.StringVar()
        self.invoice_sort_by=tk.StringVar(value="Date"); self.invoice_sort_order=tk.StringVar(value="Descending")
        self.invoice_branch=tk.StringVar(value="All Branches"); self.manual_branch=tk.StringVar(value="Head Office"); self.trial_branch=tk.StringVar(value="All Branches"); self.statement_branch=tk.StringVar(value="All Branches")
        self.statement_party = tk.StringVar()
        self.statement_from_date = tk.StringVar()
        self.statement_to_date = tk.StringVar()
        self.statement_currency = tk.StringVar(value="All Currencies")
        self.statement_display_currency = tk.StringVar(value="Original")
        self.statement_include_opening = tk.BooleanVar(value=True)
        self.journal_from_date = tk.StringVar()
        self.journal_to_date = tk.StringVar()
        self.journal_view_year = tk.StringVar()
        self.journal_section = tk.StringVar(value="All Sections")
        self.journal_sort_by=tk.StringVar(value="Date"); self.journal_sort_order=tk.StringVar(value="Ascending")
        self.pnl_from_date = tk.StringVar(value=f"01-01-{datetime.now().year}")
        self.pnl_to_date = tk.StringVar(value=f"31-12-{datetime.now().year}")
        self.close_year = tk.StringVar(value=str(datetime.now().year))
        self.report_from_date = tk.StringVar(value=f"01-01-{datetime.now().year}")
        self.report_to_date = tk.StringVar(value=f"31-12-{datetime.now().year}")
        self.ageing_as_of=tk.StringVar(value=datetime.now().strftime("%d-%m-%Y"))
        self.ageing_from=tk.StringVar(); self.ageing_to=tk.StringVar()
        self.ledger_account = tk.StringVar()
        self.report_account_from=tk.StringVar(); self.report_account_to=tk.StringVar()
        self.active_account_variable=None
        self._style()
        self.bind_all("<F2>",self.open_active_account_lookup)
        self.install_mouse_wheel(); self.install_field_right_click(); self.install_date_dashes()
        self.bind_all("<Control-f>",self.focus_page_search); self.bind_all("<Control-F>",self.focus_page_search)
        self.login_screen()

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=LIGHT, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 9), font=("Segoe UI", 9, "bold"), background="#E5ECF2", foreground=NAVY)
        style.map("TNotebook.Tab", background=[("selected", "white"), ("active", "#D6E4ED")], foreground=[("selected", NAVY)])
        style.configure("Treeview", rowheight=31, font=("Segoe UI", 9), background="white", fieldbackground="white", foreground=NAVY)
        style.map("Treeview", background=[("selected", "#D6E4ED")], foreground=[("selected", NAVY)])
        style.configure("Treeview.Heading", background=NAVY, foreground="white", font=("Segoe UI", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", NAVY)])
        style.configure("TCombobox", padding=4)
        style.configure("Sales.Treeview", rowheight=28, font=("Segoe UI", 9))
        # lighter, calmer look: shorter rows (more lines on screen), soft heading, clean inputs
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", background="#23405E", relief="flat", padding=(4, 5))
        style.map("Treeview.Heading", background=[("active", "#2E5277")])
        style.configure("TLabelframe", background=LIGHT); style.configure("TLabelframe.Label", background=LIGHT, foreground=NAVY, font=("Segoe UI", 9, "bold"))
        style.configure("Vertical.TScrollbar", arrowsize=12); style.configure("Horizontal.TScrollbar", arrowsize=12)
        self.option_add("*Font", ("Segoe UI", 9))
        self.option_add("*Entry.relief", "solid"); self.option_add("*Entry.borderWidth", 1)
        self.option_add("*Entry.highlightThickness", 1); self.option_add("*Entry.highlightColor", GOLD); self.option_add("*Entry.highlightBackground", "#C9D3DD")
        self.option_add("*LabelFrame.foreground", NAVY); self.option_add("*LabelFrame.font", ("Segoe UI", 9, "bold"))
        self.option_add("*Button.cursor", "hand2"); self.option_add("*Button.relief", "flat")
        # buttons light up under the mouse
        def hover(event, entering):
            widget = event.widget
            try:
                if entering:
                    widget._saber_bg = widget.cget("background"); color = widget._saber_bg.lstrip("#")
                    if len(color) == 6:
                        lighter = "#" + "".join(f"{min(255, int(color[i:i + 2], 16) + 28):02x}" for i in (0, 2, 4)); widget._saber_hover = lighter; widget.configure(background=lighter)
                elif getattr(widget, "_saber_bg", None) and str(widget.cget("background")).lower() == str(getattr(widget, "_saber_hover", "")).lower():
                    widget.configure(background=widget._saber_bg)  # only undo our own highlight
            except Exception: pass
        self.bind_class("Button", "<Enter>", lambda e: hover(e, True), add="+"); self.bind_class("Button", "<Leave>", lambda e: hover(e, False), add="+")

    # ------------------------------------------------------------ mouse wheel scrolling
    def install_mouse_wheel(self):
        """One wheel handler for the whole program: it scrolls whatever is under the mouse pointer.
        Tables, lists and text boxes scroll themselves; everywhere else the page scrolls. A drop-down
        list under the pointer no longer changes its value by accident, the page scrolls instead."""
        def steps(event):
            if getattr(event, "num", None) == 4: return -1
            if getattr(event, "num", None) == 5: return 1
            delta = getattr(event, "delta", 0) or 0
            if not delta: return 0
            return -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        def scrolls_itself(widget, horizontal):
            try:
                if widget.winfo_class() not in ("Treeview", "Text", "Listbox"): return False
                first, last = (widget.xview() if horizontal else widget.yview())
                return float(first) > 0.0 or float(last) < 1.0
            except Exception: return False
        def scroll_page(event, skip_self_scrolling=True):
            amount = steps(event)
            if not amount: return
            horizontal = bool(getattr(event, "state", 0) & 0x0001)  # Shift + wheel scrolls sideways
            try: widget = self.winfo_containing(event.x_root, event.y_root)
            except Exception: widget = None
            while widget is not None:
                if skip_self_scrolling and scrolls_itself(widget, horizontal): return  # its own binding scrolled it
                if getattr(widget, "_saber_scroll_page", False):
                    try:
                        view = widget.xview() if horizontal else widget.yview()
                        if float(view[0]) > 0.0 or float(view[1]) < 1.0:
                            (widget.xview_scroll if horizontal else widget.yview_scroll)(amount, "units")
                    except tk.TclError: pass
                    return "break"
                widget = getattr(widget, "master", None)
        self._scroll_page_under_pointer = scroll_page
        for sequence in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>", "<Shift-Button-4>", "<Shift-Button-5>"):
            self.bind_all(sequence, scroll_page, add="+")
            self.bind_class("TCombobox", sequence, lambda event: (scroll_page(event, False), "break")[1])

    def register_scroll_page(self, canvas):
        canvas._saber_scroll_page = True; return canvas

    # ------------------------------------------------------------ dates typed as digits get their dashes
    DATE_LABEL_WORDS=("date","expiry","issue","as of","birth","valid until","retro","period")
    DATE_LABEL_EXACT=("from","to","date from","date to","from date","to date","dob")

    def install_date_dashes(self):
        """Every date field (not only the ones built with date_entry) turns 31122025 into 31-12-2025 while
        typing. A field counts as a date when it was marked as one, when its label says Date / From / To /
        Expiry / Issue / Period ..., or when it already holds a DD-MM-YYYY date."""
        self.bind_class("Entry","<KeyRelease>",self._auto_dash_any_date,add="+")

    def _looks_like_date_field(self,widget):
        if getattr(widget,"_saber_date",None) is not None: return widget._saber_date
        try: current=widget.get().strip()
        except Exception: current=""
        if len(current)==10 and current[2]=="-" and current[5]=="-" and current.replace("-","").isdigit(): return True
        try:
            siblings=widget.master.winfo_children(); index=siblings.index(widget)
        except Exception: return False
        for sibling in reversed(siblings[:index]):
            if sibling.winfo_class()=="Label":
                text=str(sibling.cget("text") or "").strip().lower().rstrip(":")
                return text in self.DATE_LABEL_EXACT or any(word in text for word in self.DATE_LABEL_WORDS)
            if sibling.winfo_class() in ("Entry","TCombobox","Checkbutton","Button"): return False
        return False

    def _auto_dash_any_date(self,event):
        widget=event.widget
        if getattr(widget,"_saber_date_entry",False): return  # date_entry fields do this themselves
        if event.keysym in ("BackSpace","Delete","Left","Right","Home","End","Tab","Shift_L","Shift_R","Return","Escape"): return
        if len(event.keysym)!=1 or not event.keysym.isdigit(): return
        try: value=widget.get()
        except Exception: return
        if not value or any(ch.isalpha() for ch in value) or (len(value)>=5 and value[4]=="-"): return
        if not value.replace("-","").isdigit(): return
        if getattr(widget,"_saber_date",None) is None: widget._saber_date=self._looks_like_date_field(widget)
        if not widget._saber_date: return
        formatted=auto_dash_date(value)
        if formatted!=value:
            try: widget.delete(0,"end"); widget.insert(0,formatted); widget.icursor("end")
            except Exception: pass

    # ------------------------------------------------------------ right-click search in any field
    def install_field_right_click(self):
        """Right-click inside a field opens the search that belongs to it (F2 does the same):
        account fields list the saved accounts, customer / supplier fields the saved parties, item
        cells the saved items. Other fields get a small menu to search accounts, parties or items
        and put the choice in the field, plus Cut / Copy / Paste."""
        for widget_class in ("Entry", "TEntry", "TCombobox", "Spinbox"):
            for sequence in (("<Button-3>", "<Button-2>") if sys.platform == "darwin" else ("<Button-3>",)):
                self.bind_class(widget_class, sequence, self.field_right_click, add="+")

    def field_right_click(self, event):
        widget = event.widget
        try: widget.focus_set()
        except Exception: pass
        self.active_account_variable = getattr(widget, "_account_var", self.active_account_variable)
        # 1) a field that knows its own list (customers / suppliers, items, accounts)
        node = widget
        while node is not None:
            action = getattr(node, "_f2", None)
            if action: self.after_idle(action); return "break"
            if getattr(node, "_account_var", None) is not None:
                variable = node._account_var; self.after_idle(lambda: self.open_account_lookup(variable)); return "break"
            node = getattr(node, "master", None)
        # 2) a cell editor or field with its own F2 search (Journal Voucher account cell, ...)
        try: own_f2 = widget.bind("<F2>")
        except Exception: own_f2 = ""
        if own_f2: self.after_idle(lambda: widget.event_generate("<F2>")); return "break"
        # 3) any other field: offer the searches and the usual editing commands
        self.field_search_menu(widget, event)
        return "break"

    def field_search_menu(self, widget, event):
        try: state = str(widget.cget("state"))
        except Exception: state = "normal"
        editable = state not in ("disabled", "readonly")
        class _FieldValue:
            def __init__(self, target): self.target = target
            def get(self):
                try: return self.target.get()
                except Exception: return ""
            def set(self, value):
                try:
                    if isinstance(self.target, ttk.Combobox): self.target.set(value); self.target.event_generate("<<ComboboxSelected>>")
                    else: self.target.delete(0, "end"); self.target.insert(0, value)
                except Exception: pass
        target = _FieldValue(widget)
        menu = tk.Menu(widget, tearoff=0)
        state_for = lambda allowed: "normal" if allowed else "disabled"
        menu.add_command(label="Search accounts…  (F2)", state=state_for(editable), command=lambda: self.open_account_lookup(target))
        menu.add_command(label="Search customers / suppliers…", state=state_for(editable), command=lambda: self.party_search_into(target))
        if hasattr(self, "item_picker"):
            menu.add_command(label="Search items…", state=state_for(editable), command=lambda: self.item_picker(lambda sku: target.set(sku)))
        menu.add_separator()
        for label, virtual, allowed in (("Cut", "<<Cut>>", editable), ("Copy", "<<Copy>>", True), ("Paste", "<<Paste>>", editable)):
            menu.add_command(label=label, state=state_for(allowed), command=lambda v=virtual: widget.event_generate(v))
        def select_all():
            try: widget.select_range(0, "end"); widget.icursor("end")
            except Exception: pass
        menu.add_command(label="Select all", command=select_all)
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()

    def party_search_into(self, target):
        """Customers / suppliers search whose choice is written into any field."""
        try: parties = self.client.parties()
        except Exception as exc: return messagebox.showerror("Customers / Suppliers", str(exc))
        window = tk.Toplevel(self); window.title("Customers / Suppliers - Search"); window.geometry("700x420"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        search = tk.StringVar(); entry = tk.Entry(window, textvariable=search, width=40); entry.pack(padx=10, pady=8); entry.focus_set()
        tree = ttk.Treeview(window, columns=("name", "account", "kind", "currency"), show="headings"); tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for key, label, width in (("name", "Name", 300), ("account", "Account", 110), ("kind", "Type", 90), ("currency", "Currency", 70)): tree.heading(key, text=label); tree.column(key, width=width)
        def fill(*_args):
            tree.delete(*tree.get_children()); text = search.get().casefold()
            for party in parties:
                if not text or text in f'{party["name"]} {party.get("account_number") or ""} {party.get("tax_number") or ""}'.casefold():
                    tree.insert("", "end", iid=str(party["id"]), values=(party["name"], party.get("account_number") or "", party["kind"], party.get("currency") or ""))
        def choose(_event=None):
            if not tree.selection(): return
            party = next(p for p in parties if str(p["id"]) == tree.selection()[0]); window.destroy(); target.set(party["name"])
        search.trace_add("write", fill); tree.bind("<Double-1>", choose); tree.bind("<Return>", choose)
        entry.bind("<Return>", lambda _event: (tree.selection_set(tree.get_children()[0]), choose()) if tree.get_children() else None); fill()

    def clear(self):
        for child in self.winfo_children(): child.destroy()

    def fiscal_today(self):
        today=datetime.now()
        year=int(getattr(self,"current_fiscal_year",today.year))
        return today.strftime("%d-%m-%Y") if year==today.year else f"01-01-{year}"

    def date_entry(self,parent,variable,width=13):
        entry=tk.Entry(parent,textvariable=variable,width=width); entry._saber_date_entry=True
        def dashes(event=None):
            if event is not None and event.keysym in ("BackSpace","Delete","Left","Right","Home","End","Tab","Shift_L","Shift_R"): return
            value=variable.get()
            if not value or any(ch.isalpha() for ch in value) or (len(value)==10 and value[4]=="-"): return
            formatted=auto_dash_date(value)
            if formatted!=value: variable.set(formatted); entry.icursor("end")
        entry.bind("<KeyRelease>",dashes,add="+")
        def normalize(_event=None):
            value=variable.get().strip()
            if not value: return
            try: variable.set(formatted_user_date(value))
            except ValueError: pass
        entry.bind("<FocusOut>",normalize); entry.bind("<Return>",normalize)
        return entry

    def login_screen(self):
        self.clear()
        card = tk.Frame(self, bg="white", padx=42, pady=36)
        card.place(relx=.5, rely=.5, anchor="center")
        try:
            self.login_logo = tk.PhotoImage(file=str(resource_path("assets/Saber_for_Audit_logo.png"))).subsample(6, 6)
            tk.Label(card, image=self.login_logo, bg="white").grid(row=0, column=0, columnspan=2, pady=(0, 14))
        except Exception:
            tk.Label(card, text="SABER FOR AUDIT", font=("Segoe UI", 24, "bold"), fg=NAVY, bg="white").grid(row=0, column=0, columnspan=2)
        tk.Label(card, text="PROFESSIONAL ACCOUNTING", font=("Segoe UI", 11, "bold"), fg=GOLD, bg="white").grid(row=1, column=0, columnspan=2, pady=(0,25))
        self.server = tk.StringVar(value="http://127.0.0.1:8765")
        self.username = tk.StringVar(value="admin")
        self.password = tk.StringVar()
        fields = [("server", self.server, False), ("username", self.username, False), ("password", self.password, True)]
        for row,(key,var,secret) in enumerate(fields, 2):
            tk.Label(card, text=tr("en",key), bg="white", anchor="w").grid(row=row,column=0,sticky="w",pady=7,padx=(0,14))
            entry=tk.Entry(card,textvariable=var,width=34,show="*" if secret else "")
            entry.grid(row=row,column=1,pady=7)
            if secret:
                entry.bind("<Return>",lambda _event:self.login())
        tk.Label(card,text="Language",bg="white").grid(row=5,column=0,sticky="w",pady=7)
        ttk.Combobox(card,textvariable=self.language,values=["en","ar","fr"],state="readonly",width=31).grid(row=5,column=1,pady=7)
        tk.Button(card,text="Sign in",command=self.login,bg=NAVY,fg="white",activebackground=GOLD,width=29,pady=8,border=0).grid(row=6,column=0,columnspan=2,pady=(22,0))

    def login(self):
        try:
            self.client = ApiClient(self.server.get(), on_unauthorized=self.session_ended)
            self.current_user=self.client.login(self.username.get(), self.password.get())
            self.last_activity=time.monotonic(); self.bind_all("<Any-KeyPress>",self.record_activity); self.bind_all("<Any-Button>",self.record_activity); self.after(60000,self.check_auto_logout)
            self.company_selection_screen()
        except Exception as exc: messagebox.showerror("Saber Accounting", str(exc))

    def company_selection_screen(self):
        try: companies=self.client.companies()
        except Exception as exc: return messagebox.showerror("Companies",str(exc))
        self.available_companies=companies; self.clear()
        card=tk.Frame(self,bg="white",padx=42,pady=34); card.place(relx=.5,rely=.5,anchor="center")
        tk.Label(card,text="Select Company & Fiscal Year",bg="white",fg=NAVY,font=("Segoe UI",18,"bold")).grid(row=0,column=0,columnspan=2,pady=(0,20))
        labels={f'{c["name"]} ({"Active" if c.get("active",True) else "Inactive"})':c for c in companies}; company_var=tk.StringVar(value=next(iter(labels),"")); year_var=tk.StringVar()
        tk.Label(card,text="Company",bg="white").grid(row=1,column=0,sticky="w",pady=8); company_box=ttk.Combobox(card,textvariable=company_var,values=list(labels),state="readonly",width=34); company_box.grid(row=1,column=1,pady=8)
        tk.Label(card,text="Fiscal Year",bg="white").grid(row=2,column=0,sticky="w",pady=8); year_box=ttk.Combobox(card,textvariable=year_var,state="readonly",width=34); year_box.grid(row=2,column=1,pady=8)
        def refresh_years(*_args):
            company=labels.get(company_var.get()); years=[str(y["year"]) for y in company.get("years",[])] if company else []
            year_box["values"]=years
            selected=str(getattr(self,"current_fiscal_year","")) if company and company.get("id")==getattr(self,"current_company",{}).get("id") else ""
            year_var.set(selected if selected in years else (years[-1] if years else ""))
        company_box.bind("<<ComboboxSelected>>",refresh_years); refresh_years()
        previous=getattr(self,"current_company",None)
        if previous:
            choice=next((label for label,entry in labels.items() if entry["id"]==previous.get("id")),None)
            if choice: company_var.set(choice); refresh_years()
        def open_company():
            company=labels.get(company_var.get())
            if not company or not year_var.get(): return messagebox.showwarning("Companies","Select a company and fiscal year")
            if not company.get("active",True): return messagebox.showwarning("Companies","This company is inactive")
            old_company,old_year=self.client.company_id,self.client.fiscal_year
            try:
                year=int(year_var.get())
                self.client.select_company_year(company["id"],year)
                self.client.dashboard()  # Verify the selected year's data before replacing the current screen.
                self.current_company=company; self.current_fiscal_year=year
                self.journal_view_year.set(str(year))
                for name in ("pnl_from_date", "report_from_date", "trial_from_date", "journal_from_date"):
                    variable=getattr(self,name,None)
                    if variable is not None: variable.set(f"01-01-{year}")
                for name in ("pnl_to_date", "report_to_date", "trial_to_date", "journal_to_date"):
                    variable=getattr(self,name,None)
                    if variable is not None: variable.set(f"31-12-{year}")
                self.close_year.set(str(year))
                self.main_screen()
            except Exception as exc:
                self.client.company_id,self.client.fiscal_year=old_company,old_year
                traceback.print_exc()
                messagebox.showerror("Switch Company / Year",f"Could not open {company['name']} · {year_var.get()}: {exc}")
        tk.Button(card,text="Open Company",command=open_company,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=25,pady=8).grid(row=3,column=0,columnspan=2,pady=(18,6))
        if self.current_user.get("role")=="admin":
            self.action_button(card,"Create Company",self.create_company_dialog).grid(row=4,column=0,padx=4,pady=5)
            self.action_button(card,"Manage Selected",lambda:self.manage_company_dialog(labels.get(company_var.get()))).grid(row=4,column=1,padx=4,pady=5)

    def create_company_dialog(self):
        window=tk.Toplevel(self); window.title("Create Company"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        fields={key:tk.StringVar(value=str(datetime.now().year) if key=="year" else "") for key in ("name","year","address","phone","mof_number","email","website")}
        for row,(key,label) in enumerate((("name","Company Name"),("year","Opening Fiscal Year"),("address","Address"),("phone","Phone"),("mof_number","MOF / VAT Number"),("email","Email"),("website","Website"))):
            tk.Label(window,text=label,bg=LIGHT).grid(row=row,column=0,sticky="w",padx=14,pady=7); tk.Entry(window,textvariable=fields[key],width=38).grid(row=row,column=1,padx=14,pady=7)
        def save():
            try: self.client.create_company({key:var.get().strip() for key,var in fields.items()})
            except Exception as exc: return messagebox.showerror("Create Company",str(exc),parent=window)
            window.destroy(); self.company_selection_screen()
        self.action_button(window,"Create Company",save).grid(row=7,column=0,columnspan=2,pady=14)

    def manage_company_dialog(self,company):
        if not company: return
        window=tk.Toplevel(self); window.title("Manage Company"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        name=tk.StringVar(value=company["name"]); new_year=tk.StringVar(value=str(max(int(y["year"]) for y in company.get("years",[]))+1)); active=tk.BooleanVar(value=company.get("active",True))
        tk.Label(window,text="Company Name",bg=LIGHT).grid(row=0,column=0,padx=14,pady=8); tk.Entry(window,textvariable=name,width=32).grid(row=0,column=1,padx=14,pady=8)
        tk.Checkbutton(window,text="Active",variable=active,bg=LIGHT).grid(row=1,column=0,columnspan=2,pady=5)
        tk.Label(window,text="New Fiscal Year",bg=LIGHT).grid(row=2,column=0,padx=14,pady=8); tk.Entry(window,textvariable=new_year,width=12).grid(row=2,column=1,padx=14,pady=8,sticky="w")
        def update():
            try: self.client.update_company(company["id"],{"name":name.get(),"active":active.get()})
            except Exception as exc: return messagebox.showerror("Company",str(exc),parent=window)
            window.destroy(); self.company_selection_screen()
        def create_year():
            if not messagebox.askyesno("Fiscal Year","Create this fiscal year as a separate open year? The previous year will remain open until you close it manually.",parent=window): return
            try: self.client.create_fiscal_year(company["id"],int(new_year.get()))
            except Exception as exc: return messagebox.showerror("Fiscal Year",str(exc),parent=window)
            window.destroy(); self.company_selection_screen()
        self.action_button(window,"Save Company",update).grid(row=3,column=0,padx=6,pady=14); self.action_button(window,"Create Separate Year",create_year).grid(row=3,column=1,padx=6,pady=14)

    def main_screen(self):
        if not hasattr(self, "show_department"): self.show_department=tk.BooleanVar(value=True)
        if not hasattr(self, "show_project"): self.show_project=tk.BooleanVar(value=True)
        self._dimension_groups=[]; self._dimension_sheets=[]
        # Forget the widgets of the previous screen (switching company / year rebuilds every page).
        for name in ("purchase_form","expense_form","payment_forms","trial_state","statement_state","voucher_sheet","budget_sheet","departments_tree","pr_tree","vat_summary_tree","_dimensions","_account_cache","items_tree","sd_find_box","warehouses_tree","ir_warehouse_box","ir_item_box","ir_category_box","stock_sheet","_cash_accounts","_expense_accounts",
                     "sio_sheet","pc_sheet","pc_find_box","sio_wh_box","pc_wh_box","cat_tree","item_boxes","ir_subcategory_box","ir_unit_box","ir_supplier_box","_all_accounts"):
            self.__dict__.pop(name,None)
        # Also forget every page widget of the previous screen: they are destroyed below, and a page that is
        # built later (in the background) must not be mistaken for one that already exists.
        for name,value in list(self.__dict__.items()):
            if isinstance(value,tk.Misc) and not isinstance(value,(tk.Tk,tk.Toplevel)) and not name.startswith("_") and name not in ("tk","master"):
                self.__dict__.pop(name,None)
        self.clear(); lang=self.language.get()
        try: self.currency_codes=[row["code"] for row in self.client.currencies()]
        except Exception: self.currency_codes=["USD","LBP","EUR","AED"]
        top=tk.Frame(self,bg=NAVY,height=58); top.pack(fill="x"); top.pack_propagate(False)
        try:
            self.header_logo = tk.PhotoImage(file=str(resource_path("assets/Saber_for_Audit_logo.png"))).subsample(18, 18)
            tk.Label(top,image=self.header_logo,bg=NAVY).pack(side="left",padx=(18,8),pady=2)
        except Exception:
            pass
        tk.Label(top,text=tr(lang,"title"),bg=NAVY,fg="white",font=("Segoe UI",16,"bold")).pack(side="left",padx=8,pady=12)
        tk.Label(top,text="11% VAT  |  " + " · ".join(self.currency_codes[:5]),bg=NAVY,fg=GOLD,font=("Segoe UI",10,"bold")).pack(side="right",padx=28)
        tk.Button(top,text="Switch Company / Year",command=self.company_selection_screen,bg=GOLD,fg=NAVY,border=0,padx=10,pady=5).pack(side="right",padx=5)
        self.alerts_button=tk.Button(top,text="Document Alerts",command=self.show_document_alerts,bg=NAVY,fg="white",border=1,padx=10,pady=5)
        self.alerts_button.pack(side="right",padx=5)
        tk.Label(top,text=f'{getattr(self,"current_company",{}).get("name","")} · {getattr(self,"current_fiscal_year","")}',bg=NAVY,fg="white",font=("Segoe UI",9,"bold")).pack(side="right",padx=8)
        self.status_bar()
        nav_outer=tk.Frame(self,bg=LIGHT); nav_outer.pack(fill="x",padx=8,pady=(4,0))
        nav_canvas=tk.Canvas(nav_outer,bg=LIGHT,highlightthickness=0,height=56)
        nav_canvas.pack(side="top",fill="x",expand=True)
        nav_scroll=ttk.Scrollbar(nav_outer,orient="horizontal",command=nav_canvas.xview)
        nav_scroll.pack(side="bottom",fill="x")
        nav_canvas.configure(xscrollcommand=nav_scroll.set)
        tab_nav=tk.Frame(nav_canvas,bg=LIGHT)
        nav_window=nav_canvas.create_window((0,0),window=tab_nav,anchor="nw")
        nav_buttons=[]; navigation_columns=None
        def size_navigation(_event=None):
            nonlocal navigation_columns
            columns=min(8,max(2,nav_canvas.winfo_width()//155))
            if nav_buttons and columns!=navigation_columns:
                navigation_columns=columns
                for button in nav_buttons: button.grid_forget()
                for column in range(8): tab_nav.grid_columnconfigure(column,weight=0,uniform="")
                for row in range(8): tab_nav.grid_rowconfigure(row,weight=0,uniform="")
                for column in range(columns): tab_nav.grid_columnconfigure(column,weight=1,uniform="main_tabs")
                for row in range((len(nav_buttons)+columns-1)//columns):
                    tab_nav.grid_rowconfigure(row,weight=1,uniform="main_tab_rows")
                for index,button in enumerate(nav_buttons):
                    button.grid(row=index//columns,column=index%columns,sticky="nsew",padx=4,pady=3)
            nav_canvas.itemconfigure(nav_window,width=max(nav_canvas.winfo_width(),tab_nav.winfo_reqwidth()))
            nav_canvas.configure(height=max(56,tab_nav.winfo_reqheight()+2),scrollregion=nav_canvas.bbox("all"))
            if tab_nav.winfo_reqwidth()>nav_canvas.winfo_width()+1:
                if not nav_scroll.winfo_manager(): nav_scroll.pack(side="bottom",fill="x")
            elif nav_scroll.winfo_manager(): nav_scroll.pack_forget()
        tab_nav.bind("<Configure>",size_navigation)
        nav_canvas.bind("<Configure>",size_navigation)
        ttk.Style(self).layout("Tabless.TNotebook.Tab",[])
        notebook=ttk.Notebook(self,style="Tabless.TNotebook"); self.main_notebook=notebook
        filter_bar=tk.Frame(self,bg=LIGHT); filter_bar.pack(fill="x",padx=28)
        notebook.pack(fill="both",expand=True,padx=18,pady=(6,16))
        pages=[("dashboard_tab",tr(lang,"dashboard")),("invoices_tab",tr(lang,"invoices")),("sales_tab","Sales Invoice"),("manual_tab",tr(lang,"manual_entry")),
            ("import_tab",tr(lang,"import")),("parties_tab",tr(lang,"customers_suppliers")),("transactions_tab",tr(lang,"payments_expenses")),("purchases_tab","Purchases & Expenses"),("inventory_tab","Inventory")]
        if self.can_use("payroll"): pages.append(("payroll_tab","Payroll"))
        if self.can_use("vat"): pages.append(("vat_tab","Quarterly VAT"))
        pages+=[("journal_tab",tr(lang,"general_journal")),("account_reports_tab","Accounts & Statements"),("pnl_tab",tr(lang,"profit_loss")),("reports_tab",tr(lang,"financial_reports")),
            ("settings_tab",tr(lang,"security_backup_rates"))]
        self.main_tab_pages=[]
        for attribute,name in pages:
            container=tk.Frame(notebook,bg=LIGHT)
            container.grid_rowconfigure(0,weight=1)
            container.grid_columnconfigure(0,weight=1)
            canvas=tk.Canvas(container,bg=LIGHT,highlightthickness=0); canvas._saber_scroll_page=True  # scrolled by the mouse wheel
            vertical=ttk.Scrollbar(container,orient="vertical",command=canvas.yview)
            horizontal=ttk.Scrollbar(container,orient="horizontal",command=canvas.xview)
            canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
            canvas.grid(row=0,column=0,sticky="nsew")
            vertical.grid(row=0,column=1,sticky="ns")
            horizontal.grid(row=1,column=0,sticky="ew")
            frame=tk.Frame(canvas,bg=LIGHT)
            item=canvas.create_window((0,0),window=frame,anchor="nw")
            def resize_page(_event=None, *, page=frame, view=canvas, window=item, vbar=vertical, hbar=horizontal):
                if page.winfo_reqheight()>view.winfo_height()+1: vbar.grid()
                else: vbar.grid_remove()
                if page.winfo_reqwidth()>view.winfo_width()+1: hbar.grid()
                else: hbar.grid_remove()
                view.itemconfigure(window,width=max(view.winfo_width(),page.winfo_reqwidth()),
                                   height=max(view.winfo_height(),page.winfo_reqheight()))
                view.configure(scrollregion=view.bbox("all"))
            frame.bind("<Configure>",resize_page)
            canvas.bind("<Configure>",resize_page)
            setattr(self,attribute,frame); notebook.add(container,text=name); self.main_tab_pages.append(container)
        account_notebook=ttk.Notebook(self.account_reports_tab); account_notebook.pack(fill="both",expand=True,padx=8,pady=8)
        for attribute,name in (("trial_tab",tr(lang,"trial_balance")),("statement_tab",tr(lang,"statement_account")),("accounts_tab",tr(lang,"chart_accounts"))):
            frame=tk.Frame(account_notebook,bg=LIGHT); setattr(self,attribute,frame); account_notebook.add(frame,text=name)
        self.tab_names=[notebook.tab(tab,"text") for tab in notebook.tabs()]
        self.tab_choice=tk.StringVar(value=self.tab_names[0])
        self.tab_buttons=nav_buttons
        for index,(page,name) in enumerate(zip(self.main_tab_pages,self.tab_names)):
            button=tk.Button(tab_nav,text=name,command=lambda p=page:self.select_main_tab(p),bg=NAVY,fg="white",
                activebackground=GOLD,activeforeground=NAVY,border=0,font=("Segoe UI",8,"bold"),pady=1,wraplength=120,cursor="hand2")
            nav_buttons.append(button)
        self.after_idle(size_navigation)
        notebook.bind("<<NotebookTabChanged>>",lambda _event:self.highlight_main_tab())
        self.highlight_main_tab()
        tk.Label(filter_bar,text="Show currency:",bg=LIGHT,font=("Segoe UI",10,"bold")).pack(side="left")
        currency_filter=ttk.Combobox(filter_bar,textvariable=self.view_currency,values=["All Currencies"]+self.currency_codes,state="readonly",width=16)
        currency_filter.pack(side="left",padx=8); currency_filter.bind("<<ComboboxSelected>>",lambda _event:self.currency_changed())
        builders=[self.build_dashboard,self.build_invoices,self.build_sales_invoice,self.build_manual,self.build_import,self.build_parties,self.build_transactions,self.build_purchases_expenses,self.build_inventory]
        if self.can_use("payroll"): builders.append(self.build_payroll)
        if self.can_use("vat"): builders.append(self.build_vat_return)
        builders+=[self.build_journal,self.build_trial,self.build_profit_loss,self.build_financial_reports,self.build_statement,self.build_accounts,self.build_settings]
        # Faster opening: the Dashboard is built at once and shown; the other pages are built one by one
        # in the background right after (a page the user opens first, or any page element another
        # screen needs, is built immediately - see __getattr__ / build_pending_pages).
        self._page_generation=getattr(self,"_page_generation",0)+1
        self._pending_builders=list(builders[1:])
        self._run_page_builder(builders[0])
        self.update_idletasks()
        generation=self._page_generation
        self.after(30,lambda:self._build_next_page(generation))
        self.after(700,lambda:self.show_document_alerts(startup=True))

    def _run_page_builder(self,build):
        self.__dict__["_building_depth"]=self.__dict__.get("_building_depth",0)+1
        try: build()
        except Exception as exc:
            traceback.print_exc(); messagebox.showerror("Saber Accounting",f"A page could not be loaded ({build.__name__.replace('build_','').replace('_',' ')}): {exc}\n\nThe other pages are still available.")
        finally: self.__dict__["_building_depth"]-=1

    def _build_next_page(self,generation):
        if generation!=getattr(self,"_page_generation",None): return  # the company / year was switched meanwhile
        pending=self.__dict__.get("_pending_builders")
        if pending:
            self._run_page_builder(pending.pop(0))
        if pending: self.after(1,lambda:self._build_next_page(generation))
        elif self.__dict__.get("_pages_finished_for")!=generation: self._pages_finished_for=generation; self._finish_pages()

    def build_pending_pages(self):
        """Build every page that is still waiting (called when a page or one of its widgets is needed now)."""
        pending=self.__dict__.get("_pending_builders")
        while pending:
            self._run_page_builder(pending.pop(0))
        if self.__dict__.get("_pages_finished_for")!=self.__dict__.get("_page_generation"):
            self._pages_finished_for=self.__dict__.get("_page_generation"); self._finish_pages()

    def _finish_pages(self):
        self.setup_context_f2()

    def __getattr__(self,name):
        # Only reached when normal lookup fails: a widget of a page that is not built yet.
        pending=self.__dict__.get("_pending_builders")
        # While a page is being built, a missing attribute means exactly what it meant before (not built yet).
        if pending and not name.startswith("__") and not self.__dict__.get("_building_depth",0):
            self.build_pending_pages()
            try: return object.__getattribute__(self,name)
            except AttributeError: pass
        return super().__getattr__(name)

    def record_activity(self,_event=None): self.last_activity=time.monotonic()

    def journal_document(self,mode):
        rows=getattr(self,"journal_rows",[])
        if not rows: return messagebox.showwarning("General Journal","Nothing to print: apply the filters or the Find first")
        headers=["Entry No.","Date","Description","Account","Account Name","Customer / Supplier","Currency","Debit","Credit"]
        body=[[r.get("entry_number"),r.get("entry_date"),r.get("description") or "",r.get("account_code"),r.get("account_name") or "",r.get("party_name") or "",r.get("currency"),
               float(r.get("debit") or 0),float(r.get("credit") or 0)] for r in rows]
        body.append(["TOTAL","","","","","","",round(sum(float(r.get("debit") or 0) for r in rows),2),round(sum(float(r.get("credit") or 0) for r in rows),2)])
        meta=[f"From {self.journal_from_date.get() or '-'} to {self.journal_to_date.get() or '-'}"]+([f"Voucher: {self.journal_find.get()}"] if self.journal_find.get().strip() else [])+([f"Details: {self.journal_find_details.get()}"] if self.journal_find_details.get().strip() else [])
        self.output_sections("General Journal",meta,[{"heading":f"{len(rows)} line(s)","headers":headers,"rows":body,"total_rows":[len(body)-1]}],"General_Journal",
                             {"preview":"preview","pdf":"pdf","print":"print"}[mode])

    def focus_page_search(self,_event=None):
        """Ctrl+F: put the cursor in the first visible Search box of the current page."""
        try: page=self.nametowidget(self.main_notebook.select())
        except Exception: return "break"
        stack=[page]
        while stack:
            widget=stack.pop(0)
            if getattr(widget,"_is_search_entry",False) and widget.winfo_ismapped():
                widget.focus_set(); widget.select_range(0,"end"); return "break"
            stack.extend(widget.winfo_children())
        return "break"

    def check_auto_logout(self):
        if self.client and time.monotonic()-self.last_activity>=1800:
            self.client=None; self.current_user=None; self.login_screen(); messagebox.showinfo("Saber Accounting","Signed out automatically after 30 minutes of inactivity"); return
        self.after(60000,self.check_auto_logout)

    def move_main_tab(self,direction):
        try: current_page=self.main_notebook.select(); current=self.main_tab_pages.index(self.nametowidget(current_page))
        except (ValueError,KeyError): current=self.visible_tab_start
        target=(current+direction)%len(self.main_tab_pages)
        start=self.visible_tab_start
        if target<start: start=target
        elif target>=start+6: start=target-5
        if direction>0 and current==len(self.main_tab_pages)-1: start=0
        elif direction<0 and current==0: start=max(0,len(self.main_tab_pages)-6)
        self.show_tab_window(start,target)

    def select_main_tab(self,page):
        if self.__dict__.get("_pending_builders"): self.build_pending_pages()
        self.main_notebook.select(page); self.highlight_main_tab()

    def highlight_main_tab(self):
        selected=self.main_notebook.select()
        for page,button in zip(getattr(self,"main_tab_pages",[]),getattr(self,"tab_buttons",[])):
            button.config(bg=GOLD if str(page)==selected else NAVY,fg=NAVY if str(page)==selected else "white")

    def show_tab_window(self,start,selected_index=None):
        maximum=max(0,len(self.main_tab_pages)-6); self.visible_tab_start=max(0,min(start,maximum))
        for page in self.main_tab_pages:
            try: self.main_notebook.forget(page)
            except tk.TclError: pass
        end=min(len(self.main_tab_pages),self.visible_tab_start+6)
        for index in range(self.visible_tab_start,end):
            self.main_notebook.add(self.main_tab_pages[index],text=self.tab_names[index],padding=(8,4))
        target=selected_index if selected_index is not None and self.visible_tab_start<=selected_index<end else self.visible_tab_start
        self.main_notebook.select(self.main_tab_pages[target]); self.tab_choice.set(self.tab_names[target])

    def select_named_tab(self):
        try:
            index=self.tab_names.index(self.tab_choice.get()); self.show_tab_window(max(0,min(index,len(self.main_tab_pages)-6)),index)
        except ValueError: pass

    def currency_changed(self):
        self.load_dashboard(); self.load_invoices(); self.load_journal(); self.load_trial(); self.load_profit_loss(); self.load_financial_reports(); self.load_ageing_report()

    def table(self,parent,columns):
        search_bar=tk.Frame(parent,bg=LIGHT); search_bar.pack(fill="x",padx=10,pady=(10,0))
        search_var=tk.StringVar()
        tk.Label(search_bar,text="Search:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        search_entry=tk.Entry(search_bar,textvariable=search_var,width=36); search_entry._is_search_entry=True
        search_entry.pack(side="left",padx=8)
        tk.Label(search_bar,text="Ctrl+F  |  searches every column; amounts and dates work with or without , and -",bg=LIGHT,fg="#5f6b76",font=("Segoe UI",8)).pack(side="right")
        tk.Button(search_bar,text="Clear",command=lambda:search_var.set(""),bg=NAVY,fg="white",
                  border=0,padx=12,pady=3).pack(side="left")

        frame=tk.Frame(parent,bg=LIGHT); frame.pack(fill="both",expand=True,padx=10,pady=10)
        tree=ttk.Treeview(frame,columns=[c[0] for c in columns],show="headings")
        for key,label,width in columns: tree.heading(key,text=label); tree.column(key,width=width,anchor="w")
        scroll=ttk.Scrollbar(frame,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y")

        real_insert,real_delete=tree.insert,tree.delete
        tree._search_rows=[]
        tree._search_counter=0
        def tracked_insert(parent_id,index,*args,**kwargs):
            tree._search_counter+=1
            saved_kwargs=dict(kwargs)
            saved_kwargs.setdefault("iid",f"search-{id(tree)}-{tree._search_counter}")
            record=(parent_id,index,args,saved_kwargs)
            tree._search_rows.append(record)
            if row_matches_search(saved_kwargs.get("values",()),search_var.get()):
                real_insert(parent_id,index,*args,**saved_kwargs)
            return saved_kwargs["iid"]
        def tracked_delete(*item_ids):
            visible=set(tree.get_children(""))
            requested=set(item_ids)
            if requested==visible:
                tree._search_rows.clear()
            else:
                tree._search_rows=[
                    record for record in tree._search_rows
                    if str(record[3].get("iid")) not in requested
                ]
            if item_ids:
                real_delete(*item_ids)
        def apply_search(*_args):
            visible=tree.get_children("")
            if visible:
                real_delete(*visible)
            for parent_id,index,args,saved_kwargs in tree._search_rows:
                if row_matches_search(saved_kwargs.get("values",()),search_var.get()):
                    real_insert(parent_id,index,*args,**saved_kwargs)
        # Debounce: re-filtering rebuilds the whole Treeview, so on a big table
        # doing it on every keystroke feels laggy. Wait a beat after typing
        # stops, then filter once. The result is identical, just smoother.
        tree._search_after=None
        def schedule_search(*_args):
            pending=getattr(tree,"_search_after",None)
            if pending is not None:
                try: tree.after_cancel(pending)
                except Exception: pass
            tree._search_after=tree.after(180,apply_search)
        tree.insert=tracked_insert
        tree.delete=tracked_delete
        tree.search_var=search_var
        tree._sort_reverse={}
        def sort_column(key):
            reverse=tree._sort_reverse.get(key,False)
            def sortable(value):
                clean=str(value).replace(",","").strip()
                try: return (0,float(clean))
                except ValueError: return (1,clean.casefold())
            ordered=sorted(tree.get_children(""),key=lambda item:sortable(tree.set(item,key)),reverse=reverse)
            for position,item in enumerate(ordered): tree.move(item,"",position)
            tree._sort_reverse[key]=not reverse
        for key,label,_width in columns: tree.heading(key,text=label,command=lambda column=key:sort_column(column))
        search_var.trace_add("write",schedule_search)
        search_entry.bind("<Escape>",lambda _event:search_var.set(""))
        context_menu=tk.Menu(tree,tearoff=0)
        def focus_search():
            search_entry.focus_set(); search_entry.select_range(0,"end")
        context_menu.add_command(label="Search…",command=focus_search)
        context_menu.add_command(label="Clear search",command=lambda:search_var.set(""))
        def show_context_menu(event):
            try: context_menu.tk_popup(event.x_root,event.y_root)
            finally: context_menu.grab_release()
        tree.bind("<Button-3>",show_context_menu)  # right-click on Windows/Linux
        tree.bind("<Button-2>",show_context_menu)  # right-click on macOS trackpads
        return tree

    def build_dashboard(self):
        actions=tk.Frame(self.dashboard_tab,bg=LIGHT); actions.pack(fill="x",padx=12,pady=(8,6))
        tk.Label(actions,text="Company overview",bg=LIGHT,fg=NAVY,font=("Segoe UI",12,"bold")).pack(side="left",padx=(0,16))
        self.action_button(actions,tr(self.language.get(),"refresh"),self.load_dashboard).pack(side="left",padx=4)
        tk.Label(actions,text="Base currency",bg=LIGHT).pack(side="left",padx=(10,3))
        ttk.Combobox(actions,textvariable=self.dashboard_base_currency,values=["All Currencies","USD","LBP","EUR","AED"],state="readonly",width=13).pack(side="left")
        tk.Label(actions,text="Convert to",bg=LIGHT).pack(side="left",padx=(10,3))
        ttk.Combobox(actions,textvariable=self.dashboard_display_currency,values=["Original","USD","LBP","EUR","AED"],state="readonly",width=9).pack(side="left")
        self.action_button(actions,"Apply",self.load_dashboard).pack(side="left",padx=4)
        self.action_button(actions,"Export Excel",lambda:self.export_report("dashboard","xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.export_report("dashboard","pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.export_report("dashboard","print")).pack(side="left",padx=4)
        self.dashboard_cards=tk.Frame(self.dashboard_tab,bg=LIGHT); self.dashboard_cards.pack(fill="x",padx=12)
        self.dashboard_chart=tk.Canvas(self.dashboard_tab,height=105,bg="white",highlightthickness=0)
        self.dashboard_chart.pack(fill="x",padx=12,pady=(8,4))
        self.build_dashboard_charts(self.dashboard_tab)
        self.load_dashboard()

    def load_dashboard(self):
        try: data=self.client.professional_dashboard(); rows=data["metrics"]
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        selected=self.dashboard_base_currency.get()
        rows=[r for r in rows if selected=="All Currencies" or r["currency"]==selected]
        target=self.dashboard_display_currency.get(); display_rows=[]
        date=datetime.now().strftime("%d-%m-%Y")
        for row in rows:
            item=dict(row)
            if target!="Original" and target!=row["currency"]:
                try: rate=float(self.client.dashboard_conversion(row["currency"],target,date)["rate"])
                except Exception as exc: return messagebox.showerror("Dashboard Exchange Rate",str(exc))
                for key in ("sales","purchases","expenses","profit","receivables","payables"): item[key]=float(item[key])*rate
                item["currency"]=f'{row["currency"]} → {target} (1 = {rate:,.4f}; {date})'
            display_rows.append(item)
        rows=display_rows
        self.dashboard_rows=rows
        for child in self.dashboard_cards.winfo_children(): child.destroy()
        if not rows:
            tk.Label(self.dashboard_cards,text="No activity for this currency yet.",bg=LIGHT,fg="#506274",font=("Segoe UI",10)).pack(anchor="w",padx=10,pady=12)
        labels=(("sales","Sales"),("purchases","Purchases"),("expenses","Expenses"),("profit","Net profit"),
                ("receivables","Receivables"),("payables","Payables"),("overdue","Overdue invoices"))
        for index,r in enumerate(rows):
            card=tk.LabelFrame(self.dashboard_cards,text=r["currency"],bg="white",fg=NAVY,font=("Segoe UI",10,"bold"),padx=10,pady=6)
            card.grid(row=index//2,column=index%2,sticky="ew",padx=4,pady=3)
            for col,(key,title) in enumerate(labels):
                line=tk.Frame(card,bg="white"); line.grid(row=col//4,column=col%4,sticky="ew",padx=5,pady=3)
                tk.Label(line,text=title,bg="white",fg="#506274",font=("Segoe UI",8)).pack(anchor="w")
                value=str(r[key]) if key=="overdue" else f'{r[key]:,.2f}'
                tk.Label(line,text=value,bg="white",fg=NAVY,font=("Segoe UI",10,"bold"),anchor="w").pack(anchor="w")
            for col in range(4): card.grid_columnconfigure(col,weight=1)
        for col in range(2): self.dashboard_cards.grid_columnconfigure(col,weight=1)
        chart_rows=[]; chart_rates={}
        for source_row in data.get("monthly",[]):
            if selected!="All Currencies" and source_row["currency"]!=selected: continue
            row=dict(source_row)
            if target!="Original" and target!=row["currency"]:
                if row["currency"] not in chart_rates:
                    chart_rates[row["currency"]]=float(self.client.dashboard_conversion(row["currency"],target,date)["rate"])
                row["amount"]=float(row["amount"])*chart_rates[row["currency"]]
            chart_rows.append(row)
        self.draw_dashboard_chart(chart_rows)
        self.load_dashboard_charts()

    def draw_dashboard_chart(self,rows):
        canvas=self.dashboard_chart; canvas.delete("all"); canvas.update_idletasks(); width=max(canvas.winfo_width(),700); height=100
        values=[float(row["amount"] or 0) for row in rows[-12:]]; maximum=max([1,*values])
        canvas.create_text(10,10,anchor="nw",text="Monthly Sales / Purchases",fill=NAVY,font=("Segoe UI",10,"bold"))
        for index,row in enumerate(rows[-12:]):
            x=20+index*max(48,(width-40)//max(1,min(12,len(rows))))
            bar_height=(float(row["amount"] or 0)/maximum)*56
            color="#1F6E8C" if row["kind"]=="sale" else GOLD
            canvas.create_rectangle(x,height-25-bar_height,x+24,height-25,fill=color,outline="")
            canvas.create_text(x+12,height-12,text=str(row["month"])[5:],font=("Segoe UI",7))

    def build_invoices(self):
        l=self.language.get(); self.invoice_tree=self.table(self.invoices_tab,[("no",tr(l,"invoice_no"),90),("status","Status",85),("date",tr(l,"date"),90),("party",tr(l,"party"),150),("branch","Branch",120),("kind","Type",90),("currency",tr(l,"currency"),60),("deductible","Deductible",95),("non_deductible","Non-Deductible",105),("total",tr(l,"total"),90),("payment_method","Payment Method",110),("paid","Paid Amount",100),("lbp","LBP Eq.",105),("usd","USD Eq.",90),("debit","D",80),("credit","C",80),("vat_status","VAT Deductible",95)])
        invoice_actions=tk.Frame(self.invoices_tab,bg=LIGHT); invoice_actions.pack(fill="x",anchor="w",pady=(0,10))
        tk.Label(invoice_actions,text="Branch:",bg=LIGHT).pack(side="left"); self.branch_selector(invoice_actions,self.invoice_branch,15,True).pack(side="left",padx=4)
        tk.Label(invoice_actions,text="Sort By:",bg=LIGHT).pack(side="left",padx=(8,2))
        ttk.Combobox(invoice_actions,textvariable=self.invoice_sort_by,state="readonly",width=16,
            values=["Date","Invoice Number","Customer / Supplier","Account","Amount","Currency"]).pack(side="left",padx=2)
        ttk.Combobox(invoice_actions,textvariable=self.invoice_sort_order,state="readonly",width=10,
            values=["Ascending","Descending"]).pack(side="left",padx=2)
        tk.Button(invoice_actions,text=tr(l,"refresh"),command=self.load_invoices,bg=NAVY,fg="white",border=0,padx=20,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Save Data",command=self.confirm_invoice_data_saved,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Export Excel",command=self.export_invoices_excel,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Add Invoice Row",command=self.add_invoice_row,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Add Item",command=self.add_item_to_selected_invoice,bg=NAVY,fg="white",border=0,padx=18,pady=7).pack(side="left",padx=4)
        tk.Button(invoice_actions,text="Edit Selected",command=self.edit_selected_invoice,bg=GOLD,fg=NAVY,
                  font=("Segoe UI",9,"bold"),border=0,padx=20,pady=7).pack(side="left",padx=4)
        lifecycle=tk.Frame(self.invoices_tab,bg=LIGHT); lifecycle.pack(fill="x",anchor="w",pady=(0,8))
        self.action_button(lifecycle,"Duplicate",self.duplicate_selected_invoice).pack(side="left",padx=4)
        tk.Button(lifecycle,text="Cancel Invoice",command=self.cancel_selected_invoice,bg="#8B1E1E",fg="white",border=0,padx=15,pady=7).pack(side="left",padx=4)
        tk.Button(lifecycle,text="Delete Selected",command=self.delete_selected_invoice,bg="#6B1010",fg="white",border=0,padx=15,pady=7).pack(side="left",padx=4)
        self.action_button(lifecycle,"Attach PDF / Image",self.attach_to_selected_invoice).pack(side="left",padx=4)
        self.action_button(lifecycle,"Attachments",self.show_selected_attachments).pack(side="left",padx=4)
        self.action_button(lifecycle,"History",self.show_invoice_history).pack(side="left",padx=4)
        self.action_button(lifecycle,"Branded Invoice PDF",self.export_selected_invoice_pdf).pack(side="left",padx=4)
        self.action_button(lifecycle,"VAT Deductible / Non-Deductible",self.toggle_selected_invoice_vat).pack(side="left",padx=4)
        self.action_button(lifecycle,"VAT Treatment",self.vat_classification_dialog).pack(side="left",padx=4)
        self.invoice_tree.bind("<Double-1>",lambda _event:self.edit_selected_invoice())
        self.load_invoices()

    def load_invoices(self):
        try: rows=self.client.invoices(); rates=self.client.exchange_rates()
        except Exception as exc: return messagebox.showerror("Error",str(exc))
        account=self.invoice_account_search.get().split(" - ",1)[0].strip()
        if account: rows=[row for row in rows if account in (str(row.get("supplier_account") or ""),str(row.get("vat_account") or ""),str(row.get("expense_account") or ""),str(row.get("expense_no_vat_account") or ""))]
        selected=self.view_currency.get()
        rows=[r for r in rows if selected=="All Currencies" or r["currency"]==selected]
        if self.invoice_branch.get()!="All Branches": rows=[r for r in rows if r.get("branch_name")==self.invoice_branch.get()]
        sort_name=self.invoice_sort_by.get()
        def invoice_key(row):
            if sort_name=="Date": return sortable_date(row.get("invoice_date"))
            if sort_name=="Invoice Number": return natural_sort_value(row.get("invoice_number"))
            if sort_name=="Customer / Supplier": return str(row.get("party_name") or "").casefold()
            if sort_name=="Account": return natural_sort_value(row.get("supplier_account"))
            if sort_name=="Amount": return float(row.get("total") or 0)
            return str(row.get("currency") or "").casefold()
        rows.sort(key=invoice_key,reverse=self.invoice_sort_order.get()=="Descending")
        self.invoice_rows={str(r["id"]):r for r in rows}
        self.invoice_tree.delete(*self.invoice_tree.get_children())
        for r in rows:
            lbp,usd=self.exchange_equivalents(float(r["total"] or 0),r["currency"],rates)
            self.invoice_tree.insert("","end",iid=str(r["id"]),values=(r["invoice_number"],"DELETED" if r.get("status")=="deleted" else str(r.get("status") or "").title(),r["invoice_date"],r["party_name"],r.get("branch_name") or "Head Office",r.get("entry_type") or r["kind"],r["currency"],r.get("deductible_subtotal",r["subtotal"]),r.get("non_deductible_subtotal",0),r["total"],r.get("payment_method") or "",r.get("amount_paid") or 0,"" if lbp is None else f"{lbp:,.2f}","" if usd is None else f"{usd:,.2f}",r["debit"],r["credit"],("Yes" if r.get("vat_recoverable",1) else "NO") if r.get("kind")=="purchase" and float(r.get("vat") or 0) else ""),tags=("deleted",) if r.get("status")=="deleted" else ())
        self.invoice_tree.tag_configure("deleted",foreground="#8B1E1E")

    def vat_classification_dialog(self):
        selected=self.invoice_tree.selection()
        if not selected: return messagebox.showwarning("VAT Treatment","Select an invoice first")
        row=self.invoice_rows.get(selected[0])
        if not row: return
        sale=row["kind"]=="sale"
        window=tk.Toplevel(self); window.title(f"VAT Treatment - {row['invoice_number']}"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        treatment=tk.StringVar(); use=tk.StringVar(); reverse=tk.BooleanVar(value=row.get("vat_treatment")=="reverse_charge")
        if sale:
            treatment.set(next((k for k,v in SALE_TREATMENTS.items() if v==(row.get("vat_treatment") or "standard")),"Taxable 11%"))
            tk.Label(window,text="Sale type (Law 379/2001)",bg=LIGHT,font=("Segoe UI",9,"bold")).grid(row=0,column=0,padx=12,pady=10,sticky="w")
            ttk.Combobox(window,textvariable=treatment,values=list(SALE_TREATMENTS),state="readonly",width=24).grid(row=0,column=1,padx=12,pady=10)
            tk.Label(window,text="Zero-rated: exports and like transactions (Art. 19-21), deductible input VAT.\nExempt: Art. 16-17 activities and goods, reduces the deduction ratio.",bg=LIGHT,fg="#5f6b76",justify="left").grid(row=1,column=0,columnspan=2,padx=12,sticky="w")
        else:
            use.set(next((k for k,v in PURCHASE_USES.items() if v==(row.get("vat_use") or "mixed")),"Mixed (partial deduction)"))
            tk.Label(window,text="Input VAT used for",bg=LIGHT,font=("Segoe UI",9,"bold")).grid(row=0,column=0,padx=12,pady=10,sticky="w")
            ttk.Combobox(window,textvariable=use,values=list(PURCHASE_USES),state="readonly",width=26).grid(row=0,column=1,padx=12,pady=10)
            tk.Checkbutton(window,text="Service from abroad - reverse charge (Art. 40)",variable=reverse,bg=LIGHT).grid(row=1,column=0,columnspan=2,padx=12,sticky="w")
        def save():
            try: self.client.set_vat_classification("invoice",row["id"],SALE_TREATMENTS[treatment.get()] if sale else ("reverse_charge" if reverse.get() else "standard"),None if sale else PURCHASE_USES[use.get()])
            except Exception as exc: return messagebox.showerror("VAT Treatment",str(exc),parent=window)
            window.destroy(); self.load_invoices()
        self.action_button(window,"Save",save).grid(row=2,column=0,columnspan=2,pady=12)

    def edit_selected_invoice(self):
        selected=self.invoice_tree.selection()
        if not selected:
            return messagebox.showwarning("Invoices","Select one invoice row to edit")
        invoice_id=selected[0]
        row=self.invoice_rows.get(invoice_id)
        if not row:
            return messagebox.showerror("Invoices","The selected invoice could not be found")
        window=tk.Toplevel(self); window.title(f'Edit Invoice {row["invoice_number"]}')
        window.configure(bg=LIGHT); window.transient(self); window.grab_set(); window.resizable(False,False)
        variables={
            "invoice_number":tk.StringVar(value=row["invoice_number"]),
            "invoice_date":tk.StringVar(value=row["invoice_date"]),
            "party_name":tk.StringVar(value=row["party_name"]),
            "kind":tk.StringVar(value=row.get("entry_type") or ("sales" if row["kind"]=="sale" else "purchases")),
            "currency":tk.StringVar(value=row["currency"]),
            "deductible_subtotal":tk.StringVar(value=row.get("deductible_subtotal") or row["subtotal"]),
            "non_deductible_subtotal":tk.StringVar(value=row.get("non_deductible_subtotal") or "0"),
            "vat":tk.StringVar(value=row["vat"]),
            "total":tk.StringVar(value=row["total"]),
            "supplier_account":tk.StringVar(value=row["supplier_account"]),
            "vat_account":tk.StringVar(value=row["vat_account"]),
            "expense_account":tk.StringVar(value=row["expense_account"]),
            "expense_no_vat_account":tk.StringVar(value=row.get("expense_no_vat_account") or "601100001"),
            "supplier_side":tk.StringVar(value="C - Credit" if (row.get("supplier_side") or "C")=="C" else "D - Debit"),
            "vat_side":tk.StringVar(value="C - Credit" if (row.get("vat_side") or "D")=="C" else "D - Debit"),
            "expense_side":tk.StringVar(value="C - Credit" if (row.get("expense_side") or "D")=="C" else "D - Debit"),
            "expense_no_vat_side":tk.StringVar(value="C - Credit" if (row.get("expense_no_vat_side") or "D")=="C" else "D - Debit"),
            "status":tk.StringVar(value=row["status"]),
            "due_date":tk.StringVar(value=row.get("due_date") or ""),
            "amount_paid":tk.StringVar(value=row.get("amount_paid") or "0"),
            "payment_method":tk.StringVar(value=row.get("payment_method") or "Cash"),
            "description":tk.StringVar(value=row.get("description") or ""),
            "branch":tk.StringVar(value=row.get("branch_name") or "Head Office"),
        }
        fields=[
            ("Invoice Number","invoice_number"),("Date (DD-MM-YYYY)","invoice_date"),("Description","description"),("Branch","branch"),
            ("Customer / Supplier","party_name"),("Type","kind"),("Currency","currency"),
            ("Before VAT Deductible","deductible_subtotal"),("Before VAT Non-Deductible","non_deductible_subtotal"),("VAT","vat"),("Total","total"),
            ("Supplier Account","supplier_account"),("VAT Account","vat_account"),
            ("Expense Account","expense_account"),("Expense Account without VAT","expense_no_vat_account"),("Status","status"),
            ("Payment Method","payment_method"),("Amount Paid","amount_paid"),("Due Date (DD-MM-YYYY)","due_date"),
        ]
        for index,(label,key) in enumerate(fields):
            grid_row=index//2; grid_column=(index%2)*2
            tk.Label(window,text=label,bg=LIGHT,anchor="w").grid(row=grid_row,column=grid_column,sticky="w",padx=(14,5),pady=8)
            if key=="kind":
                widget=ttk.Combobox(window,textvariable=variables[key],values=["assets","expenses","purchases","sales"],state="readonly",width=24)
            elif key=="currency":
                widget=ttk.Combobox(window,textvariable=variables[key],values=self.currency_codes,state="readonly",width=24)
            elif key=="status":
                widget=ttk.Combobox(window,textvariable=variables[key],values=["posted","review"],state="readonly",width=24)
            elif key=="payment_method":
                widget=ttk.Combobox(window,textvariable=variables[key],values=["Cash","Bank Transfer","Cheque","Card","Other"],state="readonly",width=24)
            elif key=="branch":
                widget=self.branch_selector(window,variables[key],24,False)
            elif key in ("supplier_account","vat_account","expense_account","expense_no_vat_account"):
                frame=tk.Frame(window,bg=LIGHT); side_key={"supplier_account":"supplier_side","vat_account":"vat_side","expense_account":"expense_side","expense_no_vat_account":"expense_no_vat_side"}[key]
                self.account_search_box(frame,variables[key],18).pack(side="left")
                ttk.Combobox(frame,textvariable=variables[side_key],values=["D - Debit","C - Credit"],state="readonly",width=10).pack(side="left",padx=(5,0))
                widget=frame
            elif key in ("invoice_date","due_date"):
                widget=self.date_entry(window,variables[key],27)
            else:
                widget=tk.Entry(window,textvariable=variables[key],width=27)
            widget.grid(row=grid_row,column=grid_column+1,padx=(5,14),pady=8)

        def save_update():
            values={key:variable.get().strip() for key,variable in variables.items()}
            if not all(values[key] for key in ("invoice_number","invoice_date","party_name")):
                return messagebox.showwarning("Invoices","Invoice number, date, and customer/supplier are required",parent=window)
            try:
                values["invoice_date"]=formatted_user_date(values["invoice_date"])
                if values.get("due_date"): values["due_date"]=formatted_user_date(values["due_date"])
            except ValueError: return messagebox.showwarning("Invoices","Enter 8 date digits: DDMMYYYY",parent=window)
            try:
                deductible=float(values["deductible_subtotal"]); non_deductible=float(values["non_deductible_subtotal"]); subtotal=deductible+non_deductible; vat=float(values["vat"]); total=float(values["total"])
                amount_paid=float(values["amount_paid"] or 0)
            except ValueError:
                return messagebox.showwarning("Invoices","Deductible, Non-Deductible, VAT, and Total must be valid numbers",parent=window)
            if abs((subtotal+vat)-total)>0.005:
                return messagebox.showwarning("Invoices","Total must equal Before VAT plus VAT",parent=window)
            if amount_paid<0 or amount_paid>total:
                return messagebox.showwarning("Invoices","Amount paid must be between zero and Total",parent=window)
            try:
                self.client.update_invoice(int(invoice_id),values)
            except Exception as exc:
                return messagebox.showerror("Invoices",str(exc),parent=window)
            window.destroy()
            self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial()
            messagebox.showinfo("Invoices","Invoice updated successfully")

        exchange_label=tk.Label(window,text=self.exchange_equivalent_text(float(row["total"] or 0),row["currency"]),bg=LIGHT,fg=NAVY,font=("Segoe UI",9,"bold"))
        exchange_label.grid(row=(len(fields)+1)//2,column=0,columnspan=4,pady=(6,0))
        buttons=tk.Frame(window,bg=LIGHT); buttons.grid(row=(len(fields)+1)//2+1,column=0,columnspan=4,pady=16)
        tk.Button(buttons,text="Save Update",command=save_update,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),
                  border=0,padx=24,pady=8).pack(side="left",padx=5)
        tk.Button(buttons,text="Cancel",command=window.destroy,bg=NAVY,fg="white",border=0,padx=20,pady=8).pack(side="left",padx=5)

    def selected_invoice_id(self):
        selected=self.invoice_tree.selection()
        if not selected:
            messagebox.showwarning("Invoices","Select one invoice row first"); return None
        return int(selected[0])

    def delete_selected_invoice(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        if not messagebox.askyesno("Delete Invoice","Mark this invoice DELETED? Its number and details stay visible; its journal entry is removed."): return
        try: self.client.delete_invoice(invoice_id)
        except Exception as exc: return messagebox.showerror("Delete Uploaded Data",str(exc))
        self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial(); messagebox.showinfo("Invoices","Invoice marked DELETED")

    def duplicate_selected_invoice(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        try: created=self.client.duplicate_invoice(invoice_id)
        except Exception as exc: return messagebox.showerror("Invoices",str(exc))
        self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial()
        messagebox.showinfo("Invoices",f'Invoice duplicated as {created["invoice_number"]}')

    def cancel_selected_invoice(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        row=self.invoice_rows.get(str(invoice_id),{})
        if row.get("status")=="cancelled": return messagebox.showwarning("Invoices","Invoice is already cancelled")
        window=tk.Toplevel(self); window.title("Cancel Invoice"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        reason=tk.StringVar()
        tk.Label(window,text="Cancellation reason:",bg=LIGHT).grid(row=0,column=0,padx=14,pady=14)
        tk.Entry(window,textvariable=reason,width=45).grid(row=0,column=1,padx=14,pady=14)
        def confirm():
            if not reason.get().strip(): return messagebox.showwarning("Cancel Invoice","Enter a cancellation reason",parent=window)
            try: self.client.cancel_invoice(invoice_id,reason.get().strip())
            except Exception as exc: return messagebox.showerror("Cancel Invoice",str(exc),parent=window)
            window.destroy(); self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial()
            messagebox.showinfo("Cancel Invoice","Invoice cancelled and reversing journal entry created")
        tk.Button(window,text="Confirm Cancellation",command=confirm,bg="#8B1E1E",fg="white",border=0,padx=18,pady=7).grid(row=1,column=0,columnspan=2,pady=12)

    def attach_to_selected_invoice(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        path=filedialog.askopenfilename(filetypes=[("Invoice files","*.pdf *.png *.jpg *.jpeg"),("All files","*.*")])
        if not path: return
        try:
            content=Path(path).read_bytes()
            mime=mimetypes.guess_type(path)[0] or "application/octet-stream"
            self.client.upload_attachment(invoice_id,Path(path).name,mime,content)
        except Exception as exc: return messagebox.showerror("Attachments",str(exc))
        self.load_invoices(); messagebox.showinfo("Attachments","File attached successfully")

    def show_selected_attachments(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        try: items=self.client.attachments(invoice_id)
        except Exception as exc: return messagebox.showerror("Attachments",str(exc))
        if not items: return messagebox.showinfo("Attachments","This invoice has no attachments")
        window=tk.Toplevel(self); window.title("Invoice Attachments"); window.geometry("620x340")
        tree=ttk.Treeview(window,columns=("name","type","size","date"),show="headings")
        for key,label,width in (("name","File Name",240),("type","Type",140),("size","Size",80),("date","Uploaded",140)):
            tree.heading(key,text=label); tree.column(key,width=width)
        for item in items: tree.insert("","end",iid=str(item["id"]),values=(item["file_name"],item["mime_type"],f'{item["size"]/1024:,.1f} KB',item["uploaded_at"][:19]))
        tree.pack(fill="both",expand=True,padx=10,pady=10)
        def download():
            selected=tree.selection()
            if not selected: return messagebox.showwarning("Attachments","Select one file",parent=window)
            record=next(item for item in items if str(item["id"])==selected[0])
            path=filedialog.asksaveasfilename(initialfile=record["file_name"],parent=window)
            if not path: return
            try: Path(path).write_bytes(self.client.download_attachment(record["id"])["content"])
            except Exception as exc: return messagebox.showerror("Attachments",str(exc),parent=window)
            messagebox.showinfo("Attachments",f"Saved successfully:\n{path}",parent=window)
        self.action_button(window,"Download Selected",download).pack(pady=(0,10))

    def show_invoice_history(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        try: items=self.client.invoice_history(invoice_id)
        except Exception as exc: return messagebox.showerror("History",str(exc))
        window=tk.Toplevel(self); window.title("Invoice Modification History"); window.geometry("760x380")
        tree=ttk.Treeview(window,columns=("date","user","action","details"),show="headings")
        for key,label,width in (("date","Date",170),("user","User",100),("action","Action",100),("details","Details",370)):
            tree.heading(key,text=label); tree.column(key,width=width)
        for item in items: tree.insert("","end",values=(item["created_at"][:19],item.get("username") or "",item["action"],item.get("details") or ""))
        tree.pack(fill="both",expand=True,padx=10,pady=10)

    def export_selected_invoice_pdf(self):
        invoice_id=self.selected_invoice_id()
        if invoice_id is None: return
        try: detail=self.client.invoice_detail(invoice_id)
        except Exception as exc: return messagebox.showerror("Invoice PDF",str(exc))
        invoice=detail["invoice"]; path=filedialog.asksaveasfilename(defaultextension=".pdf",initialfile=f'Invoice_{invoice["invoice_number"]}.pdf',filetypes=[("PDF document","*.pdf")])
        if not path: return
        try:
            company=self.client.settings(); custom_logo=company.get("company_logo")
            logo=Path(custom_logo) if custom_logo and Path(custom_logo).exists() else resource_path("assets/Saber_for_Audit_logo.png")
            export_invoice_pdf(path,invoice,detail["items"],logo,company)
        except Exception as exc: return messagebox.showerror("Invoice PDF",str(exc))
        messagebox.showinfo("Invoice PDF",f"Saved successfully:\n{path}")

    def confirm_invoice_data_saved(self):
        try:
            rows=self.client.invoices()
        except Exception as exc:
            return messagebox.showerror("Invoices",str(exc))
        self.load_invoices()
        messagebox.showinfo("Invoices",f"{len(rows)} invoice rows are saved in the shared database")

    def export_invoices_excel(self):
        rows=list(getattr(self,"invoice_rows",{}).values())
        if not rows: return messagebox.showwarning("Invoices","No invoice data to export")
        headers=["Invoice Number","Date","Customer / Supplier","Type","Currency","Before VAT Deductible","Before VAT Non-Deductible","VAT","Total","Payment Method","Paid Amount","Debit","Credit",
                 "Supplier Account","VAT Account","Expense Account","Expense without VAT","Status","Source Row"]
        values=[[r["invoice_number"],r["invoice_date"],r["party_name"],r.get("entry_type") or r["kind"],r["currency"],r.get("deductible_subtotal",r["subtotal"]),r.get("non_deductible_subtotal",0),
                 r["vat"],r["total"],r.get("payment_method") or "",r.get("amount_paid") or 0,r["debit"],r["credit"],r["supplier_account"],r["vat_account"],r["expense_account"],r.get("expense_no_vat_account","601100001"),r["status"],r["source_row"]] for r in rows]
        path=filedialog.asksaveasfilename(defaultextension=".xlsx",filetypes=[("Excel workbook","*.xlsx")],
                                          initialfile="Saber_Accounting_Invoices.xlsx")
        if not path: return
        try:
            export_excel(path,"Saber Accounting - Invoices",headers,values)
            messagebox.showinfo("Invoices",f"Saved successfully:\n{path}")
        except Exception as exc:
            messagebox.showerror("Invoices",str(exc))

    def add_invoice_row(self):
        window=tk.Toplevel(self); window.title("Add Invoice Row"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        defaults={"invoice_number":"","invoice_date":datetime.now().strftime("%d-%m-%Y"),"party_name":"",
                  "kind":"purchases","currency":"USD","deductible_subtotal":"0","non_deductible_subtotal":"0","vat":"0","total":"0",
                  "supplier_account":"4011","vat_account":"442660000","expense_account":"601100000",
                  "expense_no_vat_account":"601100001",
                  "description":"","branch":"Head Office","due_date":"","payment_method":"Cash","amount_paid":"0"}
        variables={key:tk.StringVar(value=value) for key,value in defaults.items()}
        fields=[("Invoice Number","invoice_number"),("Date (DD-MM-YYYY)","invoice_date"),("Customer / Supplier","party_name"),
                ("Description","description"),("Branch","branch"),("Type","kind"),("Currency","currency"),("Before VAT Deductible","deductible_subtotal"),("Before VAT Non-Deductible","non_deductible_subtotal"),("VAT","vat"),("Total","total"),
                ("Supplier Account (C - Credit)","supplier_account"),("VAT Account (D - Debit)","vat_account"),("Expense Account (D - Debit)","expense_account"),("Expense without VAT","expense_no_vat_account"),
                ("Due Date (DD-MM-YYYY)","due_date"),("Payment Method","payment_method"),("Paid Amount","amount_paid")]
        for index,(label,key) in enumerate(fields):
            rr=index//2; cc=(index%2)*2
            tk.Label(window,text=label,bg=LIGHT).grid(row=rr,column=cc,sticky="w",padx=(14,5),pady=7)
            if key=="kind": widget=ttk.Combobox(window,textvariable=variables[key],values=["assets","expenses","purchases","sales"],state="readonly",width=24)
            elif key=="currency": widget=ttk.Combobox(window,textvariable=variables[key],values=self.currency_codes,state="readonly",width=24)
            elif key=="payment_method": widget=ttk.Combobox(window,textvariable=variables[key],values=["Cash","Bank Transfer","Cheque","Card","Other"],state="readonly",width=24)
            elif key=="branch": widget=self.branch_selector(window,variables[key],24,False)
            elif key in ("supplier_account","vat_account","expense_account","expense_no_vat_account"): widget=self.account_search_box(window,variables[key],24)
            elif key in ("invoice_date","due_date"): widget=self.date_entry(window,variables[key],27)
            else: widget=tk.Entry(window,textvariable=variables[key],width=27)
            widget.grid(row=rr,column=cc+1,padx=(5,14),pady=7)
        def save():
            values={key:var.get().strip() for key,var in variables.items()}
            try:
                values["invoice_date"]=formatted_user_date(values["invoice_date"])
                if values.get("due_date"): values["due_date"]=formatted_user_date(values["due_date"])
                deductible=float(values["deductible_subtotal"]); non_deductible=float(values["non_deductible_subtotal"]); subtotal=deductible+non_deductible; vat=float(values["vat"]); total=float(values["total"])
            except ValueError:
                return messagebox.showwarning("Invoices","Check the date and amounts",parent=window)
            if not values["party_name"] or abs(subtotal+vat-total)>0.005:
                return messagebox.showwarning("Invoices","Enter customer/supplier; Total must equal Before VAT plus VAT",parent=window)
            item={"description":"Manual invoice row","quantity":1,"unit_price":deductible,"deductible_subtotal":deductible,"non_deductible_subtotal":non_deductible,
                  "vat_rate":0 if deductible==0 else vat*100/deductible,"vat":vat,"total":total}
            try: self.client.create_manual_invoice(values,[item])
            except Exception as exc: return messagebox.showerror("Invoices",str(exc),parent=window)
            window.destroy(); self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial(); self.load_statement_parties()
            messagebox.showinfo("Invoices","Invoice row added successfully")
        tk.Button(window,text="Save Invoice",command=save,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=24,pady=8).grid(row=9,column=0,columnspan=4,pady=16)

    def add_item_to_selected_invoice(self):
        selected=self.invoice_tree.selection()
        if not selected: return messagebox.showwarning("Invoices","Select one invoice row")
        invoice_id=int(selected[0]); window=tk.Toplevel(self); window.title("Add Item to Invoice"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        defaults={"description":"","quantity":"1","unit_price":"0","subtotal":"0","vat_rate":"11","vat":"0"}
        variables={key:tk.StringVar(value=value) for key,value in defaults.items()}
        fields=[("Description","description"),("Quantity","quantity"),("Unit Price","unit_price"),
                ("Before VAT","subtotal"),("VAT %","vat_rate"),("VAT Amount","vat")]
        for index,(label,key) in enumerate(fields):
            tk.Label(window,text=label,bg=LIGHT).grid(row=index,column=0,sticky="w",padx=14,pady=6)
            tk.Entry(window,textvariable=variables[key],width=30).grid(row=index,column=1,padx=14,pady=6)
        def save():
            item={key:var.get().strip() for key,var in variables.items()}
            try:
                if not item["description"]: raise ValueError
                for key in ("quantity","unit_price","subtotal","vat_rate","vat"): float(item[key])
            except ValueError:
                return messagebox.showwarning("Invoices","Enter a description and valid amounts",parent=window)
            try: self.client.add_invoice_item(invoice_id,item)
            except Exception as exc: return messagebox.showerror("Invoices",str(exc),parent=window)
            window.destroy(); self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial()
            messagebox.showinfo("Invoices","Item added and invoice totals updated")
        tk.Button(window,text="Add Item",command=save,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=24,pady=8).grid(row=6,column=0,columnspan=2,pady=14)

    def build_sales_invoice(self):
        self.sales_items=[]; self.sales_edit_id=None
        header=tk.LabelFrame(self.sales_tab,text="Sales Invoice",bg=LIGHT,padx=6,pady=2)
        header.pack(fill="x",padx=10,pady=(2,1))
        self.sales_no=tk.StringVar(); self.sales_date=tk.StringVar(value=self.fiscal_today())
        self.sales_party=tk.StringVar(); self.sales_kind=tk.StringVar(value="sales"); self.sales_currency=tk.StringVar(value="USD")
        self.sales_supplier_account=tk.StringVar(value="")
        self.sales_vat_account=tk.StringVar(value="4427")
        self.sales_expense_account=tk.StringVar(value="713000001")
        self.sales_expense_no_vat_account=tk.StringVar(value="601100001")
        self.sales_supplier_side=tk.StringVar(value="D - Debit"); self.sales_vat_side=tk.StringVar(value="C - Credit"); self.sales_expense_side=tk.StringVar(value="C - Credit"); self.sales_expense_no_vat_side=tk.StringVar(value="C - Credit")
        self.sales_due_date=tk.StringVar(); self.sales_payment_method=tk.StringVar(value="On Account (Not Cash)"); self.sales_amount_paid=tk.StringVar(value="0"); self.sales_branch=tk.StringVar(value="Head Office")
        self.sales_open_choice=tk.StringVar(); self.sales_doc_type=tk.StringVar(value="Invoice"); self.sales_category=tk.StringVar(value="Services")
        tabs_row=tk.Frame(header,bg=LIGHT); tabs_row.pack(fill="x")
        nav=tk.LabelFrame(tabs_row,text="Find Invoice",bg=LIGHT,padx=4,pady=1); nav.pack(side="right",padx=(6,0))
        self.sales_open_box=ttk.Combobox(nav,textvariable=self.sales_open_choice,width=17); self.sales_open_box.pack(side="left",padx=(0,4))
        self.sales_open_box.bind("<<ComboboxSelected>>",lambda _event:self.open_sales_invoice()); self.sales_open_box.bind("<KeyRelease>",self.search_open_sales)
        self.sales_open_box.bind("<Return>",lambda _event:self.open_sales_by_number())
        self.sales_previous=tk.Button(nav,text="◀",command=lambda:self.navigate_sales_invoice(-1),bg=NAVY,fg="white",border=0,padx=7,pady=3)
        self.sales_previous.pack(side="left",padx=2)
        self.sales_next=tk.Button(nav,text="▶",command=lambda:self.navigate_sales_invoice(1),bg=NAVY,fg="white",border=0,padx=7,pady=3)
        self.sales_next.pack(side="left",padx=2)
        details=ttk.Notebook(tabs_row); details.pack(side="left",fill="x",expand=True)
        invoice_details=tk.Frame(details,bg=LIGHT); account_details=tk.Frame(details,bg=LIGHT)
        details.add(invoice_details,text="Invoice details"); details.add(account_details,text="Posting accounts")
        top=tk.Frame(invoice_details,bg=LIGHT); top.pack(anchor="w",fill="x",pady=(1,0))
        doc_box=ttk.Combobox(top,textvariable=self.sales_doc_type,values=["Invoice","Credit Note"],state="readonly",width=11)
        doc_box.pack(side="left",padx=(0,8)); doc_box.bind("<<ComboboxSelected>>",lambda _event:self.sales_doc_type_changed())
        tk.Label(top,text="Invoice No.",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left",padx=(0,4))
        tk.Entry(top,textvariable=self.sales_no,width=18,font=("Segoe UI",10,"bold"),state="readonly",readonlybackground="white").pack(side="left",padx=(0,12))
        tk.Label(top,text="Customer",bg=LIGHT).pack(side="left")
        self.sales_party_box=ttk.Combobox(top,textvariable=self.sales_party,width=23); self.sales_party_box.pack(side="left",padx=(4,10))
        self.sales_party_box.bind("<KeyRelease>",self.search_sales_customers); self.sales_party_box.bind("<<ComboboxSelected>>",lambda _event:self.sales_customer_chosen())
        self.sales_party_box.bind("<Return>",lambda _event:self.select_searched_sales_customer())
        tk.Label(top,text="Client Account",bg=LIGHT).pack(side="left",padx=(0,4))
        tk.Entry(top,textvariable=self.sales_supplier_account,width=12).pack(side="left",padx=(0,10))
        tk.Label(top,text="Currency",bg=LIGHT).pack(side="left")
        ttk.Combobox(top,textvariable=self.sales_currency,values=self.currency_codes,state="readonly",width=6).pack(side="left",padx=(4,8))
        account_fields=[("Client Account",self.sales_supplier_account,self.sales_supplier_side),("VAT Account",self.sales_vat_account,self.sales_vat_side),("Revenue Account",self.sales_expense_account,self.sales_expense_side)]
        accounts_grid=tk.Frame(account_details,bg=LIGHT); accounts_grid.pack(anchor="w",fill="x",pady=1)
        for col,(label,var,side) in enumerate(account_fields):
            cell=tk.Frame(accounts_grid,bg=LIGHT,bd=1,relief="groove"); cell.grid(row=0,column=col,padx=4,pady=2,sticky="nw")
            caption=tk.Label(cell,text=label,bg=LIGHT,anchor="w",font=("Segoe UI",9,"bold")); caption.pack(anchor="w",padx=(6,4),pady=(2,0))
            if label=="Revenue Account": self.sales_revenue_caption=caption
            self.account_search_box(cell,var,26).pack(anchor="w",padx=6,pady=1)
            side_box=ttk.Combobox(cell,textvariable=side,values=["D - Debit","C - Credit"],state="readonly",width=11); side_box.pack(anchor="w",padx=6,pady=(0,3))
            side_box.bind("<<ComboboxSelected>>",lambda _event:self.update_sales_totals())
        payment=tk.Frame(invoice_details,bg=LIGHT); payment.pack(anchor="w",fill="x",pady=(1,0))
        tk.Label(payment,text="Date",bg=LIGHT).pack(side="left"); self.date_entry(payment,self.sales_date,12).pack(side="left",padx=(4,10))
        tk.Label(payment,text="Sales Type",bg=LIGHT).pack(side="left")
        self.sales_category_box=ttk.Combobox(payment,textvariable=self.sales_category,values=["Goods","Products","Services"],state="readonly",width=9)
        self.sales_category_box.pack(side="left",padx=(4,10)); self.sales_category_box.bind("<<ComboboxSelected>>",lambda _event:self.sales_category_changed())
        self.sales_category_box.bind("<space>",lambda _event:self.cycle_sales_type())
        self.sales_category_box.bind("<Key-space>",lambda _event:self.cycle_sales_type())
        tk.Label(payment,text="Payment Mode",bg=LIGHT).pack(side="left")
        ttk.Combobox(payment,textvariable=self.sales_payment_method,values=["On Account (Not Cash)","Cash","Bank Transfer","Cheque","Card","Other"],state="readonly",width=16).pack(side="left",padx=(4,10))
        tk.Label(payment,text="Due Date",bg=LIGHT).pack(side="left"); self.date_entry(payment,self.sales_due_date,12).pack(side="left",padx=(4,10))
        dims=tk.Frame(invoice_details,bg=LIGHT); dims.pack(anchor="w",fill="x",pady=(1,0))
        self.sales_department=tk.StringVar(); self.sales_project=tk.StringVar(); self.dimension_selectors(dims,self.sales_department,self.sales_project)
        vat_row=tk.Frame(invoice_details,bg=LIGHT); vat_row.pack(anchor="w",fill="x",pady=(1,0))
        tk.Label(vat_row,text="Branch",bg=LIGHT).pack(side="left"); self.branch_selector(vat_row,self.sales_branch,14,False).pack(side="left",padx=(4,10))
        tk.Label(vat_row,text="Amount Paid",bg=LIGHT).pack(side="left"); tk.Entry(vat_row,textvariable=self.sales_amount_paid,width=10).pack(side="left",padx=(4,10))
        self.sales_treatment=tk.StringVar(value="Taxable 11%")
        tk.Label(vat_row,text="VAT Treatment",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left",padx=(6,4))
        treatment_box=ttk.Combobox(vat_row,textvariable=self.sales_treatment,values=list(SALE_TREATMENTS),state="readonly",width=19); treatment_box.pack(side="left")
        treatment_box.bind("<<ComboboxSelected>>",lambda _event:self.sales_treatment_changed())
        self.sales_mode_label=tk.Label(vat_row,text="NEW INVOICE",bg=GOLD,fg=NAVY,font=("Segoe UI",8,"bold"),padx=8)
        self.sales_mode_label.pack(side="left",padx=(12,0))
        self.sales_payment_method.trace_add("write",lambda *_args:self.sales_payment_changed())
        self.sales_supplier_account.trace_add("write",lambda *_args:self.sales_account_chosen())
        self.sales_currency.trace_add("write",lambda *_args:self.update_sales_totals())
        self.sales_date.trace_add("write",lambda *_args:self.sales_date_changed())

        self.sales_discount_percent=tk.StringVar(value="0"); self.sales_discount_amount=tk.StringVar(value="0")
        toolbar=tk.Frame(self.sales_tab,bg=LIGHT); toolbar.pack(fill="x",padx=10,pady=(2,0))
        self.action_button(toolbar,"New",self.new_sales_invoice).pack(side="left",padx=2)
        self.action_button(toolbar,"Add Line",self.add_sales_item).pack(side="left",padx=2)
        tk.Button(toolbar,text="Delete Line",command=self.remove_sales_item,bg="#8B1E1E",fg="white",border=0,padx=10,pady=4).pack(side="left",padx=2)
        tk.Button(toolbar,text="Save",command=lambda:self.save_sales_invoice(True),bg=NAVY,fg="white",font=("Segoe UI",10,"bold"),border=0,padx=14,pady=4).pack(side="left",padx=(8,2))
        tk.Button(toolbar,text="Delete",command=self.delete_sales_invoice,bg="#8B1E1E",fg="white",border=0,padx=12,pady=4).pack(side="left",padx=2)
        self.action_button(toolbar,"Duplicate",self.duplicate_sales_invoice).pack(side="left",padx=(8,2))
        for text,command in (("Print Preview",lambda:self.sales_invoice_pdf("preview")),("PDF",lambda:self.sales_invoice_pdf("pdf")),("Print",lambda:self.sales_invoice_pdf("print")),
                             ("Excel",lambda:self.sales_entry_report("xlsx"))):
            tk.Button(toolbar,text=text,command=command,bg=NAVY,fg="white",border=0,padx=10,pady=4).pack(side="left",padx=2)
        for text,command in (("Import Excel",self.import_sales_excel),("Import PDF",self.import_sales_pdf)):
            tk.Button(toolbar,text=text,command=command,bg=GOLD,fg=NAVY,border=0,padx=10,pady=4).pack(side="left",padx=(8 if text=="Import Excel" else 2,2))
        self.action_button(toolbar,"AI Read PDF",self.ai_read_sales_pdf).pack(side="left",padx=2)
        # Totals bar is pinned to the very bottom of the tab FIRST, so it can never be pushed off-screen by the table
        bottom=tk.Frame(self.sales_tab,bg=LIGHT); bottom.pack(side="bottom",fill="x",padx=10,pady=(0,4))
        body=tk.Frame(self.sales_tab,bg=LIGHT); body.pack(side="top",fill="both",expand=True,padx=10,pady=(2,4))
        # Item table on top, enlarged
        items_area=tk.Frame(body,bg=LIGHT); items_area.pack(side="top",fill="both",expand=True)
        sheet_frame=tk.Frame(items_area,bg=LIGHT); sheet_frame.pack(fill="both",expand=True)
        self.sales_columns=[("item_code","Item",90),("description","Description",250),("quantity","Qty",55),("unit","Unit",60),("unit_price","Unit Price",95),
            ("gross_amount","Total Amount",105),("discount_percent","Discount %",80),("vat_rate","VAT %",60),("total","Net",105)]
        self.sales_sheet=ttk.Treeview(sheet_frame,columns=[c[0] for c in self.sales_columns],show="headings",height=9,style="Sales.Treeview")
        for key,label,width in self.sales_columns: self.sales_sheet.heading(key,text=label); self.sales_sheet.column(key,width=width,anchor="w" if key=="description" else "e")
        scroll=ttk.Scrollbar(sheet_frame,orient="vertical",command=self.sales_sheet.yview)
        xscroll=ttk.Scrollbar(sheet_frame,orient="horizontal",command=self.sales_sheet.xview)
        self.sales_sheet.configure(yscrollcommand=scroll.set,xscrollcommand=xscroll.set)
        self.sales_sheet.grid(row=0,column=0,sticky="nsew"); scroll.grid(row=0,column=1,sticky="ns")
        xscroll.grid(row=1,column=0,sticky="ew")
        sheet_frame.grid_rowconfigure(0,weight=1); sheet_frame.grid_columnconfigure(0,weight=1)
        self.sales_sheet.bind("<Double-1>",self.edit_sales_cell); self.sales_sheet.bind("<Return>",self.edit_sales_cell)
        self.sales_sheet.bind("<Delete>",lambda _event:self.remove_sales_item())
        totals=tk.Frame(bottom,bg=LIGHT); totals.pack(side="right",fill="y",padx=(8,0))
        box=tk.Frame(totals,bg="#dfe6ee",padx=6,pady=3); box.pack(side="top",fill="x")
        self.sales_total_labels={}
        for key,caption,row,column in (("Total","Total",0,0),("Discount","Discount",0,1),("Total HT","Total HT",0,2),
                                       ("VAT","VAT 11%",1,0),("TOTAL","TOTAL TTC",1,1)):
            label=tk.Label(box,text=caption,bg="#dfe6ee",font=("Segoe UI",9,"bold" if key=="TOTAL" else "normal"))
            label.grid(row=row,column=column*2,sticky="e",padx=(6,2),pady=1)
            if key=="VAT": self.sales_vat_caption=label
            value=tk.Label(box,text="0.00",bg="#dfe6ee",width=10,anchor="e",font=("Segoe UI",12 if key=="TOTAL" else 10,"bold"))
            value.grid(row=row,column=column*2+1,sticky="e",padx=(0,4)); self.sales_total_labels[key]=value
        discount=tk.Frame(box,bg="#dfe6ee"); discount.grid(row=1,column=4,columnspan=2,sticky="e",pady=1)
        tk.Label(discount,text="Discount %",bg="#dfe6ee").pack(side="left"); e1=tk.Entry(discount,textvariable=self.sales_discount_percent,width=5); e1.pack(side="left",padx=2)
        tk.Label(discount,text="or amount",bg="#dfe6ee").pack(side="left"); e2=tk.Entry(discount,textvariable=self.sales_discount_amount,width=9); e2.pack(side="left",padx=2)
        for entry in (e1,e2): entry.bind("<KeyRelease>",lambda _event:self.update_sales_totals())
        self.sales_totals=tk.Label(totals,text="",bg=LIGHT,fg=NAVY); self.sales_totals.pack(side="top",anchor="e",padx=8,pady=3)
        self.sales_words=tk.Label(bottom,text="",bg=LIGHT,fg="#5f6b76",anchor="w",justify="left",wraplength=380,font=("Segoe UI",8))
        self.sales_words.pack(side="left",fill="x",expand=True,padx=4,pady=(3,0))
        self.new_sales_invoice(confirm=False)

    # ---- sales invoice helpers
    def sales_treatment_changed(self):
        """Zero-rated and exempt sales carry no VAT: set every line to 0% (Taxable puts them back to 11%)."""
        rate=11 if self.sales_treatment.get()=="Taxable 11%" else 0
        for item in self.sales_items:
            item["vat_rate"]=rate; item["_vat_typed"]=False; self.recalculate_sales_item(item)
            if self.sales_sheet.exists(item.get("_iid","")): self.sales_sheet.item(item["_iid"],values=self.sales_row_values(item))
        self.update_sales_totals()

    def sales_payment_changed(self):
        if self.sales_payment_method.get().startswith("On Account"): self.sales_amount_paid.set("0")

    def sales_date_changed(self):
        self.update_sales_totals()
        if not self.sales_edit_id and len(self.sales_date.get())==10: self.refresh_sales_number()

    def refresh_sales_number(self):
        kind={"Credit Note":"credit_note","Debit Note":"debit_note"}.get(self.sales_doc_type.get() if hasattr(self,"sales_doc_type") else "Invoice","sale")
        try: self.sales_no.set(self.client.next_invoice_number(kind,self.sales_date.get().strip() or None))
        except Exception: self.sales_no.set("")

    def load_sales_customer_list(self):
        try: parties=self.client.parties()
        except Exception: parties=[]
        self.sales_customers={f'{p["name"]}':p for p in parties if p["kind"] in ("customer","both")}
        self.sales_party_box["values"]=list(self.sales_customers)
        try: invoices=[r for r in self.client.invoices() if r["kind"]=="sale" and r.get("status")!="cancelled"]
        except Exception: invoices=[]
        invoices.sort(key=lambda r:(sortable_date(r["invoice_date"]),str(r["invoice_number"]),r["id"]))
        self.sales_open_map={}
        for row in invoices:
            number=str(row["invoice_number"])
            label=number; duplicate=2
            while label in self.sales_open_map:
                label=f"{number} ({duplicate})"; duplicate+=1
            self.sales_open_map[label]=row
        self.sales_open_all=invoices
        self.sales_open_box["values"]=list(self.sales_open_map)
        self.update_sales_navigation()

    def update_sales_navigation(self):
        keys=list(getattr(self,"sales_open_map",{}))
        current=next((i for i,key in enumerate(keys) if self.sales_edit_id and self.sales_open_map[key]["id"]==self.sales_edit_id),None)
        if hasattr(self,"sales_previous"):
            self.sales_previous.config(state="normal" if keys and (current is None or current>0) else "disabled")
            self.sales_next.config(state="normal" if keys and (current is None or current<len(keys)-1) else "disabled")

    def navigate_sales_invoice(self,step):
        keys=list(getattr(self,"sales_open_map",{}))
        current=next((i for i,key in enumerate(keys) if self.sales_edit_id and self.sales_open_map[key]["id"]==self.sales_edit_id),None)
        index=(len(keys)-1 if step<0 else 0) if current is None else current+step
        if not 0<=index<len(keys): return
        previous=self.sales_open_choice.get()
        self.sales_open_choice.set(keys[index])
        if not self.open_sales_invoice(): self.sales_open_choice.set(previous)

    def search_sales_customers(self,_event=None):
        typed=self.sales_party.get().strip().casefold(); names=list(getattr(self,"sales_customers",{}))
        found=[name for name in names if name.casefold().startswith(typed)]
        found += [name for name in names if typed in name.casefold() and name not in found]
        self.sales_party_box["values"]=found if typed else names
        if typed and found:
            if len(found)==1 and found[0].casefold()==typed:
                self.sales_party.set(found[0]); self.sales_customer_chosen()
            elif _event is not None and _event.keysym not in ("Up","Down","Return","Escape"):
                self.sales_party_box.after_idle(lambda:self.sales_party_box.event_generate("<Down>"))

    def select_searched_sales_customer(self):
        choices=list(self.sales_party_box["values"])
        if len(choices)==1:
            self.sales_party.set(choices[0]); self.sales_customer_chosen()

    def search_open_sales(self,_event=None):
        """Type only the number: 12 finds SAL-2026-000012 (and CN / DN numbers)."""
        typed=self.sales_open_choice.get().strip(); choices=list(getattr(self,"sales_open_map",{}))
        if typed.isdigit():
            wanted=int(typed); found=[c for c in choices if c.split(" (",1)[0].rsplit("-",1)[-1].isdigit() and int(c.split(" (",1)[0].rsplit("-",1)[-1])==wanted]
            self.sales_open_box["values"]=found or [c for c in choices if typed in c.split(" (",1)[0]]
        else: self.sales_open_box["values"]=[c for c in choices if typed.casefold() in c.casefold()] if typed else choices
        if typed and self.sales_open_box["values"] and _event is not None and _event.keysym not in ("Up","Down","Return","Escape","Tab"):
            self.sales_open_box.after_idle(lambda:self.sales_open_box.event_generate("<Down>"))

    def edit_sales_invoice(self):
        """Load the invoice picked in Find Invoice into the form for editing; then Save re-saves it."""
        if self.sales_open_choice.get().strip() and getattr(self,"sales_open_map",{}).get(self.sales_open_choice.get()):
            self.open_sales_invoice(); return
        choices=list(getattr(self,"sales_open_map",{}))
        if not choices:
            messagebox.showinfo("Sales Invoice","No saved invoices to edit yet."); return
        win=tk.Toplevel(self); win.title("Edit Invoice"); win.configure(bg=LIGHT); win.transient(self); win.grab_set()
        tk.Label(win,text="Pick the invoice you want to edit:",bg=LIGHT,font=("Segoe UI",10,"bold")).pack(padx=14,pady=(14,4))
        pick=tk.StringVar()
        box=ttk.Combobox(win,textvariable=pick,width=40,values=choices); box.pack(padx=14,pady=4)
        def do_edit():
            if pick.get() in getattr(self,"sales_open_map",{}):
                self.sales_open_choice.set(pick.get()); win.destroy(); self.open_sales_invoice()
        def filt(_e=None):
            t=pick.get().strip().casefold(); box["values"]=[c for c in choices if t in c.casefold()] if t else choices
            if t and box["values"] and _e is not None and _e.keysym not in ("Up","Down","Return","Escape","Tab"):
                box.after_idle(lambda:box.event_generate("<Down>"))
        box.bind("<KeyRelease>",filt); box.bind("<Return>",lambda _e:do_edit())
        tk.Button(win,text="Open for Editing",command=do_edit,bg=GOLD,fg=NAVY,font=("Segoe UI",10,"bold"),border=0,padx=14,pady=5).pack(pady=(8,14))
        box.focus_set()

    def sales_customer_chosen(self):
        party=getattr(self,"sales_customers",{}).get(self.sales_party.get())
        if party:
            self.sales_supplier_account.set(party.get("account_number") or "")
            if party.get("currency"): self.sales_currency.set(party["currency"])

    def sales_category_changed(self):
        self.sales_vat_account.set("4427")
        self.sales_expense_account.set(self.default_sales_posting_account())

    def default_sales_posting_account(self):
        category=self.sales_category.get()
        if self.sales_doc_type.get()=="Credit Note": return "709000001" if category=="Goods" else "719000001"
        return {"Goods":"701100001","Products":"711100001","Services":"713000001"}.get(category,"713000001")

    def cycle_sales_type(self):
        """Space bar toggles Sales Type (Goods -> Products -> Services -> ...) and
        re-applies the matching posting accounts and data entry."""
        options=list(self.sales_category_box["values"]) or ["Goods","Products","Services"]
        try: index=options.index(self.sales_category.get())
        except ValueError: index=-1
        self.sales_category.set(options[(index+1)%len(options)])
        self.sales_category_changed()
        return "break"

    def sales_vat_in_lbp(self,vat_amount,currency=None):
        """Return (VAT expressed in LBP, LBP rate for one currency unit) for the
        invoice date. LBP invoices return the amount as-is; when no rate exists
        it returns (None, None)."""
        currency=currency or self.sales_currency.get()
        try: vat=float(vat_amount or 0)
        except (TypeError,ValueError): vat=0.0
        if currency=="LBP": return vat,None
        try:
            rates=self.sales_rates_for_date(self.client.exchange_rates(),self.sales_date.get())
            vat_lbp,_=self.exchange_equivalents(vat,currency,rates)
            unit_lbp,_=self.exchange_equivalents(1.0,currency,rates)
            return vat_lbp,unit_lbp
        except Exception:
            return None,None

    def sales_account_chosen(self):
        code=self.sales_supplier_account.get().split(" - ",1)[0].strip()
        if not code: return
        party=next((party for party in getattr(self,"sales_customers",{}).values()
                    if str(party.get("account_number") or "").strip()==code),None)
        if party:
            self.sales_party.set(party["name"])
            if party.get("currency"): self.sales_currency.set(party["currency"])

    def new_sales_invoice(self,confirm=True):
        if confirm and self.sales_items and not messagebox.askyesno("Sales Invoice","Start a new invoice? Lines that are not saved will be cleared."): return
        self.sales_edit_id=None; self.sales_items=[]; self.sales_sheet.delete(*self.sales_sheet.get_children())
        self._sales_loaded_state=None
        self.sales_party.set(""); self.sales_supplier_account.set(""); self.sales_amount_paid.set("0"); self.sales_due_date.set(""); self.sales_open_choice.set("")
        self.sales_doc_type.set("Invoice"); self.sales_category.set("Services")
        self.sales_category_box["values"]=["Goods","Products","Services"]
        self.sales_revenue_caption.config(text="Revenue Account")
        self.sales_supplier_side.set("D - Debit"); self.sales_vat_side.set("C - Credit"); self.sales_expense_side.set("C - Credit")
        self.sales_payment_method.set("On Account (Not Cash)"); self.sales_date.set(self.fiscal_today())
        self.sales_department.set("(none)"); self.sales_project.set("(none)"); self.sales_treatment.set("Taxable 11%")
        self.sales_discount_percent.set("0"); self.sales_discount_amount.set("0")
        self.sales_category_changed()
        self.sales_mode_label.config(text="NEW INVOICE",bg=GOLD); self.load_sales_customer_list(); self.refresh_sales_number()
        self.update_sales_navigation()
        self.add_sales_item(); self.update_sales_totals()

    def sales_row_values(self,item):
        return (item.get("item_code") or "",item.get("description",""),f'{float(item.get("quantity") or 0):g}',item.get("unit") or "",f'{float(item.get("unit_price") or 0):,.2f}',
                f'{float(item.get("gross_amount") or 0):,.2f}',f'{float(item.get("discount_percent") or 0):g}%' if float(item.get("discount_percent") or 0) else "",
                f'{float(item.get("vat_rate") or 0):g}',f'{float(item.get("net") or 0):,.2f}')

    def recalculate_sales_item(self,item):
        """Line: Amount = Qty x Price, less the line discount %. VAT and the invoice discount are shared in update_sales_totals."""
        item["quantity"]=float(item.get("quantity") or 0); item["unit_price"]=float(item.get("unit_price") or 0)
        item["discount_percent"]=float(item.get("discount_percent") or 0); item["vat_rate"]=float(item.get("vat_rate") if item.get("vat_rate") not in (None,"") else 11)
        item["gross_amount"]=round(item["quantity"]*item["unit_price"],2); item["net"]=round(item["gross_amount"]*(1-item["discount_percent"]/100),2)
        item.setdefault("unit",""); item.setdefault("subtotal",item["net"]); item.setdefault("vat",0.0); item.setdefault("total",item["net"])
        return item

    def add_sales_item(self,item=None):
        item=self.recalculate_sales_item(dict(item or {"description":"","quantity":1,"unit":"","unit_price":0,"discount_percent":0,"vat_rate":0 if getattr(self,"sales_treatment",None) is not None and self.sales_treatment.get()!="Taxable 11%" else 11}))
        self.sales_items.append(item); iid=self.sales_sheet.insert("","end",values=self.sales_row_values(item))
        item["_iid"]=iid; self.update_sales_totals()
        if not item["description"]:
            self.sales_sheet.selection_set(iid); self.sales_sheet.focus(iid)
            self.after(50,lambda:self.edit_sales_cell(column_index=1 if not getattr(self,"inventory_rows",None) else 0,iid=iid))
        return iid

    def sales_item_for(self,iid):
        return next((item for item in self.sales_items if item.get("_iid")==iid),None)

    def edit_sales_cell(self,event=None,column_index=None,iid=None):
        """Put an entry box over one cell of the sheet, like a spreadsheet."""
        tree=self.sales_sheet
        if event is not None and column_index is None:
            if getattr(event,"keysym","")=="Return": iid=tree.focus(); column_index=0
            else:
                iid=tree.identify_row(event.y); column=tree.identify_column(event.x) or "#1"
                column_index=max(0,int(column.lstrip("#") or 1)-1)
        iid=iid or tree.focus()
        if not iid or not tree.exists(iid) or not tree.winfo_ismapped(): return
        editable=[key for key,_label,_width in self.sales_columns if key not in ("total","gross_amount")]
        key=self.sales_columns[column_index][0]
        if key in ("total","gross_amount"): key="description"; column_index=1
        bbox=tree.bbox(iid,f"#{column_index+1}")
        if not bbox: return
        item=self.sales_item_for(iid)
        if item is None: return
        value=item.get(key,"")
        editor=tk.Entry(tree,justify="left" if key in ("description","item_code","unit") else "right"); editor.insert(0,str(value if key in ("description","item_code","unit") else f"{float(value or 0):g}"))
        editor.place(x=bbox[0],y=bbox[1],width=bbox[2],height=bbox[3]); editor.focus_set(); editor.select_range(0,"end")
        def commit(move=0):
            text=editor.get().strip(); editor.destroy()
            if key=="description": item["description"]=text
            elif key=="unit": item["unit"]=text
            elif key=="item_code":
                product=self.item_by_code(text) if text else None
                if text and not product: return messagebox.showwarning("Sales Invoice",f"Item {text} was not found (Inventory > Items)")
                item["item_code"]=product["sku"] if product else ""
                if product:
                    item["description"]=product["name"]; item["unit"]=product.get("unit") or ""
                    if product["sales_price"]: item["unit_price"]=product["sales_price"]
                    if product.get("default_vat") not in (None,""):
                        item["vat_rate"]=float(str(product["default_vat"]).replace("%","") or 11); item["_vat_typed"]=False
            else:
                try: number=float(text.replace(",","") or 0)
                except ValueError: return messagebox.showwarning("Sales Invoice",f"{self.sales_columns[column_index][1]} must be a number")
                if number<0: return messagebox.showwarning("Sales Invoice","Amounts cannot be negative")
                item[key]=number
                if key=="deductible_subtotal": item["_taxable_typed"]=True
                if key in ("quantity","unit_price"): item["_taxable_typed"]=False
                if key=="vat": item["_vat_typed"]=True
                if key in ("quantity","unit_price","deductible_subtotal","vat_rate"): item["_vat_typed"]=False
            self.recalculate_sales_item(item); tree.item(iid,values=self.sales_row_values(item)); self.update_sales_totals()
            if move:
                position=editable.index(key) if key in editable else 0
                if position+1<len(editable): self.after(10,lambda:self.edit_sales_cell(column_index=[c[0] for c in self.sales_columns].index(editable[position+1]),iid=iid))
                else:
                    rows=tree.get_children(); index=rows.index(iid)
                    if index+1<len(rows): self.after(10,lambda:self.edit_sales_cell(column_index=0,iid=rows[index+1]))
                    elif item["description"]: self.add_sales_item()
        editor.bind("<Return>",lambda _event:commit(1)); editor.bind("<Tab>",lambda _event:(commit(1),"break")[1])
        editor.bind("<FocusOut>",lambda _event:commit(0) if editor.winfo_exists() else None); editor.bind("<Escape>",lambda _event:editor.destroy())

    def remove_sales_item(self):
        selected=self.sales_sheet.selection()
        if not selected: return messagebox.showwarning("Sales Invoice","Select a line first")
        for iid in selected:
            item=self.sales_item_for(iid)
            if item: self.sales_items.remove(item)
            self.sales_sheet.delete(iid)
        self.update_sales_totals()

    def sales_debit_credit_totals(self):
        total=sum(float(item.get("total",0)) for item in self.sales_items if item.get("description"))
        return total,total

    def calculate_sales_line(self): return None

    def update_sales_totals(self):
        import invoice_calc
        from tafqeet import amount_in_words
        lines=[i for i in self.sales_items if str(i.get("description") or "").strip() or float(i.get("unit_price") or 0)]
        export=getattr(self,"sales_treatment",None) is not None and self.sales_treatment.get()!="Taxable 11%"
        try: result=invoice_calc.calculate(lines,self.sales_discount_percent.get() if hasattr(self,"sales_discount_percent") else 0,
                                           self.sales_discount_amount.get() if hasattr(self,"sales_discount_amount") else 0,export)
        except ValueError as exc:
            if hasattr(self,"sales_total_labels"): self.sales_total_labels["TOTAL"].config(text=str(exc),fg="#8B1E1E")
            return
        for item,calculated in zip(lines,result["lines"]):
            for key in ("deductible_subtotal","non_deductible_subtotal","vat","subtotal","total","gross_amount","discount_amount","discount_percent","vat_rate"): item[key]=calculated[key]
            iid=item.get("_iid")
            if iid and self.sales_sheet.exists(iid): self.sales_sheet.item(iid,values=self.sales_row_values(item))
        self.sales_calculation=result; currency=self.sales_currency.get()
        if hasattr(self,"sales_total_labels"):
            values={"Total":result["total"],"Discount":-result["discount"] if result["discount"] else 0,
                    "Total HT":result["total_ht"],"VAT":result["vat"],"TOTAL":result["grand_total"]}
            for key,label in self.sales_total_labels.items():
                label.config(text=f"{values[key]:,.2f} {currency}" if key=="TOTAL" else f"{values[key]:,.2f}",fg=NAVY)
            self.sales_vat_caption.config(text="VAT 11%" if not export else f"VAT 11%  ({self.sales_treatment.get()})",font=("Segoe UI",9,"overstrike") if export else ("Segoe UI",9))
            from report_export import shape_arabic
            words=amount_in_words(result["grand_total"],currency); self.sales_words.config(text=f'{words["en"]}\n{shape_arabic(words["ar"])}')
        self.sales_totals.config(text=f'{len(lines)} line(s)')

    def sales_type_changed(self):
        self.calculate_sales_line(); self.update_sales_totals()

    def exchange_equivalents(self,amount,currency,rates):
        def convert(value,source,target):
            if source==target: return value
            for row in rates:
                rate=float(row["rate"])
                if row["from_currency"]==source and row["to_currency"]==target: return value*rate
                if row["from_currency"]==target and row["to_currency"]==source and rate: return value/rate
            return None
        if currency=="LBP": return amount,convert(amount,"LBP","USD")
        lbp=convert(amount,currency,"LBP"); usd=amount if currency=="USD" else convert(amount,currency,"USD")
        if usd is None and lbp is not None: usd=convert(lbp,"LBP","USD")
        if lbp is None and usd is not None: lbp=convert(usd,"USD","LBP")
        return lbp,usd

    @staticmethod
    def sales_rates_for_date(rates,invoice_date):
        """Use the most recent available rate on or before the invoice date per pair."""
        try: day=parse_user_date(invoice_date)
        except (ValueError,TypeError): return rates
        selected={}
        for row in rates:
            rate_day=sortable_date(row.get("rate_date"))
            if rate_day==datetime.min or rate_day>day: continue
            pair=(row["from_currency"],row["to_currency"])
            if pair not in selected or rate_day>selected[pair][0]: selected[pair]=(rate_day,row)
        return [entry[1] for entry in selected.values()]

    def exchange_equivalent_text(self, amount, currency, rates=None):
        if not amount:
            return "Exchange equivalent: 0.00"
        if rates is None:
            try: rates=self.client.exchange_rates()
            except Exception: rates=[]
        lbp,usd=self.exchange_equivalents(amount,currency,rates)
        if currency=="LBP":
            return f"Exchange equivalent: USD {usd:,.2f}" if usd is not None else "Exchange equivalent: USD rate not entered"
        lbp_text=f"LBP {lbp:,.2f}" if lbp is not None else "LBP rate not entered"
        usd_text=f"USD {usd:,.2f}" if usd is not None else "USD rate not entered"
        return f"Exchange equivalent: {lbp_text}   |   {usd_text}"

    def sales_entry_report(self, format_name):
        if not self.sales_items:
            return messagebox.showwarning("Manual Entry","Add at least one invoice item")
        invoice_no=self.sales_no.get().strip() or "Draft"
        party=self.sales_party.get().strip() or "Unspecified"
        currency=self.sales_currency.get()
        title=f"Invoice {invoice_no} - {party} - {currency}"
        headers=["Description","Quantity","Unit Price","Deductible","Non-Deductible","VAT %","VAT Amount","After VAT","Debit","Credit"]
        rows=[[item["description"],item["quantity"],item["unit_price"],item.get("deductible_subtotal",item["subtotal"]),item.get("non_deductible_subtotal",0),item["vat_rate"],item["vat"],item["total"],
               item["total"] if self.sales_kind.get()=="sales" else 0,item["total"] if self.sales_kind.get()!="sales" else 0] for item in self.sales_items]
        total_amount=sum(float(item["total"]) for item in self.sales_items)
        rows.append(["","",f"TOTAL {currency}",sum(float(item.get("deductible_subtotal",item["subtotal"])) for item in self.sales_items),sum(float(item.get("non_deductible_subtotal",0)) for item in self.sales_items),
                     "",sum(float(item["vat"]) for item in self.sales_items),total_amount,
                     total_amount if self.sales_kind.get()=="sales" else 0,total_amount if self.sales_kind.get()!="sales" else 0])
        try:
            if format_name=="print":
                print_rows(title,headers,rows); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"
            path=filedialog.asksaveasfilename(defaultextension=extension,
                filetypes=[("Excel workbook","*.xlsx")] if format_name=="xlsx" else [("PDF document","*.pdf")],
                initialfile=f"Invoice_{invoice_no}_{currency}{extension}")
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,rows)
            messagebox.showinfo("Manual Entry",f"Saved successfully:\\n{path}")
        except Exception as exc:
            messagebox.showerror("Manual Entry",str(exc))

    def open_sales_invoice(self):
        row=getattr(self,"sales_open_map",{}).get(self.sales_open_choice.get())
        if not row: return False
        if self.sales_edit_id and getattr(self,"_sales_loaded_state",None)!=self.sales_form_state():
            prompt="Reload this invoice?" if self.sales_edit_id==row["id"] else "Open another invoice?"
            if not messagebox.askyesno("Sales Invoice",f"{prompt} Unsaved changes will be cleared."):
                self.sales_open_choice.set(next((key for key,item in self.sales_open_map.items() if item["id"]==self.sales_edit_id),""))
                return False
        if self.sales_items and any(i.get("description") for i in self.sales_items) and not self.sales_edit_id:
            if not messagebox.askyesno("Sales Invoice","Open this invoice? The lines you are typing now will be cleared."):
                self.sales_open_choice.set("")
                return False
        try: items=self.client.invoice_items(row["id"]); detail=next(r for r in self.client.invoices() if r["id"]==row["id"])
        except Exception as exc: messagebox.showerror("Sales Invoice",str(exc)); return False
        self.sales_edit_id=row["id"]; self.sales_items=[]; self.sales_sheet.delete(*self.sales_sheet.get_children())
        self.sales_no.set(detail["invoice_number"]); self.sales_date.set(safe_display_date(detail["invoice_date"])); self.sales_party.set(detail["party_name"] or "")
        self.sales_supplier_account.set(detail.get("supplier_account") or ""); self.sales_party.set(detail["party_name"] or "")
        self.sales_currency.set(detail["currency"]); self.sales_vat_account.set(detail.get("vat_account") or "4427")
        self.sales_expense_account.set(detail.get("expense_account") or "713100000"); self.sales_payment_method.set(detail.get("payment_method") or "On Account (Not Cash)")
        self.sales_branch.set(detail.get("branch_name") or "Head Office")
        sides=(detail.get("supplier_side") or "D",detail.get("vat_side") or "C",detail.get("expense_side") or "C")
        if sides==("C","D","D") and detail.get("doc_subtype")!="credit_note":
            sides=("D","C","C")  # older sales stored purchase-side defaults despite posting Dr client / Cr revenue and VAT
        self.sales_supplier_side.set("D - Debit" if sides[0].startswith("D") else "C - Credit")
        self.sales_vat_side.set("D - Debit" if sides[1].startswith("D") else "C - Credit")
        self.sales_expense_side.set("D - Debit" if sides[2].startswith("D") else "C - Credit")
        lists=self.dimension_lists(refresh=True)
        self.sales_department.set(next((f'{d["code"]} - {d["name"]}' for d in lists["departments"] if d["id"]==detail.get("department_id")),"(none)"))
        self.sales_project.set(next((f'{p["code"]} - {p["name"]}' for p in lists["projects"] if p["id"]==detail.get("project_id")),"(none)"))
        self.sales_treatment.set(next((k for k,v in SALE_TREATMENTS.items() if v==(detail.get("vat_treatment") or "standard")),"Taxable 11%"))
        self.sales_amount_paid.set(str(detail.get("amount_paid") or 0)); self.sales_due_date.set(safe_display_date(detail.get("due_date")) if detail.get("due_date") else "")
        self.sales_doc_type.set({"credit_note":"Credit Note","debit_note":"Debit Note"}.get(detail.get("doc_subtype") or "invoice","Invoice"))
        self.sales_revenue_caption.config(text="Discount Account" if self.sales_doc_type.get()=="Credit Note" else "Revenue Account")
        revenue_code=str(detail.get("expense_account") or "")
        if self.sales_doc_type.get()=="Credit Note":
            category="Goods" if revenue_code.startswith("709") else "Products / Services"
            self.sales_category_box["values"]=["Goods","Products / Services"]
        else:
            category="Goods" if revenue_code.startswith("701") else "Products" if revenue_code.startswith("711") else "Services"
            self.sales_category_box["values"]=["Goods","Products","Services"]
        self.sales_category.set(category)
        self.sales_discount_percent.set(f'{float(detail.get("invoice_discount_percent") or 0):g}'); self.sales_discount_amount.set(f'{float(detail.get("invoice_discount_amount") or 0):g}')
        for line in items or [{"description":"Invoice total","quantity":1,"unit_price":float(detail["subtotal"] or 0),"vat_rate":11}]:
            item={"item_code":line.get("item_code") or "","description":line["description"],"quantity":float(line["quantity"]),"unit":line.get("unit") or "",
                  "unit_price":float(line["unit_price"]),"discount_percent":float(line.get("discount_percent") or 0),"vat_rate":float(line["vat_rate"])}
            self.add_sales_item(item)
        status={"posted":"POSTED","review":"DRAFT"}.get(detail.get("status"),str(detail.get("status")).upper())
        self.sales_mode_label.config(text=f"EDITING {detail['invoice_number']} ({status})",bg="#dfe6ee")
        self._sales_loaded_state=self.sales_form_state()
        self.update_sales_navigation()
        return True

    def sales_form_state(self):
        fields=(self.sales_no,self.sales_date,self.sales_party,self.sales_currency,self.sales_supplier_account,self.sales_vat_account,
                self.sales_expense_account,self.sales_supplier_side,self.sales_vat_side,self.sales_expense_side,self.sales_payment_method,
                self.sales_due_date,self.sales_amount_paid,self.sales_branch,self.sales_department,self.sales_project,self.sales_treatment,
                self.sales_doc_type,self.sales_category,self.sales_discount_percent,self.sales_discount_amount)
        lines=tuple((item.get("item_code"),item.get("description"),item.get("quantity"),item.get("unit"),
                     item.get("unit_price"),item.get("discount_percent"),item.get("vat_rate")) for item in self.sales_items)
        return tuple(field.get() for field in fields),lines

    def save_sales_invoice(self,post=False):
        self.update_sales_totals()
        lines=[{k:v for k,v in item.items() if not k.startswith("_") and k!="net"} for item in self.sales_items if str(item.get("description") or "").strip()]
        if not self.sales_party.get().strip(): return messagebox.showwarning("Sales Invoice","Choose or type the customer")
        orphan=[item for item in self.sales_items if not str(item.get("description") or "").strip() and float(item.get("quantity") or 0)*float(item.get("unit_price") or 0)]
        if orphan: return messagebox.showwarning("Sales Invoice","A line has an amount but no description. Add a description or delete that line before saving, so the saved total matches what you see.")
        if not lines: return messagebox.showwarning("Sales Invoice","Add at least one line with a description")
        invoice={"invoice_number":self.sales_no.get().strip(),"invoice_date":self.sales_date.get().strip(),
                 "party_name":self.sales_party.get().strip(),"kind":"sales","currency":self.sales_currency.get(),
                 "supplier_account":self.sales_supplier_account.get().split(" - ",1)[0].strip(),
                 "vat_account":self.sales_vat_account.get().split(" - ",1)[0].strip() or "4427",
                 "expense_account":self.sales_expense_account.get().split(" - ",1)[0].strip() or self.default_sales_posting_account(),
                 "supplier_side":self.sales_supplier_side.get(),"vat_side":self.sales_vat_side.get(),"expense_side":self.sales_expense_side.get(),
                 "due_date":self.sales_due_date.get().strip(),"payment_method":self.sales_payment_method.get(),"amount_paid":self.sales_amount_paid.get().strip().replace(",","") or "0",
                 "branch":self.sales_branch.get(),"status":"posted" if post else "review","source_file":"Sales Invoice","source_row":None,
                 "department":self.dimension_code(self.sales_department.get()),"project":self.dimension_code(self.sales_project.get()),
                 "vat_treatment":SALE_TREATMENTS.get(self.sales_treatment.get(),"standard"),
                 "doc_subtype":{"Credit Note":"credit_note","Debit Note":"debit_note"}.get(self.sales_doc_type.get(),"invoice"),
                 "invoice_discount_percent":self.sales_discount_percent.get().strip() or "0","invoice_discount_amount":self.sales_discount_amount.get().strip() or "0",
                 "gross_before_discount":getattr(self,"sales_calculation",{}).get("total","")}
        if invoice["doc_subtype"]=="credit_note":
            invoice["amount_paid"]="0"
        try:
            invoice["invoice_date"]=formatted_user_date(invoice["invoice_date"])
            if invoice["due_date"]: invoice["due_date"]=formatted_user_date(invoice["due_date"])
        except ValueError as exc: return messagebox.showerror("Sales Invoice",str(exc))
        if self.sales_edit_id:
            if not messagebox.askyesno("Sales Invoice",f"Save the changes to invoice {invoice['invoice_number']}? Its journal entry will be replaced with the new figures."): return
        try:
            if self.sales_edit_id: self.client.replace_invoice(self.sales_edit_id,invoice,lines)
            else: self.client.create_manual_invoice(invoice,lines)
        except Exception as exc: return messagebox.showerror("Sales Invoice",str(exc))
        number=invoice["invoice_number"]
        messagebox.showinfo("Sales Invoice",f'Invoice {number} saved as {"Posted" if post else "Draft"}.')
        self.new_sales_invoice(confirm=False)
        self.load_dashboard(); self.load_invoices(); self.load_journal(); self.load_trial()

    def delete_sales_invoice(self):
        if not self.sales_edit_id: return messagebox.showwarning("Sales Invoice","Open a saved invoice first")
        number=self.sales_no.get()
        if not messagebox.askyesno("Delete Invoice",f"Mark invoice {number} DELETED? Its number stays in the invoice list; the journal entry is removed."):
            return
        try: self.client.delete_invoice(self.sales_edit_id)
        except Exception as exc: return messagebox.showerror("Sales Invoice",str(exc))
        self.new_sales_invoice(confirm=False)
        self.load_invoices(); self.load_dashboard(); self.load_journal(); self.load_trial()

    def build_parties(self):
        form=tk.LabelFrame(self.parties_tab,text="Customer / Supplier File",bg=LIGHT,padx=10,pady=8); form.pack(fill="x",padx=10,pady=10)
        self.edit_party_id=None; self.party_name=tk.StringVar(); self.party_kind=tk.StringVar(value="client"); self.party_account_number=tk.StringVar(); self.party_tax=tk.StringVar(); self.party_mof=tk.StringVar(); self.party_address=tk.StringVar(); self.party_contact=tk.StringVar(); self.party_currency=tk.StringVar(value="USD"); self.party_due_days=tk.StringVar(value="0")
        tk.Label(form,text="Account Number",bg=LIGHT,font=("Segoe UI",10,"bold")).grid(row=0,column=0,sticky="w",padx=4,pady=4)
        account_entry=tk.Entry(form,textvariable=self.party_account_number,width=16,font=("Segoe UI",11,"bold")); account_entry.grid(row=0,column=1,sticky="w",padx=4,pady=4)
        self.party_account_hint=tk.Label(form,text="Type the first 4 digits (4111 client, 4011 supplier) - the full number fills in automatically",bg=LIGHT,fg="#5f6b76")
        self.party_account_hint.grid(row=0,column=2,columnspan=6,sticky="w",padx=4)
        account_entry.bind("<KeyRelease>",self.party_account_typed)
        tk.Label(form,text="Type",bg=LIGHT).grid(row=1,column=0,sticky="w",padx=4,pady=4)
        kind_box=ttk.Combobox(form,textvariable=self.party_kind,values=["client","supplier","asset_supplier","other_payable"],state="readonly",width=15); kind_box.grid(row=1,column=1,sticky="w",padx=4)
        kind_box.bind("<<ComboboxSelected>>",lambda _event:self.suggest_party_prefix())
        tk.Label(form,text="Name",bg=LIGHT).grid(row=1,column=2,sticky="w",padx=4); tk.Entry(form,textvariable=self.party_name,width=32).grid(row=1,column=3,sticky="w",padx=4)
        tk.Label(form,text="Currency",bg=LIGHT).grid(row=1,column=4,sticky="w",padx=4)
        ttk.Combobox(form,textvariable=self.party_currency,values=self.currency_codes,state="readonly",width=7).grid(row=1,column=5,sticky="w",padx=4)
        tk.Label(form,text="Due days from invoice",bg=LIGHT).grid(row=2,column=4,sticky="w",padx=4)
        tk.Entry(form,textvariable=self.party_due_days,width=6).grid(row=2,column=5,sticky="w",padx=4)
        for index,(label,var,width) in enumerate((("Tax Number",self.party_tax,16),("MOF Number",self.party_mof,16),("Address",self.party_address,32),("Contact Number",self.party_contact,16))):
            tk.Label(form,text=label,bg=LIGHT).grid(row=2+index//2,column=(index%2)*2,sticky="w",padx=4,pady=4)
            tk.Entry(form,textvariable=var,width=width).grid(row=2+index//2,column=(index%2)*2+1,sticky="w",padx=4,pady=4)
        buttons=tk.Frame(form,bg=LIGHT); buttons.grid(row=4,column=0,columnspan=6,sticky="w",padx=4,pady=(6,0))
        self.action_button(buttons,"New",self.new_party_account).pack(side="left",padx=3)
        tk.Button(buttons,text="Save",command=self.save_party,bg=GOLD,fg=NAVY,font=("Segoe UI",9,"bold"),border=0,padx=18,pady=7).pack(side="left",padx=3)
        self.action_button(buttons,"Edit Selected",self.edit_selected_party).pack(side="left",padx=3)
        self.action_button(buttons,"Legal Documents",self.party_documents_dialog).pack(side="left",padx=3)
        self.action_button(buttons,"Customer / Supplier Ageing",self.open_party_ageing).pack(side="left",padx=3)
        self.action_button(buttons,"Client Items: Qty & Value",self.open_client_items_report).pack(side="left",padx=3)
        self.parties_tree=self.table(self.parties_tab,[("id","ID",55),("account","9-Digit Account",115),("name","Name",180),("kind","Type",85),("tax","Tax Number",110),("mof","MOF Number",110),("address","Address",180),("contact","Contact",110),("currency","Currency",70),("due_days","Due Days",80)])
        self.parties_tree.bind("<Double-1>",lambda _event:self.edit_selected_party())
        self.load_parties_page()

    def party_account_typed(self,event=None):
        if event is not None and event.keysym in ("BackSpace","Delete","Left","Right","Tab"): return
        digits="".join(ch for ch in self.party_account_number.get() if ch.isdigit())
        if len(digits)!=4 or self.edit_party_id: return
        try: number=self.client.next_party_account_number(digits)
        except Exception as exc: self.party_account_hint.config(text=str(exc),fg="#8B1E1E"); return
        self.party_account_number.set(number); self.party_account_hint.config(text=f"Next free account under {digits}: {number}",fg=NAVY)

    def suggest_party_prefix(self):
        if self.edit_party_id: return
        prefix={"client":"4111","supplier":"4011","asset_supplier":"4031","other_payable":"4619"}.get(self.party_kind.get(),"4011")
        current="".join(ch for ch in self.party_account_number.get() if ch.isdigit())
        if not current or (len(current)==9 and current[:4] in ("4111","4011","4031","4619")):
            self.party_account_number.set(prefix); self.party_account_typed()

    def new_party_account(self):
        self.edit_party_id=None; self.party_name.set(""); self.party_kind.set("client"); self.party_account_number.set(""); self.party_tax.set(""); self.party_mof.set(""); self.party_address.set(""); self.party_contact.set(""); self.party_currency.set("USD"); self.party_due_days.set("0")
        self.suggest_party_prefix()

    def save_party(self):
        try: saved=self.client.save_party({"id":self.edit_party_id,"name":self.party_name.get(),"account_category":self.party_kind.get(),"account_number":self.party_account_number.get(),"tax_number":self.party_tax.get(),"mof_number":self.party_mof.get(),"address":self.party_address.get(),"contact_number":self.party_contact.get(),"currency":self.party_currency.get(),"due_days":self.party_due_days.get()})
        except Exception as exc: return messagebox.showerror("Customers / Suppliers",str(exc))
        self.edit_party_id=saved.get("id"); self.party_account_number.set(saved.get("account_number") or ""); self.load_parties_page(); self.load_statement_parties()
        messagebox.showinfo("Customers / Suppliers",f'Saved successfully\nAutomatic Account Number: {saved.get("account_number") or ""}')

    def edit_selected_party(self):
        selected=self.parties_tree.selection()
        if not selected: return messagebox.showwarning("Customers / Suppliers","Select a customer or supplier first")
        values=self.parties_tree.item(selected[0],"values"); self.edit_party_id=int(values[0]); self.party_account_number.set(values[1]); self.party_name.set(values[2]); self.party_kind.set(values[3]); self.party_tax.set(values[4]); self.party_mof.set(values[5]); self.party_address.set(values[6]); self.party_contact.set(values[7]); self.party_currency.set(values[8]); self.party_due_days.set(values[9])

    def load_parties_page(self):
        try: rows=self.client.parties()
        except Exception as exc: return messagebox.showerror("Customers / Suppliers",str(exc))
        self.party_rows=rows; self.parties_tree.delete(*self.parties_tree.get_children())
        for row in rows: self.parties_tree.insert("","end",values=(row["id"],row.get("account_number") or "",row["name"],row.get("account_category") or row["kind"],row.get("tax_number") or "",row.get("mof_number") or "",row.get("address") or "",row.get("contact_number") or "",row["currency"],row.get("due_days") or 0))

    def open_party_ageing(self):
        self.select_main_tab(self.inventory_tab)
        for widget in self.inventory_tab.winfo_children():
            if isinstance(widget,ttk.Notebook):
                widget.select(self.ageing_tab); break

    def open_client_items_report(self):
        self.select_main_tab(self.reports_tab)
        self.financial_notebook.select(self.business_reports_page)
        self.br["report"].set("Client Items: Qty & Value")
        self.run_business_report()

    def party_documents_dialog(self):
        """Legal documents of a customer / supplier. Tick "Applies" for the documents this party must have,
        enter the issue / expiry dates and Save: the scanned file is optional and can be attached later.
        Expiry alerts cover only the documents that apply."""
        selected=self.parties_tree.selection()
        if not selected: return messagebox.showwarning("Legal Documents","Select a customer or supplier first")
        party_id=int(self.parties_tree.item(selected[0],"values")[0]); party_name=self.parties_tree.item(selected[0],"values")[2]
        window=tk.Toplevel(self); window.title(f"Legal Documents - {party_name}"); window.configure(bg=LIGHT); window.geometry("980x500"); window.transient(self)
        controls=tk.Frame(window,bg=LIGHT); controls.pack(fill="x",padx=8,pady=(8,2))
        doc_type=tk.StringVar(value="MOF / VAT Certificate"); issue=tk.StringVar(); expiry=tk.StringVar(); notes=tk.StringVar(); active=tk.BooleanVar(value=True)
        editing={"id":None}; pending_file={"path":None}
        tk.Label(controls,text="Document",bg=LIGHT).pack(side="left")
        ttk.Combobox(controls,textvariable=doc_type,values=["MOF / VAT Certificate","Commercial Registration","ID / Passport","NSSF Document","Contract","Other"],width=24).pack(side="left",padx=3)
        tk.Checkbutton(controls,text="Applies",variable=active,bg=LIGHT).pack(side="left",padx=(6,6))
        tk.Label(controls,text="Issue",bg=LIGHT).pack(side="left"); self.date_entry(controls,issue,11).pack(side="left",padx=3)
        tk.Label(controls,text="Expiry",bg=LIGHT).pack(side="left"); self.date_entry(controls,expiry,11).pack(side="left",padx=3)
        tk.Label(controls,text="Notes",bg=LIGHT).pack(side="left"); tk.Entry(controls,textvariable=notes,width=22).pack(side="left",padx=3)
        status=tk.Label(window,text="New document: fill in the fields and press Save (attaching a file is optional).",bg=LIGHT,fg=NAVY,anchor="w"); status.pack(fill="x",padx=10)
        tree=self.table(window,[("type","Document Type",170),("applies","Applies",70),("state","Status",130),("issue","Issue Date",95),("expiry","Expiry Date",95),("file","File",200),("notes","Notes",160)])
        records={}
        def document_state(row):
            if not row.get("active",1): return "Not applicable"
            text=str(row.get("expiry_date") or "").strip()
            if not text: return "Valid (no expiry)"
            try: remaining=(datetime.strptime(formatted_user_date(text),"%d-%m-%Y").date()-datetime.now().date()).days
            except ValueError: return "Check expiry date"
            return "EXPIRED" if remaining<0 else "Expires today" if remaining==0 else f"Expires in {remaining} days" if remaining<=30 else "Valid"
        def refresh(select_id=None):
            nonlocal records
            try: rows=self.client.party_documents(party_id)
            except Exception as exc: return messagebox.showerror("Legal Documents",str(exc),parent=window)
            records={str(row["id"]):row for row in rows}; tree.delete(*tree.get_children())
            for row in rows:
                tree.insert("","end",iid=str(row["id"]),values=(row["document_type"],"Yes" if row.get("active",1) else "No",document_state(row),row.get("issue_date") or "",
                    row.get("expiry_date") or "",row["file_name"] or "(no file yet)",row.get("notes") or ""))
            if select_id and tree.exists(str(select_id)): tree.selection_set(str(select_id))
        def new_document():
            editing["id"]=None; pending_file["path"]=None; doc_type.set("MOF / VAT Certificate"); active.set(True); issue.set(""); expiry.set(""); notes.set("")
            tree.selection_remove(tree.selection()); status.config(text="New document: fill in the fields and press Save (attaching a file is optional).")
        def selected_changed(_event=None):
            chosen=tree.selection()
            if not chosen: return
            row=records.get(chosen[0])
            if not row: return
            editing["id"]=row["id"]; pending_file["path"]=None
            doc_type.set(row["document_type"]); active.set(bool(row.get("active",1))); issue.set(row.get("issue_date") or ""); expiry.set(row.get("expiry_date") or ""); notes.set(row.get("notes") or "")
            status.config(text=f'Editing: {row["document_type"]}. Change the tick or dates and press Save.')
        tree.bind("<<TreeviewSelect>>",selected_changed,add="+")
        def fields():
            values={"document_type":doc_type.get().strip() or "Other","active":active.get(),"notes":notes.get().strip()}
            for key,variable,label in (("issue_date",issue,"Issue date"),("expiry_date",expiry,"Expiry date")):
                text=variable.get().strip()
                try: values[key]=formatted_user_date(text) if text else ""
                except ValueError: raise ValueError(f"{label} must be DD-MM-YYYY")
            return values
        def file_payload():
            path=pending_file["path"]
            if not path: return {},b""
            return {"file_name":Path(path).name,"mime_type":mimetypes.guess_type(path)[0] or "application/octet-stream"},Path(path).read_bytes()
        def save():
            try:
                values=fields(); extra,content=file_payload(); values.update(extra)
                if editing["id"]: document_id=self.client.update_party_document(editing["id"],values,content)["document_id"]
                else: document_id=self.client.upload_party_document(party_id,values,content)["document_id"]
            except Exception as exc: return messagebox.showerror("Legal Documents",str(exc),parent=window)
            editing["id"]=document_id; pending_file["path"]=None; refresh(document_id)
            status.config(text=f"Saved: {values['document_type']}"+("" if values["active"] else " (not applicable)")+".")
        def attach():
            path=filedialog.askopenfilename(parent=window,filetypes=[("Documents","*.pdf *.png *.jpg *.jpeg"),("All files","*.*")])
            if not path: return
            pending_file["path"]=path; save()
        def download():
            selected_doc=tree.selection()
            if not selected_doc: return
            record=records[selected_doc[0]]
            if not record.get("file_name"): return messagebox.showinfo("Legal Documents","No file is attached to this document yet. Use Attach File.",parent=window)
            path=filedialog.asksaveasfilename(parent=window,initialfile=record["file_name"])
            if path: Path(path).write_bytes(self.client.download_party_document(record["id"])["content"])
        buttons=tk.Frame(window,bg=LIGHT); buttons.pack(pady=8)
        self.action_button(buttons,"New",new_document).pack(side="left",padx=4)
        self.action_button(buttons,"Save",save).pack(side="left",padx=4)
        self.action_button(buttons,"Attach / Replace File…",attach).pack(side="left",padx=4)
        self.action_button(buttons,"Download File",download).pack(side="left",padx=4)
        refresh()

    def build_payroll(self):
        nested=ttk.Notebook(self.payroll_tab); nested.pack(fill="both",expand=True,padx=8,pady=8); self.payroll_notebook=nested
        employees=tk.Frame(nested,bg=LIGHT); run=tk.Frame(nested,bg=LIGHT); settings_outer,settings_page=self.scrollable_page(nested); reports_page=tk.Frame(nested,bg=LIGHT)
        self.payroll_employees_page=employees
        nested.add(employees,text="Employees"); nested.add(run,text="Payroll Entry"); nested.add(reports_page,text="Official Reports (R5 / R6 / R10)"); nested.add(settings_outer,text="Tax & NSSF Settings")
        employee_actions=tk.Frame(employees,bg=LIGHT); employee_actions.pack(fill="x",padx=10,pady=8)
        self.action_button(employee_actions,"New Employee",lambda:self.employee_dialog()).pack(side="left",padx=4)
        self.action_button(employee_actions,"Edit Selected",self.edit_selected_employee).pack(side="left",padx=4)
        self.action_button(employee_actions,"R3 Registration Worksheet",lambda:self.employee_r3_worksheet("preview")).pack(side="left",padx=4)
        self.action_button(employee_actions,"R3 PDF",lambda:self.employee_r3_worksheet("pdf")).pack(side="left",padx=4)
        self.action_button(employee_actions,"R3 Excel",lambda:self.employee_r3_worksheet("xlsx")).pack(side="left",padx=4)
        self.action_button(employee_actions,"Official R3 Form",lambda:self.download_payroll_form("R3")).pack(side="left",padx=4)
        self.action_button(employee_actions,"Official R3-1 Form",lambda:self.download_payroll_form("R3-1")).pack(side="left",padx=4)
        nssf_forms=tk.Frame(employees,bg=LIGHT); nssf_forms.pack(fill="x",padx=10,pady=(0,5))
        tk.Label(nssf_forms,text="NSSF employee forms:",bg=LIGHT,fg=NAVY,font=("Segoe UI",9,"bold")).pack(side="left",padx=4)
        self.action_button(nssf_forms,"Employment Declaration Worksheet",lambda:self.employee_nssf_declaration("hire","preview")).pack(side="left",padx=4)
        self.action_button(nssf_forms,"Termination Declaration Worksheet",lambda:self.employee_nssf_declaration("leave","preview")).pack(side="left",padx=4)
        self.action_button(nssf_forms,"New Employee Registration",lambda:self.download_payroll_form("NSSF-HIRE-NEW")).pack(side="left",padx=4)
        self.action_button(nssf_forms,"Hire Existing NSSF Member",lambda:self.download_payroll_form("NSSF-HIRE-EXISTING")).pack(side="left",padx=4)
        self.action_button(nssf_forms,"Employee Leaving",lambda:self.download_payroll_form("NSSF-LEAVE")).pack(side="left",padx=4)
        self.action_button(employee_actions,"Refresh",self.load_payroll).pack(side="left",padx=4)
        self.employee_tree=self.table(employees,[("number","Employee ID",105),("name","Employee Name",220),("job","Job Title",150),
            ("start","Starting Date",110),("leaving","Leaving Date",110),("branch","Branch",120),("currency","Currency",70),
            ("salary","Base Salary",120),("nssf","NSSF Number",120),("active","Active",65)])
        self.employee_tree.bind("<Double-1>",lambda _event:self.edit_selected_employee())

        form=tk.LabelFrame(run,text="Monthly Payroll",bg=LIGHT); form.pack(fill="x",padx=10,pady=8)
        self.payroll_employee=tk.StringVar(); self.payroll_period=tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.payroll_vars={name:tk.StringVar(value="0") for name in ("salary","transport","overtime","commission","retro_salary","schooling","bonus","thirteenth_month","director_remuneration")}
        self.payroll_family_override=tk.StringVar()
        self.payroll_retro_from=tk.StringVar(); self.payroll_retro_to=tk.StringVar()
        tk.Label(form,text="Employee",bg=LIGHT).grid(row=0,column=0,padx=6,pady=5,sticky="w")
        self.payroll_employee_combo=ttk.Combobox(form,textvariable=self.payroll_employee,state="readonly",width=26); self.payroll_employee_combo.grid(row=0,column=1,padx=6,pady=5,sticky="w")
        self.payroll_employee_combo.bind("<<ComboboxSelected>>",lambda _event:self.payroll_employee_chosen())
        tk.Label(form,text="Period Date",bg=LIGHT).grid(row=0,column=2,padx=6,pady=5,sticky="w"); self.date_entry(form,self.payroll_period,14).grid(row=0,column=3,padx=6,pady=5,sticky="w")
        labels=(("salary","Salary"),("transport","Transport"),("overtime","Overtime"),("commission","Commission"),("retro_salary","Retroactive Salary"),("schooling","Schooling"),("bonus","Bonus"),("thirteenth_month","13th Month"),("director_remuneration","Director Remuneration (not taxable)"))
        for index,(key,label) in enumerate(labels):
            row=1+index//3; column=(index%3)*2
            tk.Label(form,text=label,bg=LIGHT).grid(row=row,column=column,padx=6,pady=4,sticky="w")
            tk.Entry(form,textvariable=self.payroll_vars[key],width=16).grid(row=row,column=column+1,padx=6,pady=4,sticky="w")
        tk.Label(form,text="Retro From",bg=LIGHT).grid(row=4,column=0,padx=6,pady=4,sticky="w"); self.date_entry(form,self.payroll_retro_from,14).grid(row=4,column=1,padx=6,pady=4,sticky="w")
        tk.Label(form,text="Retro To",bg=LIGHT).grid(row=4,column=2,padx=6,pady=4,sticky="w"); self.date_entry(form,self.payroll_retro_to,14).grid(row=4,column=3,padx=6,pady=4,sticky="w")
        self.payroll_transport_days=tk.StringVar()
        tk.Label(form,text="Transport Days",bg=LIGHT).grid(row=4,column=4,padx=6,pady=4,sticky="w"); days_entry=tk.Entry(form,textvariable=self.payroll_transport_days,width=6); days_entry.grid(row=4,column=5,padx=6,pady=4,sticky="w")
        # Typing the transport days fills Transport at once: days x the daily transport of the period (Tax & NSSF Settings).
        days_entry.bind("<KeyRelease>",lambda _event:self.payroll_transport_from_days(),add="+"); days_entry.bind("<FocusOut>",lambda _event:self.payroll_transport_from_days(),add="+")
        tk.Label(form,text="Family Allocation",bg=LIGHT).grid(row=4,column=6,padx=6,pady=4,sticky="w")
        family_entry=tk.Entry(form,textvariable=self.payroll_family_override,width=12); family_entry.grid(row=4,column=7,padx=6,pady=4,sticky="w")
        # The automatic family allocation appears here as soon as the employee / period is chosen; typing in it
        # makes it a manual amount for this payroll (Calculate / Save use it).
        self._family_manual=False
        family_entry.bind("<KeyRelease>",lambda event:setattr(self,"_family_manual",True) if len(event.keysym)==1 or event.keysym in ("BackSpace","Delete") else None,add="+")
        period_widgets=[w for w in form.grid_slaves(row=0,column=3)]
        for widget in period_widgets: widget.bind("<FocusOut>",lambda _event:self.payroll_family_auto(),add="+")
        self.payroll_breakdown=tk.Label(form,text="",bg=LIGHT,fg="#5f6b76",anchor="w",justify="left",wraplength=1060); self.payroll_breakdown.grid(row=6,column=0,columnspan=8,padx=6,sticky="w")
        self.payroll_notes=tk.Label(form,text="",bg=LIGHT,fg="#8B1E1E",anchor="w",justify="left",font=("Segoe UI",9,"bold"),wraplength=1060); self.payroll_notes.grid(row=7,column=0,columnspan=8,padx=6,sticky="w")
        self.payroll_result=tk.StringVar(value="Gross: 0 | Tax: 0 | Employee NSSF: 0 | Net: 0")
        tk.Label(form,textvariable=self.payroll_result,bg=LIGHT,fg=NAVY,font=("Segoe UI",10,"bold"),wraplength=1000,justify="left").grid(row=5,column=0,columnspan=8,padx=6,pady=6,sticky="w")
        buttons=tk.Frame(form,bg=LIGHT); buttons.grid(row=0,column=4,columnspan=4,sticky="w",padx=6)
        self.action_button(buttons,"Calculate",self.calculate_payroll).pack(side="left",padx=3)
        tk.Button(buttons,text="Save Payroll",command=self.save_payroll,bg=GOLD,fg=NAVY,border=0,padx=15,pady=7,font=("Segoe UI",9,"bold")).pack(side="left",padx=3)
        payroll_actions=tk.Frame(run,bg=LIGHT); payroll_actions.pack(fill="x",padx=10)
        self.action_button(payroll_actions,"Post Selected to Accounting",self.post_selected_payroll).pack(side="left",padx=4,pady=3)
        self.payroll_tree=self.table(run,[("number","Payroll No.",135),("period","Period",95),("employee","Employee",190),("currency","Currency",65),
            ("gross","Gross",105),("tax","Tax",95),("nssf","Employee NSSF",110),("net","Net Salary",110),("status","Status",75)])
        self.payroll_setting_vars={key:tk.StringVar() for key in ("date_from","date_to","single_allowance","spouse_allowance","child_allowance","employee_nssf_rate","medical_rate","end_service_rate","family_rate","employee_ceiling","medical_ceiling","family_ceiling","end_service_ceiling","salary_account","salary_payable_account","payroll_tax_account","nssf_payable_account",
            "max_children_deduction","transport_daily_exempt","default_transport_days","schooling_annual_exempt","schooling_max_children","tax_rounding","minimum_wage","family_allowance_spouse","family_allowance_child","family_allowance_cap","family_allowance_max_children")}
        setting_labels=(("date_from","Date From"),("date_to","Date To"),("single_allowance","Single Allowance"),("spouse_allowance","Spouse Allowance"),("child_allowance","Child Allowance"),("employee_nssf_rate","Employee NSSF Rate"),("medical_rate","Employer Medical Rate"),("end_service_rate","End Service Rate"),("family_rate","Family Rate"),("employee_ceiling","Employee NSSF Ceiling"),("medical_ceiling","Medical Ceiling"),("family_ceiling","Family Ceiling"),("end_service_ceiling","End Service Ceiling"),("salary_account","Salary Expense Account"),("salary_payable_account","Salary Payable Account"),("payroll_tax_account","Payroll Tax Account"),("nssf_payable_account","NSSF Payable Account"),
            ("max_children_deduction","Tax Deduction Children"),("transport_daily_exempt","Transport Exempt / Day"),("default_transport_days","Default Transport Days"),("schooling_annual_exempt","Schooling Exempt / Year"),("schooling_max_children","Schooling Children"),
            ("tax_rounding","Round Tax Up To"),("minimum_wage","Minimum Wage"),("family_allowance_spouse","Allowance Spouse"),("family_allowance_child","Allowance per Child"),("family_allowance_cap","Allowance Maximum"),("family_allowance_max_children","Allowance Children"))
        for index,(key,label) in enumerate(setting_labels):
            column=(index//10)*2; row=index%10
            tk.Label(settings_page,text=label,bg=LIGHT).grid(row=row,column=column,padx=(10,2),pady=3,sticky="w")
            tk.Entry(settings_page,textvariable=self.payroll_setting_vars[key],width=13).grid(row=row,column=column+1,padx=(2,10),pady=3,sticky="w")
        tk.Label(settings_page,text="Tax Brackets JSON (annual LBP): [[ceiling,rate], ... [null,rate]]   Rates as decimals: 3% = 0.03   Dates: DD-MM-YYYY",bg=LIGHT).grid(row=10,column=0,columnspan=4,padx=10,pady=4,sticky="w")
        self.payroll_brackets=tk.Text(settings_page,width=62,height=4); self.payroll_brackets.grid(row=11,column=0,columnspan=6,padx=10,pady=5,sticky="ew")
        self.action_button(settings_page,"Load Settings",self.load_payroll_settings).grid(row=12,column=0,padx=10,pady=10)
        self.action_button(settings_page,"Save Settings",self.save_payroll_settings).grid(row=12,column=1,padx=10,pady=10)
        tk.Button(settings_page,text="Load Lebanese Law 2024-2026",command=self.apply_lebanese_payroll_rules,bg=GOLD,fg=NAVY,border=0,padx=14,pady=7,font=("Segoe UI",9,"bold")).grid(row=12,column=2,columnspan=2,padx=10,pady=10)
        self.build_payroll_periods_panel(settings_page,13)
        mapping_frame=tk.LabelFrame(settings_page,text="Standard Posting Accounts",bg=LIGHT,padx=8,pady=6); mapping_frame.grid(row=14,column=0,columnspan=6,padx=10,pady=8,sticky="ew")
        self.payroll_employee_accounts={key:tk.StringVar() for key in ("salary","transport","overtime","commission","retro_salary","schooling","bonus","thirteenth_month","director_remuneration","family_allowance","tax","nssf","payable")}
        self.payroll_manager_accounts={key:tk.StringVar() for key in self.payroll_employee_accounts}
        tk.Label(mapping_frame,text="Component",bg=LIGHT,font=("Segoe UI",9,"bold")).grid(row=0,column=0,padx=5); tk.Label(mapping_frame,text="Employees",bg=LIGHT,font=("Segoe UI",9,"bold")).grid(row=0,column=1,padx=5); tk.Label(mapping_frame,text="Managers",bg=LIGHT,font=("Segoe UI",9,"bold")).grid(row=0,column=2,padx=5)
        labels={"salary":"Salary","transport":"Transportation","overtime":"Overtime","commission":"Commission","retro_salary":"Retro Salary","schooling":"Schooling","bonus":"Bonus","thirteenth_month":"13th Salary","director_remuneration":"Director Remuneration","family_allowance":"Family Allocation (empty = NSSF account)","tax":"Payroll Tax","nssf":"NSSF","payable":"Net Salary Payable"}
        for index,(key,label) in enumerate(labels.items(),1):
            tk.Label(mapping_frame,text=label,bg=LIGHT).grid(row=index,column=0,padx=5,pady=2,sticky="w")
            self.account_search_box(mapping_frame,self.payroll_employee_accounts[key],16).grid(row=index,column=1,padx=5,pady=2)
            self.account_search_box(mapping_frame,self.payroll_manager_accounts[key],16).grid(row=index,column=2,padx=5,pady=2)
        self.build_payroll_reports_page(reports_page)
        self.load_payroll()
        self.load_payroll_settings()

    def employee_dialog(self,employee=None):
        window=tk.Toplevel(self); window.title("Employee File"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        window.geometry(f"{min(940,self.winfo_screenwidth())}x{min(650,self.winfo_screenheight()-80)}")
        outer,form=self.scrollable_page(window); outer.pack(fill="both",expand=True)
        data=employee or {}; fields={key:tk.StringVar(value=str(data.get(key) or "")) for key in ("employee_number","full_name","national_id","mof_number","nssf_number","address","contact_number","nationality","father_name","mother_name","birth_date","birth_place","job_title","hire_date","leave_date","base_salary","salary_account","payable_account")}
        if not fields["employee_number"].get(): fields["employee_number"].set("1000")
        marital=tk.StringVar(value=data.get("marital_status","single")); spouse_works=tk.BooleanVar(value=bool(data.get("spouse_works",0))); children=tk.StringVar(value=str(data.get("children",0))); employee_group=tk.StringVar(value=data.get("employee_group","employee")); currency=tk.StringVar(value=data.get("currency","LBP")); active=tk.BooleanVar(value=bool(data.get("active",1)))
        rows=(("employee_number","Employee ID / 4-digit prefix"),("full_name","Full Name"),("national_id","National ID"),("mof_number","MOF Number"),("nssf_number","NSSF Number"),("address","Address"),("contact_number","Contact Number"),("nationality","Nationality"),("father_name","Father's Name"),("mother_name","Mother's Name"),("birth_date","Date of Birth"),("birth_place","Place of Birth"),("job_title","Job Title"),("hire_date","Hire Date"),("leave_date","Leave Date"),("base_salary","Base Salary"),("salary_account","Salary Expense Account"),("payable_account","Payable Account"))
        for index,(key,label) in enumerate(rows):
            column=0 if index<9 else 2; row=index if index<9 else index-9
            tk.Label(form,text=label,bg=LIGHT).grid(row=row,column=column,padx=10,pady=5,sticky="w")
            (self.date_entry(form,fields[key],28) if key in ("hire_date","leave_date","birth_date") else tk.Entry(form,textvariable=fields[key],width=28)).grid(row=row,column=column+1,padx=10,pady=5)
        tk.Label(form,text="Marital Status",bg=LIGHT).grid(row=9,column=0,padx=10,pady=5,sticky="w"); ttk.Combobox(form,textvariable=marital,values=["single","married"],state="readonly",width=25).grid(row=9,column=1)
        tk.Label(form,text="Children",bg=LIGHT).grid(row=10,column=0,padx=10,pady=5,sticky="w"); tk.Entry(form,textvariable=children,width=28).grid(row=10,column=1)
        tk.Label(form,text="Currency",bg=LIGHT).grid(row=9,column=2,padx=10,pady=5,sticky="w"); ttk.Combobox(form,textvariable=currency,values=self.currency_codes,state="readonly",width=25).grid(row=9,column=3)
        tk.Checkbutton(form,text="Spouse Works",variable=spouse_works,bg=LIGHT).grid(row=10,column=2,sticky="w")
        tk.Checkbutton(form,text="Active",variable=active,bg=LIGHT).grid(row=10,column=3,sticky="w")
        tk.Label(form,text="Payroll Group",bg=LIGHT).grid(row=11,column=0,padx=10,pady=5,sticky="w"); ttk.Combobox(form,textvariable=employee_group,values=["employee","manager"],state="readonly",width=25).grid(row=11,column=1)
        def save():
            payload={key:var.get().strip() for key,var in fields.items()}; payload.update({"id":data.get("id"),"marital_status":marital.get(),"spouse_works":spouse_works.get(),"children":children.get(),"employee_group":employee_group.get(),"currency":currency.get(),"active":active.get()})
            try: saved=self.client.save_employee(payload)
            except Exception as exc: return messagebox.showerror("Employee",str(exc),parent=window)
            window.destroy(); self.load_payroll(); messagebox.showinfo("Employee",f'Employee {saved["employee_number"]} saved successfully')
        self.action_button(window,"Save Employee",save).pack(pady=8)

    def edit_selected_employee(self):
        selected=self.employee_tree.selection()
        if not selected: return messagebox.showwarning("Employees","Select an employee first")
        employee=next((row for row in getattr(self,"employee_rows",[]) if str(row["id"])==str(selected[0])),None)
        if employee: self.employee_dialog(employee)

    def employee_r3_worksheet(self,format_name):
        selected=self.employee_tree.selection()
        if not selected: return messagebox.showwarning("R3 Registration","Select an employee first")
        employee=next((row for row in getattr(self,"employee_rows",[]) if str(row["id"])==str(selected[0])),None)
        if not employee: return messagebox.showwarning("R3 Registration","Refresh the employee list and select an employee")
        company=self.client.settings()
        employer=((("Employer / company",company.get("company_name")),("Employer address",company.get("company_address")),
                   ("Employer phone",company.get("company_phone")),("MOF / VAT number",company.get("company_mof")),
                   ("NSSF employer number",company.get("company_nssf"))))
        employer_rows=[[label,value if value not in (None,"") else "MISSING"] for label,value in employer]
        fields=(("Full name","full_name"),("Father's name","father_name"),("Mother's name","mother_name"),
                ("Nationality","nationality"),("Date of birth","birth_date"),("Place of birth","birth_place"),
                ("National ID","national_id"),("MOF personal number","mof_number"),("NSSF number","nssf_number"),
                ("Marital status","marital_status"),("Children","children"),("Address","address"),
                ("Phone","contact_number"),("Profession","job_title"),("Start date","hire_date"))
        rows=[[label,employee.get(key) if employee.get(key) not in (None,"") else "MISSING"] for label,key in fields]
        missing=[label for (label,key),row in zip(fields,rows) if row[1]=="MISSING"]
        missing+=[label for label,row in zip(("Employer / company","Employer address","Employer phone","MOF / VAT number","NSSF employer number"),employer_rows) if row[1]=="MISSING"]
        meta=[f'Employee ID: {employee["employee_number"]}',
              "Preparation worksheet only. Complete and submit the Ministry of Finance R3 / R3-1 form separately.",
              "Official form: https://eservices.finance.gov.lb/Resources/Namazej/DASS1/%D8%B13.pdf",
              "Check the official form for other details and supporting documents."]
        if missing: meta.append("Missing in the company or employee file: " + ", ".join(missing))
        self.output_sections("R3 Employee Registration Worksheet",meta,
            [{"heading":"Employer information","headers":["Field","Value"],"rows":employer_rows,"total_rows":[]},
             {"heading":"Employee information","headers":["Field","Value"],"rows":rows,"total_rows":[]}],
            f'R3_Worksheet_{employee["employee_number"]}',format_name)

    def employee_nssf_declaration(self,kind,format_name):
        titles={"hire":("NSSF Employment Declaration","NSSF Employment Declaration (Estekhdam Ajir) Worksheet | \u0625\u0639\u0644\u0627\u0645 \u0627\u0633\u062a\u062e\u062f\u0627\u0645 \u0623\u062c\u064a\u0631","NSSF-HIRE-NEW","hire_date","Start date"),
                "leave":("NSSF Termination Declaration","NSSF Termination Declaration (Tark Ajir) Worksheet | \u0625\u0639\u0644\u0627\u0645 \u062a\u0631\u0643 \u0623\u062c\u064a\u0631","NSSF-LEAVE","leave_date","Leaving date")}
        warn,title,form,date_key,date_label=titles[kind]
        selected=self.employee_tree.selection()
        if not selected: return messagebox.showwarning(warn,"Select an employee first")
        employee=next((row for row in getattr(self,"employee_rows",[]) if str(row["id"])==str(selected[0])),None)
        if not employee: return messagebox.showwarning(warn,"Refresh the employee list and select an employee")
        company=self.client.settings()
        employer=(("Employer / company",company.get("company_name")),("Employer address",company.get("company_address")),
                  ("Employer phone",company.get("company_phone")),("NSSF employer number",company.get("company_nssf")),
                  ("MOF / VAT number",company.get("company_mof")))
        employer_rows=[[label,value if value not in (None,"") else "MISSING"] for label,value in employer]
        fields=(("Full name","full_name"),("Father's name","father_name"),("Mother's name","mother_name"),
                ("Nationality","nationality"),("Date of birth","birth_date"),("Place of birth","birth_place"),
                ("National ID","national_id"),("NSSF number","nssf_number"),("Marital status","marital_status"),
                ("Children","children"),("Address","address"),("Phone","contact_number"),("Profession","job_title"),
                (date_label,date_key),("Base salary","base_salary"))
        rows=[[label,employee.get(key) if employee.get(key) not in (None,"") else "MISSING"] for label,key in fields]
        missing=[label for (label,key),row in zip(fields,rows) if row[1]=="MISSING"]
        missing+=[label for label,row in zip(("Employer / company","Employer address","Employer phone","NSSF employer number","MOF / VAT number"),employer_rows) if row[1]=="MISSING"]
        meta=[f'Employee ID: {employee["employee_number"]}',
              "Preparation worksheet only. Complete and submit the official CNSS form separately.",
              "Download the official blank form from the NSSF employee forms buttons."]
        if kind=="leave" and (employee.get("leave_date") in (None,"")): meta.append("No leaving date on file - set it in the employee file before you file the termination.")
        if missing: meta.append("Missing in the company or employee file: " + ", ".join(missing))
        self.output_sections(title,meta,
            [{"heading":"Employer information","headers":["Field","Value"],"rows":employer_rows,"total_rows":[]},
             {"heading":"Employee information","headers":["Field","Value"],"rows":rows,"total_rows":[]}],
            f'NSSF_{kind}_Worksheet_{employee["employee_number"]}',format_name)

    def download_payroll_form(self,form):
        official={"R3":"https://eservices.finance.gov.lb/Resources/Namazej/DASS1/%D8%B13.pdf",
                  "R3-1":"https://www.finance.gov.lb/en-us/Taxation/Na/DASS1/%D8%B13-1.pdf",
                  "NSSF-DUE":"https://drive.google.com/uc?export=download&id=1ZwZR6kFj19KPbtALttm8U6Ji3ICJUjGB",
                  "NSSF-SETTLEMENT":"https://drive.google.com/uc?export=download&id=14eHUtHDblW9mE_4Vs82PmRrmbMGGSEKg",
                  "NSSF-ANNUAL":"https://drive.google.com/uc?export=download&id=1TNwLlioahMJLaiX3ma6PPYqrgbHm07f_",
                  "NSSF-HIRE-NEW":"https://drive.google.com/uc?export=download&id=1FHWgIuJm38oLcypxT6lMXlTlY9eCXDpe",
                  "NSSF-HIRE-EXISTING":"https://drive.google.com/uc?export=download&id=1jK1Nv4RgzslncCsV-5gc7e2rHYZQThyq",
                  "NSSF-LEAVE":"https://drive.google.com/uc?export=download&id=1_stgCRJwJjdqr2kFLy07ZCwiXDkMdZIy"}
        if form not in official: raise ValueError("Unknown payroll form")
        agency="CNSS" if form.startswith("NSSF") else "MOF"
        target=filedialog.asksaveasfilename(title=f"Save official {form} form",defaultextension=".pdf",
            initialfile=f"Lebanon_{agency}_{form}.pdf",filetypes=[("PDF files","*.pdf")])
        if not target: return
        try:
            with urlopen(official[form],timeout=20) as response: content=response.read()
            if not content.startswith(b"%PDF"): raise ValueError(f"The {agency} form link did not return a PDF")
            Path(target).write_bytes(content)
        except Exception as exc: return messagebox.showerror(f"Official {form}",f"Could not download the form: {exc}")
        note=("\nCheck the preprinted rates against the period's NSSF settings before using this blank form."
              if form in ("NSSF-DUE","NSSF-SETTLEMENT","NSSF-ANNUAL") else "")
        messagebox.showinfo(f"Official {form}",f"Official blank form saved to {target}{note}")

    def load_payroll(self):
        if not hasattr(self,"employee_tree"): return
        try: self.employee_rows=self.client.employees(); payroll=self.client.payroll()
        except Exception as exc: return messagebox.showerror("Payroll",str(exc))
        self.employee_tree.delete(*self.employee_tree.get_children())
        for row in self.employee_rows: self.employee_tree.insert("","end",iid=str(row["id"]),values=(row["employee_number"],row["full_name"],row["job_title"],safe_display_date(row.get("hire_date")),safe_display_date(row.get("leave_date")),row.get("branch_name") or "",row["currency"],row["base_salary"],row["nssf_number"],"Yes" if row["active"] else "No"))
        self.payroll_employee_map={f'{row["employee_number"]} - {row["full_name"]}':row for row in self.employee_rows if row["active"]}
        self.payroll_employee_combo["values"]=list(self.payroll_employee_map)
        if not self.payroll_employee.get() and self.payroll_employee_map: self.payroll_employee.set(next(iter(self.payroll_employee_map))); self.payroll_employee_chosen()
        self.payroll_tree.delete(*self.payroll_tree.get_children())
        for row in payroll: self.payroll_tree.insert("","end",iid=str(row["id"]),values=(row["payroll_number"],safe_display_date(row["period_date"]),row["full_name"],row["currency"],f'{float(row["gross_salary"]):,.2f}',f'{float(row["income_tax"]):,.2f}',f'{float(row["employee_nssf"]):,.2f}',f'{float(row["net_salary"]):,.2f}',row["status"]))

    def payroll_employee_chosen(self):
        employee=getattr(self,"payroll_employee_map",{}).get(self.payroll_employee.get())
        if employee: self.payroll_vars["salary"].set(str(employee.get("base_salary") or "0"))
        self._family_manual=False; self.payroll_family_auto()

    def payroll_family_auto(self):
        """Show the automatic family allocation of the chosen employee and period (unless it was typed by hand)."""
        if getattr(self,"_family_manual",False) or not hasattr(self,"payroll_family_override"): return
        try:
            payload=self.payroll_payload(); payload.pop("family_allowance_override",None)
            result=self.client.calculate_payroll(payload)
        except Exception: return
        value=float(result.get("family_allowance") or 0)
        self.payroll_family_override.set(f"{value:.0f}" if result.get("currency")=="LBP" else f"{value:.2f}")

    def payroll_transport_from_days(self):
        """Transport = transport days x daily transport of the payroll period, in the employee's currency."""
        text=self.payroll_transport_days.get().strip()
        if not text: return
        try: days=int(text)
        except ValueError: return
        if days<0 or days>31: return
        employee=getattr(self,"payroll_employee_map",{}).get(self.payroll_employee.get())
        currency=(employee or {}).get("currency") or "LBP"
        try: period=formatted_user_date(self.payroll_period.get())
        except ValueError: period=None
        key=(period,currency); cache=self.__dict__.setdefault("_transport_rate_cache",{})
        try:
            if key not in cache:
                daily=Decimal(str(self.client.payroll_settings(period).get("transport_daily_exempt") or 0))
                rate=Decimal("1") if currency=="LBP" else Decimal(str(self.client.suggested_rates(currency,period)["rate_lbp"]))
                cache[key]=(daily,rate)
            daily,rate=cache[key]
        except Exception: return
        if daily<=0 or rate<=0: return
        amount=daily*days/rate
        self.payroll_vars["transport"].set(f"{amount:.0f}" if currency=="LBP" else f"{amount.quantize(Decimal('0.01'))}")

    def payroll_payload(self):
        employee=self.payroll_employee_map.get(self.payroll_employee.get())
        if not employee: raise ValueError("Select an employee")
        payload={"employee_id":employee["id"],"period_date":formatted_user_date(self.payroll_period.get())}
        payload.update({key:var.get().strip() or "0" for key,var in self.payroll_vars.items()})
        if self.payroll_transport_days.get().strip(): payload["transport_days"]=self.payroll_transport_days.get().strip()
        if getattr(self,"payroll_family_override",None) is not None and getattr(self,"_family_manual",False) and self.payroll_family_override.get().strip():
            payload["family_allowance_override"]=self.payroll_family_override.get().strip()
        if float(payload.get("retro_salary") or 0):
            if not self.payroll_retro_from.get().strip() or not self.payroll_retro_to.get().strip(): raise ValueError("Enter Retro From and Retro To dates")
            payload["retro_from"]=formatted_user_date(self.payroll_retro_from.get()); payload["retro_to"]=formatted_user_date(self.payroll_retro_to.get())
        return payload

    def calculate_payroll(self):
        try: result=self.client.calculate_payroll(self.payroll_payload())
        except Exception as exc: return messagebox.showerror("Payroll",str(exc))
        if not getattr(self,"_family_manual",False) and hasattr(self,"payroll_family_override"):
            value=float(result.get("family_allowance") or 0)
            self.payroll_family_override.set(f"{value:.0f}" if result.get("currency")=="LBP" else f"{value:.2f}")
        retro=f' (of which retro tax {result["retro_tax"]:,.2f})' if result.get("retro_tax") else ""
        rules=result.get("settings_period") or {}
        period=f' | Rules from {safe_display_date(rules["date_from"])}' if rules.get("date_from") else ""
        self.payroll_breakdown.config(text=f'Tax: regular {result.get("regular_tax",0):,.2f} + bonus/13th {result.get("one_off_tax",0):,.2f} + retro {result.get("retro_tax",0):,.2f}   |   Exempt: transport {result.get("exempt_transport",0):,.2f} ({result.get("transport_days","")} days), schooling {result.get("exempt_schooling",0):,.2f}   |   NSSF family allowance paid: {result.get("family_allowance",0):,.2f} {result["currency"]}')
        self.payroll_notes.config(text=("Check: "+"  |  ".join(result.get("compliance_notes") or [])) if result.get("compliance_notes") else "Compliant with the rules of this period")
        self.payroll_notes.config(fg="#8B1E1E" if result.get("compliance_notes") else NAVY)
        self.payroll_result.set(f'Gross: {result["gross_salary"]:,.2f} | Tax: {result["income_tax"]:,.2f} {result["currency"]} ({result["income_tax_lbp"]:,.0f} LBP){retro} | Employee NSSF: {result["employee_nssf"]:,.2f} | Employer NSSF: {result["employer_medical"]+result["employer_family"]+result["employer_end_service"]:,.2f} | Net: {result["net_salary"]:,.2f}{period}')

    def save_payroll(self):
        try: saved=self.client.save_payroll(self.payroll_payload())
        except Exception as exc: return messagebox.showerror("Payroll",str(exc))
        self.load_payroll(); messagebox.showinfo("Payroll",f'Payroll {saved["payroll_number"]} saved as draft')

    def post_selected_payroll(self):
        selected=self.payroll_tree.selection()
        if not selected: return messagebox.showwarning("Payroll","Select a payroll record first")
        if not messagebox.askyesno("Post Payroll","Post this payroll to the General Journal? Posted payroll cannot be edited."): return
        try: saved=self.client.post_payroll(int(selected[0]))
        except Exception as exc: return messagebox.showerror("Payroll",str(exc))
        self.load_payroll(); self.load_journal(); self.load_trial(); messagebox.showinfo("Payroll",f'Payroll {saved["payroll_number"]} posted successfully')

    def load_payroll_settings(self):
        self.__dict__.pop("_transport_rate_cache",None)  # settings may have changed: recalculate transport from days
        if not hasattr(self,"payroll_setting_vars"): return
        try: settings=self.client.payroll_settings(self.payroll_period.get().strip())
        except Exception as exc: return messagebox.showerror("Payroll Settings",str(exc))
        for key,var in self.payroll_setting_vars.items():
            value=settings.get(key,"") if settings.get(key) is not None else ""
            var.set(safe_display_date(value) if key in ("date_from","date_to") and value else value)
        for key,var in self.payroll_employee_accounts.items(): var.set(settings.get("employee_account_map",{}).get(key,""))
        for key,var in self.payroll_manager_accounts.items(): var.set(settings.get("manager_account_map",{}).get(key,""))
        self.payroll_brackets.delete("1.0","end"); self.payroll_brackets.insert("1.0",json.dumps(settings.get("tax_brackets",[])))

    def apply_lebanese_payroll_rules(self):
        if not messagebox.askyesno("Lebanese Payroll Rules","Replace ALL Tax & NSSF periods with the official Lebanese rules from 01-01-2024?\n\n"
            "- Budget Law 2024 brackets and family deductions\n- Transport exempt 450,000 LBP/day, schooling 6M/year\n- Tax rounded up to 10,000 LBP from 25-11-2024\n"
            "- NSSF ceilings: 45M -> 90M (04-2024) -> 120M (08-2025); family 12M -> 18M (07-2025) -> 28M (05-2026)\n- NSSF family allowances from 05-2026 (Decree 2923)\n\n"
            "Employer sickness & maternity is set to 8% (check with your accountant). Posting accounts are kept. Already saved payroll is NOT recalculated."): return
        try: self.client.apply_lebanese_payroll_rules()
        except Exception as exc: return messagebox.showerror("Lebanese Payroll Rules",str(exc))
        self.load_payroll_periods(); self.load_payroll_settings(); messagebox.showinfo("Lebanese Payroll Rules","Lebanese payroll rules loaded. Recalculate draft payroll to apply them.")

    def save_payroll_settings(self):
        payload={key:var.get().strip() for key,var in self.payroll_setting_vars.items()}
        for key in ("date_from","date_to"):
            if payload.get(key):
                try: payload[key]=parse_user_date(payload[key]).strftime("%Y-%m-%d")
                except ValueError: return messagebox.showerror("Payroll Settings",f"{key.replace('_',' ').title()} must use DD-MM-YYYY")
        payload["employee_account_map"]={key:var.get().split(" - ",1)[0].strip() for key,var in self.payroll_employee_accounts.items()}
        payload["manager_account_map"]={key:var.get().split(" - ",1)[0].strip() for key,var in self.payroll_manager_accounts.items()}
        try: payload["tax_brackets"]=json.loads(self.payroll_brackets.get("1.0","end").strip()); self.client.save_payroll_settings(payload)
        except Exception as exc: return messagebox.showerror("Payroll Settings",str(exc))
        self.load_payroll_periods()
        messagebox.showinfo("Payroll Settings","Tax and NSSF settings saved. The previous period now ends the day before the new Date From.")

    def build_journal(self):
        filters=tk.Frame(self.journal_tab,bg=LIGHT); filters.pack(fill="x",padx=10,pady=(10,0))
        tk.Label(filters,text="View Year:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        years=[str(item["year"]) for item in getattr(self,"current_company",{}).get("years",[])]
        if not self.journal_view_year.get(): self.journal_view_year.set(str(getattr(self,"current_fiscal_year",datetime.now().year)))
        ttk.Combobox(filters,textvariable=self.journal_view_year,values=years,state="readonly",width=7).pack(side="left",padx=(4,10))
        tk.Label(filters,text="From Date:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        self.date_entry(filters,self.journal_from_date,13).pack(side="left",padx=(5,14))
        tk.Label(filters,text="To Date:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        self.date_entry(filters,self.journal_to_date,13).pack(side="left",padx=(5,10))
        tk.Label(filters,text="DD-MM-YYYY",bg=LIGHT,fg="#5f6b76").pack(side="left",padx=(0,10))
        tk.Label(filters,text="Sort By:",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        ttk.Combobox(filters,textvariable=self.journal_sort_by,state="readonly",width=16,
            values=["Date","Voucher Number","Account Number","Account Name","Customer / Supplier","Debit","Credit","Currency"]).pack(side="left",padx=4)
        ttk.Combobox(filters,textvariable=self.journal_sort_order,state="readonly",width=10,
            values=["Ascending","Descending"]).pack(side="left",padx=(0,8))
        ttk.Combobox(filters,textvariable=self.journal_section,state="readonly",width=17,
            values=["All Sections","Payroll","Expenses","Purchases","Sales","Journal Vouchers","Opening / Closing"]).pack(side="left",padx=(0,8))
        tk.Button(filters,text="Apply",command=self.load_journal,bg=GOLD,fg=NAVY,
                  font=("Segoe UI",9,"bold"),border=0,padx=16,pady=6).pack(side="left")
        finder=tk.Frame(self.journal_tab,bg=LIGHT); finder.pack(fill="x",padx=10,pady=(6,0)); self.journal_find=tk.StringVar(); self.journal_find_details=tk.StringVar()
        tk.Label(finder,text="Find voucher No.",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        number_entry=tk.Entry(finder,textvariable=self.journal_find,width=16); number_entry.pack(side="left",padx=(4,10)); number_entry.bind("<Return>",lambda _event:self.load_journal())
        tk.Label(finder,text="Find in details",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left")
        details_entry=tk.Entry(finder,textvariable=self.journal_find_details,width=28); details_entry.pack(side="left",padx=(4,10)); details_entry.bind("<Return>",lambda _event:self.load_journal())
        tk.Button(finder,text="Find",command=self.load_journal,bg=GOLD,fg=NAVY,border=0,padx=12,pady=5).pack(side="left",padx=2)
        tk.Button(finder,text="Clear",command=lambda:(self.journal_find.set(""),self.journal_find_details.set(""),self.load_journal()),bg=NAVY,fg="white",border=0,padx=10,pady=5).pack(side="left",padx=2)
        for text,mode in (("Print Preview","preview"),("PDF","pdf"),("Print","print")):
            tk.Button(finder,text=text,command=lambda m=mode:self.journal_document(m),bg=NAVY,fg="white",border=0,padx=10,pady=5).pack(side="right",padx=2)
        actions=tk.Frame(self.journal_tab,bg=LIGHT); actions.pack(anchor="w",padx=10,pady=(6,4))
        self.action_button(actions,"Refresh",self.load_journal).pack(side="left",padx=4)
        self.action_button(actions,"Export Excel",lambda:self.journal_report("xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.journal_report("pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.journal_report("print")).pack(side="left",padx=4)
        tk.Button(actions,text="Delete Selected Voucher",command=self.delete_selected_journal_voucher,bg="#6B1010",fg="white",border=0,padx=14,pady=7).pack(side="left",padx=4)
        self.journal_totals=tk.Label(actions,text="Debit: 0.00   Credit: 0.00",bg=LIGHT,font=("Segoe UI",10,"bold"))
        self.journal_totals.pack(side="left",padx=15)
        self.journal_tree=self.table(self.journal_tab,[
            ("entry","Entry No.",95),("date","Date",95),("description","Description",190),
            ("source","Source",75),("reference","Reference",75),("currency","Currency",70),
            ("account","Account",85),("account_name","Account Name",190),("party","Customer / Supplier",165),
            ("debit","Debit",105),("credit","Credit",105),("balance","Balance",110)])
        self.load_journal()

    def journal_date_range(self):
        values=[]
        for label,raw in (("From Date",self.journal_from_date.get()),("To Date",self.journal_to_date.get())):
            value=raw.strip()
            if not value:
                values.append(None); continue
            try: values.append(parse_user_date(value).strftime("%Y-%m-%d"))
            except ValueError:
                messagebox.showwarning("General Journal",f"{label} must use DD-MM-YYYY"); return None
        if values[0] and values[1] and values[0]>values[1]:
            messagebox.showwarning("General Journal","From Date cannot be after To Date"); return None
        return values

    def load_journal(self):
        if not hasattr(self,"journal_tree"): return
        dates=self.journal_date_range()
        if dates is None: return
        currency=None if self.view_currency.get()=="All Currencies" else self.view_currency.get()
        view_year=int(self.journal_view_year.get() or self.current_fiscal_year)
        try: rows=self.client.journal(dates[0],dates[1],currency) if view_year==int(self.current_fiscal_year) else self.client.fiscal_year_journal(view_year,dates[0],dates[1],currency)
        except Exception as exc: return messagebox.showerror("General Journal",str(exc))
        if self.journal_section.get()!="All Sections": rows=[row for row in rows if row.get("journal_category")==self.journal_section.get()]
        number=self.journal_find.get().strip() if hasattr(self,"journal_find") else ""
        if number:
            if number.isdigit(): rows=[row for row in rows if str(row.get("entry_number") or "").rsplit("-",1)[-1].lstrip("0")==number.lstrip("0") or number in str(row.get("entry_number") or "")]
            else: rows=[row for row in rows if number.casefold() in str(row.get("entry_number") or "").casefold()]
        details=self.journal_find_details.get().strip() if hasattr(self,"journal_find_details") else ""
        if details: rows=[row for row in rows if row_matches_search((row.get("description"),row.get("line_description"),row.get("party_name"),row.get("reference"),row.get("account_name")),details)]
        sort_name=self.journal_sort_by.get()
        def journal_key(row):
            if sort_name=="Date": return sortable_date(row.get("entry_date"))
            if sort_name=="Voucher Number": return natural_sort_value(row.get("entry_number"))
            if sort_name=="Account Number": return natural_sort_value(row.get("account_code"))
            if sort_name=="Account Name": return str(row.get("account_name") or "").casefold()
            if sort_name=="Customer / Supplier": return str(row.get("party_name") or "").casefold()
            if sort_name=="Debit": return float(row.get("debit") or 0)
            if sort_name=="Credit": return float(row.get("credit") or 0)
            return str(row.get("currency") or "").casefold()
        rows.sort(key=journal_key,reverse=self.journal_sort_order.get()=="Descending")
        self.journal_rows=rows; self.journal_tree.delete(*self.journal_tree.get_children())
        for row in rows:
            self.journal_tree.insert("","end",values=(row["entry_number"],row["entry_date"],row["description"],
                "DOE" if row.get("voucher_type")=="07" else row["source_type"],row["source_id"],row["currency"],row["account_code"],row["account_name"],
                row["party_name"],f'{row["debit"]:,.2f}',f'{row["credit"]:,.2f}',f'{row["balance"]:,.2f}'))
        debit=sum(float(row["debit"] or 0) for row in rows); credit=sum(float(row["credit"] or 0) for row in rows)
        state="Balanced" if abs(debit-credit)<0.005 else "UNBALANCED"
        mode="Current Year" if view_year==int(self.current_fiscal_year) else f"{view_year} Read-Only"
        self.journal_totals.config(text=f"{mode}   Debit: {debit:,.2f}   Credit: {credit:,.2f}   {state}")

    def delete_selected_journal_voucher(self):
        if int(self.journal_view_year.get() or self.current_fiscal_year)!=int(self.current_fiscal_year): return messagebox.showwarning("General Journal","Previous-year transactions are read-only")
        selected=self.journal_tree.selection()
        if not selected: return messagebox.showwarning("General Journal","Select a Journal Voucher line first")
        entry_number=str(self.journal_tree.item(selected[0],"values")[0])
        row=next((item for item in getattr(self,"journal_rows",[]) if str(item["entry_number"])==entry_number),None)
        if not row: return messagebox.showwarning("General Journal","Selected entry was not found")
        if row.get("source_type")=="year_close":
            year=int(row.get("source_id") or str(row["entry_number"]).split("-")[1])
            if not messagebox.askyesno("Reopen Fiscal Year",f"This is a closing voucher. Reopen fiscal year {year} and remove all its closing entries?"): return
            try: self.client.reopen_fiscal_year(year)
            except Exception as exc: return messagebox.showerror("Reopen Fiscal Year",str(exc))
            self.load_journal(); return messagebox.showinfo("Fiscal Year",f"Fiscal year {year} reopened successfully")
        if row.get("source_type")=="opening":
            if not messagebox.askyesno("Delete Opening Voucher",f'Delete opening voucher {entry_number}? You can recreate it with Refresh Next-Year Opening.'): return
            try: self.client.delete_opening_voucher(row["entry_id"])
            except Exception as exc: return messagebox.showerror("Delete Opening Voucher",str(exc))
            self.load_journal(); self.load_trial(); return messagebox.showinfo("Opening Voucher","Opening voucher deleted")
        if row.get("source_type")!="journal_voucher":
            return messagebox.showwarning("General Journal","This system entry must be cancelled or reversed from its original module")
        if not messagebox.askyesno("Delete Journal Voucher",f"Delete {entry_number} and all its debit/credit lines?\nThis action is recorded in the audit log."): return
        try: self.client.delete_journal_voucher(row["entry_id"])
        except Exception as exc: return messagebox.showerror("Delete Journal Voucher",str(exc))
        self.load_journal(); self.load_invoices(); self.load_dashboard(); self.load_trial(); messagebox.showinfo("General Journal","Journal Voucher deleted")

    def journal_report(self,format_name):
        rows=getattr(self,"journal_rows",[])
        if not rows: return messagebox.showwarning("General Journal","No journal data to export")
        title="Saber Accounting - General Journal"
        headers=["Entry No.","Date","Description","Source","Reference","Currency","Account","Account Name","Customer / Supplier","Debit","Credit","Balance"]
        values=[[r["entry_number"],r["entry_date"],r["description"],r["source_type"],r["source_id"],r["currency"],
                 r["account_code"],r["account_name"],r["party_name"],r["debit"],r["credit"],r["balance"]] for r in rows]
        values.append(["","","","","","","","","TOTAL",sum(float(r["debit"] or 0) for r in rows),sum(float(r["credit"] or 0) for r in rows),""])
        try:
            if format_name=="print": print_rows(title,headers,values); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"
            path=filedialog.asksaveasfilename(defaultextension=extension,filetypes=[("Excel workbook","*.xlsx")] if format_name=="xlsx" else [("PDF document","*.pdf")],initialfile="Saber_Accounting_General_Journal"+extension)
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,values)
            messagebox.showinfo("General Journal",f"Saved successfully:\n{path}")
        except Exception as exc: messagebox.showerror("General Journal",str(exc))

    def build_profit_loss(self):
        year=getattr(self,"current_fiscal_year",datetime.now().year)
        self.pnl_from_date.set(f"01-01-{year}"); self.pnl_to_date.set(f"31-12-{year}"); self.close_year.set(str(year))
        controls=tk.Frame(self.pnl_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=(10,4))
        tk.Label(controls,text=f"Fiscal Year {year}",bg=NAVY,fg="white",font=("Segoe UI",10,"bold"),padx=10,pady=4).pack(side="left",padx=(0,10))
        tk.Label(controls,text="From:",bg=LIGHT).pack(side="left")
        self.date_entry(controls,self.pnl_from_date,11).pack(side="left",padx=(4,10))
        tk.Label(controls,text="To:",bg=LIGHT).pack(side="left")
        self.date_entry(controls,self.pnl_to_date,11).pack(side="left",padx=(4,10))
        tk.Button(controls,text="Apply",command=self.load_profit_loss,bg=GOLD,fg=NAVY,border=0,padx=15,pady=6).pack(side="left")
        self.fiscal_status=tk.Label(controls,text="",bg=LIGHT,font=("Segoe UI",9,"bold")); self.fiscal_status.pack(side="left",padx=12)
        closing=tk.LabelFrame(self.pnl_tab,text=f"Year-end closing {year}",bg=LIGHT,padx=8,pady=5); closing.pack(fill="x",padx=10,pady=4)
        self.action_button(closing,"Preview Closing 6&7",self.preview_closing).pack(side="left",padx=(0,4))
        tk.Button(closing,text=f"Close {year} & Open {year+1}",command=self.close_fiscal_year,bg="#8B1E1E",fg="white",border=0,padx=14,pady=7,font=("Segoe UI",9,"bold")).pack(side="left",padx=4)
        tk.Button(closing,text="Delete Closing & Reopen Year",command=self.reopen_fiscal_year,bg=NAVY,fg="white",border=0,padx=12,pady=7).pack(side="left",padx=4)
        tk.Button(closing,text=f"Refresh Opening of {year+1}",command=self.refresh_next_year_opening,bg=NAVY,fg="white",border=0,padx=12,pady=7).pack(side="left",padx=4)
        if (self.current_user or {}).get("role")=="admin":
            tk.Button(closing,text=f"Delete Year {year}",command=self.delete_fiscal_year,bg="#5a0f0f",fg="white",border=0,padx=10,pady=7).pack(side="left",padx=4)
        tk.Label(closing,text="1 Journal Voucher per currency; result to 121 / 125",bg=LIGHT,fg="#5f6b76",wraplength=190,justify="left").pack(side="left",padx=6)
        actions=tk.Frame(self.pnl_tab,bg=LIGHT); actions.pack(side="bottom",pady=(0,8))
        self.pnl_tree=self.table(self.pnl_tab,[("currency","Currency",85),("type","Type",90),("account","Account",100),
            ("name","Account Name",300),("debit","Debit",130),("credit","Credit",130),("amount","P&L Amount",140)])
        self.action_button(actions,"Export Excel",lambda:self.profit_loss_report("xlsx")).pack(side="left",padx=4)
        self.action_button(actions,"Export PDF",lambda:self.profit_loss_report("pdf")).pack(side="left",padx=4)
        self.action_button(actions,"Print",lambda:self.profit_loss_report("print")).pack(side="left",padx=4)
        self.pnl_totals=tk.Label(actions,text="",bg=LIGHT,font=("Segoe UI",10,"bold")); self.pnl_totals.pack(side="left",padx=15)
        self.load_profit_loss()

    def refresh_fiscal_status(self):
        if not hasattr(self,"fiscal_status"): return
        year=getattr(self,"current_fiscal_year",None)
        record=next((y for y in (getattr(self,"current_company",{}) or {}).get("years",[]) if int(y["year"])==int(year or 0)),{})
        closed=record.get("status")=="closed"
        self.fiscal_status.config(text="CLOSED (read-only) - the P&L is shown before the closing voucher" if closed else "Open",fg="#8B1E1E" if closed else NAVY)

    def delete_fiscal_year(self):
        from tkinter import simpledialog
        year=int(getattr(self,"current_fiscal_year",0))
        answer=simpledialog.askstring("Delete Fiscal Year",f"This deletes ALL the data of {year} for {self.current_company['name']}\n(a backup copy of the file is kept),\n"
            f"and reopens {year-1} so you can close it again.\n\nType DELETE {year} to confirm:",parent=self)
        if (answer or "").strip().upper()!=f"DELETE {year}": return messagebox.showinfo("Delete Fiscal Year","Nothing was deleted")
        try: result=self.client.delete_fiscal_year(year)
        except Exception as exc: return messagebox.showerror("Delete Fiscal Year",str(exc))
        self.current_company=result["company"]
        messagebox.showinfo("Delete Fiscal Year",f"{year} deleted. Backup: {result['backup']}\n{result['reopened_year']} is open again (closing removed).\n\nOpen {result['reopened_year']} and close it again to make a new opening.")
        self.company_selection_screen()

    def preview_closing(self):
        year=int(self.close_year.get())
        try: data=self.client.closing_preview(year)
        except Exception as exc: return messagebox.showerror("Closing 6&7",str(exc))
        if not data: return messagebox.showinfo("Closing 6&7",f"There are no expense or revenue balances to close in {year}")
        sections=[]
        for currency,info in data.items():
            rows=[[code,name,round(amount,2) if amount>0 else 0,round(-amount,2) if amount<0 else 0,round(abs(lbp),0)] for code,amount,lbp,_usd,name in info["lines"]]
            rows.append(["","TOTAL",round(sum(r[2] for r in rows),2),round(sum(r[3] for r in rows),2),""])
            sections.append({"heading":f"CLOSING 6&7 - {year} ({currency})   Net result: {info['net_result']:,.2f} {'profit' if info['net_result']>=0 else 'loss'}",
                "headers":["Account","Account Name",f"Debit ({currency})",f"Credit ({currency})","LBP"],"rows":rows,"total_rows":[len(rows)-1]})
        window=tk.Toplevel(self); window.title(f"Preview closing {year}"); window.geometry("900x480"); window.configure(bg=LIGHT); window.transient(self)
        viewer=self.report_viewer(window); self.show_sections(viewer,sections)
        self.action_button(window,"Close",window.destroy).pack(pady=6)

    def profit_loss_range(self):
        values=[]
        for label,raw in (("From Date",self.pnl_from_date.get()),("To Date",self.pnl_to_date.get())):
            try: values.append(parse_user_date(raw).strftime("%Y-%m-%d"))
            except ValueError: messagebox.showwarning("Profit & Loss",f"{label} must use DD-MM-YYYY"); return None
        if values[0]>values[1]: messagebox.showwarning("Profit & Loss","From Date cannot be after To Date"); return None
        year=str(getattr(self,"current_fiscal_year",values[0][:4]))
        if values[0][:4]!=year or values[1][:4]!=year:
            messagebox.showwarning("Profit & Loss",f"The dates must be inside the selected fiscal year {year}. Use 'Switch Company / Year' to see another year.")
            self.pnl_from_date.set(f"01-01-{year}"); self.pnl_to_date.set(f"31-12-{year}"); return [f"{year}-01-01",f"{year}-12-31"]
        return values

    def load_profit_loss(self):
        if not hasattr(self,"pnl_tree"): return
        dates=self.profit_loss_range()
        if dates is None: return
        currency=None if self.view_currency.get()=="All Currencies" else self.view_currency.get()
        try: rows=self.client.profit_loss(dates[0],dates[1],currency)
        except Exception as exc: return messagebox.showerror("Profit & Loss",str(exc))
        self.pnl_rows=rows; self.pnl_tree.delete(*self.pnl_tree.get_children())
        for row in rows: self.pnl_tree.insert("","end",values=(row["currency"],row["type"],row["code"],row["name_en"],
            f'{row["debit"]:,.2f}',f'{row["credit"]:,.2f}',f'{row["amount"]:,.2f}'))
        totals={}
        for row in rows:
            totals.setdefault(row["currency"],0)
            totals[row["currency"]]+=row["amount"] if row["type"]=="income" else -row["amount"]
        self.pnl_totals.config(text="   ".join(f"{code} Net P&L: {amount:,.2f}" for code,amount in totals.items()) or "No activity")
        self.refresh_fiscal_status()

    def profit_loss_report(self,format_name):
        rows=getattr(self,"pnl_rows",[])
        if not rows: return messagebox.showwarning("Profit & Loss","No data to export")
        title=f"Saber Accounting - Profit & Loss ({self.pnl_from_date.get()} to {self.pnl_to_date.get()})"
        headers=["Currency","Type","Account","Account Name","Debit","Credit","P&L Amount"]
        values=[[r["currency"],r["type"],r["code"],r["name_en"],r["debit"],r["credit"],r["amount"]] for r in rows]
        try:
            if format_name=="print": print_rows(title,headers,values); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"
            path=filedialog.asksaveasfilename(defaultextension=extension,initialfile="Profit_and_Loss"+extension,
                filetypes=[("Excel workbook","*.xlsx")] if format_name=="xlsx" else [("PDF document","*.pdf")])
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,values)
            messagebox.showinfo("Profit & Loss",f"Saved successfully:\n{path}")
        except Exception as exc: messagebox.showerror("Profit & Loss",str(exc))

    def close_fiscal_year(self):
        year=int(getattr(self,"current_fiscal_year",self.close_year.get()))
        warning=(f"Close fiscal year {year}?\n\n- Any earlier closing of {year} is deleted first.\n- A 'CLOSING 6&7' Journal Voucher is made for each currency (result to 121 / 125).\n"
                 f"- {year} becomes read-only and {year+1} is opened with the balance-sheet balances.\n\nYou can undo this with 'Delete Closing & Reopen Year'.")
        if not messagebox.askyesno("Close Fiscal Year",warning): return
        try: result=self.client.close_fiscal_year(year)
        except Exception as exc: return messagebox.showerror("Close Fiscal Year",str(exc))
        self.client.select_company_year(self.current_company["id"],year+1)
        self.current_company=result.get("company",self.current_company); self.current_fiscal_year=year+1
        self.pnl_from_date.set(f"01-01-{year+1}"); self.pnl_to_date.set(f"31-12-{year+1}"); self.close_year.set(str(year+1))
        vouchers=", ".join(result.get("opening_vouchers",[])) or "No opening balance required"
        closing_vouchers=", ".join(result.get("closing_vouchers",[])) or "no P&L balances"
        summary=" / ".join(f"{code}: {amount:,.2f}" for code,amount in result.get("net_results",{}).items()) or "No P&L activity"
        self.main_screen()
        messagebox.showinfo("Fiscal Year",f"Year {year} closed.\nClosing 6&7 vouchers: {closing_vouchers}\nYear {year+1} opened for {self.current_company['name']}.\nOpening vouchers: {vouchers}\nNet results: {summary}")

    def reopen_fiscal_year(self):
        year=int(getattr(self,"current_fiscal_year",self.close_year.get()))
        if not messagebox.askyesno("Delete Closing & Reopen",f"Delete ALL closing entries of {year} and open it again?\n\nThe opening vouchers of {year+1} are removed too, until you close {year} again."): return
        try: result=self.client.reopen_fiscal_year(year)
        except Exception as exc: return messagebox.showerror("Reopen Fiscal Year",str(exc))
        self.current_company=result.get("company",self.current_company); self.current_fiscal_year=year
        self.client.select_company_year(self.current_company["id"],year); self.main_screen()
        messagebox.showinfo("Fiscal Year",f"Fiscal year {year} is open again.\nRemoved closing entries: {result.get('removed_closing_entries',0)}\nRemoved old opening entries: {result.get('removed_opening_entries',0)}")

    def refresh_next_year_opening(self):
        year=int(getattr(self,"current_fiscal_year",self.close_year.get()))
        if not messagebox.askyesno("Refresh Opening",f"Replace the opening vouchers in {year+1} using the latest balances from {year}?"): return
        try: result=self.client.refresh_opening(year)
        except Exception as exc: return messagebox.showerror("Refresh Opening",str(exc))
        status="Provisional because the source year is still open" if result.get("provisional") else "Final from a closed source year"
        messagebox.showinfo("Refresh Opening",f'Opening {year+1} refreshed successfully.\nVouchers: {", ".join(result.get("opening_vouchers",[])) or "No balances"}\n{status}')

    def build_financial_reports(self):
        controls=tk.Frame(self.reports_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=10)
        tk.Label(controls,text="From:",bg=LIGHT).pack(side="left"); self.date_entry(controls,self.report_from_date,13).pack(side="left",padx=(4,10))
        tk.Label(controls,text="To:",bg=LIGHT).pack(side="left"); self.date_entry(controls,self.report_to_date,13).pack(side="left",padx=(4,10))
        tk.Label(controls,text="Account From:",bg=LIGHT).pack(side="left"); self.account_search_box(controls,self.report_account_from,16).pack(side="left",padx=(4,6))
        tk.Label(controls,text="To:",bg=LIGHT).pack(side="left"); self.account_search_box(controls,self.report_account_to,16).pack(side="left",padx=(4,10))
        tk.Button(controls,text="Apply",command=self.load_financial_reports,bg=GOLD,fg=NAVY,border=0,padx=15,pady=6).pack(side="left")
        nested=ttk.Notebook(self.reports_tab); nested.pack(fill="both",expand=True,padx=10,pady=(0,10)); self.financial_notebook=nested
        gl=tk.Frame(nested,bg=LIGHT); bs=tk.Frame(nested,bg=LIGHT); vat=tk.Frame(nested,bg=LIGHT); cash=tk.Frame(nested,bg=LIGHT); cash_outlook=tk.Frame(nested,bg=LIGHT); aging=self.ageing_tab; comparative=tk.Frame(nested,bg=LIGHT)
        nested.add(gl,text="General Ledger"); nested.add(bs,text="Balance Sheet"); nested.add(vat,text="Lebanese VAT Report"); nested.add(cash,text="Cash Flow"); nested.add(cash_outlook,text="Cash Flow Outlook"); nested.add(comparative,text="Comparative P&L"); self.ageing_page=aging; self.build_budget_page(nested); self.build_business_reports_page(nested)
        self.ledger_tree=self.table(gl,[("date","Date",95),("entry","Entry",90),("account","Account",85),("currency","Currency",70),("name","Account Name",180),("description","Description",200),("debit","Debit",105),("credit","Credit",105),("balance","Balance",110)])
        self.report_buttons(gl,"ledger")
        self.balance_tree=self.table(bs,[("type","Type",90),("account","Account",90),("currency","Currency",80),("name","Account Name",280),("debit","Debit",120),("credit","Credit",120),("balance","Balance",130)])
        self.report_buttons(bs,"balance")
        self.vat_tree=self.table(vat,[("currency","Currency",85),("type","Type",100),("invoices","Count",75),("subtotal","Before VAT",130),("vat","VAT",110),("total","Total",130)])
        self.report_buttons(vat,"vat")
        self.vat_summary=tk.Label(vat,text="",bg=LIGHT,font=("Segoe UI",10,"bold")); self.vat_summary.pack(pady=(0,8))
        self.cash_tree=self.table(cash,[("currency","Currency",90),("category","Cash Flow Category",280),("inflow","Inflow",140),("outflow","Outflow",140),("net","Net Cash Movement",160)]); self.report_buttons(cash,"cash")
        outlook_bar=tk.Frame(cash_outlook,bg=LIGHT); outlook_bar.pack(fill="x",padx=10,pady=8)
        self.cash_outlook_year=tk.StringVar(value=str(self.current_fiscal_year))
        self.cash_outlook_horizon=tk.StringVar(value="Quarter (3 months)")
        tk.Label(outlook_bar,text="Report year",bg=LIGHT,fg=NAVY).pack(side="left")
        tk.Entry(outlook_bar,textvariable=self.cash_outlook_year,width=6).pack(side="left",padx=(4,10))
        tk.Label(outlook_bar,text="Project ahead",bg=LIGHT,fg=NAVY).pack(side="left")
        ttk.Combobox(outlook_bar,textvariable=self.cash_outlook_horizon,values=["Quarter (3 months)","6 Months","Yearly (12 months)"],state="readonly",width=21).pack(side="left",padx=(4,10))
        tk.Label(outlook_bar,text="Projected values use the last 3 complete months.",bg=LIGHT,fg=NAVY).pack(side="left")
        self.action_button(outlook_bar,"Refresh Projection",self.load_cashflow_outlook).pack(side="right")
        self.cash_projection_tree=self.table(cash_outlook,[("month","Period",180),("status","Status",95),("currency","Currency",85),
            ("inflow","Inflow",130),("outflow","Outflow",130),("net","Net cash movement",150)])
        self.report_buttons(cash_outlook,"cash_projection")
        long_cash_bar=tk.Frame(cash_outlook,bg=LIGHT); long_cash_bar.pack(fill="x",padx=10,pady=(0,8))
        self.cash_long_target=tk.StringVar(value=""); self.cash_long_growth=tk.StringVar(value="0"); self.cash_long_growth_by_year=tk.StringVar(value="")
        tk.Label(long_cash_bar,text="5-Year Projection to date (DD-MM-YYYY)",bg=LIGHT,fg=NAVY).pack(side="left")
        tk.Entry(long_cash_bar,textvariable=self.cash_long_target,width=12).pack(side="left",padx=(4,10))
        tk.Label(long_cash_bar,text="Growth % per year",bg=LIGHT,fg=NAVY).pack(side="left")
        tk.Entry(long_cash_bar,textvariable=self.cash_long_growth,width=7).pack(side="left",padx=(4,10))
        tk.Label(long_cash_bar,text="Per-year % (e.g. 2027=10, 2028=5)",bg=LIGHT,fg=NAVY).pack(side="left")
        tk.Entry(long_cash_bar,textvariable=self.cash_long_growth_by_year,width=22).pack(side="left",padx=(4,10))
        self.action_button(long_cash_bar,"5-Year Projection",self.cashflow_long_term_projection).pack(side="left",padx=3)
        tk.Label(long_cash_bar,text="Uses \"Report year\" above as the base year; compounds the growth % each year ahead.",bg=LIGHT,fg=NAVY).pack(side="left",padx=10)
        self.cash_long_tree=self.table(cash_outlook,[("year","Year",70),("up_to","Up to",100),("currency","Currency",85),("source","Source",85),
            ("inflow","Inflow",130),("outflow","Outflow",130),("net","Net cash movement",150)])
        ageing_controls=tk.Frame(aging,bg=LIGHT); ageing_controls.pack(fill="x",padx=8,pady=4)
        self.ageing_kind=tk.StringVar(value="Customers & Suppliers")
        tk.Label(ageing_controls,text="Show",bg=LIGHT).pack(side="left")
        kind_box=ttk.Combobox(ageing_controls,textvariable=self.ageing_kind,values=["Customers & Suppliers","Customers","Suppliers"],state="readonly",width=24)
        kind_box.pack(side="left",padx=6); kind_box.bind("<<ComboboxSelected>>",lambda _e:self.refresh_ageing_tree())
        tk.Label(ageing_controls,text="As of",bg=LIGHT).pack(side="left",padx=(8,2)); self.date_entry(ageing_controls,self.ageing_as_of,12).pack(side="left",padx=3)
        range_row=tk.Frame(aging,bg=LIGHT); range_row.pack(fill="x",padx=8,pady=(0,4))
        choices=[f'{p.get("account_number") or ""} - {p["name"]}' for p in self.client.parties()]
        for label,var in (("Account / Name From",self.ageing_from),("To",self.ageing_to)):
            tk.Label(range_row,text=label,bg=LIGHT).pack(side="left",padx=(6,2))
            ttk.Combobox(range_row,textvariable=var,values=choices,width=27).pack(side="left",padx=(2,8))
        self.action_button(range_row,"Apply",self.load_ageing_report).pack(side="left",padx=4)
        tk.Label(range_row,text="Type a number or name, or choose from the list.",bg=LIGHT,fg="#5f6b76").pack(side="left",padx=8)
        tk.Label(aging,text="Past dates use the current invoice outstanding balance; future dates show the expected lateness if no further payment is made.",
            bg=LIGHT,fg="#5f6b76",anchor="w").pack(fill="x",padx=12)
        self.aging_tree=self.table(aging,[("kind","Type",85),("party","Customer / Supplier",220),("invoice","Invoice",110),("due","Due Date",100),("currency","Currency",75),("outstanding","Outstanding",120),("days","Days Overdue",110),("bucket","Aging Bucket",100)]); self.report_buttons(aging,"aging")
        self.comparative_tree=self.table(comparative,[("currency","Currency",75),("type","Type",85),("account","Account",95),("name","Account Name",260),("current","Current Period",130),("prior","Prior Year",130),("variance","Variance",130)]); self.report_buttons(comparative,"comparative")
        self.load_financial_reports()
        self.load_ageing_report()
        self.load_cashflow_outlook()

    def report_buttons(self,parent,report):
        frame=tk.Frame(parent,bg=LIGHT); frame.pack(pady=(0,8))
        self.action_button(frame,"Excel",lambda:self.financial_report_export(report,"xlsx")).pack(side="left",padx=4)
        self.action_button(frame,"PDF",lambda:self.financial_report_export(report,"pdf")).pack(side="left",padx=4)
        self.action_button(frame,"Print",lambda:self.financial_report_export(report,"print")).pack(side="left",padx=4)

    def financial_report_range(self):
        values=[]
        for raw in (self.report_from_date.get(),self.report_to_date.get()):
            try: values.append(parse_user_date(raw).strftime("%Y-%m-%d"))
            except ValueError: messagebox.showwarning("Financial Reports","Dates must use DD-MM-YYYY"); return None
        if values[0]>values[1]: messagebox.showwarning("Financial Reports","From Date cannot be after To Date"); return None
        return values

    def load_financial_reports(self):
        if not hasattr(self,"ledger_tree"): return
        dates=self.financial_report_range()
        if dates is None: return
        currency=None if self.view_currency.get()=="All Currencies" else self.view_currency.get()
        try:
            ledger=self.client.general_ledger(None,dates[0],dates[1],currency)
            balance=self.client.balance_sheet(dates[1],currency)
            vat=self.client.vat_report(dates[0],dates[1],currency)
            cash=self.client.cash_flow(dates[0],dates[1],currency)
            comparative=self.client.comparative_reports(dates[0],dates[1],currency)
        except Exception as exc: return messagebox.showerror("Financial Reports",str(exc))
        account_from=self.report_account_from.get().split(" - ",1)[0].strip(); account_to=self.report_account_to.get().split(" - ",1)[0].strip()
        def in_account_range(code):
            digits=int(''.join(c for c in str(code) if c.isdigit()) or 0)
            low=int(''.join(c for c in account_from if c.isdigit()) or 0); high=int(''.join(c for c in account_to if c.isdigit()) or 999999999999)
            return low<=digits<=high
        self.ledger_rows=[row for row in ledger["items"] if in_account_range(row["account_code"])]; self.balance_rows=[row for row in balance if in_account_range(row["code"])]; self.vat_rows=vat["items"]; self.cash_rows=cash; self.comparative_rows=comparative["items"]
        self.ledger_tree.delete(*self.ledger_tree.get_children()); self.balance_tree.delete(*self.balance_tree.get_children()); self.vat_tree.delete(*self.vat_tree.get_children()); self.cash_tree.delete(*self.cash_tree.get_children()); self.comparative_tree.delete(*self.comparative_tree.get_children())
        for r in self.ledger_rows: self.ledger_tree.insert("","end",values=(r["entry_date"],r["entry_number"],r["account_code"],r["currency"],r["account_name"],r["description"],f'{r["debit"]:,.2f}',f'{r["credit"]:,.2f}',f'{r["balance"]:,.2f}'))
        for r in balance: self.balance_tree.insert("","end",values=(r["type"],r["code"],r["currency"],r["name_en"],f'{r["debit"]:,.2f}',f'{r["credit"]:,.2f}',f'{r["balance"]:,.2f}'))
        for r in self.vat_rows: self.vat_tree.insert("","end",values=(r["currency"],r["kind"],r["invoices"],f'{r["subtotal"] or 0:,.2f}',f'{r["vat"] or 0:,.2f}',f'{r["total"] or 0:,.2f}'))
        for r in self.cash_rows: self.cash_tree.insert("","end",values=(r["currency"],r["category"],f'{r["inflow"]:,.2f}',f'{r["outflow"]:,.2f}',f'{r["net"]:,.2f}'))
        for r in self.comparative_rows: self.comparative_tree.insert("","end",values=(r["currency"],r["type"],r["code"],r["name_en"],f'{r["current"]:,.2f}',f'{r["prior"]:,.2f}',f'{r["variance"]:,.2f}'))
        self.vat_summary.config(text="   ".join(f'{r["currency"]} VAT payable: {r["vat_payable"]:,.2f}' for r in vat["summary"]) or "No VAT activity")

    def load_ageing_report(self):
        try: as_of=parse_user_date(self.ageing_as_of.get()).strftime("%Y-%m-%d")
        except ValueError: return messagebox.showwarning("Ageing Report","As of date must use DD-MM-YYYY")
        currency=None if self.view_currency.get()=="All Currencies" else self.view_currency.get()
        try: self.aging_rows=self.client.aging(as_of,None,currency)
        except Exception as exc: return messagebox.showerror("Ageing Report",str(exc))
        self.refresh_ageing_tree()

    def visible_ageing_rows(self):
        choice = self.ageing_kind.get()
        rows=[r for r in getattr(self,"aging_rows",[]) if choice=="Customers & Suppliers" or (r["kind"]=="sale")== (choice=="Customers")]
        lower=self.ageing_from.get().strip(); upper=self.ageing_to.get().strip()
        if lower and not upper and " - " not in lower:
            needle=lower.casefold()
            return [row for row in rows if needle in str(row.get("account_number") or "").casefold() or needle in str(row.get("party_name") or "").casefold()]
        def bound(value):
            if not value: return None
            code=value.split(" - ",1)[0].strip()
            if code.isdigit(): return ("account",code)
            match=next((r for r in rows if (r.get("party_name") or "").casefold()==value.casefold()),None)
            if match: return ("account",match.get("account_number") or "") if match.get("account_number") else ("name",value.casefold())
            return ("name",value.casefold())
        start,end=bound(lower),bound(upper)
        if start and end and start[0]!=end[0]: return []
        for edge,is_lower in ((start,True),(end,False)):
            if not edge: continue
            key="account_number" if edge[0]=="account" else "party_name"
            rows=[r for r in rows if (str(r.get(key) or "").casefold()>=edge[1] if is_lower else str(r.get(key) or "").casefold()<=edge[1])]
        return rows

    def refresh_ageing_tree(self):
        self.aging_tree.delete(*self.aging_tree.get_children())
        for r in self.visible_ageing_rows():
            self.aging_tree.insert("","end",values=("Receivable" if r["kind"]=="sale" else "Payable",r["party_name"],r["invoice_number"],r.get("due_date") or r["invoice_date"],r["currency"],f'{r["outstanding"]:,.2f}',r["days_overdue"],r["bucket"]))

    def load_cashflow_outlook(self):
        from financial_projection import HORIZONS, completed_months, future_months, month_range, trailing_average
        try:
            year=int(self.cash_outlook_year.get()); last=completed_months(year)
            future=future_months(year,last,HORIZONS[self.cash_outlook_horizon.get()])
        except (ValueError,KeyError) as exc: return messagebox.showwarning("Cash Flow Outlook",str(exc))
        currency=None if self.view_currency.get()=="All Currencies" else self.view_currency.get()
        history={}; currencies=set()
        try:
            for month in range(1,last+1):
                start,end=month_range(year,month)
                rows=self.client.cash_flow(start,end,currency)
                for row in rows:
                    key=row["currency"]; currencies.add(key)
                    values=history.setdefault((key,month),{"inflow":0.0,"outflow":0.0})
                    values["inflow"]+=float(row["inflow"]); values["outflow"]+=float(row["outflow"])
        except Exception as exc: return messagebox.showerror("Cash Flow Outlook",str(exc))
        self.cash_projection_rows=[]
        if not currencies: currencies={currency or "USD"}
        for code in sorted(currencies):
            actual_total={"inflow":0.0,"outflow":0.0}
            for month in range(1,last+1):
                values=history.get((code,month),{"inflow":0.0,"outflow":0.0})
                for key in actual_total: actual_total[key]+=values[key]
                self.cash_projection_rows.append({"month":f"{year}-{month:02d}","status":"Actual","currency":code,**values,
                    "net":values["inflow"]-values["outflow"]})
            self.cash_projection_rows.append({"month":f"{year} actual total (Jan–{last:02d})","status":"Actual total","currency":code,**actual_total,
                "net":actual_total["inflow"]-actual_total["outflow"]})
            monthly={month:history.get((code,month),{}) for month in range(1,last+1)}
            average={key:trailing_average(monthly,last,key) for key in ("inflow","outflow")}
            for projected_year,projected_month in future:
                self.cash_projection_rows.append({"month":f"{projected_year}-{projected_month:02d}","status":"Projected","currency":code,**average,
                    "net":average["inflow"]-average["outflow"]})
            totals={key:average[key]*len(future) for key in average}
            self.cash_projection_rows.append({"month":f"{future[0][0]}-{future[0][1]:02d} to {future[-1][0]}-{future[-1][1]:02d}",
                "status":"Forecast total","currency":code,**totals,"net":totals["inflow"]-totals["outflow"]})
        self.cash_projection_tree.delete(*self.cash_projection_tree.get_children())
        for row in self.cash_projection_rows:
            self.cash_projection_tree.insert("","end",values=(row["month"],row["status"],row["currency"],
                f'{row["inflow"]:,.2f}',f'{row["outflow"]:,.2f}',f'{row["net"]:,.2f}'))

    def _parse_growth_by_year(self,text):
        """Parse 'YYYY=rate%' pairs (comma/semicolon separated) into {year: decimal_rate}. Empty -> {}."""
        result={}
        for part in str(text or "").replace(";",",").split(","):
            part=part.strip()
            if not part: continue
            for sep in ("=",":"):
                if sep in part: key,_,value=part.partition(sep); break
            else: raise ValueError(f"Use YYYY=rate for per-year growth, not '{part}'")
            try: year=int(key.strip()); rate=float(value.strip().rstrip("%"))/100
            except ValueError: raise ValueError(f"Invalid per-year growth entry '{part}'")
            result[year]=rate
        return result

    def cashflow_long_term_projection(self):
        from financial_projection import long_term_projection
        try: base_year=int(self.cash_outlook_year.get())
        except ValueError: return messagebox.showwarning("5-Year Projection","Enter the base year in \"Report year\", for example 2026")
        try: target_date=datetime.strptime(self.cash_long_target.get().strip(),"%d-%m-%Y").strftime("%Y-%m-%d")
        except ValueError: return messagebox.showwarning("5-Year Projection","Enter the target date as DD-MM-YYYY, for example 31-12-2030")
        try: growth_rate=float(self.cash_long_growth.get() or 0)/100
        except ValueError: growth_rate=0
        try: growth_by_year=self._parse_growth_by_year(self.cash_long_growth_by_year.get())
        except ValueError as exc: return messagebox.showwarning("5-Year Projection",str(exc))
        currency=None if self.view_currency.get()=="All Currencies" else self.view_currency.get()
        try: actual_rows=self.client.cash_flow(f"01-01-{base_year}",f"31-12-{base_year}",currency)
        except Exception as exc: return messagebox.showerror("5-Year Projection",str(exc))
        base_by_currency={}
        for row in actual_rows:
            values=base_by_currency.setdefault(row["currency"],{"inflow":0.0,"outflow":0.0})
            values["inflow"]+=float(row["inflow"]); values["outflow"]+=float(row["outflow"])
        if not base_by_currency: return messagebox.showwarning("5-Year Projection",f"No cash flow actuals in {base_year} to project from")
        rows=[]
        for code,base_values in sorted(base_by_currency.items()):
            try: projection=long_term_projection(base_values,base_year,target_date,growth_rate,growth_by_year=growth_by_year)
            except ValueError as exc: return messagebox.showwarning("5-Year Projection",str(exc))
            for entry in projection:
                inflow=entry["values"]["inflow"]; outflow=entry["values"]["outflow"]
                rows.append({"year":entry["year"],"up_to":entry["date_to"],"currency":code,"source":entry["source"].title(),
                    "inflow":inflow,"outflow":outflow,"net":inflow-outflow})
        self.cash_long_tree.delete(*self.cash_long_tree.get_children())
        for row in rows:
            self.cash_long_tree.insert("","end",values=(row["year"],row["up_to"],row["currency"],row["source"],
                f'{row["inflow"]:,.2f}',f'{row["outflow"]:,.2f}',f'{row["net"]:,.2f}'))
        if not rows: messagebox.showinfo("5-Year Projection","No rows to project (check the base year and target date)")

    def financial_report_export(self,report,format_name):
        if report=="ledger": title="General Ledger"; headers=["Date","Entry","Account","Currency","Name","Description","Debit","Credit","Balance"]; rows=[[r["entry_date"],r["entry_number"],r["account_code"],r["currency"],r["account_name"],r["description"],r["debit"],r["credit"],r["balance"]] for r in getattr(self,"ledger_rows",[])]
        elif report=="balance": title="Balance Sheet"; headers=["Type","Account","Currency","Name","Debit","Credit","Balance"]; rows=[[r["type"],r["code"],r["currency"],r["name_en"],r["debit"],r["credit"],r["balance"]] for r in getattr(self,"balance_rows",[])]
        elif report=="vat": title="Lebanese VAT Report"; headers=["Currency","Type","Count","Before VAT","VAT","Total"]; rows=[[r["currency"],r["kind"],r["invoices"],r["subtotal"],r["vat"],r["total"]] for r in getattr(self,"vat_rows",[])]
        elif report=="cash": title="Cash Flow"; headers=["Currency","Category","Inflow","Outflow","Net"]; rows=[[r["currency"],r["category"],r["inflow"],r["outflow"],r["net"]] for r in getattr(self,"cash_rows",[])]
        elif report=="cash_projection": title="Cash Flow Actual and Projection"; headers=["Month","Status","Currency","Inflow","Outflow","Net"]; rows=[[r["month"],r["status"],r["currency"],r["inflow"],r["outflow"],r["net"]] for r in getattr(self,"cash_projection_rows",[])]
        elif report=="aging": title=f"Customer and Supplier Ageing as of {self.ageing_as_of.get()}"; headers=["Type","Party","Invoice","Due Date","Currency","Outstanding","Days Overdue","Bucket"]; rows=[["Receivable" if r["kind"]=="sale" else "Payable",r["party_name"],r["invoice_number"],r.get("due_date") or r["invoice_date"],r["currency"],r["outstanding"],r["days_overdue"],r["bucket"]] for r in self.visible_ageing_rows()]
        else: title="Comparative Profit and Loss"; headers=["Currency","Type","Account","Name","Current Period","Prior Year","Variance"]; rows=[[r["currency"],r["type"],r["code"],r["name_en"],r["current"],r["prior"],r["variance"]] for r in getattr(self,"comparative_rows",[])]
        if not rows: return messagebox.showwarning(title,"No data to export")
        try:
            if format_name=="print": print_rows(title,headers,rows); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"; path=filedialog.asksaveasfilename(defaultextension=extension,initialfile=title.replace(" ","_")+extension)
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,rows); messagebox.showinfo(title,f"Saved successfully:\n{path}")
        except Exception as exc: messagebox.showerror(title,str(exc))

    def build_accounts(self):
        controls=tk.Frame(self.accounts_tab,bg=LIGHT); controls.pack(fill="x",padx=10,pady=(10,0))
        self.new_account_code=tk.StringVar(); self.new_account_name=tk.StringVar(); self.new_account_parent=tk.StringVar(); self.new_account_type=tk.StringVar(value="expense")
        tk.Label(controls,text="Account (4-digit prefix = automatic):",bg=LIGHT,font=("Segoe UI",9,"bold"),fg=NAVY).pack(side="left",padx=(0,4))
        self.new_account_code_entry=tk.Entry(controls,textvariable=self.new_account_code,width=11); self.new_account_code_entry.pack(side="left",padx=3)
        self.new_account_code_entry.bind("<FocusOut>",self.preview_new_account_number); self.new_account_code_entry.bind("<Return>",self.preview_new_account_number)
        tk.Entry(controls,textvariable=self.new_account_name,width=22).pack(side="left",padx=3)
        tk.Entry(controls,textvariable=self.new_account_parent,width=9).pack(side="left",padx=3)
        ttk.Combobox(controls,textvariable=self.new_account_type,values=["asset","liability","equity","income","expense"],state="readonly",width=9).pack(side="left",padx=3)
        self.action_button(controls,"Create Account",self.save_new_account).pack(side="left",padx=5)
        self.action_button(controls,"Edit Selected Name",self.rename_selected_account).pack(side="left",padx=5)
        self.action_button(controls,tr(self.language.get(),"refresh"),self.load_accounts).pack(side="right")
        self.accounts_tree=self.table(self.accounts_tab,[
            ("code","Account",100),("parent","Parent",80),("english","English",270),
            ("french","French",270),("arabic","Arabic",270),("type","Type",90)])
        self.accounts_tree.bind("<Double-1>",lambda _event:self.load_selected_account_name())
        self.load_accounts()

    def save_new_account(self):
        try: account=self.client.save_account({"code":self.new_account_code.get(),"name_en":self.new_account_name.get(),"parent_code":self.new_account_parent.get(),"type":self.new_account_type.get()})
        except Exception as exc: return messagebox.showerror("Chart of Accounts",str(exc))
        self._account_cache=None
        self.new_account_code.set(""); self.new_account_name.set(""); self.new_account_parent.set(""); self.load_accounts()
        messagebox.showinfo("Chart of Accounts",f'Account {account["code"]} created successfully')

    def preview_new_account_number(self,_event=None):
        prefix=self.new_account_code.get().strip()
        if len(prefix)!=4 or not prefix.isdigit(): return
        try: number=self.client.next_account_number(prefix)
        except Exception as exc: return messagebox.showwarning("Chart of Accounts",str(exc))
        self.new_account_parent.set(prefix); self.new_account_code.set(number)

    def load_selected_account_name(self):
        selected=self.accounts_tree.selection()
        if not selected: return
        values=self.accounts_tree.item(selected[0],"values"); self.new_account_code.set(values[0]); self.new_account_name.set(values[2])

    def rename_selected_account(self):
        selected=self.accounts_tree.selection()
        if not selected: return messagebox.showwarning("Chart of Accounts","Select an account first")
        code=str(self.accounts_tree.item(selected[0],"values")[0]); name=self.new_account_name.get().strip()
        try: self.client.rename_account(code,name)
        except Exception as exc: return messagebox.showerror("Chart of Accounts",str(exc))
        self.load_accounts(); messagebox.showinfo("Chart of Accounts",f"Account {code} name updated")

    def load_accounts(self):
        try:
            rows=self.client.accounts()
        except Exception as exc:
            return messagebox.showerror("Error",str(exc))
        self.accounts_tree.delete(*self.accounts_tree.get_children())
        for row in rows:
            self.accounts_tree.insert("","end",values=(row["code"],row.get("parent_code") or "",
                row["name_en"],row.get("name_fr") or "",row.get("name_ar") or "",row["type"]))

    def build_settings(self):
        nested=ttk.Notebook(self.settings_tab); nested.pack(fill="both",expand=True,padx=10,pady=10)
        users=tk.Frame(nested,bg=LIGHT); backups=tk.Frame(nested,bg=LIGHT); rates=tk.Frame(nested,bg=LIGHT); branches=tk.Frame(nested,bg=LIGHT); general=tk.Frame(nested,bg=LIGHT)
        is_admin=(self.current_user or {}).get("role")=="admin"
        if is_admin: nested.add(users,text="Users & Permissions")
        nested.add(backups,text="Backup & Restore" if is_admin else "My Backups"); nested.add(rates,text="Exchange Rates"); nested.add(branches,text="Branches"); nested.add(general,text="General Settings"); self.build_dimensions_pages(nested)
        if is_admin: self.build_users_page(users)
        backup_controls=tk.Frame(backups,bg=LIGHT); backup_controls.pack(fill="x",padx=10,pady=10)
        self.backup_scope=tk.Label(backups,text="",bg=LIGHT,fg=NAVY,font=("Segoe UI",10,"bold"),anchor="w"); self.backup_scope.pack(fill="x",padx=14,before=backup_controls)
        tk.Button(backup_controls,text="Create Backup Now",command=self.create_backup,bg=GOLD,fg=NAVY,border=0,padx=15,pady=7,font=("Segoe UI",9,"bold")).pack(side="left",padx=4)
        self.action_button(backup_controls,"Save Backup As... (USB / Drive)",self.save_backup_as).pack(side="left",padx=4)
        self.action_button(backup_controls,"Open Backup Folder",self.open_backup_folder).pack(side="left",padx=4)
        if is_admin: tk.Button(backup_controls,text="Restore Selected",command=self.restore_selected_backup,bg="#8B1E1E",fg="white",border=0,padx=15,pady=7).pack(side="left",padx=4)
        tk.Label(backups,text="Backups are saved by company and fiscal year automatically each day while signed in to Windows. You can also create or export one here.",bg=LIGHT,fg="#5f6b76",wraplength=1050,justify="left").pack(fill="x",padx=14)
        self.backups_tree=self.table(backups,[("name","Backup File",430),("kind","Type",100),("size","Size",100),("modified","Created",170)])
        rate_controls=tk.Frame(rates,bg=LIGHT); rate_controls.pack(fill="x",padx=10,pady=10)
        self.rate_date=tk.StringVar(value=datetime.now().strftime("%d-%m-%Y")); self.rate_date_to=tk.StringVar(value=datetime.now().strftime("%d-%m-%Y")); self.rate_from=tk.StringVar(value="USD"); self.rate_to=tk.StringVar(value="LBP"); self.rate_value=tk.StringVar(value="1")
        tk.Label(rate_controls,text="Date From",bg=LIGHT).pack(side="left"); self.date_entry(rate_controls,self.rate_date,12).pack(side="left",padx=4)
        tk.Label(rate_controls,text="Date To",bg=LIGHT).pack(side="left"); self.date_entry(rate_controls,self.rate_date_to,12).pack(side="left",padx=4)
        self.rate_from_box=ttk.Combobox(rate_controls,textvariable=self.rate_from,values=self.currency_codes,state="readonly",width=7); self.rate_from_box.pack(side="left",padx=4)
        tk.Label(rate_controls,text="to",bg=LIGHT).pack(side="left")
        self.rate_to_box=ttk.Combobox(rate_controls,textvariable=self.rate_to,values=self.currency_codes,state="readonly",width=7); self.rate_to_box.pack(side="left",padx=4)
        tk.Entry(rate_controls,textvariable=self.rate_value,width=14).pack(side="left",padx=4)
        self.action_button(rate_controls,"Add Daily Rate",self.save_exchange_rate).pack(side="left",padx=5)
        self.action_button(rate_controls,"Restore EUR Rates 2024-Today",self.restore_euro_rates).pack(side="left",padx=5)
        currency_controls=tk.Frame(rates,bg=LIGHT); currency_controls.pack(fill="x",padx=12,pady=(0,6))
        self.new_currency_code=tk.StringVar(); self.new_currency_name=tk.StringVar()
        tk.Label(currency_controls,text="Create currency",bg=LIGHT,font=("Segoe UI",9,"bold")).pack(side="left",padx=(0,6))
        tk.Entry(currency_controls,textvariable=self.new_currency_code,width=7).pack(side="left")
        tk.Label(currency_controls,text="Code (3 letters)",bg=LIGHT).pack(side="left",padx=(3,12))
        tk.Entry(currency_controls,textvariable=self.new_currency_name,width=22).pack(side="left")
        tk.Label(currency_controls,text="Name",bg=LIGHT).pack(side="left",padx=(3,8))
        self.action_button(currency_controls,"Add Currency",self.create_currency).pack(side="left",padx=4)
        tk.Label(currency_controls,text="Set a rate before using it in another currency's report.",bg=LIGHT,fg="#5f6b76").pack(side="left",padx=8)
        self.rates_tree=self.table(rates,[("date","Date",110),("from","From",80),("to","To",80),("rate","Daily Average",150),("samples","Entries",75),("created","Saved",180)])
        self.rates_tree.bind("<Double-1>",lambda _event:self.edit_selected_exchange_rate())
        branch_controls=tk.Frame(branches,bg=LIGHT); branch_controls.pack(fill="x",padx=10,pady=10)
        self.new_branch_name=tk.StringVar(); tk.Label(branch_controls,text="New Branch Name",bg=LIGHT).pack(side="left"); tk.Entry(branch_controls,textvariable=self.new_branch_name,width=32).pack(side="left",padx=6)
        self.action_button(branch_controls,"Save Branch",self.save_branch).pack(side="left",padx=4)
        self.branches_tree=self.table(branches,[("id","ID",80),("name","Branch Name",320),("active","Active",90)])
        self.base_currency=tk.StringVar(value="USD"); self.backup_hours=tk.StringVar(value="24")
        self.company_fields={key:tk.StringVar() for key in ("company_name","company_address","company_phone","company_mof","company_nssf","company_email","company_website","company_logo")}
        tk.Label(general,text="Base Currency",bg=LIGHT).grid(row=0,column=0,padx=14,pady=14,sticky="w")
        self.base_currency_box=ttk.Combobox(general,textvariable=self.base_currency,values=self.currency_codes,state="readonly",width=15); self.base_currency_box.grid(row=0,column=1,padx=14,pady=14)

        for row,(key,label) in enumerate((("company_name","Company Name"),("company_address","Address"),("company_phone","Phone"),("company_mof","MOF / VAT Number"),("company_nssf","NSSF Employer Number"),("company_email","Email"),("company_website","Website"),("company_logo","Logo File Path")),2):
            tk.Label(general,text=label,bg=LIGHT).grid(row=row,column=0,padx=14,pady=7,sticky="w")
            tk.Entry(general,textvariable=self.company_fields[key],width=42).grid(row=row,column=1,padx=14,pady=7,sticky="w")
        self.company_vat_registered=tk.StringVar(value="Yes"); self.company_vat_date=tk.StringVar()
        tk.Label(general,text="Registered in VAT",bg=LIGHT).grid(row=10,column=0,padx=14,pady=7,sticky="w")
        ttk.Combobox(general,textvariable=self.company_vat_registered,values=["Yes","No"],state="readonly",width=15).grid(row=10,column=1,padx=14,pady=7,sticky="w")
        tk.Label(general,text="VAT Registration Date",bg=LIGHT).grid(row=11,column=0,padx=14,pady=7,sticky="w")
        self.date_entry(general,self.company_vat_date,42).grid(row=11,column=1,padx=14,pady=7,sticky="w")
        self.action_button(general,"Save Settings",self.save_general_settings).grid(row=12,column=0,columnspan=2,pady=14)
        self.load_settings_pages()

    def load_settings_pages(self):
        if not hasattr(self,"backups_tree"): return
        try:
            settings=self.client.settings(); rates=self.client.exchange_rates()
            self.base_currency.set(settings.get("base_currency","USD")); self.backup_hours.set(settings.get("backup_interval_hours","24"))
            for key,var in self.company_fields.items(): var.set(settings.get(key,"Saber for Audit" if key=="company_name" else ""))
            self.company_vat_registered.set(settings.get("company_vat_registered","Yes") or "Yes"); self.company_vat_date.set(settings.get("company_vat_date","") or "")
        except Exception as exc: return messagebox.showerror("Settings",str(exc))
        self.rates_tree.delete(*self.rates_tree.get_children())
        for row in rates: self.rates_tree.insert("","end",values=(row["rate_date"],row["from_currency"],row["to_currency"],row["rate"],row.get("samples",0),row["created_at"][:19]))
        try: branch_rows=self.client.branches()
        except Exception: branch_rows=[]
        self.branches_tree.delete(*self.branches_tree.get_children())
        for row in branch_rows: self.branches_tree.insert("","end",values=(row["id"],row["name"],"Yes" if row["active"] else "No"))
        try: backups=self.client.backups()
        except Exception: backups=[]
        self.backups_tree.delete(*self.backups_tree.get_children())
        if (self.current_user or {}).get("role")=="admin":
            try: users=self.client.users()
            except Exception: users=[]
            self.users_tree.delete(*self.users_tree.get_children()); self.fill_users_tree(users)
        for row in backups: self.backups_tree.insert("","end",iid=row["name"],values=(row["name"],row.get("kind","backup"),f'{row["size"]/1024/1024:,.2f} MB',row["modified"][:19].replace("T"," ")))
        if hasattr(self,"backup_scope"): self.backup_scope.config(text=f'Backups of {getattr(self,"current_company",{}).get("name","")} - fiscal year {getattr(self,"current_fiscal_year","")}')

    def save_branch(self):
        try: branch=self.client.save_branch(self.new_branch_name.get().strip())
        except Exception as exc: return messagebox.showerror("Branches",str(exc))
        self.new_branch_name.set(""); self.load_settings_pages(); messagebox.showinfo("Branches",f'Branch {branch["name"]} saved successfully')

    def create_backup(self):
        try: result=self.client.create_backup()
        except Exception as exc: return messagebox.showerror("Backup",str(exc))
        self.load_settings_pages(); messagebox.showinfo("Backup",f'Backup created:\n{result["path"]}')

    def save_backup_as(self):
        selected=self.backups_tree.selection()
        if not selected:
            if not messagebox.askyesno("Save Backup As","No backup is selected. Create a new backup now and save a copy?"): return
            try: name=Path(self.client.create_backup()["path"]).name
            except Exception as exc: return messagebox.showerror("Backup",str(exc))
            self.load_settings_pages()
        else: name=selected[0]
        path=filedialog.asksaveasfilename(initialfile=name,defaultextension=".db",filetypes=[("Saber backup","*.db")])
        if not path: return
        try: Path(path).write_bytes(self.client.download_backup(name)["content"])
        except Exception as exc: return messagebox.showerror("Save Backup As",str(exc))
        messagebox.showinfo("Save Backup As",f"Backup copied to:\n{path}")

    def open_backup_folder(self):
        try: folder=self.client.backup_folder(); Path(folder).mkdir(parents=True,exist_ok=True)
        except Exception as exc: return messagebox.showerror("Backups",str(exc))
        try:
            if os.name=="nt": os.startfile(folder)
            else: raise RuntimeError
        except Exception: messagebox.showinfo("Backups",f"Backup folder:\n{folder}")

    def restore_selected_backup(self):
        selected=self.backups_tree.selection()
        if not selected: return messagebox.showwarning("Restore","Select one backup")
        if not messagebox.askyesno("Restore Database","Restore this backup? A safety backup of current data will be created first."): return
        try: self.client.restore_backup(selected[0])
        except Exception as exc: return messagebox.showerror("Restore",str(exc))
        messagebox.showinfo("Restore","Database restored successfully. Refreshing all pages."); self.load_dashboard(); self.load_invoices(); self.load_journal(); self.load_trial(); self.load_settings_pages(); self.load_payroll(); self.load_transactions(); self.load_vat_return()

    def save_exchange_rate(self):
        try: self.client.save_exchange_rate({"date_from":self.rate_date.get(),"date_to":self.rate_date_to.get(),"from_currency":self.rate_from.get(),"to_currency":self.rate_to.get(),"rate":self.rate_value.get()})
        except Exception as exc: return messagebox.showerror("Exchange Rates",str(exc))
        self.load_settings_pages(); messagebox.showinfo("Exchange Rates","Rate added. The daily rate is the average of all entered rates for this date and currency pair.")

    def create_currency(self):
        try: item=self.client.save_currency(self.new_currency_code.get(),self.new_currency_name.get())
        except Exception as exc: return messagebox.showerror("Currencies",str(exc))
        previous=set(self.currency_codes)
        self.currency_codes=[row["code"] for row in self.client.currencies()]
        def refresh(widget):
            if isinstance(widget,ttk.Combobox):
                choices=list(widget["values"])
                existing=set(choices)
                if existing==previous: widget["values"]=self.currency_codes
                elif existing==previous|{"All Currencies"}: widget["values"]=["All Currencies"]+self.currency_codes
                elif existing==previous|{"account"}: widget["values"]=["account"]+self.currency_codes
                elif existing==previous|{"account","none"}: widget["values"]=["account"]+self.currency_codes+["none"]
            for child in widget.winfo_children(): refresh(child)
        refresh(self)
        for state in (getattr(self,"trial_state",None),getattr(self,"statement_state",None)):
            if state and item["code"] not in state["currencies"]:
                var=tk.BooleanVar(value=True); state["currencies"][item["code"]]=var
                tk.Checkbutton(state["dimension_row"],text=item["code"],variable=var,bg=LIGHT).pack(side="left")
        self.new_currency_code.set(""); self.new_currency_name.set("")
        messagebox.showinfo("Currencies",f'{item["code"]} added. Set its exchange rate before using cross-currency reports.')

    def edit_selected_exchange_rate(self):
        selected=self.rates_tree.selection()
        if not selected: return
        values=self.rates_tree.item(selected[0],"values")
        self.rate_date.set(values[0]); self.rate_date_to.set(values[0]); self.rate_from.set(values[1]); self.rate_to.set(values[2]); self.rate_value.set(values[3])

    def restore_euro_rates(self):
        if not messagebox.askyesno("Exchange Rates","Restore daily EUR to USD and EUR to LBP rates from 01-01-2024 until today?"): return
        try: result=self.client.restore_euro_rates()
        except Exception as exc: return messagebox.showerror("Exchange Rates",str(exc))
        self.load_settings_pages(); messagebox.showinfo("Exchange Rates",f'Restored {result.get("days",0)} days from 01-01-2024 until today')

    def save_general_settings(self):
        payload={"base_currency":self.base_currency.get(),"backup_interval_hours":self.backup_hours.get()}
        payload.update({key:var.get().strip() for key,var in self.company_fields.items()})
        payload["company_vat_registered"]=self.company_vat_registered.get(); payload["company_vat_date"]=self.company_vat_date.get().strip()
        try: self.client.save_settings(payload)
        except Exception as exc: return messagebox.showerror("Settings",str(exc))
        messagebox.showinfo("Settings","Settings saved successfully")

    def action_button(self,parent,text,command):
        return tk.Button(parent,text=text,command=command,bg=NAVY,fg="white",border=0,padx=15,pady=7)

    def account_search_box(self,parent,variable,width=22):
        try: accounts=self.client.accounts() if self.client else []
        except Exception: accounts=[]
        accounts=[row for row in accounts if len(str(row.get("code") or ""))==9 and str(row.get("code") or "").isdigit()]
        choices=[f'{row["code"]} - {row["name_en"]}' for row in accounts]
        box=ttk.Combobox(parent,textvariable=variable,values=choices,width=width)
        def search(_event=None):
            typed=variable.get().strip().casefold()
            box["values"]=[value for value in choices if typed in value.casefold()] if typed else choices
            if typed and box["values"]: box.after_idle(lambda: box.event_generate("<Down>"))
        def choose(_event=None):
            value=variable.get(); variable.set(value.split(" - ",1)[0].strip() if " - " in value else value.strip())
        box.bind("<KeyRelease>",search); box.bind("<<ComboboxSelected>>",choose); box.bind("<FocusOut>",choose)
        box.bind("<Button-1>",lambda _event: box.after_idle(lambda: box.event_generate("<Down>")))
        box.bind("<FocusIn>",lambda _event:setattr(self,"active_account_variable",variable))
        box._account_var=variable  # right-click opens the account search for this field
        return box

    def open_active_account_lookup(self,event=None):
        if self.active_account_variable is not None: self.open_account_lookup(self.active_account_variable)
        return "break"

    def open_account_lookup(self,variable):
        try: accounts=self.client.accounts()
        except Exception as exc: return messagebox.showerror("Account Search",str(exc))
        accounts=[row for row in accounts if len(str(row.get("code") or ""))==9 and str(row.get("code") or "").isdigit()]
        window=tk.Toplevel(self); window.title("Account Search - F2"); window.geometry("700x500"); window.configure(bg=LIGHT); window.transient(self); window.grab_set()
        search_var=tk.StringVar(); top=tk.Frame(window,bg=LIGHT); top.pack(fill="x",padx=10,pady=10)
        tk.Label(top,text="Search by Account Number or Name:",bg=LIGHT,font=("Segoe UI",10,"bold")).pack(side="left")
        entry=tk.Entry(top,textvariable=search_var,width=42); entry.pack(side="left",padx=8); entry.focus_set()
        frame=tk.Frame(window,bg=LIGHT); frame.pack(fill="both",expand=True,padx=10,pady=(0,10))
        tree=ttk.Treeview(frame,columns=("code","name","type"),show="headings"); tree.heading("code",text="Account Number"); tree.heading("name",text="Account Name"); tree.heading("type",text="Type"); tree.column("code",width=150); tree.column("name",width=350); tree.column("type",width=120)
        scroll=ttk.Scrollbar(frame,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=scroll.set); tree.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y")
        def populate(*_args):
            tree.delete(*tree.get_children()); typed=search_var.get().strip().casefold()
            for row in accounts:
                text=f'{row["code"]} {row["name_en"]}'.casefold()
                if not typed or typed in text: tree.insert("","end",values=(row["code"],row["name_en"],row["type"]))
        def select(_event=None):
            selected=tree.selection()
            if not selected: return
            values=tree.item(selected[0],"values"); variable.set(str(values[0])); window.destroy()
        search_var.trace_add("write",populate); tree.bind("<Double-1>",select); tree.bind("<Return>",select); entry.bind("<Return>",lambda _event:(tree.selection_set(tree.get_children()[0]),select()) if tree.get_children() else None)
        tk.Label(window,text="Double-click an account or press Enter to select",bg=LIGHT,fg="#5f6b76").pack(pady=(0,8)); populate()

    def branch_selector(self,parent,variable,width=18,include_all=False):
        try: branches=self.client.branches() if self.client else []
        except Exception: branches=[]
        values=(["All Branches"] if include_all else [])+[row["name"] for row in branches]
        if not values: values=["All Branches"] if include_all else ["Head Office"]
        if variable.get() not in values: variable.set(values[0])
        return ttk.Combobox(parent,textvariable=variable,values=values,state="readonly",width=width)

    def selected_branch_id(self,variable):
        if variable.get()=="All Branches": return None
        try: return next(row["id"] for row in self.client.branches() if row["name"]==variable.get())
        except Exception: return None

    def export_report(self,report,format_name):
        if report == "dashboard":
            title="Saber Accounting - Dashboard"; headers=["Currency","Sales","Purchases","Expenses","Net Profit","Receivables","Payables","Overdue"]
            rows=[[r["currency"],r["sales"],r["purchases"],r["expenses"],r["profit"],r["receivables"],r["payables"],r["overdue"]] for r in getattr(self,"dashboard_rows",[])]
        else:
            title="Saber Accounting - Trial Balance"
            if self.trial_from_date.get().strip() or self.trial_to_date.get().strip():
                title += f" ({self.trial_from_date.get().strip() or 'Beginning'} to {self.trial_to_date.get().strip() or 'Today'})"
            headers=["Currency","Account","Account Name","Opening Balance","Debit","Credit","Closing Balance"]
            rows=[[r["currency"],r["code"],r["name_en"],r.get("opening",0),r["debit"] or 0,r["credit"] or 0,r.get("closing_balance",0)] for r in getattr(self,"trial_rows",[])]
        if not rows: return messagebox.showwarning("Saber Accounting","No report data to export")
        try:
            if format_name == "print": print_rows(title,headers,rows); return
            extension=".xlsx" if format_name=="xlsx" else ".pdf"
            path=filedialog.asksaveasfilename(defaultextension=extension,filetypes=[("Excel workbook","*.xlsx")] if format_name=="xlsx" else [("PDF document","*.pdf")],initialfile=title.replace(" - ","_").replace(" ","_")+extension)
            if not path: return
            (export_excel if format_name=="xlsx" else export_pdf)(path,title,headers,rows)
            messagebox.showinfo("Saber Accounting",f"Saved successfully:\n{path}")
        except Exception as exc: messagebox.showerror("Saber Accounting",str(exc))

def main(): SaberApp().mainloop()

if __name__ == "__main__": main()
