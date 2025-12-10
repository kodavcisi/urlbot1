from pyrogram import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from functions.forcesub import handle_force_subscribe
from config import AUTH_CHANNEL
from database.add import add_user_to_database
from functions.settings import *
from translation import Translation


@Client.on_message(filters.private & filters.photo)
@Client.on_message(filters.command(["setthumb", "set_thumbnail"]) & filters.incoming & filters.reply)
async def set_thumbnail(c: Client, m: "types.Message"):
    if (not m.reply_to_message) or (not m.reply_to_message.photo):
        thumbnail = m.photo.file_id
    else:
        thumbnail = m.reply_to_message.photo.file_id
    if not m.from_user:
        return await m.reply_text("Seni tanımıyorum ahbap.")
    if AUTH_CHANNEL:
        fsub = await handle_force_subscribe(c, m)
        if fsub == 400:
            return
    editable = await m.reply_text("**👀 İşleniyor...**")
    await db.set_thumbnail(m.from_user.id, thumbnail=thumbnail)
    await editable.edit(Translation.SAVED_CUSTOM_THUMB_NAIL)


@Client.on_message(filters.private & filters.command(["delthumb", "delete_thumbnail"]))
async def delete_thumbnail(c: Client, m: "types.Message"):
    if not m.from_user:
        return await m.reply_text("Seni tanımıyorum ahbap.")
    if AUTH_CHANNEL:
        fsub = await handle_force_subscribe(c, m)
        if fsub == 400:
            return
    await db.set_thumbnail(m.from_user.id, thumbnail=None)
    await m.reply_text(
        Translation.DEL_ETED_CUSTOM_THUMB_NAIL,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙ Ayarlar", callback_data="Settings")]
        ])
    )


@Client.on_message(filters.private & filters.command(["showthumb", "show_thumbnail"]))
async def show_thumbnail(c: Client, m: "types.Message"):
    if not m.from_user:
        return await m.reply_text("Seni tanımıyorum ahbap.")
    if AUTH_CHANNEL:
        fsub = await handle_force_subscribe(c, m)
        if fsub == 400:
            return
    thumbnail = await db.get_thumbnail(m.from_user.id)
    if thumbnail is not None:
        await c.send_photo(
            chat_id=m.chat.id,
            photo=thumbnail,
            caption=f"**Ayarlı Thumbnail.**",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🗑️ Sil", callback_data="deleteThumbnail")]]
            ),
            reply_to_message_id=m.id)
    else:
        await m.reply_text(text=f"**Thumbnail Bulunamadı.**")
