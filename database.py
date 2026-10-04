# -*- coding: utf-8 -*-
"""Dream Academy Manager, SQLite layer: schema, seed data, helpers, backups."""
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
    "template_absence": "مرحبا، لاحظنا غياب [الاسم] عن تمرين اليوم, إن شاء الله كل شي تمام؟",
    # subscription bundles the admin can pick at renewal
    "bundles": [
        {"name_en": "Monthly", "name_ar": "شهري", "sessions": 12, "price": 20},
        {"name_en": "8 sessions", "name_ar": "8 حصص", "sessions": 8, "price": 15},
        {"name_en": "Single", "name_ar": "حصة", "sessions": 1, "price": 3},
    ],
    # training-day schedule over time: [{"from": "YYYY-MM-DD", "days": [...]}].
    # Empty = training_days applies to all dates. Changing days "from a date"
    # appends an entry so past sessions keep their original schedule.
    "schedule_history": [],
    # whole-academy days off (Eid, court closed): [{"date": "YYYY-MM-DD", "note": ""}]
    "closed_days": [],
    # cash in the box before the app started tracking (for the running balance)
    "opening_balance": 0,
    # quick "log a session" costs: each is priced per booking / per unit and
    # entered with a quantity (3 groups = 3 court bookings)
    "cost_presets": [
        {"key": "court", "name_en": "Court booking", "name_ar": "حجز ملعب", "price": 5, "category": "court_rent"},
        {"key": "court_lights", "name_en": "Court + lights", "name_ar": "ملعب مع إنارة", "price": 10, "category": "court_rent"},
        {"key": "water", "name_en": "Water", "name_ar": "مي", "price": 1.5, "category": "water"},
        {"key": "water_cold", "name_en": "Water (cold day)", "name_ar": "مي (يوم بارد)", "price": 1, "category": "water"},
    ],
}

SEED_GROUPS = [
    ("أشبال", "Kids (U-10)", 5, 9, "mixed", "Sun/Tue/Thu", "4:00-5:30"),
    ("ناشئين", "Juniors (U-14)", 10, 13, "M", "Sun/Tue/Thu", "5:30-7:00"),
    ("شباب", "Youth (U-18)", 14, 17, "M", "Sun/Tue/Thu", "7:00-8:30"),
    ("رجال", "Men", 18, 99, "M", "Sun/Tue/Thu", "8:30-10:00"),
    ("سيدات", "Ladies", 14, 99, "F", "Sun/Tue/Thu", "3:00-4:00"),
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
CREATE TABLE IF NOT EXISTS coaches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    salary_type TEXT DEFAULT 'monthly',    -- monthly / session
    salary_amount REAL DEFAULT 0,
    active INTEGER DEFAULT 1,
    join_date TEXT
);
CREATE TABLE IF NOT EXISTS coach_attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coach_id INTEGER NOT NULL REFERENCES coaches(id),
    session_date TEXT NOT NULL,
    UNIQUE(coach_id, session_date)
);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category TEXT DEFAULT 'other',
    amount REAL NOT NULL,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS salary_payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coach_id INTEGER NOT NULL REFERENCES coaches(id),
    month TEXT NOT NULL,                   -- YYYY-MM the salary is for
    amount REAL NOT NULL,
    date TEXT NOT NULL,                    -- day the money was handed over
    method TEXT DEFAULT 'cash'
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    kind TEXT DEFAULT 'other',             -- school / outdoor / indoor / tournament / collab / sponsorship / other
    partner TEXT DEFAULT '',               -- school, sponsor or collab partner name
    location TEXT DEFAULT '',
    date TEXT NOT NULL,
    start_time TEXT DEFAULT '',
    end_time TEXT DEFAULT '',
    amount REAL,                           -- sponsorship / fee in JD (optional)
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS player_freezes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    start_date TEXT NOT NULL,              -- first frozen day
    end_date TEXT                          -- first active day again (NULL = still frozen)
);
"""

# expenses.recurring values
EXP_ONCE, EXP_MONTHLY, EXP_PER_SESSION = 0, 1, 2


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
    # salary Due/Paid tracking starts the month this version first ran: earlier
    # months were settled outside the app and must not show up as owed
    row = con.execute("SELECT data FROM settings WHERE id=1").fetchone()
    data = json.loads(row["data"])
    if "salary_tracking_from" not in data:
        data["salary_tracking_from"] = date.today().strftime("%Y-%m")
        con.execute("UPDATE settings SET data=? WHERE id=1", (json.dumps(data, ensure_ascii=False),))
    con.commit()
    con.close()


def _migrate(con):
    """Add columns introduced after the first release, without touching existing data."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(players)").fetchall()}
    if "added_by" not in cols:
        con.execute("ALTER TABLE players ADD COLUMN added_by TEXT DEFAULT ''")
    acols = {r["name"] for r in con.execute("PRAGMA table_info(attendance)").fetchall()}
    if "trial" not in acols:
        con.execute("ALTER TABLE attendance ADD COLUMN trial INTEGER DEFAULT 0")
    scols = {r["name"] for r in con.execute("PRAGMA table_info(subscriptions)").fetchall()}
    if "paused_days" not in scols:
        con.execute("ALTER TABLE subscriptions ADD COLUMN paused_days INTEGER DEFAULT 0")
    try:
        ecols = {r["name"] for r in con.execute("PRAGMA table_info(expenses)").fetchall()}
        if ecols and "recurring" not in ecols:
            con.execute("ALTER TABLE expenses ADD COLUMN recurring INTEGER DEFAULT 0")
        if ecols and "end_date" not in ecols:
            con.execute("ALTER TABLE expenses ADD COLUMN end_date TEXT")
        if ecols and "qty" not in ecols:
            con.execute("ALTER TABLE expenses ADD COLUMN qty REAL DEFAULT 1")
            con.execute("ALTER TABLE expenses ADD COLUMN unit_price REAL")
    except Exception:
        pass
    # players frozen before freeze periods existed get an open freeze row
    for p in con.execute("SELECT id, frozen_at FROM players WHERE status='frozen' AND frozen_at IS NOT NULL").fetchall():
        has = con.execute("SELECT 1 FROM player_freezes WHERE player_id=? AND end_date IS NULL",
                          (p["id"],)).fetchone()
        if not has:
            con.execute("INSERT INTO player_freezes (player_id, start_date) VALUES (?,?)",
                        (p["id"], p["frozen_at"]))
    # a frozen player marked present must never count as an unpaid session
    con.execute(
        "UPDATE attendance SET unpaid=0 WHERE unpaid=1 AND EXISTS (SELECT 1 FROM player_freezes f "
        "WHERE f.player_id=attendance.player_id AND attendance.session_date >= f.start_date "
        "AND (f.end_date IS NULL OR attendance.session_date < f.end_date))")


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


