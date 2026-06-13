"""
Katman C — LLM Destekli Semantik Analiz
Mantıksal tutarlılık, anlatım bozukluğu ve ek-metin uyumunu analiz eder.
Anthropic Claude (varsayılan) veya Google Gemini API kullanır.

Ortam değişkenleri:
  LAYER_C_PROVIDER   = "gemini" | "claude"  (varsayılan: "gemini")
  GEMINI_API_KEY     — Gemini için (birincil)
  ANTHROPIC_API_KEY  — Claude için (karşılaştırma)
  LAYER_C_MODEL      — model ID override
"""
from __future__ import annotations
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from app.models.finding import (
    Finding, Severity, Layer, ParsedDocument, DocumentSection
)

logger = logging.getLogger(__name__)

# Config dosyası — .env dışında, git'e gitmez, UI'dan yazılabilir
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "api_config.json"

_RULE_CODE_MAP: dict[str, str] = {
    "konu_metin":       "SEM-001",
    "ek_metin":         "SEM-002",
    "mantiksal":        "SEM-003",
    "anlatim":          "SEM-004",
    "belge_yeterlilik": "SEM-005",
}

_SEVERITY_MAP: dict[str, Severity] = {
    "error":   Severity.ERROR,
    "warning": Severity.WARNING,
    "info":    Severity.INFO,
}

_CONFIDENCE_THRESHOLD = 0.50  # Altındaki bulgular atlanır


