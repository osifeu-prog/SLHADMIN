-- 0001_init.sql
CREATE TABLE IF NOT EXISTS users (
  chat_id INTEGER PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  last_name TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS wallets (
  wallet_id TEXT PRIMARY KEY,
  chat_id INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'internal',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  FOREIGN KEY(chat_id) REFERENCES users(chat_id)
);

CREATE TABLE IF NOT EXISTS ledger (
  id TEXT PRIMARY KEY,
  wallet_id TEXT NOT NULL,
  ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  type TEXT NOT NULL,
  amount TEXT NOT NULL,
  asset TEXT NOT NULL DEFAULT 'SLH',
  ref TEXT,
  memo TEXT,
  FOREIGN KEY(wallet_id) REFERENCES wallets(wallet_id)
);

CREATE INDEX IF NOT EXISTS idx_wallets_chat ON wallets(chat_id);
CREATE INDEX IF NOT EXISTS idx_ledger_wallet ON ledger(wallet_id);
