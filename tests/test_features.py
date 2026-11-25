import json
import os
import tempfile
import unittest

from app import db, manager
from app.agent import handle_incoming
from app.config import Settings
from app.poster import build_caption, build_poster_html
from app.ranking import refresh_scores
from app.report import build_report

MANAGER = "212612345678"


def settings_for(path):
    return Settings(verify_token="v", app_secret="s", whatsapp_token="", phone_number_id="",
                    manager_phone=MANAGER, db_path=path, graph_version="v21.0", port=0,
                    auto_reply=True, anthropic_api_key="")


def msg(mid, body, phone="212600000001"):
    return {"id": mid, "from": phone, "name": "Ali", "type": "text", "body": body, "raw": "{}"}


class FeatureTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = db.connect(self.path)
        db.init_db(self.conn)
        self.settings = settings_for(self.path)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _offer(self, title, status="published", availability="available", location="أزيلال"):
        cur = self.conn.execute(
            "INSERT INTO offers (title, category, location, price, status, availability) VALUES (?, 'land', ?, '500000', ?, ?)",
            (title, location, status, availability))
        self.conn.commit()
        return cur.lastrowid

    def test_ranking_prefers_interest_and_availability(self):
        a = self._offer("A")
        b = self._offer("B")
        c = self._offer("C", availability="sold")
        cid = db.upsert_customer(self.conn, "1", None)
        db.link_customer_offer(self.conn, cid, b, "reservation")
        refresh_scores(self.conn)
        scores = {r["id"]: r["efficiency_score"] for r in self.conn.execute("SELECT id, efficiency_score FROM offers")}
        self.assertGreater(scores[b], scores[a])
        self.assertLess(scores[c], scores[a])

    def test_manager_approves_pending_offer_by_command(self):
        oid = self._offer("أرض", status="pending_approval")
        self.assertIn("published", manager.handle_command(self.conn, f"approve {oid}"))
        status = self.conn.execute("SELECT status FROM offers WHERE id = ?", (oid,)).fetchone()["status"]
        self.assertEqual(status, "published")

    def test_manager_message_is_routed_to_commands_not_customers(self):
        handle_incoming(self.conn, self.settings, msg("mgr1", "report", phone=MANAGER))
        count = self.conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        self.assertEqual(count, 0)

    def test_pending_listing_notifies_manager_once(self):
        def llm(messages, system=None):
            return json.dumps({"reply": "ok", "customer_name": None, "interest": "seller",
                               "offer": {"title": "أرض", "category": "land", "location": "أزيلال",
                                         "price": "500000", "details": None, "availability": None},
                               "ready_for_manager": True, "missing": []})
        handle_incoming(self.conn, self.settings, msg("s1", "عندي أرض"), llm=llm)
        handle_incoming(self.conn, self.settings, msg("s2", "شكراً"), llm=llm)
        pending = self.conn.execute("SELECT COUNT(*) FROM offers WHERE status='pending_approval'").fetchone()[0]
        self.assertEqual(pending, 1)

    def test_poster_and_caption_follow_rules(self):
        oid = self._offer("أرض فلاحية", status="published")
        row = self.conn.execute("SELECT * FROM offers WHERE id = ?", (oid,)).fetchone()
        page = build_poster_html(row)
        self.assertIn("أرض فلاحية", page)
        self.assertNotIn("212", page)  # no phone numbers on posters
        caption = build_caption(row).splitlines()
        self.assertIn("أزيلال", caption[0])
        tags = [t for t in caption[-1].split() if t.startswith("#")]
        self.assertTrue(5 <= len(tags) <= 8)

    def test_report_sections(self):
        text = build_report(self.conn)
        self.assertIn("Customers:", text)
        self.assertIn("Top published offers:", text)


if __name__ == "__main__":
    unittest.main()
