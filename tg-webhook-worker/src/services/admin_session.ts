const SESSION_TTL_SEC = 6 * 60 * 60; // 6h
const key = (chatId: number) => `admin:session:${chatId}`;

export async function setAdminSession(env: any, chatId: number): Promise<void> {
  if (!env?.KV) return;
  await env.KV.put(key(chatId), "1", { expirationTtl: SESSION_TTL_SEC });
}

export async function clearAdminSession(env: any, chatId: number): Promise<void> {
  if (!env?.KV) return;
  await env.KV.delete(key(chatId));
}

export async function hasAdminSession(env: any, chatId: number): Promise<boolean> {
  if (!env?.KV) return false;
  const v = await env.KV.get(key(chatId));
  return v === "1";
}