#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KONUT ZAMANLAYICI - veri toplayici

GitHub Actions icinde gunde bir kez calisir.
TCMB EVDS'den seri ceker, veri.json dosyasini yazar.
Uygulama sadece o dosyayi okur - CORS ve API anahtari sorunu boylece kalmaz.

GUVENLIK KURALLARI (bu dosyada bilerek uygulanmistir):
  1. API anahtari bu dosyada YAZILI DEGILDIR. Yalnizca ortam degiskeninden
     okunur: os.environ["EVDS_ANAHTARI"].
  2. Anahtar YALNIZCA HTTP header'inda gonderilir. Hicbir kosulda URL'ye,
     query string'e veya log'a yazilmaz - query string sunucu erisim
     kayitlarina ve istisna mesajlarina sizabilir.
  3. Disariya cikan her hata metni redakte edilir (bkz. redakte()).
  4. veri.json yazilmadan once icerik anahtara karsi taranir; bulunursa
     dosya YAZILMAZ ve program hata ile durur.
  5. veri.json'a hicbir kisisel/finansal bilgi yazilmaz. Kullanicinin
     birikimi, geliri ve ayarlari yalnizca tarayicinin localStorage'inda
     durur, hicbir yere gonderilmez.

Harici kutuphane gerekmez.
"""

import json
import os
import sys
from datetime import datetime, timezone
from urllib import request, error, parse

CIKTI = "veri.json"
BASLANGIC = "01-01-2014"
SERI_LIMIT = 84  # uygulamaya gonderilecek son ay sayisi

# --- Zorunlu seriler -------------------------------------------------------
ZORUNLU = {
    "tufe":    "TP.FG.J0",     # TUFE genel endeks
    "kfe_tr":  "TP.KFE.TR",    # Konut Fiyat Endeksi - Turkiye
    "kfe_ank": "TP.KFE.TR51",  # Konut Fiyat Endeksi - Ankara
}

# --- Opsiyonel seriler -----------------------------------------------------
# Bulunamazsa program durmaz, "yok" diye isaretler.
# EVDS'de kod degisirse buraya dogrusunu yaz.
OPSIYONEL = {
    "konut_kredi_faiz": "TP.KTFTUK",   # konut kredisi agirlikli ort. faiz
    "politika_faiz":    "TP.APIFON4",  # agirlikli ort. fonlama maliyeti
}

_ANAHTAR = ""  # sadece redakte() icin tutulur, asla disariya verilmez


def redakte(metin):
    """Disariya cikacak her metinden anahtari ve olasi URL'leri temizler."""
    s = str(metin)
    if _ANAHTAR and len(_ANAHTAR) >= 6:
        s = s.replace(_ANAHTAR, "***")
        s = s.replace(parse.quote(_ANAHTAR), "***")
    # tedbiren: metinde tam URL varsa kirp
    if "evds2.tcmb.gov.tr" in s:
        s = "EVDS istegi basarisiz (ayrinti gizlendi)"
    return s[:200]


def log(m=""):
    print(redakte(m) if m else "", flush=True)


def _istek(url, basliklar, sure=30):
    """Tek bir HTTP istegi atar, ham metni dondurur."""
    r = request.Request(url, headers=basliklar)
    with request.urlopen(r, timeout=sure) as y:
        return y.read().decode("utf-8", "replace")


