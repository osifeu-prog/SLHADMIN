import { sendMessage } from "./telegram";
import { audit } from "./audit";

export async function reportError(env: any, where: string, err: any, extra?: any) {
  try {
    await audit(env, "error", undefined, false, {
      where,
      err: err && err.stack ? err.stack : String(err),
      extra
    });
  } catch (_e) {}

  try {
    const admin = Number((env.ADMIN_CHAT_ID || "").toString().trim() || "0");
    if (!admin) return;

    const msg =
`ERROR @ ${where}
ts: ${new Date().toISOString()}
err: ${err && err.stack ? err.stack : String(err)}
extra: ${extra ? JSON.stringify(extra).slice(0, 800) : ""}`;

    await sendMessage(env, admin, msg);
  } catch (_e) {
    // never throw from reporter
  }
}