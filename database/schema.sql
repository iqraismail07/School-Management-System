-- ============================================================
-- SMS-SCHOOL — School Management System (KG to 10th)
-- Full database schema (SQLite)
--
-- Run order:  1) database/schema.sql  2) database/v2.sql .. v9.sql in order  3) database/seed.sql
--   sqlite3 backend/data/sms.db < database/schema.sql
--   sqlite3 backend/data/sms.db < database/v2.sql   (repeat for v3..v9)
--   sqlite3 backend/data/sms.db < database/seed.sql
--
-- CONVENTION: never edit this file after it is finished.
-- Future changes go in new migration files (database/v2.sql, ...).
-- ============================================================

-- ---------- lookup / core ----------
CREATE TABLE classes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,            -- 'KG','1',...,'10'
  section TEXT NOT NULL DEFAULT 'A',
  UNIQUE (name, section)
);

CREATE TABLE students (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE admissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE teachers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone TEXT,
  cnic TEXT,
  qualification TEXT,
  salary_monthly NUMERIC NOT NULL DEFAULT 0,
  joining_date DATE DEFAULT CURRENT_DATE,
  status TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active','Inactive'))
);

-- users references students + teachers, so it is created after them
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('super_admin','principal','teacher','student')),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  linked_student_id INTEGER REFERENCES students(id),
  linked_teacher_id INTEGER REFERENCES teachers(id),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE subjects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  UNIQUE (class_id, name)
);

CREATE TABLE teacher_assignment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  UNIQUE (teacher_id, class_id, subject_id)
);

-- ---------- attendance ----------
CREATE TABLE attendance (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  class_id INTEGER NOT NULL REFERENCES classes(id),
  att_date DATE NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PRESENT','ABSENT','LEAVE')),
  marked_by INTEGER REFERENCES users(id),
  UNIQUE (student_id, att_date)
);

-- ---------- fees ----------
CREATE TABLE fee_heads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  class_id INTEGER NOT NULL UNIQUE REFERENCES classes(id) ON DELETE CASCADE,
  monthly_amount NUMERIC NOT NULL
);

CREATE TABLE fee_invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE fee_payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES fee_invoices(id) ON DELETE CASCADE,
  amount NUMERIC NOT NULL,
  method TEXT DEFAULT 'Cash',
  paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  received_by INTEGER REFERENCES users(id),
  receipt_no TEXT
);

CREATE TABLE fee_concessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  fee_month TEXT NOT NULL,
  amount NUMERIC NOT NULL,
  reason TEXT,
  granted_by INTEGER REFERENCES users(id),
  granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------- exams ----------
CREATE TABLE exams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,                      -- 'First Term','Second Term','Annual'
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  year INTEGER NOT NULL,
  start_date DATE
);

CREATE TABLE exam_marks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  obtained NUMERIC NOT NULL,
  total NUMERIC NOT NULL DEFAULT 100,
  UNIQUE (exam_id, student_id, subject_id)
);

-- ---------- notes & announcements ----------
CREATE TABLE notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  file_path TEXT NOT NULL,
  uploaded_by INTEGER REFERENCES users(id),
  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE announcements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  audience TEXT NOT NULL DEFAULT 'ALL' CHECK (audience IN ('ALL','TEACHERS','STUDENTS')),
  posted_by INTEGER REFERENCES users(id),
  posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------- salaries & expenses ----------
CREATE TABLE salaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  amount NUMERIC NOT NULL,
  category TEXT,
  expense_date DATE DEFAULT CURRENT_DATE,
  added_by INTEGER REFERENCES users(id)
);

-- ---------- teacher leaves ----------
CREATE TABLE teacher_leaves (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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

-- ---------- certificates ----------
CREATE TABLE certificates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  cert_type TEXT NOT NULL CHECK (cert_type IN ('CHARACTER','STUDY')),
  issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  issued_by INTEGER REFERENCES users(id)
);

-- ---------- settings & audit ----------
CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  username TEXT,
  role TEXT,
  action TEXT NOT NULL,
  entity TEXT,
  entity_id TEXT,
  details JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
