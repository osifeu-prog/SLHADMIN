export function isAdmin(env: any, chatId: number): boolean {
  const raw = (env.ADMIN_CHAT_ID || "").toString().trim();
  if (!raw) return false;
  return String(chatId) === raw;
}

export function adminOnly(env: any, chatId: number) {
  if (!isAdmin(env, chatId)) {
    throw new Error("UNAUTHORIZED");
  }
}
