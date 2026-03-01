import { sendMessage } from "../services/telegram";
import { verifyAdminPassword } from "../services/auth";
import { setAdminSession } from "../services/admin_session";
import { audit } from "../services/audit";

export async function handleLogin(env: any, update: any, text: string) {
  const chat = update.message.chat;
  const chatId = chat.id;

  // only private chat
  if (chat.type !== "private") {
    await sendMessage(env, chatId, "Login allowed only in private chat.");
    return;
  }

  // only ADMIN_CHAT_ID can login
  const adminId = Number((env.ADMIN_CHAT_ID || "").toString().trim() || "0");
  if (!adminId || chatId !== adminId) {
    await sendMessage(env, chatId, "Unauthorized.");
    return;
  }

  const parts = text.trim().split(/\s+/);
  if (parts.length < 2) {
    await sendMessage(env, chatId, "Usage: /login <password>");
    return;
  }

  const pass = parts.slice(1).join(" ");
  const ok = await verifyAdminPassword(env, pass);

  await audit(env, "login", chatId, ok, { ok });

  if (!ok) {
    await sendMessage(env, chatId, "Login failed.");
    return;
  }

  await setAdminSession(env, chatId);
  await sendMessage(env, chatId, "Admin session enabled (6h).");
}