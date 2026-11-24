"""خادم Webhook. يستخدم مكتبة http القياسية لتجنب الاعتماد على حزم خارجية."""
import json
import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import db
from .agent import handle_incoming
from .config import Settings, load_settings
from .whatsapp import extract_messages, verify_signature

MAX_BODY = 1_000_000  # 1 MB
log = logging.getLogger("wassata")


def make_handler(settings: Settings):
    class WebhookHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/webhook":
                return self._reply(404, "not found")
            q = urllib.parse.parse_qs(parsed.query)
            mode = q.get("hub.mode", [""])[0]
            token = q.get("hub.verify_token", [""])[0]
            challenge = q.get("hub.challenge", [""])[0]
            # تحقق اشتراك Meta: يجب أن يُعاد التحدي كما هو
            if mode == "subscribe" and settings.verify_token and token == settings.verify_token:
                return self._reply(200, challenge)
            return self._reply(403, "forbidden")

        def do_POST(self):
            if self.path.split("?")[0] != "/webhook":
                return self._reply(404, "not found")
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY:
                return self._reply(413, "too large")
            body = self.rfile.read(length)

            if not verify_signature(settings.app_secret, body, self.headers.get("X-Hub-Signature-256")):
                log.warning("رفض طلب بتوقيع غير صالح")
                return self._reply(403, "bad signature")

            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return self._reply(400, "bad json")

            conn = db.connect(settings.db_path)
            try:
                for msg in extract_messages(payload):
                    try:
                        handle_incoming(conn, settings, msg)
                    except Exception:
                        # لا نفشل الطلب كله بسبب رسالة واحدة، حتى لا تعيد Meta الإرسال بلا نهاية
                        log.exception("فشل معالجة الرسالة %s", msg.get("id"))
            finally:
                conn.close()
            # Meta تتوقع 200 بسرعة
            return self._reply(200, "EVENT_RECEIVED")

        def _reply(self, status: int, text: str):
            data = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):  # نترك التسجيل للـ logging
            log.info("%s - %s", self.address_string(), fmt % args)

    return WebhookHandler


def create_server(settings: Settings, host: str = "0.0.0.0", port: int | None = None) -> HTTPServer:
    conn = db.connect(settings.db_path)
    db.init_db(conn)
    conn.close()
    return HTTPServer((host, settings.port if port is None else port), make_handler(settings))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    server = create_server(settings)
    log.info("الخادم يعمل على المنفذ %s", server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
