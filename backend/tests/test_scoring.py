"""
Ağırlıklı uyum skoru testleri (EKSIK 2).

  • Ağırlıklar merkezi dosyada, kural koduna göre (severity'den bağımsız).
  • Aynı belgede font (ORTA) ile hiyerarşi (KRİTİK) farklı skor düşüşü üretir.
  • Skor her zaman 0–100 ve monotoniktir (daha çok/ağır hata → daha düşük skor).
"""
from __future__ import annotations
import pytest

from app.models.finding import Finding, Layer, Severity
from app.rules.scoring_weights import (
    compute_compliance_score, weight_for, RULE_WEIGHTS,
    KRITIK, ORTA, DUSUK, DOYGUNLUK_CEZASI,
)


def _f(code: str, severity: Severity = Severity.WARNING) -> Finding:
    return Finding(id="X", layer=Layer.A, severity=severity, rule_code=code,
                   title=code, description="")


# ── Ağırlık tablosu ──────────────────────────────────────────────────────────

class TestWeights:
    def test_hierarchy_is_critical(self):
        assert weight_for("HIR-001", Severity.WARNING) == KRITIK

    def test_font_is_medium(self):
        assert weight_for("FMT-001", Severity.ERROR) == ORTA

    def test_punctuation_is_low(self):
        assert weight_for("LNG-002", Severity.INFO) == DUSUK

    def test_weight_decoupled_from_severity(self):
        """HIR-001 'warning' ama KRİTİK; FMT-001 'error' ama ORTA — severity'den bağımsız."""
        assert weight_for("HIR-001", Severity.WARNING) > weight_for("FMT-001", Severity.ERROR)

    def test_unknown_code_falls_back_to_severity(self):
        assert weight_for("XYZ-999", Severity.ERROR) == ORTA
        assert weight_for("XYZ-999", Severity.INFO) == DUSUK


# ── Skor davranışı ───────────────────────────────────────────────────────────

class TestScore:
    def test_perfect_is_100(self):
        assert compute_compliance_score([]) == 100

    def test_range_always_0_100(self):
        for findings in ([], [_f("FMT-001")], [_f("HIR-001")] * 20):
            s = compute_compliance_score(findings)
            assert 0 <= s <= 100

    def test_font_vs_hierarchy_different_drop(self):
        """Kabul kriteri: 1 font hatası ile 1 hiyerarşi hatası FARKLI skor düşüşü."""
        font = compute_compliance_score([_f("FMT-001", Severity.ERROR)])
        hier = compute_compliance_score([_f("HIR-001", Severity.WARNING)])
        assert font != hier
        assert hier < font, "Hiyerarşi hatası fonttan daha çok düşürmeli (kritik > orta)"

    def test_monotonic_more_findings_lower_score(self):
        s1 = compute_compliance_score([_f("FMT-001")])
        s2 = compute_compliance_score([_f("FMT-001"), _f("LNG-002")])
        s3 = compute_compliance_score([_f("FMT-001"), _f("LNG-002"), _f("HIR-001")])
        assert s1 > s2 > s3

    def test_monotonic_heavier_lower_score(self):
        light = compute_compliance_score([_f("LNG-002")])     # DÜŞÜK
        heavy = compute_compliance_score([_f("FLD-001")])     # KRİTİK
        assert heavy < light

    def test_saturates_at_zero(self):
        # 6 kritik (6×20=120 > 100) → 0'da doygunlaşır, negatif olmaz
        findings = [_f("FLD-001")] * 6
        assert compute_compliance_score(findings) == 0

    def test_formula_value(self):
        # 1 KRİTİK (20) → 100 × (1 − 20/100) = 80
        assert compute_compliance_score([_f("HIR-001")]) == 80
        # 1 ORTA (8) → 92 ; 1 DÜŞÜK (2) → 98
        assert compute_compliance_score([_f("FMT-001")]) == 92
        assert compute_compliance_score([_f("LNG-002")]) == 98


# ── Merkezi tablo bütünlüğü ──────────────────────────────────────────────────

class TestWeightTable:
    def test_all_weights_positive(self):
        assert all(w > 0 for w in RULE_WEIGHTS.values())

    def test_three_tiers_used(self):
        vals = set(RULE_WEIGHTS.values())
        assert {KRITIK, ORTA, DUSUK} <= vals

    def test_saturation_constant(self):
        assert DOYGUNLUK_CEZASI == 100
