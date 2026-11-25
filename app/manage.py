"""Manager tool: review pending listings, publish or reject them, and list reservations.

Usage:
  py -m app.manage pending
  py -m app.manage publish ID
  py -m app.manage reject ID
  py -m app.manage reservations
"""
import sys

from . import db
from .config import load_settings


def main(argv: list[str]) -> int:
    settings = load_settings()
    conn = db.connect(settings.db_path)
    db.init_db(conn)
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "pending":
        for r in db.pending_offers(conn):
            print(f"#{r['id']} | {r['title']} | {r['category']} | {r['location']} | {r['price']} | {r['details']}")
    elif cmd in ("publish", "reject") and len(argv) == 2 and argv[1].isdigit():
        status = "published" if cmd == "publish" else "rejected"
        ok = db.set_offer_status(conn, int(argv[1]), status)
        print(f"offer {argv[1]} -> {status}" if ok else f"offer {argv[1]} not found")
    elif cmd == "reservations":
        for r in db.reservations(conn):
            print(f"{r['phone']} | {r['name']} | offer #{r['offer_id']} {r['title']}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
