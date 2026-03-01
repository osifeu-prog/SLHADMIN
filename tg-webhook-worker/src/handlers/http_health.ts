export async function handleHealthz(_env: any): Promise<Response> {
  return new Response(
    JSON.stringify({ ok: true, ts: new Date().toISOString(), service: "tg-webhook-worker" }),
    { status: 200, headers: { "content-type": "application/json" } }
  );
}

export async function handleReadyz(env: any): Promise<Response> {
  const t0 = Date.now();
  const out: any = {
    ok: true,
    ts: new Date().toISOString(),
    kv: !!env?.KV,
    db: !!env?.DB,
    checks: {},
  };

  try {
    if (!env?.KV) throw new Error("KV binding missing");
    await env.KV.put("health:last", String(Date.now()), { expirationTtl: 60 });
    out.checks.kv = true;
  } catch (e) {
    out.ok = false;
    out.checks.kv = false;
    out.checks.kv_error = String(e);
  }

  try {
    if (!env?.DB) throw new Error("DB binding missing");
    const r = await env.DB.prepare("SELECT 1 AS ok").first();
    out.checks.db = !!r?.ok;
    if (!out.checks.db) out.ok = false;
  } catch (e) {
    out.ok = false;
    out.checks.db = false;
    out.checks.db_error = String(e);
  }

  out.elapsed_ms = Date.now() - t0;

  return new Response(JSON.stringify(out), {
    status: out.ok ? 200 : 503,
    headers: { "content-type": "application/json" },
  });
}