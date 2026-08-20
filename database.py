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
    # subscription bundles the admin can pick at renewal
    "bundles": [
        {"name_en": "Monthly", "name_ar": "شهري", "sessions": 12, "price": 20},
        {"name_en": "8 sessions", "name_ar": "8 حصص", "sessions": 8, "price": 15},
        {"name_en": "Single", "name_ar": "حصة", "sessions": 1, "price": 3},
    ],
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
    except Exception:
        pass


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


def training_weekdays(settings=None):
    settings = settings or get_settings()
    return {_WD[d] for d in (settings.get("training_days") or []) if d in _WD}


def scheduled_session_dates(start_iso, count, wds):
    """The next `count` training-day dates on/after start_iso (as date objects)."""
    if not wds or count <= 0:
        return []
    d = date.fromisoformat(start_iso)
    out = []
    for _ in range(count * 12 + 90):          # generous safety bound
        if d.weekday() in wds:
            out.append(d)
            if len(out) >= count:
                break
        d += timedelta(days=1)
    return out


def sub_progress(con, sub, settings=None):
    """Calendar-based progress for a subscription.

    Sessions are the next `sessions_total` training days (Sun/Tue/Thu by default)
    starting from start_date. One session is consumed for every such day that has
    passed — whether or not the player attended. Freezing pauses the count via
    subscriptions.paused_days. Returns {total, used, left, expiry, days_left, active}.
    """
    settings = settings or get_settings()
    total = int(sub["sessions_total"] or 0)
    paused = int(sub["paused_days"]) if ("paused_days" in sub.keys() and sub["paused_days"]) else 0
    player = con.execute("SELECT frozen_at FROM players WHERE id=?", (sub["player_id"],)).fetchone()
    frozen_at = player["frozen_at"] if player else None
    wds = training_weekdays(settings)

    if wds:
        sched = scheduled_session_dates(sub["start_date"], total, wds)
        base_expiry = sched[-1] if sched else date.fromisoformat(sub["expiry_date"])
        expiry_iso = (base_expiry + timedelta(days=paused)).isoformat()
        # count scheduled sessions that have already occurred (pause rewinds "today")
        cutoff = (date.fromisoformat(frozen_at) if frozen_at else date.today()) - timedelta(days=paused)
        used = max(0, min(total, sum(1 for s in sched if s <= cutoff)))
    else:
        # no training days configured -> fall back to the stored counter + date expiry
        used = max(0, min(total, int(sub["sessions_used"] or 0)))
        expiry_iso = sub["expiry_date"]

    left = total - used
    days_left = (date.fromisoformat(expiry_iso) - date.today()).days
    active = date.today() <= date.fromisoformat(expiry_iso)
    return {"total": total, "used": used, "left": left, "expiry": expiry_iso,
            "days_left": days_left, "active": active}


def get_active_subscription(con, player_id):
    """Return the player's active subscription (most recent), keeping the stored
    sessions_used / expiry_date / status in sync with the calendar. Else None."""
    settings = get_settings()
    subs = con.execute(
        "SELECT * FROM subscriptions WHERE player_id=? ORDER BY start_date DESC, id DESC",
        (player_id,)).fetchall()
    for s in subs:
        prog = sub_progress(con, s, settings)
        new_status = "active" if prog["active"] else ("finished" if prog["used"] >= prog["total"] else "expired")
        # keep the row's stored values fresh for lists, receipts and exports
        if (s["sessions_used"] != prog["used"] or s["expiry_date"] != prog["expiry"]
                or (s["status"] != new_status and s["status"] != "frozen")):
            con.execute("UPDATE subscriptions SET sessions_used=?, expiry_date=?, status=? WHERE id=?",
                        (prog["used"], prog["expiry"], new_status, s["id"]))
            con.commit()
        if prog["active"]:
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


def subscription_expiry(start_date, sessions_total, settings=None):
    """The date the subscription ends = the Nth training day from the start date.
    Falls back to start + expiry_days if no training days are configured."""
    settings = settings or get_settings()
    wds = training_weekdays(settings)
    if wds:
        sched = scheduled_session_dates(start_date, int(sessions_total), wds)
        if sched:
            return sched[-1].isoformat()
    return (date.fromisoformat(start_date) + timedelta(days=int(settings.get("expiry_days", 35)))).isoformat()


