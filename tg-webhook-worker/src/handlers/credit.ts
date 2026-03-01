import { sendMessage } from "../services/telegram";
import { isAdmin } from "../services/admin";
import { ensureUser, getOrCreateInternalWallet, addLedger, getBalance } from "../services/d1";
import { audit } from "../services/audit";

export async function handleCredit(env: any, update: any, text: string) {
  const chatId = update.message.chat.id;
  if (!isAdmin(env, chatId)) return;

  const parts = text.trim().split(/\\s+/);
  if (parts.length < 3) {
    await sendMessage(env, chatId, "Usage:\\n/credit <chat_id> <amount>\\nExample: /credit 224223270 1");
    return;
  }

  const target = Number(parts[1]);
  const amount = parts[2];

  if (!Number.isFinite(target)) {
    await sendMessage(env, chatId, "Invalid chat_id");
    return;
  }

  if (!/^\\d+(\\.\\d+)?$/.test(amount)) {
    await sendMessage(env, chatId, "Invalid amount (use number like 10 or 10.5)");
    return;
  }

  await ensureUser(env, { chat_id: target });
  const wid = await getOrCreateInternalWallet(env, target);
  const ledgerId = await addLedger(env, wid, "credit", amount, "SLH", "admin credit");
  const bal = await getBalance(env, wid, "SLH");

  await audit(env, "credit", chatId, true, { target, wallet_id: wid, amount, asset: "SLH", ledger_id: ledgerId, balance_slh: bal });

  await sendMessage(env, chatId, `credit\\nchat_id: ${target}\\nwallet_id: ${wid}\\nledger_id: ${ledgerId}\\nbalance_slh: ${bal}`);
}