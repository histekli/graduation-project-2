"""
Belge Ayrıştırıcı (Document Parser)
.docx dosyalarından yapısal bilgi çıkarır:
- Paragrafları bölümlere ayırır (başlık, sayı/tarih, konu, metin, imza vb.)
- Font, boyut, hizalama bilgilerini toplar
- Marj bilgilerini okur
"""
from __future__ import annotations
import re
from pathlib import Path
from docx import Document
from docx.shared import Pt, Cm, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH

from app.models.finding import (
    ParsedDocument, ParsedParagraph, DocumentSection
)
from app.rules.hierarchy import FACULTIES, INSTITUTES, DEPARTMENTS


# ── Bölüm tespit kalıpları ──────────────────────────────────────────────
_RE_TC = re.compile(r"^\s*T\s*\.?\s*C\s*\.?\s*$", re.IGNORECASE)
_RE_UNIVERSITY = re.compile(
    r"GEBZE\s+TEKNİK\s+ÜNİVERSİTESİ\s+REKTÖRLÜĞÜ", re.IGNORECASE
)
_RE_SAYI = re.compile(r"^\s*Sayı\s*:", re.IGNORECASE)
_RE_TARIH = re.compile(r"\d{2}[./]\d{2}[./]\d{4}")
_RE_KONU = re.compile(r"^\s*Konu\s*:", re.IGNORECASE)
_RE_ILGI = re.compile(r"^\s*İlgi\s*:", re.IGNORECASE)
_RE_ILGI_ITEM = re.compile(r"^\s*[a-zçğıöşü]\)", re.IGNORECASE)
_RE_EK = re.compile(r"^\s*EK\s*:", re.IGNORECASE)
_RE_EK_ITEM = re.compile(r"^\s*EK[\s-]*\d", re.IGNORECASE)
_RE_DAGITIM = re.compile(r"^\s*DAĞITIM", re.IGNORECASE)
_RE_KAPANIS = re.compile(
    r"(Arz\s+ederim|Rica\s+ederim|Arz\s+ve\s+rica\s+ederim|"
    r"Bilgilerinize\s+arz\s+ederim|Gereğini\s+arz\s+ederim|"
    r"Gereğini\s+rica\s+ederim|Bilgilerinize\s+rica\s+ederim|"
    r"Takdirlerinize\s+arz\s+ederim|Uygun\s+görüşle\s+arz\s+ederim|"
    r"Rica\s+olunur|OLUR|Uygundur|Muvafıktır)",
    re.IGNORECASE,
)
_RE_REKTOR_A = re.compile(r"Rektör\s+a\.", re.IGNORECASE)
_RE_ONAY_WORDS = re.compile(r"\b(Onay|Uygundur|Muvafıktır)\b", re.IGNORECASE)

_KNOWN_UNITS = [*FACULTIES, *INSTITUTES, *DEPARTMENTS]
_KNOWN_UNITS_UPPER = [name.upper() for name in _KNOWN_UNITS]


def _matches_known_unit(text: str) -> bool:
    upper_text = text.upper()
    return any(unit in upper_text for unit in _KNOWN_UNITS_UPPER)


def _get_paragraph_font(para) -> tuple[str | None, float | None, bool | None]:
    """Paragraftaki baskın font adı, boyutu ve kalınlık durumunu döndürür."""
    fonts, sizes, bolds = [], [], []
    for run in para.runs:
        if run.font.name:
            fonts.append(run.font.name)
        if run.font.size:
            sizes.append(run.font.size.pt)
        if run.font.bold is not None:
            bolds.append(run.font.bold)
    
    font_name = max(set(fonts), key=fonts.count) if fonts else None
    font_size = max(set(sizes), key=sizes.count) if sizes else None
    is_bold = any(bolds) if bolds else None
    return font_name, font_size, is_bold


def _get_alignment_str(alignment) -> str | None:
    if alignment is None:
        return None
    mapping = {
        WD_ALIGN_PARAGRAPH.LEFT: "left",
        WD_ALIGN_PARAGRAPH.CENTER: "center",
        WD_ALIGN_PARAGRAPH.RIGHT: "right",
        WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
    }
    return mapping.get(alignment, str(alignment))


def _get_margins(doc: Document) -> dict | None:
    """Belgenin sayfa marjlarını cm cinsinden döndürür."""
    try:
        section = doc.sections[0]
        def emu_to_cm(val):
            if val is None:
                return None
            return round(val / 360000, 2)  # EMU → cm
        return {
            "top_cm": emu_to_cm(section.top_margin),
            "bottom_cm": emu_to_cm(section.bottom_margin),
            "left_cm": emu_to_cm(section.left_margin),
            "right_cm": emu_to_cm(section.right_margin),
        }
    except Exception:
        return None


