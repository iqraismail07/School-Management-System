"""SMS-SCHOOL — School Management System backend (Flask + SQLite).

KG to 10th. Roles: super_admin, principal, teacher, student.
Every route carries @auth(...) / @auth_public; the deny-by-default startup
self-test verify_auth_coverage() refuses to run quietly with gaps.
"""
import os
import re
import uuid
import calendar
import json
import shutil
import sqlite3
import traceback
from functools import wraps
from datetime import date, datetime, timedelta
from decimal import Decimal
import urllib.request
import urllib.error

from flask import Flask, request, jsonify, session, send_from_directory, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(dotenv_path=_env_path)
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SMS_SECRET", "sms-school-secret-change-me")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_WRITE_ROOT = "/tmp" if os.environ.get("VERCEL") else BASE_DIR
DATA_DIR = os.path.join(_WRITE_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "sms.db")
os.makedirs(DATA_DIR, exist_ok=True)
UPLOAD_DIR = os.path.join(_WRITE_ROOT, "uploads")
PHOTO_DIR = os.path.join(UPLOAD_DIR, "photos")
NOTES_DIR = os.path.join(UPLOAD_DIR, "notes")
LOGO_DIR = os.path.join(UPLOAD_DIR, "logos")
for _d in (UPLOAD_DIR, PHOTO_DIR, NOTES_DIR, LOGO_DIR):
    os.makedirs(_d, exist_ok=True)

PHOTO_ALLOWED_EXT = {"jpg", "jpeg", "png"}
NOTE_ALLOWED_EXT = {"pdf"}
LOGO_ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
LOGO_MAX_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


# ---------- db helpers ----------
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def json_safe(d):
    for k, v in list(d.items()):
        if isinstance(v, Decimal):
            d[k] = float(v)
        elif isinstance(v, (date, datetime)):
            d[k] = v.isoformat()
    return d


def q(sql, args=(), one=False):
    c = conn()
    try:
        cur = c.cursor()
        cur.execute(sql, args)
        rows = cur.fetchall()
    finally:
        c.close()
    out = [json_safe(dict(r)) for r in rows]
    if one:
        return out[0] if out else None
    return out


def run(sql, args=()):
    c = conn()
    try:
        cur = c.cursor()
        cur.execute(sql, args)
        rid = cur.fetchone()[0] if cur.description else None
        c.commit()
    finally:
        c.close()
    return rid


# ---------- first-run database initialization ----------
SQL_FILES = ["schema.sql", "v2.sql", "v3.sql", "v4.sql", "v5.sql", "v6.sql",
             "v7.sql", "v8.sql", "v9.sql", "v10.sql", "seed.sql"]


def ensure_db():
    """Create and seed backend/data/sms.db on first run.

    Skips when tables already exist. Any failure is printed loudly
    (with a traceback) and never swallowed."""
    try:
        c = conn()
        try:
            n = c.execute("SELECT count(*) FROM sqlite_master "
                          "WHERE type='table'").fetchone()[0]
        finally:
            c.close()
        if not n:
            db_dir = os.path.join(os.path.dirname(BASE_DIR), "database")
            for fn in SQL_FILES:
                path = os.path.join(db_dir, fn)
                with open(path, encoding="utf-8") as fh:
                    script = fh.read()
                cc = sqlite3.connect(DB_PATH)
                try:
                    cc.execute("PRAGMA foreign_keys=ON")
                    cc.executescript(script)
                    cc.commit()
                finally:
                    cc.close()
            _seed_procedural()
            print("ensure_db: database created and seeded at %s" % DB_PATH)
    except Exception:
        print("!! ensure_db FAILED - the database was NOT initialized:")
        traceback.print_exc()
    # Part 3 migration — display_name on users. Runs on EVERY boot (fresh or
    # pre-existing sms.db), AFTER the first-run guard above, so DBs created
    # by the previous version get the column + backfill too.
    try:
        _ensure_display_name_column()
    except Exception:
        print("!! display_name migration FAILED:")
        traceback.print_exc()
    try:
        _ensure_ai_tables()
    except Exception:
        print("!! ai_tables migration FAILED:")
        traceback.print_exc()


def _ensure_display_name_column():
    """Add users.display_name when missing and backfill from username."""
    cc = sqlite3.connect(DB_PATH)
    try:
        cols = [r[1] for r in cc.execute("PRAGMA table_info(users)").fetchall()]
        if "display_name" not in cols:
            cc.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
            print("migration: added users.display_name column")
        n = cc.execute(
            "UPDATE users SET display_name = username "
            "WHERE display_name IS NULL OR display_name = ''").rowcount
        if n:
            print("migration: backfilled display_name for %d user(s)" % n)
        cc.commit()
    finally:
        cc.close()


