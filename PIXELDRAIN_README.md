# Pixeldrain İndirme Modülü

## Özellikler

Bu modül, Pixeldrain linklerini özel bir sistemle indirir:

- ✅ **Otomatik Tespit**: Pixeldrain URL'leri otomatik olarak tespit edilir
- ✅ **aria2c ile Hızlı İndirme**: 16 paralel bağlantı ile maksimum hız
- ✅ **API Kota Kontrolü**: Her indirme öncesi gerçek API kota kontrolü
- ✅ **Otomatik Hesap Geçişi**: Kota dolduğunda otomatik hesap değişimi
- ✅ **Gerçek Zamanlı Progress**: Kullanıcıya detaylı ilerleme bilgisi
- ✅ **Otomatik Yeniden Deneme**: Başarısız indirmelerde 3 kez deneme

## Konfigürasyon

### Ortam Değişkenleri

`.env` dosyanıza ekleyin:

```bash
# Pixeldrain ayarları
PIXELDRAIN_ARIA2C_CONNECTIONS=16             # Paralel bağlantı sayısı (varsayılan: 16)
```

### Varsayılan Değerler

Ortam değişkenleri tanımlanmazsa, şu varsayılanlar kullanılır:

- `PIXELDRAIN_ARIA2C_CONNECTIONS`: 16

## Kullanım

Bot'a herhangi bir Pixeldrain linki gönderin:

```
https://pixeldrain.com/u/XXXXXXXX
```

Bot otomatik olarak:

1. Pixeldrain linkini tespit eder
2. Dosya boyutunu kontrol eder
3. API'den tüm hesapların gerçek kota durumunu sorgular
4. En uygun hesabı seçer (yeterli kotası olmalı)
5. aria2c ile dosyayı indirir
6. İndirme ilerlemesini gösterir
7. Dosyayı Telegram'a yükler
8. İndirilen miktarı hesap kotasından düşer
9. Geçici dosyayı temizler

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

## API Kota Kontrolü

### Gerçek Zamanlı API Kontrolü

Her indirme öncesi sistem:

1. **API'den gerçek kota sorgular**: `https://pixeldrain.com/api/user` endpoint'i kullanılır
2. **Günlük limit**: Her hesap için 6GB (6,442,450,944 bytes)
3. **Otomatik hesap seçimi**: Yeterli kotası olan hesaplar arasından en uygun olanı seçilir
4. **Kota güncelleme**: İndirme tamamlandığında kullanılan miktar hesaba kaydedilir

### Hesap Seçim Stratejisi

Sistem akıllı hesap seçimi yapar:

1. **Küçük dosyalar (<2GB)**: En az kotası olan uygun hesabı seçer (kota tasarrufu)
2. **Büyük dosyalar (≥2GB)**: En çok kotası olan uygun hesabı seçer (büyük indirmeyi garantiler)
3. **Kota kontrolü**: Tüm hesapların gerçek kotaları API'den kontrol edilir

### Otomatik Hesap Geçişi

- Seçilen hesabın kotası yetersizse, bir sonraki uygun hesaba otomatik geçiş yapılır
- Tüm hesapların kotası doluysa kullanıcıya bilgi verilir
- Her hesabın durumu kullanıcıya gösterilir

## Hata Yönetimi

- **Kota Yetersiz**: Tüm hesapların kotası doluysa kullanıcıya bilgi verilir
- **API Hatası**: API'den kota alınamazsa local bilgi kullanılır
- **aria2c Crash**: Hata mesajı gösterilir ve maksimum 3 kez yeniden denenir
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

3. **`functions/pixeldrain_accounts.py`**: Hesap yönetimi
   - `PixeldrainAccount`: Hesap bilgisi dataclass
   - `PixeldrainAccountManager`: Hesap yönetici sınıfı
   - `get_account_quota()`: API'den gerçek kota sorgulama
   - `update_account_quota()`: Hesap kotasını güncelleme
   - `select_best_account()`: En uygun hesabı seçme
   - `mark_quota_used()`: Kullanılan kotayı kaydetme

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

### Tüm hesapların kotası dolmuş

Sistem size tüm hesapların durumunu gösterecektir:

```
❌ Tüm hesapların günlük kotası dolmuş!

📊 Pixeldrain Hesap Durumu:
1. noelledark
   Kalan: 0.00GB / 6GB (0%)
2. johnsnow33
   Kalan: 0.50GB / 6GB (8%)
...
```

Çözüm: Kotalar günlük sıfırlanır, ertesi gün tekrar deneyin.

### API bağlantısı başarısız

Eğer API'ye bağlanılamazsa, sistem local kota bilgisini kullanmaya devam eder ancak tam doğru olmayabilir.

### İndirme başarısız

- Dosya boyutunu kontrol edin (>4.2GB Telegram limiti)
- aria2c kurulu olduğundan emin olun
- Log dosyasını kontrol edin
- API key'lerin geçerli olduğunu kontrol edin

### Progress güncellenmesi yok

- aria2c çıktısının düzgün parse edildiğinden emin olun
- LOGGER'ı DEBUG seviyesine alın

## Geliştirme

Modülü geliştirmek için:

1. `functions/aria2c_helper.py`: aria2c komut seçeneklerini özelleştir
2. `functions/pixeldrain_accounts.py`: Yeni hesap ekle veya kota stratejisini değiştir
3. `plugins/pixeldrain_downloader.py`: Progress gösterimini özelleştir

## API Detayları

### Pixeldrain API Endpoint

```
GET https://pixeldrain.com/api/user
Authorization: Basic <base64_encoded_api_key>
```

### Örnek API Yanıtı

```json
{
  "bandwidth_remaining": 5368709120,
  "bandwidth_limit": 6442450944,
  "subscription": "free",
  ...
}
```

- `bandwidth_remaining`: Kalan kota (bytes)
- `bandwidth_limit`: Toplam günlük limit (6GB = 6,442,450,944 bytes)

### Kimlik Doğrulama

API key, base64 ile encode edilip Basic auth formatında gönderilir:

```python
auth_b64 = base64.b64encode(api_key.encode()).decode()
headers = {"Authorization": f"Basic {auth_b64}"}
```
