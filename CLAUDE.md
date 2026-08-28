# CLAUDE.md

Bu dosya, bu depoda çalışan AI asistanları (Claude Code vb.) için rehberdir.
Kod ve arayüz dili **Türkçe**dir; buradaki açıklamalar da Türkçe tutulmuştur.

---

## 1. Proje ne yapıyor?

**Konut Zamanlayıcı** — Ankara'da konut alımı için "ne zaman almalıyım?"
sorusunu hesaplayan tek sayfalık bir web uygulaması.

Kullanıcı birikimini, aylık tasarrufunu, ödeyebileceği taksiti ve hedef
mahallesindeki m² fiyatını girer. Uygulama TCMB verileriyle (TÜFE + Konut Fiyat
Endeksi) 24 aylık senaryolar üretir ve **alım gücünün metrekare cinsinden tepe
yaptığı ayı** gösterir. O aydan sonra beklemek kaybettirmeye başlar.

Mimari üç parçadan oluşur ve aralarındaki tek bağ `veri.json` dosyasıdır:

```
GitHub Actions (günde 1 kez)
   └── toplayici.py  ──yazar──▶  veri.json  ──okur──▶  index.html (tarayıcı)
        (TCMB EVDS API)           (repoda commit'li)     (statik, sunucusuz)
```

Bu ayrım bilinçlidir: tarayıcı EVDS'e hiç bağlanmaz, böylece **CORS sorunu ve
tarayıcıya API anahtarı gömme zorunluluğu ortadan kalkar**.

---

## 2. Dosya haritası

| Dosya | Ne işe yarar |
|---|---|
| `index.html` | Uygulamanın tamamı: HTML + CSS + JS tek dosyada (~465 satır). Build yok, framework yok, bağımlılık yok. |
| `toplayici.py` | TCMB EVDS'ten seri çeken toplayıcı. Sadece Python standart kütüphanesi kullanır. `veri.json` üretir. |
| `.github/workflows/topla.yml` | Her gün 06:00 UTC'de `toplayici.py`'yi çalıştırır, güvenlik kontrolünden geçirir, `veri.json`'u commit'ler. |
| `.gitignore` | Yalnızca Python ara çıktıları (`__pycache__/`, `*.pyc`) ve işletim sistemi artıkları. `veri.json` **buraya eklenmemelidir** — iş akışının onu commit'lemesi gerekir. |
| `veri.json` | **Üretilen dosya — elle düzenleme.** Depoda yoksa henüz iş akışı başarılı çalışmamıştır; uygulama yedek değerlere düşer. |

Başka dosya yok. `package.json`, test klasörü, lint yapılandırması, build adımı
**bilerek** yoktur. Yeni bir araç zinciri eklemeden önce bunun bilinçli bir
tercih olduğunu hatırla.

---

## 3. Değişmez güvenlik kuralları

Bu depodaki en önemli kısıtlar bunlardır. `toplayici.py` ve `topla.yml`
dosyalarının başındaki yorumlar da aynı kuralları anlatır. **Hiçbiri
gevşetilmemelidir.**

