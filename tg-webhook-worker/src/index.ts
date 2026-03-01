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