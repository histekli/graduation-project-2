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

# Anlamsal embedding modelini DERLEME aşamasında indir ve imaja göm.
# Böylece çalışma anında (offline cold-start) model HF'den indirilmek zorunda
# kalmaz. Model HF cache'ine (~/.cache/huggingface) yazılır ve imajda kalır.
ENV EMBEDDING_MODEL=intfloat/multilingual-e5-small
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('${EMBEDDING_MODEL}')"

# Uygulama kodu ve kaynak veriler
COPY app/ app/
COPY data/ data/

# ChromaDB vektör veritabanını imaj derlenirken önceden oluştur.
# Embedding modeli yukarıda imaja gömüldüğü için bu adım offline çalışır ve
# runtime cold start hızlanır. Koleksiyon metadata'sına model adı yazılır;
# model değişirse pipeline başlangıçta otomatik yeniden ingest eder.
RUN python -m app.rag.ingest

# Entrypoint scripti
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
