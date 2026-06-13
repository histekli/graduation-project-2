"""
Pipeline Servisi
Tüm katmanları sırayla çalıştırır ve sonuçları birleştirir.
"""
from __future__ import annotations
import logging
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=False) or ".env")

from app.models.finding import (
    AnalysisResult, Finding, Severity, ParsedDocument
)
from app.services.parser import parse_docx
from app.services.layer_a import LayerA
from app.services.layer_b import LayerB
from app.services.layer_c import LayerC
from app.rag.retriever import GuidelineRetriever

logger = logging.getLogger(__name__)

_DEFAULT_CHROMA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chromadb"
_GUIDELINES_DIR     = Path(__file__).resolve().parent.parent.parent / "data" / "guidelines"


def _ensure_chromadb(chroma_dir: Path) -> None:
    """ChromaDB dizini yoksa veya boşsa otomatik olarak ingest çalıştırır."""
    if chroma_dir.exists() and any(chroma_dir.iterdir()):
        return
    if not _GUIDELINES_DIR.exists():
        logger.warning("Kılavuz dizini bulunamadı: %s — Katman B devre dışı", _GUIDELINES_DIR)
        return
    logger.info("ChromaDB boş — otomatik ingest başlatılıyor (%s)...", chroma_dir)
    try:
        from app.rag.ingest import run_ingest
        run_ingest(data_dir=_GUIDELINES_DIR.parent, persist_dir=chroma_dir)
        logger.info("ChromaDB ingest tamamlandı.")
    except Exception as exc:
        logger.error("ChromaDB ingest başarısız: %s — Katman B devre dışı kalacak", exc)


class Pipeline:
    """Belge analiz pipeline'ı."""

    def __init__(self, chroma_dir: str | None = None):
        self._last_layer_c_error: str | None = None
        self.layer_a = LayerA()

        # Katman B: RAG varsa aktif et; yoksa otomatik ingest dene
        retriever = None
        target_dir = Path(chroma_dir) if chroma_dir else _DEFAULT_CHROMA_DIR
        _ensure_chromadb(target_dir)
        if target_dir.exists():
            retriever = GuidelineRetriever(persist_dir=str(target_dir))

        self.layer_b = LayerB(retriever=retriever) if retriever and retriever.is_ready else None

        # Katman C: env/config'den API anahtarı varsa aktif
        self.layer_c = LayerC._from_config()

    def reload_layer_c(self, provider: str | None = None, api_key: str | None = None,
                       model: str | None = None) -> None:
        """Katman C'yi verilen parametrelerle (veya config'den) yeniden başlatır."""
        if provider and api_key:
            self.layer_c = LayerC(provider=provider, api_key=api_key, model=model)
        else:
            self.layer_c = LayerC._from_config()

    def analyze(self, file_path: str | Path, mode: str = "full", original_filename: str | None = None) -> AnalysisResult:
        """
        Belgeyi analiz eder ve tüm bulguları döndürür.
        
        Args:
            file_path: .docx dosya yolu
            mode: "full" | "format_only" | "content_only"
        """
        # 1. Belgeyi ayrıştır
        parsed = parse_docx(file_path, original_filename=original_filename)

        all_findings: list[Finding] = []

        # 2. Katman A — Deterministik kurallar
        if mode in ("full", "format_only"):
            layer_a_findings = self.layer_a.run(parsed)
            all_findings.extend(layer_a_findings)

        # 3. Katman B — RAG destekli kontrol
        if mode in ("full", "content_only") and self.layer_b:
            layer_b_findings = self.layer_b.run(parsed)
            all_findings.extend(layer_b_findings)

        # 4. Katman C — Semantik analiz (LLM destekli)
        if mode in ("full", "content_only") and self.layer_c.is_ready:
            try:
                layer_c_findings = self.layer_c.run(parsed)
                all_findings.extend(layer_c_findings)
                self._last_layer_c_error = None
            except Exception as exc:
                self._last_layer_c_error = str(exc)
                logger.error("Katman C çalıştırılamadı: %s", exc)

        # 5. Sonuçları derle
        errors = sum(1 for f in all_findings if f.severity == Severity.ERROR)
        warnings = sum(1 for f in all_findings if f.severity == Severity.WARNING)
        infos = sum(1 for f in all_findings if f.severity == Severity.INFO)

        return AnalysisResult(
            filename=parsed.filename,
            total_findings=len(all_findings),
            errors=errors,
            warnings=warnings,
            infos=infos,
            findings=all_findings,
            parsed_document=parsed,
        )
