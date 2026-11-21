-- ============================================================
-- SMS-SCHOOL — demo seed data
-- Run AFTER database/schema.sql:
--   sqlite3 backend/data/sms.db < database/seed.sql
-- Plain sqlite3 CLI: no Python needed. Passwords below are precomputed
-- werkzeug scrypt hashes for: super123 / prin123 / teach123 / stu123.
-- Fee invoices are generated for the CURRENT month at seed time
-- (strftime('%Y-%m','now')), so this file works whenever run.
-- ============================================================

BEGIN;

-- ---------- users ----------
INSERT INTO users (username, password_hash, role) VALUES
('superadmin', 'scrypt:32768:8:1$wTIqUu9TF1AXjfXF$58bb8f6cff9fb8df5adb1ac60ca6dba60a093f02027a2df5486bc04240cbcff36fbe4f5e5cb90cf30bd4751d3adf13a02141c219b60d7c8049940d246b48f498', 'super_admin'),
('principal',  'scrypt:32768:8:1$bMI1E96zMUl2Ixz4$dc691a55f717b7ee59479f705f4c5dc9721c38190ce712bac274da35a0ede8c0dc4bfb69bd9a4374174b0c0d8ce3e12fd2768a250f623bd56b6b814752fa66d6', 'principal'),
('tch1',       'scrypt:32768:8:1$8ENaBnTq6ciJEe4L$38f9e0a5e46bad9e144dc3f6604cfbaa13e5b3fb511a0f909032e92b04e412bc0b423f7963ebac6ab7222be1a6164d77f10c8cd136faa5d70c872baa347437b7', 'teacher'),
('std1',       'scrypt:32768:8:1$zB1yhChmtsacsspQ$63bc9a6caa23cf462b4a38b9422618363ae4124c58afdb873d62d3b4a7a5d23e1915dbbdd81eed1f5ea6c5647c8907a0c9733aaa2080f806fb2433ae4b323575', 'student')
ON CONFLICT (username) DO NOTHING;

-- ---------- classes: KG..10 section A, plus 10-B ----------
INSERT INTO classes (name, section) VALUES
('KG','A'),('1','A'),('2','A'),('3','A'),('4','A'),('5','A'),
('6','A'),('7','A'),('8','A'),('9','A'),('10','A'),('10','B')
ON CONFLICT (name, section) DO NOTHING;

-- ---------- subjects per class band (every class row incl. sections) ----------
-- SQLITE-PORT-BLOCK-1: procedural seed implemented in Python (backend/app.py ensure_db)

-- ---------- teachers ----------
INSERT INTO teachers (name, phone, cnic, qualification, salary_monthly)
SELECT 'Ahmed Khan','0300-1111111','35202-1111111-1','MSc Mathematics',45000
WHERE NOT EXISTS (SELECT 1 FROM teachers WHERE name='Ahmed Khan');
INSERT INTO teachers (name, phone, cnic, qualification, salary_monthly)
SELECT 'Sara Bibi','0300-2222222','35202-2222222-2','MA English',40000
WHERE NOT EXISTS (SELECT 1 FROM teachers WHERE name='Sara Bibi');
INSERT INTO teachers (name, phone, cnic, qualification, salary_monthly)
SELECT 'Imran Shah','0300-3333333','35202-3333333-3','MSc Physics',50000
WHERE NOT EXISTS (SELECT 1 FROM teachers WHERE name='Imran Shah');

-- ---------- students (12 demo, admission_no uses current year) ----------
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-001','Ali Raza','Muhammad Raza','Male','2013-05-10',
       (SELECT id FROM classes WHERE name='8' AND section='A'),
       'Muhammad Raza','0300-4444444','House 12, Street 5, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Ali Raza');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-002','Bilal Hussain','Hussain Ahmed','Male','2013-08-22',
       (SELECT id FROM classes WHERE name='8' AND section='A'),
       'Hussain Ahmed','0300-5555555','House 8, Street 2, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Bilal Hussain');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-003','Maryam Siddiq','Siddiq Ahmed','Female','2013-02-14',
       (SELECT id FROM classes WHERE name='8' AND section='A'),
       'Siddiq Ahmed','0300-6666666','House 21, Street 9, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Maryam Siddiq');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-004','Daniyal Khan','Tariq Khan','Male','2012-11-30',
       (SELECT id FROM classes WHERE name='8' AND section='A'),
       'Tariq Khan','0300-7777777','House 3, Street 7, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Daniyal Khan');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-005','Usman Tariq','Tariq Mehmood','Male','2015-06-18',
       (SELECT id FROM classes WHERE name='5' AND section='A'),
       'Tariq Mehmood','0300-8888888','House 45, Street 1, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Usman Tariq');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-006','Zainab Ahmed','Ahmed Raza','Female','2015-09-25',
       (SELECT id FROM classes WHERE name='5' AND section='A'),
       'Ahmed Raza','0300-9999999','House 17, Street 4, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Zainab Ahmed');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-007','Sana Malik','Malik Aslam','Female','2010-04-12',
       (SELECT id FROM classes WHERE name='10' AND section='A'),
       'Malik Aslam','0301-1111111','House 9, Street 11, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Sana Malik');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-008','Kamran Iqbal','Iqbal Hussain','Male','2010-07-08',
       (SELECT id FROM classes WHERE name='10' AND section='A'),
       'Iqbal Hussain','0301-2222222','House 30, Street 6, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Kamran Iqbal');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-009','Hira Shah','Shahid Mehmood','Female','2010-12-01',
       (SELECT id FROM classes WHERE name='10' AND section='A'),
       'Shahid Mehmood','0301-3333333','House 51, Street 3, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Hira Shah');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-010','Fatima Khan','Khan Muhammad','Female','2018-03-15',
       (SELECT id FROM classes WHERE name='1' AND section='A'),
       'Khan Muhammad','0301-4444444','House 6, Street 8, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Fatima Khan');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-011','Ayesha Noor','Noor Muhammad','Female','2020-01-20',
       (SELECT id FROM classes WHERE name='KG' AND section='A'),
       'Noor Muhammad','0301-5555555','House 14, Street 10, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Ayesha Noor');
