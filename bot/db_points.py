from __future__ import annotations

import json
from sqlalchemy import text

async def ensure_user(conn, chat_id: int, username: str | None) -> int:
    # returns users.id
    row = (await conn.execute(
        text("select id from users where chat_id = :chat_id limit 1"),
        {"chat_id": chat_id},
    )).first()
    if row:
        return int(row[0])

    row = (await conn.execute(
        text("insert into users (chat_id, username) values (:chat_id, :username) returning id"),
        {"chat_id": chat_id, "username": username},
    )).first()
    return int(row[0])

async def ensure_points_account(conn, user_id: int) -> None:
    # account "type" and "label" are required. We'll standardize: type='points', label='Points'
    row = (await conn.execute(
        text("select id from accounts where user_id = :uid and type = 'points' limit 1"),
        {"uid": user_id},
    )).first()
    if row:
        return

    details = json.dumps({"kind": "points"}, ensure_ascii=False)
    await conn.execute(
        text("insert into accounts (user_id, type, label, details_json) values (:uid, 'points', 'Points', :dj)"),
        {"uid": user_id, "dj": details},
    )

async def points_balance(conn, user_id: int) -> int:
    row = (await conn.execute(
        text("select coalesce(sum(delta),0) as bal from points_ledger where user_id = :uid"),
        {"uid": user_id},
    )).first()
    return int(row[0] or 0)
