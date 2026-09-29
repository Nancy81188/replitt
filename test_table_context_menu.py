"""Right-click on any listing table exposes Search / Clear search.

The table() widget wiring lives in a real tkinter Treeview, which cannot be
instantiated in a headless environment (no display). We therefore guard the
feature by inspecting the shared table() source so the right-click access
cannot be silently removed.
"""
import inspect
import unittest

import desktop


class TableContextMenuTests(unittest.TestCase):
    def setUp(self):
        self.source = inspect.getsource(desktop.DesktopMixin.table) \
            if hasattr(desktop, "DesktopMixin") else self._find_table_source()

    def _find_table_source(self):
        for name in dir(desktop):
            obj = getattr(desktop, name)
            if isinstance(obj, type) and hasattr(obj, "table"):
                try:
                    return inspect.getsource(obj.table)
                except (OSError, TypeError):
                    continue
        self.fail("could not locate the shared table() method source")

    def test_context_menu_is_created(self):
        self.assertIn("tk.Menu", self.source,
                      "table() must build a context menu")

    def test_context_menu_has_search_and_clear_entries(self):
        self.assertIn("add_command", self.source)
        self.assertIn("Search", self.source,
                      "context menu must offer a Search entry")
        self.assertIn("Clear search", self.source,
                      "context menu must offer a Clear search entry")

    def test_right_click_bindings_are_wired(self):
        # Button-3 = right-click on Windows/Linux; Button-2 = macOS trackpad.
        self.assertIn("<Button-3>", self.source,
                      "right-click (Button-3) must open the context menu")
        self.assertIn("<Button-2>", self.source,
                      "macOS right-click (Button-2) must open the context menu")

    def test_search_entry_focus_helper_present(self):
        # Selecting "Search…" should focus the search box for the table.
        self.assertIn("focus_set", self.source,
                      "Search entry must focus the search box")


if __name__ == "__main__":
    unittest.main()
