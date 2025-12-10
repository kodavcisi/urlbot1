import asyncio

from config import LOGGER, PASS
from database.database import db

from pyrogram.emoji import *
from pyrogram.types import ForceReply
from pyrogram import types, errors, filters
from pyrogram.enums import MessageEntityType


async def Settings(m: "types.Message"):
    usr_id = m.chat.id
    is_command = m.entities[0].type is MessageEntityType.BOT_COMMAND

    if is_command:
        message = await m.reply_text('**İşleniyor..**', reply_to_message_id=m.id, quote=True)
        message = message.edit
    else:
        message = m.edit

    user_data = await db.get_user_data(usr_id)

    if not user_data:
        await message("Verileriniz veritabanından alınamadı!")
        return

    upload_as_doc = user_data.get("upload_as_doc", False)
    thumbnail = user_data.get("thumbnail", None)
    # generate_sample_video = user_data.get("generate_sample_video", False)
    generate_ss = user_data.get("generate_ss", False)
    get_notif = user_data.get("notif", False)
    get_caption = user_data.get("caption", False)
    get_aria2 = user_data.get("aria2", False)

    buttons_markup = [
        [types.InlineKeyboardButton(f"{'🔔' if get_notif else '🔕'} Bildirimler",
                                    callback_data="notifon")],
        [types.InlineKeyboardButton(f"{'🗃️ Dosya' if upload_as_doc else '🎥 Video'} Modu ✅",
                                    callback_data="triggerUploadMode")],
        [types.InlineKeyboardButton(f"📚 Kütüphane: {'aria2' if get_aria2 else 'aiohttp'}",
                                    callback_data="aria2")],
        # [types.InlineKeyboardButton(f"🎞 Kısa Video Oluştur {'✅' if generate_sample_video else '❎'}",
        # callback_data="triggerGenSample")],
        [types.InlineKeyboardButton(f"📜 Video Açıklaması {'✅' if get_caption else '❌'}",
                                    callback_data="setCaption")],
        [types.InlineKeyboardButton(f"📸 Ekran Görüntüsü Al {'✅' if generate_ss else '❌'}",
                                    callback_data="triggerGenSS")],
        [types.InlineKeyboardButton("🎛 Filtreler", callback_data="blockFileExtensions")],
        [types.InlineKeyboardButton(f"🌃 Thumbnail {'Değiştir' if thumbnail else 'Ayarla'}",
                                    callback_data="setThumbnail")]
    ]
    if thumbnail:
        buttons_markup.append([types.InlineKeyboardButton("🌆 Thumbnail Göster",
                                                          callback_data="showThumbnail")])

    buttons_markup.append([types.InlineKeyboardButton(f"🛠 Ayarları Sıfırla", callback_data="reset")])
    buttons_markup.append([types.InlineKeyboardButton(f"🔙 Geri",
                                                      callback_data="home"),
                           types.InlineKeyboardButton(f"✖ Kapat",
                                                      callback_data="close")
                           ])

    try:
        await message(
            text="**⚙ Bot Ayarları**",
            reply_markup=types.InlineKeyboardMarkup(buttons_markup),
            disable_web_page_preview=True
        )
    except errors.MessageNotModified:
        pass
    except errors.FloodWait as e:
        await asyncio.sleep(e.value)
        await message("Spam Yapıyorsunuz!")
    except Exception as err:
        LOGGER.error(err)


async def Filters(cb: types.CallbackQuery):
    get_data = await db.get_blocked_exts(cb.message.chat.id)
    markup = [[types.InlineKeyboardButton(f"webm {'✅' if ('webm' in get_data) else '❌'}",
                                          callback_data="set_filter_webm")],
              [types.InlineKeyboardButton(f"mhtml {'✅' if ('mhtml' in get_data) else '❌'}",
                                          callback_data="set_filter_mhtml")],
              [types.InlineKeyboardButton(f"3gp {'✅' if ('3gp' in get_data) else '❌'}",
                                          callback_data="set_filter_3gp")],
              [types.InlineKeyboardButton(f"m4a {'✅' if ('m4a' in get_data) else '❌'}",
                                          callback_data="set_filter_m4a")],
              [types.InlineKeyboardButton(f"mp4 {'✅' if ('mp4' in get_data) else '❌'}",
                                          callback_data="set_filter_mp4")],
              [types.InlineKeyboardButton(f"mkv {'✅' if ('mkv' in get_data) else '❌'}",
                                          callback_data="set_filter_mkv")]]
    if get_data is not None:
        markup.append([types.InlineKeyboardButton("♻ Filtre Sıfırla", callback_data="set_filter_default")])

    markup.append([types.InlineKeyboardButton(f"🔙 Geri",
                                              callback_data="Settings"),
                   types.InlineKeyboardButton(f"✖ Kapat",
                                              callback_data="close")
                   ])

    try:
        await cb.message.edit(
            text=f"**Filtre Ayarları:**",
            disable_web_page_preview=True,
            reply_markup=types.InlineKeyboardMarkup(markup)
        )
    except errors.FloodWait as e:
        await asyncio.sleep(e.value)
        pass
    except errors.MessageNotModified:
        pass


async def Login(c, m: "types.Message"):
    usr_id = m.chat.id
    if PASS:
        try:
            try:
                msg = await m.reply(
                    "**Şifreyi gönderin.**\n\n__(İşlemi iptal etmek için /iptal komutunu kullanabilirsiniz.)__",
                    reply_markup=ForceReply(True))
                _text = await c.listen(usr_id, filters=filters.text, timeout=90)
                if _text.text:
                    textp = _text.text.upper()
                    if textp == "/IPTAL":
                        await m.delete(True)
                        await msg.delete(True)
                        await msg.reply("__İşlem Başarıyla İptal Edildi.__")
                        return
                else:
                    return
            except TimeoutError:
                await m.reply("__Şifre için daha fazla bekleyemem, tekrar dene.__")
                return
            if textp == PASS:
                await db.add_user_pass(usr_id, textp)
                msg_text = f"__Evet! Başarıyla Oturum Açıldı.__ {FACE_SAVORING_FOOD} /start"
            else:
                msg_text = "__Yanlış şifre, tekrar deneyin. /login__"
            await m.reply(msg_text)
        except errors.FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            LOGGER.error(e)
        await m.delete(True)
        await msg.delete(True)
