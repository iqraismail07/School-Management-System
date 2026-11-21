-- SMS-SCHOOL v3: class timetable module (new table; run after v2.sql)
CREATE TABLE IF NOT EXISTS timetables (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
