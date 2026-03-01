import { sendMessage } from "../services/telegram";
import { saveUser } from "../services/kv";

export async function handleStart(env: any, update: any) {
  const chatId = update.message.chat.id;
  const username = update.message.from.username || "unknown";

  await saveUser(env, chatId, {
    username,
    createdAt: Date.now(),
  });

  await sendMessage(env, chatId, " Guardian MVP Activated (KV Saved)");
}
