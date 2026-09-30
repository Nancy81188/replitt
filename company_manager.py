from __future__ import annotations

import json
import re
import secrets
import sqlite3
from contextlib import closing
import uuid
from datetime import datetime
from pathlib import Path

from database import Database, utcnow


class CompanyManager:
    """Keeps every company/fiscal year in its own SQLite file."""

    def __init__(self, master_database, pooled=False):
        self.pooled=pooled  # the running data service keeps each company file open (faster)
        self.master_path=Path(master_database).resolve()
        self.root=self.master_path.parent/"companies"; self.root.mkdir(parents=True,exist_ok=True)
        self.registry_path=self.root/"companies.json"; self._cache={}
        if not self.registry_path.exists():
            self._write({"companies":[{"id":"ecologe-lebanon-sarl","name":"ECOLOGE LEBANON SARL","active":True,
                "years":[{"year":2024,"database":str(self.master_path),"status":"open"}]}]})
        else:
            data=self._read(); companies=data.get("companies",[])
            if len(companies)==1 and companies[0].get("id")=="saber-for-audit" and companies[0].get("name")=="Saber for Audit":
                companies[0]["id"]="ecologe-lebanon-sarl"; companies[0]["name"]="ECOLOGE LEBANON SARL"
                for fiscal in companies[0].get("years",[]): fiscal["year"]=2024
                self._write(data)
                try:
                    with Database(self.master_path).connect() as db:
                        db.execute("INSERT INTO app_settings(key,value) VALUES('company_name','ECOLOGE LEBANON SARL') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
                except Exception: pass

    # ------------------------------------------------------------ files named after the company
    @staticmethod
    def safe_name(name, fallback="company"):
        """The company name as it can be used for a Windows folder / file name (same rule as the backups)."""
        text="".join(ch for ch in str(name or "") if ch.isalnum() or ch in " -_&.").strip()
        return text or fallback

    def company_folder(self, company, data=None):
        """companies/<Company Name>/ - two companies with the same name get their id added."""
        safe=self.safe_name(company.get("name"),company.get("id") or "company")
        others=[c for c in (data or self._read())["companies"] if c.get("id")!=company.get("id")]
        if any(self.safe_name(c.get("name"),c.get("id")).casefold()==safe.casefold() for c in others): safe=f'{safe} ({company.get("id")})'
        return self.root/safe

    def year_file(self, company, year, data=None):
        """companies/<Company Name>/<Company Name>_<year>.db - named like the backups (<Company Name>_<year>_<date>.db)."""
        folder=self.company_folder(company,data)
        return folder/f"{folder.name}_{int(year)}.db"

    def organize_files(self, only_company_id=None):
        """Move every company-year file to companies/<Company Name>/<Company Name>_<year>.db.

        Each file is copied with SQLite's backup (a consistent copy), checked (integrity and the number of
        rows of every table), the company list is updated, and only then is the old file removed. The main
        file (users and passwords) is never removed: a company year that was kept inside it is copied out.
        A file that cannot be moved now (for example open in another program) keeps working where it is
        and is moved on a later start. Returns the list of moves."""
        import os
        data=self._read(); moved=[]
        for company in data["companies"]:
            if only_company_id and company.get("id")!=only_company_id: continue
            for fiscal in company.get("years",[]):
                source=Path(fiscal["database"]).resolve(); target=self.year_file(company,fiscal["year"],data).resolve()
                if source==target or not source.exists(): continue
                if target.exists(): continue  # never overwrite; resolve by hand
                cached=self._cache.pop(str(source),None)
                if cached is not None: cached.release()
                try:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    temporary=target.with_suffix(".moving")
                    if temporary.exists(): temporary.unlink()
                    with closing(sqlite3.connect(str(source))) as old,closing(sqlite3.connect(str(temporary))) as new: old.backup(new)
                    with closing(sqlite3.connect(str(source))) as old,closing(sqlite3.connect(str(temporary))) as new:
                        if new.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise ValueError("copy failed the integrity check")
                        for (table,) in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
                            if old.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]!=new.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]:
                                raise ValueError(f"table {table} differs after the copy")
                    os.replace(temporary,target)
                except Exception:
                    try: temporary.unlink()
                    except Exception: pass
                    continue
                fiscal["database"]=str(target); self._write(data); moved.append((str(source),str(target)))
                if source!=self.master_path.resolve():
                    for suffix in ("","-wal","-shm"):
                        try: Path(str(source)+suffix).unlink()
                        except FileNotFoundError: pass
                        except OSError: pass
                    try: source.parent.rmdir()  # the old id-named folder, when it is now empty
                    except OSError: pass
        return moved

    def _read(self):
        try: return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception: return {"companies":[]}

    def _write(self,data):
        temporary=self.registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); temporary.replace(self.registry_path)

    def list_companies(self,include_inactive=False):
        companies=self._read()["companies"]
        return companies if include_inactive else [c for c in companies if c.get("active",True)]

    def _company(self,company_id):
        company=next((c for c in self._read()["companies"] if c["id"]==company_id),None)
        if not company: raise KeyError("Company not found")
        return company

    def database(self,company_id=None,year=None):
        companies=self.list_companies(True)
        if not companies: raise KeyError("No company is configured")
        company=next((c for c in companies if c["id"]==company_id),None) if company_id else companies[0]
        if not company: raise KeyError("Company not found")
        years=company.get("years",[])
        selected=next((y for y in years if int(y["year"])==int(year)),None) if year else (max(years,key=lambda y:int(y["year"])) if years else None)
        if not selected: raise KeyError("Fiscal year not found")
        path=str(Path(selected["database"]).resolve())
        if path not in self._cache:
            database=Database(path,pooled=self.pooled)
            safe=self.safe_name(company["name"],company["id"])
            database.backup_folder=str(self.master_path.parent/"backups"/safe/str(selected["year"])); database.backup_label=f'{safe}_{selected["year"]}'
            # Bring files made by an older version up to date (new tables and columns); existing data is kept.
            if Path(path).exists() and Path(path)!=self.master_path: database.initialize(secrets.token_urlsafe(24))
            self._cache[path]=database
        return self._cache[path]

    def year_status(self,company_id,year):
        company=self._company(company_id)
        selected=next((item for item in company.get("years",[]) if int(item["year"])==int(year)),None)
        if not selected: raise KeyError("Fiscal year not found")
        return selected.get("status","open")

    def create_company(self,item,master_db):
        name=str(item.get("name") or "").strip(); year=int(item.get("year") or datetime.now().year)
        if not name or year<2000 or year>2100: raise ValueError("Enter a valid company name and fiscal year")
        data=self._read(); company_id=re.sub(r"[^a-z0-9]+","-",name.lower()).strip("-") or uuid.uuid4().hex[:10]
        if any(c["id"]==company_id or c["name"].casefold()==name.casefold() for c in data["companies"]): raise ValueError("Company already exists")
        company_id=f"{company_id}-{uuid.uuid4().hex[:6]}"
        path=self.year_file({"id":company_id,"name":name},year,data); path.parent.mkdir(parents=True,exist_ok=True)
        target=Database(path); target.initialize(secrets.token_urlsafe(24))
        self._copy_master_data(master_db,target)
        settings={"company_name":name,"company_address":item.get("address","").strip(),"company_phone":item.get("phone","").strip(),
            "company_mof":item.get("mof_number","").strip(),"company_email":item.get("email","").strip(),"company_website":item.get("website","").strip()}
        with target.connect() as db:
            for key,value in settings.items(): db.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value))
        company={"id":company_id,"name":name,"active":True,"years":[{"year":year,"database":str(path.resolve()),"status":"open"}]}
        data["companies"].append(company); self._write(data); return company

    def update_company(self,company_id,item):
        data=self._read(); company=next((c for c in data["companies"] if c["id"]==company_id),None)
        if not company: raise KeyError("Company not found")
        old_backups=self.master_path.parent/"backups"/self.safe_name(company["name"],company["id"])
        if str(item.get("name") or "").strip(): company["name"]=str(item["name"]).strip()
        if "active" in item: company["active"]=bool(item["active"])
        self._write(data)
        for year in company.get("years",[]):
            db=Database(year["database"])
            with db.connect() as connection:
                connection.execute("INSERT INTO app_settings(key,value) VALUES('company_name',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(company["name"],))
        # A renamed company: its files and its backups folder follow the new name.
        self.organize_files(company_id)
        new_backups=self.master_path.parent/"backups"/self.safe_name(company["name"],company["id"])
        if old_backups!=new_backups and old_backups.is_dir() and not new_backups.exists():
            try: old_backups.rename(new_backups)
            except OSError: pass
        for path in [p for p in self._cache]: self._cache.pop(path).release()  # backup folders are set again on next use
        return next(c for c in self._read()["companies"] if c["id"]==company_id)

    def create_year(self,company_id,year,user_id):
        year=int(year); data=self._read(); company=next((c for c in data["companies"] if c["id"]==company_id),None)
        if not company: raise KeyError("Company not found")
        if any(int(y["year"])==year for y in company["years"]): raise ValueError("Fiscal year already exists")
        previous=max((y for y in company["years"] if int(y["year"])<year),key=lambda y:int(y["year"]),default=None)
        if not previous: raise ValueError("Create fiscal years in chronological order")
        source=Database(previous["database"])
        import fixed_assets
        fixed_assets.check_carry_forward(source,year)
        path=self.year_file(company,year,data); path.parent.mkdir(parents=True,exist_ok=True); target=Database(path); target.initialize(secrets.token_urlsafe(24)); self._copy_master_data(source,target)
        import inventory
        inventory.carry_forward(source,target,year,user_id)
        fixed_assets.carry_forward(source,target,year)
        company["years"].append({"year":year,"database":str(path.resolve()),"status":"open"}); company["years"].sort(key=lambda y:int(y["year"]))
        self._write(data); return company

    def delete_year(self,company_id,year,user_id):
        """Remove the LAST fiscal year of a company (for example to redo the opening). The file is kept as a backup
        in the company's 'deleted_years' folder, and the previous year is reopened (its closing is removed)."""
        import shutil
        from datetime import datetime as _dt
        year=int(year); data=self._read(); company=next((c for c in data["companies"] if c["id"]==company_id),None)
        if not company: raise KeyError("Company not found")
        years=sorted(company.get("years",[]),key=lambda y:int(y["year"]))
        current=next((y for y in years if int(y["year"])==year),None)
        if not current: raise ValueError(f"Fiscal year {year} was not found for this company")
        if int(years[-1]["year"])!=year: raise ValueError(f"Only the last fiscal year can be deleted ({years[-1]['year']}). Delete the later years first.")
        if len(years)==1: raise ValueError("The only fiscal year of a company cannot be deleted")
        path=Path(current["database"]).resolve()
        if path==self.master_path.resolve(): raise ValueError("This year uses the main database file and cannot be deleted")
        backup_folder=self.company_folder(company,data)/"deleted_years"; backup_folder.mkdir(parents=True,exist_ok=True)
        backup=backup_folder/f"{year}_deleted_{_dt.now():%Y%m%d_%H%M%S}.db"
        cached=self._cache.pop(str(path),None)
        if cached is not None: cached.release()  # close the open file handle so it can be moved (Windows)
        if path.exists(): shutil.move(str(path),str(backup))
        company["years"]=[y for y in company["years"] if int(y["year"])!=year]
        previous=years[-2]
        self._write(data)
        reopened=self.reopen_year(company_id,int(previous["year"]),user_id)
        return {"deleted_year":year,"backup":str(backup),"reopened_year":int(previous["year"]),"removed_closing_entries":reopened.get("removed_closing_entries",0),
                "company":reopened["company"]}

    def reopen_year(self,company_id,year,user_id):
        year=int(year); data=self._read(); company=next((c for c in data["companies"] if c["id"]==company_id),None)
        if not company: raise KeyError("Company not found")
        current=next((item for item in company.get("years",[]) if int(item["year"])==year),None)
        if not current: raise ValueError("Fiscal year not found for this company")
        result=Database(current["database"]).reopen_fiscal_year(year,user_id)
        current["status"]="open"
        next_year=next((item for item in company.get("years",[]) if int(item["year"])==year+1),None)
        removed_opening=0
        if next_year:
            with Database(next_year["database"]).connect() as db:
                ids=[row["id"] for row in db.execute("SELECT id FROM journal_entries WHERE source_type='opening' AND entry_number LIKE ?",(f"OPEN-{year+1}-%",))]
                for entry_id in ids: db.execute("DELETE FROM journal_entries WHERE id=?",(entry_id,))
                removed_opening=len(ids)
        self._write(data); return {**result,"company":company,"removed_opening_entries":removed_opening}

    def refresh_opening(self,company_id,source_year,user_id):
        source_year=int(source_year); target_year=source_year+1; company=self._company(company_id)
        source_record=next((item for item in company.get("years",[]) if int(item["year"])==source_year),None)
        target_record=next((item for item in company.get("years",[]) if int(item["year"])==target_year),None)
        if not source_record or not target_record: raise ValueError(f"Both fiscal years {source_year} and {target_year} must exist")
        source=Database(source_record["database"]); target=Database(target_record["database"])
        with target.connect() as db:
            ids=[row["id"] for row in db.execute("SELECT id FROM journal_entries WHERE source_type='opening' AND entry_number LIKE ?",(f"OPEN-{target_year}-%",))]
            for entry_id in ids: db.execute("DELETE FROM journal_entries WHERE id=?",(entry_id,))
            db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,"refresh_opening","fiscal_year",target_year,json.dumps({"source_year":source_year,"replaced":len(ids)}),utcnow()))
        vouchers=self._opening_balances(source,target,target_year,user_id)
        import inventory
        inventory.carry_forward(source,target,target_year,user_id)
        return {"source_year":source_year,"target_year":target_year,"opening_vouchers":vouchers,"replaced":len(ids),"provisional":source_record.get("status")!="closed"}

    def close_and_open_year(self,company_id,year,user_id):
        """Close one company year, create its next database, and post opening vouchers."""
        year=int(year); next_year=year+1; data=self._read()
        company=next((c for c in data["companies"] if c["id"]==company_id),None)
        if not company: raise KeyError("Company not found")
        current=next((y for y in company.get("years",[]) if int(y["year"])==year),None)
        if not current: raise ValueError("Fiscal year not found for this company")
        next_record=next((item for item in company.get("years",[]) if int(item["year"])==next_year),None)
        source=Database(current["database"])
        source_backup=source.backup("safety")
        target_backup=Database(next_record["database"]).backup("safety") if next_record else None
        try:
            close_result=source.close_fiscal_year(year,user_id)
            current["status"]="closed"
            if next_record:
                path=Path(next_record["database"]); target=Database(path)
                with target.connect() as db:
                    ids=[row["id"] for row in db.execute("SELECT id FROM journal_entries WHERE source_type='opening' AND entry_number LIKE ?",(f"OPEN-{next_year}-%",))]
                    for entry_id in ids: db.execute("DELETE FROM journal_entries WHERE id=?",(entry_id,))
            else:
                path=self.year_file(company,next_year,data); path.parent.mkdir(parents=True,exist_ok=True)
                target=Database(path); target.initialize(secrets.token_urlsafe(24)); self._copy_master_data(source,target)
            opening_vouchers=self._opening_balances(source,target,next_year,user_id)
            import inventory
            stock_openings=inventory.carry_forward(source,target,next_year,user_id)
            if not next_record: company["years"].append({"year":next_year,"database":str(path.resolve()),"status":"open"})
            company["years"].sort(key=lambda item:int(item["year"]))
            self._write(data)
        except Exception:
            # Restore both company-year files to their pre-close state; keep the safety copies.
            with closing(sqlite3.connect(source_backup)) as old,closing(sqlite3.connect(source.path)) as live: old.backup(live)
            if target_backup:
                with closing(sqlite3.connect(target_backup)) as old,closing(sqlite3.connect(next_record["database"])) as live: old.backup(live)
            raise
        return {**close_result,"company":company,"opening_vouchers":opening_vouchers,"stock_openings":stock_openings}

    def _copy_master_data(self,source,target):
        with source.connect() as src, target.connect() as dst:
            for table in ("users","accounts","parties","branches","app_settings"):
                rows=src.execute(f"SELECT * FROM {table}").fetchall()
                if not rows: continue
                columns=list(rows[0].keys())
                if table=="accounts": dst.execute("UPDATE accounts SET parent_id=NULL")
                dst.execute(f"DELETE FROM {table}")
                placeholders=",".join("?" for _ in columns)
                if table=="accounts" and "parent_id" in columns:
                    # insert with parent_id detached, then re-link by code so row order never trips the FK
                    pid=columns.index("parent_id"); code_by_id={row["id"]:row["code"] for row in rows}
                    detached=[]
                    for row in rows:
                        vals=list(row[col] for col in columns); vals[pid]=None; detached.append(tuple(vals))
                    dst.executemany(f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})",detached)
                    for row in rows:
                        if row["parent_id"] and row["parent_id"] in code_by_id:
                            dst.execute("UPDATE accounts SET parent_id=(SELECT id FROM accounts WHERE code=?) WHERE code=?",(code_by_id[row["parent_id"]],row["code"]))
                else:
                    dst.executemany(f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})",[tuple(row[col] for col in columns) for row in rows])

    def _opening_balances(self,source,target,year,user_id):
        import year_end
        return year_end.post_opening(source,target,year,user_id)
