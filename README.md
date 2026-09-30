# Saber Accounting MVP

## Version 2.9.23 (Payroll: family allocation shown at once and editable)

- Payroll > Payroll Entry: the **Family Allocation** field now shows the automatic amount as soon as the employee (or the period date) is chosen, and after Calculate: spouse and children allowances of the period (Tax & NSSF Settings), within the maximum. Type in the field to use another amount for this payroll; Calculate and Save then use your amount (with a compliance note). Choosing another employee shows the automatic amount again.
- Includes everything from 2.9.19 - 2.9.22. Changed files: `desktop.py`, `test_ui_v2_9_18.py`, `installer.iss` and this README. Validation: 178 automated tests passed.

## Version 2.9.22 (Payroll: transport filled from the transport days)

- Payroll > Payroll Entry: typing the **Transport Days** fills **Transport** at once = days x the daily transport of the payroll period (Tax & NSSF Settings > Transport Exempt / Day, LBP 450,000 under the Lebanese rules), converted to the employee's currency at the period's rate for USD / other-currency employees. The amount can still be changed by hand afterwards.
- Includes everything from 2.9.19 - 2.9.21. Changed files: `desktop.py`, `test_ui_v2_9_18.py`, `installer.iss` and this README. Validation: 177 automated tests passed.

## Version 2.9.21 (Fix: Windows build test failure; switching company / year)

- Fixed the Windows build failure in "Run all tests" (`test_program_opens_on_the_dashboard_first_and_builds_the_rest`). On a slower PC the previous company's pages had finished building, and their (destroyed) widgets were still remembered, so after Switch Company / Year the program could think a page was already built. Every page widget of the previous screen is now forgotten when the screen is rebuilt, so the pages are rebuilt for the newly opened company / year. The test now reproduces the slower-PC case.
- Changed files: `desktop.py`, `test_ui_v2_9_18.py`, `installer.iss` and this README. Validation: 176 automated tests passed.

## Version 2.9.20 (Company data files named after the company, like the backups)