_WD = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
       "Friday": 4, "Saturday": 5, "Sunday": 6}
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_EPOCH = date(2000, 1, 1)


def _d(v):
    return v if isinstance(v, date) else date.fromisoformat(v)


# ----- training-day schedule (changes over time) -----

def schedule_entries(settings=None):
    """The schedule as [(from_date, {weekday ints})], oldest first. Each entry
    applies from its date until the next entry starts."""
    settings = settings or get_settings()
    out = []
    for e in settings.get("schedule_history") or []:
        try:
            out.append((_d(e["from"]), {_WD[x] for x in e.get("days", []) if x in _WD}))
        except (KeyError, ValueError, TypeError):
            continue
    out.sort(key=lambda x: x[0])
    if not out:
        out = [(_EPOCH, {_WD[x] for x in (settings.get("training_days") or []) if x in _WD})]
    return out


def weekdays_on(entries, d):
    cur = entries[0][1] if entries else set()
    for frm, wds in entries:
        if frm <= d:
            cur = wds
        else:
            break
    return cur


def closed_dates(settings=None):
    settings = settings or get_settings()
    out = set()
    for c in settings.get("closed_days") or []:
        try:
            out.add(_d(c["date"] if isinstance(c, dict) else c))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def training_weekdays(settings=None):
    """Weekday ints (0=Mon) the academy trains on today."""
    return weekdays_on(schedule_entries(settings), date.today())


def days_on(settings, d):
    """Training-day names in force on date d."""
    wds = weekdays_on(schedule_entries(settings), _d(d))
    return [n for n in WEEKDAY_NAMES if _WD[n] in wds]


def set_training_days(settings, days, effective_from):
    """Change the training days from `effective_from` onward. Earlier dates keep
    the schedule they actually had, so past session counts never move."""
    days = [d for d in WEEKDAY_NAMES if d in set(days)]
    hist = list(settings.get("schedule_history") or [])
    if not hist:
        hist = [{"from": _EPOCH.isoformat(), "days": list(settings.get("training_days") or [])}]
    if days_on({**settings, "schedule_history": hist}, effective_from) != days:
        hist = [h for h in hist if h["from"] < effective_from]
        hist.append({"from": effective_from, "days": days})
    settings["schedule_history"] = hist
    settings["training_days"] = days_on(settings, date.today())
    return settings


def is_training_day(d, settings=None):
    settings = settings or get_settings()
    d = _d(d)
    return d.weekday() in weekdays_on(schedule_entries(settings), d) and d not in closed_dates(settings)


def scheduled_session_dates(start_iso, count, wds):
    """The next `count` dates on/after start_iso whose weekday is in wds (fixed schedule)."""
    if not wds or count <= 0:
        return []
    d = _d(start_iso)
    out = []
    for _ in range(count * 12 + 90):
        if d.weekday() in wds:
            out.append(d)
            if len(out) >= count:
                break
        d += timedelta(days=1)
    return out


def session_dates(start, count, settings=None, skip=None):
    """The next `count` real sessions on/after `start`: training days per the
    schedule in force on each date, minus closed days and any date `skip(d)`
    rejects (a player's freeze)."""
    settings = settings or get_settings()
    entries = schedule_entries(settings)
    closed = closed_dates(settings)
    if count <= 0 or not any(w for _, w in entries):
        return []
    d = _d(start)
    out = []
    for _ in range(3660):
        if d.weekday() in weekdays_on(entries, d) and d not in closed and not (skip and skip(d)):
            out.append(d)
            if len(out) >= count:
                break
        d += timedelta(days=1)
    return out


