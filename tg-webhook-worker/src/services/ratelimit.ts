export async function rateLimit(env: any, subject: string, limit: number, windowSec: number): Promise<boolean> {
  try {
    if (!env?.KV) return true;

    const window = Math.max(60, Math.floor(windowSec));
    const now = Math.floor(Date.now() / 1000);
    const bucket = Math.floor(now / window);
    const key = `rl:${subject}:${bucket}`;

    const raw = await env.KV.get(key);
    const n = raw ? parseInt(raw, 10) : 0;

    if (n >= limit) return false;

    const ttl = Math.max(60, window + 5);
    await env.KV.put(key, String(n + 1), { expirationTtl: ttl });
    return true;
  } catch (e) {
    console.log("rateLimit error:", e);
    return true; // fail-open
  }
}