"""إرسال العرض الموافَق عليه إلى مستودع الأتمتة (social-to-blogger-automation) عبر repository_dispatch.
الأفيش والنشر على Blogger وفيسبوك وإنستغرام يتم داخل GitHub Actions في ذلك المستودع."""
import json
import urllib.request

from .config import Settings
from .poster import build_caption, build_poster_html

# تحويل تصنيفاتنا إلى تصنيفات المستودع (تمت الموافقة عليه)
CATEGORY_MAP = {"land": "land", "farm": "land", "property": "residential", "commercial": "residential"}
# نوع الصورة في صفحة Blogger: land للأراضي والضيّع، res للمباني
MEDIA_MAP = {"land": "land", "farm": "land", "property": "res", "commercial": "res"}


def build_payload(row) -> dict:
    specs = json.loads(row["specs"]) if row["specs"] else {}
    raw_category = row["category"] or "land"
    return {
        "offer_id": row["id"],
        "title": row["title"] or "عرض عقاري",
        "category": CATEGORY_MAP.get(raw_category, "land"),
        "media": MEDIA_MAP.get(raw_category, "land"),
        "badge": "للبيع · " + ("أرض" if raw_category in ("land", "farm") else "عقار"),
        "location": row["location"] or "غير محدد",
        "area": specs.get("area") or "غير محدد",
        "price": row["price"] or "ثمن قابل للتفاوض",
        "caption": build_caption(row),
        "poster_html": build_poster_html(row),
    }


def dispatch_offer(settings: Settings, row) -> bool:
    """يرسل الحدث إلى المستودع. بدون GITHUB_DISPATCH_TOKEN يكتفي بالتسجيل (وضع تجريبي)."""
    payload = build_payload(row)
    if not settings.github_dispatch_token:
        print(f"[dry-run] dispatch offer #{row['id']} to {settings.automation_repo}: {payload['title']}")
        return False
    body = json.dumps({"event_type": "new-offer", "client_payload": payload}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{settings.automation_repo}/dispatches",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.github_dispatch_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status == 204
