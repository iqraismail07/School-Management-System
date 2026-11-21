-- SMS-SCHOOL v7: school leaving certificate support (run after v6.sql)
-- Adds 'LEAVING' to cert_type and leaving-specific columns.
-- SQLite cannot DROP/ADD a named CHECK constraint, so the certificates
-- table is rebuilt with the widened check plus the new columns (rows
-- preserved, ids unchanged). sqlite3-safe and re-runnable (no DO block).
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS certificates_new;
CREATE TABLE certificates_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  cert_type TEXT NOT NULL CHECK (cert_type IN ('CHARACTER','STUDY','LEAVING')),
  issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  issued_by INTEGER REFERENCES users(id),
  leaving_date DATE,
  reason TEXT
);
INSERT INTO certificates_new (id, student_id, cert_type, issued_at, issued_by)
  SELECT id, student_id, cert_type, issued_at, issued_by FROM certificates;
DROP TABLE certificates;
ALTER TABLE certificates_new RENAME TO certificates;

PRAGMA foreign_keys=ON;
