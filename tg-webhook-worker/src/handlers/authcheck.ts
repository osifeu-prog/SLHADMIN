import { sendMessage } from "../services/telegram";
import { verifyAdminPassword } from "../services/auth";

export async function handleAuthCheck(env: any, update: any) {
  const chat = update.message.chat;
  const chatId = chat.id;

  const adminId = Number((env.ADMIN_CHAT_ID || "").toString().trim() || "0");
  const adminChatOk = !!adminId && chatId === adminId;
  if (!adminChatOk) {
    await sendMessage(env, chatId, "Unauthorized.");
    return;
  }

  const dbg = ((env.DEBUG_ADMIN_TOOLS || "").toString().trim() === "1");
  if (!dbg) {
    await sendMessage(env, chatId, "authcheck: Disabled.");
    return;
  }

  const hasEnvHash = !!((env.ADMIN_PASS_SHA256 || "").toString().trim());
  const candidate = "13572468"; // TEMP diagnostic (no hash leakage)
  const passOk = await verifyAdminPassword(env, candidate);

  await sendMessage(
    env,
    chatId,
    [
      "authcheck:",
      `- env.ADMIN_PASS_SHA256 present: ${hasEnvHash}`,
      `- verifyAdminPassword("13572468"): ${passOk}`,
      `- chatId == ADMIN_CHAT_ID: ${adminChatOk}`,
    ].join("\n")
  );
}