1. **API anahtarı asla kaynak koda yazılmaz.** Yalnızca ortam değişkeninden
   okunur: `os.environ["EVDS_ANAHTARI"]`. GitHub'da `Settings > Secrets and
   variables > Actions` altında `EVDS_ANAHTARI` adıyla saklanır.
2. **Anahtar loglanmaz.** Dışarı çıkan her metin `redakte()` fonksiyonundan
   geçer: anahtarı ve URL-encode edilmiş halini `***` ile değiştirir, EVDS URL'i
   içeren metinleri tamamen kırpar, çıktıyı 200 karakterle sınırlar.
   `log()` doğrudan `print` yerine `redakte()` üzerinden yazar — **yeni kod da
   `log()` kullanmalı, çıplak `print` kullanmamalıdır.**
3. **`veri.json` yazılmadan önce taranır.** `guvenlik_taramasi()` çıktı JSON'unda
   anahtar arar; bulursa dosya yazılmaz ve program `2` koduyla çıkar.
4. **İş akışında ikinci bir emniyet ağı vardır.** "Güvenlik kontrolü" adımı
   `grep -qF` ile `veri.json` içinde anahtarı arar; bulursa commit atılmadan
   iş akışı hata verir.
5. **`veri.json`'a kişisel/finansal hiçbir alan yazılmaz.** İçeriği yalnızca
   kamuya açık TCMB serileridir. Kullanıcının birikimi, geliri ve ayarları
   sadece tarayıcının `localStorage`'ında durur; hiçbir yere gönderilmez.
6. **`index.html` dışarıya tek istek atar:** kendi klasöründeki `veri.json`.
   Buraya analytics, CDN, üçüncü taraf script veya herhangi bir `fetch` hedefi
   eklenmemelidir.

Not: `evds_cek()` içindeki denemelerden biri anahtarı query string'e koyar
(header yöntemi reddedilirse düşülen yedek). Bu bilinçlidir ve güvenlidir,
çünkü o URL hiçbir koşulda loglanmaz — `redakte()` EVDS URL'i içeren her metni
kırpar. **Bu URL'i yazdıran hata ayıklama kodu ekleme.**

---

## 4. `veri.json` sözleşmesi (en kritik nokta)

`toplayici.py` yazar, `index.html` okur. Şeması iki dosyada da elle
tanımlıdır — **birinde alan adı değişirse diğeri de değişmelidir**, yoksa
uygulama sessizce yedek değerlere düşer.

```jsonc
{
  "guncelleme": "2026-08-28T06:00:00+00:00",  // UTC ISO, tazelik göstergesi
  "son_ay": "2026-07",                        // KFE Ankara'nın son ayı
  "tufe_son_ay": "2026-07",
  "tufe_yillik": 31.75,                       // yıllık % değişim
  "kfe_tr_yillik": 25.0,
  "kfe_ank_yillik": 26.6,
  "kfe_ank_endeks": 234.8,                    // m² fiyatı taşımada kullanılır
  "kfe_tr_endeks": 220.1,
  "seri": {                                   // [["YYYY-MM", değer], ...]
    "kfe_ank": [], "reel_ank": [], "reel_tr": []   // son 84 ay (SERI_LIMIT)
  },
  "reel": {
    "ank_zirveden": -12.3,                    // reel zirveye göre % fark
    "tr_zirveden": -9.8,
    "ank_zirve_ay": "2022-06"
  },
  "opsiyonel": {                              // alınamazsa null
    "konut_kredi_faiz": {"ay": "2026-07", "deger": 2.65},
    "politika_faiz": null
  },
  "hatalar": ["konut_kredi_faiz (TP.KTFTUK): ..."]  // redakte edilmiş
}
```

Uygulama tarafındaki karşılığı `index.html` içindeki `YEDEK` sabitidir — aynı
şeklin varsayılan değerlerle doldurulmuş halidir. **Şemaya alan eklersen
`YEDEK`'e de ekle.**

### EVDS seri kodları

`toplayici.py` başında iki sözlük var:

- `ZORUNLU` — `tufe` (`TP.FG.J0`), `kfe_tr` (`TP.KFE.TR`), `kfe_ank`
  (`TP.KFE.TR51`). Biri çekilemezse veya 13 aydan kısa gelirse program `1`
  koduyla durur, `veri.json` yazılmaz.
- `OPSIYONEL` — `konut_kredi_faiz` (`TP.KTFTUK`), `politika_faiz`
  (`TP.APIFON4`). Alınamazsa program devam eder; ilgili alan `null` olur ve
  gerekçe `hatalar` dizisine yazılır, arayüzde uyarı kutusunda görünür.

EVDS zaman zaman seri kodlarını değiştirir. "Seri boş döndü" hatası
görüyorsan çözüm **kodu bu sözlüklerde düzeltmektir**, çekme mantığını
değiştirmek değil.

---

## 5. `index.html` yapısı

Tek dosya, dört mantıksal bölüm hâlinde okunur:

**Sabitler ve durum**
- `VARSAYILAN` — ilk açılışta kullanılan ayarlar (birikim, tasarruf, faiz…).
- `YEDEK` — `veri.json` hiç okunamazsa kullanılan son bilinen TCMB değerleri.
- `A` = kullanıcı ayarları (`konut.ayarlar`), `V` = TCMB verisi (`konut.veri`).

**Finans çekirdeği**
- `maxKredi(odeme, aylikFaiz, vadeAy)` — standart anüite formülü; faiz ~0 ise
  `odeme * vade`.
- `aylikOran(yillikYuzde)` — yıllık yüzdeyi bileşik aylık orana çevirir.
- `birikimT(t)` — `t` ay sonraki birikim (anapara büyümesi + düzenli katkı).
- `senaryolar()` — üç senaryo üretir: **Mevcut seyir**, **Kademeli indirim**
  (faiz 12 ayda yarıya iner), **İlk Evim** (belirtilen ayda düşük faiz devreye
  girer ama fiyat sıçrar). Her senaryo 0–24 ay için
  `(birikim + kredi) / m²fiyatı` hesaplar ve **tepe ayını** bulur.

**Çizim ve gösterim**
- `grafikCiz()` — bağımlılıksız, elle üretilen inline SVG (340×130).
- `sinyalCiz()` — eşik tabanlı uyarı listesi (faiz eşiği %1.80, konut
  enflasyonu TÜFE'yi geçti mi, reel zirveden uzaklık…).
- `hesapla()` — her girdi değişiminde çağrılan ana yeniden çizim fonksiyonu.

**Veri ve kalıcılık**
- `veriYukle()` — `veri.json`'u `cache:"no-store"` ile çeker; başarısızsa
  `localStorage` önbelleğine, o da yoksa `YEDEK`'e düşer. Sağ üstteki tazelik
  rozeti hangi kaynağın kullanıldığını gösterir: `canlı` / `önbellek` / `elle giriş`.
- `m2Guncelle(oncekiEndeks)` — KFE Ankara endeksi ilerledikçe kullanıcının
  girdiği mahalle m² fiyatını otomatik taşır. Kullanıcının fiyatı bir daha
  girmesine gerek kalmamasının sebebi budur; **bu davranışı bozma.**
- `ALANLAR` — `input` id'si → `A` içindeki anahtar eşlemesi. Yeni bir ayar
  eklerken **üç yeri birden** güncelle: HTML'deki `<input>`, `ALANLAR` ve
  `VARSAYILAN`. Eksik kalırsa `formaBas()` `null` üzerinde patlar.

### localStorage anahtarları

| Anahtar | İçerik |
|---|---|
| `konut.ayarlar` | Kullanıcının tüm girdileri (`A`) |
| `konut.veri` | `veri.json`'un son başarılı kopyası (çevrimdışı yedek) |
| `konut.gecmis` | Ay bazında m² alım gücü geçmişi, son 36 kayıt |

Hepsi cihazda kalır, hiçbiri gönderilmez.

---

## 6. Yerel çalıştırma

**Uygulama** — `file://` ile açma; `fetch("veri.json")` başarısız olur ve
uygulama "elle giriş" moduna düşer. Basit bir sunucu kullan:

