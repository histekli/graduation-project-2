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
    "konu_metin": "SEM-001",
    "ek_metin":   "SEM-002",
    "mantiksal":  "SEM-003",
    "anlatim":    "SEM-004",
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

    def run(self, doc: ParsedDocument) -> list[Finding]:
        """Tüm Katman C analizlerini çalıştırır."""
        if not self.is_ready:
            logger.warning("Katman C: API anahtarı bulunamadı — atlanıyor.")
            return []

        self._counter = 0
        metin_text = self._get_metin_text(doc)

        findings: list[Finding] = []

        # 1. Deterministik EK-Metin çapraz kontrolü — metin kısa olsa da çalışır
        findings.extend(self._check_ek_references(doc, metin_text))

        # 2. LLM tabanlı analiz — çok kısa metinlerde anlamsız, atla
        if len(metin_text.split()) >= 15:
            try:
                findings.extend(self._run_llm_analysis(doc, metin_text))
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

    # ── LLM analizi ─────────────────────────────────────────────────────────

    def _run_llm_analysis(
        self, doc: ParsedDocument, metin_text: str
    ) -> list[Finding]:
        prompt = self._build_prompt(doc, metin_text)
        raw_response = self._call_llm(prompt)
        return self._parse_llm_response(raw_response)

    def _build_prompt(self, doc: ParsedDocument, metin_text: str) -> str:
        konu   = doc.konu    or "(belirtilmemiş)"
        muhatap = doc.muhatap or "(belirtilmemiş)"
        kapanis = doc.kapanis_phrase or "(belirtilmemiş)"
        ek_str  = "; ".join(doc.ek_list) if doc.ek_list else "(yok)"

        # Uzun metinleri kırp (token tasarrufu)
        metin_snippet = metin_text[:2500] if len(metin_text) > 2500 else metin_text

        return f"""Sen Türk resmi yazışma standartları (YÖ-0030, Cumhurbaşkanlığı Yazışma Kılavuzu 2025) konusunda uzman bir denetçisin.

Aşağıdaki resmi yazıyı analiz et:

KONU: {konu}
MUHATAP: {muhatap}
METİN:
---
{metin_snippet}
---
KAPANIŞ: {kapanis}
EK LİSTESİ: {ek_str}

Şu 3 kategoride analiz yap:

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

KURALLAR:
- SADECE gerçek ve somut sorunları raporla.
- Sorun yoksa boş JSON dizisi `[]` döndür.
- Noktalama, büyük/küçük harf, font gibi biçimsel sorunları RAPORLAMA (bunları başka katmanlar zaten kontrol ediyor).
- Her bulgu için confidence: 0.5–1.0 arası gerçekçi bir değer ver.
- confidence < 0.55 olan bulguları listeye EKLEME.

Yanıtı SADECE aşağıdaki JSON formatında döndür, başka hiçbir metin ekleme:
[
  {{
    "category": "konu_metin" | "mantiksal" | "anlatim",
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
