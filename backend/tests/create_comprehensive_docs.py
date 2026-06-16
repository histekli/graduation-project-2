"""
Kapsamlı Test Belgesi Oluşturucu
Her kural kodu ve katman için ayrı senaryo belgesi üretir.

Senaryo grupları:
  a_*   — Katman A (deterministik) senaryoları
  b_*   — Katman B (RAG) senaryoları
  c_*   — Katman C (LLM semantik) senaryoları
  mix_* — Birden fazla katmanı kapsayan karmaşık senaryolar
  ok_*  — Hatasız referans belgeler (false-positive kontrolü)

Kullanım:
  cd backend
  python -m tests.create_comprehensive_docs
"""
from __future__ import annotations
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FIXTURES = Path(__file__).parent / "fixtures"

# ── Genel yardımcılar ─────────────────────────────────────────────────────────

def _margins(doc: Document, cm: float = 1.5) -> None:
    for sec in doc.sections:
        sec.top_margin    = Cm(cm)
        sec.bottom_margin = Cm(cm)
        sec.left_margin   = Cm(cm)
        sec.right_margin  = Cm(cm)


def _para(doc, text, font="Times New Roman", pt=12.0, bold=False,
          align=WD_ALIGN_PARAGRAPH.LEFT) -> None:
    p = doc.add_paragraph()
    p.alignment = align
    run = p.add_run(text)
    run.font.name = font
    run.font.size = Pt(pt)
    run.bold = bold


def _center(doc, text, font="Times New Roman", pt=12.0, bold=False) -> None:
    _para(doc, text, font=font, pt=pt, bold=bold, align=WD_ALIGN_PARAGRAPH.CENTER)


def _body(doc, text, font="Times New Roman", pt=12.0) -> None:
    _para(doc, text, font=font, pt=pt, align=WD_ALIGN_PARAGRAPH.JUSTIFY)


def _sayi_tarih_row(doc, sayi_no="F.01.2-2025/042", tarih="26.05.2025",
                    font="Times New Roman", pt=12.0) -> None:
    """Sayı sol kenarda, Tarih sağ kenarda — right-tab hizalaması ile."""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    tabs_el = OxmlElement("w:tabs")
    tab_el = OxmlElement("w:tab")
    tab_el.set(qn("w:val"), "right")
    # A4 (21cm) - sol (1.5cm) - sağ (1.5cm) = 18cm metin alanı ≈ 10206 twip
    tab_el.set(qn("w:pos"), "10206")
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


def _std_header(doc, birim="Mühendislik Fakültesi",
                sayi_no="F.01.2-2025/042",
                tarih="26.05.2025",
                konu="Konu: Akademik Faaliyet Raporu",
                muhatap="Rektörlük Makamına,") -> None:
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, birim, bold=True)
    _sayi_tarih_row(doc, sayi_no=sayi_no, tarih=tarih)
    _para(doc, konu)
    _para(doc, "")
    _para(doc, muhatap)
    _para(doc, "")


def _std_closing(doc, phrase="Arz ederim.", name="Prof. Dr. Ahmet Yılmaz",
                 title="Dekan") -> None:
    _para(doc, "")
    _para(doc, phrase)
    _para(doc, "")
    _para(doc, name)
    _para(doc, title)


def _save(doc: Document, name: str) -> Path:
    path = FIXTURES / name
    doc.save(str(path))
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# KATMAN A — Deterministik Kurallar
# ═══════════════════════════════════════════════════════════════════════════════

# ── FMT-001: Farklı yanlış font kombinasyonları ──────────────────────────────

def make_a_font_calibri(path: Path) -> None:
    """FMT-001: Calibri 11pt — yaygın yanlış font."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "Fakültemiz 2025 yılı akademik faaliyetlerine ilişkin rapor hazırlanmıştır.",
          font="Calibri", pt=11.0)
    _body(doc, "Söz konusu rapor ekte sunulmaktadır.", font="Calibri", pt=11.0)
    _std_closing(doc)
    _save(doc, path.name)


def make_a_font_arial_wrong_size(path: Path) -> None:
    """FMT-001: Arial 12pt — doğru font yanlış punto (Arial 11pt olmalı)."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "Bölümümüz öğrencilerinin staj süreçleri hakkında bilgi sunulmaktadır.",
          font="Arial", pt=12.0)
    _body(doc, "Gereğini bilgilerinize arz ederim.", font="Arial", pt=12.0)
    _std_closing(doc)
    _save(doc, path.name)


def make_a_font_tnr_wrong_size(path: Path) -> None:
    """FMT-001: Times New Roman 11pt — doğru font yanlış punto (12pt olmalı)."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "Üniversitemiz akademik takvimi kapsamında düzenlenen etkinlikler hakkında bilgi verilecektir.",
          font="Times New Roman", pt=11.0)
    _std_closing(doc)
    _save(doc, path.name)


def make_a_font_mixed(path: Path) -> None:
    """FMT-001: Aynı belgede hem TNR 12pt hem Calibri 11pt (karışık)."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "Bu paragraf doğru font ile yazılmıştır.", font="Times New Roman", pt=12.0)
    _body(doc, "Bu paragraf ise yanlış Calibri fontu ile yazılmıştır.", font="Calibri", pt=11.0)
    _body(doc, "Bu paragraf da yanlış, Arial büyük punto kullanılmış.", font="Arial", pt=14.0)
    _std_closing(doc)
    _save(doc, path.name)


# ── FMT-002: Marj hataları ────────────────────────────────────────────────────

def make_a_margin_large(path: Path) -> None:
    """FMT-002: 2.54 cm marj (Word varsayılanı) — 1.5 cm olmalı."""
    doc = Document()
    _margins(doc, cm=2.54)
    _std_header(doc)
    _body(doc, "Bu belge Word'ün varsayılan marj ayarları ile oluşturulmuştur.")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_margin_small(path: Path) -> None:
    """FMT-002: 1.0 cm marj — çok dar, 1.5 cm olmalı."""
    doc = Document()
    _margins(doc, cm=1.0)
    _std_header(doc)
    _body(doc, "Bu belge çok dar marj ayarları ile oluşturulmuştur.")
    _std_closing(doc)
    _save(doc, path.name)


# ── FLD: Eksik zorunlu alanlar ────────────────────────────────────────────────

