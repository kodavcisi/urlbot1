# Pixeldrain İndirme Modülü

## Özellikler

Bu modül, Pixeldrain linklerini özel bir sistemle indirir:

- ✅ **Otomatik Tespit**: Pixeldrain URL'leri otomatik olarak tespit edilir
- ✅ **aria2c ile Hızlı İndirme**: 16 paralel bağlantı ile maksimum hız
- ✅ **Proxy Desteği**: IP rotasyonu ile limit bypass
- ✅ **Gerçek Zamanlı Progress**: Kullanıcıya detaylı ilerleme bilgisi
- ✅ **Otomatik Yeniden Deneme**: Başarısız indirmelerde 3 kez deneme

## Konfigürasyon

### Ortam Değişkenleri

`.env` dosyanıza ekleyin:

```bash
# Pixeldrain ayarları
PIXELDRAIN_USE_PROXY=True                    # Proxy kullanımı (True/False)
PIXELDRAIN_AUTO_PROXY=True                   # Otomatik free proxy çekme (True/False)
PIXELDRAIN_PROXY_LIST=http://proxy1:8080,http://proxy2:8080  # Manuel proxy listesi (virgülle ayrılmış)
PIXELDRAIN_ARIA2C_CONNECTIONS=16             # Paralel bağlantı sayısı (varsayılan: 16)
```

### Varsayılan Değerler

Ortam değişkenleri tanımlanmazsa, şu varsayılanlar kullanılır:

- `PIXELDRAIN_USE_PROXY`: True
- `PIXELDRAIN_AUTO_PROXY`: True
- `PIXELDRAIN_PROXY_LIST`: [] (boş liste)
- `PIXELDRAIN_ARIA2C_CONNECTIONS`: 16

## Kullanım

Bot'a herhangi bir Pixeldrain linki gönderin:

```
https://pixeldrain.com/u/XXXXXXXX
```

Bot otomatik olarak:

1. Pixeldrain linkini tespit eder
2. Proxy sistemi kurar (aktifse)
3. aria2c ile dosyayı indirir
4. İndirme ilerlemesini gösterir
5. Dosyayı Telegram'a yükler
6. Geçici dosyayı temizler

## Progress Görüntüsü

İndirme sırasında şu bilgiler gösterilir:

```
📥 İndiriliyor...

📊 Boyut: 8.5GiB
⬇️ İndirilen: 2.1GiB (24%)
⚡ Hız: 15.3MiB/s
⏱ Kalan Süre: 7m23s
🔗 Bağlantı: 16

━━━━━━░░░░░░░░░░░░░░░░░░ 24%
```

## Proxy Sistemi

### Manuel Proxy Listesi

```bash
PIXELDRAIN_PROXY_LIST=http://proxy1.example.com:8080,http://proxy2.example.com:3128
```

### Otomatik Free Proxy

`PIXELDRAIN_AUTO_PROXY=True` olduğunda, sistem otomatik olarak free proxy'leri çeker ve kullanır.

### Proxy Rotasyonu

- Her indirmede farklı proxy kullanılır
- Başarısız proxy'ler işaretlenir ve atlanır
- Limit hatası alındığında otomatik yeni proxy denenimi yapılır
- Maksimum 3 deneme yapılır

## Limit Bypass Stratejileri

Modül şu stratejileri kullanır:

1. **IP Rotasyonu**: Her indirmede farklı proxy
2. **User-Agent Rotasyonu**: Her istekte farklı browser user-agent
3. **Referer Header**: Pixeldrain.com referrer eklenir
4. **Otomatik Retry**: Başarısız denemelerde otomatik yeniden deneme

## Hata Yönetimi

- **Proxy Hatası**: Otomatik olarak başka proxy denenir
- **aria2c Crash**: Hata mesajı gösterilir
- **Dosya Boyutu Aşımı**: Telegram limiti aşılırsa uyarı verilir (4.2GB)
- **Timeout**: PROCESS_MAX_TIMEOUT değeri kullanılır

## Teknik Detaylar

### Modüller

1. **`plugins/pixeldrain_downloader.py`**: Ana indirme modülü
   - `is_pixeldrain_url()`: URL kontrolü
   - `extract_pixeldrain_id()`: Dosya ID çıkarma
   - `pixeldrain_download()`: Ana indirme fonksiyonu

2. **`functions/aria2c_helper.py`**: aria2c yardımcıları
   - `build_aria2c_command()`: Komut oluşturma
   - `run_aria2c()`: Subprocess yönetimi
   - `parse_progress()`: Progress parsing

3. **`functions/proxy_manager.py`**: Proxy yönetimi
   - `ProxyManager`: Ana sınıf
   - `get_free_proxies()`: Free proxy çekme
   - `get_next_proxy()`: Proxy rotasyonu

### Entegrasyon

`plugins/ytdlp_trigger.py` dosyasında, normal URL işlemeden önce Pixeldrain kontrolü yapılır:

```python
if is_pixeldrain_url(message_text):
    await pixeldrain_download(bot, update, message_text)
    return
```

## Önemli Notlar

- ✅ **Mevcut kod etkilenmez**: Sadece Pixeldrain linkleri özel modüle gider
- ✅ **aria2 gereklidir**: Dockerfile'da zaten yüklü
- ✅ **Async/await pattern**: Kod tamamen asenkron çalışır
- ✅ **Logging**: Tüm işlemler LOGGER ile kayıt edilir
- ✅ **Türkçe mesajlar**: Kullanıcı mesajları Türkçe

## Bağımlılıklar

`requirements.txt`'e eklenen paketler:

- `aiohttp-socks`: SOCKS proxy desteği
- `PySocks`: Proxy bağlantıları
- `fake-useragent`: User-agent rotasyonu

## Test

Pixeldrain URL örneği ile test edin:

```
https://pixeldrain.com/u/TEST123
```

Bot şu adımları takip eder:

1. URL'yi tespit eder
2. "Pixeldrain linki tespit edildi" mesajı gösterir
3. Proxy sistemi hazırlanır
4. aria2c ile indirme başlar
5. Progress her 2 saniyede güncellenir
6. Dosya Telegram'a yüklenir

## Sorun Giderme

### Proxy çalışmıyor

```bash
PIXELDRAIN_USE_PROXY=False  # Proxy'siz dene
```

### İndirme başarısız

- Dosya boyutunu kontrol edin (>4.2GB Telegram limiti)
- aria2c kurulu olduğundan emin olun
- Log dosyasını kontrol edin

### Progress güncellenmesi yok

- aria2c çıktısının düzgün parse edildiğinden emin olun
- LOGGER'ı DEBUG seviyesine alın

## Geliştirme

Modülü geliştirmek için:

1. `functions/aria2c_helper.py`: aria2c komut seçeneklerini özelleştir
2. `functions/proxy_manager.py`: Farklı proxy kaynakları ekle
3. `plugins/pixeldrain_downloader.py`: Progress gösterimini özelleştir
