"""منطق الحوار مع Claude: بناء السياق، وتحليل الرد المنظم، وتطبيق النتيجة على قاعدة البيانات."""
import json
import sqlite3

from . import db

SYSTEM_PROMPT = """You are the assistant of "Wassata", a Moroccan real-estate and commercial brokerage, chatting on WhatsApp.

Goals:
1. Reply in the same language the customer uses (Arabic, Moroccan Darija, French, or a mix). Keep replies short (2 to 4 sentences).
2. Find out whether the customer is a SELLER (has a property, land, farm or business to sell), a BUYER, or only seeks INFORMATION.
3. For sellers collect: title or short description, category (land, farm, property, commercial), location, area or size, price expectation, availability, and their name.
4. For buyers collect: what they look for, budget, preferred location, and their name.
5. Never confirm a price, legal status or availability as final. Say that the manager will confirm.
6. Never invent offers or facts. If you do not know, say so.

Seller requirements (ask for each one that is still missing, one or two at a time, never all at once):
a. Photos and videos of the property.
b. The land title (rasm 3aqari / titre foncier) or the topographic survey (rasm topographique), and any administrative document proving ownership.
c. The exact location: ask the seller to send a WhatsApp location pin or a Google Maps link.
d. Service fee: explain that Wassata's commission is 1.5% of the final sale amount. It is deducted only when the deal is concluded and the sale price is paid. Ask the seller to confirm acceptance. Do not quote any other fee; if asked, say the manager will confirm.
e. Publication consent: ask the seller's explicit approval to publish an advertisement for the sale request on social media. Nothing is published without the manager's approval.

Set "ready_for_manager" to true ONLY when all of a, b, c, d and e are collected. Otherwise set it to false and list the still-missing items in "missing".

Return ONLY a JSON object with this shape, and no other text:
{"reply": "message to send to the customer",
 "customer_name": string or null,
 "interest": "seller" | "buyer" | "info" | "unknown",
 "offer": {"title": string|null, "category": string|null, "location": string|null, "price": string|null, "details": string|null, "availability": string|null} or null,
 "missing": list of strings,
 "ready_for_manager": true or false}"""


def parse_reply(text: str) -> dict:
    """يستخرج JSON من رد النموذج، ويعود إلى النص الخام إن تعذّر ذلك."""
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict) and data.get("reply"):
                return data
        except json.JSONDecodeError:
            pass
    return {"reply": text.strip(), "customer_name": None, "interest": "unknown",
            "offer": None, "ready_for_manager": False}


def history_for_model(conn: sqlite3.Connection, customer_id: int, limit: int = 20) -> list[dict]:
    """آخر الرسائل بصيغة Claude، مع دمج الرسائل المتتالية من الدور نفسه وبدء الحوار برسالة زبون."""
    rows = conn.execute(
        "SELECT direction, body FROM messages WHERE customer_id = ? AND body IS NOT NULL AND body != '' "
        "ORDER BY rowid DESC LIMIT ?",
        (customer_id, limit),
    ).fetchall()
    msgs: list[dict] = []
    for row in reversed(rows):
        role = "user" if row["direction"] == "in" else "assistant"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n" + row["body"]
        else:
            msgs.append({"role": role, "content": row["body"]})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def apply_result(conn: sqlite3.Connection, customer_id: int, result: dict) -> None:
    """يطبّق نتيجة النموذج على الزبون والعرض: الاسم، نوع الاهتمام، المسودة، والرفع للمدير."""
    name = result.get("customer_name")
    if name:
        conn.execute("UPDATE customers SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (name, customer_id))
    interest = result.get("interest")
    if interest in ("seller", "buyer", "info"):
        conn.execute("UPDATE customers SET interest = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                     (interest, customer_id))
    offer = result.get("offer")
    if isinstance(offer, dict) and any(offer.values()):
        db.save_offer_draft(conn, customer_id, offer, bool(result.get("ready_for_manager")))
