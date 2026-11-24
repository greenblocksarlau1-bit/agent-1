import hashlib
import hmac
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from app import db
from app.agent import classify, handle_incoming
from app.config import Settings
from app.server import create_server
from app.whatsapp import extract_messages, verify_signature

SECRET = "test-secret"
VERIFY = "test-verify"


def make_settings(db_path: str) -> Settings:
    return Settings(
        verify_token=VERIFY, app_secret=SECRET, whatsapp_token="", phone_number_id="",
        manager_phone="", db_path=db_path, graph_version="v21.0", port=0, auto_reply=True,
    )


def sample_payload(message_id="wamid.1", text="بغيت نعرف ثمن الأرض"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "contacts": [{"wa_id": "212600000001", "profile": {"name": "Ali"}}],
            "messages": [{"from": "212600000001", "id": message_id, "timestamp": "1700000000",
                          "type": "text", "text": {"body": text}}],
        }}]}],
    }


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


class WhatsAppTests(unittest.TestCase):
    def test_signature_valid_and_invalid(self):
        body = b'{"a":1}'
        self.assertTrue(verify_signature(SECRET, body, sign(body)))
        self.assertFalse(verify_signature(SECRET, body, "sha256=deadbeef"))
        self.assertFalse(verify_signature(SECRET, body, None))
        self.assertFalse(verify_signature("", body, sign(body)))

    def test_extract_messages(self):
        msgs = extract_messages(sample_payload())
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["id"], "wamid.1")
        self.assertEqual(msgs[0]["name"], "Ali")
        self.assertIn("ثمن", msgs[0]["body"])

    def test_extract_handles_empty_payload(self):
        self.assertEqual(extract_messages({}), [])


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.settings = make_settings(self.tmp.name)
        self.conn = db.connect(self.tmp.name)
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)

    def test_classify(self):
        self.assertEqual(classify("عندي ضيعة للبيع في أزيلال"), "offer")
        self.assertEqual(classify("combien coûte le terrain ?"), "interest")
        self.assertEqual(classify("salam"), "other")

    def test_incoming_is_stored_once(self):
        msg = extract_messages(sample_payload())[0]
        handle_incoming(self.conn, self.settings, msg)
        handle_incoming(self.conn, self.settings, msg)  # تكرار من Meta
        count = self.conn.execute("SELECT COUNT(*) FROM messages WHERE direction='in'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_greeting_sent_once_per_customer(self):
        handle_incoming(self.conn, self.settings, extract_messages(sample_payload("wamid.1"))[0])
        handle_incoming(self.conn, self.settings, extract_messages(sample_payload("wamid.2"))[0])
        outs = self.conn.execute("SELECT COUNT(*) FROM messages WHERE direction='out'").fetchone()[0]
        self.assertEqual(outs, 1)

    def test_seller_offer_creates_draft(self):
        msg = extract_messages(sample_payload("wamid.9", "عندي أرض للبيع 2 هكتار"))[0]
        handle_incoming(self.conn, self.settings, msg)
        row = self.conn.execute("SELECT status, details FROM offers").fetchone()
        self.assertEqual(row["status"], "draft")
        self.assertIn("أرض", row["details"])


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.server = create_server(make_settings(self.tmp.name), host="127.0.0.1", port=0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        os.unlink(self.tmp.name)

    def url(self, query=""):
        return f"http://127.0.0.1:{self.port}/webhook{query}"

    def test_verification_challenge(self):
        with urllib.request.urlopen(self.url(f"?hub.mode=subscribe&hub.verify_token={VERIFY}&hub.challenge=12345")) as r:
            self.assertEqual(r.read().decode(), "12345")

    def test_wrong_verify_token_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url("?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1"))
        self.assertEqual(ctx.exception.code, 403)

    def test_post_with_bad_signature_rejected(self):
        body = json.dumps(sample_payload()).encode()
        req = urllib.request.Request(self.url(), data=body, method="POST",
                                     headers={"X-Hub-Signature-256": "sha256=bad"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_post_with_valid_signature_accepted(self):
        body = json.dumps(sample_payload("wamid.77")).encode()
        req = urllib.request.Request(self.url(), data=body, method="POST",
                                     headers={"X-Hub-Signature-256": sign(body)})
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.read().decode(), "EVENT_RECEIVED")


if __name__ == "__main__":
    unittest.main()