def make_a_missing_tc(path: Path) -> None:
    """FLD-001: Sadece T.C. başlığı eksik."""
    doc = Document()
    _margins(doc)
    # T.C. YOK
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, "Mühendislik Fakültesi", bold=True)
    _sayi_tarih_row(doc)
    _para(doc, "Konu: Bölüm Faaliyet Raporu")
    _para(doc, "")
    _para(doc, "Rektörlük Makamına,")
    _para(doc, "")
    _body(doc, "Fakültemiz bölümlerinin 2024-2025 dönemi faaliyet raporu ekte sunulmaktadır.")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_missing_university(path: Path) -> None:
    """FLD-002: Üniversite adı satırı eksik."""
    doc = Document()
    _margins(doc)
    _center(doc, "T.C.", bold=True)
    # ÜNİVERSİTE ADI YOK
    _center(doc, "Mühendislik Fakültesi", bold=True)
    _sayi_tarih_row(doc)
    _para(doc, "Konu: Staj Süreçleri Düzenlemesi")
    _para(doc, "")
    _para(doc, "Rektörlük Makamına,")
    _para(doc, "")
    _body(doc, "Staj süreçlerine ilişkin yeni düzenlemeler hakkında bilgi sunulmaktadır.")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_missing_sayi(path: Path) -> None:
    """FLD-004: Sayı alanı eksik."""
    doc = Document()
    _margins(doc)
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, "Mühendislik Fakültesi", bold=True)
    # SAYI YOK
    _para(doc, "Tarih: 26.05.2025")
    _para(doc, "Konu: Burs Başvurusu")
    _para(doc, "")
    _para(doc, "Rektörlük Makamına,")
    _para(doc, "")
    _body(doc, "Burs başvurularının değerlendirilmesi talep edilmektedir.")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_wrong_date_format(path: Path) -> None:
    """FLD-005: Tarih yanlış formatta (2025/05/26 yerine 26.05.2025 olmalı)."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        sayi_no="F.01.2-2025/010",
        tarih="2025/05/26")
    _body(doc, "Tarih formatı yanlış yazılmış (YYYY/MM/DD yerine GG.AA.YYYY olmalı).")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_missing_konu(path: Path) -> None:
    """FLD-006: Konu satırı eksik."""
    doc = Document()
    _margins(doc)
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, "Mühendislik Fakültesi", bold=True)
    _para(doc, "Sayı: F.01.2-2025/042                    Tarih: 26.05.2025")
    # KONU YOK
    _para(doc, "")
    _para(doc, "Rektörlük Makamına,")
    _para(doc, "")
    _body(doc, "Konu satırı olmayan bir yazı örneğidir. Bu durum FLD-006 hatasını tetiklemelidir.")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_missing_imza(path: Path) -> None:
    """FLD-007: İmza bloğu eksik (kapanış var ama imzalayan yok)."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "Fakültemiz 2024-2025 akademik yılı faaliyet raporu ekte sunulmaktadır.")
    _para(doc, "")
    _para(doc, "Arz ederim.")
    # İMZA BLOĞU YOK (ad, soyad, unvan eklenmedi)
    _save(doc, path.name)


def make_a_all_fields_missing(path: Path) -> None:
    """FLD-001..007 hepsi: Zorunlu alanların tamamı eksik minimal belge."""
    doc = Document()
    _margins(doc)
    # Sadece bir gövde paragrafı — hiçbir zorunlu alan yok
    _body(doc, "Bu belge zorunlu alanların hiçbirini içermiyor.")
    _body(doc, "FLD-001 (T.C.), FLD-002 (üniversite), FLD-003 (birim), "
               "FLD-004 (sayı), FLD-005 (tarih), FLD-006 (konu), "
               "FLD-007 (imza) hepsinin tetiklenmesi beklenir.")
    _save(doc, path.name)


# ── CLS: Kapanış ifadesi hataları ────────────────────────────────────────────

def make_a_no_closing(path: Path) -> None:
    """CLS-001: Kapanış ifadesi hiç yok."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "Fakültemiz 2025 yılı bütçe teklifine ilişkin gerekli bilgiler sunulmaktadır.")
    _body(doc, "Tablolar ekte yer almaktadır.")
    _para(doc, "")
    # Kapanış YOK — doğrudan imza
    _para(doc, "Prof. Dr. Ahmet Yılmaz")
    _para(doc, "Dekan")
    _save(doc, path.name)


def make_a_forbidden_closing_saygila(path: Path) -> None:
    """CLS-002: 'Saygılarımla arz ederim' — yasaklı kapanış."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "İlgili birimlerle koordineli olarak yürütülen çalışmalar tamamlanmıştır.")
    _std_closing(doc, phrase="Saygılarımla arz ederim.")
    _save(doc, path.name)


def make_a_forbidden_closing_rica_olunur(path: Path) -> None:
    """CLS-002: 'Rica olunur' — yasaklı kapanış."""
    doc = Document()
    _margins(doc)
    _std_header(doc, muhatap="Bilgisayar Mühendisliği Bölüm Başkanlığına,",
               konu="Konu: Ders Programı Güncellemesi")
    _body(doc, "2025-2026 akademik yılı ders programı değişikliklerine ilişkin öneriler aşağıda sunulmuştur.")
    _std_closing(doc, phrase="Rica olunur.", name="Prof. Dr. Ahmet Yılmaz", title="Dekan")
    _save(doc, path.name)


def make_a_onay_words_uygundur(path: Path) -> None:
    """CLS-003: Onay yazısında 'Uygundur' kullanılmış — 'OLUR' olmalı."""
    doc = Document()
    _margins(doc)
    _std_header(doc, konu="Konu: İzin Talebi Onayı")
    _body(doc, "Personel Dairesi Başkanlığının 15.05.2025 tarih ve 142 sayılı yazısı incelenmiştir.")
    _body(doc, "Talep edilen yıllık izin hakkı değerlendirilmiş olup uygun bulunmuştur.")
    _para(doc, "")
    _para(doc, "Uygundur.")
    _para(doc, "")
    _para(doc, "Prof. Dr. Ahmet Yılmaz")
    _para(doc, "Rektör")
    _save(doc, path.name)


# ── LNG: Dil/Yazım hataları ──────────────────────────────────────────────────

