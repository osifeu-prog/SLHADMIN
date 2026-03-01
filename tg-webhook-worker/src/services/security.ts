export function getClientIp(request: Request): string {
  return (
    request.headers.get("cf-connecting-ip") ||
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    "unknown"
  );
}

export async function bumpFail(env: any, key: string, ttlSec: number): Promise<number> {
  if (!env?.KV) return 0;
  const raw = await env.KV.get(key);
  const n = raw ? parseInt(raw, 10) : 0;
  const next = Number.isFinite(n) ? (n + 1) : 1;
  await env.KV.put(key, String(next), { expirationTtl: Math.max(60, ttlSec) });
  return next;
}

export async function getFail(env: any, key: string): Promise<number> {
  if (!env?.KV) return 0;
  const raw = await env.KV.get(key);
  const n = raw ? parseInt(raw, 10) : 0;
  return Number.isFinite(n) ? n : 0;
}