- Each company's data is now kept in a folder with the company's name, one file per fiscal year, named like its backups:
  - Data: `SaberAccounting\companies\<Company Name>\<Company Name>_<year>.db` (for example `companies\ECOLOGE LEBANON SARL\ECOLOGE LEBANON SARL_2025.db`).
  - Backups (unchanged): `SaberAccounting\backups\<Company Name>\<year>\<Company Name>_<year>_<date>.db`.
  - Deleted fiscal years: `companies\<Company Name>\deleted_years\`.
- Existing files are moved automatically the first time 2.9.20 starts. Each file is copied with SQLite's backup, checked (integrity check and the number of rows of every table), the company list is updated, and only then the old file is removed. A file that is in use by another program is left where it is, keeps working, and is moved on a later start. A company year that was stored inside the main file `saber_accounting_v0_7.db` is copied out to its company folder; the main file stays (it holds the users and passwords).
- Renaming a company (Manage Selected > Company Name) renames its data files and its backups folder to the new name.
- New companies and new fiscal years (Create Separate Year, year closing) are created directly in the company-named folder. Two companies with the same name get their company id added to the folder name.
- Tests changed on purpose because the file locations changed: `test_final_features.py` (deleted-years folder) and `test_regressions.py` (company data is read from the company file, not the main file).
- Validation: 176 automated tests passed (173 previous + 3 new in `test_company_named_files.py`: existing files moved with their data, new company / year named after the company, rename moves the files and the backups folder).
- Changed files: `company_manager.py`, `server.py`, `desktop.py` (version), `test_company_named_files.py` (new), `test_final_features.py`, `test_regressions.py`, `test_ui_v2_9_18.py` (frees window objects on the main thread), `installer.iss` and this README.

## Version 2.9.19 (Faster opening, DOE in LBP or USD books, payroll periods / director remuneration / family allocation, date dashes, item cost link)

- **Faster opening.** The program now shows the Dashboard as soon as a company is opened (measured about 10x faster to the first screen) and builds the other pages in the background right after; a page you click first is built at once. The Excel / PDF libraries are loaded the first time you export instead of when the program starts (the program's own code now loads about 4x faster).
- **Automatic DOE: choose the books and the currency.** "Revalue in" LBP (as before: foreign-currency class 4/5 balances revalued in LBP) or **USD** (LBP and other non-USD class 4/5 balances revalued in USD). "Currency" = All currencies or one currency. One DOE voucher is posted per currency. A USD DOE changes only the USD equivalent: the account's own balance and the LBP books do not move. From this version an LBP DOE also changes only the LBP books (earlier LBP DOE vouchers also moved the USD equivalent by the LBP difference converted at the day's rate; the USD DOE corrects that). Rates: LBP books "1 USD / 1 EUR = x LBP"; USD books "1 USD = x LBP" for LBP balances and "1 EUR = x USD" for others.
- **Payroll > Tax & NSSF Settings: periods can be edited freely.** Save Periods now saves the whole list together, so Date From / Date To can be changed and a period split (for example 01-05-2025 - 30-06-2025 with its own ceiling). The list is checked for overlaps and gaps first; if something is wrong nothing is saved and the message says which days. Each period keeps its tax brackets, allowances and accounts.
- **Payroll: Director Remuneration** (Payroll Entry): paid with the payroll, part of gross and net pay, **not subject to salary tax and not to NSSF**, posted to its own account (default 6316; set in Standard Posting Accounts for employees and managers). The payroll shows a compliance note.
- **Payroll: Family Allocation.** Payroll Entry has a Family Allocation field (empty = calculated automatically from the NSSF family allowance settings, as before; a number = that amount for this payroll). Standard Posting Accounts has a Family Allocation account (empty = offset on the NSSF account, as before).
- **Dates typed as digits get their dashes in every date field** (31122025 becomes 31-12-2025), including the payroll period cells, Journal Voucher date cells, the DOE date and the company VAT registration date.
- **Items: the cost price is a link.** Click it to open the item's Stock Card, which shows every purchase / sale and the running average cost.
- Validation: 173 automated tests passed (163 previous + new: payroll periods split / edit / overlap and gap refused, director remuneration not taxed and posted to 6316, manual family allocation on its own account, USD DOE moving only the USD equivalent, and on the program window: USD-books DOE for one selected currency, date dashes, the item cost link, dashboard-first opening).
- Changed files: `desktop.py`, `desktop_brains.py`, `desktop_final.py`, `desktop_inventory.py`, `database.py`, `server.py`, `client.py`, `chart_extra.py`, `report_export.py`, `importer.py`, `test_assets_doe.py`, `test_ui_v2_9_18.py`, `test_payroll_periods_director.py` (new), `installer.iss` and this README.

## Version 2.9.18 (Automatic DOE for all currencies, legal documents "Applies" + dates, fixes, faster program, wheel scrolling, right-click search)

- **Automatic DOE for all currencies at once.** Journal Voucher > Automatic DOE now loads every foreign-currency class 4/5 balance (USD, EUR, SAR, ...) in one screen, with one DOE date rate per currency (the suggested rate is filled in). Post DOE vouchers creates **one DOE voucher per currency** (one for USD, one for EUR, ...) holding all that currency's accounts, instead of one voucher per account. Each voucher credits the total gains to 775100000 and debits the total losses to 675100000 on separate lines; each account line says its foreign balance and carrying LBP. The DOE rule itself is unchanged (revaluation in LBP, gains credit 7751, losses debit 6751); a DOE voucher may now hold several class 4/5 accounts. The Journal Voucher has no "Calculate DOE" button (removed in 2.9.17).
- **Customers / Suppliers > Legal Documents.** Each document has an **Applies** tick and Issue / Expiry dates that can be **saved without a file** (attach the scan later with Attach / Replace File). Click a saved document to change its tick, dates or notes and press Save. The list shows a status (Valid, Expires in N days, EXPIRED, Not applicable). Documents whose tick is removed no longer raise expiry alerts. Dates are checked (DD-MM-YYYY, expiry not before issue). Existing documents keep their files and count as applying.
- **Fixed: Items > Stock Card crashed** and **Inventory Reports > Inventory Analysis (3D) could not run.** The code that builds the 3D options (rows / columns / measure) had been pasted into the Stock Card button instead of the Inventory Reports page, so Stock Card raised an error and the 3D report had no options. The options are back on the Inventory Reports page (shown only for the 3D report) and Stock Card opens the item's card again.
- **Fixed: page scrolling with the mouse wheel.** One wheel handler now scrolls whatever is under the pointer: tables and lists scroll themselves, everywhere else the page scrolls (Shift + wheel scrolls sideways). The old handler of some long forms switched the wheel off for the whole program when the mouse left them. Turning the wheel over a drop-down list no longer changes its value by accident; the page scrolls instead.
- **New: right-click search in any field.** Right-click in an account field and the account search opens (same as F2); in a customer / supplier field the parties search; on the account cell of the Journal Voucher, or an item cell, the matching search. Any other field shows a menu: Search accounts, Search customers / suppliers, Search items (the choice is written into the field), plus Cut, Copy, Paste and Select all. Listing tables keep their Search / Clear search menu.
- **Faster.** Measured on a test company (300 invoices): posting invoices is about 7x faster and opening a company about 40% faster; the gain is larger on Windows. How:
  - The program keeps one connection to its data service open and reuses it (HTTP keep-alive, no Nagle delay) instead of opening a new connection for every request.
  - The data service keeps each company file open instead of opening, configuring and closing it on every request (the file is released before a restore or a deleted year is moved).
  - Lists the screens request repeatedly (chart of accounts ~40 times when a company opens, branches, parties, currencies, rates...) are kept for 10 seconds and dropped at once after any change is saved.
  - A request that fails inside the data service now returns its error message instead of a "cannot reach the data service" message.
- Housekeeping: README note on DOE corrected (see 2.9.17); duplicate 2.9.5 heading clarified; removed `temp.txt` files and the `workflows - Shortcut.lnk` file; removed six unused imports; the background backup program must now build successfully (it was allowed to fail silently, leaving the "daily backups" option without its program); the Linux test workflow installs the same pinned versions as `requirements.txt`; installer paths use the real `Assets` folder name. The README has no sections for 2.9.12 and 2.9.13 (they were not recorded in earlier versions).
- No accounting rule, feature or test was removed or changed.
- Validation: 163 automated tests passed (151 previous tests + new tests in `test_ui_v2_9_18.py` on the real program window: Stock Card, 3D report options, wheel scrolling, right-click on account and plain fields, Automatic DOE posting one voucher per currency, a legal document saved with dates and no file; `test_legal_documents_applies.py`; and a grouped-DOE test in `test_assets_doe.py`).
- Changed files: `desktop.py`, `desktop_inventory.py`, `desktop_brains.py`, `desktop_final.py`, `client.py`, `server.py`, `database.py`, `company_manager.py`, `ai_service.py`, `bank_rec.py`, `inventory.py`, `year_end.py`, `test_assets_doe.py`, `test_ui_v2_9_18.py` (new), `test_legal_documents_applies.py` (new), `installer.iss`, `.github/workflows/build-windows-installer.yml`, `.github/workflows/tests.yml` and this README. Removed: `Assets/fonts/temp.txt`, `.github/workflows/temp.txt`, `workflows - Shortcut.lnk`.

## Version 2.9.17 (Remove Calculate DOE button + Linux CI test job)

- Removed the "Calculate DOE" button from the Journal Voucher screen and its underlying `prepare_doe` handler, per user request (the manual button was redundant). Exchange differences are still handled by the **Automatic DOE** screen (Journal Voucher > Automatic DOE): load the foreign class 4/5 balances for the DOE date (the suggested rate is filled in), preview, then post the selected lines. Gains credit `775100000` and losses debit `675100000`. Nothing is posted without the accountant pressing "Post selected DOE". *(Wording corrected in 2.9.18: the first version of this note said DOE was posted automatically, which is not the case.)*
- Added a dedicated Linux CI workflow (`.github/workflows/tests.yml`) that runs the full unit-test suite on `ubuntu-latest` on every push and pull request to `main`. It uses the system Python + system Tk (not `actions/setup-python`) to avoid a tkinter/Tk version mismatch, installs the runtime requirements, adds a lowercase `assets` symlink for the case-sensitive Linux filesystem, and runs the tests headlessly under `xvfb`. This complements the existing Windows build workflow, which already ran the tests on Windows.
- Removed the now-unused `simpledialog` import from `desktop_brains.py`.
- Changed files: `desktop_brains.py`, `desktop.py`, `installer.iss`, `.github/workflows/tests.yml` and this README.

## Version 2.9.16 (Fix Windows installer build)

- Fixed the Windows installer build failure `Source file "dist\SaberAccounting.exe" does not exist`. The application is now built with PyInstaller `--onedir`, which produces `dist\SaberAccounting\SaberAccounting.exe` inside a folder (not a single `dist\SaberAccounting.exe`). `installer.iss` was still packaging the old single-file path, so Inno Setup could not find the program. The `[Files]` section now packages the whole `dist\SaberAccounting\` folder (recurses subdirectories); `SaberAccounting.exe` still installs to `{app}\SaberAccounting.exe`, so all shortcuts, the uninstaller icon and the post-install "Open" action keep working.
- Added a "Verify the application was built" CI step so that if PyInstaller ever fails to produce the executable, the build now fails immediately with a clear message at the build step instead of a confusing error later in the Inno Setup step.
- No application feature or test was changed; this is a packaging/CI fix only.
- Changed files: `installer.iss`, `.github/workflows/build-windows-installer.yml`, `desktop.py` and this README.

## Version 2.9.15 (Speed / performance tuning)

- Database performance indexes added on the columns used for filtering and joins (invoices by party/kind/date/branch, invoice items, journal entries by source/date and journal lines by entry/account/party, stock movements, payments and allocations, expenses, payroll records, audit log, budgets and more). Previously only one index existed, so these lookups did full-table scans that got slow as data grew; now they use indexes. This applies automatically to every company database on next start.
- SQLite is now opened in WAL journal mode with `synchronous=NORMAL`, an in-memory temp store and a larger page cache. Reads stay fast while writing and disk churn is reduced. Foreign-key enforcement is unchanged.
- `ANALYZE` runs at the end of setup so the query planner actually uses the new indexes.
- The shared table search box is now debounced (~180 ms): typing a filter rebuilds the list once after you stop typing instead of on every keystroke, so large tables no longer feel laggy while searching. The filtering result is identical.
- Validation: 151 automated tests passed (147 previous + 4 new that guard the WAL journal mode, the required indexes, that an index is actually chosen for an invoice lookup, and that foreign keys stay enforced). No existing feature or test was removed.
- Changed files: `database.py`, `desktop.py`, `test_performance_tuning.py`, `installer.iss` and this README.

## Version 2.9.14 (Right-click search on every table)

- Every listing table now opens a right-click menu (Windows/Linux right button, macOS trackpad two-finger) with "Search…" and "Clear search". "Search…" jumps to and selects the table's search box so you can type immediately; "Clear search" empties it and shows all rows again. This is an additional way to reach the search bar that was already on top of every table (Ctrl+F still works) — no existing behaviour was changed.
- Validation: 147 automated tests passed (143 previous + 4 new that guard the right-click context menu, its Search / Clear search entries, and both right-click bindings). No existing feature or test was removed.
- Changed files: `desktop.py`, `test_table_context_menu.py`, `installer.iss` and this README.

## Version 2.9.11 (Payroll fairness rules and per-year projections)

- Family income-tax deduction is now split in half for a married employee whose spouse also works, so the spouse and children deduction is shared between the two working spouses instead of being claimed twice. A compliance note reminds you to confirm the split with your accountant. When the spouse does not work the full deduction is kept as before.
- The NSSF family allowance paid with the salary is shown explicitly on the individual salary statement (R6): a dedicated "NSSF Family Allowance" column reports the allowance already paid on behalf of the NSSF for each month, alongside gross, tax, NSSF and net.
- The employer end-of-service contribution (8.5%) is automatically exempted for foreign nationals (not covered by the end-of-service scheme) and for employees over 64 (past the end-of-service retirement age), based on the nationality and date of birth in the employee file. A compliance note states the reason; confirm eligibility with your accountant. Lebanese employees under 64 still owe the contribution.
- R3 / R3-1 registration and the NSSF employment (إعلام استخدام أجير) and termination (إعلام ترك أجير) declaration worksheets are auto-filled from the company (employer name, address, phone, MOF/VAT and NSSF employer numbers) and the selected employee file. Missing employer or employee fields are flagged. The official blank forms remain downloadable.
- The 5-Year Projection for both Cash Flow and Budget accepts a per-year growth override (for example `2027=10, 2028=5`) in addition to the single flat growth rate. Each future year can grow at its own rate; a saved budget for a year still wins over any growth assumption.
- Validation: 143 automated tests passed (138 previous + 5 new for the family-deduction split, end-of-service exemption, NSSF family allowance on the statement, and per-year projection growth). No existing feature or test was removed.
- Changed files: `database.py`, `payroll_reports.py`, `financial_projection.py`, `desktop.py`, `desktop_dimensions.py`, `test_final_features.py`, `test_financial_projection.py`, `installer.iss` and this README.

## Version 2.9.10 (Combined payroll and financial reporting update)

- Integrates PR #4 payroll/NSSF, journal-entry, visibility and login updates with PR #5 financial reporting. Version markers are unified; both change histories are retained.
- Business Reports > Financial Statements + Audit + Notes: enter one or two years (for example `2025` or `2024,2025`). Each year comes from the selected company's own database, latest year first. Annual calendar-year periods use posted entries, opening balances and exclude closing P&L transfers.
- Includes financial position, profit/loss and OCI, changes in equity by component, cash flow reconciliation, account schedules, editable notes and an editable audit-report draft. Print, PDF and Excel use the same selected-year pack; exports refresh to prevent stale results.
- Edit Notes / Audit / Mapping saves disclosures and account-prefix classification overrides per company/year, with an audit log. Presentation settings may be edited for closed years without unlocking or changing their books; viewers cannot save them.
- This is a preparation/review pack, not a compliance certification or issued audit opinion. Single-year or nonconsecutive comparisons are labelled. OCI and classified cash-flow totals must be supplied and reconciled; blanks remain REVIEW REQUIRED. Book equivalents do not automatically implement IAS 21 translation or IAS 29 restatement. Direct equity movements need disclosure of owner transactions, OCI and restatements. Review all classifications, disclosures and applicable standards, including IFRS 18 for periods from 2027.
- Validation: 130 automated tests passed, including separate-year API routing, closed-year draft permissions, closing-entry exclusion, cash reconciliation, saved disclosures, and PDF/Excel exports. PDF pages were visually reviewed.
- Changed files: `financial_statements.py`, `desktop_v22.py`, `server.py`, `client.py`, `report_export.py`, `test_financial_statements.py`, `installer.iss`, the Windows build workflow and this README.
- References: [IAS 1](https://www.ifrs.org/issued-standards/list-of-standards/ias-1-presentation-of-financial-statements/), [IAS 7](https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows/), [ISA 700](https://www.iaasb.org/publications/international-standard-auditing-isa-700-revised-forming-opinion-and-reporting-financial-statements).

## Version 2.9.9 (NSSF reporting and employee forms)

- NSSF contributions report defaults to Auto by employee count: fewer than ten employees in the selected month gives the full quarter; ten or more gives that month. The report shows the roster count and chosen declaration period. Monthly, quarterly and yearly remain selectable for review.
- Payroll > Employees offers blank official CNSS forms for registering a new employee, hiring an employee already registered with CNSS, and notifying CNSS that an employee left. R3 and R3-1 remain available.
- The annual NSSF settlement automatically shows monthly posted payroll contributions and wage bases alongside the filed wage bases and payments entered by the accountant. Unknown filed amounts remain blank instead of being guessed.
- Tax & NSSF Settings already provides editable, dated Family Ceiling and Sickness Ceiling. Default Family Ceiling is LBP 18,000,000 through April 2026 and LBP 28,000,000 from May 2026, with the effective May family allowances. Payroll tax and retroactive pay use the saved settings for their periods.

## Version 2.9.8 (Employee dates in Payroll)

- Payroll > Employees shows Starting Date and Leaving Date in the employee list, using the dates saved in each employee file. Double-click an employee or use Edit Selected to change them.

## Version 2.9.7 (Independent Department and Project controls)

- Departments and Projects now each have their own visibility checkbox in their respective Security data sheets. Either field can be hidden independently in entry forms, report filters, and Journal Voucher without deleting saved values. The application title matches the installer version.

## Version 2.9.6 (Department and Project visibility)

- The Departments and Projects data sheets under Security each have a Show Department / Project checkbox for entry forms, budget and report filters, and the Journal Voucher sheet.
- Hiding fields only changes the display; saved department and project data remains intact. Report filters return to All when hidden so an unseen filter cannot narrow the report.

## Version 2.9.5 (Journal entry and shared-server login protection)

- In Journal Voucher, the first letter selects a currency in the voucher header and the line currency cell. The line detail copies into the next line; editing the next line leaves the first unchanged.
- New Account in Journal Voucher creates an account immediately and places it on an available line without saving the voucher. Accounts created on the Accounts page are immediately recognized by an already-open Journal Voucher.
- Failed logins are audited without passwords or tokens. Five failures per username or 30 per client IP within 15 minutes trigger a 15-minute lockout; the server returns HTTP 429 while blocked.
- The shared server accepts a trusted TLS certificate and key. Plaintext is limited to localhost unless `--allow-insecure-lan` is deliberately specified for a trusted VPN/LAN.
## Version 2.9.5 - second update (5-Year Projection for Budget and Cash Flow)

- Budget page: a "5-Year Projection" section next to the existing quarterly/6-month/yearly forecast. Enter a target date up to 5 years after the "Actual report year" and, optionally, a yearly growth % applied to that year's posted income/expense actuals. For any future year that already has a saved budget, the saved budget is used instead of the growth %. The final (partial) year is prorated to the target date. Shown as net income/expense by year and by account, exportable like the existing forecast.
- Cash Flow Outlook page: the same "5-Year Projection" idea for cash inflow/outflow, projected per currency from the "Report year" actuals and a yearly growth %; the final year is prorated to the target date the same way.
- Both build on a new `financial_projection.long_term_projection()` helper (unit tested), capped at 5 years ahead of the base year.

## Version 2.9.4 (Equal height navigation rows)

- Navigation tabs in every row share the same height, including rows with labels that wrap onto two lines.

## Version 2.9.3 (Navigation and invoice controls alignment)

- The navigation tabs have visible spacing, stretch across the application window and automatically wrap into more rows as the window gets narrower; horizontal scrolling remains available on exceptionally narrow windows.
- On Uploaded Data, the Branch selector and both rows of invoice action buttons begin at the left edge below the table.

## Version 2.9.2 (Payroll registration worksheet)

- Employee files now retain nationality, parents' names, date of birth and place of birth. Existing company files add these empty fields automatically without changing saved payroll.
- Employees > R3 Registration Worksheet can preview, export PDF or export Excel with the saved employee details and highlights missing information. This worksheet helps prepare the Ministry of Finance's R3 new-employee registration; it is not the official form or an electronic submission. Complete the official form and its supporting documents separately.
- Employees has download buttons for the original Ministry of Finance R3 and R3-1 PDF forms. The original blank forms are downloaded from the Ministry website when requested.
- NSSF contributions report lists the employees in the selected period, counts both registered employees and employees with payroll, and shows missing NSSF numbers. The report's Employee List / Edit button opens the editable employee list.
- Payroll > Official Reports > SETTLEMENT builds an annual NSSF reconciliation from posted payroll. Use Filed NSSF Wages to enter the wages already declared for each month and actual payments; unknown values stay blank and the settlement remains incomplete. The difference uses the effective rates saved for each month. The entries have an audit log and do not post a journal voucher automatically.
- The original blank CNSS contributions, annual settlement and annual employee declaration PDFs can be downloaded from the CNSS links. Those public templates show a preprinted 9% sickness rate; compare the template with the period's saved rates before submission. The application's reconciliation is a review worksheet, not an official CNSS filing.
- The Employee File dialog scrolls on smaller screens, with Save always visible.
- Main navigation grows to fit both rows of tabs; outer page scrollbars appear only when the content exceeds the available space.

## Version 2.9.1

- Main window opens within the available screen dimensions and its minimum size respects smaller displays.
- Every main page now has vertical and horizontal scrollbars so forms, tables, and action buttons remain reachable on smaller screens or with larger Windows display scaling. The two-row navigation can scroll horizontally as well.
- General Journal action buttons and totals now appear above the table, so they are immediately visible instead of being squeezed against the bottom of the window.

## Version 2.9.0

- **Bank Reconciliation** (Payment & Receipt > Bank Reconciliation): import the bank statement (Excel or CSV: Date, Description, Reference, Debit / Credit or Amount) for a bank account (511 / 512 / 519 / 53), Auto Match (same amount, dates within 5 days), Match / Unmatch by hand, post statement-only items (bank charges 6739, interest...) as a voucher that is matched at once, and the reconciliation: book balance, deposits not yet at the bank, payments not yet cleared, statement items not booked, expected bank balance and the difference with the statement balance. Report in PDF / Excel / print.
- **Dashboard charts** for the fiscal year (USD or LBP): sales vs purchases and expenses by month, receivables by age, top 5 clients, cash and bank balances.
- **AI_RULES.md**: the rules for anyone (people, ChatGPT, Claude) who changes the program - start from the latest version, never remove features or tests, run the tests, deliver the whole project, accounting rules.
- VAT declaration box numbers: kept as the section layout (A / B / C / E / F) until the official Ministry of Finance form is provided.

## Version 2.8.3 (review)

- New currencies (for example SAR) now work everywhere: payroll converts LBP -> USD -> the new currency when there is no direct rate, and VAT adjustments accept any currency set up under Exchange Rates.
- Layout at 1366 x 768: "Due days from invoice" moved so its box is visible on Customers / Suppliers; Sales Invoice "Amount Paid", "Branch" and "VAT Treatment" moved to their own row so nothing is cut off.

## Version 2.8.2

- Purchase Invoice actions sit beside the shorter entry form; the item table has more height and a wider description column.
- In Inventory Reports, Stock Card has Item From / Item To selectors and the existing date From / To fields. The Ageing buckets entry box is removed; Stock Ageing uses its standard ageing buckets.
- The main navigation takes less space above the working area.
- Customer / Supplier Ageing lists invoice due dates and overdue days. Business Reports has Today and +30 days shortcuts and an expected collection/payment summary due by the chosen as-of date.
- Inventory Analysis (3D) compares item/category/supplier by warehouse or month, using quantity or cost value. Inventory Health lists stock issues needing review, including reorder levels, missing supplier or unit cost, and no recent issue.
- The Customers / Suppliers page links directly to Customer / Supplier Ageing and Client Items: Qty & Value; the latter lists each client's purchased items, quantity, sales before VAT, VAT, and TTC.

## Version 2.8.1

- Customer and supplier files include **Due days from invoice**. New invoices automatically use invoice date plus the saved term when Due Date is blank; an explicit Due Date takes precedence. Existing invoices keep their saved due dates.
- Purchase Invoice header is shorter so more item rows fit. Cost on Purchase uses predefined expense accounts, with an Edit Cost Accounts dialog for a particular posting.
- Inventory Reports adds Stock Turnover, Stock by Supplier, and Physical Count Variances. Stock Ageing can filter by item; Stock Card continues to use the selected item and From/To dates. Physical Inventory can add an item to its count sheet.
- Each manually entered exchange rate is saved separately. The daily rate used in reports is the arithmetic mean of entered rates for that date and currency pair. Automatic reference rates no longer overwrite a manual daily average.

Saber Accounting is a Windows desktop accounting application with a central shared database for three users. This first version includes:

- English, Arabic, and French interface
- Automatic USD, EUR, LBP, and AED detection from currency and amount cells
- Missing currency defaults to USD; conflicting or unsupported currencies are flagged for review
- Currency filter for the dashboard, invoices, trial balance, and exported reports
- Lebanese VAT at 11%
- Purchase and sales invoice import from Excel
- Manual purchase and sales invoice entry with multiple items
- Invoice deletion retains the invoice number and marks it DELETED; it removes the journal and stock effect. Linked allocations and active dependent invoices must be resolved first.
- Purchases and sales show gross total, discount, total after discount before VAT, VAT, and final total. Purchase discounts reduce the posted invoice amount and stock line costs.
- Journal Voucher Find searches each line's detail; each line detail can be edited in its own table column.
- Bank commissions on receipts and payments post to the nine-digit account 673900000.
- Stock Card accepts an item and From Date / To Date and includes the range in the report heading.
- Stock Ageing groups the on-hand value by receipt date in configurable ageing buckets, as of the selected To Date.
- Trial Balance can show EUR and AED equivalents as either reporting column. Add a three-letter currency under Security / Backup / Rates → Exchange Rates, then enter its exchange rate before cross-currency reporting.
- The dashboard uses compact currency summaries; purchase invoice entry keeps the items and totals on one page, while landed costs have a separate tab.
- Optional AI buttons suggest expense accounts and preview page 1 of a PDF invoice. The existing local account suggestion and PDF reader work without AI. For online assistance enter an OpenAI API key when prompted (kept in memory for that session), or set `SABER_AI_API_KEY` before starting the app. Each request needs confirmation, sends the description or first PDF page to OpenAI, may incur API charges, and never saves an invoice automatically. Review all amounts and the account before Save.
- Automatic 11% VAT per item, with editable VAT rate and VAT amount
- Editable total before VAT per item with automatic invoice totals
- Original invoice number when supplied; otherwise original Excel row number
- Completely empty rows skipped; duplicate invoices retained
- Automatic double-entry journal posting
- Invoice register, dashboard, and trial balance
- User authentication, roles, audit log, customer/supplier, inventory, and stock database foundations

## Important status

This is an MVP for controlled testing. TLS is available for shared access but requires a trusted certificate and secure server configuration. Fiscal-year closing blocks later edits, while finer monthly period locks remain to be added. Before production use, complete encrypted backup and restore, exchange-rate revaluation, and independent validation of Lebanese tax/NSSF reporting by the firm's accountant.

## Quick start on one computer

Install Python 3.11 or newer. Open Command Prompt in this folder and run:

```bat
python -m pip install -r requirements.txt
python run_server.py --admin-password YourStrongPassword
```

Open a second Command Prompt in the same folder:

```bat
python run_desktop.py
```

Sign in with username `admin`, your chosen server password, and server address `http://127.0.0.1:8765`.

