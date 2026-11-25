import json
import os
import tempfile
import unittest

from app import db, media
from app.agent import handle_incoming
from app.config import Settings
from app.whatsapp import extract_messages


def settings_for(path):
    return Settings(verify_token="v", app_secret="s", whatsapp_token="", phone_number_id="",
                    manager_phone="", db_path=path, graph_version="v21.0", port=0,
                    auto_reply=True, anthropic_api_key="")


def image_payload(mid="media-1", caption="صورة الأرض", phone="212600000001"):
    return {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": phone, "profile": {"name": "Ali"}}],
        "messages": [{"from": phone, "id": mid, "type": "image",
                      "image": {"id": "MEDIA-" + mid, "mime_type": "image/jpeg", "caption": caption}}],
    }}]}]}


class MediaTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.root = tempfile.mkdtemp()
        media.MEDIA_ROOT = self.root
        self.conn = db.connect(self.path)
        db.init_db(self.conn)
        self.settings = settings_for(self.path)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def fake_download(self, settings, media_id):
        return b"fake-bytes", "image/jpeg"

    def test_extracts_media_fields(self):
        msg = extract_messages(image_payload())[0]
        self.assertEqual(msg["media_id"], "MEDIA-media-1")
        self.assertEqual(msg["media_kind"], "image")
        self.assertEqual(msg["body"], "صورة الأرض")

    def _offer_llm(self, messages, system=None):
        return json.dumps({"reply": "ok", "customer_name": None, "interest": "seller",
                           "offer": {"title": "أرض", "category": "land", "location": "أزيلال",
                                     "price": None, "details": None, "availability": None},
                           "ready_for_manager": False, "missing": ["price"]})

    def test_photo_after_offer_is_linked_and_saved(self):
        handle_incoming(self.conn, self.settings, extract_messages(image_payload("t0", "عندي أرض"))[0],
                        llm=self._offer_llm, downloader=self.fake_download)
        handle_incoming(self.conn, self.settings, extract_messages(image_payload("m1", "ستايلة الأرض"))[0],
                        llm=self._offer_llm, downloader=self.fake_download)
        row = self.conn.execute("SELECT * FROM media WHERE id = 'MEDIA-m1'").fetchone()
        self.assertEqual(row["label"], "photo")
        self.assertIsNotNone(row["offer_id"])
        self.assertTrue(os.path.exists(row["path"]))
        self.assertIn("offer-", row["path"])

    def test_photo_before_offer_is_relinked_and_moved(self):
        handle_incoming(self.conn, self.settings, extract_messages(image_payload("m9", "صورة قبل العرض"))[0],
                        llm=self._offer_llm, downloader=self.fake_download)
        row = self.conn.execute("SELECT * FROM media WHERE id = 'MEDIA-m9'").fetchone()
        self.assertIsNotNone(row["offer_id"])
        self.assertTrue(os.path.exists(row["path"]))
        self.assertIn(f"offer-{row['offer_id']}", row["path"])

    def test_legal_document_classified_by_caption(self):
        self.assertEqual(media.classify("image", "الرسم العقاري", None), "legal")
        self.assertEqual(media.classify("document", None, "scan.pdf"), "legal")
        self.assertEqual(media.classify("video", "جولة في الأرض", None), "video")

    def test_download_failure_does_not_stop_conversation(self):
        def broken(settings, media_id):
            raise RuntimeError("network down")
        handle_incoming(self.conn, self.settings, extract_messages(image_payload("m2"))[0], downloader=broken)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages WHERE direction = 'in'").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM media").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
