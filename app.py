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
    }


# ---------------- helpers ----------------

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
    con.close()
    return render_template("dashboard.html", kpis=kpis, alerts=alerts, unpaid=unpaid,
                           pending=pending, att_chart=att_chart, rev_chart=rev_chart,
                           grp_chart=grp_chart, bdays=bdays, public_url=PUBLIC_URL["url"])


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
            con.close()
            return redirect(url_for("player_card", pid=new_id))
    groups = con.execute("SELECT * FROM groups").fetchall()
    con.close()
    return render_template("player_form.html", player=player, groups=groups, error=error,
                           today=date.today().isoformat())


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
    msg = render_template_msg(st["template_renewal"], p["full_name"], info["left"], st["monthly_price"])
    wa = wa_link(p["guardian_phone"] or p["phone"], msg)
    # early-renewal option: day after previous expiry
    prev_expiry = None
    if info["sub"] and info["sub"].get("expiry_date") and info["sub"]["expiry_date"] >= date.today().isoformat():
        prev_expiry = (date.fromisoformat(info["sub"]["expiry_date"]) + timedelta(days=1)).isoformat()
    con.close()
    return render_template("player_card.html", p=p, info=info, subs=subs, pays=pays, att=att,
                           wa=wa, settings=st, prev_expiry=prev_expiry, today=date.today().isoformat())


@app.route("/api/players/<int:pid>/renew", methods=["POST"])
@require_role("admin")
def api_renew(pid):
    data = request.get_json(force=True)
    con = db.get_db()
    start = data.get("start_date") or date.today().isoformat()
    sub_id, receipt = db.create_subscription(
        con, pid, start,
        price=data.get("price"), amount=data.get("amount"),
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


# ---------------- attendance ----------------

@app.route("/attendance")
@require_role("admin", "coach")
def attendance_page():
    con = db.get_db()
    st = db.get_settings()
    groups = con.execute("SELECT * FROM groups").fetchall()
    con.close()
    default_date = next_training_day(st).isoformat()
    return render_template("attendance.html", groups=groups, default_date=default_date)


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
                    "left": info["left"], "paid": info["active"]})


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
    months = [r["m"] for r in con.execute(
        "SELECT DISTINCT substr(date,1,7) m FROM payments ORDER BY m DESC").fetchall()]
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
    return redirect(url_for("settings_page"))


@app.route("/groups/<int:gid>/delete", methods=["POST"])
@require_role("admin")
def groups_delete(gid):
    con = db.get_db()
    count = con.execute("SELECT COUNT(*) c FROM players WHERE group_id=?", (gid,)).fetchone()["c"]
    if count > 0:
        con.close()
        return redirect(url_for("settings_page", group_error=gid))
    con.execute("DELETE FROM groups WHERE id=?", (gid,))
    con.commit()
    con.close()
    return redirect(url_for("settings_page"))


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
    imported, skipped, errors = excel_io.import_players(con, file, db.suggest_group)
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
