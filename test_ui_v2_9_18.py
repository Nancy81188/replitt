"""Version 2.9.18 fixes, checked on the real program window (skipped when no display is available):
Stock Card from Items, the Inventory Analysis (3D) options, mouse-wheel page scrolling and
right-click search in fields."""
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk
    _probe = tk.Tk(); _probe.destroy(); HAVE_DISPLAY = True
except Exception:
    HAVE_DISPLAY = False

from client import ApiClient
from server import run_server


@unittest.skipUnless(HAVE_DISPLAY, "needs a display for the program window")
class ProgramWindowFixesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        database = Path(cls.folder.name) / "SaberAccounting" / "saber.db"; database.parent.mkdir(parents=True)
        probe = socket.socket(); probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]; probe.close()
        threading.Thread(target=run_server, kwargs={"host": "127.0.0.1", "port": port, "database": str(database), "admin_password": "admin12345"}, daemon=True).start()
        cls.url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try: ApiClient(cls.url).login("admin", "admin12345"); break
            except Exception: time.sleep(0.1)
        api = ApiClient(cls.url); api.login("admin", "admin12345")
        company = api.companies()[0]; api.select_company_year(company["id"], company["years"][0]["year"])
        api.save_inventory_item({"sku": "ITM-1", "name": "Test Panel", "unit": "unit", "sales_price": "10", "default_vat": "11"})
        cls.company = company

    @classmethod
    def tearDownClass(cls):
        import gc; gc.collect(); cls.folder.cleanup()

    def setUp(self):
        self.messages = []
        patches = [mock.patch(f"tkinter.messagebox.{name}", side_effect=lambda *a, n=name, **k: self.messages.append((n, a)) or True)
                   for name in ("showerror", "showwarning", "showinfo", "askyesno")]
        for patch in patches: patch.start(); self.addCleanup(patch.stop)
        import desktop
        # Tk objects must be freed on this (main) thread, never by a data-service thread's garbage collection.
        import gc; self.addCleanup(gc.collect)
        self.app = desktop.SaberApp(); self.addCleanup(self.app.destroy)
        self.app.server.set(self.url); self.app.password.set("admin12345"); self.app.login()
        year = self.company["years"][0]["year"]
        self.app.client.select_company_year(self.company["id"], year); self.app.current_company = self.company; self.app.current_fiscal_year = int(year)
        self.app.main_screen(); self.app.update()

    def test_stock_card_opens_from_items(self):
        self.app.load_inventory(); self.app.update()
        rows = self.app.items_tree.get_children(); self.assertTrue(rows)
        self.app.items_tree.selection_set(rows[0])
        self.app.open_stock_card(); self.app.update()
        self.assertEqual(self.app.ir_report.get(), "Stock Card")
        self.assertFalse([m for m in self.messages if m[0] == "showerror"], self.messages)

    def test_inventory_analysis_3d_options_exist_and_run(self):
        self.assertTrue(hasattr(self.app, "ir_3d_rows"))
        self.app.ir_report.set("Inventory Analysis (3D)"); self.app.inventory_report_selected()
        options = self.app.inventory_report_options()
        self.assertEqual((options["rows"], options["columns"], options["measure"]), ("item", "warehouse", "quantity"))
        self.app.run_inventory_report(); self.app.update()
        self.assertFalse([m for m in self.messages if m[0] == "showerror"], self.messages)

    def test_mouse_wheel_scrolls_the_page_under_the_pointer(self):
        app = self.app; app.geometry("800x400"); app.update()
        page = app.main_tab_pages[app.tab_names.index("Payroll")] if "Payroll" in app.tab_names else app.main_tab_pages[-1]
        app.select_main_tab(page); app.update()
        canvas = next(child for child in page.winfo_children() if getattr(child, "_saber_scroll_page", False))
        tall = tk.Frame(canvas.winfo_children()[0] if canvas.winfo_children() else canvas, height=3000, width=10); tall.pack()
        app.update()
        event = mock.Mock(num=None, delta=-120, state=0, x_root=canvas.winfo_rootx() + 5, y_root=canvas.winfo_rooty() + 5)
        with mock.patch.object(app, "winfo_containing", return_value=canvas):
            before = canvas.yview()[0]; app._scroll_page_under_pointer(event); app.update()
        self.assertGreater(canvas.yview()[0], before)

    def test_right_click_on_account_field_opens_account_search(self):
        variable = tk.StringVar(); box = self.app.account_search_box(self.app, variable)
        opened = []
        with mock.patch.object(self.app, "open_account_lookup", side_effect=lambda var, **kwargs: opened.append((var,kwargs))):
            self.app.field_right_click(mock.Mock(widget=box, x_root=0, y_root=0)); self.app.update()
        self.assertEqual(opened, [(variable,{"include_groups":True})])

    def test_vat_account_name_selects_code_with_tab(self):
        account=next(row for row in self.app.client.accounts() if row["code"]=="44216")
        variable=tk.StringVar(value=account["name_en"])
        box=self.app.account_search_box(self.app,variable); box.pack(); box.focus_set(); self.app.update()
        box.event_generate("<Tab>"); self.app.update()
        self.assertEqual(variable.get(),"44216")
        self.assertIn("44216", " ".join(box["values"]))

    def test_import_preview_account_edits_advance_with_tab_and_offer_lookup(self):
        app=self.app; page=app.import_tab
        while page not in app.main_tab_pages: page=page.master
        app.select_main_tab(page); app.update()
        app.import_mode="excel"
        app.import_rows=[{"invoice_number":"TEST-1","invoice_date":"25-09-2026","party_name":"Supplier",
                          "currency":"USD","subtotal":100.0,"vat":11.0,"total":111.0,"source":"Excel row 2"}]
        app.populate_import_preview(); app.update()
        sheet=app.import_sheet; iid=sheet.tree.get_children()[0]
        self.assertEqual(sheet.rows[iid]["vat_account"],"44210")
        sheet.edit(iid,"vat_account"); app.update()
        editor=app.focus_get(); self.assertIsInstance(editor,tk.Entry)
        editor.delete(0,"end"); editor.insert(0,"44216")
        editor.event_generate("<Tab>"); time.sleep(0.04); app.update()
        self.assertEqual(sheet.rows[iid]["vat_account"],"44216")
        self.assertIsInstance(app.focus_get(),tk.Entry)
        with mock.patch.object(app,"open_account_lookup",side_effect=lambda variable, **kwargs: variable.set("4427")) as search:
            sheet.edit(iid,"vat_account"); app.update()
            app.focus_get().event_generate("<F2>"); app.update()
            self.assertEqual(sheet.rows[iid]["vat_account"],"4427")
            self.assertEqual(search.call_args.kwargs,{"include_groups":True})

    def test_bulk_vat_account_only_changes_confirmed_selected_rows_and_import_payload(self):
        app = self.app
        page = app.import_tab
        while page not in app.main_tab_pages: page = page.master
        app.select_main_tab(page); app.update()
        app.import_mode = "excel"
        app.import_type.set("Purchases")
        app.import_rows = [
            {"invoice_number": f"BULK-{index}", "invoice_date": "25-09-2026",
             "party_name": "Supplier", "currency": "USD", "subtotal": 100.0,
             "vat": 11.0, "total": 111.0, "source": f"Excel row {index + 2}"}
            for index in range(3)
        ]
        app.populate_import_preview(); app.update()
        sheet = app.import_sheet
        self.assertEqual(str(sheet.tree.cget("selectmode")), "extended")
        first, second, third = sheet.tree.get_children()
        app.import_cell_changed(third, "vat_account", "4427"); sheet.refresh(third)
        sheet.tree.selection_set((first, second))
        app.import_bulk_vat_account.set("44216")
        with mock.patch("tkinter.messagebox.askyesno", return_value=False):
            app.apply_selected_import_vat_account()
        self.assertEqual([sheet.rows[iid]["vat_account"] for iid in (first, second, third)],
                         ["44210", "44210", "4427"])
        with mock.patch("tkinter.messagebox.askyesno", return_value=True) as confirm:
            app.apply_selected_import_vat_account()
        self.assertIn("2 selected", confirm.call_args.args[1])
        self.assertEqual([sheet.rows[iid]["vat_account"] for iid in (first, second, third)],
                         ["44216", "44216", "4427"])
        self.assertEqual([sheet.tree.set(iid, "vat_account") for iid in (first, second, third)],
                         ["44216", "44216", "4427"])
        app.populate_import_preview(); app.update()
        self.assertEqual([row["vat_account"] for row in sheet.ordered()], ["44216", "44216", "4427"])
        with mock.patch.object(app.client, "import_invoices",
                               return_value={"imported": 3, "errors": [], "ids": []}) as upload, \
             mock.patch.object(app, "load_dashboard"), mock.patch.object(app, "load_invoices"), \
             mock.patch.object(app, "load_journal"), mock.patch.object(app, "load_trial"), \
             mock.patch.object(app, "load_transactions"):
            app.send_import()
        self.assertEqual([row["vat_account"] for row in upload.call_args.args[0]],
                         ["44216", "44216", "4427"])
        self.assertTrue(all("_vat_account_chosen" not in row for row in upload.call_args.args[0]))

    def test_bulk_vat_requires_selection_and_account_and_respects_pdf_type_changes(self):
        app = self.app
        page = app.import_tab
        while page not in app.main_tab_pages: page = page.master
        app.select_main_tab(page); app.update()
        app.import_mode = "pdf"
        app.import_rows = [
            {"invoice_number": f"PDF-{index}", "invoice_date": "25-09-2026",
             "party_name": "Supplier", "currency": "USD", "subtotal": 100.0,
             "vat": 11.0, "total": 111.0, "entry_type": "Purchases",
             "source": f"test.pdf - Page {index}"}
            for index in range(2)
        ]
        app.populate_import_preview()
        sheet = app.import_sheet
        first, second = sheet.tree.get_children()
        with mock.patch("tkinter.messagebox.askyesno") as confirm, \
             mock.patch("tkinter.messagebox.showwarning") as warning:
            app.import_bulk_vat_account.set("44216")
            app.apply_selected_import_vat_account()
            self.assertIn("Select", warning.call_args.args[1])
            sheet.tree.selection_set((first, second))
            app.import_bulk_vat_account.set("")
            app.apply_selected_import_vat_account()
            self.assertIn("Choose a VAT account", warning.call_args.args[1])
            confirm.assert_not_called()
        sheet.tree.selection_set(first)
        app.import_bulk_vat_account.set("44210")
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            app.apply_selected_import_vat_account()
        app.import_cell_changed(first, "entry_type", "Expenses")
        app.import_cell_changed(second, "entry_type", "Expenses")
        sheet.refresh(first); sheet.refresh(second)
        self.assertEqual(sheet.rows[first]["vat_account"], "44210")
        self.assertEqual(sheet.rows[second]["vat_account"], "44216")

    def test_bulk_vat_account_is_used_when_importing_pdf_invoices(self):
        app = self.app
        page = app.import_tab
        while page not in app.main_tab_pages: page = page.master
        app.select_main_tab(page); app.update()
        app.import_mode = "pdf"
        app.import_rows = [
            {"invoice_number": f"PDF-{index}", "invoice_date": "25-09-2026",
             "party_name": "Supplier", "currency": "USD", "subtotal": 100.0,
             "vat": 11.0, "total": 111.0, "entry_type": "Purchases",
             "source": f"test.pdf - Page {index}", "_path": __file__}
            for index in range(3)
        ]
        app.populate_import_preview(); app.update()
        sheet = app.import_sheet
        first, second, third = sheet.tree.get_children()
        app.import_cell_changed(third, "vat_account", "4427"); sheet.refresh(third)
        sheet.tree.selection_set((first, second))
        app.import_bulk_vat_account.set("44216")
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            app.apply_selected_import_vat_account()
        with mock.patch.object(app.client, "import_invoices",
                               return_value={"imported": 3, "errors": [], "ids": [1, 2, 3]}) as upload, \
             mock.patch.object(app.client, "upload_attachment"), \
             mock.patch.object(app, "load_dashboard"), mock.patch.object(app, "load_invoices"), \
             mock.patch.object(app, "load_journal"), mock.patch.object(app, "load_trial"), \
             mock.patch.object(app, "load_transactions"):
            app.send_import()
        self.assertEqual([row["vat_account"] for row in upload.call_args.args[0]],
                         ["44216", "44216", "4427"])

    def test_pdf_preview_type_can_be_selected_per_row(self):
        from tkinter import ttk
        app=self.app; page=app.import_tab
        while page not in app.main_tab_pages: page=page.master
        app.select_main_tab(page); app.update()
        app.import_mode="pdf"
        app.import_rows=[{"invoice_number":"A-1","invoice_date":"25-09-2026","party_name":"Supplier",
                          "currency":"USD","subtotal":100.0,"vat":11.0,"total":111.0,"entry_type":"Purchases",
                          "source":"test.pdf - Page 1"}]
        app.populate_import_preview(); app.update()
        sheet=app.import_sheet; iid=sheet.tree.get_children()[0]
        sheet.edit(iid,"entry_type"); app.update()
        editor=app.focus_get()
        self.assertIsInstance(editor,ttk.Combobox)
        self.assertEqual(editor.get(),"Purchases")
        editor.set("Assets"); editor.event_generate("<<ComboboxSelected>>"); app.update()
        self.assertEqual(sheet.rows[iid]["entry_type"],"Assets")
        self.assertEqual(sheet.rows[iid]["expense_account"],"")

    def test_edit_invoice_vat_selection_is_saved_as_account_code(self):
        app=self.app
        row={"invoice_number":"TEST-42","invoice_date":"25-09-2024","party_name":"Supplier",
             "kind":"purchase","currency":"USD","subtotal":100.0,"vat":11.0,"total":111.0,
             "supplier_account":"4011","vat_account":"44210","expense_account":"601100000","status":"review"}
        tree=app.invoice_tree  # build the lazy Invoices page before replacing its test rows
        app.invoice_rows={"42":row}
        tree.insert("","end",iid="42")
        tree.selection_set("42")
        app.edit_selected_invoice(); app.update()
        windows=[child for child in app.winfo_children() if isinstance(child,tk.Toplevel) and child.title()=="Edit Invoice TEST-42"]
        self.assertTrue(windows,(self.messages,[(child.title(),type(child).__name__) for child in app.winfo_children() if isinstance(child,tk.Toplevel)]))
        window=windows[0]
        self.addCleanup(lambda: window.destroy() if window.winfo_exists() else None)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        account_boxes=[widget for widget in descendants(window) if getattr(widget,"_account_var",None) is not None]
        self.assertEqual(len(account_boxes),4)
        for box in account_boxes:
            self.assertTrue(any(isinstance(child,tk.Button) and child.cget("text")=="Find" for child in box.master.winfo_children()))
            self.assertLessEqual(box.master.winfo_rootx()+box.master.winfo_width(),window.winfo_rootx()+window.winfo_width())
        supplier_box=account_boxes[0]
        supplier_box.focus_set(); app.update()
        self.assertTrue(supplier_box.selection_present())
        find=next(child for child in supplier_box.master.winfo_children() if isinstance(child,tk.Button) and child.cget("text")=="Find")
        find.invoke(); app.update()
        lookup=next(child for child in app.winfo_children() if isinstance(child,tk.Toplevel) and child.title()=="Find or Create Account - F2")
        search=next(child for child in descendants(lookup) if isinstance(child,tk.Entry))
        self.assertTrue(search.selection_present())
        search.delete(0,"end"); search.insert(0,"4111"); app.update()
        search.event_generate("<Return>"); app.update()
        self.assertEqual(supplier_box._account_var.get(),"4111")
        self.assertEqual(app.grab_current(),window)
        vat_box=account_boxes[1]
        vat_box.focus_set(); app.update()
        vat_box._account_var.set("VAT on Expenses - Deductible")
        vat_box.event_generate("<Tab>"); app.update()
        self.assertEqual(vat_box._account_var.get(),"44216")
        with mock.patch.object(app.client,"update_invoice") as update, \
             mock.patch.object(app,"load_invoices"),mock.patch.object(app,"load_dashboard"), \
             mock.patch.object(app,"load_journal"),mock.patch.object(app,"load_trial"):
            save=next(widget for widget in descendants(window) if isinstance(widget,tk.Button) and widget.cget("text")=="Save Update")
            save.invoke(); app.update()
            self.assertEqual(update.call_args.args[1]["vat_account"],"44216")
            self.assertEqual(update.call_args.args[1]["supplier_account"],"4111")

    def test_tab_and_enter_from_voucher_header_edit_account_cell(self):
        app = self.app
        app.select_main_tab(app.main_tab_pages[3]); app.new_manual_voucher(confirm=False); app.update()
        for key in ("<Tab>", "<Return>"):
            with self.subTest(key=key):
                app.manual_find.set("")
                app.manual_find_box.focus_set(); app.update()
                app.manual_find_box.event_generate(key)
                time.sleep(0.04); app.update()
                editor = app.focus_get()
                self.assertIsInstance(editor, tk.Entry)
                self.assertEqual(editor.master, app.voucher_sheet.tree)
                editor.event_generate("<Escape>"); app.update()

    def test_right_click_on_voucher_account_cell_or_editor_opens_f2_search(self):
        app = self.app
        app.select_main_tab(app.main_tab_pages[3]); app.new_manual_voucher(confirm=False); app.update()
        sheet = app.voucher_sheet
        iid = sheet.tree.get_children()[0]
        account_code = next(row["code"] for row in app.client.accounts() if len(str(row["code"])) == 9)
        with mock.patch.object(app, "open_account_lookup", side_effect=lambda variable: variable.set(account_code)) as search:
            x, y, _width, _height = sheet.tree.bbox(iid, "#2")
            sheet.tree.event_generate("<Button-3>", x=x+5, y=y+5); app.update()
            self.assertEqual(sheet.rows[iid]["account"], account_code)
            sheet.rows[iid]["account"] = ""; sheet.refresh(iid)
            sheet.tree.focus_set(); sheet.tree.event_generate("<F2>"); app.update()
            self.assertEqual(sheet.rows[iid]["account"], account_code)
            sheet.rows[iid]["account"] = ""; sheet.refresh(iid)
            sheet.edit(iid, "account"); app.update()
            editor = app.focus_get()
            self.assertIsInstance(editor, tk.Entry)
            editor.event_generate("<Button-3>", x=5, y=5); app.update()
            self.assertEqual(sheet.rows[iid]["account"], account_code)
            sheet.rows[iid]["account"] = ""; sheet.refresh(iid)
            sheet.edit(iid, "account"); app.update()
            app.focus_get().event_generate("<F2>"); app.update()
            self.assertEqual(sheet.rows[iid]["account"], account_code)
            self.assertEqual(search.call_count, 4)

    def test_statement_copies_account_to_second_row_and_escape_returns_dashboard(self):
        app=self.app
        index=app.tab_names.index("Accounts & Statements")
        app.show_tab_window(max(0,index-5),index)
        app.statement_tab.master.select(app.statement_tab); app.update()
        v=app.statement_state["vars"]
        code=next(row["code"] for row in app.client.accounts() if len(str(row["code"]))==9)
        v["account_to"].set("")
        v["account_from"].set(code)
        self.assertEqual(v["account_to"].get(),code)
        self.assertEqual(v["account_to_name"].get(),app._all_accounts[code])
        v["account_from_box"].focus_set(); app.update()
        v["account_from_box"].event_generate("<Escape>"); app.update()
        self.assertEqual(app.main_notebook.select(),str(app.main_tab_pages[0]))

    def test_right_click_on_plain_field_offers_searches(self):
        entry = tk.Entry(self.app); shown = []
        with mock.patch.object(tk.Menu, "tk_popup", side_effect=lambda *a: shown.append(True)):
            self.app.field_right_click(mock.Mock(widget=entry, x_root=0, y_root=0))
        self.assertEqual(shown, [True])

    def _toplevel(self, title_part):
        return next(w for w in self.app.winfo_children() if isinstance(w, tk.Toplevel) and title_part in w.title())

    def _button(self, window, text):
        stack = [window]
        while stack:
            widget = stack.pop()
            if isinstance(widget, tk.Button) and widget.cget("text") == text: return widget
            stack.extend(widget.winfo_children())
        raise AssertionError(f"button {text!r} not found")

    def test_automatic_doe_posts_one_voucher_per_currency(self):
        api = self.app.client; year = self.app.current_fiscal_year
        for currency, account, amount in (("USD", "4011", "100"), ("USD", "4111", "50"), ("EUR", "5121", "200")):
            try: api.save_journal_voucher({"entry_date": f"01-03-{year}", "description": f"{currency} balance", "currency": currency, "voucher_type": "01"},
                                          [{"account_code": account, "debit": amount}, {"account_code": "211", "credit": amount}])
            except RuntimeError: api.save_journal_voucher({"entry_date": f"01-03-{year}", "description": f"{currency} balance", "currency": currency, "voucher_type": "01"},
                                          [{"account_code": account, "debit": amount}, {"account_code": "101", "credit": amount}])
        self.app.manual_date.set(f"30-09-{year}"); self.app.show_doe_page(); self.app.update()
        page = self._toplevel("DOE")
        entries = [w for w in page.winfo_children()[1].winfo_children() if w.winfo_class() == "Entry"]
        self.assertEqual(len(entries), 2)  # one rate per foreign currency (USD, EUR)
        for entry in entries: entry.delete(0, "end"); entry.insert(0, "999999")
        self._button(page, "Preview").invoke(); self._button(page, "Post DOE vouchers").invoke(); self.app.update()
        self.assertFalse([m for m in self.messages if m[0] in ("showerror", "showwarning")], self.messages)
        info = [m for m in self.messages if m[0] == "showinfo"][-1][1][1]
        self.assertIn("Posted 2 LBP DOE voucher(s)", info); self.assertIn("EUR", info); self.assertIn("USD", info)

    def test_usd_books_doe_for_one_selected_currency(self):
        api = self.app.client; year = self.app.current_fiscal_year
        api.save_journal_voucher({"entry_date": f"01-03-{year}", "description": "LBP balance", "currency": "LBP", "voucher_type": "01"},
                                 [{"account_code": "531", "debit": "895000000"}, {"account_code": "211", "credit": "895000000"}])
        self.app.manual_date.set(f"30-09-{year}"); self.app.show_doe_page(); self.app.update()
        page = self._toplevel("DOE")
        combos = [w for w in page.winfo_children()[0].winfo_children() if w.winfo_class() == "TCombobox"]
        combos[0].set("USD"); combos[0].event_generate("<<ComboboxSelected>>"); self.app.update()
        self.assertIn("LBP", combos[1]["values"])
        combos[1].set("LBP"); combos[1].event_generate("<<ComboboxSelected>>"); self.app.update()
        entries = [w for w in page.winfo_children()[1].winfo_children() if w.winfo_class() == "Entry"]
        self.assertEqual(len(entries), 1)
        entries[0].delete(0, "end"); entries[0].insert(0, "100000")
        self._button(page, "Preview").invoke(); self._button(page, "Post DOE vouchers").invoke(); self.app.update()
        self.assertFalse([m for m in self.messages if m[0] in ("showerror", "showwarning")], self.messages)
        self.assertIn("Posted 1 USD DOE voucher(s)", [m for m in self.messages if m[0] == "showinfo"][-1][1][1])
        row = next(r for r in api.doe_candidates(f"30-09-{year}", "USD")["items"] if r["account"] == "531")
        self.assertAlmostEqual(float(row["carrying_usd"]), float(row["balance"]) / 100000, places=2)

    def test_legal_document_saved_with_dates_and_no_file(self):
        api = self.app.client
        party = api.save_party({"kind": "customer", "name": "Docs Client"}) if hasattr(api, "save_party") else None
        self.assertIsNotNone(party)
        self.app.load_parties_page(); self.app.update()
        iid = next(i for i in self.app.parties_tree.get_children() if self.app.parties_tree.item(i, "values")[2] == "Docs Client")
        self.app.parties_tree.selection_set(iid); self.app.party_documents_dialog(); self.app.update()
        window = self._toplevel("Legal Documents")
        date_entries = [w for w in window.winfo_children()[0].winfo_children() if w.winfo_class() == "Entry"]
        date_entries[0].insert(0, "01-01-2026"); date_entries[1].insert(0, "31-12-2027")
        self._button(window, "Save").invoke(); self.app.update()
        self.assertFalse([m for m in self.messages if m[0] == "showerror"], self.messages)
        saved = api.party_documents(party["id"])
        self.assertEqual((saved[0]["issue_date"], saved[0]["expiry_date"], saved[0]["file_name"]), ("01-01-2026", "31-12-2027", ""))

    def test_digits_typed_in_any_date_field_get_dashes(self):
        frame = tk.Frame(self.app); tk.Label(frame, text="Date From").pack(); entry = tk.Entry(frame); entry.pack()
        plain = tk.Frame(self.app); tk.Label(plain, text="Quantity").pack(); qty = tk.Entry(plain); qty.pack()
        for widget in (entry, qty):
            widget.insert(0, "31122025"); self.app._auto_dash_any_date(mock.Mock(widget=widget, keysym="5"))
        self.assertEqual(entry.get(), "31-12-2025"); self.assertEqual(qty.get(), "31122025")

    def test_item_cost_is_a_link_to_the_stock_card(self):
        self.app.load_inventory(); self.app.update()
        self.app.items_tree.selection_set(self.app.items_tree.get_children()[0])
        with mock.patch.object(self.app, "open_stock_card") as opened:
            self.app.item_cost_label.event_generate("<Button-1>"); self.app.update()
            self.app.open_item_cost_link()
        self.assertTrue(opened.called)

    def test_program_opens_on_the_dashboard_first_and_builds_the_rest(self):
        self.app.build_pending_pages(); self.app.update()  # as on a slower PC: the previous screen is complete
        self.app.main_screen()
        self.assertTrue(self.app.__dict__.get("_pending_builders"))  # the other pages are still waiting
        self.assertTrue(hasattr(self.app, "payroll_tree"))          # needing one builds them at once
        self.assertFalse(self.app.__dict__.get("_pending_builders"))

    def test_transport_days_fill_the_transport_amount(self):
        api = self.app.client; api.apply_lebanese_payroll_rules()
        api.save_employee({"employee_number": "7000", "full_name": "Transport Emp", "currency": "LBP", "base_salary": "40000000"})
        self.app.load_payroll(); self.app.load_payroll_settings(); self.app.update()
        label = next(k for k in self.app.payroll_employee_map if "Transport Emp" in k)
        self.app.payroll_employee.set(label); self.app.payroll_period.set("31-03-2026")
        self.app.payroll_transport_days.set("20"); self.app.payroll_transport_from_days()
        self.assertEqual(self.app.payroll_vars["transport"].get(), "9000000")  # 20 days x 450,000 LBP

    def test_family_allocation_shows_automatically_and_can_be_edited(self):
        api = self.app.client; api.apply_lebanese_payroll_rules()
        api.save_employee({"employee_number": "7100", "full_name": "Family Emp", "currency": "LBP", "base_salary": "40000000",
                           "marital_status": "married", "children": "2"})
        self.app.load_payroll(); self.app.update()
        label = next(k for k in self.app.payroll_employee_map if "Family Emp" in k)
        self.app.payroll_period.set("31-05-2026"); self.app.payroll_employee.set(label); self.app.payroll_employee_chosen()
        self.assertEqual(self.app.payroll_family_override.get(), "4410000")  # 2,100,000 spouse + 2 x 1,155,000
        self.assertNotIn("family_allowance_override", self.app.payroll_payload())
        self.app.payroll_family_override.set("3000000"); self.app._family_manual = True
        self.assertEqual(self.app.payroll_payload()["family_allowance_override"], "3000000")
        self.app.calculate_payroll(); self.assertEqual(self.app.payroll_family_override.get(), "3000000")


if __name__ == "__main__":
    unittest.main()
