#!/usr/bin/env python3
"""SEO geçmişi: Google Search Console'dan sitelerin anahtar kelime sıralarını,
tıklama ve gösterimlerini çeker; "eskiden nasıldı, şimdi nasıl" sayfası (seo.html) üretir.

- Search Console 16 ay geriye veri tutar. Bu betik her ayın özetini seo_arsiv.json'a
  yazar, böylece 16 aydan eski aylar da kaybolmaz.
- Kimlik: GSC_ANAHTAR ortam değişkeni (hizmet hesabı JSON'u) ya da gsc_anahtar.json dosyası.
- Denemek için: python3 seo.py --ornek   (Google'a bağlanmaz, uydurma veriyle sayfayı gösterir)
"""
import json, os, re, sys, math, random, html
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

KOK = os.path.dirname(os.path.abspath(__file__))
ARSIV = os.path.join(KOK, "seo_arsiv.json")
KELIME_DOSYASI = os.path.join(KOK, "kelimeler.txt")
API = "https://searchconsole.googleapis.com/webmasters/v3"
ARSIV_KELIME = 1000   # her ay saklanan en fazla kelime
ARSIV_SAYFA = 500     # her ay saklanan en fazla sayfa
SAYFADA_KELIME = 400  # sayfada gösterilen en fazla kelime (izlenenler hariç)
SAYFADA_SAYFA = 150
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

    def sorgu(self, site, bas, bit, boyut, limit=1000, regex=None):
        govde = {"startDate": bas.isoformat(), "endDate": bit.isoformat(),
                 "dimensions": [boyut] if boyut else [], "rowLimit": limit, "type": "web"}
        if regex:
            govde["dimensionFilterGroups"] = [{"filters": [
                {"dimension": "query", "operator": "includingRegex", "expression": regex}]}]
        return self._cagir(f"/sites/{quote(site, safe='')}/searchAnalytics/query", govde).get("rows", [])


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

    def sorgu(self, site, bas, bit, boyut, limit=1000, regex=None):
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
        if anahtar not in a["aylar"] or not a["aylar"][anahtar]["toplam"][2]:   # boş ay tekrar denenir
            satir = [gunler[d.isoformat()] for d in (bas + timedelta(i) for i in range((bit - bas).days + 1))
                     if d.isoformat() in gunler]
            gos = sum(r["impressions"] for r in satir)
            a["aylar"][anahtar] = {
                "toplam": [round(sum(r["position"] * r["impressions"] for r in satir) / gos, 1) if gos else None,
                           int(sum(r["clicks"] for r in satir)), int(gos)],
                "kelimeler": tablo(g.sorgu(site, bas, bit, "query", ARSIV_KELIME)),
                "sayfalar": tablo(g.sorgu(site, bas, bit, "page", ARSIV_SAYFA)),
            }
            if izlenen:
                a["aylar"][anahtar]["kelimeler"].update(tablo(g.sorgu(site, bas, bit, "query", 500, izlenen)))
        ay = (ay + timedelta(32)).replace(day=1)

    # 3) Karşılaştırılacak dönemler: son 28 gün, önceki 28 gün, geçen yıl aynı 28 gün + arşivdeki aylar
    donemler = []
    def ekle(kod, etiket, bas, bit):
        k = tablo(g.sorgu(site, bas, bit, "query", ARSIV_KELIME))
        if izlenen:
            k.update(tablo(g.sorgu(site, bas, bit, "query", 500, izlenen)))
        satir = [r for d, r in gunler.items() if bas.isoformat() <= d <= bit.isoformat()]
        gos = sum(r["impressions"] for r in satir)
        toplam = [round(sum(r["position"] * r["impressions"] for r in satir) / gos, 1) if gos else None,
                  int(sum(r["clicks"] for r in satir)), int(gos)]
        donemler.append({"kod": kod, "ad": etiket, "aralik": f"{bas:%d.%m.%Y} – {bit:%d.%m.%Y}", "gun": (bit - bas).days + 1,
                         "toplam": toplam, "kelimeler": k,
                         "sayfalar": tablo(g.sorgu(site, bas, bit, "page", ARSIV_SAYFA))})
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
        if tur == "kelimeler":
            secim += [k for k in izlenen_liste if k not in secim]
        return [[k] + [d[tur].get(k) for d in donemler] for k in dict.fromkeys(secim)]
    izlenen_liste = izlenen_kelimeler().get(ad(site), [])

    return {
        "site": ad(site), "mulk": site, "seri": seri, "seri_tur": seri_tur,
        "donemler": [{k: d[k] for k in ("kod", "ad", "aralik", "gun", "toplam")} for d in donemler],
        "kelimeler": liste("kelimeler", SAYFADA_KELIME),
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
                return [None, sum(r.get("Clicks", 0) for r in t), sum(r.get("Impressions", 0) for r in t)]
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
    if ornek and veriler:                           # örnekte Bing kutusunu da göster
        v = veriler[0]
        v["bing"] = {"mulk": "https://www." + v["site"] + "/", "simdi": [None, 412, 9800], "once": [None, 350, 9100],
                     "kelimeler": [[k[0], [round(k[1][0] * 0.8, 1), k[1][1] // 4, k[1][2] // 5] if k[1] else None,
                                    [round(k[1][0] * 0.9, 1), k[1][1] // 5, k[1][2] // 5] if k[1] else None] for k in v["kelimeler"][:40]],
                     "seri": [[r_[0], r_[1] // 9, r_[2] // 9] for r_ in v["seri"][-26:]]}
    bing_anahtar = os.environ.get("BING_ANAHTAR", "").strip()
    if bing_anahtar and not ornek:
        print("Bing verisi okunuyor")
        bing, bh = bing_verisi(bing_anahtar, [v["site"] for v in veriler])
        hatalar += bh
        for v in veriler:
            if v["site"] in bing:
                v["bing"] = bing[v["site"]]
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


if __name__ == "__main__":
    main()
