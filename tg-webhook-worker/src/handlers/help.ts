import { sendMessage } from "../services/telegram";

export async function handleHelp(env: any, update: any) {
  const chatId = update.message.chat.id;
  const msg = `Help
/start
/whoami
/admin

Admin auth
/login <password>
/logout
/session

/authcheck  (admin debug)
/debug  (admin status)
Admin DB (admin only, requires login)
/dbstatus
/wallet <chat_id>
/credit <chat_id> <amount>
/balance <chat_id>

KV tools (admin only, requires login)
kv get <chat_id>
kv del <chat_id>
`;
  await sendMessage(env, chatId, msg);
}