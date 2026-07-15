CREATE TABLE IF NOT EXISTS user_settings (
  user_id TEXT PRIMARY KEY,
  settings_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_resumes (
  user_id TEXT NOT NULL,
  language TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, language)
);

CREATE TABLE IF NOT EXISTS user_history (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  path TEXT NOT NULL DEFAULT '',
  size INTEGER NOT NULL DEFAULT 0,
  modified TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS user_history_owner_idx
  ON user_history(user_id, modified DESC);
