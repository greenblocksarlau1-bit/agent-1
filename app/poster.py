"""Instagram poster (1080x1350 HTML) and caption for an offer, following the Wassata rules:
type, size, location and price in the first two lines; 5 to 8 relevant hashtags; a clear call to action."""
import html
import os

BRAND = "Wassata"
CTA_AR = "للتفاصيل والمعاينة: اكتب 'تفاصيل' في التعليقات أو راسلنا عبر واتساب"
HASHTAGS = ["#وساطة_عقارية", "#استثمار_عقاري_المغرب"]


def build_caption(row) -> str:
    price = row["price"] or "قابل للنقاش"
    first = f"{row['title']} | {row['location'] or ''} | {price}".strip(" |")
    tags = HASHTAGS.copy()
    if row["category"] == "land":
        tags += ["#أراضي_للبيع", "#ضيعة_فلاحية"]
    elif row["category"] == "property":
        tags += ["#عقارات_للبيع", "#فيلا_للبيع"]
    if row["location"]:
        tags.append("#" + row["location"].replace(" ", "_"))
    return "\n".join([first, row["details"] or "", CTA_AR, " ".join(tags[:8])]).strip()


def _esc(value) -> str:
    return html.escape(str(value)) if value else "—"


def build_poster_html(row) -> str:
    return f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>{BRAND} - offer {row['id']}</title>
<style>
body{{margin:0;font-family:Arial,sans-serif;background:#f4f1ea}}
.poster{{width:1080px;height:1350px;background:linear-gradient(160deg,#1f4d3a,#0d2a20);color:#fff;
padding:90px;box-sizing:border-box;display:flex;flex-direction:column;gap:36px}}
.brand{{font-size:40px;letter-spacing:2px;opacity:.85}}
.type{{font-size:52px;color:#e8c872}}
h1{{font-size:88px;line-height:1.1;margin:0}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:28px;font-size:38px}}
.box{{background:rgba(255,255,255,.08);border-radius:24px;padding:28px}}
.label{{font-size:28px;opacity:.7}}
.price{{font-size:72px;color:#e8c872;font-weight:bold}}
.cta{{margin-top:auto;font-size:38px;background:#e8c872;color:#0d2a20;border-radius:20px;padding:30px;text-align:center}}
</style></head>
<body><div class="poster">
<div class="brand">{BRAND}</div>
<div class="type">{_esc(row['category'])}</div>
<h1>{_esc(row['title'])}</h1>
<div class="grid">
<div class="box"><div class="label">الموقع</div>{_esc(row['location'])}</div>
<div class="box"><div class="label">التوفر</div>{_esc(row['availability'])}</div>
</div>
<div class="price">{_esc(row['price'] or 'قابل للنقاش')}</div>
<div class="box">{_esc(row['details'])}</div>
<div class="cta">{CTA_AR}</div>
</div></body></html>"""


def write_poster(conn, offer_id: int, folder: str = "posters") -> str:
    row = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()
    if row is None:
        return f"offer {offer_id} not found"
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"offer-{offer_id}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_poster_html(row))
    return f"poster: {os.path.abspath(path)}\n\ncaption:\n{build_caption(row)}"
