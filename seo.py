#!/usr/bin/env python3
"""SEO geçmişi: Google Search Console'dan sitelerin anahtar kelime sıralarını,
tıklama ve gösterimlerini çeker; "eskiden nasıldı, şimdi nasıl" sayfası (seo.html) üretir.

- Search Console 16 ay geriye veri tutar. Bu betik her ayın özetini seo_arsiv.json'a
  yazar, böylece 16 aydan eski aylar da kaybolmaz.
- Kimlik: GSC_ANAHTAR ortam değişkeni (hizmet hesabı JSON'u) ya da gsc_anahtar.json dosyası.
- İsteğe bağlı: BING_ANAHTAR (Bing Webmaster API anahtarı), YANDEX_ANAHTAR (Yandex Webmaster OAuth anahtarı).
- Denemek için: python3 seo.py --ornek   (Google'a bağlanmaz, uydurma veriyle sayfayı gösterir)
"""
import json, os, re, sys, math, random, html
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

KOK = os.path.dirname(os.path.abspath(__file__))
ARSIV = os.path.join(KOK, "seo_arsiv.json")
FIRSAT_CSV = os.path.join(KOK, "firsatlar.csv")
KELIME_DOSYASI = os.path.join(KOK, "kelimeler.txt")
API = "https://searchconsole.googleapis.com/webmasters/v3"
ARSIV_KELIME = 5000   # her ay saklanan en fazla kelime
ARSIV_SAYFA = 2000    # her ay saklanan en fazla sayfa
DONEM_KELIME = 25000  # son 28 gün / önceki 28 gün / geçen yıl için okunan en fazla kelime
DONEM_SAYFA = 5000    # (eskiden 1000'di: az aranan marka kelimeleri listeye girmiyor, yanlışlıkla "kayboldu" görünüyordu)
ARSIV_SURUM = 3       # arşivdeki aylar bu sürümden eskiyse yeniden okunur (3: kelime/sayfa sıraları yalnız Türkiye)
ULKE = "tur"          # kelime ve sayfa sıraları yalnız bu ülkedeki aramalardan (yurt dışı aramalar ortalamayı bozuyordu)
AZ_GOSTERIM = 50      # bundan az gösterimi olan kelimenin ortalama sırası güvenilmez (değişim hesaplanmaz)
SAYFADA_KELIME = 1500 # sayfada gösterilen en fazla kelime (izlenenler ve tıklama alanlar hariç)
SAYFADA_SAYFA = 400
GECIKME = 3           # Search Console verisi 2-3 gün geriden gelir
AY_ADLARI = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
             "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


