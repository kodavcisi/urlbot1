from pyrogram import Client, filters
from sys import executable
import os
import asyncio

@Client.on_message(filters.command('onbellek'))
async def onbellek(bot, message):
    try:
        msg = await message.reply_text("Önbellek Siliniyor..") 
        try:
            caching.clear_cache()
        except Exception as e:
            await msg.edit(f"Önbellek Silinmedi..\n{e}")
    except Exception as e:
        await message.reply_text(e)
