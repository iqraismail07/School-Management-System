-- SMS-SCHOOL v8: sports certificate support (run after v7.sql)
-- Adds 'SPORTS' to cert_type and an achievement column.
-- SQLite cannot DROP/ADD a named CHECK constraint, so the certificates
-- table is rebuilt with the widened check plus the new column (rows
-- preserved, ids unchanged). sqlite3-safe and re-runnable (no DO block).
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS certificates_new;
CREATE TABLE certificates_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  cert_type TEXT NOT NULL CHECK (cert_type IN ('CHARACTER','STUDY','LEAVING','SPORTS')),
  issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  issued_by INTEGER REFERENCES users(id),
  leaving_date DATE,
  reason TEXT,
  achievement TEXT
);
INSERT INTO certificates_new (id, student_id, cert_type, issued_at, issued_by, leaving_date, reason)
  SELECT id, student_id, cert_type, issued_at, issued_by, leaving_date, reason FROM certificates;
DROP TABLE certificates;
ALTER TABLE certificates_new RENAME TO certificates;

PRAGMA foreign_keys=ON;
