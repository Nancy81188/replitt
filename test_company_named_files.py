"""Company data files are named after the company: companies/<Company Name>/<Company Name>_<year>.db,
like the backups (backups/<Company Name>/<year>/<Company Name>_<year>_<date>.db)."""
import tempfile
import unittest
from pathlib import Path

from company_manager import CompanyManager
from database import Database


class CompanyNamedFilesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.root = Path(self.folder.name)
        self.master = Database(self.root / "saber_accounting_v0_7.db"); self.master.initialize("secret")
        self.manager = CompanyManager(self.root / "saber_accounting_v0_7.db")
        company = self.manager.list_companies()[0]
        self.manager.database(company["id"], 2024).create_manual_invoice({"invoice_date": "15-03-2024", "party_name": "C", "kind": "sales", "currency": "USD", "status": "posted"},
                                                                         [{"description": "S", "quantity": 1, "unit_price": 1000}], 1)

    def tearDown(self): self.folder.cleanup()

    def test_existing_files_are_moved_to_company_named_folders_with_their_data(self):
        moved = self.manager.organize_files()
        self.assertEqual(len(moved), 1)
        company = self.manager.list_companies()[0]; path = Path(company["years"][0]["database"])
        self.assertEqual((path.parent.name, path.name), ("ECOLOGE LEBANON SARL", "ECOLOGE LEBANON SARL_2024.db"))
        fresh = CompanyManager(self.root / "saber_accounting_v0_7.db")
        self.assertEqual(len(fresh.database(company["id"], 2024).list_invoices()), 1)
        self.assertTrue((self.root / "saber_accounting_v0_7.db").exists())  # users and passwords stay in the main file
        self.assertEqual(self.manager.organize_files(), [])                 # nothing left to move

    def test_new_company_and_new_year_use_the_company_name(self):
        created = self.manager.create_company({"name": "MDCC International L.L.C", "year": 2025}, self.master)
        path = Path(created["years"][0]["database"])
        self.assertEqual((path.parent.name, path.name), ("MDCC International L.L.C", "MDCC International L.L.C_2025.db"))
        self.assertEqual(self.manager.database(created["id"], 2025).backup_label, "MDCC International L.L.C_2025")

    def test_renamed_company_files_and_backups_follow_the_new_name(self):
        self.manager.organize_files(); company = self.manager.list_companies()[0]
        backup = Path(self.manager.database(company["id"], 2024).backup())
        self.assertEqual(backup.parent.parent.name, "ECOLOGE LEBANON SARL")
        renamed = self.manager.update_company(company["id"], {"name": "Ecologe Lebanon"})
        path = Path(renamed["years"][0]["database"])
        self.assertEqual((path.parent.name, path.name), ("Ecologe Lebanon", "Ecologe Lebanon_2024.db"))
        self.assertTrue((self.root / "backups" / "Ecologe Lebanon" / "2024" / backup.name).exists())
        self.assertEqual(len(self.manager.database(company["id"], 2024).list_invoices()), 1)


if __name__ == "__main__":
    unittest.main()
