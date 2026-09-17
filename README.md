# TEST KONTROL

Python/Tkinter tabanlı bağımsız Windows **TEST KONTROL** uygulaması.

Bu proje `pdf_kw_selector` içinden ayrıdır. PDF kW Selector'ın PDF analiz koduna bağımlı değildir.

## Mimari

```text
Python / Tkinter
      ↓
TEST KONTROL.exe
      ↓
Genel / Fan / Damper / Filtre / Modüller / Sensorler / C600 / Rapor
```

Arayüz, önceki Test Kontrol uygulamasındaki iş akışını koruyacak şekilde Python'a taşınacaktır.

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
EXE değiştirme → otomatik yeniden başlatma
```

Güncelleme manifest adresi:
`http://20.91.245.7/pdf-updates/test-kontrol/manifest.json`

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
3. C600 kimlik bilgileri kaynak koda gömülmeyecek.
4. Her faz küçük ve test edilebilir olacak.
5. Her başarılı fazdan sonra README güncellenecek.
6. Windows EXE build ve startup smoke test geçmeden release yayınlanmayacak.
