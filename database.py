# -*- coding: utf-8 -*-
"""Dream Academy Manager — SQLite layer: schema, seed data, helpers, backups."""
import json
import os
import shutil
import sqlite3
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "academy.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

DEFAULT_SETTINGS = {
    "monthly_price": 20,
    "sessions_per_month": 12,
    "expiry_days": 35,
    "deduct_on_absence": False,
    "training_days": ["Sunday", "Tuesday", "Thursday"],
    "academy_phone": "",
    "coach_pin": "1234",
    "admin_pin": "0000",
    "template_renewal": "مرحبا، اشتراك [الاسم] بأكاديمية Dream Academy قرّب يخلص (ضل [X] حصص). للتجديد: [السعر] دينار بالشهر. يعطيكم العافية.",
    "template_absence": "مرحبا، لاحظنا غياب [الاسم] عن تمرين اليوم — إن شاء الله كل شي تمام؟",
}

SEED_GROUPS = [
    ("أشبال", "Kids (U-10)", 5, 9, "mixed", "Sun/Tue/Thu", "4:00–5:30"),
    ("ناشئين", "Juniors (U-14)", 10, 13, "M", "Sun/Tue/Thu", "5:30–7:00"),
    ("شباب", "Youth (U-18)", 14, 17, "M", "Sun/Tue/Thu", "7:00–8:30"),
    ("رجال", "Men", 18, 99, "M", "Sun/Tue/Thu", "8:30–10:00"),
    ("سيدات", "Ladies", 14, 99, "F", "Sun/Tue/Thu", "3:00–4:00"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL,
    min_age INTEGER DEFAULT 0,
    max_age INTEGER DEFAULT 99,
    gender TEXT DEFAULT 'mixed',
    schedule_days TEXT DEFAULT 'Sun/Tue/Thu',
    time_slot TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    birth_date TEXT,
    gender TEXT DEFAULT 'M',
    phone TEXT DEFAULT '',
    guardian_name TEXT DEFAULT '',
    guardian_phone TEXT DEFAULT '',
    group_id INTEGER REFERENCES groups(id),
    join_date TEXT,
    notes TEXT DEFAULT '',
    photo TEXT DEFAULT '',
    status TEXT DEFAULT 'active',          -- active / frozen / left
    trial_used INTEGER DEFAULT 0,
    frozen_at TEXT                          -- date freezing started (NULL if not frozen)
);
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    start_date TEXT NOT NULL,
    sessions_total INTEGER DEFAULT 12,
    sessions_used INTEGER DEFAULT 0,
    price REAL DEFAULT 20,
    expiry_date TEXT NOT NULL,
    status TEXT DEFAULT 'active'            -- active / expired / finished
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    subscription_id INTEGER REFERENCES subscriptions(id),
    amount REAL NOT NULL,
    date TEXT NOT NULL,
    method TEXT DEFAULT 'cash',             -- cash / cliq / other
    note TEXT DEFAULT '',
    receipt_no TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    session_date TEXT NOT NULL,
    group_id INTEGER REFERENCES groups(id),
    status TEXT NOT NULL,                   -- present / absent / excused
    marked_by TEXT DEFAULT '',
    marked_at TEXT,
    deducted INTEGER DEFAULT 0,             -- did this row consume a session?
    unpaid INTEGER DEFAULT 0,               -- present with no active subscription
    UNIQUE(player_id, session_date)
);
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL
);
"""


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    con = get_db()
    con.executescript(SCHEMA)
    _migrate(con)
    if con.execute("SELECT COUNT(*) c FROM groups").fetchone()["c"] == 0:
        con.executemany(
            "INSERT INTO groups (name_ar,name_en,min_age,max_age,gender,schedule_days,time_slot) VALUES (?,?,?,?,?,?,?)",
            SEED_GROUPS,
        )
    if con.execute("SELECT COUNT(*) c FROM settings").fetchone()["c"] == 0:
        con.execute("INSERT INTO settings (id, data) VALUES (1, ?)", (json.dumps(DEFAULT_SETTINGS),))
    con.commit()
    con.close()


def _migrate(con):
    """Add columns introduced after the first release, without touching existing data."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(players)").fetchall()}
    if "added_by" not in cols:
        con.execute("ALTER TABLE players ADD COLUMN added_by TEXT DEFAULT ''")


