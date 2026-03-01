export async function saveUser(env: any, chatId: number, data: any) {
  await env.KV.put(`user:${chatId}`, JSON.stringify(data));
}

export async function getUser(env: any, chatId: number) {
  const data = await env.KV.get(`user:${chatId}`);
  return data ? JSON.parse(data) : null;
}
