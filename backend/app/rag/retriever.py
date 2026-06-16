"""
RAG Retriever
ChromaDB'den hibrit arama (semantic + kaynak filtreli).
Katman B tarafından kullanılır.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

import chromadb

logger = logging.getLogger(__name__)

CHROMA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chromadb"
COLLECTION_NAME = "guidelines"

# Birincil kaynak tipleri — kural referansları için
_PRIMARY_SOURCE_TYPES = [
    "gtu_yonerge",
    "resmi_yazisma_yonetmeligi",
    "cb_kilavuzu",
]


class GuidelineRetriever:
    """Kılavuz/yönerge dökümanlarından ilgili chunk'ları getirir."""

    def __init__(self, persist_dir: str | Path | None = None):
        from app.rag.embeddings import get_embedding_provider

        p_dir = str(persist_dir or CHROMA_DIR)
        self.client = chromadb.PersistentClient(path=p_dir)
        self.embedding_fn = get_embedding_provider()
        try:
            self.collection = self.client.get_collection(
                COLLECTION_NAME,
                embedding_function=self.embedding_fn,
            )
        except Exception:
            self.collection = None

    @property
    def is_ready(self) -> bool:
        return self.collection is not None and self.collection.count() > 0

    @property
    def is_fallback(self) -> bool:
        """Aktif embedding hash fallback mı (anlamsal model yüklenememiş mi)?"""
        return bool(getattr(self.embedding_fn, "is_fallback", False))

    def embedding_label(self) -> str:
        """Aktif embedding modelinin insan-okunur etiketi (/status için)."""
        name = self.embedding_fn.name()
        if self.is_fallback:
            return f"fallback (hash) — düşük kalite"
        return name

    def search(
        self,
        query: str,
        n_results: int = 5,
        k: Optional[int] = None,
        source_filter: Optional[str] = None,
        source_types: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Semantik arama yapar.

        Args:
            query: Arama sorgusu
            n_results: Döndürülecek sonuç sayısı (k ile alias)
            k: n_results için kısayol
            source_filter: Tek kaynak tipi filtresi (geriye dönük uyumluluk)
            source_types: Çoklu kaynak tipi filtresi (öncelikli)

        Returns:
            [{"text": ..., "metadata": ..., "distance": ..., "id": ...}, ...]
        """
        if not self.is_ready:
            return []

        n = k if k is not None else n_results

        where_filter = None
        if source_types:
            where_filter = {"source_type": {"$in": source_types}}
        elif source_filter:
            where_filter = {"source_type": source_filter}

        # Sorguyu manuel vektörle (e5 için "query:" prefix uygulanır); ChromaDB'nin
        # query_texts yolu doküman prefix'ini ("passage:") uygulayacağı için kullanılmaz.
        query_vec = self.embedding_fn.embed_query(query)
        try:
            results = self.collection.query(
                query_embeddings=[query_vec],
                n_results=n,
                where=where_filter,
            )
        except Exception as exc:
            logger.warning("ChromaDB sorgu başarısız (bozuk collection?): %s", exc)
            return []

        output: list[dict] = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                output.append({
                    "text": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                    "id": results["ids"][0][i] if results["ids"] else None,
                })
        return output

    def search_by_rule(self, rule_topic: str, n_results: int = 3) -> list[dict]:
        """Birincil kaynaklarda (YÖ-0030 R5, Yönetmelik, CB Kılavuzu) kural araması."""
        return self.search(
            query=rule_topic,
            n_results=n_results,
            source_types=_PRIMARY_SOURCE_TYPES,
        )

    def search_tdk(self, topic: str, n_results: int = 3) -> list[dict]:
        """TDK yazım kurallarında arama."""
        return self.search(
            query=topic,
            n_results=n_results,
            source_filter="tdk_official",
        )

    def search_all(self, query: str, n_results: int = 5) -> list[dict]:
        """Tüm kaynaklarda arama."""
        return self.search(query=query, n_results=n_results)

    def get_stats(self) -> dict:
        """Veritabanı istatistikleri."""
        if not self.is_ready:
            return {"status": "not_initialized", "total_chunks": 0}
        return {
            "status": "ready",
            "total_chunks": self.collection.count(),
            "collection_name": COLLECTION_NAME,
        }
