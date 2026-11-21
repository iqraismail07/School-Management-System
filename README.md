# SMS-SCHOOL — School Management System (SQLite edition)

School Management System for a Pakistani school (KG to 10th).
**Python Flask + SQLite** backend with a JSON API under `/api/...`.
Roles: `super_admin`, `principal`, `clerk`, `teacher`, `student` (exactly these
five — see the role matrix below).

No database server, no password, no pgAdmin — the app creates its own
database file automatically on first run.

## Quick start (Windows)

1. Download or clone this repository and open the folder in VS Code.
2. Install requirements:

```powershell
pip install -r requirements.txt
```
3. Copy `backend/.env.example` to `backend/.env` and add your Gemini API key
   (get one free at https://aistudio.google.com/apikey):

```powershell
copy backend\.env.example backend\.env
```
4. Run the app:

```powershell
python backend/app.py
```
5. Open http://localhost:5000 in your browser.

No database setup is needed. On the first run the app creates `backend/data/sms.db` with demo data. To start fresh, stop the app, delete `backend/data/sms.db` and run it again.

### Demo logins (from seed)

| login | password | role | linked to |
|---|---|---|---|
| `superadmin` | `super123` | super_admin | — |
| `principal` | `prin123` | principal | — |
| `clerk` | `clerk123` | clerk | — |
| `tch1` | `teach123` | teacher | Ahmed Khan (teaches 8-A Mathematics, Science) |
| `std1` | `stu123` | student | Ali Raza (class 8-A) |

New users created inside the system get the default password `1234567`.

## Role matrix (summary)

- **super_admin** — everything: user management (all roles), teacher login
  accounts, **settings (super_admin ONLY)**, backup download + restore, audit
  log, dashboard.
- **principal** — school management: students, teachers incl. teacher login
  accounts (create / activate / deactivate / guarded delete), classes,
  subjects, attendance, exams, report cards, gazette, announcements, notes,
  salaries, expenses, ID cards, certificates, reports, dashboard. Fees &
  admissions: **view + report oversight only** (invoices, payments history,
  defaulters, challans, applications) — the daily fee/admission work
  (recording payments, refunds, late fees, concessions, generating invoices,
  approving/rejecting admissions) belongs to the clerk. Settings: **view
  only** — any settings change is 403.
- **clerk** — day-to-day control of TWO modules only: (a) fees (monthly
  invoice generation, payments, refunds, late fees, concessions, challans,
  defaulter list with WhatsApp text; fee-heads view only) and (b) admissions
  (new applications, approve/reject, enrolment incl. creating the student
  record and optional student login on approval). Plus: view students, print
  student ID cards (individual + class-wise), view announcements. NO
  certificate issuing (view/print + class-wide generation allowed),
  NO exams, NO attendance marking, NO salaries, NO settings,
  NO user management.
- **teacher** — only assigned classes+subjects: mark attendance, enter marks,
  upload notes, view announcements, own profile.
- **student** — own record only, view only.

Every route is guarded by `@auth(...)`; a deny-by-default startup self-test
`verify_auth_coverage()` prints loudly and lists gaps on `/api/health` if any
route lacks a permission declaration. Deactivated users are logged out on the
next request.

## API modules

Session · Users (incl. super_admin-only password reset via
POST /api/users/<id>/reset-password; everyone else changes only their own
password via POST /api/me/password) · Dashboard stats (incl. per-class latest
exam gazette top-5) · Classes & subjects · Admissions · Students (+ photo
upload) · Teachers (+ assignments, teacher login accounts) · Teacher leaves
(request / approve / reject) · Attendance · Fees (heads, monthly invoices,
payments, refunds, late fees, concessions, defaulters with WhatsApp text,
challan) · Exams & marks · Report cards · Gazette · Notes (PDF
upload/download) · Announcements · Salaries (+ payslip) · Expenses · ID cards ·
Certificates (CHARACTER/STUDY/LEAVING/SPORTS; issue: super_admin/principal;
  view/print + class-wide generation incl. clerk; leaving certs carry
  leaving_date + reason) · Timetable (class-wise weekly
  schedule) · Reports · Settings · About School sections · Audit log ·
Backup (database file download + restore, super_admin only).

Grading: 90+ A+, 80+ A, 70+ B, 60+ C, 50+ D, 40+ E, else F. Money in Rs.
Dates are ISO strings.

## Tables & relationships (for the ER diagram)

- `users` — logins. `role` ∈ super_admin/principal/clerk/teacher/student.
  `linked_student_id` → `students.id`, `linked_teacher_id` → `teachers.id`.
- `classes` — (`name`, `section`) unique, e.g. `8`/`A`, `10`/`B`.
- `subjects` — `class_id` → `classes.id` (CASCADE); (`class_id`, `name`) unique.
- `students` — `admission_no` unique; `class_id` → `classes.id`;
  `photo_path` → file in `backend/uploads/photos/`.
- `admissions` — applications; `student_id` → `students.id` set on approval.
- `teachers` — staff records.
- `teacher_assignment` — `teacher_id` → `teachers.id` (CASCADE),
  `class_id` → `classes.id` (CASCADE), `subject_id` → `subjects.id` (CASCADE);
  (`teacher_id`, `class_id`, `subject_id`) unique. Drives teacher permissions.
- `attendance` — `student_id` → `students.id` (CASCADE), `class_id` → `classes.id`,
  `marked_by` → `users.id`; (`student_id`, `att_date`) unique.
- `fee_heads` — `class_id` → `classes.id` (CASCADE) unique; monthly fee per class.
- `fee_invoices` — `student_id` → `students.id` (CASCADE);
  (`student_id`, `fee_month`) unique; `total = amount + late_fee − concession`.
- `fee_payments` — `invoice_id` → `fee_invoices.id` (CASCADE),
  `received_by` → `users.id`.
- `fee_concessions` — `student_id` → `students.id` (CASCADE),
  `granted_by` → `users.id`.
- `exams` — `class_id` → `classes.id` (CASCADE).
- `exam_marks` — `exam_id` → `exams.id` (CASCADE),
  `student_id` → `students.id` (CASCADE),
  `subject_id` → `subjects.id` (CASCADE);
  (`exam_id`, `student_id`, `subject_id`) unique.
- `notes` — `class_id` → `classes.id` (CASCADE),
  `subject_id` → `subjects.id` (CASCADE), `uploaded_by` → `users.id`;
  file in `backend/uploads/notes/`.
- `announcements` — `audience` ∈ ALL/TEACHERS/STUDENTS; `posted_by` → `users.id`.
- `salaries` — `teacher_id` → `teachers.id` (CASCADE);
  (`teacher_id`, `sal_month`) unique; `net = basic + allowances − deductions`.
- `expenses` — `added_by` → `users.id`.
- `teacher_leaves` — leave requests: `teacher_id` → `teachers.id` (CASCADE),
  `date_from`/`date_to`, `status` ∈ PENDING/APPROVED/REJECTED,
  `decided_by` → `users.id`.
- `timetables` — `class_id` → `classes.id` (CASCADE), `subject_id` →
  `subjects.id` (SET NULL), `teacher_id` → `teachers.id` (SET NULL);
  (`class_id`, `day_of_week`, `period_no`) unique; `day_of_week` ∈
  Monday..Saturday.
- `certificates` — `student_id` → `students.id` (CASCADE),
  `cert_type` ∈ CHARACTER/STUDY/LEAVING/SPORTS; `leaving_date` + `reason`
  (used for LEAVING), `achievement` (used for SPORTS); `issued_by` → `users.id`.
- `about_sections` — extra About School info sections (super_admin manages).
- `ai_chats` — Gemini AI Assistant persistent conversation history per user (`user_id`, `role`, `content`, `created_at`).
- `settings` — key/value store (school name, logo, theme color, opening/closing
  time, school rules, late fee %, address, phone, `gemini_api_key`, `gemini_model`, `gemini_system_prompt`).
- `audit_log` — who did what (user changes, payments, refunds, concessions,
  approvals, salary payments, settings changes, teacher login changes…).

## Project layout

```
sms-sqlite/
  backend/app.py            # complete Flask API (SQLite via stdlib sqlite3)
  backend/data/sms.db       # auto-created on first run (not shipped in the ZIP)
  backend/uploads/photos/   # student photos (served only via authenticated route)
  backend/uploads/notes/    # note PDFs (served only via authenticated route)
  backend/uploads/logos/    # school logo (served via public /api/logo)
  database/schema.sql       # full DDL in SQLite dialect — never edit after finishing; use migrations
  database/v2.sql           # migration: add 'clerk' to users.role check
  database/v3.sql           # migration: timetables table (class schedule module)
  database/v4.sql           # migration: warnings table (misbehavior warnings)
  database/v5.sql           # migration: teacher_complaints table (complaints to super_admin)
  database/v6.sql           # migration: teachers.photo_path column
  database/v7.sql           # migration: certificates LEAVING type + leaving_date/reason
  database/v8.sql           # migration: certificates SPORTS type + achievement
  database/v9.sql           # migration: about_sections table (extra About School info)
  database/v10.sql          # migration: ai_chats table (Gemini AI Assistant history)
  database/seed.sql         # demo data (SQLite dialect; procedural parts run from app.py)
  frontend/index.html       # single-file frontend, served from /
  docs/SMS-ER-Diagram.pdf   # ER diagram (25 tables)
  requirements.txt          # Flask only (sqlite3 is Python stdlib)
  README.md
```

## Gemini AI Assistant

The software includes an integrated Google Gemini AI Assistant accessible from:
1. The **Gemini AI** tab in the sidebar navigation.
2. The **floating ✨ Gemini AI button** present on every screen.

### Features
- **Role-Aware Context**: Automatically provides contextual school information to Gemini based on whether the logged-in user is a Super Admin, Principal, Teacher, Clerk, or Student.
- **Quick Action Prompts**: Pre-configured prompt chips for each role (Lesson plans, 5-question quizzes, PTM agendas, WhatsApp fee notices, student revision timetables).
- **Persistent Chat History**: Saved per user in the SQLite `ai_chats` table with instant copy and clear-chat options.
- **Bilingual**: Understands and answers in both English and Urdu (Urdu Nastaliq and Roman Urdu).
- **Zero Extra Dependencies**: Calls the official Google Gemini REST API using Python's standard library `urllib` (no heavy third-party packages needed).

### How to configure the Gemini API key

1. Get a free key at [Google AI Studio](https://aistudio.google.com/apikey).
2. Open `backend/.env` and set:
```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
```
3. Restart the app (`python backend/app.py`).
4. Login as `superadmin` / `super123`, go to **Settings** and click **Test Gemini Connection** to check that it works.
The key stays on the server in `.env` and is never shown in the Settings page. Super admin can still edit the custom AI instructions there.
If you see a 503 "high demand" error, wait a minute and try again.

## Notes & conventions

- Migrations: new tables/columns go in a new `database/vN.sql` — never edit
  `schema.sql` after it is finished.
- `python -m py_compile backend/app.py` must pass before delivery.
- SQLite notes: `SERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`;
  `now()` → `CURRENT_TIMESTAMP`; `to_char(x,'YYYY-MM')` →
  `strftime('%Y-%m', x)`; `ILIKE` → `LIKE`; `::type` casts → `CAST(x AS type)`.
  Foreign keys are enforced via `PRAGMA foreign_keys=ON` on every connection.
