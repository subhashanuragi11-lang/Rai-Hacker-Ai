
import os
import socket
import socket

hosts = [
    "huggingface.co",
    "router.huggingface.co",
    "api-inference.huggingface.co"
]

for host in hosts:
    try:
        print(f"{host} => {socket.gethostbyname(host)}")
    except Exception as e:
        print(f"{host} => ERROR: {e}")
    
import asyncio
import sqlite3
import logging
import os
import re
import time
import json
import io
import zipfile
import aiohttp
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, FSInputFile
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.client.session.aiohttp import AiohttpSession

# ─── CONFIG ───────────────────────────────────────────────────────────────
BOT_TOKEN = "8931898805:AAGLB86K10gukBhrVcr-zCXCy-QviP7chRM"
ADMIN_ID = 6406769029
DEVELOPER_NAME = "RAI DEVELOPER"
DEVELOPER_USERNAME = "@Subhash_Anuragi_RAI"
MAIN_CHANNEL = "https://t.me/raiaddaarmys"

HF_ACCESS_TOKEN = "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"

HF_MODEL_NAME = "mradermacher/llama3.1-heretic-uncensored-i1-GGUF"

HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL_NAME}"

DB_FILE = "bot_data.db"

# ─── DATABASE ───────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        plan TEXT DEFAULT 'Free',
        premium_expiry TEXT,
        join_date TEXT,
        referral_count INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT NULL,
        banned INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS premium_users (
        user_id INTEGER PRIMARY KEY,
        expiry_date TEXT,
        added_by INTEGER
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        date TEXT,
        rewarded INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS force_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT UNIQUE,
        channel_name TEXT,
        invite_link TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS group_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        reason TEXT,
        group_link TEXT,
        status TEXT DEFAULT 'pending',
        date TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS banned_users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        banned_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS usage_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        amount INTEGER,
        date TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS broadcast_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT,
        success INTEGER,
        failed INTEGER,
        date TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS premium_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        days INTEGER,
        price TEXT
    )''')

    # Default settings
    defaults = [
        ("website_url", "https://example.com"),
        ("referral_reward_hours", "1"),
        ("referral_milestone_reward_months", "2"),
        ("referral_milestone_count", "50"),
        ("free_daily_hours", "4"),
        ("free_daily_code_lines", "2000"),
        ("premium_daily_hours", "12"),
        ("premium_daily_code_lines", "5000"),
    ]
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Default premium plans
    default_plans = [
        ("1 Month", 30, "₹99"),
        ("3 Months", 90, "₹249"),
        ("6 Months", 180, "₹399"),
        ("12 Months", 365, "₹699"),
    ]
    for name, days, price in default_plans:
        c.execute("INSERT OR IGNORE INTO premium_plans (name, days, price) VALUES (?, ?, ?)", (name, days, price))

    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect(DB_FILE)

def get_setting(key, default=""):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

# ─── FLASK KEEP-ALIVE ───────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot Running Successfully | Rai Developer"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ─── BOT SETUP ──────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = AiohttpSession()

bot = Bot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# ─── HELPERS ──────────────────────────────────────────────────────────
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_user(user_id, username, full_name, referred_by=None):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT OR IGNORE INTO users (user_id, username, full_name, join_date, referred_by)
                   VALUES (?, ?, ?, ?, ?)''', (user_id, username, full_name, now, referred_by))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == 1

def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def get_usage_today(user_id, usage_type):
    conn = get_db()
    c = conn.cursor()
    today = get_today()
    c.execute("SELECT SUM(amount) FROM usage_logs WHERE user_id=? AND type=? AND date LIKE ?",
              (user_id, usage_type, today + "%"))
    row = c.fetchone()
    conn.close()
    return row[0] or 0

def add_usage(user_id, usage_type, amount):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO usage_logs (user_id, type, amount, date) VALUES (?, ?, ?, ?)",
              (user_id, usage_type, amount, now))
    conn.commit()
    conn.close()

