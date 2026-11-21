# SMS-SCHOOL — Build Specification (v1)

School Management System for a Pakistani school, KG to 10th.
Python Flask + SQLite + single-file frontend. SQLite edition at `~/workspace/sms-sqlite/` (ported from `~/workspace/sms-school/`).
Do NOT touch `~/workspace/cms-basic/`.

Reference implementation (patterns only — copy the ideas, write new code):
- `~/workspace/cms-basic/backend/app.py` — the `@auth()` decorator, `_active_user()`,
  `verify_auth_coverage()` deny-by-default self-test, `q()`/`run()` DB helpers, `audit()`.
- `~/workspace/cms-basic/frontend/index.html` — structural patterns: role-based tabs,
  `ME` global, `api()` helper, dark mode toggle, print views.

## 1. Conventions (mandatory)

- One `@auth(...)` decorator guards EVERY route. `@auth()` = any logged-in active user.
  `@auth("super_admin","principal")` = listed roles only. `@auth_public` = login/health only.
- Deny-by-default: a startup self-test `verify_auth_coverage()` must walk
  `app.url_map` and FAIL LOUDLY (print + refuse to start... at minimum loud log)
  if any route lacks `__sms_auth__` metadata. No ad-hoc login checks.
- Server-side ownership: teachers only their assigned class+subject; students only
  their own record. Deactivated users are logged out on next request.
- Passwords: werkzeug `generate_password_hash` / `check_password_hash`.
- DB helpers: `q(sql, params, one=False)` returns dict rows (dates→isoformat,
  Decimal→float); `run(sql, params)` executes + commits, returns lastrow id.
- JSON API under `/api/...`. Frontend served from `/` (single `frontend/index.html`).
  Uploads stored under `backend/uploads/` (photos/, notes/), served only through
  authenticated download routes (never static).
- `requirements.txt`: Flask, Werkzeug (comes with Flask). sqlite3 is Python stdlib.
- Run: `python backend/app.py` (database auto-creates at backend/data/sms.db; no password, no database server needed).
  Bind `0.0.0.0:5000` (same as CMS).
- `python -m py_compile` must pass on backend. Frontend JS must pass `node --check`.
- CSS embedded in `frontend/index.html` (NO separate CSS file). Dark mode toggle for
  all roles, persisted in localStorage. Print views (`@media print`) stay light.
- Migrations: `database/schema.sql` (all tables), `database/seed.sql` (demo data).
  README lists run order: schema.sql → seed.sql.
- Grading (percentage → grade): 90+ A+, 80+ A, 70+ B, 60+ C, 50+ D, 40+ E, else F.
- Money in Rs (NUMERIC). Dates ISO strings.

## 2. Roles & demo logins

ROLES = ("super_admin", "principal", "clerk", "teacher", "student")

| login | password | role | linked to |
|---|---|---|---|
| superadmin | super123 | super_admin | — |
| principal | prin123 | principal | — |
| clerk | clerk123 | clerk | — |
| tch1 | teach123 | teacher | teacher "Ahmed Khan" |
| std1 | stu123 | student | student "Ali Raza" (class 8-A) |

Role matrix:
- **super_admin**: EVERYTHING. User management (create, activate/deactivate, delete
  for ALL roles), teacher login accounts, settings (school name, logo, theme color,
  opening time, closing time, school rules — SUPER_ADMIN ONLY), backup download,
  audit log, dashboard. Guard rules on delete: cannot delete yourself; cannot delete
  a user whose linked teacher/student has linked records (attendance/marks/invoices/
  payments/salaries) — return 400 with reason.
- **principal**: school management — students, teachers: full record management PLUS
  teacher login accounts (create login, activate/deactivate, guarded delete),
  subjects, classes, attendance (view + mark), exams, report cards, gazette,
  announcements (post), notes (view/download), salaries, expenses, certificates,
  ID cards, reports, dashboard. Fees & admissions: VIEW + REPORT oversight only
  (invoices, payments history, defaulters, challans, applications) — the daily
  fee/admission work (recording payments, refunds, late fees, concessions,
  generating invoices, approving/rejecting admissions) belongs to the clerk.
  Settings: VIEW ONLY — principal must NOT change any setting.
- **clerk**: day-to-day control of TWO modules only —
  (a) FEES: monthly invoice generation, payments, refunds, late fees, concessions,
  challans, defaulter list (with WhatsApp text); view fee-heads;
  (b) ADMISSIONS: new applications, approve/reject, enrolment (incl. creating the
  student record and optional student login on approval).
  Plus: view students (needed for the work), print student ID cards (individual +
  class-wise) and print character certificates (class-wise), view announcements.
  NO single-certificate issuance (principal/super_admin only), NO exams, NO attendance marking, NO salaries, NO settings, NO user management.