def make_a_lng001_sentence_case(path: Path) -> None:
    """LNG-001: Cümle başları küçük harf."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    # her cümle küçük harfle başlıyor
    _body(doc, "fakültemiz akademik faaliyetleri kapsamında gerçekleştirilen çalışmalar değerlendirilmiştir. "
               "söz konusu çalışmaların sonuçları aşağıda özetlenmektedir. gereğini arz ederim.")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_lng002_comma_space(path: Path) -> None:
    """LNG-002: Virgül öncesi boşluk."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "Söz konusu durum ,ilgili birimlerle paylaşılmıştır.")
    _body(doc, "Raporlar ,tablolar ve ekler birlikte değerlendirilmelidir.")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_lng003_period_nospace(path: Path) -> None:
    """LNG-003: Noktadan sonra boşluk yok."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "Raporlar tamamlanmıştır.Sonuçlar değerlendirilecektir.")
    _body(doc, "Tablolar hazırlanmıştır.İnceleme yapılacaktır.Gereğini bildiririz.")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_lng004_double_spaces(path: Path) -> None:
    """LNG-004: Art arda fazla boşluk."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "Akademik  takvim  kapsamında  gerçekleştirilen  etkinlikler  tamamlanmıştır.")
    _body(doc, "Söz  konusu  belgeler  ekte  sunulmaktadır.")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_language_combo(path: Path) -> None:
    """LNG-001/002/003/004 + CLS-002: Tüm dil hataları bir arada."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "raporlar hazırlanmıştır.tablolar  oluşturulmuştur.")  # LNG-001, LNG-003, LNG-004
    _body(doc, "Söz konusu durum ,birimlerle paylaşılmıştır.")        # LNG-002
    _body(doc, "Gerekli  evraklar  teslim  edilmiştir.")              # LNG-004
    _std_closing(doc, phrase="Saygılarımla arz ederim.")              # CLS-002
    _save(doc, path.name)


# ── SEM-002: Ek sayısı tutarsızlığı (Katman A deterministik) ─────────────────

def make_a_ek_count_too_few(path: Path) -> None:
    """SEM-002: Metinde '4 adet' denmiş, ekte 2 belge var."""
    doc = Document()
    _margins(doc)
    _std_header(doc, konu="Konu: Belge Teslimi")
    _body(doc, "Ekte sunulan 4 adet belgenin incelenerek gereğinin yapılmasını arz ederim.")
    _std_closing(doc)
    _para(doc, "")
    _para(doc, "EK:")
    _para(doc, "EK-1: Dilekçe")
    _para(doc, "EK-2: Nüfus Cüzdanı Fotokopisi")
    # (EK-3 ve EK-4 yok)
    _save(doc, path.name)


def make_a_ek_count_too_many(path: Path) -> None:
    """SEM-002: Metinde 'iki adet' denmiş, ekte 4 belge var."""
    doc = Document()
    _margins(doc)
    _std_header(doc, konu="Konu: Başvuru Belgesi Teslimi")
    _body(doc, "Başvuruya esas iki adet belge ekte sunulmaktadır.")
    _std_closing(doc)
    _para(doc, "")
    _para(doc, "EK:")
    _para(doc, "EK-1: Diploma")
    _para(doc, "EK-2: Transkript")
    _para(doc, "EK-3: Referans Mektubu")
    _para(doc, "EK-4: Kimlik Fotokopisi")
    _save(doc, path.name)


def make_a_sem006_repeated(path: Path) -> None:
    """SEM-006: Metin gövdesinde neredeyse aynı iki cümle (tekrar eden ifade)."""
    doc = Document()
    _margins(doc)
    _std_header(doc, konu="Konu: Toplantı Duyurusu")
    _body(doc, "Söz konusu değerlendirme toplantısı on beş Mayıs iki bin yirmi beş "
               "tarihinde yapılacaktır.")
    _body(doc, "Söz konusu değerlendirme toplantısı on beş Mayıs iki bin yirmi beş "
               "tarihinde yapılacaktır.")
    _std_closing(doc)
    _save(doc, path.name)


def make_a_ek_no_reference_in_text(path: Path) -> None:
    """SEM-002 (Layer C): Ek listesi var ama metin içinde atıf yok."""
    doc = Document()
    _margins(doc)
    _std_header(doc, konu="Konu: Akademik Takvim")
    _body(doc, "2025-2026 akademik yılı takvimi incelenmiştir. Gerekli güncellemeler yapılacaktır.")
    _body(doc, "Konuya ilişkin bilgilerin dikkate alınmasını arz ederim.")
    _std_closing(doc)
    _para(doc, "")
    _para(doc, "EK:")
    _para(doc, "EK-1: Akademik Takvim (2025-2026)")
    # Metinde "EK" veya "ekte" geçmiyor
    _save(doc, path.name)


# ═══════════════════════════════════════════════════════════════════════════════
# KATMAN B — RAG Destekli Kurallar
# ═══════════════════════════════════════════════════════════════════════════════

def make_b_hir001_bolum_rektor(path: Path) -> None:
    """HIR-001: Bölüm Başkanlığı → Rektörlüğe 'Rica ederim' kullanmış."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        birim="Bilgisayar Mühendisliği Bölümü",
        konu="Konu: Öğrenci Muafiyeti Talebi",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Öğrencimizin muafiyet talebine ilişkin bilgiler ekte sunulmaktadır.")
    _body(doc, "Değerlendirilerek gereğinin yapılmasını talep ederiz.")
    _std_closing(doc, phrase="Rica ederim.",
                 name="Prof. Dr. Kemal Arslan", title="Bölüm Başkanı")
    _save(doc, path.name)


def make_b_hir001_muhendislik_rektor(path: Path) -> None:
    """HIR-001: Mühendislik Fakültesi → Rektörlüğe 'Rica ederim' (açık hiyerarşi hatası)."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        birim="Mühendislik Fakültesi",
        konu="Konu: Sınav Takvimi Düzenlemesi",
        muhatap="Rektörlük Makamına,")
    _body(doc, "2025 güz dönemi sınav takvimi düzenlemelerine ilişkin talep Rektörlüğe iletilmektedir.")
    _std_closing(doc, phrase="Rica ederim.",
                 name="Prof. Dr. Ahmet Yılmaz", title="Dekan")
    _save(doc, path.name)


def make_b_hir002_rektor_a_yrd(path: Path) -> None:
    """HIR-002: Rektör Yardımcısı adına 'Rektör a.' kullanılmış."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        muhatap="Mühendislik Fakültesi Dekanlığına,",
        konu="Konu: Bütçe Ödeneği Bildirimi")
    _body(doc, "2025 yılı bütçe ödeneğine ilişkin bilgiler aşağıda sunulmaktadır.")
    _body(doc, "Gereği için bilgilerinize arz ederiz.")
    _para(doc, "")
    _para(doc, "Arz ederim.")
    _para(doc, "")
    _para(doc, "Prof. Dr. Zeynep Kaya")
    _para(doc, "Rektör a.")
    _para(doc, "Rektör Yardımcısı")
    _save(doc, path.name)


def make_b_hir003_ilgi_sirasi_yanlis(path: Path) -> None:
    """HIR-003: İlgi satırları ters tarih sıralaması (yeniden eskiye)."""
    doc = Document()
    _margins(doc)
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, "Mühendislik Fakültesi", bold=True)
    _sayi_tarih_row(doc, sayi_no="F.01.2-2025/099")
    _para(doc, "Konu: Personel Değişikliği")
    _para(doc, "")
    # İlgi satırları ters sırada (yeniden eskiye)
    _para(doc, "İlgi: a) Rektörlüğün 20.05.2025 tarih ve 055 sayılı yazısı.")
    _para(doc, "     b) Rektörlüğün 10.03.2025 tarih ve 021 sayılı yazısı.")
    _para(doc, "     c) Rektörlüğün 05.01.2025 tarih ve 003 sayılı yazısı.")
    _para(doc, "")
    _para(doc, "Rektörlük Makamına,")
    _para(doc, "")
    _body(doc, "İlgi yazılar doğrultusunda personel değişikliğine ilişkin bilgiler sunulmaktadır.")
    _std_closing(doc)
    _save(doc, path.name)


