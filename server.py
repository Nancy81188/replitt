from __future__ import annotations

import argparse
import os
import secrets
import socket
import ssl
import base64
import json
import traceback
import sqlite3
import tempfile
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from database import Database, iso_date
from company_manager import CompanyManager
from payroll_reports import build_payroll_report, json_ready as payroll_json
import ledger_reports
import inventory
import fixed_assets
import vat_return

class ApiHandler(BaseHTTPRequestHandler):
    db: Database = None
    master_db: Database = None
    company_manager: CompanyManager = None

    def log_message(self, fmt, *args):
        print(f"[Saber API] {self.address_string()} {fmt % args}")

    # HTTP/1.1 lets the desktop program keep one connection open and reuse it for every
    # request, instead of opening a new TCP connection (and a new server thread) each time.
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        # Send each small answer at once (no Nagle / delayed-ACK wait on a kept-open connection).
        try: self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (OSError, AttributeError): pass

    def _json(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self._responded = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        raw = getattr(self, "_raw_body", None)
        if raw is None:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length > 0 else b""; self._raw_body = raw
        return json.loads(raw or b"{}")

    def _user(self):
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        # Backups are made when the user asks (and automatically before a restore or an import that replaces data),
        # not every time the program is opened.
        return self.master_db.user_for_token(token)

    def _query(self, parsed, name, default=None):
        return parse_qs(parsed.query).get(name, [default])[0]

    def _module_denied(self, user, path):
        """Module permissions: payroll (salaries) and VAT can be granted per user."""
        module = "payroll" if path.startswith(("/api/employees", "/api/payroll")) else "vat" if path.startswith(("/api/vat", "/api/vat-")) else None
        if module and not self.master_db.user_can(user, module):
            self._json(403, {"error": f"You do not have permission to use {module.upper() if module=='vat' else module.title()}. Ask the administrator."})
            return True
        return False

    def _previous_year_db(self, year):
        try:
            company_id = self.headers.get("X-Company-ID")
            return self.company_manager.database(company_id, int(year) - 1) if company_id else None
        except Exception:
            return None

    def _select_database(self):
        try:
            self.db=self.company_manager.database(self.headers.get("X-Company-ID"),self.headers.get("X-Fiscal-Year"))
            return True
        except (KeyError, ValueError) as exc:
            self._json(400,{"error":str(exc).strip("'\"")})
            return False

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            return self._json(200, {"status": "ok", "application": "Saber Accounting"})
        user = self._user()
        if not user:
            return self._json(401, {"error": "Unauthorized"})
        if path == "/api/companies": return self._json(200,{"items":self.company_manager.list_companies(user["role"]=="admin")})
        if not self._select_database(): return
        if self._module_denied(user, path): return
        if path == "/api/me":
            info={k:user[k] for k in ("id","username","role","language","expires_at")}; info["permissions"]={m:self.master_db.user_can(user,m) for m in ("payroll","vat")}
            return self._json(200,info)
        if path == "/api/fixed-assets":
            return self._json(200,{"items":fixed_assets.list_assets(self.db)})
        if path.startswith("/api/fixed-assets/") and path.endswith("/schedule"):
            try: return self._json(200,{"items":fixed_assets.schedule(self.db,int(path.split("/")[-2]))})
            except KeyError: return self._json(404,{"error":"Asset not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/payroll/reports":
            try:
                result=build_payroll_report(self.db,self._query(parsed,"report","R10"),self._query(parsed,"period_type","quarterly"),
                    self._query(parsed,"year"),self._query(parsed,"index","1"),self._query(parsed,"group","both"),
                    self._query(parsed,"include_drafts","false").lower()=="true")
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,payroll_json(result))
        if path == "/api/payroll/nssf-filed":
            try: return self._json(200,{"items":self.db.nssf_filed_wages(self._query(parsed,"year",""))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/reports/accounts":
            try:
                options=json.loads(self._query(parsed,"options","{}") or "{}")
                with self.db.connect() as connection:
                    department_id,project_id=self.db._dimension_ids(connection,{"department":options.get("department"),"project":options.get("project")})
                options["department_id"]=department_id; options["project_id"]=project_id
                return self._json(200,ledger_reports.json_ready(ledger_reports.build_account_report(self.db,options)))
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/documents/next-number":
            try: return self._json(200,{"number":self.db.next_document_number(self._query(parsed,"kind"),self._query(parsed,"date"))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/expenses/") and path.endswith("/attachments"):
            try: return self._json(200,{"items":self.db.list_expense_attachments(int(path.split("/")[-2]))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/expense-attachments/"):
            try:
                attachment=self.db.get_expense_attachment(int(path.rsplit("/",1)[-1])); attachment["content"]=base64.b64encode(attachment["content"]).decode("ascii")
            except KeyError: return self._json(404,{"error":"Attachment not found"})
            return self._json(200,attachment)
        if path.startswith("/api/invoices/") and path.endswith("/landed-costs"):
            try: return self._json(200,{"items":self.db.landed_costs(int(path.split("/")[-2]))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/fiscal-years/closing-preview":
            try:
                import year_end
                data=year_end.closing_preview(self.db,int(self._query(parsed,"year")))
                return self._json(200,{c:{"lines":[[code,float(a),float(l),float(u),name] for code,a,l,u,name in v["lines"]],"net_result":float(v["net_result"])} for c,v in data.items()})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/inventory/"):
            try:
                if path == "/api/inventory/items": return self._json(200,{"items":inventory.list_items(self.db,self._query(parsed,"date"))})
                if path == "/api/inventory/warehouses": return self._json(200,{"items":inventory.list_warehouses(self.db)})
                if path == "/api/inventory/settings": return self._json(200,inventory.settings(self.db))
                if path == "/api/inventory/documents": return self._json(200,{"items":inventory.list_documents(self.db)})
                if path.startswith("/api/inventory/documents/"): return self._json(200,inventory.get_document(self.db,int(path.rsplit("/",1)[-1])))
                if path == "/api/inventory/next-number": return self._json(200,{"number":inventory.next_number(self.db,self._query(parsed,"type"),self._query(parsed,"date"))})
                if path == "/api/inventory/categories": return self._json(200,inventory.list_categories(self.db))
                if path == "/api/inventory/count-sheet": return self._json(200,{"items":inventory.count_sheet(self.db,self._query(parsed,"warehouse_id"),self._query(parsed,"date"))})
                if path == "/api/inventory/counts": return self._json(200,{"items":inventory.list_counts(self.db)})
                if path.startswith("/api/inventory/counts/"): return self._json(200,inventory.get_count(self.db,int(path.rsplit("/",1)[-1])))
                if path == "/api/inventory/report":
                    result=inventory.build_report(self.db,self._query(parsed,"report"),json.loads(self._query(parsed,"options","{}") or "{}"))
                    return self._json(200,ledger_reports.json_ready(result))
            except KeyError as exc: return self._json(404,{"error":str(exc).strip("'")})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/parties/") and path.endswith("/open-documents"):
            try: return self._json(200,{"items":self.db.open_documents(int(path.split("/")[-2]))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/payments/") and path.endswith("/allocations"):
            try: return self._json(200,{"items":self.db.payment_allocations(int(path.split("/")[-2]))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/reports/dashboard-charts":
            try:
                import business_reports
                return self._json(200,business_reports.dashboard_charts(self.db,{"year":self._query(parsed,"year"),"basis":self._query(parsed,"basis","USD")}))
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/bank/lines":
            try:
                import bank_rec
                account=self._query(parsed,"account",""); currency=self._query(parsed,"currency","USD"); start=iso_date(self._query(parsed,"from")); end=iso_date(self._query(parsed,"to"))
                return self._json(200,ledger_reports.json_ready({"statement":bank_rec.statement_lines(self.db,account,start,end),"books":bank_rec.book_lines(self.db,account,currency,start,end),
                    "report":bank_rec.reconciliation(self.db,account,currency,start,end,self._query(parsed,"balance"))}))
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/reports/financial-config":
            try:
                import financial_statements
                year = int(self._query(parsed,"year",self.headers.get("X-Fiscal-Year")))
                target = self.company_manager.database(self.headers.get("X-Company-ID"),year)
                return self._json(200,financial_statements.config(target))
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/reports/business":
            try:
                import business_reports
                report = self._query(parsed,"report","")
                options = json.loads(self._query(parsed,"options","{}") or "{}")
                if report == "financial_statements":
                    import financial_statements
                    years = financial_statements.years_from(options.get("years"))
                    databases = {year:self.company_manager.database(self.headers.get("X-Company-ID"),year) for year in years}
                    result = financial_statements.build(databases,options)
                else:
                    result=business_reports.build(self.db,report,options)
                return self._json(200,ledger_reports.json_ready(result))
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/departments": return self._json(200,{"items":self.db.list_departments()})
        if path == "/api/projects": return self._json(200,{"items":self.db.list_projects()})
        if path == "/api/budgets":
            try: return self._json(200,{"items":self.db.list_budgets(self._query(parsed,"year"),self._query(parsed,"currency","USD"),self._query(parsed,"department"),self._query(parsed,"project"))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/rates/suggest":
            try:
                rates=self.db.suggested_rates(self._query(parsed,"currency","USD"),self._query(parsed,"date"))
                return self._json(200,{k:(float(v) if not isinstance(v,str) else v) for k,v in rates.items()})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/payroll/settings/list": return self._json(200,{"items":self.db.list_payroll_settings()})
        if path == "/api/vat-return":
            try:
                year=self._query(parsed,"year"); result=vat_return.build_vat_return(self.db,year,self._query(parsed,"quarter"),self._query(parsed,"currency"),
                    self._query(parsed,"include_review","false").lower()=="true",self._previous_year_db(year),self._query(parsed,"credit_brought_forward"),self._query(parsed,"refund_requested"))
                result["provisional_ratio"]=self.db.vat_provisional_ratio(year)
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,vat_return.json_ready(result))
        if path == "/api/vat-returns": return self._json(200,{"items":vat_return.list_saved_returns(self.db)})
        if path == "/api/alerts/documents":
            try: return self._json(200,self.db.legal_document_alerts(int(self._query(parsed,"days","30"))))
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/fiscal-year/journal":
            query=parse_qs(parsed.query)
            try:
                company_id=self.headers.get("X-Company-ID"); year=int(query.get("year",[""])[0])
                if not company_id: raise ValueError("Select a company first")
                year_db=self.company_manager.database(company_id,year)
                return self._json(200,{"items":year_db.journal(query.get("from_date",[None])[0],query.get("to_date",[None])[0],query.get("currency",[None])[0]),"year":year,"read_only":True})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/invoices/next-number":
            try: return self._json(200,{"invoice_number":self.db.next_invoice_number(self._query(parsed,"kind","sale"),self._query(parsed,"date"))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/parties/next-number":
            try: return self._json(200,{"account_number":self.db.next_party_account_number(self._query(parsed,"prefix",""))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/invoices/") and path.endswith("/items"):
            try: return self._json(200,{"items":self.db.invoice_detail(int(path.split("/")[-2])).get("items",[])})
            except KeyError: return self._json(404,{"error":"Invoice not found"})
        if path == "/api/invoices":
            return self._json(200, {"items": self.db.list_invoices()})
        if path.startswith("/api/invoices/") and path.endswith("/detail"):
            try: result=self.db.invoice_detail(int(path.split("/")[-2]))
            except KeyError: return self._json(404,{"error":"Invoice not found"})
            return self._json(200,result)
        if path.startswith("/api/invoices/") and path.endswith("/history"):
            try: invoice_id=int(path.split("/")[-2]); items=self.db.invoice_history(invoice_id)
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"items":items})
        if path.startswith("/api/invoices/") and path.endswith("/attachments"):
            try: invoice_id=int(path.split("/")[-2]); items=self.db.list_attachments(invoice_id)
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"items":items})
        if path.startswith("/api/attachments/"):
            try:
                attachment=self.db.get_attachment(int(path.rsplit("/",1)[-1]))
                attachment["content"]=base64.b64encode(attachment["content"]).decode("ascii")
            except KeyError: return self._json(404,{"error":"Attachment not found"})
            return self._json(200,attachment)
        if path == "/api/document-cases": return self._json(200,{"items":self.db.list_document_cases()})
        if path.startswith("/api/document-cases/") and path.endswith("/attachments"):
            try: items=self.db.list_case_attachments(int(path.split("/")[-2]))
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"items":items})
        if path.startswith("/api/case-attachments/"):
            try:
                attachment=self.db.get_case_attachment(int(path.rsplit("/",1)[-1])); attachment["content"]=base64.b64encode(attachment["content"]).decode("ascii")
            except KeyError: return self._json(404,{"error":"Case attachment not found"})
            return self._json(200,attachment)
        if path.startswith("/api/parties/") and path.endswith("/documents"):
            try: items=self.db.list_party_documents(int(path.split("/")[-2]))
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"items":items})
        if path.startswith("/api/party-documents/"):
            try:
                document=self.db.get_party_document(int(path.rsplit("/",1)[-1])); document["content"]=base64.b64encode(document["content"]).decode("ascii")
            except KeyError: return self._json(404,{"error":"Party document not found"})
            return self._json(200,document)
        if path == "/api/accounts":
            return self._json(200, {"items": self.db.list_accounts()})
        if path == "/api/accounts/next-number":
            query=parse_qs(parsed.query)
            try: return self._json(200,{"account_number":self.db.next_account_number(query.get("prefix",[""])[0])})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/parties":
            return self._json(200, {"items": self.db.list_parties()})
        if path == "/api/branches": return self._json(200,{"items":self.db.list_branches()})
        if path == "/api/payments": return self._json(200,{"items":self.db.list_payments()})
        if path == "/api/expenses": return self._json(200,{"items":self.db.list_expenses()})
        if path == "/api/employees": return self._json(200,{"items":self.db.list_employees()})
        if path == "/api/payroll":
            query=parse_qs(parsed.query)
            return self._json(200,{"items":self.db.list_payroll(query.get("from_date",[None])[0],query.get("to_date",[None])[0])})
        if path == "/api/payroll/settings":
            query=parse_qs(parsed.query)
            return self._json(200,self.db.payroll_settings_for(query.get("date",[None])[0]))
        if path == "/api/employees/next-number":
            query=parse_qs(parsed.query)
            try: return self._json(200,{"employee_number":self.db.next_employee_number(query.get("prefix",["1000"])[0])})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/statement":
            query = parse_qs(parsed.query)
            try:
                party_id = int(query.get("party_id", [""])[0])
                result = self.db.statement_of_account(
                    party_id,
                    query.get("from_date", [None])[0],
                    query.get("to_date", [None])[0],
                    query.get("currency", [None])[0],
                    query.get("include_opening", ["true"])[0].lower() == "true",
                    query.get("display_currency", [None])[0],
                    query.get("branch_id",[None])[0],
                )
            except KeyError:
                return self._json(404, {"error": "Party not found"})
            except Exception as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(200, result)
        if path == "/api/dashboard":
            return self._json(200, {"items": self.db.dashboard()})
        if path == "/api/dashboard/professional": return self._json(200,self.db.professional_dashboard())
        if path == "/api/dashboard/conversion":
            source=self._query(parsed,"source","USD").upper(); target=self._query(parsed,"target","USD").upper()
            day=self._query(parsed,"date","")
            if source not in self.db.currency_codes() or target not in self.db.currency_codes(): return self._json(400,{"error":"Invalid currency"})
            try: rate=self.db._converted_amount(__import__("decimal").Decimal("1"),source,target,day)
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"rate":str(rate),"source":source,"target":target,"date":day})
        if path == "/api/users":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            return self._json(200,{"items":self.master_db.list_users()})
        if path == "/api/backups/download":
            try:
                target=self.db.backup_path(self._query(parsed,"name",""))
                return self._json(200,{"name":target.name,"content":base64.b64encode(target.read_bytes()).decode("ascii")})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/backups/folder": return self._json(200,{"folder":str(self.db._backups_dir())})
        if path == "/api/backups":
            return self._json(200,{"items":self.db.list_backups()})
        if path == "/api/settings": return self._json(200,self.db.settings())
        if path == "/api/currencies": return self._json(200,{"items":self.db.currencies()})
        if path == "/api/exchange-rates": return self._json(200,{"items":self.db.list_exchange_rates()})
        if path == "/api/doe/candidates":
            try: return self._json(200,self.db.doe_candidates(self._query(parsed,"date",""),self._query(parsed,"basis","LBP")))
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/trial-balance":
            query = parse_qs(parsed.query)
            from_date = query.get("from_date", [None])[0]
            to_date = query.get("to_date", [None])[0]
            return self._json(200, {"items": self.db.trial_balance(from_date, to_date,
                query.get("account",[None])[0],query.get("include_subaccounts",["true"])[0].lower()=="true",
                query.get("account_from",[None])[0],query.get("account_to",[None])[0],query.get("branch_id",[None])[0],query.get("posting_status",["posted"])[0])})
        if path == "/api/journal":
            query = parse_qs(parsed.query)
            return self._json(200, {"items": self.db.journal(
                query.get("from_date", [None])[0],
                query.get("to_date", [None])[0],
                query.get("currency", [None])[0],
            )})
        if path.startswith("/api/journal-vouchers/"):
            try: return self._json(200,self.db.journal_voucher_detail(int(path.rsplit("/",1)[-1])))
            except KeyError: return self._json(404,{"error":"Journal Voucher not found"})
        if path == "/api/profit-loss":
            query=parse_qs(parsed.query)
            return self._json(200,{"items":self.db.profit_and_loss(query.get("from_date",[None])[0],query.get("to_date",[None])[0],query.get("currency",[None])[0])})
        if path == "/api/fiscal-years":
            return self._json(200,{"items":self.db.list_fiscal_years()})
        if path == "/api/general-ledger":
            query=parse_qs(parsed.query)
            return self._json(200,self.db.general_ledger(query.get("account",[None])[0],query.get("from_date",[None])[0],query.get("to_date",[None])[0],query.get("currency",[None])[0]))
        if path == "/api/balance-sheet":
            query=parse_qs(parsed.query)
            return self._json(200,{"items":self.db.balance_sheet(query.get("to_date",[None])[0],query.get("currency",[None])[0])})
        if path == "/api/vat-report":
            query=parse_qs(parsed.query)
            return self._json(200,self.db.vat_report(query.get("from_date",[None])[0],query.get("to_date",[None])[0],query.get("currency",[None])[0]))
        if path == "/api/cash-flow":
            query=parse_qs(parsed.query)
            return self._json(200,{"items":self.db.cash_flow(query.get("from_date",[None])[0],query.get("to_date",[None])[0],query.get("currency",[None])[0])})
        if path == "/api/aging":
            query=parse_qs(parsed.query)
            return self._json(200,{"items":self.db.aging_report(query.get("as_of_date",[None])[0],query.get("kind",[None])[0],query.get("currency",[None])[0])})
        if path == "/api/comparative-reports":
            query=parse_qs(parsed.query)
            try: result=self.db.comparative_reports(query.get("from_date",[""])[0],query.get("to_date",[""])[0],query.get("currency",[None])[0])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        return self._json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body()
        except Exception:
            return self._json(400, {"error": "Invalid JSON"})
        if path == "/api/login":
            try: session = self.master_db.login(body.get("username", ""), body.get("password", ""), self.client_address[0])
            except PermissionError as exc: return self._json(403,{"error":str(exc)})
            if session and session.get("rate_limited"):
                return self._json(429,{"error":"Too many sign-in attempts. Try again later."})
            return self._json(200, session) if session else self._json(401, {"error": "Invalid username or password"})
        user = self._user()
        if not user:
            return self._json(401, {"error": "Unauthorized"})
        if path == "/api/companies":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: result=self.company_manager.create_company(body,self.master_db)
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"company":result})
        if path == "/api/companies/year":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: result=self.company_manager.create_year(body.get("company_id"),body.get("year"),user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"company":result})
        if not self._select_database(): return
        fiscal_admin_paths=("/api/reports/financial-config","/api/fiscal-years/reopen","/api/fiscal-years/refresh-opening","/api/fiscal-years/delete")
        if path not in fiscal_admin_paths and self.headers.get("X-Company-ID") and self.headers.get("X-Fiscal-Year") and self.company_manager.year_status(self.headers.get("X-Company-ID"),self.headers.get("X-Fiscal-Year"))=="closed":
            return self._json(423,{"error":"This fiscal year is closed and read-only"})
        if user["role"] == "viewer":
            return self._json(403,{"error":"Viewer access is read-only"})
        if self._module_denied(user, path): return
        if path == "/api/reports/financial-config":
            try:
                import financial_statements
                target = self.company_manager.database(self.headers.get("X-Company-ID"),int(body["year"]))
                return self._json(200,financial_statements.save_config(target,body["config"],user["id"]))
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/fixed-assets":
            try: return self._json(201,{"asset":fixed_assets.save_asset(self.db,body,user_id=user["id"])})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/fixed-assets/") and path.endswith("/post"):
            try: return self._json(201,{"voucher":fixed_assets.post_period(self.db,int(path.split("/")[-2]),body.get("period_end"),user["id"],self.headers.get("X-Fiscal-Year"))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/expenses/") and path.endswith("/attachments"):
            try:
                raw=base64.b64decode(body.get("content","").encode("ascii"),validate=True)
                return self._json(201,{"attachment_id":self.db.add_expense_attachment(int(path.split("/")[-2]),body.get("file_name"),body.get("mime_type"),raw,user["id"])})
            except KeyError: return self._json(404,{"error":"Expense not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/invoices/") and path.endswith("/replace"):
            try: return self._json(200,{"invoice_id":self.db.replace_manual_invoice(int(path.split("/")[-2]),body.get("invoice",{}),body.get("items",[]),user["id"])})
            except KeyError: return self._json(404,{"error":"Invoice not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/invoices/") and path.endswith("/landed-cost"):
            try: return self._json(201,{"invoice_id":self.db.add_landed_cost(int(path.split("/")[-2]),body,user["id"])})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/inventory/"):
            try:
                if path == "/api/inventory/items": return self._json(201,{"item":inventory.save_item(self.db,body,user["id"])})
                if path == "/api/inventory/warehouses": return self._json(201,{"item":inventory.save_warehouse(self.db,body,user["id"])})
                if path == "/api/inventory/settings": return self._json(200,inventory.save_settings(self.db,body,user["id"]))
                if path == "/api/inventory/documents":
                    return self._json(201,inventory.save_document(self.db,body.get("header",{}),body.get("lines",[]),user["id"],body.get("id")))
                if path == "/api/inventory/stock-variation": return self._json(200,inventory.post_stock_variation(self.db,body.get("year"),user["id"]))
                if path == "/api/inventory/categories": return self._json(200,inventory.save_category(self.db,body,user["id"]))
                if path == "/api/inventory/counts": return self._json(201,inventory.save_count(self.db,body.get("header",{}),body.get("lines",[]),user["id"],body.get("id"),bool(body.get("post"))))
                if path == "/api/inventory/find-or-create": return self._json(200,{"item":inventory.find_or_create_item(self.db,body.get("name"),body.get("unit"),body.get("sku"),user["id"],body.get("supplier_id"))})
            except KeyError as exc: return self._json(404,{"error":str(exc).strip("'")})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/payments/") and path.endswith("/allocations"):
            try: return self._json(200,{"items":self.db.save_allocations(int(path.split("/")[-2]),body.get("allocations",[]),user["id"])})
            except KeyError as exc: return self._json(404,{"error":str(exc).strip("'")})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/bank/"):
            try:
                import bank_rec
                action=path.rsplit("/",1)[-1]
                if action=="import": return self._json(201,{"added":bank_rec.add_statement_lines(self.db,body.get("account"),body.get("currency"),body.get("rows",[]),user["id"])})
                if action=="auto-match": return self._json(200,{"matched":bank_rec.auto_match(self.db,body.get("account"),body.get("currency"),iso_date(body.get("from")),iso_date(body.get("to")),int(body.get("days") or 5))})
                if action=="match": return self._json(200,{"ok":bank_rec.match(self.db,body.get("statement_id"),body.get("journal_line_id"))})
                if action=="unmatch": return self._json(200,{"ok":bank_rec.unmatch(self.db,body.get("statement_id"))})
                if action=="delete": return self._json(200,{"ok":bank_rec.delete_statement_line(self.db,body.get("statement_id"))})
                if action=="post": return self._json(201,{"voucher":bank_rec.post_statement_line(self.db,body.get("statement_id"),body.get("account_code"),user["id"])})
            except KeyError as exc: return self._json(404,{"error":str(exc).strip("'")})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path in ("/api/departments","/api/projects","/api/budgets"):
            try:
                saver={"/api/departments":self.db.save_department,"/api/projects":self.db.save_project,"/api/budgets":self.db.save_budget}[path]
                return self._json(201,{"item":saver(body,user["id"])})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/vat-return/adjustments":
            try: adjustment_id=vat_return.add_adjustment(self.db,body,user["id"],user["username"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"adjustment_id":adjustment_id})
        if path == "/api/vat-return/save":
            try:
                year=body.get("year"); result=vat_return.save_return(self.db,year,body.get("quarter"),user["id"],self._previous_year_db(year),body.get("credit_brought_forward"),user["username"],body.get("refund_requested"))
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,vat_return.json_ready(result))
        if path == "/api/vat-return/reopen":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: result=vat_return.reopen_return(self.db,body.get("year"),body.get("quarter"),user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/vat-ratio":
            try: return self._json(200,{"ratio":vat_return.json_ready(self.db.save_vat_provisional_ratio(body.get("year"),body.get("ratio"),user["id"]))})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/vat-classification":
            try: return self._json(200,self.db.set_vat_classification(body.get("source"),body.get("id"),body.get("vat_treatment"),body.get("vat_use"),user["id"]))
            except KeyError as exc: return self._json(404,{"error":str(exc).strip("'")})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/vat-recoverable":
            try: result=self.db.set_vat_recoverable(body.get("source"),body.get("id"),body.get("recoverable",True),user["id"])
            except KeyError as exc: return self._json(404,{"error":str(exc).strip("'")})
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/parties":
            try: result=self.db.save_party(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"party":result})
        if path == "/api/branches":
            try: result=self.db.save_branch(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"branch":result})
        if path == "/api/accounts":
            try: account=self.db.save_account(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"saved":True,"account":account})
        if path == "/api/users":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: result=self.master_db.save_user(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"user":result})
        if path == "/api/backups/create":
            return self._json(200,{"path":self.db.backup()})
        if path == "/api/backups/restore":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: result=self.db.restore_backup(body.get("name"),user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/settings":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: result=self.db.save_settings(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/currencies":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: currency=self.db.save_currency(body.get("code"),body.get("name"),user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"currency":currency})
        if path == "/api/exchange-rates":
            try: self.db.save_exchange_rate(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"saved":True})
        if path == "/api/exchange-rates/restore-euro":
            try: result=self.db.restore_euro_rates()
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/payments":
            try: payment_id=self.db.add_payment(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"payment_id":payment_id})
        if path == "/api/expenses":
            try: expense_id=self.db.add_expense(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"expense_id":expense_id})
        if path == "/api/employees":
            try: result=self.db.save_employee(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"employee":result})
        if path == "/api/payroll/calculate":
            try: result=self.db.calculate_payroll(body)
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/payroll":
            try: result=self.db.save_payroll(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"payroll":result})
        if path.startswith("/api/payroll/") and path.endswith("/post"):
            try: result=self.db.post_payroll(int(path.split("/")[-2]),user["id"])
            except KeyError: return self._json(404,{"error":"Payroll record not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"payroll":result})
        if path == "/api/payroll/nssf-filed":
            try: return self._json(201,{"item":self.db.save_nssf_filed_wages(body,user["id"])})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/payroll/nssf-payment":
            try: return self._json(201,self.db.record_nssf_payment(body,user["id"]))
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/payroll/delete-period":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: return self._json(200,{"items":self.db.delete_payroll_period(body.get("date_from"),user["id"])})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/payroll/apply-lebanese-rules":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: return self._json(200,{"items":self.db.apply_lebanese_payroll_rules(user["id"])})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/payroll/periods":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: return self._json(200,{"items":self.db.save_payroll_periods(body.get("periods") or [],user["id"])})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path == "/api/payroll/settings":
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: result=self.db.save_payroll_settings(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/journal-vouchers":
            try: result=self.db.save_journal_voucher(body.get("voucher",{}),body.get("lines",[]),user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,result)
        if path.startswith("/api/invoices/") and path.endswith("/items"):
            try:
                invoice_id = int(path.split("/")[-2])
                result = self.db.add_invoice_item(invoice_id, body.get("item", {}), user["id"])
            except KeyError:
                return self._json(404, {"error": "Invoice not found"})
            except Exception as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(201, {"invoice": result})
        if path.startswith("/api/invoices/") and path.endswith("/cancel"):
            try: result=self.db.cancel_invoice(int(path.split("/")[-2]),body.get("reason"),user["id"])
            except KeyError: return self._json(404,{"error":"Invoice not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"invoice":result})
        if path.startswith("/api/invoices/") and path.endswith("/duplicate"):
            try: result=self.db.duplicate_invoice(int(path.split("/")[-2]),user["id"])
            except KeyError: return self._json(404,{"error":"Invoice not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"invoice":result})
        if path.startswith("/api/invoices/") and path.endswith("/attachments"):
            try:
                raw=base64.b64decode(body.get("content","").encode("ascii"),validate=True)
                attachment_id=self.db.add_attachment(int(path.split("/")[-2]),body.get("file_name"),body.get("mime_type"),raw,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"attachment_id":attachment_id})
        if path == "/api/document-cases":
            try: result=self.db.save_document_case(body,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"case":result})
        if path.startswith("/api/document-cases/") and path.endswith("/attachments"):
            try:
                raw=base64.b64decode(body.get("content","").encode("ascii"),validate=True)
                attachment_id=self.db.add_case_attachment(int(path.split("/")[-2]),body.get("document_role"),body.get("file_name"),body.get("mime_type"),raw,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"attachment_id":attachment_id})
        if path.startswith("/api/document-cases/") and path.endswith("/post"):
            try: result=self.db.post_document_case(int(path.split("/")[-2]),user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"case":result})
        if path.startswith("/api/parties/") and path.endswith("/documents"):
            try:
                raw=base64.b64decode((body.get("content") or "").encode("ascii"),validate=True)
                document_id=self.db.add_party_document(int(path.split("/")[-2]),body,raw,user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(201,{"document_id":document_id})
        if path == "/api/fiscal-years/close":
            if user["role"] != "admin": return self._json(403,{"error":"Administrator permission required"})
            try:
                company_id=self.headers.get("X-Company-ID")
                if not company_id: raise ValueError("Select a company before closing the fiscal year")
                result=self.company_manager.close_and_open_year(company_id,body.get("year"),user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/fiscal-years/delete":
            if user["role"] != "admin": return self._json(403,{"error":"Administrator permission required"})
            try:
                company_id=self.headers.get("X-Company-ID")
                if not company_id: raise ValueError("Select a company first")
                result=self.company_manager.delete_year(company_id,body.get("year"),user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/fiscal-years/reopen":
            if user["role"] != "admin": return self._json(403,{"error":"Administrator permission required"})
            try:
                company_id=self.headers.get("X-Company-ID")
                if not company_id: raise ValueError("Select a company before reopening the fiscal year")
                result=self.company_manager.reopen_year(company_id,body.get("year"),user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/fiscal-years/refresh-opening":
            if user["role"] != "admin": return self._json(403,{"error":"Administrator permission required"})
            try:
                company_id=self.headers.get("X-Company-ID")
                if not company_id: raise ValueError("Select a company first")
                result=self.company_manager.refresh_opening(company_id,body.get("source_year"),user["id"])
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path == "/api/invoices/manual":
            invoice = body.get("invoice", {})
            items = body.get("items", [])
            if not isinstance(invoice, dict) or not isinstance(items, list) or len(items) > 500:
                return self._json(400, {"error": "Invalid manual invoice"})
            required = ("invoice_date", "party_name", "kind", "currency")
            missing = [field for field in required if not str(invoice.get(field) or "").strip()]
            if missing:
                return self._json(400, {"error": "Missing fields: " + ", ".join(missing)})
            try:
                invoice_id = self.db.create_manual_invoice(invoice, items, user["id"])
            except Exception as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(201, {"invoice_id": invoice_id})
        if path == "/api/invoices/import":
            items = body.get("items", [])
            if not isinstance(items, list) or len(items) > 5000:
                return self._json(400, {"error": "Invalid import batch"})
            if body.get("replace_existing", False):
                # Validate the entire replacement on a private SQLite snapshot first.
                # A failed row leaves the live database untouched.
                with self.db._lock, tempfile.TemporaryDirectory() as directory:
                    stage_path=Path(directory)/"replacement.db"
                    with closing(sqlite3.connect(self.db.path)) as source, closing(sqlite3.connect(stage_path)) as stage:
                        source.backup(stage)
                    stage_db=Database(stage_path)
                    try: replacement=stage_db.clear_invoices(user["id"],make_backup=False)
                    except Exception as exc: return self._json(400,{"error":str(exc)})
                    ids,errors=[],[]
                    for index,item in enumerate(items):
                        try: ids.append(stage_db.import_invoice(item,user["id"]))
                        except Exception as exc: errors.append({"index":index,"invoice_number":item.get("invoice_number") if isinstance(item,dict) else None,"error":str(exc)})
                    if errors:
                        return self._json(400,{"error":"Replacement cancelled; no existing data was changed","errors":errors})
                    try:
                        safety=self.db.backup("safety")
                        with closing(sqlite3.connect(stage_path)) as source,closing(sqlite3.connect(self.db.path)) as target:
                            source.backup(target)
                    except Exception as exc: return self._json(500,{"error":f"Replacement could not be saved: {exc}"})
                    return self._json(200,{"imported":len(ids),"ids":ids,"errors":[],"deleted":replacement["deleted"],"backup":safety})
            replacement={"deleted":0,"backup":None}
            ids, errors = [], []
            for index, item in enumerate(items):
                try:
                    ids.append(self.db.import_invoice(item, user["id"]))
                except Exception as exc:
                    errors.append({"index": index, "invoice_number": item.get("invoice_number"), "error": str(exc)})
            return self._json(200, {"imported": len(ids), "ids": ids, "errors": errors, "deleted": replacement["deleted"], "backup": replacement["backup"]})
        return self._json(404, {"error": "Not found"})

    def do_PUT(self):
        path = urlparse(self.path).path
        user = self._user()
        if not user:
            return self._json(401, {"error": "Unauthorized"})
        if path.startswith("/api/companies/"):
            if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
            try: result=self.company_manager.update_company(path.rsplit("/",1)[-1],self._body())
            except KeyError: return self._json(404,{"error":"Company not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"company":result})
        if not self._select_database(): return
        if self.headers.get("X-Company-ID") and self.headers.get("X-Fiscal-Year") and self.company_manager.year_status(self.headers.get("X-Company-ID"),self.headers.get("X-Fiscal-Year"))=="closed":
            return self._json(423,{"error":"This fiscal year is closed and read-only"})
        if user["role"] == "viewer":
            return self._json(403,{"error":"Viewer access is read-only"})
        if path.startswith("/api/party-documents/"):
            try:
                body=self._body(); raw=base64.b64decode((body.get("content") or "").encode("ascii"),validate=True)
                return self._json(200,{"document_id":self.db.update_party_document(int(path.rsplit("/",1)[-1]),body,raw,user["id"])})
            except KeyError: return self._json(404,{"error":"Party document not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/fixed-assets/"):
            try: return self._json(200,{"asset":fixed_assets.save_asset(self.db,self._body(),int(path.rsplit("/",1)[-1]),user["id"])})
            except KeyError: return self._json(404,{"error":"Asset not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
        if path.startswith("/api/payments/") or path.startswith("/api/expenses/"):
            try:
                body=self._body(); record_id=int(path.rsplit("/",1)[-1])
                result=self.db.update_payment(record_id,body,user["id"]) if path.startswith("/api/payments/") else self.db.update_expense(record_id,body,user["id"])
            except KeyError as exc: return self._json(404,{"error":str(exc).strip("'")})
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"id":result})
        if path.startswith("/api/journal-vouchers/"):
            try:
                body=self._body(); result=self.db.save_journal_voucher(body.get("voucher",{}),body.get("lines",[]),user["id"],int(path.rsplit("/",1)[-1]))
            except KeyError: return self._json(404,{"error":"Journal Voucher not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,result)
        if path.startswith("/api/invoices/"):
            try:
                invoice_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                return self._json(400, {"error": "Invalid invoice ID"})
            try:
                body = self._body()
                invoice = body.get("invoice", {})
                if not isinstance(invoice, dict):
                    raise ValueError("Invalid invoice details")
                updated = self.db.update_invoice(invoice_id, invoice, user["id"])
            except KeyError:
                return self._json(404, {"error": "Invoice not found"})
            except Exception as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(200, {"invoice": updated})
        if path.startswith("/api/accounts/"):
            code=path.rsplit("/",1)[-1]
            try: account=self.db.rename_account(code,self._body().get("name_en"),user["id"])
            except KeyError: return self._json(404,{"error":"Account not found"})
            except Exception as exc: return self._json(400,{"error":str(exc)})
            return self._json(200,{"account":account})
        return self._json(404, {"error": "Not found"})

    def do_DELETE(self):
        path=urlparse(self.path).path; user=self._user()
        if not user: return self._json(401,{"error":"Unauthorized"})
        if not self._select_database(): return
        if self.headers.get("X-Company-ID") and self.headers.get("X-Fiscal-Year") and self.company_manager.year_status(self.headers.get("X-Company-ID"),self.headers.get("X-Fiscal-Year"))=="closed":
            return self._json(423,{"error":"This fiscal year is closed and read-only"})
        if user["role"]=="viewer": return self._json(403,{"error":"Viewer access is read-only"})
        try:
            if self._module_denied(user, path): return
            if path.startswith("/api/fixed-assets/"): result=fixed_assets.delete_asset(self.db,int(path.rsplit("/",1)[-1]),user["id"])
            elif path.startswith("/api/vat-return/adjustments/"): result=vat_return.delete_adjustment(self.db,int(path.rsplit("/",1)[-1]),user["id"])
            elif path.startswith("/api/inventory/documents/"): result=inventory.delete_document(self.db,int(path.rsplit("/",1)[-1]),user["id"])
            elif path.startswith("/api/payments/"): result=self.db.delete_payment(int(path.rsplit("/",1)[-1]),user["id"])
            elif path.startswith("/api/expenses/"): result=self.db.delete_expense(int(path.rsplit("/",1)[-1]),user["id"])
            elif path.startswith("/api/invoices/"): result=self.db.mark_invoice_deleted(int(path.rsplit("/",1)[-1]),user["id"])
            elif path.startswith("/api/journal/"): result=self.db.delete_journal_voucher(int(path.rsplit("/",1)[-1]),user["id"])
            elif path.startswith("/api/opening-vouchers/"):
                if user["role"]!="admin": return self._json(403,{"error":"Administrator permission required"})
                result=self.db.delete_opening_voucher(int(path.rsplit("/",1)[-1]),user["id"])
            else: return self._json(404,{"error":"Not found"})
        except KeyError: return self._json(404,{"error":"Entry not found"})
        except Exception as exc: return self._json(400,{"error":str(exc)})
        return self._json(200,result)

def _keep_alive_safe(method):
    """Read the whole request body first and always answer, so a kept-open connection stays in step."""
    def handle(self):
        self._responded = False
        try: length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError: length = 0
        self._raw_body = self.rfile.read(length) if length > 0 else b""
        try:
            method(self)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True; return
        except Exception as exc:
            traceback.print_exc()
            if self._responded: self.close_connection = True; return
            try: self._json(500, {"error": f"The data service could not complete the request: {exc}"})
            except Exception: self.close_connection = True
            return
        if not self._responded:
            self._json(500, {"error": "The data service did not answer this request"})
    handle.__name__ = method.__name__; handle.__doc__ = method.__doc__
    return handle

for _verb in ("do_GET", "do_POST", "do_PUT", "do_DELETE"):
    setattr(ApiHandler, _verb, _keep_alive_safe(getattr(ApiHandler, _verb)))

def run_server(host="127.0.0.1", port=8765, database="saber_accounting.db", admin_password=None, tls_cert=None, tls_key=None, allow_insecure_lan=False):
    if bool(tls_cert)!=bool(tls_key): raise ValueError("Provide both TLS certificate and private key")
    if host not in ("127.0.0.1","localhost","::1") and not tls_cert and not allow_insecure_lan:
        raise ValueError("Shared network access requires --tls-cert and --tls-key (or explicit --allow-insecure-lan for a trusted VPN)")
    admin_password = admin_password or os.environ.get("SABER_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
    db = Database(database, pooled=True)
    db.initialize_if_needed(admin_password)
    ApiHandler.db = db; ApiHandler.master_db=db; ApiHandler.company_manager=CompanyManager(database, pooled=True)
    # Company data lives in companies/<Company Name>/<Company Name>_<year>.db (moved there once, safely).
    try:
        for source,target in ApiHandler.company_manager.organize_files(): print(f"Company file moved: {source} -> {target}")
    except Exception as exc: print(f"Company files were not reorganised this time: {exc}")
    server = ThreadingHTTPServer((host, port), ApiHandler)
    if tls_cert:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(tls_cert,tls_key)
        server.socket=context.wrap_socket(server.socket,server_side=True)
    print(f"Saber Accounting server running at {'https' if tls_cert else 'http'}://{host}:{port}")
    print("For a new database, sign in as admin with this one-time initial password:")
    print(admin_password)
    server.serve_forever()

def main():
    parser = argparse.ArgumentParser(description="Saber Accounting shared server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", default=str(Path.home() / "SaberAccounting" / "saber_accounting_v0_7.db"))
    parser.add_argument("--admin-password", default=None,
                        help="Initial admin password (or set SABER_ADMIN_PASSWORD)")
    parser.add_argument("--tls-cert",help="Path to a trusted TLS certificate chain (PEM)")
    parser.add_argument("--tls-key",help="Path to the matching TLS private key (PEM)")
    parser.add_argument("--allow-insecure-lan",action="store_true",help="Explicitly permit plaintext on a trusted VPN/LAN")
    args = parser.parse_args()
    Path(args.database).parent.mkdir(parents=True, exist_ok=True)
    run_server(args.host,args.port,args.database,args.admin_password,args.tls_cert,args.tls_key,args.allow_insecure_lan)

if __name__ == "__main__":
    main()
