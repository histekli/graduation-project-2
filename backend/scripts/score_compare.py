"""
Skor Karşılaştırma Scripti (EKSIK 2 kabul kriteri).

Eski (severity tabanlı) formül ile yeni (kural-ağırlıklı, oransal) formülü aynı
test belgeleri üzerinde karşılaştırır. Katman A + B (deterministik) bulguları
kullanılır; LLM gerektirmez.

Eski:  max(0, 100 − HATA×10 − UYARI×5 − BİLGİ×2)
Yeni:  100 × max(0, 1 − Σ kural_ağırlığı / 100)

Çalıştırma:
  cd backend
  python -m scripts.score_compare
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.parser import parse_docx          # noqa: E402
from app.services.layer_a import LayerA             # noqa: E402
from app.services.layer_b import LayerB             # noqa: E402
from app.rag.retriever import GuidelineRetriever    # noqa: E402
from app.models.finding import Severity             # noqa: E402
from app.rules.scoring_weights import (             # noqa: E402
    compute_compliance_score, legacy_compliance_score, weight_for,
)

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# Temsili belgeler (deterministik bulgu üretenler)
DOCS = [
    "test_perfect.docx",
    "a_fmt001_calibri.docx",
    "b_hir001_muhendislik_rektor.docx",
    "a_fld_all_missing.docx",
    "a_lng_combo.docx",
    "mix_fmt_hir.docx",
    "test_all_errors.docx",
]


def _findings(name: str, retriever):
    doc = parse_docx(str(FIXTURES / name))
    fs = LayerA().run(doc)
    if retriever is not None:
        fs += LayerB(retriever=retriever).run(doc)
    return fs


def main() -> None:
    r = GuidelineRetriever()
    retriever = r if r.is_ready else None

    print(f"{'Belge':<34} {'E/U/B':>8} {'eski':>5} {'yeni':>5}   en ağır bulgular")
    print(f"{'-'*34} {'-'*8} {'-'*5} {'-'*5}   {'-'*30}")
    for name in DOCS:
        fs = _findings(name, retriever)
        e = sum(1 for f in fs if f.severity == Severity.ERROR)
        w = sum(1 for f in fs if f.severity == Severity.WARNING)
        i = sum(1 for f in fs if f.severity == Severity.INFO)
        old = legacy_compliance_score(e, w, i)
        new = compute_compliance_score(fs)
        top = sorted(fs, key=lambda f: weight_for(f.rule_code, f.severity), reverse=True)[:3]
        top_str = ", ".join(f"{f.rule_code}({weight_for(f.rule_code, f.severity)})" for f in top)
        print(f"{name:<34} {f'{e}/{w}/{i}':>8} {old:>5} {new:>5}   {top_str}")

    # Tek-bulgu kıyaslaması: font (ORTA) vs hiyerarşi (KRİTİK) — aynı severity farkı
    print(f"\n{'─'*70}")
    print("Tek hata etkisi (boş belgeye tek bulgu eklenince skor düşüşü):")
    from app.models.finding import Finding, Layer

    def _one(code, sev):
        f = Finding(id="X1", layer=Layer.A, severity=sev, rule_code=code,
                    title=code, description="")
        return compute_compliance_score([f])

    print(f"  1 × FMT-001 (font, ORTA)        → skor {_one('FMT-001', Severity.ERROR)}")
    print(f"  1 × HIR-001 (hiyerarşi, KRİTİK) → skor {_one('HIR-001', Severity.WARNING)}")
    print("  → Aynı belgede font ve hiyerarşi hatası FARKLI skor düşüşü üretir "
          "(eski formülde font 'error' olduğu için daha çok düşürürdü — savunulamaz).")


if __name__ == "__main__":
    main()
