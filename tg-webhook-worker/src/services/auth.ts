function toHex(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (const b of bytes) s += b.toString(16).padStart(2, "0");
  return s;
}

export async function sha256Hex(text: string): Promise<string> {
  const data = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return toHex(hash);
}

export function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}

export async function verifyAdminPassword(env: any, candidate: string): Promise<boolean> {
  const expected = (env.ADMIN_PASS_SHA256 || "").toString().trim().toLowerCase();
  if (!expected) return false;
  const got = (await sha256Hex(candidate)).toLowerCase();
  return timingSafeEqual(got, expected);
}