def _ensure_ai_tables():
    """Create ai_chats table and default settings if missing on existing databases."""
    cc = sqlite3.connect(DB_PATH)
    try:
        cc.execute("PRAGMA foreign_keys=ON")
        cc.execute("""
            CREATE TABLE IF NOT EXISTS ai_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cc.execute("CREATE INDEX IF NOT EXISTS idx_ai_chats_user ON ai_chats(user_id, id)")
        cc.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('gemini_system_prompt', 'You are the helpful AI assistant for Anjum Grammar School. Answer questions clearly, accurately, and politely in English or Urdu.')")
        cc.commit()
    finally:
        cc.close()


def _seed_procedural():
    """Python ports of seed.sql's four PostgreSQL DO blocks (B1-B4)
    (marked -- SQLITE-PORT-BLOCK-N in seed.sql; executescript skips them),
    plus B5/B6: seed sections that had to move here because they depend on
    the subjects created by B1 (SQLite runs this file's SQL before B1)."""
    # B1 - subjects per class band (every class row incl. sections)
    kg5 = ['Urdu', 'English', 'Mathematics', 'Islamiat', 'Nazra Quran']
    s68 = ['Urdu', 'English', 'Mathematics', 'Science', 'Computer',
           'Islamiat', 'Tarjuma-tul-Quran']
    s910 = ['Urdu', 'English', 'Mathematics', 'Physics', 'Chemistry',
            'Biology', 'Computer Science', 'Islamiat', 'Pak Studies',
            'Tarjuma-tul-Quran']
    for cl in q("SELECT id, name FROM classes"):
        if cl["name"] in ('KG', '1', '2', '3', '4', '5'):
            lst = kg5
        elif cl["name"] in ('6', '7', '8'):
            lst = s68
        else:
            lst = s910
        for subj in lst:
            run("INSERT INTO subjects (class_id, name) VALUES (?, ?) "
                "ON CONFLICT (class_id, name) DO NOTHING",
                (cl["id"], subj))

    # B5 - demo teacher assignments (needs subjects from B1)
    for tname, cname, sec, subjs in (
            ("Ahmed Khan", "8", "A", ["Mathematics", "Science"]),
            ("Sara Bibi", "5", "A", ["English", "Urdu"]),
            ("Imran Shah", "10", "A", ["Physics", "Mathematics"])):
        t = q("SELECT id FROM teachers WHERE name=?", (tname,), one=True)
        cl = q("SELECT id FROM classes WHERE name=? AND section=?",
               (cname, sec), one=True)
        if not t or not cl:
            continue
        for sname in subjs:
            s = q("SELECT id FROM subjects WHERE class_id=? AND name=?",
                  (cl["id"], sname), one=True)
            if s:
                run("INSERT INTO teacher_assignment "
                    "(teacher_id, class_id, subject_id) VALUES (?, ?, ?) "
                    "ON CONFLICT (teacher_id, class_id, subject_id) "
                    "DO NOTHING", (t["id"], cl["id"], s["id"]))

    # B6 - demo exam marks for 8-A First Term (needs subjects from B1)
    ex = q("SELECT id FROM exams WHERE name='First Term' AND year=2026 "
           "LIMIT 1", one=True)
    c8a = q("SELECT id FROM classes WHERE name='8' AND section='A'",
            one=True)
    if ex and c8a:
        for sname, subj, obt in (
                ("Ali Raza", "Mathematics", 85),
                ("Ali Raza", "Science", 78),
                ("Bilal Hussain", "Mathematics", 72),
                ("Bilal Hussain", "Science", 88),
                ("Maryam Siddiq", "Mathematics", 91),
                ("Maryam Siddiq", "Science", 82),
                ("Daniyal Khan", "Mathematics", 64),
                ("Daniyal Khan", "Science", 70)):
            st = q("SELECT id FROM students WHERE name=?", (sname,), one=True)
            su = q("SELECT id FROM subjects WHERE class_id=? AND name=?",
                   (c8a["id"], subj), one=True)
            if st and su:
                run("INSERT INTO exam_marks "
                    "(exam_id, student_id, subject_id, obtained, total) "
                    "VALUES (?, ?, ?, ?, 100) "
                    "ON CONFLICT (exam_id, student_id, subject_id) "
                    "DO NOTHING", (ex["id"], st["id"], su["id"], obt))

    today = date.today()
    cur_month = today.strftime('%Y-%m')
    due = today.replace(day=10).isoformat()
    heads = {r["class_id"]: r["monthly_amount"]
             for r in q("SELECT class_id, monthly_amount FROM fee_heads")}

    # B2 - current-month invoices for every active student
    n = 0
    for st in q("SELECT id, class_id FROM students WHERE status='Active' "
                "ORDER BY id"):
        amt = heads.get(st["class_id"])
        if amt is None:
            continue
        if q("SELECT 1 FROM fee_invoices WHERE student_id=? AND fee_month=?",
             (st["id"], cur_month), one=True):
            continue
        n += 1
        rcp = 'R-' + cur_month.replace('-', '') + '-' + str(n).zfill(3)
        run("INSERT INTO fee_invoices (student_id, fee_month, amount, late_fee,"
            " concession, total, paid, status, due_date, receipt_no) "
            "VALUES (?, ?, ?, 0, 0, ?, 0, 'UNPAID', ?, ?)",
            (st["id"], cur_month, amt, amt, due, rcp))

    # B3 - one PARTIAL invoice with a payment (first invoice)
    inv = q("SELECT id, total FROM fee_invoices ORDER BY id LIMIT 1", one=True)
    sup = q("SELECT id FROM users WHERE username='superadmin'", one=True)
    if inv and sup and not q("SELECT 1 FROM fee_payments "
                             "WHERE receipt_no='RCP-SEED-001'", one=True):
        half = float(inv["total"]) / 2
        run("INSERT INTO fee_payments (invoice_id, amount, method, receipt_no,"
            " received_by) VALUES (?, ?, 'Cash', 'RCP-SEED-001', ?)",
            (inv["id"], half, sup["id"]))
        run("UPDATE fee_invoices SET paid=?, status='PARTIAL' WHERE id=?",
            (half, inv["id"]))

    # B4 - one OVERDUE invoice from last month (first active student)
    prev = today.replace(day=1) - timedelta(days=1)
    last_month = prev.strftime('%Y-%m')
    due4 = prev.replace(day=10).isoformat()
    s1 = q("SELECT id, class_id FROM students WHERE status='Active' "
           "ORDER BY id LIMIT 1", one=True)
    if s1:
        amt4 = heads.get(s1["class_id"])
        if amt4 is not None and not q(
                "SELECT 1 FROM fee_invoices WHERE student_id=? AND fee_month=?",
                (s1["id"], last_month), one=True):
            run("INSERT INTO fee_invoices (student_id, fee_month, amount,"
                " late_fee, concession, total, paid, status, due_date,"
                " receipt_no) VALUES (?, ?, ?, 0, 0, ?, 0, 'OVERDUE', ?, ?)",
                (s1["id"], last_month, amt4, amt4, due4,
                 'R-' + last_month.replace('-', '') + '-001'))


# ---------- centralized authorization ----------
# EVERY route must use @auth(...) or @auth_public. The startup self-test
# verify_auth_coverage() (bottom of file) fails loudly if any route lacks
# a permission declaration (deny-by-default).
ROLES = ("super_admin", "principal", "clerk", "teacher", "student")
# SPEC UPDATE 9: default password for EVERY newly created user.
# Creation endpoints take no password field (ignored if sent).
DEFAULT_PASSWORD = "1234567"
AUTH_GAPS = []  # filled by verify_auth_coverage(); exposed via /api/health


def _active_user():
    """Logged-in user, or None. Deactivated accounts are logged out."""
    u = session.get("user")
    if not u:
        return None
    if not q("SELECT 1 FROM users WHERE id=? AND is_active=TRUE", (u["id"],), one=True):
        session.clear()
        return None
    return u


def auth(*roles):
    """THE single permission decorator.

    @auth()                              -> any logged-in (and active) user
    @auth("super_admin", "principal")     -> only the listed roles
    @auth_public                          -> no login needed (use sparingly)
    """
    for r in roles:
        assert r in ROLES, "unknown role %r in @auth" % (r,)

    def deco(f):
        @wraps(f)
        def w(*a, **kw):
            u = _active_user()
            if not u:
                return jsonify({"error": "login required"}), 401
            if roles and u["role"] not in roles:
                return jsonify({"error": "forbidden"}), 403
            return f(*a, **kw)
        w.__sms_auth__ = {"roles": roles if roles else ("<any-authenticated>",),
                          "public": False}
        return w
    return deco


def auth_public(f):
    """Public endpoint — no login required. Only for: login, public settings,
    /api/health, and the frontend root."""
    @wraps(f)
    def w(*a, **kw):
        return f(*a, **kw)
    w.__sms_auth__ = {"roles": ("<public>",), "public": True}
    return w


def my_student_id():
    """Student row id linked to the logged-in user (None if not a student)."""
    return q("SELECT linked_student_id AS v FROM users WHERE id=?",
             (session["user"]["id"],), one=True)["v"]


def my_teacher_id():
    """Teacher row id linked to the logged-in user (None if not a teacher)."""
    return q("SELECT linked_teacher_id AS v FROM users WHERE id=?",
             (session["user"]["id"],), one=True)["v"]


def teacher_class_ids(tid):
    return [r["v"] for r in q(
        "SELECT DISTINCT class_id AS v FROM teacher_assignment WHERE teacher_id=?",
        (tid,))]


def teacher_subject_ids(tid):
    return [r["v"] for r in q(
        "SELECT DISTINCT subject_id AS v FROM teacher_assignment WHERE teacher_id=?",
        (tid,))]


def require_student_ownership(sid):
    """Ownership gate for student-scoped data. super_admin/principal may read
    anyone; a teacher only students of assigned classes; a student only their
    own record. Returns None when allowed, else a (json, 403) tuple."""
    role = session["user"]["role"]
    if role in ("super_admin", "principal", "clerk"):
        return None
    if role == "teacher":
        tid = my_teacher_id()
        stu = q("SELECT class_id FROM students WHERE id=?", (sid,), one=True)
        if stu and tid and stu["class_id"] in teacher_class_ids(tid):
            return None
        return jsonify({"error": "forbidden"}), 403
    if role == "student":
        if my_student_id() == sid:
            return None
        return jsonify({"error": "forbidden"}), 403
    return jsonify({"error": "forbidden"}), 403


def audit(action, entity=None, entity_id=None, details=None):
    """Record a sensitive action. Must never break the request it logs."""
    u = session.get("user") or {}
    try:
        run("""INSERT INTO audit_log (user_id, username, role, action, entity, entity_id, details)
               VALUES (?,?,?,?,?,?,?)""",
            (u.get("id"), u.get("username", ""), u.get("role", ""), action, entity,
             None if entity_id is None else str(entity_id),
             json.dumps(details or {})))
    except Exception:
        pass


def grade_of(pct):
    if pct is None:
        return None
    if pct >= 90:
        return "A+"
    if pct >= 80:
        return "A"
    if pct >= 70:
        return "B"
    if pct >= 60:
        return "C"
    if pct >= 50:
        return "D"
    if pct >= 40:
        return "E"
    return "F"


def _setting(key, default=""):
    r = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return r["value"] if r else default


def _next_admission_no():
    prefix = "SMS-%d-" % date.today().year
    mx = q("SELECT admission_no FROM students WHERE admission_no LIKE ? "
           "ORDER BY admission_no DESC LIMIT 1", (prefix + "%",), one=True)
    n = int(mx["admission_no"].rsplit("-", 1)[1]) + 1 if mx else 1
    return "%s%03d" % (prefix, n)


def _recalc_invoice(iid):
    """Recompute an invoice's total/paid/status from its parts. Returns dict."""
    inv = q("SELECT amount, late_fee, concession, due_date FROM fee_invoices WHERE id=?",
            (iid,), one=True)
    if not inv:
        return None
    total = round(float(inv["amount"] or 0) + float(inv["late_fee"] or 0)
                  - float(inv["concession"] or 0), 2)
    paid = round(float(q("SELECT COALESCE(SUM(amount),0) AS v FROM fee_payments "
                         "WHERE invoice_id=?", (iid,), one=True)["v"] or 0), 2)
    if paid >= total and total > 0:
        status = "PAID"
    elif paid > 0:
        status = "PARTIAL"
    else:
        status = "UNPAID"
    if status in ("UNPAID", "PARTIAL") and inv["due_date"] \
            and str(inv["due_date"]) < date.today().isoformat():
        status = "OVERDUE"
    run("UPDATE fee_invoices SET total=?, paid=?, status=? WHERE id=?",
        (total, paid, status, iid))
    return {"total": total, "paid": paid, "status": status}


def _save_upload(f, dest_dir, prefix, allowed_ext):
    orig = f.filename or ""
    ext = orig.rsplit(".", 1)[-1].lower() if "." in orig else ""
    if ext not in allowed_ext:
        raise ValueError("file type not allowed (allowed: %s)"
                         % ", ".join(sorted(allowed_ext)))
    data = f.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("file too large (max 10MB)")
    stored = "%s_%s.%s" % (prefix, uuid.uuid4().hex[:8], ext)
    with open(os.path.join(dest_dir, stored), "wb") as fh:
        fh.write(data)
    return stored


def _remove_upload(dest_dir, stored):
    try:
        if stored:
            os.remove(os.path.join(dest_dir, os.path.basename(stored)))
    except OSError:
        pass


def _body():
    return request.get_json(force=True) or {}


# ---------- session ----------
@app.post("/api/login")
@auth_public
def login():
    d = _body()
    u = q("SELECT * FROM users WHERE username=? AND is_active=TRUE",
          (d.get("username"),), one=True)
    if not u or not check_password_hash(u["password_hash"], d.get("password", "")):
        return jsonify({"error": "invalid username or password"}), 401
    session["user"] = {"id": u["id"], "username": u["username"], "role": u["role"]}
    return jsonify({"ok": True, "user": session["user"]})


@app.post("/api/logout")
@auth()
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
@auth()
def me():
    u = dict(session["user"])
    full = q("SELECT linked_student_id, linked_teacher_id, display_name "
             "FROM users WHERE id=?", (u["id"],), one=True) or {}
    u.update(full)
    if u.get("linked_student_id"):
        s = q("SELECT name FROM students WHERE id=?",
              (u["linked_student_id"],), one=True)
        if s:
            u["student_name"] = s["name"]
    if u.get("linked_teacher_id"):
        t = q("SELECT name FROM teachers WHERE id=?",
              (u["linked_teacher_id"],), one=True)
        if t:
            u["teacher_name"] = t["name"]
    return jsonify(u)


@app.get("/api/me/profile")
@auth()
def my_profile():
    u = session["user"]
    out = {"user": {"id": u["id"], "username": u["username"],
                    "role": u["role"],
                    "display_name": u.get("display_name") or u["username"]}}
    full = q("SELECT linked_student_id, linked_teacher_id, display_name FROM users "
             "WHERE id=?", (u["id"],), one=True) or {}
    if full.get("display_name"):
        out["user"]["display_name"] = full["display_name"]
    if u["role"] == "teacher" and full.get("linked_teacher_id"):
        t = q("SELECT id, name, phone, qualification, photo_path, status "
              "FROM teachers WHERE id=?",
              (full["linked_teacher_id"],), one=True)
        if t:
            t["photo_url"] = ("/api/teachers/%d/photo" % t["id"]
                              if t.pop("photo_path") else None)
            out["teacher"] = t
            out["assignments"] = q(
                """SELECT ta.class_id, c.name AS class_name, c.section,
                          ta.subject_id, s.name AS subject_name
                   FROM teacher_assignment ta
                   JOIN classes c ON c.id=ta.class_id
                   JOIN subjects s ON s.id=ta.subject_id
                   WHERE ta.teacher_id=?
                   ORDER BY c.name, c.section, s.name""", (t["id"],))
    if u["role"] == "student" and full.get("linked_student_id"):
        st = q("""SELECT st.*, c.name AS class_name, c.section
                  FROM students st LEFT JOIN classes c ON c.id=st.class_id
                  WHERE st.id=?""",
               (full["linked_student_id"],), one=True)
        if st:
            st["photo_url"] = ("/api/students/%d/photo" % st["id"]
                               if st.pop("photo_path") else None)
            out["student"] = st
            marks = q(
                """SELECT e.name AS exam_name, e.year,
                          COALESCE(SUM(em.obtained),0) AS total_obtained,
                          COALESCE(SUM(em.total),0) AS total_max
                   FROM exams e
                   LEFT JOIN exam_marks em
                     ON em.exam_id=e.id AND em.student_id=?
                   WHERE e.class_id=?
                   GROUP BY e.id, e.name, e.year
                   ORDER BY e.year DESC, e.id""",
                (st["id"], st["class_id"]))
            for m in marks:
                pct = round(100.0 * float(m["total_obtained"])
                            / float(m["total_max"]), 1) \
                    if float(m["total_max"]) else 0
                m["percentage"] = pct
                m["grade"] = grade_of(pct)
            out["marks_summary"] = marks
    return jsonify(out)


@app.post("/api/me/password")
@auth()
def change_password():
    d = _body()
    old, new = d.get("old", ""), d.get("new", "")
    if len(new) < 6:
        return jsonify({"error": "new password must be at least 6 characters"}), 400
    u = q("SELECT * FROM users WHERE id=?", (session["user"]["id"],), one=True)
    if not u or not check_password_hash(u["password_hash"], old):
        return jsonify({"error": "old password is wrong"}), 400
    run("UPDATE users SET password_hash=? WHERE id=?",
        (generate_password_hash(new), session["user"]["id"]))
    audit("password_change", "user", session["user"]["id"], {})
    return jsonify({"ok": True})


@app.get("/api/health")
@auth_public
def health():
    return jsonify({"ok": True, "auth_gaps": AUTH_GAPS})


# ---------- users (super_admin + principal manage) ----------
@app.get("/api/users")
@auth("super_admin")
def users_list():
    return jsonify(q(
        """SELECT u.id, u.username, u.display_name, u.role, u.is_active,
                  u.linked_student_id, u.linked_teacher_id,
                  s.name AS student_name, t.name AS teacher_name,
                  u.created_at
           FROM users u
           LEFT JOIN students s ON s.id=u.linked_student_id
           LEFT JOIN teachers t ON t.id=u.linked_teacher_id
           ORDER BY u.id"""))


def _valid_display_name(d):
    """Return (ok, value-or-error-message) for a display_name payload value."""
    name = d.get("display_name")
    if not isinstance(name, str) or not name.strip():
        return False, "display_name must be a non-empty string"
    name = name.strip()
    if len(name) > 80:
        return False, "display_name must be at most 80 characters"
    return True, name


@app.put("/api/users/<int:uid>")
@auth("super_admin")
def user_update(uid):
    """super_admin only: edit any user's display_name, role, is_active."""
    target = q("SELECT id, username, role FROM users WHERE id=?",
               (uid,), one=True)
    if not target:
        return jsonify({"error": "user not found"}), 404
    d = _body()
    allowed_keys = ("display_name", "role", "is_active")
    if not any(k in d for k in allowed_keys):
        return jsonify({"error": "nothing to update; send one of: "
                                 + ", ".join(allowed_keys)}), 400
    sets, vals = [], []
    if "display_name" in d:
        ok, name = _valid_display_name(d)
        if not ok:
            return jsonify({"error": name}), 400
        sets.append("display_name=?")
        vals.append(name)
    if "role" in d:
        if d["role"] not in ROLES:
            return jsonify({"error": "role must be one of: "
                                     + ", ".join(ROLES)}), 400
        sets.append("role=?")
        vals.append(d["role"])
    if "is_active" in d:
        sets.append("is_active=?")
        vals.append(bool(d["is_active"]))
    run("UPDATE users SET " + ", ".join(sets) + " WHERE id=?",
        tuple(vals) + (uid,))
    audit("user_update", "user", uid,
          {"changed": sorted(k for k in allowed_keys if k in d),
           "target_username": target["username"]})
    u = q("SELECT id, username, display_name, role, is_active FROM users "
          "WHERE id=?", (uid,), one=True)
    return jsonify({"ok": True, "user": u})


@app.post("/api/users")
@auth("super_admin")
def user_add():
    d = _body()
    username = (d.get("username") or "").strip()
    role = d.get("role")  # password is always DEFAULT_PASSWORD (SPEC UPDATE 9)
    if not username:
        return jsonify({"error": "username is required"}), 400
    if role not in ROLES:
        return jsonify({"error": "role must be one of: " + ", ".join(ROLES)}), 400
    if q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
        return jsonify({"error": "username already taken"}), 400
    lsid = d.get("linked_student_id")
    ltid = d.get("linked_teacher_id")
    if lsid and not q("SELECT 1 FROM students WHERE id=?", (lsid,), one=True):
        return jsonify({"error": "linked student not found"}), 404
    if ltid and not q("SELECT 1 FROM teachers WHERE id=?", (ltid,), one=True):
        return jsonify({"error": "linked teacher not found"}), 404
    rid = run(
        """INSERT INTO users (username, password_hash, role, linked_student_id, linked_teacher_id)
           VALUES (?,?,?,?,?) RETURNING id""",
        (username, generate_password_hash(DEFAULT_PASSWORD), role, lsid, ltid))
    audit("user_create", "user", rid, {"username": username, "role": role})
    return jsonify({"ok": True, "id": rid})


@app.post("/api/users/<int:uid>/activate")
@auth("super_admin")
def user_activate(uid):
    if not q("SELECT 1 FROM users WHERE id=?", (uid,), one=True):
        return jsonify({"error": "user not found"}), 404
    run("UPDATE users SET is_active=TRUE WHERE id=?", (uid,))
    audit("user_activate", "user", uid, {})
    return jsonify({"ok": True})


@app.post("/api/users/<int:uid>/deactivate")
@auth("super_admin")
def user_deactivate(uid):
    if uid == session["user"]["id"]:
        return jsonify({"error": "cannot deactivate yourself"}), 400
    if not q("SELECT 1 FROM users WHERE id=?", (uid,), one=True):
        return jsonify({"error": "user not found"}), 404
    run("UPDATE users SET is_active=FALSE WHERE id=?", (uid,))
    audit("user_deactivate", "user", uid, {})
    return jsonify({"ok": True})


@app.post("/api/users/<int:uid>/reset-password")
@auth("super_admin")
def user_reset_password(uid):
    """The ONLY way to change another user's password. Everyone else uses
    POST /api/me/password (own password, requires old password)."""
    u = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not u:
        return jsonify({"error": "user not found"}), 404
    d = _body()
    new = d.get("new_password") or ""
    if len(new) < 6:
        return jsonify({"error": "new password must be at least 6 characters"}), 400
    run("UPDATE users SET password_hash=? WHERE id=?",
        (generate_password_hash(new), uid))
    audit("user_reset_password", "user", uid, {"username": u["username"]})
    return jsonify({"ok": True})


@app.delete("/api/users/<int:uid>")
@auth("super_admin")
def user_del(uid):
    if uid == session["user"]["id"]:
        return jsonify({"error": "cannot delete yourself"}), 400
    u = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not u:
        return jsonify({"error": "user not found"}), 404
    reasons = []
    tid, sid = u["linked_teacher_id"], u["linked_student_id"]
    if tid:
        if q("SELECT 1 FROM teacher_assignment WHERE teacher_id=? LIMIT 1",
             (tid,), one=True):
            reasons.append("teacher assignments")
        if q("SELECT 1 FROM salaries WHERE teacher_id=? LIMIT 1",
             (tid,), one=True):
            reasons.append("salary rows")
        if q("SELECT 1 FROM attendance WHERE marked_by=? LIMIT 1",
             (uid,), one=True):
            reasons.append("marked attendance")
    if sid:
        if q("SELECT 1 FROM attendance WHERE student_id=? LIMIT 1",
             (sid,), one=True):
            reasons.append("attendance records")
        if q("SELECT 1 FROM exam_marks WHERE student_id=? LIMIT 1",
             (sid,), one=True):
            reasons.append("exam marks")
        if q("SELECT 1 FROM fee_invoices WHERE student_id=? LIMIT 1",
             (sid,), one=True):
            reasons.append("fee invoices")
        if q("SELECT 1 FROM fee_payments WHERE invoice_id IN "
             "(SELECT id FROM fee_invoices WHERE student_id=?) LIMIT 1",
             (sid,), one=True):
            reasons.append("fee payments")
        if q("SELECT 1 FROM fee_concessions WHERE student_id=? LIMIT 1",
             (sid,), one=True):
            reasons.append("fee concessions")
        if q("SELECT 1 FROM certificates WHERE student_id=? LIMIT 1",
             (sid,), one=True):
            reasons.append("certificates")
    if reasons:
        return jsonify({"error": "Cannot delete user: linked %s has %s. "
                                 "Deactivate the user instead — this keeps all records safe."
                                 % (u["role"], ", ".join(reasons))}), 400
    run("DELETE FROM users WHERE id=?", (uid,))
    audit("user_delete", "user", uid, {"username": u["username"]})
    return jsonify({"ok": True})


# ---------- dashboard ----------
@app.get("/api/stats")
@auth("super_admin", "principal")
def stats():
    m = date.today().strftime("%Y-%m")
    out = q(
        """SELECT
           (SELECT COUNT(*) FROM students WHERE status='Active') AS students,
           (SELECT COUNT(*) FROM teachers WHERE status='Active') AS teachers,
           (SELECT COUNT(*) FROM admissions WHERE status='PENDING') AS admissions_pending,
           (SELECT COUNT(*) FROM admissions) AS admissions_total,
           (SELECT COALESCE(SUM(amount),0) FROM fee_payments
             WHERE strftime('%Y-%m', paid_at)=?) AS fees_collected_month,
           (SELECT COALESCE(SUM(total-paid),0) FROM fee_invoices
             WHERE status IN ('UNPAID','PARTIAL','OVERDUE')) AS fees_pending,
           (SELECT CASE WHEN COUNT(*)=0 THEN 0 ELSE
                    ROUND(100.0*COUNT(*) FILTER (WHERE status='PRESENT')/COUNT(*),1) END
            FROM attendance WHERE att_date=CURRENT_DATE) AS attendance_today_pct,
           (SELECT COUNT(*) FROM classes) AS classes,
           (SELECT COUNT(*) FROM exams) AS exams""", (m,), one=True)
    # gazette: each class's latest exam, top-5 rows (empty rows if no exam yet)
    gaz = []
    classes = q(
        """SELECT id, name, section FROM classes
           ORDER BY CASE name WHEN 'KG' THEN -1 ELSE CAST(name AS INTEGER) END, section""")
    for c in classes:
        ex = q("""SELECT id, name FROM exams WHERE class_id=?
                  ORDER BY year DESC, id DESC LIMIT 1""",
               (c["id"],), one=True)
        entry = {"class_id": c["id"],
                 "class_label": "%s-%s" % (c["name"], c["section"]),
                 "exam_id": None, "exam_name": None, "rows": []}
        if ex:
            entry["exam_id"] = ex["id"]
            entry["exam_name"] = ex["name"]
            rows = q(
                """SELECT RANK() OVER (ORDER BY COALESCE(SUM(em.obtained),0) DESC)
                            AS position,
                          st.name AS student_name, st.admission_no,
                          COALESCE(SUM(em.obtained),0) AS total_obtained,
                          COALESCE(SUM(em.total),0) AS total_max
                   FROM students st
                   LEFT JOIN exam_marks em
                     ON em.student_id=st.id AND em.exam_id=?
                   WHERE st.class_id=? AND st.status='Active'
                   GROUP BY st.id, st.name, st.admission_no
                   ORDER BY position LIMIT 5""", (ex["id"], c["id"]))
            for r in rows:
                pct = round(100.0 * float(r["total_obtained"])
                            / float(r["total_max"]), 1) \
                    if float(r["total_max"]) else 0
                r["percentage"] = pct
                r["grade"] = grade_of(pct)
                del r["total_max"]
            entry["rows"] = rows
        gaz.append(entry)
    out["gazette"] = gaz
    return jsonify(out)


# ---------- classes & subjects ----------
@app.get("/api/classes")
@auth()
def classes_list():
    return jsonify(q(
        """SELECT c.id, c.name, c.section,
                  (SELECT COUNT(*) FROM students s
                    WHERE s.class_id=c.id AND s.status='Active') AS student_count
           FROM classes c ORDER BY c.name, c.section"""))


@app.post("/api/classes")
@auth("super_admin", "principal")
def class_add():
    d = _body()
    name = (d.get("name") or "").strip()
    section = (d.get("section") or "A").strip() or "A"
    if not name:
        return jsonify({"error": "name is required"}), 400
    try:
        rid = run("INSERT INTO classes (name, section) VALUES (?,?) RETURNING id",
                  (name, section))
    except sqlite3.IntegrityError:
        return jsonify({"error": "class already exists"}), 400
    audit("class_create", "class", rid, {"name": name, "section": section})
    return jsonify({"ok": True, "id": rid})


@app.get("/api/subjects")
@auth()
def subjects_list():
    where, args = ["1=1"], []
    if request.args.get("class_id"):
        where.append("s.class_id=?")
        args.append(int(request.args["class_id"]))
    return jsonify(q(
        """SELECT s.id, s.class_id, c.name AS class_name, c.section, s.name
           FROM subjects s JOIN classes c ON c.id=s.class_id
           WHERE %s ORDER BY c.name, c.section, s.name""" % " AND ".join(where),
        args))


@app.post("/api/subjects")
@auth("super_admin", "principal")
def subject_add():
    d = _body()
    cid = d.get("class_id")
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not q("SELECT 1 FROM classes WHERE id=?", (cid,), one=True):
        return jsonify({"error": "class not found"}), 404
    try:
        rid = run("INSERT INTO subjects (class_id, name) VALUES (?,?) RETURNING id",
                  (cid, name))
    except sqlite3.IntegrityError:
        return jsonify({"error": "subject already exists for this class"}), 400
    return jsonify({"ok": True, "id": rid})


@app.delete("/api/subjects/<int:sid>")
@auth("super_admin", "principal")
def subject_del(sid):
    if not q("SELECT 1 FROM subjects WHERE id=?", (sid,), one=True):
        return jsonify({"error": "subject not found"}), 404
    run("DELETE FROM subjects WHERE id=?", (sid,))
    return jsonify({"ok": True})


# ---------- admissions ----------
@app.get("/api/admissions")
@auth("super_admin", "principal", "clerk")
def admissions_list():
    where, args = ["1=1"], []
    if request.args.get("status") in ("PENDING", "APPROVED", "REJECTED"):
        where.append("status=?")
        args.append(request.args["status"])
    return jsonify(q("SELECT * FROM admissions WHERE %s ORDER BY id DESC"
                     % " AND ".join(where), args))


@app.post("/api/admissions")
@auth("super_admin", "clerk")
def admission_add():
    d = _body()
    name = (d.get("applicant_name") or "").strip()
    if not name:
        return jsonify({"error": "applicant_name is required"}), 400
    if not (d.get("apply_class") or "").strip():
        return jsonify({"error": "apply_class is required"}), 400
    rid = run(
        """INSERT INTO admissions
           (applicant_name, father_name, gender, dob, apply_class,
            guardian_phone, address)
           VALUES (?,?,?,?,?,?,?) RETURNING id""",
        (name, d.get("father_name"), d.get("gender"), d.get("dob") or None,
         d["apply_class"].strip(), d.get("guardian_phone"), d.get("address")))
    audit("admission_create", "admission", rid, {"applicant_name": name})
    return jsonify({"ok": True, "id": rid})


@app.post("/api/admissions/<int:aid>/approve")
@auth("super_admin", "clerk")
def admission_approve(aid):
    d = _body()
    adm = q("SELECT * FROM admissions WHERE id=?", (aid,), one=True)
    if not adm:
        return jsonify({"error": "admission not found"}), 404
    if adm["status"] != "PENDING":
        return jsonify({"error": "admission already decided"}), 400
    class_id = d.get("class_id")
    if not class_id or not q("SELECT 1 FROM classes WHERE id=?",
                             (class_id,), one=True):
        return jsonify({"error": "class_id is required"}), 400
    adm_no = _next_admission_no()
    gender = adm["gender"] if adm["gender"] in ("Male", "Female") else None
    sid = run(
        """INSERT INTO students
           (admission_no, name, father_name, gender, dob, class_id,
            guardian_name, guardian_phone, address, status)
           VALUES (?,?,?,?,?,?,?,?,?,'Active') RETURNING id""",
        (adm_no, adm["applicant_name"], adm["father_name"], gender,
         adm["dob"], class_id, None, adm["guardian_phone"], adm["address"]))
    run("UPDATE admissions SET status='APPROVED', decided_at=CURRENT_TIMESTAMP, "
        "student_id=? WHERE id=?", (sid, aid))
    uid = None
    if d.get("make_login"):
        username = (d.get("username") or "").strip()
        if not username:
            return jsonify({"error": "username required for login"}), 400
        if q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            return jsonify({"error": "username already taken"}), 400
        uid = run(
            """INSERT INTO users (username, password_hash, role, linked_student_id)
               VALUES (?,?,'student',?) RETURNING id""",
            (username, generate_password_hash(DEFAULT_PASSWORD), sid))
    audit("admission_approve", "admission", aid,
          {"student_id": sid, "admission_no": adm_no, "login_created": bool(uid)})
    return jsonify({"ok": True, "student_id": sid, "admission_no": adm_no,
                    "user_id": uid})


@app.post("/api/admissions/<int:aid>/reject")
@auth("super_admin", "clerk")
def admission_reject(aid):
    adm = q("SELECT * FROM admissions WHERE id=?", (aid,), one=True)
    if not adm:
        return jsonify({"error": "admission not found"}), 404
    if adm["status"] != "PENDING":
        return jsonify({"error": "admission already decided"}), 400
    run("UPDATE admissions SET status='REJECTED', decided_at=CURRENT_TIMESTAMP WHERE id=?",
        (aid,))
    audit("admission_reject", "admission", aid, {})
    return jsonify({"ok": True})


# ---------- students ----------
@app.get("/api/students")
@auth("super_admin", "principal", "clerk")
def students_list():
    where, args = ["1=1"], []
    if request.args.get("class_id"):
        where.append("s.class_id=?")
        args.append(int(request.args["class_id"]))
    if request.args.get("q"):
        like = "%" + request.args["q"] + "%"
        where.append("(s.name LIKE ? OR s.admission_no LIKE ? "
                     "OR s.guardian_name LIKE ?)")
        args += [like, like, like]
    if request.args.get("status") in ("Active", "Inactive"):
        where.append("s.status=?")
        args.append(request.args["status"])
    if request.args.get("subject_id"):
        where.append("""EXISTS (SELECT 1 FROM subjects sub2
                                WHERE sub2.class_id=s.class_id AND sub2.id=?)""")
        args.append(int(request.args["subject_id"]))
    return jsonify(q(
        """SELECT s.*, c.name AS class_name, c.section
           FROM students s LEFT JOIN classes c ON c.id=s.class_id
           WHERE %s ORDER BY s.id""" % " AND ".join(where), args))


@app.get("/api/teacher/students")
@auth("teacher")
def teacher_students():
    tid = my_teacher_id()
    if not tid:
        return jsonify({"error": "no teacher record linked"}), 404
    return jsonify(q(
        """SELECT s.*, c.name AS class_name, c.section
           FROM students s LEFT JOIN classes c ON c.id=s.class_id
           WHERE s.class_id IN (SELECT class_id FROM teacher_assignment
                                WHERE teacher_id=?)
             AND s.status='Active'
           ORDER BY c.name, c.section, s.name""", (tid,)))


@app.get("/api/students/<int:sid>/profile")
@auth()
def student_profile(sid):
    err = require_student_ownership(sid)
    if err:
        return err
    rec = q(
        """SELECT s.*, c.name AS class_name, c.section
           FROM students s LEFT JOIN classes c ON c.id=s.class_id
           WHERE s.id=?""", (sid,), one=True)
    if not rec:
        return jsonify({"error": "student not found"}), 404
    att = q("""SELECT COUNT(*) FILTER (WHERE status='PRESENT') AS present,
                      COUNT(*) AS total FROM attendance WHERE student_id=?""",
            (sid,), one=True)
    pct = round(100.0 * att["present"] / att["total"], 1) if att["total"] else 0
    inv = q("""SELECT fee_month, amount, late_fee, concession, total, paid,
                      status, due_date, receipt_no
               FROM fee_invoices WHERE student_id=? ORDER BY fee_month DESC""",
            (sid,))
    billed = round(sum(float(i["total"]) for i in inv), 2)
    paid = round(sum(float(i["paid"]) for i in inv), 2)
    res = q(
        """SELECT em.obtained, em.total, sub.name AS subject_name,
                  e.name AS exam_name, e.year
           FROM exam_marks em
           JOIN exams e ON e.id=em.exam_id
           JOIN subjects sub ON sub.id=em.subject_id
           WHERE em.student_id=? ORDER BY e.year DESC, e.id, sub.name""",
        (sid,))
    for r in res:
        p = round(100.0 * float(r["obtained"]) / float(r["total"]), 1) \
            if float(r["total"]) else 0
        r["percentage"] = p
        r["grade"] = grade_of(p)
    return jsonify({
        "student": rec,
        "attendance_pct": pct,
        "fee_summary": {"billed": billed, "total": billed, "paid": paid,
                        "pending": round(billed - paid, 2), "invoices": inv},
        "results": res,
    })


@app.post("/api/students")
@auth("super_admin", "principal")
def student_add():
    d = _body()
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    class_id = d.get("class_id")
    if class_id and not q("SELECT 1 FROM classes WHERE id=?",
                          (class_id,), one=True):
        return jsonify({"error": "class not found"}), 404
    adm_no = _next_admission_no()
    status = d.get("status") if d.get("status") in ("Active", "Inactive") \
        else "Active"
    gender = d.get("gender") if d.get("gender") in ("Male", "Female") else None
    sid = run(
        """INSERT INTO students
           (admission_no, name, father_name, gender, dob, class_id,
            guardian_name, guardian_phone, address, status)
           VALUES (?,?,?,?,?,?,?,?,?,?) RETURNING id""",
        (adm_no, name, d.get("father_name"), gender, d.get("dob") or None,
         class_id, d.get("guardian_name"), d.get("guardian_phone"),
         d.get("address"), status))
    audit("student_create", "student", sid, {"admission_no": adm_no})
    return jsonify({"ok": True, "id": sid, "admission_no": adm_no})


@app.put("/api/students/<int:sid>")
@auth("super_admin", "principal")
def student_upd(sid):
    if not q("SELECT 1 FROM students WHERE id=?", (sid,), one=True):
        return jsonify({"error": "student not found"}), 404
    d = _body()
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    class_id = d.get("class_id")
    if class_id and not q("SELECT 1 FROM classes WHERE id=?",
                          (class_id,), one=True):
        return jsonify({"error": "class not found"}), 404
    status = d.get("status") if d.get("status") in ("Active", "Inactive") \
        else "Active"
    gender = d.get("gender") if d.get("gender") in ("Male", "Female") else None
    run("""UPDATE students SET name=?, father_name=?, gender=?, dob=?,
           class_id=?, guardian_name=?, guardian_phone=?, address=?,
           status=? WHERE id=?""",
        (name, d.get("father_name"), gender, d.get("dob") or None, class_id,
         d.get("guardian_name"), d.get("guardian_phone"), d.get("address"),
         status, sid))
    audit("student_update", "student", sid, {})
    return jsonify({"ok": True})


@app.post("/api/students/<int:sid>/photo")
@auth("super_admin", "principal")
def student_photo_upload(sid):
    if not q("SELECT 1 FROM students WHERE id=?", (sid,), one=True):
        return jsonify({"error": "student not found"}), 404
    f = request.files.get("photo") or request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "photo file required"}), 400
    try:
        stored = _save_upload(f, PHOTO_DIR, "photo_%d" % sid,
                              PHOTO_ALLOWED_EXT)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    old = q("SELECT photo_path FROM students WHERE id=?",
            (sid,), one=True)["photo_path"]
    run("UPDATE students SET photo_path=? WHERE id=?", (stored, sid))
    _remove_upload(PHOTO_DIR, old)
    return jsonify({"ok": True})


