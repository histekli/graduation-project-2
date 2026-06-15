"""
Senaryo tabanlı entegrasyon testleri.
Katman A (deterministik), Katman B (RAG) ve Katman C (LLM) ayrı ayrı test edilir.
"""
from __future__ import annotations
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.pipeline import Pipeline
from app.services.parser import parse_docx
from app.services.layer_a import LayerA
from app.services.layer_b import LayerB
from app.services.layer_c import LayerC
from app.rag.retriever import GuidelineRetriever
from tests.create_test_docs import create_all, FIXTURES


# ── Session fixture: belgeler yoksa oluştur ───────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def ensure_fixtures():
    needed = [
        "test_perfect.docx", "test_format_errors.docx", "test_missing_fields.docx",
        "test_hierarchy_mismatch.docx", "test_semantic_issues.docx",
        "test_language_errors.docx", "test_rektor_a.docx",
    ]
    if not all((FIXTURES / f).exists() for f in needed):
        create_all()


@pytest.fixture(scope="session")
def retriever():
    """ChromaDB varsa GuidelineRetriever, yoksa None döner."""
    r = GuidelineRetriever()
    return r if r.is_ready else None


# ── Yardımcılar ───────────────────────────────────────────────────────────────

def _parse(filename: str):
    return parse_docx(str(FIXTURES / filename))

def _layer_a(filename: str) -> set[str]:
    doc = _parse(filename)
    findings = LayerA().run(doc)
    return {f.rule_code for f in findings}

def _layer_b(filename: str, retriever) -> list:
    doc = _parse(filename)
    lb = LayerB(retriever=retriever)
    return lb.run(doc)

def _pipeline(filename: str, mode: str = "full") -> tuple:
    p = Pipeline()
    result = p.analyze(str(FIXTURES / filename), mode=mode)
    codes = {f.rule_code for f in result.findings}
    return p, result, codes


