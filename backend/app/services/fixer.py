"""
Belge Düzeltici (Document Fixer)
Tespit edilen hataları python-docx ile otomatik olarak düzeltir.
Düzeltilemeyen hatalar için belgenin sonuna profesyonel bir rapor tablosu ekler.

Otomatik düzeltilebilen kurallar:
  FMT-001  Font → Times New Roman 12pt  (metin paragrafları; miras/tema fontları dahil)
  FMT-002  Marj → 1.5 cm               (üst / sol / sağ)
  LNG-001  Cümle başı büyük harf        (noktadan sonra gelen küçük harfler)
  LNG-002  Virgül öncesi boşluk kaldır
  LNG-003  Noktadan sonra boşluk ekle  (≥3 harfli kelimelerden sonra)
  LNG-004  Art arda fazla boşlukları temizle
  LNG-005  Virgül/noktalı virgülden sonra boşluk ekle
  CLS-002  Yasaklı kapanış ifadesi → standart ifadeyle değiştir
"""
from __future__ import annotations

import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.models.finding import DocumentSection, Finding, ParsedDocument, Severity

# ── Sabitler ──────────────────────────────────────────────────────────────────

_AUTO_FIXABLE = frozenset({"FMT-001", "FMT-002", "LNG-001", "LNG-002", "LNG-003", "LNG-004", "LNG-005", "CLS-002"})

# Türkçe özel büyük harf dönüşümü: Python .upper() 'i'→'I' yapar, Türkçe'de 'İ' olmalı
_TR_UPPER = str.maketrans("iı", "İI")

# Yasaklı kapanış → standart kapanış eşlemesi  (regex pattern → replacement)
# \.? at the end matches the trailing period that the parser stores with the phrase
_CLOSING_REPLACEMENTS: list[tuple[str, str]] = [
    (r"saygılarımla\s+arz\s+ederim\.?",          "Arz ederim."),
    (r"saygıyla\s+arz\s+ederim\.?",               "Arz ederim."),
    (r"derin\s+saygılarımla\s+arz\s+ederim\.?",   "Arz ederim."),
    (r"saygılarımla\s+rica\s+ederim\.?",          "Rica ederim."),
    (r"saygıyla\s+rica\s+ederim\.?",              "Rica ederim."),
    (r"\brica\s+olunur\.?\b",                      "Rica ederim."),
]

# Rapor tablosu renkleri (hex, '#' olmadan)
_C_HEADER  = "1E293B"   # koyu lacivert — başlık satırı
_C_FIXED   = "DCFCE7"   # açık yeşil   — otomatik düzeltildi
_C_ERROR   = "FEE2E2"   # açık kırmızı — hata
_C_WARNING = "FEF9C3"   # açık sarı    — uyarı
_C_INFO    = "DBEAFE"   # açık mavi    — bilgi
_C_WHITE   = "FFFFFF"

_SEV_LABEL = {
    Severity.ERROR:   "Hata",
    Severity.WARNING: "Uyarı",
    Severity.INFO:    "Bilgi",
}
_SEV_COLOR = {
    Severity.ERROR:   _C_ERROR,
    Severity.WARNING: _C_WARNING,
    Severity.INFO:    _C_INFO,
}

# Rapor tablosu sütun genişlikleri (toplam ≈ 14.5 cm)
_COL_WIDTHS = [Cm(1.8), Cm(1.5), Cm(3.0), Cm(4.6), Cm(3.6)]
_COL_HEADERS = ["Kural", "Önem", "Başlık", "Açıklama", "Öneri / Eylem"]


# ── Dönüş veri yapısı ─────────────────────────────────────────────────────────

class FixSummary(NamedTuple):
    fixed_path: Path
    auto_fixed_codes: list[str]    # gerçekten değişiklik yapılan kural kodları
    report_findings: list[Finding]  # rapor tablosuna eklenen bulgular


# ── Ana fonksiyon ─────────────────────────────────────────────────────────────

