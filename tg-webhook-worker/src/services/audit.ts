export async function audit(env: any, action: string, actorChatId?: number, ok: boolean = true, details?: any) {
  try {
    if (!env?.DB) return;
    const id = crypto.randomUUID();
    const payload = details ? JSON.stringify(details).slice(0, 2000) : null;

    await env.DB.prepare(
      "INSERT INTO audit_log(id, actor_chat_id, action, ok, details) VALUES (?1, ?2, ?3, ?4, ?5)"
    ).bind(id, actorChatId ?? null, action, ok ? 1 : 0, payload).run();
  } catch (_e) {
    // never throw from audit
  }
}