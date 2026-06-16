"""
Türkçe dil işleme testleri (EKSIK 5).

İki bölüm:
  1. tr_lower / tr_upper / kapanış tespiti — saf fonksiyon birim testleri.
  2. Çekim-toleranslı kapanış: morfolojik varyasyonların CLS-001'i yanlış
     tetiklememesi ve hiyerarşi yanlışsa HIR-001'in hâlâ çalışması.
"""
from __future__ import annotations
import pytest

from app.services.turkish_text import (
    tr_lower, tr_upper, tr_fold,
    is_closing_line, closing_uses_arz, closing_uses_rica, closing_uses_approval,
)
from app.services.parser import parse_docx
from app.services.layer_a import LayerA
from app.services.layer_b import LayerB
from app.rag.retriever import GuidelineRetriever
from tests.create_comprehensive_docs import create_comprehensive, FIXTURES


@pytest.fixture(scope="session", autouse=True)
def ensure_fixtures():
    if not (FIXTURES / "infl_arz_edilmektedir.docx").exists():
        create_comprehensive()


@pytest.fixture(scope="session")
def retriever():
    r = GuidelineRetriever()
    return r if r.is_ready else None


def _parse(name: str):
    return parse_docx(str(FIXTURES / name))


def _layer_a_codes(name: str) -> set[str]:
    return {f.rule_code for f in LayerA().run(_parse(name))}


# ── 1. Büyük/küçük harf dönüşümü ─────────────────────────────────────────────

class TestTurkishCase:
    def test_tr_lower_dotted_capital_i(self):
        assert tr_lower("İLGİ") == "ilgi"

    def test_tr_lower_dotless_handling(self):
        assert tr_lower("BAŞKANLIK") == "başkanlık"
        assert tr_lower("IĞDIR") == "ığdır"

    def test_tr_upper_dotless(self):
        assert tr_upper("ığdır") == "IĞDIR"

    def test_tr_upper_dotted(self):
        assert tr_upper("bilgi") == "BİLGİ"
        assert tr_upper("ilgi") == "İLGİ"

    def test_roundtrip_consistency(self):
        # tr_upper sonrası tr_lower özgün küçük biçime dönmeli
        assert tr_lower(tr_upper("işlem")) == "işlem"
        assert tr_lower(tr_upper("ışık")) == "ışık"

    def test_builtin_lower_differs(self):
        """Yerleşik str.lower() ile farkı belgelemek için (regresyon değil, kanıt)."""
        # str.lower("İ") birleşik nokta üretirken tr_lower temiz "i" verir
        assert tr_lower("İ") == "i"
        assert "İ".lower() != "i"  # yerleşik metot bozuk sonuç verir

    def test_fold_strips_diacritics(self):
        assert tr_fold("İŞLEM Görüşü") == "islem gorusu"


# ── 2. Çekim-toleranslı kapanış tespiti (saf fonksiyon) ──────────────────────

class TestClosingDetection:
    @pytest.mark.parametrize("text", [
        "Arz ederim.",
        "Arz ederiz.",
        "Bilgilerinize arz edilmektedir.",
        "Gereğini arz ediyorum.",
        "Arz olunur.",
        "Rica ederim.",
        "Gereğini rica ederiz.",
        "Rica olunur.",
        "Arz ve rica ederim.",
        "OLUR",
        "Uygundur.",
    ])
    def test_recognized_as_closing(self, text):
        assert is_closing_line(text), f"kapanış sayılmalı: {text!r}"

    @pytest.mark.parametrize("text", [
        "Arz edilen konuların incelenmesi gerekmektedir.",
        "Rica edilen belgeler henüz teslim edilmemiştir.",
        "Fakültemiz çalışmalarına devam etmektedir.",
    ])
    def test_body_text_not_closing(self, text):
        assert not is_closing_line(text), f"gövde metni kapanış sayılmamalı: {text!r}"

    def test_arz_vs_rica_classification(self):
        assert closing_uses_arz("arz edilmektedir")
        assert not closing_uses_rica("arz edilmektedir")
        assert closing_uses_rica("rica olunur")
        assert not closing_uses_arz("rica olunur")
        assert closing_uses_approval("OLUR")


# ── 3. Çekim varyasyonları belge davranışı (entegrasyon) ─────────────────────

class TestInflectionInDocuments:
    @pytest.mark.parametrize("filename", [
        "infl_arz_edilmektedir.docx",
        "infl_arz_olunur.docx",
        "infl_arz_ederiz.docx",
        "infl_rica_ederiz_wrong.docx",
    ])
    def test_inflected_closing_no_cls001(self, filename):
        """Çekimli kapanış geçerli sayılmalı → CLS-001 (kapanış eksik) çıkmamalı."""
        codes = _layer_a_codes(filename)
        assert "CLS-001" not in codes, (
            f"[{filename}] çekimli kapanış tanınmadı, CLS-001 yanlış tetiklendi: {sorted(codes)}"
        )

    def test_arz_edilmektedir_parsed_as_closing(self):
        parsed = _parse("infl_arz_edilmektedir.docx")
        assert parsed.kapanis_phrase is not None
        assert "edilmektedir" in tr_lower(parsed.kapanis_phrase)

    def test_correct_upward_inflection_no_hir001(self, retriever):
        """'arz edilmektedir' üst makama doğru → HIR-001 çıkmamalı."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        doc = _parse("infl_arz_edilmektedir.docx")
        codes = {f.rule_code for f in LayerB(retriever=retriever).run(doc)}
        assert "HIR-001" not in codes, f"yanlış HIR-001: {sorted(codes)}"

    def test_wrong_hierarchy_inflection_still_triggers_hir001(self, retriever):
        """'rica ederiz' (çekimli) üst makama → HIR-001 hâlâ tetiklenmeli."""
        if retriever is None:
            pytest.skip("ChromaDB yok")
        doc = _parse("infl_rica_ederiz_wrong.docx")
        codes = {f.rule_code for f in LayerB(retriever=retriever).run(doc)}
        assert "HIR-001" in codes, (
            f"çekimli 'rica' üst makama HIR-001 üretmeli; bulunan: {sorted(codes)}"
        )
        # Çekimli kapanış yine de tanınmalı → CLS-001 yok
        assert "CLS-001" not in _layer_a_codes("infl_rica_ederiz_wrong.docx")
