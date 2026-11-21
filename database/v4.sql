-- SMS-SCHOOL v4: misbehavior warnings module (new table; run after v3.sql)
-- Only super_admin can issue; principal views; warned teacher/student sees own.
CREATE TABLE IF NOT EXISTS warnings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