def make_b_hir003_ilgi_sirasi_dogru(path: Path) -> None:
    """HIR-003 (false positive): İlgi satırları doğru kronolojik sırada."""
    doc = Document()
    _margins(doc)
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, "Mühendislik Fakültesi", bold=True)
    _sayi_tarih_row(doc, sayi_no="F.01.2-2025/100")
    _para(doc, "Konu: Bölüm Kontenjan Düzenlemesi")
    _para(doc, "")
    # İlgi satırları doğru sırada (eskiden yeniye)
    _para(doc, "İlgi: a) Rektörlüğün 05.01.2025 tarih ve 003 sayılı yazısı.")
    _para(doc, "     b) Rektörlüğün 10.03.2025 tarih ve 021 sayılı yazısı.")
    _para(doc, "     c) Rektörlüğün 20.05.2025 tarih ve 055 sayılı yazısı.")
    _para(doc, "")
    _para(doc, "Rektörlük Makamına,")
    _para(doc, "")
    _body(doc, "İlgi yazılar çerçevesinde bölüm kontenjanları düzenlenmiştir.")
    _std_closing(doc)
    _save(doc, path.name)


def make_b_hir004_dagitim_no_split(path: Path) -> None:
    """HIR-004: Dağıtım bölümünde Gereği/Bilgi ayrımı yapılmamış."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        konu="Konu: Akademik Takvim Duyurusu",
        muhatap="Tüm Fakülte Dekanlıklarına,")
    _body(doc, "2025-2026 akademik yılı takvimi aşağıda sunulmaktadır. "
               "Tüm birimlerin takvimleri buna göre düzenlemesi gerekmektedir.")
    _std_closing(doc, phrase="Rica ederim.",
                 name="Prof. Dr. Mehmet Demir", title="Rektör")
    _para(doc, "")
    _para(doc, "DAĞITIM:")
    _para(doc, "Mühendislik Fakültesi Dekanlığına")
    _para(doc, "Temel Bilimler Fakültesi Dekanlığına")
    _para(doc, "Mimarlık Fakültesi Dekanlığına")
    _para(doc, "İşletme Fakültesi Dekanlığına")
    # Gereği/Bilgi ayrımı YOK
    _save(doc, path.name)


def make_b_hir004_dagitim_with_split(path: Path) -> None:
    """HIR-004 (false positive): Dağıtım bölümünde Gereği/Bilgi ayrımı var."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        konu="Konu: Personel Bilgilendirmesi",
        muhatap="İlgili Birimlere,")
    _body(doc, "Personel yönetmeliğinde yapılan değişiklikler ilgili birimlere duyurulmaktadır.")
    _std_closing(doc, phrase="Rica ederim.",
                 name="Prof. Dr. Mehmet Demir", title="Rektör")
    _para(doc, "")
    _para(doc, "DAĞITIM:")
    _para(doc, "Gereği:")
    _para(doc, "  Personel Dairesi Başkanlığına")
    _para(doc, "  İdari ve Mali İşler Daire Başkanlığına")
    _para(doc, "Bilgi:")
    _para(doc, "  Tüm Fakülte Dekanlıklarına")
    _save(doc, path.name)


def make_b_hir005_bolum_rektor_direct(path: Path) -> None:
    """HIR-005: Bölüm → Rektörlük doğrudan (Dekanlık atlanmış)."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        birim="Bilgisayar Mühendisliği Bölümü",
        konu="Konu: Araştırma Laboratuvarı Talebi",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Bölümümüz araştırma laboratuvarı kurulması için gerekli olan ekipman listesi "
               "hazırlanmış olup bütçe onayı için Rektörlüğe arz edilmektedir.")
    _body(doc, "Gereğini saygılarımla arz ederim.")
    _std_closing(doc, phrase="Arz ederim.",
                 name="Prof. Dr. Selin Yıldız", title="Bölüm Başkanı")
    _save(doc, path.name)


def make_b_correct_upward(path: Path) -> None:
    """Layer B doğru: Fakülte → Rektörlük, 'Arz ederim' (hata yok)."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        birim="Mühendislik Fakültesi",
        konu="Konu: Yıllık Faaliyet Raporu",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Fakültemiz 2024-2025 yılı faaliyet raporu hazırlanarak ekte sunulmaktadır.")
    _body(doc, "Bilgilerinize arz ederim.")
    _std_closing(doc)
    _para(doc, "")
    _para(doc, "EK:")
    _para(doc, "EK-1: Faaliyet Raporu (24 sayfa)")
    _save(doc, path.name)


def make_b_correct_downward(path: Path) -> None:
    """Layer B doğru: Rektörlük → Fakülte, 'Rica ederim' (hata yok)."""
    doc = Document()
    _margins(doc)
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _sayi_tarih_row(doc, sayi_no="R.01.1-2025/200")
    _para(doc, "Konu: Akreditasyon Belgeleri")
    _para(doc, "")
    _para(doc, "Mühendislik Fakültesi Dekanlığına,")
    _para(doc, "")
    _body(doc, "Akreditasyon sürecine ilişkin belgeler hazırlanarak Dekanlığınıza gönderilmektedir.")
    _body(doc, "Gereğini rica ederim.")
    _para(doc, "")
    _para(doc, "Rica ederim.")
    _para(doc, "")
    _para(doc, "Prof. Dr. Mehmet Demir")
    _para(doc, "Rektör")
    _save(doc, path.name)


# ═══════════════════════════════════════════════════════════════════════════════
# KATMAN C — LLM Semantik Analiz Senaryoları
# ═══════════════════════════════════════════════════════════════════════════════

def make_c_sem001_strong_mismatch(path: Path) -> None:
    """SEM-001 (güçlü): Konu 'Burs Başvurusu', metin tamamen farklı konuda (inşaat ihalesi)."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        konu="Konu: Burs Başvurusu Değerlendirmesi",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Kampüs içi yemekhane binasının tadilat ihalesi kapsamında alınan teklifler "
               "incelenmiş olup en uygun fiyatı sunan firma belirlenmiştir. "
               "İhale süreci yürürlükteki kamu ihale mevzuatı çerçevesinde yürütülmüştür.")
    _body(doc, "İnşaat çalışmalarının Eylül 2025 itibarıyla tamamlanması planlanmaktadır. "
               "Yapım sözleşmesinin imzalanması için gerekli onayın verilmesini arz ederim.")
    _std_closing(doc)
    _save(doc, path.name)


def make_c_sem001_vague_konu(path: Path) -> None:
    """SEM-001 (muğlak konu): Konu satırı 'Hk.' ile bitmiş, anlamsız."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        konu="Konu: Bilgi Hk.",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Fakültemiz Bilgisayar Mühendisliği Bölümü 2024-2025 akademik yılında "
               "toplam 45 mezun vermiştir. Mezunların %78'i mezuniyetten itibaren 6 ay "
               "içinde işe başlamıştır. Endüstri işbirliği projeleri sayısı bir önceki "
               "yıla kıyasla %35 artmıştır.")
    _body(doc, "Söz konusu başarı göstergelerinin değerlendirilmesini arz ederim.")
    _std_closing(doc)
    _save(doc, path.name)


