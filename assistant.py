# -*- coding: utf-8 -*-
"""Dream Academy — smart assistant.

NOT a real LLM. An Arabic/English normalization + intent-matching engine over
the SQLite DB. Returns structured replies the chat drawer renders (player names
become clickable rows with WhatsApp buttons). Bilingual: Jordanian Arabic + EN.
"""
import re
from datetime import date, timedelta

import database as db

_DIAC = re.compile(r"[ؗ-ًؚ-ْٰـ]")


def normalize(text):
    if not text:
        return ""
    t = text.strip().lower()
    t = _DIAC.sub("", t)
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    for ar, en in zip("٠١٢٣٤٥٦٧٨٩", "0123456789"):
        t = t.replace(ar, en)
    return re.sub(r"\s+", " ", t).strip()


def _has(text, *words):
    return any(w in text for w in words)


def _extract_int(text):
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


SUGGESTIONS = {
    "en": ["Who needs renewal?", "Revenue this month", "Who was absent today?",
           "Attendance rate", "How many active players?", "Unpaid players", "Best revenue month"],
    "ar": ["مين بدو تجديد؟", "قديش دخل هالشهر؟", "مين غاب اليوم؟",
           "نسبة الحضور", "كم لاعب فعال؟", "مين ما دفع؟", "أفضل شهر بالإيراد"],
}


def _reply(text, rows=None, kind="text"):
    return {"kind": kind, "text": text, "rows": rows or []}


def _active_players(con):
    return con.execute(
        "SELECT * FROM players WHERE status='active' ORDER BY full_name").fetchall()


def _row(p, sub):
    return {"id": p["id"], "name": p["full_name"],
            "phone": p["guardian_phone"] or p["phone"], "sub": sub}


