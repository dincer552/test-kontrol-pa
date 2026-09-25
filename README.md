# TEST KONTROL

Python/Tkinter tabanlı bağımsız Windows **TEST KONTROL** uygulaması.

Bu proje `pdf_kw_selector` içinden ayrıdır. PDF kW Selector'ın PDF analiz koduna bağımlı değildir.

## Mimari

```text
Python / Tkinter
      ↓
TEST KONTROL.exe
      ↓
app.py — ana pencere / ortak durum
      ↓
connection.py — BAĞLANTI / C600
general.py — GENEL
fan.py — FAN KONTROL
damper.py — DAMPER KONTROL
filter.py — FİLTRE KONTROL
modules.py — MODÜLLER
sensors.py — SENSÖRLER
user_report.py — USER / RAPOR
      ↓
models.py / updater.py / build sistemi
```

Arayüz, önceki Test Kontrol uygulamasındaki iş akışını koruyacak şekilde Python'a taşınacaktır.

## PDF keşfi

GENEL sekmesindeki PDF alanı Windows'ta PDF'nin sürükleyip bırakılmasını veya dosya seçilmesini kabul eder. İlk aşamada yalnızca PDF'den keşfedilen proje bilgileri ve ekipman adetleri görünür hale getirilir. Sonraki aşamada bu keşif sonucu Fan, Damper, Filtre, Modül ve Sensör sekmelerindeki kutuların dinamik oluşturulmasında kullanılacaktır. PDF'de bulunmayan ekipman için kutu oluşturulmayacaktır.

## Hedef modül yapısı

Her ana sekme kendi Python dosyasında tutulacaktır. app.py yalnızca ana pencereyi, ortak durumu ve sekmelerin birleştirilmesini yönetecektir.

- app.py → ana pencere, ortak tema, ortak durum ve sekme orkestrasyonu
- general.py → GENEL + PDF alma / sürükle-bırak
- fan.py → FAN KONTROL
- damper.py → DAMPER KONTROL
- filters.py → FİLTRE KONTROL
- modules.py → MODÜLLER
- sensors.py → SENSÖRLER
- user_report.py → USER / RAPOR
- connection.py → BAĞLANTI / C600
- pdf_reader.py → PDF analiz ve ekipman keşfi
- models.py → ortak veri modeli
- updater.py → güncelleme sistemi
- .github/workflows/build-windows.yml → Windows EXE build / release / deploy

Sekmeye özel iş mantığı app.py içinde tutulmayacak. Modüllere taşıma sırasında mevcut UI, kayıt/temizleme, güncelleme ve build davranışları korunacaktır.

## Sekme modüler mimarisi

Her ana sekme kendi Python modülünde tutulacaktır. `app.py` ana pencereyi, ortak durumu ve sekmelerin birleştirilmesini yönetir. Böylece bir sekmedeki geliştirme diğer sekmelerin koduna mümkün olduğunca dokunmaz.

Mevcut yapılandırma:
- `connection.py` → BAĞLANTI / Climatix C600 / RainbowScope TCP Tunnel / GenericJSON
- `app.py` → ana pencere, ortak tema, durum yönetimi ve sekme yerleşimi
- Diğer sekmeler aynı yapı ile kademeli olarak ayrı modüllere taşınacaktır.

C600 modülünde TCP 4242, Climatix `/json.html` okuma, cihaz kimliği ve System Clock işlemleri bulunur.

## Güncelleme mimarisi

PDF kW Selector'daki VM tabanlı yayın/indirme mantığı bu projeye de uygulanır:

```text
GitHub push
   ↓
GitHub Actions
   ↓
Windows EXE build + smoke test
   ↓
GitHub Latest Release
   ↓
Self-hosted runner / VM
   ↓
/var/www/pdf-selector-updates/test-kontrol
   ↓
manifest.json + 256 KB parçalar + Test_Kontrol_latest.exe
   ↓
TEST KONTROL → GÜNCELLE
   ↓
manifest kontrolü → paralel parça indirme → SHA-256 doğrulama
   ↓
EXE değiştirme → kullanıcıya yeniden başlatma uyarısı → manuel yeniden başlatma
```

Güncelleme manifest adresi:
`https://dinceryuksek.com/pdf-updates/test-kontrol/manifest.json`

Self-updater, güncelleme dosyasını dört paralel indirme hattıyla ve parça bazında yeniden denemeyle indirir; toplam boyut ve SHA-256 doğrulamasından sonra çalışan EXE'yi yardımcı PowerShell süreciyle değiştirir.

## Geliştirme aşamaları

- ☑ Faz 0 — bağımsız repository ve Python uygulama temeli
- ☑ Faz 1 — Python veri modeli
- ☑ Faz 2 — Tkinter ana arayüz ve sekmeler
- ☐ Faz 3 — Genel ekran ve durum yönetimi
- ☐ Faz 4 — Fan Kontrol
- ☐ Faz 5 — Damper Kontrol
- ☐ Faz 6 — Filtre Kontrol
- ☐ Faz 7 — Modüller
- ☐ Faz 8 — Sensörler
- ☐ Faz 9 — C600 / GenericJSON
- ☐ Faz 10 — gerçek sensör okumaları
- ☐ Faz 11 — User / imza
- ☐ Faz 12 — Excel raporu
- ☐ Faz 13 — PDF raporu
- ☑ Faz 14 — update client ve VM entegrasyonu
- ☐ Faz 15 — regression / Windows paket testleri

## Kurallar

1. PDF kW Selector'a kod bağımlılığı oluşturulmayacak.
2. C# yalnızca davranış referansı olarak kullanılacak.
3. C600 bağlantı bilgileri ve API erişimi yalnızca `connection.py` içinde tutulacak.
4. Her faz küçük ve test edilebilir olacak.
5. Her başarılı fazdan sonra README güncellenecek.
6. Windows EXE build ve startup smoke test geçmeden release yayınlanmayacak.


<!-- GitHub updater compatibility build test -->
