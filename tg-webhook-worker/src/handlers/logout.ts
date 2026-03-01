import { sendMessage } from "../services/telegram";
import { clearAdminSession } from "../services/admin_session";
import { audit } from "../services/audit";

export async function handleLogout(env: any, update: any) {
  const chatId = update.message.chat.id;
  await clearAdminSession(env, chatId);
  await audit(env, "logout", chatId, true, {});
  await sendMessage(env, chatId, "Logged out.");
}