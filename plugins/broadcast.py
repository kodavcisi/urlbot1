import logging
from pyrogram import Client, filters
import datetime
import time
from database.database import db
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid, UserNotParticipant
from pyrogram.enums import ChatMemberStatus
from config import OWNER_ID, AUTH_CHANNEL, BROADCAST_AS_COPY
import asyncio

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def broadcast_messages(bot, user_id, message):
    if AUTH_CHANNEL:
        try:
            user = await bot.get_chat_member(AUTH_CHANNEL, user_id)
        except UserNotParticipant:
            return False, "Blocked"
        except Exception as e:
            logging.exception(e)
        else:
            if user.status == ChatMemberStatus.BANNED:
                return False, "Blocked"
    try:
        if BROADCAST_AS_COPY is True:
            await message.copy(chat_id=user_id, protect_content=True)
        elif BROADCAST_AS_COPY is False:
            await message.forward(chat_id=user_id)
        return True, "Succes"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await broadcast_messages(bot, user_id, message)
    except InputUserDeactivated:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id} - Hesap silindiği için veritabanından kaldırıldı.")
        return False, "Deleted"
    except UserIsBlocked:
        logging.info(f"{user_id} - Bot'u engelledi.")
        return False, "Blocked"
    except PeerIdInvalid:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id} - Kimliği geçersiz")
        return False, "Error"
    except Exception as e:
        return False, "Error"


@Client.on_message(filters.command(["broadcast", "yay"]) & filters.user(OWNER_ID) & filters.reply)
async def broadcast_handler(bot, message):
    message = message.reply_to_message
    await message.reply(
        text='__Bunu yayınlamak istediğinizden emin misiniz...?__',
        quote=True,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(text='Evet (Üyelere)', callback_data='bdcast#notifon')],
                [InlineKeyboardButton(text='Evet (Herkese)', callback_data='bdcast#all')],
                [InlineKeyboardButton(text='Hayır', callback_data='close_data')]
            ]
        )
    )
    return


@Client.on_callback_query(filters.user(OWNER_ID) & filters.regex(r'^bdcast+.*$'))
async def broadcast_confrm(bot, query):
    await query.answer()
    bdcast_type = query.data.split("#")[1]
    print(bdcast_type)
    message = query.message
    b_msg = message.reply_to_message
    if not b_msg:
        await query.answer(
            text='Mesaj bulunamadı.',
            show_alert=True
        )
        await message.delete()
        return
    total_users = await db.total_users_count()
    if bdcast_type == 'notifon':
        users = await db.get_all_notif_user()
    elif bdcast_type == 'all':
        users = await db.get_all_users()
    await message.edit(text='Mesajı yayınlıyorum..', reply_markup=None)
    start_time = time.time()
    done = 0
    blocked = 0
    deleted = 0
    failed = 0
    success = 0
    async for user in users:
        pti, sh = await broadcast_messages(bot, int(user['id']), b_msg)
        if pti:
            success += 1
        elif not pti:
            if sh == "Blocked":
                blocked += 1
            elif sh == "Deleted":
                deleted += 1
            elif sh == "Error":
                failed += 1
        done += 1
        await asyncio.sleep(2)
        if not done % 20:
            await message.edit(
                f"Yayın devam ediyor:\n\n"
                f"Toplam Kullanıcılar: {total_users}\n"
                f"Tamamlanan: {done} / {total_users}\n"
                f"Başarılı: {success}\n"
                f"Engelleyen: {blocked}\n"
                f"Silinen: {deleted}")
    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    await message.edit(
        f"Yayın Tamamlandı:\n"
        f"{completed_in} saniye içinde tamamlandı.\n\n"
        f"Toplam Kullanıcılar: {total_users}\n"
        f"Tamamlanan: {done} / {total_users}\n"
        f"Başarılı: {success}\n"
        f"Engelleyen: {blocked}\n"
        f"Silinen: {deleted}")
