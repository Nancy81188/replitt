"""Regression coverage for payment allocations in historical ageing reports."""
import secrets
import tempfile
import unittest
from pathlib import Path

from business_reports import ageing
from database import Database


class AgeingAllocationAsOfTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "company.db")
        password = secrets.token_hex(16)
        self.db.initialize(password)
        self.user = self.db.user_for_token(self.db.login("admin", password)["token"])["id"]
        self.party = self.db.save_party({"kind": "customer", "name": "Ageing Customer", "currency": "USD"}, self.user)

    def tearDown(self):
        self.folder.cleanup()

    def add_invoice(self, number, total, invoice_date="01-01-2026"):
        return self.db.import_invoice({
            "invoice_number": number,
            "invoice_date": invoice_date,
            "due_date": "01-01-2026",
            "party_name": "Ageing Customer",
            "kind": "sale",
            "currency": "USD",
            "subtotal": total,
            "vat": 0,
            "total": total,
            "status": "posted",
        }, self.user)

    def allocate(self, invoice_id, amount, payment_date):
        payment_id = self.db.add_payment({
            "kind": "customer_receipt",
            "payment_date": payment_date,
            "party_id": self.party["id"],
            "currency": "USD",
            "amount": amount,
            "cash_account": "531",
            "party_account": self.party["account_number"],
        }, self.user)
        self.db.save_allocations(payment_id, [{"invoice_id": invoice_id, "amount": amount}], self.user)
        return payment_id

    def report_amounts(self, as_of):
        stock_rows = self.db.aging_report(as_of, "sale", "USD")
        stock = {row["invoice_number"]: row["outstanding"] for row in stock_rows}
        report = ageing(self.db, {"date_to": as_of, "side": "receivables", "basis": "USD"})
        detail = next(section for section in report["sections"] if section["heading"] == "Open documents")
        business = {row[1]: float(row[5]) for row in detail["rows"] if row[1]}
        return stock, business

    def test_allocations_apply_only_on_or_before_as_of_with_both_date_formats(self):
        # The invoice and payment dates deliberately use different supported formats.
        invoice_id = self.add_invoice("MIXED-DATES", 100, "2026-01-01")
        payment_id = self.allocate(invoice_id, 40, "10-01-2026")
        with self.db.connect() as connection:
            connection.execute("UPDATE payments SET payment_date=? WHERE id=?", ("2026-01-10", payment_id))

        before_stock, before_business = self.report_amounts("09-01-2026")
        after_stock, after_business = self.report_amounts("11-01-2026")
        self.assertEqual(before_stock["MIXED-DATES"], 100)
        self.assertEqual(before_business["MIXED-DATES"], 100)
        self.assertEqual(after_stock["MIXED-DATES"], 60)
        self.assertEqual(after_business["MIXED-DATES"], 60)

        # Also exercise a DD-MM-YYYY payment date and ISO as-of date.
        invoice2 = self.add_invoice("DD-PAYMENT", 100)
        self.allocate(invoice2, 40, "10-01-2026")
        stock, business = self.report_amounts("2026-01-11")
        self.assertEqual(stock["DD-PAYMENT"], 60)
        self.assertEqual(business["DD-PAYMENT"], 60)

    def test_manual_paid_is_additive_and_fully_allocated_invoice_is_excluded(self):
        partly_paid = self.add_invoice("PARTIAL", 100)
        fully_paid = self.add_invoice("FULL", 100)
        with self.db.connect() as connection:
            connection.execute("UPDATE invoices SET amount_paid='20' WHERE id=?", (partly_paid,))
        self.allocate(partly_paid, 30, "10-01-2026")
        self.allocate(fully_paid, 100, "10-01-2026")

        stock, business = self.report_amounts("11-01-2026")
        self.assertEqual(stock["PARTIAL"], 50)
        self.assertEqual(business["PARTIAL"], 50)
        self.assertNotIn("FULL", stock)
        self.assertNotIn("FULL", business)

    def test_unallocated_receipt_is_visible_even_without_an_open_invoice(self):
        self.db.add_payment({
            "kind": "customer_receipt", "payment_date": "10-01-2026",
            "party_id": self.party["id"], "currency": "USD",
            "amount": 40, "cash_account": "531",
            "party_account": self.party["account_number"],
        }, self.user)
        before = ageing(self.db, {"date_to": "09-01-2026", "side": "receivables", "basis": "USD"})
        after = ageing(self.db, {"date_to": "11-01-2026", "side": "receivables", "basis": "USD"})

        def net_balance(report):
            summary = report["sections"][0]["rows"]
            return next(row[1] for row in summary if row[0] == "NET BALANCE")

        self.assertEqual(net_balance(before), 0)
        self.assertEqual(net_balance(after), -40)
        by_customer = after["sections"][1]
        row = next(row for row in by_customer["rows"] if row[0] == "Ageing Customer")
        self.assertEqual(row[by_customer["headers"].index("Unallocated")], 40)
        self.assertEqual(row[by_customer["headers"].index("Net Due")], -40)

    def test_paid_credit_note_reduces_the_credit_balance_in_all_three_views(self):
        note_id = self.db.create_manual_invoice({
            "invoice_number": "CN-PARTIAL", "invoice_date": "01-01-2026",
            "party_name": "Ageing Customer", "kind": "sales", "currency": "USD",
            "status": "posted", "doc_subtype": "credit_note", "amount_paid": 20,
            "supplier_side": "C - Credit", "vat_side": "D - Debit", "expense_side": "D - Debit",
        }, [{"description": "Returned goods", "quantity": 1, "unit_price": 100, "vat_rate": 0}], self.user)
        payment_id = self.db.add_payment({
            "kind": "supplier_payment", "payment_date": "10-01-2026",
            "party_id": self.party["id"], "currency": "USD", "amount": 30,
            "cash_account": "531", "party_account": self.party["account_number"],
        }, self.user)
        self.db.save_allocations(payment_id, [{"invoice_id": note_id, "amount": 30}], self.user)

        before_stock, before_business = self.report_amounts("09-01-2026")
        after_stock, after_business = self.report_amounts("11-01-2026")
        self.assertEqual(before_stock["CN-PARTIAL"], -80)
        self.assertEqual(before_business["CN-PARTIAL"], -80)
        self.assertEqual(after_stock["CN-PARTIAL"], -50)
        self.assertEqual(after_business["CN-PARTIAL"], -50)
        open_note = next(row for row in self.db.open_documents(self.party["id"]) if row["id"] == note_id)
        self.assertEqual(open_note["open_amount"], -50)

    def test_cash_settlements_match_document_direction_and_journal(self):
        supplier = self.db.save_party({"kind": "supplier", "name": "Ageing Supplier", "currency": "USD"}, self.user)
        for invoice_kind, credit, payment_kind, party in (
            ("sale", False, "customer_receipt", self.party),
            ("sale", True, "supplier_payment", self.party),
            ("purchase", False, "supplier_payment", supplier),
            ("purchase", True, "customer_receipt", supplier),
        ):
            with self.subTest(document=invoice_kind, credit=credit):
                number = f"{invoice_kind}-{'credit' if credit else 'invoice'}"
                if credit:
                    invoice_id = self.db.create_manual_invoice({
                        "invoice_number": number, "invoice_date": "01-01-2026",
                        "party_name": party["name"], "kind": "sales" if invoice_kind == "sale" else "purchases",
                        "currency": "USD", "status": "posted", "doc_subtype": "credit_note",
                    }, [{"description": "Returned goods", "quantity": 1, "unit_price": 100, "vat_rate": 0}], self.user)
                else:
                    invoice_id = self.db.import_invoice({
                        "invoice_number": number, "invoice_date": "01-01-2026",
                        "party_name": party["name"], "kind": invoice_kind,
                        "currency": "USD", "subtotal": 100, "vat": 0, "total": 100, "status": "posted",
                    }, self.user)
                payment_id = self.db.add_payment({
                    "kind": payment_kind, "payment_date": "10-01-2026", "party_id": party["id"],
                    "currency": "USD", "amount": 40, "cash_account": "531",
                    "party_account": party["account_number"],
                }, self.user)
                self.db.save_allocations(payment_id, [{"invoice_id": invoice_id, "amount": 40}], self.user)
                open_doc = next(d for d in self.db.open_documents(party["id"]) if d["id"] == invoice_id)
                self.assertEqual(open_doc["open_amount"], -60 if credit else 60)
                with self.db.connect() as connection:
                    lines = connection.execute("""
                        SELECT a.code, CAST(l.debit AS REAL) debit, CAST(l.credit AS REAL) credit
                        FROM journal_lines l JOIN accounts a ON a.id=l.account_id
                        JOIN journal_entries e ON e.id=l.entry_id
                        WHERE e.source_type='payment' AND e.source_id=?""", (payment_id,)).fetchall()
                by_account = {line["code"]: (line["debit"], line["credit"]) for line in lines}
                incoming = payment_kind == "customer_receipt"
                self.assertEqual(by_account["531"], (40, 0) if incoming else (0, 40))
                self.assertEqual(by_account[party["account_number"]], (0, 40) if incoming else (40, 0))
                side = "receivables" if invoice_kind == "sale" else "payables"
                detail = next(s for s in ageing(self.db, {"date_to": "11-01-2026", "side": side})["sections"] if s["heading"] == "Open documents")
                self.assertEqual(next(r[5] for r in detail["rows"] if r[1] == number), -60 if credit else 60)

    def test_incompatible_allocation_is_rejected_without_changing_existing_rows(self):
        note_id = self.db.create_manual_invoice({
            "invoice_number": "CN-REJECT", "invoice_date": "01-01-2026",
            "party_name": self.party["name"], "kind": "sales", "currency": "USD",
            "status": "posted", "doc_subtype": "credit_note",
        }, [{"description": "Return", "quantity": 1, "unit_price": 100, "vat_rate": 0}], self.user)
        invoice_id = self.add_invoice("INV-KEEP", 100)
        receipt = self.allocate(invoice_id, 30, "10-01-2026")
        with self.assertRaisesRegex(ValueError, "outgoing payment/refund"):
            self.db.save_allocations(receipt, [{"invoice_id": note_id, "amount": 30}], self.user)
        self.assertEqual(self.db.payment_allocations(receipt)[0]["invoice_id"], invoice_id)
        refund = self.db.add_payment({
            "kind": "supplier_payment", "payment_date": "10-01-2026",
            "party_id": self.party["id"], "currency": "USD", "amount": 20,
        }, self.user)
        with self.assertRaisesRegex(ValueError, "incoming receipt/refund"):
            self.db.save_allocations(refund, [{"invoice_id": invoice_id, "amount": 20}], self.user)
        self.assertEqual(self.db.payment_allocations(refund), [])
        supplier = self.db.save_party({"kind": "supplier", "name": "Reject Supplier", "currency": "USD"}, self.user)
        purchase = self.db.import_invoice({
            "invoice_number": "PUR-REJECT", "invoice_date": "01-01-2026",
            "party_name": supplier["name"], "kind": "purchase", "currency": "USD",
            "subtotal": 100, "vat": 0, "total": 100, "status": "posted",
        }, self.user)
        purchase_credit = self.db.create_manual_invoice({
            "invoice_number": "PCN-REJECT", "invoice_date": "01-01-2026",
            "party_name": supplier["name"], "kind": "purchases", "currency": "USD",
            "status": "posted", "doc_subtype": "credit_note",
        }, [{"description": "Return", "quantity": 1, "unit_price": 100, "vat_rate": 0}], self.user)
        incoming = self.db.add_payment({
            "kind": "customer_receipt", "payment_date": "10-01-2026",
            "party_id": supplier["id"], "currency": "USD", "amount": 20,
        }, self.user)
        outgoing = self.db.add_payment({
            "kind": "supplier_payment", "payment_date": "10-01-2026",
            "party_id": supplier["id"], "currency": "USD", "amount": 20,
        }, self.user)
        with self.assertRaisesRegex(ValueError, "outgoing payment/refund"):
            self.db.save_allocations(incoming, [{"invoice_id": purchase, "amount": 20}], self.user)
        with self.assertRaisesRegex(ValueError, "incoming receipt/refund"):
            self.db.save_allocations(outgoing, [{"invoice_id": purchase_credit, "amount": 20}], self.user)

    def test_unallocated_refund_increases_net_receivables(self):
        self.db.add_payment({
            "kind": "supplier_payment", "payment_date": "10-01-2026",
            "party_id": self.party["id"], "currency": "USD", "amount": 25,
        }, self.user)
        report = ageing(self.db, {"date_to": "11-01-2026", "side": "receivables"})
        self.assertEqual(next(row[1] for row in report["sections"][0]["rows"] if row[0] == "NET BALANCE"), 25)
        supplier = self.db.save_party({"kind": "supplier", "name": "Refund Supplier", "currency": "USD"}, self.user)
        self.db.add_payment({
            "kind": "customer_receipt", "payment_date": "10-01-2026",
            "party_id": supplier["id"], "currency": "USD", "amount": 15,
        }, self.user)
        payable = ageing(self.db, {"date_to": "11-01-2026", "side": "payables"})
        self.assertEqual(next(row[1] for row in payable["sections"][0]["rows"] if row[0] == "NET BALANCE"), 15)
        receivable = ageing(self.db, {"date_to": "11-01-2026", "side": "receivables"})
        self.assertEqual(next(row[1] for row in receivable["sections"][0]["rows"] if row[0] == "NET BALANCE"), 25)


if __name__ == "__main__":
    unittest.main()