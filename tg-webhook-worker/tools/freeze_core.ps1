param([string]$Root = ".")
$ErrorActionPreference="Stop"
Set-Location $Root

function WriteFile([string]$Path, [string]$Text){
  $full = Join-Path (Get-Location) $Path
  $dir = Split-Path -Parent $full
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $enc = New-Object System.Text.UTF8Encoding($false)
  $lf = $Text -replace "`r`n","`n"
  [System.IO.File]::WriteAllText($full, $lf, $enc)
  "WROTE $Path"
}

$httpHealth = @'
export async function handleHealthz(_env: any): Promise<Response> {
  return new Response(JSON.stringify({
    ok: true,
    ts: new Date().toISOString(),
    service: "tg-webhook-worker"
  }), { status: 200, headers: { "content-type": "application/json" } });
}

export async function handleReadyz(env: any): Promise<Response> {
  const t0 = Date.now();
  const out: any = { ok: true, ts: new Date().toISOString(), kv: !!env?.KV, db: !!env?.DB, checks: {} };

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
    headers: { "content-type": "application/json" }
  });
}
'@

$index = @'
import { route } from "./router";
import { handleHealthz, handleReadyz } from "./handlers/http_health";
import { reportError } from "./services/report";

export default {
  async fetch(request: Request, env: any): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/healthz") return await handleHealthz(env);
    if (request.method === "GET" && url.pathname === "/readyz") return await handleReadyz(env);

    if (url.pathname !== "/tg/webhook") return new Response("not found", { status: 404 });
    if (request.method !== "POST") return new Response("method not allowed", { status: 405 });

    const got = request.headers.get("x-telegram-bot-api-secret-token") || "";
    if (got !== env.TG_SECRET_TOKEN) return new Response("forbidden", { status: 403 });

    try {
      const update = await request.json();
      console.log("Update received:", JSON.stringify(update));
      await route(env, update);
      return new Response("ok");
    } catch (e: any) {
      console.log("Worker exception:", (e && e.stack) ? e.stack : String(e));
      await reportError(env, "webhook", e);
      return new Response("ok");
    }
  },
};
'@

WriteFile "src/handlers/http_health.ts" $httpHealth
WriteFile "src/index.ts" $index
