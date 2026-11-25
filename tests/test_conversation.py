import json
import os
import tempfile
import unittest

from app import db
from app.agent import handle_incoming
from app.config import Settings
from app.conversation import history_for_model, parse_reply


def make_settings(path, auto_reply=True):
    return Settings(verify_token="v", app_secret="s", whatsapp_token="", phone_number_id="",
                    manager_phone="", db_path=path, graph_version="v21.0", port=0,
                    auto_reply=auto_reply, anthropic_api_key="")


def msg(mid, body, phone="212600000001", name="Ali"):
    return {"id": mid, "from": phone, "name": name, "type": "text", "body": body, "raw": "{}"}


class ConversationTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = db.connect(self.path)
        db.init_db(self.conn)
        self.settings = make_settings(self.path)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def test_parse_reply_json_and_fallback(self):
        data = parse_reply('ok {"reply": "salam", "interest": "buyer", "offer": null, "ready_for_manager": false}')
        self.assertEqual(data["reply"], "salam")
        plain = parse_reply("ahlan bik")
        self.assertEqual(plain["reply"], "ahlan bik")
        self.assertEqual(plain["interest"], "unknown")

    def test_history_merges_and_starts_with_user(self):
        cid = db.upsert_customer(self.conn, "1", None)
        db.insert_message(self.conn, "o1", cid, "out", "hi")
        db.insert_message(self.conn, "i1", cid, "in", "a")
        db.insert_message(self.conn, "i2", cid, "in", "b")
        msgs = history_for_model(self.conn, cid)
        self.assertEqual(msgs, [{"role": "user", "content": "a\nb"}])

    def test_llm_reply_extracts_seller_offer_and_marks_ready(self):
        captured = {}

        def fake_llm(messages, system=None):
            captured["messages"] = messages
            return json.dumps({
                "reply": "شكراً، سيراجع المدير العرض.",
                "customer_name": "Ali",
                "interest": "seller",
                "offer": {"title": "أرض 2 هكتار", "category": "land", "location": "أزيلال",
                          "price": None, "details": None, "availability": None},
                "ready_for_manager": True,
            }, ensure_ascii=False)

        handle_incoming(self.conn, self.settings, msg("m1", "عندي أرض للبيع في أزيلال 2 هكتار"), llm=fake_llm)

        self.assertEqual(captured["messages"][-1]["role"], "user")
        cust = self.conn.execute("SELECT interest, name FROM customers").fetchone()
        self.assertEqual((cust["interest"], cust["name"]), ("seller", "Ali"))
        offer = self.conn.execute("SELECT title, location, status FROM offers").fetchone()
        self.assertEqual(offer["location"], "أزيلال")
        self.assertEqual(offer["status"], "pending_approval")
        out = self.conn.execute("SELECT body FROM messages WHERE direction='out'").fetchone()
        self.assertIn("المدير", out["body"])

    def test_second_message_updates_same_draft(self):
        def llm_one(messages, system=None):
            return json.dumps({"reply": "ok", "interest": "seller",
                               "offer": {"title": "أرض", "category": "land", "location": None,
                                         "price": None, "details": None, "availability": None},
                               "ready_for_manager": False})

        def llm_two(messages, system=None):
            return json.dumps({"reply": "ok", "interest": "seller",
                               "offer": {"title": None, "category": None, "location": "أزيلال",
                                         "price": "500000", "details": None, "availability": None},
                               "ready_for_manager": False})

        handle_incoming(self.conn, self.settings, msg("m1", "عندي أرض"), llm=llm_one)
        handle_incoming(self.conn, self.settings, msg("m2", "في أزيلال بثمن 500000"), llm=llm_two)
        rows = self.conn.execute("SELECT title, location, price FROM offers").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["title"], rows[0]["location"], rows[0]["price"]), ("أرض", "أزيلال", "500000"))


    def test_buyer_reservation_links_published_offer(self):
        self.conn.execute(
            "INSERT INTO offers (title, category, location, price, status) VALUES (?, ?, ?, ?, 'published')",
            ("فيلا", "property", "مراكش", "3000000"),
        )
        self.conn.commit()
        seen = {}

        def fake_llm(messages, system=None):
            seen["system"] = system
            return json.dumps({"reply": "ok", "customer_name": "Sara", "interest": "buyer",
                               "offer": None, "offer_id": 1, "reservation_requested": True,
                               "missing": [], "ready_for_manager": False})

        handle_incoming(self.conn, self.settings, msg("b1", "بغيت نحجز الفيلا"), llm=fake_llm)
        self.assertIn("فيلا", seen["system"])
        self.assertIn("ONLY properties", seen["system"])
        row = self.conn.execute("SELECT relation FROM customer_offers").fetchone()
        self.assertEqual(row["relation"], "reservation")


if __name__ == "__main__":
    unittest.main()
