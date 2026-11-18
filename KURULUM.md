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
ortalama sıra, haftalık grafik, hangi kelime kaçıncı sırada, yükselen/düşen/yeni çıkan kelimeler, bu dönem verisi gelmeyen kelimeler (son görüldüğü ay ve sırayla) ve sayfalar.
Karşılaştırma: önceki 28 gün, geçen yılın aynı dönemi ya da geçmişteki herhangi bir ay.
Veri ücretsiz Google Search Console'dan gelir (16 ay geriye). `seo_arsiv.json` her ayı saklar; 16 aydan eskiler de kaybolmaz.
Her gün 08:30'da güncellenir. Denemek için: `python3 seo.py --ornek` (uydurma veriyle).

Sayfada ayrıca: cihaz ve ülke kırılımı, "Fırsatlar" süzgeci (4–20. sıradaki çok aranan kelimeler), bir kelimeye tıklayınca
o kelimenin ay ay sıra geçmişi. Bing ve Yandex bağlıysa üç arama motoru karşılaştırması ve ayrı Bing / Yandex bölümleri.

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

### Bing ve Yandex'i bağlamak (isteğe bağlı, ücretsiz)
Bağlanınca SEO sayfasının altında "Google, Bing ve Yandex: nerede güçlüyüz, nerede ihtiyaç var?" bölümü dolar:
her kelimenin üç arama motorundaki sırası yan yana, "Güçlü" (1–3. sıra), "Fırsat" (4–20. sıra, çok aranan) ve
"Bing'de / Yandex'te / Google'da geride" etiketleriyle. Hangisi bağlı değilse o sütun boş kalır, sayfa yine çalışır.

#### Bing (yaklaşık 5 dakika)
1. https://www.bing.com/webmasters adresine Microsoft ya da Google hesabınızla girin.
   Siteleriniz orada yoksa **Search Console'dan içe aktar** düğmesiyle hepsini tek seferde ekleyin (doğrulama gerekmez).
2. Sağ üstteki dişli (**Ayarlar**) > **API Access** > **API Key** > anahtarı oluşturun ve kopyalayın.
3. GitHub deposunda **Settings > Secrets and variables > Actions > New repository secret**: ad `BING_ANAHTAR`, değer kopyaladığınız anahtar.

#### Yandex (yaklaşık 10 dakika)
1. https://webmaster.yandex.com adresine Yandex hesabınızla girin (yoksa ücretsiz açın).
   Her siteyi **Site ekle** ile ekleyin ve doğrulayın. En kolayı meta etiketi: bodrum.gen.tr, avsa.com ve izmir.gen.tr'de
   yönetim panelinde **Ayarlar > Sosyal medya ve Google > Yandex doğrulama** kutusu var, Yandex'in verdiği etiketi oraya yapıştırın.
   Diğer sitelerde Yandex'in verdiği küçük HTML dosyasını sitenin ana klasörüne yükleyin ya da DNS kaydını cPanel'den ekleyin.
2. https://oauth.yandex.com/client/new adresinde yeni uygulama oluşturun:
   ad `site-paneli`; platform olarak **Web services**; Redirect URI kutusuna `https://oauth.yandex.com/verification_code`;
   izinlerde **Yandex.Webmaster > Get information about the site (webmaster:hostinfo)** işaretli olsun. Kaydedin ve
   **ClientID** yazısını kopyalayın.
3. Tarayıcıda şu adresi açın (sonundaki ClientID yerine kopyaladığınızı yazın):
   `https://oauth.yandex.com/authorize?response_type=token&client_id=ClientID`
   **İzin ver** deyin; ekranda uzun bir anahtar (token) çıkar, kopyalayın.
4. GitHub deposunda yeni secret: ad `YANDEX_ANAHTAR`, değer bu anahtar.
5. Anahtar yaklaşık bir yıl geçerlidir; süresi dolunca SEO sayfasının üstünde "Yandex: anahtar geçersiz" uyarısı çıkar,
   3. adımı tekrarlayıp secret'ı güncellemeniz yeterli.

Anahtarları ekledikten sonra **Actions** sekmesinden "SEO geçmişini güncelle"yi elle çalıştırırsanız hemen görürsünüz;
çalıştırmazsanız ertesi sabah kendiliğinden gelir.