def get_settings():
    con = get_db()
    row = con.execute("SELECT data FROM settings WHERE id=1").fetchone()
    con.close()
    data = dict(DEFAULT_SETTINGS)
    if row:
        data.update(json.loads(row["data"]))
    return data


def save_settings(data):
    con = get_db()
    con.execute("UPDATE settings SET data=? WHERE id=1", (json.dumps(data, ensure_ascii=False),))
    con.commit()
    con.close()


# ---------- business helpers ----------

def today_str():
    return date.today().isoformat()


def refresh_subscription_status(con, sub_row, player_frozen=False):
    """Lazily transition active subs to finished/expired. Returns current status."""
    status = sub_row["status"]
    if status != "active":
        return status
    if sub_row["sessions_used"] >= sub_row["sessions_total"]:
        status = "finished"
    elif not player_frozen and today_str() > sub_row["expiry_date"]:
        status = "expired"
    if status != "active":
        con.execute("UPDATE subscriptions SET status=? WHERE id=?", (status, sub_row["id"]))
    return status


def get_active_subscription(con, player_id):
    """Return the player's active subscription row (after lazy refresh), or None."""
    player = con.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
    frozen = bool(player and player["frozen_at"])
    subs = con.execute(
        "SELECT * FROM subscriptions WHERE player_id=? AND status='active' ORDER BY start_date DESC",
        (player_id,),
    ).fetchall()
    for s in subs:
        if refresh_subscription_status(con, s, frozen) == "active":
            return con.execute("SELECT * FROM subscriptions WHERE id=?", (s["id"],)).fetchone()
    return None


def next_receipt_no(con):
    year = date.today().year
    prefix = f"DA-{year}-"
    row = con.execute(
        "SELECT receipt_no FROM payments WHERE receipt_no LIKE ? ORDER BY id DESC LIMIT 1", (prefix + "%",)
    ).fetchone()
    n = int(row["receipt_no"].split("-")[-1]) + 1 if row else 1
    return f"{prefix}{n:04d}"


def create_subscription(con, player_id, start_date, price=None, sessions_total=None,
                        method="cash", note="", amount=None):
    """New subscription + payment in one flow. Returns (sub_id, receipt_no)."""
    st = get_settings()
    price = float(price if price is not None else st["monthly_price"])
    sessions_total = int(sessions_total if sessions_total is not None else st["sessions_per_month"])
    expiry = (date.fromisoformat(start_date) + timedelta(days=int(st["expiry_days"]))).isoformat()
    # close any lingering active sub (one active sub max)
    con.execute(
        "UPDATE subscriptions SET status='finished' WHERE player_id=? AND status='active'", (player_id,)
    )
    cur = con.execute(
        "INSERT INTO subscriptions (player_id,start_date,sessions_total,sessions_used,price,expiry_date,status) "
        "VALUES (?,?,?,0,?,?,'active')",
        (player_id, start_date, sessions_total, price, expiry),
    )
    sub_id = cur.lastrowid
    receipt = next_receipt_no(con)
    con.execute(
        "INSERT INTO payments (player_id,subscription_id,amount,date,method,note,receipt_no) VALUES (?,?,?,?,?,?,?)",
        (player_id, sub_id, float(amount if amount is not None else price), today_str(), method, note, receipt),
    )
    return sub_id, receipt


