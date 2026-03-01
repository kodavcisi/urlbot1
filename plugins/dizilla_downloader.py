"""
Dizilla.to episode indirme modülü.

Akış:
1. dizilla.to linki algılanır → Playwright ile m3u8 URL + headerlar çıkarılır.
2. yt-dlp -F ile format listesi alınır → kullanıcıya kalite butonları gösterilir.
3. Kullanıcı kaliteyi seçer → audio track listesi alınır → ses butonları gösterilir.
4. Kullanıcı sesi seçer → yt-dlp ile indirme başlar, progress Telegram'a yansıtılır.
5. İndirme biter → ffmpeg ile AAC stereo 256k + volume=1.2 encode yapılır.
6. Telegram'a video olarak yüklenir (supports_streaming=True).
7. Geçici dosyalar silinir.
"""

import asyncio
import json
import logging
import os
import re
import time

from pyrogram.enums import ChatAction
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import DOWNLOAD_LOCATION, LOG_CHANNEL, TG_MAX_FILE_SIZE
from functions.ffmpeg import DocumentThumb, VideoMetaData
from functions.progress import humanbytes, progress_for_pyrogram

LOGGER = logging.getLogger(__name__)

# ─────────────────────────────── helpers ────────────────────────────────── #

def is_dizilla_url(url: str) -> bool:
    """URL'nin dizilla.to episode linki olup olmadığını döner."""
    return "dizilla.to" in url.lower()


def _safe_delete(*paths: str) -> None:
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


# ─────────────────────────────── extraction ─────────────────────────────── #

