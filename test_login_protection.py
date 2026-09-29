"""Persistent login lockout and security audit regression tests."""
import sqlite3
import tempfile
import threading
import json
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from database import Database
from server import ApiHandler, run_server


class LoginProtectionTest(unittest.TestCase):
    def test_failure_audit_and_lockout_survive_database_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"users.db"
            db=Database(path); db.initialize("right-password")
            for _ in range(5):
                self.assertIsNone(db.login("admin","wrong-password","192.0.2.10"))
            db=Database(path)
            self.assertTrue(db.login("admin","right-password","192.0.2.10")["rate_limited"])
            with closing(sqlite3.connect(path)) as connection:
                with connection:
                    actions=connection.execute("SELECT action,details FROM audit_log WHERE entity='auth'").fetchall()
                    self.assertEqual(sum(action=="login_failed" for action,_ in actions),5)
                    self.assertEqual(sum(action=="login_blocked" for action,_ in actions),1)
                    self.assertNotIn("wrong-password",str(actions))
                    self.assertNotIn("right-password",str(actions))
                    connection.execute("UPDATE login_attempts SET locked_until='2000-01-01T00:00:00+00:00'")
            self.assertIn("token",db.login("admin","right-password","192.0.2.10"))

    def test_nonlocal_http_requires_explicit_opt_in(self):
        with self.assertRaisesRegex(ValueError,"--tls-cert"):
            run_server(host="0.0.0.0",port=0)

    def test_login_endpoint_returns_429_without_exposing_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/"users.db"); db.initialize("right-password")
            ApiHandler.master_db=db
            server=ThreadingHTTPServer(("127.0.0.1",0),ApiHandler)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            try:
                codes=[]
                for _ in range(6):
                    request=Request(f"http://127.0.0.1:{server.server_port}/api/login",
                                    data=json.dumps({"username":"admin","password":"wrong-password"}).encode(),
                                    headers={"Content-Type":"application/json"},method="POST")
                    try: urlopen(request,timeout=5)
                    except HTTPError as exc: codes.append(exc.code)
                self.assertEqual(codes,[401]*5+[429])
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
