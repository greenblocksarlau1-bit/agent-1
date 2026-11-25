"""التعامل مع WhatsApp Cloud API: التحقق من التوقيع، استخراج الرسائل والوسائط، تنزيل الملفات، وإرسال الردود."""
import hashlib
import hmac
import json
import urllib.request

from .config import Settings

MEDIA_TYPES = ("image", "video", "document", "audio")


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """يتحقق من أن الطلب جاء من Meta باستخدام X-Hub-Signature-256."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", header)


def extract_messages(payload: dict) -> list[dict]:
    """يحوّل حمولة Webhook إلى قائمة رسائل مبسطة، مع بيانات الوسائط إن وُجدت."""
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                sender = msg.get("from")
                kind = msg.get("type")
                block = msg.get(kind, {}) if kind in MEDIA_TYPES else {}
                body = msg.get("text", {}).get("body", "") if kind == "text" else (block.get("caption") or "")
                messages.append({
                    "id": msg.get("id"),
                    "from": sender,
                    "name": names.get(sender),
                    "type": kind,
                    "body": body,
                    "timestamp": msg.get("timestamp"),
                    "raw": json.dumps(msg, ensure_ascii=False),
                    "media_id": block.get("id"),
                    "media_kind": kind if block else None,
                    "mime": block.get("mime_type"),
                    "filename": block.get("filename"),
                    "caption": block.get("caption"),
                })
    return messages


def _get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_media(settings: Settings, media_id: str) -> tuple[bytes, str | None]:
    """ينزّل الملف من Meta: أولاً رابط التنزيل من معرّف الوسيط، ثم الملف نفسه بالتوكن."""
    meta = _get_json(f"https://graph.facebook.com/{settings.graph_version}/{media_id}", settings.whatsapp_token)
    req = urllib.request.Request(meta["url"], headers={"Authorization": f"Bearer {settings.whatsapp_token}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read(), meta.get("mime_type")


def send_text(settings: Settings, to: str, text: str) -> dict | None:
    """يرسل رسالة نصية. إن لم تكن بيانات الإرسال مضبوطة يكتفي بالتسجيل (وضع تجريبي)."""
    if not settings.whatsapp_token or not settings.phone_number_id:
        print(f"[dry-run] to={to}: {text}")
        return None
    url = f"https://graph.facebook.com/{settings.graph_version}/{settings.phone_number_id}/messages"
    data = json.dumps({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {settings.whatsapp_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print("Meta refused:", e.read().decode("utf-8", "replace"))
        raise
