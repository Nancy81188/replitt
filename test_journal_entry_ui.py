"""Journal entry behavior that must work before the voucher is saved."""
import unittest

from desktop_brains import BrainsScreensMixin, currency_from_prefix


class FakeTree:
    def get_children(self):
        return ("first", "second")


class FakeSheet:
    def __init__(self):
        self.rows = {"first": {"description": ""}, "second": {"description": ""}}
        self.tree = FakeTree()
        self.refreshed = []

    def refresh(self, iid):
        self.refreshed.append(iid)


class JournalEntryUiTest(unittest.TestCase):
    def test_currency_first_letter_selects_full_code(self):
        codes = ["USD", "LBP", "EUR", "AED"]
        self.assertEqual(currency_from_prefix("l", codes), "LBP")
        self.assertEqual(currency_from_prefix("U", codes), "USD")
        self.assertEqual(currency_from_prefix("eur", codes), "EUR")
        self.assertEqual(currency_from_prefix("x", codes), "X")

    def test_detail_inherits_then_second_line_can_be_changed_alone(self):
        journal = BrainsScreensMixin()
        journal.voucher_sheet = FakeSheet()
        journal.recalculate_voucher_line = lambda row: row
        journal.update_manual_totals = lambda: None
        journal.voucher_line_selected = lambda selection: None
        journal.voucher_cell_changed("first", "description", "Original detail")
        self.assertEqual(journal.voucher_sheet.rows["second"]["description"], "Original detail")
        journal.voucher_cell_changed("second", "description", "Different detail")
        self.assertEqual(journal.voucher_sheet.rows["first"]["description"], "Original detail")
        journal.voucher_cell_changed("first", "description", "Updated first")
        self.assertEqual(journal.voucher_sheet.rows["second"]["description"], "Different detail")


if __name__ == "__main__":
    unittest.main()
