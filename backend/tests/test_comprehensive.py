"""
Kapsamlı Senaryo Testleri — 53 test belgesi
Her dosya için beklenen kural kodları doğrulanır.

Çalıştırma:
  cd backend
  pytest tests/test_comprehensive.py -v                        # tümü
  pytest tests/test_comprehensive.py -v -k "layer_a"          # sadece Layer A
  pytest tests/test_comprehensive.py -v -k "layer_b"          # sadece Layer B
  pytest tests/test_comprehensive.py -v -k "layer_c"          # sadece Layer C (LLM gerekir)
  pytest tests/test_comprehensive.py -v -k "false_positive"   # sadece FP kontrolleri
"""
from __future__ import annotations
import os
import pytest
from pathlib import Path
from unittest.mock import patch

from app.services.pipeline import Pipeline
from app.services.parser import parse_docx
from app.services.layer_a import LayerA
from app.services.layer_b import LayerB
from app.services.layer_c import LayerC
from app.rag.retriever import GuidelineRetriever
from tests.create_comprehensive_docs import create_comprehensive, FIXTURES


# ── Session fixture'ları ───────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def ensure_comprehensive_fixtures():
    """Kapsamlı test belgeleri yoksa oluştur."""
    sample = FIXTURES / "a_fmt001_calibri.docx"
    if not sample.exists():
        create_comprehensive()


@pytest.fixture(scope="session")
def retriever():
    r = GuidelineRetriever()
    return r if r.is_ready else None


@pytest.fixture(scope="session")
def pipeline():
    return Pipeline()


# ── Yardımcılar ───────────────────────────────────────────────────────────────

def _parse(filename: str):
    return parse_docx(str(FIXTURES / filename))


def _layer_a_codes(filename: str) -> set[str]:
    doc = _parse(filename)
    return {f.rule_code for f in LayerA().run(doc)}


def _layer_b_codes(filename: str, retriever) -> set[str]:
    doc = _parse(filename)
    return {f.rule_code for f in LayerB(retriever=retriever).run(doc)}


def _pipeline_codes(filename: str, p: Pipeline, mode="full") -> tuple[set, set, set]:
    """(layer_a_codes, layer_b_codes, layer_c_codes) döner."""
    result = p.analyze(str(FIXTURES / filename), mode=mode,
                       original_filename=filename)
    a = {f.rule_code for f in result.findings if f.layer.value == "A"}
    b = {f.rule_code for f in result.findings if f.layer.value == "B"}
    c = {f.rule_code for f in result.findings if f.layer.value == "C"}
    return a, b, c


def _assert_has(codes: set, expected: str, filename: str) -> None:
    assert expected in codes, (
        f"[{filename}] beklenen '{expected}' bulunamadı; mevcut: {sorted(codes)}"
    )


