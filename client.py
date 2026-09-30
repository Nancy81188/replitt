from __future__ import annotations

import json
import base64
import http.client
import socket
import ssl
import threading
import time
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit

class SessionExpired(RuntimeError):
    """Raised when the server no longer accepts the saved sign-in."""


# Reference lists the screens ask for again and again while they are built (the chart of accounts
# alone was requested ~40 times when a company opened). Their answers are kept for a few seconds
# and dropped immediately after ANY change the program sends, so what you see is always current.
CACHED_PATHS = ("/api/accounts", "/api/branches", "/api/currencies", "/api/exchange-rates", "/api/parties",
                "/api/projects", "/api/departments", "/api/settings", "/api/dimension-settings", "/api/inventory/items",
                "/api/inventory/warehouses", "/api/inventory/categories", "/api/me")
CACHE_SECONDS = 10.0


class ApiClient:
    def __init__(self, base_url="http://127.0.0.1:8765", on_unauthorized=None):
        self.base_url = base_url.rstrip("/")
        self.token = None
        self.company_id = None
        self.fiscal_year = None
        self.on_unauthorized = on_unauthorized
        self._local = threading.local()      # one kept-open connection per thread
        self._cache = {}; self._cache_lock = threading.Lock()

    # ------------------------------------------------------------ connection handling
    def _connection(self):
        connection = getattr(self._local, "connection", None)
        if connection is None:
            parts = urlsplit(self.base_url)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise URLError(f"invalid server address {self.base_url}")
            if parts.scheme == "https":
                connection = http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=60, context=ssl.create_default_context())
            else:
                connection = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=60)
            connection.connect()
            try: connection.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except (OSError, AttributeError): pass
            self._local.connection = connection; self._local.prefix = parts.path.rstrip("/")
        return connection

    def _drop_connection(self):
        connection = getattr(self._local, "connection", None); self._local.connection = None
        if connection is not None:
            try: connection.close()
            except Exception: pass

    def _send(self, method, path, data, headers):
        """One HTTP exchange on the kept-open connection. A connection the server already closed is
        reopened once; only a GET is ever repeated after it may have reached the server."""
        for attempt in (1, 2):
            sent = False
            try:
                connection = self._connection()
                connection.request(method, self._local.prefix + path, body=data, headers=headers); sent = True
                response = connection.getresponse(); payload = response.read()
                if response.getheader("Connection", "").lower() == "close" or response.version == 10: self._drop_connection()
                return response.status, payload
            except (http.client.RemoteDisconnected, ConnectionResetError, ConnectionAbortedError, BrokenPipeError, http.client.CannotSendRequest, http.client.BadStatusLine) as exc:
                self._drop_connection()
                if attempt == 2 or (sent and method != "GET"): raise URLError(exc) from exc
            except socket.timeout as exc:
                self._drop_connection(); raise TimeoutError(str(exc)) from exc
            except OSError as exc:
                self._drop_connection(); raise URLError(exc) from exc

    def close(self):
        self._drop_connection()

    def __del__(self):
        try: self._drop_connection()
        except Exception: pass

    def clear_cache(self):
        with self._cache_lock: self._cache.clear()

    def request(self, method, path, body=None):
        cacheable = method == "GET" and path.split("?", 1)[0] in CACHED_PATHS
        key = (self.token, self.company_id, self.fiscal_year, path)
        if cacheable:
            with self._cache_lock: hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_SECONDS: return json.loads(hit[1])
        elif method != "GET":
            self.clear_cache()  # anything may have changed
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.company_id: headers["X-Company-ID"]=str(self.company_id)
        if self.fiscal_year: headers["X-Fiscal-Year"]=str(self.fiscal_year)
        try:
            status, payload = self._send(method, path, data, headers)
        except URLError as exc:
            raise RuntimeError(f"Cannot reach the Saber Accounting data service at {self.base_url}. "
                               "Check that the server computer is on and the address is correct.") from exc
        except TimeoutError as exc:
            raise RuntimeError("The data service took too long to answer. Please try again.") from exc
        if status >= 400:
            try: message = json.loads(payload.decode("utf-8")).get("error", f"HTTP Error {status}")
            except Exception: message = f"The server returned an error ({status}). Please try again."
            if status == 401 and path != "/api/login" and self.token:
                self.token = None; self.clear_cache()
                if self.on_unauthorized:
                    try: self.on_unauthorized()
                    except Exception: pass
                raise SessionExpired("Your session has ended. Please sign in again.")
            raise RuntimeError(message)
        result = json.loads(payload.decode("utf-8"))
        if cacheable:
            with self._cache_lock: self._cache[key] = (time.monotonic(), payload)
        return result

    def login(self, username, password):
        result = self.request("POST", "/api/login", {"username": username, "password": password})
        self.token = result["token"]
        return result

    def dashboard(self): return self.request("GET", "/api/dashboard")["items"]
    def companies(self): return self.request("GET","/api/companies")["items"]
    def create_company(self,item): return self.request("POST","/api/companies",item)["company"]
    def update_company(self,company_id,item): return self.request("PUT",f"/api/companies/{company_id}",item)["company"]
    def create_fiscal_year(self,company_id,year): return self.request("POST","/api/companies/year",{"company_id":company_id,"year":year})["company"]
    def select_company_year(self,company_id,year): self.company_id=company_id; self.fiscal_year=int(year)
    def professional_dashboard(self): return self.request("GET","/api/dashboard/professional")
    def dashboard_conversion(self,source,target,date):
        return self.request("GET","/api/dashboard/conversion?"+urlencode({"source":source,"target":target,"date":date}))
    def invoices(self): return self.request("GET", "/api/invoices")["items"]
    def accounts(self): return self.request("GET", "/api/accounts")["items"]
    def next_account_number(self,prefix): return self.request("GET",f"/api/accounts/next-number?{urlencode({'prefix':prefix})}")["account_number"]
    def save_account(self,item): return self.request("POST","/api/accounts",item)["account"]
    def rename_account(self,code,name): return self.request("PUT",f"/api/accounts/{code}",{"name_en":name})["account"]
    def parties(self): return self.request("GET", "/api/parties")["items"]
    def branches(self): return self.request("GET","/api/branches")["items"]
    def save_branch(self,name): return self.request("POST","/api/branches",{"name":name})["branch"]
    def statement(self, party_id, from_date=None, to_date=None, currency=None, include_opening=True, display_currency=None, branch_id=None):
        query = urlencode({key:value for key,value in {
            "party_id":party_id,"from_date":from_date,"to_date":to_date,"currency":currency,
            "include_opening":"true" if include_opening else "false","display_currency":display_currency,"branch_id":branch_id
        }.items() if value})
        return self.request("GET", f"/api/statement?{query}")
    def add_invoice_item(self, invoice_id, item):
        return self.request("POST", f"/api/invoices/{invoice_id}/items", {"item":item})["invoice"]
    def trial_balance(self, from_date=None, to_date=None, account=None, include_subaccounts=True, account_from=None, account_to=None, branch_id=None, posting_status="posted"):
        query = urlencode({key: value for key, value in {
            "from_date": from_date, "to_date": to_date,"account":account,"include_subaccounts":"true" if include_subaccounts else "false","account_from":account_from,"account_to":account_to,"branch_id":branch_id,"posting_status":posting_status
        }.items() if value})
        path = "/api/trial-balance" + (f"?{query}" if query else "")
        return self.request("GET", path)["items"]
    def journal(self, from_date=None, to_date=None, currency=None):
        query = urlencode({key: value for key, value in {
            "from_date": from_date, "to_date": to_date, "currency": currency
        }.items() if value})
        path = "/api/journal" + (f"?{query}" if query else "")
        return self.request("GET", path)["items"]
    def import_invoices(self, items, replace_existing=True): return self.request("POST", "/api/invoices/import", {"items": items, "replace_existing": replace_existing})
    def create_manual_invoice(self, invoice, items): return self.request("POST", "/api/invoices/manual", {"invoice": invoice, "items": items})
    def update_invoice(self, invoice_id, invoice): return self.request("PUT", f"/api/invoices/{invoice_id}", {"invoice": invoice})
    def delete_invoice(self,invoice_id): return self.request("DELETE",f"/api/invoices/{invoice_id}")
    def delete_journal_voucher(self,entry_id): return self.request("DELETE",f"/api/journal/{entry_id}")
    def delete_opening_voucher(self,entry_id): return self.request("DELETE",f"/api/opening-vouchers/{entry_id}")
    def journal_voucher(self,entry_id): return self.request("GET",f"/api/journal-vouchers/{entry_id}")
    def save_journal_voucher(self,voucher,lines,entry_id=None): return self.request("PUT" if entry_id else "POST",f"/api/journal-vouchers/{entry_id}" if entry_id else "/api/journal-vouchers",{"voucher":voucher,"lines":lines})
    def fixed_assets(self): return self.request("GET","/api/fixed-assets")["items"]
    def asset_schedule(self,asset_id): return self.request("GET",f"/api/fixed-assets/{asset_id}/schedule")["items"]
    def save_asset(self,item,asset_id=None): return self.request("PUT" if asset_id else "POST",f"/api/fixed-assets/{asset_id}" if asset_id else "/api/fixed-assets",item)["asset"]
    def post_asset_period(self,asset_id,period_end): return self.request("POST",f"/api/fixed-assets/{asset_id}/post",{"period_end":period_end})["voucher"]
    def delete_asset(self,asset_id): return self.request("DELETE",f"/api/fixed-assets/{asset_id}")
    def invoice_detail(self, invoice_id): return self.request("GET",f"/api/invoices/{invoice_id}/detail")
    def cancel_invoice(self, invoice_id, reason): return self.request("POST",f"/api/invoices/{invoice_id}/cancel",{"reason":reason})["invoice"]
    def duplicate_invoice(self, invoice_id): return self.request("POST",f"/api/invoices/{invoice_id}/duplicate",{})["invoice"]
    def invoice_history(self, invoice_id): return self.request("GET",f"/api/invoices/{invoice_id}/history")["items"]
    def attachments(self, invoice_id): return self.request("GET",f"/api/invoices/{invoice_id}/attachments")["items"]
    def upload_attachment(self, invoice_id, file_name, mime_type, content):
        return self.request("POST",f"/api/invoices/{invoice_id}/attachments",{
            "file_name":file_name,"mime_type":mime_type,"content":base64.b64encode(content).decode("ascii")})
    def download_attachment(self, attachment_id):
        result=self.request("GET",f"/api/attachments/{attachment_id}"); result["content"]=base64.b64decode(result["content"]); return result
    def document_cases(self): return self.request("GET","/api/document-cases")["items"]
    def save_document_case(self,item): return self.request("POST","/api/document-cases",item)["case"]
    def post_document_case(self,case_id): return self.request("POST",f"/api/document-cases/{case_id}/post",{})["case"]
    def case_attachments(self,case_id): return self.request("GET",f"/api/document-cases/{case_id}/attachments")["items"]
    def upload_case_attachment(self,case_id,role,file_name,mime_type,content):
        return self.request("POST",f"/api/document-cases/{case_id}/attachments",{"document_role":role,"file_name":file_name,"mime_type":mime_type,"content":base64.b64encode(content).decode("ascii")})
    def download_case_attachment(self,attachment_id):
        result=self.request("GET",f"/api/case-attachments/{attachment_id}"); result["content"]=base64.b64decode(result["content"]); return result
    def party_documents(self,party_id): return self.request("GET",f"/api/parties/{party_id}/documents")["items"]
    def upload_party_document(self,party_id,item,content=b""):
        return self.request("POST",f"/api/parties/{party_id}/documents",{**item,"content":base64.b64encode(content or b"").decode("ascii")})
    def update_party_document(self,document_id,item,content=b""):
        return self.request("PUT",f"/api/party-documents/{document_id}",{**item,"content":base64.b64encode(content or b"").decode("ascii")})
    def download_party_document(self,document_id):
        result=self.request("GET",f"/api/party-documents/{document_id}"); result["content"]=base64.b64decode(result["content"]); return result
    def profit_loss(self, from_date=None, to_date=None, currency=None):
        query=urlencode({k:v for k,v in {"from_date":from_date,"to_date":to_date,"currency":currency}.items() if v})
        return self.request("GET","/api/profit-loss"+(f"?{query}" if query else ""))["items"]
    def fiscal_years(self): return self.request("GET","/api/fiscal-years")["items"]
    def close_fiscal_year(self, year): return self.request("POST","/api/fiscal-years/close",{"year":year})
    def reopen_fiscal_year(self, year): return self.request("POST","/api/fiscal-years/reopen",{"year":year})
    def refresh_opening(self, source_year): return self.request("POST","/api/fiscal-years/refresh-opening",{"source_year":source_year})
    def fiscal_year_journal(self,year,from_date=None,to_date=None,currency=None):
        query=urlencode({k:v for k,v in {"year":year,"from_date":from_date,"to_date":to_date,"currency":currency}.items() if v})
        return self.request("GET",f"/api/fiscal-year/journal?{query}")["items"]
    def save_party(self, item): return self.request("POST","/api/parties",item)["party"]
    def payments(self): return self.request("GET","/api/payments")["items"]
    def add_payment(self, item): return self.request("POST","/api/payments",item)
    def expenses(self): return self.request("GET","/api/expenses")["items"]
    def add_expense(self, item): return self.request("POST","/api/expenses",item)
    def general_ledger(self, account=None, from_date=None, to_date=None, currency=None):
        query=urlencode({k:v for k,v in {"account":account,"from_date":from_date,"to_date":to_date,"currency":currency}.items() if v})
        return self.request("GET","/api/general-ledger"+(f"?{query}" if query else ""))
    def balance_sheet(self, to_date=None, currency=None):
        query=urlencode({k:v for k,v in {"to_date":to_date,"currency":currency}.items() if v})
        return self.request("GET","/api/balance-sheet"+(f"?{query}" if query else ""))["items"]
    def vat_report(self, from_date=None, to_date=None, currency=None):
        query=urlencode({k:v for k,v in {"from_date":from_date,"to_date":to_date,"currency":currency}.items() if v})
        return self.request("GET","/api/vat-report"+(f"?{query}" if query else ""))
    def cash_flow(self,from_date=None,to_date=None,currency=None):
        query=urlencode({k:v for k,v in {"from_date":from_date,"to_date":to_date,"currency":currency}.items() if v}); return self.request("GET","/api/cash-flow"+(f"?{query}" if query else ""))["items"]
    def aging(self,as_of_date=None,kind=None,currency=None):
        query=urlencode({k:v for k,v in {"as_of_date":as_of_date,"kind":kind,"currency":currency}.items() if v}); return self.request("GET","/api/aging"+(f"?{query}" if query else ""))["items"]
    def comparative_reports(self,from_date,to_date,currency=None):
        query=urlencode({k:v for k,v in {"from_date":from_date,"to_date":to_date,"currency":currency}.items() if v}); return self.request("GET",f"/api/comparative-reports?{query}")
    def users(self): return self.request("GET","/api/users")["items"]
    def save_user(self,item): return self.request("POST","/api/users",item)["user"]
    def backups(self): return self.request("GET","/api/backups")["items"]
    def create_backup(self): return self.request("POST","/api/backups/create",{})
    def restore_backup(self,name): return self.request("POST","/api/backups/restore",{"name":name})
    def settings(self): return self.request("GET","/api/settings")
    def save_settings(self,item): return self.request("POST","/api/settings",item)
    def exchange_rates(self): return self.request("GET","/api/exchange-rates")["items"]
    def currencies(self): return self.request("GET","/api/currencies")["items"]
    def save_currency(self,code,name): return self.request("POST","/api/currencies",{"code":code,"name":name})["currency"]
    def save_exchange_rate(self,item): return self.request("POST","/api/exchange-rates",item)
    def restore_euro_rates(self): return self.request("POST","/api/exchange-rates/restore-euro",{})
    def employees(self): return self.request("GET","/api/employees")["items"]
    def next_employee_number(self,prefix="1000"):
        return self.request("GET",f"/api/employees/next-number?{urlencode({'prefix':prefix})}")["employee_number"]
    def save_employee(self,item): return self.request("POST","/api/employees",item)["employee"]
    def payroll(self,from_date=None,to_date=None):
        query=urlencode({k:v for k,v in {"from_date":from_date,"to_date":to_date}.items() if v})
        return self.request("GET","/api/payroll"+(f"?{query}" if query else ""))["items"]
    def calculate_payroll(self,item): return self.request("POST","/api/payroll/calculate",item)
    def save_payroll(self,item): return self.request("POST","/api/payroll",item)["payroll"]
    def post_payroll(self,payroll_id): return self.request("POST",f"/api/payroll/{payroll_id}/post",{})["payroll"]
    def payroll_settings(self,date=None):
        return self.request("GET","/api/payroll/settings"+(f"?{urlencode({'date':date})}" if date else ""))
    def save_payroll_settings(self,item): return self.request("POST","/api/payroll/settings",item)
    def me(self): return self.request("GET","/api/me")
    def payroll_settings_list(self): return self.request("GET","/api/payroll/settings/list")["items"]
    def payroll_report(self,report,period_type,year,index=1,group="both",include_drafts=False):
        query=urlencode({"report":report,"period_type":period_type,"year":year,"index":index,"group":group,"include_drafts":"true" if include_drafts else "false"})
        return self.request("GET",f"/api/payroll/reports?{query}")
    def nssf_filed_wages(self,year): return self.request("GET",f"/api/payroll/nssf-filed?{urlencode({'year':year})}")["items"]
    def save_nssf_filed_wages(self,item): return self.request("POST","/api/payroll/nssf-filed",item)["item"]
    def vat_return(self,year,quarter,currency=None,include_review=False,credit_brought_forward=None,refund_requested=None):
        query=urlencode({k:v for k,v in {"year":year,"quarter":quarter,"currency":currency,"include_review":"true" if include_review else "false",
            "credit_brought_forward":credit_brought_forward,"refund_requested":refund_requested}.items() if v not in (None,"")})
        return self.request("GET",f"/api/vat-return?{query}")
    def vat_returns(self): return self.request("GET","/api/vat-returns")["items"]
    def add_vat_adjustment(self,item): return self.request("POST","/api/vat-return/adjustments",item)
    def delete_vat_adjustment(self,adjustment_id): return self.request("DELETE",f"/api/vat-return/adjustments/{adjustment_id}")
    def save_vat_return(self,year,quarter,credit_brought_forward=None,refund_requested=None):
        return self.request("POST","/api/vat-return/save",{"year":year,"quarter":quarter,"credit_brought_forward":credit_brought_forward,"refund_requested":refund_requested})
    def save_vat_ratio(self,year,ratio): return self.request("POST","/api/vat-ratio",{"year":year,"ratio":ratio})["ratio"]
    def set_vat_classification(self,source,document_id,vat_treatment=None,vat_use=None):
        return self.request("POST","/api/vat-classification",{"source":source,"id":document_id,"vat_treatment":vat_treatment,"vat_use":vat_use})
    def reopen_vat_return(self,year,quarter): return self.request("POST","/api/vat-return/reopen",{"year":year,"quarter":quarter})
    def set_vat_recoverable(self,source,document_id,recoverable):
        return self.request("POST","/api/vat-recoverable",{"source":source,"id":document_id,"recoverable":bool(recoverable)})
    def document_alerts(self,days=30): return self.request("GET",f"/api/alerts/documents?{urlencode({'days':days})}")
    def next_invoice_number(self,kind="sale",date=None):
        return self.request("GET","/api/invoices/next-number?"+urlencode({k:v for k,v in {"kind":kind,"date":date}.items() if v}))["invoice_number"]
    def next_party_account_number(self,prefix): return self.request("GET",f"/api/parties/next-number?{urlencode({'prefix':prefix})}")["account_number"]
    def invoice_items(self,invoice_id): return self.request("GET",f"/api/invoices/{invoice_id}/items")["items"]
    def account_report(self,options): return self.request("GET","/api/reports/accounts?"+urlencode({"options":json.dumps(options)}))
    def suggested_rates(self,currency,date=None): return self.request("GET","/api/rates/suggest?"+urlencode({k:v for k,v in {"currency":currency,"date":date}.items() if v}))
    def doe_candidates(self,date,basis="LBP"): return self.request("GET","/api/doe/candidates?"+urlencode({"date":date,"basis":basis}))
    def departments(self): return self.request("GET","/api/departments")["items"]
    def save_department(self,item): return self.request("POST","/api/departments",item)["item"]
    def projects(self): return self.request("GET","/api/projects")["items"]
    def save_project(self,item): return self.request("POST","/api/projects",item)["item"]
    def budgets(self,year,currency="USD",department=None,project=None):
        return self.request("GET","/api/budgets?"+urlencode({k:v for k,v in {"year":year,"currency":currency,"department":department,"project":project}.items() if v}))["items"]
    def save_budget(self,item): return self.request("POST","/api/budgets",item)["item"]
    def next_document_number(self,kind,date=None): return self.request("GET","/api/documents/next-number?"+urlencode({k:v for k,v in {"kind":kind,"date":date}.items() if v}))["number"]
    def update_payment(self,payment_id,item): return self.request("PUT",f"/api/payments/{payment_id}",item)["id"]
    def delete_payment(self,payment_id): return self.request("DELETE",f"/api/payments/{payment_id}")
    def update_expense(self,expense_id,item): return self.request("PUT",f"/api/expenses/{expense_id}",item)["id"]
    def delete_expense(self,expense_id): return self.request("DELETE",f"/api/expenses/{expense_id}")
    def expense_attachments(self,expense_id): return self.request("GET",f"/api/expenses/{expense_id}/attachments")["items"]
    def upload_expense_attachment(self,expense_id,file_name,mime_type,content):
        return self.request("POST",f"/api/expenses/{expense_id}/attachments",{"file_name":file_name,"mime_type":mime_type,"content":base64.b64encode(content).decode("ascii")})
    def download_expense_attachment(self,attachment_id):
        result=self.request("GET",f"/api/expense-attachments/{attachment_id}"); result["content"]=base64.b64decode(result["content"]); return result
    def replace_invoice(self,invoice_id,invoice,items): return self.request("POST",f"/api/invoices/{invoice_id}/replace",{"invoice":invoice,"items":items})["invoice_id"]
    def add_landed_cost(self,purchase_id,item): return self.request("POST",f"/api/invoices/{purchase_id}/landed-cost",item)["invoice_id"]
    def landed_costs(self,purchase_id): return self.request("GET",f"/api/invoices/{purchase_id}/landed-costs")["items"]
    def closing_preview(self,year): return self.request("GET",f"/api/fiscal-years/closing-preview?{urlencode({'year':year})}")
    def apply_lebanese_payroll_rules(self): return self.request("POST","/api/payroll/apply-lebanese-rules",{})["items"]
    def inventory_items(self,date=None): return self.request("GET","/api/inventory/items"+(f"?{urlencode({'date':date})}" if date else ""))["items"]
    def save_inventory_item(self,item): return self.request("POST","/api/inventory/items",item)["item"]
    def warehouses(self): return self.request("GET","/api/inventory/warehouses")["items"]
    def save_warehouse(self,item): return self.request("POST","/api/inventory/warehouses",item)["item"]
    def inventory_settings(self): return self.request("GET","/api/inventory/settings")
    def save_inventory_settings(self,item): return self.request("POST","/api/inventory/settings",item)
    def stock_documents(self): return self.request("GET","/api/inventory/documents")["items"]
    def stock_document(self,document_id): return self.request("GET",f"/api/inventory/documents/{document_id}")
    def save_stock_document(self,header,lines,document_id=None): return self.request("POST","/api/inventory/documents",{"header":header,"lines":lines,"id":document_id})
    def delete_stock_document(self,document_id): return self.request("DELETE",f"/api/inventory/documents/{document_id}")
    def next_stock_number(self,doc_type,date): return self.request("GET","/api/inventory/next-number?"+urlencode({"type":doc_type,"date":date}))["number"]
    def inventory_report(self,report,options): return self.request("GET","/api/inventory/report?"+urlencode({"report":report,"options":json.dumps(options)}))
    def post_stock_variation(self,year): return self.request("POST","/api/inventory/stock-variation",{"year":year})
    def record_nssf_payment(self,item): return self.request("POST","/api/payroll/nssf-payment",item)
    def open_documents(self,party_id): return self.request("GET",f"/api/parties/{party_id}/open-documents")["items"]
    def payment_allocations(self,payment_id): return self.request("GET",f"/api/payments/{payment_id}/allocations")["items"]
    def save_allocations(self,payment_id,allocations): return self.request("POST",f"/api/payments/{payment_id}/allocations",{"allocations":allocations})["items"]
    def item_categories(self): return self.request("GET","/api/inventory/categories")
    def save_item_category(self,item): return self.request("POST","/api/inventory/categories",item)
    def count_sheet(self,warehouse_id,date): return self.request("GET","/api/inventory/count-sheet?"+urlencode({"warehouse_id":warehouse_id,"date":date}))["items"]
    def physical_counts(self): return self.request("GET","/api/inventory/counts")["items"]
    def physical_count(self,count_id): return self.request("GET",f"/api/inventory/counts/{count_id}")
    def save_physical_count(self,header,lines,count_id=None,post=False): return self.request("POST","/api/inventory/counts",{"header":header,"lines":lines,"id":count_id,"post":post})
    def find_or_create_item(self,name,unit="unit",sku=None,supplier_id=None): return self.request("POST","/api/inventory/find-or-create",{"name":name,"unit":unit,"sku":sku,"supplier_id":supplier_id})["item"]
    def delete_fiscal_year(self,year): return self.request("POST","/api/fiscal-years/delete",{"year":year})
    def download_backup(self,name):
        result=self.request("GET","/api/backups/download?"+urlencode({"name":name})); result["content"]=base64.b64decode(result["content"]); return result
    def backup_folder(self): return self.request("GET","/api/backups/folder")["folder"]
    def financial_config(self,year): return self.request("GET","/api/reports/financial-config?"+urlencode({"year":year}))
    def save_financial_config(self,year,config): return self.request("POST","/api/reports/financial-config",{"year":year,"config":config})
    def business_report(self,report,options): return self.request("GET","/api/reports/business?"+urlencode({"report":report,"options":json.dumps(options)}))
    def save_payroll_periods(self,periods): return self.request("POST","/api/payroll/periods",{"periods":periods})["items"]
    def delete_payroll_period(self,date_from): return self.request("POST","/api/payroll/delete-period",{"date_from":date_from})["items"]
    def dashboard_charts(self,year,basis="USD"): return self.request("GET","/api/reports/dashboard-charts?"+urlencode({"year":year,"basis":basis}))
    def bank_lines(self,account,currency,date_from,date_to,balance=None):
        return self.request("GET","/api/bank/lines?"+urlencode({k:v for k,v in {"account":account,"currency":currency,"from":date_from,"to":date_to,"balance":balance}.items() if v not in (None,"")}))
    def bank_action(self,action,item): return self.request("POST",f"/api/bank/{action}",item)
