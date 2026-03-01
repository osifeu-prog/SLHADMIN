const SESSION_TTL_SEC = 6 * 60 * 60; // 6h

export async function setAdminSession(env: any, chatId: number): Promise<void> {
  if (!env?.KV) return;
  await env.KV.put(`admin:session:${chatId}`, String(Date.now()), { expirationTtl: SESSION_TTL_SEC });
}

export async function clearAdminSession(env: any, chatId: number): Promise<void> {
  if (!env?.KV) return;
  await env.KV.delete(`admin:session:${chatId}`);
}

export async function hasAdminSession(env: any, chatId: number): Promise<boolean> {
  if (!env?.KV) return false;
  const v = await env.KV.get(`admin:session:${chatId}`);
  return !!v;
}