def parse_docx(file_path: str | Path, original_filename: str | None = None) -> ParsedDocument:
    """
    .docx dosyasını ayrıştırır ve yapılandırılmış ParsedDocument döndürür.
    """
    doc = Document(str(file_path))
    filename = original_filename or Path(file_path).name

    parsed = ParsedDocument(filename=filename)
    parsed.page_margins = _get_margins(doc)
    
    all_fonts = set()
    all_sizes = set()
    paragraphs: list[ParsedParagraph] = []
    
    # ── İlk geçiş: paragrafları topla ──
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue
        
        font_name, font_size, is_bold = _get_paragraph_font(para)
        alignment = _get_alignment_str(para.alignment)
        is_centered = alignment == "center"
        
        if font_name:
            all_fonts.add(font_name)
        if font_size:
            all_sizes.add(font_size)
        
        pp = ParsedParagraph(
            index=i,
            text=text,
            font_name=font_name,
            font_size=font_size,
            is_bold=is_bold,
            is_centered=is_centered,
            alignment=alignment,
        )
        paragraphs.append(pp)
    
    parsed.fonts_used = sorted(all_fonts)
    parsed.font_sizes_used = sorted(all_sizes)
    
    # ── İkinci geçiş: bölüm tespiti ──
    current_section = DocumentSection.HEADER
    header_done = False
    sayi_tarih_done = False
    konu_done = False
    ilgi_active = False
    metin_started = False
    kapanis_done = False
    dagitim_active = False
    
    for pp in paragraphs:
        text = pp.text
        
        # T.C. başlığı
        if _RE_TC.match(text):
            pp.section = DocumentSection.HEADER
            parsed.has_tc_header = True
            continue
        
        # Üniversite adı
        if _RE_UNIVERSITY.search(text):
            pp.section = DocumentSection.HEADER
            parsed.has_university_name = True
            parsed.header_text = text
            continue
        
        # Birim adı (üniversite adından sonraki ortalanmış satır)
        if not header_done and pp.is_centered and not _RE_SAYI.match(text):
            if parsed.has_university_name and not parsed.unit_name:
                if not _RE_TC.match(text) and not _RE_UNIVERSITY.search(text):
                    pp.section = DocumentSection.HEADER
                    if _matches_known_unit(text):
                        parsed.unit_name = text
                    continue
        
        # Sayı satırı
        if _RE_SAYI.match(text):
            pp.section = DocumentSection.SAYI_TARIH
            parsed.sayi = text
            header_done = True
            sayi_tarih_done = True
            continue
        
        # Tarih (sayı satırında olmayıp ayrı satırda olabilir)
        if not sayi_tarih_done and _RE_TARIH.search(text) and len(text) < 30:
            pp.section = DocumentSection.SAYI_TARIH
            parsed.tarih = text
            continue
        
        # Konu
        if _RE_KONU.match(text):
            pp.section = DocumentSection.KONU
            parsed.konu = text
            konu_done = True
            header_done = True
            continue
        
        # Muhatap (konu'dan sonra, ilgi/metin'den önce)
        if konu_done and not metin_started and not ilgi_active:
            if not _RE_ILGI.match(text) and not _RE_EK.match(text):
                if parsed.muhatap is None and len(text) < 200:
                    pp.section = DocumentSection.MUHATAP
                    parsed.muhatap = text
                    continue
        
        # İlgi
        if _RE_ILGI.match(text):
            pp.section = DocumentSection.ILGI
            parsed.ilgi_list.append(text)
            ilgi_active = True
            continue
        
        if ilgi_active and _RE_ILGI_ITEM.match(text):
            pp.section = DocumentSection.ILGI
            parsed.ilgi_list.append(text)
            continue
        else:
            ilgi_active = False
        
        # Kapanış ifadesi — kısa paragraflar kapanış olarak kabul edilir (< 70 karakter)
        # Uzun paragrafların sonu "arz ederim" ile bitebilir ama bunlar metin gövdesidir
        if _RE_KAPANIS.search(text) and not kapanis_done and len(text) < 70:
            pp.section = DocumentSection.KAPANIS
            parsed.kapanis_phrase = text
            kapanis_done = True
            metin_started = False
            continue
        
        # Ek
        if _RE_EK.match(text) or _RE_EK_ITEM.match(text):
            pp.section = DocumentSection.EK
            parsed.ek_list.append(text)
            continue
        
        # Dağıtım başlığı ve alt satırları
        if _RE_DAGITIM.match(text):
            pp.section = DocumentSection.DAGITIM
            parsed.dagitim_list.append(text)
            dagitim_active = True
            continue

        if dagitim_active and not _RE_EK.match(text) and not _RE_EK_ITEM.match(text):
            # Dağıtım alt satırı (birim adları, Gereği/Bilgi başlıkları)
            pp.section = DocumentSection.DAGITIM
            parsed.dagitim_list.append(text)
            continue
        else:
            dagitim_active = False

        # İmza bloğu (kapanıştan sonra, ek'ten önce)
        if kapanis_done and not _RE_EK.match(text) and not _RE_DAGITIM.match(text):
            if len(text) < 150:
                pp.section = DocumentSection.IMZA
                if parsed.imza_block is None:
                    parsed.imza_block = text
                else:
                    parsed.imza_block += "\n" + text
                continue
        
        # Metin gövdesi (yukarıdaki hiçbir kalıba uymuyorsa)
        if header_done or konu_done:
            pp.section = DocumentSection.METIN
            parsed.metin_paragraphs.append(pp.index)
            metin_started = True
    
    # Tarih'i sayı satırından çıkar (eğer ayrı yoksa)
    if parsed.tarih is None and parsed.sayi:
        tarih_match = _RE_TARIH.search(parsed.sayi)
        if tarih_match:
            parsed.tarih = tarih_match.group(0)
    
    parsed.paragraphs = paragraphs
    return parsed
