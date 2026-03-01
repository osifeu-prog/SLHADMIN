export function hasDB(env: any): boolean {
  return !!env?.DB;
}

export async function dbPing(env: any) {
  return await env.DB.prepare("SELECT 1 AS ok").first();
}

export async function ensureUser(env: any, u: { chat_id: number, username?: string, first_name?: string, last_name?: string }) {
  await env.DB.prepare(
    "INSERT OR IGNORE INTO users(chat_id, username, first_name, last_name) VALUES (?1, ?2, ?3, ?4)"
  ).bind(u.chat_id, u.username || null, u.first_name || null, u.last_name || null).run();
}

export async function getOrCreateInternalWallet(env: any, chatId: number) {
  const existing = await env.DB.prepare(
    "SELECT wallet_id FROM wallets WHERE chat_id=?1 AND kind='internal' LIMIT 1"
  ).bind(chatId).first();

  if (existing?.wallet_id) return String(existing.wallet_id);

  const walletId = crypto.randomUUID();
  await env.DB.prepare(
    "INSERT INTO wallets(wallet_id, chat_id, kind, status) VALUES (?1, ?2, 'internal', 'active')"
  ).bind(walletId, chatId).run();

  return walletId;
}

export async function addLedger(env: any, walletId: string, type: string, amount: string, asset: string, memo?: string, ref?: string) {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    "INSERT INTO ledger(id, wallet_id, type, amount, asset, memo, ref) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)"
  ).bind(id, walletId, type, amount, asset, memo || null, ref || null).run();
  return id;
}

export async function getBalance(env: any, walletId: string, asset: string) {
  const r = await env.DB.prepare(
    "SELECT " +
    "COALESCE(SUM(CASE WHEN type='credit' THEN CAST(amount AS REAL) ELSE 0 END),0) - " +
    "COALESCE(SUM(CASE WHEN type='debit' THEN CAST(amount AS REAL) ELSE 0 END),0) " +
    "AS bal FROM ledger WHERE wallet_id=?1 AND asset=?2"
  ).bind(walletId, asset).first();

  return Number(r?.bal ?? 0);
}