def evds_cek(kodlar):
    """
    EVDS'den seri ceker.

    EVDS'in belgelenen adres bicimi soru isaretsizdir:
        /service/evds/series=...&startDate=...
    Bazi kurulumlarda soru isaretli hali de calisir, o yuzden ikisi de denenir.
    Kimlik once header ile gonderilir (anahtar URL'ye girmez); kabul edilmezse
    query yontemine dusulur.

    Guvenlik: URL hicbir kosulda loglanmaz, redakte() tum ciktilari tarar,
    veri.json yazilmadan once anahtara karsi taranir.
    """
    bit = datetime.now().strftime("%d-%m-%Y")
    param = parse.urlencode({
        "series": "-".join(kodlar),
        "startDate": BASLANGIC,
        "endDate": bit,
        "type": "json",
    })
    kok = "https://evds2.tcmb.gov.tr/service/evds/"
    ortak = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0 Safari/537.36"),
        "Accept": "application/json, text/plain, */*",
    }

    denemeler = []
    for sekil, taban in (("duz", kok + param), ("soru", kok + "?" + param)):
        denemeler.append((sekil + "/header", taban, {**ortak, "key": _ANAHTAR}))
        denemeler.append((sekil + "/query",
                          taban + "&key=" + parse.quote(_ANAHTAR), dict(ortak)))

    son_hata = "bilinmeyen"
    for yontem, url, basliklar in denemeler:
        try:
            ham = _istek(url, basliklar, sure=30)
        except error.HTTPError as e:
            son_hata = f"{yontem}: HTTP {e.code}"
            log(f"  {son_hata}")
            continue
        except (error.URLError, TimeoutError):
            son_hata = f"{yontem}: cevap yok (zaman asimi)"
            log(f"  {son_hata}")
            continue

        kirp = ham.lstrip()[:120]
        if kirp.startswith("<"):
            son_hata = f"{yontem}: HTML dondu -> {redakte(kirp[:70])}"
            log(f"  {son_hata}")
            continue

        try:
            veri = json.loads(ham)
        except json.JSONDecodeError:
            son_hata = f"{yontem}: JSON degil -> {redakte(kirp[:70])}"
            log(f"  {son_hata}")
            continue

        if not isinstance(veri, dict) or not veri.get("items"):
            son_hata = f"{yontem}: yanit bos - seri kodu yanlis olabilir"
            log(f"  {son_hata}")
            continue

        log(f"  BASARILI yontem: {yontem}")
        return veri["items"]

    raise RuntimeError(son_hata)


def seriye_cevir(items, kod):
    """EVDS yanitindan tek seriyi [(YYYY-MM, deger)] olarak cikarir."""
    alan = kod.replace(".", "_")
    out = []
    for it in items:
        ham = it.get(alan)
        if ham in (None, "", "null"):
            continue
        t = it.get("Tarih", "")
        if len(t) == 7 and "-" in t:                # "01-2026"
            ay, yil = t.split("-")
        elif len(t) == 10 and t.count("-") == 2:    # "01-01-2026"
            _, ay, yil = t.split("-")
        else:
            continue
        try:
            out.append((f"{yil}-{ay}", float(str(ham).replace(",", "."))))
        except ValueError:
            continue
    d = {}
    for ay, v in out:      # ayni ay birden fazla geldiyse sonuncuyu tut
        d[ay] = v
    return sorted(d.items())


def yillik(seri):
    if len(seri) < 13:
        return None
    return round((seri[-1][1] / seri[-13][1] - 1) * 100, 2)


def reel_endeks(nominal, tufe):
    """Nominal endeksi TUFE ile deflate eder, ilk ortak ay = 100."""
    t = dict(tufe)
    ort = [(ay, v / t[ay]) for ay, v in nominal if ay in t and t[ay]]
    if not ort:
        return []
    b = ort[0][1]
    return [[ay, round(100 * v / b, 2)] for ay, v in ort]


def guvenlik_taramasi(metin):
    """veri.json yazilmadan once son kontrol. True = temiz."""
    if not _ANAHTAR or len(_ANAHTAR) < 6:
        return True
    return _ANAHTAR not in metin and parse.quote(_ANAHTAR) not in metin


