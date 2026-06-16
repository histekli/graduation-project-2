"""
Katman C — LLM Destekli Semantik Analiz
Mantıksal tutarlılık, anlatım bozukluğu ve ek-metin uyumunu analiz eder.
Google Gemini (birincil) veya Groq/Llama (yedek) API kullanır.

Ortam değişkenleri:
  LAYER_C_PROVIDER   = "gemini" | "groq"  (varsayılan: "gemini")
  GEMINI_API_KEY     — Gemini için (birincil)
  GROQ_API_KEY       — Groq için (yedek, ücretsiz tier mevcuttur)
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

# Katman C YALNIZCA LLM semantik kategorileri üretir. Deterministik SEM-002
# (ek-metin) ve SEM-006 (tekrar) Katman A'ya taşındı; burada yer almazlar.
_RULE_CODE_MAP: dict[str, str] = {
    "konu_metin":       "SEM-001",
    "mantiksal":        "SEM-003",
    "anlatim":          "SEM-004",
    "belge_yeterlilik": "SEM-005",
}

_CATEGORY_REFERENCES: dict[str, str] = {
    "konu_metin":       "YÖ-0030 R5 Madde 6 — Konu Satırı",
    "mantiksal":        "Resmi Yazışma İlkeleri — Mantıksal Tutarlılık",
    "anlatim":          "TDK Yazım Kılavuzu; Resmi Yazışma Dili",
    "belge_yeterlilik": "YÖ-0030 R5 — Belge Yeterliliği",
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
            else "llama-3.3-70b-versatile"
        )
        self.model = model or os.getenv("LAYER_C_MODEL", _default_model)

        _default_key = (
            os.getenv("GEMINI_API_KEY")
            if self.provider == "gemini"
            else os.getenv("GROQ_API_KEY")
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

        # Katman C YALNIZCA LLM tabanlı semantik bulgular üretir. Deterministik
        # içerik kuralları (SEM-002 ek-metin çapraz kontrolü, SEM-006 tekrar eden
        # ifade) Katman A'ya (deterministik motor) taşınmıştır. Böylece "Katman C =
        # LLM" anlatısı mutlaktır ve her C bulgusunun layer alanı doğrudur.
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

        return f"""Sen Türk resmi yazışma standartları (YÖ-0030 R5, Cumhurbaşkanlığı Yazışma Kılavuzu 2025) konusunda uzman bir denetçisin.{rag_block}

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

1. **KONU-METİN UYUMU** (category: "konu_metin")
   - Konu satırı metnin içeriğini doğru ve yeterince özetliyor mu?
   - Konu çok muğlak, yanıltıcı ya da fazla genel mi?
   - Konu ≤3 kelime ise ya da metnin amacını yansıtmıyorsa sorun bildir.

2. **MANTIKSAL TUTARLILIK** (category: "mantiksal")
   - Metinde iç çelişki, belirsiz gönderme ya da eksik bağlam var mı?
   - Muhatap ile yazının tonu ve içeriği uyuşuyor mu?
   - Talep veya bildirim açık, eylemlenebilir ve net mi?

3. **ANLATIM BOZUKLUKLARI** (category: "anlatim")
   - Özne-yüklem uyumsuzluğu, sarkık cümle, belirsiz zamir var mı?
   - Gereksiz edilgen yapı ya da anlam belirsizliği var mı?
   - Türkçe resmi yazışma diline uymayan ifade, anglisizm veya jargon var mı?

4. **BELGE YETERLİLİĞİ** (category: "belge_yeterlilik")
   - Konuda belirtilen amaç metinde yeterince açıklanmış mı?
   - Gerekli bilgiler (tarih, süre, adet, gerekçe vb.) eksiksiz mi?
   - Okuyucu bu yazıdan sonra ne yapacağını anlayabiliyor mu?

KURALLAR:
- YALNIZCA gerçek ve belgeye özgü somut sorunları raporla. Genel gözlem yapma.
- Her bulguda sorunlu metni doğrudan alıntıla ("found_text" alanına koy).
- "anlatim" ve "konu_metin" kategorilerinde mümkünse yeniden yazılmış öneri sun ("suggested_text").
- Sorun yoksa boş JSON dizisi `[]` döndür.
- Noktalama, büyük/küçük harf, font gibi biçimsel sorunları RAPORLAMA.
- confidence: 0.55–1.0 arası gerçekçi değer; 0.55 altını EKLEME.

SADECE aşağıdaki JSON dizisini döndür, başka metin ekleme:
[
  {{
    "category": "konu_metin" | "mantiksal" | "anlatim" | "belge_yeterlilik",
    "severity": "error" | "warning" | "info",
    "title": "Kısa başlık (≤70 karakter)",
    "description": "Sorunun somut açıklaması — hangi metin, neden sorunlu",
    "found_text": "Sorunlu metnin alıntısı (varsa, ≤120 karakter)",
    "suggestion": "Nasıl düzeltilmeli — genel tavsiye",
    "suggested_text": "Yeniden yazılmış metin önerisi (yalnızca anlatim/konu_metin; yoksa null)",
    "confidence": 0.75
  }}
]"""

    def _call_llm(self, prompt: str) -> str:
        if self.provider == "gemini":
            return self._call_gemini(prompt)
        if self.provider == "groq":
            return self._call_groq(prompt)
        raise ValueError(f"Bilinmeyen LLM sağlayıcı: '{self.provider}'. 'gemini' veya 'groq' kullanın.")

    def _call_groq(self, prompt: str) -> str:
        try:
            from groq import Groq
        except ImportError as exc:
            raise RuntimeError(
                "groq paketi kurulu değil. Yüklemek için: pip install groq"
            ) from exc

        if self._client is None:
            self._client = Groq(api_key=self.api_key)

        completion = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.3,
        )
        return completion.choices[0].message.content

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

            # found_text → found alanına; suggested_text → ayrı alan
            found_text = item.get("found_text") or None
            suggested  = item.get("suggested_text") or None
            # null/boş string'leri temizle
            if suggested and len(suggested.strip()) < 5:
                suggested = None

            reference = _CATEGORY_REFERENCES.get(
                category,
                "YÖ-0030 R5; Cumhurbaşkanlığı Yazışma Kılavuzu 2025",
            )
            findings.append(Finding(
                id=self._next_id(),
                layer=Layer.C,
                severity=severity,
                rule_code=rule_code,
                title=str(item.get("title", "Semantik sorun"))[:120],
                description=str(item.get("description", "")),
                found=found_text,
                suggestion=item.get("suggestion"),
                suggested_text=suggested,
                reference=reference,
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
