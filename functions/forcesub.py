import logging
import asyncio

from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta

from database.database import db
from functions.settings import Login
from database.add import add_user_to_database
from translation import Translation
from config import AUTH_CHANNEL, PASS


logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)


async def handle_force_subscribe(c: Client, m: Message):
    user_id = m.from_user.id
    start_time = datetime.now()
    await add_user_to_database(c, m)
    try:
        user = await c.get_chat_member(AUTH_CHANNEL, user_id)
        if user.status == ChatMemberStatus.BANNED:
            await c.delete_messages(
                chat_id=m.chat.id,
                message_ids=m.id,
                revoke=True
            )
            return 400
    except UserNotParticipant:
        if PASS:
            check_pass = await db.get_user_pass(m.chat.id)
            if check_pass is None:
                await m.reply_text(
                    text=Translation.LOGIN_TXT,
                    reply_markup=Translation.LOGIN_BUTTON,
                    reply_to_message_id=m.id,
                )
                return 400
            elif check_pass != PASS:
                await db.delete_user(m.chat.id)
                await Login(c, m)
                return 400
        date = start_time + timedelta(seconds=120)
        try:
            invite_link = await c.create_chat_invite_link(int(AUTH_CHANNEL), expire_date=date, member_limit=1)
        except ChatAdminRequired:
            LOGGER.error("Bot'un Forcesub kanalında yönetici olduğundan emin olun.")
            return
        btn = [
            [
                InlineKeyboardButton(
                    Translation.BUTTON_TEXT, url=invite_link.invite_link
                )
            ]
        ]
        await c.send_message(
            chat_id=user_id,
            text=Translation.FORCE_TXT,
            reply_markup=InlineKeyboardMarkup(btn),
            reply_to_message_id=m.id,
        )
        return 400
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return 400
    except Exception as e:
        await c.send_message(
            chat_id=user_id,
            text="Bir şeyler ters gitti.",
            disable_web_page_preview=True,
            reply_to_message_id=m.id,
        )
        LOGGER.info(e)
        return 400