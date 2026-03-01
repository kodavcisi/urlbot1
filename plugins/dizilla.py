import asyncio
import json
import os
import re
import shutil
import time
from urllib.parse import urlparse, parse_qs

from pyrogram.enums import ChatAction
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DOWNLOAD_LOCATION, TG_MAX_FILE_SIZE
from functions.ffmpeg import VideoThumb, VideoMetaData, DocumentThumb
from functions.progress import progress_for_pyrogram

import logging
LOGGER = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

# Turkish keyword map for slug conversion
_TR_MAP = {
    'bolum': 'Bölüm',
    'sezon': 'Sezon',
}

# Maximum safe filename length for Telegram/filesystem compatibility
MAX_FILENAME_LENGTH = 80


def slug_to_title(slug: str) -> str:
    """Convert a dizilla.to URL slug to a human-readable Turkish title.

    Example: 'forensic-files-1-sezon-1-bolum' -> 'Forensic Files 1. Sezon 1. Bölüm'
    """
    words = slug.split('-')
    result = []
    for word in words:
        lower = word.lower()
        if lower in _TR_MAP:
            # Append a dot to the preceding number token if present
            if result and result[-1].rstrip('.').isdigit():
                result[-1] = result[-1].rstrip('.') + '.'
            result.append(_TR_MAP[lower])
        else:
            result.append(word.capitalize())
    return ' '.join(result)


