"""Visibility is only a display setting; stored journal values remain available."""
import unittest

from desktop_brains import EditableSheet
from desktop_dimensions import DimensionsMixin


class FakeVar:
    def __init__(self, value): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


class FakeWidget:
    def __init__(self): self.packed = True
    def winfo_exists(self): return True
    def winfo_manager(self): return "pack" if self.packed else ""
    def pack(self, **_kwargs): self.packed = True
    def pack_forget(self): self.packed = False


class FakeTree:
    def __init__(self): self.displaycolumns = ()
    def configure(self, **kwargs): self.displaycolumns = kwargs["displaycolumns"]
    def winfo_exists(self): return True


class DimensionVisibilityTests(unittest.TestCase):
    def test_independent_visibility_preserves_journal_values(self):
        sheet = object.__new__(EditableSheet)
        sheet.columns = [(key, key, 80, "w") for key in ("account", "department", "project", "amount")]
        sheet.tree = FakeTree()
        sheet.rows = {"row": {"account": "101", "department": "HQ", "project": "A", "amount": 50}}
        app = object.__new__(DimensionsMixin)
        app.show_department = FakeVar(False)
        app.show_project = FakeVar(True)
        department = FakeVar("All"); project = FakeVar("All")
        dep_group = FakeWidget(); project_group = FakeWidget()
        app._dimension_groups = [(dep_group, project_group, department, project, True)]
        app._dimension_sheets = [sheet]
        app.toggle_dimensions()
        self.assertFalse(dep_group.packed)
        self.assertTrue(project_group.packed)
        self.assertEqual(sheet.tree.displaycolumns, ["account", "project", "amount"])
        self.assertEqual(sheet.rows["row"]["department"], "HQ")
        app.show_department.set(True); app.show_project.set(False)
        app.toggle_dimensions()
        self.assertTrue(dep_group.packed)
        self.assertFalse(project_group.packed)
        self.assertEqual(sheet.tree.displaycolumns, ["account", "department", "amount"])
        self.assertEqual(sheet.rows["row"]["project"], "A")


if __name__ == "__main__": unittest.main()