def sessions_between(d1, d2, settings=None):
    """Every training session date in [d1, d2] (inclusive)."""
    settings = settings or get_settings()
    entries = schedule_entries(settings)
    closed = closed_dates(settings)
    d, end, out = _d(d1), _d(d2), []
    while d <= end:
        if d.weekday() in weekdays_on(entries, d) and d not in closed:
            out.append(d)
        d += timedelta(days=1)
    return out


# ----- freezes -----

def freeze_ranges(con, player_id):
    """[(start, end_exclusive_or_None)] for a player, oldest first."""
    rows = con.execute("SELECT start_date, end_date FROM player_freezes WHERE player_id=? ORDER BY start_date",
                       (player_id,)).fetchall()
    return [(_d(r["start_date"]), _d(r["end_date"]) if r["end_date"] else None) for r in rows]


def _freeze_skipper(ranges):
    """skip(d) for session math. An open freeze covers its start up to today;
    future sessions are projected as if the player returns tomorrow."""
    if not ranges:
        return None
    today = date.today()

    def skip(d):
        for s, e in ranges:
            if d >= s and (d < e if e else d <= max(today, s)):
                return True
        return False
    return skip


def frozen_on(con, player_id, d):
    sk = _freeze_skipper(freeze_ranges(con, player_id))
    return bool(sk and sk(_d(d)))


# ----- subscriptions -----

def sub_progress(con, sub, settings=None):
    """Calendar-based progress for a subscription.

    Sessions are the next `sessions_total` training days from start_date, using
    the schedule in force on each date and skipping closed days and the player's
    freeze periods. A session is consumed when its date passes, attended or not.
    Returns {total, used, left, expiry, days_left, active, dates}.
    """
    settings = settings or get_settings()
    total = int(sub["sessions_total"] or 0)
    # legacy: freezes before player_freezes existed shifted the calendar by N days
    paused = int(sub["paused_days"]) if ("paused_days" in sub.keys() and sub["paused_days"]) else 0
    today = date.today()
    sched = session_dates(sub["start_date"], total, settings,
                          _freeze_skipper(freeze_ranges(con, sub["player_id"])))
    if sched:
        expiry_iso = (sched[-1] + timedelta(days=paused)).isoformat()
        cutoff = today - timedelta(days=paused)
        used = max(0, min(total, sum(1 for s in sched if s <= cutoff)))
    else:
        used = max(0, min(total, int(sub["sessions_used"] or 0)))
        expiry_iso = sub["expiry_date"]
    left = total - used
    exp = _d(expiry_iso)
    return {"total": total, "used": used, "left": left, "expiry": expiry_iso,
            "days_left": (exp - today).days, "active": today <= exp,
            "dates": sched}


def get_active_subscription(con, player_id, settings=None):
    """Return the player's active subscription (most recent), keeping the stored
    sessions_used / expiry_date / status in sync with the calendar. Else None."""
    settings = settings or get_settings()
    subs = con.execute(
        "SELECT * FROM subscriptions WHERE player_id=? ORDER BY start_date DESC, id DESC",
        (player_id,)).fetchall()
    today = date.today()
    progs = [(s, sub_progress(con, s, settings)) for s in subs]
    live = [s for s, p in progs if p["active"]]
    # the package running today wins; otherwise the next one waiting to start
    current = [s for s in live if _d(s["start_date"]) <= today]
    found = current[0]["id"] if current else (live[-1]["id"] if live else None)
    dirty = False
    for s, prog in progs:
        if s["id"] == found:
            new_status = "active"
        elif prog["active"]:
            new_status = "active" if _d(s["start_date"]) > today else "finished"
        else:
            new_status = "finished" if prog["used"] >= prog["total"] else "expired"
        if (s["sessions_used"] != prog["used"] or s["expiry_date"] != prog["expiry"] or s["status"] != new_status):
            con.execute("UPDATE subscriptions SET sessions_used=?, expiry_date=?, status=? WHERE id=?",
                        (prog["used"], prog["expiry"], new_status, s["id"]))
            dirty = True
    if dirty:
        con.commit()
    return con.execute("SELECT * FROM subscriptions WHERE id=?", (found,)).fetchone() if found else None


def covered_on(con, player_id, d, settings=None):
    """True if a subscription period (start .. live expiry) covers date d."""
    settings = settings or get_settings()
    d = _d(d)
    for s in con.execute("SELECT * FROM subscriptions WHERE player_id=?", (player_id,)).fetchall():
        if _d(s["start_date"]) <= d <= _d(sub_progress(con, s, settings)["expiry"]):
            return True
    return False


