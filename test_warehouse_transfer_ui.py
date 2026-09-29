"""The warehouse-transfer shortcut uses the existing stock-document posting flow."""

import unittest
from unittest.mock import Mock, patch

from desktop_inventory import InventoryMixin


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class WarehouseTransferUiTest(unittest.TestCase):
    def make_ui(self):
        ui = InventoryMixin()
        ui.sd_vars = {
            "type": Value("Stock Receipt"),
            "warehouse": Value("MAIN - Main"),
            "to_warehouse": Value(""),
        }
        ui.warehouse_rows = [
            {"code": "MAIN", "name": "Main", "active": True},
            {"code": "WH2", "name": "Second", "active": True},
        ]
        ui.inventory_notebook_select = Mock()
        ui.new_stock_document = Mock()
        ui.client = Mock()
        return ui

    def test_shortcut_opens_transfer_with_distinct_warehouses(self):
        ui = self.make_ui()
        ui.new_warehouse_transfer()
        ui.inventory_notebook_select.assert_called_once_with("Stock Documents")
        ui.new_stock_document.assert_called_once_with()
        self.assertEqual(ui.sd_vars["type"].get(), "Transfer")
        self.assertEqual(ui.sd_vars["warehouse"].get(), "MAIN - Main")
        self.assertEqual(ui.sd_vars["to_warehouse"].get(), "WH2 - Second")

    @patch("desktop_inventory.messagebox.showwarning")
    def test_shortcut_requires_two_active_warehouses(self, warning):
        ui = self.make_ui()
        ui.warehouse_rows[1]["active"] = False
        ui.new_warehouse_transfer()
        ui.inventory_notebook_select.assert_not_called()
        ui.new_stock_document.assert_not_called()
        warning.assert_called_once()

    @patch("desktop_inventory.messagebox.showwarning")
    def test_save_rejects_same_warehouse_before_posting(self, warning):
        ui = self.make_ui()
        ui.sd_vars["type"].set("Transfer")
        ui.sd_vars["to_warehouse"].set("MAIN - Main")
        ui.stock_sheet = Mock()
        ui.stock_sheet.ordered.return_value = [{"sku": "SKU1", "quantity": 1}]
        ui.save_stock_document()
        ui.client.save_stock_document.assert_not_called()
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()