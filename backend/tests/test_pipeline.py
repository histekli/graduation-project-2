"""
Pipeline entegrasyon testleri.
Katman A deterministik kurallarını doğrular; RAG (Katman B) kaynak veri
gerektirdiğinden `rag_retriever` fikstürü yoksa test atlanır.
"""
from __future__ import annotations
import pytest
from pathlib import Path

from app.services.pipeline import Pipeline
from app.services.parser import parse_docx


# ── Yardımcılar ──────────────────────────────────────────────────────────────

def _rule_codes(result) -> set[str]:
    return {f.rule_code for f in result.findings}


# ── Test 1: Kurallara uygun belge ────────────────────────────────────────────

def test_correct_document(correct_docx_path: Path):
    """Doğru biçimlendirilmiş belgede hata bulunmamalı."""
    pipeline = Pipeline()
    result = pipeline.analyze(str(correct_docx_path), mode="format_only")

    # Hata (error) seviyesinde bulgu olmamalı
    assert result.errors == 0, (
        f"Hatasız belgede {result.errors} hata bulundu: "
        + str([f.rule_code for f in result.findings if f.severity.value == "error"])
    )


# ── Test 2: Hatalı belge ─────────────────────────────────────────────────────

def test_error_document(errors_docx_path: Path):
    """Kasıtlı hatalı belgede beklenen kural kodları tetiklenmeli."""
    pipeline = Pipeline()
    result = pipeline.analyze(str(errors_docx_path), mode="format_only")

    codes = _rule_codes(result)

    # T.C. başlığı yok → FLD-001
    assert "FLD-001" in codes, f"FLD-001 bekleniyor, bulunanlar: {codes}"

    # Tarih yok → FLD-005 (FLD-004 = Sayı eksik; FLD-005 = Tarih eksik)
    assert "FLD-005" in codes, f"FLD-005 bekleniyor, bulunanlar: {codes}"

    # Kapanış yok → CLS-001
    assert "CLS-001" in codes, f"CLS-001 bekleniyor, bulunanlar: {codes}"

    # Toplam en az 3 bulgu
    assert result.total_findings >= 3, (
        f"En az 3 bulgu bekleniyor, {result.total_findings} bulundu"
    )


# ── Test 3: Parser bölüm tespiti ─────────────────────────────────────────────

def test_parser_sections(correct_docx_path: Path, errors_docx_path: Path):
    """Parser, T.C. başlığını ve kapanış ifadesini doğru tespit etmeli."""
    correct = parse_docx(str(correct_docx_path))
    errors = parse_docx(str(errors_docx_path))

    # Doğru belge: T.C. başlığı var, kapanış "Arz ederim"
    assert correct.has_tc_header is True, "Doğru belgede T.C. başlığı tespit edilemedi"
    assert correct.kapanis_phrase is not None, "Doğru belgede kapanış ifadesi bulunamadı"
    assert "arz" in correct.kapanis_phrase.lower(), (
        f"Kapanış ifadesi 'arz' içermeli, bulunan: {correct.kapanis_phrase!r}"
    )

    # Hatalı belge: T.C. başlığı yok, kapanış yok
    assert errors.has_tc_header is False, "Hatalı belgede T.C. başlığı olmamalı"
    assert errors.kapanis_phrase is None, (
        f"Hatalı belgede kapanış olmamalı, bulunan: {errors.kapanis_phrase!r}"
    )


# ── Test 4: RAG arama (veri yoksa atlanır) ───────────────────────────────────

def test_rag_search(rag_retriever):
    """RAG retriever, TDK ve yönerge sorgularında sonuç döndürmeli."""
    results_tdk = rag_retriever.search("yazım kuralları", k=3)
    assert len(results_tdk) > 0, "TDK sorgusu sonuç döndürmedi"

    results_guideline = rag_retriever.search("resmi yazışma yönetmeliği", k=3)
    assert len(results_guideline) > 0, "Yönerge sorgusu sonuç döndürmedi"
