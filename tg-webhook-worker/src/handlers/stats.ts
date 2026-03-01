import type { KVNamespace } from "@cloudflare/workers-types";
import { sendMessage } from "../services/telegram";
import { isAdmin } from "../services/admin";

type KVListResult = {
  keys: Array<{ name: string }>;
  list_complete?: boolean;
  cursor?: string;
};

export async function handleStats(env: any, update: any) {
  const chatId = update.message.chat.id;
  if (!isAdmin(env, chatId)) return;

  if (!env?.KV) {
    await sendMessage(env, chatId, "stats\nKV: false (binding missing)");
    return;
  }

  const kv = env.KV as KVNamespace;

  let cursor: string | undefined = undefined;
  let total = 0;

  // Guardrails: dont scan forever
  for (let i = 0; i < 30; i++) {
    const res = (await kv.list({ prefix: "user:", cursor })) as unknown as KVListResult;
    total += (res.keys || []).length;

    if (!res.cursor || res.list_complete) break;
    cursor = res.cursor;
  }

  await sendMessage(env, chatId, `stats\nusers_saved_kv: ${total}`);
}
