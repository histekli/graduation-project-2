"""
Katman bütünlüğü testleri (EKSIK 4).

Mimari anlatı: Katman A = deterministik motor, Katman C = YALNIZCA LLM.
Deterministik içerik kuralları (SEM-002 ek-metin, SEM-006 tekrar) Katman C'den
Katman A'ya taşındı. Bu testler:
  • SEM-002 / SEM-006 bulgularının layer alanının "A" olduğunu,
  • Katman C kodunda deterministik kural metodunun kalmadığını,
  • Katman C bulgularının tamamının layer="C" ve LLM kategorilerinden olduğunu
doğrular.
"""
from __future__ import annotations
import pytest
from unittest.mock import patch

from app.services.parser import parse_docx
from app.services.layer_a import LayerA
from app.services.layer_c import LayerC
from tests.create_comprehensive_docs import create_comprehensive, FIXTURES


@pytest.fixture(scope="session", autouse=True)
def ensure_fixtures():
    if not (FIXTURES / "a_sem006_repeated.docx").exists():
        create_comprehensive()


def _parse(name):
    return parse_docx(str(FIXTURES / name))


# ── Deterministik içerik kuralları Katman A'da ───────────────────────────────

class TestDeterministicRulesInLayerA:
    def test_sem002_finding_is_layer_a(self):
        findings = LayerA().run(_parse("a_sem002_ek_no_ref.docx"))
        sem002 = [f for f in findings if f.rule_code == "SEM-002"]
        assert sem002, "SEM-002 Layer A'da üretilmeli"
        assert all(f.layer.value == "A" for f in sem002), (
            f"SEM-002 layer alanı 'A' olmalı: {[f.layer.value for f in sem002]}"
        )

    def test_sem006_finding_is_layer_a(self):
        findings = LayerA().run(_parse("a_sem006_repeated.docx"))
        sem006 = [f for f in findings if f.rule_code == "SEM-006"]
        assert sem006, "SEM-006 Layer A'da üretilmeli"
        assert all(f.layer.value == "A" for f in sem006)


# ── Katman C yalnızca LLM bulgusu üretir ─────────────────────────────────────

class TestLayerCIsLlmOnly:
    def test_no_deterministic_methods_remain(self):
        """Deterministik kural metodları Katman C'den kaldırılmış olmalı."""
        assert not hasattr(LayerC, "_check_ek_references")
        assert not hasattr(LayerC, "_check_repeated_content")

    def test_layer_c_findings_all_layer_c_and_llm_codes(self):
        """Mock LLM yanıtı → tüm bulgular layer='C' ve SEM-002/006 İÇERMEZ."""
        mock = (
            '[{"category": "konu_metin", "severity": "warning", '
            '"title": "Konu-metin", "description": "...", '
            '"suggestion": "...", "confidence": 0.8},'
            '{"category": "anlatim", "severity": "info", '
            '"title": "Anlatım", "description": "...", '
            '"suggestion": "...", "confidence": 0.7}]'
        )
        lc = LayerC(provider="gemini", api_key="mock-key-test")
        with patch.object(lc, "_call_llm", return_value=mock):
            findings = lc.run(_parse("c_sem001_strong_mismatch.docx"))
        assert findings, "Mock LLM bulgu döndürmeli"
        assert all(f.layer.value == "C" for f in findings)
        deterministic = {f.rule_code for f in findings} & {"SEM-002", "SEM-006"}
        assert not deterministic, f"Katman C deterministik kod üretmemeli: {deterministic}"

    def test_layer_c_empty_when_llm_empty(self):
        """LLM boş dönerse Katman C hiçbir (deterministik) bulgu üretmemeli."""
        lc = LayerC(provider="gemini", api_key="mock-key-test")
        with patch.object(lc, "_call_llm", return_value="[]"):
            findings = lc.run(_parse("a_sem002_ek_no_ref.docx"))
        assert findings == [], f"Katman C deterministik bulgu sızdırdı: {findings}"
