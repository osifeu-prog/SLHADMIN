import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

TON_WALLET = os.getenv('TON_WALLET', '')

PLANS = {
    'basic': {'name': 'Basic', 'price_usd': 9, 'price_ton': 2.5},
    'pro': {'name': 'Pro', 'price_usd': 29, 'price_ton': 7.5},
    'vip': {'name': 'VIP', 'price_usd': 99, 'price_ton': 25},
}

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = 'SLH Guardian Premium Plans:'
    txt += ' Basic $9 (2.5 TON) | Pro $29 (7.5 TON) | VIP $99 (25 TON)'
    buttons = [
        [InlineKeyboardButton('Basic - 2.5 TON', callback_data='premium_buy:basic')],
        [InlineKeyboardButton('Pro - 7.5 TON', callback_data='premium_buy:pro')],
        [InlineKeyboardButton('VIP - 25 TON', callback_data='premium_buy:vip')],
    ]
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(buttons))

async def premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data.startswith('premium_buy:'):
        return
    key = query.data.split(':')[1]
    plan = PLANS.get(key)
    if not plan:
        return
    n = plan['name']; t = plan['price_ton']; u = plan['price_usd']
    wallet = TON_WALLET or 'UQ_NOT_CONFIGURED'
    msg = 'Plan: ' + n + ' | ' + str(t) + ' TON (~$' + str(u) + '/month)'
    msg += ' | Send to: ' + wallet + ' | After payment DM @osifeu_prog'
    await query.edit_message_text(msg)

def get_premium_handler():
    return CallbackQueryHandler(premium_callback, pattern=r'^premium_buy:')
