-- SMS-SCHOOL v10: Gemini AI Assistant chat history
CREATE TABLE IF NOT EXISTS ai_chats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_chats_user ON ai_chats(user_id, id);

INSERT OR IGNORE INTO settings (key, value) VALUES
  ('gemini_api_key', ''),
  ('gemini_model', 'gemini-1.5-flash'),
  ('gemini_system_prompt', 'You are the helpful AI assistant for Anjum Grammar School. Answer questions clearly, accurately, and politely in English or Urdu.');
