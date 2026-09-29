"""Creating an account from Find must select it without leaving the entry form."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from tkinter import ttk
from unittest.mock import Mock

from desktop import SaberApp, row_matches_search


class AccountLookupCreationTests(unittest.TestCase):
    def setUp(self):
        self.app = SimpleNamespace(client=Mock(), accounts_tree=object(), load_accounts=Mock(), _account_cache={"old": True})
        self.field = Mock()
        self.app.client.save_account.return_value = {"code": "601100003", "name_en": "Office Rent"}

    def test_create_under_parent_assigns_number_and_selects_it(self):
        self.app._all_accounts = {"6011": "Operating Expenses"}
        account = SaberApp.create_account_in_lookup(self.app, "6011 - Operating Expenses", " Office Rent ", "expense", self.field)
        self.assertEqual(account["code"], "601100003")
        self.app.client.save_account.assert_called_once_with({
            "code": "", "parent_code": "6011", "name_en": "Office Rent", "type": "expense",
        })
        self.field.set.assert_called_once_with("601100003")
        self.assertIsNone(self.app._account_cache)
        self.assertEqual(self.app._all_accounts["601100003"], "Office Rent")
        self.app.load_accounts.assert_called_once()

    def test_invalid_parent_or_name_does_not_create_an_account(self):
        for parent, name, account_type in (("601", "Office Rent", "expense"), ("6011", "", "expense"),
                                          ("6011", "Office Rent", "")):
            with self.subTest(parent=parent, name=name, account_type=account_type):
                with self.assertRaises(ValueError):
                    SaberApp.create_account_in_lookup(self.app, parent, name, account_type, self.field)
        self.app.client.save_account.assert_not_called()
        self.field.set.assert_not_called()

    def test_find_matches_separate_terms_across_number_and_multilingual_names(self):
        values = ("601100003", "Office Rent", "إيجار المكتب", "Loyer bureau", "expense")
        self.assertTrue(row_matches_search(values, "6011 rent"))
        self.assertTrue(row_matches_search(values, "إيجار المكتب"))
        self.assertTrue(row_matches_search(values, "loyer 6011"))
        self.assertFalse(row_matches_search(values, "6011 salary"))

    def test_find_window_creates_account_from_same_window_when_display_available(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("a Tk display is not available")
        try:
            root.geometry("400x300+0+0")
            root.client = Mock()
            root.client.accounts.return_value = [
                {"code": "6011", "name_en": "Operating Expenses", "name_ar": "", "name_fr": "", "type": "expense"},
                {"code": "601100001", "name_en": "Utilities", "name_ar": "خدمات", "name_fr": "", "type": "expense"},
            ]
            root.client.next_account_number.return_value = "601100003"
            root.client.save_account.return_value = {"code": "601100003", "name_en": "Office Rent"}
            root.action_button = lambda parent, text, command: SaberApp.action_button(root, parent, text, command)
            root.create_account_in_lookup = lambda parent, name, kind, field: SaberApp.create_account_in_lookup(root, parent, name, kind, field)
            field = tk.StringVar(master=root)
            SaberApp.open_account_lookup(root, field)
            window = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
            root.update()
            self.assertLessEqual(window.winfo_width(), root.winfo_screenwidth())
            self.assertLessEqual(window.winfo_height(), root.winfo_screenheight())

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            widgets = list(descendants(window))
            parent_box = next(widget for widget in widgets if isinstance(widget, ttk.Combobox) and widget.cget("width") == 26)
            name_entry = next(widget for widget in widgets if isinstance(widget, tk.Entry) and widget.grid_info() and widget.grid_info()["column"] == 3)
            create_button = next(widget for widget in widgets if isinstance(widget, tk.Button) and widget.cget("text") == "Create & Select")
            for widget in (parent_box, name_entry, create_button):
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), window.winfo_rootx() + window.winfo_width())
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), window.winfo_rooty() + window.winfo_height())
            parent_box.set("6011 - Operating Expenses")
            parent_box.event_generate("<<ComboboxSelected>>")
            name_entry.insert(0, "Office Rent")
            create_button.invoke()
            self.assertEqual(field.get(), "601100003")
            self.assertFalse(window.winfo_exists())
            root.client.save_account.assert_called_once()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()