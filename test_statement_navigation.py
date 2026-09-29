"""Statement account range defaults and keyboard navigation."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from desktop_brains import BrainsScreensMixin


class Value:
    def __init__(self, value=""):
        self.value=value

    def get(self):
        return self.value

    def set(self, value):
        self.value=value


class StatementNavigationTests(unittest.TestCase):
    def test_known_start_account_fills_second_row_without_overwriting_custom_range(self):
        app=BrainsScreensMixin()
        app._all_accounts={"6011":"Expenses","601100001":"Utilities","601100002":"Rent"}
        v={"account_from":Value(""),"account_to":Value(""),"_auto_account_to":None}

        v["account_from"].set("601100001")
        app.statement_account_from_changed(v)
        self.assertEqual(v["account_to"].get(),"601100001")
        v["account_from"].set("601100002 - Rent")
        app.statement_account_from_changed(v)
        self.assertEqual(v["account_to"].get(),"601100002")

        v["account_to"].set("6011")
        v["account_from"].set("601100001")
        app.statement_account_from_changed(v)
        self.assertEqual(v["account_to"].get(),"6011")
        v["account_to"].set("")
        app.statement_account_from_changed(v)
        self.assertEqual(v["account_to"].get(),"601100001")

    def test_partial_or_unknown_account_does_not_fill_second_row(self):
        app=BrainsScreensMixin()
        app._all_accounts={"601100001":"Utilities"}
        v={"account_from":Value("6011000"),"account_to":Value(""),"_auto_account_to":None}
        app.statement_account_from_changed(v)
        self.assertEqual(v["account_to"].get(),"")

    def test_escape_from_nested_statement_result_returns_dashboard_only(self):
        app=BrainsScreensMixin()
        app.statement_tab=SimpleNamespace(master=None)
        app.show_tab_window=Mock()
        result_widget=SimpleNamespace(master=SimpleNamespace(master=app.statement_tab))
        self.assertEqual(app.statement_escape(SimpleNamespace(widget=result_widget)),"break")
        app.show_tab_window.assert_called_once_with(0,0)
        app.show_tab_window.reset_mock()
        self.assertIsNone(app.statement_escape(SimpleNamespace(widget=SimpleNamespace(master=None))))
        app.show_tab_window.assert_not_called()


if __name__ == "__main__":
    unittest.main()