def make_c_sem003_ic_celisik(path: Path) -> None:
    """SEM-003: Metin içinde iç çelişki (önce var, sonra yok diyor)."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        konu="Konu: Proje Onayı",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Bölümümüz akademik kadrosunun tamamı söz konusu projeyi desteklemektedir. "
               "Proje önerisi geçen ay oybirliği ile kabul edilmiştir.")
    _body(doc, "Ne var ki bölüm akademisyenlerinin büyük çoğunluğu bu projeye karşı olduğunu "
               "bildirmiş; önerinin reddedilmesini talep etmiştir. Bölüm kurulu henüz "
               "bu konuda resmi bir karar almamıştır.")
    _body(doc, "Proje onayının verilmesini arz ederim.")
    _std_closing(doc)
    _save(doc, path.name)


def make_c_sem003_belirsiz_atif(path: Path) -> None:
    """SEM-003: Belirsiz gönderme — 'o', 'bu', 'söz konusu' neye atıfta bulunduğu belirsiz."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        konu="Konu: Başvuru Sonucu",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Bu konuda gerekli işlemler yapılmıştır. O da incelenmiş ve uygun bulunmuştur. "
               "Söz konusu durum değerlendirildiğinde, bunun yapılması zorunlu görülmektedir. "
               "Bu nedenle o şekilde işlem yapılmasını arz ederiz.")
    _body(doc, "Gereğini bilgilerinize arz ederim.")
    _std_closing(doc)
    _save(doc, path.name)


def make_c_sem003_muhatap_uyumsuz(path: Path) -> None:
    """SEM-003: Muhatap-içerik uyumsuzluğu — Rektörlüğe yazılmış ama Dekana hitap ediyor."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        konu="Konu: Bölüm Başkanlığı Görevi",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Sayın Dekan,")
    _body(doc, "Bölüm başkanlığı görevine atanmak istediğimizi belirtmek isterim. "
               "Sizin de bildiğiniz üzere, Dekan Bey, bölümümüzdeki akademik kadro "
               "eksikliği ciddi sorunlara yol açmaktadır.")
    _body(doc, "Bu talebin Dekan tarafından değerlendirilmesini arz ederim.")
    _std_closing(doc)
    _save(doc, path.name)


def make_c_sem004_anlatim_bozuklugu(path: Path) -> None:
    """SEM-004: Anlatım bozuklukları — özne-yüklem uyumsuzluğu, sarkık cümleler."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        konu="Konu: Akademik Performans Raporu",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Öğrenciler ve öğretim üyeleri ile birlikte müfredat komisyonu "
               "toplantısı gerçekleştirilmiş ve kararlar alınmıştır.")
    _body(doc, "Bu durum değerlendirildiğinde öğrencilerin başarı oranlarının artması "
               "beklenmekte olup bölümümüzün söz konusu bu meselesini çözüme kavuşturması "
               "yönünde gerekli olan çalışmalar yapılmış bulunmaktadır.")
    _body(doc, "Raporun ve eklerin incelenmesi için gereği saygılarımla birlikte "
               "arz etmekle birlikte ilgi ve alaka göstereceklerine olan inancımla "
               "takdirlerinize sunmayı uygun bulmaktayım.")  # sarkık cümle
    _std_closing(doc)
    _save(doc, path.name)


def make_c_sem004_edilgen_belirsiz(path: Path) -> None:
    """SEM-004: Aşırı edilgen yapı ve anlam belirsizliği."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        konu="Konu: Proje Raporu Talebi",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Söz konusu proje raporu tarafımızca hazırlanmış olunmuştur. "
               "Gerekli belgelerin ilgili makamlarca tarafımıza gönderilmesi "
               "hususunda gereğinin yapılması arz olunur.")
    _body(doc, "Belirtilen belgeler tarafınızca tarafımıza iletilmesi durumunda "
               "işlemlerin tarafımızca yürütülmesi sağlanacak olup sonuçlar "
               "tarafınıza bildirilecektir.")
    _std_closing(doc)
    _save(doc, path.name)


def make_c_sem_all_correct(path: Path) -> None:
    """Katman C doğru: Konu-metin uyumlu, mantıksal, açık anlatım — SEM hatası yok."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        konu="Konu: 2025 Mezuniyet Töreni Organizasyonu",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Fakültemiz 2024-2025 akademik yılı mezuniyet töreni 20 Haziran 2025 "
               "Cuma günü saat 14.00'te üniversite konferans salonunda gerçekleştirilecektir.")
    _body(doc, "Törene 180 mezun öğrenci, aileleri ve davetliler katılacaktır. "
               "Organizasyon detayları ve teknik gereksinimler ekte sunulmaktadır.")
    _body(doc, "Tören programının onaylanmasını ve gerekli konferans salonunun "
               "tahsisinin yapılmasını arz ederim.")
    _std_closing(doc)
    _para(doc, "")
    _para(doc, "EK:")
    _para(doc, "EK-1: Tören Programı")
    _para(doc, "EK-2: Teknik Gereksinimler Listesi")
    _save(doc, path.name)


# ═══════════════════════════════════════════════════════════════════════════════
# MIX — Birden fazla katman / karmaşık senaryolar
# ═══════════════════════════════════════════════════════════════════════════════

def make_mix_fmt_and_hir(path: Path) -> None:
    """Mix: FMT-001 (yanlış font) + HIR-001 (yanlış kapanış) aynı belgede."""
    doc = Document()
    _margins(doc)
    _std_header(doc, muhatap="Rektörlük Makamına,")
    _body(doc, "Bölümümüz akademik kadro ihtiyacı hakkında bilgi sunulmaktadır.",
          font="Calibri", pt=11.0)
    _body(doc, "Yeni öğretim üyesi alımı için gerekli onayın verilmesini talep ederiz.",
          font="Calibri", pt=11.0)
    _std_closing(doc, phrase="Rica ederim.")  # HIR-001: üst makama Rica ederim
    _save(doc, path.name)


def make_mix_missing_fields_and_lang(path: Path) -> None:
    """Mix: FLD-001 (T.C. yok) + LNG-002 (virgül boşluğu) + CLS-002 (yasaklı kapanış)."""
    doc = Document()
    _margins(doc)
    # T.C. yok
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, "Mühendislik Fakültesi", bold=True)
    _sayi_tarih_row(doc, sayi_no="F.01.2-2025/099")
    _para(doc, "Konu: Etkinlik Duyurusu")
    _para(doc, "")
    _para(doc, "Rektörlük Makamına,")
    _para(doc, "")
    _body(doc, "Fakültemizde düzenlenen etkinlik ,tüm akademik personele duyurulmaktadır.")  # LNG-002
    _body(doc, "Katılım formu ,ekte sunulmuştur.")  # LNG-002
    _std_closing(doc, phrase="Saygılarımla arz ederim.")  # CLS-002
    _save(doc, path.name)


def make_mix_all_layers(path: Path) -> None:
    """Mix: 3 katmandan da hata — FMT-001, HIR-001, SEM-001."""
    doc = Document()
    _margins(doc, cm=2.54)  # FMT-002 de tetiklensin
    _std_header(doc,
        konu="Konu: Bütçe Onayı",  # Konu bütçe ama metin başka şey → SEM-001
        muhatap="Rektörlük Makamına,")
    _body(doc, "Bölümümüz öğrencilerinin kariyer gelişimi için mentorluk programı başlatılmıştır. "
               "Program kapsamında her öğrenciye bir akademisyen rehber atanmaktadır. "
               "İlk dönem katılımcı sayısı 85 olarak belirlenmiştir.",
          font="Calibri", pt=11.0)  # FMT-001
    _std_closing(doc, phrase="Rica ederim.")  # HIR-001
    _save(doc, path.name)