def main():
    global _ANAHTAR
    _ANAHTAR = os.environ.get("EVDS_ANAHTARI", "").strip()

    if not _ANAHTAR:
        log("HATA: EVDS_ANAHTARI ortam degiskeni bos.")
        log("GitHub > Settings > Secrets and variables > Actions > New repository secret")
        log("Ad: EVDS_ANAHTARI")
        return 1

    log(f"Anahtar okundu ({len(_ANAHTAR)} karakter). Once header yontemi denenecek.")

    hatalar = []

    log("Zorunlu seriler cekiliyor...")
    try:
        items = evds_cek(list(ZORUNLU.values()))
    except RuntimeError as e:
        log(f"HATA: zorunlu seriler cekilemedi - {e}")
        return 1

    seriler = {ad: seriye_cevir(items, kod) for ad, kod in ZORUNLU.items()}
    for ad, s in seriler.items():
        if len(s) < 13:
            log(f"HATA: '{ad}' serisi cok kisa ({len(s)} kayit). Kod: {ZORUNLU[ad]}")
            return 1
        log(f"  {ad:8s} {len(s):3d} ay, son {s[-1][0]}")

    log("Opsiyonel seriler deneniyor...")
    ops = {}
    for ad, kod in OPSIYONEL.items():
        try:
            s = seriye_cevir(evds_cek([kod]), kod)
            if s:
                ops[ad] = {"ay": s[-1][0], "deger": round(s[-1][1], 2)}
                log(f"  {ad}: {s[-1][1]:.2f} ({s[-1][0]})")
            else:
                ops[ad] = None
                hatalar.append(f"{ad} ({kod}): seri bos dondu")
                log(f"  {ad}: bos")
        except RuntimeError as e:
            ops[ad] = None
            hatalar.append(f"{ad} ({kod}): {redakte(e)}")
            log(f"  {ad}: alinamadi - {e}")

    tufe, kfe_tr, kfe_ank = seriler["tufe"], seriler["kfe_tr"], seriler["kfe_ank"]
    rtr = reel_endeks(kfe_tr, tufe)
    rank = reel_endeks(kfe_ank, tufe)

    zirve_tr = max((v for _, v in rtr), default=0) or 1
    zirve_ank = max((v for _, v in rank), default=0) or 1
    zirve_ank_ay = max(rank, key=lambda x: x[1])[0] if rank else ""

    kisalt = lambda s: [[a, round(v, 2)] for a, v in s[-SERI_LIMIT:]]

    # veri.json icerigi: yalnizca kamuya acik TCMB verisi.
    # Kisisel/finansal hicbir alan yoktur ve eklenmemelidir.
    veri = {
        "guncelleme": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "son_ay": kfe_ank[-1][0],
        "tufe_son_ay": tufe[-1][0],
        "tufe_yillik": yillik(tufe),
        "kfe_tr_yillik": yillik(kfe_tr),
        "kfe_ank_yillik": yillik(kfe_ank),
        "kfe_ank_endeks": round(kfe_ank[-1][1], 2),
        "kfe_tr_endeks": round(kfe_tr[-1][1], 2),
        "seri": {
            "kfe_ank": kisalt(kfe_ank),
            "reel_ank": rank[-SERI_LIMIT:],
            "reel_tr": rtr[-SERI_LIMIT:],
        },
        "reel": {
            "ank_zirveden": round((rank[-1][1] / zirve_ank - 1) * 100, 1) if rank else None,
            "tr_zirveden": round((rtr[-1][1] / zirve_tr - 1) * 100, 1) if rtr else None,
            "ank_zirve_ay": zirve_ank_ay,
        },
        "opsiyonel": ops,
        "hatalar": [redakte(h) for h in hatalar],
    }

    ham_json = json.dumps(veri, ensure_ascii=False, separators=(",", ":"))

    if not guvenlik_taramasi(ham_json):
        log("")
        log("GUVENLIK HATASI: cikti icinde API anahtari bulundu.")
        log("veri.json YAZILMADI. Kod degistirilmis olabilir - kontrol et.")
        return 2

    with open(CIKTI, "w", encoding="utf-8") as f:
        f.write(ham_json)

    log("")
    log(f"Guvenlik taramasi temiz. {CIKTI} yazildi ({len(ham_json)/1024:.1f} KB)")
    log(f"  veri ayi     {veri['son_ay']}")
    log(f"  enflasyon    {veri['tufe_yillik']}%")
    log(f"  Ankara konut {veri['kfe_ank_yillik']}%")
    if hatalar:
        log(f"  uyari: {len(hatalar)} opsiyonel seri alinamadi (program yine de calisti)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"BEKLENMEYEN HATA: {type(e).__name__}: {redakte(e)}")
        sys.exit(1)
