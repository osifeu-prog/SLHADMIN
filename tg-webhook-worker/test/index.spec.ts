import { describe, it, expect, beforeAll } from "vitest";
import worker from "../src/index";

beforeAll(() => {
  // prevent real network calls (Telegram)
  // @ts-ignore
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ ok: true, result: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
});

function mkKv() {
  const m = new Map<string, string>();
  return {
    async get(key: string) {
      return m.has(key) ? m.get(key)! : null;
    },
    async put(key: string, value: string, _opts?: any) {
      m.set(key, value);
    },
    async delete(key: string) {
      m.delete(key);
    },
  };
}

function mkDb() {
  return {
    prepare(_sql: string) {
      return {
        bind(..._args: any[]) {
          return this;
        },
        async run() {
          return { success: true };
        },
        async all() {
          return { results: [{ ok: 1 }] as any[] };
        },
        async first() {
          return { ok: 1 } as any;
        },
      };
    },
  };
}

function mkEnv(overrides: any = {}) {
  return {
    TG_SECRET_TOKEN: "test-secret",
    ADMIN_CHAT_ID: "123",
    ADMIN_PASS_SHA256: "x",
    DEBUG_ADMIN_TOOLS: "0",
    KV: mkKv(),
    DB: mkDb(),
    ...overrides,
  };
}

function mkCtx() {
  return {
    waitUntil() {},
    passThroughOnException() {},
  } as any;
}

describe("tg-webhook-worker", () => {
  it("GET /healthz -> 200 ok", async () => {
    const env = mkEnv();
    const req = new Request("http://example.com/healthz", { method: "GET" });
    const res = await worker.fetch(req, env, mkCtx());
    expect(res.status).toBe(200);
    const j: any = await res.json();
    expect(j.ok).toBe(true);
  });

  it("GET /readyz -> 200 ok", async () => {
    const env = mkEnv();
    const req = new Request("http://example.com/readyz", { method: "GET" });
    const res = await worker.fetch(req, env, mkCtx());
    expect(res.status).toBe(200);
    const j: any = await res.json();
    expect(j.ok).toBe(true);
  });

  it("POST /tg/webhook without secret -> 403", async () => {
    const env = mkEnv();
    const req = new Request("http://example.com/tg/webhook", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ update_id: 1, message: { text: "/help", chat: { id: 123, type: "private" } } }),
    });
    const res = await worker.fetch(req, env, mkCtx());
    expect(res.status).toBe(403);
  });

  it("POST /tg/webhook with secret -> 200 ok", async () => {
    const env = mkEnv({ TG_SECRET_TOKEN: "test-secret" });
    const req = new Request("http://example.com/tg/webhook", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-telegram-bot-api-secret-token": "test-secret",
      },
      body: JSON.stringify({ update_id: 1, message: { text: "/help", chat: { id: 123, type: "private" } } }),
    });
    const res = await worker.fetch(req, env, mkCtx());
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
  });

  it("unknown path -> 404", async () => {
    const env = mkEnv();
    const req = new Request("http://example.com/nope", { method: "GET" });
    const res = await worker.fetch(req, env, mkCtx());
    expect(res.status).toBe(404);
  });
});