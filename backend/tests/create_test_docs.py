"""
Test belgesi oluşturucu.
tests/fixtures/ dizinine 6 senaryo belgesi yazar.

Kullanım:
  cd backend
  python -m tests.create_test_docs
"""
from __future__ import annotations
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FIXTURES = Path(__file__).parent / "fixtures"


# ── Yardımcılar ──────────────────────────────────────────────────────────────

def _margins(doc: Document, cm: float) -> None:
    for sec in doc.sections:
        sec.top_margin = Cm(cm)
        sec.bottom_margin = Cm(cm)
        sec.left_margin = Cm(cm)
        sec.right_margin = Cm(cm)


def _para(
    doc: Document,
    text: str,
    font: str = "Times New Roman",
    pt: float = 12.0,
    bold: bool = False,
    align=WD_ALIGN_PARAGRAPH.LEFT,
) -> None:
    p = doc.add_paragraph()
    p.alignment = align
    run = p.add_run(text)
    run.font.name = font
    run.font.size = Pt(pt)
    run.bold = bold


def _center(doc: Document, text: str, font: str = "Times New Roman", pt: float = 12.0, bold: bool = False) -> None:
    _para(doc, text, font=font, pt=pt, bold=bold, align=WD_ALIGN_PARAGRAPH.CENTER)


def _body(doc: Document, text: str, font: str = "Times New Roman", pt: float = 12.0) -> None:
    _para(doc, text, font=font, pt=pt, align=WD_ALIGN_PARAGRAPH.JUSTIFY)


def _sayi_tarih_row(doc: Document, sayi_no: str = "F.01.2-2025/001",
                    tarih: str = "26.05.2025",
                    font: str = "Times New Roman", pt: float = 12.0) -> None:
    """Sayı sol kenarda, Tarih sağ kenarda — right-tab hizalaması ile."""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    tabs_el = OxmlElement("w:tabs")
    tab_el = OxmlElement("w:tab")
    tab_el.set(qn("w:val"), "right")
    tab_el.set(qn("w:pos"), "10206")  # 18 cm ≈ 10206 twip (A4 - 1.5cm*2)
    tabs_el.append(tab_el)
    pPr.append(tabs_el)

    r1 = p.add_run(f"Sayı: {sayi_no}")
    r1.font.name = font
    r1.font.size = Pt(pt)

    rt = p.add_run("\t")
    rt.font.name = font
    rt.font.size = Pt(pt)

    r2 = p.add_run(f"Tarih: {tarih}")
    r2.font.name = font
    r2.font.size = Pt(pt)


def _standard_header(
    doc: Document,
    birim: str = "Mühendislik Fakültesi",
    sayi_no: str = "F.01.2-2025/001",
    tarih: str = "26.05.2025",
    konu: str = "Konu: Akademik Faaliyet Raporu",
    muhatap: str = "Rektörlük Makamına,",
) -> None:
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, birim, bold=True)
    _sayi_tarih_row(doc, sayi_no=sayi_no, tarih=tarih)
    _para(doc, konu)
    _para(doc, "")
    _para(doc, muhatap)
    _para(doc, "")


def _standard_closing(
    doc: Document,
    kapanish: str = "Arz ederim.",
    imza_ad: str = "Prof. Dr. Ahmet Yılmaz",
    imza_unvan: str = "Dekan",
) -> None:
    _para(doc, "")
    _para(doc, kapanish)
    _para(doc, "")
    _para(doc, imza_ad)
    _para(doc, imza_unvan)


# ── Belge 1: Mükemmel belge (0 hata, 0 uyarı) ────────────────────────────────

def make_perfect(path: Path) -> None:
    """Tüm kurallara tam uyumlu resmi yazı."""
    doc = Document()
    _margins(doc, 1.5)
    _standard_header(doc)
    _body(doc, (
        "Fakültemiz bünyesinde 2024-2025 eğitim-öğretim yılında gerçekleştirilen "
        "akademik etkinliklere ait ayrıntılı bilgiler ilişik belgede yer almaktadır."
    ))
    _body(doc, (
        "Söz konusu faaliyetlerin değerlendirilmesini ve gereğinin yapılmasını "
        "saygılarınıza sunarım."
    ))
    _standard_closing(doc)
    doc.save(str(path))


# ── Belge 2: Biçim hataları (FMT-001, FMT-002, LNG-004) ─────────────────────