# ═══════════════════════════════════════════════════════════════════════════════
# KATMAN A — Deterministik Kural Motoru
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayerA:

    def test_perfect_document_no_errors(self):
        """Mükemmel belgede hiç hata olmamalı."""
        codes = _layer_a("test_perfect.docx")
        errors = LayerA().run(_parse("test_perfect.docx"))
        error_codes = [f.rule_code for f in errors if f.severity.value == "error"]
        warn_codes  = [f.rule_code for f in errors if f.severity.value == "warning"]
        assert not error_codes, f"Mükemmel belgede hata beklenmez: {error_codes}"
        assert not warn_codes,  f"Mükemmel belgede uyarı beklenmez: {warn_codes}"

    def test_format_errors_detected(self):
        """Yanlış font, yanlış marj ve fazla boşluk tespiti."""
        codes = _layer_a("test_format_errors.docx")
        assert "FMT-001" in codes, f"FMT-001 (yanlış font) eksik; bulunan: {codes}"
        assert "FMT-002" in codes, f"FMT-002 (yanlış marj) eksik; bulunan: {codes}"
        assert "LNG-004" in codes, f"LNG-004 (fazla boşluk) eksik; bulunan: {codes}"

    def test_missing_fields_detected(self):
        """T.C., Konu ve imza bloğu eksikliği tespiti + false-positive kontrolü."""
        codes = _layer_a("test_missing_fields.docx")
        assert "FLD-001" in codes, f"FLD-001 (T.C. eksik) eksik; bulunan: {codes}"
        assert "FLD-006" in codes, f"FLD-006 (Konu eksik) eksik; bulunan: {codes}"
        assert "FLD-007" in codes, f"FLD-007 (imza bloğu eksik) eksik; bulunan: {codes}"
        assert "FLD-004" not in codes, f"FLD-004 false positive (Sayı mevcut); bulunan: {codes}"
        assert "FLD-005" not in codes, f"FLD-005 false positive (Tarih mevcut); bulunan: {codes}"

    def test_hierarchy_mismatch_hir001(self):
        """HIR-001 Layer A'da artık yok (Layer B'ye taşındı) — Layer A'dan gelmemeli."""
        codes = _layer_a("test_hierarchy_mismatch.docx")
        assert "HIR-001" not in codes, (
            f"HIR-001 Layer A'dan geliyorsa duplikasyon var; bulunan: {codes}"
        )

    def test_hierarchy_mismatch_no_false_positive(self):
        """Mükemmel belgede Layer A HIR-001 üretmemeli."""
        codes = _layer_a("test_perfect.docx")
        assert "HIR-001" not in codes, f"HIR-001 false positive; bulunan: {codes}"

    def test_ek_count_mismatch_sem002(self):
        """Metinde '3 adet' denip ek listesinde 2 belge olduğunda SEM-002 tetiklenmeli."""
        codes = _layer_a("test_semantic_issues.docx")
        assert "SEM-002" in codes, f"SEM-002 (ek sayısı tutarsızlığı) eksik; bulunan: {codes}"

    def test_ek_count_no_false_positive(self):
        """Mükemmel belgede SEM-002 olmamalı."""
        codes = _layer_a("test_perfect.docx")
        assert "SEM-002" not in codes, f"SEM-002 false positive; bulunan: {codes}"

    def test_language_errors_detected(self):
        """Virgül boşluğu, nokta boşluğu, çift boşluk ve yasaklı kapanış tespiti."""
        codes = _layer_a("test_language_errors.docx")
        assert "LNG-002" in codes, f"LNG-002 (virgül öncesi boşluk) eksik; bulunan: {codes}"
        assert "LNG-003" in codes, f"LNG-003 (noktadan sonra boşluk yok) eksik; bulunan: {codes}"
        assert "LNG-004" in codes, f"LNG-004 (çift boşluk) eksik; bulunan: {codes}"
        assert "CLS-002" in codes, f"CLS-002 (yasaklı kapanış) eksik; bulunan: {codes}"

    def test_cls002_no_false_positive(self):
        """Mükemmel belgede CLS-002 olmamalı."""
        codes = _layer_a("test_perfect.docx")
        assert "CLS-002" not in codes, f"CLS-002 false positive; bulunan: {codes}"


