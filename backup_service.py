"""Create daily per-company backups independently of the desktop window."""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from company_manager import CompanyManager


def backup_all(master_path):
    master_path = Path(master_path)
    if not master_path.is_file():
        return []
    manager = CompanyManager(master_path)
    made = []
    for company in manager.list_companies(True):
        for year in company.get("years", []):
            try:
                database = manager.database(company["id"], year["year"])
                path = database.maybe_scheduled_backup()
                if path:
                    made.append(path)
            except Exception:
                logging.exception("Backup failed for %s / %s", company["id"], year.get("year"))
    return made


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--database", default=str(Path.home()/"SaberAccounting"/"saber_accounting_v0_7.db"))
    args = parser.parse_args()
    log_dir = Path(args.database).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_dir/"backup_service.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    while True:
        try:
            for path in backup_all(args.database):
                logging.info("Backup created: %s", path)
        except Exception:
            logging.exception("Automatic backup cycle failed")
        if args.once:
            break
        time.sleep(3600)


if __name__ == "__main__":
    main()
