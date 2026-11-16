# Site izleme paneli

Tüm sitelerinizi tek sayfada gösterir: ayakta mı, yanıt süresi, uptime yüzdesi, SSL sertifikasının bitmesine kaç gün kaldığı.

## Dosyalar
- `sites.txt`: izlenecek siteler, her satıra bir adres
- `kontrol.py`: siteleri kontrol edip `index.html` üretir (yalnızca Python, kurulum gerekmez)
- `sablon.html`: panelin görünümü
- `.github/workflows/kontrol.yml`: GitHub'da her 15 dakikada bir otomatik çalıştırır

## Bilgisayarda denemek
    python3 kontrol.py
Sonra `index.html` dosyasını tarayıcıda açın.

## GitHub'da ücretsiz yayınlamak
1. GitHub'da yeni bir depo açın ve bu klasördeki dosyaları yükleyin.
2. Settings > Pages bölümünden "main" dalını seçin.
3. Actions sekmesinden "Siteleri kontrol et" iş akışını bir kez elle çalıştırın.
Panel `https://KULLANICI.github.io/DEPO/` adresinde açılır ve her 15 dakikada güncellenir.

## Renkler
- Yanıt: 800 ms altı yeşil, 2 sn altı sarı, üstü kırmızı
- SSL: 30 günden az sarı, 7 günden az kırmızı

## Güncelleme önerileri
Her kontrolde site için öneri listesi de çıkar ve kartın altında gösterilir (Acil / Önemli / İyileştirme):
- SSL bitişi yaklaşıyor mu, HTTPS ve http→https yönlendirmesi var mı
- WordPress sürümü eski mi (wordpress.org'daki son sürümle karşılaştırır)
- PHP sürümü destek dışı mı, eski jQuery var mı
- Sunucu/PHP sürümü dışarıya görünüyor mu, güvenlik başlıkları eksik mi
- www / www'siz adres yönlendirmesi, yavaş yanıt, mobil uyum etiketi, meta açıklama, eski telif yılı

## Rakip takibi
`rakipler.txt` dosyasına rakip siteleri yazın (`https://rakip.com | avsa.com` biçiminde). `rakip.py` her gün 07:00'de çalışır ve `rakipler.html` sayfasında şunları listeler:
- Yeni eklenen sayfalar (başlığıyla birlikte)
- Güncellenen sayfalar (site haritasındaki tarihe göre)
- Kaldırılan sayfalar
- Ana sayfadaki değişiklikler (yeni/kaldırılan başlıklar, sayfa başlığı)
İlk tarama yalnızca mevcut durumu kaydeder, değişiklikler ikinci taramadan itibaren görünür.

## SEO geçmişi (seo.html)
Her sitenin Google'daki durumunu "eskiden nasıldı, şimdi nasıl" diye gösterir: tıklama, gösterim, tıklama oranı,
ortalama sıra, haftalık grafik, hangi kelime kaçıncı sırada, yükselen/düşen/yeni çıkan/kaybolan kelimeler ve sayfalar.
Karşılaştırma: önceki 28 gün, geçen yılın aynı dönemi ya da geçmişteki herhangi bir ay.
Veri ücretsiz Google Search Console'dan gelir (16 ay geriye). `seo_arsiv.json` her ayı saklar; 16 aydan eskiler de kaybolmaz.
Her gün 08:30'da güncellenir. Denemek için: `python3 seo.py --ornek` (uydurma veriyle).

### Bir kerelik kurulum (yaklaşık 15 dakika)
1. https://console.cloud.google.com adresine Gmail hesabınızla girin, üstten **yeni proje** açın (adı: site-paneli).
2. Arama kutusuna **Google Search Console API** yazın, açılan sayfada **Etkinleştir**'e basın.
3. Sol menüden **IAM ve Yönetici > Hizmet hesapları > Hizmet hesabı oluştur**. Ad: seo-okuyucu. Rol vermeden **Bitti**.
4. Oluşan hesaba tıklayın > **Anahtarlar > Anahtar ekle > Yeni anahtar > JSON**. Bir .json dosyası iner (şifre gibi saklayın).
   Hesabın e-posta adresini kopyalayın (seo-okuyucu@....iam.gserviceaccount.com).
5. https://search.google.com/search-console adresinde her site için: **Ayarlar > Kullanıcılar ve izinler > Kullanıcı ekle**,
   kopyaladığınız e-postayı yapıştırın, izin **Kısıtlı** olsun. (Yalnızca okuyabilir, hiçbir şeyi değiştiremez.)
6. GitHub'daki panel deposunda **Settings > Secrets and variables > Actions > New repository secret**:
   Ad `GSC_ANAHTAR`, değer olarak indirdiğiniz .json dosyasının içindeki metnin tamamı.
7. **Actions** sekmesinden "SEO geçmişini güncelle" iş akışını bir kez elle çalıştırın. İlk çalışma 16 ayı arşivler (birkaç dakika).

Not: GitHub Pages ücretsiz planda yalnızca herkese açık depoda çalışır; o zaman bu sayfadaki rakamları adresi bilen herkes görebilir
(sayfa Google'a kapalıdır). İstemezseniz depoyu gizli tutup `seo.html`'i indirip bilgisayarınızda açabilirsiniz.
