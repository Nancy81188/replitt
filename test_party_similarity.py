"""Duplicate-party suggestions must warn before saving without blocking distinct names."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from party_similarity import normalize_party_name, similar_parties


class PartySimilarityTests(unittest.TestCase):
    def test_normalization_and_ninety_percent_boundary(self):
        self.assertEqual(normalize_party_name("  شَرِكَةُ أَحْمَد ـ  "), "شركه احمد")
        parties = [
            {"id": 1, "name": "abcdefghij", "kind": "customer", "account_number": "411100001"},
            {"id": 2, "name": "abcdefghiX", "kind": "customer", "account_number": "411100002"},
            {"id": 3, "name": "abcdefghXY", "kind": "customer", "account_number": "411100003"},
        ]
        self.assertEqual({row["id"] for row in similar_parties("abcdefghij", parties)}, {1, 2})
        self.assertEqual({row["id"] for row in similar_parties("abcdefghij", parties, exclude_id=1)}, {2})
        self.assertTrue(similar_parties("شركة أحمد", [{"id": 4, "name": "شركه احمد", "kind": "supplier"}])[0]["exact"])

    @staticmethod
    def _app(existing):
        values = {"party_name": "Acme Tradin", "party_kind": "client", "party_account_number": "",
                  "party_tax": "", "party_mof": "", "party_address": "", "party_contact": "",
                  "party_currency": "USD", "party_due_days": "0"}
        app = SimpleNamespace(edit_party_id=None, client=Mock(), load_parties_page=Mock(), load_statement_parties=Mock())
        for field, value in values.items():
            setattr(app, field, Mock(get=Mock(return_value=value)))
        app.client.parties.return_value = existing
        app.client.save_party.return_value = {"id": 7, "account_number": "411100007"}
        return app

    def test_near_match_can_be_reviewed_or_saved_after_confirmation(self):
        from desktop import SaberApp

        app = self._app([{"id": 1, "name": "Acme Trading", "kind": "customer", "account_number": "411100001"}])
        with patch("desktop.messagebox.askyesno", return_value=False) as confirm, \
             patch("desktop.messagebox.showwarning") as warning, \
             patch("desktop.messagebox.showerror") as error, \
             patch("desktop.messagebox.showinfo") as info:
            SaberApp.save_party(app)
            self.assertIn("Acme Trading", confirm.call_args.args[1])
            self.assertIn("411100001", confirm.call_args.args[1])
            app.client.save_party.assert_not_called()
            confirm.return_value = True
            SaberApp.save_party(app)
            app.client.save_party.assert_called_once()
            app.load_parties_page.assert_called_once()
            warning.assert_not_called()
            error.assert_not_called()
            info.assert_called_once()

    def test_exact_name_does_not_silently_update_existing_party(self):
        from desktop import SaberApp

        app = self._app([{"id": 1, "name": "ACME TRADIN", "kind": "customer", "account_number": "411100001"}])
        with patch("desktop.messagebox.askyesno") as confirm, \
             patch("desktop.messagebox.showwarning") as warning, \
             patch("desktop.messagebox.showerror") as error, \
             patch("desktop.messagebox.showinfo") as info:
            SaberApp.save_party(app)
            warning.assert_called_once()
            confirm.assert_not_called()
            app.client.save_party.assert_not_called()
            error.assert_not_called()
            info.assert_not_called()

    def test_editing_same_party_does_not_warn_about_itself(self):
        from desktop import SaberApp

        app = self._app([{"id": 1, "name": "Acme Tradin", "kind": "customer", "account_number": "411100001"}])
        app.edit_party_id = 1
        with patch("desktop.messagebox.askyesno") as confirm, \
             patch("desktop.messagebox.showwarning") as warning, \
             patch("desktop.messagebox.showerror") as error, \
             patch("desktop.messagebox.showinfo"):
            SaberApp.save_party(app)
            app.client.save_party.assert_called_once()
            self.assertEqual(app.client.save_party.call_args.args[0]["id"], 1)
            confirm.assert_not_called()
            warning.assert_not_called()
            error.assert_not_called()


if __name__ == "__main__":
    unittest.main()