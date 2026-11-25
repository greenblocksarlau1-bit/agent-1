"""طبقة قاعدة البيانات. SQLite من مكتبة Python القياسية، وسهلة الانتقال إلى PostgreSQL لاحقاً."""
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone       TEXT UNIQUE NOT NULL,
    name        TEXT,
    interest    TEXT NOT NULL DEFAULT 'unknown',   -- unknown | buyer | seller | info
    notes       TEXT,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id           TEXT PRIMARY KEY,                 -- معرّف الرسالة من Meta، يمنع التكرار
    customer_id  INTEGER REFERENCES customers(id),
    direction    TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    body         TEXT,
    kind         TEXT,                             -- offer | interest | other
    raw          TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS offers (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_customer_id INTEGER REFERENCES customers(id),
    title             TEXT,
    category          TEXT,                       -- land | farm | property | commercial
    price             TEXT,
    location          TEXT,
    details           TEXT,
    status            TEXT NOT NULL DEFAULT 'draft',  -- draft | pending_approval | published | sold
    efficiency_score  REAL DEFAULT 0,             -- للترتيب لاحقاً
    availability      TEXT DEFAULT 'available',
    specs             TEXT,                       -- JSON: legal status, zoning, access, utilities...
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_offers (
    customer_id INTEGER REFERENCES customers(id),
    offer_id    INTEGER REFERENCES offers(id),
    relation    TEXT NOT NULL DEFAULT 'interested', -- interested | owner
    PRIMARY KEY (customer_id, offer_id, relation)
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(offers)")}
    if "specs" not in cols:  # قواعد بيانات قديمة
        conn.execute("ALTER TABLE offers ADD COLUMN specs TEXT")
    conn.commit()


def upsert_customer(conn: sqlite3.Connection, phone: str, name: str | None) -> int:
    conn.execute(
        """
        INSERT INTO customers (phone, name) VALUES (?, ?)
        ON CONFLICT(phone) DO UPDATE SET
            name = COALESCE(excluded.name, customers.name),
            updated_at = CURRENT_TIMESTAMP
        """,
        (phone, name),
    )
    row = conn.execute("SELECT id FROM customers WHERE phone = ?", (phone,)).fetchone()
    return row["id"]


def message_exists(conn: sqlite3.Connection, message_id: str) -> bool:
    return conn.execute("SELECT 1 FROM messages WHERE id = ?", (message_id,)).fetchone() is not None


def insert_message(conn, message_id, customer_id, direction, body, kind=None, raw=None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO messages (id, customer_id, direction, body, kind, raw) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, customer_id, direction, body, kind, raw),
    )


def has_outgoing_greeting(conn: sqlite3.Connection, customer_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM messages WHERE customer_id = ? AND direction = 'out' LIMIT 1",
        (customer_id,),
    ).fetchone() is not None


def create_offer_draft(conn, owner_customer_id: int, details: str) -> int:
    cur = conn.execute(
        "INSERT INTO offers (owner_customer_id, details) VALUES (?, ?)",
        (owner_customer_id, details),
    )
    conn.execute(
        "UPDATE customers SET interest = 'seller', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (owner_customer_id,),
    )
    return cur.lastrowid




def list_catalog(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    """العروض المنشورة فقط، وهي الوحيدة التي يحق للوكيل وصفها للمشترين."""
    return conn.execute(
        "SELECT id, title, category, location, price, details, availability, specs FROM offers "
        "WHERE status = 'published' ORDER BY efficiency_score DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def link_customer_offer(conn: sqlite3.Connection, customer_id: int, offer_id: int, relation: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO customer_offers (customer_id, offer_id, relation) VALUES (?, ?, ?)",
        (customer_id, offer_id, relation),
    )


def set_offer_status(conn: sqlite3.Connection, offer_id: int, status: str) -> int:
    cur = conn.execute("UPDATE offers SET status = ? WHERE id = ?", (status, offer_id))
    conn.commit()
    return cur.rowcount


def pending_offers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, title, category, location, price, details FROM offers WHERE status = 'pending_approval' ORDER BY id"
    ).fetchall()


def reservations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT c.phone, c.name, o.id AS offer_id, o.title FROM customer_offers co "
        "JOIN customers c ON c.id = co.customer_id JOIN offers o ON o.id = co.offer_id "
        "WHERE co.relation = 'reservation' ORDER BY co.rowid DESC"
    ).fetchall()


def save_offer_draft(conn: sqlite3.Connection, owner_customer_id: int, offer: dict, ready: bool) -> int:
    """يحدّث مسودة العرض الأخيرة للزبون أو ينشئ واحدة جديدة، ويرفعها للمدير عند الاكتمال."""
    fields = ("title", "category", "location", "price", "details", "availability")
    values = {f: offer.get(f) for f in fields}
    specs = offer.get("specs")
    specs_text = json.dumps(specs, ensure_ascii=False) if isinstance(specs, dict) and specs else None
    row = conn.execute(
        "SELECT id FROM offers WHERE owner_customer_id = ? AND status IN ('draft', 'pending_approval') ORDER BY id DESC LIMIT 1",
        (owner_customer_id,),
    ).fetchone()
    if row:
        offer_id = row["id"]
        conn.execute(
            "UPDATE offers SET " + ", ".join(f"{f} = COALESCE(?, {f})" for f in fields)
            + ", specs = COALESCE(?, specs) WHERE id = ?",
            (*[values[f] for f in fields], specs_text, offer_id),
        )
    else:
        cur = conn.execute(
            "INSERT INTO offers (owner_customer_id, title, category, location, price, details, availability, specs) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (owner_customer_id, *[values[f] for f in fields], specs_text),
        )
        offer_id = cur.lastrowid
    if ready:
        conn.execute("UPDATE offers SET status = 'pending_approval' WHERE id = ?", (offer_id,))
    return offer_id


def pending_count(conn: sqlite3.Connection, customer_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM offers WHERE owner_customer_id = ? AND status = 'pending_approval'", (customer_id,)
    ).fetchone()[0]
