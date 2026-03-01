import asyncio
import logging
import re
from typing import Optional, Tuple

LOGGER = logging.getLogger(__name__)

# Timeout for waiting for m3u8 to appear (seconds)
M3U8_WAIT_TIMEOUT = 30


def is_dizilla_url(url: str) -> bool:
    """
    URL'nin Dizilla linki olup olmadığını kontrol eder.

    Note: Bu kontrol yalnızca yönlendirme amaçlıdır, güvenlik filtresi değil.
    """
    return "dizilla.to" in url.lower()


async def _click_play_everywhere(page) -> None:
    """
    Sayfada oynat düğmelerine tıklamayı dener.
    Kullanıcının paylaştığı click_play_everywhere mantığına benzer.
    """
    selectors = [
        "button.play-button",
        ".jw-icon-display",
        ".vjs-big-play-button",
        ".play-btn",
        "[class*='play']",
        "video",
        "div.player",
        "div#player",
        "iframe",
    ]
    for sel in selectors:
        try:
            element = await page.query_selector(sel)
            if element:
                await element.click(timeout=3000)
                LOGGER.debug(f"Tıklandı: {sel}")
                await asyncio.sleep(0.5)
        except Exception:
            pass

    # Sayfaya da tıkla (viewport merkezine)
    try:
        vp = page.viewport_size or {"width": 1280, "height": 720}
        await page.mouse.click(vp["width"] // 2, vp["height"] // 2)
    except Exception:
        pass


async def extract_m3u8_from_dizilla(
    episode_url: str,
) -> Tuple[Optional[str], Optional[str], Optional[dict]]:
    """
    Dizilla bölüm sayfasından Playwright ile m3u8 URL'sini ve referer bilgisini yakalar.

    Döndürülen değerler:
        (m3u8_url, referer, extra_headers)
        - m3u8_url  : Yakalanan m3u8 playlist URL'si (None = bulunamadı)
        - referer   : Kullanılacak referer (None = belirlenemedi)
        - extra_headers : İstekle birlikte kullanılacak ek header'lar (user-agent, cookie vb.)

    Referer seçim kuralı:
        1. .m3u8 isteğinin gerçek referer header'ı
        2. four.pichive.online/iframe.php?v=<id> aracılığıyla bulunan fallback
        3. Hiçbiri yoksa None döner → çağıran taraf kullanıcıya hata mesajı verir.
        Episode URL asla referer olarak kullanılmaz.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        LOGGER.error("Playwright yüklü değil. Lütfen 'pip install playwright' çalıştırın.")
        raise RuntimeError(
            "Playwright yüklü değil. Lütfen 'pip install playwright' çalıştırın."
        )

    from urllib.parse import urlparse

    m3u8_url: Optional[str] = None
    m3u8_headers: dict = {}
    iframe_v_param: Optional[str] = None

    # four.pichive.online iframe URL pattern
    pichive_pattern = re.compile(
        r"https?://four\.pichive\.online/iframe\.php\?v=([^&\s]+)", re.IGNORECASE
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        viewport = {"width": 1280, "height": 720}
        context = await browser.new_context(
            viewport=viewport,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # Network isteği dinleyici
        async def on_request(request):
            nonlocal m3u8_url, m3u8_headers, iframe_v_param
            req_url = request.url

            # four.pichive.online iframe v param yakalama
            m = pichive_pattern.search(req_url)
            if m and iframe_v_param is None:
                iframe_v_param = m.group(1)
                LOGGER.debug(f"Pichive v parametresi yakalandı: {iframe_v_param}")

            # .m3u8 URL yakalama (master veya index içereni tercih et)
            if ".m3u8" in req_url:
                is_preferred = "master" in req_url.lower() or "index" in req_url.lower()
                # Daha iyi bir URL bulunursa veya henüz hiç bulunamadıysa al
                if m3u8_url is None or is_preferred:
                    try:
                        headers = await request.all_headers()
                    except Exception:
                        headers = {}
                    m3u8_url = req_url
                    m3u8_headers = headers
                    LOGGER.debug(f"m3u8 yakalandı: {req_url}")

        page.on("request", on_request)

        try:
            LOGGER.info(f"Dizilla sayfası açılıyor: {episode_url}")
            await page.goto(episode_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # Oynat düğmesine tıkla
            await _click_play_everywhere(page)
            await asyncio.sleep(2)

            # m3u8 için bekle
            loop = asyncio.get_running_loop()
            deadline = loop.time() + M3U8_WAIT_TIMEOUT
            while m3u8_url is None and loop.time() < deadline:
                await _click_play_everywhere(page)
                await asyncio.sleep(2)

        except Exception as e:
            LOGGER.error(f"Sayfa yükleme/navigasyon hatası: {e}")
        finally:
            await browser.close()

    # --- Referer seçim mantığı ---
    episode_parsed = urlparse(episode_url)
    referer: Optional[str] = None
    if m3u8_headers:
        # HTTP headers are case-insensitive; check both common casings
        candidate = (
            m3u8_headers.get("referer")
            or m3u8_headers.get("Referer")
        )
        if candidate:
            candidate_parsed = urlparse(candidate)
            # Episode URL'yi referer olarak kullanma
            if candidate_parsed.netloc != episode_parsed.netloc or \
               candidate_parsed.path != episode_parsed.path:
                referer = candidate
                LOGGER.debug(f"Referer header'dan alındı: {referer}")

    if referer is None and iframe_v_param:
        referer = f"https://four.pichive.online/iframe.php?v={iframe_v_param}"
        LOGGER.debug(f"Referer fallback (pichive): {referer}")

    # Yardımcı header'lar (user-agent, cookie, origin)
    # HTTP headers are case-insensitive; check lowercase and title-case variants
    extra_headers: dict = {}
    for key in ("user-agent", "cookie", "origin"):
        val = m3u8_headers.get(key) or m3u8_headers.get(key.title())
        if val:
            extra_headers[key] = val

    return m3u8_url, referer, extra_headers


async def handle_dizilla(bot, message, url: str) -> None:
    """
    Dizilla URL'sini işler: m3u8 yakalar ve kullanıcıyı bilgilendirir.

    Args:
        bot    : Pyrogram Client
        message: Kullanıcı mesajı
        url    : Dizilla bölüm URL'si
    """
    status_msg = await message.reply_text(
        "🔍 Dizilla linki tespit edildi, m3u8 aranıyor... ⏳",
        disable_web_page_preview=True,
    )

    try:
        m3u8_url, referer, extra_headers = await extract_m3u8_from_dizilla(url)

        if m3u8_url is None:
            await status_msg.edit_text(
                "❌ m3u8 URL'si bulunamadı.\n\n"
                "Sayfa video içermiyor olabilir veya yükleme zaman aşımına uğradı."
            )
            return

        if referer is None:
            await status_msg.edit_text(
                "❌ Referer bilgisi belirlenemedi.\n\n"
                "m3u8 isteğinde referer header'ı yok ve pichive iframe linki de yakalanamadı. "
                "İndirme işlemi durduruluyor."
            )
            return

        # Başarı: kullanıcıya bilgi ver
        masked_url = m3u8_url[:80] + "..." if len(m3u8_url) > 80 else m3u8_url
        await status_msg.edit_text(
            f"✅ m3u8 yakalandı!\n\n"
            f"🔗 **URL:** `{masked_url}`\n"
            f"🌐 **Referer:** `{referer}`"
        )
        LOGGER.info(
            f"Dizilla m3u8 başarıyla yakalandı | url={m3u8_url} | referer={referer}"
        )

    except RuntimeError as e:
        await status_msg.edit_text(f"❌ Hata: {e}")
    except Exception as e:
        LOGGER.error(f"Dizilla handle hatası: {e}")
        try:
            await status_msg.edit_text(f"❌ Beklenmeyen hata:\n\n{e}")
        except Exception:
            pass