- **teacher**: ONLY classes+subjects assigned via teacher_assignment — mark attendance
  for assigned classes, enter marks for assigned subjects, upload notes for assigned
  class/subject, submit leave requests, view announcements, own profile.
  Everything else 403.
- **student**: ONLY own record — VIEW ONLY. Own fees/ledger, own attendance %,
  own results & report card, download notes for own class, view announcements,
  own profile. No editing, no admin powers.
- Roles are exactly these five: super_admin, principal, clerk, teacher, student.
  Do NOT add any other role.

## 3. Database schema (SQLite)

```sql
-- users
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('super_admin','principal','clerk','teacher','student')),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  linked_student_id INTEGER REFERENCES students(id),
  linked_teacher_id INTEGER REFERENCES teachers(id),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- classes
CREATE TABLE classes (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,            -- 'KG','1',...,'10'
  section TEXT NOT NULL DEFAULT 'A',
  UNIQUE (name, section)
);
-- subjects
CREATE TABLE subjects (
  id SERIAL PRIMARY KEY,
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  UNIQUE (class_id, name)
);
-- students
CREATE TABLE students (
  id SERIAL PRIMARY KEY,
  admission_no TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  father_name TEXT,
  gender TEXT CHECK (gender IN ('Male','Female')),
  dob DATE,
  class_id INTEGER REFERENCES classes(id),
  guardian_name TEXT,
  guardian_phone TEXT,
  address TEXT,
  photo_path TEXT,
  status TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active','Inactive')),
  admission_date DATE DEFAULT CURRENT_DATE
);
-- admissions
CREATE TABLE admissions (
  id SERIAL PRIMARY KEY,
  applicant_name TEXT NOT NULL,
  father_name TEXT,
  gender TEXT,
  dob DATE,
  apply_class TEXT NOT NULL,
  guardian_phone TEXT,
  address TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED')),
  applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  decided_at TIMESTAMP,
  student_id INTEGER REFERENCES students(id)
);
-- teachers
CREATE TABLE teachers (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  phone TEXT,
  cnic TEXT,
  qualification TEXT,
  salary_monthly NUMERIC NOT NULL DEFAULT 0,
  joining_date DATE DEFAULT CURRENT_DATE,
  status TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active','Inactive'))
);
-- teacher_assignment
CREATE TABLE teacher_assignment (
  id SERIAL PRIMARY KEY,
  teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  UNIQUE (teacher_id, class_id, subject_id)
);
-- attendance
CREATE TABLE attendance (
  id SERIAL PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  class_id INTEGER NOT NULL REFERENCES classes(id),
  att_date DATE NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PRESENT','ABSENT','LEAVE')),
  marked_by INTEGER REFERENCES users(id),
  UNIQUE (student_id, att_date)
);
-- fee_heads (monthly fee per class)
CREATE TABLE fee_heads (
  id SERIAL PRIMARY KEY,
  class_id INTEGER NOT NULL UNIQUE REFERENCES classes(id) ON DELETE CASCADE,
  monthly_amount NUMERIC NOT NULL
);
-- fee_invoices
CREATE TABLE fee_invoices (
  id SERIAL PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  fee_month TEXT NOT NULL,                 -- 'YYYY-MM'
  amount NUMERIC NOT NULL,
  late_fee NUMERIC NOT NULL DEFAULT 0,
  concession NUMERIC NOT NULL DEFAULT 0,
  total NUMERIC NOT NULL,
  paid NUMERIC NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'UNPAID'
    CHECK (status IN ('UNPAID','PARTIAL','PAID','OVERDUE')),
  due_date DATE,
  receipt_no TEXT UNIQUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (student_id, fee_month)
);
-- fee_payments
CREATE TABLE fee_payments (
  id SERIAL PRIMARY KEY,
  invoice_id INTEGER NOT NULL REFERENCES fee_invoices(id) ON DELETE CASCADE,
  amount NUMERIC NOT NULL,
  method TEXT DEFAULT 'Cash',
  paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  received_by INTEGER REFERENCES users(id),
  receipt_no TEXT
);
-- fee_concessions
CREATE TABLE fee_concessions (
  id SERIAL PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  fee_month TEXT NOT NULL,
  amount NUMERIC NOT NULL,
  reason TEXT,
  granted_by INTEGER REFERENCES users(id),
  granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- exams
CREATE TABLE exams (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,                      -- 'First Term','Second Term','Annual'
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  year INTEGER NOT NULL,
  start_date DATE
);
-- exam_marks
CREATE TABLE exam_marks (
  id SERIAL PRIMARY KEY,
  exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  obtained NUMERIC NOT NULL,
  total NUMERIC NOT NULL DEFAULT 100,
  UNIQUE (exam_id, student_id, subject_id)
);
-- notes (study material PDFs)
CREATE TABLE notes (
  id SERIAL PRIMARY KEY,
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  file_path TEXT NOT NULL,
  uploaded_by INTEGER REFERENCES users(id),
  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- announcements
CREATE TABLE announcements (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  audience TEXT NOT NULL DEFAULT 'ALL' CHECK (audience IN ('ALL','TEACHERS','STUDENTS')),
  posted_by INTEGER REFERENCES users(id),
  posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- salaries
CREATE TABLE salaries (
  id SERIAL PRIMARY KEY,
  teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  sal_month TEXT NOT NULL,                 -- 'YYYY-MM'
  basic NUMERIC NOT NULL DEFAULT 0,
  allowances NUMERIC NOT NULL DEFAULT 0,
  deductions NUMERIC NOT NULL DEFAULT 0,
  net NUMERIC NOT NULL DEFAULT 0,
  paid BOOLEAN NOT NULL DEFAULT FALSE,
  paid_at TIMESTAMP,
  UNIQUE (teacher_id, sal_month)
);
-- expenses
CREATE TABLE expenses (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  amount NUMERIC NOT NULL,
  category TEXT,
  expense_date DATE DEFAULT CURRENT_DATE,
  added_by INTEGER REFERENCES users(id)
);
-- teacher_leaves
CREATE TABLE teacher_leaves (
  id SERIAL PRIMARY KEY,
  teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  date_from DATE NOT NULL,
  date_to DATE NOT NULL,
  reason TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','APPROVED','REJECTED')),
  decided_by INTEGER REFERENCES users(id),
  decided_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- timetables (NEW module — lives in database/v3.sql, not schema.sql)
CREATE TABLE timetables (
  id SERIAL PRIMARY KEY,
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  day_of_week TEXT NOT NULL
    CHECK (day_of_week IN ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')),
  period_no INTEGER NOT NULL,
  start_time TEXT,
  end_time TEXT,
  subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
  teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
  room TEXT,
  UNIQUE (class_id, day_of_week, period_no)
);
-- warnings (NEW module — lives in database/v4.sql)
-- Only super_admin can issue; principal views; warned teacher/student sees own.
CREATE TABLE warnings (
  id SERIAL PRIMARY KEY,
  person_type TEXT NOT NULL CHECK (person_type IN ('TEACHER','STUDENT')),
  teacher_id INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
  student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
  warn_date DATE NOT NULL DEFAULT CURRENT_DATE,
  reason TEXT NOT NULL CHECK (reason IN ('Late arrival','Uniform violation',
    'Misbehavior','Absence without leave','Student complaint','Other')),
  warning_text TEXT NOT NULL,
  issued_by INTEGER REFERENCES users(id),
  issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CHECK ((person_type='TEACHER' AND teacher_id IS NOT NULL AND student_id IS NULL)
      OR (person_type='STUDENT' AND student_id IS NOT NULL AND teacher_id IS NULL))
);
-- teacher_complaints (NEW module — lives in database/v5.sql)
-- Teachers file complaints/suggestions directly to super_admin; super_admin resolves.
CREATE TABLE teacher_complaints (
  id SERIAL PRIMARY KEY,
  teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  category TEXT NOT NULL CHECK (category IN ('School equipment','Students',
    'Teachers','Clerk','Other')),
  subject TEXT,
  details TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED')),
  resolution TEXT,
  resolved_by INTEGER REFERENCES users(id),
  resolved_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- teacher photo (NEW — lives in database/v6.sql)
ALTER TABLE teachers ADD COLUMN IF NOT EXISTS photo_path TEXT;
CREATE TABLE certificates (
  id SERIAL PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  cert_type TEXT NOT NULL CHECK (cert_type IN ('CHARACTER','STUDY')),
  issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  issued_by INTEGER REFERENCES users(id)
);
-- settings
CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- audit_log
CREATE TABLE audit_log (
  id SERIAL PRIMARY KEY,
  user_id INTEGER,
  username TEXT,
  role TEXT,
  action TEXT NOT NULL,
  entity TEXT,
  entity_id TEXT,
  details JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Seed data (demo):
- 4 users as in §2 (passwords hashed): superadmin, principal, clerk, tch1, std1.
- classes: KG,1,2,3,4,5,6,7,8,9,10 section A; plus 10-B to show sections.
- subjects: KG–5: Urdu, English, Mathematics, Islamiat, Nazra Quran;
  6–8: Urdu, English, Mathematics, Science, Computer, Islamiat, Tarjuma-tul-Quran;
  9,10: Urdu, English, Mathematics, Physics, Chemistry, Biology, Computer Science,
  Islamiat, Pak Studies, Tarjuma-tul-Quran. (Apply per section row too — 10-A and
  10-B get the same subject list.)
- teachers: Ahmed Khan (8-A: Mathematics, Science), Sara Bibi (5-A: English, Urdu),
  Imran Shah (10-A: Physics, Mathematics). teacher_assignment rows accordingly.
  Link tch1 → Ahmed Khan.
- students: 12 demo students spread across KG,1,5,8-A,10-A; one is Ali Raza in 8-A
  linked to std1. admission_no like 'SMS-2026-001'.
- fee_heads: KG–5: 1500; 6–8: 2000; 9–10: 2500 (per class row).
- fee_invoices: for the CURRENT month (generate at seed time) for all Active
  students; one invoice PARTIAL with a payment; one OVERDUE from last month.
- exams: 'First Term' 2026 for class 8-A with marks for all 8-A students in
  Mathematics and Science (varied scores).
- announcements: 2 (one ALL, one STUDENTS).
- teacher_leaves: 1 sample PENDING request (Sara Bibi, 3 days next week, "Family wedding").
- salaries: current month rows for the 3 teachers (one paid).
- expenses: 3 rows (Electricity bill, Chalk & stationery, Building repair).
- settings: school_name='Anjum Grammer School', theme_color='#0d9488', school_logo='',
  opening_time='08:00 AM', closing_time='02:00 PM', school_rules='',
  late_fee_percent='5', school_address='Main Road', school_phone=''.

## 4. API contract

All responses JSON. Errors: {"error": "..."} with 400/401/403/404.
Auth: session cookie. Every route has @auth(...) except marked public.

### My Profile (NEW)
- GET /api/me/profile @auth() → {user:{id,username,role},
  teacher?:{id,name,phone,qualification,photo_url,status},
  assignments?:[{class_id,class_name,section,subject_id,subject_name}],
  student?:{id,admission_no,name,father_name,gender,dob,class_id,class_name,section,
    guardian_name,guardian_phone,address,photo_url,status},
  marks_summary?:[{exam_name,year,total_obtained,total_max,percentage,grade}]}
  (teacher key only for teachers, student+marks_summary only for students)
- POST /api/teachers/<id>/photo @auth("super_admin","principal") (multipart field
  "photo") → {ok:true}; GET /api/teachers/<id>/photo @auth() → image file (404 if none)

### Session (public: login, health)
- POST /api/login {username,password} → {ok, user:{id,username,role}} or 401
- POST /api/logout @auth() → {ok:true}
- GET /api/me @auth() → {id,username,role,linked_student_id,linked_teacher_id,student_name?,teacher_name?}
- POST /api/me/password @auth() {old,new} → {ok:true}
- GET /api/health @auth_public → {ok:true, auth_gaps:[...]}

### Users — @auth("super_admin") all
- GET /api/users → [{id,username,role,is_active,linked names}] — NEVER includes
  password or password_hash. The users table in the UI must never show passwords.
- POST /api/users {username,role,linked_student_id?,linked_teacher_id?} → {ok,id,username}.
  Default password for EVERY new user is '1234567' (no custom password at creation;
  the user changes it later via Change password). The response NEVER contains the
  password. The UI shows a "Copy login details" button that copies a WhatsApp-ready
  text (built client-side): "Assalam-o-Alaikum! Your school system login — Username:
  {username}, Password: 1234567. Please change your password after first login."
- POST /api/users/<id>/activate | /deactivate → {ok:true}
- POST /api/users/<id>/reset-password @auth("super_admin") {new_password} → {ok:true}.
  ONLY super_admin can change another user's password (audited). Every other user
  changes ONLY their own password via POST /api/me/password (requires old password).
- DELETE /api/users/<id> → 400 if self or linked records exist; else {ok:true}
- Audit every user change.
- NOTE: principal manages TEACHER login accounts through the teacher endpoints
  below, not through /api/users.

### Dashboard — @auth("super_admin","principal")
- GET /api/stats → {students, teachers, admissions_pending, admissions_total,
  fees_collected_month, fees_pending, attendance_today_pct, classes, exams,
  gazette: [{class_id, class_label, exam_id, exam_name, rows: top-5
  [{position, student_name, admission_no, total_obtained, percentage, grade}]}]}
  (gazette covers each class's latest exam; empty rows if no exam yet)

### Classes & subjects
- GET /api/classes @auth() → [{id,name,section,student_count}]
- POST /api/classes @auth("super_admin","principal") {name,section} → {ok,id}
- GET /api/subjects @auth() ?class_id= → [{id,class_id,class_name,section,name}]
- POST /api/subjects @auth("super_admin","principal") {class_id,name} → {ok,id}
- DELETE /api/subjects/<id> @auth("super_admin","principal")

### Admissions — view: @auth("super_admin","principal","clerk"); actions: @auth("super_admin","clerk")
- GET /api/admissions ?status= → list (principal: view oversight)
- POST /api/admissions {applicant_name,father_name,gender,dob,apply_class,guardian_phone,address} → {ok,id}
- POST /api/admissions/<id>/approve {class_id} → creates student (auto admission_no
  SMS-YYYY-NNN) + optional student user {make_login:true, username} with default
  password '1234567' (response has NO password; UI offers "Copy login details");
  sets status APPROVED. Audit.
- POST /api/admissions/<id>/reject → {ok:true}

### Students
- GET /api/students @auth("super_admin","principal","clerk") ?class_id=&q=&status=&subject_id=
  → list with class_name (subject_id filters to students whose class offers that subject;
  clerk: view only — no create/edit)
- GET /api/teacher/students @auth("teacher") → students of teacher's assigned classes
- GET /api/teacher/students @auth("teacher") → students of teacher's assigned classes
- GET /api/students/<id>/profile @auth() + ownership (student: own only; teacher:
  assigned class only; clerk: view any) → {student, attendance_pct, fee_summary, results}
- POST /api/students @auth("super_admin","principal") → {ok,id}
- PUT /api/students/<id> @auth("super_admin","principal") → {ok:true}
- POST /api/students/<id>/photo @auth("super_admin","principal") (multipart file) → {ok:true}
- GET /api/students/<id>/photo @auth() + ownership → image file (or 404)

### Teachers — @auth("super_admin","principal") except own profile
- GET /api/teachers → [{id,name,phone,qualification,salary_monthly,status,subjects}]
- POST /api/teachers {name,phone,cnic,qualification,salary_monthly, make_login, username}
  → {ok,id} (login uses default password '1234567'; response has NO password;
  UI offers "Copy login details")
- PUT /api/teachers/<id> → {ok:true}
- GET /api/teacher-assignments → list; POST /api/teacher-assignments {teacher_id,class_id,subject_id} → {ok,id};
  DELETE /api/teacher-assignments/<id>
- GET /api/me/teacher @auth("teacher") → own profile + assigned classes/subjects
- Teacher login accounts — @auth("super_admin","principal"):
  - POST /api/teachers/<id>/login {username} → creates users row
    (role='teacher', linked_teacher_id, default password '1234567'); 400 if teacher
    already has a login. Response has NO password. UI shows "Copy login details"
    button (WhatsApp-ready text). Audit.
  - POST /api/teachers/<id>/login/activate | /deactivate → toggles the linked
    user; 404 if no login exists. Audit.
  - DELETE /api/teachers/<id> → guarded: 400 if teacher has salary rows, notes,
    announcements, or attendance marked_by their user; else deletes teacher +
    linked login user. Audit.

### Attendance
- GET /api/attendance @auth("super_admin","principal") ?class_id=&date= → [{student_id,name,status}]
- GET /api/teacher/attendance @auth("teacher") ?class_id=&date= (class must be assigned) → same
- POST /api/attendance @auth("super_admin","principal") |
  @auth("teacher") with assigned-class check {class_id,date,records:[{student_id,status}]} → {ok:true}
  (upsert on (student_id, att_date))
- GET /api/attendance/absent @auth("super_admin","principal") ?date= → absent list
- GET /api/me/attendance @auth("student") → own records + percentage

### Fees
- GET /api/fee-heads @auth("super_admin","principal","clerk") → list (clerk: view only)
- POST /api/fee-heads @auth("super_admin","principal") {class_id,monthly_amount} (upsert) → {ok:true}
- POST /api/fee-invoices/generate-monthly @auth("super_admin","clerk") {fee_month}
  → {ok:true, created:n} (skips existing (student_id,fee_month); total=amount+late_fee-concession;
  due_date = month+10 days; receipt_no auto 'R-YYYYMM-NNN')
- GET /api/fee-invoices @auth("super_admin","principal","clerk") ?month=&status=&q= → list w/ student_name
- GET /api/me/invoices @auth("student") → own invoices
- POST /api/fee-payments @auth("super_admin","clerk") {invoice_id,amount,method}
  → {ok, receipt_no}; updates paid + status (PAID/PARTIAL). Audit.
- POST /api/fee-invoices/<id>/refund @auth("super_admin","clerk") {amount} → {ok:true}
- POST /api/fee-invoices/apply-late-fees @auth("super_admin","clerk") {fee_month}
  → adds late_fee_percent of amount to UNPAID/PARTIAL invoices past due_date, marks OVERDUE
- POST /api/fee-concessions @auth("super_admin","clerk") {student_id,fee_month,amount,reason}
  → {ok:true}; recalculates invoice total. Audit.
- GET /api/fee-defaulters @auth("super_admin","principal","clerk") ?month= →
  [{student_id,name,class_name,guardian_phone,pending, whatsapp_text}]
  whatsapp_text like: "Assalam-o-Alaikum! This is {school}: fee of Rs {pending} for {month}
  is pending for {name} (Class {class}). Please pay by {due}. Thank you."
- GET /api/fee-invoices/<id>/challan @auth("super_admin","principal","clerk") + student-own
  → challan print data {school, invoice, student}

### Exams
- GET /api/exams @auth() ?class_id= → list
- POST /api/exams @auth("super_admin","principal") {name,class_id,year,start_date} → {ok,id}
- GET /api/exam-marks @auth() ?exam_id= (teacher: assigned subject only; student: own only)
- POST /api/exam-marks @auth("super_admin","principal") | @auth("teacher") w/ subject-assigned check
  {exam_id, subject_id, rows:[{student_id,obtained,total}]} → {ok:true} (upsert)
- GET /api/report-card @auth() ?exam_id=&student_id= + ownership →
  {student, exam, subjects:[{name,obtained,total,grade}], total_obtained, total_max, percentage, grade, position?}
- GET /api/exams/<id>/gazette @auth("super_admin","principal") → class merit list

### Notes
- GET /api/notes @auth() ?class_id=&subject_id= (student: own class only) → list
- POST /api/notes @auth("super_admin","principal") | @auth("teacher") w/ class+subject assigned
  (multipart: class_id, subject_id, title, file .pdf) → {ok,id}
- GET /api/notes/<id>/file @auth() (+ student own-class check) → PDF download
- DELETE /api/notes/<id> @auth("super_admin","principal") (+ teacher own upload)

### Teacher leaves (NEW small module)
- GET /api/leaves @auth("super_admin","principal") → all [{id,teacher_id,teacher_name,
  date_from,date_to,reason,status,decided_by_name,decided_at}] ?status= filter;
  @auth("teacher") → own requests only.
- POST /api/leaves @auth("teacher") {date_from,date_to,reason} → {ok,id}
  (teacher resolved via users.linked_teacher_id; 400 if none). Audit.
- POST /api/leaves/<id>/approve | /reject @auth("super_admin","principal")
  → {ok:true}; sets decided_by/decided_at. Audit.

### Timetable (NEW module)
- GET /api/timetable @auth() ?class_id= → [{id,class_id,class_label,day_of_week,
  period_no,start_time,end_time,subject_id,subject_name,teacher_id,teacher_name,room}].
  Teachers: only their assigned classes (enforced). Students: own class only (class_id
  optional; defaults to own). Clerk/principal/super_admin: all.
- POST /api/timetable @auth("super_admin","principal","clerk")
  {class_id,day_of_week,period_no,start_time?,end_time?,subject_id?,teacher_id?,room?}
  → upsert on (class_id,day_of_week,period_no) → {ok,id}. Audit.
- DELETE /api/timetable/<id> @auth("super_admin","principal","clerk") → {ok:true}. Audit.

### Warnings (NEW module — misbehavior warnings)
- GET /api/warnings @auth("super_admin","principal") → all [{id,person_type,
  teacher_id,student_id,person_name,warn_date,reason,warning_text,issued_by_name,
  issued_at}] ?person_type= filter; @auth("teacher") → own warnings only (via
  users.linked_teacher_id); @auth("student") → own warnings only (via
  users.linked_student_id). Clerk: no access (403).
- POST /api/warnings @auth("super_admin") ONLY {person_type, teacher_id?,
  student_id?, warn_date?, reason, warning_text} → {ok,id}. Audit.
  reason is a category: 'Late arrival' | 'Uniform violation' | 'Misbehavior' |
  'Absence without leave' | 'Student complaint' | 'Other' (enforced by DB check;
  400 otherwise). 'Student complaint' = warning to a teacher when a student is
  not satisfied with that teacher.
- DELETE /api/warnings/<id> @auth("super_admin") → {ok:true}. Audit.

### Teacher complaints/suggestions (NEW module)
- GET /api/teacher-complaints @auth("super_admin") → all [{id,teacher_id,teacher_name,
  category,subject,details,status,resolution,resolved_by_name,resolved_at,created_at}];
  @auth("teacher") → own only. Other roles: 403 (principal included — this channel
  is directly to super_admin).
- POST /api/teacher-complaints @auth("teacher") {category, subject?, details}
  → {ok,id}. category in ('School equipment','Students','Teachers','Clerk','Other').
  teacher resolved via users.linked_teacher_id. Audit.
- POST /api/teacher-complaints/<id>/resolve @auth("super_admin") {resolution}
  → {ok:true}; sets status RESOLVED, resolved_by, resolved_at. Audit.

### Announcements
- GET /api/announcements @auth() → filtered by audience (ALL always; TEACHERS for
  teacher/principal/super_admin; STUDENTS for student/principal/super_admin)
- POST /api/announcements @auth("super_admin","principal") {title,body,audience} → {ok,id}
- DELETE /api/announcements/<id> @auth("super_admin","principal")

### Salaries & expenses — @auth("super_admin","principal")
- GET /api/salaries ?month= → [{id,teacher_name,month,basic,allowances,deductions,net,paid}]
- POST /api/salaries {teacher_id,sal_month,basic,allowances,deductions} → computes net, {ok,id}
- POST /api/salaries/<id>/pay → {ok:true} (sets paid, paid_at). Audit.
- GET /api/salaries/<id>/payslip → payslip print data
- GET /api/expenses → list; POST /api/expenses {title,amount,category,expense_date} → {ok,id};
  DELETE /api/expenses/<id> → {ok:true}

### ID cards & certificates
- ID cards (print): @auth("super_admin","principal","clerk")
- Certificates: issue = @auth("super_admin","principal") ONLY;
  print/view class-wise = @auth("super_admin","principal","clerk").
- GET /api/students/<id>/idcard → {school, student{name,admission_no,class_name,father_name,photo_url}}
- POST /api/certificates @auth("super_admin","principal") {student_id, cert_type, leaving_date?, reason?, achievement?}
  → {ok,id}; cert_type in ('CHARACTER','STUDY','LEAVING','SPORTS'). LEAVING = school leaving
  certificate (printable: student details, class, admission date, leaving date, reason).
  SPORTS = cricket sports certificate (participation/achievement; achievement text stored).
  GET /api/certificates @auth("super_admin","principal","clerk") ?student_id= → list
- POST /api/certificates/generate-class @auth("super_admin","principal","clerk") {class_id, cert_type}
  → creates a certificate of that type for every Active student in the class (skips students
  who already have one of the same type) → {ok:true, created:n, skipped:m}. Audit. This powers
  the class-wise printable certificates UI. cert_type for generate-class: CHARACTER, STUDY or
  SPORTS (LEAVING is issued individually, 400 otherwise).

### Reports — @auth("super_admin","principal")
- GET /api/reports/fee-collection ?month= → {collected, pending, by_method}
- GET /api/reports/attendance ?class_id=&month= → {pct, present_days, total_days}

### Settings
- GET /api/settings @auth("super_admin","principal") → {key:value} (principal: view only)
- POST /api/settings @auth("super_admin") ONLY {key,value} → {ok:true}.
  Principal MUST NOT be able to change any setting (school name, opening time,
  closing time, school rules, logo, theme color). Enforce server-side: 403 for
  principal. Audit.
- GET /api/public-settings @auth_public → {school_name, school_logo, theme_color, school_rules,
  school_history, school_facilities}
  (rules/history/facilities are public so the notice widget + About tab work for every role)
- Settings keys (seed): school_name, school_logo, theme_color, school_address,
  school_phone, opening_time ('08:00 AM'), closing_time ('02:00 PM'),
  school_rules ('1. Be punctual — assembly at 7:45 AM sharp. 2. Wear proper uniform daily. 3. Respect teachers and fellow students. 4. No mobile phones on campus.'),
  school_history ('Anjum Grammer School was founded with a mission to provide quality education...'),
  school_facilities ('Spacious classrooms, science laboratory, computer lab, library, playground...'),
  late_fee_percent ('5')

### Audit & backup — @auth("super_admin")
- GET /api/audit-log ?limit=100 → list
- GET /api/backup → streams pg_dump output as .sql download (subprocess pg_dump;
  if unavailable return 500 {"error":"pg_dump not available"})

### Static
- GET / → frontend/index.html @auth_public
- GET /api/* unknown → 404 JSON

## 5. Frontend requirements (single file `frontend/index.html`)

- Login screen (school name/logo from /api/public-settings).
- After login: header (school name, user chip, dark-mode toggle, "My Profile" button,
  change password, logout), role-based tab bar.
- ALWAYS-VISIBLE notice widget: a slim banner under the header on EVERY page showing
  the school rules (settings.school_rules, truncated) + the 3 latest announcement
  titles (clicking jumps to the Announcements tab). Visible to all roles.
- "My Profile" page (all roles, via header button): name, role, photo (student/teacher
  photo if set, else initial avatar), class/classes, contact info. Students also see
  a marks summary table (per exam: total, %, grade). Teachers see assigned classes.
- Role-based tab bar. Tabs per role:
  - super_admin: Dashboard, Students, Admissions, Teachers, Leaves, Subjects, Timetable, Attendance,
    Fees, Exams, Notes, Announcements, Salaries, Expenses, ID Cards, Certificates, Warnings, Complaints, Users, Audit Log, About, Settings
  - principal: Dashboard, Students, Admissions, Teachers, Leaves, Subjects, Timetable, Attendance,
    Fees, Exams, Notes, Announcements, Salaries, Expenses, ID Cards, Certificates, Warnings, Reports, About, Settings
  - teacher: Dashboard, My Classes, Timetable, Attendance, Exams, Notes, Leave, Complaints, Announcements, About
  - student: My Record, Timetable, Notes, Announcements, About
  - clerk: Fees, Admissions, Students (view-only: no add/edit/photo buttons), Timetable, ID Cards (print only), Certificates (print only), Announcements (view only), About
- Dashboard (super_admin/principal): stat cards — students, admissions (pending),
  teachers, attendance today %, fees collected this month, fees pending, exams —
  plus a CLASS-WISE RESULT GAZETTE widget: class dropdown → gazette table for the
  latest exam of that class (position, student, total, %, grade).
- Every tab: working tables + forms calling the API above. Keep it functional and
  clean — mirror the CMS frontend's straightforward style (no heavy frameworks).
- FILTERS (required): list pages must have a visible filter/search bar. Students list
  at minimum: (1) class-wise dropdown (All + each class/section), (2) admission/ID
  number search box (matches admission_no), (3) subject dropdown (shows students
  whose class offers that subject). Apply the same visible filter-bar pattern
  (class dropdown + text search) on the Teachers, Fees/invoices, Exams/marks and
  Notes lists wherever it fits.
- Print views: challan, report card, ID card, certificate, payslip — render into a
  print-only area and call window.print(); print CSS forces light theme.
- ID Cards tab: pick class → grid of printable student ID cards (photo, name,
  admission no, class, school name/logo).
- Certificates tab: per-student issue AND class-wise generation — pick class + cert
  type → "Generate for class" (POST /api/certificates/generate-class) → printable
  list of that class's certificates with a Print-all button (one certificate per
  printed page). Certificate types: Character, Study, School Leaving, Sports (cricket).
  For School Leaving the issue form also asks leaving date + reason, and the printout shows
  student details, class, admission date, leaving date and reason. For Sports the form asks
  participation/achievement text. EVERY certificate print has an "edit before print" step:
  the printed fields (student name, date of birth, father name, class, admission no.,
  plus leaving date/reason or achievement) open in an edit dialog pre-filled from the
  student record, changeable before printing. Clerk sees the tab print-only (no single-issue form).
- Leave tab (teacher "Leave"; super_admin/principal "Leaves"): teachers submit leave
  requests (date from/to, reason) and see their own requests with status; principal
  and super_admin see all requests with teacher names and Approve/Reject buttons.
- Timetable tab: super_admin/principal/clerk see a class picker + weekly grid
  (days × periods) with add/edit/delete per cell (subject, teacher, room, time);
  teacher sees view-only grid of own assigned classes; student sees view-only grid
  of own class.
- Users tab (super_admin): table with activate/deactivate/delete buttons + create form
  (no password field — default '1234567'). After creating any login (user, teacher
  login, student login on admission approval), show a "Copy login details" button
  that copies a WhatsApp-ready text with username + default password. Passwords are
  NEVER displayed in the page or the users table.
- Complaints tab: teacher sees "My Complaints" (file form: category dropdown —
  School equipment / Students / Teachers / Clerk / Other, subject, details text;
  own list with status + resolution); super_admin sees all teachers' complaints
  with Resolve buttons (resolution note → marks RESOLVED).
- About tab (ALL roles): school history + facilities, read from public settings.
  super_admin edits both texts in Settings (textareas); everyone else views.
- Warnings tab: super_admin sees issue form (person type Teacher/Student dropdown,
  person picker, date, reason dropdown: Late arrival / Uniform violation / Misbehavior /
  Absence without leave / Student complaint / Other, warning text) + full list with delete; principal sees
  view-only list. Warned teacher sees own warnings in teacher Dashboard ("My Warnings"
  section); warned student sees own warnings in My Record.
- Teachers tab: list, add (with optional login), assignments management (assign class+subject),
  and teacher login account management — for each teacher show linked login status with
  buttons: Create login / Activate / Deactivate / Delete teacher (guarded). These
  buttons are available to super_admin AND principal.
- Audit Log tab: table of audit entries.
- Settings tab: super_admin sees an editable form (school name, logo, theme color,
  opening time, closing time, school rules, late fee %, address, phone) + backup
  download button. Principal sees the SAME values READ-ONLY (no save button,
  no backup button).
- Dark mode: toggle in header, `body.dark` class, localStorage persistence.
- STYLING (required): polished, modern, clean CSS embedded in the file — card-based
  layout, consistent buttons/forms/tables, dashboard stat cards with clear visual
  hierarchy, responsive for mobile (tabs wrap, tables scroll horizontally, forms
  stack). Match or exceed the college system's styling quality. Print views stay
  light in dark mode.
- Plain JS, no build step. `node --check` must pass on the extracted script.

## 6. Test plan (run by the coordinator after build)

Delete backend/data/sms.db → start app (auto-creates + seeds) →
endpoint tests for every module + authorization matrix (each role × allowed/denied
routes expecting 403/401 where denied; ownership tests: teacher unassigned subject
403, student other-record 403, deactivated user 401).

## 7. Deliverables

- `~/workspace/sms-school/backend/app.py`, `~/workspace/sms-school/backend/uploads/`
- `~/workspace/sms-school/frontend/index.html`
- `~/workspace/sms-school/database/schema.sql`, `seed.sql`
- `~/workspace/sms-school/requirements.txt`, `~/workspace/sms-school/README.md`
  (run order, demo logins, Windows run commands like the CMS README)
- `~/workspace/sms-school.zip` (built by coordinator)
