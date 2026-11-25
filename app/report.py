"""Manager report: customers, offers, bookings, and the top published offers."""
from . import ranking


def build_report(conn) -> str:
    ranking.refresh_scores(conn)
    interests = {r[0]: r[1] for r in conn.execute("SELECT interest, COUNT(*) FROM customers GROUP BY interest")}
    statuses = {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM offers GROUP BY status")}
    customers_total = sum(interests.values())
    messages_week = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE created_at >= datetime('now', '-7 days')"
    ).fetchone()[0]
    reservations = conn.execute("SELECT COUNT(*) FROM customer_offers WHERE relation = 'reservation'").fetchone()[0]
    top = conn.execute(
        "SELECT id, title, location, efficiency_score FROM offers WHERE status = 'published' "
        "ORDER BY efficiency_score DESC, id DESC LIMIT 3"
    ).fetchall()

    lines = [
        "Weekly report",
        f"Customers: {customers_total} (sellers {interests.get('seller', 0)}, "
        f"buyers {interests.get('buyer', 0)}, info {interests.get('info', 0)}, unknown {interests.get('unknown', 0)})",
        f"Messages in the last 7 days: {messages_week}",
        f"Offers: draft {statuses.get('draft', 0)}, pending {statuses.get('pending_approval', 0)}, "
        f"published {statuses.get('published', 0)}, rejected {statuses.get('rejected', 0)}",
        f"Booking requests: {reservations}",
        "Top published offers:",
    ]
    if top:
        lines += [f"  #{r['id']} {r['title']} | {r['location']} | score {r['efficiency_score']}" for r in top]
    else:
        lines.append("  none yet")
    return "\n".join(lines)
