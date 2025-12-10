import logging
from database.database import db
from pyrogram import Client
from pyrogram.types import Message
from config import LOG_CHANNEL
from translation import Translation

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('log.txt'), logging.StreamHandler()],
                    level=logging.INFO)
LOGGER = logging.getLogger(__name__)


async def add_user_to_database(c: Client, cmd: Message):
    bot = await c.get_me()
    BOT_USERNAME = bot.username
    user = cmd.from_user
    dc_id = user.dc_id or "[DC'si Yok]"
    username = user.username or "Yok"
    if not await db.is_user_exist(user.id):
        if LOG_CHANNEL:
            await c.send_message(LOG_CHANNEL,
                                 Translation.LOG_TEXT_P.format(user.id,
                                                               user.mention,
                                                               user.language_code,
                                                               username,
                                                               dc_id,
                                                               BOT_USERNAME
                                                               ))
        else:
            LOGGER.info(f"#YeniKullanıcı :- Ad : {user.first_name} ID : {user.id}")
        await db.add_user(user.id)