def ask(con, raw, lang="en"):
    """Return {kind, text, rows}. Rows get WhatsApp links added by the caller."""
    t = normalize(raw)
    ar = lang == "ar"
    st = db.get_settings()
    month = date.today().strftime("%Y-%m")

    # revenue
    if _has(t, "revenue", "income", "money", "earn", "دخل", "ايراد", "مقبوضات", "فلوس", "قبض") \
            and not _has(t, "debt", "unpaid", "دين", "دفع"):
        if _has(t, "today", "اليوم"):
            v = con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date=?",
                            (date.today().isoformat(),)).fetchone()["s"]
            return _reply((f"مقبوضات اليوم: {v:g} دينار." if ar else f"Revenue today: {v:g} JD."))
        v = con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date LIKE ?",
                        (month + "%",)).fetchone()["s"]
        return _reply((f"إيراد هذا الشهر: {v:g} دينار." if ar else f"Revenue this month: {v:g} JD."))

    # best month
    if _has(t, "best month", "top month", "افضل شهر", "احسن شهر", "اعلى شهر"):
        r = con.execute("SELECT substr(date,1,7) m, SUM(amount) s FROM payments "
                        "GROUP BY m ORDER BY s DESC LIMIT 1").fetchone()
        if not r:
            return _reply("ما في بيانات إيراد بعد." if ar else "No revenue data yet.")
        return _reply((f"أفضل شهر: {r['m']} بمبلغ {r['s']:g} دينار." if ar
                       else f"Best month: {r['m']} with {r['s']:g} JD."))

    # attendance rate
    if _has(t, "attendance rate", "rate", "نسبه الحضور", "نسبة الحضور", "معدل الحضور"):
        rate = db.month_attendance_rate(con, month)
        if rate is None:
            return _reply("ما في حضور مسجّل هالشهر." if ar else "No attendance logged this month.")
        return _reply((f"نسبة الحضور هذا الشهر: {rate}%." if ar
                       else f"Attendance rate this month: {rate}%."))

    # absent today
    if _has(t, "absent", "غاب", "غايب", "غياب"):
        d = date.today().isoformat()
        rows = con.execute(
            "SELECT p.* FROM attendance a JOIN players p ON p.id=a.player_id "
            "WHERE a.session_date=? AND a.status='absent' ORDER BY p.full_name", (d,)).fetchall()
        if not rows:
            return _reply("ما في غياب اليوم." if ar else "No absences today.")
        out = [_row(p, ("غائب اليوم" if ar else "absent today")) for p in rows]
        return _reply((f"{len(rows)} غابوا اليوم:" if ar else f"{len(rows)} absent today:"),
                      out, kind="absent")

    # present today
    if _has(t, "present today", "who came", "حضر اليوم", "مين حضر", "الحاضرين"):
        d = date.today().isoformat()
        n = con.execute("SELECT COUNT(*) c FROM attendance WHERE session_date=? AND status='present'",
                        (d,)).fetchone()["c"]
        return _reply((f"حضر اليوم: {n} لاعب." if ar else f"Present today: {n} players."))

    # active count
    if _has(t, "how many", "count", "number", "كم", "قديش", "عدد") \
            and _has(t, "player", "active", "لاعب", "فعال", "لاعبين"):
        n = con.execute("SELECT COUNT(*) c FROM players WHERE status='active'").fetchone()["c"]
        return _reply((f"عدد اللاعبين الفعالين: {n}." if ar else f"Active players: {n}."))

    # unpaid
    if _has(t, "unpaid", "not paid", "debt", "owe", "ما دفع", "مدفوع", "دين", "بدون اشتراك"):
        rows = con.execute(
            "SELECT DISTINCT p.* FROM attendance a JOIN players p ON p.id=a.player_id "
            "WHERE a.unpaid=1 ORDER BY p.full_name").fetchall()
        if not rows:
            return _reply("ما في لاعبين غير مدفوعين." if ar else "No unpaid players.")
        out = [_row(p, ("غير مدفوع" if ar else "unpaid session")) for p in rows]
        return _reply((f"{len(rows)} لاعب غير مدفوع:" if ar else f"{len(rows)} unpaid players:"),
                      out, kind="unpaid")

    # renewal / expiring
    if _has(t, "renew", "expire", "expiring", "ending", "soon",
            "تجديد", "بينتهي", "بيخلص", "قرب", "خلص", "منتهي"):
        days = _extract_int(t) or 5
        rows = []
        for p in _active_players(con):
            sub = db.get_active_subscription(con, p["id"])
            if not sub:
                rows.append(_row(p, ("اشتراكه خالص" if ar else "no active subscription")))
            else:
                left = sub["sessions_total"] - sub["sessions_used"]
                dleft = (date.fromisoformat(sub["expiry_date"]) - date.today()).days
                if left <= 2 or dleft <= days:
                    rows.append(_row(p, (f"ضل {left} حصص · {dleft} يوم" if ar
                                         else f"{left} left · {dleft}d")))
        if not rows:
            return _reply("ما في حدا بدو تجديد هلق." if ar else "Nobody needs renewal right now.")
        return _reply((f"{len(rows)} لاعب بدهم تجديد:" if ar else f"{len(rows)} players need renewal:"),
                      rows, kind="renewal")

    # birthdays
    if _has(t, "birthday", "عيد ميلاد", "مواليد", "اعياد"):
        mm = date.today().strftime("%m")
        rows = con.execute("SELECT * FROM players WHERE substr(birth_date,6,2)=? AND status='active' "
                           "ORDER BY substr(birth_date,9,2)", (mm,)).fetchall()
        if not rows:
            return _reply("ما في أعياد ميلاد هالشهر." if ar else "No birthdays this month.")
        out = [_row(p, (p["birth_date"][8:10] + "/" + p["birth_date"][5:7])) for p in rows]
        return _reply((f"{len(rows)} عيد ميلاد هالشهر:" if ar else f"{len(rows)} birthdays this month:"),
                      out, kind="birthday")

    # today summary
    if _has(t, "summary", "today", "what's up", "whats up", "status", "ملخص", "شو صار", "الوضع", "اليوم"):
        d = date.today().isoformat()
        present = con.execute("SELECT COUNT(*) c FROM attendance WHERE session_date=? AND status='present'",
                              (d,)).fetchone()["c"]
        rev = con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date LIKE ?",
                          (month + "%",)).fetchone()["s"]
        unpaid = con.execute("SELECT COUNT(*) c FROM attendance WHERE unpaid=1").fetchone()["c"]
        if ar:
            return _reply(f"ملخص اليوم:\nحاضرين اليوم: {present}\nإيراد الشهر: {rev:g} دينار\nغير مدفوع: {unpaid}")
        return _reply(f"Today's summary:\nPresent today: {present}\nRevenue this month: {rev:g} JD\nUnpaid: {unpaid}")

    # player lookup by name
    hit = _find_player(con, t)
    if hit:
        p = hit
        sub = db.get_active_subscription(con, p["id"])
        if sub:
            left = sub["sessions_total"] - sub["sessions_used"]
            dleft = (date.fromisoformat(sub["expiry_date"]) - date.today()).days
            line = (f"{p['full_name']} — ضل {left} حصص، بنتهي بعد {dleft} يوم." if ar
                    else f"{p['full_name']} — {left} sessions left, expires in {dleft}d.")
        else:
            line = (f"{p['full_name']} — ما عنده اشتراك فعال." if ar
                    else f"{p['full_name']} — no active subscription.")
        return _reply(line, [_row(p, "")], kind="player")

    return _reply(
        ("ما فهمت عليك تماماً. جرّب تسألني وحدة من هدول:" if ar
         else "I didn't quite get that. Try one of these:"))


def _find_player(con, norm_text):
    best = None
    for r in con.execute("SELECT * FROM players").fetchall():
        nm = normalize(r["full_name"])
        if not nm:
            continue
        toks = [x for x in nm.split() if len(x) >= 2]
        if nm in norm_text or any(x in norm_text for x in toks if len(x) >= 3):
            if best is None or len(nm) > len(normalize(best["full_name"])):
                best = r
    return best
