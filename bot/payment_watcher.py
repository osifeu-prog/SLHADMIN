import asyncio, httpx, os
from guardian_infra import db

TON_ADDRESS = "UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp"
ADMIN_ID = 224223270

async def check_ton_payments(app):
    last_tx = None
    while True:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://tonapi.io/v2/blockchain/accounts/{TON_ADDRESS}/transactions?limit=10")
                data = r.json()
                for tx in data.get("transactions", []):
                    txid = tx["hash"]
                    if txid == last_tx:
                        continue
                    in_msg = tx.get("in_msg", {})
                    value = int(in_msg.get("value", "0")) / 1e9
                    if value >= 1:
                        await db.execute(
                            "INSERT INTO payments (txid, amount, status) VALUES (\, \, 'pending') ON CONFLICT DO NOTHING",
                            txid, value
                        )
                        await app.bot.send_message(ADMIN_ID, f"💰 New TON payment: {value} TON\nTXID: {txid}\n/pay {txid}")
                        last_tx = txid
        except Exception as e:
            print(f"Payment watcher error: {e}")
        await asyncio.sleep(300)