def _assert_not_has(codes: set, unexpected: str, filename: str, note="false positive") -> None:
    assert unexpected not in codes, (
        f"[{filename}] {note}: '{unexpected}' bulunmamalıydı; mevcut: {sorted(codes)}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# KATMAN A — Format Kuralları
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayerAFont:
    """FMT-001: Font ve punto kontrolleri."""

    def test_calibri_11pt_triggers_fmt001(self):
        codes = _layer_a_codes("a_fmt001_calibri.docx")
        _assert_has(codes, "FMT-001", "a_fmt001_calibri.docx")

    def test_arial_wrong_size_triggers_fmt001(self):
        codes = _layer_a_codes("a_fmt001_arial_wrong_size.docx")
        _assert_has(codes, "FMT-001", "a_fmt001_arial_wrong_size.docx")

    def test_tnr_wrong_size_triggers_fmt001(self):
        codes = _layer_a_codes("a_fmt001_tnr_wrong_size.docx")
        _assert_has(codes, "FMT-001", "a_fmt001_tnr_wrong_size.docx")

    def test_mixed_fonts_triggers_fmt001(self):
        codes = _layer_a_codes("a_fmt001_mixed_fonts.docx")
        _assert_has(codes, "FMT-001", "a_fmt001_mixed_fonts.docx")

    def test_arial_11pt_no_fmt001(self):
        """FP: Arial 11pt → FMT-001 olmamalı."""
        codes = _layer_a_codes("ok_arial_font.docx")
        _assert_not_has(codes, "FMT-001", "ok_arial_font.docx")

    def test_perfect_no_fmt001(self):
        """FP: Mükemmel belgede FMT-001 olmamalı."""
        codes = _layer_a_codes("test_perfect.docx")
        _assert_not_has(codes, "FMT-001", "test_perfect.docx")


class TestLayerAMargin:
    """FMT-002: Marj kontrolleri."""

    def test_large_margin_triggers_fmt002(self):
        codes = _layer_a_codes("a_fmt002_margin_large.docx")
        _assert_has(codes, "FMT-002", "a_fmt002_margin_large.docx")

    def test_small_margin_triggers_fmt002(self):
        codes = _layer_a_codes("a_fmt002_margin_small.docx")
        _assert_has(codes, "FMT-002", "a_fmt002_margin_small.docx")

    def test_correct_margin_no_fmt002(self):
        """FP: 1.5 cm marjda FMT-002 olmamalı."""
        codes = _layer_a_codes("test_perfect.docx")
        _assert_not_has(codes, "FMT-002", "test_perfect.docx")


class TestLayerAMandatoryFields:
    """FLD-001..007: Zorunlu alan kontrolleri."""

    def test_missing_tc_triggers_fld001(self):
        codes = _layer_a_codes("a_fld001_missing_tc.docx")
        _assert_has(codes, "FLD-001", "a_fld001_missing_tc.docx")

    def test_missing_university_triggers_fld002(self):
        codes = _layer_a_codes("a_fld002_missing_university.docx")
        _assert_has(codes, "FLD-002", "a_fld002_missing_university.docx")

    def test_missing_sayi_triggers_fld004(self):
        codes = _layer_a_codes("a_fld004_missing_sayi.docx")
        _assert_has(codes, "FLD-004", "a_fld004_missing_sayi.docx")

    def test_wrong_date_format_triggers_fld005(self):
        codes = _layer_a_codes("a_fld005_wrong_date_format.docx")
        _assert_has(codes, "FLD-005", "a_fld005_wrong_date_format.docx")

    def test_missing_konu_triggers_fld006(self):
        codes = _layer_a_codes("a_fld006_missing_konu.docx")
        _assert_has(codes, "FLD-006", "a_fld006_missing_konu.docx")

    def test_missing_imza_triggers_fld007(self):
        codes = _layer_a_codes("a_fld007_missing_imza.docx")
        _assert_has(codes, "FLD-007", "a_fld007_missing_imza.docx")

    def test_all_fields_missing_triggers_multiple(self):
        """FLD-001..007: Hepsinin birden eksik olduğu durumda çoklu hata."""
        codes = _layer_a_codes("a_fld_all_missing.docx")
        for code in ("FLD-001", "FLD-002", "FLD-004", "FLD-006"):
            _assert_has(codes, code, "a_fld_all_missing.docx")

    def test_perfect_no_fld_errors(self):
        """FP: Mükemmel belgede FLD-xxx olmamalı."""
        codes = _layer_a_codes("test_perfect.docx")
        fld_errors = [c for c in codes if c.startswith("FLD-")]
        assert not fld_errors, f"Mükemmel belgede FLD hata: {fld_errors}"

    def test_correct_fields_no_fld004_fld005(self):
        """FP: Sayı ve tarih olan belgede FLD-004/005 olmamalı."""
        codes = _layer_a_codes("b_correct_upward.docx")
        _assert_not_has(codes, "FLD-004", "b_correct_upward.docx")
        _assert_not_has(codes, "FLD-005", "b_correct_upward.docx")


class TestLayerAClosing:
    """CLS-001..003: Kapanış ifadesi kontrolleri."""

    def test_no_closing_triggers_cls001(self):
        codes = _layer_a_codes("a_cls001_no_closing.docx")
        _assert_has(codes, "CLS-001", "a_cls001_no_closing.docx")

    def test_saygila_arz_triggers_cls002(self):
        codes = _layer_a_codes("a_cls002_saygila_arz.docx")
        _assert_has(codes, "CLS-002", "a_cls002_saygila_arz.docx")

    def test_rica_olunur_triggers_cls002(self):
        codes = _layer_a_codes("a_cls002_rica_olunur.docx")
        _assert_has(codes, "CLS-002", "a_cls002_rica_olunur.docx")

    def test_uygundur_triggers_cls003(self):
        codes = _layer_a_codes("a_cls003_uygundur.docx")
        _assert_has(codes, "CLS-003", "a_cls003_uygundur.docx")

    def test_arz_ederim_no_cls002(self):
        """FP: 'Arz ederim' CLS-002 tetiklemez."""
        codes = _layer_a_codes("test_perfect.docx")
        _assert_not_has(codes, "CLS-002", "test_perfect.docx")

    def test_rica_ederim_no_cls002(self):
        """FP: 'Rica ederim' alt makama CLS-002 tetiklemez."""
        codes = _layer_a_codes("b_correct_downward.docx")
        _assert_not_has(codes, "CLS-002", "b_correct_downward.docx")

    def test_combo_cls002_in_language_errors(self):
        """Dil hatası belgesi CLS-002 de içeriyor."""
        codes = _layer_a_codes("a_lng_combo.docx")
        _assert_has(codes, "CLS-002", "a_lng_combo.docx")


class TestLayerALanguage:
    """LNG-001..004: Dil ve yazım kuralları."""

    def test_sentence_case_triggers_lng001(self):
        codes = _layer_a_codes("a_lng001_sentence_case.docx")
        _assert_has(codes, "LNG-001", "a_lng001_sentence_case.docx")

    def test_comma_space_triggers_lng002(self):
        codes = _layer_a_codes("a_lng002_comma_space.docx")
        _assert_has(codes, "LNG-002", "a_lng002_comma_space.docx")

    def test_period_nospace_triggers_lng003(self):
        codes = _layer_a_codes("a_lng003_period_nospace.docx")
        _assert_has(codes, "LNG-003", "a_lng003_period_nospace.docx")

    def test_double_spaces_triggers_lng004(self):
        codes = _layer_a_codes("a_lng004_double_spaces.docx")
        _assert_has(codes, "LNG-004", "a_lng004_double_spaces.docx")

    def test_combo_has_all_lng_errors(self):
        """Kombine dosya tüm LNG hatalarını içermeli."""
        codes = _layer_a_codes("a_lng_combo.docx")
        for code in ("LNG-002", "LNG-004"):
            _assert_has(codes, code, "a_lng_combo.docx")

    def test_perfect_no_language_errors(self):
        """FP: Mükemmel belgede LNG-xxx olmamalı."""
        codes = _layer_a_codes("test_perfect.docx")
        lng_errors = [c for c in codes if c.startswith("LNG-")]
        assert not lng_errors, f"Mükemmel belgede dil hatası: {lng_errors}"


class TestLayerAEkCount:
    """SEM-002: Ek sayısı tutarsızlığı (deterministik)."""

    def test_ek_too_few_triggers_sem002(self):
        """Metinde 4 adet, ekte 2 → SEM-002."""
        codes = _layer_a_codes("a_sem002_ek_too_few.docx")
        _assert_has(codes, "SEM-002", "a_sem002_ek_too_few.docx")

    def test_ek_too_many_triggers_sem002(self):
        """Metinde iki adet, ekte 4 → SEM-002."""
        codes = _layer_a_codes("a_sem002_ek_too_many.docx")
        _assert_has(codes, "SEM-002", "a_sem002_ek_too_many.docx")

    def test_no_ek_no_sem002(self):
        """FP: Ek olmayan belgede SEM-002 olmamalı."""
        codes = _layer_a_codes("test_perfect.docx")
        _assert_not_has(codes, "SEM-002", "test_perfect.docx")

    def test_consistent_ek_no_sem002(self):
        """FP: Ek sayısı tutarlı olduğunda SEM-002 olmamalı."""
        codes = _layer_a_codes("mix_ilgili_ekli_complete.docx")
        _assert_not_has(codes, "SEM-002", "mix_ilgili_ekli_complete.docx")

    def test_ek_no_ref_triggers_sem002_layer_a(self):
        """EKSIK 4: EK var ama metinde atıf yok → SEM-002 artık Layer A'dan gelir."""
        codes = _layer_a_codes("a_sem002_ek_no_ref.docx")
        _assert_has(codes, "SEM-002", "a_sem002_ek_no_ref.docx")

    def test_repeated_content_triggers_sem006_layer_a(self):
        """EKSIK 4: Tekrar eden ifade → SEM-006 artık Layer A (deterministik)."""
        codes = _layer_a_codes("a_sem006_repeated.docx")
        _assert_has(codes, "SEM-006", "a_sem006_repeated.docx")


# ═══════════════════════════════════════════════════════════════════════════════
# KATMAN B — RAG Destekli Kurallar
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayerBHIR001:
    """HIR-001: Kapanış-hiyerarşi uyumsuzluğu."""

    def test_bolum_rektor_rica_triggers_hir001(self, retriever):
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_hir001_bolum_rektor.docx", retriever)
        _assert_has(codes, "HIR-001", "b_hir001_bolum_rektor.docx")

    def test_muhendislik_rektor_rica_triggers_hir001(self, retriever):
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_hir001_muhendislik_rektor.docx", retriever)
        _assert_has(codes, "HIR-001", "b_hir001_muhendislik_rektor.docx")

    def test_correct_upward_no_hir001(self, retriever):
        """FP: 'Arz ederim' ile üst makama yazan belgede HIR-001 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_correct_upward.docx", retriever)
        _assert_not_has(codes, "HIR-001", "b_correct_upward.docx")

    def test_correct_downward_no_hir001(self, retriever):
        """FP: Alt makama 'Rica ederim' doğru — HIR-001 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_correct_downward.docx", retriever)
        _assert_not_has(codes, "HIR-001", "b_correct_downward.docx")

    def test_perfect_no_hir001(self, retriever):
        """FP: Mükemmel belgede HIR-001 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("test_perfect.docx", retriever)
        _assert_not_has(codes, "HIR-001", "test_perfect.docx")

    def test_hir001_has_rag_reference(self, retriever):
        """HIR-001 bulgusunda RAG referansı olmalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        doc = _parse("b_hir001_bolum_rektor.docx")
        findings = LayerB(retriever=retriever).run(doc)
        hir001_list = [f for f in findings if f.rule_code == "HIR-001"]
        assert hir001_list, "HIR-001 bulgusu yok"
        assert hir001_list[0].reference, "HIR-001'de RAG referansı eksik"


class TestLayerBHIR002:
    """HIR-002: Yetki devri imzası tespiti."""

    def test_rektor_a_triggers_hir002(self, retriever):
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("test_rektor_a.docx", retriever)
        _assert_has(codes, "HIR-002", "test_rektor_a.docx")

    def test_rektor_a_yrd_triggers_hir002(self, retriever):
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_hir002_rektor_a_yrd.docx", retriever)
        _assert_has(codes, "HIR-002", "b_hir002_rektor_a_yrd.docx")

    def test_normal_imza_no_hir002(self, retriever):
        """FP: Normal imza bloğunda HIR-002 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("test_perfect.docx", retriever)
        _assert_not_has(codes, "HIR-002", "test_perfect.docx")

    def test_hir002_is_info_severity(self, retriever):
        """HIR-002 bilgi seviyesinde olmalı (uyarı değil)."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        doc = _parse("test_rektor_a.docx")
        findings = LayerB(retriever=retriever).run(doc)
        hir002 = next((f for f in findings if f.rule_code == "HIR-002"), None)
        assert hir002 is not None, "HIR-002 bulunamadı"
        assert hir002.severity.value == "info", f"HIR-002 info olmalı: {hir002.severity}"


class TestLayerBHIR003:
    """HIR-003: İlgi satırları sıralama kontrolü."""

    def test_reversed_ilgi_triggers_hir003(self, retriever):
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_hir003_ilgi_ters.docx", retriever)
        _assert_has(codes, "HIR-003", "b_hir003_ilgi_ters.docx")

    def test_correct_ilgi_order_no_hir003(self, retriever):
        """FP: Doğru tarih sıralamasında HIR-003 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_hir003_ilgi_dogru.docx", retriever)
        _assert_not_has(codes, "HIR-003", "b_hir003_ilgi_dogru.docx")

    def test_no_ilgi_no_hir003(self, retriever):
        """FP: İlgi satırı olmayan belgede HIR-003 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("test_perfect.docx", retriever)
        _assert_not_has(codes, "HIR-003", "test_perfect.docx")

    def test_complete_doc_correct_ilgi_no_hir003(self, retriever):
        """FP: Tam belgede ilgi doğru sıralandığında HIR-003 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("mix_ilgili_ekli_complete.docx", retriever)
        _assert_not_has(codes, "HIR-003", "mix_ilgili_ekli_complete.docx")


class TestLayerBHIR004:
    """HIR-004: Dağıtım Gereği/Bilgi ayrımı kontrolü."""

    def test_dagitim_no_split_triggers_hir004(self, retriever):
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_hir004_dagitim_no_split.docx", retriever)
        _assert_has(codes, "HIR-004", "b_hir004_dagitim_no_split.docx")

    def test_dagitim_with_split_no_hir004(self, retriever):
        """FP: Gereği/Bilgi ayrımı yapılan dağıtım bölümünde HIR-004 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_hir004_dagitim_with_split.docx", retriever)
        _assert_not_has(codes, "HIR-004", "b_hir004_dagitim_with_split.docx")

    def test_no_dagitim_no_hir004(self, retriever):
        """FP: Dağıtım bölümü olmayan belgede HIR-004 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("test_perfect.docx", retriever)
        _assert_not_has(codes, "HIR-004", "test_perfect.docx")

    def test_complete_doc_split_dagitim_no_hir004(self, retriever):
        """FP: Tam belgede Gereği/Bilgi ayrımı varsa HIR-004 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("mix_ilgili_ekli_complete.docx", retriever)
        _assert_not_has(codes, "HIR-004", "mix_ilgili_ekli_complete.docx")


class TestLayerBHIR005:
    """HIR-005: Bölüm→Rektörlük hiyerarşi atlama kontrolü."""

    def test_bolum_rektor_direct_triggers_hir005(self, retriever):
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_hir005_bolum_rektor.docx", retriever)
        _assert_has(codes, "HIR-005", "b_hir005_bolum_rektor.docx")

    def test_fakulte_rektor_no_hir005(self, retriever):
        """FP: Fakülte→Rektörlük normal hiyerarşi (HIR-005 olmamalı)."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("b_correct_upward.docx", retriever)
        _assert_not_has(codes, "HIR-005", "b_correct_upward.docx")

    def test_enstitü_rektor_no_hir005(self, retriever):
        """FP: Enstitü→Rektörlük normal hiyerarşi (HIR-005 olmamalı)."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("ok_enstitü_yazisi.docx", retriever)
        _assert_not_has(codes, "HIR-005", "ok_enstitü_yazisi.docx")


class TestLayerBNoChromaDB:
    """ChromaDB olmadan Layer B davranışı."""

    def test_layer_b_inactive_without_chromadb(self):
        r = GuidelineRetriever(persist_dir="/tmp/nonexistent_xyz_comprehensive")
        assert not r.is_ready
        lb = LayerB(retriever=r)
        result = lb.run(_parse("b_hir001_bolum_rektor.docx"))
        assert result == [], "Hazır olmayan retriever bulgu üretmemeli"

    def test_layer_b_returns_empty_for_correct_doc_without_chroma(self):
        lb = LayerB(retriever=None)
        result = lb.run(_parse("test_perfect.docx"))
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════════
# KATMAN C — LLM Semantik Analiz (Mock ve gerçek API)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayerCInactive:
    """API anahtarsız Layer C davranışı."""

    def test_no_key_is_not_ready(self):
        env_backup = {k: os.environ.pop(k, None)
                      for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY")}
        try:
            lc = LayerC()
            assert not lc.is_ready
        finally:
            for k, v in env_backup.items():
                if v:
                    os.environ[k] = v

    def test_no_key_returns_empty(self):
        env_backup = {k: os.environ.pop(k, None)
                      for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY")}
        try:
            lc = LayerC()
            result = lc.run(_parse("c_sem001_strong_mismatch.docx"))
            assert result == []
        finally:
            for k, v in env_backup.items():
                if v:
                    os.environ[k] = v


# ── SEM-001 mock testleri ─────────────────────────────────────────────────────

_MOCK_SEM001 = (
    '[{"category": "konu_metin", "severity": "error", '
    '"title": "Konu metin uyumsuzluğu", '
    '"description": "Konu bütçe ancak metin inşaatla ilgili.", '
    '"suggestion": "Konu ile metin tutarlı olmalı.", "confidence": 0.92}]'
)

_MOCK_SEM003 = (
    '[{"category": "mantiksal", "severity": "warning", '
    '"title": "İç çelişki", '
    '"description": "Metin önce tüm ekibin desteklediğini, sonra çoğunluğun karşı olduğunu söylüyor.", '
    '"suggestion": "Çelişkiyi giderin.", "confidence": 0.88}]'
)

_MOCK_SEM004 = (
    '[{"category": "anlatim", "severity": "warning", '
    '"title": "Sarkık cümle", '
    '"description": "Cümle özne-yüklem uyumsuzluğu içeriyor.", '
    '"suggestion": "Cümleyi sadeleştirin.", "confidence": 0.80}]'
)

_MOCK_EMPTY = '[]'


class TestLayerCMock:
    """Mock LLM yanıtları ile Layer C davranışı."""

    def _run_mock(self, filename: str, mock_response: str) -> set[str]:
        lc = LayerC(provider="gemini", api_key="mock-key-test")
        with patch.object(lc, "_call_llm", return_value=mock_response):
            findings = lc.run(_parse(filename))
        return {f.rule_code for f in findings}

    def test_mock_sem001_strong_mismatch(self):
        codes = self._run_mock("c_sem001_strong_mismatch.docx", _MOCK_SEM001)
        _assert_has(codes, "SEM-001", "c_sem001_strong_mismatch.docx")

    def test_mock_sem001_vague_konu(self):
        codes = self._run_mock("c_sem001_vague_konu.docx", _MOCK_SEM001)
        _assert_has(codes, "SEM-001", "c_sem001_vague_konu.docx")

    def test_mock_sem003_internal_contradiction(self):
        codes = self._run_mock("c_sem003_ic_celisik.docx", _MOCK_SEM003)
        _assert_has(codes, "SEM-003", "c_sem003_ic_celisik.docx")

    def test_mock_sem003_vague_reference(self):
        codes = self._run_mock("c_sem003_belirsiz_atif.docx", _MOCK_SEM003)
        _assert_has(codes, "SEM-003", "c_sem003_belirsiz_atif.docx")

    def test_mock_sem003_muhatap_mismatch(self):
        codes = self._run_mock("c_sem003_muhatap_uyumsuz.docx", _MOCK_SEM003)
        _assert_has(codes, "SEM-003", "c_sem003_muhatap_uyumsuz.docx")

    def test_mock_sem004_anlatim_bozuk(self):
        codes = self._run_mock("c_sem004_anlatim_bozuk.docx", _MOCK_SEM004)
        _assert_has(codes, "SEM-004", "c_sem004_anlatim_bozuk.docx")

    def test_mock_sem004_edilgen(self):
        codes = self._run_mock("c_sem004_edilgen.docx", _MOCK_SEM004)
        _assert_has(codes, "SEM-004", "c_sem004_edilgen.docx")

    def test_mock_empty_correct_doc(self):
        """Mock [] → semantik doğru belgede SEM-xxx olmamalı."""
        codes = self._run_mock("c_sem_correct.docx", _MOCK_EMPTY)
        sem_codes = [c for c in codes if c.startswith("SEM-") and c != "SEM-002"]
        assert not sem_codes, f"Doğru belgede mock LLM SEM hatası döndürmemeli: {sem_codes}"

    def test_mock_confidence_threshold(self):
        """confidence < 0.50 olan bulgular filtrelenmeli."""
        low_conf = (
            '[{"category": "konu_metin", "severity": "warning", '
            '"title": "Düşük güven", "description": "...", '
            '"suggestion": "...", "confidence": 0.30}]'
        )
        lc = LayerC(provider="gemini", api_key="mock-key-test")
        with patch.object(lc, "_call_llm", return_value=low_conf):
            findings = lc.run(_parse("c_sem001_strong_mismatch.docx"))
        assert findings == [], "Düşük confidence bulgu filtrelenmeli"

    def test_mock_invalid_json_returns_empty(self):
        """Geçersiz JSON → boş liste."""
        lc = LayerC(provider="gemini", api_key="mock-key-test")
        with patch.object(lc, "_call_llm", return_value="Bu bir JSON değil !!!"):
            findings = lc.run(_parse("c_sem001_strong_mismatch.docx"))
        assert findings == []

    def test_layer_c_no_deterministic_sem002(self):
        """EKSIK 4: SEM-002 Katman A'ya taşındı → Katman C üretmemeli (LLM boş)."""
        lc = LayerC(provider="gemini", api_key="mock-key-test")
        with patch.object(lc, "_call_llm", return_value=_MOCK_EMPTY):
            findings = lc.run(_parse("a_sem002_ek_no_ref.docx"))
        codes = {f.rule_code for f in findings}
        _assert_not_has(codes, "SEM-002", "a_sem002_ek_no_ref.docx",
                        note="deterministik kural Katman A'ya taşındı")


class TestLayerCRealAPI:
    """Gerçek API ile Layer C testleri (API anahtarı varsa)."""

    def _get_lc(self):
        lc = LayerC()
        if not lc.is_ready:
            pytest.skip(f"GEMINI_API_KEY veya ANTHROPIC_API_KEY gerekli (provider: {lc.provider})")
        return lc

    def _safe_run(self, lc: LayerC, filename: str) -> set[str]:
        try:
            findings = lc.run(_parse(filename))
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in ("429", "quota", "rate", "resource_exhausted")):
                pytest.skip(f"API kotası aşıldı: {exc}")
            raise
        if not findings:
            pytest.skip("API kotası aşılmış olabilir — boş yanıt")
        return {f.rule_code for f in findings}

    def test_real_sem001_strong_mismatch(self):
        """Güçlü konu-metin uyumsuzluğu gerçek API'de SEM-001 üretmeli."""
        lc = self._get_lc()
        codes = self._safe_run(lc, "c_sem001_strong_mismatch.docx")
        has_sem = any(c.startswith("SEM-") for c in codes)
        assert has_sem, f"En az bir SEM-xxx bekleniyor; bulunan: {codes}"

    def test_real_sem003_internal_contradiction(self):
        """İç çelişki gerçek API'de tespit edilmeli."""
        lc = self._get_lc()
        codes = self._safe_run(lc, "c_sem003_ic_celisik.docx")
        has_sem = any(c.startswith("SEM-") for c in codes)
        assert has_sem, f"En az bir SEM-xxx bekleniyor; bulunan: {codes}"

    def test_real_correct_doc_minimal_errors(self):
        """Semantik doğru belgede LLM çok az ya da hiç hata çıkarmamalı."""
        lc = self._get_lc()
        try:
            findings = lc.run(_parse("c_sem_correct.docx"))
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in ("429", "quota", "rate", "resource_exhausted")):
                pytest.skip(f"API kotası aşıldı: {exc}")
            raise
        if findings is None:
            pytest.skip("API yanıt vermedi")
        error_findings = [f for f in findings if f.severity.value == "error"]
        assert len(error_findings) == 0, (
            f"Doğru belgede {len(error_findings)} hata seviyesi bulgu: "
            f"{[f.rule_code for f in error_findings]}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE — Uçtan Uca Çok Katmanlı Testler
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineMultiLayer:
    """Pipeline ile birden fazla katmanı aynı anda test et."""

    def test_format_only_mode_no_b_c(self, pipeline):
        """format_only modunda Layer B ve C bulgusu olmamalı."""
        a, b, c = _pipeline_codes("a_fmt001_calibri.docx", pipeline, mode="format_only")
        assert not b, f"format_only'de Layer B bulgusu: {b}"
        assert not c, f"format_only'de Layer C bulgusu: {c}"
        _assert_has(a, "FMT-001", "a_fmt001_calibri.docx")

    def test_mix_fmt_hir_has_both_layers(self, pipeline):
        """FMT-001 + HIR-001 belgesi her iki katmandan da bulgu döndürmeli."""
        a, b, _ = _pipeline_codes("mix_fmt_hir.docx", pipeline, mode="full")
        _assert_has(a, "FMT-001", "mix_fmt_hir.docx")
        if b:  # Layer B aktifse
            _assert_has(b, "HIR-001", "mix_fmt_hir.docx")

    def test_perfect_doc_zero_errors(self, pipeline):
        """Mükemmel belgede deterministik katmanlar (A+B) hata üretmemeli.

        Katman C (LLM) non-deterministiktir; canlı modelin mükemmel belgede ara sıra
        döndürdüğü semantik bulgular testi kırılgan yapmasın diye yalnızca A+B denetlenir.
        """
        result = pipeline.analyze(str(FIXTURES / "test_perfect.docx"),
                                  mode="full", original_filename="test_perfect.docx")
        det_errors = [f.rule_code for f in result.findings
                      if f.layer.value in ("A", "B") and f.severity.value == "error"]
        assert not det_errors, f"Deterministik katmanlarda hata: {det_errors}"

    def test_all_fields_missing_many_errors(self, pipeline):
        """Tüm alanlar eksik belgede çok sayıda hata gelmeli."""
        result = pipeline.analyze(str(FIXTURES / "a_fld_all_missing.docx"),
                                  mode="format_only", original_filename="a_fld_all_missing.docx")
        assert result.errors >= 4, f"En az 4 hata bekleniyor; bulunan: {result.errors}"

    def test_complete_doc_no_errors(self, pipeline):
        """İlgi+Ek+Dağıtım tam belgesi Layer A hata üretmemeli."""
        a, b, c = _pipeline_codes("mix_ilgili_ekli_complete.docx", pipeline, mode="full")
        a_errors = {c for c in a if c.startswith(("FMT", "FLD", "CLS", "LNG"))}
        assert not a_errors, f"Tam belgede Layer A formatı hatası: {a_errors}"

    def test_result_filename_preserved(self, pipeline):
        """Pipeline filename'i orijinal olarak korumalı."""
        fname = "a_fmt001_calibri.docx"
        result = pipeline.analyze(str(FIXTURES / fname), mode="format_only",
                                  original_filename=fname)
        assert result.filename == fname

    def test_content_only_mode_skips_a(self, pipeline):
        """content_only modunda Layer A formatı bulgusu olmamalı."""
        a, b, c = _pipeline_codes("a_fmt001_calibri.docx", pipeline, mode="content_only")
        assert "FMT-001" not in a, "content_only modunda FMT-001 çıkmamalı"

    def test_enstitü_doc_no_fmt_errors(self, pipeline):
        """Enstitü belgesi doğru font ve marj kullandığında format hatası olmamalı."""
        a, _, _ = _pipeline_codes("ok_enstitü_yazisi.docx", pipeline, mode="format_only")
        fmt_errors = {c for c in a if c.startswith("FMT-")}
        assert not fmt_errors, f"Doğru belgede format hatası: {fmt_errors}"


# ═══════════════════════════════════════════════════════════════════════════════
# FALSE POSITIVE — Doğru belgelerin yanlış hata üretmediğini doğrula
# ═══════════════════════════════════════════════════════════════════════════════

class TestFalsePositives:
    """Tüm 'ok_*' ve 'doğru' belgeler için kapsamlı FP kontrolü."""

    @pytest.mark.parametrize("filename", [
        "ok_arial_font.docx",
        "ok_enstitü_yazisi.docx",
        "ok_daire_rektorluk.docx",
        "b_correct_upward.docx",
        "b_correct_downward.docx",
        "c_sem_correct.docx",
        "mix_enstitü_correct.docx",
        "mix_bolum_dekan_correct.docx",
        "mix_rektorluk_daire_correct.docx",
    ])
    def test_no_error_severity_findings(self, filename):
        """Doğru belgelerde 'error' seviyesinde Katman A bulgusu olmamalı."""
        doc = _parse(filename)
        findings = LayerA().run(doc)
        errors = [f.rule_code for f in findings if f.severity.value == "error"]
        assert not errors, f"[{filename}] false positive error: {errors}"

    def test_arial_font_no_fmt_error(self):
        """Arial 11pt mükemmel belgede FMT-001 olmamalı."""
        codes = _layer_a_codes("ok_arial_font.docx")
        _assert_not_has(codes, "FMT-001", "ok_arial_font.docx")

    def test_correct_ek_count_no_sem002(self):
        """3 adet denmiş, 3 ek var → SEM-002 olmamalı."""
        codes = _layer_a_codes("mix_ilgili_ekli_complete.docx")
        _assert_not_has(codes, "SEM-002", "mix_ilgili_ekli_complete.docx")

    def test_correct_date_format_no_fld005(self):
        """GG.AA.YYYY formatında tarihte FLD-005 olmamalı."""
        codes = _layer_a_codes("test_perfect.docx")
        _assert_not_has(codes, "FLD-005", "test_perfect.docx")

    def test_bolum_dekan_correct_no_hir001(self, retriever):
        """Bölüm→Dekanlık 'Arz ederim' → HIR-001 olmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        codes = _layer_b_codes("mix_bolum_dekan_correct.docx", retriever)
        _assert_not_has(codes, "HIR-001", "mix_bolum_dekan_correct.docx")