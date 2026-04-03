import { route } from "./router";
import { handleHealthz, handleReadyz } from "./handlers/http_health";
import { reportError } from "./services/report";
import { audit } from "./services/audit";
import { getClientIp, bumpFail, getFail } from "./services/security";

const FAIL_TTL_SEC = 60 * 60; // 1h
const FAIL_MAX = 20;          // lock after 20 bad secrets per IP per hour

export default {
  async fetch(request: Request, env: any): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/healthz") return await handleHealthz(env);
    if (request.method === "GET" && url.pathname === "/readyz") return await handleReadyz(env);

    if (request.method === "POST" && url.pathname === "/diag_echo") {
      const update = await request.json();
      const msg = (update && (update.message || update.edited_message)) || null;
      const text = msg ? (msg.text || "") : "";
      const keys = Object.keys(update || {});
      return new Response(JSON.stringify({ ok: true, has_message: !!msg, keys, text: text.slice(0, 200) }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }


    if (request.method === "GET" && url.pathname === "/diag_secrets") {
      const hasBot = !!((env.BOT_TOKEN || "").toString().trim());
      const hasSecret = !!((env.TG_SECRET_TOKEN || "").toString().trim());
      const hasAdmin = !!((env.ADMIN_CHAT_ID || "").toString().trim());
      return new Response(JSON.stringify({ ok: true, hasBot, hasSecret, hasAdmin }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }

    if (request.method === "POST" && url.pathname === "/diag_ping_tg") {
      const admin = Number((env.ADMIN_CHAT_ID || "").toString().trim() || "0");
      if (!admin) return new Response("admin missing", { status: 500 });

      const text = "diag_ping_tg ok " + new Date().toISOString();
      const r = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/sendMessage`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ chat_id: admin, text }),
      });
      const t = await r.text();
      return new Response(JSON.stringify({ ok: r.ok, status: r.status, body: t.slice(0, 400) }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }


    if (url.pathname !== "/tg/webhook") return new Response("not found", { status: 404 });
    if (request.method !== "POST") return new Response("method not allowed", { status: 405 });

    const ip = getClientIp(request);
    const failKey = `sec:fail:${ip}`;
    const fails = await getFail(env, failKey);
    if (fails >= FAIL_MAX) return new Response("forbidden", { status: 403 });

    const got = request.headers.get("x-telegram-bot-api-secret-token") || "";
    const expected = (env.TG_SECRET_TOKEN || "").toString().trim();

    if (!expected || got !== expected) {
      const n = await bumpFail(env, failKey, FAIL_TTL_SEC);
      await audit(env, "secret_mismatch", undefined, false, { ip, fails: n });
      return new Response("forbidden", { status: 403 });
    }

    try {
      const update = await request.json();
      await route(env, update);
      return new Response("ok");
    } catch (e: any) {
      await reportError(env, "webhook", e);
      return new Response("ok");
    }
  },
};