```bash
cd /home/user/Konut
python3 -m http.server 8000
# tarayıcıda http://localhost:8000
```

**Toplayıcı** — geçerli bir EVDS anahtarı gerekir
(https://evds2.tcmb.gov.tr üzerinden ücretsiz alınır):

```bash
EVDS_ANAHTARI="..." python3 toplayici.py
```

Çıkış kodları: `0` başarılı · `1` zorunlu seri çekilemedi veya anahtar boş ·
`2` güvenlik taraması anahtar buldu (dosya yazılmadı).

Anahtar olmadan arayüzü denemek için `veri.json`'u §4'teki şemaya uygun sahte
değerlerle elle oluşturabilirsin — ama **onu commit'leme**, iş akışının
ürettiğiyle çakışır.

Kurulacak bağımlılık, çalıştırılacak test paketi veya linter yoktur.
Doğrulama şu üçüyle yapılır:

```bash
python3 -m py_compile toplayici.py     # sözdizimi
python3 -m http.server 8000            # arayüzü tarayıcıda gözle kontrol et
# iş akışı: Actions sekmesi > "Veri topla" > Run workflow (elle tetikleme)
```

---

## 7. GitHub Actions iş akışı

`.github/workflows/topla.yml`, `contents: write` izniyle çalışır ve
varsayılan dala (`main`) commit atar.

| Adım | Notlar |
|---|---|
| Teşhis | `continue-on-error: true`. EVDS'e erişilebiliyor mu, hangi adres biçimi çalışıyor? Anahtar sadece `-H` ile gönderilir. **İçindeki tarihler sabit kodludur** (`01-01-2026`–`01-08-2026`); yıllar ilerleyince güncellenmesi gerekir. |
| Veriyi çek | `python toplayici.py` — asıl iş. |
| Güvenlik kontrolü | `veri.json` var mı ve anahtar içeriyor mu? İçeriyorsa commit iptal. |
| Değişiklik varsa kaydet | `git diff --quiet` ile fark yoksa commit atlanır. Yazan: `veri-botu`. |

Zamanlama: `cron: "0 6 * * *"` (06:00 UTC = TR 09:00). `workflow_dispatch` ile
elle de tetiklenebilir. **Zamanlanmış çalışma yalnızca varsayılan dalda
gerçekleşir** — bir dalda iş akışını değiştirdiysen elle tetikleyerek dene.

---

## 8. Kod yazım kuralları

- **İsimlendirme Türkçedir.** Fonksiyon, değişken ve JSON alan adları Türkçe:
  `evds_cek`, `seriye_cevir`, `guvenlik_taramasi`, `hesapla`, `grafikCiz`,
  `kfe_ank_yillik`. İngilizce isim ekleme; mevcut üsluba uy.
- **Python ve YAML yorumlarında Türkçe karakter kullanılmaz** (`gunde`,
  `calisir`, `guvenlik`). Bu tutarlı bir tercihtir, korunmalıdır.
- **Kullanıcıya görünen metinler tam Türkçedir**, şapkalı/noktalı harfler
  dahil: "Bugün alabileceğin", "Tepe çok yakın", "yükleniyor".
- **Sıfır bağımlılık.** Python tarafında yalnızca standart kütüphane
  (`json`, `os`, `sys`, `datetime`, `urllib`). Tarayıcı tarafında framework,
  build adımı veya harici script yok. Yeni bir bağımlılık gerçekten
  kaçınılmaz değilse ekleme.
- **Tek dosya kuralı.** `index.html` kendi kendine yeter; CSS ve JS ayrı
  dosyalara bölünmemelidir (GitHub Pages'te doğrudan servis edilir).
- **Hata toleransı.** `localStorage` erişimleri `try/catch` içinde, ağ
  istekleri kademeli yedeklerle yazılmıştır. Uygulama hiçbir koşulda beyaz
  ekran vermemelidir — bozuk veri gelirse `YEDEK`'e düşüp çalışmaya devam eder.
- **Tasarım dili.** Sabit renk paleti: zemin `#EDEEE8`, metin `#1B2A33`,
  ikincil `#6B7D87`, yeşil `#2E7D63`, kırmızı `#A93A31`, amber `#B8791F`.
  Köşeler keskin (`border-radius:0`), rakamlar monospace + `tabular-nums`.
  Yeni bileşen eklerken bu palete ve mevcut `.panel` / `.kart` / `.sinyal`
  sınıflarına uy.

---

## 9. Sık yapılan işler

**Yeni bir TCMB serisi eklemek**
1. `toplayici.py` içinde `OPSIYONEL` sözlüğüne seri kodunu ekle (zorunlu
   yapma — EVDS kodları değişebilir, program durmamalı).
2. Gerekirse `veri` sözlüğüne yeni alanı ekle.
3. `index.html` içinde `YEDEK`'e aynı alanı ekle ve `sinyalCiz()` içinde
   göster (mevcut `ops.konut_kredi_faiz` bloğunu örnek al).

**Yeni bir senaryo eklemek**
`senaryolar()` içindeki `kur(ad, not, renk, faizFn, fiyatFn)` çağrılarına
bir tane daha ekle. `faizFn(t)` `{oran, vade}` döndürür, `fiyatFn(t)` `t`.
ayki m² fiyatını döndürür. Grafik ve liste kendiliğinden güncellenir.

**Yeni bir kullanıcı ayarı eklemek**
`<input>` + `ALANLAR` + `VARSAYILAN` — üçü birden, aynı commit'te.

**Yedek değerleri tazelemek**
`index.html` içindeki `YEDEK` ve `VARSAYILAN`'ın TCMB alanları son bilinen
gerçek değerlerdir. Uzun süre güncellenmezse `veri.json`'a hiç ulaşamayan
kullanıcı eski rakam görür; ara sıra tazele.

---

## 10. Dikkat edilecekler

- `veri.json` **üretilen bir dosyadır**; elle düzenleme veya commit'leme.
  Bir sonraki iş akışı üzerine yazar.
- Depoda `veri.json` yoksa iş akışı henüz başarıyla çalışmamıştır — önce
  `EVDS_ANAHTARI` secret'ının tanımlı olduğunu doğrula.
- Bu bir hesap aracıdır, yatırım tavsiyesi değildir; arayüzdeki bu uyarı
  metnini kaldırma.
- Uygulama tek şehre (Ankara, KFE kodu `TP.KFE.TR51`) göre kurgulanmıştır.
  Şehir seçimi eklemek isteniyorsa hem seri kodu hem `veri.json` şeması
  genişlemelidir — küçük bir değişiklik değildir.
