import asyncpg, os, random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

QUESTIONS = [
    {"id": 1, "q": "מה הוא Bitcoin?", "options": ["מטבע קריפטו מבוזר", "מניה בבורסה", "בנק דיגיטלי", "NFT"], "answer": "מטבע קריפטו מבוזר"},
    {"id": 2, "q": "מה עושה Blockchain?", "options": ["מאחסן נתונים בשרשרת בלוקים", "מכרה ביטקוין", "מנהל ארנקים", "מחשב מחירים"], "answer": "מאחסן נתונים בשרשרת בלוקים"},
    {"id": 3, "q": "מה זה DeFi?", "options": ["פיננסים מבוזרים", "מטבע דיגיטלי", "בורסה מרכזית", "ארנק חומרה"], "answer": "פיננסים מבוזרים"},
    {"id": 4, "q": "מה זה Gas ב-Ethereum?", "options": ["עמלת עסקה", "סוג מטבע", "פרוטוקול אבטחה", "שם בורסה"], "answer": "עמלת עסקה"},
    {"id": 5, "q": "מה זה NFT?", "options": ["טוקן לא ניתן להחלפה", "מטבע יציב", "רשת בלוקצ׳יין", "ארנק קר"], "answer": "טוקן לא ניתן להחלפה"},
    {"id": 6, "q": "מה זה Staking?", "options": ["נעילת מטבעות לתגמול", "מכירת מטבעות", "כריית ביטקוין", "העברת טוקנים"], "answer": "נעילת מטבעות לתגמול"},
    {"id": 7, "q": "מה זה Smart Contract?", "options": ["חוזה מבצע עצמי על בלוקצ׳יין", "הסכם בין בנקים", "ארנק מאובטח", "פרוטוקול הצפנה"], "answer": "חוזה מבצע עצמי על בלוקצ׳יין"},
    {"id": 8, "q": "מה זה Wallet Address?", "options": ["כתובת ציבורית לקבלת מטבעות", "סיסמת ארנק", "מפתח פרטי", "שם משתמש בבורסה"], "answer": "כתובת ציבורית לקבלת מטבעות"},
    {"id": 9, "q": "מה זה Liquidity Pool?", "options": ["מאגר נזילות למסחר מבוזר", "קרן השקעות", "בנק מרכזי", "מכרה קריפטו"], "answer": "מאגר נזילות למסחר מבוזר"},
    {"id": 10, "q": "מה זה SLH Token?", "options": ["טוקן תגמולים של SLH Guardian", "מטבע בורסאי", "סטייבלקוין", "NFT של אמן"], "answer": "טוקן תגמולים של SLH Guardian"},
]

XP_PER_CORRECT = 10
SLH_PER_CORRECT = 1.0

async def _get_conn():
    import asyncpg, os
    return await asyncpg.connect(os.environ["DATABASE_URL"])

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    q = random.choice(QUESTIONS)
    context.user_data["quiz_q"] = q
    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"quiz:{q['id']}:{opt}")]
        for opt in q["options"]
    ]
    await update.message.reply_text(
        f"🧠 *Crypto Quiz*\n\n{q['q']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    parts = data.split(":", 2)
    if len(parts) != 3:
        return
    _, qid_str, chosen = parts
    qid = int(qid_str)
    q = next((x for x in QUESTIONS if x["id"] == qid), None)
    if not q:
        return
    correct = chosen == q["answer"]
    conn = await _get_conn()
    try:
        await conn.execute(
            "INSERT INTO quiz_attempts (user_id, question_id, chosen_answer, correct) VALUES ($1,$2,$3,$4)",
            user_id, qid, chosen, correct
        )
        if correct:
            await conn.execute(
                "UPDATE users SET xp = COALESCE(xp,0) + $1 WHERE user_id = $2",
                XP_PER_CORRECT, user_id
            )
            await conn.execute(
                "INSERT INTO token_balances (user_id, token, balance) VALUES ($1, 'SLH', $2) ON CONFLICT (user_id, token) DO UPDATE SET balance = token_balances.balance + EXCLUDED.balance",
                user_id, SLH_PER_CORRECT
            )
    finally:
        await conn.close()
    if correct:
        msg = f"✅ נכון! +{XP_PER_CORRECT} XP ו-+{SLH_PER_CORRECT} SLH נוספו לחשבונך."
    else:
        msg = f"❌ לא נכון. התשובה הנכונה: *{q['answer']}*"
    await query.edit_message_text(msg, parse_mode="Markdown")

def get_quiz_handler():
    return CallbackQueryHandler(quiz_callback, pattern=r"^quiz:")
