#!/usr/bin/env python3
"""Rakip takibi: rakipler.txt'deki siteleri inceler, son kontrolden beri
eklenen/güncellenen sayfaları ve ana sayfadaki değişiklikleri rakipler.html'e yazar."""
import json, re, os, html, gzip, hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen

KOK = os.path.dirname(os.path.abspath(__file__))
DURUM = os.path.join(KOK, "rakip_durum.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; SiteIzlemePaneli/1.0)"}
SITEMAP_LIMIT = 20000       # rakip başına en fazla sayfa
OLAY_LIMIT = 300            # rapordaki en fazla olay

def getir(url, limit=8_000_000):
    with urlopen(Request(url, headers=UA), timeout=20) as r:
        veri = r.read(limit)
        if url.endswith(".gz") or veri[:2] == b"\x1f\x8b":
            veri = gzip.decompress(veri)
        return veri.decode("utf-8", "replace"), r.geturl()

def rakipleri_oku():
    out = []
    with open(os.path.join(KOK, "rakipler.txt"), encoding="utf-8") as f:
        for s in f:
            s = s.strip()
            if s and not s.startswith("#"):
                url, _, bizim = (p.strip() for p in s.partition("|"))
                out.append((url.rstrip("/"), bizim))
    return out

def sitemap_adresleri(kok):
    """robots.txt ve /sitemap.xml üzerinden {url: lastmod} döner."""
    adaylar = []
    try:
        robots, _ = getir(kok + "/robots.txt", 200_000)
        adaylar += re.findall(r"(?im)^sitemap:\s*(\S+)", robots)
    except Exception:
        pass
    adaylar += [kok + "/sitemap.xml", kok + "/sitemap_index.xml"]
    sayfalar, gorulen, kuyruk = {}, set(), list(dict.fromkeys(adaylar))
    while kuyruk and len(gorulen) < 60 and len(sayfalar) < SITEMAP_LIMIT:
        sm = kuyruk.pop(0)
        if sm in gorulen:
            continue
        gorulen.add(sm)
        try:
            xml, _ = getir(sm)
        except Exception:
            continue
        if "<sitemapindex" in xml:
            kuyruk += [html.unescape(u) for u in re.findall(r"<sitemap>.*?<loc>\s*(.*?)\s*</loc>", xml, re.S)]
            continue
        for blok in re.findall(r"<url>(.*?)</url>", xml, re.S):
            loc = re.search(r"<loc>\s*(.*?)\s*</loc>", blok, re.S)
            if loc:
                lm = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", blok, re.S)
                sayfalar[html.unescape(loc.group(1))] = lm.group(1) if lm else ""
        if sayfalar and sm.endswith(("sitemap.xml",)) and kok + "/sitemap_index.xml" in kuyruk:
            kuyruk.remove(kok + "/sitemap_index.xml")
    return sayfalar

def metin(govde):
    govde = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", govde)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", govde))).strip()

def tek_sayfa_mi(url):
    return urlparse(url).path not in ("", "/")

def ana_sayfa(kok):
    govde, son = getir(kok if tek_sayfa_mi(kok) else kok + "/", 3_000_000)
    baslik = re.search(r"(?is)<title[^>]*>(.*?)</title>", govde)
    basliklar = [metin(h) for h in re.findall(r"(?is)<h[1-3][^>]*>(.*?)</h[1-3]>", govde)]
    basliklar = [b for b in dict.fromkeys(basliklar) if b][:200]
    return {"baslik": metin(baslik.group(1)) if baslik else "", "basliklar": basliklar,
            "ozet": hashlib.sha1(metin(govde).encode()).hexdigest()}

def sayfa_basligi(url):
    try:
        g, _ = getir(url, 300_000)
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", g)
        return metin(m.group(1))[:140] if m else ""
    except Exception:
        return ""