async def click_play_everywhere(page) -> None:
    """Videoyu oynatmak için gerekli alanlara tıklar (sync script mantığının async uyarlaması)."""
    selectors = [
        "button:has-text('Play')", "button:has-text('PLAY')",
        ".vjs-big-play-button", ".jw-icon-playback", ".play",
        "video", "iframe", "#player",
    ]

    for sel in selectors:
        try:
            loc = page.locator(sel).first
            cnt = await loc.count()
            if cnt > 0:
                await loc.click(timeout=800, force=True)
                await page.wait_for_timeout(200)
        except Exception:
            pass

    # Center click
    try:
        vs = page.viewport_size
        if vs:
            await page.mouse.click(vs["width"] // 2, vs["height"] // 2)
            await page.wait_for_timeout(200)
    except Exception:
        pass

    # Frame click for vjs button
    try:
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            try:
                await fr.click(".vjs-big-play-button", timeout=400, force=True)
            except Exception:
                pass
    except Exception:
        pass


async def capture_m3u8_playwright(dizilla_url: str) -> dict:
    """
    Open dizilla.to page with Playwright and capture the master/index m3u8 URL + headers.

    Bu fonksiyon, kullanıcının paylaştığı sync scriptteki sistemi uygular:
      - context.route("**/*") ile tüm network trafiğini dinler (iframe dahil)
      - .m3u8/.mp4 yakalayınca URL'yi kaydeder ve route.abort() ile token tüketmeyi engeller
      - request header'larından referer/cookie/origin/user-agent yakalar
      - iframe.php?v=<id> görürse v parametresini yakalar (referer fallback için)

    Returns a dict with keys: m3u8_url, referer, cookie, origin, user_agent, iframe_v
    """
    from playwright.async_api import async_playwright

    captured = {
        "m3u8_url": None,
        "referer": "",
        "cookie": "",
        "origin": "",
        "user_agent": UA,
        "iframe_v": None,
    }

    def _is_preferred(url: str) -> bool:
        u = url.lower()
        return ("master" in u) or ("index" in u)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = await browser.new_context(
                user_agent=UA,
                viewport={"width": 1280, "height": 720},
            )

            async def route_handler(route, request):
                req_url = request.url

                # Capture iframe v parameter
                if "iframe.php?v=" in req_url and captured["iframe_v"] is None:
                    try:
                        parsed = urlparse(req_url)
                        params = parse_qs(parsed.query)
                        v = params.get("v", [None])[0]
                        if v:
                            captured["iframe_v"] = v
                    except Exception:
                        pass

                # Capture m3u8 / mp4 and abort to keep token fresh
                if (".m3u8" in req_url) or (".mp4" in req_url):
                    if (not captured["m3u8_url"]) or _is_preferred(req_url):
                        captured["m3u8_url"] = req_url
                        try:
                            headers = await request.all_headers()
                        except Exception:
                            headers = request.headers or {}

                        captured["referer"] = headers.get("referer", "") or ""
                        captured["cookie"] = headers.get("cookie", "") or ""
                        captured["origin"] = headers.get("origin", "") or ""
                        captured["user_agent"] = headers.get("user-agent", UA) or UA

                        await route.abort()
                        return

                await route.continue_()

            await context.route("**/*", route_handler)

            page = await context.new_page()
            try:
                await page.goto(dizilla_url, wait_until="domcontentloaded", timeout=90000)
            except Exception:
                pass

            # Link düşene kadar tıklamaya devam (sync scriptteki gibi 40 tur)
            for _ in range(40):
                if captured["m3u8_url"]:
                    break
                await click_play_everywhere(page)
                await page.wait_for_timeout(1000)

            try:
                await context.unroute("**/*", route_handler)
            except Exception:
                pass

            await context.close()
        finally:
            await browser.close()

    return captured


def get_referer(captured: dict) -> str:
    """Apply the referer rule.

    Priority:
      1. Real referer from the m3u8 request headers.
      2. Fallback: https://four.pichive.online/iframe.php?v=<v>
      3. Empty string (caller should treat as error).
    """
    referer = captured.get("referer", "") or ""
    if referer:
        return referer
    iframe_v = captured.get("iframe_v")
    if iframe_v:
        return f"https://four.pichive.online/iframe.php?v={iframe_v}"
    return ""


async def dizilla_trigger(bot, update, url: str, file_name: str = None):
    """Main entry point: detect dizilla.to link, capture m3u8, show quality buttons."""
    message_id = update.id
    chat_id = update.chat.id
    user_id = update.from_user.id
    session_id = str(time.time())

    send_message = await update.reply(
        text="🎬 Dizilla linki tespit edildi. Sayfa taranıyor...",
        disable_web_page_preview=True,
        reply_to_message_id=message_id,
    )

    # Generate title from URL slug if no custom name given
    if file_name:
        title = file_name.strip()
    else:
        try:
            path_parts = urlparse(url).path.strip("/").split("/")
            slug = path_parts[-1] if path_parts else ""
            # Remove trailing numeric ID like -123456
            slug = re.sub(r"-\d+$", "", slug)
            title = slug_to_title(slug) if slug else "Dizilla Video"
        except Exception:
            title = "Dizilla Video"

    await send_message.edit_text("🎬 Playwright ile m3u8 yakalanıyor... ⏳")

    try:
        captured = await capture_m3u8_playwright(url)
    except Exception as e:
        LOGGER.error(f"Playwright error: {e}")
        await send_message.edit_text(f"❌ Playwright hatası: {e}")
        return

    if not captured["m3u8_url"]:
        await send_message.edit_text("❌ m3u8 URL yakalanamadı. Sayfa oynatıcıyı başlatamadı.")
        return

    referer = get_referer(captured)
    if not referer:
        await send_message.edit_text("❌ Referer tespit edilemedi ve iframe fallback için 'v' parametresi de bulunamadı.")
        return

    await send_message.edit_text("🔍 Formatlar ayıklanıyor...")

    # Run yt-dlp -j to retrieve format information
    cmd_j = [
        "yt-dlp",
        "--no-warnings",
        "--no-check-certificate",
        "-j",
        "--impersonate", "chrome",
        "--referer", referer,
        captured["m3u8_url"],
    ]
    if captured.get("cookie"):
        cmd_j += ["--add-header", f"Cookie:{captured['cookie']}"]
    if captured.get("origin"):
        cmd_j += ["--add-header", f"Origin:{captured['origin']}"]
    if captured.get("user_agent"):
        cmd_j += ["--add-header", f"User-Agent:{captured['user_agent']}"]

    process = await asyncio.create_subprocess_exec(
        *cmd_j,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    t_response = stdout.decode().strip()
    e_response = stderr.decode().strip()

    if not t_response:
        err_msg = e_response[:500] if e_response else "Bilinmeyen hata"
        await send_message.edit_text(f"❌ yt-dlp format bilgisi alınamadı:\n{err_msg}")
        return

    try:
        response_json = json.loads(t_response.split("\n")[0])
    except json.JSONDecodeError as e:
        await send_message.edit_text(f"❌ yt-dlp çıktısı ayrıştırılamadı: {e}")
        return

    formats = response_json.get("formats", [])
    video_formats = [
        f for f in formats
        if f.get("vcodec", "none") not in ("none", None) and f.get("height")
    ]
    audio_formats = [
        f for f in formats
        if f.get("vcodec", "none") in ("none", None)
        and f.get("acodec", "none") not in ("none", None)
    ]

    if not video_formats and not formats:
        await send_message.edit_text("❌ Hiçbir format bulunamadı.")
        return

    # Persist session data for callback use
    session_data = {
        "m3u8_url": captured["m3u8_url"],
        "referer": referer,
        "cookie": captured.get("cookie", ""),
        "origin": captured.get("origin", ""),
        "user_agent": captured.get("user_agent", ""),
        "title": title,
        "file_name": file_name,
        "formats": formats,
        "audio_formats": audio_formats,
    }
    os.makedirs(DOWNLOAD_LOCATION, exist_ok=True)
    session_path = os.path.join(DOWNLOAD_LOCATION, f"{user_id}_dizilla_{session_id}.json")
    with open(session_path, "w", encoding="utf8") as f:
        json.dump(session_data, f, ensure_ascii=False)

    # Build quality selection inline keyboard
    inline_keyboard = []
    seen_heights = set()
    for fmt in sorted(video_formats, key=lambda x: x.get("height", 0), reverse=True):
        height = fmt.get("height", 0)
        fmt_id = fmt.get("format_id", "")
        tbr = fmt.get("tbr")
        tbr_str = f" ~{int(tbr)}k" if tbr else ""
        label = f"🎬 {height}p{tbr_str}"
        if height not in seen_heights:
            seen_heights.add(height)
            cb_data = f"dizilla|q|{fmt_id}|{session_id}"
            if len(cb_data.encode("utf-8")) <= 64:
                inline_keyboard.append([InlineKeyboardButton(label, callback_data=cb_data)])

    if not inline_keyboard:
        cb_data = f"dizilla|q|best|{session_id}"
        if len(cb_data.encode("utf-8")) <= 64:
            inline_keyboard.append([InlineKeyboardButton("🎬 En İyi Kalite", callback_data=cb_data)])

    inline_keyboard.append([InlineKeyboardButton("♨ İptal et", callback_data="close")])

    await send_message.edit_text(
        text=f"🎬 **{title}**\n\nKalite seçin:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard),
        disable_web_page_preview=True,
    )


# --- callback/download kısmın aşağıda aynen kalabilir ---
# (Senin gönderdiğin kodun geri kalanı burada değişmeden bırakıldı)

async def dizilla_callback(bot, cb):
    """Dispatch dizilla| callback queries to the appropriate handler."""
    parts = cb.data.split('|')
    action = parts[1] if len(parts) > 1 else ''
    if action == 'q':
        await _handle_quality_selection(bot, cb, parts)
    elif action == 'a':
        await _handle_audio_selection(bot, cb, parts)
    else:
        await cb.message.delete(True)


async def _handle_quality_selection(bot, cb, parts):
    """Show audio track buttons after quality selection (or skip if single audio)."""
    if len(parts) < 4:
        return
    format_id = parts[2]
    session_id = parts[3]

    user_id = cb.from_user.id
    message = cb.message
    chat_id = message.chat.id
    msg_id = message.id

    if message.reply_to_message and message.reply_to_message.from_user:
        original_user = message.reply_to_message.from_user.id
        if original_user != user_id:
            await bot.answer_callback_query(
                callback_query_id=cb.id,
                text="Bu butonlar sana ait değil.",
                show_alert=True,
            )
            return

    session_path = os.path.join(DOWNLOAD_LOCATION, f"{user_id}_dizilla_{session_id}.json")
    try:
        with open(session_path, 'r', encoding='utf8') as f:
            session = json.load(f)
    except FileNotFoundError:
        await bot.edit_message_text("❌ Oturum verisi bulunamadı.", chat_id=chat_id, message_id=msg_id)
        return

    audio_formats = session.get('audio_formats', [])
    title = session.get('title', 'Dizilla Video')

    if len(audio_formats) > 1:
        inline_keyboard = []
        for af in audio_formats:
            af_id = af.get('format_id', '')
            lang = (af.get('language') or af.get('format_note') or af_id).upper()
            abr = af.get('abr')
            abr_str = f" {int(abr)}k" if abr else ""
            label = f"🔊 {lang}{abr_str}"
            cb_data = f"dizilla|a|{af_id}|{format_id}|{session_id}"
            if len(cb_data.encode('utf-8')) <= 64:
                inline_keyboard.append([InlineKeyboardButton(label, callback_data=cb_data)])

        if inline_keyboard:
            inline_keyboard.append([InlineKeyboardButton("♨ İptal et", callback_data='close')])
            await bot.edit_message_text(
                text=f"🎬 **{title}**\n\nSes dili seçin:",
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=InlineKeyboardMarkup(inline_keyboard),
            )
            return

    best_audio = audio_formats[0]['format_id'] if audio_formats else None
    await _start_download(bot, cb, session, session_id, format_id, best_audio)


async def _handle_audio_selection(bot, cb, parts):
    """Start download after user picks an audio track."""
    if len(parts) < 5:
        return
    audio_format_id = parts[2]
    quality_format_id = parts[3]
    session_id = parts[4]

    user_id = cb.from_user.id
    message = cb.message
    chat_id = message.chat.id
    msg_id = message.id

    if message.reply_to_message and message.reply_to_message.from_user:
        original_user = message.reply_to_message.from_user.id
        if original_user != user_id:
            await bot.answer_callback_query(
                callback_query_id=cb.id,
                text="Bu butonlar sana ait değil.",
                show_alert=True,
            )
            return

    session_path = os.path.join(DOWNLOAD_LOCATION, f"{user_id}_dizilla_{session_id}.json")
    try:
        with open(session_path, 'r', encoding='utf8') as f:
            session = json.load(f)
    except FileNotFoundError:
        await bot.edit_message_text("❌ Oturum verisi bulunamadı.", chat_id=chat_id, message_id=msg_id)
        return

    await _start_download(bot, cb, session, session_id, quality_format_id, audio_format_id)


async def _start_download(bot, cb, session, session_id, video_fmt, audio_fmt):
    """Download via yt-dlp, postprocess via ffmpeg, upload to Telegram, then clean up."""
    user_id = cb.from_user.id
    message = cb.message
    chat_id = message.chat.id
    msg_id = message.id

    m3u8_url = session['m3u8_url']
    referer = session['referer']
    cookie = session.get('cookie', '')
    origin = session.get("origin", "")
    user_agent = session.get("user_agent", "")

    title = session.get('title', 'Dizilla Video')
    file_name = session.get('file_name') or title
    safe_name = re.sub(r'[\\/*?:"<>|]', '', file_name)[:MAX_FILENAME_LENGTH]

    dtime = str(time.time())
    tmp_dir = os.path.join(DOWNLOAD_LOCATION, str(user_id), dtime)
    os.makedirs(tmp_dir, exist_ok=True)

    raw_output = os.path.join(tmp_dir, f"{safe_name}_raw.mp4")
    final_output = os.path.join(tmp_dir, f"{safe_name}.mp4")
    session_path = os.path.join(DOWNLOAD_LOCATION, f"{user_id}_dizilla_{session_id}.json")

    if audio_fmt and audio_fmt != video_fmt:
        fmt_str = f"{video_fmt}+{audio_fmt}"
    else:
        fmt_str = video_fmt

    cmd_dl = [
        "yt-dlp",
        "--no-warnings",
        "--no-check-certificate",
        "--impersonate", "chrome",
        "--referer", referer,
        "-f", fmt_str,
        "--merge-output-format", "mp4",
        "-N", "4",
        m3u8_url,
        "-o", raw_output,
    ]
    if cookie:
        cmd_dl += ["--add-header", f"Cookie:{cookie}"]
    if origin:
        cmd_dl += ["--add-header", f"Origin:{origin}"]
    if user_agent:
        cmd_dl += ["--add-header", f"User-Agent:{user_agent}"]

    dl_progress_re = re.compile(
        r'\[download\]\s+([\d.]+)%\s+of\s+~?([\d.]+\s*\S+)\s+at\s+([\S]+)\s+ETA\s+([\S]+)'
    )

    try:
        await bot.edit_message_text(
            text=f"📥 **{title}** indiriliyor...",
            chat_id=chat_id,
            message_id=msg_id,
        )

        process = await asyncio.create_subprocess_exec(
            *cmd_dl,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stderr_lines = []
        last_edit = 0.0

        async def read_stderr():
            nonlocal last_edit
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                decoded = line.decode('utf-8', errors='replace').rstrip()
                stderr_lines.append(decoded)
                match = dl_progress_re.search(decoded)
                if match:
                    percentage, size, speed, eta = match.group(1), match.group(2), match.group(3), match.group(4)
                    now = time.time()
                    if now - last_edit >= 5:
                        try:
                            await bot.edit_message_text(
                                text=(
                                    f"📥 **{title}** indiriliyor...\n"
                                    f"{percentage}% | {size} | {speed}/s | ETA {eta}"
                                ),
                                chat_id=chat_id,
                                message_id=msg_id,
                            )
                            last_edit = now
                        except Exception:
                            pass

        async def drain_stdout():
            while not process.stdout.at_eof():
                await process.stdout.read(4096)

        await asyncio.gather(read_stderr(), drain_stdout(), process.wait())

        if process.returncode != 0:
            err = '\n'.join(stderr_lines[-10:])[:500]
            await bot.edit_message_text(text=f"❌ İndirme hatası:\n{err}", chat_id=chat_id, message_id=msg_id)
            return

        await bot.edit_message_text(text=f"🔧 **{title}** işleniyor...", chat_id=chat_id, message_id=msg_id)

        cmd_ff = [
            "ffmpeg", "-y",
            "-i", raw_output,
            "-c:v", "copy",
            "-c:a", "aac",
            "-ac", "2",
            "-b:a", "256k",
            "-af", "volume=1.2",
            final_output,
        ]
        ff_proc = await asyncio.create_subprocess_exec(
            *cmd_ff,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await ff_proc.wait()

        upload_path = final_output if os.path.exists(final_output) else raw_output
        if not os.path.exists(upload_path):
            await bot.edit_message_text(text="❌ İşlem sonrası dosya bulunamadı.", chat_id=chat_id, message_id=msg_id)
            return

        await bot.edit_message_text(text=f"📤 **{title}** yükleniyor...", chat_id=chat_id, message_id=msg_id)

        width, height_v, duration = await VideoMetaData(upload_path)
        thumb_path = await VideoThumb(bot, cb, duration, upload_path, session_id)

        start_upload = time.time()
        if message.reply_to_message:
            await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_VIDEO)

        await bot.send_video(
            chat_id=chat_id,
            video=upload_path,
            caption=f"🎬 **{title}**",
            duration=duration,
            width=width,
            height=height_v,
            supports_streaming=True,
            thumb=thumb_path,
            reply_to_message_id=(message.reply_to_message.id if message.reply_to_message else None),
            progress=progress_for_pyrogram,
            progress_args=(f"📤 {title}", message, start_upload),
        )

        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=msg_id, revoke=True)
        except Exception:
            pass

    finally:
        for path in [raw_output, final_output, session_path]:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        try:
            if os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
