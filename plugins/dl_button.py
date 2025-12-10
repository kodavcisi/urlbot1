import os
import time
import asyncio
import aiohttp

from datetime import datetime
from database.database import db
from translation import Translation
from pyrogram.enums import ChatAction, MessageEntityType

from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from functions.progress import progress_for_pyrogram, humanbytes, TimeFormatter
from functions.ffmpeg import VideoThumb, VideoMetaData, VMMetaData, DocumentThumb, AudioMetaData
from config import DOWNLOAD_LOCATION, TG_MAX_FILE_SIZE, LOG_CHANNEL, PROCESS_MAX_TIMEOUT, CHUNK_SIZE, PROMO

import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('log.txt'), logging.StreamHandler()],
                    level=logging.INFO)
LOGGER = logging.getLogger(__name__)


async def ddl_call_back(bot, update):
    LOGGER.info(update)
    cb_data = update.data
    tg_send_type, yt_dlp_format, yt_dlp_ext, random = cb_data.split("=")

    dtime = str(time.time())
    message = update.message
    user_id = update.from_user.id
    chat_id = message.chat.id

    thumb_image_path = DOWNLOAD_LOCATION + \
                       "/" + str(user_id) + f'{random}' + ".jpg"

    yt_dlp_url = message.reply_to_message.text
    custom_file_name = os.path.basename(yt_dlp_url[:100])

    if "|" in yt_dlp_url:
        url_parts = yt_dlp_url.split("|")
        if len(url_parts) == 2:
            yt_dlp_url = url_parts[0]
            custom_file_name = url_parts[1]
            if len(custom_file_name) > 60:
                await update.edit_message_text(
                    Translation.IFLONG_FILE_NAME.format(
                        alimit="64",
                        num=len(custom_file_name)
                    )
                )
                return
        else:
            for entity in message.reply_to_message.entities:
                if entity.type == MessageEntityType.TEXT_LINK:
                    yt_dlp_url = entity.url
                elif entity.type == MessageEntityType.URL:
                    o = entity.offset
                    l = entity.length
                    yt_dlp_url = yt_dlp_url[o:o + l]
        if yt_dlp_url is not None:
            yt_dlp_url = yt_dlp_url.strip()
        if custom_file_name is not None:
            custom_file_name = custom_file_name.strip()
        # https://stackoverflow.com/a/761825/4723940
        LOGGER.info(yt_dlp_url)
        LOGGER.info(custom_file_name)
    else:
        for entity in message.reply_to_message.entities:
            if entity.type == MessageEntityType.TEXT_LINK:
                yt_dlp_url = entity.url
            elif entity.type == MessageEntityType.URL:
                o = entity.offset
                l = entity.length
                yt_dlp_url = yt_dlp_url[o:o + l]
    start = datetime.now()
    await bot.edit_message_text(
        text=Translation.DOWNLOAD_START.format(custom_file_name),
        chat_id=chat_id,
        message_id=message.id
    )
    tmp_directory_for_each_user = os.path.join(
        DOWNLOAD_LOCATION,
        str(user_id),
        dtime
    )
    if not os.path.isdir(tmp_directory_for_each_user):
        os.makedirs(tmp_directory_for_each_user)
    download_directory = os.path.join(tmp_directory_for_each_user, custom_file_name)
    async with aiohttp.ClientSession() as session:
        c_time = time.time()
        try:
            await download_coroutine(
                bot,
                session,
                yt_dlp_url,
                download_directory,
                chat_id,
                message.id,
                c_time
            )
        except asyncio.TimeoutError:
            await bot.edit_message_text(
                text=Translation.SLOW_URL_DECED,
                chat_id=chat_id,
                message_id=message.id
            )
            return False
    if os.path.exists(download_directory):
        end_one = datetime.now()
        await bot.edit_message_text(
            text=Translation.UPLOAD_START,
            chat_id=chat_id,
            message_id=message.id
        )
        try:
            file_size = os.stat(download_directory).st_size
        except FileNotFoundError as exc:
            download_directory = os.path.splitext(download_directory)[0] + "." + "mkv"
            # https://stackoverflow.com/a/678242/4723940
            file_size = os.stat(download_directory).st_size
        if file_size > TG_MAX_FILE_SIZE:
            await bot.edit_message_text(
                chat_id=chat_id,
                text=Translation.RCHD_TG_API_LIMIT,
                message_id=message.id
            )
        else:

            start_time = time.time()
            user = await bot.get_me()

            if PROMO:
                btn = [[
                    InlineKeyboardButton(f"Uploaded By {user.first_name}", url=f"tg://user?id={user.id}")
                ]]
                reply_markup = InlineKeyboardMarkup(btn)
            else:
                reply_markup = False

            # try to upload file
            try:
                if tg_send_type == "audio":
                    duration = await AudioMetaData(download_directory)
                    thumbnail = await DocumentThumb(bot, update)
                    await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_AUDIO)
                    copy = await bot.send_audio(
                        chat_id=chat_id,
                        audio=download_directory,
                        caption=custom_file_name,
                        duration=duration,
                        thumb=thumbnail,
                        reply_to_message_id=message.reply_to_message.id,
                        # reply_markup=reply_markup,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            Translation.UPLOAD_START,
                            message,
                            start_time
                        )
                    )
                elif (await db.get_upload_as_doc(user_id)) is True:
                    thumbnail = await DocumentThumb(bot, update)
                    await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
                    copy = await bot.send_document(
                        chat_id=chat_id,
                        document=download_directory,
                        thumb=thumbnail,
                        caption=custom_file_name,
                        reply_to_message_id=message.reply_to_message.id,
                        reply_markup=reply_markup,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            Translation.UPLOAD_START,
                            message,
                            start_time
                        )
                    )
                else:
                    width, height, duration = await VideoMetaData(download_directory)
                    thumb_image_path = await VideoThumb(bot, update, duration, download_directory, random)
                    await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_VIDEO)
                    copy = await bot.send_video(
                        chat_id=chat_id,
                        video=download_directory,
                        caption=custom_file_name,
                        duration=duration,
                        width=width,
                        height=height,
                        supports_streaming=True,
                        thumb=thumb_image_path,
                        reply_to_message_id=message.reply_to_message.id,
                        reply_markup=reply_markup,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            Translation.UPLOAD_START,
                            message,
                            start_time
                        )
                    )
                if LOG_CHANNEL:
                    await copy.copy(LOG_CHANNEL)
            except FloodWait as e:
                print(f"Sleep of {e.value} required by FloodWait ...")
                time.sleep(e.value)
            except MessageNotModified:
                pass

            end_two = datetime.now()
            try:
                os.remove(download_directory)
                os.remove(thumb_image_path)
            except:
                pass
            time_taken_for_download = (end_one - start).seconds
            time_taken_for_upload = (end_two - end_one).seconds
            await bot.edit_message_text(
                text=Translation.AFTER_SUCCESSFUL_UPLOAD_MSG_WITH_TS.format(time_taken_for_download,
                                                                            time_taken_for_upload),
                chat_id=chat_id,
                message_id=message.id,
                disable_web_page_preview=True
            )
    else:
        await bot.edit_message_text(
            text=Translation.NO_VOID_FORMAT_FOUND.format("Incorrect Link"),
            chat_id=chat_id,
            message_id=message.id,
            disable_web_page_preview=True
        )


