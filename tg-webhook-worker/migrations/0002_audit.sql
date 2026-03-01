-- 0002_audit.sql
CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY,
  ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  actor_chat_id INTEGER,
  action TEXT NOT NULL,
  ok INTEGER NOT NULL DEFAULT 1,
  details TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_chat_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