def make_mix_enstitü_rektor_correct(path: Path) -> None:
    """Mix doğru: Enstitü → Rektörlük, Arz ederim, doğru format — hata yok."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        birim="Lisansüstü Eğitim Enstitüsü",
        konu="Konu: Tez Savunma Takvimi",
        muhatap="Rektörlük Makamına,")
    _body(doc, "Enstitümüz 2025 yılı tez savunma takvimi hazırlanmış olup bilgilerinize "
               "arz edilmektedir. Takvim üç aylık dönemler halinde planlanmıştır.")
    _body(doc, "Onaylanması halinde takvim tüm ilgili birimlere duyurulacaktır.")
    _std_closing(doc,
        name="Prof. Dr. Fatih Yıldız",
        title="Enstitü Müdürü")
    _save(doc, path.name)


def make_mix_bolum_dekan_correct(path: Path) -> None:
    """Mix doğru: Bölüm → Dekanlık yazışması, 'Arz ederim' (üst makama doğru)."""
    doc = Document()
    _margins(doc)
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, "Bilgisayar Mühendisliği Bölümü", bold=True)
    _sayi_tarih_row(doc, sayi_no="B.02.1-2025/015")
    _para(doc, "Konu: Ders Programı Değişikliği")
    _para(doc, "")
    _para(doc, "Mühendislik Fakültesi Dekanlığına,")
    _para(doc, "")
    _body(doc, "2025-2026 güz dönemi ders programında yapılması planlanan değişiklikler "
               "Bölüm Kurulumuzca onaylanmıştır.")
    _body(doc, "Değişikliklerin Fakülte Kuruluna sunulmasını arz ederim.")
    _std_closing(doc,
        name="Prof. Dr. Kemal Arslan",
        title="Bölüm Başkanı")
    _save(doc, path.name)


def make_mix_rektorluk_daireye_correct(path: Path) -> None:
    """Mix doğru: Rektörlük → Daire Başkanlığı (alt makama 'Rica ederim')."""
    doc = Document()
    _margins(doc)
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _sayi_tarih_row(doc, sayi_no="R.01.1-2025/310")
    _para(doc, "Konu: Personel Listesi Talebi")
    _para(doc, "")
    _para(doc, "Personel Dairesi Başkanlığına,")
    _para(doc, "")
    _body(doc, "Akademik ve idari personele ait güncel liste 30 Mayıs 2025 tarihine kadar "
               "Rektörlüğümüze iletilmesi gerekmektedir.")
    _body(doc, "Gereğini rica ederim.")
    _para(doc, "")
    _para(doc, "Rica ederim.")
    _para(doc, "")
    _para(doc, "Prof. Dr. Mehmet Demir")
    _para(doc, "Rektör")
    _save(doc, path.name)


def make_mix_ilgili_ekli_complete(path: Path) -> None:
    """Mix: İlgi + Ek + Dağıtım bölümlerinin hepsini içeren tam belge (hata yok)."""
    doc = Document()
    _margins(doc)
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, "Mühendislik Fakültesi", bold=True)
    _sayi_tarih_row(doc, sayi_no="F.01.2-2025/150")
    _para(doc, "Konu: Akreditasyon Belgesi Talebi")
    _para(doc, "")
    _para(doc, "İlgi: a) Rektörlüğün 03.02.2025 tarih ve 012 sayılı yazısı.")
    _para(doc, "     b) Rektörlüğün 14.04.2025 tarih ve 043 sayılı yazısı.")
    _para(doc, "")
    _para(doc, "Rektörlük Makamına,")
    _para(doc, "")
    _body(doc, "İlgi yazılar uyarınca akreditasyon süreci başlatılmıştır. "
               "Süreçle ilgili 3 adet belge ekte sunulmaktadır.")
    _body(doc, "Belgelerin incelenerek gereğinin yapılmasını arz ederim.")
    _std_closing(doc)
    _para(doc, "")
    _para(doc, "EK:")
    _para(doc, "EK-1: Akreditasyon Başvuru Formu")
    _para(doc, "EK-2: Öz Değerlendirme Raporu")
    _para(doc, "EK-3: Destekleyici Belgeler")
    _para(doc, "")
    _para(doc, "DAĞITIM:")
    _para(doc, "Gereği:")
    _para(doc, "  Strateji Geliştirme Daire Başkanlığına")
    _para(doc, "Bilgi:")
    _para(doc, "  Tüm Bölüm Başkanlıklarına")
    _save(doc, path.name)


# ═══════════════════════════════════════════════════════════════════════════════
# TÜRKÇE ÇEKİM VARYASYONLARI — Kapanış ifadesi morfolojik testleri (EKSIK 5)
# ═══════════════════════════════════════════════════════════════════════════════
# Türkçe sondan eklemeli olduğundan kapanış ifadeleri tek kalıp değildir.
# Parser'ın "arz ederim" dışındaki çekimleri de kapanış sayması beklenir
# (aksi halde CLS-001 yanlış tetiklenir).

def make_infl_arz_edilmektedir(path: Path) -> None:
    """Çekim: 'Bilgilerinize arz edilmektedir.' — geçerli kapanış (CLS-001 yok)."""
    doc = Document()
    _margins(doc)
    _std_header(doc, birim="Mühendislik Fakültesi", muhatap="Rektörlük Makamına,")
    _body(doc, "Fakültemiz 2025 yılı faaliyet raporu hazırlanmış olup ekte sunulmaktadır.")
    _std_closing(doc, phrase="Bilgilerinize arz edilmektedir.")
    _save(doc, path.name)


def make_infl_arz_olunur(path: Path) -> None:
    """Çekim: 'Arz olunur.' — geçerli kapanış (CLS-001 yok)."""
    doc = Document()
    _margins(doc)
    _std_header(doc, birim="Mühendislik Fakültesi", muhatap="Rektörlük Makamına,")
    _body(doc, "Söz konusu talebe ilişkin değerlendirme tamamlanmıştır.")
    _std_closing(doc, phrase="Arz olunur.")
    _save(doc, path.name)


def make_infl_arz_ederiz(path: Path) -> None:
    """Çekim: 'Gereğini arz ederiz.' (çoğul) — geçerli kapanış (CLS-001 yok)."""
    doc = Document()
    _margins(doc)
    _std_header(doc, birim="Mühendislik Fakültesi", muhatap="Rektörlük Makamına,")
    _body(doc, "Bölümümüzün ek ödenek talebine ilişkin gerekçeler aşağıda sunulmuştur.")
    _std_closing(doc, phrase="Gereğini arz ederiz.")
    _save(doc, path.name)


def make_infl_rica_ederiz_wrong_hier(path: Path) -> None:
    """Çekim: 'Rica ederiz.' üst makama — geçerli kapanış (CLS-001 yok) ama HIR-001 tetiklenir."""
    doc = Document()
    _margins(doc)
    _std_header(doc, birim="Mühendislik Fakültesi", muhatap="Rektörlük Makamına,")
    _body(doc, "2025 güz dönemi sınav takvimi düzenlemelerine ilişkin talep iletilmektedir.")
    _std_closing(doc, phrase="Gereğini rica ederiz.",
                 name="Prof. Dr. Ahmet Yılmaz", title="Dekan")
    _save(doc, path.name)


# ═══════════════════════════════════════════════════════════════════════════════
# REFERANS BELGELER — Doğru format, false-positive kontrolü
# ═══════════════════════════════════════════════════════════════════════════════

def make_ok_arial_font(path: Path) -> None:
    """Arial 11pt ile yazılmış mükemmel belge (FMT-001 olmamalı)."""
    doc = Document()
    _margins(doc)
    _std_header(doc)
    _body(doc, "Fakültemiz 2024-2025 akademik yılı faaliyetleri hakkında gerekli bilgiler "
               "sunulmaktadır.", font="Arial", pt=11.0)
    _body(doc, "Söz konusu faaliyetlere ilişkin raporlar ekte yer almaktadır.",
          font="Arial", pt=11.0)
    _std_closing(doc)
    _para(doc, "")
    _para(doc, "EK:")
    _para(doc, "EK-1: Faaliyet Raporu")
    _save(doc, path.name)


def make_ok_enstitü_yazisi(path: Path) -> None:
    """Enstitü'den Rektörlüğe doğru yazı (tüm alanlar, doğru hiyerarşi)."""
    doc = Document()
    _margins(doc)
    _std_header(doc,
        birim="Lisansüstü Eğitim Enstitüsü",
        konu="Konu: Öğrenci Kabul Takvimi",
        muhatap="Rektörlük Makamına,")
    _body(doc, "2025-2026 güz dönemi lisansüstü öğrenci kabul takvimi hazırlanmıştır.")
    _body(doc, "Takvimin onaylanarak ilgili birimlere duyurulmasını arz ederim.")
    _std_closing(doc,
        name="Prof. Dr. Ali Kaya",
        title="Enstitü Müdürü")
    _save(doc, path.name)


