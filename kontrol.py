#!/usr/bin/env python3
"""Site izleme paneli: sites.txt'deki her siteyi kontrol eder, index.html üretir.
Sadece Python standart kütüphanesi kullanır (kurulum gerekmez)."""
import json, socket, ssl, time, html, os, re
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

KOK = os.path.dirname(os.path.abspath(__file__))
GECMIS = os.path.join(KOK, "gecmis.json")
GECMIS_LIMIT = 96 * 7  # 15 dakikada bir ise ~1 hafta

def siteleri_oku():
    with open(os.path.join(KOK, "sites.txt"), encoding="utf-8") as f:
        return [s.strip() for s in f if s.strip() and not s.startswith("#")]

def ssl_bitis(host):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as s:
                bitis = ssl.cert_time_to_seconds(s.getpeercert()["notAfter"])
                return int((bitis - time.time()) // 86400)
    except Exception:
        return None

_WP_SON = None
def wp_son_surum():
    global _WP_SON
    if _WP_SON is None:
        try:
            with urlopen("https://api.wordpress.org/core/version-check/1.7/", timeout=10) as r:
                _WP_SON = json.load(r)["offers"][0]["current"]
        except Exception:
            _WP_SON = ""
    return _WP_SON

def surum(t):
    return tuple(int(x) for x in re.findall(r"\d+", t)[:3])

def http_https_yonleniyor_mu(host):
    try:
        with urlopen(Request(f"http://{host}/", headers={"User-Agent": "SiteIzlemePaneli/1.0"}), timeout=10) as r:
            return r.geturl().startswith("https://")
    except Exception:
        return None

def oneriler_bul(url, sonuc, h, govde, son_url):
    """(öncelik, metin) listesi döner. öncelik: 'yuksek', 'orta', 'dusuk'"""
    o = []
    host = urlparse(url).hostname
    # SSL
    g = sonuc.get("ssl_gun")
    if url.startswith("https") and g is None:
        o.append(("yuksek", "SSL sertifikası okunamadı. HTTPS düzgün çalışmıyor olabilir."))
    elif g is not None and g < 30:
        o.append(("yuksek" if g < 7 else "orta", f"SSL sertifikası {g} gün içinde bitiyor. Yenilemeyi kontrol edin."))
    if not son_url.startswith("https://"):
        o.append(("yuksek", "Site HTTPS kullanmıyor. Ücretsiz Let's Encrypt sertifikası kurun."))
    elif http_https_yonleniyor_mu(host) is False:
        o.append(("orta", "http:// adresi https://'e yönlenmiyor. Tüm trafiği HTTPS'e yönlendirin."))
    # WordPress
    m = re.search(r'<meta[^>]+generator[^>]+WordPress\s*([\d.]+)', govde, re.I)
    if m:
        son = wp_son_surum()
        if son and surum(m.group(1)) < surum(son):
            o.append(("yuksek", f"WordPress {m.group(1)} kullanılıyor, en son sürüm {son}. Güncelleyin."))
        o.append(("dusuk", "WordPress sürümü sayfa kaynağında görünüyor. Gizlemek saldırganların işini zorlaştırır."))
    elif "wp-content" in govde:
        o.append(("dusuk", "WordPress sitesi. Yönetim panelinden çekirdek, tema ve eklenti güncellemelerini kontrol edin."))
    # PHP
    pb = h.get("x-powered-by", "")
    m = re.search(r"PHP/([\d.]+)", pb)
    if m:
        v = surum(m.group(1))
        if v < (8, 2):
            o.append(("yuksek", f"PHP {m.group(1)} artık güvenlik güncellemesi almıyor. Hosting panelinden PHP 8.3 veya üstüne geçin."))
        elif v < (8, 3):
            o.append(("orta", f"PHP {m.group(1)} kullanılıyor, desteği Aralık 2026'da bitiyor. PHP 8.3 veya üstüne geçmeyi planlayın."))
        o.append(("dusuk", "PHP sürümü X-Powered-By başlığında görünüyor. Gizlenmesi önerilir."))
    sv = h.get("server", "")
    if re.search(r"\d", sv):
        o.append(("dusuk", f"Sunucu yazılımı ve sürümü dışarıya görünüyor ({sv[:40]}). Gizlenmesi önerilir."))
    # jQuery
    m = re.search(r"jquery(?:\.min)?\.js\?ver=([\d.]+)|jquery[-.]([\d.]+)(?:\.min)?\.js", govde, re.I)
    if m:
        jv = m.group(1) or m.group(2)
        if surum(jv) < (3, 5):
            o.append(("orta", f"Eski jQuery {jv} kullanılıyor, bilinen güvenlik açıkları var. 3.7 veya üstüne güncelleyin."))
    # Güvenlik başlıkları
    eksik = [ad for ad, k in [("HSTS", "strict-transport-security"), ("X-Content-Type-Options", "x-content-type-options"),
             ("X-Frame-Options", "x-frame-options")] if k not in h]
    if eksik:
        o.append(("dusuk", "Eksik güvenlik başlıkları: " + ", ".join(eksik) + "."))
    # Kanonik adres: www ve www'siz iki ayrı adres olarak açılıyorsa
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', govde, re.I)
    if m and urlparse(m.group(1)).hostname and urlparse(m.group(1)).hostname != urlparse(son_url).hostname:
        o.append(("orta", f"Site {urlparse(son_url).hostname} adresinde yönlendirme olmadan açılıyor ama asıl adres {urlparse(m.group(1)).hostname}. "
                          "Google iki ayrı site gibi görmesin diye 301 yönlendirmesi ekleyin."))
    # Hız ve SEO
    if sonuc["ms"] > 2000:
        o.append(("orta", f"Sayfa {sonuc['ms']} ms'de yanıt veriyor. Önbellek eklentisi veya daha hızlı hosting düşünün."))
    if govde and 'name="viewport"' not in govde and "name='viewport'" not in govde:
        o.append(("orta", "Mobil uyum etiketi (viewport) yok. Site telefonda düzgün görünmeyebilir."))
    if govde and not re.search(r'<meta[^>]+name=["\']description', govde, re.I):
        o.append(("dusuk", "Sayfa açıklaması (meta description) yok. Google sonuçlarındaki görünümü iyileştirir."))
    m = re.search(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", govde, re.I)
    if m and int(m.group(1)) < datetime.now().year - 1:
        o.append(("dusuk", f"Alt bilgideki telif yılı {m.group(1)}. Site uzun süredir güncellenmemiş görünüyor."))
    sira = {"yuksek": 0, "orta": 1, "dusuk": 2}
    return sorted(o, key=lambda x: sira[x[0]])

def kontrol_et(url):
    basliklar, govde, son_url = {}, "", url
    sonuc = {"url": url, "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    bas = time.monotonic()
    try:
        req = Request(url, headers={"User-Agent": "SiteIzlemePaneli/1.0"})
        with urlopen(req, timeout=15) as r:
            sonuc["kod"] = r.status
            basliklar = {k.lower(): v for k, v in r.headers.items()}
            govde = r.read(400_000).decode("utf-8", "replace")
            son_url = r.geturl()
    except HTTPError as e:
        sonuc["kod"] = e.code
        basliklar, govde, son_url = {k.lower(): v for k, v in e.headers.items()}, "", url
    except Exception as e:
        sonuc["kod"] = None
        sonuc["hata"] = str(getattr(e, "reason", e))[:120]
    sonuc["ms"] = int((time.monotonic() - bas) * 1000)
    sonuc["ayakta"] = sonuc["kod"] is not None and sonuc["kod"] < 400
    host = urlparse(url).hostname
    sonuc["ssl_gun"] = ssl_bitis(host) if url.startswith("https") else None
    sonuc["oneriler"] = oneriler_bul(url, sonuc, basliklar, govde, son_url) if sonuc["kod"] else []
    return sonuc

def gecmisi_guncelle(sonuclar):
    try:
        with open(GECMIS, encoding="utf-8") as f:
            gecmis = json.load(f)
    except Exception:
        gecmis = {}
    for s in sonuclar:
        kayit = gecmis.setdefault(s["url"], [])
        kayit.append([s["zaman"], 1 if s["ayakta"] else 0, s["ms"]])
        del kayit[:-GECMIS_LIMIT]
    with open(GECMIS, "w", encoding="utf-8") as f:
        json.dump(gecmis, f)
    return gecmis

def html_uret(sonuclar, gecmis):
    satirlar = []
    for s in sonuclar:
        k = gecmis.get(s["url"], [])
        uptime = 100 * sum(x[1] for x in k) / len(k) if k else 0
        son = k[-48:]
        cubuk = "".join(f'<i class="{"u" if x[1] else "d"}" title="{x[0]}"></i>' for x in son)
        if s["ssl_gun"] is None:
            ssl_t, ssl_c = "—", ""
        else:
            ssl_t = f'{s["ssl_gun"]} gün'
            ssl_c = "kotu" if s["ssl_gun"] < 7 else ("uyari" if s["ssl_gun"] < 30 else "iyi")
        durum = "Ayakta" if s["ayakta"] else "Çöktü"
        detay = f'HTTP {s["kod"]}' if s["kod"] else html.escape(s.get("hata", "yanıt yok"))
        on = s.get("oneriler", [])
        oneri_html = ""
        if on:
            ad = {"yuksek": "Acil", "orta": "Önemli", "dusuk": "İyileştirme"}
            li = "".join(f'<li class="{p}"><span>{ad[p]}</span>{html.escape(t)}</li>' for p, t in on)
            acil = sum(1 for p, _ in on if p == "yuksek")
            baslik = f'{len(on)} öneri' + (f', {acil} acil' if acil else '')
            oneri_html = f'<details class="oneri"{" open" if acil else ""}><summary>{baslik}</summary><ul>{li}</ul></details>'
        ms_c = "iyi" if s["ms"] < 800 else ("uyari" if s["ms"] < 2000 else "kotu")
        satirlar.append(f'''<div class="kart {'up' if s['ayakta'] else 'down'}">
  <div class="ust"><span class="nokta"></span><a href="{html.escape(s['url'])}" target="_blank">{html.escape(urlparse(s['url']).hostname)}</a><span class="durum">{durum}</span></div>
  <div class="olcu"><div><small>Yanıt</small><b class="{ms_c}">{s['ms']} ms</b></div><div><small>Uptime</small><b>%{uptime:.1f}</b></div><div><small>SSL</small><b class="{ssl_c}">{ssl_t}</b></div></div>
  <div class="cubuk">{cubuk}</div><small class="detay">{detay}</small>{oneri_html}</div>''')
    cokenler = sum(1 for s in sonuclar if not s["ayakta"])
    ozet = "Tüm siteler ayakta" if not cokenler else f"{cokenler} site çökmüş"
    zaman = datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")
    with open(os.path.join(KOK, "sablon.html"), encoding="utf-8") as f:
        sablon = f.read()
    sayfa = (sablon.replace("{{OZET}}", ozet).replace("{{OZET_SINIF}}", "down" if cokenler else "up")
             .replace("{{ZAMAN}}", zaman).replace("{{KARTLAR}}", "\n".join(satirlar)))
    with open(os.path.join(KOK, "index.html"), "w", encoding="utf-8") as f:
        f.write(sayfa)

if __name__ == "__main__":
    sonuclar = [kontrol_et(u) for u in siteleri_oku()]
    for s in sonuclar:
        print(f'{"OK " if s["ayakta"] else "HATA"} {s["url"]} {s["kod"]} {s["ms"]}ms SSL:{s["ssl_gun"]}')
        for p, t in s.get("oneriler", []):
            print(f"   [{p}] {t}")
    html_uret(sonuclar, gecmisi_guncelle(sonuclar))