async def download_coroutine(bot, session, url, file_name, chat_id, message_id, start):
    downloaded = 0
    display_message = ""
    async with session.get(url, timeout=PROCESS_MAX_TIMEOUT) as response:
        total_length = int(response.headers["Content-Length"])
        content_type = response.headers["Content-Type"]
        if "text" in content_type and total_length < 500:
            return await response.release()
        await bot.edit_message_text(
            chat_id,
            message_id,
            text="""İndirme Başlatılıyor..
Boyut: {}""".format(humanbytes(total_length))
        )
        with open(file_name, "wb") as f_handle:
            while True:
                chunk = await response.content.read(CHUNK_SIZE)
                if not chunk:
                    break
                f_handle.write(chunk)
                downloaded += CHUNK_SIZE
                now = time.time()
                diff = now - start
                if round(diff % 5.00) == 0 or downloaded == total_length:
                    percentage = downloaded * 100 / total_length
                    speed = downloaded / diff
                    elapsed_time = round(diff) * 1000
                    time_to_completion = round(
                        (total_length - downloaded) / speed) * 1000
                    estimated_total_time = elapsed_time + time_to_completion
                    try:
                        current_message = """**İndirme Durumu**
Boyut: {}
İndirilen: {}
Süre: {}""".format(
                            humanbytes(total_length),
                            humanbytes(downloaded),
                            TimeFormatter(estimated_total_time)
                        )
                        if current_message != display_message:
                            await bot.edit_message_text(
                                chat_id,
                                message_id,
                                text=current_message
                            )
                            display_message = current_message
                    except Exception as e:
                        LOGGER.info(str(e))
                        pass
        return await response.release()
