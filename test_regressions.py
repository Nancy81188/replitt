"""Regression checks for data safety and self-service backups."""
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from backup_service import backup_all
from client import ApiClient
from database import Database
from server import run_server
from pdf_import import read_invoice_pdf_pages


class DataSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.database = Path(cls.folder.name) / "saber_accounting_v0_7.db"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0)); cls.port = probe.getsockname()[1]
        cls.url = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=run_server, kwargs={"host":"127.0.0.1","port":cls.port,"database":str(cls.database),"admin_password":"secret12345"}, daemon=True).start()
        for _ in range(100):
            try: ApiClient(cls.url).login("admin", "secret12345"); break
            except Exception: time.sleep(.05)

    @classmethod
    def tearDownClass(cls): cls.folder.cleanup()

    def company_database(self):
        from company_manager import CompanyManager
        return CompanyManager(self.database).list_companies(True)[0]["years"][0]["database"]

    def test_replacement_failure_preserves_invoice_and_journal(self):
        admin=ApiClient(self.url); admin.login("admin","secret12345")
        company=admin.companies()[0]; admin.select_company_year(company["id"],2024)
        admin.create_manual_invoice({"invoice_date":"01-03-2024","party_name":"Client","kind":"sale","currency":"USD"},
                                    [{"description":"Service","quantity":1,"unit_price":100}])
        voucher=admin.save_journal_voucher({"entry_date":"01-03-2024","description":"Keep me","currency":"USD"},
            [{"account_code":"511","debit":20,"credit":0},{"account_code":"512","debit":0,"credit":20}])
        before=len(admin.invoices())
        with self.assertRaisesRegex(RuntimeError,"Replacement cancelled"):
            admin.import_invoices([{"invoice_number":"broken","invoice_date":"not a date"}], True)
        self.assertEqual(len(admin.invoices()),before)
        self.assertTrue(admin.journal_voucher(voucher["voucher"]["id"]))
        valid={"invoice_number":"new","invoice_date":"02-03-2024","party_name":"Client","kind":"sale","currency":"USD","subtotal":100,"vat":11,"total":111}
        result=admin.import_invoices([valid],True)
        self.assertEqual(result["imported"],1)
        self.assertEqual(len(admin.invoices()),1)
        self.assertTrue(admin.journal_voucher(voucher["voucher"]["id"]))

    def test_invalid_company_rejected_and_user_can_export_backup(self):
        admin=ApiClient(self.url); admin.login("admin","secret12345")
        company=admin.companies()[0]; admin.select_company_year(company["id"],2024)
        admin.save_user({"username":"staff","password":"staff12345","role":"accountant"})
        staff=ApiClient(self.url); staff.login("staff","staff12345"); staff.select_company_year(company["id"],2024)
        name=Path(staff.create_backup()["path"]).name
        self.assertIn(name,[b["name"] for b in staff.backups()])
        self.assertTrue(staff.download_backup(name)["content"].startswith(b"SQLite format 3"))
        staff.select_company_year("wrong-company",2024)
        with self.assertRaisesRegex(RuntimeError,"Company not found"): staff.invoices()

    def test_background_backup_runs_without_application(self):
        created=backup_all(self.database)
        self.assertTrue(created)
        self.assertEqual(backup_all(self.database),[])

    def test_failed_payment_edit_preserves_existing_record(self):
        db=Database(self.company_database())  # 2.9.20: company data is in companies/<Company Name>/
        user=db.user_for_token(db.login("admin","secret12345")["token"])["id"]
        party=db.save_party({"kind":"customer","name":"Edit Safety Client"},user)
        original={"kind":"customer_receipt","party_id":party["id"],"payment_date":"03-03-2024","amount":"50","currency":"USD"}
        payment_id=db.add_payment(original,user)
        with self.assertRaises(ValueError):
            db.update_payment(payment_id,{**original,"amount":"0"},user)
        self.assertTrue(any(row["id"]==payment_id for row in db.list_payments()))

    def test_pdf_pages_make_distinct_invoices_and_keep_scans_visible(self):
        from reportlab.pdfgen import canvas
        output=Path(self.folder.name)/"many.pdf"
        pdf=canvas.Canvas(str(output))
        for number in (101,102):
            pdf.drawString(30,750,f"Invoice No: {number}")
            pdf.drawString(30,730,"Date: 12-03-2024")
            pdf.drawString(30,710,"Subtotal 100")
            pdf.drawString(30,690,"VAT 11")
            pdf.drawString(30,670,"Total 111")
            pdf.showPage()
        pdf.showPage(); pdf.save()
        invoices=read_invoice_pdf_pages(output)
        self.assertEqual(len(invoices),3)
        self.assertEqual([row["page_range"] for row in invoices],["Page 1","Page 2","Page 3"])
        self.assertEqual([row["invoice_number"] for row in invoices[:2]],["101","102"])
        self.assertIn("scanned",invoices[2]["notes"])

    def test_invoice_vat_lbp_uses_rate_as_of_invoice_date(self):
        from desktop import SaberApp
        rates=[{"rate_date":"20-09-2026","from_currency":"USD","to_currency":"LBP","rate":90000},
               {"rate_date":"15-09-2026","from_currency":"USD","to_currency":"LBP","rate":89500}]
        selected=SaberApp.sales_rates_for_date(rates,"18-09-2026")
        self.assertEqual(SaberApp.exchange_equivalents(None,11,"USD",selected)[0],984500)
        self.assertEqual(SaberApp.sales_rates_for_date(rates,"01-09-2026"),[])

    def test_invoice_arrows_follow_order_and_keep_selection_on_cancel(self):
        from types import SimpleNamespace
        from desktop import SaberApp
        class Choice:
            value="first"
            def get(self): return self.value
            def set(self,value): self.value=value
        state=SimpleNamespace(sales_open_map={"first":{"id":1},"second":{"id":2}},
                              sales_edit_id=1,sales_open_choice=Choice(),open_sales_invoice=lambda:False)
        SaberApp.navigate_sales_invoice(state,1)
        self.assertEqual(state.sales_open_choice.get(),"first")
        state.open_sales_invoice=lambda:True
        SaberApp.navigate_sales_invoice(state,1)
        self.assertEqual(state.sales_open_choice.get(),"second")
        state.sales_edit_id=None; state.sales_open_choice.set("")
        SaberApp.navigate_sales_invoice(state,-1)
        self.assertEqual(state.sales_open_choice.get(),"second")

    def test_invoice_customer_and_account_match_both_ways(self):
        from types import SimpleNamespace
        from desktop import SaberApp
        class Choice:
            def __init__(self,value=""): self.value=value
            def get(self): return self.value
            def set(self,value): self.value=value
        customer={"name":"Client A","account_number":"411100001","currency":"USD"}
        state=SimpleNamespace(sales_customers={"Client A":customer},sales_party=Choice("Client A"),
                              sales_supplier_account=Choice(),sales_currency=Choice("EUR"))
        SaberApp.sales_customer_chosen(state)
        self.assertEqual(state.sales_supplier_account.get(),"411100001")
        state.sales_party.set(""); state.sales_supplier_account.set("411100001")
        SaberApp.sales_account_chosen(state)
        self.assertEqual((state.sales_party.get(),state.sales_currency.get()),("Client A","USD"))

    def test_invoice_category_selects_requested_posting_account(self):
        from types import SimpleNamespace
        from desktop import SaberApp
        class Choice:
            def __init__(self,value=""): self.value=value
            def get(self): return self.value
            def set(self,value): self.value=value
        state=SimpleNamespace(sales_doc_type=Choice("Invoice"),sales_category=Choice("Goods"),
                              sales_vat_account=Choice(),sales_expense_account=Choice())
        state.default_sales_posting_account=lambda:SaberApp.default_sales_posting_account(state)
        expected={"Goods":"701100001","Products":"711100001","Services":"713000001"}
        for category,account in expected.items():
            state.sales_category.set(category); SaberApp.sales_category_changed(state)
            self.assertEqual((state.sales_vat_account.get(),state.sales_expense_account.get()),("4427",account))
        state.sales_doc_type.set("Credit Note")
        for category,account in (("Goods","709000001"),("Products / Services","719000001")):
            state.sales_category.set(category); SaberApp.sales_category_changed(state)
            self.assertEqual((state.sales_vat_account.get(),state.sales_expense_account.get()),("4427",account))

    def test_invoice_find_filters_by_number_without_customer_data(self):
        from types import SimpleNamespace
        from desktop import SaberApp
        state=SimpleNamespace(sales_open_choice=SimpleNamespace(get=lambda:"2"),
                              sales_open_map={"SAL-2026-000001":{"id":1},"SAL-2026-000002":{"id":2},
                                              "SAL-2026-000002 (2)":{"id":3}},sales_open_box={})
        SaberApp.search_open_sales(state)
        self.assertEqual(state.sales_open_box["values"],["SAL-2026-000002","SAL-2026-000002 (2)"])

    def test_replacement_rejects_allocated_invoices(self):
        db=Database(self.company_database())  # 2.9.20: company data is in companies/<Company Name>/
        user=db.user_for_token(db.login("admin","secret12345")["token"])["id"]
        with db.connect() as connection:
            invoice=connection.execute("SELECT id FROM invoices LIMIT 1").fetchone()
            payment=connection.execute("SELECT id FROM payments LIMIT 1").fetchone()
            connection.execute("INSERT INTO payment_allocations(payment_id,invoice_id,amount,created_at) VALUES(?,?,?,?)",
                               (payment["id"],invoice["id"],"1","2024-03-01"))
        with self.assertRaisesRegex(ValueError,"allocated"):
            db.clear_invoices(user,make_backup=False)


if __name__=="__main__": unittest.main()