class LayerC:
    """LLM destekli semantik analiz motoru."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.provider = (provider or os.getenv("LAYER_C_PROVIDER", "gemini")).lower()

        _default_model = (
            "gemini-2.5-flash"
            if self.provider == "gemini"
            else "claude-haiku-4-5-20251001"
        )
        self.model = model or os.getenv("LAYER_C_MODEL", _default_model)

        _default_key = (
            os.getenv("GEMINI_API_KEY")
            if self.provider == "gemini"
            else os.getenv("ANTHROPIC_API_KEY")
        )
        self.api_key = api_key or _default_key

        self._counter = 0
        self._client: Any = None

    # ── Factory ─────────────────────────────────────────────────────────────

    @classmethod
    def _from_config(cls) -> "LayerC":
        """
        Önce data/api_config.json'u okur (UI'dan kaydedilen key),
        bulunamazsa env var'a düşer.
        """
        cfg = _load_config()
        if cfg.get("api_key") and cfg.get("provider"):
            return cls(
                provider=cfg["provider"],
                api_key=cfg["api_key"],
                model=cfg.get("model") or None,
            )
        return cls()

    # ── Hazırlık ────────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return bool(self.api_key)

    def _next_id(self) -> str:
        self._counter += 1
        return f"C{self._counter:03d}"

    # ── Yardımcılar ────────────────────────────────────────────────────────

    def _get_metin_text(self, doc: ParsedDocument) -> str:
        """Belgenin metin gövdesini düz metin olarak döndürür."""
        metin_parts = [
            pp.text for pp in doc.paragraphs
            if pp.index in doc.metin_paragraphs
            or pp.section == DocumentSection.METIN
        ]
        return " ".join(metin_parts)

    # ── Ana giriş noktası ───────────────────────────────────────────────────

    def run(
        self,
        doc: ParsedDocument,
        rag_context: list[dict] | None = None,
    ) -> list[Finding]:
        """
        Tüm Katman C analizlerini çalıştırır.

        Args:
            doc: Ayrıştırılmış belge
            rag_context: Katman B'den gelen ilgili yönerge chunk'ları (few-shot bağlam)
        """
        if not self.is_ready:
            logger.warning("Katman C: API anahtarı bulunamadı — atlanıyor.")
            return []

        self._counter = 0
        metin_text = self._get_metin_text(doc)

        findings: list[Finding] = []

        # 1. Deterministik EK-Metin çapraz kontrolü — metin kısa olsa da çalışır
        findings.extend(self._check_ek_references(doc, metin_text))

        # 2. Deterministik tekrar eden ifade kontrolü
        findings.extend(self._check_repeated_content(doc, metin_text))

        # 3. LLM tabanlı analiz — çok kısa metinlerde anlamsız, atla
        if len(metin_text.split()) >= 15:
            try:
                findings.extend(self._run_llm_analysis(doc, metin_text, rag_context or []))
            except Exception as exc:
                msg = str(exc)
                # Kota/ağ hatalarını pipeline'ın yakalayıp raporlayabilmesi için yukarı fırlat
                if any(k in msg for k in ("429", "quota", "RESOURCE_EXHAUSTED", "rate")):
                    raise
                logger.error("Katman C LLM analizi başarısız: %s", exc)

        return findings

    # ── Deterministik EK-Metin kontrolü ────────────────────────────────────

    def _check_ek_references(
        self, doc: ParsedDocument, metin_text: str
    ) -> list[Finding]:
        """
        Metin içindeki ek atıfları ile EK listesini çapraz kontrol eder.
        LLM maliyeti olmadan yüksek doğrulukla yakalanabilecek durum.
        """
        findings: list[Finding] = []

        ek_refs_in_text = set(
            re.findall(r"\bEK[-\s]?\d+\b", metin_text, re.IGNORECASE)
        )
        has_genel_ek_ref = bool(
            re.search(r"\bekte\b|\bekli\b|\bek'te\b", metin_text, re.IGNORECASE)
        )

        ek_nums_in_list: set[str] = set()
        for ek_item in doc.ek_list:
            ek_nums_in_list.update(re.findall(r"\d+", ek_item))

        # Metin içinde ek atıfı var ama EK bölümü oluşturulmamış
        if (ek_refs_in_text or has_genel_ek_ref) and not doc.ek_list:
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.C,
                severity=Severity.WARNING,
                rule_code="SEM-002",
                title="Ek atıfı var fakat EK bölümü boş",
                description=(
                    "Metin içinde ek belgeye atıfta bulunulmuş ancak "
                    "belgede EK bölümü oluşturulmamış ya da boş bırakılmış."
                ),
                found=", ".join(sorted(ek_refs_in_text)) or "ekte/ekli ifadesi",
                reference="YÖ-0030 R5, Ekler bölümü",
                suggestion=(
                    "EK bölümü ekleyip ekleri numaralandırın. "
                    "Örn: 'EK-1: Dilekçe (1 sayfa)'"
                ),
                confidence=0.92,
            ))

        # EK listesi var ama metin içinde hiç atıf yapılmamış
        elif doc.ek_list and not ek_refs_in_text and not has_genel_ek_ref:
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.C,
                severity=Severity.INFO,
                rule_code="SEM-002",
                title="EK listesi var fakat metin içinde atıf yok",
                description=(
                    f"{len(doc.ek_list)} adet ek listelenmiş ancak "
                    "metin içinde bu eklere atıfta bulunulmamış."
                ),
                reference="Resmi yazışma ilkeleri",
                suggestion=(
                    "Metin içinde eklerden söz edin. "
                    "Örn: '...dilekçe örneği ekte sunulmuştur. (EK-1)'"
                ),
                confidence=0.78,
            ))

        return findings

    # ── Deterministik tekrar kontrolü ───────────────────────────────────────

    @staticmethod
    def _word_overlap(a: str, b: str) -> float:
        """İki cümle arasındaki sözcük örtüşme oranını hesaplar (0.0–1.0)."""
        wa = set(a.split())
        wb = set(b.split())
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / max(len(wa), len(wb))

    def _check_repeated_content(
        self, doc: ParsedDocument, metin_text: str
    ) -> list[Finding]:
        """
        Metin gövdesinde tekrar eden cümleleri deterministik olarak tespit eder.
        Hem tam tekrarları hem de yüksek sözcük örtüşmeli (≥85%) cümleleri yakalar.
        """
        metin_paras = [
            pp.text for pp in doc.paragraphs
            if pp.section == DocumentSection.METIN
        ]
        if not metin_paras:
            return []

        sentences: list[str] = []
        for text in metin_paras:
            for sent in re.split(r"(?<=[.!?])\s+", text):
                cleaned = re.sub(r"\s+", " ", sent.strip().lower())
                if len(cleaned) >= 30:
                    sentences.append(cleaned)

        if len(sentences) < 2:
            return []

        repeated_pairs: list[tuple[str, str]] = []
        for i in range(len(sentences)):
            for j in range(i + 1, len(sentences)):
                if self._word_overlap(sentences[i], sentences[j]) >= 0.85:
                    repeated_pairs.append((sentences[i], sentences[j]))

        if not repeated_pairs:
            return []

        first_a, first_b = repeated_pairs[0]
        return [Finding(
            id=self._next_id(),
            layer=Layer.C,
            severity=Severity.INFO,
            rule_code="SEM-006",
            title=f"Tekrar eden ifade ({len(repeated_pairs)} çift)",
            description=(
                f"Metin gövdesinde {len(repeated_pairs)} çift birbirine çok benzer "
                f"cümle veya ifade tespit edildi."
            ),
            found=f'"{first_a[:60]}..." ↔ "{first_b[:60]}..."',
            reference="Resmi yazışma ilkeleri — özlük ve sadelik",
            suggestion="Tekrar eden ifadeleri kaldırın veya farklı şekilde ifade edin.",
            confidence=0.92,
        )]

    # ── LLM analizi ─────────────────────────────────────────────────────────

    def _run_llm_analysis(
        self,
        doc: ParsedDocument,
        metin_text: str,
        rag_context: list[dict] | None = None,
    ) -> list[Finding]:
        prompt = self._build_prompt(doc, metin_text, rag_context or [])
        raw_response = self._call_llm(prompt)
        return self._parse_llm_response(raw_response)

    def _build_prompt(
        self,
        doc: ParsedDocument,
        metin_text: str,
        rag_context: list[dict] | None = None,
    ) -> str:
        konu    = doc.konu           or "(belirtilmemiş)"
        muhatap = doc.muhatap        or "(belirtilmemiş)"
        kapanis = doc.kapanis_phrase or "(belirtilmemiş)"
        ek_str  = "; ".join(doc.ek_list) if doc.ek_list else "(yok)"

        # Uzun metinleri kırp (token tasarrufu)
        metin_snippet = metin_text[:2500] if len(metin_text) > 2500 else metin_text

        # RAG bağlamı: ilgili yönerge maddelerini few-shot olarak ekle
        rag_block = ""
        if rag_context:
            chunks = []
            seen_texts: set[str] = set()
            for item in rag_context[:3]:
                text = (item.get("text") or item.get("document") or item.get("content") or "").strip()
                src  = item.get("metadata", {}).get("source", item.get("metadata", {}).get("source_name", ""))
                if text and text not in seen_texts and len(text) > 50:
                    seen_texts.add(text)
                    chunks.append(f"[{src}] {text[:400]}")
            if chunks:
                rag_block = (
                    "\n\nİLGİLİ YÖNERGİ MADDELERİ (referans olarak kullan):\n"
                    + "\n---\n".join(chunks)
                    + "\n"
                )

        return f"""Sen Türk resmi yazışma standartları (YÖ-0030, Cumhurbaşkanlığı Yazışma Kılavuzu 2025) konusunda uzman bir denetçisin.{rag_block}

