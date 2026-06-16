"""
Parser güvenilirlik metrikleri (EKSIK 3).

  1. Bölüm tespiti ground-truth değerlendirmesi: tests/fixtures/section_labels.json
     içindeki elle doğrulanmış etiketlere karşı precision/recall/F1 ölçer ve eşik
     altına düşerse başarısız olur (regresyon koruması).
  2. Yanlış-alarm (false-positive) eşiği: ok_* referans belgelerinde üretilen
     toplam deterministik bulgu sayısı eşiği aşarsa başarısız olur.

`python -m tests.test_parser_metrics` ile metrikleri yazdırabilirsiniz.
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

import pytest

from app.services.parser import parse_docx
from app.services.layer_a import LayerA
from tests.create_comprehensive_docs import create_comprehensive, FIXTURES

LABELS_PATH = FIXTURES / "section_labels.json"

# Regresyon eşikleri (mevcut: accuracy 0.97, macroF1 0.97)
MIN_ACCURACY = 0.90
MIN_MACRO_F1 = 0.85
# ok_* referans belgelerinde izin verilen toplam deterministik bulgu (mevcut: 0)
MAX_FP_TOTAL = 3
# Bu bölümler kararlı yapısal işaretlere sahip → kusursuz beklenir
PERFECT_CLASSES = {"header", "konu", "muhatap", "ilgi", "ek", "dagitim", "sayi_tarih"}


@pytest.fixture(scope="session", autouse=True)
def ensure_fixtures():
    if not LABELS_PATH.exists() or not (FIXTURES / "ok_short_minimal.docx").exists():
        create_comprehensive()


def compute_section_metrics() -> dict:
    """section_labels.json'a karşı bölüm tespiti P/R/F1 + accuracy hesaplar."""
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    gold_n = defaultdict(int)
    correct = total = 0

    for name, rows in labels.items():
        parsed = parse_docx(str(FIXTURES / name))
        preds = [pp.section.value for pp in parsed.paragraphs]
        assert len(preds) == len(rows), (
            f"{name}: paragraf sayısı uyuşmuyor (parser={len(preds)}, etiket={len(rows)})"
        )
        for pred, row in zip(preds, rows):
            gold = row["section"]
            gold_n[gold] += 1
            total += 1
            if pred == gold:
                correct += 1
                tp[gold] += 1
            else:
                fp[pred] += 1
                fn[gold] += 1

    classes = sorted(set(list(tp) + list(fp) + list(fn)))
    per_class = {}
    f1s = []
    for c in classes:
        P = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 1.0
        R = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 1.0
        F = 2 * P * R / (P + R) if (P + R) else 0.0
        per_class[c] = {"P": P, "R": R, "F1": F, "n": gold_n[c]}
        f1s.append(F)

    return {
        "accuracy": correct / total if total else 1.0,
        "macro_f1": sum(f1s) / len(f1s) if f1s else 1.0,
        "paragraphs": total,
        "per_class": per_class,
    }


# ── Bölüm tespiti F1 ─────────────────────────────────────────────────────────

class TestSectionDetectionF1:
    def test_accuracy_above_threshold(self):
        m = compute_section_metrics()
        assert m["accuracy"] >= MIN_ACCURACY, (
            f"Bölüm tespiti accuracy={m['accuracy']:.3f} < {MIN_ACCURACY}"
        )

    def test_macro_f1_above_threshold(self):
        m = compute_section_metrics()
        assert m["macro_f1"] >= MIN_MACRO_F1, (
            f"Bölüm tespiti macro-F1={m['macro_f1']:.3f} < {MIN_MACRO_F1}"
        )

    def test_structural_classes_perfect(self):
        """Yapısal işareti güçlü bölümler kusursuz tespit edilmeli."""
        m = compute_section_metrics()
        for c in PERFECT_CLASSES:
            pc = m["per_class"].get(c)
            if pc is None:
                continue
            assert pc["F1"] == pytest.approx(1.0), (
                f"'{c}' bölümü F1={pc['F1']:.2f} (kusursuz beklenir)"
            )


# ── Yanlış-alarm (false-positive) eşiği ──────────────────────────────────────

class TestReferenceFalsePositives:
    def _ok_docs(self):
        return sorted(p.name for p in FIXTURES.glob("ok_*.docx"))

    def test_reference_set_size(self):
        """Referans belge sayısı yeterli ölçekte (≥12) olmalı."""
        assert len(self._ok_docs()) >= 12, (
            f"En az 12 ok_* referans belge beklenir; bulunan: {len(self._ok_docs())}"
        )

    def test_no_error_or_warning_in_reference_docs(self):
        """ok_* belgelerinde hiç error/warning seviyesinde Katman A bulgusu olmamalı."""
        offenders = {}
        for name in self._ok_docs():
            fs = LayerA().run(parse_docx(str(FIXTURES / name)))
            ew = [f.rule_code for f in fs if f.severity.value in ("error", "warning")]
            if ew:
                offenders[name] = ew
        assert not offenders, f"Referans belgelerde yanlış-alarm (error/warning): {offenders}"

    def test_total_findings_below_threshold(self):
        """Tüm ok_* belgelerinde toplam deterministik bulgu eşiği aşmamalı (regresyon)."""
        total = sum(
            len(LayerA().run(parse_docx(str(FIXTURES / name))))
            for name in self._ok_docs()
        )
        assert total <= MAX_FP_TOTAL, (
            f"ok_* belgelerinde toplam {total} bulgu > eşik {MAX_FP_TOTAL} — yanlış-alarm artışı"
        )


if __name__ == "__main__":
    m = compute_section_metrics()
    print(f"Bölüm tespiti — {m['paragraphs']} paragraf, "
          f"accuracy={m['accuracy']:.3f}, macro-F1={m['macro_f1']:.3f}")
    print(f"{'bölüm':<12} {'P':>5} {'R':>5} {'F1':>5} {'n':>4}")
    for c, pc in sorted(m["per_class"].items()):
        print(f"{c:<12} {pc['P']:>5.2f} {pc['R']:>5.2f} {pc['F1']:>5.2f} {pc['n']:>4}")