## Yeni adres eklemek
Dosyaları GitHub'da depo sayfasında dosyaya tıklayıp sağ üstteki kalem simgesiyle düzenleyin, alttan **Commit changes** deyin.
- **SEO sayfasına yeni site**: dosya düzenlemek gerekmez. Yeni sitenin Search Console mülküne (tercihen "Alan" mülkü)
  `seo-okuyucu@my-project-1520717025362.iam.gserviceaccount.com` adresini **Kısıtlı** izinle ekleyin. Ertesi sabah kendiliğinden gelir.
- **Takip edilecek özel kelime**: `kelimeler.txt` dosyasına `site | kelime` biçiminde satır ekleyin (ör. `bodrum.gen.tr | bodrum nöbetçi eczane`).
- **Ayakta mı / hız / SSL takibine yeni site**: `sites.txt` dosyasına `https://yenisite.com` satırı ekleyin.
- **Rakip takibine yeni rakip**: `rakipler.txt` dosyasına `https://rakip.com/sayfa | sizinsiteniz.com` satırı ekleyin.

## Sayfa sağlığı (saglik.html)
Her sabah (09:27 civarı) çalışır, ek ayar gerekmez (SEO ile aynı Google anahtarını kullanır):
- **Google dizini**: site haritasındaki sayfalar Search Console'un "URL denetimi" ile her gün parça parça (site başına 120 sayfa)
  sorulur; dizinde olmayanlar nedeniyle listelenir ("Tarandı ama dizine alınmadı" gibi). 14 günde bir yenilenir.
- **Site haritaları**: Search Console'a gönderilen haritalar, hata ve uyarı sayıları.
- **Telefon hızı**: Google PageSpeed ile ana sayfa ve en çok tıklanan 2 sayfa ölçülür (puan, yüklenme süresi, gerçek kullanıcı verisi).
  Ölçümler sık sık "kota" hatası verirse Google Cloud'da "PageSpeed Insights API"yi açıp bir API anahtarı oluşturun ve
  GitHub'a `PSI_ANAHTAR` adıyla ekleyin (ücretsiz).

## E-posta uyarıları (uyari.py)
Sayfa sağlığından hemen sonra çalışır. Kötüye giden bir şey varsa depoda bir **Issue** açar ve size atar; GitHub bunu
hesabınızın e-postasına gönderir. Uyarılar: tıklamalar %30'dan fazla düştü, önemli bir kelime 3 sıradan fazla geriledi
(kelimeler.txt'dekiler + en çok tıklanan 30 kelime), dizinde olmayan sayfa bir haftada 10'dan fazla arttı, site haritasında hata,
ana sayfa telefon hız puanı 50'nin altında. Aynı uyarı 7 gün tekrar gelmez. E-posta gelmiyorsa GitHub'da
Settings > Notifications > "Email" seçili olmalı.

## Bir kelimenin sırası neden değişti? (Kelime incele)
GitHub'da **Actions > "Kelime incele" > Run workflow**: siteyi ve kelimeyi yazın. Kayıtta (log) o kelimenin son 28 gün ve
önceki 28 gün için cihaz, ülke, sayfa ve gün gün sırası, tıklaması ve gösterimi yazar.
Not: Search Console'daki "ortalama sıra" her gösterimin ortalamasıdır. Masaüstü, başka ülkeler ya da sitenizin alt sıralardaki
başka sayfaları karışınca ortalama büyür; tıklamalar artıyorsa gerçek bir düşüş yoktur. Panel bu durumda "TIKLAMA ARTTI" yazar,
uyarı e-postası da yalnız sıra VE tıklama birlikte düştüğünde gelir.

Kelime ve sayfa sıraları yalnızca **Türkiye'deki** aramalardan hesaplanır (`seo.py` içinde `ULKE`). Bir dönemde 50'den az
gösterimi olan kelimede (`AZ_GOSTERIM`) değişim hesaplanmaz, "az veri" yazar; bu kelimeler "Düşenler/Yükselenler" listesine ve
uyarılara girmez. Kelimeye tıklayınca son 28 günün telefon ve bilgisayar sırası ayrı görünür. Az aranan bir kelimenin gerçek
sırası için Google'da kendiniz arayın (gizli pencerede, oturum kapalıyken).
