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
const SESSION_TTL_SEC = 6 * 60 * 60;
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
  if (chat.type !== "private") { await sendMessage(env, chatId, "Login allowed only in private chat."); return; }
  const adminId = Number((env.ADMIN_CHAT_ID || "").toString().trim() || "0");
  if (!adminId || chatId !== adminId) { await sendMessage(env, chatId, "Unauthorized."); return; }
  const parts = text.trim().split(/\\s+/);
  if (parts.length < 2) { await sendMessage(env, chatId, "Usage: /login <password>"); return; }
  const pass = parts.slice(1).join(" ");
  const ok = await verifyAdminPassword(env, pass);
  if (!ok) { await sendMessage(env, chatId, "Login failed."); return; }
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

WriteFile "src/services/auth.ts" $auth
WriteFile "src/services/admin_session.ts" $session
WriteFile "src/handlers/login.ts" $login
WriteFile "src/handlers/logout.ts" $logout
WriteFile "src/handlers/help.ts" $help

$routerPath = Join-Path (Get-Location) "src/router.ts"
$router = Get-Content $routerPath -Raw

if ($router -notmatch "admin_session") {
  $router = $router -replace "import \\{ rateLimit \\} from \\"\\.\\/services\\/ratelimit\\";","import { rateLimit } from \"./services/ratelimit\";`nimport { hasAdminSession } from \"./services/admin_session\";";
}
if ($router -notmatch "handleLogin") {
  $router = $router -replace "import \\{ handleHelp \\} from \\"\\.\\/handlers\\/help\\";","import { handleHelp } from \"./handlers/help\";`nimport { handleLogin } from \"./handlers/login\";`nimport { handleLogout } from \"./handlers/logout\";";
}
if ($router -notmatch "startsWith\\(\\\"\\/login") {
  $router = $router -replace "if \\(text === \\"\\/help\\"" , "if (text === \"/login\" || text.startsWith(\"/login \")) return await handleLogin(env, update, text);`n  if (text === \"/logout\") return await handleLogout(env, update);`n  if (text === \"/help\"";
}
if ($router -notmatch "requiresAdmin") {
  $inject = "`n  const adminId = Number((env.ADMIN_CHAT_ID || '').toString().trim() || '0');`n  const isAdminChat = adminId && chatId === adminId;`n  const requiresAdmin = [\"/admin\",\"/status\",\"/stats\",\"/users\",\"/dbstatus\"].includes(text) || text.startsWith(\"/wallet \") || text.startsWith(\"/credit \") || text.startsWith(\"/balance \") || text.startsWith(\"kv \");`n  if (requiresAdmin) {`n    const okSession = isAdminChat && (await hasAdminSession(env, chatId));`n    if (!okSession) {`n      return await handleHelp(env, update);`n    }`n  }`n";
  $router = $router -replace "const text = \\(update\\.message\\.text \\|\\| \\"\\"\\)\\.trim\\(\\);", "const text = (update.message.text || \"\").trim();$inject";
}
Set-Content -Encoding utf8 $routerPath $router
"PATCHED router.ts"
