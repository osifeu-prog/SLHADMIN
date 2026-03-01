import { sendMessage } from "../services/telegram";
import { isAdmin } from "../services/admin";

export async function handleUsers(env: any, update: any) {
  const chatId = update.message.chat.id;
  if (!isAdmin(env, chatId)) {
    await sendMessage(env, chatId, " Unauthorized");
    return;
  }

  const res = await env.KV.list({ prefix: "user:", limit: 20 });
  const keys = (res.keys || []).map((k: any) => k.name);

  if (!keys.length) {
    await sendMessage(env, chatId, "No users in KV yet.");
    return;
  }

  await sendMessage(env, chatId, " users (KV keys)\n" + keys.join("\n"));
}
