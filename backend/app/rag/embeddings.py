"""
Embedding Sağlayıcıları (EmbeddingProvider) — Katman B / RAG vektörleştirme.

İki implementasyon, tek soyutlama:

  • SentenceTransformerEmbedding  (VARSAYILAN, gerçek anlamsal model)
      - intfloat/multilingual-e5-small (varsayılan) veya
        sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
      - Çok-dilli; Türkçe'yi öğrenilmiş temsil ile destekler.
      - e5 ailesi sorgu/doküman için prefix ister:  "query: " / "passage: "

  • SimpleHashEmbedding  (YALNIZCA fallback)
      - Karakter trigram + MD5 hash. Anlamsal değil; yalnızca model
        indirilemediğinde devreye girer ve loglara açık uyarı basar.

ChromaDB tek bir `__call__(input)` ile hem doküman ekleme hem sorgu yapar; bu
yüzden e5 prefix ayrımını korumak için DOKÜMANLAR `embed_documents` (passage),
SORGULAR `embed_query` (query) ile vektörlenir. Retriever sorguyu manuel
vektörleyip `query_embeddings=` ile arar (ChromaDB'nin query_texts yolunu
kullanmaz), böylece sorguya yanlışlıkla "passage:" prefix'i uygulanmaz.

Ortam değişkeni:
  EMBEDDING_MODEL   (varsayılan: intfloat/multilingual-e5-small)
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import Sequence

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"

# Model nesneleri ağırdır (~120 MB, ~400 MB RAM); süreç başına bir kez yüklenip
# yeniden kullanılır (Pipeline + retriever aynı modeli paylaşsın).
_MODEL_CACHE: dict = {}
_PROVIDER_SINGLETON: "EmbeddingProvider | None" = None


# ── Fallback: karakter-hash embedding ────────────────────────────────────────

class SimpleHashEmbedding:
    """
    Karakter n-gram hash tabanlı embedding (anlamsal DEĞİL).

    Ağ/model gerektirmez; yalnızca anlamsal model yüklenemezse fallback olarak
    kullanılır. Türkçe çekim ekleri trigram dağılımını kaydırdığından anlamsal
    yakınlığı yakalayamaz — bu yüzden retrieval kalitesi düşüktür.
    """
    is_fallback = True
    is_semantic = False

    def __init__(self, dim: int = 384):
        self.dim = dim
        self._name = "hash::simple_384"

    def name(self) -> str:
        return self._name

    def _embed_one(self, text: str) -> list[float]:
        # Türkçe-duyarlı küçük harf (İ→i, I→ı) — bağımsız olması için yerinde.
        text_lower = text.replace("İ", "i").replace("I", "ı").lower()
        vec = [0.0] * self.dim
        for i in range(len(text_lower) - 2):
            ngram = text_lower[i:i + 3]
            h = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    # ChromaDB EmbeddingFunction arayüzü — doküman ekleme sırasında çağrılır
    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        return self.embed_documents(list(input))


# ── Birincil: gerçek anlamsal embedding ──────────────────────────────────────

class SentenceTransformerEmbedding:
    """
    sentence-transformers tabanlı çok-dilli anlamsal embedding.

    e5 ailesi modelleri (intfloat/multilingual-e5-*) sorgu ve doküman metinlerine
    sırasıyla "query: " ve "passage: " ön ekleri ister; diğer modeller için ön ek
    boştur.
    """
    is_fallback = False
    is_semantic = True

    def __init__(
        self,
        model_name: str | None = None,
        query_prefix: str | None = None,
        passage_prefix: str | None = None,
    ):
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)

        # e5 modelleri prefix ister; paraphrase-multilingual gibi modeller istemez.
        is_e5 = "e5" in self.model_name.lower()
        self.query_prefix = (
            query_prefix if query_prefix is not None
            else ("query: " if is_e5 else "")
        )
        self.passage_prefix = (
            passage_prefix if passage_prefix is not None
            else ("passage: " if is_e5 else "")
        )

        self._model = _load_st_model(self.model_name)
        # sentence-transformers 5.x: get_embedding_dimension; eski sürüm: get_sentence_embedding_dimension
        _dim_fn = (
            getattr(self._model, "get_embedding_dimension", None)
            or self._model.get_sentence_embedding_dimension
        )
        self.dim = int(_dim_fn())

    def name(self) -> str:
        return f"st::{self.model_name}"

    def _encode(self, texts: Sequence[str], prefix: str) -> list[list[float]]:
        prefixed = [f"{prefix}{t}" for t in texts]
        vecs = self._model.encode(
            prefixed,
            normalize_embeddings=True,   # cosine için L2 normalize
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.tolist()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode(list(texts), self.passage_prefix)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text], self.query_prefix)[0]

    # ChromaDB doküman ekleme yolu → passage prefix
    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        return self.embed_documents(list(input))


# ── Yükleme / fabrika ────────────────────────────────────────────────────────

def _load_st_model(model_name: str):
    """SentenceTransformer modelini yükler (süreç içi cache)."""
    if model_name not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer
        logger.info("Anlamsal embedding modeli yükleniyor: %s", model_name)
        _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _MODEL_CACHE[model_name]


def get_embedding_provider(force_reload: bool = False) -> "EmbeddingProvider":
    """
    Aktif embedding sağlayıcısını döndürür (süreç başına tek örnek).

    Önce SentenceTransformerEmbedding denenir; model paketi yoksa veya model
    indirilemezse SimpleHashEmbedding'e düşülür ve loglara açık uyarı basılır.
    """
    global _PROVIDER_SINGLETON
    if _PROVIDER_SINGLETON is not None and not force_reload:
        return _PROVIDER_SINGLETON

    model_name = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    try:
        _PROVIDER_SINGLETON = SentenceTransformerEmbedding(model_name)
        logger.info("Embedding sağlayıcı aktif: %s (boyut=%d)",
                    _PROVIDER_SINGLETON.name(), _PROVIDER_SINGLETON.dim)
    except Exception as exc:  # ImportError, model indirme/ağ hatası vb.
        logger.warning(
            "Anlamsal embedding yüklenemedi (%s): %s — hash fallback aktif, "
            "retrieval kalitesi düşük.",
            model_name, exc,
        )
        _PROVIDER_SINGLETON = SimpleHashEmbedding()
    return _PROVIDER_SINGLETON


def reset_provider_cache() -> None:
    """Test/yeniden yapılandırma için sağlayıcı önbelleğini temizler."""
    global _PROVIDER_SINGLETON
    _PROVIDER_SINGLETON = None


# Tip ipucu için birleşik takma ad
EmbeddingProvider = SentenceTransformerEmbedding | SimpleHashEmbedding
