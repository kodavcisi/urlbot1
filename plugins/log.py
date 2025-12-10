from config import OWNER_ID
from pyrogram.types import Message
from pyrogram import Client, filters
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('log.txt'), logging.StreamHandler()],
                    level=logging.INFO)
LOGGER = logging.getLogger(__name__)


@Client.on_message(filters.command('log'))
async def log_handler(c: Client, m: Message):
    with open('log.txt', 'rb') as f:
        try:
            await c.send_document(document=f,
                                  file_name=f.name, reply_to_message_id=m.id,
                                  chat_id=m.chat.id, caption=f.name)
        except Exception as e:
            await m.reply_text(str(e))
