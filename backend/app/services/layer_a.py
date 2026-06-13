"""
Katman A — Deterministik Kural Motoru
Kesin, ölçülebilir kuralları regex ve yapısal analiz ile kontrol eder.
Yüksek precision, sıfır hallüsinasyon.
"""
from __future__ import annotations
import re
from app.models.finding import (
    Finding, FindingLocation, Severity, Layer, ParsedDocument, DocumentSection
)
from app.rules.hierarchy import CLOSING_RULES


class LayerA:
    """Deterministik kural motoru. Her kural metodu bir veya daha fazla Finding döndürür."""

    def __init__(self):
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"A{self._counter:03d}"

    def run(self, doc: ParsedDocument) -> list[Finding]:
        """Tüm Katman A kurallarını çalıştırır."""
        findings: list[Finding] = []
        self._counter = 0

        # ── Biçim kuralları ──
        findings.extend(self._check_fonts(doc))
        findings.extend(self._check_margins(doc))

        # ── Zorunlu alan kuralları ──
        findings.extend(self._check_tc_header(doc))
        findings.extend(self._check_university_name(doc))
        findings.extend(self._check_unit_name(doc))
        findings.extend(self._check_sayi(doc))
        findings.extend(self._check_tarih(doc))
        findings.extend(self._check_konu(doc))
        findings.extend(self._check_imza_block(doc))

        # ── Kapanış ifadesi kuralları ──
        findings.extend(self._check_kapanis(doc))
        findings.extend(self._check_onay_words(doc))

        # ── Tutarlılık kuralları (deterministik) ──
        findings.extend(self._check_ek_count(doc))

        # ── Dil/yazım kuralları ──
        findings.extend(self._check_language(doc))

        return findings

    # ═══════════════════════════════════════════════════════════════
    # BİÇİM KURALLARI
    # ═══════════════════════════════════════════════════════════════

    def _check_fonts(self, doc: ParsedDocument) -> list[Finding]:
        """Yönetmelik Madde 7: Times New Roman 12pt veya Arial 11pt."""
        findings = []
        allowed = {
            ("Times New Roman", 12.0),
            ("Arial", 11.0),
        }
        # Başlıklar farklı olabilir, sadece metin paragraflarını kontrol et
        for pp in doc.paragraphs:
            if pp.section not in (DocumentSection.METIN, DocumentSection.KAPANIS):
                continue
            if pp.font_name and pp.font_size:
                if (pp.font_name, pp.font_size) not in allowed:
                    findings.append(Finding(
                        id=self._next_id(),
                        layer=Layer.A,
                        severity=Severity.ERROR,
                        rule_code="FMT-001",
                        title="Yanlış font kullanımı",
                        description=(
                            f"Metin paragrafında '{pp.font_name} {pp.font_size}pt' "
                            f"kullanılmış."
                        ),
                        expected="Times New Roman 12pt veya Arial 11pt",
                        found=f"{pp.font_name} {pp.font_size}pt",
                        location=FindingLocation(
                            paragraph=pp.index,
                            section=pp.section.value,
                            text_snippet=pp.text[:80],
                        ),
                        reference="Yönetmelik Madde 7; YÖ-0030 R5",
                        suggestion="Font türünü ve boyutunu düzeltin.",
                    ))
        # Birden fazla aynı hata varsa özetle
        if len(findings) > 3:
            summary = Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.ERROR,
                rule_code="FMT-001",
                title="Yaygın font hatası",
                description=(
                    f"Belgede {len(findings)} paragrafta yanlış font tespit edildi. "
                    f"Kullanılan fontlar: {', '.join(doc.fonts_used)}"
                ),
                expected="Times New Roman 12pt veya Arial 11pt",
                found=", ".join(doc.fonts_used),
                reference="Yönetmelik Madde 7; YÖ-0030 R5",
                suggestion="Tüm metin gövdesinin fontunu düzeltin.",
            )
            return [summary]
        return findings

    def _check_margins(self, doc: ParsedDocument) -> list[Finding]:
        """Yönetmelik Madde 8: 1.5 cm üst, sol, sağ marj."""
        findings = []
        if doc.page_margins is None:
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.INFO,
                rule_code="FMT-002",
                title="Marj bilgisi okunamadı",
                description="Belgenin sayfa marjları okunamadı.",
                reference="Yönetmelik Madde 8",
                suggestion="Belgenin marj ayarlarını manuel kontrol edin.",
                confidence=0.5,
            ))
            return findings

        margins = doc.page_margins
        expected_cm = 1.5
        tolerance = 0.15  # ±0.15 cm tolerans

        checks = [
            ("top_cm", "Üst marj"),
            ("left_cm", "Sol marj"),
            ("right_cm", "Sağ marj"),
        ]

        for key, label in checks:
            val = margins.get(key)
            if val is not None and abs(val - expected_cm) > tolerance:
                findings.append(Finding(
                    id=self._next_id(),
                    layer=Layer.A,
                    severity=Severity.WARNING,
                    rule_code="FMT-002",
                    title=f"Yanlış {label.lower()}",
                    description=f"{label} {val} cm olarak ayarlanmış.",
                    expected=f"{expected_cm} cm",
                    found=f"{val} cm",
                    reference="Yönetmelik Madde 8",
                    suggestion=f"{label}'ı {expected_cm} cm olarak ayarlayın.",
                ))
        return findings

    # ═══════════════════════════════════════════════════════════════
    # ZORUNLU ALAN KURALLARI
    # ═══════════════════════════════════════════════════════════════

    def _check_tc_header(self, doc: ParsedDocument) -> list[Finding]:
        """Belgenin ilk satırında 'T.C.' olmalı."""
        if not doc.has_tc_header:
            return [Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.ERROR,
                rule_code="FLD-001",
                title="'T.C.' başlığı eksik",
                description="Belgenin ilk satırında 'T.C.' ibaresi bulunamadı.",
                expected="T.C.",
                reference="YÖ-0030 R5, Dördüncü Bölüm Madde 4",
                suggestion="Belgenin en üstüne 'T.C.' ekleyin.",
            )]
        return []

    def _check_university_name(self, doc: ParsedDocument) -> list[Finding]:
        """'GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ' satırı olmalı."""
        if not doc.has_university_name:
            return [Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.ERROR,
                rule_code="FLD-002",
                title="Üniversite adı eksik",
                description=(
                    "'GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ' ibaresi bulunamadı."
                ),
                expected="GEBZE TEKNİK ÜNİVERSİTESİ REKTÖRLÜĞÜ",
                reference="YÖ-0030 R5, Dördüncü Bölüm Madde 4",
                suggestion="İkinci satıra üniversite adını ekleyin.",
            )]
        return []

    def _check_unit_name(self, doc: ParsedDocument) -> list[Finding]:
        """Üçüncü satırda birim adı olmalı."""
        if not doc.unit_name:
            return [Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.WARNING,
                rule_code="FLD-003",
                title="Birim adı tespit edilemedi",
                description=(
                    "Başlık bölümünde birim adı (Dekanlık, Daire Başkanlığı vb.) "
                    "tespit edilemedi."
                ),
                reference="YÖ-0030 R5, Dördüncü Bölüm Madde 4",
                suggestion="Üniversite adının altına birim adını ekleyin.",
            )]
        return []

    def _check_sayi(self, doc: ParsedDocument) -> list[Finding]:
        """Sayı numarası olmalı ve formatı doğru olmalı."""
        findings = []
        if not doc.sayi:
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.ERROR,
                rule_code="FLD-004",
                title="Sayı numarası eksik",
                description="Belgede 'Sayı:' alanı bulunamadı.",
                reference="Yönetmelik Madde 12",
                suggestion="'Sayı:' alanını ekleyin.",
            ))
        return findings

    def _check_tarih(self, doc: ParsedDocument) -> list[Finding]:
        """Tarih olmalı ve GG.AA.YYYY formatında olmalı."""
        findings = []
        if not doc.tarih:
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.ERROR,
                rule_code="FLD-005",
                title="Tarih eksik",
                description="Belgede tarih bilgisi bulunamadı.",
                reference="Yönetmelik Madde 13",
                suggestion="Tarih alanını GG/AA/YYYY formatında ekleyin.",
            ))
        else:
            # Format kontrolü: GG.AA.YYYY veya GG/AA/YYYY
            date_pattern = re.compile(
                r"^(0[1-9]|[12]\d|3[01])[./](0[1-9]|1[0-2])[./](19|20)\d{2}$"
            )
            clean_date = doc.tarih.strip()
            # Sayı satırından çıkarılmış olabilir
            date_match = re.search(
                r"(0[1-9]|[12]\d|3[01])[./](0[1-9]|1[0-2])[./](19|20)\d{2}",
                clean_date,
            )
            if not date_match:
                findings.append(Finding(
                    id=self._next_id(),
                    layer=Layer.A,
                    severity=Severity.WARNING,
                    rule_code="FLD-005",
                    title="Geçersiz tarih formatı",
                    description=f"Tarih '{clean_date}' standart formata uymuyor.",
                    expected="GG.AA.YYYY (ör: 15.03.2026)",
                    found=clean_date,
                    reference="Yönetmelik Madde 13",
                    suggestion="Tarihi GG.AA.YYYY formatına dönüştürün.",
                ))
        return findings

    def _check_konu(self, doc: ParsedDocument) -> list[Finding]:
        """'Konu:' alanı olmalı."""
        if not doc.konu:
            return [Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.ERROR,
                rule_code="FLD-006",
                title="Konu alanı eksik",
                description="Belgede 'Konu:' alanı bulunamadı.",
                reference="Yönetmelik Madde 14",
                suggestion="'Konu:' alanını ekleyin.",
            )]
        return []

    def _check_imza_block(self, doc: ParsedDocument) -> list[Finding]:
        """İmza bloğu olmalı (ad soyad, unvan)."""
        if not doc.imza_block:
            return [Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.ERROR,
                rule_code="FLD-007",
                title="İmza bloğu eksik",
                description="Belgede imza bloğu (ad, soyad, unvan) tespit edilemedi.",
                reference="Yönetmelik Madde 18; YÖ-0030 R5",
                suggestion="Kapanış ifadesinden sonra imza bloğunu ekleyin.",
            )]
        return []

    # ═══════════════════════════════════════════════════════════════
    # KAPANIŞ İFADESİ KURALLARI
    # ═══════════════════════════════════════════════════════════════

    def _check_kapanis(self, doc: ParsedDocument) -> list[Finding]:
        """Kapanış ifadesi olmalı ve yasaklı ifadeler kullanılmamalı."""
        findings = []

        if not doc.kapanis_phrase:
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.ERROR,
                rule_code="CLS-001",
                title="Kapanış ifadesi eksik",
                description=(
                    "Belgede kapanış ifadesi ('Arz ederim', 'Rica ederim' vb.) "
                    "bulunamadı."
                ),
                reference="YÖ-0030 R5, Madde 5-e",
                suggestion=(
                    "Metin sonuna uygun kapanış ifadesini ekleyin. "
                    "Üst makama: 'Arz ederim', Alt makama: 'Rica ederim'"
                ),
            ))
            return findings

        # Yasaklı ifade kontrolü (kelime sınırı ile — "onaylanarak" gibi substring'leri hariç tut)
        phrase = doc.kapanis_phrase.strip()
        for forbidden in CLOSING_RULES["forbidden"]:
            pattern = r"\b" + re.escape(forbidden) + r"\b"
            if re.search(pattern, phrase, re.IGNORECASE):
                findings.append(Finding(
                    id=self._next_id(),
                    layer=Layer.A,
                    severity=Severity.ERROR,
                    rule_code="CLS-002",
                    title="Yasaklı kapanış ifadesi",
                    description=f"'{forbidden}' ifadesi resmi yazışmalarda kullanılmamalıdır.",
                    found=phrase,
                    expected="'Arz ederim' veya 'Rica ederim'",
                    reference="YÖ-0030 R5, Madde 5-e",
                    suggestion=(
                        f"'{forbidden}' yerine 'Arz ederim' veya 'Rica ederim' "
                        f"kullanın."
                    ),
                ))
        return findings

    def _check_onay_words(self, doc: ParsedDocument) -> list[Finding]:
        """Onay yazılarında 'OLUR' kullanılmalı; 'Onay', 'Uygundur' yasak."""
        findings = []
        re_onay = re.compile(r"\b(Onay|Uygundur|Muvafıktır)\b", re.IGNORECASE)
        last_metin_index = max(doc.metin_paragraphs) if doc.metin_paragraphs else None

        for pp in doc.paragraphs:
            in_closing_block = pp.section in (DocumentSection.KAPANIS, DocumentSection.IMZA)
            after_body = last_metin_index is not None and pp.index > last_metin_index
            if not (in_closing_block or after_body):
                continue
            if pp.section in (DocumentSection.EK, DocumentSection.DAGITIM):
                continue

            match = re_onay.search(pp.text)
            if match:
                findings.append(Finding(
                    id=self._next_id(),
                    layer=Layer.A,
                    severity=Severity.ERROR,
                    rule_code="CLS-003",
                    title="Yanlış onay ifadesi",
                    description=(
                        f"'{match.group(0)}' ifadesi kullanılmış. "
                        f"Onay yazılarında sadece 'OLUR' kullanılmalıdır."
                    ),
                    found=match.group(0),
                    expected="OLUR",
                    location=FindingLocation(
                        paragraph=pp.index,
                        section=pp.section.value,
                        text_snippet=pp.text[:80],
                    ),
                    reference="YÖ-0030 R5, Madde 5-e",
                    suggestion="'OLUR' ifadesini kullanın.",
                ))
        return findings

    # ═══════════════════════════════════════════════════════════════
    # TUTARLILIK KURALLARI (deterministik)
    # ═══════════════════════════════════════════════════════════════

    def _check_ek_count(self, doc: ParsedDocument) -> list[Finding]:
        """Metindeki ek sayısı ifadesi ile ek listesindeki sayıyı karşılaştırır (SEM-002)."""
        if not doc.ek_list:
            return []

        # Metin + kapanış paragraflarından tam metni oluştur
        metin_texts = [
            pp.text for pp in doc.paragraphs
            if pp.index in doc.metin_paragraphs
            or pp.section in (DocumentSection.METIN, DocumentSection.KAPANIS)
        ]
        if not metin_texts:
            return []
        full_metin = " ".join(metin_texts)

        number_map = {
            "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5,
            "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10,
        }
        m = re.search(
            r"(\d+|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on)\s*adet",
            full_metin, re.IGNORECASE
        )
        if not m:
            return []

        raw = m.group(1)
        ek_count_in_text = int(raw) if raw.isdigit() else number_map.get(raw.lower())
        if ek_count_in_text is None:
            return []

        # Sadece gerçek ek öğelerini say (EK-1, EK-2, ...) — "EK:" başlık satırını hariç tut
        ek_items = [e for e in doc.ek_list if re.match(r"EK[-\s]*\d+", e, re.IGNORECASE)]
        actual = len(ek_items) if ek_items else len(doc.ek_list)

        if ek_count_in_text != actual:
            return [Finding(
                id=self._next_id(),
                layer=Layer.A,
                severity=Severity.ERROR,
                rule_code="SEM-002",
                title="Ek sayısı tutarsızlığı",
                description=(
                    f"Metinde '{ek_count_in_text} adet' ek belirtilmiş "
                    f"ancak ek listesinde {actual} belge var."
                ),
                found=str(actual),
                expected=str(ek_count_in_text),
                reference="Yönetmelik Madde 20-d; YÖ-0030 R5",
                suggestion=(
                    f"Ek listesini {ek_count_in_text} belgeye tamamlayın "
                    f"veya metin ifadesini {actual} olarak düzeltin."
                ),
            )]
        return []

    # ═══════════════════════════════════════════════════════════════
    # DİL / YAZIM KURALLARI (deterministik regex tabanlı)
    # ═══════════════════════════════════════════════════════════════

    def _check_language(self, doc: ParsedDocument) -> list[Finding]:
        """Sık yapılan Türkçe yazım hatalarını kontrol eder."""
        findings = []
        metin_paragraphs = [
            pp for pp in doc.paragraphs
            if pp.section in (
                DocumentSection.METIN,
                DocumentSection.KAPANIS,
                DocumentSection.MUHATAP,
            )
        ]

        for pp in metin_paragraphs:
            text = pp.text

            # ── de/da bağlaç kontrolü ──
            # "da/de" bağlacı ses uyumuna göre kullanılmalı
            # Yaygın hata: sert ünsüzden sonra "de" yerine "da" yazma veya tam tersi
            # Bu karmaşık, sadece açık hataları yakala
            wrong_deda = re.findall(
                r"\b(\w*[çfhkpstş])\s+(de|da)\b", text, re.IGNORECASE
            )
            # Sert ünsüzden sonra "de/da" → "te/ta" olmalı (ek olarak)
            # Ama bağlaç olarak ayrı yazılıyorsa sorun yok
            # Bu kural karmaşık, sadece INFO seviyesinde uyar

            # ── ki bağlacı ──
            # Bağlaç olan "ki" ayrı yazılır (istisna: halbuki, mademki, oysaki, sanki)
            exceptions = {"halbuki", "mademki", "oysaki", "sanki", "belki", "çünkü"}
            ki_errors = re.findall(r"\b(\w+ki)\b", text)
            for word in ki_errors:
                if word.lower() not in exceptions and len(word) > 4:
                    if word.lower().endswith("ki") and not word.lower().endswith("deki"):
                        # Potansiyel hata ama çok false positive, INFO seviyesinde
                        pass

            # ── Büyük harf kuralları ──
            # Cümle başı büyük harf kontrolü (noktadan sonra)
            sentences = re.split(r'(?<=[.!?])\s+', text)
            for sent in sentences:
                if sent and sent[0].islower() and len(sent) > 2:
                    findings.append(Finding(
                        id=self._next_id(),
                        layer=Layer.A,
                        severity=Severity.WARNING,
                        rule_code="LNG-001",
                        title="Cümle başı küçük harf",
                        description="Cümle küçük harfle başlıyor.",
                        found=sent[:40],
                        location=FindingLocation(
                            paragraph=pp.index,
                            text_snippet=sent[:60],
                        ),
                        reference="TDK Yazım Kılavuzu - Büyük Harflerin Kullanıldığı Yerler",
                        suggestion="Cümle başını büyük harfle yazın.",
                    ))

            # ── Noktalama hataları ──
            # Virgülden önce boşluk
            if re.search(r"\s,", text):
                findings.append(Finding(
                    id=self._next_id(),
                    layer=Layer.A,
                    severity=Severity.INFO,
                    rule_code="LNG-002",
                    title="Virgül öncesi gereksiz boşluk",
                    description="Virgülden önce boşluk bırakılmış.",
                    location=FindingLocation(
                        paragraph=pp.index,
                        text_snippet=text[:80],
                    ),
                    reference="TDK Yazım Kılavuzu - Noktalama İşaretleri",
                    suggestion="Virgülden önceki boşluğu kaldırın.",
                ))

            # Noktadan sonra boşluk eksik
            if re.search(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]\.[a-zA-ZçğıöşüÇĞİÖŞÜ]", text):
                # Kısaltmaları hariç tut (T.C., vb.)
                potential = re.findall(
                    r"([a-zA-ZçğıöşüÇĞİÖŞÜ]{2,})\.([a-zA-ZçğıöşüÇĞİÖŞÜ])", text
                )
                for before, after in potential:
                    if len(before) > 2:  # kısaltma değilse
                        findings.append(Finding(
                            id=self._next_id(),
                            layer=Layer.A,
                            severity=Severity.INFO,
                            rule_code="LNG-003",
                            title="Noktadan sonra boşluk eksik",
                            description=f"'...{before}.{after}...' — noktadan sonra boşluk yok.",
                            location=FindingLocation(
                                paragraph=pp.index,
                                text_snippet=text[:80],
                            ),
                            reference="TDK Yazım Kılavuzu - Noktalama İşaretleri",
                            suggestion="Noktadan sonra bir boşluk bırakın.",
                        ))

            # Virgül/noktalı virgülden sonra boşluk eksik
            # Kural: "noktalama işaretlerinden sonra bir harf boşluğu ara verilir"
            # TDK Yazım Kılavuzu — Noktalama İşaretleri (Açıklamalar)
            # Resmi yazışmalarda URL, sayısal ifade vb. false-positive'leri dışla
            punct_no_space = re.findall(
                r"([A-ZÇĞİÖŞÜa-zçğıöşü]{2,})"  # kelime (≥2 harf)
                r"([,;])"                         # virgül veya noktalı virgül
                r"([A-ZÇĞİÖŞÜa-zçğıöşü])",      # hemen ardından harf (boşluk yok)
                text,
            )
            if punct_no_space:
                before, punct, after = punct_no_space[0]
                findings.append(Finding(
                    id=self._next_id(),
                    layer=Layer.A,
                    severity=Severity.INFO,
                    rule_code="LNG-005",
                    title="Noktalama işaretinden sonra boşluk eksik",
                    description=(
                        f"'{before}{punct}{after}...' — "
                        f"{'Virgül' if punct == ',' else 'Noktalı virgül'}'den "
                        f"sonra boşluk bırakılmamış."
                    ),
                    location=FindingLocation(
                        paragraph=pp.index,
                        text_snippet=text[:80],
                    ),
                    reference="TDK Yazım Kılavuzu - Noktalama İşaretleri",
                    suggestion=(
                        f"{'Virgül' if punct == ',' else 'Noktalı virgül'}'den "
                        f"sonra bir boşluk bırakın."
                    ),
                ))

            # ── Gereksiz boşluklar ──
            if re.search(r"  +", text):
                findings.append(Finding(
                    id=self._next_id(),
                    layer=Layer.A,
                    severity=Severity.INFO,
                    rule_code="LNG-004",
                    title="Fazla boşluk",
                    description="Metinde art arda birden fazla boşluk var.",
                    location=FindingLocation(
                        paragraph=pp.index,
                        text_snippet=text[:80],
                    ),
                    reference="Genel yazım kuralı",
                    suggestion="Fazla boşlukları temizleyin.",
                ))

        return findings
