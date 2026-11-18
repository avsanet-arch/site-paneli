#!/usr/bin/env python3
"""Sayfa sağlığı: Google'da dizinde olmayan sayfalar, site haritaları ve telefon hız puanı.

- Dizin durumu: Search Console "URL denetimi" servisi. Site haritasındaki sayfalar her gün parça parça
  denetlenir (site başına DENETIM_GUNLUK); sonuçlar saglik_durum.json'da birikir, 14 günde bir yenilenir.
- Site haritaları: Search Console'a gönderilen haritalar, hata/uyarı sayıları.
- Hız: Google PageSpeed Insights (telefon). Ana sayfa + en çok tıklanan 2 sayfa. Gerçek kullanıcı verisi
  (Chrome) varsa o da yazılır. PSI_ANAHTAR varsa kullanılır (isteğe bağlı).
Kimlik seo.py ile aynı (GSC_ANAHTAR). Denemek için: python3 saglik.py --ornek
"""
import json, os, re, sys, gzip, html, random
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import seo

KOK = seo.KOK
DURUM = os.path.join(KOK, "saglik_durum.json")
DENETIM_GUNLUK = 120        # site başına günde denetlenen sayfa (Google sınırı mülk başına 2000/gün)
YENILE_GUN = 14             # bir sayfa bu kadar günde bir yeniden denetlenir
HARITA_LIMIT = 20000
UA = {"User-Agent": "Mozilla/5.0 (compatible; SiteIzlemePaneli/1.0)"}
PSI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Google'ın İngilizce durum adlarının sade Türkçesi
DURUMLAR = {
    "Submitted and indexed": "Dizinde",
    "Indexed, not submitted in sitemap": "Dizinde (haritada yok)",
    "Crawled - currently not indexed": "Tarandı ama dizine alınmadı",
    "Discovered - currently not indexed": "Bulundu, henüz taranmadı",
    "URL is unknown to Google": "Google bu sayfayı bilmiyor",
    "Duplicate without user-selected canonical": "Kopya sayıldı (kanonik seçilmemiş)",
    "Duplicate, Google chose different canonical than user": "Kopya sayıldı (Google başka sayfayı seçti)",
    "Alternate page with proper canonical tag": "Başka sayfanın kopyası (normal)",
    "Excluded by 'noindex' tag": "noindex ile kapalı",
    "Page with redirect": "Yönlendirme",
    "Not found (404)": "Bulunamadı (404)",
    "Soft 404": "Boş sayfa (soft 404)",
    "Blocked by robots.txt": "robots.txt engelliyor",
    "Server error (5xx)": "Sunucu hatası (5xx)",
    "Redirect error": "Yönlendirme hatası",
    "Blocked due to access forbidden (403)": "Erişim engelli (403)",
}


def getir(url, limit=10_000_000):
    with urlopen(Request(url, headers=UA), timeout=30) as r:
        veri = r.read(limit)
    if url.endswith(".gz") or veri[:2] == b"\x1f\x8b":
        veri = gzip.decompress(veri)
    return veri.decode("utf-8", "replace")


def harita_adresleri(haritalar):
    """Site haritası adreslerinden (dizin haritaları dahil) sayfa adreslerini toplar."""
    sayfalar, gorulen, kuyruk = [], set(), list(haritalar)
    while kuyruk and len(gorulen) < 80 and len(sayfalar) < HARITA_LIMIT:
        sm = kuyruk.pop(0)
        if sm in gorulen:
            continue
        gorulen.add(sm)
        try:
            xml = getir(sm)
        except Exception:
            continue
        if "<sitemapindex" in xml:
            kuyruk += [html.unescape(u) for u in re.findall(r"<sitemap>.*?<loc>\s*(.*?)\s*</loc>", xml, re.S)]
        else:
            sayfalar += [html.unescape(u) for u in re.findall(r"<url>.*?<loc>\s*(.*?)\s*</loc>", xml, re.S)]
    return list(dict.fromkeys(sayfalar))


