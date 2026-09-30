"""Durability, size and idempotency checks for fixed-asset PDF attachments."""
import base64
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

import fixed_assets
from client import ApiClient
from database import Database
from server import run_server


class AssetAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db=Database(Path(self.folder.name)/"company.db")
        self.db.initialize("secret12345")
        self.asset=fixed_assets.save_asset(self.db,{
            "asset_code":"PDF-ASSET","name":"Equipment","acquired_on":"01-01-2024","start_on":"01-01-2024",
            "currency":"USD","cost":"1000","residual":"0","useful_months":60,"frequency":"monthly",
            "asset_account":"211","depreciation_account":"6811","accumulated_account":"2811",
        })

    def test_same_pdf_content_is_idempotent_for_asset_and_downloadable(self):
        content=b"%PDF-1.4\nfixture data"
        first=fixed_assets.add_attachment(self.db,self.asset["id"],"source.pdf","application/pdf",content,1)
        retry=fixed_assets.add_attachment(self.db,self.asset["id"],"renamed.pdf","application/pdf",content,1)

        self.assertFalse(first["duplicate"])
        self.assertTrue(retry["duplicate"])
        self.assertEqual(first["attachment_id"],retry["attachment_id"])
        self.assertEqual(len(fixed_assets.list_attachments(self.db,self.asset["id"])),1)
        stored=fixed_assets.get_attachment(self.db,first["attachment_id"])
        self.assertEqual(stored["content"],content)
        self.assertEqual(stored["sha256"],first["sha256"])

    def test_same_pdf_can_be_attached_once_to_each_distinct_asset(self):
        second=fixed_assets.save_asset(self.db,{
            "asset_code":"PDF-ASSET-2","name":"Second equipment","acquired_on":"01-01-2024",
            "start_on":"01-01-2024","currency":"USD","cost":"2000","residual":"0","useful_months":60,
            "frequency":"monthly","asset_account":"211","depreciation_account":"6811","accumulated_account":"2811",
        })
        content=b"%PDF-1.4\nsame bytes"
        one=fixed_assets.add_attachment(self.db,self.asset["id"],"asset.pdf","application/pdf",content)
        two=fixed_assets.add_attachment(self.db,second["id"],"asset.pdf","application/pdf",content)
        self.assertNotEqual(one["attachment_id"],two["attachment_id"])
        self.assertEqual(len(fixed_assets.list_attachments(self.db,second["id"])),1)

    def test_pdf_attachment_carries_forward_with_asset_to_next_fiscal_database(self):
        source=Database(Path(self.folder.name)/"carry-source.db")
        source.initialize("secret12345")
        asset=fixed_assets.save_asset(source,{
            "asset_code":"CARRY-PDF","name":"New equipment","acquired_on":"01-01-2025",
            "start_on":"01-01-2025","currency":"USD","cost":"1000","residual":"0","useful_months":60,
            "frequency":"monthly","asset_account":"211","depreciation_account":"6811","accumulated_account":"2811",
        })
        content=b"%PDF-1.4\ncarry forward"
        fixed_assets.add_attachment(source,asset["id"],"carry.pdf","application/pdf",content)
        target=Database(Path(self.folder.name)/"next-year.db")
        target.initialize("secret12345")

        fixed_assets.carry_forward(source,target,2025)

        carried=fixed_assets.list_assets(target)[0]
        attachment=fixed_assets.list_attachments(target,carried["id"])[0]
        self.assertEqual(attachment["file_name"],"carry.pdf")
        self.assertEqual(fixed_assets.get_attachment(target,attachment["id"])["content"],content)

    def test_rejects_non_pdf_and_over_limit_uploads(self):
        with self.assertRaisesRegex(ValueError,"valid PDF"):
            fixed_assets.add_attachment(self.db,self.asset["id"],"bad.pdf","application/pdf",b"not a PDF")
        oversized=b"%PDF-"+b"x"*(15*1024*1024)
        with self.assertRaisesRegex(ValueError,"15 MB"):
            fixed_assets.add_attachment(self.db,self.asset["id"],"large.pdf","application/pdf",oversized)

    def test_client_exposes_authenticated_asset_attachment_operations(self):
        client=ApiClient()
        client.request=Mock(return_value={"attachment_id":9,"duplicate":False})
        data=b"%PDF-1.4\nclient fixture"
        client.upload_asset_attachment(4,"invoice.pdf","application/pdf",data)
        method,path,body=client.request.call_args.args
        self.assertEqual((method,path),("POST","/api/fixed-assets/4/attachments"))
        self.assertEqual(base64.b64decode(body["content"]),data)

        client.request=Mock(return_value={"id":9,"content":base64.b64encode(data).decode("ascii")})
        self.assertEqual(client.download_asset_attachment(9)["content"],data)
        client.request.assert_called_once_with("GET","/api/fixed-asset-attachments/9")


class AssetAttachmentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.database=Path(cls.folder.name)/"app.db"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1",0)); cls.port=probe.getsockname()[1]
        cls.url=f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=run_server,kwargs={"host":"127.0.0.1","port":cls.port,
            "database":str(cls.database),"admin_password":"secret12345"},daemon=True).start()
        cls.admin=ApiClient(cls.url)
        for _ in range(100):
            try:
                cls.admin.login("admin","secret12345")
                break
            except Exception:
                time.sleep(.05)
        else:
            raise RuntimeError("Asset attachment API test server did not start")
        company=cls.admin.companies()[0]
        cls.admin.select_company_year(company["id"],company["years"][0]["year"])

    @classmethod
    def tearDownClass(cls):
        cls.admin.close()
        cls.folder.cleanup()

    def test_authenticated_api_persists_and_idempotently_retrieves_asset_pdf(self):
        asset=self.admin.save_asset({
            "asset_code":"API-PDF-ASSET","name":"API attachment test","acquired_on":"01-01-2024",
            "start_on":"01-01-2024","currency":"USD","cost":"1000","residual":"0","useful_months":60,
            "frequency":"monthly","asset_account":"211","depreciation_account":"6811","accumulated_account":"2811",
        })
        content=b"%PDF-1.4\napi test"
        first=self.admin.upload_asset_attachment(asset["id"],"source.pdf","application/pdf",content)
        retry=self.admin.upload_asset_attachment(asset["id"],"other-name.pdf","application/pdf",content)
        self.assertFalse(first["duplicate"])
        self.assertTrue(retry["duplicate"])
        self.assertEqual(first["attachment_id"],retry["attachment_id"])
        records=self.admin.asset_attachments(asset["id"])
        self.assertEqual(len(records),1)
        self.assertEqual(self.admin.download_asset_attachment(records[0]["id"])["content"],content)


if __name__=="__main__":
    unittest.main()