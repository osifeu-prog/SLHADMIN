import { sendMessage } from "../services/telegram";
import { isAdmin } from "../services/admin";
import { ensureUser, getOrCreateInternalWallet } from "../services/d1";
import { audit } from "../services/audit";

export async function handleWallet(env: any, update: any, text: string) {
  const chatId = update.message.chat.id;
  if (!isAdmin(env, chatId)) return;

  const parts = text.trim().split(/\\s+/);
  if (parts.length < 2) {
    await sendMessage(env, chatId, "Usage:\\n/wallet <chat_id>");
    return;
  }

  const target = Number(parts[1]);
  if (!Number.isFinite(target)) {
    await sendMessage(env, chatId, "Invalid chat_id");
    return;
  }

  await ensureUser(env, { chat_id: target });
  const wid = await getOrCreateInternalWallet(env, target);

  await audit(env, "wallet", chatId, true, { target, wallet_id: wid });
  await sendMessage(env, chatId, `wallet\\nchat_id: ${target}\\nwallet_id: ${wid}`);
}