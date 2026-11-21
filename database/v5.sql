-- SMS-SCHOOL v5: teacher complaints/suggestions module (new table; run after v4.sql)
-- Teachers file directly to super_admin; super_admin views and resolves.
CREATE TABLE IF NOT EXISTS teacher_complaints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
