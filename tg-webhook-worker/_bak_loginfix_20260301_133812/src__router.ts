import { handleStart } from "./handlers/start";
import { handleHelp } from "./handlers/help";
import { handleWhoAmI } from "./handlers/whoami";
import { handleAdmin } from "./handlers/admin";
import { handleStatus } from "./handlers/status";
import { handleStats } from "./handlers/stats";
import { handleUsers } from "./handlers/users";
import { handleKvTools } from "./handlers/kvtools";
import { handleDbStatus } from "./handlers/dbstatus";
import { handleWallet } from "./handlers/wallet";
import { handleCredit } from "./handlers/credit";
import { handleBalance } from "./handlers/balance";
import { handleLogin } from "./handlers/login";
import { handleLogout } from "./handlers/logout";
import { handleSession } from "./handlers/session";
import { rateLimit } from "./services/ratelimit";
import { hasAdminSession } from "./services/admin_session";

function isAdminChat(env: any, chatId: number): boolean {
  const adminId = Number((env.ADMIN_CHAT_ID || "").toString().trim() || "0");
  return !!adminId && chatId === adminId;
}

async function requireAdminSession(env: any, chatId: number): Promise<boolean> {
  if (!isAdminChat(env, chatId)) return false;
  return await hasAdminSession(env, chatId);
}

export async function route(env: any, update: any) {
  if (!update?.message) return;

  const chatId = update.message.chat.id;
  const text = (update.message.text || "").trim();

  const rlOk = await rateLimit(env, String(chatId), 30, 60);
  if (!rlOk) return;

  // auth/session always available
  if (text === "/login" || text.startsWith("/login ")) return await handleLogin(env, update, text);
  if (text === "/logout") return await handleLogout(env, update);
  if (text === "/session") return await handleSession(env, update);

  // public
  if (text === "/start") return await handleStart(env, update);
  if (text === "/help") return await handleHelp(env, update);
  if (text === "/whoami") return await handleWhoAmI(env, update);

  // gated admin actions
  const isAdminCmd =
    text === "/admin" || text === "/status" || text === "/stats" || text === "/users" || text === "/dbstatus" ||
    text.startsWith("/wallet ") || text.startsWith("/credit ") || text.startsWith("/balance ") || text.startsWith("kv ");

  if (isAdminCmd) {
    const okSession = await requireAdminSession(env, chatId);
    if (!okSession) {
      await handleHelp(env, update);
      return;
    }
  }

  if (text === "/admin") return await handleAdmin(env, update);
  if (text === "/status") return await handleStatus(env, update);
  if (text === "/stats") return await handleStats(env, update);
  if (text === "/users") return await handleUsers(env, update);
  if (text === "/dbstatus") return await handleDbStatus(env, update);
  if (text.startsWith("/wallet ")) return await handleWallet(env, update, text);
  if (text.startsWith("/credit ")) return await handleCredit(env, update, text);
  if (text.startsWith("/balance ")) return await handleBalance(env, update, text);
  if (text.startsWith("kv ")) return await handleKvTools(env, update, text);
}