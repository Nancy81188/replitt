"""Accounting checks for asset amortisation and exchange difference vouchers."""
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import fixed_assets
from database import Database


class AssetAndDoeTest(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db=Database(Path(self.folder.name)/"company.db")
        self.db.initialize("secret12345")

    def test_monthly_amortisation_posts_balanced_and_once(self):
        asset=fixed_assets.save_asset(self.db,{"asset_code":"LAP-1","name":"Laptop","acquired_on":"01-01-2024",
            "start_on":"01-01-2024","currency":"USD","cost":"1200","residual":"120","useful_months":12,
            "frequency":"monthly","asset_account":"211","depreciation_account":"6811","accumulated_account":"2811"})
        periods=fixed_assets.schedule(self.db,asset["id"])
        self.assertEqual(len(periods),12)
        self.assertEqual(sum(float(row["amount"]) for row in periods),1080)
        result=fixed_assets.post_period(self.db,asset["id"],periods[0]["period_end"],1)
        details=self.db.journal_voucher_detail(result["voucher"]["id"])
        self.assertEqual([(row["account_code"],row["debit"],row["credit"]) for row in details["lines"]],
                         [("6811",90.0,0.0),("2811",0.0,90.0)])
        with self.assertRaisesRegex(ValueError,"already posted"):
            fixed_assets.post_period(self.db,asset["id"],periods[0]["period_end"],1)
        with self.assertRaisesRegex(ValueError,"cannot be deleted"):
            fixed_assets.delete_asset(self.db,asset["id"])

    def test_yearly_amortisation_sums_partial_years(self):
        asset=fixed_assets.save_asset(self.db,{"asset_code":"EQ-1","name":"Equipment","acquired_on":"01-03-2024",
            "start_on":"01-03-2024","currency":"USD","cost":"1200","residual":"0","useful_months":12,
            "frequency":"yearly","asset_account":"211","depreciation_account":"6811","accumulated_account":"2811"})
        self.assertEqual([(row["period_end"],row["amount"]) for row in fixed_assets.schedule(self.db,asset["id"])],
                         [("2024-12-31","1000.00"),("2025-02-28","200.00")])
        with self.assertRaisesRegex(ValueError,"Post earlier"):
            fixed_assets.check_carry_forward(self.db,2025)
        fixed_assets.post_period(self.db,asset["id"],"2024-12-31",1,2024)
        target=Database(Path(self.folder.name)/"next-year.db"); target.initialize("secret12345")
        fixed_assets.carry_forward(self.db,target,2025)
        continued=fixed_assets.list_assets(target)[0]
        self.assertEqual([r["posted"] for r in fixed_assets.schedule(target,continued["id"])],[True,False])
        with self.assertRaisesRegex(ValueError,"Select fiscal year 2025"):
            fixed_assets.post_period(self.db,asset["id"],"2025-02-28",1,2024)
        fixed_assets.post_period(target,continued["id"],"2025-02-28",1,2025)

    def test_exact_annual_rate_caps_net_at_residual_and_carries_forward(self):
        asset=fixed_assets.save_asset(self.db,{"asset_code":"RATE-7","name":"Seven percent","acquired_on":"01-01-2024",
            "start_on":"01-01-2024","currency":"USD","cost":"1000","residual":"50","useful_months":60,
            "annual_rate":"7","frequency":"yearly","asset_account":"211","depreciation_account":"6811","accumulated_account":"2811"})
        periods=fixed_assets.schedule(self.db,asset["id"])
        self.assertEqual(periods[0]["amount"],"70.00")
        self.assertEqual(periods[-1]["net_book_value"],"50.00")
        self.assertTrue(all(float(row["net_book_value"])>=50 for row in periods))
        fixed_assets.post_period(self.db,asset["id"],"2024-12-31",1,2024)
        target=Database(Path(self.folder.name)/"rate-next.db"); target.initialize("secret12345")
        fixed_assets.carry_forward(self.db,target,2025)
        copied=fixed_assets.list_assets(target)[0]
        self.assertEqual(copied["annual_rate"],"7.00")
        self.assertEqual(fixed_assets.schedule(target,copied["id"])[0]["amount"],"70.00")

    def test_doe_enforces_class_and_gain_loss_sides(self):
        with self.assertRaisesRegex(ValueError,"gains credit"):
            self.db.save_journal_voucher({"entry_date":"01-09-2024","description":"DOE","currency":"LBP","voucher_type":"07"},
                [{"account_code":"4011","credit":"100"},{"account_code":"775100000","debit":"100"}],1)
        saved=self.db.save_journal_voucher({"entry_date":"01-09-2024","description":"DOE","currency":"LBP","voucher_type":"07"},
            [{"account_code":"4011","credit":"100"},{"account_code":"675100000","debit":"100"}],1)
        self.assertEqual(saved["voucher"]["voucher_type"],"07")
        self.assertEqual(saved["voucher"]["entry_date"],"01-09-2024")

    def test_automatic_doe_uses_foreign_balances_and_prior_adjustments(self):
        self.db.save_journal_voucher({"entry_date":"01-09-2024","currency":"USD","voucher_type":"01"},
            [{"account_code":"4011","debit":"100"},{"account_code":"211","credit":"100"}],1)
        before=next(row for row in self.db.doe_candidates("30-09-2024")["items"] if row["account"]=="4011")
        self.assertEqual(before["currency"],"USD")
        self.assertEqual(before["balance"],"100")
        self.db.save_journal_voucher({"entry_date":"30-09-2024","currency":"LBP","voucher_type":"07"},
            [{"account_code":"4011","debit":"500"},{"account_code":"775100000","credit":"500"}],1)
        after=next(row for row in self.db.doe_candidates("30-09-2024")["items"] if row["account"]=="4011")
        self.assertEqual(float(after["carrying_lbp"])-float(before["carrying_lbp"]),500)


    def test_grouped_doe_voucher_per_currency(self):
        """Automatic DOE posts one voucher per currency with all its accounts (gains and losses separately)."""
        saved=self.db.save_journal_voucher({"entry_date":"30-09-2024","description":"DOE USD","currency":"LBP","voucher_type":"07"},
            [{"account_code":"4011","debit":"300"},{"account_code":"4111","credit":"200"},
             {"account_code":"775100000","credit":"300"},{"account_code":"675100000","debit":"200"}],1)
        self.assertEqual(saved["voucher"]["voucher_type"],"07")
        with self.assertRaisesRegex(ValueError,"class 4 or 5"):
            self.db.save_journal_voucher({"entry_date":"30-09-2024","description":"DOE","currency":"LBP","voucher_type":"07"},
                [{"account_code":"4011","debit":"100"},{"account_code":"6011","debit":"50"},{"account_code":"775100000","credit":"150"}],1)
        with self.assertRaisesRegex(ValueError,"gains credit"):
            self.db.save_journal_voucher({"entry_date":"30-09-2024","description":"DOE","currency":"LBP","voucher_type":"07"},
                [{"account_code":"4011","credit":"100"},{"account_code":"4111","credit":"100"},{"account_code":"775100000","debit":"200"}],1)


    def test_usd_doe_moves_only_the_usd_equivalent(self):
        """DOE in the USD books: an LBP balance is revalued in USD; its LBP balance and the LBP books do not move."""
        self.db.save_journal_voucher({"entry_date":"01-09-2024","currency":"LBP","voucher_type":"01"},
            [{"account_code":"4111","debit":"89500000"},{"account_code":"211","credit":"89500000"}],1)
        before=next(r for r in self.db.doe_candidates("30-09-2024","USD")["items"] if r["account"]=="4111")
        self.assertEqual((before["currency"],Decimal(before["balance"])),("LBP",Decimal("89500000")))
        self.assertFalse([r for r in self.db.doe_candidates("30-09-2024","USD")["items"] if r["currency"]=="USD"])
        target=Decimal("89500000")/Decimal("100000"); difference=(target-Decimal(before["carrying_usd"])).quantize(Decimal("0.01"))
        self.assertNotEqual(difference,0)
        side,offset,offside=("debit","775100000","credit") if difference>0 else ("credit","675100000","debit")
        self.db.save_journal_voucher({"entry_date":"30-09-2024","description":"DOE USD books","currency":"USD","voucher_type":"07","doe_basis":"USD"},
            [{"account_code":"4111",side:str(abs(difference)),"native_currency":"LBP"},{"account_code":offset,offside:str(abs(difference))}],1)
        after=next(r for r in self.db.doe_candidates("30-09-2024","USD")["items"] if r["account"]=="4111")
        self.assertEqual(Decimal(after["carrying_usd"]).quantize(Decimal("0.01")),target.quantize(Decimal("0.01")))
        self.assertEqual(Decimal(after["balance"]),Decimal("89500000"))
        import ledger_reports
        lines=[l for l in ledger_reports._load_lines(self.db,{"posting_status":"posted"}) if l["code"]=="4111"]
        self.assertEqual(sum(l["signed"]["LBP"] for l in lines),Decimal("89500000"))
        self.assertEqual(sum(l["signed"]["account"] for l in lines),Decimal("89500000"))


if __name__=="__main__": unittest.main()
