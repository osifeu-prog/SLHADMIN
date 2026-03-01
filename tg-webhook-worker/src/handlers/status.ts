import { sendMessage } from "../services/telegram";
import { isAdmin } from "../services/admin";

export async function handleStatus(env: any, update: any) {
  const chatId = update.message.chat.id;
  if (!isAdmin(env, chatId)) {
    await sendMessage(env, chatId, " Unauthorized");
    return;
  }

  const now = new Date().toISOString();
  const hasKV = !!env.KV;
  const hasBot = !!env.BOT_TOKEN;
  const hasSecret = !!env.TG_SECRET_TOKEN;

  await sendMessage(env, chatId,
` status
time: ${now}
KV: ${hasKV}
BOT_TOKEN: ${hasBot}
TG_SECRET_TOKEN: ${hasSecret}
`);
}