def is_premium(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT expiry_date FROM premium_users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False
    expiry = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    return expiry > datetime.now()

def get_plan_name(user_id):
    return "Premium" if is_premium(user_id) else "Free"

def get_premium_expiry(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT expiry_date FROM premium_users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "N/A"

def add_premium(user_id, days, added_by):
    conn = get_db()
    c = conn.cursor()
    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR REPLACE INTO premium_users (user_id, expiry_date, added_by) VALUES (?, ?, ?)",
              (user_id, expiry, added_by))
    c.execute("UPDATE users SET plan='Premium', premium_expiry=? WHERE user_id=?", (expiry, user_id))
    conn.commit()
    conn.close()

def remove_premium(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM premium_users WHERE user_id=?", (user_id,))
    c.execute("UPDATE users SET plan='Free', premium_expiry=NULL WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_force_channels():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM force_channels")
    rows = c.fetchall()
    conn.close()
    return rows

def get_referral_count(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] or 0

def get_referral_link(user_id):
    return f"https://t.me/{(BOT_TOKEN.split(':')[0] if False else 'YOUR_BOT_USERNAME')}?start={user_id}"

# ─── FORCE JOIN CHECK ───────────────────────────────────────────────────
async def check_force_join(user_id: int) -> list:
    channels = get_force_channels()
    not_joined = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch[1], user_id=user_id)
            if member.status in ["left", "kicked"]:
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined

def force_join_kb(not_joined):
    buttons = []
    for ch in not_joined:
        buttons.append([InlineKeyboardButton(text=f"📢 Join {ch[2] or ch[1]}", url=ch[3] or f"https://t.me/{ch[1].replace('@', '')}")])
    buttons.append([InlineKeyboardButton(text="✅ Check Join", callback_data="check_join")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ─── MAIN MENU ──────────────────────────────────────────────────────────
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Ask AI", callback_data="ask_ai")],
        [InlineKeyboardButton(text="👤 Profile", callback_data="profile"),
         InlineKeyboardButton(text="🎁 Referral", callback_data="referral")],
        [InlineKeyboardButton(text="💎 Premium Plans", callback_data="premium_plans"),
         InlineKeyboardButton(text="🛒 Buy Projects", callback_data="buy_projects")],
        [InlineKeyboardButton(text="❓ Help", callback_data="help"),
         InlineKeyboardButton(text="📊 Status", callback_data="status")],
        [InlineKeyboardButton(text="➕ Add Bot In Group", callback_data="add_group")],
        [InlineKeyboardButton(text="📞 Admin Contact", callback_data="admin_contact")],
    ])

# ─── START ──────────────────────────────────────────────────────────────
@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    full_name = message.from_user.full_name or "User"

    args = message.text.split()[1] if len(message.text.split()) > 1 else None
    referred_by = int(args) if args and args.isdigit() else None

    user = get_user(user_id)
    if not user:
        add_user(user_id, username, full_name, referred_by)
        if referred_by and referred_by != user_id:
            conn = get_db()
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("SELECT * FROM referrals WHERE referred_id=?", (user_id,))
            if not c.fetchone():
                c.execute("INSERT INTO referrals (referrer_id, referred_id, date) VALUES (?, ?, ?)",
                          (referred_by, user_id, now))
                c.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id=?", (referred_by,))
                # Reward referred user 1 hour premium
                reward_hours = int(get_setting("referral_reward_hours", "1"))
                add_premium(user_id, reward_hours // 24 or 1, 0)
                # Check milestone
                milestone = int(get_setting("referral_milestone_count", "50"))
                milestone_reward = int(get_setting("referral_milestone_reward_months", "2")) * 30
                c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (referred_by,))
                count = c.fetchone()[0]
                if count % milestone == 0:
                    add_premium(referred_by, milestone_reward, 0)
            conn.commit()
            conn.close()

    if is_banned(user_id):
        await message.answer("🚫 <b>You are banned from using this bot.</b>")
        return

    not_joined = await check_force_join(user_id)
    if not_joined:
        await message.answer(
            "🔒 <b>Please join all required channels to use this bot.</b>",
            reply_markup=force_join_kb(not_joined)
        )
        return

    await message.answer(
        f"👋 <b>Welcome, {full_name}!</b>\n\n"
        f"🤖 <b>Rai AI Bot</b> is ready to assist you.\n"
        f"✨ Powered by <b>{DEVELOPER_NAME}</b>",
        reply_markup=main_menu_kb()
    )

@router.callback_query(F.data == "check_join")
async def cb_check_join(callback: CallbackQuery):
    not_joined = await check_force_join(callback.from_user.id)
    if not_joined:
        await callback.answer("❌ You haven't joined all channels yet!", show_alert=True)
        await callback.message.edit_text(
            "🔒 <b>Please join all required channels to use this bot.</b>",
            reply_markup=force_join_kb(not_joined)
        )
    else:
        await callback.answer("✅ Welcome!", show_alert=True)
        await callback.message.edit_text(
            f"👋 <b>Welcome!</b>\n\n"
            f"🤖 <b>Rai AI Bot</b> is ready to assist you.\n"
            f"✨ Powered by <b>{DEVELOPER_NAME}</b>",
            reply_markup=main_menu_kb()
        )

# ─── ASK AI ─────────────────────────────────────────────────────────────
user_ai_state = {}

@router.callback_query(F.data == "ask_ai")
async def cb_ask_ai(callback: CallbackQuery):
    user_id = callback.from_user.id
    if is_banned(user_id):
        await callback.answer("🚫 You are banned!", show_alert=True)
        return
    not_joined = await check_force_join(user_id)
    if not_joined:
        await callback.answer("❌ Join channels first!", show_alert=True)
        return
    user_ai_state[user_id] = True
    await callback.message.edit_text(
        "🤖 <b>Ask AI</b>\n\n"
        "You can ask anything.\n"
        "This is Uncensored AI powered by Rai Developer.\n\n"
        "✏️ <i>Send your question or coding request now.</i>\n\n"
        "🔙 Use /start to go back.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_menu")]
        ])
    )

