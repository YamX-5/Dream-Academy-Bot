# -*- coding: utf-8 -*-
"""Excel export/import for Dream Academy Manager (openpyxl, Arabic-safe)."""
import io
import os
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def _sheet(wb, title, headers, rows, rtl=True):
    ws = wb.create_sheet(title)
    ws.sheet_view.rightToLeft = rtl
    ws.append(headers)
    for c in ws[1]:
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center")
    for r in rows:
        ws.append(list(r))
    # auto column widths
    for i, h in enumerate(headers, 1):
        width = len(str(h)) + 4
        for r in rows[:200]:
            v = r[i - 1] if i - 1 < len(r) else ""
            width = max(width, min(len(str(v)) + 4, 45))
        ws.column_dimensions[get_column_letter(i)].width = width
    return ws


def export_all(con):
    """Return xlsx bytes with Players / Subscriptions / Payments / Attendance / Summary sheets."""
    wb = Workbook()
    wb.remove(wb.active)

    players = con.execute(
        "SELECT p.id, p.full_name, p.birth_date, p.gender, p.phone, p.guardian_name, p.guardian_phone, "
        "g.name_ar AS grp, p.join_date, p.status, p.notes FROM players p LEFT JOIN groups g ON g.id=p.group_id "
        "ORDER BY p.full_name"
    ).fetchall()
    _sheet(wb, "Players اللاعبين",
           ["ID", "الاسم", "تاريخ الميلاد", "الجنس", "الهاتف", "ولي الأمر", "هاتف ولي الأمر",
            "المجموعة", "تاريخ الانضمام", "الحالة", "ملاحظات"],
           [tuple(r) for r in players])

    subs = con.execute(
        "SELECT s.id, p.full_name, s.start_date, s.sessions_total, s.sessions_used, s.price, s.expiry_date, s.status "
        "FROM subscriptions s JOIN players p ON p.id=s.player_id ORDER BY s.start_date DESC"
    ).fetchall()
    _sheet(wb, "Subscriptions الاشتراكات",
           ["ID", "اللاعب", "تاريخ البداية", "الحصص الكلية", "الحصص المستخدمة", "السعر", "تاريخ الانتهاء", "الحالة"],
           [tuple(r) for r in subs])

    pays = con.execute(
        "SELECT pm.receipt_no, p.full_name, pm.amount, pm.date, pm.method, pm.note "
        "FROM payments pm JOIN players p ON p.id=pm.player_id ORDER BY pm.date DESC"
    ).fetchall()
    _sheet(wb, "Payments الدفعات",
           ["رقم الإيصال", "اللاعب", "المبلغ (دينار)", "التاريخ", "طريقة الدفع", "ملاحظة"],
           [tuple(r) for r in pays])

    att = con.execute(
        "SELECT a.session_date, p.full_name, g.name_ar, a.status, a.unpaid, a.marked_by "
        "FROM attendance a JOIN players p ON p.id=a.player_id LEFT JOIN groups g ON g.id=a.group_id "
        "ORDER BY a.session_date DESC"
    ).fetchall()
    _sheet(wb, "Attendance الحضور",
           ["التاريخ", "اللاعب", "المجموعة", "الحالة", "غير مدفوع", "سجّله"],
           [(r[0], r[1], r[2], {"present": "حاضر", "absent": "غائب", "excused": "معذور"}.get(r[3], r[3]),
             "نعم" if r[4] else "", r[5]) for r in att])

    month = date.today().strftime("%Y-%m")
    kpis = [
        ("اللاعبين الفعالين / Active players",
         con.execute("SELECT COUNT(*) c FROM players WHERE status='active'").fetchone()["c"]),
        ("إيراد هذا الشهر / Revenue this month (JD)",
         con.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date LIKE ?", (month + "%",)).fetchone()["s"]),
        ("اشتراكات فعالة / Active subscriptions",
         con.execute("SELECT COUNT(*) c FROM subscriptions WHERE status='active'").fetchone()["c"]),
        ("حصص غير مدفوعة / Unpaid sessions",
         con.execute("SELECT COUNT(*) c FROM attendance WHERE unpaid=1").fetchone()["c"]),
        ("تاريخ التصدير / Exported at", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]
    _sheet(wb, "Summary الملخص", ["البند / Item", "القيمة / Value"], kpis)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


PLAYER_TEMPLATE_HEADERS = ["الاسم الكامل*", "تاريخ الميلاد (YYYY-MM-DD)", "الجنس (M/F)", "هاتف اللاعب",
                           "اسم ولي الأمر", "هاتف ولي الأمر (07XXXXXXXX)", "المجموعة (اسمها بالعربي)", "ملاحظات"]


def players_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "Players"
    ws.sheet_view.rightToLeft = True
    ws.append(PLAYER_TEMPLATE_HEADERS)
    for c in ws[1]:
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
    ws.append(["عمر خالد", "2013-05-01", "M", "", "خالد أحمد", "0791234567", "ناشئين", "مثال — احذف هذا الصف"])
    for i in range(1, len(PLAYER_TEMPLATE_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 26
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def import_players(con, file_stream, suggest_group_fn):
    """Bulk-load players from a template xlsx. Returns (imported, skipped, errors)."""
    wb = load_workbook(file_stream)
    ws = wb.active
    imported, skipped, errors = 0, 0, []
    groups = {r["name_ar"].strip(): r["id"] for r in con.execute("SELECT id, name_ar FROM groups").fetchall()}
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or not row[0]:
            continue
        name = str(row[0]).strip()
        if "احذف هذا الصف" in (str(row[7] or "")):
            continue
        try:
            birth = str(row[1]).strip()[:10] if row[1] else ""
            gender = (str(row[2]).strip().upper() or "M") if row[2] else "M"
            gender = "F" if gender.startswith("F") or gender == "أنثى" else "M"
            phone = str(row[3] or "").strip()
            gname = str(row[4] or "").strip()
            gphone = str(row[5] or "").strip()
            grp_name = str(row[6] or "").strip()
            notes = str(row[7] or "").strip()
            group_id = groups.get(grp_name) or suggest_group_fn(con, birth, gender)
            dup = con.execute("SELECT id FROM players WHERE full_name=?", (name,)).fetchone()
            if dup:
                skipped += 1
                continue
            con.execute(
                "INSERT INTO players (full_name,birth_date,gender,phone,guardian_name,guardian_phone,"
                "group_id,join_date,notes,status) VALUES (?,?,?,?,?,?,?,?,?,'active')",
                (name, birth, gender, phone, gname, gphone, group_id, date.today().isoformat(), notes),
            )
            imported += 1
        except Exception as e:
            errors.append(f"صف {i}: {e}")
    con.commit()
    return imported, skipped, errors


def weekly_auto_export(con, exports_dir):
    """Write a dated full export to /exports if none exists in the last 7 days."""
    os.makedirs(exports_dir, exist_ok=True)
    existing = sorted(f for f in os.listdir(exports_dir) if f.startswith("academy-export-"))
    if existing:
        last = existing[-1][len("academy-export-"):len("academy-export-") + 10]
        try:
            if (date.today() - date.fromisoformat(last)).days < 7:
                return None
        except ValueError:
            pass
    path = os.path.join(exports_dir, f"academy-export-{date.today().isoformat()}.xlsx")
    with open(path, "wb") as f:
        f.write(export_all(con))
    return path
