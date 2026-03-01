export async function sendMessage(env: any, chatId: number, text: string) {
  const r = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });

  if (!r.ok) {
    const t = await r.text();
    console.log("Telegram sendMessage failed:", r.status, t);
  }
}