## Three synchronized computers

1. Choose one always-on office computer or Windows server to host the shared database.
2. Give that computer a fixed local IP address.
3. Allow TCP port `8765` only on the trusted office network. Provision a certificate whose name matches the host name used by clients and whose CA is trusted on their computers.
4. Run `python run_server.py --host SERVER-IP --tls-cert server-cert.pem --tls-key server-key.pem` only on the server computer. Keep the private key restricted to the server account.
5. Run the desktop client on each of the three computers.
6. Enter `https://SERVER-NAME:8765` on the sign-in screen, using the name on the certificate.

For access outside the office, do not expose port 8765 directly to the internet. Use a professionally configured HTTPS reverse proxy or VPN. When TLS terminates at a reverse proxy, bind the Python server to `127.0.0.1` and proxy only to that loopback address. Existing trusted VPN/LAN installations that intentionally need plaintext must pass `--allow-insecure-lan`; HTTP traffic on such networks exposes passwords and tokens to anyone able to observe it.

## Excel import rules

The first worksheet is imported. Recognized English, Arabic, and French headings include Invoice Number, Date, Supplier/Customer Name, Total Before VAT, VAT, Total After VAT, Currency, and Type.

- If an invoice-number column contains a value, that value is used.
- Otherwise the original Excel row number is used. Excel row 24 becomes invoice 24.
- Completely empty rows are ignored.
- Duplicate invoices are deliberately retained.
- The original filename and Excel row number are stored for audit tracking.
- Missing VAT is calculated at 11% when the subtotal exists.
- Existing VAT values are preserved, even when they differ from 11%.
- Source totals that do not equal subtotal plus VAT are preserved, marked `review`, and posted against Import Variance so the ledger remains balanced.

