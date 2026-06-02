#!/bin/sh
set -e

# İlk başlatmada ChromaDB yoksa ingest et
CHROMA_PATH="/app/data/chromadb"
if [ ! -d "$CHROMA_PATH" ] || [ -z "$(ls -A "$CHROMA_PATH" 2>/dev/null)" ]; then
    echo "[entrypoint] ChromaDB bulunamadı — vektör veritabanı oluşturuluyor..."
    python -m app.rag.ingest
    echo "[entrypoint] Ingest tamamlandı."
else
    echo "[entrypoint] ChromaDB mevcut — ingest atlanıyor."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
