-- ============================================================
-- SMS-SCHOOL v2: add the 'clerk' role (SPEC UPDATE 5)
-- Run AFTER database/schema.sql, BEFORE database/seed.sql.
-- SQLite cannot DROP/ADD a named CHECK constraint on an existing
-- table, so the users table is rebuilt with the widened five-role
-- list (rows preserved, ids unchanged). Idempotent: safe to run twice
-- (a second run rebuilds an identical table).
-- ============================================================

PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS users_new;
CREATE TABLE users_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('super_admin','principal','clerk','teacher','student')),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  linked_student_id INTEGER REFERENCES students(id),
  linked_teacher_id INTEGER REFERENCES teachers(id),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO users_new (id, username, password_hash, role, is_active,
  linked_student_id, linked_teacher_id, created_at)
  SELECT id, username, password_hash, role, is_active,
  linked_student_id, linked_teacher_id, created_at FROM users;
DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

PRAGMA foreign_keys=ON;