def make_format_errors(path: Path) -> None:
    """Yanlış font, yanlış marj, fazla boşluklar."""
    doc = Document()
    _margins(doc, 2.54)   # yanlış marj — FMT-002
    _standard_header(doc)
    # Metin gövdesi: Calibri 11pt — FMT-001
    _para(doc, (
        "Bu  belgede  fazla  boşluklar  kullanılmıştır."
    ), font="Calibri", pt=11.0, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    _para(doc, (
        "Ayrıca yazı tipi ve punto yönetmeliğe aykırıdır."
    ), font="Calibri", pt=11.0, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    _standard_closing(doc, imza_ad="Dr. Mehmet Kaya", imza_unvan="Dekan Yardımcısı")
    doc.save(str(path))


# ── Belge 3: Eksik zorunlu alanlar (FLD-001, FLD-006, FLD-007) ───────────────

def make_missing_fields(path: Path) -> None:
    """T.C. yok, Konu yok, İmza bloğu yok."""
    doc = Document()
    _margins(doc, 1.5)
    # T.C. YOK — FLD-001
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, "Mühendislik Fakültesi", bold=True)
    _sayi_tarih_row(doc)
    # KONU YOK — FLD-006
    _para(doc, "")
    _para(doc, "Rektörlük Makamına,")
    _para(doc, "")
    _body(doc, "İlgili konuya dair bilgiler ekte sunulmaktadır.")
    _para(doc, "")
    _para(doc, "Arz ederim.")
    _para(doc, "")
    # İMZA BLOĞU YOK — FLD-007
    doc.save(str(path))


# ── Belge 4: Hiyerarşi uyumsuzluğu (HIR-001) ─────────────────────────────────

def make_hierarchy_mismatch(path: Path) -> None:
    """Rektörlüğe yazılmış, yanlış 'Rica ederim' kullanılmış."""
    doc = Document()
    _margins(doc, 1.5)
    # Üst makama (Rektörlük) yazılıyor → "Arz ederim" olmalı
    _standard_header(
        doc,
        birim="Mühendislik Fakültesi",
        muhatap="Rektörlük Makamına,",
    )
    _body(doc, (
        "Fakültemiz öğrencilerinin staj süreçlerine ilişkin düzenlemeler hakkında "
        "bilgi talep edilmektedir. Konu hakkında görüşlerinizi bekliyoruz."
    ))
    # HIR-001: Rektörlüğe gidecek yazıda "Rica ederim" kullanıldı
    _standard_closing(doc, kapanish="Rica ederim.", imza_ad="Prof. Dr. Ahmet Yılmaz", imza_unvan="Dekan")
    doc.save(str(path))


# ── Belge 5: Mantıksal tutarsızlıklar (SEM-001, SEM-002) ─────────────────────

def make_semantic_issues(path: Path) -> None:
    """Konu-metin uyumsuzluğu + ek sayısı tutarsızlığı."""
    doc = Document()
    _margins(doc, 1.5)
    _standard_header(
        doc,
        konu="Konu: 2025 Yılı Bütçe Önerisi",    # Bütçe konusu
    )
    # Metin bütçeyle alakasız — SEM-001
    _body(doc, (
        "Fakültemiz Bilgisayar Mühendisliği Bölümüne yapılacak yeni "
        "öğretim üyesi atamaları kapsamında, adayların özgeçmiş ve akademik "
        "yeterlilik belgelerini inceledik. Atama kriterleri değerlendirilmiş olup "
        "her aday için detaylı rapor hazırlanmıştır."
    ))
    # Metinde 3 ek deniyor ama ekte 2 var — SEM-002
    _body(doc, (
        "Ekte sunulan 3 adet belgenin incelenerek gereğinin yapılmasını arz ederim."
    ))
    _standard_closing(doc)
    _para(doc, "")
    _para(doc, "EK:")
    _para(doc, "EK-1: Aday Listesi")
    _para(doc, "EK-2: Değerlendirme Formu")
    # (EK-3 yok — tutarsızlık)
    doc.save(str(path))


# ── Belge 6: Dil/yazım hataları (LNG-001, LNG-002, LNG-003, CLS-002) ─────────

def make_language_errors(path: Path) -> None:
    """Cümle başı küçük harf, virgül öncesi boşluk, noktadan sonra boşluk yok, yasaklı kapanış."""
    doc = Document()
    _margins(doc, 1.5)
    _standard_header(doc)
    # LNG-001: cümle sonrası küçük harfle devam
    _body(doc, "Belge incelenmiştir. bu konuda gerekli işlemler yapılacaktır.")
    # LNG-002: virgül öncesi boşluk
    _body(doc, "Söz konusu durum ,ilgili birimlerle paylaşılmıştır.")
    # LNG-003: noktadan sonra boşluk yok
    _body(doc, "Raporlar hazırlanmıştır.Sonuçlar değerlendirilecektir.")
    # LNG-004: art arda boşluk
    _body(doc, "Gerekli  evraklar  teslim  edilmiştir.")
    # CLS-002: yasaklı kapanış ifadesi — parser tam metni sakladığından tespit edilir
    _standard_closing(doc, kapanish="Saygılarımla arz ederim.")
    doc.save(str(path))


# ── Belge 7: Yetki devri imzası (HIR-002) ─────────────────────────────────────

def make_rektor_a(path: Path) -> None:
    """İmzada 'Rektör a.' ibaresi bulunan yetki devri belgesi."""
    doc = Document()
    _margins(doc, 1.5)
    _standard_header(doc, muhatap="Mühendislik Fakültesi Dekanlığına,")
    _body(doc, (
        "Üniversitemiz akademik takvimi kapsamında düzenlenen konferansa ait "
        "katılım listesi ve program ekte sunulmaktadır."
    ))
    # Rektör adına imzalayan Genel Sekreter
    _para(doc, "")
    _para(doc, "Arz ederim.")
    _para(doc, "")
    _para(doc, "Prof. Dr. Mehmet Demir")
    _para(doc, "Rektör a.")
    _para(doc, "Genel Sekreter")
    doc.save(str(path))


# ── Ana akış ─────────────────────────────────────────────────────────────────

def create_all(output_dir: Path | None = None) -> Path:
    dest = output_dir or FIXTURES
    dest.mkdir(parents=True, exist_ok=True)

    specs = [
        ("test_perfect.docx",           make_perfect),
        ("test_format_errors.docx",     make_format_errors),
        ("test_missing_fields.docx",    make_missing_fields),
        ("test_hierarchy_mismatch.docx",make_hierarchy_mismatch),
        ("test_semantic_issues.docx",   make_semantic_issues),
        ("test_language_errors.docx",   make_language_errors),
        ("test_rektor_a.docx",          make_rektor_a),
    ]

    for fname, fn in specs:
        fpath = dest / fname
        fn(fpath)
        print(f"  ✓ {fname}")

    return dest


if __name__ == "__main__":
    print("Test belgeleri oluşturuluyor...")
    d = create_all()
    print(f"\n6 belge → {d}")