# ---------------------------------------------------------------- Google bağlantısı
class Google:
    def __init__(self):
        metin = os.environ.get("GSC_ANAHTAR", "").strip()
        yol = os.path.join(KOK, "gsc_anahtar.json")
        if not metin and os.path.exists(yol):
            metin = open(yol, encoding="utf-8").read()
        if not metin:
            sys.exit("Search Console anahtarı bulunamadı. KURULUM.md'deki 'SEO geçmişi' adımlarına bakın.\n"
                     "Uydurma veriyle denemek için: python3 seo.py --ornek")
        try:
            from google.oauth2 import service_account
            import google.auth.transport.requests as gtr
        except ImportError:
            sys.exit("Önce şunu çalıştırın: pip install google-auth requests")
        try:
            bilgi = json.loads(metin.lstrip("\ufeff"))
            assert isinstance(bilgi, dict) and bilgi.get("type") == "service_account"
        except Exception:
            sys.exit("GSC_ANAHTAR geçersiz: indirilen .json dosyasının içindeki yazının TAMAMI yapıştırılmalı "
                     "({ ile başlar, } ile biter; içinde \"type\": \"service_account\" yazar).")
        self.kimlik = service_account.Credentials.from_service_account_info(
            bilgi, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
        self._istek = gtr.Request()
        self.eposta = self.kimlik.service_account_email

    def _cagir(self, yol, govde=None):
        if not self.kimlik.valid:
            self.kimlik.refresh(self._istek)
        veri = json.dumps(govde).encode() if govde is not None else None
        r = Request(API + yol, data=veri, method="POST" if veri else "GET", headers={
            "Authorization": "Bearer " + self.kimlik.token, "Content-Type": "application/json"})
        try:
            with urlopen(r, timeout=60) as y:
                return json.load(y)
        except HTTPError as e:
            raise RuntimeError(f"Search Console hatası {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")

    def siteler(self):
        out = self._cagir("/sites").get("siteEntry", [])
        return [s["siteUrl"] for s in out if s.get("permissionLevel") != "siteUnverifiedUser"]

    def sorgu(self, site, bas, bit, boyut, limit=1000, regex=None, ulke=None):
        boyutlar = boyut if isinstance(boyut, list) else ([boyut] if boyut else [])
        govde = {"startDate": bas.isoformat(), "endDate": bit.isoformat(), "dimensions": boyutlar, "type": "web"}
        suzgec = []
        if regex:
            suzgec.append({"dimension": "query", "operator": "includingRegex", "expression": regex})
        if ulke:
            suzgec.append({"dimension": "country", "operator": "equals", "expression": ulke})
        if suzgec:
            govde["dimensionFilterGroups"] = [{"filters": suzgec}]
        satirlar = []
        while len(satirlar) < limit:                # API tek seferde en çok 25000 satır verir
            parca = min(25000, limit - len(satirlar))
            govde.update(rowLimit=parca, startRow=len(satirlar))
            yeni = self._cagir(f"/sites/{quote(site, safe='')}/searchAnalytics/query", govde).get("rows", [])
            satirlar += yeni
            if len(yeni) < parca:
                break
        return satirlar


# ---------------------------------------------------------------- deneme verisi
class Ornek:
    """Google'a bağlanmadan sayfayı görmek için tutarlı uydurma veri üretir."""
    SITELER = {
        "sc-domain:bodrum.gen.tr": ["bodrum nöbetçi eczane", "bodrum dolmuş saatleri", "bodrum otelleri", "gümbet otelleri",
                                    "bodrum hava durumu", "bodrum deniz suyu sıcaklığı", "bitez plajı", "bodrum havaş saatleri",
                                    "yalıkavak restoranları", "bodrum ücretsiz plajlar", "leros feribot", "bodrum etkinlikleri",
                                    "turgutreis eczane", "bodrum taksi", "bodrum pansiyon", "gümüşlük gezilecek yerler"],
        "sc-domain:avsa.com": ["avşa otelleri", "avşa feribot saatleri", "avşa adası", "avşa pansiyon", "avşa ido",
                               "avşa denize sıfır otel", "avşa nasıl gidilir", "avşa minibüs", "avşa her şey dahil"],
        "sc-domain:izmir.gen.tr": ["izmir nöbetçi eczane", "izmir su kesintisi", "izmir elektrik kesintisi", "izmir son depremler",
                                   "izmir semt pazarları", "eshot saatleri", "izmir akaryakıt fiyatları", "çeşme otelleri"],
        "sc-domain:erdek.com": ["erdek otelleri", "erdek pansiyon", "erdek plajları", "erdek feribot", "erdek gezilecek yerler"],
        "sc-domain:tatil.gen.tr": ["tatil yerleri", "karadeniz turu", "kapadokya otelleri", "ucuz tatil", "ege tatil"],
    }

    def __init__(self):
        self.eposta = "ornek@deneme"

    def siteler(self):
        return list(self.SITELER)

    def _kelimeler(self, site):
        kel = self.SITELER[site]
        ek = [f"{k.split()[0]} {s}" for k in kel[:6] for s in ("fiyat", "yorum", "harita", "2026", "en iyi")]
        return kel + ek

    def _deger(self, site, kelime, gun):
        r = random.Random(f"{site}|{kelime}")
        taban = r.uniform(1.5, 35)
        egim = r.uniform(-0.02, 0.03)          # günde pozisyon değişimi
        yas = (date.today() - gun).days
        sira = max(1.0, taban + egim * yas + math.sin(yas / 9 + r.random() * 6) * 1.2)
        hacim = r.uniform(20, 900) * (1.6 if gun.month in (6, 7, 8) else 1.0)
        if yas > r.uniform(200, 500):          # bazı kelimeler sonradan çıktı
            return None
        gos = hacim * max(0.05, 1.3 - sira / 25)
        tik = gos * max(0.002, 0.32 / sira)
        return sira, tik, gos

    def sorgu(self, site, bas, bit, boyut, limit=1000, regex=None, ulke=None):
        if isinstance(boyut, list):                 # [kelime, cihaz]: telefon biraz daha iyi, bilgisayar biraz daha kötü
            out = []
            for r_ in self.sorgu(site, bas, bit, boyut[0], limit, regex, ulke):
                for cihaz, pay, fark in (("MOBILE", .7, -1.2), ("DESKTOP", .3, 2.5)):
                    out.append({"keys": r_["keys"] + [cihaz], "clicks": round(r_["clicks"] * pay),
                                "impressions": round(r_["impressions"] * pay), "position": max(1, r_["position"] + fark)})
            return out
        gunler = [bas + timedelta(d) for d in range((bit - bas).days + 1)]
        if boyut == "date":
            out = []
            for g in gunler:
                t = [v for k in self._kelimeler(site) if (v := self._deger(site, k, g))]
                gos = sum(v[2] for v in t) / 3
                out.append({"keys": [g.isoformat()], "clicks": round(sum(v[1] for v in t) / 3),
                            "impressions": round(gos), "position": sum(v[0] * v[2] for v in t) / 3 / max(gos, 1)})
            return out
        if boyut in ("device", "country"):
            rr = random.Random(f"{site}{boyut}{bas}")
            adlar = ["MOBILE", "DESKTOP", "TABLET"] if boyut == "device" else ["tur", "deu", "gbr", "nld", "rus", "usa"]
            pay = [0.7, 0.27, 0.03] if boyut == "device" else [0.86, 0.05, 0.03, 0.02, 0.02, 0.02]
            return [{"keys": [k], "clicks": round(900 * p_ * rr.uniform(.8, 1.2)), "impressions": round(30000 * p_ * rr.uniform(.8, 1.2)),
                     "position": rr.uniform(6, 14)} for k, p_ in zip(adlar, pay)]
        adaylar = self._kelimeler(site)
        if boyut == "page":
            ad = site.split(":")[-1]
            adaylar = [f"https://www.{ad}/" + re.sub(r"[^a-z0-9]+", "-", k.replace("ı", "i").replace("ş", "s")
                       .replace("ü", "u").replace("ö", "o").replace("ç", "c").replace("ğ", "g")) for k in adaylar]
        out = []
        for k in adaylar:
            if regex and not re.fullmatch(regex, k):
                continue
            t = [v for g in gunler[::3] if (v := self._deger(site, k, g))]
            if not t:
                continue
            gos = sum(v[2] for v in t) / len(t) * len(gunler) / 30
            out.append({"keys": [k], "clicks": round(sum(v[1] for v in t) / len(t) * len(gunler) / 30),
                        "impressions": round(gos), "position": sum(v[0] for v in t) / len(t)})
        return sorted(out, key=lambda r: -r["impressions"])[:limit]


# ---------------------------------------------------------------- yardımcılar
def ad(site):
    return re.sub(r"^(sc-domain:|https?://)(www\.)?", "", site).rstrip("/")

def tablo(satirlar):
    """API satırlarını {anahtar: [sıra, tıklama, gösterim]} yapar."""
    return {r["keys"][0]: [round(r["position"], 1), int(r["clicks"]), int(r["impressions"])] for r in satirlar}

def ay_araligi(ay):
    y, m = map(int, ay.split("-"))
    bas = date(y, m, 1)
    bit = (date(y + m // 12, m % 12 + 1, 1)) - timedelta(1)
    return bas, bit

def ay_adi(ay):
    y, m = map(int, ay.split("-"))
    return f"{AY_ADLARI[m - 1]} {y}"

def izlenen_kelimeler():
    """kelimeler.txt: 'bodrum.gen.tr | bodrum nöbetçi eczane' biçiminde satırlar."""
    out = {}
    if os.path.exists(KELIME_DOSYASI):
        for s in open(KELIME_DOSYASI, encoding="utf-8"):
            s = s.strip()
            if s and not s.startswith("#") and "|" in s:
                site, _, kel = (p.strip() for p in s.partition("|"))
                out.setdefault(ad(site), []).append(kel.lower())
    return out

def tekillestir(siteler):
    """Aynı site hem alan adı hem adres öneki mülkü olarak ekliyse alan adı mülkünü al."""
    secilen = {}
    for s in siteler:
        a = ad(s)
        if a not in secilen or s.startswith("sc-domain:"):
            secilen[a] = s
    return sorted(secilen.values(), key=ad)


# ---------------------------------------------------------------- veri toplama
def site_verisi(g, site, arsiv, izlenen):
    son = date.today() - timedelta(GECIKME)
    ilk = son - timedelta(486)                      # Search Console sınırı ~16 ay
    a = arsiv.setdefault(ad(site), {"aylar": {}})
    if a.get("mulk") != site:                       # mülk değiştiyse (ör. Alan mülkü eklendi) arşivi yeniden kur
        a["aylar"], a["mulk"] = {}, site

    # 1) Günlük toplamlar (grafik ve aylık özet)
    gunluk = g.sorgu(site, ilk, son, "date", 25000)
    gunler = {r["keys"][0]: r for r in gunluk}

    # 2) Tamamlanmış aylar: arşivde yoksa (ya da eksikse) Search Console'dan al
    ay = date(ilk.year, ilk.month, 1)
    if ay < ilk:
        ay = (ay + timedelta(32)).replace(day=1)    # ilk ay yarımsa atla
    while True:
        bas, bit = ay_araligi(ay.strftime("%Y-%m"))
        if bit > son:
            break
        anahtar = ay.strftime("%Y-%m")
        if (anahtar not in a["aylar"] or not a["aylar"][anahtar]["toplam"][2]      # boş ay tekrar denenir
                or a["aylar"][anahtar].get("surum", 1) < ARSIV_SURUM):           # eski (1000 satırlık) arşiv yenilenir
            satir = [gunler[d.isoformat()] for d in (bas + timedelta(i) for i in range((bit - bas).days + 1))
                     if d.isoformat() in gunler]
            gos = sum(r["impressions"] for r in satir)
            a["aylar"][anahtar] = {
                "toplam": [round(sum(r["position"] * r["impressions"] for r in satir) / gos, 1) if gos else None,
                           int(sum(r["clicks"] for r in satir)), int(gos)],
                "kelimeler": tablo(g.sorgu(site, bas, bit, "query", ARSIV_KELIME, ulke=ULKE)),
                "sayfalar": tablo(g.sorgu(site, bas, bit, "page", ARSIV_SAYFA, ulke=ULKE)),
                "surum": ARSIV_SURUM,
            }
            if izlenen:
                a["aylar"][anahtar]["kelimeler"].update(tablo(g.sorgu(site, bas, bit, "query", 500, izlenen, ULKE)))
        ay = (ay + timedelta(32)).replace(day=1)

    # 3) Karşılaştırılacak dönemler: son 28 gün, önceki 28 gün, geçen yıl aynı 28 gün + arşivdeki aylar
    donemler = []
    def ekle(kod, etiket, bas, bit):
        k = tablo(g.sorgu(site, bas, bit, "query", DONEM_KELIME, ulke=ULKE))
        if izlenen:
            k.update(tablo(g.sorgu(site, bas, bit, "query", 500, izlenen, ULKE)))
        satir = [r for d, r in gunler.items() if bas.isoformat() <= d <= bit.isoformat()]
        gos = sum(r["impressions"] for r in satir)
        toplam = [round(sum(r["position"] * r["impressions"] for r in satir) / gos, 1) if gos else None,
                  int(sum(r["clicks"] for r in satir)), int(gos)]
        donemler.append({"kod": kod, "ad": etiket, "aralik": f"{bas:%d.%m.%Y} – {bit:%d.%m.%Y}", "gun": (bit - bas).days + 1,
                         "toplam": toplam, "kelimeler": k,
                         "sayfalar": tablo(g.sorgu(site, bas, bit, "page", DONEM_SAYFA, ulke=ULKE))})
    ekle("simdi", "Son 28 gün", son - timedelta(27), son)
    ekle("once", "Önceki 28 gün", son - timedelta(55), son - timedelta(28))
    if son - timedelta(27 + 364) >= ilk:
        ekle("gecen_yil", "Geçen yıl aynı dönem", son - timedelta(27 + 364), son - timedelta(364))
    for anahtar in sorted(a["aylar"], reverse=True):
        m = a["aylar"][anahtar]
        if not m["toplam"][2]:
            continue                                # sitenin verisi olmayan ay
        bas, bit = ay_araligi(anahtar)
        donemler.append({"kod": anahtar, "ad": ay_adi(anahtar), "aralik": f"{bas:%d.%m.%Y} – {bit:%d.%m.%Y}",
                         "gun": (bit - bas).days + 1, "toplam": m["toplam"],
                         "kelimeler": m["kelimeler"], "sayfalar": m["sayfalar"]})

    # Cihaz ve ülke kırılımı (son 28 gün ve önceki 28 gün)
    def kirilim(boyut):
        a_, b_ = son - timedelta(27), son - timedelta(55)
        simdi = tablo(g.sorgu(site, a_, son, boyut, 10))
        once = tablo(g.sorgu(site, b_, son - timedelta(28), boyut, 50))
        return [[k, v, once.get(k)] for k, v in simdi.items()]
    cihaz, ulke = kirilim("device"), kirilim("country")

    # 4) Haftalık grafik serisi
    haftalar = {}
    for d, r in sorted(gunler.items()):
        gun = date.fromisoformat(d)
        h = (gun - timedelta(gun.weekday())).isoformat()
        x = haftalar.setdefault(h, [0, 0, 0.0, 0])
        x[0] += r["clicks"]; x[1] += r["impressions"]; x[2] += r["position"] * r["impressions"]; x[3] += 1
    seri = [[h, int(x[0]), int(x[1]), round(x[2] / x[1], 1) if x[1] else None] for h, x in haftalar.items()]
    if seri and haftalar[seri[-1][0]][3] < 7:
        seri.pop()                                  # yarım kalan son hafta grafiği yanıltmasın
    seri_tur = "hafta"
    if len(seri) < 8:                               # yeni site: günlük göster
        seri_tur = "gun"
        seri = [[d, int(r["clicks"]), int(r["impressions"]), round(r["position"], 1)] for d, r in sorted(gunler.items())]

    # 5) Sayfada gösterilecek kelime/sayfa listesi (her biri dönemlere göre [sıra, tık, gös])
    def liste(tur, adet):
        simdi, once = donemler[0][tur], donemler[1][tur]
        secim = sorted(simdi, key=lambda k: -simdi[k][2])[:adet]
        secim += [k for k in sorted(once, key=lambda k: -once[k][2])[:adet // 3] if k not in simdi]
        secim += [k for k, v in list(simdi.items()) + list(once.items()) if v[1] > 0]   # tıklama alan her kelime
        if tur == "kelimeler":
            secim += [k for k in izlenen_liste if k not in secim]
        return [[k] + [d[tur].get(k) for d in donemler] for k in dict.fromkeys(secim)]
    izlenen_liste = izlenen_kelimeler().get(ad(site), [])
    kelime_listesi = liste("kelimeler", SAYFADA_KELIME)

    # Kelimelerin telefon / bilgisayar sırası (son 28 gün, Türkiye): {kelime: {"m": [sıra, gös], "d": [sıra, gös]}}
    gosterilen = {k[0] for k in kelime_listesi}
    cihazlar = {}
    for r_ in g.sorgu(site, son - timedelta(27), son, ["query", "device"], DONEM_KELIME * 2, ulke=ULKE):
        k, c = r_["keys"]
        if k in gosterilen and c in ("MOBILE", "DESKTOP"):
            cihazlar.setdefault(k, {})["m" if c == "MOBILE" else "d"] = [round(r_["position"], 1), int(r_["impressions"])]

    return {
        "site": ad(site), "mulk": site, "seri": seri, "seri_tur": seri_tur, "son_veri": son.isoformat(),
        "donemler": [{k: d[k] for k in ("kod", "ad", "aralik", "gun", "toplam")} for d in donemler],
        "kelimeler": kelime_listesi, "kelime_cihaz": cihazlar, "sira_ulke": ULKE, "az_gosterim": AZ_GOSTERIM,
        "sayfalar": liste("sayfalar", SAYFADA_SAYFA),
        "izlenen": izlenen_liste, "cihaz": cihaz, "ulke": ulke,
    }


# ---------------------------------------------------------------- Bing (isteğe bağlı)
BING_API = "https://ssl.bing.com/webmaster/api.svc/json/"

def bing_cagir(yontem, anahtar, **param):
    from urllib.parse import urlencode
    url = BING_API + yontem + "?" + urlencode(dict(param, apikey=anahtar))
    with urlopen(Request(url, headers={"Content-Type": "application/json; charset=utf-8"}), timeout=60) as y:
        return json.load(y).get("d") or []

def bing_tarih(t):
    m = re.search(r"/Date\((\d+)", t or "")
    return datetime.fromtimestamp(int(m.group(1)) / 1000, timezone.utc).date() if m else None

def bing_verisi(anahtar, siteler):
    """Bing Webmaster Tools: site başına son 28 gün / önceki 28 gün tıklama, gösterim ve kelimeler."""
    out = {}
    try:
        bing_siteler = {ad(s["Url"]): s["Url"] for s in bing_cagir("GetUserSites", anahtar) if s.get("IsVerified")}
    except Exception as e:
        print("Bing hatası:", e)
        return out, [f"Bing: {e}"]
    hatalar = []
    for a_ in siteler:
        url = bing_siteler.get(a_)
        if not url:
            continue
        try:
            bugun = date.today()
            gunluk = [(bing_tarih(r.get("Date")), r) for r in bing_cagir("GetRankAndTrafficStats", anahtar, siteUrl=url)]
            kel = [(bing_tarih(r.get("Date")), r) for r in bing_cagir("GetQueryStats", anahtar, siteUrl=url)]
            def toplam(bas, bit):
                t = [r for d, r in gunluk if d and bas <= d <= bit]
                k = [r for d, r in kel if d and bas <= d <= bit]
                gos = sum(r.get("Impressions", 0) for r in k)
                sira = round(sum(r.get("AvgImpressionPosition", 0) * r.get("Impressions", 0) for r in k) / gos, 1) if gos else None
                return [sira, sum(r.get("Clicks", 0) for r in t), sum(r.get("Impressions", 0) for r in t)]
            def kelimeler(bas, bit):
                k = {}
                for d, r in kel:
                    if d and bas <= d <= bit and r.get("Query"):
                        x = k.setdefault(r["Query"], [0.0, 0, 0])
                        x[0] += r.get("AvgImpressionPosition", 0) * r.get("Impressions", 0)
                        x[1] += r.get("Clicks", 0); x[2] += r.get("Impressions", 0)
                return {q: [round(x[0] / x[2], 1) if x[2] else None, x[1], x[2]] for q, x in k.items()}
            s1, s0 = bugun - timedelta(28), bugun - timedelta(56)
            simdi, once = kelimeler(s1, bugun), kelimeler(s0, s1 - timedelta(1))
            secim = sorted(simdi, key=lambda q: -simdi[q][2])[:300]
            secim += [q for q in sorted(once, key=lambda q: -once[q][2])[:100] if q not in simdi]
            seri = sorted([[d.isoformat(), r.get("Clicks", 0), r.get("Impressions", 0)] for d, r in gunluk if d])
            out[a_] = {"mulk": url, "simdi": toplam(s1, bugun), "once": toplam(s0, s1 - timedelta(1)),
                       "kelimeler": [[q, simdi.get(q), once.get(q)] for q in secim], "seri": seri[-180:]}
        except Exception as e:
            print("  Bing hatası:", a_, e)
            hatalar.append(f"Bing {a_}: {e}")
    return out, hatalar


# ---------------------------------------------------------------- Yandex (isteğe bağlı)
YANDEX_API = "https://api.webmaster.yandex.net/v4"

def yandex_cagir(yol, anahtar, **param):
    from urllib.parse import urlencode
    url = YANDEX_API + yol + ("?" + urlencode(param, doseq=True) if param else "")
    try:
        with urlopen(Request(url, headers={"Authorization": "OAuth " + anahtar}), timeout=60) as y:
            return json.load(y)
    except HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("anahtar geçersiz ya da süresi dolmuş (KURULUM.md'deki Yandex adımlarıyla yenisini alın)")
        raise RuntimeError(f"hata {e.code}: {e.read()[:200].decode('utf-8', 'replace')}")

def yandex_verisi(anahtar, siteler):
    """Yandex Webmaster: site başına son 28 gün / önceki 28 gün tıklama, gösterim, ortalama sıra ve kelimeler."""
    out, hatalar = {}, []
    try:
        uid = yandex_cagir("/user", anahtar)["user_id"]
        hostlar = {}
        for h in yandex_cagir(f"/user/{uid}/hosts", anahtar).get("hosts", []):
            if h.get("verified"):
                a_ = ad(h.get("unicode_host_url") or h.get("ascii_host_url", ""))
                # aynı site www'li ve www'siz ekliyse ana aynayı (main_mirror olmayanı) tercih et
                if a_ not in hostlar or not h.get("main_mirror"):
                    hostlar[a_] = h
    except Exception as e:
        print("Yandex hatası:", e)
        return out, [f"Yandex: {e}"]
    gostergeler = ["TOTAL_SHOWS", "TOTAL_CLICKS", "AVG_SHOW_POSITION"]
    son = date.today() - timedelta(1)
    s1, s0 = son - timedelta(27), son - timedelta(55)
    for a_ in siteler:
        h = hostlar.get(a_)
        if not h:
            continue
        yol = f"/user/{uid}/hosts/{quote(h['host_id'], safe='')}"
        try:
            def kelimeler(bas, bit):
                r = yandex_cagir(yol + "/search-queries/popular", anahtar, order_by="TOTAL_SHOWS",
                                 query_indicator=gostergeler, date_from=bas.isoformat(), date_to=bit.isoformat(), limit=500)
                k = {}
                for q in r.get("queries", []):
                    i = q.get("indicators", {})
                    if q.get("query_text") and i.get("TOTAL_SHOWS"):
                        k[q["query_text"]] = [round(i["AVG_SHOW_POSITION"], 1) if i.get("AVG_SHOW_POSITION") else None,
                                              int(i.get("TOTAL_CLICKS") or 0), int(i["TOTAL_SHOWS"])]
                return k
            gecmis = yandex_cagir(yol + "/search-queries/all/history", anahtar, query_indicator=gostergeler,
                                  date_from=(son - timedelta(180)).isoformat(), date_to=son.isoformat()).get("indicators", {})
            gun = {}
            for gosterge, sira in (("TOTAL_CLICKS", 0), ("TOTAL_SHOWS", 1), ("AVG_SHOW_POSITION", 2)):
                for n in gecmis.get(gosterge, []):
                    gun.setdefault(n["date"][:10], [0, 0, None])[sira] = n.get("value")
            def toplam(bas, bit):
                t = [v for d, v in gun.items() if bas.isoformat() <= d <= bit.isoformat()]
                gos = sum(v[1] or 0 for v in t)
                sira = sum((v[2] or 0) * (v[1] or 0) for v in t)
                return [round(sira / gos, 1) if gos else None, int(sum(v[0] or 0 for v in t)), int(gos)]
            simdi, once = kelimeler(s1, son), kelimeler(s0, s1 - timedelta(1))
            secim = sorted(simdi, key=lambda q: -simdi[q][2])[:300]
            secim += [q for q in sorted(once, key=lambda q: -once[q][2])[:100] if q not in simdi]
            out[a_] = {"mulk": h.get("unicode_host_url") or h.get("ascii_host_url"),
                       "simdi": toplam(s1, son), "once": toplam(s0, s1 - timedelta(1)),
                       "kelimeler": [[q, simdi.get(q), once.get(q)] for q in secim],
                       "seri": [[d, int(v[0] or 0), int(v[1] or 0)] for d, v in sorted(gun.items())]}
        except Exception as e:
            print("  Yandex hatası:", a_, e)
            hatalar.append(f"Yandex {a_}: {e}")
    return out, hatalar


def firsat_mi(r):
    """Sayfadaki "Fırsatlar" süzgeciyle aynı: 4–20. sıra ve en az 20 gösterim."""
    return bool(r) and 3 < r[0] <= 20 and r[2] >= 20


def firsatlar_csv(veriler, yol=FIRSAT_CSV):
    """Tüm sitelerin fırsatlarını Excel'de düzgün açılan CSV'ye yazar (UTF-8 BOM, noktalı virgül, virgüllü ondalık)."""
    import csv
    d = lambda x: f"{x:.1f}".replace(".", ",")
    satirlar = []
    for v in veriler:
        for tur, etiket in (("kelimeler", "Anahtar kelime"), ("sayfalar", "Sayfa")):
            for k in v.get(tur, []):
                ad_, simdi, once = k[0], k[1], k[2] if len(k) > 2 else None
                if not firsat_mi(simdi):
                    continue
                ek = max(0, round(simdi[2] * 0.10) - simdi[1])   # 3. sıraya çıkarsa (≈%10 tıklama oranı)
                satirlar.append([v["site"], etiket, ad_, d(once[0]) if once else "", d(simdi[0]),
                                 d(once[0] - simdi[0]) if once else "yeni", once[1] if once else "", simdi[1], simdi[2],
                                 d(100 * simdi[1] / simdi[2]) if simdi[2] else "0,0", ek])
    satirlar.sort(key=lambda r: (r[0], r[1], -r[10]))
    with open(yol, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Site", "Tür", "Anahtar kelime / Sayfa", "Sıra (önceki 28 gün)", "Sıra (son 28 gün)",
                    "Değişim (+ = yükseldi)", "Tıklama (önceki)", "Tıklama (son)", "Gösterim (son)",
                    "Tıklama oranı %", "Tahmini ek tıklama (3. sıraya çıkarsa)"])
        w.writerows(satirlar)
    return len(satirlar)


def main():
    ornek = "--ornek" in sys.argv
    g = Ornek() if ornek else Google()
    arsiv = {} if ornek else (json.load(open(ARSIV, encoding="utf-8")) if os.path.exists(ARSIV) else {})
    izlenen = izlenen_kelimeler()
    siteler = tekillestir(g.siteler())
    if not siteler:
        sys.exit(f"Hizmet hesabı hiçbir Search Console mülküne ekli değil. {g.eposta} adresini "
                 "her sitenin Search Console > Ayarlar > Kullanıcılar ve izinler bölümüne ekleyin.")
    veriler, hatalar = [], []
    for s in siteler:
        print("SEO verisi:", s)
        try:
            kel = izlenen.get(ad(s))
            regex = "^(" + "|".join(re.escape(k) for k in kel) + ")$" if kel else None
            veriler.append(site_verisi(g, s, arsiv, regex))
        except Exception as e:
            print("  hata:", e)
            hatalar.append(f"{ad(s)}: {e}")
    if ornek:                                       # örnekte Bing ve Yandex kutularını da göster
        for n, v in enumerate(veriler):
            for motor, carpan in (("bing", 0.8), ("yandex", 1.4)):
                if motor == "yandex" and n % 2:
                    continue                        # bazı siteler Yandex'e bağlı değilmiş gibi
                r = random.Random(motor + v["site"])
                def ornek_k(k):
                    return [round(min(60, max(1, k[0] * carpan * r.uniform(.5, 1.8))), 1), k[1] // 4, max(5, k[2] // 5)] if k else None
                v[motor] = {"mulk": "https://www." + v["site"] + "/", "simdi": [11.2, 412, 9800], "once": [12.4, 350, 9100],
                            "kelimeler": [[k[0], ornek_k(k[1]), ornek_k(k[2])] for k in v["kelimeler"][:60] if r.random() < .75],
                            "seri": [[r_[0], r_[1] // 9, r_[2] // 9] for r_ in v["seri"][-26:]]}
    bing_anahtar = os.environ.get("BING_ANAHTAR", "").strip()
    if bing_anahtar and not ornek:
        print("Bing verisi okunuyor")
        bing, bh = bing_verisi(bing_anahtar, [v["site"] for v in veriler])
        hatalar += bh
        for v in veriler:
            if v["site"] in bing:
                v["bing"] = bing[v["site"]]
    yandex_anahtar = os.environ.get("YANDEX_ANAHTAR", "").strip()
    if yandex_anahtar and not ornek:
        print("Yandex verisi okunuyor")
        yandex, yh = yandex_verisi(yandex_anahtar, [v["site"] for v in veriler])
        hatalar += yh
        for v in veriler:
            if v["site"] in yandex:
                v["yandex"] = yandex[v["site"]]
    if not ornek:
        with open(ARSIV, "w", encoding="utf-8") as f:
            json.dump(arsiv, f, ensure_ascii=False, separators=(",", ":"))
    zaman = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")
    sablon = open(os.path.join(KOK, "sablon_seo.html"), encoding="utf-8").read()
    veri = json.dumps({"siteler": veriler, "hatalar": hatalar, "ornek": ornek}, ensure_ascii=False, separators=(",", ":"))
    sayfa = (sablon.replace("{{ZAMAN}}", html.escape(zaman))
             .replace("{{VERI}}", veri.replace("</", "<\\/")))
    with open(os.path.join(KOK, "seo.html"), "w", encoding="utf-8") as f:
        f.write(sayfa)
    print("seo.html yazıldı:", len(veriler), "site")
    if not ornek:
        print("firsatlar.csv yazıldı:", firsatlar_csv(veriler), "satır")


if __name__ == "__main__":
    main()
