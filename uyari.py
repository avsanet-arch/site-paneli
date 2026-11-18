#!/usr/bin/env python3
"""Uyarılar: SEO ve sayfa sağlığı verisinde kötüye giden bir şey varsa GitHub'da bir "issue" açar.
GitHub depo sahibine bunu e-postayla bildirir (ek ayar gerekmez).

Kurallar (son 28 gün, önceki 28 güne göre):
- Sitenin Google tıklaması %30'dan fazla düştüyse (önceki dönemde en az 30 tıklama varsa)
- Önemli bir kelime (kelimeler.txt'dekiler + önceki dönemde en çok tıklanan 30 kelime) 3 sıradan fazla düştüyse
- Dizinde olmayan sayfa sayısı bir haftada 10'dan fazla arttıysa
- Site haritasında yeni hata çıktıysa
- Ana sayfanın telefon hız puanı 50'nin altına indiyse
Aynı uyarı 7 gün içinde tekrar gönderilmez (uyari_durum.json).
Denemek için: python3 uyari.py --dene   (issue açmaz, ekrana yazar)
"""
import json, os, re, sys
from datetime import date, timedelta
from urllib.request import Request, urlopen

KOK = os.path.dirname(os.path.abspath(__file__))
DURUM = os.path.join(KOK, "uyari_durum.json")
TEKRAR_GUN = 7


def oku_seo():
    try:
        s = open(os.path.join(KOK, "seo.html"), encoding="utf-8").read()
        return json.loads(re.search(r"const V = (.*?);\n", s).group(1).replace("<\\/", "</"))
    except Exception:
        return {"siteler": []}


def oku_saglik():
    try:
        return json.load(open(os.path.join(KOK, "saglik.json"), encoding="utf-8"))
    except Exception:
        return {"siteler": []}


def f1(x):
    return f"{x:.1f}".replace(".", ",")


def uyarilar():
    out = []   # (anahtar, site, metin)
    for s in oku_seo().get("siteler", []):
        if s.get("ornek") or len(s.get("donemler", [])) < 2:
            continue
        site, a, b = s["site"], s["donemler"][0]["toplam"], s["donemler"][1]["toplam"]
        if b[1] and b[1] >= 30 and a[1] < b[1] * 0.7:
            out.append((f"tik|{site}", site, f"Google tıklamaları düştü: son 28 günde **{a[1]}**, önceki 28 günde {b[1]} "
                        f"(%{round(100 * (b[1] - a[1]) / b[1])} azalma)."))
        izlenen = set(s.get("izlenen") or [])
        kel = s.get("kelimeler", [])
        onemli = {k[0] for k in sorted([k for k in kel if k[2]], key=lambda k: -k[2][1])[:30] if k[2][1] > 0} | izlenen
        dusen = sorted([k for k in kel if k[0] in onemli and k[1] and k[2] and k[1][2] >= 10 and k[1][0] - k[2][0] > 3],
                       key=lambda k: -(k[1][0] - k[2][0]))
        for k in dusen[:10]:                       # en çok düşen 10 kelime
            ad_, simdi, once = k[0], k[1], k[2]
            if True:
                out.append((f"kelime|{site}|{ad_}", site, f"\"{ad_}\" kelimesinde sıra düştü: **{f1(once[0])} → {f1(simdi[0])}** "
                            f"(tıklama {once[1]} → {simdi[1]})."))
    for s in oku_saglik().get("siteler", []):
        site = s["site"]
        g = dict(s.get("gecmis") or [])
        if g:
            son = max(g)
            hafta = (date.fromisoformat(son) - timedelta(7)).isoformat()
            eski = [t for t in g if t <= hafta]
            if eski:
                d0, d1 = g[max(eski)], g[son]
                artis = (d1[0] - d1[1]) - (d0[0] - d0[1])
                if artis > 10:
                    out.append((f"dizin|{site}", site, f"Google dizininde olmayan sayfa sayısı bir haftada **{artis}** arttı "
                                f"(şimdi {d1[0] - d1[1]} sayfa). Ayrıntı: Sayfa sağlığı sayfası."))
        for m in s.get("haritalar") or []:
            if m.get("hata"):
                out.append((f"harita|{site}|{m['adres']}|{m['hata']}", site, f"Site haritasında **{m['hata']} hata** var: {m['adres']}"))
        hiz = s.get("hiz") or []
        if hiz and hiz[0].get("puan") is not None and hiz[0]["puan"] < 50:
            out.append((f"hiz|{site}", site, f"Ana sayfanın telefon hız puanı düşük: **{hiz[0]['puan']}/100**."))
    return out


def issue_ac(baslik, govde):
    depo, belirtec = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not depo or not belirtec:
        print("GitHub bilgisi yok, issue açılmadı.")
        return
    veri = {"title": baslik, "body": govde}
    sahip = os.environ.get("GITHUB_REPOSITORY_OWNER")
    if sahip:
        veri["assignees"] = [sahip]
    r = Request(f"https://api.github.com/repos/{depo}/issues", data=json.dumps(veri).encode(), method="POST",
                headers={"Authorization": "Bearer " + belirtec, "Accept": "application/vnd.github+json"})
    with urlopen(r, timeout=30) as y:
        print("Issue açıldı:", json.load(y).get("html_url"))


def main():
    dene = "--dene" in sys.argv
    durum = json.load(open(DURUM, encoding="utf-8")) if os.path.exists(DURUM) else {}
    bugun = date.today()
    sinir = (bugun - timedelta(TEKRAR_GUN)).isoformat()
    yeni = [(k, s, m) for k, s, m in uyarilar() if durum.get(k, "") < sinir]
    print(len(yeni), "yeni uyarı")
    if not yeni:
        return
    siteler = {}
    for _, s, m in yeni:
        siteler.setdefault(s, []).append(m)
    govde = "Site panelinde dikkat edilmesi gereken değişiklikler var.\n\n"
    for s, mm in siteler.items():
        govde += f"### {s}\n" + "".join(f"- {m}\n" for m in mm) + "\n"
    sahip = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    depo = os.environ.get("GITHUB_REPOSITORY", "").split("/")[-1]
    if sahip and depo:
        govde += (f"Ayrıntılar: [SEO geçmişi](https://{sahip}.github.io/{depo}/seo.html) · "
                  f"[Sayfa sağlığı](https://{sahip}.github.io/{depo}/saglik.html)\n\n")
    govde += "_Aynı uyarı 7 gün boyunca tekrar gönderilmez. Bu kaydı okuduktan sonra kapatabilirsiniz._"
    baslik = f"SEO uyarısı – {bugun:%d.%m.%Y} ({len(yeni)} madde)"
    if dene:
        print(baslik + "\n\n" + govde)
        return
    issue_ac(baslik, govde)
    for k, _, _ in yeni:
        durum[k] = bugun.isoformat()
    for k in [k for k, t in durum.items() if t < (bugun - timedelta(60)).isoformat()]:
        del durum[k]
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