Aşağıdaki resmi yazıyı analiz et:

KONU: {konu}
MUHATAP: {muhatap}
METİN:
---
{metin_snippet}
---
KAPANIŞ: {kapanis}
EK LİSTESİ: {ek_str}

Şu 4 kategoride analiz yap:

1. **KONU-METİN UYUMU (category: "konu_metin", rule_code: "SEM-001")**
   - Konu satırı metnin içeriğini doğru özetliyor mu?
   - Konu çok muğlak mı, yanıltıcı mı veya fazla genel mi?

2. **MANTIKSAL TUTARLILIK (category: "mantiksal", rule_code: "SEM-003")**
   - Metinde iç çelişki, belirsiz gönderme ya da eksik bağlam var mı?
   - Muhatap ile yazı içeriği uyuşuyor mu?
   - Talep veya bildirim açık ve net mi?

3. **ANLATIM BOZUKLUKLARI (category: "anlatim", rule_code: "SEM-004")**
   - Özne-yüklem uyumsuzluğu, sarkık cümle, belirsiz zamir kullanımı var mı?
   - Gereksiz edilgen yapı veya anlam belirsizliği var mı?
   - Türkçe resmi yazışma diline uymayan ifadeler var mı?

4. **BELGE YETERLİLİĞİ (category: "belge_yeterlilik", rule_code: "SEM-005")**
   - Konuda belirtilen amaç metinde yeterince açıklanmış mı?
   - Gerekli bilgiler (tarih, süre, adet, gerekçe vb.) tam mı?
   - Okuyucu bilgiden ne yapacağını anlayabiliyor mu?