def make_ok_daire_rektorluk(path: Path) -> None:
    """Daire Başkanlığı → Rektörlük doğru yazı."""
    doc = Document()
    _margins(doc)
    _center(doc, "T.C.", bold=True)
    _center(doc, "GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ", bold=True)
    _center(doc, "Personel Dairesi Başkanlığı", bold=True)
    _sayi_tarih_row(doc, sayi_no="P.01.3-2025/055")
    _para(doc, "Konu: Kadro Cetvelini Güncellemesi")
    _para(doc, "")
    _para(doc, "Rektörlük Makamına,")
    _para(doc, "")
    _body(doc, "Personel kadro cetveli güncellenerek Rektörlüğe arz edilmektedir.")
    _std_closing(doc,
        name="Mehmet Çelik",
        title="Daire Başkanı")
    _save(doc, path.name)


# ═══════════════════════════════════════════════════════════════════════════════
# Ana akış
# ═══════════════════════════════════════════════════════════════════════════════

COMPREHENSIVE_SPECS: list[tuple[str, str, callable]] = [
    # ── Katman A: Format ────────────────────────────────────────────────────
    ("a_fmt001_calibri.docx",           "FMT-001: Calibri 11pt",                         make_a_font_calibri),
    ("a_fmt001_arial_wrong_size.docx",  "FMT-001: Arial 12pt (11pt olmalı)",             make_a_font_arial_wrong_size),
    ("a_fmt001_tnr_wrong_size.docx",    "FMT-001: TNR 11pt (12pt olmalı)",               make_a_font_tnr_wrong_size),
    ("a_fmt001_mixed_fonts.docx",       "FMT-001: Karma font kullanımı",                 make_a_font_mixed),
    ("a_fmt002_margin_large.docx",      "FMT-002: 2.54 cm marj (Word varsayılan)",       make_a_margin_large),
    ("a_fmt002_margin_small.docx",      "FMT-002: 1.0 cm marj (çok dar)",               make_a_margin_small),
    # ── Katman A: Zorunlu alanlar ──────────────────────────────────────────
    ("a_fld001_missing_tc.docx",        "FLD-001: T.C. başlığı eksik",                   make_a_missing_tc),
    ("a_fld002_missing_university.docx","FLD-002: Üniversite adı eksik",                 make_a_missing_university),
    ("a_fld004_missing_sayi.docx",      "FLD-004: Sayı numarası eksik",                  make_a_missing_sayi),
    ("a_fld005_wrong_date_format.docx", "FLD-005: Yanlış tarih formatı",                 make_a_wrong_date_format),
    ("a_fld006_missing_konu.docx",      "FLD-006: Konu alanı eksik",                     make_a_missing_konu),
    ("a_fld007_missing_imza.docx",      "FLD-007: İmza bloğu eksik",                     make_a_missing_imza),
    ("a_fld_all_missing.docx",          "FLD-001..007: Tüm zorunlu alanlar eksik",       make_a_all_fields_missing),
    # ── Katman A: Kapanış ─────────────────────────────────────────────────
    ("a_cls001_no_closing.docx",        "CLS-001: Kapanış ifadesi yok",                  make_a_no_closing),
    ("a_cls002_saygila_arz.docx",       "CLS-002: 'Saygılarımla arz ederim'",            make_a_forbidden_closing_saygila),
    ("a_cls002_rica_olunur.docx",       "CLS-002: 'Rica olunur'",                        make_a_forbidden_closing_rica_olunur),
    ("a_cls003_uygundur.docx",          "CLS-003: 'Uygundur' (OLUR olmalı)",             make_a_onay_words_uygundur),
    # ── Katman A: Dil hataları ─────────────────────────────────────────────
    ("a_lng001_sentence_case.docx",     "LNG-001: Cümle başı küçük harf",                make_a_lng001_sentence_case),
    ("a_lng002_comma_space.docx",       "LNG-002: Virgül öncesi boşluk",                 make_a_lng002_comma_space),
    ("a_lng003_period_nospace.docx",    "LNG-003: Noktadan sonra boşluk yok",            make_a_lng003_period_nospace),
    ("a_lng004_double_spaces.docx",     "LNG-004: Art arda fazla boşluk",                make_a_lng004_double_spaces),
    ("a_lng_combo.docx",                "LNG-001/002/003/004 + CLS-002 kombine",         make_a_language_combo),
    # ── Katman A: Tutarlılık ──────────────────────────────────────────────
    ("a_sem002_ek_too_few.docx",        "SEM-002: Metinde 4 adet, ekte 2 var",           make_a_ek_count_too_few),
    ("a_sem002_ek_too_many.docx",       "SEM-002: Metinde iki adet, ekte 4 var",         make_a_ek_count_too_many),
    ("a_sem002_ek_no_ref.docx",         "SEM-002: Ek var ama metinde atıf yok (det. içerik)", make_a_ek_no_reference_in_text),
    ("a_sem006_repeated.docx",          "SEM-006: Tekrar eden ifade (det. içerik)",      make_a_sem006_repeated),
    # ── Katman B: Hiyerarşi ──────────────────────────────────────────────
    ("b_hir001_bolum_rektor.docx",      "HIR-001: Bölüm→Rektör 'Rica ederim'",           make_b_hir001_bolum_rektor),
    ("b_hir001_muhendislik_rektor.docx","HIR-001: Fakülte→Rektör 'Rica ederim'",         make_b_hir001_muhendislik_rektor),
    ("b_hir002_rektor_a_yrd.docx",      "HIR-002: Rektör Yardımcısı 'Rektör a.'",       make_b_hir002_rektor_a_yrd),
    ("b_hir003_ilgi_ters.docx",         "HIR-003: İlgi sıralaması ters (yeni→eski)",     make_b_hir003_ilgi_sirasi_yanlis),
    ("b_hir003_ilgi_dogru.docx",        "HIR-003 (FP): İlgi sıralaması doğru",           make_b_hir003_ilgi_sirasi_dogru),
    ("b_hir004_dagitim_no_split.docx",  "HIR-004: Dağıtım Gereği/Bilgi ayrımı yok",     make_b_hir004_dagitim_no_split),
    ("b_hir004_dagitim_with_split.docx","HIR-004 (FP): Dağıtım Gereği/Bilgi var",        make_b_hir004_dagitim_with_split),
    ("b_hir005_bolum_rektor.docx",      "HIR-005: Bölüm→Rektörlük hiyerarşi atlama",    make_b_hir005_bolum_rektor_direct),
    ("b_correct_upward.docx",           "B doğru: Fakülte→Rektör 'Arz ederim'",          make_b_correct_upward),
    ("b_correct_downward.docx",         "B doğru: Rektör→Fakülte 'Rica ederim'",          make_b_correct_downward),
    # ── Katman C: Semantik ───────────────────────────────────────────────
    ("c_sem001_strong_mismatch.docx",   "SEM-001: Güçlü konu-metin uyumsuzluğu",         make_c_sem001_strong_mismatch),
    ("c_sem001_vague_konu.docx",        "SEM-001: Muğlak konu satırı ('Bilgi Hk.')",     make_c_sem001_vague_konu),
    ("c_sem003_ic_celisik.docx",        "SEM-003: Metin iç çelişkisi",                   make_c_sem003_ic_celisik),
    ("c_sem003_belirsiz_atif.docx",     "SEM-003: Belirsiz zamir/gönderme",              make_c_sem003_belirsiz_atif),
    ("c_sem003_muhatap_uyumsuz.docx",   "SEM-003: Muhatap-içerik uyumsuzluğu",           make_c_sem003_muhatap_uyumsuz),
    ("c_sem004_anlatim_bozuk.docx",     "SEM-004: Sarkık cümle, özne-yüklem sorunu",     make_c_sem004_anlatim_bozuklugu),
    ("c_sem004_edilgen.docx",           "SEM-004: Aşırı edilgen, anlam belirsizliği",    make_c_sem004_edilgen_belirsiz),
    ("c_sem_correct.docx",              "C doğru: Semantik hata yok",                    make_c_sem_all_correct),
    # ── Mix: Çok katmanlı ────────────────────────────────────────────────
    ("mix_fmt_hir.docx",                "Mix: FMT-001 + HIR-001",                        make_mix_fmt_and_hir),
    ("mix_fld_lng_cls.docx",            "Mix: FLD-001 + LNG-002 + CLS-002",              make_mix_missing_fields_and_lang),
    ("mix_all_layers.docx",             "Mix: 3 katmandan hata (FMT+HIR+SEM)",           make_mix_all_layers),
    ("mix_enstitü_correct.docx",        "Mix doğru: Enstitü→Rektörlük tam belge",        make_mix_enstitü_rektor_correct),
    ("mix_bolum_dekan_correct.docx",    "Mix doğru: Bölüm→Dekanlık doğru yazı",          make_mix_bolum_dekan_correct),
    ("mix_rektorluk_daire_correct.docx","Mix doğru: Rektörlük→Daire alt makam",          make_mix_rektorluk_daireye_correct),
    ("mix_ilgili_ekli_complete.docx",   "Mix doğru: İlgi+Ek+Dağıtım tam belge",          make_mix_ilgili_ekli_complete),
    # ── Türkçe çekim varyasyonları (EKSIK 5) ──────────────────────────────
    ("infl_arz_edilmektedir.docx",      "Çekim: 'arz edilmektedir' geçerli kapanış",     make_infl_arz_edilmektedir),
    ("infl_arz_olunur.docx",            "Çekim: 'arz olunur' geçerli kapanış",           make_infl_arz_olunur),
    ("infl_arz_ederiz.docx",            "Çekim: 'arz ederiz' geçerli kapanış",           make_infl_arz_ederiz),
    ("infl_rica_ederiz_wrong.docx",     "Çekim: 'rica ederiz' üst makama → HIR-001",     make_infl_rica_ederiz_wrong_hier),
    # ── Referans belgeler ────────────────────────────────────────────────
    ("ok_arial_font.docx",              "OK: Arial 11pt doğru kullanım",                 make_ok_arial_font),
    ("ok_enstitü_yazisi.docx",          "OK: Enstitü tam ve doğru yazı",                 make_ok_enstitü_yazisi),
    ("ok_daire_rektorluk.docx",         "OK: Daire Başkanlığı→Rektörlük doğru",          make_ok_daire_rektorluk),
]


