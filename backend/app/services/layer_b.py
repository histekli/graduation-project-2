"""
Katman B — RAG Destekli Kuralsal Kontrol
Yönerge/yönetmelik chunk'larını kullanarak bağlamsal kural kontrolü yapar.
Her bulguya ilgili yönerge maddesi referansı ekler.
"""
from __future__ import annotations
from app.models.finding import (
    Finding, FindingLocation, Severity, Layer, ParsedDocument, DocumentSection
)
from app.rag.retriever import GuidelineRetriever
from app.rules.hierarchy import CLOSING_RULES, HIERARCHY
import re


class LayerB:
    """RAG destekli kuralsal kontrol motoru."""

    def __init__(self, retriever: GuidelineRetriever | None = None):
        self.retriever = retriever
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"B{self._counter:03d}"

    def run(self, doc: ParsedDocument) -> list[Finding]:
        """Tüm Katman B kurallarını çalıştırır."""
        if not self.retriever or not self.retriever.is_ready:
            return []

        self._counter = 0
        findings: list[Finding] = []

        findings.extend(self._check_kapanis_hierarchy(doc))   # HIR-001
        findings.extend(self._check_rektor_a_usage(doc))       # HIR-002
        findings.extend(self._check_ilgi_order(doc))           # HIR-003
        findings.extend(self._check_dagitim_section(doc))      # HIR-004
        findings.extend(self._check_muhatap_birim_uyumu(doc))  # HIR-005
        findings.extend(self._check_closing_enrichment(doc))

        return findings

    def _check_kapanis_hierarchy(self, doc: ParsedDocument) -> list[Finding]:
        """HIR-001: Kapanış ifadesinin gönderen-alıcı hiyerarşisine uygunluğunu kontrol eder."""
        findings = []
        if not doc.kapanis_phrase or not doc.muhatap:
            return findings

        phrase = doc.kapanis_phrase.strip().lower()
        muhatap_upper = doc.muhatap.upper()
        unit_upper = (doc.unit_name or "").upper()

        sender_is_lower = False
        if any(k in muhatap_upper for k in ["REKTÖRLÜK", "REKTÖR"]):
            sender_is_lower = True
        elif any(k in muhatap_upper for k in ["DEKANLIK", "DEKAN"]):
            if any(k in unit_upper for k in ["BÖLÜM", "ANABİLİM"]):
                sender_is_lower = True

        if sender_is_lower:
            is_arz = any(k in phrase for k in ["arz ederim", "arz ve rica"])
            if not is_arz and "rica ederim" in phrase:
                rag_results = self.retriever.search_by_rule(
                    "kapanış ifadesi arz ederim üst makam hiyerarşi"
                )
                ref_text = self._extract_reference(rag_results)
                findings.append(Finding(
                    id=self._next_id(),
                    layer=Layer.B,
                    severity=Severity.WARNING,
                    rule_code="HIR-001",
                    title="Kapanış-hiyerarşi uyumsuzluğu",
                    description=(
                        f"Üst makama ({doc.muhatap}) yazılan yazıda "
                        f"'{doc.kapanis_phrase}' kullanılmış. "
                        f"Üst makama 'Arz ederim' yazılmalıdır."
                    ),
                    expected="Arz ederim",
                    found=doc.kapanis_phrase,
                    reference=ref_text or "YÖ-0030 R5, Madde 5-e",
                    suggestion=(
                        "'Rica ederim' ifadesini 'Arz ederim' olarak değiştirin. "
                        "Üst makama yazılan yazılarda 'Arz ederim' kullanılır."
                    ),
                    confidence=0.85,
                ))

        return findings

    def _check_ilgi_order(self, doc: ParsedDocument) -> list[Finding]:
        """HIR-003: İlgi satırlarının tarih sırasına göre sıralandığını kontrol eder."""
        findings = []
        if len(doc.ilgi_list) < 2:
            return findings

        date_re = re.compile(r"(\d{2})[./](\d{2})[./](\d{4})")
        dates = []
        for item in doc.ilgi_list:
            m = date_re.search(item)
            if m:
                day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dates.append((year, month, day))

        if len(dates) < 2:
            return findings

        is_sorted = all(dates[i] <= dates[i + 1] for i in range(len(dates) - 1))
        if not is_sorted:
            rag_results = self.retriever.search_by_rule(
                "ilgi satırı tarih sıralaması kronolojik sıra"
            )
            ref_text = self._extract_reference(rag_results)
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.B,
                severity=Severity.WARNING,
                rule_code="HIR-003",
                title="İlgi sıralaması hatalı",
                description=(
                    "İlgi satırları kronolojik tarih sırasına göre dizilmemiş. "
                    "En eski tarihli yazı önce gelmelidir."
                ),
                reference=ref_text or "YÖ-0030 R5, Madde 6-c",
                suggestion="İlgi satırlarını en eski tarihten en yeniye doğru sıralayın.",
                confidence=0.90,
            ))

        return findings

    def _check_dagitim_section(self, doc: ParsedDocument) -> list[Finding]:
        """HIR-004: Dağıtım bölümünde Gereği/Bilgi ayrımının yapıldığını kontrol eder."""
        findings = []
        if len(doc.dagitim_list) < 2:
            return findings

        dagitim_text = " ".join(doc.dagitim_list).upper()
        has_geregi = "GEREĞİ" in dagitim_text or "GEREĞI" in dagitim_text
        has_bilgi = "BİLGİ" in dagitim_text or "BILGI" in dagitim_text

        if not has_geregi and not has_bilgi:
            rag_results = self.retriever.search_by_rule(
                "dağıtım bölümü gereği bilgi ayrımı resmi yazı"
            )
            ref_text = self._extract_reference(rag_results)
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.B,
                severity=Severity.INFO,
                rule_code="HIR-004",
                title="Dağıtım bölümünde Gereği/Bilgi ayrımı yapılmamış",
                description=(
                    f"Dağıtım bölümünde {len(doc.dagitim_list)} birim var ancak "
                    "'Gereği:' / 'Bilgi:' ayrımı yapılmamış."
                ),
                reference=ref_text or "YÖ-0030 R5, Madde 8",
                suggestion=(
                    "Dağıtım bölümünü 'Gereği:' ve 'Bilgi:' başlıklarıyla ikiye ayırın. "
                    "İşlem yapacak birimler 'Gereği', bilgi amaçlı gönderilecekler 'Bilgi' altına yazılır."
                ),
                confidence=0.75,
            ))

        return findings

    def _check_muhatap_birim_uyumu(self, doc: ParsedDocument) -> list[Finding]:
        """HIR-005: Muhatap ile gönderen birim arasındaki hiyerarşik ilişkiyi doğrular."""
        findings = []
        if not doc.muhatap:
            return findings

        muhatap_upper = doc.muhatap.upper()

        # unit_name bilinen birimler listesinden geliyor; standart dışı birimler için
        # HEADER paragraflarını da tara (ör. "Bilgisayar Mühendisliği Bölümü")
        if doc.unit_name:
            unit_upper = doc.unit_name.upper()
        else:
            unit_upper = " ".join(
                pp.text for pp in doc.paragraphs
                if pp.section.value == "header"
            ).upper()

        # Fakülte/Enstitü → Rektörlük (üst makam, normal)
        # Rektörlük → Fakülte/Enstitü (alt makam, normal)
        # Fakülte → Fakülte (aynı düzey, normal)
        # Bölüm → Rektörlük (atlamak hiyerarşiyi atlıyor olabilir)

        is_dept = any(k in unit_upper for k in ["BÖLÜM", "ANABİLİM", "BİLİM DALI"])
        goes_to_rector = any(k in muhatap_upper for k in ["REKTÖRLÜK", "REKTÖR"])

        if is_dept and goes_to_rector:
            rag_results = self.retriever.search_by_rule(
                "bölüm rektörlük doğrudan yazışma hiyerarşi dekanlık"
            )
            ref_text = self._extract_reference(rag_results)
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.B,
                severity=Severity.INFO,
                rule_code="HIR-005",
                title="Hiyerarşi atlama — Bölüm Rektörlüğe doğrudan yazıyor",
                description=(
                    f"'{doc.unit_name}' birimi doğrudan Rektörlüğe yazıyor. "
                    "Bölümler genellikle Dekanlık aracılığıyla yazışır."
                ),
                reference=ref_text or "YÖ-0030 R5, Madde 4-b",
                suggestion=(
                    "Rektörlüğe iletilmesi gereken yazılar için Dekanlık aracılığıyla "
                    "üst yazı yazılması değerlendirilebilir."
                ),
                confidence=0.70,
            ))

        return findings

    def _check_rektor_a_usage(self, doc: ParsedDocument) -> list[Finding]:
        """
        Yetki devri yazılarında 'Rektör a.' ibaresinin doğru kullanımını kontrol eder.
        İmza bloğunda "Rektör a." varsa: gönderen Rektör değilse doğru, Rektör ise yanlış.
        """
        findings = []
        if not doc.imza_block:
            return findings

        has_rektor_a = bool(re.search(r"Rektör\s+a\.", doc.imza_block, re.IGNORECASE))

        if has_rektor_a:
            # RAG'dan yetki devri kuralını getir
            rag_results = self.retriever.search_by_rule(
                "Rektör adına yetki devri imza yetkisi"
            )
            ref_text = self._extract_reference(rag_results)

            # Bilgilendirme: doğru kullanım
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.B,
                severity=Severity.INFO,
                rule_code="HIR-002",
                title="Yetki devri imzası tespit edildi",
                description=(
                    "İmza bloğunda 'Rektör a.' ibaresi bulundu. "
                    "Bu yazının Rektör adına imzalandığını gösterir."
                ),
                found="Rektör a.",
                reference=ref_text or "YÖ-0030 R5, Giden Yazılar bölümü",
                suggestion=(
                    "İmzalayanın adı-soyadı yazılıp altına 'Rektör a.' ibaresi, "
                    "onun altına da memuriyet unvanı yazılmalıdır."
                ),
                confidence=0.9,
            ))

        return findings

    def _check_closing_enrichment(self, doc: ParsedDocument) -> list[Finding]:
        """
        Kapanış ifadesini RAG ile zenginleştirerek ek bağlam sağlar.
        Yasaklı ifadeler için ilgili yönerge maddesini bulur.
        """
        findings = []
        if not doc.kapanis_phrase:
            return findings

        phrase = doc.kapanis_phrase.strip().lower()

        # Yasaklı ifade kontrolü (Katman A da yapıyor ama burada referans ekliyoruz)
        forbidden_matches = []
        for forbidden in CLOSING_RULES["forbidden"]:
            if forbidden.lower() in phrase:
                forbidden_matches.append(forbidden)

        if forbidden_matches:
            rag_results = self.retriever.search_by_rule(
                "yasaklı ifade onay uygundur olur standardizasyon"
            )
            ref_text = self._extract_reference(rag_results)
            # Katman A zaten hata veriyor, burada sadece referansla zenginleştir
            # Bu bulguyu eklemeyelim — duplicate olur

        return findings

    def _extract_reference(self, rag_results: list[dict], max_results: int = 2) -> str | None:
        """RAG sonuçlarından referans metni oluşturur."""
        if not rag_results:
            return None

        refs = []
        for res in rag_results[:max_results]:
            source = res["metadata"].get("source", "")
            section = res["metadata"].get("section", "")
            if source and section:
                refs.append(f"{source}, {section}")

        return "; ".join(refs) if refs else None
