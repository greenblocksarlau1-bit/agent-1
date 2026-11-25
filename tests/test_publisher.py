import json
import os
import tempfile
import unittest

from app import db, manager, publisher
from app.config import Settings


class PublisherTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = db.connect(self.path)
        db.init_db(self.conn)
        self.settings = Settings(verify_token="v", app_secret="s", whatsapp_token="", phone_number_id="",
                                 manager_phone="", db_path=self.path, graph_version="v21.0", port=0,
                                 auto_reply=True, anthropic_api_key="", github_dispatch_token="")

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _offer(self, category, specs=None):
        cur = self.conn.execute(
            "INSERT INTO offers (title, category, location, price, details, status, specs) "
            "VALUES (?, ?, 'أزيلال', '500000', 'ماء وكهرباء', 'pending_approval', ?)",
            ("أرض فلاحية", category, json.dumps(specs) if specs else None))
        self.conn.commit()
        return cur.lastrowid

    def test_category_and_media_mapping(self):
        oid = self._offer("farm", {"area": "2 هكتار"})
        row = self.conn.execute("SELECT * FROM offers WHERE id = ?", (oid,)).fetchone()
        payload = publisher.build_payload(row)
        self.assertEqual(payload["category"], "land")
        self.assertEqual(payload["media"], "land")
        self.assertEqual(payload["area"], "2 هكتار")
        self.assertIn("أرض", payload["badge"])
        self.assertNotIn("<html", payload["caption"])

    def test_property_maps_to_residential(self):
        oid = self._offer("property")
        row = self.conn.execute("SELECT * FROM offers WHERE id = ?", (oid,)).fetchone()
        payload = publisher.build_payload(row)
        self.assertEqual((payload["category"], payload["media"]), ("residential", "res"))

    def test_approve_without_token_is_dry_run_and_publishes(self):
        oid = self._offer("land")
        reply = manager.handle_command(self.conn, f"approve {oid}", self.settings)
        self.assertIn("published", reply)
        status = self.conn.execute("SELECT status FROM offers WHERE id = ?", (oid,)).fetchone()["status"]
        self.assertEqual(status, "published")


if __name__ == "__main__":
    unittest.main()