# ═══════════════════════════════════════════════════════════════════════════════
# KATMAN B — RAG Destekli Kontrol
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayerB:

    def test_retriever_is_ready(self, retriever):
        """ChromaDB koleksiyonu yüklü ve sorgu yapılabilir olmalı."""
        if retriever is None:
            pytest.skip("ChromaDB bulunamadı — veri dizini mevcut değil")
        assert retriever.is_ready, "Retriever hazır olmalı"

    def test_retriever_returns_results(self, retriever):
        """RAG araması anlamlı sonuçlar döndürmeli."""
        if retriever is None:
            pytest.skip("ChromaDB bulunamadı")
        results = retriever.search_by_rule("kapanış ifadesi arz ederim üst makam", n_results=3)
        assert len(results) > 0, "Arama sonucu boş olmamalı"
        first = results[0]
        assert "text" in first and len(first["text"]) > 10
        assert "metadata" in first
        assert first["metadata"].get("source_type") in [
            "resmi_yazisma_yonetmeligi", "gtu_yonerge", "cb_kilavuzu"
        ], f"Birincil kaynak bekleniyor; bulunan: {first['metadata']}"

    def test_retriever_font_query(self, retriever):
        """Font sorgusu Madde 7'yi döndürmeli."""
        if retriever is None:
            pytest.skip("ChromaDB bulunamadı")
        results = retriever.search_by_rule("Times New Roman Arial punto yazı tipi")
        assert len(results) > 0
        sections = [r["metadata"].get("section", "") for r in results]
        assert any("Madde 7" in s or "7" in s for s in sections), (
            f"Madde 7 (font kuralları) bekleniyor; bulunan bölümler: {sections}"
        )

    def test_hir001_hierarchy_mismatch(self, retriever):
        """Layer B: Üst makama 'Rica ederim' kullanımı HIR-001 tetiklemeli."""
        if retriever is None:
            pytest.skip("ChromaDB bulunamadı — Katman B çalışmaz")
        findings = _layer_b("test_hierarchy_mismatch.docx", retriever)
        codes = {f.rule_code for f in findings}
        assert "HIR-001" in codes, f"HIR-001 (hiyerarşi uyumsuzluğu) eksik; bulunan: {codes}"
        hir001 = next(f for f in findings if f.rule_code == "HIR-001")
        assert hir001.reference, "HIR-001 bulgusunda RAG referansı olmalı"

    def test_hir002_rektor_a_usage(self, retriever):
        """'Rektör a.' ibareli imza bloğu HIR-002 bilgi bulgusunu tetiklemeli."""
        if retriever is None:
            pytest.skip("ChromaDB bulunamadı — Katman B çalışmaz")
        findings = _layer_b("test_rektor_a.docx", retriever)
        codes = {f.rule_code for f in findings}
        assert "HIR-002" in codes, (
            f"HIR-002 (Rektör a. yetki devri) eksik; bulunan: {codes}"
        )
        hir002 = next(f for f in findings if f.rule_code == "HIR-002")
        assert hir002.reference, "HIR-002 bulgusunda RAG referansı olmalı"

    def test_hir002_absent_in_normal_doc(self, retriever):
        """Normal imzada HIR-002 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB bulunamadı")
        findings = _layer_b("test_perfect.docx", retriever)
        codes = {f.rule_code for f in findings}
        assert "HIR-002" not in codes, f"HIR-002 false positive; bulunan: {codes}"

    def test_layer_b_inactive_without_chromadb(self):
        """ChromaDB olmadan Pipeline başlatıldığında Katman B None olmamalı değil — is_ready False."""
        from app.rag.retriever import GuidelineRetriever
        r = GuidelineRetriever(persist_dir="/tmp/nonexistent_chroma_xyz")
        assert not r.is_ready, "Geçersiz dizinde retriever hazır olmamalı"
        lb = LayerB(retriever=r)
        result = lb.run(_parse("test_perfect.docx"))
        assert result == [], "Hazır olmayan retriever hiçbir bulgu döndürmemeli"


# ═══════════════════════════════════════════════════════════════════════════════
# KATMAN C — LLM Destekli Semantik Analiz
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayerC:

    def test_layer_c_inactive_without_key(self):
        """API anahtarı olmadan Katman C is_ready=False olmalı."""
        with patch.dict(os.environ, {}, clear=False):
            env_backup = {}
            for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
                env_backup[key] = os.environ.pop(key, None)
            try:
                lc = LayerC()
                assert not lc.is_ready, "API anahtarsız LayerC hazır olmamalı"
                result = lc.run(_parse("test_semantic_issues.docx"))
                assert result == [], "Hazır olmayan LayerC hiçbir bulgu döndürmemeli"
            finally:
                for key, val in env_backup.items():
                    if val is not None:
                        os.environ[key] = val

    def test_layer_c_gemini_mock(self):
        """Gemini API mock ile SEM-001 bulgusunun döndürülmesini doğrula.

        _call_llm bir JSON array string döndürmeli; _parse_llm_response bunu Finding'e çevirir.
        """
        # _parse_llm_response'ın beklediği format: category, description, suggestion, confidence
        mock_json = (
            '[{"category": "konu_metin", "severity": "warning", '
            '"title": "Konu-metin uyumsuzluğu", '
            '"description": "Konu bütçe ama metin atama hakkında.", '
            '"suggestion": "Konu ile metin uyumlu olmalı.", "confidence": 0.85}]'
        )

        lc = LayerC(provider="gemini", api_key="mock-key-for-test")
        assert lc.is_ready, "Mock API key ile LayerC hazır olmalı"

        with patch.object(lc, "_call_llm", return_value=mock_json):
            doc = _parse("test_semantic_issues.docx")
            findings = lc.run(doc)

        codes = {f.rule_code for f in findings}
        # SEM-001 mock LLM'den gelmeli
        assert "SEM-001" in codes, f"SEM-001 (konu-metin uyumsuzluğu) eksik; bulunan: {codes}"
        # Bulgu güvenilirlik eşiği geçmiş olmalı
        sem001 = next(f for f in findings if f.rule_code == "SEM-001")
        assert sem001.confidence >= 0.5, f"Confidence çok düşük: {sem001.confidence}"

    def test_layer_c_with_real_api(self):
        """Gerçek API anahtarı varsa tam Katman C akışını çalıştır."""
        lc = LayerC()
        if not lc.is_ready:
            pytest.skip(
                f"Katman C aktif değil — GEMINI_API_KEY veya ANTHROPIC_API_KEY gerekli "
                f"(provider: {lc.provider})"
            )
        doc = _parse("test_semantic_issues.docx")
        try:
            findings = lc.run(doc)
        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "quota" in msg or "rate" in msg or "resource_exhausted" in msg:
                pytest.skip(f"Gemini API kotası aşıldı — test atlandı: {exc}")
            raise
        codes = {f.rule_code for f in findings}
        # LLM hatası nedeniyle boş döndüyse (quota aşımı run() içinde yakalanıp [] döner)
        if not findings:
            pytest.skip("Katman C hiç bulgu döndürmedi — API kotası aşılmış olabilir")

        # Konu-metin uyumsuzluğu (bütçe konusu / atama metni)
        has_sem = any(c.startswith("SEM-") for c in codes)
        assert has_sem, f"En az bir SEM-xxx bekleniyor; bulunan: {codes}"

        # SEM-002: ek sayısı uyumsuzluğu (3 adet belirtilmiş, 2 var)
        assert "SEM-002" in codes, f"SEM-002 (ek sayısı) eksik; bulunan: {codes}"

        # Her bulgunun confidence değeri eşiğin üzerinde olmalı
        for f in findings:
            if hasattr(f, "confidence") and f.confidence is not None:
                assert f.confidence >= 0.5, (
                    f"{f.rule_code} confidence çok düşük: {f.confidence}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE — Uçtan Uca Entegrasyon
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipeline:

    def test_format_only_mode_skips_b_and_c(self):
        """format_only modunda Katman B ve C çalışmamalı."""
        p, result, codes = _pipeline("test_hierarchy_mismatch.docx", mode="format_only")
        # HIR-001 Layer A'da olduğu için format_only'de de bulunur
        layer_b_codes = {f.rule_code for f in result.findings if f.layer.value == "B"}
        layer_c_codes = {f.rule_code for f in result.findings if f.layer.value == "C"}
        assert not layer_b_codes, f"format_only'de Layer B bulgular olmamalı: {layer_b_codes}"
        assert not layer_c_codes, f"format_only'de Layer C bulgular olmamalı: {layer_c_codes}"

    def test_full_mode_includes_all_layers(self):
        """full modunda tüm katmanlar çalışır; deterministik katmanlar mükemmel belgede temiz olmalı."""
        p, result, codes = _pipeline("test_perfect.docx", mode="full")
        # Deterministik katmanlar (A + B) mükemmel belgede HİÇ hata üretmemeli.
        # Katman C (LLM) non-deterministiktir; canlı modelin mükemmel belgede ara sıra
        # döndürdüğü semantik bulgular testi kırılgan yapmasın diye yalnızca A+B denetlenir.
        det_errors = [
            f for f in result.findings
            if f.layer.value in ("A", "B") and f.severity.value == "error"
        ]
        assert not det_errors, f"Deterministik katmanlarda hata beklenmez: {det_errors}"

    def test_pipeline_filename_preserved(self):
        """Pipeline sonucu orijinal dosya adını korumalı."""
        p = Pipeline()
        fname = "test_perfect.docx"
        result = p.analyze(
            str(FIXTURES / fname),
            mode="format_only",
            original_filename=fname,
        )
        assert result.filename == fname, (
            f"Dosya adı korunmadı; beklenen: {fname}, bulunan: {result.filename}"
        )
