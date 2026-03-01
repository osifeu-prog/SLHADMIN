import { sendMessage } from "../services/telegram";
import { hasAdminSession } from "../services/admin_session";

export async function handleSession(env: any, update: any) {
  const chatId = update.message.chat.id;
  const ok = await hasAdminSession(env, chatId);
  await sendMessage(env, chatId, ok ? "session: ON" : "session: OFF");
}