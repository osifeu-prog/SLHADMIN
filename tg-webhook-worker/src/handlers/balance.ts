import { sendMessage } from "../services/telegram";
import { isAdmin } from "../services/admin";
import { getOrCreateInternalWallet, getBalance } from "../services/d1";

export async function handleBalance(env: any, update: any, text: string) {
  const chatId = update.message.chat.id;
  if (!isAdmin(env, chatId)) return;

  const parts = text.trim().split(/\s+/);
  if (parts.length < 2) {
    await sendMessage(env, chatId, "Usage:\n/balance <chat_id>");
    return;
  }

  const target = Number(parts[1]);
  if (!Number.isFinite(target)) {
    await sendMessage(env, chatId, "Invalid chat_id");
    return;
  }

  const wid = await getOrCreateInternalWallet(env, target);
  const bal = await getBalance(env, wid, "SLH");
  await sendMessage(env, chatId, `balance\nchat_id: ${target}\nwallet_id: ${wid}\nSLH: ${bal}`);
}