-- SMS-SCHOOL v9: extra "About School" info sections (run after v8.sql)
-- super_admin adds unlimited sections (title + text); all roles view.
CREATE TABLE IF NOT EXISTS about_sections (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  title      TEXT NOT NULL,
  body       TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
