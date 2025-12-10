import asyncio
import aiohttp
import logging
from typing import List, Optional
from fake_useragent import UserAgent

LOGGER = logging.getLogger(__name__)


class ProxyManager:
    """Proxy havuzu yönetimi ve rotasyon sistemi"""
    
    def __init__(self, manual_proxies: List[str] = None, auto_fetch: bool = True):
        """
        Args:
            manual_proxies: Manuel proxy listesi
            auto_fetch: Otomatik free proxy çekme
        """
        self.manual_proxies = manual_proxies or []
        self.auto_fetch = auto_fetch
        self.proxy_pool = []
        self.current_index = 0
        self.failed_proxies = set()
        self.ua = UserAgent()
        
    async def initialize(self):
        """Proxy havuzunu başlat"""
        # Manuel proxy'leri ekle
        if self.manual_proxies:
            self.proxy_pool.extend([p.strip() for p in self.manual_proxies if p.strip()])
            LOGGER.info(f"{len(self.manual_proxies)} manuel proxy eklendi")
        
        # Otomatik free proxy çek
        if self.auto_fetch:
            free_proxies = await self.get_free_proxies()
            self.proxy_pool.extend(free_proxies)
            LOGGER.info(f"{len(free_proxies)} free proxy çekildi")
        
        if not self.proxy_pool:
            LOGGER.warning("Proxy havuzu boş!")
        else:
            LOGGER.info(f"Toplam {len(self.proxy_pool)} proxy hazır")
    
    async def get_free_proxies(self, limit: int = 10) -> List[str]:
        """
        Free proxy listesi çeker
        
        Args:
            limit: Maksimum proxy sayısı
            
        Returns:
            Proxy listesi
        """
        proxies = []
        
        try:
            # Free proxy API'lerinden çek
            sources = [
                "https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
                "https://www.proxy-list.download/api/v1/get?type=http",
            ]
            
            async with aiohttp.ClientSession() as session:
                for source in sources:
                    try:
                        async with session.get(source, timeout=aiohttp.ClientTimeout(total=10)) as response:
                            if response.status == 200:
                                text = await response.text()
                                # Satır satır proxy'leri ayıkla
                                for line in text.strip().split('\n'):
                                    line = line.strip()
                                    if line and ':' in line:
                                        # Format: http://ip:port
                                        if not line.startswith('http'):
                                            line = f"http://{line}"
                                        proxies.append(line)
                                        if len(proxies) >= limit:
                                            break
                            if len(proxies) >= limit:
                                break
                    except Exception as e:
                        LOGGER.debug(f"Proxy kaynağı hatası ({source}): {e}")
                        continue
                        
        except Exception as e:
            LOGGER.error(f"Free proxy çekme hatası: {e}")
        
        return proxies[:limit]
    
    async def get_next_proxy(self) -> Optional[str]:
        """
        Sıradaki proxy'yi döndürür (rotasyon)
        
        Returns:
            Proxy string veya None
        """
        if not self.proxy_pool:
            return None
        
        # Tüm proxy'ler başarısız olduysa sıfırla
        if len(self.failed_proxies) >= len(self.proxy_pool):
            LOGGER.warning("Tüm proxy'ler başarısız, baştan başlıyoruz")
            self.failed_proxies.clear()
        
        # Başarısız olmayan bir proxy bul
        attempts = 0
        while attempts < len(self.proxy_pool):
            proxy = self.proxy_pool[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxy_pool)
            
            if proxy not in self.failed_proxies:
                LOGGER.info(f"Proxy seçildi: {proxy}")
                return proxy
            
            attempts += 1
        
        return None
    
    async def test_proxy(self, proxy: str, test_url: str = "http://www.google.com", timeout: int = 10) -> bool:
        """
        Proxy'yi test eder
        
        Args:
            proxy: Test edilecek proxy
            test_url: Test URL'si
            timeout: Timeout süresi (saniye)
            
        Returns:
            True = çalışıyor, False = çalışmıyor
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    test_url,
                    proxy=proxy,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status == 200:
                        LOGGER.info(f"Proxy çalışıyor: {proxy}")
                        return True
        except Exception as e:
            LOGGER.debug(f"Proxy test hatası ({proxy}): {e}")
        
        return False
    
    def mark_proxy_failed(self, proxy: str):
        """Proxy'yi başarısız olarak işaretle"""
        if proxy:
            self.failed_proxies.add(proxy)
            LOGGER.warning(f"Proxy başarısız olarak işaretlendi: {proxy}")
    
    def get_random_user_agent(self) -> str:
        """Random User-Agent döndürür"""
        try:
            return self.ua.random
        except Exception as e:
            LOGGER.debug(f"User-Agent oluşturma hatası: {e}")
            # Fallback user agents
            fallback_uas = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ]
            import random
            return random.choice(fallback_uas)
    
    def rotate_proxy(self) -> Optional[str]:
        """Synchronous proxy rotation (backward compatibility)"""
        if not self.proxy_pool:
            return None
        proxy = self.proxy_pool[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxy_pool)
        return proxy
