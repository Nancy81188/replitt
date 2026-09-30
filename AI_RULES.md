# Rules for anyone changing Saber Accounting (people, ChatGPT, Claude)

Read this file first. Saber Accounting is used for real accounting data: nothing may be lost, and the numbers must stay right under Lebanese law.

## 1. Always start from the latest version
- The GitHub repository is the only master copy. Download it (Code > Download ZIP) or start from the latest ZIP that was uploaded to it.
- Never rebuild from an older copy or from memory: older copies miss features (this is how the stock ageing report was lost once).
- Check the version in `installer.iss` (`#define MyAppVersion`) and the top of `README.md` before starting.

## 2. Never remove what exists
- Do not delete features, screens, reports, tests or options unless the owner asks for it in writing.
- Do not delete or rename tests to make them pass. If a test fails because the rule changed on purpose, change the test and say why in the README.
- Keep the folder name `Assets` (with its `fonts` and the logo) exactly as it is; the build and the Arabic PDFs need it.

## 3. Test before delivering
Run all tests (on Linux create the link first: `ln -s Assets assets`):

    python -m unittest discover -p "test_*.py"

Every test must pass. Add a test for every new calculation (VAT, payroll, stock, ageing, reconciliation).

## 4. Deliver clearly
- Raise the version in `installer.iss`, and add a short section at the top of `README.md`: what changed and why.
- A new Python module must be added to `.github/workflows/build-windows-installer.yml` as `--hidden-import <module>`.
- Deliver the whole project as one ZIP, and list the files that changed.
- Do not leave temporary files (`temp.txt`, shortcuts, `__pycache__`).

## 5. Accounting rules that must not change without the accountant
- VAT 11% (Law 379/2001): output 4427; input 44210 purchases, 44211 export-related, 44216 expenses; partial deduction (Art. 31); VAT due rounded up to LBP 10,000 from 25-11-2024.
- Payroll: Budget Law 324/2024 brackets and family deductions; NSSF sickness & maternity 3% employee + 8% employer = 11%; ceilings by period (Date From / Date To); each payroll uses the rules of the last day of its month. Accounts 6311 salaries, 6312 bonus, 6313 commission, 6315 schooling, 6316 managers, 6319 transport, 4411 salary tax, 4431 NSSF.
- Year end: result to 138 (profit) / 139 (loss); stock by the periodic method (6051 / 6052 / 37).
- Each company and each fiscal year is its own database file; backups are made on request (the background daily backup is an optional installer task, off by default).

## 6. Privacy
- The optional OpenAI features send data outside the computer; they must stay optional and ask before sending.