KURALLAR:
- SADECE gerçek ve somut sorunları raporla.
- Sorun yoksa boş JSON dizisi `[]` döndür.
- Noktalama, büyük/küçük harf, font gibi biçimsel sorunları RAPORLAMA (bunları başka katmanlar zaten kontrol ediyor).
- Her bulgu için confidence: 0.5–1.0 arası gerçekçi bir değer ver.
- confidence < 0.55 olan bulguları listeye EKLEME.

Yanıtı SADECE aşağıdaki JSON formatında döndür, başka hiçbir metin ekleme:
[
  {{
    "category": "konu_metin" | "mantiksal" | "anlatim" | "belge_yeterlilik",
    "severity": "error" | "warning" | "info",
    "title": "Kısa başlık (en fazla 70 karakter)",
    "description": "Sorunun açık ve somut açıklaması",
    "suggestion": "Nasıl düzeltilmeli (somut öneri)",
    "confidence": 0.75
  }}
]"""

    def _call_llm(self, prompt: str) -> str:
        if self.provider == "gemini":
            return self._call_gemini(prompt)
        if self.provider == "claude":
            return self._call_claude(prompt)
        raise ValueError(f"Bilinmeyen LLM sağlayıcı: '{self.provider}'. 'gemini' veya 'claude' kullanın.")

    def _call_claude(self, prompt: str) -> str:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic paketi kurulu değil. Yüklemek için: pip install anthropic"
            ) from exc

        if self._client is None:
            self._client = Anthropic(api_key=self.api_key)

        message = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def _call_gemini(self, prompt: str) -> str:
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "google-genai paketi kurulu değil. Yüklemek için: pip install google-genai"
            ) from exc

        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return response.text

    # ── LLM yanıtı ayrıştırma ───────────────────────────────────────────────

    def _parse_llm_response(self, raw: str) -> list[Finding]:
        """LLM JSON yanıtını Finding listesine dönüştürür."""
        # Yanıt içindeki JSON dizisini bul (```json ... ``` bloğu veya düz)
        json_match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if not json_match:
            logger.warning("Katman C: LLM yanıtından JSON çıkarılamadı — yanıt: %s", raw[:300])
            return []

        try:
            items: list[dict] = json.loads(json_match.group(0))
        except json.JSONDecodeError as exc:
            logger.warning("Katman C: JSON ayrıştırma hatası: %s", exc)
            return []

        findings: list[Finding] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            confidence = float(item.get("confidence", 0.7))
            if confidence < _CONFIDENCE_THRESHOLD:
                continue

            category  = item.get("category", "mantiksal")
            rule_code = _RULE_CODE_MAP.get(category, "SEM-003")
            severity  = _SEVERITY_MAP.get(item.get("severity", "warning"), Severity.WARNING)

            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.C,
                severity=severity,
                rule_code=rule_code,
                title=str(item.get("title", "Semantik sorun"))[:120],
                description=str(item.get("description", "")),
                suggestion=item.get("suggestion"),
                reference="YÖ-0030 R5; Cumhurbaşkanlığı Yazışma Kılavuzu 2025",
                confidence=confidence,
            ))

        return findings


# ── Config dosyası yardımcıları (modül seviyesi) ──────────────────────────────

def _load_config() -> dict:
    """data/api_config.json dosyasını okur; yoksa boş dict döner."""
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("api_config.json okunamadı: %s", exc)
    return {}


def save_config(provider: str, api_key: str, model: str | None = None) -> None:
    """API key ve sağlayıcıyı data/api_config.json'a kaydeder."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = _load_config()
    cfg["provider"] = provider
    cfg["api_key"]  = api_key
    if model:
        cfg["model"] = model
    elif "model" in cfg:
        del cfg["model"]
    _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("API config kaydedildi: provider=%s model=%s", provider, model or "default")