async def _extract_m3u8_playwright(episode_url: str) -> dict:
    """
    Playwright ile dizilla.to sayfasından m3u8 URL ve header bilgisini çıkarır.

    Dönen sözlük örneği:
    {
        "m3u8_url": "https://cdn.example.com/master.m3u8",
        "referer": "https://dizilla.to/...",
        "cookie": "...",       # yoksa ""
        "origin": "...",       # yoksa ""
        "user_agent": "...",   # yoksa ""
    }
    Hiç m3u8 bulunamazsa ValueError fırlatır.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError("playwright paketi kurulu değil.") from e

    result = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()

        captured_requests = []

        async def handle_request(req):
            url = req.url
            if "m3u8" in url.lower():
                headers = req.headers
                captured_requests.append({
                    "url": url,
                    "headers": headers,
                })

        page.on("request", handle_request)

        try:
            await page.goto(episode_url, wait_until="networkidle", timeout=60000)
            # İframe varsa bekle
            await page.wait_for_timeout(5000)
            # İframe içindeki networkidle için biraz daha bekle
            frames = page.frames
            for frame in frames:
                if frame != page.main_frame:
                    try:
                        await frame.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
            await page.wait_for_timeout(3000)
        finally:
            await browser.close()

    if not captured_requests:
        raise ValueError(f"m3u8 URL bulunamadı: {episode_url}")

    # En uzun (en muhtemel master) m3u8'i seç
    best = max(captured_requests, key=lambda r: len(r["url"]))
    headers = best["headers"]

    result["m3u8_url"] = best["url"]
    result["referer"] = headers.get("referer", episode_url)
    result["cookie"] = headers.get("cookie", "")
    result["origin"] = headers.get("origin", "")
    result["user_agent"] = headers.get("user-agent", "")

    return result


# ─────────────────── format/audio list via yt-dlp ───────────────────────── #

def _build_ytdlp_base_cmd(info: dict) -> list:
    """info sözlüğündeki referer/cookie/ua/origin ile yt-dlp temel komutunu döner."""
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--no-check-certificate",
        "--impersonate", "chrome",
    ]
    referer = info.get("referer", "")
    if referer:
        cmd += ["--referer", referer]
    cookie = info.get("cookie", "")
    if cookie:
        cmd += ["--add-header", f"Cookie: {cookie}"]
    origin = info.get("origin", "")
    if origin:
        cmd += ["--add-header", f"Origin: {origin}"]
    ua = info.get("user_agent", "")
    if ua:
        cmd += ["--add-header", f"User-Agent: {ua}"]
    return cmd


async def _run_ytdlp_list_formats(info: dict) -> list:
    """
    yt-dlp -J komutu ile format listesini döner (JSON parse edilmiş formats listesi).
    """
    cmd = _build_ytdlp_base_cmd(info) + ["-J", info["m3u8_url"]]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"yt-dlp -J başarısız: {err}")
    data = json.loads(stdout.decode(errors="replace"))
    return data.get("formats", [])


# ────────────────────── state persistence (json) ───────────────────────── #

def _state_path(user_id: int, token: str) -> str:
    return os.path.join(DOWNLOAD_LOCATION, f"dizilla_{user_id}_{token}.json")


def _save_state(user_id: int, token: str, state: dict) -> None:
    os.makedirs(DOWNLOAD_LOCATION, exist_ok=True)
    with open(_state_path(user_id, token), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def _load_state(user_id: int, token: str) -> dict:
    path = _state_path(user_id, token)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _delete_state(user_id: int, token: str) -> None:
    _safe_delete(_state_path(user_id, token))


# ─────────────────────────── entry point ───────────────────────────────── #

async def dizilla_start(bot, update) -> None:
    """
    Dizilla.to URL'si algılandığında `ytdlp_trigger.py` tarafından çağrılır.
    Playwright ile m3u8 çıkarır ve kalite butonlarını gösterir.
    """
    episode_url = update.text.strip()
    user_id = update.from_user.id
    token = str(time.time())

    msg = await update.reply(
        "🎬 Dizilla linki algılandı, video bilgisi alınıyor...",
        disable_web_page_preview=True,
    )

    try:
        await msg.edit("🔍 Playwright ile m3u8 adresi çıkarılıyor...")
        try:
            info = await _extract_m3u8_playwright(episode_url)
        except Exception as e:
            await msg.edit(f"❌ m3u8 çıkarılamadı:\n`{e}`")
            return

        await msg.edit("📋 Format listesi alınıyor (yt-dlp -J)...")
        try:
            formats = await _run_ytdlp_list_formats(info)
        except Exception as e:
            await msg.edit(f"❌ Format listesi alınamadı:\n`{e}`")
            return

        # Yalnızca video formatlarını filtrele (vcodec != none)
        video_formats = [
            f for f in formats
            if f.get("vcodec", "none") not in ("none", None, "")
               and f.get("acodec", "none") == "none"  # video-only tercih
        ]
        # Hiç video-only yoksa acodec kısıtlamasını kaldır
        if not video_formats:
            video_formats = [
                f for f in formats
                if f.get("vcodec", "none") not in ("none", None, "")
            ]

        if not video_formats:
            await msg.edit("❌ Hiç video formatı bulunamadı.")
            return

        # State kaydet
        state = {
            "episode_url": episode_url,
            "info": info,
            "formats": formats,
            "token": token,
            "msg_id": msg.id,
            "chat_id": update.chat.id,
            "user_id": user_id,
        }
        _save_state(user_id, token, state)

        # Kalite butonlarını oluştur
        keyboard = []
        seen_labels = set()
        for fmt in video_formats:
            fmt_id = fmt.get("format_id", "")
            resolution = fmt.get("resolution") or fmt.get("format_note") or fmt.get("height") or ""
            resolution = str(resolution)
            filesize = fmt.get("filesize") or fmt.get("filesize_approx") or 0
            size_str = f" ({humanbytes(filesize)})" if filesize else ""
            label = f"🎬 {resolution}{size_str}"
            if label in seen_labels:
                label = f"🎬 {resolution} [{fmt_id}]{size_str}"
            seen_labels.add(label)
            cb = f"dizilla|quality|{token}|{fmt_id}"
            keyboard.append([InlineKeyboardButton(label, callback_data=cb.encode("UTF-8"))])

        keyboard.append([InlineKeyboardButton("♨ İptal et", callback_data="close")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await msg.edit(
            "**Kalite seçin:** 👇",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )

    except Exception as e:
        LOGGER.exception(e)
        try:
            await msg.edit(f"❌ Beklenmedik hata: `{e}`")
        except Exception:
            pass


# ─────────────────── callback: quality selected ────────────────────────── #

async def dizilla_quality_selected(bot, cb) -> None:
    """
    Kullanıcı kalite butonuna tıkladığında çağrılır.
    Audio track listesini çıkarıp ses butonlarını gösterir.
    """
    # cb.data: "dizilla|quality|<token>|<video_format_id>"
    parts = cb.data.split("|")
    token = parts[2]
    video_fmt_id = parts[3]
    user_id = cb.from_user.id
    message = cb.message

    if message.reply_to_message and message.reply_to_message.from_user:
        owner_id = message.reply_to_message.from_user.id
    else:
        owner_id = user_id

    if owner_id != user_id:
        await cb.answer("Seni tanımıyorum ahbap.", show_alert=True)
        return

    await cb.answer()

    try:
        state = _load_state(user_id, token)
    except FileNotFoundError:
        await message.edit("❌ Oturum süresi doldu. Lütfen linki tekrar gönderin.")
        return

    state["video_fmt_id"] = video_fmt_id
    _save_state(user_id, token, state)

    formats = state.get("formats", [])
    # Audio-only formatları çıkar
    audio_formats = [
        f for f in formats
        if f.get("acodec", "none") not in ("none", None, "")
           and f.get("vcodec", "none") in ("none", None, "")
    ]

    if not audio_formats:
        # Audio format yoksa direkt indirmeye başla (video+bestaudio)
        state["audio_fmt_id"] = "bestaudio"
        _save_state(user_id, token, state)
        await message.edit("⬇️ İndirme başlatılıyor...")
        await _do_download(bot, message, state)
        return

    # Ses butonlarını oluştur
    keyboard = []
    seen_labels = set()
    for afmt in audio_formats:
        fmt_id = afmt.get("format_id", "")
        lang = (
            afmt.get("language")
            or afmt.get("format_note")
            or afmt.get("language_preference")
            or ""
        )
        lang = str(lang).upper() if lang else fmt_id
        abr = afmt.get("abr") or ""
        label = f"🔊 {lang}" + (f" {abr}kbps" if abr else "")
        if label in seen_labels:
            label = f"🔊 {lang} [{fmt_id}]"
        seen_labels.add(label)
        cb_data = f"dizilla|audio|{token}|{fmt_id}"
        keyboard.append([InlineKeyboardButton(label, callback_data=cb_data.encode("UTF-8"))])

    keyboard.append([InlineKeyboardButton("♨ İptal et", callback_data="close")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.edit(
        "**Ses dili seçin:** 👇",
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


# ─────────────────── callback: audio selected ──────────────────────────── #

async def dizilla_audio_selected(bot, cb) -> None:
    """
    Kullanıcı ses butonuna tıkladığında çağrılır.
    İndirmeyi başlatır.
    """
    # cb.data: "dizilla|audio|<token>|<audio_format_id>"
    parts = cb.data.split("|")
    token = parts[2]
    audio_fmt_id = parts[3]
    user_id = cb.from_user.id
    message = cb.message

    if message.reply_to_message and message.reply_to_message.from_user:
        owner_id = message.reply_to_message.from_user.id
    else:
        owner_id = user_id

    if owner_id != user_id:
        await cb.answer("Seni tanımıyorum ahbap.", show_alert=True)
        return

    await cb.answer()

    try:
        state = _load_state(user_id, token)
    except FileNotFoundError:
        await message.edit("❌ Oturum süresi doldu. Lütfen linki tekrar gönderin.")
        return

    state["audio_fmt_id"] = audio_fmt_id
    _save_state(user_id, token, state)

    await message.edit("⬇️ İndirme başlatılıyor...")
    await _do_download(bot, message, state)


# ─────────────────────────── download + encode + upload ───────────────────── #

async def _do_download(bot, message, state: dict) -> None:
    """
    yt-dlp ile indir → ffmpeg ile encode et → Telegram'a yükle → temizle.
    """
    user_id = state["user_id"]
    token = state["token"]
    info = state["info"]
    video_fmt_id = state.get("video_fmt_id", "bestvideo")
    audio_fmt_id = state.get("audio_fmt_id", "bestaudio")
    chat_id = message.chat.id
    message_id = message.id

    # Çalışma dizini
    work_dir = os.path.join(DOWNLOAD_LOCATION, f"dizilla_{user_id}_{token}")
    os.makedirs(work_dir, exist_ok=True)

    raw_video = os.path.join(work_dir, "raw_video.mp4")
    raw_audio = os.path.join(work_dir, "raw_audio.m4a")
    output_file = os.path.join(work_dir, "output.mp4")

    try:
        # ─── 1. Video indir ─────────────────────────────────────────────── #
        await _edit_msg(message, "⬇️ Video indiriliyor...")
        vid_cmd = _build_ytdlp_base_cmd(info) + [
            "--no-playlist",
            "-f", video_fmt_id,
            "-o", raw_video,
            "--newline",
            info["m3u8_url"],
        ]
        await _run_with_progress(vid_cmd, message, "⬇️ Video indiriliyor")

        # ─── 2. Audio indir ─────────────────────────────────────────────── #
        if audio_fmt_id and audio_fmt_id != "bestaudio":
            await _edit_msg(message, "⬇️ Ses indiriliyor...")
            aud_cmd = _build_ytdlp_base_cmd(info) + [
                "--no-playlist",
                "-f", audio_fmt_id,
                "-o", raw_audio,
                "--newline",
                info["m3u8_url"],
            ]
            await _run_with_progress(aud_cmd, message, "⬇️ Ses indiriliyor")
        else:
            # bestaudio — video ile birlikte seç
            await _edit_msg(message, "⬇️ Video+Ses indiriliyor...")
            combined_fmt = f"{video_fmt_id}+bestaudio"
            comb_cmd = _build_ytdlp_base_cmd(info) + [
                "--no-playlist",
                "-f", combined_fmt,
                "--merge-output-format", "mp4",
                "-o", raw_video,
                "--newline",
                info["m3u8_url"],
            ]
            await _run_with_progress(comb_cmd, message, "⬇️ Video+Ses indiriliyor")
            raw_audio = None  # birleşik indirildi

        # ─── 3. ffmpeg encode ───────────────────────────────────────────── #
        await _edit_msg(message, "🎞 Ses encode ediliyor (AAC 256k)...")
        if raw_audio and os.path.exists(raw_audio):
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", raw_video,
                "-i", raw_audio,
                "-c:v", "copy",
                "-c:a", "aac",
                "-ac", "2",
                "-b:a", "256k",
                "-filter:a", "volume=1.2",
                "-movflags", "+faststart",
                output_file,
            ]
        else:
            # Ses raw_video içinde zaten var
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", raw_video,
                "-c:v", "copy",
                "-c:a", "aac",
                "-ac", "2",
                "-b:a", "256k",
                "-filter:a", "volume=1.2",
                "-movflags", "+faststart",
                output_file,
            ]
        await _run_ffmpeg(ffmpeg_cmd)

        if not os.path.exists(output_file):
            await _edit_msg(message, "❌ ffmpeg encode başarısız oldu.")
            return

        # ─── 4. Telegram upload ─────────────────────────────────────────── #
        await _edit_msg(message, "📤 Yükleniyor...")
        thumbnail = await DocumentThumb(bot, _FakeUpdate(user_id))
        width, height, duration = await VideoMetaData(output_file)

        start_time = time.time()

        try:
            await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_VIDEO)
        except Exception:
            pass

        await bot.send_video(
            chat_id=chat_id,
            video=output_file,
            caption="",
            duration=duration,
            width=width,
            height=height,
            supports_streaming=True,
            thumb=thumbnail,
            reply_to_message_id=message.reply_to_message.id if message.reply_to_message else None,
            progress=progress_for_pyrogram,
            progress_args=("📤 Yükleniyor", message, start_time),
        )

        if LOG_CHANNEL:
            try:
                await bot.copy_message(LOG_CHANNEL, chat_id, message.id)
            except Exception:
                pass

        await _edit_msg(message, "✅ Tamamlandı!")

    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        LOGGER.exception(e)
        try:
            await _edit_msg(message, f"❌ Hata oluştu:\n`{e}`")
        except Exception:
            pass
    finally:
        # Temizlik
        _safe_delete(raw_video, raw_audio, output_file)
        try:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass
        _delete_state(user_id, token)


# ─────────────────────────── progress helpers ──────────────────────────── #

_YTDLP_PROGRESS_RE = re.compile(
    r"\[download\]\s+([\d.]+)%\s+of\s+~?([\d.]+\s*\w+)\s+at\s+([\d.]+\s*\w+/s)\s+ETA\s+(\S+)"
)

# İlerleme güncellemeleri arasındaki minimum süre (saniye)
_PROGRESS_UPDATE_INTERVAL = 5


async def _run_with_progress(cmd: list, message, label: str) -> None:
    """
    yt-dlp komutunu çalıştırır, stdout'tan progress bilgisini parse ederek
    Telegram mesajını günceller.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    last_edit = 0.0
    buffer = b""

    async def _read_stdout():
        nonlocal buffer, last_edit
        while True:
            chunk = await proc.stdout.read(256)
            if not chunk:
                break
            buffer += chunk
            lines = re.split(rb"[\r\n]", buffer)
            buffer = lines[-1]
            for line in lines[:-1]:
                text = line.decode(errors="replace")
                m = _YTDLP_PROGRESS_RE.search(text)
                if m:
                    pct, size, speed, eta = m.groups()
                    now = time.time()
                    if now - last_edit >= _PROGRESS_UPDATE_INTERVAL:
                        last_edit = now
                        try:
                            await message.edit(
                                f"**{label}**\n\n"
                                f"`%{pct}` — {size}\n"
                                f"Hız: {speed}\n"
                                f"ETA: {eta}"
                            )
                        except (MessageNotModified, FloodWait):
                            pass
                        except Exception:
                            pass

    await asyncio.gather(_read_stdout(), proc.wait())

    if proc.returncode not in (0, None):
        stderr_out = await proc.stderr.read()
        raise RuntimeError(
            f"yt-dlp hata kodu {proc.returncode}: "
            + stderr_out.decode(errors="replace")[:500]
        )


async def _run_ffmpeg(cmd: list) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg hatası: " + stderr.decode(errors="replace")[-500:]
        )


async def _edit_msg(message, text: str) -> None:
    try:
        await message.edit(text, disable_web_page_preview=True)
    except (MessageNotModified, FloodWait):
        pass
    except Exception:
        pass


# ─────────────────── tiny helper: fake update for DocumentThumb ─────────── #

class _FakeUpdate:
    """DocumentThumb(bot, update) çağrısı için minimal nesne."""

    def __init__(self, user_id: int):
        self.from_user = _FakeUser(user_id)


class _FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id