class Kaynak:
    """Google servisleri (gerçek)."""
    def __init__(self):
        self.g = seo.Google()

    def mulkler(self):
        return seo.tekillestir(self.g.siteler())

    def haritalar(self, mulk):
        out = self.g._cagir(f"/sites/{quote(mulk, safe='')}/sitemaps").get("sitemap", [])
        return [{"adres": h.get("path"), "son_okuma": (h.get("lastDownloaded") or "")[:10],
                 "hata": int(h.get("errors", 0) or 0), "uyari": int(h.get("warnings", 0) or 0),
                 "bekliyor": bool(h.get("isPending")),
                 "gonderilen": sum(int(c.get("submitted", 0) or 0) for c in h.get("contents", []))} for h in out]

    def sayfalar(self, mulk, haritalar):
        return harita_adresleri([h["adres"] for h in haritalar if h["adres"]])

    def denetle(self, mulk, url):
        g = self.g
        if not g.kimlik.valid:
            g.kimlik.refresh(g._istek)
        govde = json.dumps({"inspectionUrl": url, "siteUrl": mulk, "languageCode": "en-US"}).encode()
        r = Request("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect", data=govde, method="POST",
                    headers={"Authorization": "Bearer " + g.kimlik.token, "Content-Type": "application/json"})
        with urlopen(r, timeout=60) as y:
            s = json.load(y).get("inspectionResult", {}).get("indexStatusResult", {})
        return {"karar": s.get("verdict", ""), "durum": s.get("coverageState", ""),
                "son_tarama": (s.get("lastCrawlTime") or "")[:10], "kanonik": s.get("googleCanonical", "")}

    def hiz(self, url):
        p = {"url": url, "strategy": "mobile", "category": "performance", "locale": "tr"}
        if os.environ.get("PSI_ANAHTAR"):
            p["key"] = os.environ["PSI_ANAHTAR"]
        with urlopen(Request(PSI + "?" + urlencode(p), headers=UA), timeout=120) as y:
            d = json.load(y)
        lh = d.get("lighthouseResult", {})
        a = lh.get("audits", {})
        def sayi(k):
            return (a.get(k) or {}).get("numericValue")
        alan = (d.get("loadingExperience") or {})
        m = alan.get("metrics") or {}
        def yuzde(k):
            return (m.get(k) or {}).get("percentile")
        return {"puan": round((lh.get("categories", {}).get("performance", {}).get("score") or 0) * 100),
                "lcp": sayi("largest-contentful-paint"), "cls": sayi("cumulative-layout-shift"),
                "tbt": sayi("total-blocking-time"),
                "gercek": {"genel": alan.get("overall_category"), "lcp": yuzde("LARGEST_CONTENTFUL_PAINT_MS"),
                           "inp": yuzde("INTERACTION_TO_NEXT_PAINT"),
                           "cls": (yuzde("CUMULATIVE_LAYOUT_SHIFT_SCORE") or 0) / 100 if yuzde("CUMULATIVE_LAYOUT_SHIFT_SCORE") is not None else None}
                if alan.get("metrics") else None}


class Ornek(Kaynak):
    """Google'a bağlanmadan sayfayı görmek için uydurma veri."""
    def __init__(self):
        pass

    def mulkler(self):
        return list(seo.Ornek.SITELER)

    def haritalar(self, mulk):
        a = seo.ad(mulk)
        return [{"adres": f"https://www.{a}/sitemap.xml", "son_okuma": "2026-11-17", "hata": 0 if "avsa" not in a else 2,
                 "uyari": 1, "bekliyor": False, "gonderilen": 180}]

    def sayfalar(self, mulk, haritalar):
        a = seo.ad(mulk)
        return [f"https://www.{a}/sayfa-{i}" for i in range(180)]

    def denetle(self, mulk, url):
        r = random.Random(url)
        d = r.choices(list(DURUMLAR)[:6], weights=[70, 3, 12, 8, 3, 4])[0]
        return {"karar": "PASS" if d.startswith(("Submitted", "Indexed")) else "NEUTRAL", "durum": d,
                "son_tarama": "2026-11-1" + str(r.randint(0, 7)), "kanonik": ""}

    def hiz(self, url):
        r = random.Random(url)
        return {"puan": r.randint(35, 96), "lcp": r.uniform(1500, 5200), "cls": r.uniform(0, .2), "tbt": r.uniform(50, 700),
                "gercek": {"genel": r.choice(["FAST", "AVERAGE", "SLOW"]), "lcp": r.randint(1700, 4200),
                           "inp": r.randint(90, 420), "cls": round(r.uniform(0, .2), 2)} if r.random() < .6 else None}


def en_cok_tiklanan(site, adet=2):
    """seo.html'deki veriden sitenin en çok tıklanan sayfaları."""
    try:
        v = seo_verisi()
        for s in v["siteler"]:
            if s["site"] == site:
                sayfalar = [k for k in s["sayfalar"] if k[1]]
                return [k[0] for k in sorted(sayfalar, key=lambda k: -k[1][1])[:adet]]
    except Exception:
        pass
    return []


def seo_verisi():
    s = open(os.path.join(KOK, "seo.html"), encoding="utf-8").read()
    return json.loads(re.search(r"const V = (.*?);\n", s).group(1).replace("<\\/", "</"))


