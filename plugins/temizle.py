from pyrogram import Client, filters
import os
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
import time
import logging 
from sys import executable

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('log.txt'), logging.StreamHandler()],
                    level=logging.INFO)
LOGGER = logging.getLogger(__name__)

async def dosyasil(dosyaYolu, message, silinecekler):
    for dosya in os.listdir(dosyaYolu):
        text = dosyaYolu
        dosyaYolu = os.path.join(text, dosya)
        try:
            if os.path.isfile(dosyaYolu):
                os.remove(dosyaYolu)
                textim += f"{dosyaYolu}\n"
            elif os.path.isdir(dosyaYolu):
                for i in os.listdir(dosyaYolu):
                    text = f"{dosyaYolu}"
                    dosyaYol = os.path.join(text, i)
                    await message.reply_text(dosyaYol)
                    if os.path.isfile(dosyaYol):
                        textim = f"{dosyaYol}"
                        silinecekler.append(textim)
                    elif os.path.isdir(dosyaYol):
                        for i in os.listdir(dosyaYol):
                            text = f"{dosyaYol}"
                            dosyaYolu = os.path.join(text, i)
                            if os.path.isfile(dosyaYolu):
                                textim = f"{dosyaYolu}"
                                silinecekler.append(textim)
                            else:
                                await message.reply_text("Silemiyom aq..")
        except Exception as hata:
            await message.reply_text(hata)

@Client.on_message(filters.command('diskiy'))
async def deldirecttory(bot, message):
    try:
        silinecekler = []
        text = "DOWNLOADS"
        msg = await message.reply_text("`Siliyorum..`") 
        for dosya in os.listdir(text):
            dosyaYolu = os.path.join(text, dosya)
            try:
                if os.path.isfile(dosyaYolu):
                    textim = f"{dosyaYolu}"
                    silinecekler.append(textim)
                elif os.path.isdir(dosyaYolu):
                    dosyaYolu = await dosyasil(dosyaYolu, message, silinecekler)
            except Exception as hata:
                await message.reply_text(hata)
        for sil in silinecekler:
            await message.reply_text(sil)
            os.remove(sil)
        await msg.edit(f"Dosyaları Başarıyla Silindi..")
        await message.reply_text("Şimdi Botu Resetliyorum..")
        try:
            os.execl(executable, executable, "bot.py")
        except Exception as e:
            await message.reply_text(e)
    except Exception as e:
        await message.reply_text(e) 

@Client.on_message(filters.command('get'))
async def get_directoryyy(bot, message):
    try:
        text = message.text.split(" ", 1)
        if len(text) < 2:
            await bot.send_message(message.chat.id, "Hatalı Kullanım :/ Doğru Kullanım Şu Şekilde:\n\n`/get downloads`") 
            return
        directory = text[1]
        if 1 == 1:
            if not os.listdir(directory):
                await message.reply(f"{directory} klasörünüz boş")
            else:
                dsy = ""
                say = 0
                for files in os.listdir(directory):
                    say += 1
                    dsy = dsy + "  " + str(say) + "-) " + f"`{directory}/{files}`" + '\n'
                await message.reply_text(
                    f"{directory} Klasöründeki Dosyalar." + "\n\n" + dsy + "\n" + str(
                        say) + " Tane Dosya Var.")
    except Exception as e:
        await message.reply_text(e)
