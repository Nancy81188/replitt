import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from database import Database


class InvoiceReturnTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "returns.db")
        self.db.initialize("secret")
        self.user = self.db.user_for_token(self.db.login("admin", "secret")["token"])
        with self.db.connect() as conn:
            conn.execute("INSERT INTO inventory_items(sku,name,unit,quantity,average_cost) VALUES('SKU-1','Returnable item','unit','0','10')")

    def tearDown(self):
        self.temp.cleanup()

    def _return(self,source_id,items,date,request_id=None):
        return self.db.create_invoice_return(source_id,items,date,self.user["id"],request_id or str(uuid.uuid4()))

    def _sale_source(self):
        import inventory
        inventory.save_document(self.db, {"doc_type":"receipt","doc_date":"2026-09-01","warehouse_id":"MAIN"},
                                [{"sku":"SKU-1","quantity":5,"unit_cost":10}], self.user["id"])
        return self.db.create_manual_invoice({
            "invoice_number":"SALE-ORIG","invoice_date":"2026-09-02","party_name":"Customer",
            "kind":"sales","currency":"USD","status":"posted","source_file":"Sales Invoice",
            "supplier_account":"411100001","vat_account":"4427","expense_account":"711000001",
        },[{"description":"Returnable item","item_code":"SKU-1","quantity":2,"unit_price":100,"vat_rate":11}],self.user["id"])

    def _purchase_source(self):
        return self.db.create_manual_invoice({
            "invoice_number":"PUR-ORIG","invoice_date":"2026-09-02","party_name":"Supplier",
            "kind":"purchases","currency":"USD","status":"posted","source_file":"Purchase Invoice",
            "supplier_account":"401100001","vat_account":"442660000","expense_account":"601100000",
        },[{"description":"Returnable item","item_code":"SKU-1","quantity":2,"unit_price":100,"vat_rate":11}],self.user["id"])

    def _credit_note_with_later_consumption(self):
        import inventory
        inventory.save_document(self.db,{"doc_type":"receipt","doc_date":"2026-09-01","warehouse_id":"MAIN"},
                                [{"sku":"SKU-1","quantity":2,"unit_cost":10}],self.user["id"])
        source_id=self.db.create_manual_invoice({
            "invoice_number":"SALE-TWO","invoice_date":"2026-09-02","party_name":"Customer",
            "kind":"sales","currency":"USD","status":"posted","source_file":"Sales Invoice",
            "supplier_account":"411100001","vat_account":"4427","expense_account":"711000001",
        },[{"description":"Returnable item","item_code":"SKU-1","quantity":2,"unit_price":100,"vat_rate":0}],self.user["id"])
        source_item=self.db.invoice_detail(source_id)["items"][0]
        credit=self._return(source_id,[{"item_id":source_item["id"],"quantity":"1"}],"2026-09-03")
        inventory.save_document(self.db,{"doc_type":"issue","doc_date":"2026-09-04","warehouse_id":"MAIN"},
                                [{"sku":"SKU-1","quantity":1}],self.user["id"])
        return credit

    def _check_return(self, source_id, expect_kind, expected_sides, expected_stock_type):
        source_before=self.db.get_invoice(source_id)
        source_items_before=self.db.invoice_detail(source_id)["items"]
        result=self._return(source_id,[{"item_id":source_items_before[0]["id"],"quantity":"1"}],"2026-09-03")
        self.assertEqual(result["kind"],expect_kind)
        self.assertEqual(result["doc_subtype"],"credit_note")
        self.assertEqual(result["linked_invoice_id"],source_id)
        self.assertEqual(result["amount_paid"],0.0)
        self.assertEqual(result["payment_status"],"unpaid")
        self.assertEqual((result["supplier_side"],result["vat_side"],result["expense_side"]),expected_sides)
        self.assertAlmostEqual(float(result["subtotal"]),100.0)
        self.assertAlmostEqual(float(result["vat"]),11.0)
        self.assertAlmostEqual(float(result["total"]),111.0)
        self.assertEqual(self.db.get_invoice(source_id),source_before)
        after_items=self.db.invoice_detail(source_id)["items"]
        for before,after in zip(source_items_before,after_items):
            self.assertEqual({k:v for k,v in before.items() if not k.startswith("returned_")},
                             {k:v for k,v in after.items() if not k.startswith("returned_")})
        with self.db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0],0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM payment_allocations").fetchone()[0],0)
            stock=conn.execute("""SELECT d.doc_type FROM stock_documents d WHERE d.invoice_id=?""",(result["id"],)).fetchone()
        self.assertIsNotNone(stock)
        self.assertEqual(stock["doc_type"],expected_stock_type)
        # A second return cannot exceed the quantity left after this posted partial return.
        with self.assertRaisesRegex(ValueError,"remains returnable"):
            self._return(source_id,[{"item_id":source_items_before[0]["id"],"quantity":"2"}],"2026-09-04")

    def test_sales_return_is_linked_credit_note_with_receipt_stock_and_no_refund(self):
        source_id=self._sale_source()
        self._check_return(source_id,"sale",("C","D","D"),"receipt")

    def test_purchase_return_is_linked_credit_note_with_issue_stock_and_no_refund(self):
        source_id=self._purchase_source()
        self._check_return(source_id,"purchase",("D","C","C"),"issue")

    def test_return_rejects_unposted_invoice_without_mutating_it(self):
        source_id=self.db.create_manual_invoice({
            "invoice_number":"DRAFT","invoice_date":"2026-09-02","party_name":"Customer",
            "kind":"sales","currency":"USD","status":"review","source_file":"Sales Invoice",
        },[{"description":"Service","quantity":1,"unit_price":50,"vat_rate":11}],self.user["id"])
        before=self.db.get_invoice(source_id)
        with self.assertRaisesRegex(ValueError,"posted invoice"):
            self._return(source_id,[{"item_id":self.db.invoice_detail(source_id)["items"][0]["id"],"quantity":"1"}],"2026-09-03")
        self.assertEqual(self.db.get_invoice(source_id),before)
        self.assertEqual(len(self.db.list_invoices()),1)

    def test_exempt_discounted_sales_return_uses_saved_net_line_value_and_zero_vat(self):
        source_id=self.db.create_manual_invoice({
            "invoice_number":"EXEMPT-ORIG","invoice_date":"2026-09-02","party_name":"Customer",
            "kind":"sales","currency":"USD","status":"posted","source_file":"Sales Invoice",
            "invoice_discount_percent":"10","vat_treatment":"exempt",
        },[{"description":"Exempt service","quantity":2,"unit_price":50,
            "deductible_subtotal":0,"non_deductible_subtotal":90,"vat_rate":0,"vat":0}],self.user["id"])
        source_line=self.db.invoice_detail(source_id)["items"][0]
        result=self._return(source_id,[{"item_id":source_line["id"],"quantity":"1"}],"2026-09-03")
        returned=self.db.invoice_detail(result["id"])["items"][0]
        self.assertEqual(result["invoice_discount_percent"],"0")
        self.assertAlmostEqual(float(result["subtotal"]),45.0)
        self.assertAlmostEqual(float(result["vat"]),0.0)
        self.assertAlmostEqual(float(result["total"]),45.0)
        self.assertAlmostEqual(float(returned["non_deductible_subtotal"]),45.0)

    def test_nonrecoverable_purchase_vat_reclassification_is_reversed_once(self):
        source_id=self.db.create_manual_invoice({
            "invoice_number":"NONREC-ORIG","invoice_date":"2026-09-02","party_name":"Supplier",
            "kind":"purchases","currency":"USD","status":"posted","source_file":"Purchase Invoice",
            "supplier_account":"401100001","vat_account":"442660000","expense_account":"601100000",
            "vat_use":"exempt",
        },[{"description":"Taxed purchase","quantity":1,"unit_price":100,"vat_rate":11}],self.user["id"])
        source=self.db.get_invoice(source_id)
        self.assertEqual(source["vat_recoverable"],0)
        result=self._return(source_id,[{"item_id":self.db.invoice_detail(source_id)["items"][0]["id"],"quantity":"1"}],
                            "2026-09-03")
        self.assertEqual(result["vat_recoverable"],0)
        journal=self.db.journal(currency="USD")
        relevant=[row for row in journal if row.get("source_id") in (source_id,result["id"])]
        for account in ("401100001","442660000","601100000"):
            movement=sum(float(row["debit"])-float(row["credit"]) for row in relevant if row["account_code"]==account)
            self.assertAlmostEqual(movement,0.0)

    def test_return_respects_closed_return_period_without_posting(self):
        source_id=self._purchase_source()
        source=self.db.get_invoice(source_id)
        item_id=self.db.invoice_detail(source_id)["items"][0]["id"]
        with self.db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO fiscal_years(year,status,opened_at) VALUES(2026,'closed','test')")
        with self.assertRaisesRegex(ValueError,"closed"):
            self._return(source_id,[{"item_id":item_id,"quantity":"1"}],"2026-09-03")
        self.assertEqual(self.db.get_invoice(source_id),source)
        self.assertEqual(len(self.db.list_invoices()),1)

    def test_return_is_idempotent_and_rejects_reused_key_with_different_payload(self):
        source_id=self._sale_source(); item_id=self.db.invoice_detail(source_id)["items"][0]["id"]
        key="stable-return-request"
        first=self.db.create_invoice_return(source_id,[{"item_id":item_id,"quantity":"1"}],"2026-09-03",self.user["id"],key)
        retry=self.db.create_invoice_return(source_id,[{"item_id":item_id,"quantity":"1"}],"2026-09-03",self.user["id"],key)
        self.assertEqual(first["id"],retry["id"])
        self.assertEqual(len(self.db.list_invoices()),2)
        with self.assertRaisesRegex(ValueError,"different return details"):
            self.db.create_invoice_return(source_id,[{"item_id":item_id,"quantity":"0.5"}],"2026-09-03",self.user["id"],key)

    def test_concurrent_returns_cannot_overrun_source_quantity(self):
        source_id=self._sale_source(); item_id=self.db.invoice_detail(source_id)["items"][0]["id"]
        barrier=threading.Barrier(2); outcomes=[]
        def post(key):
            barrier.wait()
            try:
                outcomes.append(("ok",self.db.create_invoice_return(source_id,[{"item_id":item_id,"quantity":"2"}],
                    "2026-09-03",self.user["id"],key)["id"]))
            except ValueError as exc: outcomes.append(("error",str(exc)))
        threads=[threading.Thread(target=post,args=(f"concurrent-{i}",)) for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sum(result[0]=="ok" for result in outcomes),1)
        self.assertEqual(sum(result[0]=="error" for result in outcomes),1)
        self.assertEqual(self.db.invoice_detail(source_id)["items"][0]["returned_quantity"],2)

    def test_post_failure_rolls_back_credit_journal_link_and_stock(self):
        source_id=self._sale_source(); before_invoices=len(self.db.list_invoices())
        with self.db.connect() as conn:
            before_docs=conn.execute("SELECT COUNT(*) FROM stock_documents").fetchone()[0]
            before_entries=conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        import inventory
        with patch.object(inventory,"issue_for_invoice",side_effect=RuntimeError("simulated stock failure")):
            with self.assertRaisesRegex(RuntimeError,"simulated stock failure"):
                self._return(source_id,[{"item_id":self.db.invoice_detail(source_id)["items"][0]["id"],"quantity":"1"}],"2026-09-03")
        self.assertEqual(len(self.db.list_invoices()),before_invoices)
        with self.db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM stock_documents").fetchone()[0],before_docs)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0],before_entries)
        self.assertEqual(self.db.invoice_detail(source_id)["items"][0]["returned_quantity"],0)

    def test_active_linked_credit_blocks_source_edit_and_cancel_and_cancellation_releases_qty(self):
        source_id=self._sale_source(); source_item=self.db.invoice_detail(source_id)["items"][0]
        credit=self._return(source_id,[{"item_id":source_item["id"],"quantity":"1"}],"2026-09-03")
        with self.assertRaisesRegex(ValueError,"active linked credit note"):
            self.db.replace_manual_invoice(source_id,{},[],self.user["id"])
        with self.assertRaisesRegex(ValueError,"active linked credit note"):
            self.db.cancel_invoice(source_id,"test",self.user["id"])
        with self.assertRaisesRegex(ValueError,"credit note cannot be edited"):
            self.db.replace_manual_invoice(credit["id"],{},[],self.user["id"])
        self.db.cancel_invoice(credit["id"],"Return reversed",self.user["id"])
        replacement=self._return(source_id,[{"item_id":source_item["id"],"quantity":"2"}],"2026-09-04")
        self.assertEqual(replacement["linked_invoice_id"],source_id)

    def test_sales_return_restores_original_issue_cost_not_current_average_or_sales_price(self):
        import inventory
        source_id=self._sale_source()
        inventory.save_document(self.db,{"doc_type":"receipt","doc_date":"2026-09-04","warehouse_id":"MAIN"},
                                [{"sku":"SKU-1","quantity":5,"unit_cost":50}],self.user["id"])
        source_item=self.db.invoice_detail(source_id)["items"][0]
        credit=self._return(source_id,[{"item_id":source_item["id"],"quantity":"1"}],"2026-09-05")
        with self.db.connect() as conn:
            movement=conn.execute("""SELECT m.unit_cost FROM stock_movements m JOIN stock_documents d ON d.id=m.document_id
                WHERE d.invoice_id=?""",(credit["id"],)).fetchone()
        self.assertEqual(float(movement["unit_cost"]),10.0)

    def test_fifo_sales_return_reintroduces_the_consumed_original_layers(self):
        import inventory
        with self.db.connect() as conn:
            conn.execute("UPDATE app_settings SET value='fifo' WHERE key='inventory_method'")
        inventory.save_document(self.db,{"doc_type":"receipt","doc_date":"2026-09-01","warehouse_id":"MAIN"},
                                [{"sku":"SKU-1","quantity":2,"unit_cost":10}],self.user["id"])
        inventory.save_document(self.db,{"doc_type":"receipt","doc_date":"2026-09-02","warehouse_id":"MAIN"},
                                [{"sku":"SKU-1","quantity":2,"unit_cost":20}],self.user["id"])
        source_id=self.db.create_manual_invoice({
            "invoice_number":"FIFO-SALE","invoice_date":"2026-09-03","party_name":"Customer",
            "kind":"sales","currency":"USD","status":"posted","source_file":"Sales Invoice",
            "supplier_account":"411100001","vat_account":"4427","expense_account":"711000001",
        },[{"description":"Returnable item","item_code":"SKU-1","quantity":3,"unit_price":100,"vat_rate":0}],self.user["id"])
        source_item=self.db.invoice_detail(source_id)["items"][0]
        first=self._return(source_id,[{"item_id":source_item["id"],"quantity":"2"}],"2026-09-04")
        second=self._return(source_id,[{"item_id":source_item["id"],"quantity":"1"}],"2026-09-05")
        with self.db.connect() as conn:
            costs=[float(row["unit_cost"]) for row in conn.execute("""SELECT m.unit_cost FROM stock_movements m JOIN stock_documents d ON d.id=m.document_id
                WHERE d.invoice_id IN (?,?) ORDER BY d.invoice_id""",(first["id"],second["id"]))]
        self.assertEqual(costs,[10.0,20.0])

    def test_purchase_return_rejects_exhausted_stock(self):
        import inventory
        source_id=self._purchase_source()
        inventory.save_document(self.db,{"doc_type":"issue","doc_date":"2026-09-04","warehouse_id":"MAIN"},
                                [{"sku":"SKU-1","quantity":2}],self.user["id"])
        source_item=self.db.invoice_detail(source_id)["items"][0]
        with self.assertRaisesRegex(ValueError,"Not enough stock"):
            self._return(source_id,[{"item_id":source_item["id"],"quantity":"1"}],"2026-09-05")
        self.assertEqual(self.db.invoice_detail(source_id)["items"][0]["returned_quantity"],0)

    def test_fifo_purchase_return_rejects_when_original_layer_was_consumed(self):
        import inventory
        with self.db.connect() as conn:
            conn.execute("UPDATE app_settings SET value='fifo' WHERE key='inventory_method'")
        source_id=self._purchase_source()
        inventory.save_document(self.db,{"doc_type":"receipt","doc_date":"2026-09-03","warehouse_id":"MAIN"},
                                [{"sku":"SKU-1","quantity":2,"unit_cost":20}],self.user["id"])
        self.db.create_manual_invoice({
            "invoice_number":"FIFO-SALE","invoice_date":"2026-09-04","party_name":"Customer",
            "kind":"sales","currency":"USD","status":"posted","source_file":"Sales Invoice",
            "supplier_account":"411100001","vat_account":"4427","expense_account":"711000001",
        },[{"description":"Returnable item","item_code":"SKU-1","quantity":2,"unit_price":100,"vat_rate":0}],self.user["id"])
        source_item=self.db.invoice_detail(source_id)["items"][0]
        with self.assertRaisesRegex(ValueError,"Original FIFO purchase layer"):
            self._return(source_id,[{"item_id":source_item["id"],"quantity":"1"}],"2026-09-05")
        self.assertEqual(self.db.invoice_detail(source_id)["items"][0]["returned_quantity"],0)

    def test_cancelling_credit_rolls_back_if_its_receipt_was_consumed_later(self):
        credit=self._credit_note_with_later_consumption()
        with self.db.connect() as conn:
            doc_ids=[row["id"] for row in conn.execute("SELECT id FROM stock_documents WHERE invoice_id=?",(credit["id"],))]
            journals=[tuple(row) for row in conn.execute("SELECT id,source_type FROM journal_entries WHERE source_id=? ORDER BY id",(credit["id"],))]
        with self.assertRaisesRegex(ValueError,"would make later stock negative"):
            self.db.cancel_invoice(credit["id"],"Cancel consumed goods return",self.user["id"])
        self.assertEqual(self.db.get_invoice(credit["id"])["status"],"posted")
        with self.db.connect() as conn:
            self.assertEqual([row["id"] for row in conn.execute("SELECT id FROM stock_documents WHERE invoice_id=?",(credit["id"],))],doc_ids)
            self.assertEqual([tuple(row) for row in conn.execute("SELECT id,source_type FROM journal_entries WHERE source_id=? ORDER BY id",(credit["id"],))],journals)

    def test_marking_credit_deleted_rolls_back_if_its_receipt_was_consumed_later(self):
        credit=self._credit_note_with_later_consumption()
        with self.db.connect() as conn:
            doc_ids=[row["id"] for row in conn.execute("SELECT id FROM stock_documents WHERE invoice_id=?",(credit["id"],))]
            journals=[tuple(row) for row in conn.execute("SELECT id,source_type FROM journal_entries WHERE source_id=? ORDER BY id",(credit["id"],))]
        with self.assertRaisesRegex(ValueError,"would make later stock negative"):
            self.db.mark_invoice_deleted(credit["id"],self.user["id"])
        self.assertEqual(self.db.get_invoice(credit["id"])["status"],"posted")
        with self.db.connect() as conn:
            self.assertEqual([row["id"] for row in conn.execute("SELECT id FROM stock_documents WHERE invoice_id=?",(credit["id"],))],doc_ids)
            self.assertEqual([tuple(row) for row in conn.execute("SELECT id,source_type FROM journal_entries WHERE source_id=? ORDER BY id",(credit["id"],))],journals)

    def test_non_usd_purchase_stock_cost_is_converted_and_return_copies_rate(self):
        import inventory
        with self.db.connect() as conn:
            conn.execute("INSERT INTO exchange_rates(rate_date,from_currency,to_currency,rate,created_at) VALUES('2026-09-02','EUR','USD','1.2','test')")
        source_id=self.db.create_manual_invoice({
            "invoice_number":"PUR-EUR","invoice_date":"2026-09-02","party_name":"Euro Supplier",
            "kind":"purchases","currency":"EUR","exchange_rate":"1.2","status":"posted","source_file":"Purchase Invoice",
            "supplier_account":"401100001","vat_account":"442660000","expense_account":"601100000",
        },[{"description":"Returnable item","item_code":"SKU-1","quantity":2,"unit_price":100,"vat_rate":0}],self.user["id"])
        with self.db.connect() as conn:
            source_cost=conn.execute("""SELECT m.unit_cost FROM stock_movements m JOIN stock_documents d ON d.id=m.document_id
                WHERE d.invoice_id=?""",(source_id,)).fetchone()["unit_cost"]
        self.assertEqual(float(source_cost),120.0)
        source_line=self.db.invoice_detail(source_id)["items"][0]
        credit=self._return(source_id,[{"item_id":source_line["id"],"quantity":"1"}],"2026-09-03")
        self.assertEqual(credit["exchange_rate"],"1.2")
        with self.db.connect() as conn:
            return_cost=conn.execute("""SELECT m.unit_cost FROM stock_movements m JOIN stock_documents d ON d.id=m.document_id
                WHERE d.invoice_id=?""",(credit["id"],)).fetchone()["unit_cost"]
        self.assertEqual(float(return_cost),120.0)

    def test_backdated_purchase_return_cannot_make_later_stock_issue_negative(self):
        import inventory
        source_id=self._purchase_source()
        inventory.save_document(self.db,{"doc_type":"issue","doc_date":"2026-09-04","warehouse_id":"MAIN"},
                                [{"sku":"SKU-1","quantity":1}],self.user["id"])
        source_item=self.db.invoice_detail(source_id)["items"][0]
        with self.assertRaisesRegex(ValueError,"later stock negative"):
            self._return(source_id,[{"item_id":source_item["id"],"quantity":"2"}],"2026-09-03")
        self.assertEqual(self.db.invoice_detail(source_id)["items"][0]["returned_quantity"],0)


if __name__ == "__main__":
    unittest.main()