def main():
    ornek = "--ornek" in sys.argv
    k = Ornek() if ornek else Kaynak()
    durum = {} if ornek else (json.load(open(DURUM, encoding="utf-8")) if os.path.exists(DURUM) else {})
    bugun = date.today().isoformat()
    siteler, hatalar = [], []
    for mulk in k.mulkler():
        site = seo.ad(mulk)
        print("Sayfa sağlığı:", mulk)
        d = durum.setdefault(site, {})
        if d.get("mulk") != mulk:
            d.clear(); d["mulk"] = mulk
        d.setdefault("sayfalar", {})
        kayit = {"site": site, "mulk": mulk}
        # 1) Site haritaları
        try:
            kayit["haritalar"] = k.haritalar(mulk)
        except Exception as e:
            kayit["haritalar"] = []
            hatalar.append(f"{site} site haritası: {e}")
        # 2) Dizin durumu (parça parça)
        try:
            adresler = k.sayfalar(mulk, kayit["haritalar"])
            if not adresler:
                adresler = [f"https://www.{site}/"]
            eski = d["sayfalar"]
            for u in list(eski):
                if u not in adresler:
                    del eski[u]                     # haritadan çıkan sayfa unutulur
            sinir = (date.today() - timedelta(YENILE_GUN)).isoformat()
            sira = [u for u in adresler if u not in eski] + sorted(
                [u for u in adresler if u in eski and eski[u]["tarih"] < sinir], key=lambda u: eski[u]["tarih"])
            yapilan = 0
            for u in sira[:DENETIM_GUNLUK]:
                try:
                    eski[u] = dict(k.denetle(mulk, u), tarih=bugun)
                    yapilan += 1
                except Exception as e:
                    hatalar.append(f"{site} URL denetimi: {str(e)[:200]}")
                    break
            print(f"  {yapilan} sayfa denetlendi, toplam {len(eski)}/{len(adresler)}")
            kayit["harita_sayfa"] = len(adresler)
        except Exception as e:
            hatalar.append(f"{site} dizin durumu: {e}")
        sayfa = d["sayfalar"]
        kayit["denetlenen"] = len(sayfa)
        kayit["dizinde"] = sum(1 for v in sayfa.values() if v["karar"] == "PASS")
        kayit["sorunlu"] = sorted([[u, v["durum"], DURUMLAR.get(v["durum"], v["durum"]), v["son_tarama"], v["tarih"]]
                                   for u, v in sayfa.items() if v["karar"] != "PASS"], key=lambda x: (x[1], x[0]))[:500]
        ozet = {}
        for v in sayfa.values():
            ozet[DURUMLAR.get(v["durum"], v["durum"] or "Bilinmiyor")] = ozet.get(DURUMLAR.get(v["durum"], v["durum"] or "Bilinmiyor"), 0) + 1
        kayit["ozet"] = sorted(ozet.items(), key=lambda x: -x[1])
        # dizinde olmayan sayısının geçmişi (uyarı ve grafik için)
        gecmis = d.setdefault("gecmis", {})
        gecmis[bugun] = [kayit["denetlenen"], kayit["dizinde"]]
        for t in sorted(gecmis)[:-120]:
            del gecmis[t]
        kayit["gecmis"] = sorted(gecmis.items())
        # 3) Hız (telefon)
        hiz = []
        for u in [f"https://www.{site}/"] + en_cok_tiklanan(site):
            try:
                hiz.append(dict(k.hiz(u), adres=u))
            except Exception as e:
                hatalar.append(f"{site} hız ölçümü: {str(e)[:200]}")
        kayit["hiz"] = hiz
        hg = d.setdefault("hiz_gecmis", {})
        if hiz:
            hg[bugun] = hiz[0]["puan"]
        for t in sorted(hg)[:-120]:
            del hg[t]
        kayit["hiz_gecmis"] = sorted(hg.items())
        siteler.append(kayit)
    if not ornek:
        with open(DURUM, "w", encoding="utf-8") as f:
            json.dump(durum, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(KOK, "saglik.json"), "w", encoding="utf-8") as f:
        json.dump({"siteler": siteler, "hatalar": hatalar, "tarih": bugun}, f, ensure_ascii=False, separators=(",", ":"))
    zaman = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")
    sablon = open(os.path.join(KOK, "sablon_saglik.html"), encoding="utf-8").read()
    veri = json.dumps({"siteler": siteler, "hatalar": hatalar, "ornek": ornek}, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(KOK, "saglik.html"), "w", encoding="utf-8") as f:
        f.write(sablon.replace("{{ZAMAN}}", html.escape(zaman)).replace("{{VERI}}", veri.replace("</", "<\\/")))
    print("saglik.html yazıldı:", len(siteler), "site")


if __name__ == "__main__":
    main()
