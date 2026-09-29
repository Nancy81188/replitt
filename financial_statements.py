"""Reviewable IAS 1 reporting pack from each company's separate fiscal-year books.

No ledger mutations or automatic audit opinion. Saved presentation mappings are
explicit; cash flow classifications and disclosures require accountant review.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import re
from database import iso_date, utcnow

ZERO = Decimal('0')
KEY = 'financial_statement_draft'
GROUPS = {
    'ppe': 'Property, plant and equipment (net)',
    'intangible': 'Intangible assets (net)',
    'noncurrent_assets': 'Other non-current assets',
    'inventory': 'Inventories', 'receivables': 'Trade and other receivables',
    'cash': 'Cash and cash equivalents', 'current_assets': 'Other current assets',
    'capital': 'Share capital', 'reserves': 'Reserves', 'retained': 'Retained earnings / accumulated results',
    'noncurrent_liabilities': 'Non-current liabilities and provisions',
    'payables': 'Trade and other payables', 'current_liabilities': 'Other current liabilities',
    'revenue': 'Revenue (net of discounts)', 'other_income': 'Other income',
    'materials': 'Purchases and inventory movement', 'services': 'External services',
    'staff': 'Employee benefits expense', 'taxes': 'Other taxes and duties',
    'finance': 'Net finance costs', 'depreciation': 'Depreciation, amortisation and provisions',
    'other_expenses': 'Other expenses', 'income_tax': 'Income tax expense',
    'unmapped': 'Unmapped accounts - classification required',
}
ASSETS = ['ppe','intangible','noncurrent_assets','inventory','receivables','cash','current_assets']
EQUITY = ['capital','reserves','retained']
LIABILITIES = ['noncurrent_liabilities','payables','current_liabilities']
INCOME = ['revenue','other_income']
EXPENSES = ['materials','services','staff','taxes','finance','depreciation','other_expenses','income_tax']
NARRATIVES = {
 'Entity and activities': '[Complete legal form, domicile, registered address, activities and ownership.]',
 'Basis of preparation': '[Confirm applicable IFRS requirements, measurement basis, going concern and authorisation date. This draft does not assert compliance.]',
 'Material accounting policies': '[Describe policies relevant to this entity: IFRS 15 revenue, IFRS 9 financial instruments, IFRS 16 leases, IAS 2 inventory, IAS 12 taxes, IAS 16 assets and IAS 19 employee benefits.]',
 'Judgements and estimates': '[Describe material judgements, estimation uncertainty and impairment assessments.]',
 'Currency and inflation': '[Confirm functional and presentation currencies, IAS 21 translation and applicability of IAS 29. Recorded book equivalents are used; no automatic IAS 21/IAS 29 restatement is performed.]',
 'Related parties and commitments': '[Complete IAS 24 relationships, transactions, balances, commitments and contingencies; do not assume none.]',
 'Events and going concern': '[Complete IAS 10 events after the reporting period, going concern assessment and authorisation for issue.]',
 'Additional disclosures': '[Add entity-specific IFRS disclosures, financial risks, leases, tax reconciliation, asset roll-forwards and other material information.]',
}
AUDIT = {
 'Addressee': '[Shareholders / appropriate addressee]',
 'Opinion': '[Auditor to insert the opinion after completing the audit. No opinion has been generated.]',
 'Basis for opinion': '[Auditor to complete applicable ISAs, ethics and independence requirements, and evidence supporting the opinion.]',
 'Going concern / key audit matters': '[Auditor to assess applicable reporting requirements and complete or remove sections as appropriate.]',
 'Other information': '[Auditor to assess ISA 720 applicability and insert appropriate wording.]',
 'Management and governance responsibilities': '[Complete responsibilities for preparation, internal control, going concern and oversight.]',
 'Auditor responsibilities': '[Auditor to insert engagement-appropriate ISA reporting wording.]',
 'Other legal and regulatory requirements': '[Complete where applicable.]',
 'Signature, address and report date': '[Auditor name, signature, address and date - to be completed by the auditor.]',
}
SUPPLEMENTS = {
 'oci': 'Other comprehensive income (net of tax, signed)',
 'cf_operating': 'Net operating cash flows (signed)',
 'cf_investing': 'Net investing cash flows (signed)',
 'cf_financing': 'Net financing cash flows (signed)',
 'cf_fx': 'Exchange effect on cash (signed)',
}

def number(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite(): raise ValueError()
        return result
    except (InvalidOperation, ValueError): raise ValueError('Enter a finite numeric amount')

def money(value):
    return value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if value else ZERO

def years_from(value):
    parts = re.split(r'[,;\s]+', value.strip()) if isinstance(value, str) else value
    if not isinstance(parts, (list, tuple)) or not parts: raise ValueError('Choose one or two fiscal years, e.g. 2025 or 2024,2025')
    if any(not re.fullmatch(r'\d{4}', str(x)) for x in parts): raise ValueError('Years must be four digits')
    years = sorted({int(x) for x in parts}, reverse=True)
    if len(years) > 2 or any(y < 2000 or y > 2100 for y in years): raise ValueError('Choose one or two years between 2000 and 2100')
    return years

def config(db):
    return json.loads(db.settings().get(KEY) or '{}')

def save_config(db, data, user_id):
    if not isinstance(data, dict): raise ValueError('Invalid financial report settings')
    if data.get('basis','USD') not in ('USD','LBP'): raise ValueError('Choose USD or LBP')
    for field in ('mapping','supplements'):
        if not isinstance(data.get(field,{}),dict): raise ValueError('Invalid '+field)
    for code, group in data.get('mapping', {}).items():
        if not re.fullmatch(r'\d{1,12}', code) or group not in GROUPS: raise ValueError('Invalid account mapping')
    for name in ('notes', 'audit'):
        if not isinstance(data.get(name, {}), dict): raise ValueError('Invalid report text')
        for value in data.get(name, {}).values():
            if not isinstance(value, str) or len(value) > 20000: raise ValueError('Report text must be under 20,000 characters per section')
    for key, value in data.get('supplements', {}).items():
        if key not in SUPPLEMENTS: raise ValueError('Invalid supplementary amount')
        if value != '': number(value)
    text = json.dumps(data, ensure_ascii=False)
    with db.connect() as conn:
        conn.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (KEY,text))
        conn.execute('INSERT INTO audit_log(user_id,action,entity,details,created_at) VALUES(?,?,?,?,?)', (user_id,'update','financial_statement_draft',text,utcnow()))
    return data

def default_group(code, amount):
    # Lebanese chart; overrides can be applied to exact accounts or prefixes.
    if code.startswith(('21','281','291')): return 'intangible'
    if code.startswith(('22','23','282','283','292','293')): return 'ppe'
    if code.startswith('2'): return 'noncurrent_assets'
    if code.startswith('3'): return 'inventory'
    if code.startswith('10'): return 'capital'
    if code.startswith(('11','14')): return 'reserves'
    if code.startswith(('12','13')): return 'retained'
    if code.startswith(('15','16','17','18')): return 'noncurrent_liabilities'
    if code.startswith('49'): return 'receivables'
    if code.startswith('4'): return 'receivables' if amount >= 0 else 'payables'
    if code.startswith(('51','53')): return 'cash' if amount >= 0 else 'current_liabilities'
    if code.startswith('5'): return 'current_assets' if amount >= 0 else 'current_liabilities'
    if code.startswith(('70','71')): return 'revenue'
    if code.startswith('77'): return 'finance'
    if code.startswith('7'): return 'other_income'
    for prefix, group in [('60','materials'),('61','materials'),('62','services'),('63','staff'),('64','taxes'),('67','finance'),('65','depreciation'),('69','income_tax'),('6','other_expenses')]:
        if code.startswith(prefix): return group
    return 'unmapped'

def load_year(db, year, basis):
    """Use decimal text and recorded equivalents; never silently turn a missing FX rate into zero."""
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute("""SELECT j.*,a.code,a.name_en,e.entry_date,e.source_type,e.voucher_type,e.description entry_description,e.currency
          FROM journal_lines j JOIN journal_entries e ON e.id=j.entry_id JOIN accounts a ON a.id=j.account_id
          LEFT JOIN invoices i ON e.source_type='invoice' AND i.id=e.source_id
          WHERE (e.source_type!='invoice' OR i.status IN ('posted','cancelled') OR i.status IS NULL)""")]
    balances = defaultdict(lambda: ZERO); opening = defaultdict(lambda: ZERO); names = {}; count = 0
    for row in rows:
        day = iso_date(row['entry_date'])
        if day > f'{year}-12-31': continue
        if day >= f'{year}-01-01' and (row['source_type'] == 'year_close' or (row['voucher_type'] == '05' and (row['entry_description'] or '').startswith('CLOSING 6&7 - '))): continue
        code = row['code']; names[code] = row['name_en']
        value = number(row['debit']) - number(row['credit'])
        if row['line_currency'] and row['amount'] not in (None,''):
            raw = row['amount_usd'] if basis == 'USD' else row['amount_lbp']
            if raw in (None,''): raise ValueError(f'Missing {basis} equivalent for account {code}, {day}')
            value = number(raw) * (1 if value >= 0 else -1)
        elif row['currency'] != basis:
            value = db._converted_amount(value,row['currency'],basis,day)
        is_opening = day < f'{year}-01-01' or row['source_type'] == 'opening' or row['voucher_type'] == '04'
        if is_opening:
            opening[code] += value
            if code[:1] not in '67': balances[code] += value
        else:
            balances[code] += value; count += 1
    return balances, opening, names, count

def year_data(db, year, basis):
    cfg = config(db); balances, opening, names, count = load_year(db,year,basis)
    mapping = cfg.get('mapping', {})
    def group(code, value):
        found = [p for p in mapping if code.startswith(p)]
        return mapping[max(found,key=len)] if found else default_group(code,value)
    totals = defaultdict(lambda: ZERO); starts = defaultdict(lambda: ZERO); detail = []
    for code in sorted(set(balances) | set(opening)):
        value = balances[code]; g = group(code,value)
        # Class 6/7 opening balances are never current-year profit.
        totals[g] += value
        starts[group(code,opening[code])] += opening[code]
        if value or opening[code]: detail.append([code,names[code],GROUPS[g],money(opening[code]),money(value)])
    profit = -sum((totals[g] for g in INCOME + EXPENSES),ZERO)
    equity_start = -sum((starts[g] for g in EQUITY),ZERO)
    equity_end = -sum((totals[g] for g in EQUITY),ZERO) + profit
    supplements = cfg.get('supplements', {}) if cfg.get('basis',basis) == basis else {}
    extra = {k:number(v) for k,v in supplements.items() if v != ''}
    return dict(config=cfg,totals=totals,opening=starts,profit=profit,detail=detail,count=count,
                equity_start=equity_start,equity_end=equity_end,extra=extra)

def build(databases, options):
    years = years_from(options.get('years')); basis = options.get('basis','USD')
    if basis not in ('USD','LBP'): raise ValueError('Choose USD or LBP')
    missing = [str(y) for y in years if y not in databases]
    if missing: raise ValueError('Fiscal year not found: ' + ', '.join(missing))
    data = {y:year_data(databases[y],y,basis) for y in years}
    latest = data[years[0]]; settings = databases[years[0]].settings(); sections = []
    warnings = ['DRAFT - accountant review required. No IFRS compliance assertion or audit opinion is generated.',
                'All selected years use posted books, opening balances and recorded currency equivalents. Closing P&L transfers are excluded.',
                'Default Lebanese account classifications require review, including maturity, offsetting, cash equivalents and OCI.',
                'Supplementary OCI and cash-flow figures are presentation inputs, not journal entries. Post accounting adjustments separately.']
    if len(years)==1: warnings.append('Single-year presentation: prior-year comparatives required by IAS 1 are omitted.')
    elif years[0]-years[1]!=1: warnings.append('Selected years are not consecutive: preceding-year IAS 1 comparatives are missing.')
    if years[0]>=2027: warnings.append('Assess IFRS 18 applicability: this pack uses the IAS 1 presentation structure, not an IFRS 18 implementation.')
    def table(title, specs):
        rows=[]; total_rows=[]
        for label, fn, total in specs:
            rows.append([label]+[money(fn(data[y])) if isinstance(fn(data[y]),Decimal) else fn(data[y]) for y in years])
            if total: total_rows.append(len(rows)-1)
        sections.append(dict(heading=title,headers=['Description']+[f'{y} ({basis})' for y in years],rows=rows,total_rows=total_rows))
    def amount(g): return lambda d:d['totals'][g] * (-1 if g in EQUITY+LIABILITIES+INCOME else 1)
    specs=[(GROUPS[g],amount(g),False) for g in ASSETS]
    specs += [('TOTAL ASSETS',lambda d:sum((d['totals'][g] for g in ASSETS),ZERO),True)]
    specs += [(GROUPS[g],amount(g),False) for g in EQUITY]
    specs += [('Current-year profit / (loss)',lambda d:d['profit'],False),('TOTAL EQUITY',lambda d:d['equity_end'],True)]
    specs += [(GROUPS[g],amount(g),False) for g in LIABILITIES]
    specs += [('TOTAL LIABILITIES',lambda d:-sum((d['totals'][g] for g in LIABILITIES),ZERO),True),
              ('TOTAL EQUITY AND LIABILITIES',lambda d:d['equity_end']-sum((d['totals'][g] for g in LIABILITIES),ZERO),True),
              ('Balance check (must be zero)',lambda d:sum((d['totals'][g] for g in ASSETS+LIABILITIES),ZERO)-d['equity_end'],True)]
    table('Statement of financial position at 31 December', specs)
    table('Statement of profit or loss and other comprehensive income',
          [(GROUPS[g],amount(g),False) for g in INCOME+EXPENSES]+[
              ('PROFIT / (LOSS)',lambda d:d['profit'],True),
              ('Other comprehensive income (net of tax)',lambda d:d['extra'].get('oci','REVIEW REQUIRED'),False),
              ('TOTAL COMPREHENSIVE INCOME',lambda d:d['profit']+d['extra']['oci'] if 'oci' in d['extra'] else 'REVIEW REQUIRED',True)])
    for year in years:
        d=data[year]; oci=d['extra'].get('oci'); rows=[]
        # Separate opening, direct movements and earnings by equity component.
        for g in EQUITY:
            start=-d['opening'][g]; end=-d['totals'][g]; result=d['profit'] if g=='retained' else ZERO
            rows.append([GROUPS[g],money(start),money(end-start),money(result),money(end+result)])
        rows.append(['TOTAL',money(d['equity_start']),money(-sum((d['totals'][g]-d['opening'][g] for g in EQUITY),ZERO)),money(d['profit']),money(d['equity_end'])])
        sections.append(dict(heading=f'Statement of changes in equity - {year} ({basis})',headers=['Component','Opening','Direct book movements*','Profit / loss','Closing'],rows=rows,total_rows=[3]))
        warnings.append(f'{year}: equity direct movements require separation of owner transactions, OCI and restatements in the notes; OCI input is not added twice to book equity.')
    table('Statement of cash flows - classified totals (IAS 7 review)',[
        ('Opening cash and cash equivalents',lambda d:d['opening']['cash'],False),
        *[(label,lambda d,k=k:d['extra'].get(k,'REVIEW REQUIRED'),False) for k,label in SUPPLEMENTS.items() if k.startswith('cf_')],
        ('Closing cash and cash equivalents',lambda d:d['totals']['cash'],True),
        ('Unreconciled cash movement (must be zero)',lambda d:d['totals']['cash']-d['opening']['cash']-sum((d['extra'][k] for k in SUPPLEMENTS if k.startswith('cf_')),ZERO) if all(k in d['extra'] for k in SUPPLEMENTS if k.startswith('cf_')) else 'REVIEW REQUIRED',True)])
    for year in years:
        d=data[year]
        difference = sum((d['totals'][g] for g in ASSETS+LIABILITIES),ZERO)-d['equity_end']
        if abs(difference) >= Decimal('.01'): warnings.append(f'{year}: financial position does not balance ({money(difference)} {basis}). Resolve classification or book differences.')
        if d['config'].get('basis',basis) != basis and d['config'].get('supplements'):
            warnings.append(f'{year}: saved supplementary amounts use another currency; enter reviewed {basis} amounts.')
        if not d['count']: warnings.append(f'{year}: no posted operating movements found. Confirm opening balances and completeness.')
        if any(row[2] == GROUPS['unmapped'] for row in d['detail']): warnings.append(f'{year}: unmapped balance {money(d["totals"]["unmapped"])} {basis}. Review account mapping.')
        sections.append(dict(heading=f'Notes: account schedules - {year} ({basis})',headers=['Account','Name','Statement line','Opening signed','Closing / movement signed'],rows=d['detail'] or [['No posted balances','','','','']],total_rows=[]))
    for index,(name,default) in enumerate(NARRATIVES.items(),1):
        # Keep each year's disclosures separate rather than silently applying current text to comparatives.
        rows=[[str(y),data[y]['config'].get('notes',{}).get(name) or default] for y in years]
        sections.append(dict(heading=f'Note {index} - {name}',headers=['Year','Disclosure'],rows=rows,total_rows=[],narrative=True))
    for name, default in AUDIT.items():
        text=latest['config'].get('audit',{}).get(name) or default
        sections.append(dict(heading='Independent auditor report DRAFT - '+name,headers=['Text'],rows=[[p] for p in text.splitlines() if p.strip()] or [[default]],total_rows=[],narrative=True))
    sections.insert(0,dict(heading='Preparation and review',headers=['Review points'],rows=[[w] for w in warnings],total_rows=[],narrative=True))
    return dict(title='Financial Statements, Notes and Audit Report - DRAFT',
                meta=[f"Company: {settings.get('company_name') or '-'}",'Years: '+', '.join(map(str,years))+f' | Presentation currency: {basis}',
                      'Annual periods ending 31 December | IAS 1 / IAS 7 structure | Audit report: ISA 700 review template'],sections=sections)
