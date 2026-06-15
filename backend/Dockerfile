FROM python:3.11-slim

WORKDIR /app

# chromadb'nin derleme gereksinimleri
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Bağımlılıkları önce yükle (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodu ve kaynak veriler
COPY app/ app/
COPY data/ data/

# ChromaDB vektör veritabanını imaj derlenirken önceden oluştur.
# SimpleHashEmbedding offline çalışır (API anahtarı gerektirmez); böylece
# Render Free runtime'da bellek yoğun ingest çalışmaz ve cold start hızlanır.
RUN python -m app.rag.ingest

# Entrypoint scripti
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