def mark_attendance(con, player_id, session_date, group_id, status, marked_by=""):
    """Set/update attendance and manage session deduction. Returns dict summary."""
    st = get_settings()
    existing = con.execute(
        "SELECT * FROM attendance WHERE player_id=? AND session_date=?", (player_id, session_date)
    ).fetchone()

    # revert previous deduction if any (we recompute from scratch)
    if existing and existing["deducted"]:
        # the sub that was deducted from: the most recent one with sessions_used > 0
        sub = con.execute(
            "SELECT * FROM subscriptions WHERE player_id=? AND sessions_used > 0 ORDER BY start_date DESC LIMIT 1",
            (player_id,),
        ).fetchone()
        if sub:
            con.execute("UPDATE subscriptions SET sessions_used = sessions_used - 1 WHERE id=?", (sub["id"],))
            # un-finish if it was finished purely by count and not expired
            s2 = con.execute("SELECT * FROM subscriptions WHERE id=?", (sub["id"],)).fetchone()
            if s2["status"] == "finished" and s2["sessions_used"] < s2["sessions_total"] and today_str() <= s2["expiry_date"]:
                con.execute("UPDATE subscriptions SET status='active' WHERE id=?", (sub["id"],))

    if status is None or status == "none":
        # clear the mark entirely
        if existing:
            con.execute("DELETE FROM attendance WHERE id=?", (existing["id"],))
        con.commit()
        return {"status": "none", "unpaid": False}

    deduct = status == "present" or (status == "absent" and st.get("deduct_on_absence"))
    unpaid = 0
    deducted = 0
    if deduct:
        sub = get_active_subscription(con, player_id)
        if sub:
            con.execute("UPDATE subscriptions SET sessions_used = sessions_used + 1 WHERE id=?", (sub["id"],))
            s2 = con.execute("SELECT * FROM subscriptions WHERE id=?", (sub["id"],)).fetchone()
            refresh_subscription_status(con, s2)
            deducted = 1
        elif status == "present":
            unpaid = 1

    now = datetime.now().isoformat(timespec="seconds")
    if existing:
        con.execute(
            "UPDATE attendance SET status=?, group_id=?, marked_by=?, marked_at=?, deducted=?, unpaid=? WHERE id=?",
            (status, group_id, marked_by, now, deducted, unpaid, existing["id"]),
        )
    else:
        con.execute(
            "INSERT INTO attendance (player_id,session_date,group_id,status,marked_by,marked_at,deducted,unpaid) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (player_id, session_date, group_id, status, marked_by, now, deducted, unpaid),
        )
    con.commit()
    return {"status": status, "unpaid": bool(unpaid)}


def freeze_player(con, player_id):
    con.execute("UPDATE players SET status='frozen', frozen_at=? WHERE id=?", (today_str(), player_id))
    con.commit()


def unfreeze_player(con, player_id):
    p = con.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
    if p and p["frozen_at"]:
        days = (date.today() - date.fromisoformat(p["frozen_at"])).days
        if days > 0:
            sub = con.execute(
                "SELECT * FROM subscriptions WHERE player_id=? AND status IN ('active','expired') "
                "ORDER BY start_date DESC LIMIT 1", (player_id,),
            ).fetchone()
            if sub:
                new_expiry = (date.fromisoformat(sub["expiry_date"]) + timedelta(days=days)).isoformat()
                new_status = "active" if sub["sessions_used"] < sub["sessions_total"] and new_expiry >= today_str() else sub["status"]
                con.execute("UPDATE subscriptions SET expiry_date=?, status=? WHERE id=?",
                            (new_expiry, new_status, sub["id"]))
    con.execute("UPDATE players SET status='active', frozen_at=NULL WHERE id=?", (player_id,))
    con.commit()


def suggest_group(con, birth_date, gender):
    """Suggest group id from age + gender."""
    if not birth_date:
        return None
    try:
        bd = date.fromisoformat(birth_date)
    except ValueError:
        return None
    age = (date.today() - bd).days // 365
    rows = con.execute("SELECT * FROM groups").fetchall()
    best = None
    for g in rows:
        if g["min_age"] <= age <= g["max_age"] and (g["gender"] == "mixed" or g["gender"] == gender):
            # prefer gender-specific match over mixed
            if best is None or (best["gender"] == "mixed" and g["gender"] != "mixed"):
                best = g
    return best["id"] if best else None


def add_pending_player(con, full_name, group_id, guardian_phone="", gender="M",
                       birth_date="", added_by="coach"):
    """Quick add from the court: minimal fields, status=pending for admin review."""
    cur = con.execute(
        "INSERT INTO players (full_name,birth_date,gender,phone,guardian_name,guardian_phone,"
        "group_id,join_date,notes,status,trial_used,added_by) "
        "VALUES (?,?,?,?,'',?,?,?,'','pending',0,?)",
        (full_name.strip(), birth_date, gender, "", guardian_phone.strip(),
         group_id, today_str(), added_by),
    )
    con.commit()
    return cur.lastrowid


# ---------- backups ----------

def backup_db(force=False):
    """Copy academy.db to backups/academy-YYYY-MM-DD.db; keep last 30."""
    if not os.path.exists(DB_PATH):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    target = os.path.join(BACKUP_DIR, f"academy-{today_str()}.db")
    if force or not os.path.exists(target):
        shutil.copy2(DB_PATH, target)
    files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("academy-") and f.endswith(".db"))
    for old in files[:-30]:
        os.remove(os.path.join(BACKUP_DIR, old))
    return target
