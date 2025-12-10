import os
from pyrogram import Client, filters

@Client.on_message(filters.command('diskx'))
async def disksil(bot, message):
    try:
        silkomut = "rm -rf DOWNLOADS"
        try:
            os.system(silkomut)
            await message.reply_text("Dosyalar Silindi..")
        except Exception as e:
            await message.reply_text("silemedim") 
        downloadskomut = "mkdir DOWNLOADS" 
        try:
            os.system(downloadskomut)
            await message.reply_text("DOWNLOADS klasörü tekrar oluşturuldu") 
        except Exception as e:
            await message.reply_text(e)
    except Exception as e:
        await message.reply_text(e)

@Client.on_message(filters.command('diske'))
async def diskesil(bot, message):
    try:
        silkomut = "rm -rf encodes"
        try:
            os.system(silkomut)
            await message.reply_text("Dosyalar Silindi..")
        except Exception as e:
            await message.reply_text("silemedim") 
        downloadskomut = "mkdir encodes" 
        try:
            os.system(downloadskomut)
            await message.reply_text("downloads klasörü tekrar oluşturuldu") 
        except Exception as e:
            await message.reply_text(e)
    except Exception as e:
        await message.reply_text(e)
