"""Pydantic models for the document compliance checker."""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "error"      # Mutlaka düzeltilmeli
    WARNING = "warning"  # Düzeltilmesi önerilir
    INFO = "info"        # Stil önerisi


class Layer(str, Enum):
    A = "A"  # Deterministik kural motoru
    B = "B"  # RAG destekli kuralsal kontrol
    C = "C"  # Semantik/mantıksal analiz


class FindingLocation(BaseModel):
    paragraph: Optional[int] = None
    page: Optional[int] = None
    section: Optional[str] = None
    text_snippet: Optional[str] = None


class Finding(BaseModel):
    """Tek bir bulgu/hata."""
    id: str = Field(..., description="Benzersiz bulgu ID'si, ör: F001")
    layer: Layer
    severity: Severity
    rule_code: str = Field(..., description="Kural kodu, ör: FMT-001")
    title: str
    description: str
    expected: Optional[str] = None
    found: Optional[str] = None
    location: Optional[FindingLocation] = None
    reference: Optional[str] = Field(None, description="İlgili yönerge/yönetmelik maddesi")
    suggestion: Optional[str] = None
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class DocumentSection(str, Enum):
    HEADER = "header"          # T.C., Üniversite adı, birim
    SAYI_TARIH = "sayi_tarih"  # Sayı ve tarih satırı
    KONU = "konu"              # Konu satırı
    MUHATAP = "muhatap"        # Alıcı/muhatap
    ILGI = "ilgi"              # İlgi referansları
    METIN = "metin"            # Ana metin gövdesi
    KAPANIS = "kapanis"        # Arz ederim / Rica ederim
    IMZA = "imza"              # İmza bloğu
    EK = "ek"                  # Ekler
    DAGITIM = "dagitim"        # Dağıtım listesi
    ILETISIM = "iletisim"      # Alt bilgi (adres, tel, fax)
    UNKNOWN = "unknown"


class ParsedParagraph(BaseModel):
    """Ayrıştırılmış paragraf."""
    index: int
    text: str
    section: DocumentSection = DocumentSection.UNKNOWN
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    is_bold: Optional[bool] = None
    is_centered: Optional[bool] = None
    alignment: Optional[str] = None


class ParsedDocument(BaseModel):
    """Ayrıştırılmış belge."""
    filename: str
    paragraphs: list[ParsedParagraph] = []
    # Tespit edilen bölümler
    header_text: Optional[str] = None
    has_tc_header: bool = False
    has_university_name: bool = False
    unit_name: Optional[str] = None
    sayi: Optional[str] = None
    tarih: Optional[str] = None
    konu: Optional[str] = None
    muhatap: Optional[str] = None
    ilgi_list: list[str] = []
    metin_paragraphs: list[int] = []  # paragraf indeksleri
    kapanis_phrase: Optional[str] = None
    imza_block: Optional[str] = None
    ek_list: list[str] = []
    dagitim_list: list[str] = []
    # Biçim bilgileri
    fonts_used: list[str] = []
    font_sizes_used: list[float] = []
    page_margins: Optional[dict] = None


class AnalysisRequest(BaseModel):
    """API'ye gelen analiz isteği."""
    mode: str = "full"       # "full" | "format_only" | "content_only"
    priority: str = "all"    # "all" | "error" | "warning"


class AnalysisResult(BaseModel):
    """Analiz sonucu."""
    filename: str
    total_findings: int
    errors: int
    warnings: int
    infos: int
    findings: list[Finding]
    parsed_document: Optional[ParsedDocument] = None