async def query_ai(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {HF_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 512,
            "temperature": 0.7,
            "return_full_text": False
        }
    }

    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                HF_API_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:

                text = await resp.text()
                print("HF STATUS:", resp.status)
                print("HF RESPONSE:", text)

                if resp.status == 200:
                    data = await resp.json()

                    if isinstance(data, list) and len(data) > 0:
                        return data[0].get("generated_text", "No response")

                    return str(data)

                return f"⚠️ AI Error: HTTP {resp.status}\n{text}"

    except Exception as e:
        return f"⚠️ AI Error: {str(e)}"

@router.message(F.text)
async def handle_text(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id):
        return

    # Handle group request flow
    if user_id in group_request_state:
        state = group_request_state[user_id]
        if state["step"] == "reason":
            state["reason"] = message.text
            state["step"] = "link"
            await message.answer("🔗 <b>Now send your Group/Channel link:</b>")
            return
        elif state["step"] == "link":
            state["link"] = message.text
            conn = get_db()
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute('''INSERT INTO group_requests (user_id, username, reason, group_link, date)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, message.from_user.username or "N/A", state["reason"], state["link"], now))
            req_id = c.lastrowid
            conn.commit()
            conn.close()
            del group_request_state[user_id]
            await message.answer("✅ <b>Request submitted!</b>\nAdmin will review it soon.")
            # Notify admin
            await bot.send_message(
                ADMIN_ID,
                f"📩 <b>New Group Request</b>\n\n"
                f"👤 User: @{message.from_user.username or 'N/A'}\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"📝 Reason: {state['reason']}\n"
                f"🔗 Link: {state['link']}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Approve", callback_data=f"grp_approve_{req_id}"),
                     InlineKeyboardButton(text="❌ Reject", callback_data=f"grp_reject_{req_id}")]
                ])
            )
            return

    if user_id not in user_ai_state or not user_ai_state[user_id]:
        return

    not_joined = await check_force_join(user_id)
    if not_joined:
        await message.answer("🔒 <b>Please join all channels first.</b>", reply_markup=force_join_kb(not_joined))
        return

    prompt = message.text
    is_code_request = any(kw in prompt.lower() for kw in ["code", "program", "script", "function", "class", "write", "create", "build", "develop"])

    # Check limits
    premium = is_premium(user_id)
    daily_hours_limit = int(get_setting("premium_daily_hours" if premium else "free_daily_hours", "12" if premium else "4"))
    daily_code_limit = int(get_setting("premium_daily_code_lines" if premium else "free_daily_code_lines", "5000" if premium else "2000"))

    used_hours = get_usage_today(user_id, "hours")
    used_lines = get_usage_today(user_id, "code_lines")

    if used_hours >= daily_hours_limit:
        await message.answer(f"⏰ <b>Daily AI limit reached!</b>\n🔄 Resets at midnight.")
        return

    add_usage(user_id, "hours", 1)

    await message.answer("🤖 <b>Thinking...</b>")

    response = await query_ai(prompt)

    if not response or response.strip() == "":
        response = "⚠️ <b>AI couldn't generate a response. Please try again.</b>"

    # Code handling
    code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', response, re.DOTALL)
    total_code_lines = sum(len(block.splitlines()) for block in code_blocks)

    if is_code_request and total_code_lines > 0:
        if used_lines + total_code_lines > daily_code_limit:
            remaining = daily_code_limit - used_lines
            if remaining <= 0:
                await message.answer("📛 <b>Daily code limit reached!</b>\n🔄 Resets at midnight.")
                return
            await message.answer(
                f"⚠️ <b>Code limit exceeded!</b>\n"
                f"Remaining: {remaining} lines\n"
                f"Requested: {total_code_lines} lines\n\n"
                f"📝 Write <b>Continue</b> to receive remaining code in next ZIP."
            )
            return
        add_usage(user_id, "code_lines", total_code_lines)

    # Send response
    if len(response) > 4000:
        # Large response - create text file
        file_obj = io.BytesIO(response.encode())
        file_obj.name = "ai_response.txt"
        await message.answer_document(FSInputFile(file_obj.name, file_obj), caption="📄 <b>AI Response (Large)</b>")
    elif is_code_request and total_code_lines > 50:
        # ZIP for large code
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            ext = ".py" if "python" in prompt.lower() else ".txt"
            zf.writestr(f"code{ext}", response)
        zip_buffer.seek(0)
        zip_buffer.name = "ai_code.zip"
        await message.answer_document(FSInputFile(zip_buffer.name, zip_buffer), caption="📦 <b>AI Generated Code</b>")
    else:
        await message.answer(response)

# ─── PROFILE ────────────────────────────────────────────────────────────
@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    if not user:
        await callback.answer("User not found!", show_alert=True)
        return
    plan = get_plan_name(user_id)
    expiry = get_premium_expiry(user_id)
    ref_count = get_referral_count(user_id)
    await callback.message.edit_text(
        f"👤 <b>Your Profile</b>\n\n"
        f"🔹 Username: @{user[1] or 'N/A'}\n"
        f"🔹 Name: {user[2]}\n"
        f"🔹 User ID: <code>{user[0]}</code>\n"
        f"🔹 Plan: {'💎 ' + plan if plan == 'Premium' else '🆓 ' + plan}\n"
        f"🔹 Premium Expiry: {expiry if plan == 'Premium' else 'N/A'}\n"
        f"🔹 Join Date: {user[5]}\n"
        f"🔹 Referrals: {ref_count}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]
        ])
    )

# ─── REFERRAL ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "referral")
async def cb_referral(callback: CallbackQuery):
    user_id = callback.from_user.id
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={user_id}"
    ref_count = get_referral_count(user_id)
    await callback.message.edit_text(
        f"🎁 <b>Referral System</b>\n\n"
        f"🔗 <b>Your Link:</b>\n<code>{ref_link}</code>\n\n"
        f"📊 <b>Total Referrals:</b> {ref_count}\n\n"
        f"🎉 <b>Rewards:</b>\n"
        f"• Referred user gets <b>1 Hour Premium</b>\n"
        f"• You get <b>2 Months Premium</b> after 50 referrals\n\n"
        f"📢 Share your link and earn rewards!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Share Link", url=f"https://t.me/share/url?url={ref_link}&text=Join%20Rai%20AI%20Bot")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]
        ])
    )

# ─── PREMIUM PLANS ────────────────────────────────────────────────────────
@router.callback_query(F.data == "premium_plans")
async def cb_premium_plans(callback: CallbackQuery):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM premium_plans")
    plans = c.fetchall()
    conn.close()
    text = "💎 <b>Premium Plans</b>\n\n"
    buttons = []
    for p in plans:
        text += f"• <b>{p[1]}</b> - {p[3]} ({p[2]} days)\n"
        buttons.append([InlineKeyboardButton(text=f"💎 {p[1]} - {p[3]}", callback_data=f"buy_plan_{p[0]}")])
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("buy_plan_"))
async def cb_buy_plan(callback: CallbackQuery):
    await callback.answer("💳 Contact admin to purchase premium!", show_alert=True)

# ─── BUY PROJECTS ─────────────────────────────────────────────────────────
@router.callback_query(F.data == "buy_projects")
async def cb_buy_projects(callback: CallbackQuery):
    url = get_setting("website_url", "https://example.com")
    await callback.message.edit_text(
        f"🛒 <b>Buy Projects</b>\n\n"
        f"If you need source code of any project, visit our website.\n\n"
        f"🔗 <a href='{url}'>Visit Website</a>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Visit Website", url=url)],
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]
        ])
    )

# ─── HELP ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "❓ <b>Help & Guide</b>\n\n"
        "<b>Commands:</b>\n"
        "/start - Start the bot\n"
        "/admin - Admin Panel (Admin only)\n\n"
        "<b>Buttons:</b>\n"
        "• 🤖 <b>Ask AI</b> - Ask anything to AI\n"
        "• 👤 <b>Profile</b> - View your profile\n"
        "• 🎁 <b>Referral</b> - Get referral link & rewards\n"
        "• 💎 <b>Premium Plans</b> - View & buy premium\n"
        "• 🛒 <b>Buy Projects</b> - Visit website for projects\n"
        "• ❓ <b>Help</b> - This guide\n"
        "• 📊 <b>Status</b> - Check your usage status\n"
        "• ➕ <b>Add Bot In Group</b> - Request to add bot in group\n"
        "• 📞 <b>Admin Contact</b> - Contact developer\n\n"
        "<b>Referral System:</b>\n"
        "Share your link. Referred users get 1h premium. You get 2 months after 50 refs.\n\n"
        "<b>Premium Benefits:</b>\n"
        "• 12 hours AI daily\n"
        "• 5000 code lines daily\n"
        "• Unlimited ZIP generations\n\n"
        "<b>AI Usage:</b>\n"
        "Free: 4 hours + 2000 lines/day\n"
        "Premium: 12 hours + 5000 lines/day",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]
        ])
    )

# ─── STATUS ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "status")
async def cb_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    plan = get_plan_name(user_id)
    premium = is_premium(user_id)
    daily_hours_limit = int(get_setting("premium_daily_hours" if premium else "free_daily_hours", "12" if premium else "4"))
    daily_code_limit = int(get_setting("premium_daily_code_lines" if premium else "free_daily_code_lines", "5000" if premium else "2000"))
    used_hours = get_usage_today(user_id, "hours")
    used_lines = get_usage_today(user_id, "code_lines")
    ref_count = get_referral_count(user_id)
    expiry = get_premium_expiry(user_id)
    user = get_user(user_id)
    join_date = user[5] if user else "N/A"

    await callback.message.edit_text(
        f"📊 <b>Your Status</b>\n\n"
        f"💎 <b>Plan:</b> {plan}\n"
        f"⏰ <b>Daily Hours:</b> {used_hours}/{daily_hours_limit}\n"
        f"📄 <b>Code Lines:</b> {used_lines}/{daily_code_limit}\n"
        f"🎁 <b>Referrals:</b> {ref_count}\n"
        f"📅 <b>Premium Expiry:</b> {expiry if plan == 'Premium' else 'N/A'}\n"
        f"🗓 <b>Account Created:</b> {join_date}\n\n"
        f"🔄 Limits reset daily at midnight.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]
        ])
    )

# ─── ADD BOT TO GROUP ─────────────────────────────────────────────────────
group_request_state = {}

@router.callback_query(F.data == "add_group")
async def cb_add_group(callback: CallbackQuery):
    user_id = callback.from_user.id
    group_request_state[user_id] = {"step": "reason"}
    await callback.message.edit_text(
        "➕ <b>Add Bot In Your Group</b>\n\n"
        "📝 <b>Why do you want this bot in your group?</b>\n\n"
        "Please type your reason:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Cancel", callback_data="back_menu")]
        ])
    )

@router.callback_query(F.data.startswith("grp_approve_"))
async def cb_grp_approve(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Unauthorized!", show_alert=True)
        return
    req_id = int(callback.data.split("_")[2])
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM group_requests WHERE id=?", (req_id,))
    row = c.fetchone()
    if row:
        c.execute("UPDATE group_requests SET status='approved' WHERE id=?", (req_id,))
        conn.commit()
        await bot.send_message(row[0], "✅ <b>Your request has been approved.</b>")
    conn.close()
    await callback.answer("✅ Approved!")
    await callback.message.edit_text(callback.message.text + "\n\n✅ <b>APPROVED</b>")

@router.callback_query(F.data.startswith("grp_reject_"))
async def cb_grp_reject(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Unauthorized!", show_alert=True)
        return
    req_id = int(callback.data.split("_")[2])
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM group_requests WHERE id=?", (req_id,))
    row = c.fetchone()
    if row:
        c.execute("UPDATE group_requests SET status='rejected' WHERE id=?", (req_id,))
        conn.commit()
        await bot.send_message(row[0], "❌ <b>Your request has been rejected.</b>")
    conn.close()
    await callback.answer("❌ Rejected!")
    await callback.message.edit_text(callback.message.text + "\n\n❌ <b>REJECTED</b>")

# ─── ADMIN CONTACT ────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin_contact")
async def cb_admin_contact(callback: CallbackQuery):
    await callback.message.edit_text(
        f"📞 <b>Admin Contact</b>\n\n"
        f"👨‍💻 <b>Developer:</b> {DEVELOPER_NAME}\n"
        f"🔗 <b>Username:</b> {DEVELOPER_USERNAME}\n\n"
        f"📢 <b>Main Channel:</b> {MAIN_CHANNEL}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Contact Admin", url=f"https://t.me/{DEVELOPER_USERNAME.replace('@', '')}")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]
        ])
    )

# ─── BACK TO MENU ─────────────────────────────────────────────────────────
@router.callback_query(F.data == "back_menu")
async def cb_back_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_ai_state:
        user_ai_state[user_id] = False
    if user_id in group_request_state:
        del group_request_state[user_id]
    await callback.message.edit_text(
        f"👋 <b>Welcome back!</b>\n\n"
        f"🤖 <b>Rai AI Bot</b> is ready to assist you.\n"
        f"✨ Powered by <b>{DEVELOPER_NAME}</b>",
        reply_markup=main_menu_kb()
    )

# ─── ADMIN PANEL ──────────────────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 <b>Unauthorized!</b>")
        return
    await message.answer(
        "🔐 <b>Admin Dashboard</b>\n\n"
        f"👋 Welcome, <b>{DEVELOPER_NAME}</b>!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Users", callback_data="admin_users"),
             InlineKeyboardButton(text="🚫 Ban User", callback_data="admin_ban")],
            [InlineKeyboardButton(text="✅ Unban User", callback_data="admin_unban"),
             InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📢 Force Channels", callback_data="admin_force_ch"),
             InlineKeyboardButton(text="💎 Premium Manager", callback_data="admin_premium")],
            [InlineKeyboardButton(text="⚙ Settings", callback_data="admin_settings"),
             InlineKeyboardButton(text="🤖 Bot Requests", callback_data="admin_requests")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="admin_stats")],
        ])
    )

@router.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM premium_users")
    premium = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM banned_users")
    banned = c.fetchone()[0]
    conn.close()
    await callback.message.edit_text(
        f"👥 <b>Users Statistics</b>\n\n"
        f"📊 Total Users: {total}\n"
        f"💎 Premium Users: {premium}\n"
        f"🚫 Banned Users: {banned}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
    )

@router.callback_query(F.data == "admin_ban")
async def cb_admin_ban(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "🚫 <b>Ban User</b>\n\n"
        "Send: <code>/ban USERNAME</code> or <code>/ban USER_ID</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
    )

@router.callback_query(F.data == "admin_unban")
async def cb_admin_unban(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "✅ <b>Unban User</b>\n\n"
        "Send: <code>/unban USERNAME</code> or <code>/unban USER_ID</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
    )

@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "📢 <b>Broadcast</b>\n\n"
        "Send: <code>/broadcast YOUR MESSAGE</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
    )

@router.callback_query(F.data == "admin_force_ch")
async def cb_admin_force_ch(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    channels = get_force_channels()
    text = "📢 <b>Force Channels</b>\n\n"
    for ch in channels:
        text += f"• {ch[2] or ch[1]} ({ch[1]})\n"
    text += "\nCommands:\n<code>/addch CHANNEL_ID NAME LINK</code>\n<code>/delch CHANNEL_ID</code>"
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
    )

@router.callback_query(F.data == "admin_premium")
async def cb_admin_premium(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM premium_plans")
    plans = c.fetchall()
    conn.close()
    text = "💎 <b>Premium Manager</b>\n\n<b>Plans:</b>\n"
    for p in plans:
        text += f"• {p[1]} - {p[3]} ({p[2]} days) [ID: {p[0]}]\n"
    text += "\nCommands:\n<code>/addp USERNAME DAYS</code>\n<code>/unp USERNAME</code>\n<code>/addplan NAME DAYS PRICE</code>\n<code>/delplan ID</code>"
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
    )

@router.callback_query(F.data == "admin_settings")
async def cb_admin_settings(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    url = get_setting("website_url", "Not set")
    await callback.message.edit_text(
        f"⚙ <b>Settings</b>\n\n"
        f"🌐 Website URL: {url}\n\n"
        f"Commands:\n"
        f"<code>/seturl URL</code> - Set website URL\n"
        f"<code>/delurl</code> - Delete website URL\n"
        f"<code>/setrefhours HOURS</code> - Referral reward hours\n"
        f"<code>/setmilestone COUNT MONTHS</code> - Milestone settings",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
    )

@router.callback_query(F.data == "admin_requests")
async def cb_admin_requests(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM group_requests WHERE status='pending' ORDER BY id DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await callback.message.edit_text(
            "🤖 <b>Bot Requests</b>\n\nNo pending requests.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
            ])
        )
        return
    for row in rows:
        await callback.message.answer(
            f"📩 <b>Request #{row[0]}</b>\n\n"
            f"👤 User: @{row[2]}\n"
            f"🆔 ID: <code>{row[1]}</code>\n"
            f"📝 Reason: {row[3]}\n"
            f"🔗 Link: {row[4]}\n"
            f"📅 Date: {row[6]}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Approve", callback_data=f"grp_approve_{row[0]}"),
                 InlineKeyboardButton(text="❌ Reject", callback_data=f"grp_reject_{row[0]}")]
            ])
        )
    await callback.message.edit_text(
        "🤖 <b>Bot Requests</b>\n\nPending requests sent above.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
    )

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM premium_users")
    premium_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM banned_users")
    banned_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM group_requests WHERE status='pending'")
    pending_reqs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM referrals")
    total_refs = c.fetchone()[0]
    conn.close()
    await callback.message.edit_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total Users: {total_users}\n"
        f"💎 Premium Users: {premium_users}\n"
        f"🚫 Banned Users: {banned_users}\n"
        f"📩 Pending Requests: {pending_reqs}\n"
        f"🎁 Total Referrals: {total_refs}\n\n"
        f"🤖 Bot: @{DEVELOPER_USERNAME}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
    )

@router.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "🔐 <b>Admin Dashboard</b>\n\n"
        f"👋 Welcome, <b>{DEVELOPER_NAME}</b>!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Users", callback_data="admin_users"),
             InlineKeyboardButton(text="🚫 Ban User", callback_data="admin_ban")],
            [InlineKeyboardButton(text="✅ Unban User", callback_data="admin_unban"),
             InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📢 Force Channels", callback_data="admin_force_ch"),
             InlineKeyboardButton(text="💎 Premium Manager", callback_data="admin_premium")],
            [InlineKeyboardButton(text="⚙ Settings", callback_data="admin_settings"),
             InlineKeyboardButton(text="🤖 Bot Requests", callback_data="admin_requests")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="admin_stats")],
        ])
    )

# ─── ADMIN COMMANDS ───────────────────────────────────────────────────────
@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    target = command.args
    if not target:
        await message.answer("❌ Usage: <code>/ban USERNAME</code> or <code>/ban USER_ID</code>")
        return
    conn = get_db()
    c = conn.cursor()
    if target.isdigit():
        c.execute("UPDATE users SET banned=1 WHERE user_id=?", (int(target),))
        c.execute("INSERT OR REPLACE INTO banned_users (user_id, banned_at) VALUES (?, ?)",
                  (int(target), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    else:
        c.execute("UPDATE users SET banned=1 WHERE username=?", (target.replace("@", ""),))
        c.execute("SELECT user_id FROM users WHERE username=?", (target.replace("@", ""),))
        row = c.fetchone()
        if row:
            c.execute("INSERT OR REPLACE INTO banned_users (user_id, banned_at) VALUES (?, ?)",
                      (row[0], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    await message.answer("✅ <b>User banned successfully.</b>")

@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    target = command.args
    if not target:
        await message.answer("❌ Usage: <code>/unban USERNAME</code> or <code>/unban USER_ID</code>")
        return
    conn = get_db()
    c = conn.cursor()
    if target.isdigit():
        c.execute("UPDATE users SET banned=0 WHERE user_id=?", (int(target),))
        c.execute("DELETE FROM banned_users WHERE user_id=?", (int(target),))
    else:
        c.execute("UPDATE users SET banned=0 WHERE username=?", (target.replace("@", ""),))
        c.execute("SELECT user_id FROM users WHERE username=?", (target.replace("@", ""),))
        row = c.fetchone()
        if row:
            c.execute("DELETE FROM banned_users WHERE user_id=?", (row[0],))
    conn.commit()
    conn.close()
    await message.answer("✅ <b>User unbanned successfully.</b>")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    text = command.args
    if not text:
        await message.answer("❌ Usage: <code>/broadcast YOUR MESSAGE</code>")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    success = 0
    failed = 0
    for u in users:
        try:
            await bot.send_message(u[0], f"📢 <b>Broadcast</b>\n\n{text}")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO broadcast_logs (message, success, failed, date) VALUES (?, ?, ?, ?)",
              (text, success, failed, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    await message.answer(f"📢 <b>Broadcast Complete!</b>\n\n✅ Success: {success}\n❌ Failed: {failed}")

@router.message(Command("addch"))
async def cmd_addch(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    args = command.args
    if not args:
        await message.answer("❌ Usage: <code>/addch CHANNEL_ID NAME LINK</code>")
        return
    parts = args.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("❌ Usage: <code>/addch CHANNEL_ID NAME LINK</code>")
        return
    ch_id = parts[0]
    name = parts[1]
    link = parts[2] if len(parts) > 2 else ""
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO force_channels (channel_id, channel_name, invite_link) VALUES (?, ?, ?)",
              (ch_id, name, link))
    conn.commit()
    conn.close()
    await message.answer(f"✅ <b>Channel added:</b> {name}")

@router.message(Command("delch"))
async def cmd_delch(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    ch_id = command.args
    if not ch_id:
        await message.answer("❌ Usage: <code>/delch CHANNEL_ID</code>")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM force_channels WHERE channel_id=?", (ch_id,))
    conn.commit()
    conn.close()
    await message.answer("✅ <b>Channel removed.</b>")

@router.message(Command("addp"))
async def cmd_addp(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    args = command.args
    if not args:
        await message.answer("❌ Usage: <code>/addp USERNAME DAYS</code>")
        return
    parts = args.split()
    if len(parts) < 2:
        await message.answer("❌ Usage: <code>/addp USERNAME DAYS</code>")
        return
    username = parts[0].replace("@", "")
    days = int(parts[1])
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("❌ User not found.")
        return
    add_premium(row[0], days, ADMIN_ID)
    await message.answer(f"✅ <b>Premium added!</b>\nUser: @{username}\nDays: {days}")

@router.message(Command("unp"))
async def cmd_unp(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    username = command.args
    if not username:
        await message.answer("❌ Usage: <code>/unp USERNAME</code>")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE username=?", (username.replace("@", ""),))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("❌ User not found.")
        return
    remove_premium(row[0])
    await message.answer(f"✅ <b>Premium removed!</b>\nUser: @{username}")

@router.message(Command("addplan"))
async def cmd_addplan(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    args = command.args
    if not args:
        await message.answer("❌ Usage: <code>/addplan NAME DAYS PRICE</code>")
        return
    parts = args.rsplit(" ", 2)
    if len(parts) < 3:
        await message.answer("❌ Usage: <code>/addplan NAME DAYS PRICE</code>")
        return
    name = parts[0]
    days = int(parts[1])
    price = parts[2]
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO premium_plans (name, days, price) VALUES (?, ?, ?)", (name, days, price))
    conn.commit()
    conn.close()
    await message.answer(f"✅ <b>Plan added:</b> {name} - {price}")

@router.message(Command("delplan"))
async def cmd_delplan(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    plan_id = command.args
    if not plan_id or not plan_id.isdigit():
        await message.answer("❌ Usage: <code>/delplan ID</code>")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM premium_plans WHERE id=?", (int(plan_id),))
    conn.commit()
    conn.close()
    await message.answer("✅ <b>Plan deleted.</b>")

@router.message(Command("seturl"))
async def cmd_seturl(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    url = command.args
    if not url:
        await message.answer("❌ Usage: <code>/seturl URL</code>")
        return
    set_setting("website_url", url)
    await message.answer(f"✅ <b>Website URL set:</b> {url}")

@router.message(Command("delurl"))
async def cmd_delurl(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("website_url", "")
    await message.answer("✅ <b>Website URL removed.</b>")

@router.message(Command("setrefhours"))
async def cmd_setrefhours(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    hours = command.args
    if not hours or not hours.isdigit():
        await message.answer("❌ Usage: <code>/setrefhours HOURS</code>")
        return
    set_setting("referral_reward_hours", hours)
    await message.answer(f"✅ <b>Referral reward set:</b> {hours} hours")

@router.message(Command("setmilestone"))
async def cmd_setmilestone(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    args = command.args
    if not args:
        await message.answer("❌ Usage: <code>/setmilestone COUNT MONTHS</code>")
        return
    parts = args.split()
    if len(parts) < 2:
        await message.answer("❌ Usage: <code>/setmilestone COUNT MONTHS</code>")
        return
    set_setting("referral_milestone_count", parts[0])
    set_setting("referral_milestone_reward_months", parts[1])
    await message.answer(f"✅ <b>Milestone updated:</b> {parts[0]} refs = {parts[1]} months premium")

# ─── MAIN ─────────────────────────────────────────────────────────────────
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    asyncio.run(main())
