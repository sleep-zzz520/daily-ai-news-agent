CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, profile TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 daily_key TEXT UNIQUE, status TEXT NOT NULL, created_at TEXT NOT NULL,
 error TEXT, brief TEXT, delivery TEXT NOT NULL DEFAULT 'not_sent'
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(user_id) WHERE status='running';
CREATE TABLE IF NOT EXISTS tool_calls (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
 name TEXT NOT NULL, arguments TEXT NOT NULL, result TEXT NOT NULL, duration REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS news (
 url TEXT PRIMARY KEY, material TEXT NOT NULL, fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deliveries (
 run_id TEXT PRIMARY KEY REFERENCES runs(id), status TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0, error TEXT, updated_at TEXT NOT NULL
);
PRAGMA user_version=1;
