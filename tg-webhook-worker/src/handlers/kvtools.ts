import { sendMessage } from "../services/telegram";
import { isAdmin } from "../services/admin";

export async function handleKvTools(env: any, update: any, text: string) {
  const chatId = update.message.chat.id;

  if (!isAdmin(env, chatId)) {
    await sendMessage(env, chatId, "Unauthorized");
    return;
  }

  const parts = text.trim().split(/\s+/);
  if (parts.length < 3) {
    await sendMessage(env, chatId, "Usage:\nkv get <chat_id>\nkv del <chat_id>");
    return;
  }

  const action = parts[1];
  const id = parts[2];
  const key = `user:${id}`;

  if (action === "get") {
    const v = await env.KV.get(key);
    await sendMessage(env, chatId, v ? `${key}\n${v}` : `not found: ${key}`);
    return;
  }

  if (action === "del") {
    await env.KV.delete(key);
    await sendMessage(env, chatId, `deleted: ${key}`);
    return;
  }

  await sendMessage(env, chatId, "Usage:\nkv get <chat_id>\nkv del <chat_id>");
}