@app.get("/api/students/<int:sid>/photo")
@auth()
def student_photo_get(sid):
    err = require_student_ownership(sid)
    if err:
        return err
    rec = q("SELECT photo_path FROM students WHERE id=?", (sid,), one=True)
    if not rec or not rec["photo_path"]:
        return jsonify({"error": "no photo"}), 404
    return send_from_directory(PHOTO_DIR, os.path.basename(rec["photo_path"]))


# ---------- teachers ----------
@app.get("/api/teachers")
@auth("super_admin", "principal")
def teachers_list():
    return jsonify(q(
        """SELECT t.*,
             COALESCE((SELECT string_agg(s.name, ', ' ORDER BY s.name)
                       FROM teacher_assignment ta
                       JOIN subjects s ON s.id=ta.subject_id
                       WHERE ta.teacher_id=t.id), '') AS subjects,
             (SELECT username FROM users WHERE linked_teacher_id=t.id) AS login_username,
             (SELECT is_active FROM users WHERE linked_teacher_id=t.id) AS login_active
           FROM teachers t ORDER BY t.id"""))


@app.post("/api/teachers")
@auth("super_admin", "principal")
def teacher_add():
    d = _body()
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    try:
        sal = float(d.get("salary_monthly", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "salary_monthly must be a number"}), 400
    status = d.get("status") if d.get("status") in ("Active", "Inactive") \
        else "Active"
    tid = run(
        """INSERT INTO teachers (name, phone, cnic, qualification,
                                 salary_monthly, status)
           VALUES (?,?,?,?,?,?) RETURNING id""",
        (name, d.get("phone"), d.get("cnic"), d.get("qualification"),
         sal, status))
    uid = None
    if d.get("make_login"):
        username = (d.get("username") or "").strip()
        if not username:
            return jsonify({"error": "username required for login"}), 400
        if q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            return jsonify({"error": "username already taken"}), 400
        uid = run(
            """INSERT INTO users (username, password_hash, role, linked_teacher_id)
               VALUES (?,?,'teacher',?) RETURNING id""",
            (username, generate_password_hash(DEFAULT_PASSWORD), tid))
    audit("teacher_create", "teacher", tid,
          {"name": name, "login_created": bool(uid)})
    return jsonify({"ok": True, "id": tid, "user_id": uid})


@app.put("/api/teachers/<int:tid>")
@auth("super_admin", "principal")
def teacher_upd(tid):
    if not q("SELECT 1 FROM teachers WHERE id=?", (tid,), one=True):
        return jsonify({"error": "teacher not found"}), 404
    d = _body()
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    try:
        sal = float(d.get("salary_monthly", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "salary_monthly must be a number"}), 400
    status = d.get("status") if d.get("status") in ("Active", "Inactive") \
        else "Active"
    run("""UPDATE teachers SET name=?, phone=?, cnic=?, qualification=?,
           salary_monthly=?, status=? WHERE id=?""",
        (name, d.get("phone"), d.get("cnic"), d.get("qualification"),
         sal, status, tid))
    audit("teacher_update", "teacher", tid, {})
    return jsonify({"ok": True})