def fix_document(
    source_path: str | Path,
    parsed: ParsedDocument,
    findings: list[Finding],
) -> FixSummary:
    """
    Orijinal .docx'i düzeltir ve geçici bir dizine kaydeder.

    Döndürülen FixSummary.fixed_path dosyası kullanıcıya gönderildikten sonra
    caller tarafından temizlenmelidir (shutil.rmtree(fixed_path.parent)).
    """
    source_path = Path(source_path)
    tmp_dir = Path(tempfile.mkdtemp(prefix="doh_fix_"))
    fixed_path = tmp_dir / (source_path.stem + "_duzeltilmis.docx")
    shutil.copy2(source_path, fixed_path)

    doc = Document(str(fixed_path))

    fixable_codes = {f.rule_code for f in findings if f.rule_code in _AUTO_FIXABLE}
    report_findings = [f for f in findings if f.rule_code not in _AUTO_FIXABLE]

    auto_fixed_codes: list[str] = []

    # ── FMT-002: Marjlar ────────────────────────────────────────────────────
    if "FMT-002" in fixable_codes and _fix_margins(doc):
        auto_fixed_codes.append("FMT-002")

    # Bölüm metin setleri — indeks yerine metin içeriğiyle eşleştir
    # (parser boş paragrafları atlıyor; fixer'da aynı indeks her zaman hizalanmayabilir)
    metin_texts   = {pp.text for pp in parsed.paragraphs
                     if pp.index in set(parsed.metin_paragraphs)
                     or pp.section == DocumentSection.METIN}
    kapanis_texts = {pp.text for pp in parsed.paragraphs
                     if pp.section == DocumentSection.KAPANIS}

    # ── Paragraf bazlı düzeltmeler ──────────────────────────────────────────
    fmt001 = lng001 = lng002 = lng003 = lng004 = lng005 = cls002 = False

    for para in doc.paragraphs:
        stripped = para.text.strip()
        if not stripped:
            continue
        is_metin   = stripped in metin_texts
        is_kapanis = stripped in kapanis_texts
        if not (is_metin or is_kapanis):
            continue

        # LNG-001: Cümle başı büyük harf (paragraf düzeyinde, run sınırlarını korur)
        if "LNG-001" in fixable_codes and is_metin:
            if _fix_sentence_case_para(para):
                lng001 = True

        for run in para.runs:
            if not run.text:
                continue

            # FMT-001: Font → TNR 12pt (metin + kapanis; miras/tema override dahil)
            if "FMT-001" in fixable_codes and (is_metin or is_kapanis):
                if _fix_run_font(run):
                    fmt001 = True

            original = run.text

            # LNG-004: Art arda boşluk
            if "LNG-004" in fixable_codes:
                run.text = re.sub(r"  +", " ", run.text)
                if run.text != original:
                    lng004 = True
                    original = run.text

            # LNG-002: Virgül öncesi boşluk
            if "LNG-002" in fixable_codes:
                run.text = re.sub(r"\s+,", ",", run.text)
                if run.text != original:
                    lng002 = True
                    original = run.text

            # LNG-003: Noktadan sonra boşluk eksik (≥3 harf olan kelimelerden sonra)
            if "LNG-003" in fixable_codes:
                run.text = re.sub(
                    r"([A-ZÇĞİÖŞÜa-zçğıöşü]{3,})\.([A-ZÇĞİÖŞÜa-zçğıöşü])",
                    r"\1. \2",
                    run.text,
                )
                if run.text != original:
                    lng003 = True
                    original = run.text

            # LNG-005: Virgül/noktalı virgülden sonra boşluk eksik
            # Basit regex: [,;] hemen ardından harf geliyorsa boşluk ekle
            if "LNG-005" in fixable_codes:
                run.text = re.sub(
                    r"([,;])([A-ZÇĞİÖŞÜa-zçğıöşü])",
                    r"\1 \2",
                    run.text,
                )
                if run.text != original:
                    lng005 = True
                    original = run.text

            # CLS-002: Yasaklı kapanış ifadesi
            if "CLS-002" in fixable_codes and is_kapanis:
                new_text = _replace_forbidden_closing(run.text)
                if new_text != run.text:
                    run.text = new_text
                    cls002 = True

    if fmt001:
        auto_fixed_codes.append("FMT-001")
    if lng001:
        auto_fixed_codes.append("LNG-001")
    if lng004:
        auto_fixed_codes.append("LNG-004")
    if lng005:
        auto_fixed_codes.append("LNG-005")
    if lng003:
        auto_fixed_codes.append("LNG-003")
    if lng002:
        auto_fixed_codes.append("LNG-002")
    if cls002:
        auto_fixed_codes.append("CLS-002")
    elif "CLS-002" in fixable_codes:
        # Desen eşleşmedi → rapor tablosuna ekle
        report_findings.extend(f for f in findings if f.rule_code == "CLS-002")

    # ── Düzeltme raporu ekle ─────────────────────────────────────────────────
    _append_report(doc, parsed.filename, auto_fixed_codes, report_findings, findings)

    doc.save(str(fixed_path))
    return FixSummary(
        fixed_path=fixed_path,
        auto_fixed_codes=auto_fixed_codes,
        report_findings=report_findings,
    )