def create_subscription(con, player_id, start_date, price=None, sessions_total=None,
                        method="cash", note="", amount=None):
    """New subscription + payment in one flow. Returns (sub_id, receipt_no)."""
    st = get_settings()
    price = float(price if price is not None else st["monthly_price"])
    sessions_total = int(sessions_total if sessions_total is not None else st["sessions_per_month"])
    expiry = subscription_expiry(start_date, sessions_total, st)
    # close any lingering active sub (one active sub max)
    con.execute(
        "UPDATE subscriptions SET status='finished' WHERE player_id=? AND status='active'", (player_id,)
    )
    cur = con.execute(
        "INSERT INTO subscriptions (player_id,start_date,sessions_total,sessions_used,price,expiry_date,status,paused_days) "
        "VALUES (?,?,?,0,?,?,'active',0)",
        (player_id, start_date, sessions_total, price, expiry),
    )
    sub_id = cur.lastrowid
    receipt = next_receipt_no(con)
    con.execute(
        "INSERT INTO payments (player_id,subscription_id,amount,date,method,note,receipt_no) VALUES (?,?,?,?,?,?,?)",
        (player_id, sub_id, float(amount if amount is not None else price), today_str(), method, note, receipt),
    )
    return sub_id, receipt


def update_subscription(con, sub_id, start_date=None, sessions_total=None, sessions_used=None,
                        price=None, expiry_date=None, status=None):
    """Edit a subscription (fix a wrong one). If start_date changes and no explicit
    expiry is given, recompute expiry = start + expiry_days."""
    sub = con.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        return
    st = get_settings()
    start_date = start_date or sub["start_date"]
    sessions_total = int(sessions_total if sessions_total is not None else sub["sessions_total"])
    sessions_used = int(sessions_used if sessions_used is not None else sub["sessions_used"])
    price = float(price if price is not None else sub["price"])
    if expiry_date:
        expiry = expiry_date
    elif start_date != sub["start_date"] or sessions_total != sub["sessions_total"]:
        expiry = subscription_expiry(start_date, sessions_total, st)
    else:
        expiry = sub["expiry_date"]
    status = status or sub["status"]
    # if only one active allowed and we're activating this one, finish the others
    if status == "active":
        con.execute("UPDATE subscriptions SET status='finished' WHERE player_id=? AND id!=? AND status='active'",
                    (sub["player_id"], sub_id))
    con.execute(
        "UPDATE subscriptions SET start_date=?, sessions_total=?, sessions_used=?, price=?, expiry_date=?, status=? WHERE id=?",
        (start_date, sessions_total, sessions_used, price, expiry, status, sub_id))
    con.commit()


def delete_subscription(con, sub_id, drop_payments=True):
    """Delete a subscription (e.g. added by mistake). Optionally remove its payments
    so revenue isn't inflated by the false entry."""
    if drop_payments:
        con.execute("DELETE FROM payments WHERE subscription_id=?", (sub_id,))
    else:
        con.execute("UPDATE payments SET subscription_id=NULL WHERE subscription_id=?", (sub_id,))
    con.execute("DELETE FROM subscriptions WHERE id=?", (sub_id,))
    con.commit()


def delete_player(con, player_id):
    """Permanently remove a player and everything linked to them."""
    con.execute("DELETE FROM attendance WHERE player_id=?", (player_id,))
    con.execute("DELETE FROM payments WHERE player_id=?", (player_id,))
    con.execute("DELETE FROM subscriptions WHERE player_id=?", (player_id,))
    con.execute("DELETE FROM players WHERE id=?", (player_id,))
    con.commit()


def mark_attendance(con, player_id, session_date, group_id, status, marked_by=""):
    """Set/update attendance and manage session deduction. Returns dict summary."""
    st = get_settings()
    existing = con.execute(
        "SELECT * FROM attendance WHERE player_id=? AND session_date=?", (player_id, session_date)
    ).fetchone()

    # sessions are consumed by the calendar (Sun/Tue/Thu), NOT by attendance, so
    # marking present/absent no longer adds or removes sessions. We only give the
    # free trial back if an existing trial mark is being cleared/changed.
    if existing and ("trial" in existing.keys()) and existing["trial"]:
        con.execute("UPDATE players SET trial_used=0 WHERE id=?", (player_id,))

    if status is None or status == "none":
        # clear the mark entirely
        if existing:
            con.execute("DELETE FROM attendance WHERE id=?", (existing["id"],))
        con.commit()
        return {"status": "none", "unpaid": False, "trial": False}

    unpaid = 0
    trial = 0
    if status == "present":
        sub = get_active_subscription(con, player_id)
        if not sub:
            # present with no active subscription: free trial once for a brand-new
            # player (no subscription ever), otherwise flag the session as unpaid
            player = con.execute("SELECT trial_used FROM players WHERE id=?", (player_id,)).fetchone()
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


