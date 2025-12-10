# written by :d
import pyrogram
import time
from pyrogram import filters
from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from functions.utils import ReadableTime
from pyromod import listen
import logging
import os
import time

botStartTime = time.time()

@Client.on_message(filters.private & filters.command(["yas", "time"]))
async def time(c: Client, m: "types.Message"):
    m.reply_text(f"yaşım: {ReadableTime(time.time() - botStartTime)}")