def refresh_unpaid(con, player_id, settings=None):
    """Recompute the unpaid flag on every 'present' mark of a player: unpaid means
    no subscription covered that date, it wasn't the free trial and the player
    wasn't frozen. A late (backdated) renewal therefore clears old flags."""
    settings = settings or get_settings()
    subs = con.execute("SELECT * FROM subscriptions WHERE player_id=?", (player_id,)).fetchall()
    periods = [(_d(s["start_date"]), _d(sub_progress(con, s, settings)["expiry"])) for s in subs]
    skip = _freeze_skipper(freeze_ranges(con, player_id))
    for a in con.execute("SELECT id, session_date, status, unpaid, COALESCE(trial,0) trial "
                         "FROM attendance WHERE player_id=?", (player_id,)).fetchall():
        d = _d(a["session_date"])
        covered = any(s <= d <= e for s, e in periods)
        want = 1 if (a["status"] == "present" and not a["trial"] and not covered
                     and not (skip and skip(d))) else 0
        if want != a["unpaid"]:
            con.execute("UPDATE attendance SET unpaid=? WHERE id=?", (want, a["id"]))
    con.commit()


def next_receipt_no(con):
    year = date.today().year
    prefix = f"DA-{year}-"
    row = con.execute(
        "SELECT receipt_no FROM payments WHERE receipt_no LIKE ? ORDER BY id DESC LIMIT 1", (prefix + "%",)
    ).fetchone()
    n = int(row["receipt_no"].split("-")[-1]) + 1 if row else 1
    return f"{prefix}{n:04d}"


def subscription_expiry(start_date, sessions_total, settings=None):
    """The date the subscription ends = the Nth session from the start date.
    Falls back to start + expiry_days if no training days are configured."""
    settings = settings or get_settings()
    sched = session_dates(start_date, int(sessions_total), settings)
    if sched:
        return sched[-1].isoformat()
    return (_d(start_date) + timedelta(days=int(settings.get("expiry_days", 35)))).isoformat()


def create_subscription(con, player_id, start_date, price=None, sessions_total=None,
                        method="cash", note="", amount=None, pay_date=None):
    """New subscription + payment in one flow. `price` is what the package costs,
    `amount` what was actually handed over now (less = balance owed; 0 = nothing
    paid yet, no payment row). Returns (sub_id, receipt_no or None)."""
    st = get_settings()
    price = float(price if price not in (None, "") else st["monthly_price"])
    sessions_total = int(sessions_total if sessions_total not in (None, "") else st["sessions_per_month"])
    amount = float(amount if amount not in (None, "") else price)
    expiry = subscription_expiry(start_date, sessions_total, st)
    con.execute(
        "UPDATE subscriptions SET status='finished' WHERE player_id=? AND status='active'", (player_id,)
    )
    cur = con.execute(
        "INSERT INTO subscriptions (player_id,start_date,sessions_total,sessions_used,price,expiry_date,status,paused_days) "
        "VALUES (?,?,?,0,?,?,'active',0)",
        (player_id, start_date, sessions_total, price, expiry),
    )
    sub_id = cur.lastrowid
    receipt = None
    if amount > 0:
        receipt = next_receipt_no(con)
        con.execute(
            "INSERT INTO payments (player_id,subscription_id,amount,date,method,note,receipt_no) VALUES (?,?,?,?,?,?,?)",
            (player_id, sub_id, amount, pay_date or today_str(), method, note, receipt),
        )
    con.commit()
    refresh_unpaid(con, player_id, st)
    return sub_id, receipt


def add_payment(con, player_id, amount, pay_date=None, method="cash", note="", sub_id=None):
    """Record money received against a player's balance (attached to their
    latest subscription unless one is given). Returns the receipt number."""
    if sub_id is None:
        row = con.execute("SELECT id FROM subscriptions WHERE player_id=? ORDER BY start_date DESC, id DESC LIMIT 1",
                          (player_id,)).fetchone()
        sub_id = row["id"] if row else None
    receipt = next_receipt_no(con)
    con.execute(
        "INSERT INTO payments (player_id,subscription_id,amount,date,method,note,receipt_no) VALUES (?,?,?,?,?,?,?)",
        (player_id, sub_id, float(amount), pay_date or today_str(), method, note, receipt))
    con.commit()
    return receipt


def player_balance(con, player_id):
    """What the player still owes: package prices minus money received (>0 = owes)."""
    owed = con.execute("SELECT COALESCE(SUM(price),0) s FROM subscriptions WHERE player_id=?",
                       (player_id,)).fetchone()["s"]
    paid = con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE player_id=?",
                       (player_id,)).fetchone()["s"]
    return round(owed - paid, 2)


def update_subscription(con, sub_id, start_date=None, sessions_total=None, sessions_used=None,
                        price=None, expiry_date=None, status=None):
    """Edit a subscription (fix a wrong one). Expiry is always derived from the
    calendar, so only start/total/price matter."""
    sub = con.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        return
    st = get_settings()
    start_date = start_date or sub["start_date"]
    sessions_total = int(sessions_total if sessions_total is not None else sub["sessions_total"])
    price = float(price if price is not None else sub["price"])
    expiry = expiry_date or subscription_expiry(start_date, sessions_total, st)
    con.execute(
        "UPDATE subscriptions SET start_date=?, sessions_total=?, price=?, expiry_date=? WHERE id=?",
        (start_date, sessions_total, price, expiry, sub_id))
    con.commit()
    get_active_subscription(con, sub["player_id"], st)
    refresh_unpaid(con, sub["player_id"], st)


