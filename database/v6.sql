-- SMS-SCHOOL v6: teacher photo column (new column; run after v5.sql)
-- NOTE (SQLite): ADD COLUMN has no IF NOT EXISTS variant, so this is a plain
-- ALTER. Apply each migration once (or ignore a "duplicate column" error on re-run).
ALTER TABLE teachers ADD COLUMN photo_path TEXT;
