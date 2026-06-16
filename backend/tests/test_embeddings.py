"""
Embedding sağlayıcı testleri (EKSIK 1).

  • SimpleHashEmbedding ve SentenceTransformerEmbedding protokol uyumu
  • get_embedding_provider() fabrikası ve model yüklenemezse hash fallback
  • Koleksiyon metadata'sında embedding model adı (otomatik yeniden ingest temeli)
  • Retriever'ın fallback durumunu /status için doğru raporlaması
"""
from __future__ import annotations
import math
import pytest

import app.rag.embeddings as emb
from app.rag.embeddings import (
    SimpleHashEmbedding, get_embedding_provider, reset_provider_cache,
)


@pytest.fixture(autouse=True)
def _restore_provider():
    """Her testten sonra sağlayıcı önbelleğini sıfırla (fallback testi sızmasın)."""
    yield
    reset_provider_cache()


# ── SimpleHashEmbedding protokolü ────────────────────────────────────────────

class TestHashEmbedding:
    def test_dim_and_normalization(self):
        e = SimpleHashEmbedding()
        v = e.embed_query("resmi yazı kapanış ifadesi")
        assert len(v) == 384
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-6 or norm == 0.0

    def test_documents_shape(self):
        e = SimpleHashEmbedding()
        vs = e.embed_documents(["a b c", "d e f"])
        assert len(vs) == 2 and len(vs[0]) == 384

    def test_flags_and_name(self):
        e = SimpleHashEmbedding()
        assert e.is_fallback is True
        assert e.is_semantic is False
        assert e.name() == "hash::simple_384"

    def test_chromadb_call_interface(self):
        e = SimpleHashEmbedding()
        out = e(["belge bir", "belge iki"])  # ChromaDB __call__
        assert len(out) == 2 and len(out[0]) == 384


# ── Fabrika + fallback ───────────────────────────────────────────────────────

class TestProviderFactory:
    def test_default_is_semantic_when_available(self):
        reset_provider_cache()
        p = get_embedding_provider()
        # Bu ortamda sentence-transformers kurulu → anlamsal sağlayıcı beklenir
        assert p.is_semantic is True
        assert p.name().startswith("st::")
        assert p.dim in (384, 768)

    def test_fallback_when_model_load_fails(self, monkeypatch):
        """Model yüklenemezse hash fallback'e düşülmeli, çökmemeli."""
        def _boom(name):
            raise RuntimeError("model indirilemedi (simüle)")
        monkeypatch.setattr(emb, "_load_st_model", _boom)
        reset_provider_cache()
        p = get_embedding_provider()
        assert isinstance(p, SimpleHashEmbedding)
        assert p.is_fallback is True

    def test_singleton_cached(self):
        reset_provider_cache()
        assert get_embedding_provider() is get_embedding_provider()


# ── Koleksiyon metadata + retriever raporu ───────────────────────────────────

class TestCollectionMetadata:
    def test_collection_records_embedding_model(self):
        """Var olan koleksiyonun metadata'sındaki model, aktif sağlayıcıyla eşleşmeli."""
        from app.rag.ingest import read_collection_embedding_model
        from app.rag.retriever import CHROMA_DIR
        stored = read_collection_embedding_model(CHROMA_DIR)
        if stored is None:
            pytest.skip("ChromaDB henüz oluşturulmamış")
        assert stored == get_embedding_provider().name()

    def test_retriever_reports_fallback_label(self, monkeypatch):
        """Fallback aktifken retriever etiketi '/status' için uyarı içermeli."""
        def _boom(name):
            raise RuntimeError("model yok (simüle)")
        monkeypatch.setattr(emb, "_load_st_model", _boom)
        reset_provider_cache()
        from app.rag.retriever import GuidelineRetriever
        r = GuidelineRetriever(persist_dir="/tmp/nonexistent_emb_test")
        assert r.is_fallback is True
        assert "fallback" in r.embedding_label().lower()
