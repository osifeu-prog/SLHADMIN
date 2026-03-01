import { sendMessage } from "../services/telegram";
import { isAdmin } from "../services/admin";

export async function handleAdmin(env: any, update: any) {
  const chatId = update.message.chat.id;

  if (!isAdmin(env, chatId)) {
    await sendMessage(env, chatId, " Unauthorized");
    return;
  }

  const menu =
` Guardian Admin Menu

/status          - runtime status
/stats           - KV stats
/users           - list last users (KV prefix user:)
kv get <chat_id> - fetch user record
kv del <chat_id> - delete user record

/help            - user help
/whoami          - show your ids
`;

  await sendMessage(env, chatId, menu);
}
