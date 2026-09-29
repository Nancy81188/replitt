"""Customer / supplier legal documents: the "Applies" tick, issue / expiry dates saved without a file,
editing a saved document, and alerts only for documents that apply."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from database import Database


class LegalDocumentsAppliesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self.folder.name) / "t.db"); self.db.initialize("secret")
        self.user = self.db.user_for_token(self.db.login("admin", "secret")["token"])["id"]
        self.party = self.db.save_party({"kind": "customer", "name": "Client"}, self.user)

    def tearDown(self): self.folder.cleanup()

    def test_dates_are_saved_without_a_file(self):
        doc_id = self.db.add_party_document(self.party["id"], {"document_type": "Commercial Registration", "issue_date": "01-01-2026", "expiry_date": "31-12-2026"}, b"", self.user)
        row = self.db.list_party_documents(self.party["id"])[0]
        self.assertEqual((row["id"], row["issue_date"], row["expiry_date"], row["file_name"], row["active"]), (doc_id, "01-01-2026", "31-12-2026", "", 1))

    def test_edit_dates_tick_and_attach_file_later(self):
        doc_id = self.db.add_party_document(self.party["id"], {"document_type": "Contract", "expiry_date": "01-02-2026"}, b"", self.user)
        self.db.update_party_document(doc_id, {"document_type": "Contract", "issue_date": "01-02-2026", "expiry_date": "01-02-2027", "active": False}, b"", self.user)
        row = self.db.list_party_documents(self.party["id"])[0]
        self.assertEqual((row["issue_date"], row["expiry_date"], row["active"], row["file_name"]), ("01-02-2026", "01-02-2027", 0, ""))
        self.db.update_party_document(doc_id, {"document_type": "Contract", "expiry_date": "01-02-2027", "active": True, "file_name": "c.pdf", "mime_type": "application/pdf"}, b"%PDF", self.user)
        row = self.db.list_party_documents(self.party["id"])[0]
        self.assertEqual((row["file_name"], row["size"], row["active"]), ("c.pdf", 4, 1))
        self.assertEqual(self.db.get_party_document(doc_id)["content"], b"%PDF")

    def test_bad_dates_are_refused(self):
        with self.assertRaisesRegex(ValueError, "Expiry date cannot be before"):
            self.db.add_party_document(self.party["id"], {"issue_date": "10-10-2026", "expiry_date": "01-01-2026"}, b"", self.user)
        with self.assertRaisesRegex(ValueError, "Issue date must be a date"):
            self.db.add_party_document(self.party["id"], {"issue_date": "someday"}, b"", self.user)

    def test_alerts_skip_documents_that_do_not_apply(self):
        today = datetime(2026, 9, 24).strftime("%d-%m-%Y")
        self.db.add_party_document(self.party["id"], {"document_type": "Contract", "expiry_date": "01-09-2026"}, b"", self.user)
        off = self.db.add_party_document(self.party["id"], {"document_type": "ID / Passport", "expiry_date": "01-09-2026", "active": False}, b"", self.user)
        alerts = self.db.legal_document_alerts(30, today)
        self.assertEqual([row["document_type"] for row in alerts["items"]], ["Contract"])
        self.db.update_party_document(off, {"document_type": "ID / Passport", "expiry_date": "01-09-2026", "active": True}, b"", self.user)
        self.assertEqual(self.db.legal_document_alerts(30, today)["expired"], 2)


if __name__ == "__main__":
    unittest.main()