INSERT INTO students (admission_no, name, father_name, gender, dob, class_id, guardian_name, guardian_phone, address, status)
SELECT 'SMS-'||strftime('%Y','now')||'-012','Hamza Ali','Ali Sher','Male','2020-06-11',
       (SELECT id FROM classes WHERE name='KG' AND section='A'),
       'Ali Sher','0301-6666666','House 2, Street 12, Peshawar','Active'
WHERE NOT EXISTS (SELECT 1 FROM students WHERE name='Hamza Ali');

-- link demo logins
UPDATE users SET linked_teacher_id=(SELECT id FROM teachers WHERE name='Ahmed Khan') WHERE username='tch1';
UPDATE users SET linked_student_id=(SELECT id FROM students WHERE name='Ali Raza') WHERE username='std1';

-- ---------- teacher assignments ----------
-- SQLITE-PORT-BLOCK-5: demo teacher assignments are seeded from Python
-- (backend/app.py ensure_db _seed_procedural B5) because they need the
-- subjects, which are seeded procedurally in BLOCK-1 after this file runs.
-- ---------- fee heads: KG-5:1500, 6-8:2000, 9-10:2500 (per class row) ----------
-- NOTE (SQLite): ON CONFLICT cannot follow an INSERT..SELECT..FROM statement
-- (the ON would parse as a JOIN constraint), so the upsert is written as
-- UPDATE-then-INSERT with identical end state.
UPDATE fee_heads SET monthly_amount=(
  SELECT CASE WHEN c.name IN ('KG','1','2','3','4','5') THEN 1500
              WHEN c.name IN ('6','7','8') THEN 2000
              ELSE 2500 END
  FROM classes c WHERE c.id=fee_heads.class_id);
INSERT INTO fee_heads (class_id, monthly_amount)
SELECT c.id,
       CASE WHEN c.name IN ('KG','1','2','3','4','5') THEN 1500
            WHEN c.name IN ('6','7','8') THEN 2000
            ELSE 2500 END
FROM classes c
WHERE NOT EXISTS (SELECT 1 FROM fee_heads f WHERE f.class_id=c.id);

-- ---------- fee invoices for the CURRENT month, all Active students ----------
-- SQLITE-PORT-BLOCK-2: procedural seed implemented in Python (backend/app.py ensure_db)

