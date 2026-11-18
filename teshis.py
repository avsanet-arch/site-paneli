#!/usr/bin/env python3
"""Bir kelimenin Search Console verisini ayrıntılı döker (neden sıra değişti?).
Kullanım: python3 teshis.py avsa.com "avşa"
Son 28 gün ve önceki 28 gün için cihaz, ülke, sayfa ve hafta kırılımı yazar."""
import sys
from datetime import date, timedelta
import seo


def main():
    site_ad, kelime = sys.argv[1], sys.argv[2].strip().lower()
    g = seo.Google()
    mulk = next((m for m in seo.tekillestir(g.siteler()) if seo.ad(m) == seo.ad(site_ad)), None)
    if not mulk:
        sys.exit(f"{site_ad} için Search Console mülkü bulunamadı.")
    son = date.today() - timedelta(seo.GECIKME)
    donemler = [("Son 28 gün", son - timedelta(27), son), ("Önceki 28 gün", son - timedelta(55), son - timedelta(28))]

    def sorgu(bas, bit, boyut):
        govde = {"startDate": bas.isoformat(), "endDate": bit.isoformat(), "dimensions": [boyut], "rowLimit": 50, "type": "web",
                 "dimensionFilterGroups": [{"filters": [{"dimension": "query", "operator": "equals", "expression": kelime}]}]}
        from urllib.parse import quote
        return g._cagir(f"/sites/{quote(mulk, safe='')}/searchAnalytics/query", govde).get("rows", [])

    print(f"Mülk: {mulk} · Kelime: {kelime}\n")
    for boyut, baslik in (("device", "CİHAZ"), ("country", "ÜLKE"), ("page", "SAYFA"), ("date", "GÜN")):
        print(f"===== {baslik} =====")
        for ad_, bas, bit in donemler:
            print(f"-- {ad_} ({bas} – {bit})")
            satirlar = sorted(sorgu(bas, bit, boyut), key=lambda r: (r["keys"][0] if boyut == "date" else -r["impressions"]))
            for r in satirlar[:25]:
                print(f"   {r['keys'][0][:70]:70}  sıra {r['position']:5.1f}  tık {int(r['clicks']):4}  gösterim {int(r['impressions']):5}")
        print()


if __name__ == "__main__":
    main()
