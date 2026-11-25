"""منطق الوكيل: يستقبل رسالة، يحفظها، ويرد عبر Claude إن توفر المفتاح، وإلا يرسل الترحيب فقط."""
import sqlite3
import uuid

from . import db
from .config import Settings
from .conversation import SYSTEM_PROMPT, apply_result, history_for_model, parse_reply
from .llm import call_claude
from .whatsapp import send_text

OFFER_KEYWORDS = [
    "عرض", "للبيع", "نبيع", "عندي", "ضيعة", "أرض", "ارض", "شقة", "فيلا", "محل",
    "à vendre", "vends", "ferme", "appartement", "villa",
]
INTEREST_KEYWORDS = [
    "شراء", "نشري", "بغيت", "بغينا", "ثمن", "السعر", "شحال", "معلومات", "تفاصيل", "نحب",
    "prix", "combien", "intéressé", "interessé", "info", "renseignements", "acheter",
]

GREETING = (
    "مرحباً بك في وساطة عقارية وتجارية 🏡\n"
    "Bienvenue chez Wassata. Comment puis-je vous aider ?\n"
    "أخبرنا: هل تبحث عن عقار أو أرض، أم لديك عرض للبيع؟"
)


def classify(text: str) -> str:
    lowered = text.lower()
    if any(k.lower() in lowered for k in INTEREST_KEYWORDS):
        return "interest"
    if any(k.lower() in lowered for k in OFFER_KEYWORDS):
        return "offer"
    return "other"


def send_and_store(conn: sqlite3.Connection, settings: Settings, customer_id: int, phone: str, text: str) -> None:
    if not settings.auto_reply:
        return
    reply = send_text(settings, phone, text)
    out_id = (reply or {}).get("messages", [{}])[0].get("id") or f"local-{uuid.uuid4().hex}"
    db.insert_message(conn, out_id, customer_id, "out", text)


def handle_incoming(conn: sqlite3.Connection, settings: Settings, msg: dict, llm=None) -> None:
    """يعالج رسالة واردة. llm اختياري لتمرير نموذج وهمي في الاختبارات."""
    if not msg.get("id") or not msg.get("from"):
        return
    if db.message_exists(conn, msg["id"]):
        return

    phone = msg["from"]
    body = msg.get("body", "")
    customer_id = db.upsert_customer(conn, phone, msg.get("name"))
    db.insert_message(conn, msg["id"], customer_id, "in", body, classify(body), msg.get("raw"))
    conn.commit()

    if llm is None and settings.anthropic_api_key:
        def llm(messages):
            return call_claude(settings.anthropic_api_key, settings.anthropic_model, SYSTEM_PROMPT, messages)

    if llm is not None:
        result = parse_reply(llm(history_for_model(conn, customer_id)))
        apply_result(conn, customer_id, result)
        send_and_store(conn, settings, customer_id, phone, result["reply"])
    else:
        if classify(body) == "offer" and body:
            db.create_offer_draft(conn, customer_id, body)
        if not db.has_outgoing_greeting(conn, customer_id):
            send_and_store(conn, settings, customer_id, phone, GREETING)

    conn.commit()