-- one invoice PARTIAL with a payment (first invoice = Ali Raza's)
-- SQLITE-PORT-BLOCK-3: procedural seed implemented in Python (backend/app.py ensure_db)

-- one OVERDUE invoice from last month (first student)
-- SQLITE-PORT-BLOCK-4: procedural seed implemented in Python (backend/app.py ensure_db)

-- ---------- exams: First Term 2026 for class 8-A ----------
INSERT INTO exams (name, class_id, year, start_date)
SELECT 'First Term', c.id, 2026, CURRENT_DATE FROM classes c
WHERE c.name='8' AND c.section='A'
  AND NOT EXISTS (SELECT 1 FROM exams e WHERE e.name='First Term' AND e.year=2026 AND e.class_id=c.id);

-- marks for all 8-A students in Mathematics and Science (varied scores)
-- SQLITE-PORT-BLOCK-6: demo exam marks are seeded from Python
-- (backend/app.py ensure_db _seed_procedural B6) because they need the
-- subjects, which are seeded procedurally in BLOCK-1 after this file runs.

-- ---------- announcements ----------
INSERT INTO announcements (title, body, audience, posted_by)
SELECT 'Welcome to the new term',
       'Assalam-o-Alaikum! Classes for the new term have started. Please check the notice board and your class notes regularly.',
       'ALL', id FROM users WHERE username='superadmin'
  AND NOT EXISTS (SELECT 1 FROM announcements WHERE title='Welcome to the new term');
INSERT INTO announcements (title, body, audience, posted_by)
SELECT 'First Term exam date sheet',
       'Dear students, the First Term date sheet is now available. Contact your class teacher for details.',
       'STUDENTS', id FROM users WHERE username='superadmin'
  AND NOT EXISTS (SELECT 1 FROM announcements WHERE title='First Term exam date sheet');

-- ---------- salaries: current month for the 3 teachers (one paid) ----------
INSERT INTO salaries (teacher_id, sal_month, basic, allowances, deductions, net, paid, paid_at)
SELECT id, strftime('%Y-%m','now'), 45000, 5000, 2000, 48000, TRUE, CURRENT_TIMESTAMP
FROM teachers WHERE name='Ahmed Khan'
  AND NOT EXISTS (SELECT 1 FROM salaries s
                  WHERE s.teacher_id=teachers.id AND s.sal_month=strftime('%Y-%m','now'));
INSERT INTO salaries (teacher_id, sal_month, basic, allowances, deductions, net, paid)
SELECT id, strftime('%Y-%m','now'), 40000, 3000, 1000, 42000, FALSE
FROM teachers WHERE name='Sara Bibi'
  AND NOT EXISTS (SELECT 1 FROM salaries s
                  WHERE s.teacher_id=teachers.id AND s.sal_month=strftime('%Y-%m','now'));
INSERT INTO salaries (teacher_id, sal_month, basic, allowances, deductions, net, paid)
SELECT id, strftime('%Y-%m','now'), 50000, 8000, 3000, 55000, FALSE
FROM teachers WHERE name='Imran Shah'
  AND NOT EXISTS (SELECT 1 FROM salaries s
                  WHERE s.teacher_id=teachers.id AND s.sal_month=strftime('%Y-%m','now'));

-- ---------- teacher leaves: one sample PENDING leave (Sara Bibi, 3 days from next Monday) ----------
INSERT INTO teacher_leaves (teacher_id, date_from, date_to, reason, status)
SELECT id,
       date('now','weekday 0','+1 day'),
       date('now','weekday 0','+3 days'),
       'Family wedding', 'PENDING'
FROM teachers WHERE name='Sara Bibi'
  AND NOT EXISTS (SELECT 1 FROM teacher_leaves tl
                  JOIN teachers t2 ON t2.id=tl.teacher_id
                  WHERE t2.name='Sara Bibi' AND tl.status='PENDING'
                    AND tl.reason='Family wedding');

-- ---------- expenses ----------
INSERT INTO expenses (title, amount, category, expense_date, added_by)
SELECT 'Electricity bill', 8500, 'Utilities', CURRENT_DATE, id FROM users WHERE username='superadmin'
AND NOT EXISTS (SELECT 1 FROM expenses WHERE title='Electricity bill');
INSERT INTO expenses (title, amount, category, expense_date, added_by)
SELECT 'Chalk & stationery', 3200, 'Supplies', CURRENT_DATE, id FROM users WHERE username='superadmin'
AND NOT EXISTS (SELECT 1 FROM expenses WHERE title='Chalk & stationery');
INSERT INTO expenses (title, amount, category, expense_date, added_by)
SELECT 'Building repair', 15000, 'Maintenance', CURRENT_DATE, id FROM users WHERE username='superadmin'
AND NOT EXISTS (SELECT 1 FROM expenses WHERE title='Building repair');

-- ---------- settings ----------
INSERT INTO settings (key, value) VALUES
('school_name','Anjum Grammer School'),
('theme_color','#0d9488'),
('school_logo',''),
('late_fee_percent','5'),
('school_address','Main Road'),
('school_phone',''),
('opening_time','08:00 AM'),
('closing_time','02:00 PM'),
('school_rules','1. Be punctual — assembly at 7:45 AM sharp. 2. Wear proper uniform daily. 3. Respect teachers and fellow students. 4. No mobile phones on campus.'),
('school_history','Anjum Grammer School was founded with a mission to provide quality education at an affordable fee. Starting with a handful of students, the school has grown into a trusted institution serving KG to 10th, known for disciplined classrooms, dedicated teachers, and strong board results.'),
('school_facilities','Spacious airy classrooms, science laboratory, computer lab, well-stocked library, large playground for cricket and athletics, clean drinking water, and secure transport routes.'),
('gemini_api_key',''),
('gemini_model','gemini-1.5-flash'),
('gemini_system_prompt','You are the helpful AI assistant for Anjum Grammar School. Answer questions clearly, accurately, and politely in English or Urdu.')
ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value;

COMMIT;

-- ---------- clerk demo login (SPEC UPDATE 5; run order schema -> v2 -> seed) ----------
INSERT INTO users (username, password_hash, role) VALUES
('clerk', 'scrypt:32768:8:1$mLc509ovHNfPgjMc$f1555fc9bdb4aee7993597c3249889002a5d20efe33d53a2cdaed9963f8543c5b2b77f1185cc2c45d41969f1a0a887dce426f05862dfa33514e27715df4f28a0', 'clerk')
ON CONFLICT (username) DO NOTHING;
