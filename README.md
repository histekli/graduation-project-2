# Dekanlık Yazışma Uyum Denetleyicisi

GTU Dekanlık ofisi için resmi yazışmaları (.docx) denetleyen, 3 katmanlı yapay zeka destekli web uygulaması.

**CSE 496 — Bitirme Projesi** · Hasan Can İSTEKLİ · Danışman: Prof. Mehmet GÖKTÜRK · GTU 2025

---

## İçindekiler

- [Proje Özeti](#proje-özeti)
- [Mimari: 3 Katmanlı Pipeline](#mimari-3-katmanlı-pipeline)
- [Kural Kodları](#kural-kodları)
- [Uyum Skoru (Ağırlıklı)](#uyum-skoru-ağırlıklı)
- [Bilgi Tabanı (RAG)](#bilgi-tabanı-rag)
- [Türkçe Dil İşleme Zorlukları](#türkçe-dil-işleme-zorlukları)
- [Web Scraping: TDK Verisi](#web-scraping-tdk-verisi)
- [LLM Entegrasyonu](#llm-entegrasyonu)
- [Sistem Durumu ve API Anahtar Yönetimi](#sistem-durumu-ve-api-anahtar-yönetimi)
- [Hızlı Başlangıç (Docker)](#hızlı-başlangıç-docker)
- [DigitalOcean Droplet Deployment (Önerilen)](#digitalocean-droplet-deployment-önerilen)
- [Alternatif: Ücretsiz Demo Deploy (Render + Vercel)](#alternatif-ücretsiz-demo-deploy-render--vercel)
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

Tespit edilen hatalara göre düzeltilmiş bir `.docx` üretir, belge sonuna denetim raporu ekler ve 0–100 arası **uyum skoru** hesaplar.

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
│  · python-docx + regex · Sıfır hallüsinasyon                │
│  · Biçim/alan/dil: FMT, FLD, CLS, LNG-001..008 (20 kural)  │
│  · Deterministik İÇERİK: SEM-002 (ek-metin), SEM-006 (tekrar)│
│  · Her analiz ~0.1 ms                                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  KATMAN B — RAG Destekli Kuralsal Kontrol (layer_b.py)      │
│  · ChromaDB (569 chunk, 6 kaynak)                            │
│  · Anlamsal embedding: multilingual-e5-small (384 boyut)    │
│    (model yüklenemezse hash fallback — düşük kalite)        │
│  · HIR-001..005: Hiyerarşi, ilgi, dağıtım kuralları        │
│  · Her bulgu için yönerge maddesi referansı                  │
│  · Kaynak bulunamazsa sessizce atlanır                       │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  KATMAN C — Semantik/Mantıksal Analiz (layer_c.py)          │
│  · Google Gemini 2.5 Flash (birincil)                        │
│  · Groq / Llama 3.3 70B (yedek)                              │
│  · YALNIZCA LLM bulguları (deterministik kural YOK)          │
│  · SEM-001,003,004,005: konu, mantık, anlatım, yeterlilik   │
│  · JSON structured output, confidence scoring (≥ 0.50)      │
│  · found_text (kanıt alıntısı) + suggested_text (yeniden    │
│    yazım önerisi) alanları                                   │
│  · API anahtarı yoksa sessizce atlanır                       │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
              AnalysisResult (JSON)
           compliance_score: 0–100
           + Düzeltilmiş .docx (opsiyonel)
```

### Pipeline Orkestratörü (pipeline.py)

`Pipeline` sınıfı üç katmanı sırayla çalıştırır:

1. `parse_docx()` ile `.docx` → `ParsedDocument`
2. `LayerA.run()` → deterministik bulgular
3. `LayerB.run()` → RAG bulgular (ChromaDB hazırsa)
4. `LayerC.run()` → LLM bulgular (API anahtarı varsa)
5. Tüm bulgular birleştirilerek `AnalysisResult` oluşturulur
6. **Uyum skoru** kural-ağırlıklı, oransal formülle hesaplanır (bkz. [Uyum Skoru](#uyum-skoru-ağırlıklı))

`mode` parametresi: `"full"` (3 katman) · `"format_only"` (sadece A — deterministik biçim **ve** içerik kuralları) · `"content_only"` (B + C)

### Parser Güvenilirliği (Bölüm Tespiti)

Parser, paragrafları 12 bölüme ayırırken tek bir regex yerine **anahtar kelime + konum + biçim ipuçlarını** birleştirir. Örneğin muhatap (alıcı) satırı, "ilk satır" sezgisiyle değil; alıcı ekleriyle (`...Makamına,`, `...Dekanlığına,`) ya da `Sayın ...` kalıbıyla skorlanarak tespit edilir (İlgi bloğundan sonra gelse bile yakalanır). Hiçbir kalıba uymayan paragraf sessizce yanlış atanmaz, `unknown`'da bırakılıp loglanır.

**Ölçüm:** [`tests/fixtures/section_labels.json`](backend/tests/fixtures/section_labels.json) içinde 5 belge / 72 paragraf elle etiketlenmiştir. Parser tahmini bu ground-truth ile karşılaştırılır ([`tests/test_parser_metrics.py`](backend/tests/test_parser_metrics.py)):

| Metrik | Değer |
|--------|-------|
| Genel doğruluk (accuracy) | **%97.2** (70/72 paragraf) |
| Makro F1 | **0.974** |
| Kusursuz (F1=1.0) bölümler | header, sayi_tarih, konu, muhatap, ilgi, ek, dagitim, metin |
| En zayıf bölüm | `kapanis` (R=0.71) — belgedeki **yedek/ikinci** kapanış ifadesi imza bloğuna karışabiliyor (bilinen sınır) |

Eşik altına düşülürse (`accuracy < 0.90` veya `macro-F1 < 0.85`) test başarısız olur (regresyon koruması).

**Yanlış-alarm (false-positive):** 13 adet `ok_*` referans belgesi (farklı muhatap formatları, ilgi/ek varyasyonları, kısa/uzun metin, Arial/TNR) üzerinde Katman A **0 error/warning** ve **toplam 0 bulgu** üretir. Eşik aşılırsa test başarısız olur ([`TestReferenceFalsePositives`](backend/tests/test_parser_metrics.py), `TestFalsePositives`).

---

## Kural Kodları

### Katman A — Deterministik Kurallar (20 biçim/alan/dil + 2 deterministik içerik)

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
| **LNG-001** | Cümle başında küçük harf (paragraf başı dahil) | TDK Yazım Kılavuzu |
| **LNG-002** | Virgül öncesi boşluk (hata: " ,") | TDK |
| **LNG-003** | Nokta/soru işareti sonrası boşluk eksik | TDK |
| **LNG-004** | Art arda fazla boşluk | TDK |
| **LNG-005** | Virgül/noktalı virgül sonrası boşluk eksik (hata: ",kelime") | TDK |
| **LNG-006** | İki nokta öncesi gereksiz boşluk (hata: "konu :") | TDK |
| **LNG-007** | Parantez içi gereksiz boşluk (hata: "( metin )") | TDK |
| **LNG-008** | Çok uzun cümle (>35 kelime) | Resmi yazışma okunabilirlik ilkeleri |
| **SEM-002** | Ek-Metin tutarlılığı — ek sayısı + ek atıfı çapraz kontrolü (**deterministik içerik**) | Yönetmelik Md. 20-d; YÖ-0030 R5 Ekler |
| **SEM-006** | Tekrar eden ifade — ≥%85 sözcük örtüşmeli cümle çiftleri (**deterministik içerik**) | Resmi yazışma ilkeleri — özlük ve sadelik |

> **Not (mimari):** SEM-002 ve SEM-006 "SEM" (semantik) ailesinde kodlanmış olsa da **deterministiktir** ve bu yüzden LLM olan Katman C'de değil, deterministik Katman A motorunda çalışır. Kod kodları korunmuştur; `layer` alanları `A`'dır. Deterministik oldukları için `full` **ve** `format_only` modlarında çalışırlar (LLM maliyeti yok).

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
| **SEM-003** | Mantıksal Tutarsızlık | İç çelişki, belirsiz atıf, muhatap-içerik uyumsuzluğu |
| **SEM-004** | Anlatım Bozuklukları | Özne-yüklem, sarkık cümle, aşırı edilgen yapı |
| **SEM-005** | Belge Yeterliliği | Amaç yeterince açıklanmış mı? Gerekli bilgiler tam mı? |

> **Not:** Katman C **yalnızca** LLM çağrısıyla bulgu üretir; içinde deterministik kural yoktur. Eskiden burada bulunan deterministik SEM-002 (ek-metin) ve SEM-006 (tekrar) kuralları, mimari tutarlılık için Katman A'ya taşınmıştır (yukarıdaki Katman A tablosu).

### Otomatik Düzeltme (fixer.py)

| Kural | Düzeltme |
|-------|----------|
| `FMT-001` | Font → Times New Roman 12pt (metin paragrafları) |
| `FMT-002` | Marj → 1.5 cm (tüm bölümler) |
| `LNG-001` | Cümle başı büyük harf (paragraf başı + nokta/!? sonrası) |
| `LNG-002` | Virgül öncesi boşluk kaldırılır |
| `LNG-003` | Nokta sonrası boşluk eklenir |
| `LNG-004` | Art arda boşluklar tek boşluğa indirilir |
| `LNG-005` | Virgül/noktalı virgül sonrası boşluk eklenir |
| `LNG-006` | İki nokta öncesi boşluk kaldırılır |
| `LNG-007` | Parantez içi boşluklar kaldırılır |
| `CLS-002` | Yasaklı kapanış → "Arz ederim." veya "Rica ederim." |
| `CLS-003` | Yanlış onay ifadesi → "OLUR" |

Düzeltilemeyen bulgular belgede sonuna **UYUM DENETİM RAPORU** tablosu olarak eklenir.

### Kapanış Hiyerarşisi (HIR-001)

| Gönderen → Alıcı | Doğru İfade |
|-------------------|-------------|
| Alt makam → Üst makam | **Arz ederim.** |
| Üst makam → Alt makam | **Rica ederim.** |
| Eşit birimler arası | **Arz ederim.** (öneri) |
| Onay yazıları | **OLUR** |

---

## Uyum Skoru (Ağırlıklı)

Eski skor `max(0, 100 − HATA×10 − UYARI×5 − BİLGİ×2)` yalnızca **önem düzeyine** (severity) bakıyordu. Bu savunulamazdı: tek bir font hatası (FMT-001, `error`) ile bir hiyerarşi hatası (HIR-001, `warning`) — biri error diğeri warning olduğu için — yanlış sıralanıyordu; üstelik ceza sınırsızdı.

Yeni skor cezayı **kural koduna** göre ağırlıklandırır ve **oransal** hesaplar. Ağırlıklar tek bir merkezi dosyada toplanır: [`backend/app/rules/scoring_weights.py`](backend/app/rules/scoring_weights.py).

### Formül

```
skor = 100 × max(0, 1 − Σ kural_ağırlığı / DOYGUNLUK_CEZASI)        DOYGUNLUK_CEZASI = 100
```

`DOYGUNLUK_CEZASI = 100`, belgenin tümüyle uyumsuz sayıldığı (skorun 0'a indiği) doygunluk eşiğidir — yaklaşık 5 kritik ihlale denktir. Skor her zaman **0–100** aralığında ve **monotoniktir** (daha çok / daha ağır hata → daha düşük skor).

### Ağırlık tablosu (kategorik)

| Kategori | Ağırlık | Kapsam | Örnek kurallar |
|----------|---------|--------|----------------|
| **KRİTİK** | 20 | Belgeyi hukuki/kurumsal olarak geçersiz/yanlış kılan ihlaller | FLD-001..007 (eksik zorunlu alan), HIR-001 (yanlış hiyerarşik kapanış), CLS-001/002/003 (kapanış/onay) |
| **ORTA** | 8 | Biçimsel ve içeriksel uyumsuzluklar | FMT-001 (font), FMT-002 (marj), SEM-001/002/003/005, HIR-003 |
| **DÜŞÜK** | 2 | Kozmetik / dilbilgisi / bilgilendirme | LNG-001..008, SEM-004 (anlatım), SEM-006 (tekrar), HIR-002/004/005 |

Ağırlık **severity'den bağımsızdır**: HIR-001 önem düzeyi `warning` olsa bile KRİTİK; FMT-001 önem düzeyi `error` olsa bile ORTA. Bilinmeyen kodlar için önem düzeyine göre makul varsayılan uygulanır.

### Ağırlıkların kaynağı (dürüst kalibrasyon notu)

> Ağırlıklar, kuralların belgenin hukuki/kurumsal geçerliliğine etkisine göre **[yazar tarafından] kategorik olarak** atanmıştır; henüz uzman anketi veya hata-frekans analizi yapılmamıştır. İleride uzman görüşü ya da gerçek belge hata istatistikleriyle kalibre edilmesi planlanmaktadır. Uydurma bir literatür referansı verilmemiştir.

### Eski ↔ yeni karşılaştırma

`python -m scripts.score_compare` (Katman A + B deterministik bulguları):

| Belge | E/U/B | Eski skor | Yeni skor | Not |
|-------|-------|-----------|-----------|-----|
| `test_perfect.docx` | 0/0/0 | 100 | 100 | Hatasız → 100 (her iki formül) |
| `b_hir001_muhendislik_rektor.docx` | 0/1/0 | **95** | **80** | HIR-001 `warning` olduğu için eski formül neredeyse cezalandırmıyordu; yeni formül kritik sayar |
| `a_fmt001_calibri.docx` | 2/1/0 | 75 | 76 | Font + ek tutarsızlığı (orta ağırlıklar) |
| `mix_fmt_hir.docx` | 2/1/0 | 75 | 64 | Aynı E/U/B ama HIR-001 ağır bastığı için daha düşük |
| `a_fld_all_missing.docx` | 7/1/0 | 25 | 0 | Tüm zorunlu alanlar eksik → tümüyle uyumsuz |

Tek-bulgu etkisi: **1 × FMT-001 (ORTA) → 92**, **1 × HIR-001 (KRİTİK) → 80** — aynı belgede font ve hiyerarşi hatası farklı skor düşüşü üretir.

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

**Toplam ChromaDB chunk: 569**

### Otomatik Yükleme (Auto-Ingest)

`Pipeline.__init__()` başlatıldığında ChromaDB dizini boş/yoksa **veya** koleksiyonun embedding modeli aktif modelden farklıysa `_ensure_chromadb()` yeniden ingest tetikler:

```python
# pipeline.py
def _ensure_chromadb(chroma_dir: Path) -> None:
    if not (chroma_dir.exists() and any(chroma_dir.iterdir())):
        ...  # boş → ingest
    else:
        stored  = read_collection_embedding_model(chroma_dir)
        current = get_embedding_provider().name()
        if stored != current:               # ör. hash → multilingual-e5 geçişi
            ...  # vektör uzayı geçersiz → yeniden ingest
```

İlk başlatmada `data/guidelines/` dizinindeki tüm dosyalar taranır ve ChromaDB'ye yüklenir (~30 sn). Embedding modeli `EMBEDDING_MODEL` ile değiştirildiğinde koleksiyon otomatik olarak yeniden oluşturulur.

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

### Embedding: Anlamsal Model (multilingual-e5)

Katman B'nin retrieval kalitesi tamamen embedding'in anlamı yakalayabilmesine bağlıdır. Bu yüzden tek bir **`EmbeddingProvider`** soyutlaması altında iki implementasyon vardır ([`app/rag/embeddings.py`](backend/app/rag/embeddings.py)):

| Sağlayıcı | Ne zaman | Kalite |
|-----------|----------|--------|
| **`SentenceTransformerEmbedding`** (varsayılan) | Model yüklenebiliyorsa | Gerçek anlamsal, çok-dilli (Türkçe dahil) |
| **`SimpleHashEmbedding`** (fallback) | Model indirilemez/paket yoksa | Anlamsal **değil** — yalnızca yüzeysel; loglara açık uyarı basar |

- **Varsayılan model:** `intfloat/multilingual-e5-small` (≈120 MB, 384 boyut, CPU'da çalışır). `EMBEDDING_MODEL` ortam değişkeniyle değiştirilebilir (ör. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`).
- **e5 prefix'leri:** e5 ailesi sorgu ve dokümanları farklı işaretler. Dokümanlar `passage:`, sorgular `query:` ön ekiyle vektörlenir. Retriever sorguyu manuel vektörleyip `query_embeddings` ile arar; böylece sorguya yanlışlıkla `passage:` uygulanmaz.
- **Koleksiyon metadata + otomatik yeniden ingest:** Kullanılan model adı koleksiyon metadata'sına (`embedding_model`) yazılır. Pipeline başlarken aktif model ile koleksiyondaki model farklıysa (ör. hash → e5 geçişi) otomatik olarak yeniden ingest tetiklenir; eski vektör uzayı çöp olmaz.
- **Fallback davranışı:** Model yüklenemezse uygulama çökmez; `SimpleHashEmbedding`'e düşülür ve `/status` çıktısının `B.detail` alanında `embedding: fallback (hash) — düşük kalite` görünür.

#### Hash neden yetersizdi? (sayısal kanıt)

`python -m scripts.embedding_compare` — anlamca yakın ama **farklı kelimelerle** yazılmış 5 sorgu–doküman çifti üzerinde cosine benzerliği:

```
İlgili çiftte ortalama cosine:   hash=0.274   anlamsal=0.843   (×3.1 daha yüksek)
Anlamsal modelin daha yüksek olduğu sorgu sayısı: 5/5
```

Çarpıcı örnek: *"üst makama yazılan yazıda yanlış kapanış"* sorgusu için hash embedding, anlamca ilgili kapanış maddesine (0.193) **alan dışı bir cümleden ("patates haşlama süresi", 0.252) daha düşük** skor verir — yani yanlış belgeyi öne çıkarır. Anlamsal model 5 sorgunun tamamında ilgili maddeyi üstte tutar. (e5 mutlak benzerlik tabanı yüksektir; bu nedenle önemli olan göreli sıralamadır.)

#### Gerçek retrieval örneği (kabul kriteri)

`retriever.search_by_rule("kapanış ifadesi arz ederim üst makam hiyerarşi")` (569 chunk'lık gerçek koleksiyon, e5):

```
1. [Resmi Yazışma Yönetmeliği — Ek Örnekler | Madde 17]  "| Durum | Doğru İfade | ..."
2. [Resmi Yazışma Yönetmeliği — Ek Örnekler | Madde 17]  "Gereği için alt makam | Gereğini rica ederim | Onay yazılarında | OLUR"
3. [Resmi Yazışma Yönetmeliği — Ek Örnekler | Bölüm 1]   "ÖRNEK 19/B ..."
```

İlk iki sonuç, HIR-001'in dayandığı **kapanış-hiyerarşi tablosu** maddesidir.

---

## Türkçe Dil İşleme Zorlukları

Türkçe, İngilizce gibi dillere göre metin işlemeyi zorlaştıran iki temel özelliğe sahiptir. Sistem her ikisini de [`backend/app/services/turkish_text.py`](backend/app/services/turkish_text.py) altında ele alır.

### 1. Sondan eklemeli (agglutinative) yapı

Türkçe'de bir kök çok sayıda ek alarak farklı çekimlere girer. Resmi yazışmadaki kapanış ifadesi tek bir kalıp değildir:

```
arz ederim · arz ederiz · arz edilmektedir · arz ediyorum · arz olunur
rica ederim · rica ederiz · rica olunur · rica edilmektedir
```

Sabit string eşleşmesi (`"Arz ederim" in text`) bu varyasyonların çoğunu **kaçırır** ve kapanış var olduğu hâlde CLS-001 ("kapanış eksik") yanlış tetiklenir. Çözüm, **kök + onaylı fiil gövdesi** yaklaşımıdır:

```python
# turkish_text.py — "arz"/"rica" kökü + "ed-"/"olun-" gövdesi + serbest ek
_ARZ_RE  = re.compile(r"\barz(?:\s+ve\s+rica)?\s+(?:ed|olun)[a-zçğıöşü]*", re.IGNORECASE)
_RICA_RE = re.compile(r"\brica\s+(?:ed|olun)[a-zçğıöşü]*", re.IGNORECASE)
```

`is_closing_line()` ayrıca eşleşmenin paragraf **sonunda** olmasını arar; böylece gövde içindeki "arz edilen konular" gibi çekimler kapanış sayılmaz. CLS-001 ve HIR-001 bu çekim-toleranslı tespitten faydalanır: "arz edilmektedir" geçerli kapanış sayılır, ancak üst makama "rica ederiz" (çekimli) yazıldığında HIR-001 hâlâ doğru tetiklenir.

### 2. "İ / I" büyük-küçük harf problemi

Latin alfabesinde `'I'`'nın küçüğü `'i'` kabul edilir; Türkçe'de ise `I↔ı` (noktasız) ve `İ↔i` (noktalı) ayrıdır. Python'un yerleşik metotları bunu yanlış yapar:

```python
"İLGİ".lower()   # → "i̇lgi"  (i + birleşik nokta — bozuk karşılaştırma)
"Bilgi".upper()  # → "BILGI"  ("BİLGİ" olmalıydı)
```

`tr_lower()` / `tr_upper()` Türkçe locale kurallarını uygular (`İ→i`, `I→ı`, `i→İ`, `ı→I`). Parser'ın birim tespiti, Katman B'nin muhatap/dağıtım (`GEREĞİ`/`BİLGİ`) karşılaştırmaları ve kapanış analizleri artık bu yardımcıları kullanır:

```python
tr_lower("İLGİ")   # → "ilgi"
tr_upper("ığdır")  # → "IĞDIR"
tr_upper("bilgi")  # → "BİLGİ"
```

### 3. Neden Türkçe için anlamsal embedding şart? (Eksik 1 ile bağ)

Eski hash embedding ([SimpleHashEmbedding](#embedding-anlamsal-model-multilingual-e5)) metni karakter trigram'larına bölüp hashler. Türkçe'nin çekim ekleri tam da bu trigram dağılımını kaydırır: "ilgi", "ilgili", "ilgisine", "ilgilendirir" karakter düzeyinde benzer görünse de "öğrenci muafiyeti" ↔ "öğrencinin muaf tutulması" gibi **eş anlamlı ama farklı kelimelerle** yazılmış ifadeler trigram uzayında uzak düşer — anlamsal yakınlık kaybolur. Hash ile yapılan ölçümde alan-içi ilgili çiftlerin ortalama benzerliği yalnızca **0.27**'dir ve kimi durumda alan dışı bir cümle (ör. "patates haşlama süresi") ilgili maddeden daha yüksek skor alır.

Çok-dilli `sentence-transformers` modeli (`multilingual-e5-small`) ise kelimeleri değil **anlamı** öğrenilmiş bir temsile gömer; aynı çiftlerde benzerlik **0.84**'e çıkar (×3.1) ve çekim/eş anlam farkları korunur. Sayısal kanıt: `python -m scripts.embedding_compare`.

### Bilinen sınırlamalar

- **Argo / kurum-içi kısaltmalar:** Standart dışı kısaltmalar (ör. "Müh. Fak.") ve argo, model eğitim dağılımında seyrek olabilir.
- **OCR'lı belgeler:** Taranıp OCR'dan geçmiş `.docx`'lerde karakter hataları hem parser'ı hem embedding'i yanıltabilir.
- **Bağlamsal kısaltmalar:** "Hk." (hakkında), "a." (adına) gibi noktalı kısaltmalar cümle sonu noktalamasıyla karışabilir; bu yüzden kısaltmalar LNG-003'te ayrıca elenir.

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
| Groq / Llama | `llama-3.3-70b-versatile` | Yedek — ücretsiz tier |

> **Önemli:** `gemini-2.0-flash` yeni ücretsiz hesaplarda kota sıfırdır. `gemini-2.5-flash` kullanın.

### Prompt Tasarımı

LLM'e gönderilen prompt yapılandırılmış JSON çıkışı zorunlu kılar:

```
KONU: {konu_satiri}
MUHATAP: {muhatap}
METİN: {metin[:2500]}
KAPANIŞ: {kapanis_ifadesi}
EK LİSTESİ: {ekler}

İLGİLİ YÖNERGİ MADDELERİ (RAG bağlamı):
[Katman B'den çekilen 3 ilgili ChromaDB chunk]

Yanıtı SADECE JSON dizisi olarak döndür:
[{
  "category": "konu_metin",
  "severity": "error",
  "title": "...",
  "description": "...",
  "found_text": "Sorunlu metnin doğrudan alıntısı",
  "suggestion": "...",
  "suggested_text": "Yeniden yazılmış öneri (anlatim/konu_metin için)",
  "confidence": 0.85
}]
```

### Confidence Scoring

- LLM her bulgu için `0.0–1.0` arası güven skoru verir
- `confidence < 0.50` olan bulgular otomatik filtrelenir
- UI'da her Katman C bulgusunda kanıt alıntısı (`found_text`) ve yeniden yazım önerisi (`suggested_text`) gösterilir

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
3. Sağlayıcı seç (Gemini / Groq)
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
- **Bellek/disk:** Katman B anlamsal embedding modeli (`multilingual-e5-small`) ≈120 MB indirilir ve ≈400 MB RAM kullanır. İmaj derlenirken modele bir kez internet gerekir (sonra imaja gömülür, çalışma anı offline'dır). **512 MB'lık Free planlarda OOM riski** vardır; bu durumda model yüklenemez ve düşük kaliteli hash fallback devreye girer — anlamsal retrieval için ≥2 GB RAM (DigitalOcean Droplet) önerilir.

### Başlatma

```bash
# 1. Repo'yu klonla
git clone https://github.com/histekli/graduation-project-2.git
cd graduation-project-2

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

## DigitalOcean Droplet Deployment (Önerilen)

Kalıcı bir demo/production yayını için **önerilen yöntem** budur. Uygulama, bir Ubuntu sunucu (DigitalOcean Droplet) üzerinde Docker Compose ile çalışır; host makinedeki **Nginx reverse proxy**, dış trafiği container'lara yönlendirir. Frontend (Next.js, 3000) ve backend (FastAPI, 8000) container portları yalnızca `127.0.0.1`'e bağlanır — dışarıya yalnızca Nginx (80/443) açıktır.

```
Tarayıcı ──▶ Nginx (host :80/:443) ──┬──▶ /        Next.js  (127.0.0.1:3000)
                                     └──▶ /api/    FastAPI  (127.0.0.1:8000)
```

İlgili dosyalar: [`docker-compose.prod.yml`](docker-compose.prod.yml) · [`docs/nginx-ip.conf`](docs/nginx-ip.conf) · [`docs/nginx-domain.conf`](docs/nginx-domain.conf) · [`scripts/deploy-digitalocean.sh`](scripts/deploy-digitalocean.sh) · [`.env.digitalocean.example`](.env.digitalocean.example)

### 1. Droplet oluştur

- **Image:** Ubuntu 22.04 veya 24.04 LTS
- **Boyut:** en az **2 GB RAM** (ChromaDB ingest + iki container için önerilir)
- Docker Marketplace image'ı ya da düz Ubuntu kullanılabilir.

### 2. Sunucuya bağlan

```bash
ssh root@SERVER_IP
```

### 3. Docker + Docker Compose kur

Ubuntu image'ında Docker yoksa:

```bash
curl -fsSL https://get.docker.com | sh
docker --version && docker compose version
```

### 4. Repoyu klonla

```bash
git clone https://github.com/histekli/graduation-project-2.git
cd graduation-project-2
```

### 5. Ortam değişkenlerini ayarla

```bash
cp .env.digitalocean.example .env
nano .env        # GEMINI_API_KEY ve SERVER_IP değerlerini doldur
```

IP ile test için: `NEXT_PUBLIC_API_URL=http://SERVER_IP/api` ve `CORS_ORIGINS=http://SERVER_IP`.

### 6. Container'ları başlat

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

İlk başlatmada ChromaDB vektör veritabanı otomatik oluşturulur (~30 sn). Sonraki güncellemeler için [`scripts/deploy-digitalocean.sh`](scripts/deploy-digitalocean.sh) tek komutla `git pull` + yeniden derleme yapar.

### 7. Nginx kur ve IP üzerinden yayına al

```bash
sudo apt update && sudo apt install -y nginx
sudo cp docs/nginx-ip.conf /etc/nginx/sites-available/doh
sudo ln -s /etc/nginx/sites-available/doh /etc/nginx/sites-enabled/doh
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 8. Test et

```bash
curl http://SERVER_IP/api/health        # {"status":"ok"}
```

Tarayıcıdan **http://SERVER_IP** → uygulama arayüzü.

### 9. Güvenlik duvarı (UFW)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

Container portları (3000/8000) zaten yalnızca `127.0.0.1`'e bağlıdır; UFW dış trafiği yalnızca SSH ve Nginx ile sınırlar.

### 10. (Opsiyonel) Domain + HTTPS

1. **DNS:** `domain.com`, `www.domain.com`, `api.domain.com` için A kaydını Droplet IP'sine yönlendirin.
2. `.env` dosyasında domainli değerleri kullanın ve container'ları yeniden başlatın:
   ```
   NEXT_PUBLIC_API_URL=https://api.domain.com
   CORS_ORIGINS=https://domain.com,https://www.domain.com
   ```
   ```bash
   docker compose -f docker-compose.prod.yml up --build -d
   ```
3. [`docs/nginx-domain.conf`](docs/nginx-domain.conf) dosyasını kullanın (`domain.com` yerlerini değiştirin), ardından `sudo nginx -t && sudo systemctl reload nginx`.
4. SSL sertifikası (Certbot HTTPS bloklarını ve yönlendirmeyi otomatik ekler):
   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d domain.com -d www.domain.com -d api.domain.com
   ```

### Dağıtım öncesi kontrol listesi

- [ ] `.env` dolu (`GEMINI_API_KEY`, `NEXT_PUBLIC_API_URL`, `CORS_ORIGINS`) ve git'e **gönderilmemiş**
- [ ] `docker compose -f docker-compose.prod.yml ps` → her iki container `Up (healthy)`
- [ ] `curl http://SERVER_IP/api/health` → `{"status":"ok"}`
- [ ] Tarayıcıdan belge yükleme uçtan uca çalışıyor
- [ ] UFW etkin; yalnızca SSH + Nginx açık
- [ ] (Domainli) SSL sertifikası geçerli, `https://` çalışıyor

> **Güvenlik:** API anahtarları yalnızca sunucudaki `.env` dosyasında tutulur. `.env` ve `data/api_config.json` `.gitignore`'dadır ve **asla commit'lenmez** — anahtarları repoya yüklemeyin.

---

## Alternatif: Ücretsiz Demo Deploy (Render + Vercel)

> Bu proje için **önerilen yöntem yukarıdaki DigitalOcean Droplet** kurulumudur. Render + Vercel ücretsizdir ancak Free plan uyku/cold-start sınırlarına sahiptir; kısa süreli, sunucu istemeyen demolar için uygundur.

1–2 haftalık bir demo yayını için backend **Render Free Web Service**, frontend **Vercel** üzerinde ücretsiz çalıştırılabilir. Domain gerekmez; her iki platformun verdiği URL'ler kullanılır.

```
Tarayıcı ──▶ Vercel (Next.js frontend)  ──fetch──▶  Render (FastAPI + ChromaDB)
            https://<proje>.vercel.app              https://<proje>.onrender.com
```

> **Sıra önemli:** önce **backend (Render)**, sonra **frontend (Vercel)**, en son **CORS** güncellemesi.

### A) Backend — Render

1. [render.com](https://render.com) hesabı aç, GitHub ile bağlan.
2. **New + → Blueprint** seç ve bu repoyu bağla. Repo kökündeki [`render.yaml`](render.yaml) otomatik algılanır (servis `doh-backend`, Docker, Free plan, health check `/health`).
   - Blueprint istemezsen elle: **New + → Web Service** → repoyu bağla → **Root Directory: `backend`** → **Runtime: Docker** → **Health Check Path: `/health`** → **Instance Type: Free**.
3. **Environment** değişkenlerini gir:

   | Key | Değer |
   |-----|-------|
   | `GEMINI_API_KEY` | (Gemini anahtarın — gizli) |
   | `LAYER_C_PROVIDER` | `gemini` |
   | `LAYER_C_MODEL` | `gemini-2.5-flash` |
   | `CORS_ORIGINS` | şimdilik `*` (Vercel URL belli olunca güncellenecek) |

   > `PORT` **GİRME** — Render otomatik enjekte eder, `entrypoint.sh` bu değeri kullanır (`--port ${PORT:-8000}`).
4. **Create / Apply** — Render imajı derler; anlamsal embedding modeli (`multilingual-e5-small`) derleme sırasında indirilip imaja gömülür ve ChromaDB bu modelle oluşturulur. Çalışma anı offline'dır. İlk build birkaç dakika sürer. ⚠ Free plan 512 MB RAM'dir; e5 modeli OOM verirse hash fallback'e düşülür (düşük kaliteli retrieval).
5. Deploy bitince Render bir URL verir: `https://doh-backend-xxxx.onrender.com`. Bunu kopyala.
6. Test: tarayıcıda `https://doh-backend-xxxx.onrender.com/health` aç → `{"status":"ok"}` görmelisin (Swagger için `/docs`).

### B) Frontend — Vercel

1. [vercel.com](https://vercel.com) hesabı aç, GitHub ile bağlan.
2. **Add New → Project** → bu repoyu seç → **Import**.
3. Proje ayarları:

   | Ayar | Değer |
   |------|-------|
   | Framework Preset | Next.js (otomatik algılanır) |
   | Root Directory | `frontend` |
   | Build Command | `npm run build` (varsayılan) |
   | Output Directory | (varsayılan — dokunma) |
4. **Environment Variables** ekle:

   | Key | Value |
   |-----|-------|
   | `NEXT_PUBLIC_API_URL` | `https://doh-backend-xxxx.onrender.com` (A.5'teki URL, sonunda `/` **olmadan**) |
5. **Deploy** — bitince Vercel bir URL verir: `https://<proje>.vercel.app`.

### C) Son CORS düzeltmesi

Vercel URL'si artık belli. Backend'in yalnızca ona izin vermesi için:

1. Render → servis → **Environment** → `CORS_ORIGINS` değerini Vercel URL'sine güncelle:
   ```
   CORS_ORIGINS=https://<proje>.vercel.app
   ```
2. **Save Changes** — Render otomatik yeniden dağıtır. (Demo süresince `*` de bırakılabilir, fakat URL ile sınırlamak daha güvenlidir.)

Artık `https://<proje>.vercel.app` üzerinden uygulama uçtan uca çalışır.

### D) Demo uyarıları (ücretsiz plan sınırları)

- **Uyku:** Render Free servis ~15 dk istek almazsa uykuya geçer. Sonraki ilk istek servisi uyandırır ve **30–60 sn** sürebilir.
- **Isındırma:** Demo öncesi `https://doh-backend-xxxx.onrender.com/health` adresini açarak backend'i önceden uyandır.
- **ChromaDB + embedding modeli:** Vektör veritabanı ve `multilingual-e5-small` modeli imaja gömülüdür; her cold start'ta hazırdır. Ancak çalışma anında diske yazılan veriler (ör. UI'dan kaydedilen API anahtarı) **kalıcı değildir** — yeniden dağıtımda sıfırlanır. Bu yüzden demo için anahtarı UI yerine Render `GEMINI_API_KEY` env değişkeninden vermek daha sağlamdır.
- **Bellek:** Free plan 512 MB RAM'dir; e5 modeli (~400 MB) bu sınırı zorlar ve OOM verirse Katman B hash fallback'e düşer (düşük kaliteli retrieval; `/status` `B.detail`'de görünür). Anlamsal retrieval gerekiyorsa ≥2 GB'lık DigitalOcean Droplet kullanın. Free plan yoğun eşzamanlı kullanım için değil, demo amaçlıdır.

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
python -m tests.create_comprehensive_docs   # 60 senaryo belgesi
python -m tests.create_test_docs            # 8 temel senaryo (test_all_errors.docx dahil)

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
    "A": {"active": true, "label": "Deterministik Kural Motoru", "detail": "20 kural — her zaman aktif"},
    "B": {"active": true, "label": "RAG Kontrol", "detail": "ChromaDB hazır · embedding: st::intfloat/multilingual-e5-small"},
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
  "compliance_score": 72,
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
    },
    {
      "id": "C001",
      "layer": "C",
      "severity": "warning",
      "rule_code": "SEM-004",
      "title": "Anlatım bozukluğu",
      "description": "Özne-yüklem uyumsuzluğu tespit edildi.",
      "found": "...ilgili birimler tarafından yapılmaktadır...",
      "suggested_text": "...ilgili birimler bu işlemleri yürütmektedir...",
      "reference": "TDK Yazım Kılavuzu; Resmi Yazışma Dili",
      "confidence": 0.82
    }
  ]
}
```

**Uyum Skoru:** Kural-ağırlıklı, oransal formül — bkz. [Uyum Skoru (Ağırlıklı)](#uyum-skoru-ağırlıklı).

### `POST /analyze-and-fix`

Analiz eder, otomatik düzeltilebilen hataları uygular ve düzeltilmiş `.docx` döner. Belge sonuna UYUM DENETİM RAPORU tablosu eklenir.

```bash
curl -X POST http://localhost:8000/analyze-and-fix \
  -F "file=@belge.docx" \
  -F "mode=full" \
  -o belge_duzeltilmis.docx
```

### `GET /health`

```json
{"status": "ok"}
```

---

## Test Altyapısı

### Test Belgeleri (76 Senaryo)

`backend/tests/fixtures/` altında 76 programatik test belgesi:

| Grup | Adet | Kapsam |
|------|------|--------|
| `a_*` | 26 | Katman A: FMT, FLD, CLS, LNG + deterministik içerik (SEM-002, SEM-006) |
| `b_*` | 10 | Katman B: HIR-001..005 + doğru örnekler |
| `c_*` | 8 | Katman C: SEM-001/003/004 + doğru örnek |
| `mix_*` | 7 | Çok katmanlı senaryolar |
| `infl_*` | 4 | Türkçe kapanış çekim varyasyonları (arz edilmektedir/olunur/ederiz) |
| `ok_*` | 13 | Referans belgeler (false-positive kontrolü, farklı biçimsel varyasyonlar) |
| `test_*` | 8 | Temel senaryo belgeleri (test_all_errors dahil) |

Ayrıca [`tests/fixtures/section_labels.json`](backend/tests/fixtures/section_labels.json): bölüm tespiti için elle doğrulanmış ground-truth (5 belge, 72 paragraf).

```bash
# Test belgelerini oluştur
cd backend
python -m tests.create_comprehensive_docs
python -m tests.create_test_docs
```

`test_all_errors.docx`: LNG-001..007, FMT-001/002, HIR-001 ve Layer C bulgularını aynı anda tetikleyen kapsamlı test belgesi.

### Test Modülleri (~198 test)

```
test_comprehensive.py   → Katman A/B/C senaryoları + TestFalsePositives (genişletilmiş ok_* seti)
test_scenarios.py       → Senaryo tabanlı entegrasyon (A/B/C/pipeline)
test_pipeline.py        → Pipeline entegrasyonu
test_turkish_text.py    → tr_lower/tr_upper + çekim-toleranslı kapanış (EKSIK 5)
test_embeddings.py      → EmbeddingProvider, e5/hash, fallback, metadata (EKSIK 1)
test_scoring.py         → Kural-ağırlıklı uyum skoru (EKSIK 2)
test_layer_integrity.py → Bulgu 'layer' alanı doğruluğu, Katman C = LLM-only (EKSIK 4)
test_parser_metrics.py  → Bölüm tespiti P/R/F1 + ok_* yanlış-alarm eşiği (EKSIK 3)
```

**Ölçülen metrikler:** bölüm tespiti accuracy **%97.2** / macro-F1 **0.974** (72 paragraf); `ok_*` referans belgelerinde **0 yanlış-alarm**. Bkz. [Parser Güvenilirliği](#parser-güvenilirliği-bölüm-tespiti).

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
│   │   │   ├── parser.py            # .docx ayrıştırıcı (12 bölüm, skorlu muhatap tespiti)
│   │   │   ├── turkish_text.py      # Türkçe tr_lower/tr_upper + çekim-toleranslı kapanış
│   │   │   ├── layer_a.py           # Deterministik motor (biçim/alan/dil + SEM-002/006)
│   │   │   ├── layer_b.py           # RAG destekli kontrol (HIR-001..005)
│   │   │   ├── layer_c.py           # YALNIZCA LLM semantik analiz (Gemini/Groq)
│   │   │   │                        # _from_config() · save_config() · hot-reload
│   │   │   ├── fixer.py             # Belge düzeltici (11 otomatik kural) + rapor tablosu
│   │   │   └── pipeline.py          # Orkestratör · ChromaDB auto-ingest · uyum skoru
│   │   ├── rules/
│   │   │   ├── hierarchy.py         # GTU org. hiyerarşisi + kapanış kuralları tablosu
│   │   │   └── scoring_weights.py   # Kural-ağırlıklı uyum skoru (KRİTİK/ORTA/DÜŞÜK)
│   │   └── rag/
│   │       ├── embeddings.py        # EmbeddingProvider: SentenceTransformer + hash fallback
│   │       ├── ingest.py            # Çok-format yükleyici + koleksiyon embedding metadata
│   │       └── retriever.py         # Hibrit ChromaDB arama (query_embeddings, kaynak filtreli)
│   ├── data/
│   │   ├── guidelines/              # Kaynak belgeler (6 dosya)
│   │   │   ├── YÖ-0030...R5.pdf    # GTU Yazışma Yönergesi
│   │   │   ├── Cumhurbaşkanlığı... # CB Kılavuzu 2025 PDF
│   │   │   ├── Resmi Yazışma...pdf  # Yönetmelik PDF
│   │   │   ├── Dilekçe...3071.pdf   # Kanun PDF
│   │   │   ├── tdk_tum_kurallar.json # TDK web scraping sonucu
│   │   │   ├── yonetmelik_tam_metin.txt
│   │   │   └── yonetmelik_ek_ornekler.txt
│   │   ├── chromadb/               # ChromaDB vektör veritabanı (569 chunk, gitignore)
│   │   └── api_config.json         # UI'dan kaydedilen API anahtarı (gitignore)
│   ├── tests/
│   │   ├── fixtures/               # 76 test belgesi + section_labels.json (ground-truth)
│   │   ├── create_comprehensive_docs.py  # senaryo + ok_* + infl_* oluşturucu
│   │   ├── create_test_docs.py     # 8 temel senaryo oluşturucu
│   │   ├── test_comprehensive.py   # Katman A/B/C senaryoları + FP
│   │   ├── test_scenarios.py       # Senaryo entegrasyonu
│   │   ├── test_pipeline.py        # Pipeline entegrasyon
│   │   ├── test_turkish_text.py    # Türkçe normalizasyon + çekim (EKSIK 5)
│   │   ├── test_embeddings.py      # EmbeddingProvider + fallback (EKSIK 1)
│   │   ├── test_scoring.py         # Ağırlıklı skor (EKSIK 2)
│   │   ├── test_layer_integrity.py # Katman ayrımı (EKSIK 4)
│   │   └── test_parser_metrics.py  # Bölüm tespiti F1 + FP eşiği (EKSIK 3)
│   ├── scripts/                    # embedding_compare.py · score_compare.py
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
│   │                               # ResultsPanel · FindingCard · StatCard
│   │                               # Uyum skoru · Yapay zeka yeniden yazım önerisi paneli
│   ├── Dockerfile                  # Multi-stage: deps → builder → runner
│   └── package.json                # Next.js 14 + React 18
├── docs/
│   ├── nginx-ip.conf               # Nginx — IP ile yayın (/ → frontend, /api → backend)
│   └── nginx-domain.conf           # Nginx — domain + api.domain.com + SSL notları
├── scripts/
│   └── deploy-digitalocean.sh      # git pull + compose down/up --build -d
├── docker-compose.yml              # Yerel: backend + frontend · chromadb_data volume
├── docker-compose.prod.yml         # Production: portlar 127.0.0.1'e bağlı (Nginx önü)
├── .env.example                    # Ortam değişkeni şablonu (yerel)
├── .env.digitalocean.example       # Ortam değişkeni şablonu (DigitalOcean)
├── render.yaml                     # Render Blueprint (alternatif deploy)
├── .gitignore                      # .env · chromadb/ · api_config.json
└── README.md                       # Bu dosya
```

---

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `GEMINI_API_KEY` | — | Katman C (Gemini, birincil) için. Yoksa Katman C devre dışı |
| `GROQ_API_KEY` | — | Katman C (Groq / Llama 3.3 70B, yedek) için. Opsiyonel |
| `LAYER_C_PROVIDER` | `gemini` | `"gemini"` veya `"groq"` |
| `LAYER_C_MODEL` | `gemini-2.5-flash` | Model ID override (groq → `llama-3.3-70b-versatile`) |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Katman B anlamsal embedding modeli. Yüklenemezse hash fallback'e düşülür. ~400 MB RAM |
| `CORS_ORIGINS` | — | İzinli frontend origin'leri (virgülle ayrılmış) veya `*` (demo) |
| `PORT` | `8000` | Backend portu. Render/Cloud platformları otomatik enjekte eder |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend'in backend URL'i (build-time'da inline) |

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
