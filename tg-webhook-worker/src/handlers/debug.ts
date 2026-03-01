import { sendMessage } from "../services/telegram";
import { hasAdminSession } from "../services/admin_session";

export async function handleDebug(env: any, update: any) {
  const chat = update.message.chat;
  const chatId = chat.id;

  const adminId = Number((env.ADMIN_CHAT_ID || "").toString().trim() || "0");
  const adminChatOk = !!adminId && chatId === adminId;
  if (!adminChatOk) {
    await sendMessage(env, chatId, "Unauthorized.");
    return;
  }

  const dbg = ((env.DEBUG_ADMIN_TOOLS || "").toString().trim() === "1");
  const hasHash = !!((env.ADMIN_PASS_SHA256 || "").toString().trim());
  const hasTgSecret = !!((env.TG_SECRET_TOKEN || "").toString().trim());

  const kvOk = !!env.KV;
  const dbOk = !!env.DB;
  const sess = await hasAdminSession(env, chatId);

  await sendMessage(
    env,
    chatId,
    [
      "debug:",
      `- DEBUG_ADMIN_TOOLS: ${dbg}`,
      `- session: ${sess ? "ON" : "OFF"}`,
      `- ADMIN_PASS_SHA256 present: ${hasHash}`,
      `- TG_SECRET_TOKEN present: ${hasTgSecret}`,
      `- KV binding: ${kvOk}`,
      `- D1 binding: ${dbOk}`,
    ].join("\n")
  );
}