def create_comprehensive(output_dir: Path | None = None) -> Path:
    dest = output_dir or FIXTURES
    dest.mkdir(parents=True, exist_ok=True)

    print(f"{'='*65}")
    print(f"  Kapsamlı test belgeleri oluşturuluyor → {dest}")
    print(f"  Toplam: {len(COMPREHENSIVE_SPECS)} belge")
    print(f"{'='*65}")

    groups = {"a_": 0, "b_": 0, "c_": 0, "mix_": 0, "ok_": 0}
    errors = []

    for fname, desc, fn in COMPREHENSIVE_SPECS:
        try:
            fn(dest / fname)
            prefix = next((k for k in groups if fname.startswith(k)), "other")
            groups[prefix] = groups.get(prefix, 0) + 1
            print(f"  ✓ {fname:<45} {desc}")
        except Exception as exc:
            errors.append((fname, exc))
            print(f"  ✗ {fname:<45} HATA: {exc}")

    print(f"\n{'─'*65}")
    print(f"  Katman A (a_*):   {groups['a_']:>3} belge")
    print(f"  Katman B (b_*):   {groups['b_']:>3} belge")
    print(f"  Katman C (c_*):   {groups['c_']:>3} belge")
    print(f"  Mix (mix_*):      {groups['mix_']:>3} belge")
    print(f"  Referans (ok_*):  {groups['ok_']:>3} belge")
    print(f"  {'─'*30}")
    print(f"  TOPLAM:           {len(COMPREHENSIVE_SPECS):>3} belge")
    if errors:
        print(f"\n  ⚠ {len(errors)} hata:")
        for fname, exc in errors:
            print(f"    {fname}: {exc}")
    print(f"{'='*65}")
    return dest


if __name__ == "__main__":
    create_comprehensive()
