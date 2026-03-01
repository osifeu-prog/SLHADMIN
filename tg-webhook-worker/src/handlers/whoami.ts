import { sendMessage } from "../services/telegram";

export async function handleWhoAmI(env: any, update: any) {
  const chatId = update.message.chat.id;
  const from = update.message.from || {};
  const uname = from.username || "";
  const name = [from.first_name, from.last_name].filter(Boolean).join(" ");
  await sendMessage(env, chatId, ` whoami\nchat_id: ${chatId}\nusername: ${uname}\nname: ${name}`);
}
