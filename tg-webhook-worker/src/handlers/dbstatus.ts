import { sendMessage } from "../services/telegram";
import { isAdmin } from "../services/admin";
import { hasDB, dbPing } from "../services/d1";

export async function handleDbStatus(env: any, update: any) {
  const chatId = update.message.chat.id;
  if (!isAdmin(env, chatId)) return;

  if (!hasDB(env)) {
    await sendMessage(env, chatId, "dbstatus\nDB: false (binding missing)");
    return;
  }

  const t0 = Date.now();
  const r = await dbPing(env);
  await sendMessage(env, chatId, `dbstatus\nDB: true\nping: ${JSON.stringify(r)}\nelapsed_ms: ${Date.now()-t0}`);
}