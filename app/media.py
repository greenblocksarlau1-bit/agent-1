"""تخزين وسائط الزبناء وترتيبها: حسب الزبون والعرض ونوع الملف (صور، فيديو، وثائق قانونية، أخرى)."""
import os
import re

from . import db

MEDIA_ROOT = os.environ.get("MEDIA_DIR", "media")
EXTENSIONS = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    "video/mp4": "mp4", "video/3gpp": "3gp", "audio/ogg": "ogg", "audio/mpeg": "mp3",
    "application/pdf": "pdf",
}
# كلمات تدل على وثيقة ملكية أو مخطط: الرسم العقاري، الرسم الطوبوغرافي، عقد الملكية، الكناش...
LEGAL_WORDS = ["رسم", "ملكية", "وثيقة", "عقاري", "كناش", "كنانيش", "titre", "plan", "topo", "cadastre", "acte"]


def _phone_folder(phone: str) -> str:
    return re.sub(r"\D", "", phone or "") or "unknown"


def classify(kind: str, caption: str | None, filename: str | None) -> str:
    text = f"{caption or ''} {filename or ''}".lower()
    if kind == "document" or any(word.lower() in text for word in LEGAL_WORDS):
        return "legal"
    if kind == "image":
        return "photo"
    if kind == "video":
        return "video"
    return "other"


def save_media(conn, settings, customer_id: int, phone: str, msg: dict, download) -> str:
    """ينزّل الوسيط ويحفظه في مجلد مرتب ويسجّله في قاعدة البيانات. download(settings, media_id) -> (bytes, mime)."""
    data, mime = download(settings, msg["media_id"])
    mime = mime or msg.get("mime")
    kind = msg["media_kind"]
    label = classify(kind, msg.get("caption"), msg.get("filename"))
    offer_id = db.latest_open_offer(conn, customer_id)
    ext = EXTENSIONS.get(mime, "bin")
    folder = os.path.join(MEDIA_ROOT, _phone_folder(phone), f"offer-{offer_id or 'none'}", label)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{msg['media_id']}.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    db.insert_media(conn, msg["media_id"], customer_id, offer_id, kind, label, mime,
                    msg.get("filename"), msg.get("caption"), path)
    return path


def relink(conn, customer_id: int) -> None:
    """يربط الوسائط التي وصلت قبل إنشاء العرض بالعرض المفتوح، وينقل ملفاتها إلى مجلد العرض."""
    offer_id = db.latest_open_offer(conn, customer_id)
    if offer_id is None:
        return
    phone = conn.execute("SELECT phone FROM customers WHERE id = ?", (customer_id,)).fetchone()["phone"]
    rows = conn.execute(
        "SELECT id, label, path FROM media WHERE customer_id = ? AND offer_id IS NULL", (customer_id,)
    ).fetchall()
    for row in rows:
        folder = os.path.join(MEDIA_ROOT, _phone_folder(phone), f"offer-{offer_id}", row["label"])
        os.makedirs(folder, exist_ok=True)
        new_path = os.path.join(folder, os.path.basename(row["path"]))
        if row["path"] and os.path.exists(row["path"]):
            os.replace(row["path"], new_path)
        conn.execute("UPDATE media SET offer_id = ?, path = ? WHERE id = ?", (offer_id, new_path, row["id"]))
    conn.commit()
