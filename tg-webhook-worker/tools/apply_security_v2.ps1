param([string]$Root = ".")
$ErrorActionPreference="Stop"
Set-Location $Root

function WriteFile([string]$Path, [string]$Text){
  $full = Join-Path (Get-Location) $Path
  $dir = Split-Path -Parent $full
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $enc = New-Object System.Text.UTF8Encoding($false)
  $lf = $Text -replace "`r`n","`n"
  [System.IO.File]::WriteAllText($full, $lf, $enc)
  "WROTE $Path"
}

$auth = @'
function toHex(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (const b of bytes) s += b.toString(16).padStart(2, "0");
  return s;
}
export async function sha256Hex(text: string): Promise<string> {
  const data = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return toHex(hash);
}
export function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}
export async function verifyAdminPassword(env: any, candidate: string): Promise<boolean> {
  const expected = (env.ADMIN_PASS_SHA256 || "").toString().trim().toLowerCase();
  if (!expected) return false;
  const got = (await sha256Hex(candidate)).toLowerCase();
  return timingSafeEqual(got, expected);
}
'@

$session = @'
const SESSION_TTL_SEC = 6 * 60 * 60; // 6h
export async function setAdminSession(env: any, chatId: number): Promise<void> {
  if (!env?.KV) return;
  await env.KV.put(`admin:session:${chatId}`, String(Date.now()), { expirationTtl: SESSION_TTL_SEC });
}
export async function clearAdminSession(env: any, chatId: number): Promise<void> {
  if (!env?.KV) return;
  await env.KV.delete(`admin:session:${chatId}`);
}
export async function hasAdminSession(env: any, chatId: number): Promise<boolean> {
  if (!env?.KV) return false;
  const v = await env.KV.get(`admin:session:${chatId}`);
  return !!v;
}
'@

$login = @'
import { sendMessage } from "../services/telegram";
import { verifyAdminPassword } from "../services/auth";
import { setAdminSession } from "../services/admin_session";

export async function handleLogin(env: any, update: any, text: string) {
  const chat = update.message.chat;
  const chatId = chat.id;
  if (chat.type !== "private") {
    await sendMessage(env, chatId, "Login allowed only in private chat.");
    return;
  }

  const adminId = Number((env.ADMIN_CHAT_ID || "").toString().trim() || "0");
  if (!adminId || chatId !== adminId) {
    await sendMessage(env, chatId, "Unauthorized.");
    return;
  }

  const parts = text.trim().split(/\\s+/);
  if (parts.length < 2) {
    await sendMessage(env, chatId, "Usage: /login <password>");
    return;
  }

  const pass = parts.slice(1).join(" ");
  const ok = await verifyAdminPassword(env, pass);
  if (!ok) {
    await sendMessage(env, chatId, "Login failed.");
    return;
  }

  await setAdminSession(env, chatId);
  await sendMessage(env, chatId, "Admin session enabled (6h).");
}
'@

$logout = @'
import { sendMessage } from "../services/telegram";
import { clearAdminSession } from "../services/admin_session";

export async function handleLogout(env: any, update: any) {
  const chatId = update.message.chat.id;
  await clearAdminSession(env, chatId);
  await sendMessage(env, chatId, "Logged out.");
}
'@

$help = @'
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
'@

$router = @'
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

  const ok = await rateLimit(env, String(chatId), 30, 60);
  if (!ok) return;

  // auth commands always available (but will only succeed for ADMIN_CHAT_ID)
  if (text === "/login" || text.startsWith("/login ")) return await handleLogin(env, update, text);
  if (text === "/logout") return await handleLogout(env, update);

  // public
  if (text === "/start") return await handleStart(env, update);
  if (text === "/help") return await handleHelp(env, update);
  if (text === "/whoami") return await handleWhoAmI(env, update);

  // gated admin actions
  const isAdminCmd = (
    text === "/admin" || text === "/status" || text === "/stats" || text === "/users" || text === "/dbstatus" ||
    text.startsWith("/wallet ") || text.startsWith("/credit ") || text.startsWith("/balance ") || text.startsWith("kv ")
  );

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
'@

WriteFile "src/services/auth.ts" $auth
WriteFile "src/services/admin_session.ts" $session
WriteFile "src/handlers/login.ts" $login
WriteFile "src/handlers/logout.ts" $logout
WriteFile "src/handlers/help.ts" $help
WriteFile "src/router.ts" $router
