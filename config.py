import re
import os
from os import environ
from dotenv import load_dotenv
from pyrogram import Client, __version__
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client, enums
import string
import random
import re
import os
from os import environ
from dotenv import load_dotenv
import time, requests
from pyrogram import __version__
from platform import python_version

import logging
import logging.config

import logging

logging.basicConfig(
    format='%(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('log.txt'),
              logging.StreamHandler()],
    level=logging.INFO
)

LOGGER = logging

if os.path.exists('config.env'):
    load_dotenv('config.env')

id_pattern = re.compile(r'^.\d+$') 

def is_enabled(value:str):
    return bool(str(value).lower() in ["true", "1", "e", "d"])

def get_config_from_url():
    CONFIG_FILE_URL = os.environ.get('CONFIG_FILE_URL', None)
    try:
        if len(CONFIG_FILE_URL) == 0: raise TypeError
        try:
            res = requests.get(CONFIG_FILE_URL)
            if res.status_code == 200:
                LOGGER.info("Config uzaktan alındı. Status 200.")
                with open('config.env', 'wb+') as f:
                    f.write(res.content)
                    f.close()
            else:
                LOGGER.error(f"Failed to download config.env {res.status_code}")
        except Exception as e:
            LOGGER.error(f"CONFIG_FILE_URL: {e}")
    except TypeError:
        pass

get_config_from_url()
if os.path.exists('config.env'): load_dotenv('config.env')

id_pattern = re.compile(r'^.\d+$')

LOGGER.info("--- CONFIGS STARTS HERE ---")


# get a token from @BotFather and A Premium user Sessıon
BOT_TOKEN = environ.get("BOT_TOKEN", "")

# Where files larger than 2 GB will go
PRE_LOG = environ.get("PRE_LOG", "") 

# The Telegram API things
# Get these values from my.telegram.org
APP_ID = int(environ.get("APP_ID", 1234))
API_HASH = environ.get("API_HASH", "")
MOLY_LINKLERI = list(set(x for x in environ.get("MOLY_LINKLERI", ".cloud").split()))
OWNER_ID = int(environ.get("OWNER_ID", "1276627253"))
STRING_SESSION = environ.get("STRING_SESSION", "")
if len(STRING_SESSION) != 0:
    try:
        userbot = Client(name='userbot', api_id=APP_ID, api_hash=API_HASH, session_string=STRING_SESSION, parse_mode=enums.ParseMode.HTML)
        userbot.start()
        me = userbot.get_me()
        userbot.send_message(me.id, f"Userbot Bașlatıldı..\n\nPremium Durumu: {me.is_premium}\nAd: {me.first_name}\nid: {me.id}")
    except Exception as e:
        LOGGER.info(e)

# the download location, where the HTTP Server runs
DOWNLOAD_LOCATION = "./DOWNLOADS"

# Update channel for Force Subscribe
auth_channel = environ.get('AUTH_CHANNEL')
auth_grp = environ.get('AUTH_GROUP')
AUTH_CHANNEL = int(auth_channel) if auth_channel and id_pattern.search(auth_channel) else None

# Broadcast
BROADCAST_AS_COPY = bool(environ.get("BROADCAST_AS_COPY", True))
# Log Channel ID
log_channel = environ.get('LOG_CHANNEL')
LOG_CHANNEL = int(log_channel) if log_channel else None

# Telegram maximum file upload size
MAX_FILE_SIZE = 50000000
TG_MAX_FILE_SIZE = 4200000000

# chunk size that should be used with requests
CHUNK_SIZE = int(environ.get("CHUNK_SIZE", 128))

# default thumbnail to be used in the videos
DEF_THUMB_NAIL_VID_S = environ.get("DEF_THUMB_NAIL_VID_S", "")

# proxy for accessing youtube-dl in GeoRestricted Areas
# Get your own proxy from https://github.com/rg3/youtube-dl/issues/1091#issuecomment-230163061
HTTP_PROXY = environ.get("HTTP_PROXY", "")

# maximum message length in Telegram
MAX_MESSAGE_LENGTH = 4096

# set timeout for subprocess
PROCESS_MAX_TIMEOUT = 3600

# watermark file
DEF_WATER_MARK_FILE = ""

BOT_PM = True

# your telegram id
# database session name, example: urluploader
SESSION_NAME = environ.get("SESSION_NAME", "")

# database uri (mongodb)
DATABASE_URL = environ.get("DATABASE_URL", "")

# Heroku
HEROKU_APP_NAME = environ.get('HEROKU_APP_NAME', None)
HEROKU_API_KEY = environ.get('HEROKU_API_KEY', None)

# Advertisement
PROMO = str(environ.get("PROMO", "True")).lower() == 'true'

password = environ.get('PASS')
PASS = password.upper() if password else None

# Other
SEND_LOGS_WHEN_DYING = str(environ.get("SEND_LOGS_WHEN_DYING", "True")).lower() == 'true'

# Pixeldrain Settings
PIXELDRAIN_USE_PROXY = str(environ.get("PIXELDRAIN_USE_PROXY", "True")).lower() == 'true'
PIXELDRAIN_PROXY_LIST = environ.get("PIXELDRAIN_PROXY_LIST", "").split(",") if environ.get("PIXELDRAIN_PROXY_LIST", "") else []
PIXELDRAIN_AUTO_PROXY = str(environ.get("PIXELDRAIN_AUTO_PROXY", "True")).lower() == 'true'
PIXELDRAIN_ARIA2C_CONNECTIONS = int(environ.get("PIXELDRAIN_ARIA2C_CONNECTIONS", "16"))