def freeze_player(con, player_id):
    con.execute("UPDATE players SET status='frozen', frozen_at=? WHERE id=?", (today_str(), player_id))
    con.commit()


def unfreeze_player(con, player_id):
    p = con.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
    if p and p["frozen_at"]:
        days = (date.today() - date.fromisoformat(p["frozen_at"])).days
        if days > 0:
            # the freeze paused the calendar clock — bank the days so the remaining
            # sessions slide forward by exactly the frozen duration
            sub = con.execute(
                "SELECT * FROM subscriptions WHERE player_id=? ORDER BY start_date DESC, id DESC LIMIT 1",
                (player_id,)).fetchone()
            if sub:
                con.execute("UPDATE subscriptions SET paused_days = COALESCE(paused_days,0) + ? WHERE id=?",
                            (days, sub["id"]))
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

def coach_month_sessions(con, coach_id, month=None):
    month = month or date.today().strftime("%Y-%m")
    return con.execute(
        "SELECT COUNT(*) c FROM coach_attendance WHERE coach_id=? AND session_date LIKE ?",
        (coach_id, month + "%")).fetchone()["c"]


def coach_month_cost(con, coach, month=None):
    """What an active coach costs this month: monthly = fixed; session = sessions × rate."""
    if not coach["active"]:
        return 0
    if coach["salary_type"] == "session":
        return coach_month_sessions(con, coach["id"], month) * (coach["salary_amount"] or 0)
    return coach["salary_amount"] or 0


def _has_recurring(con):
    try:
        return "recurring" in {r["name"] for r in con.execute("PRAGMA table_info(expenses)").fetchall()}
    except Exception:
        return False


def month_expense_rows(con, month=None):
    """Effective expenses for a month: one-off entries dated in the month PLUS every
    recurring (monthly) expense whose start month is on or before it. Recurring rows
    are returned with `recurring=1` and their amount attributed to this month."""
    month = month or date.today().strftime("%Y-%m")
    if _has_recurring(con):
        oneoff = con.execute(
            "SELECT * FROM expenses WHERE COALESCE(recurring,0)=0 AND date LIKE ?", (month + "%",)).fetchall()
        recur = con.execute(
            "SELECT * FROM expenses WHERE recurring=1 AND substr(date,1,7) <= ?", (month,)).fetchall()
        return list(oneoff) + list(recur)
    return con.execute("SELECT * FROM expenses WHERE date LIKE ?", (month + "%",)).fetchall()


def month_expense_total(con, month=None):
    return sum((r["amount"] or 0) for r in month_expense_rows(con, month))


def expenses_by_category(con, month=None):
    """Where the money went this month: [{category, total, share}] biggest first."""
    month = month or date.today().strftime("%Y-%m")
    agg = {}
    for r in month_expense_rows(con, month):
        cat = (r["category"] or "other") if r["category"] else "other"
        agg[cat] = agg.get(cat, 0) + (r["amount"] or 0)
    total = sum(agg.values())
    out = [{"category": c, "total": v, "share": round(v * 100 / total) if total else 0}
           for c, v in agg.items()]
    return sorted(out, key=lambda x: x["total"], reverse=True)


def finance(con, month=None):
    """Revenue, expenses (coach salaries + other), profit, gross margin for a month."""
    month = month or date.today().strftime("%Y-%m")
    revenue = con.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date LIKE ?", (month + "%",)).fetchone()["s"]
    salaries = 0
    for c in con.execute("SELECT * FROM coaches WHERE active=1").fetchall():
        salaries += coach_month_cost(con, c, month)
    other = month_expense_total(con, month)
    expenses = salaries + other
    profit = revenue - expenses
    margin = round(profit * 100 / revenue) if revenue else None
    return {"revenue": revenue, "salaries": salaries, "other": other,
            "expenses": expenses, "profit": profit, "margin": margin}


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
