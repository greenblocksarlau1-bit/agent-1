"""Manager commands over WhatsApp, and notifications when a listing awaits approval."""
import re

from . import db, ranking
from .config import Settings
from .whatsapp import send_text

HELP = "Commands: pending | approve ID | reject ID | reservations | report"


def _digits(value) -> str:
    return re.sub(r"\D", "", value or "")


def is_manager(settings: Settings, phone: str) -> bool:
    return bool(settings.manager_phone) and _digits(phone) == _digits(settings.manager_phone)


def handle_command(conn, text: str) -> str:
    from .report import build_report

    parts = text.strip().split()
    if not parts:
        return HELP
    cmd = parts[0].lower()
    if cmd == "pending":
        rows = db.pending_offers(conn)
        if not rows:
            return "No pending offers."
        return "\n".join(f"#{r['id']} {r['title']} | {r['location']} | {r['price']}" for r in rows)
    if cmd in ("approve", "reject") and len(parts) == 2 and parts[1].isdigit():
        status = "published" if cmd == "approve" else "rejected"
        if not db.set_offer_status(conn, int(parts[1]), status):
            return f"offer {parts[1]} not found"
        ranking.refresh_scores(conn)
        return f"offer {parts[1]} -> {status}"
    if cmd == "reservations":
        rows = db.reservations(conn)
        return "\n".join(f"{r['phone']} {r['name'] or ''} | #{r['offer_id']} {r['title']}" for r in rows) or "No reservations."
    if cmd == "report":
        return build_report(conn)
    return HELP


def notify_pending(conn, settings: Settings, customer_id: int) -> None:
    row = conn.execute(
        "SELECT id, title, category, location, price FROM offers "
        "WHERE owner_customer_id = ? AND status = 'pending_approval' ORDER BY id DESC LIMIT 1",
        (customer_id,),
    ).fetchone()
    if row is None or not settings.manager_phone:
        return
    text = (f"New listing awaiting approval #{row['id']}\n"
            f"{row['title']} | {row['category']} | {row['location']} | {row['price'] or 'no price'}\n"
            f"Reply: approve {row['id']}  or  reject {row['id']}")
    send_text(settings, settings.manager_phone, text)