## Build the Windows executable

On Windows, after installing the requirements:

```bat
pyinstaller --noconfirm --onefile --windowed --name SaberAccounting run_desktop.py
pyinstaller --noconfirm --onefile --name SaberAccountingServer run_server.py
```

The executables will be created in the `dist` folder. No GitHub account is required.

## Build a one-click installer online

Upload this project to a private GitHub repository. The included workflow runs the tests, creates the standalone client and server, and packages them as `SaberAccountingSetup.exe`. Open the repository's Actions tab, select **Build Saber Accounting Installer**, run the workflow, and download the **SaberAccountingSetup** artifact. End users do not need Python or GitHub.

## Version 0.7.1 fresh start

The default server database is `SaberAccounting/saber_accounting_v0_7.db`. This gives the upgraded application a completely fresh company file with only the default admin account. The previous `saber_accounting.db` is not loaded and remains available as a safety archive. New entries in v0.7.1 persist normally after the application is closed and reopened.

## Version 0.7.2 Excel currency formats

Excel imports detect USD, EUR, LBP, and AED from both cell contents and Excel Accounting/Custom number formats. This supports sheets where currency symbols are displayed beside numeric values without a separate Currency column. Imported dashboards, invoice lists, trial balances, and exports remain separated by currency.

## Version 0.7.3 currency page filter

