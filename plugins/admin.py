import shutil
import psutil
import math

import requests
import heroku3

from config import HEROKU_APP_NAME, HEROKU_API_KEY

from pyrogram import filters
from pyrogram.types import (
    Message
)
from config import OWNER_ID
from pyrogram import Client
from database.database import db
from functions.progress import humanbytes
from plugins.broadcast import broadcast_handler


@Client.on_message(filters.command("status"))
async def status_handler(_, m: Message):
    msg = await m.reply_text(text="`İşleniyor...`")
    heroku_api = "https://api.heroku.com"
    total, used, free = shutil.disk_usage(".")
    total = humanbytes(total)
    used = humanbytes(used)
    free = humanbytes(free)
    cpu_usage = psutil.cpu_percent()
    ram_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage('/').percent
    total_users = await db.total_users_count()
    text = f"**Toplam Disk Alanı:** `{total}` \n"
    text += f"**Kullanılan Alan:** `{used}({disk_usage}%)` \n"
    text += f"**Boş Alan:** `{free}` \n"
    text += f"**CPU Kullanımı:** `{cpu_usage}%` \n"
    text += f"**RAM Kullanımı:** `{ram_usage}%`\n\n"
    text += f"**DB'deki Toplam Kullanıcılar:** `{total_users}`"
    try:
        if HEROKU_API_KEY is not None and HEROKU_APP_NAME is not None:
            Heroku = heroku3.from_key(HEROKU_API_KEY)
            app = Heroku.app(HEROKU_APP_NAME)
        else:
            await msg.edit(
                text=text
            )
            return

        useragent = (
            "Mozilla/5.0 (Linux; Android 10; SM-G975F) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/81.0.4044.117 Mobile Safari/537.36"
        )
        user_id = Heroku.account().id
        headers = {
            "User-Agent": useragent,
            "Authorization": f"Bearer {HEROKU_API_KEY}",
            "Accept": "application/vnd.heroku+json; version=3.account-quotas",
        }
        path = "/accounts/" + user_id + "/actions/get-quota"
        session = requests.Session()
        with session as ses:
            with ses.get(heroku_api + path, headers=headers) as r:
                result = r.json()
                """Account Quota."""
                quota = result["account_quota"]
                quota_used = result["quota_used"]
                quota_remain = quota - quota_used
                quota_percent = math.floor(quota_remain / quota * 100)
                minutes_remain = quota_remain / 60
                hours = math.floor(minutes_remain / 60)
                minutes = math.floor(minutes_remain % 60)
                day = math.floor(hours / 24)

                """App Quota."""
                Apps = result["apps"]
                for apps in Apps:
                    if apps.get("app_uuid") == app.id:
                        AppQuotaUsed = apps.get("quota_used") / 60
                        AppPercent = math.floor(apps.get("quota_used") * 100 / quota)
                        break
                else:
                    AppQuotaUsed = 0
                    AppPercent = 0

                AppHours = math.floor(AppQuotaUsed / 60)
                AppMinutes = math.floor(AppQuotaUsed % 60)

                await msg.edit(
                    f"**ℹ️ Dyno Kullanımı**\n\n`🟢 {app.name}`:\n"
                    f"• `{AppHours}` **Saat ve** `{AppMinutes}` **Dakika\n💯: {AppPercent}%**\n\n"
                    "**⚠️ Kalan Dyno**\n"
                    f"• `{hours}` **Saat ve** `{minutes}` **Dakika\n💯: {quota_percent}%**\n\n"
                    "**❌ Tahmini Kalan Süre**\n"
                    f"• `{day}` **Gün**" + '\n\n' + text
                )
    except Exception as e:
        await msg.edit(f"**Error:** `{e}`")


@Client.on_message(filters.command("reset") & filters.user(OWNER_ID))
async def restart(_, m: Message):
    restart_msg = await m.reply_text(text="`İşleniyor...`")
    await restart_msg.edit("`Yeniden başlatılıyor! Lütfen bekle...`")
    try:
        if HEROKU_API_KEY is not None and HEROKU_APP_NAME is not None:
            heroku_conn = heroku3.from_key(HEROKU_API_KEY)
            server = heroku_conn.app(HEROKU_APP_NAME)
            server.restart()
        else:
            await restart_msg.edit("`Heroku değişkenlerini ekleyin.`")
    except Exception as e:
        await restart_msg.edit(f"**Error:** `{e}`")
