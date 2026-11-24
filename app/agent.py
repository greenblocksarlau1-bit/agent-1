"""منطق الوكيل: يستقبل رسالة، يحفظها، يصنّفها، ويرد عند الحاجة."""
import sqlite3

from . import db
from .config import Settings
from .whatsapp import send_text

# كلمات مفتاحية أولية (عربي / فرنسي / دارجة). ستُستبدل بتصنيف عبر Claude في المرحلة الثانية.
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
    """يعيد offer (عرض بيع) أو interest (استفسار/شراء) أو other."""
    lowered = text.lower()
    # الاستفسار يُفحص أولاً: الزبون الذي يسأل عن "ثمن الأرض" مشترٍ وليس بائعاً
    if any(k.lower() in lowered for k in INTEREST_KEYWORDS):
        return "interest"
    if any(k.lower() in lowered for k in OFFER_KEYWORDS):
        return "offer"
    return "other"


def handle_incoming(conn: sqlite3.Connection, settings: Settings, msg: dict) -> None:
    """يعالج رسالة واردة واحدة. آمن ضد التكرار لأن Meta قد يعيد إرسال نفس الحدث."""
    if not msg.get("id") or not msg.get("from"):
        return
    if db.message_exists(conn, msg["id"]):
        return

    phone = msg["from"]
    customer_id = db.upsert_customer(conn, phone, msg.get("name"))
    kind = classify(msg.get("body", ""))
    db.insert_message(conn, msg["id"], customer_id, "in", msg.get("body", ""), kind, msg.get("raw"))

    if kind == "offer" and msg.get("body"):
        db.create_offer_draft(conn, customer_id, msg["body"])

    first_contact = not db.has_outgoing_greeting(conn, customer_id)
    if first_contact and settings.auto_reply:
        reply = send_text(settings, phone, GREETING)
        out_id = (reply or {}).get("messages", [{}])[0].get("id") or f"local-{msg['id']}"
        db.insert_message(conn, out_id, customer_id, "out", GREETING, None, None)

    conn.commit()