# ── Düzeltme yardımcıları ─────────────────────────────────────────────────────

def _fix_sentence_case_para(para) -> bool:
    """
    Paragraf içinde cümle başı büyük harf düzeltmesi.
    Run sınırlarını koruyarak karakter bazlı eşleştirme yapar.
    Türkçe 'i' → 'İ' dönüşümünü doğru uygular.
    """
    runs = para.runs
    if not runs:
        return False

    # Karakter → (run_idx, char_in_run) eşlemesi
    char_map: list[tuple[int, int]] = []
    for run_idx, run in enumerate(runs):
        for ci in range(len(run.text)):
            char_map.append((run_idx, ci))

    combined = "".join(r.text for r in runs)
    if not combined:
        return False

    # Noktadan (.!?) sonra gelen küçük harflerin konumlarını bul
    fix_positions: list[int] = []
    for m in re.finditer(r'(?<=[.!?])\s+([a-zçğıöşü])', combined):
        fix_positions.append(m.start(1))

    if not fix_positions:
        return False

    changed = False
    for pos in fix_positions:
        if pos >= len(char_map):
            continue
        run_idx, ci = char_map[pos]
        run = runs[run_idx]
        text = list(run.text)
        upper_char = text[ci].upper().translate(_TR_UPPER)
        if upper_char != text[ci]:
            text[ci] = upper_char
            run.text = "".join(text)
            changed = True

    return changed


def _fix_margins(doc: Document) -> bool:
    """Tüm bölümlerin marjlarını 1.5 cm'ye çeker. Değişiklik olursa True döner."""
    target = Cm(1.5)
    tol    = Cm(0.15)
    changed = False
    for sec in doc.sections:
        if abs((sec.top_margin   or 0) - target) > tol:
            sec.top_margin   = target; changed = True
        if abs((sec.left_margin  or 0) - target) > tol:
            sec.left_margin  = target; changed = True
        if abs((sec.right_margin or 0) - target) > tol:
            sec.right_margin = target; changed = True
    return changed


def _fix_run_font(run) -> bool:
    """
    Run fontunu Times New Roman 12pt olarak ayarlar.
    None (tema/miras) fontları da dahil — explicit TNR 12pt ile override edilir.
    """
    allowed = {"Times New Roman", "Arial"}
    name = run.font.name
    size = run.font.size.pt if run.font.size else None
    changed = False

    # None → miras/tema font; yanlış olabilir, explicit TNR ile ezeriz
    if name is None or name not in allowed:
        run.font.name = "Times New Roman"
        run.font.size = Pt(12)
        changed = True
    elif name == "Times New Roman" and size and abs(size - 12.0) > 0.5:
        run.font.size = Pt(12)
        changed = True
    elif name == "Arial" and size and abs(size - 11.0) > 0.5:
        run.font.size = Pt(11)
        changed = True
    return changed


def _replace_forbidden_closing(text: str) -> str:
    """Yasaklı kapanış ifadesini standart ifadeyle değiştirir."""
    for pattern, replacement in _CLOSING_REPLACEMENTS:
        new = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        if new != text:
            return new
    return text


# ── Düzeltme raporu ───────────────────────────────────────────────────────────

