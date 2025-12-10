from translation import Translation
from config import AUTH_CHANNEL, PASS, PRE_LOG
from functions.settings import Settings, Login
from functions.forcesub import handle_force_subscribe

from pyrogram.emoji import *
from pyrogram import Client, filters, types, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.database import db


@Client.on_message(filters.private & filters.command(["start", "help"]))
async def start_handler(c: Client, m: "types.Message"):
    if not m.from_user:
        return await m.reply_text("Seni tanımıyorum ahbap.")
    if AUTH_CHANNEL:
        fsub = await handle_force_subscribe(c, m)
        if fsub == 400:
            return
    await m.reply_text(
        text=Translation.START_TEXT.format(m.from_user.mention),
        disable_web_page_preview=True,
        reply_to_message_id=m.id,
        reply_markup=Translation.START_BUTTONS
    )

@Client.on_message(filters.private & filters.command(["ayarlar", "settings"]))
async def delete_thumb_handler(c: Client, m: "types.Message"):
    if not m.from_user:
        return await m.reply_text("Seni tanımıyorum ahbap.")
    if AUTH_CHANNEL:
        fsub = await handle_force_subscribe(c, m)
        if fsub == 400:
            return
    await Settings(m)


@Client.on_message(filters.private & filters.incoming & filters.command("login"), group=4)
async def login_handler(c, m):
    if PASS:
        chat_id = m.chat.id
        logged = await db.get_user_pass(chat_id)
        if logged != PASS:
            await db.delete_user(chat_id)
        elif logged is not None:
            return await m.reply(f"__Zaten giriş yaptınız.__ {VICTORY_HAND}")
        await Login(c, m)
