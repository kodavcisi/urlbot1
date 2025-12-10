import asyncio
import logging
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

LOGGER = logging.getLogger(__name__)


@dataclass
class PixeldrainAccount:
    """Pixeldrain hesap bilgisi"""
    email: str
    username: str
    password: str
    api_key: str
    remaining_quota: int = 6 * 1024 * 1024 * 1024  # 6GB başlangıç
    total_quota: int = 6 * 1024 * 1024 * 1024  # 6GB toplam
    last_checked: Optional[datetime] = None
    
    def has_quota(self, required_bytes: int) -> bool:
        """Yeterli kota var mı kontrol eder"""
        return self.remaining_quota >= required_bytes
    
    def use_quota(self, bytes_used: int):
        """Kota kullanımını kaydeder"""
        self.remaining_quota -= bytes_used
        if self.remaining_quota < 0:
            self.remaining_quota = 0
    
    def reset_quota(self):
        """Kotayı sıfırlar (günlük reset için)"""
        self.remaining_quota = self.total_quota
        self.last_checked = datetime.now()


class PixeldrainAccountManager:
    """Pixeldrain hesap yöneticisi - kota takibi ve akıllı hesap seçimi"""
    
    # Hesap listesi - kullanıcıdan gelen sırayla
    ACCOUNTS = [
        PixeldrainAccount(
            email="noelledark@comfythings.com",
            username="noelledark",
            password="Dark.0545",
            api_key="b77a4994-7ac6-43b0-94e8-396628247b6a"
        ),
        PixeldrainAccount(
            email="johnsnow33@comfythings.com",
            username="johnsnow33",
            password="John.0545",
            api_key="27f10648-e17c-4dad-8c2d-65be5982939c"
        ),
        PixeldrainAccount(
            email="ragnar33@comfythings.com",
            username="ragnar33",
            password="Ragnar.0545",
            api_key="aad77afe-6796-4781-a1af-c7acf639d360"
        ),
        PixeldrainAccount(
            email="ronaldo33@comfythings.com",
            username="ronaldo3301",
            password="Ronaldo.0545",
            api_key="76c6cac9-e864-441e-b762-2a812b69052b"
        ),
        PixeldrainAccount(
            email="jack33@comfythings.com",
            username="jack33",
            password="Jack.0545",
            api_key="0c9ad17f-685e-4c36-b12b-83f6e37beba2"
        ),
        PixeldrainAccount(
            email="jesse33@comfythings.com",
            username="jesse33",
            password="Jesse.0545",
            api_key="12d8ce77-cfbc-4256-9c85-5911d3d11cf9"
        ),
        PixeldrainAccount(
            email="neymar33@comfythings.com",
            username="neymar33",
            password="Neymar.0545",
            api_key="1af622f4-29b4-4311-bc1d-309d3931e418"
        ),
        PixeldrainAccount(
            email="messi33@comfythings.com",
            username="messi33",
            password="Messi.0535",
            api_key="7d37d20b-7128-4002-b4a3-b93df3af9ce0"
        ),
        PixeldrainAccount(
            email="tyler33@comfythings.com",
            username="tyler33",
            password="Tyler.0545",
            api_key="2cb0d271-a7ad-45c8-b485-732268356e95"
        ),
        PixeldrainAccount(
            email="michael33@comfythings.com",
            username="michael33",
            password="Michael.0545",
            api_key="4cd01a88-655d-4138-a10b-af9ca7ca0c51"
        ),
    ]
    
    def __init__(self):
        self.current_account_index = 0
    
    async def get_account_quota(self, account: PixeldrainAccount) -> Optional[int]:
        """
        Pixeldrain API'sinden hesabın kalan kotasını öğrenir
        
        Args:
            account: Kontrol edilecek hesap
            
        Returns:
            Kalan kota (bytes) veya None
        """
        try:
            import aiohttp
            
            url = "https://pixeldrain.com/api/user/limits"
            headers = {
                "Authorization": f"Basic {account.api_key}",
                "User-Agent": "Mozilla/5.0"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        # API'den dönen kota bilgisi
                        # bandwidth_limit - bandwidth_used = kalan
                        if 'bandwidth_limit' in data and 'bandwidth_used' in data:
                            remaining = data['bandwidth_limit'] - data['bandwidth_used']
                            LOGGER.info(f"Hesap {account.username}: {remaining / (1024*1024*1024):.2f}GB kalan")
                            return max(0, remaining)
                    else:
                        LOGGER.warning(f"Hesap {account.username} kota kontrolü başarısız: HTTP {response.status}")
                        return None
        except Exception as e:
            LOGGER.error(f"Hesap {account.username} kota kontrol hatası: {e}")
            return None
    
    async def update_account_quota(self, account: PixeldrainAccount):
        """Hesabın kotasını API'den günceller"""
        quota = await self.get_account_quota(account)
        if quota is not None:
            account.remaining_quota = quota
            account.last_checked = datetime.now()
    
    def select_best_account(self, file_size: int) -> Optional[PixeldrainAccount]:
        """
        Dosya boyutuna göre en uygun hesabı seçer
        
        Strateji:
        1. Dosya boyutundan büyük kotası olan hesaplar arasından
        2. Eğer dosya küçükse (<2GB), kalan kotası en az olan hesabı seç
        3. Eğer dosya büyükse (>2GB), kalan kotası en çok olan hesabı seç
        
        Args:
            file_size: İndirilecek dosya boyutu (bytes)
            
        Returns:
            Seçilen hesap veya None
        """
        # Yeterli kotası olan hesapları bul
        suitable_accounts = [acc for acc in self.ACCOUNTS if acc.has_quota(file_size)]
        
        if not suitable_accounts:
            LOGGER.error(f"Hiçbir hesapta {file_size / (1024*1024*1024):.2f}GB için yeterli kota yok!")
            return None
        
        # Dosya boyutuna göre strateji
        if file_size < 2 * 1024 * 1024 * 1024:  # 2GB'dan küçük
            # Küçük dosyalar için: en az kotası olan hesabı kullan (kota tasarrufu)
            selected = min(suitable_accounts, key=lambda acc: acc.remaining_quota)
            LOGGER.info(f"Küçük dosya ({file_size / (1024*1024):.1f}MB): En az kotalı hesap seçildi: {selected.username}")
        else:  # 2GB ve üstü
            # Büyük dosyalar için: en çok kotası olan hesabı kullan
            selected = max(suitable_accounts, key=lambda acc: acc.remaining_quota)
            LOGGER.info(f"Büyük dosya ({file_size / (1024*1024*1024):.2f}GB): En çok kotalı hesap seçildi: {selected.username}")
        
        return selected
    
    def get_account_by_api_key(self, api_key: str) -> Optional[PixeldrainAccount]:
        """API key'e göre hesap bulur"""
        for account in self.ACCOUNTS:
            if account.api_key == api_key:
                return account
        return None
    
    def mark_quota_used(self, account: PixeldrainAccount, bytes_used: int):
        """Kullanılan kotayı işaretle"""
        account.use_quota(bytes_used)
        LOGGER.info(f"Hesap {account.username}: {bytes_used / (1024*1024*1024):.2f}GB kullanıldı. "
                   f"Kalan: {account.remaining_quota / (1024*1024*1024):.2f}GB")
    
    def get_status_summary(self) -> str:
        """Tüm hesapların kota durumunu döndürür"""
        summary = "📊 Pixeldrain Hesap Durumu:\n\n"
        for i, account in enumerate(self.ACCOUNTS, 1):
            remaining_gb = account.remaining_quota / (1024 * 1024 * 1024)
            total_gb = account.total_quota / (1024 * 1024 * 1024)
            percent = (account.remaining_quota / account.total_quota) * 100
            
            summary += f"{i}. {account.username}\n"
            summary += f"   Kalan: {remaining_gb:.2f}GB / {total_gb:.0f}GB ({percent:.0f}%)\n\n"
        
        return summary


# Global instance
account_manager = PixeldrainAccountManager()