def _append_report(
    doc: Document,
    filename: str,
    auto_fixed_codes: list[str],
    report_findings: list[Finding],
    all_findings: list[Finding],
) -> None:
    """Belge sonuna sayfa sonu + Düzeltme Raporu tablosu ekler."""
    doc.add_page_break()

    # ── Başlık ────────────────────────────────────────────────────────────
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = h.add_run("UYUM DENETİM RAPORU")
    r.bold = True
    r.font.size = Pt(14)
    r.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    # Meta satırı
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    mr = meta.add_run(
        f"Dosya: {filename}   ·   "
        f"Oluşturulma: {datetime.now().strftime('%d.%m.%Y %H:%M')}   ·   "
        f"Toplam bulgu: {len(all_findings)}"
    )
    mr.font.size = Pt(9)
    mr.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
    mr.italic = True

    doc.add_paragraph()  # boşluk

    # ── Otomatik düzeltmeler özeti ─────────────────────────────────────────
    sh = doc.add_paragraph()
    sr = sh.add_run("Otomatik Uygulanan Düzeltmeler")
    sr.bold = True
    sr.font.size = Pt(11)

    if auto_fixed_codes:
        fixed_map: dict[str, list[Finding]] = {}
        for f in all_findings:
            if f.rule_code in auto_fixed_codes:
                fixed_map.setdefault(f.rule_code, []).append(f)

        for code in auto_fixed_codes:
            flist = fixed_map.get(code, [])
            label = flist[0].title if flist else code
            p = doc.add_paragraph(style="List Bullet")
            run_code = p.add_run(f"[{code}]  ")
            run_code.bold = True
            run_code.font.color.rgb = RGBColor(0x16, 0xA3, 0x4A)
            run_label = p.add_run(label)
            run_label.font.color.rgb = RGBColor(0x16, 0xA3, 0x4A)
    else:
        p = doc.add_paragraph()
        r2 = p.add_run("Otomatik düzeltilebilecek hata tespit edilmedi.")
        r2.font.size = Pt(10)
        r2.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    doc.add_paragraph()  # boşluk

    # ── Manuel düzeltme tablosu ────────────────────────────────────────────
    mh = doc.add_paragraph()
    mr2 = mh.add_run("Manuel Düzeltme Gerektiren Sorunlar")
    mr2.bold = True
    mr2.font.size = Pt(11)

    if report_findings:
        table = doc.add_table(rows=1, cols=len(_COL_HEADERS))
        _add_table_borders(table)

        # Başlık satırı
        hdr_row = table.rows[0]
        for cell, hdr in zip(hdr_row.cells, _COL_HEADERS):
            _set_cell_bg(cell, _C_HEADER)
            p2 = cell.paragraphs[0]
            rr = p2.add_run(hdr)
            rr.bold = True
            rr.font.size = Pt(9)
            rr.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

        # Veri satırları
        for finding in report_findings:
            row = table.add_row()
            bg = _SEV_COLOR.get(finding.severity, _C_WHITE)
            values = [
                finding.rule_code,
                _SEV_LABEL.get(finding.severity, str(finding.severity)),
                finding.title,
                finding.description,
                finding.suggestion or "—",
            ]
            for cell, val in zip(row.cells, values):
                _set_cell_bg(cell, bg)
                p3 = cell.paragraphs[0]
                rv = p3.add_run(val)
                rv.font.size = Pt(8)

        # Sütun genişlikleri
        for row in table.rows:
            for cell, w in zip(row.cells, _COL_WIDTHS):
                cell.width = w
    else:
        p = doc.add_paragraph()
        r3 = p.add_run("Tüm tespit edilen sorunlar otomatik olarak düzeltildi.")
        r3.font.color.rgb = RGBColor(0x16, 0xA3, 0x4A)
        r3.font.size = Pt(10)

    # Alt not
    doc.add_paragraph()
    foot = doc.add_paragraph()
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fr = foot.add_run(
        "Bu rapor Dekanlık Yazışma Uyum Denetleyicisi tarafından otomatik oluşturulmuştur. "
        "Manuel düzeltmeler için ilgili yönerge ve yönetmelik maddelerine başvurunuz."
    )
    fr.font.size = Pt(8)
    fr.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)
    fr.italic = True


# ── XML yardımcıları ──────────────────────────────────────────────────────────

def _set_cell_bg(cell, hex_color: str) -> None:
    """Hücre arka plan rengini XML üzerinden ayarlar."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  hex_color)
    tcPr.append(shd)


def _add_table_borders(table) -> None:
    """Tabloya ince çizgi kenarlık ekler."""
    tbl  = table._tbl
    tblPr = tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)

    existing = tblPr.find(qn("w:tblBorders"))
    if existing is not None:
        tblPr.remove(existing)

    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"),   "single")
        el.set(qn("w:sz"),    "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "94A3B8")
        borders.append(el)
    tblPr.append(borders)
