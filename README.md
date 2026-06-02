# Dekanlık Yazışma Uyum Denetleyicisi

GTU Mühendislik Fakültesi Dekanlık ofisi için resmi yazışmaları (.docx) denetleyen web tabanlı akıllı asistan.

**CSE 496 — Bitirme Projesi** · Hasan Can İSTEKLİ · Danışman: Prof. Mehmet GÖKTÜRK

---

## Mimari

Yüklenen .docx belgesi üç katmanlı bir sistemden geçer:

```
.docx
  │
  ▼
┌──────────────────────────────────────────────────────┐
│  Katman A — Deterministik Kural Motoru               │
│  16 kural · python-docx · regex · sıfır hallüsinasyon│
│  FMT-001/002  FLD-001..007  CLS-001..003  LNG-001..004│
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│  Katman B — RAG Destekli Kuralsal Kontrol            │
│  ChromaDB · 177 chunk (TDK + YÖ-0030 R5)            │
│  Hiyerarşi uyumu · Her bulguya madde referansı       │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│  Katman C — Semantik / Mantıksal Analiz (LLM)        │
│  Google Gemini API (birincil) · Claude API (opsiyonel)│
│  SEM-001..004 · Confidence scoring · JSON output      │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
                   JSON Rapor
              + Düzeltilmiş .docx
```

**Stack:** FastAPI · python-docx · ChromaDB · Google Gemini · Next.js 14 · Docker

---

## Hızlı Başlangıç (Docker)

### Gereksinimler

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/install/) ≥ 2.20
- Google Gemini API anahtarı ([ücretsiz](https://aistudio.google.com/app/apikey))

### 1. Ortam değişkenlerini ayarla

```bash
cp .env.example .env
# .env dosyasını düzenle — en az GEMINI_API_KEY doldurulmalı
```

### 2. Başlat

```bash
docker compose up --build
```

İlk başlatmada backend, ChromaDB vektör veritabanını otomatik olarak oluşturur (~30 sn).

| Servis    | URL                    |
|-----------|------------------------|
| Frontend  | http://localhost:3000  |
| Backend   | http://localhost:8000  |
| API Docs  | http://localhost:8000/docs |

### 3. Durdur

```bash
docker compose down          # container'ları durdur (veri korunur)
docker compose down -v       # veri dahil tamamen temizle
```

---

## Geliştirme (Docker olmadan)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# ChromaDB oluştur (ilk kez)
python -m app.rag.ingest

# Sunucuyu başlat
GEMINI_API_KEY=your_key uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
# → http://localhost:3000
```

### Testler

```bash
cd backend
pytest tests/ -v
# Beklenen: 3 passed, 1 skipped (RAG testi — ChromaDB verisi gerektiriyor)
```

---

## API

### `POST /analyze`

Belgeyi analiz eder, JSON rapor döner.

```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@belge.docx" \
  -F "mode=full"
```

**Parametreler:**
| Parametre | Değerler | Açıklama |
|-----------|----------|----------|
| `file`    | `.docx`  | Max 10 MB |
| `mode`    | `full` · `format_only` · `content_only` | Hangi katmanlar çalışsın |

**Yanıt:**
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
      "description": "...",
      "suggestion": "...",
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

Otomatik düzeltilen kurallar: `FMT-001` `FMT-002` `LNG-002` `LNG-004` `CLS-002`

Dönen belgede sonuna "UYUM DENETİM RAPORU" tablosu eklenir.

### `GET /health`

```json
{"status": "ok"}
```

---

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `GEMINI_API_KEY` | — | Katman C için zorunlu (Gemini kullanılıyorsa) |
| `ANTHROPIC_API_KEY` | — | Katman C için opsiyonel (Claude kullanılıyorsa) |
| `LAYER_C_PROVIDER` | `gemini` | `gemini` veya `claude` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend'in backend URL'i |

Katman C API anahtarı yoksa sessizce devre dışı kalır; Katman A + B çalışmaya devam eder.

---

## Proje Yapısı

```
dean-office-helper/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI uygulama + /analyze + /analyze-and-fix
│   │   ├── models/finding.py    # Pydantic modeller
│   │   ├── services/
│   │   │   ├── parser.py        # .docx ayrıştırıcı
│   │   │   ├── layer_a.py       # Deterministik kural motoru (16 kural)
│   │   │   ├── layer_b.py       # RAG destekli kontrol
│   │   │   ├── layer_c.py       # Semantik analiz (Gemini/Claude)
│   │   │   ├── fixer.py         # Belge düzeltici + rapor tablosu
│   │   │   └── pipeline.py      # Orkestratör
│   │   ├── rules/hierarchy.py   # GTU org. hiyerarşisi + kapanış kuralları
│   │   └── rag/
│   │       ├── ingest.py        # ChromaDB yükleme scripti
│   │       └── retriever.py     # Hibrit arama
│   ├── data/guidelines/         # TDK JSON + GTU YÖ-0030 R5 .docx
│   ├── tests/                   # pytest (3 passed, 1 skipped)
│   ├── Dockerfile
│   ├── entrypoint.sh            # ChromaDB yoksa ingest → uvicorn
│   └── requirements.txt
├── frontend/
│   ├── pages/
│   │   ├── _app.js              # Global stil + Google Fonts
│   │   └── index.js             # DeanOfficeHelper wrapper
│   ├── src/components/
│   │   └── DeanOfficeHelper.jsx # Ana UI bileşeni
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
├── .env.example
├── PROJECT_PLAN.md
└── README.md
```

---

## Lisans

Akademik kullanım — GTU CSE 496 Bitirme Projesi