def main():
    try:
        durum = json.load(open(DURUM, encoding="utf-8"))
    except Exception:
        durum = {"rakipler": {}, "olaylar": []}
    simdi = datetime.now(timezone.utc).isoformat(timespec="seconds")
    yeni_olaylar = []
    for kok, bizim in rakipleri_oku():
        eski = durum["rakipler"].get(kok)
        ilk = eski is None
        eski = eski or {"sayfalar": {}, "ana": None}
        ad = urlparse(kok).hostname + ("" if not tek_sayfa_mi(kok) else " (" + urlparse(kok).path[:40] + ")")
        try:
            # Büyük sitelerde tüm siteyi değil yalnızca verilen sayfayı izle
            sayfalar = {} if tek_sayfa_mi(kok) else sitemap_adresleri(kok)
        except Exception:
            sayfalar = {}
        try:
            ana = ana_sayfa(kok)
        except Exception as e:
            print("HATA", kok, e)
            continue
        if not ilk:
            yeniler = [u for u in sayfalar if u not in eski["sayfalar"]]
            guncel = [u for u in sayfalar if u in eski["sayfalar"] and sayfalar[u] and sayfalar[u] != eski["sayfalar"][u]]
            silinen = [u for u in eski["sayfalar"] if u not in sayfalar] if sayfalar else []
            for u in yeniler[:40]:
                yeni_olaylar.append({"t": simdi, "rakip": ad, "bizim": bizim, "tur": "yeni", "url": u, "baslik": sayfa_basligi(u)})
            if len(yeniler) > 40:
                yeni_olaylar.append({"t": simdi, "rakip": ad, "bizim": bizim, "tur": "yeni", "url": kok, "baslik": f"…ve {len(yeniler)-40} yeni sayfa daha"})
            for u in guncel[:40]:
                yeni_olaylar.append({"t": simdi, "rakip": ad, "bizim": bizim, "tur": "guncel", "url": u, "baslik": ""})
            if silinen:
                yeni_olaylar.append({"t": simdi, "rakip": ad, "bizim": bizim, "tur": "silindi", "url": kok,
                                     "baslik": f"{len(silinen)} sayfa kaldırıldı (örn. {silinen[0]})"})
            ea = eski.get("ana") or {}
            if ea and ea.get("ozet") != ana["ozet"]:
                eklenen = [b for b in ana["basliklar"] if b not in ea.get("basliklar", [])]
                cikan = [b for b in ea.get("basliklar", []) if b not in ana["basliklar"]]
                aciklama = []
                if ana["baslik"] != ea.get("baslik"):
                    aciklama.append(f'Sayfa başlığı: "{ea.get("baslik")}" → "{ana["baslik"]}"')
                if eklenen:
                    aciklama.append("Yeni başlıklar: " + " · ".join(eklenen[:8]))
                if cikan:
                    aciklama.append("Kaldırılan başlıklar: " + " · ".join(cikan[:8]))
                yeni_olaylar.append({"t": simdi, "rakip": ad, "bizim": bizim, "tur": "ana", "url": kok if tek_sayfa_mi(kok) else kok + "/",
                                     "baslik": " | ".join(aciklama) or "Sayfa içeriği değişti"})
        durum["rakipler"][kok] = {"sayfalar": sayfalar, "ana": ana, "son": simdi, "bizim": bizim}
        print(f"{ad}: {len(sayfalar)} sayfa" + (" (ilk tarama)" if ilk else ""))
    durum["olaylar"] = (yeni_olaylar + durum["olaylar"])[:OLAY_LIMIT]
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False)
    rapor(durum)

def rapor(durum):
    tur_ad = {"yeni": ("Yeni sayfa", "yeni"), "guncel": ("Güncellendi", "guncel"),
              "ana": ("İçerik değişti", "ana"), "silindi": ("Kaldırıldı", "silindi")}
    ozet = []
    for kok, r in durum["rakipler"].items():
        ad = urlparse(kok).hostname + ("" if not tek_sayfa_mi(kok) else " (" + urlparse(kok).path[:40] + ")")
        say = sum(1 for o in durum["olaylar"] if o["rakip"] == ad)
        ozet.append(f'<tr><td><a href="{html.escape(kok)}" target="_blank">{html.escape(ad)}</a></td><td>{html.escape(r.get("bizim") or "—")}</td>'
                    f'<td>{"tek sayfa" if tek_sayfa_mi(kok) else (len(r["sayfalar"]) or "sitemap yok")}</td><td>{say}</td><td>{r["son"][:16].replace("T"," ")}</td></tr>')
    olaylar = []
    for o in durum["olaylar"]:
        ad, sinif = tur_ad[o["tur"]]
        baslik = html.escape(o["baslik"]) if o["baslik"] else html.escape(urlparse(o["url"]).path or o["url"])
        olaylar.append(f'<li><span class="etiket {sinif}">{ad}</span><div><a href="{html.escape(o["url"])}" target="_blank">{baslik}</a>'
                       f'<small>{html.escape(o["rakip"])}{" · rakibi: " + html.escape(o["bizim"]) if o.get("bizim") else ""} · {o["t"][:16].replace("T"," ")}</small></div></li>')
    bos = '<p class="bos">Henüz değişiklik yok. İlk taramada rakiplerin mevcut sayfaları kaydedilir, sonraki taramalarda yeni ve güncellenen sayfalar burada listelenir.</p>'
    sablon = open(os.path.join(KOK, "sablon_rakip.html"), encoding="utf-8").read()
    sayfa = sablon.replace("{{OZET}}", "\n".join(ozet) or '<tr><td colspan="5">rakipler.txt boş</td></tr>') \
                  .replace("{{OLAYLAR}}", f'<ul class="olay">{"".join(olaylar)}</ul>' if olaylar else bos) \
                  .replace("{{ZAMAN}}", datetime.now().strftime("%d.%m.%Y %H:%M"))
    open(os.path.join(KOK, "rakipler.html"), "w", encoding="utf-8").write(sayfa)

if __name__ == "__main__":
    main()