def delete_subscription(con, sub_id, drop_payments=True):
    """Delete a subscription (e.g. added by mistake). Optionally remove its payments
    so revenue isn't inflated by the false entry."""
    sub = con.execute("SELECT player_id FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    if drop_payments:
        con.execute("DELETE FROM payments WHERE subscription_id=?", (sub_id,))
    else:
        con.execute("UPDATE payments SET subscription_id=NULL WHERE subscription_id=?", (sub_id,))
    con.execute("DELETE FROM subscriptions WHERE id=?", (sub_id,))
    con.commit()
    if sub:
        refresh_unpaid(con, sub["player_id"])


def delete_player(con, player_id):
    """Permanently remove a player and everything linked to them."""
    con.execute("DELETE FROM attendance WHERE player_id=?", (player_id,))
    con.execute("DELETE FROM payments WHERE player_id=?", (player_id,))
    con.execute("DELETE FROM subscriptions WHERE player_id=?", (player_id,))
    con.execute("DELETE FROM player_freezes WHERE player_id=?", (player_id,))
    con.execute("DELETE FROM players WHERE id=?", (player_id,))
    con.commit()


def mark_attendance(con, player_id, session_date, group_id, status, marked_by=""):
    """Set/update attendance. Sessions are consumed by the calendar, not by
    attendance; this only records the mark and flags trial / unpaid."""
    st = get_settings()
    existing = con.execute(
        "SELECT * FROM attendance WHERE player_id=? AND session_date=?", (player_id, session_date)
    ).fetchone()

    # give the free trial back if an existing trial mark is being cleared/changed
    if existing and ("trial" in existing.keys()) and existing["trial"]:
        con.execute("UPDATE players SET trial_used=0 WHERE id=?", (player_id,))

    if status is None or status == "none":
        if existing:
            con.execute("DELETE FROM attendance WHERE id=?", (existing["id"],))
        con.commit()
        return {"status": "none", "unpaid": False, "trial": False}

    unpaid = 0
    trial = 0
    player = con.execute("SELECT status, trial_used FROM players WHERE id=?", (player_id,)).fetchone()
    frozen = (player and player["status"] == "frozen") or frozen_on(con, player_id, session_date)
    if status == "present" and not frozen and not covered_on(con, player_id, session_date, st):
        # free trial once for a brand-new player (no subscription ever),
        # otherwise the session is unpaid until a subscription covers it
        ever_subbed = con.execute(
            "SELECT 1 FROM subscriptions WHERE player_id=? LIMIT 1", (player_id,)).fetchone()
        if player and not player["trial_used"] and not ever_subbed:
            con.execute("UPDATE players SET trial_used=1 WHERE id=?", (player_id,))
            trial = 1
        else:
            unpaid = 1

    now = datetime.now().isoformat(timespec="seconds")
    if existing:
        con.execute(
            "UPDATE attendance SET status=?, group_id=?, marked_by=?, marked_at=?, deducted=0, unpaid=?, trial=? WHERE id=?",
            (status, group_id, marked_by, now, unpaid, trial, existing["id"]),
        )
    else:
        con.execute(
            "INSERT INTO attendance (player_id,session_date,group_id,status,marked_by,marked_at,deducted,unpaid,trial) "
            "VALUES (?,?,?,?,?,?,0,?,?)",
            (player_id, session_date, group_id, status, marked_by, now, unpaid, trial),
        )
    con.commit()
    return {"status": status, "unpaid": bool(unpaid), "trial": bool(trial)}


def freeze_player(con, player_id, on=None):
    """Freeze from date `on` (default today; may be backdated). The session
    calendar stops for the whole freeze, so no sessions are lost."""
    on = min(_d(on or today_str()), date.today()).isoformat()
    if not con.execute("SELECT 1 FROM player_freezes WHERE player_id=? AND end_date IS NULL",
                       (player_id,)).fetchone():
        con.execute("INSERT INTO player_freezes (player_id, start_date) VALUES (?,?)", (player_id, on))
    con.execute("UPDATE players SET status='frozen', frozen_at=? WHERE id=?", (on, player_id))
    con.commit()
    refresh_unpaid(con, player_id)


def unfreeze_player(con, player_id, on=None):
    """Back to active from date `on` (default today; may be backdated)."""
    on = min(_d(on or today_str()), date.today())
    row = con.execute("SELECT * FROM player_freezes WHERE player_id=? AND end_date IS NULL",
                      (player_id,)).fetchone()
    if row:
        if on <= _d(row["start_date"]):
            con.execute("DELETE FROM player_freezes WHERE id=?", (row["id"],))  # cancelled same day
        else:
            con.execute("UPDATE player_freezes SET end_date=? WHERE id=?", (on.isoformat(), row["id"]))
    con.execute("UPDATE players SET status='active', frozen_at=NULL WHERE id=?", (player_id,))
    con.commit()
    refresh_unpaid(con, player_id)


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


def attendance_rate(con, player_id):
    """Present / (present + absent) over a player's whole history. Excused is ignored.
    Returns {rate, present, absent, excused, total, streak}."""
    rows = con.execute(
        "SELECT status, session_date FROM attendance WHERE player_id=? ORDER BY session_date DESC",
        (player_id,)).fetchall()
    present = sum(1 for r in rows if r["status"] == "present")
    absent = sum(1 for r in rows if r["status"] == "absent")
    excused = sum(1 for r in rows if r["status"] == "excused")
    counted = present + absent
    rate = round(present * 100 / counted) if counted else None
    # current streak: consecutive most-recent presents (excused doesn't break it)
    streak = 0
    for r in rows:
        if r["status"] == "present":
            streak += 1
        elif r["status"] == "excused":
            continue
        else:
            break
    return {"rate": rate, "present": present, "absent": absent, "excused": excused,
            "total": present + absent + excused, "streak": streak}


def month_attendance_rate(con, month=None):
    """Overall present/(present+absent) for a YYYY-MM month (default current)."""
    month = month or date.today().strftime("%Y-%m")
    row = con.execute(
        "SELECT SUM(status='present') p, SUM(status='absent') a FROM attendance "
        "WHERE session_date LIKE ?", (month + "%",)).fetchone()
    p, a = (row["p"] or 0), (row["a"] or 0)
    return round(p * 100 / (p + a)) if (p + a) else None


# ---------- coaches & finance ----------

def month_bounds(month):
    first = date(int(month[:4]), int(month[5:7]), 1)
    nxt = date(first.year + (first.month // 12), first.month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def month_sessions(month=None, settings=None, upto_today=True):
    """Training sessions in a month (by default only those already held)."""
    month = month or date.today().strftime("%Y-%m")
    first, last = month_bounds(month)
    if upto_today:
        last = min(last, date.today())
    return len(sessions_between(first, last, settings)) if last >= first else 0


def coach_month_sessions(con, coach_id, month=None):
    month = month or date.today().strftime("%Y-%m")
    return con.execute(
        "SELECT COUNT(*) c FROM coach_attendance WHERE coach_id=? AND session_date LIKE ?",
        (coach_id, month + "%")).fetchone()["c"]


def coach_month_cost(con, coach, month=None):
    """What an active coach costs this month: monthly = fixed; session = sessions x rate.
    Nothing is charged for months before the coach joined."""
    month = month or date.today().strftime("%Y-%m")
    if not coach["active"]:
        return 0
    if coach["join_date"] and month < coach["join_date"][:7]:
        return 0
    if coach["salary_type"] == "session":
        return coach_month_sessions(con, coach["id"], month) * (coach["salary_amount"] or 0)
    return coach["salary_amount"] or 0


def _has_recurring(con):
    try:
        return "recurring" in {r["name"] for r in con.execute("PRAGMA table_info(expenses)").fetchall()}
    except Exception:
        return False


def month_expense_rows(con, month=None, settings=None, projected=False):
    """Effective expenses for a month, as dicts with an attributed `amount`:
    - one-off: dated in the month
    - monthly: every month from its start until it is stopped (end_date)
    - per session (court rent, water): unit price x sessions held in the month
      from its start date (projected=True counts the whole month's schedule).
    Each row also carries `unit`, `kind` and `sessions`."""
    month = month or date.today().strftime("%Y-%m")
    if not _has_recurring(con):
        return [dict(r, unit=r["amount"], kind=EXP_ONCE, sessions=0)
                for r in con.execute("SELECT * FROM expenses WHERE date LIKE ?", (month + "%",)).fetchall()]
    settings = settings or get_settings()
    first, last = month_bounds(month)
    out = []
    for r in con.execute("SELECT * FROM expenses ORDER BY date").fetchall():
        kind = int(r["recurring"] or 0)
        start = r["date"] or ""
        end = r["end_date"] if "end_date" in r.keys() else None
        row = dict(r, unit=r["amount"], kind=kind, sessions=0)
        if kind == EXP_ONCE:
            if start.startswith(month):
                out.append(row)
        elif kind == EXP_MONTHLY:
            if start[:7] <= month and (not end or end[:7] >= month):
                out.append(row)
        elif kind == EXP_PER_SESSION:
            if start[:7] > month or (end and end[:7] < month):
                continue
            lo = max(first, _d(start))
            hi = last if projected else min(last, date.today())
            if end:
                hi = min(hi, _d(end))
            n = len(sessions_between(lo, hi, settings)) if hi >= lo else 0
            row.update(amount=round((r["amount"] or 0) * n, 2), sessions=n)
            out.append(row)
    return out


def month_expense_total(con, month=None, settings=None, projected=False):
    return round(sum((r["amount"] or 0) for r in month_expense_rows(con, month, settings, projected)), 2)


def expenses_by_category(con, month=None, settings=None):
    """Where the money went this month: [{category, total, share}] biggest first."""
    agg = {}
    for r in month_expense_rows(con, month, settings):
        cat = r["category"] or "other"
        agg[cat] = agg.get(cat, 0) + (r["amount"] or 0)
    total = sum(agg.values())
    out = [{"category": c, "total": round(v, 2), "share": round(v * 100 / total) if total else 0}
           for c, v in agg.items() if v]
    return sorted(out, key=lambda x: x["total"], reverse=True)


def month_salaries(con, month):
    return sum(coach_month_cost(con, c, month) for c in con.execute("SELECT * FROM coaches WHERE active=1").fetchall())


def salary_paid(con, coach_id, month):
    return round(con.execute("SELECT COALESCE(SUM(amount),0) s FROM salary_payouts WHERE coach_id=? AND month=?",
                             (coach_id, month)).fetchone()["s"], 2)


def salary_status(con, coach, month):
    """{due, paid, left, state} for one coach and month. state: paid / partial /
    due / none (nothing earned, e.g. a per-session coach who didn't work)."""
    due = round(coach_month_cost(con, coach, month), 2)
    paid = salary_paid(con, coach["id"], month)
    left = round(max(due - paid, 0), 2)
    state = "none" if due <= 0 and paid <= 0 else ("paid" if left <= 0 else ("partial" if paid > 0 else "due"))
    return {"due": due, "paid": paid, "left": left, "state": state}


def salaries_unpaid(con, upto_month=None, settings=None):
    """Salary still owed to coaches for every tracked month up to upto_month."""
    upto_month = upto_month or date.today().strftime("%Y-%m")
    settings = settings or get_settings()
    tracked = settings.get("salary_tracking_from") or upto_month
    total, rows = 0.0, []
    for c in con.execute("SELECT * FROM coaches WHERE active=1").fetchall():
        start = max((c["join_date"] or upto_month)[:7], tracked)
        for m in _months_from(min(start, upto_month), upto_month):
            st = salary_status(con, c, m)
            if st["left"] > 0:
                total += st["left"]
                rows.append({"coach_id": c["id"], "name": c["name"], "month": m, "left": st["left"]})
    return {"total": round(total, 2), "rows": rows}


def log_session_costs(con, on, quantities, settings=None, note=""):
    """Record one session's costs from presets: {preset_key: qty}. Each line is
    stored as an expense with qty x unit price. Returns the total logged."""
    settings = settings or get_settings()
    presets = {p["key"]: p for p in settings.get("cost_presets") or []}
    total = 0.0
    for key, qty in quantities.items():
        p = presets.get(key)
        try:
            qty = float(qty or 0)
        except (TypeError, ValueError):
            qty = 0
        if not p or qty <= 0:
            continue
        price = float(p.get("price") or 0)
        amount = round(qty * price, 2)
        con.execute("INSERT INTO expenses (date, category, amount, note, recurring, qty, unit_price) "
                    "VALUES (?,?,?,?,0,?,?)",
                    (on, p.get("category") or "other", amount,
                     (note or p.get("name_en") or key).strip(), qty, price))
        total += amount
    con.commit()
    return round(total, 2)


def session_costs_on(con, on):
    """Expense lines logged for a session date (court, water...)."""
    return con.execute("SELECT * FROM expenses WHERE date=? AND COALESCE(recurring,0)=0 "
                       "AND category IN ('court_rent','water') ORDER BY id", (on,)).fetchall()


def _session_values(con, settings):
    """Every subscription's session dates with the value of one session
    (price / sessions). This is how money is *earned*, as opposed to received."""
    out = []
    for s in con.execute("SELECT * FROM subscriptions").fetchall():
        total = int(s["sessions_total"] or 0)
        if total <= 0:
            continue
        dates = sub_progress(con, s, settings)["dates"]
        out.append(((s["price"] or 0) / total, dates))
    return out


def earned_between(con, d1, d2, settings=None, _values=None):
    """Revenue earned by sessions that took place in [d1, d2] (not after today)."""
    settings = settings or get_settings()
    values = _values if _values is not None else _session_values(con, settings)
    d1, d2 = _d(d1), min(_d(d2), date.today())
    return round(sum(v * sum(1 for x in dates if d1 <= x <= d2) for v, dates in values), 2)


def unpaid_sessions(con):
    """Present marks not covered by any subscription (excludes trials and frozen)."""
    return con.execute("SELECT COUNT(*) c FROM attendance a JOIN players p ON p.id=a.player_id "
                       "WHERE a.unpaid=1 AND p.status!='left'").fetchone()["c"]


def money_owed(con, settings=None):
    """Money owed to the academy: outstanding package balances + unpaid sessions
    valued at the standard per-session price. Returns dict with per-player rows."""
    settings = settings or get_settings()
    per_session = float(settings.get("monthly_price") or 0) / max(1, int(settings.get("sessions_per_month") or 12))
    rows = []
    for p in con.execute("SELECT id, full_name, guardian_phone, phone FROM players WHERE status!='left'").fetchall():
        bal = player_balance(con, p["id"])
        unpaid = con.execute("SELECT COUNT(*) c FROM attendance WHERE player_id=? AND unpaid=1",
                             (p["id"],)).fetchone()["c"]
        if bal > 0 or unpaid:
            rows.append({"id": p["id"], "name": p["full_name"], "phone": p["guardian_phone"] or p["phone"],
                         "balance": max(bal, 0), "unpaid": unpaid,
                         "total": round(max(bal, 0) + unpaid * per_session, 2)})
    rows.sort(key=lambda r: r["total"], reverse=True)
    return {"rows": rows, "balances": round(sum(r["balance"] for r in rows), 2),
            "unpaid_value": round(sum(r["unpaid"] for r in rows) * per_session, 2),
            "total": round(sum(r["total"] for r in rows), 2), "per_session": round(per_session, 2)}


def finance(con, month=None, settings=None, _values=None):
    """Money picture for a month.
    revenue  = cash actually received (payments dated in the month)
    earned   = value of sessions delivered in the month (smooths lumpy payments)
    expenses = coach salaries + other expenses (per-session ones as held so far)
    profit   = revenue - expenses (cash view); earned_profit = earned - expenses."""
    month = month or date.today().strftime("%Y-%m")
    settings = settings or get_settings()
    first, last = month_bounds(month)
    revenue = con.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date LIKE ?", (month + "%",)).fetchone()["s"]
    salaries = month_salaries(con, month)
    other = month_expense_total(con, month, settings)
    expenses = round(salaries + other, 2)
    profit = round(revenue - expenses, 2)
    earned = earned_between(con, first, last, settings, _values)
    margin = round(profit * 100 / revenue) if revenue else None
    return {"revenue": round(revenue, 2), "earned": earned, "salaries": round(salaries, 2), "other": other,
            "expenses": expenses, "profit": profit, "earned_profit": round(earned - expenses, 2),
            "margin": margin}


def _months_from(first_month, last_month):
    out, d = [], date.fromisoformat(first_month + "-01")
    end = date.fromisoformat(last_month + "-01")
    while d <= end:
        out.append(d.strftime("%Y-%m"))
        d = (d + timedelta(days=32)).replace(day=1)
    return out


def cash_balance(con, settings=None):
    """Cash the academy should be holding right now: opening balance + every
    payment received - every expense to date - salaries actually paid out."""
    settings = settings or get_settings()
    this_month = date.today().strftime("%Y-%m")
    starts = []
    for sql in ("SELECT MIN(date) m FROM payments", "SELECT MIN(date) m FROM expenses",
                "SELECT MIN(join_date) m FROM coaches WHERE active=1"):
        v = con.execute(sql).fetchone()["m"]
        if v:
            starts.append(v[:7])
    paid_in = con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date<=?",
                          (today_str(),)).fetchone()["s"]
    # salaries count when actually handed over, so the balance is real cash
    paid_out = con.execute("SELECT COALESCE(SUM(amount),0) s FROM salary_payouts WHERE date<=?",
                           (today_str(),)).fetchone()["s"]
    tracked = settings.get("salary_tracking_from") or this_month
    out = 0.0
    for m in _months_from(min(starts), this_month) if starts else []:
        out += month_expense_total(con, m, settings)
        if m < tracked:
            out += month_salaries(con, m)   # settled before payouts were tracked
    return round(float(settings.get("opening_balance") or 0) + paid_in - paid_out - out, 2)


def month_projection(con, settings=None):
    """Where this month should land: cash received so far + renewals falling due
    before month end, minus the full month's costs (per-session costs for every
    scheduled session). Lets you see a slow week coming."""
    settings = settings or get_settings()
    today = date.today()
    month = today.strftime("%Y-%m")
    first, last = month_bounds(month)
    received = con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date LIKE ?",
                           (month + "%",)).fetchone()["s"]
    due = []
    for p in con.execute("SELECT id, full_name FROM players WHERE status='active'").fetchall():
        sub = get_active_subscription(con, p["id"], settings)
        if sub and today <= _d(sub["expiry_date"]) <= last:
            due.append({"id": p["id"], "name": p["full_name"], "date": sub["expiry_date"], "amount": sub["price"],
                        "used": sub["sessions_used"], "total": sub["sessions_total"]})
    expected_in = round(sum(d["amount"] or 0 for d in due), 2)
    costs = round(month_salaries(con, month) + month_expense_total(con, month, settings, projected=True), 2)
    due.sort(key=lambda d: d["date"])
    return {"received": round(received, 2), "expected_in": expected_in, "costs": costs,
            "landing": round(received + expected_in - costs, 2), "due": due}


def weekly_cash(con, weeks=8, settings=None):
    """Last N weeks (Sat-Fri, Jordan work week): cash received vs revenue earned
    by sessions held. Cash jumps around; earned stays steady."""
    settings = settings or get_settings()
    values = _session_values(con, settings)
    today = date.today()
    start = today - timedelta(days=(today.weekday() - 5) % 7)   # last Saturday
    out = []
    for i in range(weeks - 1, -1, -1):
        w0 = start - timedelta(days=7 * i)
        w1 = w0 + timedelta(days=6)
        cash = con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date BETWEEN ? AND ?",
                           (w0.isoformat(), w1.isoformat())).fetchone()["s"]
        out.append({"d": w0.strftime("%d/%m"), "cash": round(cash, 2),
                    "earned": earned_between(con, w0, w1, settings, values)})
    return out


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
