# Dekanlık Yazışma Uyum Denetleyicisi

GTU Dekanlık ofisi için resmi yazışmaları (.docx) denetleyen, 3 katmanlı yapay zeka destekli web uygulaması.

**CSE 496 — Bitirme Projesi** · Hasan Can İSTEKLİ · Danışman: Prof. Mehmet GÖKTÜRK · GTU 2025

---

## İçindekiler

- [Proje Özeti](#proje-özeti)
- [Mimari: 3 Katmanlı Pipeline](#mimari-3-katmanlı-pipeline)
- [Kural Kodları](#kural-kodları)
- [Bilgi Tabanı (RAG)](#bilgi-tabanı-rag)
- [Web Scraping: TDK Verisi](#web-scraping-tdk-verisi)
- [LLM Entegrasyonu](#llm-entegrasyonu)
- [Sistem Durumu ve API Anahtar Yönetimi](#sistem-durumu-ve-api-anahtar-yönetimi)
- [Hızlı Başlangıç (Docker)](#hızlı-başlangıç-docker)
- [Geliştirme Ortamı](#geliştirme-ortamı)
- [API Referansı](#api-referansı)
- [Test Altyapısı](#test-altyapısı)
- [Proje Yapısı](#proje-yapısı)
- [Ortam Değişkenleri](#ortam-değişkenleri)
- [Kaynaklar ve Referanslar](#kaynaklar-ve-referanslar)

---

## Proje Özeti

Türk kamu kurumlarında kullanılan resmi yazışmaların büyük çoğunluğu `.docx` formatındadır ve YÖ-0030 (üniversite iç yönergesi) ile Cumhurbaşkanlığı Resmi Yazışma Kılavuzu (2025) gibi birden fazla standarda uymak zorundadır. Bu standartların elle kontrol edilmesi zaman alıcı ve hata yapımına açık bir süreçtir.

Bu uygulama, yüklenen bir `.docx` dosyasını şu konularda otomatik olarak denetler:

- **Biçimsel uyum** (font, marj, zorunlu alanlar)
- **Hiyerarşik uyum** (gönderici-alıcı statü ilişkisi, kapanış ifadesi)
- **Semantik uyum** (konu-metin tutarlılığı, anlatım bozuklukları)

Tespit edilen hatalara göre düzeltilmiş bir `.docx` üretir ve belge sonuna denetim raporu ekler.

---

## Mimari: 3 Katmanlı Pipeline

```
Kullanıcı .docx yükler
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│  PARSER (parser.py)                                          │
│  python-docx ile belgeyi okur, 12 bölüme ayırır:            │
│  header · sayi_tarih · konu · muhatap · ilgi · metin        │
│  kapanis · imza · ek · dagitim · iletisim · unknown         │
│  Font adı/boyutu, hizalama, marj, bölüm tespiti             │
└───────────────────────┬─────────────────────────────────────┘
                        │  ParsedDocument
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  KATMAN A — Deterministik Kural Motoru (layer_a.py)         │
│  · python-docx + regex                                       │
│  · Sıfır hallüsinasyon, yüksek kesinlik                     │
│  · 16 kural: FMT, FLD, CLS, LNG, SEM-002 (deterministik)   │
│  · Her analiz ~0.1 ms                                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  KATMAN B — RAG Destekli Kuralsal Kontrol (layer_b.py)      │
│  · ChromaDB (240 chunk, 6 kaynak)                            │
│  · SimpleHashEmbedding (384 boyut, offline)                  │
│  · HIR-001..005: Hiyerarşi, ilgi, dağıtım kuralları        │
│  · Her bulgu için yönerge maddesi referansı                  │
│  · Kaynak bulunamazsa sessizce atlanır                       │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  KATMAN C — Semantik/Mantıksal Analiz (layer_c.py)          │
│  · Google Gemini 2.5 Flash (birincil)                        │
│  · Anthropic Claude (opsiyonel)                              │
│  · SEM-001..004: Konu uyumu, mantıksal tutarlılık, anlatım  │
│  · JSON structured output, confidence scoring (≥ 0.50)      │
│  · API anahtarı yoksa sessizce atlanır                       │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
              AnalysisResult (JSON)
           + Düzeltilmiş .docx (opsiyonel)
```

### Pipeline Orkestratörü (pipeline.py)

`Pipeline` sınıfı üç katmanı sırayla çalıştırır:

1. `parse_docx()` ile `.docx` → `ParsedDocument`
2. `LayerA.run()` → deterministik bulgular
3. `LayerB.run()` → RAG bulgular (ChromaDB hazırsa)
4. `LayerC.run()` → LLM bulgular (API anahtarı varsa)
5. Tüm bulgular birleştirilerek `AnalysisResult` oluşturulur

`mode` parametresi: `"full"` (3 katman) · `"format_only"` (sadece A) · `"content_only"` (B + C)

---

## Kural Kodları

### Katman A — Deterministik Kurallar

| Kod | Kural | Kaynak |
|-----|-------|--------|
| **FMT-001** | Font kontrolü — metin: Times New Roman 12pt veya Arial 11pt | YÖ-0030 R5 Md. 7 |
| **FMT-002** | Marj kontrolü — üst/alt/sol/sağ: 1.5 cm | YÖ-0030 R5 Md. 8 |
| **FLD-001** | "T.C." üst başlığı varlığı | YÖ-0030 R5 Md. 4 |
| **FLD-002** | "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ" başlığı | YÖ-0030 R5 Md. 4 |
| **FLD-003** | Birim adı (fakülte/bölüm/daire) varlığı | YÖ-0030 R5 Md. 4 |
| **FLD-004** | Sayı numarası varlığı ve format (XX.YY.Z-YYYY/NNN) | Yönetmelik Md. 12 |
| **FLD-005** | Tarih varlığı ve format — GG.AA.YYYY | Yönetmelik Md. 13 |
| **FLD-006** | Konu alanı varlığı | Yönetmelik Md. 14 |
| **FLD-007** | İmza bloğu (ad-soyad + unvan) varlığı | Yönetmelik Md. 18 |
| **CLS-001** | Kapanış ifadesi varlığı ("Arz ederim.", "Rica ederim." vb.) | YÖ-0030 R5 Md. 5-e |
| **CLS-002** | Yasaklı kapanış ifadeleri ("Saygılarımla", "Hürmetlerimle" vb.) | YÖ-0030 R5 Md. 5-e |
| **CLS-003** | Onay yazılarında "OLUR" dışında kapanış kullanımı | YÖ-0030 R5 Md. 5-e |
| **LNG-001** | Cümle başında küçük harf | TDK Yazım Kılavuzu |
| **LNG-002** | Virgül öncesi boşluk (hata: " ,") | TDK |
| **LNG-003** | Nokta/soru işareti sonrası boşluk eksik | TDK |
| **LNG-004** | Art arda fazla boşluk | TDK |
| **SEM-002** | Ek sayısı tutarsızlığı (metinde "3 adet" ama ekte 2 var) | YÖ-0030 R5 |

### Katman B — RAG Destekli Kontrol

| Kod | Kural | Kaynak |
|-----|-------|--------|
| **HIR-001** | Üst makama yanlış kapanış — "Rica ederim" yerine "Arz ederim" olmalı | YÖ-0030 R5 Md. 5-e, Ek Tablo |
| **HIR-002** | Yetki devri imzası ("Rektör a." ile imzalayan) tespiti | YÖ-0030 R5 Giden Yazılar |
| **HIR-003** | İlgi satırları kronolojik sıra hatası (tarih bazlı) | YÖ-0030 R5 Md. 6-c |
| **HIR-004** | Dağıtım bölümünde "Gereği"/"Bilgi" ayrımı eksik | YÖ-0030 R5 Md. 8 |
| **HIR-005** | Bölüm → Rektörlük doğrudan yazışma (Dekanlık atlanmış) | YÖ-0030 R5 Md. 4-b |

### Katman C — LLM Semantik Analiz

| Kod | Kural | Açıklama |
|-----|-------|----------|
| **SEM-001** | Konu-Metin İçeriği Uyumsuzluğu | Konu satırı metni doğru özetlemiyor mu? |
| **SEM-002** | Ek-Metin Çapraz Kontrolü | Metinde ek atıfı var ama EK bölümü boş, ya da tersi |
| **SEM-003** | Mantıksal Tutarsızlık | İç çelişki, belirsiz atıf, muhatap-içerik uyumsuzluğu |
| **SEM-004** | Anlatım Bozuklukları | Özne-yüklem, sarkık cümle, aşırı edilgen yapı |

> **Not:** SEM-002 deterministik alt-kontrolü Katman A'da, LLM kontrolü Katman C'de çalışır.

### Kapanış Hiyerarşisi (HIR-001)

| Gönderen → Alıcı | Doğru İfade |
|-------------------|-------------|
| Alt makam → Üst makam | **Arz ederim.** |
| Üst makam → Alt makam | **Rica ederim.** |
| Eşit birimler arası | **Arz ederim.** (öneri) |
| Onay yazıları | **OLUR** |

---

## Bilgi Tabanı (RAG)

Katman B, yönerge maddelerine dayalı bulgu üretmek için ChromaDB vektör veritabanı kullanır.

### Kaynaklar

| # | Kaynak | Tür | source_type | Chunk |
|---|--------|-----|-------------|-------|
| 1 | GTU YÖ-0030 R5 Yazışma Yönergesi (08.08.2023) | PDF | `gtu_yonerge` | 52 |
| 2 | Resmi Yazışmalarda Uygulanacak Usul ve Esaslar Yönetmeliği (10.06.2020, R.G. 31151) | PDF + TXT | `resmi_yazisma_yonetmeligi` | 39 |
| 3 | Cumhurbaşkanlığı Resmi Yazışma Kılavuzu 2025 | PDF | `cb_kilavuzu` | 101 |
| 4 | TDK Yazım Kılavuzu (web scraping) | JSON | `tdk_official` | 35 |
| 5 | Dilekçe Hakkının Kullanılmasına Dair Kanun No. 3071 | PDF | `dilekce_kanunu` | 13 |
| 6 | GTU Organizasyon Hiyerarşisi | Kodlanmış | (hierarchy.py) | — |

**Toplam ChromaDB chunk: 240**

### Otomatik Yükleme (Auto-Ingest)

`Pipeline.__init__()` başlatıldığında ChromaDB dizini boş veya yoksa `_ensure_chromadb()` devreye girer:

```python
# pipeline.py
def _ensure_chromadb(chroma_dir: Path) -> None:
    if chroma_dir.exists() and any(chroma_dir.iterdir()):
        return  # Zaten yüklü
    run_ingest(data_dir=..., persist_dir=chroma_dir)  # Otomatik ingest
```

İlk başlatmada `data/guidelines/` dizinindeki tüm dosyalar taranır ve ChromaDB'ye yüklenir (~30 sn).

### Chunk Stratejisi

- **Madde bazlı bölümleme:** `re.split(r'(?=\bMadde\s+\d+)', text)` ile PDF metni Madde numaralarına göre bölünür
- **Chunk boyutu:** 800 karakter, 120 karakter örtüşme
- **TDK JSON:** Başlık bazlı chunking (36 kural başlığı)
- **ID çakışması önleme:** `source_type_Madde_N_sX_i` formatında benzersiz ID'ler

### Hibrit Arama (retriever.py)

```python
# Birincil kaynaklarda arama (yönerge + yönetmelik + CB kılavuzu)
retriever.search_by_rule("kapanış ifadesi arz ederim")

# TDK'da arama
retriever.search_tdk("virgül kullanımı")

# Tüm kaynaklarda arama
retriever.search_all("resmi yazı font boyutu", k=5)

# Kaynak filtreli arama
retriever.search(query, source_types=["gtu_yonerge", "cb_kilavuzu"])
```

### Embedding: SimpleHashEmbedding

Türkçe için özel bir embedding modeli gerekmeyecek şekilde offline çalışan, karakter n-gram hash tabanlı vektör üretici:

```python
class SimpleHashEmbedding:
    """384 boyutlu karakter trigram hash embedding."""
    def _embed(self, texts):
        for text in texts:
            vec = [0.0] * 384
            for i in range(len(text) - 2):
                ngram = text[i:i+3].lower()
                h = int(md5(ngram).hexdigest(), 16)
                vec[h % 384] += 1.0
            # L2 normalize
```

> **Prod notu:** Üretim ortamında `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` veya `intfloat/multilingual-e5-small` ile değiştirilmesi önerilir.

---

## Web Scraping: TDK Verisi

TDK Yazım Kılavuzu verileri [tdk.gov.tr](https://tdk.gov.tr/kategori/icerik/yazim-kurallari/) adresinden programatik olarak elde edilmiştir.

### Süreç

1. TDK resmi web sitesindeki yazım kuralları sayfaları `requests` + `BeautifulSoup4` ile tarandı
2. 36 kural başlığı (noktalama, büyük/küçük harf, kısaltmalar, sayılar vb.) ayrı ayrı çekildi
3. HTML etiketleri temizlenerek düz metin formatına dönüştürüldü
4. `tdk_tum_kurallar.json` formatında kaydedildi:

```json
{
  "Noktalama İşaretleri": "Nokta (.): ...",
  "Büyük Harflerin Kullanıldığı Yerler": "...",
  "Kısaltmalar": "...",
  ...
}
```

5. `ingest_tdk_json()` fonksiyonu ile 35 chunk'a bölünerek ChromaDB'ye yüklendi

### Kapsam

Yüklenen TDK kuralları: noktalama işaretleri, büyük/küçük harf, kısaltmalar, sayılar, alıntılar, ses ve şekil bilgisi, birleşik/ayrı yazım, yabancı özel adlar ve daha fazlası.

---

## LLM Entegrasyonu

### Desteklenen Sağlayıcılar

| Sağlayıcı | Model | Kullanım |
|-----------|-------|----------|
| Google Gemini | `gemini-2.5-flash` (varsayılan) | Birincil — ücretsiz kota |
| Anthropic Claude | `claude-haiku-4-5-20251001` | Opsiyonel — karşılaştırma |

> **Önemli:** `gemini-2.0-flash` yeni ücretsiz hesaplarda kota sıfırdır. `gemini-2.5-flash` kullanın.

### Prompt Tasarımı

LLM'e gönderilen prompt yapılandırılmış JSON çıkışı zorunlu kılar:

```
KONU: {konu_satiri}
MUHATAP: {muhatap}
METİN: {metin[:2500]}
KAPANIŞ: {kapanis_ifadesi}
EK LİSTESİ: {ekler}

Yanıtı SADECE JSON dizisi olarak döndür:
[{"category": "konu_metin", "severity": "error", "title": "...",
  "description": "...", "suggestion": "...", "confidence": 0.85}]
```

### Confidence Scoring

- LLM her bulgu için `0.0–1.0` arası güven skoru verir
- `confidence < 0.50` olan bulgular otomatik filtrelenir
- UI'da düşük güvenilirlikli bulgular sarı gösterilir

### Hata Yönetimi

```
429 / quota / RESOURCE_EXHAUSTED → pipeline._last_layer_c_error kayıt altına alınır
                                    Kullanıcıya UI'dan bilgi verilir
                                    Sonraki /analyze çağrılarında tekrar LLM'e sorulmaz

401 / 403 / invalid_key           → API anahtarı geçersiz hatası
```

---

## Sistem Durumu ve API Anahtar Yönetimi

### Sistem Durumu Paneli (UI)

Uygulamanın sağ üst köşesindeki "Sistem Durumu" paneli üç katmanın anlık durumunu gösterir:

- **Katman A:** Her zaman aktif (yeşil)
- **Katman B:** ChromaDB hazırsa aktif (yeşil), yoksa kırmızı
- **Katman C:** API anahtarı + kota durumuna göre:
  - Yeşil: Aktif, LLM çalışıyor
  - Sarı: Kota aşıldı (anahtar geçerli ama limit dolmuş)
  - Kırmızı: API anahtarı eksik veya geçersiz
  - Gri: Durum bilinmiyor

### API Anahtarı Yönetimi (UI'dan)

API anahtarı sunucu yeniden başlatılmadan değiştirilebilir:

1. "Sistem Durumu" panelini aç
2. "Anahtarı Değiştir" butonuna tıkla
3. Sağlayıcı seç (Gemini / Claude)
4. API anahtarı ve model adı gir
5. "Kaydet & Aktifleştir" — backend anında hot-reload yapar

Anahtar `data/api_config.json` dosyasına yazılır (`.gitignore`'da, git'e gitmez).

### Gemini API Anahtarı Alma

1. [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) adresine git
2. "Create API Key" → yeni proje veya mevcut proje seç
3. Oluşan anahtarı kopyala
4. Uygulamada "Model" alanına `gemini-2.5-flash` yaz

> **Not:** Kota, Google hesabına/projesine aittir. Aynı hesaptan yeni anahtar oluştursan da kota paylaşılır. Farklı Google hesabı gerekir.

---

## Hızlı Başlangıç (Docker)

### Gereksinimler

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/install/) ≥ 2.20
- Google Gemini API anahtarı ([ücretsiz](https://aistudio.google.com/app/apikey))

### Başlatma

```bash
# 1. Repo'yu klonla
git clone https://github.com/hasancanistekli/dean-office-helper
cd dean-office-helper

# 2. Ortam değişkenlerini ayarla
cp .env.example .env
# .env dosyasını düzenle — GEMINI_API_KEY'i doldur

# 3. Başlat
docker compose up --build
```

İlk başlatmada backend ChromaDB vektör veritabanını otomatik oluşturur (~30 sn).

| Servis | URL |
|--------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |

```bash
# Durdur (veri korunur)
docker compose down

# Sıfırdan başlat (veri silinir)
docker compose down -v
```

---

## Geliştirme Ortamı

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# ChromaDB oluştur (ilk kez, ~30 sn)
python -m app.rag.ingest

# Sunucuyu başlat
uvicorn app.main:app --reload --port 8000
```

**API anahtarı ayarlama** — iki yol:

```bash
# Yol 1: .env dosyası
echo "GEMINI_API_KEY=AIzaSy..." > .env

# Yol 2: UI'dan "Anahtarı Değiştir" (data/api_config.json'a kaydedilir)
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### Testler

```bash
cd backend

# Tüm testler
pytest tests/ -v

# Sadece Katman A testleri
pytest tests/test_comprehensive.py::TestLayerAFont -v

# Test belgelerini yeniden oluştur
python -m tests.create_comprehensive_docs   # 53 belge
python -m tests.create_test_docs            # 7 temel senaryo

# ChromaDB'yi yeniden ingest et
python -m app.rag.ingest
```

---

## API Referansı

### `GET /status`

Tüm katmanların anlık durumunu döndürür. Gereksiz LLM çağrısı yapmadan kota durumunu raporlar.

```json
{
  "backend": "ok",
  "version": "0.6.0",
  "layers": {
    "A": {"active": true, "label": "Deterministik Kural Motoru", "detail": "16 kural"},
    "B": {"active": true, "label": "RAG Kontrol", "detail": "ChromaDB hazır"},
    "C": {
      "active": true,
      "quota_state": "ok",
      "label": "Semantik Analiz (LLM)",
      "provider": "gemini",
      "model": "gemini-2.5-flash"
    }
  }
}
```

`quota_state` değerleri: `"ok"` · `"quota_exceeded"`

### `GET /check-api-key`

Mevcut API anahtarını gerçek bir LLM çağrısıyla test eder.

```json
{
  "ok": true,
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "response_preview": "OK"
}
```

Kota aşımı durumunda:
```json
{
  "ok": false,
  "error_type": "quota_exceeded",
  "tip": "Kota key'e değil Google projesine aittir..."
}
```

### `POST /admin/set-api-key`

API anahtarını kaydeder ve Katman C'yi hot-reload ile günceller. Sunucu yeniden başlatılmaz.

```bash
curl -X POST http://localhost:8000/admin/set-api-key \
  -H "Content-Type: application/json" \
  -d '{"provider": "gemini", "api_key": "AIzaSy...", "model": "gemini-2.5-flash"}'
```

```json
{"ok": true, "provider": "gemini", "model": "gemini-2.5-flash", "active": true}
```

### `POST /analyze`

Belgeyi analiz eder, JSON rapor döner.

```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@belge.docx" \
  -F "mode=full"
```

| Parametre | Değerler | Açıklama |
|-----------|----------|----------|
| `file` | `.docx` | Max 10 MB |
| `mode` | `full` · `format_only` · `content_only` | Hangi katmanlar çalışsın |

```json
{
  "filename": "belge.docx",
  "total_findings": 5,
  "errors": 2,
  "warnings": 2,
  "infos": 1,
  "findings": [
    {
      "id": "A001",
      "layer": "A",
      "severity": "error",
      "rule_code": "FLD-001",
      "title": "'T.C.' başlığı eksik",
      "description": "Belge başında 'T.C.' ibaresi bulunmamaktadır.",
      "suggestion": "Belgenin en üst satırına ortalanmış 'T.C.' ekleyin.",
      "reference": "YÖ-0030 R5, Dördüncü Bölüm Madde 4",
      "confidence": 1.0
    }
  ]
}
```

### `POST /analyze-and-fix`

Analiz eder, otomatik düzeltilebilen hataları uygular ve düzeltilmiş `.docx` döner.

```bash
curl -X POST http://localhost:8000/analyze-and-fix \
  -F "file=@belge.docx" \
  -F "mode=full" \
  -o belge_duzeltilmis.docx
```

Otomatik düzeltilen kurallar:

| Kural | Düzeltme |
|-------|----------|
| `FMT-001` | Font → Times New Roman 12pt (metin paragrafları) |
| `FMT-002` | Marj → 1.5 cm (tüm bölümler) |
| `LNG-002` | Virgül öncesi boşluk kaldırılır |
| `LNG-004` | Art arda boşluklar tek boşluğa indirilir |
| `CLS-002` | Yasaklı kapanış → "Arz ederim." veya "Rica ederim." |

Dönen belgede sonuna **UYUM DENETİM RAPORU** tablosu eklenir (otomatik düzeltmeler + manuel düzeltme gerektiren bulgular).

### `GET /health`

```json
{"status": "ok"}
```

---

## Test Altyapısı

### Test Belgeleri (53 Senaryo)

`backend/tests/fixtures/` altında 53 programatik test belgesi:

| Grup | Adet | Kapsam |
|------|------|--------|
| `a_*` | 25 | Katman A: FMT, FLD, CLS, LNG, SEM-002 |
| `b_*` | 10 | Katman B: HIR-001..005 + doğru örnekler |
| `c_*` | 8 | Katman C: SEM-001..004 + doğru örnek |
| `mix_*` | 7 | Çok katmanlı senaryolar |
| `ok_*` | 3 | Referans belgeler (false-positive kontrolü) |

```bash
# Test belgelerini oluştur
cd backend
python -m tests.create_comprehensive_docs
```

### Belge Tasarım Özellikleri

- **Tarih hizalaması:** Sayı satırında "Sayı:" sol kenara, "Tarih:" sağ kenara hizalanır (right-tab stop @ 18 cm)
- **Marjlar:** A4 (21 cm) - 1.5 cm × 2 = 18 cm metin alanı
- **Birim çeşitliliği:** Bölüm, Fakülte, Enstitü, Rektörlük, Daire Başkanlığı senaryoları

### Test Sınıfları (test_comprehensive.py)

```
TestLayerAFont          → FMT-001 (4 test)
TestLayerAMargin        → FMT-002 (2 test)
TestLayerAMandatoryFields → FLD-001..007 (8 test)
TestLayerAClosing       → CLS-001..003 (4 test)
TestLayerALanguage      → LNG-001..004 (5 test)
TestLayerAEkCount       → SEM-002 deterministik (3 test)
TestLayerBHIR001        → Hiyerarşi kapanış (4 test)
TestLayerBHIR002        → Rektör a. tespiti (2 test)
TestLayerBHIR003        → İlgi sıralaması (3 test)
TestLayerBHIR004        → Dağıtım ayrımı (3 test)
TestLayerBHIR005        → Hiyerarşi atlama (2 test)
TestLayerBNoChromaDB    → ChromaDB olmadan graceful degradation
TestLayerCInactive      → API anahtarsız çalışma
TestLayerCMock          → Sahte LLM yanıtı ile parse testi
TestLayerCRealAPI       → Gerçek Gemini API testi (kota yoksa skip)
TestPipelineMultiLayer  → Çok katmanlı entegrasyon
TestFalsePositives      → Doğru belgelerde yanlış alarm tespiti
```

---

## Proje Yapısı

```
dean-office-helper/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI uygulama v0.6.0
│   │   │                            # /analyze /analyze-and-fix /status
│   │   │                            # /check-api-key /admin/set-api-key /health
│   │   ├── models/
│   │   │   └── finding.py           # Pydantic v2 modeller
│   │   │                            # Finding · ParsedDocument · AnalysisResult
│   │   │                            # Severity · Layer · DocumentSection
│   │   ├── services/
│   │   │   ├── parser.py            # .docx ayrıştırıcı (12 bölüm tespiti)
│   │   │   ├── layer_a.py           # Deterministik kural motoru (16+ kural)
│   │   │   ├── layer_b.py           # RAG destekli kontrol (HIR-001..005)
│   │   │   ├── layer_c.py           # Semantik analiz (Gemini/Claude)
│   │   │   │                        # _from_config() · save_config() · hot-reload
│   │   │   ├── fixer.py             # Belge düzeltici + rapor tablosu
│   │   │   └── pipeline.py          # Orkestratör · ChromaDB auto-ingest
│   │   ├── rules/
│   │   │   └── hierarchy.py         # GTU org. hiyerarşisi + kapanış kuralları tablosu
│   │   └── rag/
│   │       ├── ingest.py            # Çok-format döküman yükleyici (PDF/DOCX/JSON/TXT)
│   │       └── retriever.py         # Hibrit ChromaDB arama (kaynak filtreli)
│   ├── data/
│   │   ├── guidelines/              # Kaynak belgeler (6 dosya)
│   │   │   ├── YÖ-0030...R5.pdf    # GTU Yazışma Yönergesi
│   │   │   ├── Cumhurbaşkanlığı... # CB Kılavuzu 2025 PDF
│   │   │   ├── Resmi Yazışma...pdf  # Yönetmelik PDF
│   │   │   ├── Dilekçe...3071.pdf   # Kanun PDF
│   │   │   ├── tdk_tum_kurallar.json # TDK web scraping sonucu
│   │   │   ├── yonetmelik_tam_metin.txt
│   │   │   └── yonetmelik_ek_ornekler.txt
│   │   ├── chromadb/               # ChromaDB vektör veritabanı (240 chunk, gitignore)
│   │   └── api_config.json         # UI'dan kaydedilen API anahtarı (gitignore)
│   ├── tests/
│   │   ├── fixtures/               # 53 test belgesi (programatik)
│   │   ├── create_comprehensive_docs.py  # 53 senaryo oluşturucu
│   │   ├── create_test_docs.py     # 7 temel senaryo oluşturucu
│   │   ├── test_comprehensive.py   # 95 test (sınıf tabanlı)
│   │   ├── test_scenarios.py       # 22 senaryo testi
│   │   └── test_pipeline.py        # Pipeline entegrasyon
│   ├── Dockerfile
│   ├── entrypoint.sh               # ChromaDB yoksa ingest → uvicorn
│   └── requirements.txt
├── frontend/
│   ├── pages/
│   │   ├── _app.js                 # Global stil + Google Fonts (DM Sans, JetBrains Mono)
│   │   └── index.js                # DeanOfficeHelper dynamic wrapper (SSR kapalı)
│   ├── src/components/
│   │   └── DeanOfficeHelper.jsx    # Ana UI bileşeni
│   │                               # SystemStatus · StatusDot · FileUpload
│   │                               # ResultsPanel · FindingCard
│   ├── Dockerfile                  # Multi-stage: deps → builder → runner
│   └── package.json                # Next.js 14 + React 18
├── docker-compose.yml              # backend + frontend · chromadb_data volume
├── .env.example                    # API key şablonu
├── .gitignore                      # .env · chromadb/ · api_config.json
├── PROJECT_PLAN.md                 # Sprint geçmişi ve teknik notlar
└── README.md                       # Bu dosya
```

---

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `GEMINI_API_KEY` | — | Katman C (Gemini) için. Yoksa Katman C devre dışı |
| `ANTHROPIC_API_KEY` | — | Katman C (Claude) için. Opsiyonel |
| `LAYER_C_PROVIDER` | `gemini` | `"gemini"` veya `"claude"` |
| `LAYER_C_MODEL` | `gemini-2.5-flash` | Model ID override |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend'in backend URL'i |

API anahtarı `.env` dosyasına ek olarak `data/api_config.json`'dan da okunur (UI öncelikli).

Katman C API anahtarı yoksa sessizce devre dışı kalır; Katman A + B çalışmaya devam eder.

---

## Kaynaklar ve Referanslar

### Birincil Standartlar

| Kaynak | Bağlantı |
|--------|----------|
| GTU YÖ-0030 R5 Yazışma Yönergesi (08.08.2023) | [GTU Kalite Sistemi](https://www.gtu.edu.tr/fileman/Files/UserFiles/kalite/Yönergeler/) |
| Resmi Yazışma Yönetmeliği — mevzuat.gov.tr | [Mevzuat No. 2646](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=2646&MevzuatTur=21&MevzuatTertip=5) |
| Resmi Yazışma Yönetmeliği — PDF | [mevzuat.gov.tr PDF](https://mevzuat.gov.tr/MevzuatMetin/21.5.2646.pdf) |
| CB Resmi Yazışma Kılavuzu 2025 | [tccb.gov.tr](https://tccb.gov.tr/assets/dosya/resmiyazisma/dosyalar/kilavuz.pdf) |

### TDK Kaynakları

| Kaynak | Bağlantı |
|--------|----------|
| TDK Yazım Kuralları | [tdk.gov.tr](https://tdk.gov.tr/kategori/icerik/yazim-kurallari/) |
| TDK Noktalama | [tdk.gov.tr](https://tdk.gov.tr/kategori/icerik/noktalama-isaretleri/) |

### Hukuki Dayanak

| Kaynak | Bağlantı |
|--------|----------|
| Dilekçe Hakkı Kanunu No. 3071 | [mevzuat.gov.tr](https://www.mevzuat.gov.tr/MevzuatMetin/1.5.3071.pdf) |

### GTU Kurumsal

| Kaynak | Bağlantı |
|--------|----------|
| GTU Organizasyon Şeması | [gtu.edu.tr](https://www.gtu.edu.tr/organization-schema) |
| GTU Resmi Web Sitesi | [gtu.edu.tr](https://www.gtu.edu.tr) |

### Teknoloji

| Teknoloji | Kaynak |
|-----------|--------|
| FastAPI | [fastapi.tiangolo.com](https://fastapi.tiangolo.com) |
| python-docx | [python-docx.readthedocs.io](https://python-docx.readthedocs.io) |
| ChromaDB | [trychroma.com](https://www.trychroma.com) |
| Google Gemini API | [aistudio.google.com](https://aistudio.google.com) |
| Next.js 14 | [nextjs.org](https://nextjs.org) |
| pdfplumber | [github.com/jsvine/pdfplumber](https://github.com/jsvine/pdfplumber) |

---

## Lisans

Akademik kullanım — GTU CSE 496 Bitirme Projesi © 2025 Hasan Can İSTEKLİ
