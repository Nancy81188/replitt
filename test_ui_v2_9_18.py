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
        with mock.patch.object(self.app, "open_account_lookup", side_effect=lambda var: opened.append(var)):
            self.app.field_right_click(mock.Mock(widget=box, x_root=0, y_root=0)); self.app.update()
        self.assertEqual(opened, [variable])

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
