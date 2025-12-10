import asyncio
import re
import logging
from typing import Optional, Dict, Tuple

LOGGER = logging.getLogger(__name__)


def build_aria2c_command(url: str, output_path: str, connections: int = 16, proxy: Optional[str] = None, 
                         user_agent: Optional[str] = None, referer: Optional[str] = None) -> list:
    """
    aria2c komutunu oluşturur
    
    Args:
        url: İndirilecek dosya URL'si
        output_path: Çıktı dosya yolu
        connections: Bağlantı sayısı (varsayılan: 16)
        proxy: Proxy adresi (opsiyonel)
        user_agent: User-Agent header (opsiyonel)
        referer: Referer header (opsiyonel)
    
    Returns:
        aria2c komut listesi
    """
    import os
    
    output_dir = os.path.dirname(output_path) or '.'
    output_file = os.path.basename(output_path)
    
    command = [
        "aria2c",
        "-x", str(connections),
        "-s", str(connections),
        "-k", "1M",
        "--file-allocation=none",
        "--console-log-level=error",
        "--summary-interval=0",
        "-d", output_dir,  # dizin
        "-o", output_file,  # dosya adı
        url
    ]
    
    if proxy:
        command.extend(["--all-proxy", proxy])
    
    if user_agent:
        command.extend(["--user-agent", user_agent])
    
    if referer:
        command.extend(["--referer", referer])
    
    return command


async def parse_progress(line: str) -> Optional[Dict[str, str]]:
    """
    aria2c çıktısından progress bilgisini parse eder
    
    Örnek çıktı:
    [#1 SIZE:2.1GiB/8.5GiB(24%) CN:16 DL:15.3MiB ETA:7m23s]
    
    Args:
        line: aria2c çıktı satırı
    
    Returns:
        Progress bilgisi dict veya None
    """
    pattern = re.compile(
        r'\[#\d+ SIZE:([\d.]+\w+)/([\d.]+\w+)\((\d+)%\) CN:(\d+) DL:([\d.]+\w+) ETA:([\dhms]+)\]'
    )
    
    match = pattern.search(line)
    if match:
        downloaded, total, percent, connections, speed, eta = match.groups()
        return {
            "downloaded": downloaded,
            "total": total,
            "percent": percent,
            "connections": connections,
            "speed": speed,
            "eta": eta
        }
    return None


async def run_aria2c(command: list, progress_callback=None) -> Tuple[bool, str]:
    """
    aria2c'yi subprocess olarak çalıştırır ve progress bilgisini parse eder
    
    Args:
        command: aria2c komut listesi
        progress_callback: Progress güncellemesi için callback fonksiyonu
    
    Returns:
        (başarılı mı, hata mesajı veya boş string)
    """
    try:
        LOGGER.info(f"aria2c komutu çalıştırılıyor: {' '.join(command)}")
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Progress takibi için stderr'i asenkron oku
        async def read_stderr():
            last_update = asyncio.get_event_loop().time()
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                    
                line = line.decode('utf-8', errors='ignore').strip()
                if line:
                    LOGGER.debug(f"aria2c stderr: {line}")
                    
                    # Progress parse et
                    progress_info = await parse_progress(line)
                    if progress_info and progress_callback:
                        current_time = asyncio.get_event_loop().time()
                        # Her 2 saniyede bir güncelle
                        if current_time - last_update >= 2:
                            await progress_callback(progress_info)
                            last_update = current_time
        
        # stderr okumayı başlat
        stderr_task = asyncio.create_task(read_stderr())
        
        # Process tamamlanmasını bekle
        returncode = await process.wait()
        
        # stderr okuma task'ini tamamla
        await stderr_task
        
        if returncode == 0:
            LOGGER.info("aria2c indirme başarıyla tamamlandı")
            return True, ""
        else:
            # Process zaten bitti, sadece return code'u kontrol et
            LOGGER.error(f"aria2c hata ile sonlandı (kod: {returncode})")
            return False, f"aria2c hata kodu: {returncode}"
            
    except Exception as e:
        LOGGER.error(f"aria2c çalıştırma hatası: {str(e)}")
        return False, str(e)