The Import Excel preview includes an All/USD/EUR/LBP/AED selector and Apply button. Only rows assigned to the selected currency are displayed. Blank cells with leftover number formatting are ignored during detection; genuinely mixed rows are assigned using Total, Before VAT, and VAT evidence and remain flagged for review.

## Version 1.12.0 final release

### Payroll official reports (Payroll > Official Reports)
- **R10** quarterly salary tax withholding, **R5** annual employer declaration, **R6** individual annual statement.
- Any **month, quarter or year**; employees and managers in **separate sections**, plus a grand total.
- NSSF **employee 3%** and employer medical, family and end-of-service contributions.
- Rates and ceilings are **effective-dated (Date From to Date To)**: each month uses the rules in force on its own date. Saving a new Date From automatically ends the previous period the day before; overlapping periods are rejected.
- Separate columns for **retro salary (with its own retro tax)**, transport, schooling, bonus and 13th salary. R6 shows each retro period.
- Official amounts in LBP (other currencies converted at the payroll month's rate). Posted payroll only, with an optional draft preview.
- **Excel and PDF** export.

### Quarterly VAT (Quarterly VAT tab)
- **Q1-Q4** dates set automatically.
- Sales (output) VAT; deductible VAT on purchases, fixed assets, expenses and customs/imports; **non-deductible VAT** shown separately.
- VAT **payable or credit** carried forward to the next quarter (including into Q1 from the previous fiscal-year file).
- Totals **by currency with LBP equivalents**.
- **Manual adjustments** with a mandatory reason. Saving a return locks the quarter; only an administrator can reopen it.
- Marking VAT non-deductible (Uploaded Data > "VAT Deductible / Non-Deductible", or the expense checkbox) moves that VAT into cost, so the ledger always equals the return.
- **Excel and PDF** export.

### Security and polish
- New non-admin users are valid for **1 year** ("Renew 1 Year" in Security > Users). Expired users cannot sign in. Sessions end after 24 hours.
- Per-user **Payroll** and **VAT** access. At least one active administrator is always kept.
- **Legal document alerts** at sign-in and from the header button, for expired documents and documents expiring within 30 days.
- Backups use SQLite's online backup (safe while others work). Restore validates the file and creates a safety backup first.
- Clearer error messages. A page that fails to load no longer stops the others.

### Fixes
- Payroll saved from the desktop app now stores the period correctly (this previously affected payroll numbering and rate lookups).
- Exchange-rate lookups now pick the latest rate on or before the date, chronologically.
- Users created in Settings are saved to the sign-in database.

### To confirm with your accountant
The salary tax method is unchanged: transport and schooling are included in taxable salary, and one-off bonus / 13th salary are annualized ×12 in the month paid. Adjust in Tax & NSSF Settings or ask for a rule change if your practice differs.

### Build the installer (final workflow)
1. Upload this project to the GitHub repository (replace the old files).
2. Open **Actions**, select **Build Saber Accounting Installer**, click **Run workflow**. It also runs automatically on every push to `main`.
3. When it finishes, download the **SaberAccountingSetup** artifact and run `SaberAccountingSetup.exe`.

One installer only: no Python, no manual server. The data service starts automatically inside the app, and company data stays in the user's `SaberAccounting` folder across upgrades. First sign-in on a new computer: `admin` / `admin` (change it in Security > Users).


---

# Version 2.0.0 - complete release

## Modules
| Tab | What it does |
|---|---|
| Sales Invoice | Automatic number, editable lines (Item, description, qty, price, VAT), VAT treatment (taxable / zero-rated / exempt / out of scope), New / Save / Save & Post, reopen and edit |
| Journal Voucher | BRAINS-style voucher: multi-currency lines with LBP and USD amounts and rates, due date, reference, department, project, navigation |
| Import | Excel or PDF invoices as Purchases, Sales, Expenses or Assets. PDFs are read automatically and attached. Adds to existing data (replace is optional) |
| Customers / Suppliers | Account number first; type 4 digits and the full number fills in |
| Payment & Receipt | Customer receipts (RV-) and supplier payments (PV-) on the page, with balance, edit and delete |
| Purchases & Expenses | Purchases with PDF, cost on purchase (customs, freight, insurance, import VAT - manual, Excel or PDF), VAT use; expenses with PDF, Excel import, New / Edit / Delete / Search |
| Inventory | Items, warehouses, stock documents (opening, receipt, issue, adjustments, transfer), weighted average or FIFO, reports, stock variation |
| Payroll | Lebanese rules 2024-2026, R5 / R6 / R10 reports |
| Quarterly VAT | Lebanese periodic declaration with the partial deduction right |
| Trial Balance / Statement | Balance des Comptes options (BRAINS) |
| Profit & Loss | Fiscal-year dates, closing 6 & 7 as a Journal Voucher, automatic opening of the next year |
| Financial Reports | Ledger, balance sheet, cash flow, aging, comparative P&L, budget |
| Security / Backup / Rates | Users with 1-year validity and permissions, departments, projects, backups, exchange rates |

## Inventory (Lebanese periodic method)
- Purchases stay in 601. Stock quantities and costs come from the stock documents.
- Costing: weighted average (default) or FIFO. Stock can never go negative in a warehouse.
- A Sales Invoice line with an Item code issues the stock automatically (Stock Issue linked to the invoice; deleting or cancelling the invoice removes it).
- Reports: Stock Valuation (at any date, by warehouse, at cost and at sales price), Stock Card, Stock Movements, Sales Margin (COGS), Reorder, Slow-moving stock. Excel, PDF and print.
- Year end: the Stock Variation voucher (type 06) cancels account 37 against 6051 and books the closing stock (Dr 37 / Cr 6052). It is posted automatically when the year is closed, and the closing stock becomes the Opening Stock of the next year.

## Year-end order
1. Enter the last documents of the year and check the stock (Inventory > Reports > Stock Valuation at 31-12).
2. Profit & Loss > Preview Closing 6&7.
3. Close the year: stock variation, closing 6 & 7 (result to 121 / 125), and the opening of the next year (balances and stock) are made automatically.
4. "Delete Closing & Reopen Year" undoes everything if a correction is needed.

## Points to confirm with the accountant
- Employer NSSF sickness & maternity rate (8% per PwC; one source says 11%).
- Exact start dates of Jan-Feb 2024 ceilings and the 28M minimum wage.
- VAT declaration box numbers against the official MoF form; rounding of the deduction ratio.

# Version 2.1.0

## Arabic in PDF
Every PDF (reports, statements, invoices, VAT declaration, R5 / R6 / R10, NSSF statement) prints Arabic text correctly - joined letters, right-to-left - using the Amiri font (SIL Open Font License, `assets/fonts/Amiri-OFL.txt`). Official reports carry Arabic labels next to the English.

## NSSF ceilings - automatic and monthly
- A new or never-configured company loads the Lebanese periods 2024-2026 automatically (ceilings, rates, family allowances, tax rounding). Settings you changed yourself are never overwritten; "Load Lebanese Law 2024-2026" reloads them on request.
- Payroll is monthly: each payroll uses the rules in force on the **last day of its month** (for example the 90M -> 120M ceiling change of August 2025, or the LBP 10,000 rounding from 25-11-2024 for November). Retroactive pay uses the ceilings of each of its own months.
- Payroll > Official Reports > "CEILINGS - NSSF ceilings by month" shows the ceilings and rates of every month of a year.

## NSSF payment format
Payroll > Official Reports > "NSSF - Contributions statement (payment)", monthly or quarterly, Arabic / English:
- per employee and month: NSSF number, salary subject, capped bases and contributions for sickness & maternity (employee 3% + employer), family allowances (6%) and end of service (8.5%), family allowances already paid, net due;
- payment summary by branch and the net amount payable to the NSSF (LBP);
- the monthly ceilings and rates applied; employer NSSF number from General Settings.
"Record NSSF Payment" books the payment voucher (Dr NSSF payable / Cr cash or bank).

## Fix
Company files created by older versions are brought up to date automatically when they are opened.

# Version 2.2.0

## Sales Invoice, Debit Note, Credit Note
- Document type: Invoice (SAL-), Debit Note (DN-), Credit Note (CN-, reverses the sale and reduces the VAT of the period).
- Lines: Item, Description, Qty, Unit, Unit Price, Total Amount, Discount %, VAT %, Net.
- Totals: Total, Discount (% or amount), **Total HT**, VAT 11% (struck through for zero-rated / exempt), TOTAL, and the **amount in words** in English and Arabic (tafqeet).
- Find by number only (type 12 for SAL-2026-000012), Duplicate, Print Preview, PDF, Print, Import Excel (template provided), Import PDF, Excel Template.

## General Journal
Find by voucher number and by details; Print Preview, PDF and Print.

## Payment & Receipt
Cash / bank accounts from 511, 512, 519 and 53 only; customers and suppliers in both tabs; **allocation** of each receipt / payment to open invoices (auto: oldest first), open balance per document.

## Purchases & Expenses
- Find instead of the lists. Purchases: items received into stock with warehouse (F2 item search; an item that does not exist is created automatically), Excel import with template, PDF.
- Cost on purchase: each cost to its own 9-digit 6018 account (601800001 freight, 601800002 insurance, 601800003 customs duties, 601800004 broker, 601800005 other); import VAT to 44210.
- Expense account chosen from accounts 626 to 69.

## Accounts
VAT: 44210 purchases, 44211 export-related purchases, 44216 expenses, 4427 sales. Payroll: 6311 salaries, 6312 bonus / 13th, 6313 commission, 6315 schooling, 6316 managers' salaries, 6319 transport, 4411 salary tax, 4431 NSSF.
Year-end result to **138** (profit) / **139** (loss); the closing voucher is "CLOSING 6&7" in the General Journal.

## Inventory
Items with cost price (average of purchases), supplier, category / subcategory, unit and location. New tabs: Categories & Units, Stock In / Stock Out (at average cost), Physical Inventory (stock on hand, count, difference, save, print, Excel sheet, upload, post the differences). Reports filter by category, subcategory, unit, supplier and warehouse together.

## F2
F2 opens the list that fits the field: items in item fields, customers / suppliers in party fields, accounts elsewhere.

# Version 2.3.0 - Statement of Account / Trial Balance
- Account From / To: search by number or name among all accounts (parents too); the account name shows beside each box (like BRAINS). "Same as From" copies the account.
- The options are in their own "Options" tab; every Show opens its own full-page tab with Print Preview, Print, Excel, PDF and Close Tab. Several statements can stay open side by side.
- Double-click a statement line to see the transaction (all its lines) and "Open in its screen" (journal voucher, sales invoice, purchase, receipt / payment, expense). In the Trial Balance, double-click an account to open its statement in a new tab.

# Version 2.4.0
- Profit & Loss > "Delete Year" (administrators): deletes the last fiscal year of a company (for example 2025, to redo the opening). A backup copy of the file is kept in `companies/<company>/deleted_years`, and the previous year is reopened with its closing removed. Type "DELETE <year>" to confirm. Then close the previous year again to make a new opening.
- NSSF statement: sickness & maternity shown as employee 3% + employer 8% = total 11% (as in the NSSF declaration).

# Version 2.5.0 - Backups per company and per year
- Backups are made automatically each day while signed in to Windows. You can also press "Create Backup Now"; safety backups are made before restore and replacement imports.
- Each company and each fiscal year has its own folder and file name: `SaberAccounting\backups\<Company>\<Year>\<Company>_<Year>_<date>_<time>.db`.
- Security / Backup / Rates > Backup & Restore shows the backups of the company and year you are in, with "Save Backup As..." (copy to a USB key or a drive folder) and "Open Backup Folder". Backups made by older versions still appear and can be restored.

# Data safety and automatic backups update

- The first standalone launch asks you to set an admin password. Existing installations keep their current password.
- Any signed-in user can create, view, and save a backup of the selected company/year from **My Backups**. Only administrators can restore a backup.
- The Windows installer installs a background backup process in the shared Startup folder. It runs after Windows sign-in, checks once per hour, and creates one backup per company/year when 24 hours have passed. The desktop window does not need to be open. The computer must be on and a Windows user must be signed in. On the first new-company launch, a backup is made immediately. Backup files live in `SaberAccounting/backups/<Company>/<Year>` under that Windows user's profile; copy this folder to another drive if you need protection from drive failure.
- Replacing imported invoices now validates the complete batch before changing the live file and keeps manual journal vouchers. If any row fails, the replacement is cancelled. A safety backup is made before a successful replacement.
- Replacement is refused when payments, stock documents, or a saved VAT return are linked to existing invoices, when a fiscal year is closed, or when existing invoices record amounts paid. Review those records first.
- Invalid company/year selections return an error. Payment and expense edits are prepared on a database snapshot before replacing the live file. Stock checks no longer temporarily remove saved movements.
- The PDF import preview scans every page and creates separate preview rows when invoice numbers change. Repeated invoice numbers on following pages are grouped. Scanned pages stay visible for manual entry. Invoices sharing one page still require manual separation and review.

# Version 2.6.0 - review of the ChatGPT changes + inventory reports
Kept from the ChatGPT changes (all tests pass): initial admin password (10+ characters) instead of admin/admin, safer invoice / payment edits (nothing lost if a save fails), year closing with automatic rollback, stricter company / year checks, local expense-account suggestions (ai_mapper) and optional OpenAI assistance (ai_service - needs an API key; it sends page 1 of the chosen invoice PDF to OpenAI).
Adjusted: the background daily backup is now an OPTIONAL installer task, unchecked by default (backups are made on request from Backup & Restore); leftover files removed (temp.txt, shortcut).

## Inventory reports
- **Inventory Summary**: key figures (items, value at cost and at sales price, potential margin, items to reorder, slow-moving and old-stock value), value by category and by warehouse, top 10 items, ageing, items to reorder.
- **Stock Ageing**: stock on hand by age of receipt (first in - first out): 0-30, 31-60, 61-90, 91-180, 181-365, over 365 days (buckets can be changed), value per bucket, average age, oldest receipt, last issue, % of old stock, category subtotals, ageing summary, and the list of stock older than 180 days to review.
- **Stock Valuation**: grouped by category with subtotals.
All with the filters (warehouse, category, subcategory, unit, supplier, costing method) and Excel / PDF / Print.

# Version 2.7.0
- Merged: the latest ChatGPT changes + version 2.6.0 (stock ageing, inventory summary, valuation by category, optional automatic backup were missing from the upload and are back).
- **Financial Reports > Business Reports** (Excel, PDF, print, preview):
  - Receivables Ageing (customers) and Payables Ageing (suppliers): open documents by days after the due date (not due, 1-30, 31-60, 61-90, 91-180, over 180 - buckets can be changed), receipts / payments not allocated, net due, % overdue, detail of open documents.
  - Item Sales by Client, and Client Quantities by Item: quantity, average price, HT, VAT, TTC.
  - Sales Analysis (3D pivot): rows (client / item / category) x columns (month / quarter / client / item / category) x measure (quantity / HT / VAT / TTC).
  - Top Clients and Top Suppliers (purchases and expenses): HT + VAT = TTC, share, cumulative share, number of documents.
  - Amounts in USD or LBP (converted at each document date) or one currency only; credit notes deducted.
- **Payroll > Tax & NSSF Settings**: the NSSF ceilings and rates by period (Date From - Date To) are edited directly in the table (double-click), with Add / Delete / Save Periods; a new Date From closes the previous period automatically.
- Lighter, calmer layout: shorter table rows (more lines on screen), soft headings, clean input borders, buttons that light up under the mouse.