@app.post("/api/teachers/<int:tid>/photo")
@auth("super_admin", "principal")
def teacher_photo_upload(tid):
    if not q("SELECT 1 FROM teachers WHERE id=?", (tid,), one=True):
        return jsonify({"error": "teacher not found"}), 404
    f = request.files.get("photo")
    if not f or not f.filename:
        return jsonify({"error": "photo file required"}), 400
    try:
        stored = _save_upload(f, PHOTO_DIR, "teacher_%d" % tid,
                              PHOTO_ALLOWED_EXT)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    old = q("SELECT photo_path FROM teachers WHERE id=?",
            (tid,), one=True)["photo_path"]
    run("UPDATE teachers SET photo_path=? WHERE id=?", (stored, tid))
    _remove_upload(PHOTO_DIR, old)
    return jsonify({"ok": True})


@app.get("/api/teachers/<int:tid>/photo")
@auth()
def teacher_photo_get(tid):
    rec = q("SELECT photo_path FROM teachers WHERE id=?", (tid,), one=True)
    if not rec or not rec["photo_path"]:
        return jsonify({"error": "no photo"}), 404
    return send_from_directory(PHOTO_DIR, os.path.basename(rec["photo_path"]))


@app.get("/api/teacher-assignments")
@auth("super_admin", "principal")
def assignments_list():
    return jsonify(q(
        """SELECT ta.id, ta.teacher_id, t.name AS teacher_name,
                  ta.class_id, c.name AS class_name, c.section,
                  ta.subject_id, s.name AS subject_name
           FROM teacher_assignment ta
           JOIN teachers t ON t.id=ta.teacher_id
           JOIN classes c ON c.id=ta.class_id
           JOIN subjects s ON s.id=ta.subject_id
           ORDER BY t.name, c.name, s.name"""))


@app.post("/api/teacher-assignments")
@auth("super_admin", "principal")
def assignment_add():
    d = _body()
    tid, cid, subid = d.get("teacher_id"), d.get("class_id"), d.get("subject_id")
    if not q("SELECT 1 FROM teachers WHERE id=?", (tid,), one=True):
        return jsonify({"error": "teacher not found"}), 404
    if not q("SELECT 1 FROM classes WHERE id=?", (cid,), one=True):
        return jsonify({"error": "class not found"}), 404
    sub = q("SELECT id, class_id FROM subjects WHERE id=?", (subid,), one=True)
    if not sub:
        return jsonify({"error": "subject not found"}), 404
    if sub["class_id"] != cid:
        return jsonify({"error": "subject does not belong to this class"}), 400
    try:
        rid = run(
            """INSERT INTO teacher_assignment (teacher_id, class_id, subject_id)
               VALUES (?,?,?) RETURNING id""", (tid, cid, subid))
    except sqlite3.IntegrityError:
        return jsonify({"error": "assignment already exists"}), 400
    return jsonify({"ok": True, "id": rid})


@app.delete("/api/teacher-assignments/<int:aid>")
@auth("super_admin", "principal")
def assignment_del(aid):
    if not q("SELECT 1 FROM teacher_assignment WHERE id=?", (aid,), one=True):
        return jsonify({"error": "assignment not found"}), 404
    run("DELETE FROM teacher_assignment WHERE id=?", (aid,))
    return jsonify({"ok": True})


@app.get("/api/me/teacher")
@auth("teacher")
def my_teacher():
    tid = my_teacher_id()
    if not tid:
        return jsonify({"error": "no teacher record linked"}), 404
    t = q("SELECT * FROM teachers WHERE id=?", (tid,), one=True)
    assigns = q(
        """SELECT ta.id, ta.class_id, c.name AS class_name, c.section,
                  ta.subject_id, s.name AS subject_name
           FROM teacher_assignment ta
           JOIN classes c ON c.id=ta.class_id
           JOIN subjects s ON s.id=ta.subject_id
           WHERE ta.teacher_id=? ORDER BY c.name, s.name""", (tid,))
    return jsonify({"teacher": t, "assignments": assigns})


# ---------- teacher login accounts (super_admin + principal) ----------
@app.post("/api/teachers/<int:tid>/login")
@auth("super_admin", "principal")
def teacher_login_create(tid):
    if not q("SELECT 1 FROM teachers WHERE id=?", (tid,), one=True):
        return jsonify({"error": "teacher not found"}), 404
    if q("SELECT 1 FROM users WHERE linked_teacher_id=?", (tid,), one=True):
        return jsonify({"error": "teacher already has a login"}), 400
    d = _body()
    username = (d.get("username") or "").strip()
    if not username:
        return jsonify({"error": "username is required"}), 400
    if q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
        return jsonify({"error": "username already taken"}), 400
    uid = run(
        """INSERT INTO users (username, password_hash, role, linked_teacher_id)
           VALUES (?,?,'teacher',?) RETURNING id""",
        (username, generate_password_hash(DEFAULT_PASSWORD), tid))
    audit("teacher_login_create", "user", uid,
          {"username": username, "teacher_id": tid})
    return jsonify({"ok": True, "id": uid})


@app.post("/api/teachers/<int:tid>/login/activate")
@auth("super_admin", "principal")
def teacher_login_activate(tid):
    u = q("SELECT id FROM users WHERE linked_teacher_id=?", (tid,), one=True)
    if not u:
        return jsonify({"error": "no login exists for this teacher"}), 404
    run("UPDATE users SET is_active=TRUE WHERE id=?", (u["id"],))
    audit("teacher_login_activate", "user", u["id"], {"teacher_id": tid})
    return jsonify({"ok": True})


@app.post("/api/teachers/<int:tid>/login/deactivate")
@auth("super_admin", "principal")
def teacher_login_deactivate(tid):
    u = q("SELECT id FROM users WHERE linked_teacher_id=?", (tid,), one=True)
    if not u:
        return jsonify({"error": "no login exists for this teacher"}), 404
    if u["id"] == session["user"]["id"]:
        return jsonify({"error": "cannot deactivate your own login"}), 400
    run("UPDATE users SET is_active=FALSE WHERE id=?", (u["id"],))
    audit("teacher_login_deactivate", "user", u["id"], {"teacher_id": tid})
    return jsonify({"ok": True})


@app.delete("/api/teachers/<int:tid>")
@auth("super_admin", "principal")
def teacher_del(tid):
    t = q("SELECT * FROM teachers WHERE id=?", (tid,), one=True)
    if not t:
        return jsonify({"error": "teacher not found"}), 404
    u = q("SELECT id FROM users WHERE linked_teacher_id=?", (tid,), one=True)
    uid = u["id"] if u else None
    reasons = []
    if q("SELECT 1 FROM salaries WHERE teacher_id=? LIMIT 1",
         (tid,), one=True):
        reasons.append("salary rows")
    if uid:
        if q("SELECT 1 FROM notes WHERE uploaded_by=? LIMIT 1",
             (uid,), one=True):
            reasons.append("uploaded notes")
        if q("SELECT 1 FROM announcements WHERE posted_by=? LIMIT 1",
             (uid,), one=True):
            reasons.append("posted announcements")
        if q("SELECT 1 FROM attendance WHERE marked_by=? LIMIT 1",
             (uid,), one=True):
            reasons.append("marked attendance")
    if reasons:
        return jsonify({"error": "Cannot delete teacher: "
                                 + ", ".join(reasons)
                                 + " exist. Deactivate the teacher instead — this keeps all records safe."}), 400
    if uid:
        for tbl, col in (("fee_payments", "received_by"),
                         ("expenses", "added_by"),
                         ("fee_concessions", "granted_by"),
                         ("certificates", "issued_by")):
            run("UPDATE %s SET %s=NULL WHERE %s=?" % (tbl, col, col),
                (uid,))
        run("DELETE FROM users WHERE id=?", (uid,))
    run("DELETE FROM teachers WHERE id=?", (tid,))  # cascades assignments
    audit("teacher_delete", "teacher", tid,
          {"name": t["name"], "login_deleted": bool(uid)})
    return jsonify({"ok": True})


# ---------- timetable ----------
DAY_ORDER = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


@app.get("/api/timetable")
@auth()
def timetable_list():
    role = session["user"]["role"]
    class_id = request.args.get("class_id", type=int)
    if role == "teacher":
        tid = my_teacher_id()
        allowed = teacher_class_ids(tid) if tid else []
        if class_id is not None and class_id not in allowed:
            return jsonify({"error": "forbidden"}), 403
        ids = [class_id] if class_id is not None else allowed
        if not ids:
            return jsonify([])
        return jsonify(_timetable_rows(ids))
    if role == "student":
        sid = my_student_id()
        stu = q("SELECT class_id FROM students WHERE id=?", (sid,), one=True)
        own = stu["class_id"] if stu else None
        if class_id is None:
            class_id = own
        if class_id != own:
            return jsonify({"error": "forbidden"}), 403
        return jsonify(_timetable_rows([class_id]))
    # super_admin / principal / clerk: all
    ids = [class_id] if class_id is not None else None
    return jsonify(_timetable_rows(ids))


def _timetable_rows(class_ids):
    where, args = ["1=1"], []
    if class_ids is not None:
        where.append("t.class_id IN (%s)" % ",".join(["?"] * len(class_ids)))
        args.extend(class_ids)
    return q(
        """SELECT t.id, t.class_id,
                  (c.name || '-' || c.section) AS class_label,
                  t.day_of_week, t.period_no, t.start_time, t.end_time,
                  t.subject_id, s.name AS subject_name,
                  t.teacher_id, te.name AS teacher_name, t.room
           FROM timetables t
           JOIN classes c ON c.id=t.class_id
           LEFT JOIN subjects s ON s.id=t.subject_id
           LEFT JOIN teachers te ON te.id=t.teacher_id
           WHERE %s
           ORDER BY CASE t.day_of_week
                      WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2
                      WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4
                      WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6
                      ELSE 7 END, t.period_no""" % " AND ".join(where), args)


