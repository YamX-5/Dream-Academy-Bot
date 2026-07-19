# -*- coding: utf-8 -*-
"""Dream Academy Manager — Flask app.

Runs locally on the laptop; coaches reach it from anywhere through a
Cloudflare quick tunnel (started automatically if cloudflared.exe is present).
"""
import io
import json
import os
import re
import subprocess
import threading
import urllib.parse
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

import database as db
import excel_io
import assistant as ai
from i18n import translate

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")

# On Linux hosts (e.g. PythonAnywhere) pin the clock to Jordan time so
# "today" and training-day defaults match the academy, not UTC.
if os.name != "nt":
    os.environ.setdefault("TZ", "Asia/Amman")
    import time as _time
    if hasattr(_time, "tzset"):
        _time.tzset()

app = Flask(__name__)
app.secret_key = "dream-academy-local-secret-key-2026"
app.json.ensure_ascii = False

# bump this string whenever the UI changes so you can confirm a fresh load
BUILD = "v11 · 2026-07-19"


@app.after_request
def _no_cache(resp):
    """Never let the browser serve a stale page — this is why UI changes
    sometimes 'don't show up' after a deploy."""
    ct = resp.headers.get("Content-Type", "")
    if ct.startswith("text/html"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


PUBLIC_URL = {"url": None}  # filled by the cloudflared thread
_last_backup_check = {"date": None}

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_AR = {"Sunday": "الأحد", "Monday": "الاثنين", "Tuesday": "الثلاثاء", "Wednesday": "الأربعاء",
          "Thursday": "الخميس", "Friday": "الجمعة", "Saturday": "السبت"}


# ---------------- auth ----------------

def is_local_request():
    """True only for the laptop itself. Tunnel traffic arrives from 127.0.0.1 too,
    so anything with Cloudflare headers or a non-local Host is treated as remote."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return False
    if request.headers.get("Cf-Connecting-Ip") or request.headers.get("Cf-Ray"):
        return False
    host = (request.host or "").split(":")[0]
    return host in ("127.0.0.1", "localhost", "::1")


def current_role():
    if is_local_request():
        return "admin"
    return session.get("role")


def require_role(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            role = current_role()
            if role is None:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "auth"}), 401
                return redirect(url_for("login", next=request.path))
            if roles and role not in roles:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "forbidden"}), 403
                return redirect(url_for("attendance_page"))
            return fn(*a, **kw)
        return wrapper
    return deco


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pin = (request.form.get("pin") or "").strip()
        st = db.get_settings()
        if pin == str(st.get("admin_pin")):
            session["role"] = "admin"
            session.permanent = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        if pin == str(st.get("coach_pin")):
            session["role"] = "coach"
            session.permanent = True
            return redirect(url_for("attendance_page"))
        error = translate(current_lang(), "wrong_pin")
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.before_request
def daily_backup_hook():
    t = date.today().isoformat()
    if _last_backup_check["date"] != t:
        _last_backup_check["date"] = t
        db.backup_db()
        con = db.get_db()
        try:
            excel_io.weekly_auto_export(con, EXPORTS_DIR)
        finally:
            con.close()


def current_lang():
    lang = request.cookies.get("lang", "en")
    return lang if lang in ("en", "ar") else "en"


@app.route("/lang/<code>")
def set_lang(code):
    resp = redirect(request.referrer or url_for("home"))
    if code in ("en", "ar"):
        resp.set_cookie("lang", code, max_age=60 * 60 * 24 * 365)
    return resp


@app.context_processor
def inject_globals():
    lang = current_lang()
    return {
        "role": current_role(), "DAY_AR": DAY_AR, "lang": lang,
        "dir": "rtl" if lang == "ar" else "ltr",
        "t": lambda key, **kw: translate(lang, key, **kw),
        "wa_num": jordan_wa_number,
        "BUILD": BUILD,
    }


# ---------------- helpers ----------------

def _shift_month(d, delta):
    y = d.year + (d.month - 1 + delta) // 12
    m = (d.month - 1 + delta) % 12 + 1
    return date(y, m, 1)


def month_options(con=None, back=15, fwd=2):
    """Every recent month is selectable (not just months that already have data),
    plus any historical month that does have records."""
    base = date.today().replace(day=1)
    opts = {_shift_month(base, i).strftime("%Y-%m") for i in range(-back, fwd + 1)}
    if con is not None:
        for table in ("payments", "expenses"):
            try:
                for r in con.execute(f"SELECT DISTINCT substr(date,1,7) m FROM {table}").fetchall():
                    if r["m"]:
                        opts.add(r["m"])
            except Exception:
                pass
    return sorted(opts, reverse=True)


def jordan_wa_number(phone):
    """07XXXXXXXX -> 9627XXXXXXXX for wa.me links."""
    p = re.sub(r"\D", "", phone or "")
    if p.startswith("07") and len(p) == 10:
        return "962" + p[1:]
    if p.startswith("9627"):
        return p
    return p


def wa_link(phone, text):
    return f"https://wa.me/{jordan_wa_number(phone)}?text={urllib.parse.quote(text)}"


def render_template_msg(tpl, name, sessions_left=None, price=None):
    msg = tpl.replace("[الاسم]", name)
    if sessions_left is not None:
        msg = msg.replace("[X]", str(sessions_left))
    if price is not None:
        msg = msg.replace("[السعر]", str(price))
    return msg


def next_training_day(settings, from_date=None):
    """Today if it's a training day, else the next training day."""
    d = from_date or date.today()
    tdays = set(settings.get("training_days") or [])
    for i in range(8):
        cand = d + timedelta(days=i)
        if cand.strftime("%A") in tdays:
            return cand
    return d


def player_sub_info(con, player):
    """Active-subscription summary dict for a player row."""
    sub = db.get_active_subscription(con, player["id"])
    if not sub:
        # is there a recent non-active sub? (for "needs renewal" context)
        last = con.execute(
            "SELECT * FROM subscriptions WHERE player_id=? ORDER BY start_date DESC LIMIT 1", (player["id"],)
        ).fetchone()
        return {"active": False, "sub": dict(last) if last else None, "left": 0, "days_left": 0,
                "needs_renewal": True}
    left = sub["sessions_total"] - sub["sessions_used"]
    days_left = (date.fromisoformat(sub["expiry_date"]) - date.today()).days
    return {"active": True, "sub": dict(sub), "left": left, "days_left": days_left,
            "needs_renewal": left <= 2 or days_left <= 5}


# ---------------- pages ----------------

@app.route("/")
def home():
    role = current_role()
    if role is None:
        return redirect(url_for("login"))
    if role == "coach":
        return redirect(url_for("attendance_page"))
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@require_role("admin")
def dashboard():
    con = db.get_db()
    st = db.get_settings()
    month = date.today().strftime("%Y-%m")
    today = date.today().isoformat()

    kpis = {
        "active_players": con.execute("SELECT COUNT(*) c FROM players WHERE status='active'").fetchone()["c"],
        "present_today": con.execute(
            "SELECT COUNT(*) c FROM attendance WHERE session_date=? AND status='present'", (today,)).fetchone()["c"],
        "revenue_month": con.execute(
            "SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date LIKE ?", (month + "%",)).fetchone()["s"],
        "unpaid_count": con.execute("SELECT COUNT(*) c FROM attendance WHERE unpaid=1").fetchone()["c"],
        "attendance_rate": db.month_attendance_rate(con, month),
    }

    # renewal alerts
    alerts = []
    players = con.execute(
        "SELECT p.*, g.name_ar AS group_name FROM players p LEFT JOIN groups g ON g.id=p.group_id "
        "WHERE p.status='active' ORDER BY p.full_name").fetchall()
    for p in players:
        info = player_sub_info(con, p)
        if info["needs_renewal"]:
            left = info["left"] if info["active"] else 0
            msg = render_template_msg(st["template_renewal"], p["full_name"], left, st["monthly_price"])
            alerts.append({
                "player": dict(p), "left": left,
                "days_left": info["days_left"] if info["active"] else 0,
                "active": info["active"],
                "wa": wa_link(p["guardian_phone"] or p["phone"], msg),
            })

    # unpaid sessions list
    unpaid = con.execute(
        "SELECT a.session_date, p.id AS pid, p.full_name, p.guardian_phone, g.name_ar AS group_name "
        "FROM attendance a JOIN players p ON p.id=a.player_id LEFT JOIN groups g ON g.id=a.group_id "
        "WHERE a.unpaid=1 ORDER BY a.session_date DESC").fetchall()

    # players a coach added, waiting for admin approval
    pending = con.execute(
        "SELECT p.id, p.full_name, p.guardian_phone, p.added_by, "
        "COALESCE(g.name_ar, g.name_en) AS group_name FROM players p "
        "LEFT JOIN groups g ON g.id=p.group_id WHERE p.status='pending' ORDER BY p.id DESC").fetchall()

    # charts data
    att_sessions = con.execute(
        "SELECT session_date, SUM(status='present') present FROM attendance "
        "GROUP BY session_date ORDER BY session_date DESC LIMIT 12").fetchall()
    att_chart = [{"d": r["session_date"][5:], "v": r["present"]} for r in reversed(att_sessions)]
    rev_rows = con.execute(
        "SELECT substr(date,1,7) m, SUM(amount) s FROM payments GROUP BY m ORDER BY m DESC LIMIT 6").fetchall()
    rev_chart = [{"d": r["m"], "v": r["s"]} for r in reversed(rev_rows)]
    grp_rows = con.execute(
        "SELECT g.name_ar n, COUNT(p.id) c FROM groups g LEFT JOIN players p "
        "ON p.group_id=g.id AND p.status='active' GROUP BY g.id").fetchall()
    grp_chart = [{"d": r["n"], "v": r["c"]} for r in grp_rows]

    # birthdays this month
    mm = date.today().strftime("%m")
    bdays = [dict(p) for p in players if p["birth_date"] and p["birth_date"][5:7] == mm]
    fin = db.finance(con, month)
    con.close()
    return render_template("dashboard.html", kpis=kpis, alerts=alerts, unpaid=unpaid,
                           pending=pending, att_chart=att_chart, rev_chart=rev_chart,
                           grp_chart=grp_chart, bdays=bdays, fin=fin, public_url=PUBLIC_URL["url"])


# ---------------- players ----------------

@app.route("/players")
@require_role("admin")
def players_page():
    con = db.get_db()
    q = (request.args.get("q") or "").strip()
    group_id = request.args.get("group") or ""
    gender = request.args.get("gender") or ""
    status = request.args.get("status") or ""
    renewal = request.args.get("renewal") == "1"

    sql = "SELECT p.*, g.name_ar AS group_name FROM players p LEFT JOIN groups g ON g.id=p.group_id WHERE 1=1"
    args = []
    if q:
        sql += " AND p.full_name LIKE ?"
        args.append(f"%{q}%")
    if group_id:
        sql += " AND p.group_id=?"
        args.append(group_id)
    if gender:
        sql += " AND p.gender=?"
        args.append(gender)
    if status:
        sql += " AND p.status=?"
        args.append(status)
    sql += " ORDER BY p.full_name"
    rows = con.execute(sql, args).fetchall()

    players = []
    for p in rows:
        info = player_sub_info(con, p)
        if renewal and not info["needs_renewal"]:
            continue
        players.append({"p": dict(p), "info": info})
    groups = con.execute("SELECT * FROM groups").fetchall()
    con.close()
    return render_template("players.html", players=players, groups=groups,
                           q=q, f_group=group_id, f_gender=gender, f_status=status, f_renewal=renewal)


@app.route("/players/new", methods=["GET", "POST"])
@app.route("/players/<int:pid>/edit", methods=["GET", "POST"])
@require_role("admin")
def player_form(pid=None):
    con = db.get_db()
    player = con.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone() if pid else None
    if pid and not player:
        con.close()
        abort(404)
    error = None
    if request.method == "POST":
        f = request.form
        gphone = (f.get("guardian_phone") or "").strip()
        if gphone and not re.fullmatch(r"07\d{8}", gphone):
            error = translate(current_lang(), "invalid_guardian")
        else:
            vals = (f.get("full_name", "").strip(), f.get("birth_date") or "", f.get("gender") or "M",
                    (f.get("phone") or "").strip(), (f.get("guardian_name") or "").strip(), gphone,
                    f.get("group_id") or None, f.get("join_date") or date.today().isoformat(),
                    (f.get("notes") or "").strip(), f.get("status") or "active",
                    1 if f.get("trial_used") else 0)
            if player:
                con.execute(
                    "UPDATE players SET full_name=?,birth_date=?,gender=?,phone=?,guardian_name=?,"
                    "guardian_phone=?,group_id=?,join_date=?,notes=?,status=?,trial_used=? WHERE id=?",
                    vals + (pid,))
                con.commit()
                con.close()
                return redirect(url_for("player_card", pid=pid))
            cur = con.execute(
                "INSERT INTO players (full_name,birth_date,gender,phone,guardian_name,guardian_phone,"
                "group_id,join_date,notes,status,trial_used) VALUES (?,?,?,?,?,?,?,?,?,?,?)", vals)
            con.commit()
            new_id = cur.lastrowid
            # a new player normally means they just paid — start their subscription
            if f.get("create_sub"):
                db.create_subscription(
                    con, new_id,
                    f.get("sub_start") or f.get("join_date") or date.today().isoformat(),
                    price=(f.get("sub_price") or None),
                    sessions_total=(f.get("sub_sessions") or None),
                    method=(f.get("sub_method") or "cash"),
                    amount=(f.get("sub_price") or None))
                con.commit()
            con.close()
            return redirect(url_for("player_card", pid=new_id))
    groups = con.execute("SELECT * FROM groups").fetchall()
    st = db.get_settings()
    con.close()
    return render_template("player_form.html", player=player, groups=groups, error=error,
                           settings=st, today=date.today().isoformat())


@app.route("/api/suggest-group")
@require_role("admin")
def api_suggest_group():
    con = db.get_db()
    gid = db.suggest_group(con, request.args.get("birth_date", ""), request.args.get("gender", "M"))
    con.close()
    return jsonify({"group_id": gid})


@app.route("/players/<int:pid>")
@require_role("admin")
def player_card(pid):
    con = db.get_db()
    p = con.execute(
        "SELECT p.*, g.name_ar AS group_name FROM players p LEFT JOIN groups g ON g.id=p.group_id WHERE p.id=?",
        (pid,)).fetchone()
    if not p:
        con.close()
        abort(404)
    st = db.get_settings()
    info = player_sub_info(con, p)
    subs = con.execute("SELECT * FROM subscriptions WHERE player_id=? ORDER BY start_date DESC", (pid,)).fetchall()
    pays = con.execute("SELECT * FROM payments WHERE player_id=? ORDER BY date DESC, id DESC", (pid,)).fetchall()
    att = con.execute(
        "SELECT * FROM attendance WHERE player_id=? ORDER BY session_date DESC LIMIT 30", (pid,)).fetchall()
    att_stats = db.attendance_rate(con, pid)
    trial_row = con.execute(
        "SELECT session_date FROM attendance WHERE player_id=? AND trial=1 ORDER BY session_date LIMIT 1",
        (pid,)).fetchone()
    trial_date = trial_row["session_date"] if trial_row else None
    msg = render_template_msg(st["template_renewal"], p["full_name"], info["left"], st["monthly_price"])
    wa = wa_link(p["guardian_phone"] or p["phone"], msg)
    # early-renewal option: day after previous expiry
    prev_expiry = None
    if info["sub"] and info["sub"].get("expiry_date") and info["sub"]["expiry_date"] >= date.today().isoformat():
        prev_expiry = (date.fromisoformat(info["sub"]["expiry_date"]) + timedelta(days=1)).isoformat()
    con.close()
    return render_template("player_card.html", p=p, info=info, subs=subs, pays=pays, att=att,
                           att_stats=att_stats, wa=wa, settings=st, prev_expiry=prev_expiry,
                           trial_date=trial_date, today=date.today().isoformat())


@app.route("/api/players/<int:pid>/renew", methods=["POST"])
@require_role("admin")
def api_renew(pid):
    data = request.get_json(force=True)
    con = db.get_db()
    start = data.get("start_date") or date.today().isoformat()
    sub_id, receipt = db.create_subscription(
        con, pid, start,
        price=data.get("price"), amount=data.get("amount"),
        sessions_total=data.get("sessions_total"),
        method=data.get("method", "cash"), note=data.get("note", ""))
    con.commit()
    con.close()
    return jsonify({"ok": True, "subscription_id": sub_id, "receipt_no": receipt})


@app.route("/api/players/<int:pid>/freeze", methods=["POST"])
@require_role("admin")
def api_freeze(pid):
    con = db.get_db()
    db.freeze_player(con, pid)
    con.close()
    return jsonify({"ok": True})


@app.route("/api/players/<int:pid>/unfreeze", methods=["POST"])
@require_role("admin")
def api_unfreeze(pid):
    con = db.get_db()
    db.unfreeze_player(con, pid)
    con.close()
    return jsonify({"ok": True})


@app.route("/api/players/<int:pid>/approve", methods=["POST"])
@require_role("admin")
def api_approve(pid):
    con = db.get_db()
    con.execute("UPDATE players SET status='active' WHERE id=? AND status='pending'", (pid,))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.route("/api/players/<int:pid>/reject", methods=["POST"])
@require_role("admin")
def api_reject(pid):
    """Reject a pending player. Delete if they have no records yet, else mark 'left'."""
    con = db.get_db()
    p = con.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
    if p and p["status"] == "pending":
        has_att = con.execute("SELECT 1 FROM attendance WHERE player_id=? LIMIT 1", (pid,)).fetchone()
        has_pay = con.execute("SELECT 1 FROM payments WHERE player_id=? LIMIT 1", (pid,)).fetchone()
        if has_att or has_pay:
            con.execute("UPDATE players SET status='left' WHERE id=?", (pid,))
        else:
            con.execute("DELETE FROM players WHERE id=?", (pid,))
        con.commit()
    con.close()
    return jsonify({"ok": True})


@app.route("/players/<int:pid>/delete", methods=["POST"])
@require_role("admin")
def player_delete(pid):
    con = db.get_db()
    db.delete_player(con, pid)
    con.close()
    return redirect(url_for("players_page"))


@app.route("/subscriptions/<int:sid>/edit", methods=["POST"])
@require_role("admin")
def subscription_edit(sid):
    f = request.form
    con = db.get_db()
    sub = con.execute("SELECT player_id FROM subscriptions WHERE id=?", (sid,)).fetchone()
    if sub:
        db.update_subscription(
            con, sid,
            start_date=(f.get("start_date") or None),
            sessions_total=(f.get("sessions_total") or None),
            sessions_used=(f.get("sessions_used") or None),
            price=(f.get("price") or None),
            expiry_date=(f.get("expiry_date") or None),
            status=(f.get("status") or None))
    pid = sub["player_id"] if sub else None
    con.close()
    return redirect(url_for("player_card", pid=pid) if pid else url_for("players_page"))


@app.route("/payments/<int:pay_id>/edit", methods=["POST"])
@require_role("admin")
def payment_edit(pay_id):
    """Fix a payment recorded with the wrong amount / method / date."""
    f = request.form
    con = db.get_db()
    pay = con.execute("SELECT * FROM payments WHERE id=?", (pay_id,)).fetchone()
    if pay:
        amount = float(f.get("amount") or pay["amount"])
        method = (f.get("method") or pay["method"]).strip()
        pdate = (f.get("date") or pay["date"]).strip()
        note = (f.get("note") if f.get("note") is not None else pay["note"]).strip()
        con.execute("UPDATE payments SET amount=?, method=?, date=?, note=? WHERE id=?",
                    (amount, method, pdate, note, pay_id))
        con.commit()
    pid = pay["player_id"] if pay else None
    con.close()
    return redirect(request.form.get("back") or (url_for("player_card", pid=pid) if pid else url_for("payments_page")))


@app.route("/payments/<int:pay_id>/delete", methods=["POST"])
@require_role("admin")
def payment_delete(pay_id):
    con = db.get_db()
    pay = con.execute("SELECT player_id FROM payments WHERE id=?", (pay_id,)).fetchone()
    pid = pay["player_id"] if pay else None
    con.execute("DELETE FROM payments WHERE id=?", (pay_id,))
    con.commit()
    con.close()
    return redirect(request.form.get("back") or (url_for("player_card", pid=pid) if pid else url_for("payments_page")))


@app.route("/subscriptions/<int:sid>/delete", methods=["POST"])
@require_role("admin")
def subscription_delete(sid):
    con = db.get_db()
    sub = con.execute("SELECT player_id FROM subscriptions WHERE id=?", (sid,)).fetchone()
    pid = sub["player_id"] if sub else None
    db.delete_subscription(con, sid, drop_payments=bool(request.form.get("drop_payments")))
    con.close()
    return redirect(url_for("player_card", pid=pid) if pid else url_for("players_page"))


# ---------------- attendance ----------------

@app.route("/attendance")
@require_role("admin", "coach")
def attendance_page():
    con = db.get_db()
    st = db.get_settings()
    groups = con.execute("SELECT * FROM groups").fetchall()
    con.close()
    # always default to today (Jordan time); coach can step days with the arrows
    default_date = date.today().isoformat()
    training_days = st.get("training_days") or []
    return render_template("attendance.html", groups=groups, default_date=default_date,
                           today=default_date, training_days=training_days)


@app.route("/api/attendance")
@require_role("admin", "coach")
def api_attendance_list():
    gid = request.args.get("group", type=int)
    sdate = request.args.get("date") or date.today().isoformat()
    con = db.get_db()
    players = con.execute(
        "SELECT * FROM players WHERE group_id=? AND status IN ('active','frozen','pending') ORDER BY full_name",
        (gid,)).fetchall()
    marks = {r["player_id"]: r for r in con.execute(
        "SELECT * FROM attendance WHERE session_date=? AND group_id=?", (sdate, gid)).fetchall()}
    out = []
    for p in players:
        info = player_sub_info(con, p)
        m = marks.get(p["id"])
        out.append({
            "id": p["id"], "name": p["full_name"],
            "status": m["status"] if m else "none",
            "left": info["left"], "paid": info["active"],
            "frozen": p["status"] == "frozen",
            "pending": p["status"] == "pending",
        })
    con.close()
    return jsonify({"players": out, "date": sdate})


@app.route("/api/attendance/add-player", methods=["POST"])
@require_role("admin", "coach")
def api_attendance_add_player():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    gid = data.get("group_id")
    if not name or not gid:
        return jsonify({"error": "missing"}), 400
    gphone = (data.get("guardian_phone") or "").strip()
    if gphone and not re.fullmatch(r"07\d{8}", gphone):
        return jsonify({"error": "bad_phone"}), 400
    con = db.get_db()
    grp = con.execute("SELECT * FROM groups WHERE id=?", (int(gid),)).fetchone()
    gender = grp["gender"] if grp and grp["gender"] in ("M", "F") else "M"
    # admins adding this way still create a pending row so it's reviewed like any other
    pid = db.add_pending_player(con, name, int(gid), guardian_phone=gphone,
                                gender=gender, added_by=current_role() or "coach")
    p = con.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
    info = player_sub_info(con, p)
    con.close()
    return jsonify({"ok": True, "player": {
        "id": pid, "name": name, "status": "none",
        "left": info["left"], "paid": info["active"], "frozen": False, "pending": True}})


@app.route("/api/attendance/mark", methods=["POST"])
@require_role("admin", "coach")
def api_attendance_mark():
    data = request.get_json(force=True)
    con = db.get_db()
    result = db.mark_attendance(
        con, int(data["player_id"]), data["date"], int(data["group_id"]),
        data["status"], marked_by=current_role() or "")
    # return fresh sessions-left for the badge
    p = con.execute("SELECT * FROM players WHERE id=?", (int(data["player_id"]),)).fetchone()
    info = player_sub_info(con, p)
    con.close()
    return jsonify({"ok": True, "status": result["status"], "unpaid": result["unpaid"],
                    "trial": result.get("trial", False), "left": info["left"], "paid": info["active"]})


@app.route("/api/attendance/mark-all-present", methods=["POST"])
@require_role("admin", "coach")
def api_attendance_mark_all():
    """One-tap: mark every not-yet-present player in the group present."""
    data = request.get_json(force=True)
    gid = int(data["group_id"])
    sdate = data["date"]
    con = db.get_db()
    players = con.execute(
        "SELECT id FROM players WHERE group_id=? AND status IN ('active','frozen','pending')",
        (gid,)).fetchall()
    existing = {r["player_id"]: r["status"] for r in con.execute(
        "SELECT player_id, status FROM attendance WHERE session_date=? AND group_id=?",
        (sdate, gid)).fetchall()}
    for p in players:
        if existing.get(p["id"]) != "present":
            db.mark_attendance(con, p["id"], sdate, gid, "present", marked_by=current_role() or "")
    con.close()
    return jsonify({"ok": True})


@app.route("/api/attendance/summary")
@require_role("admin", "coach")
def api_attendance_summary():
    gid = request.args.get("group", type=int)
    sdate = request.args.get("date") or date.today().isoformat()
    con = db.get_db()
    g = con.execute("SELECT * FROM groups WHERE id=?", (gid,)).fetchone()
    rows = con.execute(
        "SELECT p.full_name, a.status FROM attendance a JOIN players p ON p.id=a.player_id "
        "WHERE a.session_date=? AND a.group_id=? ORDER BY p.full_name", (sdate, gid)).fetchall()
    con.close()
    present = [r["full_name"] for r in rows if r["status"] == "present"]
    absent = [r["full_name"] for r in rows if r["status"] == "absent"]
    excused = [r["full_name"] for r in rows if r["status"] == "excused"]
    d = date.fromisoformat(sdate)
    day_ar = DAY_AR.get(d.strftime("%A"), "")
    lines = [f"Dream Academy — ملخص تمرين {g['name_ar']}",
             f"التاريخ: {day_ar} {d.strftime('%d/%m/%Y')}",
             f"الحضور ({len(present)}): " + ("، ".join(present) if present else "—")]
    if absent:
        lines.append(f"الغياب ({len(absent)}): " + "، ".join(absent))
    if excused:
        lines.append(f"معذورين ({len(excused)}): " + "، ".join(excused))
    lines.append("يعطيكم العافية.")
    return jsonify({"present": present, "absent": absent, "excused": excused, "text": "\n".join(lines)})


# ---------------- payments ----------------

@app.route("/payments")
@require_role("admin")
def payments_page():
    month = request.args.get("month") or date.today().strftime("%Y-%m")
    method = request.args.get("method") or ""
    con = db.get_db()
    sql = ("SELECT pm.*, p.full_name FROM payments pm JOIN players p ON p.id=pm.player_id "
           "WHERE pm.date LIKE ?")
    args = [month + "%"]
    if method:
        sql += " AND pm.method=?"
        args.append(method)
    sql += " ORDER BY pm.date DESC, pm.id DESC"
    rows = con.execute(sql, args).fetchall()
    total = sum(r["amount"] for r in rows)
    months = month_options(con)
    if month not in months:
        months.insert(0, month)
    con.close()
    return render_template("payments.html", rows=rows, total=total, month=month,
                           months=months, method=method)


@app.route("/payments/export")
@require_role("admin")
def payments_export():
    month = request.args.get("month") or date.today().strftime("%Y-%m")
    method = request.args.get("method") or ""
    con = db.get_db()
    sql = ("SELECT pm.receipt_no, p.full_name, pm.amount, pm.date, pm.method, pm.note "
           "FROM payments pm JOIN players p ON p.id=pm.player_id WHERE pm.date LIKE ?")
    args = [month + "%"]
    if method:
        sql += " AND pm.method=?"
        args.append(method)
    rows = con.execute(sql + " ORDER BY pm.date", args).fetchall()
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    excel_io._sheet(wb, f"Payments {month}",
                    ["رقم الإيصال", "اللاعب", "المبلغ", "التاريخ", "الطريقة", "ملاحظة"],
                    [tuple(r) for r in rows])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    con.close()
    return send_file(buf, as_attachment=True, download_name=f"payments-{month}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/receipt/<int:payment_id>")
@require_role("admin")
def receipt(payment_id):
    con = db.get_db()
    pm = con.execute(
        "SELECT pm.*, p.full_name FROM payments pm JOIN players p ON p.id=pm.player_id WHERE pm.id=?",
        (payment_id,)).fetchone()
    sub = con.execute("SELECT * FROM subscriptions WHERE id=?", (pm["subscription_id"],)).fetchone() if pm and pm["subscription_id"] else None
    con.close()
    if not pm:
        abort(404)
    return render_template("receipt.html", pm=pm, sub=sub)


# ---------------- settings & groups ----------------

@app.route("/settings", methods=["GET", "POST"])
@require_role("admin")
def settings_page():
    st = db.get_settings()
    saved = False
    if request.method == "POST":
        f = request.form
        st["monthly_price"] = float(f.get("monthly_price") or 20)
        st["sessions_per_month"] = int(f.get("sessions_per_month") or 12)
        st["expiry_days"] = int(f.get("expiry_days") or 35)
        st["deduct_on_absence"] = bool(f.get("deduct_on_absence"))
        st["training_days"] = f.getlist("training_days") or st["training_days"]
        st["academy_phone"] = (f.get("academy_phone") or "").strip()
        st["coach_pin"] = (f.get("coach_pin") or "1234").strip()
        st["admin_pin"] = (f.get("admin_pin") or "0000").strip()
        st["template_renewal"] = f.get("template_renewal") or st["template_renewal"]
        st["template_absence"] = f.get("template_absence") or st["template_absence"]
        # bundles (parallel arrays; keep rows that have a name)
        b_en = f.getlist("bundle_name_en"); b_ar = f.getlist("bundle_name_ar")
        b_se = f.getlist("bundle_sessions"); b_pr = f.getlist("bundle_price")
        bundles = []
        for i in range(len(b_en)):
            name_en = (b_en[i] or "").strip()
            name_ar = (b_ar[i] if i < len(b_ar) else "").strip()
            if not name_en and not name_ar:
                continue
            try:
                bundles.append({"name_en": name_en or name_ar, "name_ar": name_ar or name_en,
                                "sessions": int(b_se[i] or 1), "price": float(b_pr[i] or 0)})
            except (ValueError, IndexError):
                continue
        if bundles:
            st["bundles"] = bundles
        db.save_settings(st)
        saved = True
    con = db.get_db()
    groups = con.execute(
        "SELECT g.*, (SELECT COUNT(*) FROM players p WHERE p.group_id=g.id) AS player_count "
        "FROM groups g").fetchall()
    con.close()
    group_error = request.args.get("group_error", type=int)
    shown_url = coach_access_url()
    return render_template("settings.html", st=st, saved=saved, groups=groups,
                           all_days=list(DAY_AR.keys()), public_url=shown_url,
                           group_error=group_error)


@app.route("/groups/save", methods=["POST"])
@require_role("admin")
def groups_save():
    f = request.form
    con = db.get_db()
    gid = f.get("id")
    vals = (f.get("name_ar", "").strip(), f.get("name_en", "").strip(),
            int(f.get("min_age") or 0), int(f.get("max_age") or 99),
            f.get("gender") or "mixed", f.get("schedule_days") or "Sun/Tue/Thu",
            f.get("time_slot") or "")
    if gid:
        con.execute("UPDATE groups SET name_ar=?,name_en=?,min_age=?,max_age=?,gender=?,schedule_days=?,time_slot=? WHERE id=?",
                    vals + (gid,))
    else:
        con.execute("INSERT INTO groups (name_ar,name_en,min_age,max_age,gender,schedule_days,time_slot) VALUES (?,?,?,?,?,?,?)", vals)
    con.commit()
    con.close()
    return redirect(f.get("back") or url_for("groups_page"))


@app.route("/groups/<int:gid>/delete", methods=["POST"])
@require_role("admin")
def groups_delete(gid):
    back = request.form.get("back") or url_for("groups_page")
    con = db.get_db()
    count = con.execute("SELECT COUNT(*) c FROM players WHERE group_id=?", (gid,)).fetchone()["c"]
    if count > 0:
        con.close()
        sep = "&" if "?" in back else "?"
        return redirect(f"{back}{sep}group_error={gid}")
    con.execute("DELETE FROM groups WHERE id=?", (gid,))
    con.commit()
    con.close()
    return redirect(back)


@app.route("/groups")
@require_role("admin")
def groups_page():
    con = db.get_db()
    groups = con.execute(
        "SELECT g.*, (SELECT COUNT(*) FROM players p WHERE p.group_id=g.id AND p.status IN ('active','frozen','pending')) AS player_count "
        "FROM groups g ORDER BY g.id").fetchall()
    con.close()
    group_error = request.args.get("group_error", type=int)
    return render_template("groups.html", groups=groups, group_error=group_error,
                           all_days=list(DAY_AR.keys()))


# ---------------- assistant (fake AI) ----------------

@app.route("/api/assistant/suggestions")
@require_role("admin", "coach")
def api_assistant_suggestions():
    return jsonify({"suggestions": ai.SUGGESTIONS.get(current_lang(), ai.SUGGESTIONS["en"])})


@app.route("/api/assistant", methods=["POST"])
@require_role("admin", "coach")
def api_assistant():
    q = (request.get_json(force=True).get("q") or "").strip()
    lang = current_lang()
    con = db.get_db()
    reply = ai.ask(con, q, lang)
    st = db.get_settings()
    # enrich rows with a ready WhatsApp link (renewal template)
    for row in reply.get("rows", []):
        phone = row.get("phone")
        if phone:
            msg = render_template_msg(st["template_renewal"], row["name"], row.get("left", ""), st["monthly_price"])
            row["wa"] = wa_link(phone, msg)
    con.close()
    return jsonify(reply)


# ---------------- analytics ----------------

@app.route("/analytics")
@require_role("admin")
def analytics_page():
    con = db.get_db()
    st = db.get_settings()
    today = date.today()
    month = today.strftime("%Y-%m")
    prev_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    total_players = con.execute("SELECT COUNT(*) c FROM players WHERE status IN ('active','frozen')").fetchone()["c"]
    active = con.execute("SELECT COUNT(*) c FROM players WHERE status='active'").fetchone()["c"]
    rate = db.month_attendance_rate(con, month)
    prev_rate = db.month_attendance_rate(con, prev_month)
    rev = con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date LIKE ?", (month + "%",)).fetchone()["s"]
    prev_rev = con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date LIKE ?", (prev_month + "%",)).fetchone()["s"]

    # charts
    att_rows = con.execute(
        "SELECT session_date, SUM(status='present') p, SUM(status='absent') a FROM attendance "
        "GROUP BY session_date ORDER BY session_date DESC LIMIT 12").fetchall()
    att_chart = [{"d": r["session_date"][5:], "v": (round(r["p"]*100/(r["p"]+r["a"])) if (r["p"]+r["a"]) else 0)}
                 for r in reversed(att_rows)]
    rev_rows = con.execute(
        "SELECT substr(date,1,7) m, SUM(amount) s FROM payments GROUP BY m ORDER BY m DESC LIMIT 6").fetchall()
    rev_chart = [{"d": r["m"][2:], "v": r["s"]} for r in reversed(rev_rows)]
    grp_rows = con.execute(
        "SELECT COALESCE(g.name_ar, g.name_en) n, g.id gid FROM groups g").fetchall()
    grp_chart = []
    for g in grp_rows:
        gr = con.execute(
            "SELECT SUM(status='present') p, SUM(status='absent') a FROM attendance WHERE group_id=?",
            (g["gid"],)).fetchone()
        cnt = con.execute("SELECT COUNT(*) c FROM players WHERE group_id=? AND status='active'",
                          (g["gid"],)).fetchone()["c"]
        att = round(gr["p"]*100/(gr["p"]+gr["a"])) if (gr["p"] and (gr["p"]+gr["a"])) else 0
        grp_chart.append({"d": g["n"], "players": cnt, "rate": att})

    # new players per month (last 6)
    new_rows = con.execute(
        "SELECT substr(join_date,1,7) m, COUNT(*) c FROM players WHERE join_date!='' "
        "GROUP BY m ORDER BY m DESC LIMIT 6").fetchall()
    new_chart = [{"d": r["m"][2:], "v": r["c"]} for r in reversed(new_rows)]

    # at-risk: active players whose attendance rate < 50% (min 3 sessions)
    at_risk = []
    for p in con.execute("SELECT * FROM players WHERE status='active'").fetchall():
        s = db.attendance_rate(con, p["id"])
        if s["rate"] is not None and s["total"] >= 3 and s["rate"] < 50:
            at_risk.append({"id": p["id"], "name": p["full_name"], "rate": s["rate"]})
    at_risk.sort(key=lambda x: x["rate"])

    # best group by attendance
    ranked = [g for g in grp_chart if g["players"] > 0]
    best_group = max(ranked, key=lambda g: g["rate"]) if ranked else None

    # ----- auto-generated "AI" insights -----
    insights = []
    if rate is not None and prev_rate is not None:
        diff = rate - prev_rate
        if diff >= 3:
            insights.append({"tone": "ok", "text": ai_insight_att_up(current_lang(), diff, rate)})
        elif diff <= -3:
            insights.append({"tone": "bad", "text": ai_insight_att_down(current_lang(), abs(diff), rate)})
    if best_group:
        insights.append({"tone": "ok", "text": ai_insight_best_group(current_lang(), best_group)})
    if at_risk:
        insights.append({"tone": "warn", "text": ai_insight_at_risk(current_lang(), len(at_risk))})
    if prev_rev and rev:
        if rev >= prev_rev * 1.05:
            insights.append({"tone": "ok", "text": ai_insight_rev(current_lang(), "up", rev, prev_rev)})
        elif rev <= prev_rev * 0.95:
            insights.append({"tone": "warn", "text": ai_insight_rev(current_lang(), "down", rev, prev_rev)})
    if not insights:
        insights.append({"tone": "muted", "text": (
            "لسا ما في بيانات كافية لتحليل — سجّل حضور ودفعات أكثر." if current_lang() == "ar"
            else "Not enough data yet — log more attendance and payments.")})

    fin = db.finance(con, month)
    # revenue vs expenses vs profit across recent months (for a column chart)
    fin_months = []
    d0 = today.replace(day=1)
    for i in range(5, -1, -1):
        mm = (d0 - timedelta(days=30 * i)).strftime("%Y-%m")
        f = db.finance(con, mm)
        fin_months.append({"d": mm[2:], "rev": f["revenue"], "exp": f["expenses"], "profit": f["profit"]})
    con.close()
    return render_template("analytics.html",
                           kpi={"total": total_players, "active": active, "rate": rate or 0, "revenue": rev},
                           att_chart=att_chart, rev_chart=rev_chart, grp_chart=grp_chart,
                           new_chart=new_chart, at_risk=at_risk[:6], insights=insights,
                           best_group=best_group, fin=fin, fin_months=fin_months)


def ai_insight_att_up(lang, diff, rate):
    return (f"الحضور ارتفع {diff} نقطة عن الشهر الماضي ووصل {rate}٪ — استمر بنفس الروتين." if lang == "ar"
            else f"Attendance is up {diff} points vs last month, now {rate}%. Keep the routine going.")


def ai_insight_att_down(lang, diff, rate):
    return (f"الحضور نزل {diff} نقطة لـ {rate}٪ — فكّر تبعث تذكير للأهالي." if lang == "ar"
            else f"Attendance dropped {diff} points to {rate}%. Consider a reminder to parents.")


def ai_insight_best_group(lang, g):
    return (f"أعلى مجموعة حضوراً: {g['d']} بنسبة {g['rate']}٪." if lang == "ar"
            else f"Top group by attendance: {g['d']} at {g['rate']}%.")


def ai_insight_at_risk(lang, n):
    return (f"{n} لاعب حضورهم أقل من 50٪ — معرّضين يتركوا، تابعهم." if lang == "ar"
            else f"{n} players are below 50% attendance — at risk of dropping out. Follow up.")


def ai_insight_rev(lang, dirn, rev, prev):
    if dirn == "up":
        return (f"الإيراد أعلى من الشهر الماضي ({rev:g} مقابل {prev:g} دينار)." if lang == "ar"
                else f"Revenue is higher than last month ({rev:g} vs {prev:g} JD).")
    return (f"الإيراد أقل من الشهر الماضي ({rev:g} مقابل {prev:g} دينار)." if lang == "ar"
            else f"Revenue is lower than last month ({rev:g} vs {prev:g} JD).")


# ---------------- finance: coaches, salaries, expenses, profit ----------------

@app.route("/finance")
@require_role("admin")
def finance_page():
    month = request.args.get("month") or date.today().strftime("%Y-%m")
    con = db.get_db()
    fin = db.finance(con, month)
    today = date.today().isoformat()
    coaches = []
    for c in con.execute("SELECT * FROM coaches ORDER BY active DESC, name").fetchall():
        present_today = con.execute(
            "SELECT 1 FROM coach_attendance WHERE coach_id=? AND session_date=?", (c["id"], today)).fetchone()
        coaches.append({**dict(c),
                        "sessions": db.coach_month_sessions(con, c["id"], month),
                        "cost": db.coach_month_cost(con, c, month),
                        "present_today": bool(present_today)})
    expenses = con.execute(
        "SELECT * FROM expenses WHERE date LIKE ? ORDER BY date DESC, id DESC", (month + "%",)).fetchall()
    months = month_options(con)
    if month not in months:
        months.insert(0, month)
    con.close()
    return render_template("finance.html", fin=fin, coaches=coaches, expenses=expenses,
                           month=month, months=months, today=today)


@app.route("/coaches/save", methods=["POST"])
@require_role("admin")
def coaches_save():
    f = request.form
    con = db.get_db()
    cid = f.get("id")
    vals = (f.get("name", "").strip(), (f.get("phone") or "").strip(),
            f.get("salary_type") or "monthly", float(f.get("salary_amount") or 0),
            1 if f.get("active") else 0)
    if cid:
        con.execute("UPDATE coaches SET name=?,phone=?,salary_type=?,salary_amount=?,active=? WHERE id=?",
                    vals + (cid,))
    else:
        con.execute("INSERT INTO coaches (name,phone,salary_type,salary_amount,active,join_date) "
                    "VALUES (?,?,?,?,?,?)", vals + (date.today().isoformat(),))
    con.commit()
    con.close()
    return redirect(url_for("finance_page"))


@app.route("/coaches/<int:cid>/delete", methods=["POST"])
@require_role("admin")
def coaches_delete(cid):
    con = db.get_db()
    has_att = con.execute("SELECT 1 FROM coach_attendance WHERE coach_id=? LIMIT 1", (cid,)).fetchone()
    if has_att:
        con.execute("UPDATE coaches SET active=0 WHERE id=?", (cid,))  # keep history
    else:
        con.execute("DELETE FROM coaches WHERE id=?", (cid,))
    con.commit()
    con.close()
    return redirect(url_for("finance_page"))


@app.route("/coaches/<int:cid>/present", methods=["POST"])
@require_role("admin")
def coach_present(cid):
    """Toggle a coach's attendance for today."""
    con = db.get_db()
    today = date.today().isoformat()
    row = con.execute("SELECT id FROM coach_attendance WHERE coach_id=? AND session_date=?",
                      (cid, today)).fetchone()
    if row:
        con.execute("DELETE FROM coach_attendance WHERE id=?", (row["id"],))
        present = False
    else:
        con.execute("INSERT INTO coach_attendance (coach_id, session_date) VALUES (?,?)", (cid, today))
        present = True
    con.commit()
    con.close()
    return jsonify({"ok": True, "present": present})


@app.route("/expenses/save", methods=["POST"])
@require_role("admin")
def expenses_save():
    f = request.form
    con = db.get_db()
    con.execute("INSERT INTO expenses (date, category, amount, note) VALUES (?,?,?,?)",
                (f.get("date") or date.today().isoformat(), (f.get("category") or "other").strip(),
                 float(f.get("amount") or 0), (f.get("note") or "").strip()))
    con.commit()
    con.close()
    return redirect(url_for("finance_page", month=(f.get("date") or "")[:7] or None))


@app.route("/expenses/<int:eid>/delete", methods=["POST"])
@require_role("admin")
def expenses_delete(eid):
    con = db.get_db()
    con.execute("DELETE FROM expenses WHERE id=?", (eid,))
    con.commit()
    con.close()
    return redirect(request.referrer or url_for("finance_page"))


# ---------------- excel ----------------

@app.route("/export/all")
@require_role("admin")
def export_all():
    con = db.get_db()
    data = excel_io.export_all(con)
    con.close()
    return send_file(io.BytesIO(data), as_attachment=True,
                     download_name=f"dream-academy-{date.today().isoformat()}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/import/template")
@require_role("admin")
def import_template():
    return send_file(io.BytesIO(excel_io.players_template()), as_attachment=True,
                     download_name="players-template.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/import/players", methods=["POST"])
@require_role("admin")
def import_players():
    file = request.files.get("file")
    if not file:
        return redirect(url_for("players_page"))
    con = db.get_db()
    imported, skipped, errors = excel_io.import_players(con, file, db.suggest_group, filename=file.filename)
    con.close()
    msg = translate(current_lang(), "import_msg", i=imported, s=skipped)
    if errors:
        msg += " " + translate(current_lang(), "import_errors") + " | ".join(errors[:5])
    return render_template("import_result.html", msg=msg)


# ---------------- QR / connection info ----------------

@app.route("/qr")
@require_role("admin")
def qr_page():
    url = coach_access_url()
    import qrcode
    import base64
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return render_template("qr.html", url=url, qr_b64=b64, tunnel=(url != f"http://{get_local_ip()}:8000"))


def coach_access_url():
    """The URL coaches should use to reach this app: the real public hostname
    when reached through one (e.g. PythonAnywhere), else the Cloudflare tunnel
    if running, else the laptop's LAN IP for same-WiFi access."""
    host = (request.host or "").split(":")[0]
    if host not in ("127.0.0.1", "localhost", "::1") and not host.startswith("192.168.") \
            and not host.startswith("10.") and host != get_local_ip():
        return request.url_root.rstrip("/")
    return PUBLIC_URL["url"] or f"http://{get_local_ip()}:8000"


def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


# ---------------- cloudflared tunnel ----------------

def start_tunnel():
    """Start a Cloudflare quick tunnel if cloudflared.exe exists next to app.py."""
    exe = os.path.join(BASE_DIR, "cloudflared.exe")
    if not os.path.exists(exe):
        print("[i] cloudflared.exe not found - public link disabled. "
              "Download it from https://github.com/cloudflare/cloudflared/releases and place it next to app.py")
        return
    def run():
        proc = subprocess.Popen(
            [exe, "tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        for line in proc.stdout:
            m = re.search(r"(https://[a-z0-9-]+\.trycloudflare\.com)", line)
            if m and not PUBLIC_URL["url"]:
                PUBLIC_URL["url"] = m.group(1)
                print("\n" + "=" * 60)
                print(f"  Public URL ready:\n  {PUBLIC_URL['url']}")
                print(f"  Open the QR page on the laptop: http://127.0.0.1:8000/qr")
                print("=" * 60 + "\n")
    threading.Thread(target=run, daemon=True).start()


# idempotent — also covers WSGI hosting where __main__ never runs
db.init_db()

if __name__ == "__main__":
    db.backup_db()
    print("\nDream Academy Manager")
    print(f"   On this laptop:   http://127.0.0.1:8000")
    print(f"   On same network:  http://{get_local_ip()}:8000")
    start_tunnel()
    app.run(host="0.0.0.0", port=8000, debug=False)