@app.post("/api/timetable")
@auth("super_admin", "principal", "clerk")
def timetable_upsert():
    d = _body()
    try:
        class_id = int(d.get("class_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "class_id is required"}), 400
    day = (d.get("day_of_week") or "").strip()
    try:
        period_no = int(d.get("period_no"))
    except (TypeError, ValueError):
        return jsonify({"error": "period_no is required"}), 400
    if day not in DAY_ORDER:
        return jsonify({"error": "day_of_week must be one of " +
                                 ", ".join(DAY_ORDER)}), 400
    if not q("SELECT 1 FROM classes WHERE id=?", (class_id,), one=True):
        return jsonify({"error": "class not found"}), 404
    subject_id = d.get("subject_id") or None
    teacher_id = d.get("teacher_id") or None
    if subject_id is not None and not q("SELECT 1 FROM subjects WHERE id=?",
                                        (subject_id,), one=True):
        return jsonify({"error": "subject not found"}), 404
    if teacher_id is not None and not q("SELECT 1 FROM teachers WHERE id=?",
                                        (teacher_id,), one=True):
        return jsonify({"error": "teacher not found"}), 404
    rid = run(
        """INSERT INTO timetables (class_id, day_of_week, period_no,
                                   start_time, end_time, subject_id,
                                   teacher_id, room)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT (class_id, day_of_week, period_no)
           DO UPDATE SET start_time=EXCLUDED.start_time,
                         end_time=EXCLUDED.end_time,
                         subject_id=EXCLUDED.subject_id,
                         teacher_id=EXCLUDED.teacher_id,
                         room=EXCLUDED.room
           RETURNING id""",
        (class_id, day, period_no, d.get("start_time") or None,
         d.get("end_time") or None, subject_id, teacher_id,
         (d.get("room") or "").strip() or None))
    audit("timetable_upsert", "timetable", rid,
          {"class_id": class_id, "day_of_week": day, "period_no": period_no})
    return jsonify({"ok": True, "id": rid})


@app.delete("/api/timetable/<int:tid>")
@auth("super_admin", "principal", "clerk")
def timetable_delete(tid):
    row = q("SELECT id FROM timetables WHERE id=?", (tid,), one=True)
    if not row:
        return jsonify({"error": "timetable entry not found"}), 404
    run("DELETE FROM timetables WHERE id=?", (tid,))
    audit("timetable_delete", "timetable", tid, {})
    return jsonify({"ok": True})


# ---------- attendance ----------
@app.get("/api/attendance")
@auth("super_admin", "principal")
def attendance_list():
    class_id = request.args.get("class_id", type=int)
    dt = request.args.get("date") or date.today().isoformat()
    if class_id:
        # full class roster with that day's status (for the marking UI)
        return jsonify(q(
            """SELECT s.id AS student_id, s.name, s.admission_no, a.status
               FROM students s
               LEFT JOIN attendance a
                 ON a.student_id=s.id AND a.att_date=?
               WHERE s.class_id=? AND s.status='Active'
               ORDER BY s.name""", (dt, class_id)))
    where, args = ["1=1"], []
    if dt:
        where.append("a.att_date=?")
        args.append(dt)
    return jsonify(q(
        """SELECT a.id, a.student_id, s.name AS student_name,
                  s.admission_no, a.class_id, c.name AS class_name, c.section,
                  a.att_date, a.status
           FROM attendance a
           JOIN students s ON s.id=a.student_id
           LEFT JOIN classes c ON c.id=a.class_id
           WHERE %s ORDER BY a.att_date DESC, s.name LIMIT 500"""
        % " AND ".join(where), args))


@app.get("/api/teacher/attendance")
@auth("teacher")
def teacher_attendance():
    tid = my_teacher_id()
    if not tid:
        return jsonify({"error": "no teacher record linked"}), 404
    class_id = request.args.get("class_id", type=int)
    if not class_id:
        return jsonify({"error": "class_id is required"}), 400
    if class_id not in teacher_class_ids(tid):
        return jsonify({"error": "forbidden: class not assigned to you"}), 403
    dt = request.args.get("date") or date.today().isoformat()
    return jsonify(q(
        """SELECT s.id AS student_id, s.name, s.admission_no, a.status
           FROM students s
           LEFT JOIN attendance a ON a.student_id=s.id AND a.att_date=?
           WHERE s.class_id=? AND s.status='Active'
           ORDER BY s.name""", (dt, class_id)))


@app.post("/api/attendance")
@auth("super_admin", "principal", "teacher")
def attendance_mark():
    d = _body()
    class_id = d.get("class_id")
    dt = d.get("date") or date.today().isoformat()
    try:
        date.fromisoformat(dt)
    except ValueError:
        return jsonify({"error": "date must be YYYY-MM-DD"}), 400
    if session["user"]["role"] == "teacher":
        tid = my_teacher_id()
        if not tid or class_id not in teacher_class_ids(tid):
            return jsonify({"error": "forbidden: class not assigned to you"}), 403
    if not q("SELECT 1 FROM classes WHERE id=?", (class_id,), one=True):
        return jsonify({"error": "class not found"}), 404
    records = d.get("records") or []
    if not records:
        return jsonify({"error": "records required"}), 400
    valid = {"PRESENT", "ABSENT", "LEAVE"}
    class_students = {r["v"] for r in q(
        "SELECT id AS v FROM students WHERE class_id=? AND status='Active'",
        (class_id,))}
    saved = 0
    c = conn()
    try:
        cur = c.cursor()
        for r in records:
            st = r.get("status")
            sid = r.get("student_id")
            if st not in valid:
                raise ValueError("invalid status: %r" % (st,))
            if sid not in class_students:
                raise ValueError(
                    "student %r is not in this class" % (sid,))
            cur.execute(
                """INSERT INTO attendance
                   (student_id, class_id, att_date, status, marked_by)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT (student_id, att_date)
                   DO UPDATE SET status=EXCLUDED.status,
                                 class_id=EXCLUDED.class_id,
                                 marked_by=EXCLUDED.marked_by""",
                (sid, class_id, dt, st, session["user"]["id"]))
            saved += 1
        cur.close()
        c.commit()
    except ValueError as e:
        c.rollback()
        c.close()
        return jsonify({"error": str(e)}), 400
    except Exception:
        c.rollback()
        c.close()
        raise
    c.close()
    return jsonify({"ok": True, "saved": saved})


@app.get("/api/attendance/absent")
@auth("super_admin", "principal")
def attendance_absent():
    dt = request.args.get("date") or date.today().isoformat()
    return jsonify(q(
        """SELECT s.id AS student_id, s.name, s.admission_no,
                  c.name AS class_name, c.section, s.guardian_phone
           FROM attendance a
           JOIN students s ON s.id=a.student_id
           LEFT JOIN classes c ON c.id=a.class_id
           WHERE a.att_date=? AND a.status='ABSENT'
           ORDER BY c.name, s.name""", (dt,)))


@app.get("/api/me/attendance")
@auth("student")
def my_attendance():
    sid = my_student_id()
    if not sid:
        return jsonify({"error": "no student record linked"}), 404
    rows = q("""SELECT att_date, status FROM attendance
                WHERE student_id=? ORDER BY att_date DESC""", (sid,))
    total = len(rows)
    present = sum(1 for r in rows if r["status"] == "PRESENT")
    pct = round(100.0 * present / total, 1) if total else 0
    return jsonify({"records": rows, "present": present, "total": total,
                    "percentage": pct})


# ---------- fees ----------
@app.get("/api/fee-heads")
@auth("super_admin", "principal", "clerk")
def fee_heads_list():
    return jsonify(q(
        """SELECT fh.id, fh.class_id, c.name AS class_name, c.section,
                  fh.monthly_amount
           FROM fee_heads fh JOIN classes c ON c.id=fh.class_id
           ORDER BY c.name, c.section"""))


@app.post("/api/fee-heads")
@auth("super_admin", "principal")
def fee_head_upsert():
    d = _body()
    cid = d.get("class_id")
    if not q("SELECT 1 FROM classes WHERE id=?", (cid,), one=True):
        return jsonify({"error": "class not found"}), 404
    try:
        amt = float(d.get("monthly_amount"))
    except (TypeError, ValueError):
        return jsonify({"error": "monthly_amount must be a number"}), 400
    if amt < 0:
        return jsonify({"error": "monthly_amount cannot be negative"}), 400
    run("""INSERT INTO fee_heads (class_id, monthly_amount) VALUES (?,?)
           ON CONFLICT (class_id) DO UPDATE SET monthly_amount=EXCLUDED.monthly_amount""",
        (cid, amt))
    return jsonify({"ok": True})


@app.post("/api/fee-invoices/generate-monthly")
@auth("super_admin", "clerk")
def invoices_generate_monthly():
    d = _body()
    m = (d.get("fee_month") or "").strip()
    mtch = re.match(r"^(\d{4})-(0[1-9]|1[0-2])$", m)
    if not mtch:
        return jsonify({"error": "fee_month must be YYYY-MM"}), 400
    year, mon = int(mtch.group(1)), int(mtch.group(2))
    due = date(year, mon, 1) + timedelta(days=10)  # month + 10 days
    yyyymm = "%04d%02d" % (year, mon)
    students = q(
        """SELECT s.id, fh.monthly_amount FROM students s
           JOIN fee_heads fh ON fh.class_id=s.class_id
           WHERE s.status='Active' ORDER BY s.id""")
    n = q("SELECT COUNT(*) AS v FROM fee_invoices WHERE fee_month=?",
          (m,), one=True)["v"]
    created = 0
    for s in students:
        if q("SELECT 1 FROM fee_invoices WHERE student_id=? AND fee_month=?",
             (s["id"], m), one=True):
            continue
        n += 1
        rcp = "R-%s-%03d" % (yyyymm, n)
        amt = float(s["monthly_amount"])
        run(
            """INSERT INTO fee_invoices
               (student_id, fee_month, amount, late_fee, concession,
                total, paid, status, due_date, receipt_no)
               VALUES (?,?,?,0,0,?,0,'UNPAID',?,?)""",
            (s["id"], m, amt, amt, due.isoformat(), rcp))
        created += 1
    audit("invoices_generate_monthly", None, None,
          {"fee_month": m, "created": created})
    return jsonify({"ok": True, "created": created})


@app.get("/api/fee-invoices")
@auth("super_admin", "principal", "clerk")
def invoices_list():
    where, args = ["1=1"], []
    m = request.args.get("month")
    if m:
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", m):
            return jsonify({"error": "month must be YYYY-MM"}), 400
        where.append("fi.fee_month=?")
        args.append(m)
    st = request.args.get("status")
    if st in ("UNPAID", "PARTIAL", "PAID", "OVERDUE"):
        where.append("fi.status=?")
        args.append(st)
    if request.args.get("q"):
        like = "%" + request.args["q"] + "%"
        where.append("(s.name LIKE ? OR s.admission_no LIKE ?)")
        args += [like, like]
    return jsonify(q(
        """SELECT fi.*, s.name AS student_name, s.admission_no,
                  c.name AS class_name, c.section
           FROM fee_invoices fi
           JOIN students s ON s.id=fi.student_id
           LEFT JOIN classes c ON c.id=s.class_id
           WHERE %s ORDER BY fi.id DESC""" % " AND ".join(where), args))


@app.get("/api/me/invoices")
@auth("student")
def my_invoices():
    sid = my_student_id()
    if not sid:
        return jsonify({"error": "no student record linked"}), 404
    return jsonify(q("SELECT * FROM fee_invoices WHERE student_id=? "
                     "ORDER BY fee_month DESC", (sid,)))


@app.post("/api/fee-payments")
@auth("super_admin", "clerk")
def payment_add():
    d = _body()
    inv = q("SELECT id FROM fee_invoices WHERE id=?",
            (d.get("invoice_id"),), one=True)
    if not inv:
        return jsonify({"error": "invoice not found"}), 404
    try:
        amt = float(d.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be a number"}), 400
    if amt <= 0:
        return jsonify({"error": "amount must be > 0"}), 400
    method = (d.get("method") or "Cash").strip() or "Cash"
    pid = run(
        """INSERT INTO fee_payments (invoice_id, amount, method, received_by)
           VALUES (?,?,?,?) RETURNING id""",
        (d["invoice_id"], amt, method, session["user"]["id"]))
    rcp = "RCP-%06d" % pid
    run("UPDATE fee_payments SET receipt_no=? WHERE id=?", (rcp, pid))
    st = _recalc_invoice(d["invoice_id"])
    audit("fee_payment", "fee_invoice", d["invoice_id"],
          {"payment_id": pid, "receipt_no": rcp, "amount": amt,
           "method": method})
    return jsonify({"ok": True, "id": pid, "receipt_no": rcp,
                    "invoice_status": st["status"]})


@app.post("/api/fee-invoices/<int:iid>/refund")
@auth("super_admin", "clerk")
def invoice_refund(iid):
    if not q("SELECT 1 FROM fee_invoices WHERE id=?", (iid,), one=True):
        return jsonify({"error": "invoice not found"}), 404
    d = _body()
    try:
        amt = float(d.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be a number"}), 400
    if amt <= 0:
        return jsonify({"error": "amount must be > 0"}), 400
    paid = float(q("SELECT COALESCE(SUM(amount),0) AS v FROM fee_payments "
                   "WHERE invoice_id=?", (iid,), one=True)["v"])
    if amt > paid:
        return jsonify({"error": "refund cannot exceed paid amount (Rs %s)"
                                 % paid}), 400
    pid = run(
        """INSERT INTO fee_payments (invoice_id, amount, method, received_by)
           VALUES (?,?,'Refund',?) RETURNING id""",
        (iid, -amt, session["user"]["id"]))
    rcp = "RCP-%06d" % pid
    run("UPDATE fee_payments SET receipt_no=? WHERE id=?", (rcp, pid))
    st = _recalc_invoice(iid)
    audit("fee_refund", "fee_invoice", iid,
          {"refund_amount": amt, "receipt_no": rcp})
    return jsonify({"ok": True, "receipt_no": rcp,
                    "invoice_status": st["status"]})


@app.post("/api/fee-invoices/apply-late-fees")
@auth("super_admin", "clerk")
def apply_late_fees():
    d = _body()
    m = (d.get("fee_month") or "").strip()
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", m):
        return jsonify({"error": "fee_month must be YYYY-MM"}), 400
    try:
        pct = float(_setting("late_fee_percent", "5") or 5)
    except ValueError:
        pct = 5.0
    rows = q(
        """SELECT id, amount FROM fee_invoices
           WHERE fee_month=? AND status IN ('UNPAID','PARTIAL')
             AND due_date < CURRENT_DATE""", (m,))
    applied = 0
    for r in rows:
        add = round(float(r["amount"]) * pct / 100, 2)
        run("UPDATE fee_invoices SET late_fee=late_fee+? WHERE id=?",
            (add, r["id"]))
        _recalc_invoice(r["id"])
        applied += 1
    audit("late_fees_apply", None, None,
          {"fee_month": m, "applied": applied, "percent": pct})
    return jsonify({"ok": True, "applied": applied})


@app.post("/api/fee-concessions")
@auth("super_admin", "clerk")
def concession_add():
    d = _body()
    sid = d.get("student_id")
    m = (d.get("fee_month") or "").strip()
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", m):
        return jsonify({"error": "fee_month must be YYYY-MM"}), 400
    try:
        amt = float(d.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be a number"}), 400
    if amt <= 0:
        return jsonify({"error": "amount must be > 0"}), 400
    if not q("SELECT 1 FROM students WHERE id=?", (sid,), one=True):
        return jsonify({"error": "student not found"}), 404
    inv = q("SELECT id FROM fee_invoices WHERE student_id=? AND fee_month=?",
            (sid, m), one=True)
    if not inv:
        return jsonify({"error": "no invoice for that student and month"}), 404
    cid = run(
        """INSERT INTO fee_concessions (student_id, fee_month, amount, reason, granted_by)
           VALUES (?,?,?,?,?) RETURNING id""",
        (sid, m, amt, d.get("reason"), session["user"]["id"]))
    run("UPDATE fee_invoices SET concession=concession+? WHERE id=?",
        (amt, inv["id"]))
    st = _recalc_invoice(inv["id"])
    audit("fee_concession", "fee_invoice", inv["id"],
          {"concession_id": cid, "amount": amt, "reason": d.get("reason")})
    return jsonify({"ok": True, "id": cid,
                    "invoice_status": st["status"]})


@app.get("/api/fee-defaulters")
@auth("super_admin", "principal", "clerk")
def fee_defaulters():
    m = request.args.get("month") or date.today().strftime("%Y-%m")
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", m):
        return jsonify({"error": "month must be YYYY-MM"}), 400
    school = _setting("school_name", "Anjum Grammer School")
    rows = q(
        """SELECT fi.student_id, s.name, c.name AS class_name, c.section,
                  s.guardian_phone, (fi.total - fi.paid) AS pending, fi.due_date
           FROM fee_invoices fi
           JOIN students s ON s.id=fi.student_id
           LEFT JOIN classes c ON c.id=s.class_id
           WHERE fi.fee_month=? AND fi.status IN ('UNPAID','PARTIAL','OVERDUE')
             AND (fi.total - fi.paid) > 0
           ORDER BY pending DESC""", (m,))
    for r in rows:
        cls = (r["class_name"] or "") + \
            ("-" + r["section"] if r["section"] else "")
        r["whatsapp_text"] = (
            "Assalam-o-Alaikum! This is %s: fee of Rs %s for %s is pending "
            "for %s (Class %s). Please pay by %s. Thank you."
            % (school, r["pending"], m, r["name"], cls, r["due_date"]))
    return jsonify(rows)


@app.get("/api/fee-invoices/<int:iid>/challan")
@auth("super_admin", "principal", "clerk", "student")
def invoice_challan(iid):
    inv = q(
        """SELECT fi.*, s.name AS student_name, s.admission_no, s.father_name,
                  c.name AS class_name, c.section
           FROM fee_invoices fi
           JOIN students s ON s.id=fi.student_id
           LEFT JOIN classes c ON c.id=s.class_id
           WHERE fi.id=?""", (iid,), one=True)
    if not inv:
        return jsonify({"error": "invoice not found"}), 404
    if session["user"]["role"] == "student" \
            and my_student_id() != inv["student_id"]:
        return jsonify({"error": "forbidden"}), 403
    school = {k: _setting(k, "") for k in
              ("school_name", "school_address", "school_phone", "school_logo")}
    return jsonify({
        "school": school,
        "invoice": inv,
        "student": {
            "id": inv["student_id"], "name": inv["student_name"],
            "admission_no": inv["admission_no"],
            "father_name": inv["father_name"],
            "class_name": inv["class_name"], "section": inv["section"],
        },
    })


# ---------- exams ----------
@app.get("/api/exams")
@auth()
def exams_list():
    where, args = ["1=1"], []
    if request.args.get("class_id"):
        where.append("e.class_id=?")
        args.append(int(request.args["class_id"]))
    return jsonify(q(
        """SELECT e.*, c.name AS class_name, c.section
           FROM exams e LEFT JOIN classes c ON c.id=e.class_id
           WHERE %s ORDER BY e.year DESC, e.id DESC""" % " AND ".join(where),
        args))


@app.post("/api/exams")
@auth("super_admin", "principal")
def exam_add():
    d = _body()
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not q("SELECT 1 FROM classes WHERE id=?", (d.get("class_id"),),
             one=True):
        return jsonify({"error": "class not found"}), 404
    try:
        year = int(d.get("year"))
    except (TypeError, ValueError):
        return jsonify({"error": "year must be a number"}), 400
    rid = run(
        "INSERT INTO exams (name, class_id, year, start_date) "
        "VALUES (?,?,?,?) RETURNING id",
        (name, d["class_id"], year, d.get("start_date") or None))
    return jsonify({"ok": True, "id": rid})


@app.get("/api/exam-marks")
@auth()
def exam_marks_list():
    role = session["user"]["role"]
    where, args = ["1=1"], []
    if request.args.get("exam_id"):
        where.append("em.exam_id=?")
        args.append(int(request.args["exam_id"]))
    if role == "student":
        sid = my_student_id()
        if not sid:
            return jsonify({"error": "no student record linked"}), 404
        where.append("em.student_id=?")
        args.append(sid)
    elif role == "teacher":
        tid = my_teacher_id()
        subids = teacher_subject_ids(tid)
        if request.args.get("subject_id"):
            subid = int(request.args["subject_id"])
            if subid not in subids:
                return jsonify(
                    {"error": "forbidden: subject not assigned to you"}), 403
            where.append("em.subject_id=?")
            args.append(subid)
        elif subids:
            where.append("em.subject_id IN (%s)" % ",".join(["?"] * len(subids)))
            args.extend(subids)
        else:
            return jsonify([])
    elif request.args.get("subject_id"):
        where.append("em.subject_id=?")
        args.append(int(request.args["subject_id"]))
    rows = q(
        """SELECT em.*, e.name AS exam_name, st.name AS student_name,
                  sub.name AS subject_name
           FROM exam_marks em
           JOIN exams e ON e.id=em.exam_id
           JOIN students st ON st.id=em.student_id
           JOIN subjects sub ON sub.id=em.subject_id
           WHERE %s ORDER BY em.id""" % " AND ".join(where), args)
    for r in rows:
        pct = round(100.0 * float(r["obtained"]) / float(r["total"]), 1) \
            if float(r["total"]) else 0
        r["percentage"] = pct
        r["grade"] = grade_of(pct)
    return jsonify(rows)


@app.post("/api/exam-marks")
@auth("super_admin", "principal", "teacher")
def exam_marks_save():
    d = _body()
    exam_id = d.get("exam_id")
    subject_id = d.get("subject_id")
    if not q("SELECT 1 FROM exams WHERE id=?", (exam_id,), one=True):
        return jsonify({"error": "exam not found"}), 404
    if not q("SELECT 1 FROM subjects WHERE id=?", (subject_id,), one=True):
        return jsonify({"error": "subject not found"}), 404
    if session["user"]["role"] == "teacher":
        tid = my_teacher_id()
        if not q("SELECT 1 FROM teacher_assignment WHERE teacher_id=? "
                 "AND subject_id=?", (tid, subject_id), one=True):
            return jsonify(
                {"error": "forbidden: subject not assigned to you"}), 403
    rows = d.get("rows") or []
    if not rows:
        return jsonify({"error": "rows required"}), 400
    c = conn()
    try:
        cur = c.cursor()
        for r in rows:
            obt = float(r["obtained"])
            tot = float(r.get("total", 100))
            if not (0 <= obt <= tot and tot > 0):
                raise ValueError(
                    "invalid marks for student %r" % (r.get("student_id"),))
            cur.execute(
                """INSERT INTO exam_marks
                   (exam_id, student_id, subject_id, obtained, total)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT (exam_id, student_id, subject_id)
                   DO UPDATE SET obtained=EXCLUDED.obtained,
                                 total=EXCLUDED.total""",
                (exam_id, r["student_id"], subject_id, obt, tot))
        cur.close()
        c.commit()
    except ValueError as e:
        c.rollback()
        c.close()
        return jsonify({"error": str(e)}), 400
    except Exception:
        c.rollback()
        c.close()
        raise
    c.close()
    return jsonify({"ok": True, "saved": len(rows)})


@app.get("/api/report-card")
@auth()
def report_card():
    exam_id = request.args.get("exam_id", type=int)
    student_id = request.args.get("student_id", type=int)
    if not exam_id or not student_id:
        return jsonify({"error": "exam_id and student_id are required"}), 400
    err = require_student_ownership(student_id)
    if err:
        return err
    ex = q(
        """SELECT e.*, c.name AS class_name, c.section
           FROM exams e LEFT JOIN classes c ON c.id=e.class_id
           WHERE e.id=?""", (exam_id,), one=True)
    if not ex:
        return jsonify({"error": "exam not found"}), 404
    stu = q(
        """SELECT s.*, c.name AS class_name, c.section
           FROM students s LEFT JOIN classes c ON c.id=s.class_id
           WHERE s.id=?""", (student_id,), one=True)
    if not stu:
        return jsonify({"error": "student not found"}), 404
    marks = q(
        """SELECT em.obtained, em.total, sub.name
           FROM exam_marks em JOIN subjects sub ON sub.id=em.subject_id
           WHERE em.exam_id=? AND em.student_id=? ORDER BY sub.name""",
        (exam_id, student_id))
    subs, tot_obt, tot_max = [], 0.0, 0.0
    for m in marks:
        obt, tot = float(m["obtained"]), float(m["total"])
        pct = round(100.0 * obt / tot, 1) if tot else 0
        subs.append({"name": m["name"], "obtained": obt, "total": tot,
                     "percentage": pct, "grade": grade_of(pct)})
        tot_obt += obt
        tot_max += tot
    pct_all = round(100.0 * tot_obt / tot_max, 1) if tot_max else 0
    position = None
    if marks:
        ranks = q(
            """SELECT student_id,
                      RANK() OVER (ORDER BY SUM(obtained) DESC) AS pos
               FROM exam_marks WHERE exam_id=? GROUP BY student_id""",
            (exam_id,))
        for r in ranks:
            if r["student_id"] == student_id:
                position = r["pos"]
                break
    return jsonify({
        "student": stu, "exam": ex, "subjects": subs,
        "total_obtained": tot_obt, "total_max": tot_max,
        "percentage": pct_all, "grade": grade_of(pct_all),
        "position": position,
    })


@app.get("/api/exams/<int:eid>/gazette")
@auth("super_admin", "principal")
def exam_gazette(eid):
    ex = q(
        """SELECT e.*, c.name AS class_name, c.section
           FROM exams e LEFT JOIN classes c ON c.id=e.class_id
           WHERE e.id=?""", (eid,), one=True)
    if not ex:
        return jsonify({"error": "exam not found"}), 404
    rows = q(
        """SELECT st.id AS student_id, st.name, st.admission_no,
                  COALESCE(SUM(em.obtained),0) AS total_obtained,
                  COALESCE(SUM(em.total),0) AS total_max,
                  RANK() OVER (ORDER BY COALESCE(SUM(em.obtained),0) DESC)
                    AS position
           FROM students st
           LEFT JOIN exam_marks em
             ON em.student_id=st.id AND em.exam_id=?
           WHERE st.class_id=? AND st.status='Active'
           GROUP BY st.id, st.name, st.admission_no
           ORDER BY position""", (eid, ex["class_id"]))
    for r in rows:
        pct = round(100.0 * float(r["total_obtained"])
                    / float(r["total_max"]), 1) if float(r["total_max"]) else 0
        r["percentage"] = pct
        r["grade"] = grade_of(pct)
        r["total"] = r["total_max"]
    return jsonify({"exam": ex, "merit": rows, "rows": rows})


# ---------- notes (study material PDFs) ----------
@app.get("/api/notes")
@auth()
def notes_list():
    role = session["user"]["role"]
    where, args = ["1=1"], []
    if role == "student":
        sid = my_student_id()
        stu = q("SELECT class_id FROM students WHERE id=?", (sid,), one=True)
        if not stu or not stu["class_id"]:
            return jsonify([])
        where.append("n.class_id=?")
        args.append(stu["class_id"])
    else:
        if request.args.get("class_id"):
            where.append("n.class_id=?")
            args.append(int(request.args["class_id"]))
    if request.args.get("subject_id"):
        where.append("n.subject_id=?")
        args.append(int(request.args["subject_id"]))
    return jsonify(q(
        """SELECT n.id, n.title, n.class_id, c.name AS class_name, c.section,
                  n.subject_id, s.name AS subject_name,
                  n.uploaded_by, u.username AS uploaded_by_name, n.uploaded_at
           FROM notes n
           JOIN classes c ON c.id=n.class_id
           JOIN subjects s ON s.id=n.subject_id
           LEFT JOIN users u ON u.id=n.uploaded_by
           WHERE %s ORDER BY n.id DESC""" % " AND ".join(where), args))


@app.post("/api/notes")
@auth("super_admin", "principal", "teacher")
def note_add():
    class_id = request.form.get("class_id", type=int)
    subject_id = request.form.get("subject_id", type=int)
    title = (request.form.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not q("SELECT 1 FROM classes WHERE id=?", (class_id,), one=True):
        return jsonify({"error": "class not found"}), 404
    sub = q("SELECT id, class_id FROM subjects WHERE id=?",
            (subject_id,), one=True)
    if not sub:
        return jsonify({"error": "subject not found"}), 404
    if sub["class_id"] != class_id:
        return jsonify({"error": "subject does not belong to this class"}), 400
    if session["user"]["role"] == "teacher":
        tid = my_teacher_id()
        if not q("SELECT 1 FROM teacher_assignment WHERE teacher_id=? "
                 "AND class_id=? AND subject_id=?",
                 (tid, class_id, subject_id), one=True):
            return jsonify(
                {"error": "forbidden: class+subject not assigned to you"}), 403
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "PDF file required"}), 400
    try:
        stored = _save_upload(f, NOTES_DIR, "note", NOTE_ALLOWED_EXT)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    rid = run(
        """INSERT INTO notes (class_id, subject_id, title, file_path, uploaded_by)
           VALUES (?,?,?,?,?) RETURNING id""",
        (class_id, subject_id, title, stored, session["user"]["id"]))
    return jsonify({"ok": True, "id": rid})


@app.get("/api/notes/<int:nid>/file")
@auth()
def note_file(nid):
    n = q("SELECT * FROM notes WHERE id=?", (nid,), one=True)
    if not n:
        return jsonify({"error": "note not found"}), 404
    if session["user"]["role"] == "student":
        sid = my_student_id()
        stu = q("SELECT class_id FROM students WHERE id=?", (sid,), one=True)
        if not stu or stu["class_id"] != n["class_id"]:
            return jsonify({"error": "forbidden"}), 403
    return send_from_directory(NOTES_DIR, os.path.basename(n["file_path"]),
                               as_attachment=True,
                               download_name="note-%d.pdf" % nid)


@app.delete("/api/notes/<int:nid>")
@auth("super_admin", "principal", "teacher")
def note_del(nid):
    n = q("SELECT * FROM notes WHERE id=?", (nid,), one=True)
    if not n:
        return jsonify({"error": "note not found"}), 404
    if session["user"]["role"] == "teacher" \
            and n["uploaded_by"] != session["user"]["id"]:
        return jsonify({"error": "forbidden: not your upload"}), 403
    run("DELETE FROM notes WHERE id=?", (nid,))
    _remove_upload(NOTES_DIR, n["file_path"])
    return jsonify({"ok": True})


# ---------- teacher leaves ----------
@app.get("/api/leaves")
@auth("super_admin", "principal", "teacher")
def leaves_list():
    where, args = ["1=1"], []
    if session["user"]["role"] == "teacher":
        tid = my_teacher_id()
        if not tid:
            return jsonify({"error": "no teacher record linked"}), 404
        where.append("l.teacher_id=?")
        args.append(tid)
    if request.args.get("status") in ("PENDING", "APPROVED", "REJECTED"):
        where.append("l.status=?")
        args.append(request.args["status"])
    return jsonify(q(
        """SELECT l.id, l.teacher_id, t.name AS teacher_name,
                  l.date_from, l.date_to, l.reason, l.status,
                  u.username AS decided_by_name, l.decided_at, l.created_at
           FROM teacher_leaves l
           JOIN teachers t ON t.id=l.teacher_id
           LEFT JOIN users u ON u.id=l.decided_by
           WHERE %s ORDER BY l.id DESC""" % " AND ".join(where), args))


@app.post("/api/leaves")
@auth("teacher")
def leave_add():
    tid = my_teacher_id()
    if not tid:
        return jsonify({"error": "no teacher record linked"}), 400
    d = _body()
    try:
        dfi = date.fromisoformat(d.get("date_from") or "")
        dti = date.fromisoformat(d.get("date_to") or "")
    except ValueError:
        return jsonify({"error": "date_from/date_to must be YYYY-MM-DD"}), 400
    if dti < dfi:
        return jsonify({"error": "date_to cannot be before date_from"}), 400
    rid = run(
        """INSERT INTO teacher_leaves (teacher_id, date_from, date_to, reason)
           VALUES (?,?,?,?) RETURNING id""",
        (tid, dfi.isoformat(), dti.isoformat(),
         (d.get("reason") or "").strip() or None))
    audit("leave_create", "teacher_leave", rid,
          {"teacher_id": tid, "date_from": dfi.isoformat(),
           "date_to": dti.isoformat()})
    return jsonify({"ok": True, "id": rid})


@app.post("/api/leaves/<int:lid>/approve")
@auth("super_admin", "principal")
def leave_approve(lid):
    lv = q("SELECT * FROM teacher_leaves WHERE id=?", (lid,), one=True)
    if not lv:
        return jsonify({"error": "leave not found"}), 404
    if lv["status"] != "PENDING":
        return jsonify({"error": "leave already decided"}), 400
    run("UPDATE teacher_leaves SET status='APPROVED', decided_by=?, "
        "decided_at=CURRENT_TIMESTAMP WHERE id=?", (session["user"]["id"], lid))
    audit("leave_approve", "teacher_leave", lid, {})
    return jsonify({"ok": True})


@app.post("/api/leaves/<int:lid>/reject")
@auth("super_admin", "principal")
def leave_reject(lid):
    lv = q("SELECT * FROM teacher_leaves WHERE id=?", (lid,), one=True)
    if not lv:
        return jsonify({"error": "leave not found"}), 404
    if lv["status"] != "PENDING":
        return jsonify({"error": "leave already decided"}), 400
    run("UPDATE teacher_leaves SET status='REJECTED', decided_by=?, "
        "decided_at=CURRENT_TIMESTAMP WHERE id=?", (session["user"]["id"], lid))
    audit("leave_reject", "teacher_leave", lid, {})
    return jsonify({"ok": True})


# ---------- warnings (misbehavior warnings) ----------
WARN_REASONS = ("Late arrival", "Uniform violation", "Misbehavior",
                "Absence without leave", "Student complaint", "Other")


@app.get("/api/warnings")
@auth("super_admin", "principal", "teacher", "student")
def warnings_list():
    where, args = ["1=1"], []
    role = session["user"]["role"]
    if role == "teacher":
        tid = my_teacher_id()
        if not tid:
            return jsonify({"error": "no teacher record linked"}), 404
        where.append("w.teacher_id=?")
        args.append(tid)
    elif role == "student":
        sid = my_student_id()
        if not sid:
            return jsonify({"error": "no student record linked"}), 404
        where.append("w.student_id=?")
        args.append(sid)
    if request.args.get("person_type") in ("TEACHER", "STUDENT"):
        where.append("w.person_type=?")
        args.append(request.args["person_type"])
    return jsonify(q(
        """SELECT w.id, w.person_type, w.teacher_id, w.student_id,
                  COALESCE(t.name, st.name) AS person_name,
                  w.warn_date, w.reason, w.warning_text,
                  u.username AS issued_by_name, w.issued_at
           FROM warnings w
           LEFT JOIN teachers t ON t.id=w.teacher_id
           LEFT JOIN students st ON st.id=w.student_id
           LEFT JOIN users u ON u.id=w.issued_by
           WHERE %s ORDER BY w.issued_at DESC, w.id DESC"""
        % " AND ".join(where), args))


@app.post("/api/warnings")
@auth("super_admin")
def warning_add():
    d = _body()
    ptype = (d.get("person_type") or "").strip().upper()
    if ptype not in ("TEACHER", "STUDENT"):
        return jsonify({"error": "person_type must be TEACHER or STUDENT"}), 400
    teacher_id = d.get("teacher_id") or None
    student_id = d.get("student_id") or None
    if ptype == "TEACHER":
        if not teacher_id or not q("SELECT 1 FROM teachers WHERE id=?",
                                   (teacher_id,), one=True):
            return jsonify({"error": "valid teacher_id is required"}), 400
        student_id = None
    else:
        if not student_id or not q("SELECT 1 FROM students WHERE id=?",
                                   (student_id,), one=True):
            return jsonify({"error": "valid student_id is required"}), 400
        teacher_id = None
    reason = (d.get("reason") or "").strip()
    if reason not in WARN_REASONS:
        return jsonify({"error": "reason must be one of: " +
                                 ", ".join(WARN_REASONS)}), 400
    text = (d.get("warning_text") or "").strip()
    if not text:
        return jsonify({"error": "warning_text is required"}), 400
    try:
        rid = run(
            """INSERT INTO warnings (person_type, teacher_id, student_id,
                                     warn_date, reason, warning_text, issued_by)
               VALUES (?,?,?,COALESCE(?,CURRENT_DATE),?,?,?)
               RETURNING id""",
            (ptype, teacher_id, student_id, d.get("warn_date") or None,
             reason, text, session["user"]["id"]))
    except Exception:
        return jsonify({"error": "invalid warning data"}), 400
    audit("warning_issue", "warning", rid,
          {"person_type": ptype, "reason": reason})
    return jsonify({"ok": True, "id": rid})


@app.delete("/api/warnings/<int:wid>")
@auth("super_admin")
def warning_delete(wid):
    row = q("SELECT id FROM warnings WHERE id=?", (wid,), one=True)
    if not row:
        return jsonify({"error": "warning not found"}), 404
    run("DELETE FROM warnings WHERE id=?", (wid,))
    audit("warning_delete", "warning", wid, {})
    return jsonify({"ok": True})


# ---------- teacher complaints/suggestions ----------
COMPLAINT_CATEGORIES = ("School equipment", "Students", "Teachers",
                        "Clerk", "Other")


@app.get("/api/teacher-complaints")
@auth("super_admin", "teacher")
def teacher_complaints_list():
    where, args = ["1=1"], []
    if session["user"]["role"] == "teacher":
        tid = my_teacher_id()
        if not tid:
            return jsonify({"error": "no teacher record linked"}), 404
        where.append("tc.teacher_id=?")
        args.append(tid)
    return jsonify(q(
        """SELECT tc.id, tc.teacher_id, t.name AS teacher_name,
                  tc.category, tc.subject, tc.details, tc.status,
                  tc.resolution, u.username AS resolved_by_name,
                  tc.resolved_at, tc.created_at
           FROM teacher_complaints tc
           JOIN teachers t ON t.id=tc.teacher_id
           LEFT JOIN users u ON u.id=tc.resolved_by
           WHERE %s ORDER BY tc.created_at DESC, tc.id DESC"""
        % " AND ".join(where), args))


@app.post("/api/teacher-complaints")
@auth("teacher")
def teacher_complaint_add():
    tid = my_teacher_id()
    if not tid:
        return jsonify({"error": "no teacher record linked"}), 400
    d = _body()
    category = (d.get("category") or "").strip()
    if category not in COMPLAINT_CATEGORIES:
        return jsonify({"error": "category must be one of: " +
                                 ", ".join(COMPLAINT_CATEGORIES)}), 400
    details = (d.get("details") or "").strip()
    if not details:
        return jsonify({"error": "details are required"}), 400
    rid = run(
        """INSERT INTO teacher_complaints (teacher_id, category, subject, details)
           VALUES (?,?,?,?) RETURNING id""",
        (tid, category, (d.get("subject") or "").strip() or None, details))
    audit("teacher_complaint_create", "teacher_complaint", rid,
          {"category": category})
    return jsonify({"ok": True, "id": rid})


@app.post("/api/teacher-complaints/<int:cid>/resolve")
@auth("super_admin")
def teacher_complaint_resolve(cid):
    row = q("SELECT id FROM teacher_complaints WHERE id=?", (cid,), one=True)
    if not row:
        return jsonify({"error": "complaint not found"}), 404
    resolution = ((_body().get("resolution")) or "").strip()
    if not resolution:
        return jsonify({"error": "resolution is required"}), 400
    run("""UPDATE teacher_complaints
           SET status='RESOLVED', resolution=?, resolved_by=?,
               resolved_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (resolution, session["user"]["id"], cid))
    audit("teacher_complaint_resolve", "teacher_complaint", cid, {})
    return jsonify({"ok": True})


# ---------- announcements ----------
@app.get("/api/announcements")
@auth()
def announcements_list():
    role = session["user"]["role"]
    aud = ["'ALL'"]
    if role in ("teacher", "principal", "super_admin"):
        aud.append("'TEACHERS'")
    if role in ("student", "principal", "super_admin"):
        aud.append("'STUDENTS'")
    return jsonify(q(
        """SELECT a.id, a.title, a.body, a.audience, a.posted_at,
                  u.username AS posted_by_name
           FROM announcements a
           LEFT JOIN users u ON u.id=a.posted_by
           WHERE a.audience IN (%s)
           ORDER BY a.posted_at DESC, a.id DESC""" % ",".join(aud)))


@app.post("/api/announcements")
@auth("super_admin", "principal")
def announcement_add():
    d = _body()
    title = (d.get("title") or "").strip()
    body = (d.get("body") or "").strip()
    audience = (d.get("audience") or "ALL").upper()
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not body:
        return jsonify({"error": "body is required"}), 400
    if audience not in ("ALL", "TEACHERS", "STUDENTS"):
        return jsonify({"error": "audience must be ALL, TEACHERS or STUDENTS"}), 400
    rid = run(
        """INSERT INTO announcements (title, body, audience, posted_by)
           VALUES (?,?,?,?) RETURNING id""",
        (title, body, audience, session["user"]["id"]))
    return jsonify({"ok": True, "id": rid})


@app.delete("/api/announcements/<int:aid>")
@auth("super_admin", "principal")
def announcement_del(aid):
    if not q("SELECT 1 FROM announcements WHERE id=?", (aid,), one=True):
        return jsonify({"error": "announcement not found"}), 404
    run("DELETE FROM announcements WHERE id=?", (aid,))
    return jsonify({"ok": True})


# ---------- salaries & expenses ----------
def _hide_deductions(row):
    """Salary deduction breakdown is visible to super_admin ONLY.

    Every other role (principal, clerk, teacher, student) gets basic,
    allowances and net — never the deduction line items. Net-pay math
    is computed at write time and is left untouched."""
    if session["user"]["role"] != "super_admin":
        row.pop("deductions", None)
    return row


@app.get("/api/salaries")
@auth("super_admin", "principal")
def salaries_list():
    where, args = ["1=1"], []
    m = request.args.get("month")
    if m:
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", m):
            return jsonify({"error": "month must be YYYY-MM"}), 400
        where.append("s.sal_month=?")
        args.append(m)
    rows = q(
        """SELECT s.*, t.name AS teacher_name
           FROM salaries s JOIN teachers t ON t.id=s.teacher_id
           WHERE %s ORDER BY s.sal_month DESC, t.name""" % " AND ".join(where),
        args)
    for r in rows:
        _hide_deductions(r)
    return jsonify(rows)


@app.post("/api/salaries")
@auth("super_admin", "principal")
def salary_add():
    d = _body()
    tid = d.get("teacher_id")
    m = (d.get("sal_month") or "").strip()
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", m):
        return jsonify({"error": "sal_month must be YYYY-MM"}), 400
    if not q("SELECT 1 FROM teachers WHERE id=?", (tid,), one=True):
        return jsonify({"error": "teacher not found"}), 404
    try:
        basic = float(d.get("basic", 0))
        allow = float(d.get("allowances", 0))
        ded = float(d.get("deductions", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "basic/allowances/deductions must be numbers"}), 400
    if basic < 0 or allow < 0 or ded < 0:
        return jsonify({"error": "amounts cannot be negative"}), 400
    net = round(basic + allow - ded, 2)
    rid = run(
        """INSERT INTO salaries
           (teacher_id, sal_month, basic, allowances, deductions, net)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT (teacher_id, sal_month) DO UPDATE SET
             basic=EXCLUDED.basic, allowances=EXCLUDED.allowances,
             deductions=EXCLUDED.deductions, net=EXCLUDED.net
           RETURNING id""",
        (tid, m, basic, allow, ded, net))
    return jsonify({"ok": True, "id": rid, "net": net})


@app.post("/api/salaries/<int:sid>/pay")
@auth("super_admin", "principal")
def salary_pay(sid):
    if not q("SELECT 1 FROM salaries WHERE id=?", (sid,), one=True):
        return jsonify({"error": "salary not found"}), 404
    run("UPDATE salaries SET paid=TRUE, paid_at=CURRENT_TIMESTAMP WHERE id=?", (sid,))
    row = q("SELECT teacher_id, net, sal_month FROM salaries WHERE id=?",
            (sid,), one=True)
    audit("salary_pay", "salary", sid,
          {"teacher_id": row["teacher_id"], "net": row["net"],
           "sal_month": row["sal_month"]})
    return jsonify({"ok": True})


@app.get("/api/salaries/<int:sid>/payslip")
@auth("super_admin", "principal", "teacher")
def salary_payslip(sid):
    row = q(
        """SELECT s.*, t.name AS teacher_name, t.phone AS teacher_phone,
                  t.cnic AS teacher_cnic
           FROM salaries s JOIN teachers t ON t.id=s.teacher_id
           WHERE s.id=?""", (sid,), one=True)
    if not row:
        return jsonify({"error": "salary not found"}), 404
    if session["user"]["role"] == "teacher":
        # teachers may view ONLY their own payslip
        tid = my_teacher_id()
        if not tid or row["teacher_id"] != tid:
            return jsonify({"error": "forbidden"}), 403
    _hide_deductions(row)
    school = {k: _setting(k, "") for k in
              ("school_name", "school_address", "school_phone", "school_logo")}
    return jsonify({"school": school, "payslip": row, "salary": row})


@app.get("/api/expenses")
@auth("super_admin", "principal")
def expenses_list():
    return jsonify(q(
        """SELECT e.*, u.username AS added_by_name
           FROM expenses e LEFT JOIN users u ON u.id=e.added_by
           ORDER BY e.expense_date DESC, e.id DESC"""))


@app.post("/api/expenses")
@auth("super_admin", "principal")
def expense_add():
    d = _body()
    title = (d.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    try:
        amt = float(d.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be a number"}), 400
    if amt <= 0:
        return jsonify({"error": "amount must be > 0"}), 400
    rid = run(
        """INSERT INTO expenses (title, amount, category, expense_date, added_by)
           VALUES (?,?,?,COALESCE(?,CURRENT_DATE),?) RETURNING id""",
        (title, amt, d.get("category"), d.get("expense_date") or None,
         session["user"]["id"]))
    return jsonify({"ok": True, "id": rid})


@app.delete("/api/expenses/<int:eid>")
@auth("super_admin", "principal")
def expense_del(eid):
    if not q("SELECT 1 FROM expenses WHERE id=?", (eid,), one=True):
        return jsonify({"error": "expense not found"}), 404
    run("DELETE FROM expenses WHERE id=?", (eid,))
    return jsonify({"ok": True})


# ---------- ID cards & certificates ----------
@app.get("/api/students/<int:sid>/idcard")
@auth("super_admin", "principal", "clerk")
def student_idcard(sid):
    rec = q(
        """SELECT s.id, s.name, s.admission_no, s.father_name,
                  c.name AS class_name, c.section
           FROM students s LEFT JOIN classes c ON c.id=s.class_id
           WHERE s.id=?""", (sid,), one=True)
    if not rec:
        return jsonify({"error": "student not found"}), 404
    school = {k: _setting(k, "") for k in
              ("school_name", "school_address", "school_phone", "school_logo")}
    rec["photo_url"] = "/api/students/%d/photo" % sid
    return jsonify({"school": school, "student": rec})


@app.post("/api/certificates")
@auth("super_admin", "principal")
def certificate_issue():
    d = _body()
    sid = d.get("student_id")
    ctype = (d.get("cert_type") or "").upper()
    if ctype not in ("CHARACTER", "STUDY", "LEAVING", "SPORTS"):
        return jsonify({"error": "cert_type must be CHARACTER, STUDY, LEAVING or SPORTS"}), 400
    if not q("SELECT 1 FROM students WHERE id=?", (sid,), one=True):
        return jsonify({"error": "student not found"}), 404
    leaving_date = (d.get("leaving_date") or None) if ctype == "LEAVING" else None
    reason = ((d.get("reason") or "").strip() or None) \
        if ctype == "LEAVING" else None
    achievement = ((d.get("achievement") or "").strip() or None) \
        if ctype == "SPORTS" else None
    rid = run(
        """INSERT INTO certificates (student_id, cert_type, issued_by,
                                     leaving_date, reason, achievement)
           VALUES (?,?,?,?,?,?) RETURNING id""",
        (sid, ctype, session["user"]["id"], leaving_date, reason, achievement))
    audit("certificate_issue", "certificate", rid,
          {"student_id": sid, "cert_type": ctype})
    return jsonify({"ok": True, "id": rid})


@app.post("/api/certificates/generate-class")
@auth("super_admin", "principal", "clerk")
def certificates_generate_class():
    d = _body()
    cid = d.get("class_id")
    ctype = (d.get("cert_type") or "").upper()
    if ctype not in ("CHARACTER", "STUDY", "SPORTS"):
        return jsonify({"error": "cert_type must be CHARACTER, STUDY or SPORTS"}), 400
    if not q("SELECT 1 FROM classes WHERE id=?", (cid,), one=True):
        return jsonify({"error": "class not found"}), 404
    studs = q("SELECT id FROM students WHERE class_id=? AND status='Active' "
              "ORDER BY id", (cid,))
    created, skipped = 0, 0
    for s in studs:
        if q("SELECT 1 FROM certificates WHERE student_id=? AND cert_type=?",
             (s["id"], ctype), one=True):
            skipped += 1
            continue
        run("""INSERT INTO certificates (student_id, cert_type, issued_by)
               VALUES (?,?,?)""",
            (s["id"], ctype, session["user"]["id"]))
        created += 1
    audit("certificates_generate_class", None, None,
          {"class_id": cid, "cert_type": ctype,
           "created": created, "skipped": skipped})
    return jsonify({"ok": True, "created": created, "skipped": skipped})


@app.get("/api/certificates")
@auth("super_admin", "principal", "clerk")
def certificates_list():
    where, args = ["1=1"], []
    if request.args.get("student_id"):
        where.append("c.student_id=?")
        args.append(int(request.args["student_id"]))
    return jsonify(q(
        """SELECT c.*, s.name AS student_name, s.admission_no,
                  s.admission_date, s.father_name,
                  cl.name AS class_name, cl.section,
                  u.username AS issued_by_name
           FROM certificates c
           JOIN students s ON s.id=c.student_id
           LEFT JOIN classes cl ON cl.id=s.class_id
           LEFT JOIN users u ON u.id=c.issued_by
           WHERE %s ORDER BY c.id DESC""" % " AND ".join(where), args))


# ---------- reports ----------
@app.get("/api/reports/fee-collection")
@auth("super_admin", "principal")
def report_fee_collection():
    m = request.args.get("month") or date.today().strftime("%Y-%m")
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", m):
        return jsonify({"error": "month must be YYYY-MM"}), 400
    collected = q(
        "SELECT COALESCE(SUM(amount),0) AS v FROM fee_payments "
        "WHERE strftime('%Y-%m', paid_at)=?", (m,), one=True)["v"]
    pending = q(
        "SELECT COALESCE(SUM(total-paid),0) AS v FROM fee_invoices "
        "WHERE fee_month=? AND status IN ('UNPAID','PARTIAL','OVERDUE')",
        (m,), one=True)["v"]
    by_method = q(
        """SELECT method, COUNT(*) AS n, SUM(amount) AS total
           FROM fee_payments WHERE strftime('%Y-%m', paid_at)=?
           GROUP BY method ORDER BY method""", (m,))
    return jsonify({"month": m, "collected": collected, "pending": pending,
                    "by_method": by_method})


@app.get("/api/reports/attendance")
@auth("super_admin", "principal")
def report_attendance():
    where, args = ["1=1"], []
    if request.args.get("class_id"):
        where.append("a.class_id=?")
        args.append(int(request.args["class_id"]))
    m = request.args.get("month")
    if m:
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", m):
            return jsonify({"error": "month must be YYYY-MM"}), 400
        where.append("strftime('%Y-%m', a.att_date)=?")
        args.append(m)
    r = q(
        """SELECT COUNT(*) AS total_days,
                  COUNT(*) FILTER (WHERE status='PRESENT') AS present_days
           FROM attendance a WHERE %s""" % " AND ".join(where), args,
        one=True)
    pct = round(100.0 * r["present_days"] / r["total_days"], 1) \
        if r["total_days"] else 0
    return jsonify({"pct": pct, "present_days": r["present_days"],
                    "total_days": r["total_days"]})


# ---------- settings ----------
@app.get("/api/settings")
@auth("super_admin", "principal")
def settings_get():
    rows = q("SELECT key, value FROM settings WHERE key NOT IN ('gemini_api_key', 'gemini_model')")
    data = {r["key"]: r["value"] for r in rows}
    cfg = _get_gemini_config()
    data["ai_configured"] = bool(cfg["api_key"])
    return jsonify(data)


@app.post("/api/settings")
@auth("super_admin")
def settings_set():
    """super_admin ONLY. Principal gets 403 from the decorator."""
    d = _body()
    key = (d.get("key") or "").strip()
    if not key:
        return jsonify({"error": "key is required"}), 400
    if key in ("gemini_api_key", "gemini_model"):
        return jsonify({"ok": True})
    run("INSERT INTO settings (key, value) VALUES (?,?) "
        "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
        (key, d.get("value", "")))
    audit("settings_update", "setting", key, {"value": d.get("value", "")})
    return jsonify({"ok": True})


@app.get("/api/public-settings")
@auth_public
def public_settings():
    rows = q("SELECT key, value FROM settings "
             "WHERE key IN ('school_name','school_logo','theme_color',"
             "'school_rules','school_history','school_facilities')")
    return jsonify({r["key"]: r["value"] for r in rows})


# ---------- school logo upload (super_admin uploads a picture file) ----------
def _logo_filename():
    for f in os.listdir(LOGO_DIR):
        if f.startswith("logo.") and os.path.isfile(os.path.join(LOGO_DIR, f)):
            return f
    return None


@app.post("/api/settings/logo")
@auth("super_admin")
def settings_logo_upload():
    f = request.files.get("logo") or request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "logo picture required"}), 400
    ext = (f.filename.rsplit(".", 1)[-1].lower()
           if "." in (f.filename or "") else "")
    if ext not in LOGO_ALLOWED_EXT:
        return jsonify({"error": "picture type not allowed (allowed: %s)"
                                 % ", ".join(sorted(LOGO_ALLOWED_EXT))}), 400
    data = f.read()
    if len(data) > LOGO_MAX_BYTES:
        return jsonify({"error": "picture too large (max 2MB)"}), 400
    old = _logo_filename()
    if old:
        try:
            os.remove(os.path.join(LOGO_DIR, old))
        except OSError:
            pass
    with open(os.path.join(LOGO_DIR, "logo." + ext), "wb") as fh:
        fh.write(data)
    run("INSERT INTO settings (key, value) VALUES ('school_logo','/api/logo') "
        "ON CONFLICT (key) DO UPDATE SET value='/api/logo'")
    audit("settings_update", "setting", "school_logo",
          {"value": "/api/logo", "via": "upload"})
    return jsonify({"ok": True, "school_logo": "/api/logo"})


@app.get("/api/logo")
@auth_public
def logo_get():
    fn = _logo_filename()
    if not fn:
        return jsonify({"error": "no logo uploaded"}), 404
    return send_from_directory(LOGO_DIR, fn)


# ---------- about sections (extra About School info; super_admin manages) ----------
@app.get("/api/about-sections")
@auth()
def about_sections_list():
    return jsonify(q("SELECT id, title, body, sort_order, created_at, updated_at "
                     "FROM about_sections ORDER BY sort_order, id"))


@app.post("/api/about-sections")
@auth("super_admin")
def about_section_add():
    d = _body()
    title = (d.get("title") or "").strip()
    body = (d.get("body") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not body:
        return jsonify({"error": "text is required"}), 400
    try:
        so = int(d.get("sort_order") or 0)
    except (TypeError, ValueError):
        so = 0
    rid = run("INSERT INTO about_sections (title, body, sort_order) "
              "VALUES (?,?,?) RETURNING id", (title, body, so))
    audit("about_section_add", "about_section", rid, {"title": title})
    return jsonify({"ok": True, "id": rid})


@app.put("/api/about-sections/<int:sid>")
@auth("super_admin")
def about_section_edit(sid):
    row = q("SELECT id FROM about_sections WHERE id=?", (sid,), one=True)
    if not row:
        return jsonify({"error": "section not found"}), 404
    d = _body()
    title = (d.get("title") or "").strip()
    body = (d.get("body") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not body:
        return jsonify({"error": "text is required"}), 400
    try:
        so = int(d.get("sort_order") or 0)
    except (TypeError, ValueError):
        so = 0
    run("UPDATE about_sections SET title=?, body=?, sort_order=?, "
        "updated_at=CURRENT_TIMESTAMP WHERE id=?", (title, body, so, sid))
    audit("about_section_edit", "about_section", sid, {"title": title})
    return jsonify({"ok": True})


@app.delete("/api/about-sections/<int:sid>")
@auth("super_admin")
def about_section_delete(sid):
    row = q("SELECT id, title FROM about_sections WHERE id=?",
            (sid,), one=True)
    if not row:
        return jsonify({"error": "section not found"}), 404
    run("DELETE FROM about_sections WHERE id=?", (sid,))
    audit("about_section_delete", "about_section", sid,
          {"title": row["title"]})
    return jsonify({"ok": True})


# ---------- audit log & backup ----------
@app.get("/api/audit-log")
@auth("super_admin")
def audit_log_list():
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
    except (TypeError, ValueError):
        limit = 100
    return jsonify(q("SELECT id, user_id, username, role, action, entity, "
                     "entity_id, details, created_at FROM audit_log "
                     "ORDER BY id DESC LIMIT ?", (limit,)))


@app.get("/api/backup")
@auth("super_admin")
def backup():
    staging = os.path.join(DATA_DIR, ".backup-staging.db")
    try:
        shutil.copy2(DB_PATH, staging)
    except Exception as e:
        return jsonify({"error": "backup failed: %s" % e}), 500
    audit("backup_download", None, None, {})
    return send_file(staging, as_attachment=True,
                     download_name="smschool-backup-%s.db"
                     % date.today().isoformat())


@app.post("/api/restore")
@auth("super_admin")
def restore():
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"error": "no file uploaded"}), 400
    blob = f.read()
    if len(blob) < 16 or blob[:16] != b"SQLite format 3\x00":
        return jsonify({"error": "not a valid SQLite database file"}), 400
    tmp = DB_PATH + ".restore-tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(blob)
        v = sqlite3.connect(tmp)
        try:
            n = v.execute("SELECT count(*) FROM sqlite_master "
                          "WHERE type='table'").fetchone()[0]
        finally:
            v.close()
        if not n:
            raise ValueError("no tables in uploaded file")
        os.replace(tmp, DB_PATH)
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return jsonify({"error": "restore failed: %s" % e}), 400
    audit("db_restore", None, None,
          {"filename": f.filename, "bytes": len(blob)})
    return jsonify({"ok": True})


# ---------- Gemini AI Assistant ----------
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"


def _get_gemini_config():
    """Retrieve Gemini configuration only from environment variables."""
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    model = (os.getenv("GEMINI_MODEL") or "").strip() or DEFAULT_GEMINI_MODEL
    custom_prompt = _setting("gemini_system_prompt", "").strip()
    return {"api_key": key, "model": model, "custom_prompt": custom_prompt}


def _build_ai_context(user):
    """Build live context for the AI prompt appropriate to user role."""
    school_name = _setting("school_name", "Our School")
    school_address = _setting("school_address", "")
    school_phone = _setting("school_phone", "")
    school_rules = _setting("school_rules", "")
    opening_time = _setting("opening_time", "")
    closing_time = _setting("closing_time", "")

    role = user.get("role", "")
    username = user.get("username", "")
    disp_name = user.get("display_name") or username

    lines = [
        f"School Name: {school_name}",
        f"Today's Date: {date.today().isoformat()}",
        f"Logged-in User: {disp_name} (Role: {role})"
    ]
    if school_address or school_phone:
        lines.append(f"School Contact: {school_address} {school_phone}".strip())
    if opening_time or closing_time:
        lines.append(f"School Timings: {opening_time} to {closing_time}".strip())
    if school_rules:
        lines.append(f"School Rules Summary: {school_rules[:400]}")

    if role in ("super_admin", "principal"):
        try:
            st_count = q("SELECT count(*) as c FROM students WHERE status='Active'", one=True)
            tc_count = q("SELECT count(*) as c FROM teachers WHERE status='Active'", one=True)
            cl_count = q("SELECT count(*) as c FROM classes", one=True)
            lines.append(f"Statistics: {st_count['c']} Active Students, {tc_count['c']} Active Teachers, {cl_count['c']} Classes.")
            cur_m = date.today().strftime('%Y-%m')
            f_stat = q("""
                SELECT count(*) as total_inv,
                       sum(case when status='PAID' then 1 else 0 end) as paid_inv,
                       coalesce(sum(total), 0) as total_amt,
                       coalesce(sum(paid), 0) as paid_amt
                FROM fee_invoices WHERE fee_month=?
            """, (cur_m,), one=True)
            if f_stat and f_stat["total_inv"]:
                lines.append(f"Fee status for {cur_m}: {f_stat['paid_inv']}/{f_stat['total_inv']} invoices paid. Total Billed: Rs {f_stat['total_amt']:,.0f}, Collected: Rs {f_stat['paid_amt']:,.0f}.")
        except Exception:
            pass
    elif role == "clerk":
        try:
            cur_m = date.today().strftime('%Y-%m')
            f_stat = q("""
                SELECT count(*) as total_inv,
                       sum(case when status='PAID' then 1 else 0 end) as paid_inv,
                       coalesce(sum(total), 0) as total_amt,
                       coalesce(sum(paid), 0) as paid_amt
                FROM fee_invoices WHERE fee_month=?
            """, (cur_m,), one=True)
            if f_stat and f_stat["total_inv"]:
                lines.append(f"Fee status for {cur_m}: {f_stat['paid_inv']}/{f_stat['total_inv']} invoices paid. Total Billed: Rs {f_stat['total_amt']:,.0f}, Collected: Rs {f_stat['paid_amt']:,.0f}.")
        except Exception:
            pass
    elif role == "teacher":
        try:
            tid = my_teacher_id()
            if tid:
                t_row = q("SELECT name, qualification FROM teachers WHERE id=?", (tid,), one=True)
                if t_row:
                    lines.append(f"Teacher Profile: {t_row['name']} ({t_row.get('qualification') or 'Staff'})")
                asgs = q("""
                    SELECT c.name as cname, c.section, s.name as sname
                    FROM teacher_assignment ta
                    JOIN classes c ON ta.class_id = c.id
                    JOIN subjects s ON ta.subject_id = s.id
                    WHERE ta.teacher_id = ?
                """, (tid,))
                if asgs:
                    classes_str = ", ".join(f"Class {a['cname']}-{a['section']} ({a['sname']})" for a in asgs)
                    lines.append(f"Assigned Teaching Subjects: {classes_str}")
        except Exception:
            pass
    elif role == "student":
        try:
            sid = my_student_id()
            if sid:
                s_row = q("""
                    SELECT s.name, s.roll_no, s.admission_no, c.name as cname, c.section
                    FROM students s
                    LEFT JOIN classes c ON s.class_id = c.id
                    WHERE s.id = ?
                """, (sid,), one=True)
                if s_row:
                    lines.append(f"Student: {s_row['name']}, Class: {s_row.get('cname')}-{s_row.get('section')}, Roll: {s_row.get('roll_no')}")
        except Exception:
            pass

    return "\n".join(lines)


def _call_gemini_api(api_key, model, messages, system_instruction):
    """Call Google Gemini REST API generateContent."""
    if not api_key:
        raise ValueError("Gemini API key is not configured in backend/.env.")

    clean_model = model.replace("models/", "").strip() or DEFAULT_GEMINI_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"

    contents = []
    for m in messages:
        role = "user" if m.get("role") == "user" else "model"
        text = (m.get("content") or "").strip()
        if text:
            contents.append({
                "role": role,
                "parts": [{"text": text}]
            })

    if not contents:
        raise ValueError("No message content to send.")

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048
        }
    }
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8")
            res = json.loads(body)
            candidates = res.get("candidates", [])
            if not candidates:
                feedback = res.get("promptFeedback", {})
                block = feedback.get("blockReason")
                if block:
                    return f"Response blocked by safety filters ({block})."
                return "Gemini did not return any response."
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and "text" in parts[0]:
                return parts[0]["text"]
            return "No text received in Gemini response."
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            err_msg = err_json.get("error", {}).get("message", str(e))
        except Exception:
            err_msg = f"HTTP {e.code}: {e.reason}"
        raise RuntimeError(f"Gemini API error ({e.code}): {err_msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error connecting to Gemini API: {e.reason}")
    except TimeoutError:
        raise RuntimeError("Gemini request timed out after 45 seconds.")


@app.get("/api/ai/status")
@auth()
def ai_status():
    cfg = _get_gemini_config()
    u = _active_user()
    return jsonify({
        "configured": bool(cfg["api_key"]),
        "has_custom_prompt": bool(cfg["custom_prompt"]),
        "user_role": u["role"] if u else "",
        "user_name": u.get("display_name") or (u.get("username") if u else "")
    })


@app.get("/api/ai/history")
@auth()
def ai_history():
    u = _active_user()
    limit = min(int(request.args.get("limit", 40)), 100)
    rows = q("""
        SELECT id, role, content, created_at
        FROM ai_chats
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (u["id"], limit))
    rows.reverse()
    return jsonify(rows)


@app.post("/api/ai/chat")
@auth()
def ai_chat():
    u = _active_user()
    b = _body()
    msg = (b.get("message") or "").strip()
    if not msg:
        return jsonify({"error": "Message is required"}), 400

    cfg = _get_gemini_config()
    if not cfg["api_key"]:
        return jsonify({
            "error": "Gemini AI is not configured on the server."
        }), 400

    # Save user message to database
    run("INSERT INTO ai_chats (user_id, role, content) VALUES (?, 'user', ?)",
        (u["id"], msg))

    # Retrieve recent chat history for context (last 10 messages)
    history_rows = q("""
        SELECT role, content
        FROM ai_chats
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
    """, (u["id"],))
    history_rows.reverse()

    # Build system instructions
    school_ctx = _build_ai_context(u)
    school_name = _setting("school_name", "School")
    sys_instruction = (
        f"You are the official Gemini AI Assistant built into {school_name}'s School Management System.\n"
        f"Current User: {u.get('display_name') or u.get('username')} (Role: {u.get('role')}).\n"
        "Guidelines:\n"
        "- Be professional, supportive, helpful, and concise.\n"
        "- Help teachers with lesson plans, quiz questions, curriculum guidelines, classroom ideas.\n"
        "- Help principals and admins with drafting circulars, summarizing operations, school management advice.\n"
        "- Help clerks with fee notices, fee calculations, admissions guidelines, WhatsApp messages.\n"
        "- Help students with study timetables, simplifying difficult concepts, and exam prep.\n"
        "- You understand both English and Urdu (English or Urdu Nastaliq or Roman Urdu).\n"
        "- When relevant, refer to the following school details:\n"
        f"{school_ctx}\n"
    )
    if cfg["custom_prompt"]:
        sys_instruction += f"\nCustom School Guidance:\n{cfg['custom_prompt']}\n"

    try:
        reply_text = _call_gemini_api(
            api_key=cfg["api_key"],
            model=cfg["model"],
            messages=history_rows,
            system_instruction=sys_instruction
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    # Save assistant response
    run("INSERT INTO ai_chats (user_id, role, content) VALUES (?, 'assistant', ?)",
        (u["id"], reply_text))

    return jsonify({
        "reply": reply_text
    })


@app.post("/api/ai/clear")
@auth()
def ai_clear():
    u = _active_user()
    run("DELETE FROM ai_chats WHERE user_id = ?", (u["id"],))
    return jsonify({"ok": True})


@app.post("/api/ai/test")
@auth("super_admin")
def ai_test():
    cfg = _get_gemini_config()
    if not cfg["api_key"]:
        return jsonify({"ok": False, "error": "Gemini API key is not configured on the server."}), 400

    try:
        test_messages = [{"role": "user", "content": "Hello Gemini, reply with 'READY' to confirm the API connection is active."}]
        resp = _call_gemini_api(
            api_key=cfg["api_key"],
            model=cfg["model"],
            messages=test_messages,
            system_instruction="You are a health-check responder."
        )
        return jsonify({
            "ok": True,
            "response": resp.strip()
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 400


# ---------- ER diagram (super_admin only) ----------
ER_PDF = os.path.join(os.path.dirname(BASE_DIR), "docs",
                      "SMS-ER-Diagram.pdf")


@app.get("/api/er-diagram")
@auth("super_admin")
def er_diagram():
    if not os.path.exists(ER_PDF):
        return jsonify({"error": "ER diagram not found"}), 404
    return send_file(ER_PDF, mimetype="application/pdf",
                     as_attachment=(request.args.get("dl") == "1"),
                     download_name="SMS-ER-Diagram.pdf")


# ---------- static ----------
@app.get("/")
@auth_public
def index():
    idx = os.path.join(os.path.dirname(BASE_DIR), "frontend", "index.html")
    if os.path.exists(idx):
        return send_file(idx)
    return jsonify({"error": "frontend not built yet"}), 404


@app.errorhandler(404)
def api_not_found(e):
    if request.path.startswith("/api"):
        return jsonify({"error": "not found"}), 404
    return e


# ---------- deny-by-default startup self-test ----------
def verify_auth_coverage():
    """Every route must declare permissions via @auth(...) or @auth_public.
    Fails loudly (and exposes gaps on /api/health) if any route lacks the
    __sms_auth__ metadata."""
    gaps = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        fn = app.view_functions.get(rule.endpoint)
        if not getattr(fn, "__sms_auth__", None):
            methods = sorted(m for m in (rule.methods or set())
                             if m not in ("HEAD", "OPTIONS"))
            gaps.append("%s %s -> %s" % ("/".join(methods), rule.rule,
                                         rule.endpoint))
    if gaps:
        print("!! AUTH COVERAGE GAP: %d route(s) lack a permission decorator:"
              % len(gaps))
        for g in gaps:
            print("!!   " + g)
        AUTH_GAPS.extend(gaps)
    else:
        n = sum(1 for r in app.url_map.iter_rules()
                if r.endpoint != "static")
        print("auth coverage OK: all %d routes declare permissions" % n)
    return gaps


ensure_db()
verify_auth_coverage()


if __name__ == "__main__":
    ensure_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
