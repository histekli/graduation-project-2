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

# Üretim/giriş ayarları
# NOT: Gemini 2.5 Flash'ta "thinking" token'ları da max_output_tokens'tan
# harcanır. Düşük tutulursa düşünme bütçesi tüm payı yer, gerçek JSON kesilir
# (finishReason=MAX_TOKENS) ve hiç bulgu dönmez. Bu yüzden cömert tutuyoruz +
# thinking bütçesini ayrıca sınırlıyoruz.
_MAX_OUTPUT_TOKENS = 8192
_THINKING_BUDGET = 1024    # Gemini 2.5: sınırlı düşünme → JSON'a yer kalır
_TEMPERATURE = 0.2         # düşük → tutarlı, tekrarlanabilir bulgular
_METIN_SNIPPET_LIMIT = 3000

# Grounding (kanıt doğrulama) — alıntının gerçekten belgede olup olmadığını ölçer.
# Halüsinasyon alıntıları (modelin uydurduğu metin) programatik olarak elenir.
_GROUNDING_MIN_LEN = 12     # bu uzunluğun altındaki alıntılar doğrulanmadan geçer
_GROUNDING_DROP_BELOW = 0.45   # kelime örtüşmesi bunun altındaysa bulgu ELENİR
_GROUNDING_PENALTY_BELOW = 0.75  # bunun altındaysa confidence düşürülür

# Katman C'nin davranışını yöneten sistem talimatı (rol + ilkeler).
# Sağlayıcıya system_instruction / system message olarak verilir.
_SYSTEM_PROMPT = """Sen Türk kamu kurumlarının resmi yazışma standartları konusunda uzman, titiz ve temkinli bir denetçisin. Uzmanlık alanların: Cumhurbaşkanlığı Resmi Yazışma Kılavuzu (2025), GTÜ YÖ-0030 R5 İç Yazışma Yönergesi ve TDK yazım/anlatım kuralları.

ÇALIŞMA İLKELERİN:
1. KESİNLİK > KAPSAM. Şüphedeysen RAPORLAMA. Hatalı bir uyarı (false positive), kaçırılan küçük bir sorundan daha zararlıdır — kullanıcının sistemine güveni buna bağlı.
2. KANIT ZORUNLULUĞU. Her bulgu, belgeden BİREBİR alıntılanmış somut bir metne dayanmalı. Alıntılayamıyorsan, o bulgu yok demektir.
3. SADECE ANLAM/MANTIK. Senin alanın semantik ve mantıksal tutarlılıktır. Noktalama, büyük/küçük harf, boşluk, font gibi BİÇİMSEL sorunlar başka bir katman tarafından ele alınır — bunlara ASLA değinme.
4. RESMİ DİL NORMU. Resmi yazıların kısa, öz ve kalıplaşmış olması NORMALDİR; bunu eksiklik sayma. Yalnızca anlamı bozan, belirsizlik yaratan veya okuyucuyu yanıltan gerçek sorunları işaretle.
5. İÇSEL MUHAKEME, SADE ÇIKTI. Önce adım adım düşün; ama çıktın YALNIZCA istenen JSON olsun, muhakemeni yazma."""


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
        # Grounding için "saman yığını": modelin alıntı yapabileceği tüm belge metni
        haystack = " ".join(filter(None, [
            doc.konu, doc.muhatap, metin_text, doc.kapanis_phrase,
            " ".join(doc.ilgi_list), " ".join(doc.ek_list),
        ]))
        return self._parse_llm_response(raw_response, haystack)

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
        ilgi_str = "; ".join(doc.ilgi_list) if doc.ilgi_list else "(yok)"

        # Uzun metinleri kırp (token tasarrufu); cümle bütünlüğünü bozmadan kes
        metin_snippet = metin_text
        if len(metin_text) > _METIN_SNIPPET_LIMIT:
            cut = metin_text[:_METIN_SNIPPET_LIMIT]
            last_stop = max(cut.rfind(". "), cut.rfind("\n"))
            metin_snippet = (cut[:last_stop + 1] if last_stop > 1500 else cut) + " […]"

        # RAG bağlamı: ilgili yönerge maddelerini referans olarak ekle
        rag_block = ""
        if rag_context:
            chunks = []
            seen_texts: set[str] = set()
            for item in rag_context[:3]:
                text = (item.get("text") or item.get("document") or item.get("content") or "").strip()
                src  = item.get("metadata", {}).get("source", item.get("metadata", {}).get("source_name", ""))
                if text and text not in seen_texts and len(text) > 50:
                    seen_texts.add(text)
                    chunks.append(f"• [{src}] {text[:400]}")
            if chunks:
                rag_block = (
                    "\n### İLGİLİ MEVZUAT (yalnızca referans/gerekçe için; bunlar denetlenen belge DEĞİL):\n"
                    + "\n".join(chunks)
                    + "\n"
                )

        return f"""Aşağıdaki resmi yazıyı 4 semantik kategoride denetle. Önce her kategoriyi içinden adım adım değerlendir, sonra YALNIZCA gerçek sorunları JSON olarak raporla.
{rag_block}
### DENETLENEN BELGE
KONU    : {konu}
MUHATAP : {muhatap}
İLGİ    : {ilgi_str}
EK      : {ek_str}
KAPANIŞ : {kapanis}
METİN:
\"\"\"
{metin_snippet}
\"\"\"

### KATEGORİLER VE ÖLÇÜTLER

1. KONU-METİN UYUMU  (category: "konu_metin", genelde severity: "warning")
   İŞARETLE: Konu, metnin asıl amacını yansıtmıyorsa; yanıltıcıysa; metinde olmayan bir konuyu söylüyorsa; ya da metnin ana talebi konuda hiç geçmiyorsa.
   İŞARETLEME: Konu kısa ama doğruysa (resmi yazıda kısalık normaldir); konu metni makul özetliyorsa.

2. MANTIKSAL TUTARLILIK  (category: "mantiksal", severity: "warning"/"error")
   İŞARETLE: Metin içi çelişki (bir yerde X, başka yerde X-değil); tarih/sayı/miktar çelişkisi; "ilgi"ye veya eke yapılan ama karşılığı olmayan gönderme; muhatabın yapamayacağı bir talep; sonucu belirsiz bırakan eksik bağlam.
   İŞARETLEME: Bilginin kısa olması; senin dışarıdan bilemeyeceğin varsayımlar.

3. ANLATIM BOZUKLUĞU  (category: "anlatim", genelde severity: "info")
   İŞARETLE: Özne-yüklem uyumsuzluğu; sarkık/eksik cümle; anlamı bulanıklaştıran belirsiz zamir; cümleyi anlaşılmaz kılan devrik/bozuk kuruluş; resmi dile aykırı argo/anglisizm.
   İŞARETLEME: Üslup tercihi; "daha güzel olurdu" türü öznel iyileştirmeler; edilgen çatı (resmi dilde olağandır).

4. BELGE YETERLİLİĞİ  (category: "belge_yeterlilik", genelde severity: "info")
   İŞARETLE: Bir TALEP/işlem var ama onu uygulamak için zorunlu bilgi eksik (örn. tarih, süre, adet, kişi, gerekçe belirtilmeden onay/işlem isteniyor).
   İŞARETLEME: Salt bilgilendirme yazısının "eksik" sayılması; tahmini eksiklikler.

### ÇIKTI KURALLARI (kesin)
- Her bulgunun "found_text" alanı, METİN bölümünden BİREBİR (kelimesi kelimesine) kopyalanmış bir parça olmalı. Uydurma/parafraz YASAK — alıntılayamadığın bulguyu hiç yazma.
- Biçimsel sorunlara (noktalama, büyük harf, boşluk, font) DEĞİNME.
- Aynı sorunu iki kez yazma. En fazla 6 bulgu.
- "description" kısa ve öz olsun (≤200 karakter). Uzun açıklama yazma.
- Gerçek sorun yoksa: {{"findings": []}}
- confidence: gerçekçi ver. Çok eminsen 0.85–0.95; makul şüphedeysen 0.6–0.8; 0.55 altını EKLEME.

### ÖRNEKLER

Örnek A — konu "İzin Talebi", metin tamamen bütçe ek ödeneğinden bahsediyor:
{{"findings": [{{"category": "konu_metin", "severity": "warning", "title": "Konu metnin içeriğiyle örtüşmüyor", "description": "Konu 'İzin Talebi' iken metin yıllık ek bütçe ödeneği talebini anlatıyor; konu metnin amacını yansıtmıyor.", "found_text": "2025 yılı laboratuvar giderleri için ek ödenek talep edilmektedir", "suggestion": "Konu satırını metnin gerçek amacıyla eşleştirin.", "suggested_text": "Ek Ödenek Talebi", "confidence": 0.9}}]}}

Örnek B — temiz, tutarlı bir yazı:
{{"findings": []}}

### YANIT FORMATI
SADECE şu yapıda geçerli JSON döndür (başka metin yok):
{{"findings": [
  {{"category": "konu_metin|mantiksal|anlatim|belge_yeterlilik", "severity": "error|warning|info", "title": "≤70 karakter", "description": "somut açıklama: hangi metin, neden sorunlu", "found_text": "metinden birebir alıntı (≤140 karakter)", "suggestion": "kısa düzeltme tavsiyesi", "suggested_text": "yeniden yazım önerisi (yalnızca anlatim/konu_metin; yoksa null)", "confidence": 0.8}}
]}}"""

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

        # JSON mode: response_format ile geçerli JSON garanti edilir → parse hatası olmaz.
        completion = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=_MAX_OUTPUT_TOKENS,
            temperature=_TEMPERATURE,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content

    def _call_gemini(self, prompt: str) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "google-genai paketi kurulu değil. Yüklemek için: pip install google-genai"
            ) from exc

        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)

        # JSON mode + system instruction + düşük sıcaklık → tutarlı, geçerli JSON.
        # thinking_budget: Gemini 2.5'te düşünme token'larını sınırlar; aksi halde
        # tüm max_output_tokens payını yer ve JSON yanıtı kesilir (boş bulgu).
        cfg_kwargs = dict(
            system_instruction=_SYSTEM_PROMPT,
            temperature=_TEMPERATURE,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
        )
        try:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=_THINKING_BUDGET)
        except Exception:  # eski SDK / desteklemeyen model — düşünme sınırı atlanır
            pass

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(**cfg_kwargs),
        )
        text = response.text
        if not text:
            # Güvenlik filtresi/MAX_TOKENS gibi durumlarda text boş olabilir;
            # aday parçalarından metni toparlamayı dene.
            try:
                parts = response.candidates[0].content.parts
                text = "".join(getattr(p, "text", "") or "" for p in parts)
            except Exception:
                text = ""
        return text or ""

    # ── LLM yanıtı ayrıştırma ───────────────────────────────────────────────

    def _parse_llm_response(self, raw: str, haystack: str = "") -> list[Finding]:
        """LLM JSON yanıtını Finding listesine dönüştürür ve kanıt doğrulaması yapar."""
        items = _extract_findings(raw)
        if items is None:
            logger.warning("Katman C: LLM yanıtından JSON çıkarılamadı — yanıt: %s", raw[:300])
            return []

        norm_haystack = _normalize_for_match(haystack)

        findings: list[Finding] = []
        seen_keys: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue

            confidence = _coerce_confidence(item.get("confidence", 0.7))

            category  = item.get("category", "mantiksal")
            rule_code = _RULE_CODE_MAP.get(category, "SEM-003")
            severity  = _SEVERITY_MAP.get(str(item.get("severity", "warning")).lower(), Severity.WARNING)

            # found_text → found alanına; suggested_text → ayrı alan
            found_text = (item.get("found_text") or "").strip() or None
            suggested  = (item.get("suggested_text") or "").strip() or None
            if suggested and len(suggested) < 5:
                suggested = None

            # ── GROUNDING: alıntı gerçekten belgede var mı? ──
            # Halüsinasyon alıntıları ele; zayıf eşleşmelerde confidence düşür.
            if found_text and len(found_text) >= _GROUNDING_MIN_LEN and norm_haystack:
                overlap = _quote_overlap(found_text, norm_haystack)
                if overlap < _GROUNDING_DROP_BELOW:
                    logger.info(
                        "Katman C: kanıtsız bulgu elendi (örtüşme=%.2f) — '%s'",
                        overlap, found_text[:60],
                    )
                    continue
                if overlap < _GROUNDING_PENALTY_BELOW:
                    confidence = min(confidence, 0.6)

            if confidence < _CONFIDENCE_THRESHOLD:
                continue

            # Yinelenen bulguları (aynı kategori + aynı alıntı) ele
            dedup_key = f"{category}|{(found_text or item.get('title',''))[:80].lower()}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

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
                confidence=round(confidence, 2),
            ))

        return findings


# ── Yanıt ayrıştırma & kanıt doğrulama yardımcıları (modül seviyesi) ──────────

def _extract_findings(raw: str) -> list | None:
    """
    LLM yanıtından bulgu listesini çıkarır. Şu biçimleri destekler:
      • {"findings": [...]}        (JSON mode birincil format)
      • [...]                       (düz dizi — geriye dönük uyum)
      • ```json ... ``` bloğu içinde gömülü
    Çıkaramazsa None döner.
    """
    if not raw:
        return None
    text = raw.strip()

    # Önce doğrudan JSON dene
    for candidate in (text,):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and isinstance(obj.get("findings"), list):
                return obj["findings"]
            if isinstance(obj, list):
                return obj
        except json.JSONDecodeError:
            pass

    # Gömülü nesne {...} veya dizi [...] ara (greedy — kesilmeyi önler)
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match:
        try:
            obj = json.loads(obj_match.group(0))
            if isinstance(obj, dict) and isinstance(obj.get("findings"), list):
                return obj["findings"]
        except json.JSONDecodeError:
            pass

    arr_match = re.search(r"\[.*\]", text, re.DOTALL)
    if arr_match:
        try:
            arr = json.loads(arr_match.group(0))
            if isinstance(arr, list):
                return arr
        except json.JSONDecodeError:
            pass

    # Son çare — kesik/bozuk yanıttan tamamlanmış bulgu nesnelerini kurtar.
    # (Yanıt MAX_TOKENS ile kesilirse en azından tam olanları kullanırız.)
    salvaged = _salvage_objects(text)
    if salvaged:
        logger.info("Katman C: kesik yanıttan %d bulgu kurtarıldı.", len(salvaged))
        return salvaged

    return None


def _salvage_objects(text: str) -> list[dict]:
    """
    Kesik/bozuk JSON metninden dengeli {...} nesnelerini kurtarır.
    İç içe nesneleri de yakalar (dış sarmal kapanmamış olsa bile): her '{' için
    başlangıç konumunu yığına alır, kapanınca o aralığı ayrıştırmayı dener.
    """
    objs: list[dict] = []
    stack: list[int] = []
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            stack.append(i)
        elif ch == "}":
            if stack:
                start = stack.pop()
                chunk = text[start:i + 1]
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                # Sadece bulgu gibi görünen nesneleri al; sarmalı ({"findings":..}) atla
                if isinstance(obj, dict) and "findings" not in obj and (
                    "category" in obj or "title" in obj
                ):
                    objs.append(obj)
    # Yinelenenleri (iç içe yakalama nedeniyle) sırayı koruyarak temizle
    uniq, seen = [], set()
    for o in objs:
        key = json.dumps(o, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            uniq.append(o)
    return uniq


def _coerce_confidence(value: Any) -> float:
    """confidence'ı 0.0–1.0 aralığında güvenli float'a çevirir."""
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.7
    if c > 10.0:       # model 0–100 ölçeği verdiyse (ör. 90) normalize et
        c = c / 100.0
    return max(0.0, min(1.0, c))


def _normalize_for_match(text: str) -> str:
    """Eşleştirme için metni sadeleştirir: küçük harf + tek boşluk + noktalama yok."""
    if not text:
        return ""
    lowered = text.casefold()
    # noktalama ve fazla boşlukları tek boşluğa indir
    return re.sub(r"[^\wçğıöşüâîû]+", " ", lowered, flags=re.UNICODE).strip()


def _quote_overlap(found_text: str, norm_haystack: str) -> float:
    """
    Alıntının belgede ne kadar geçtiğini ölçer (0.0–1.0).
    Önce birebir alt-dize kontrolü; değilse anlamlı kelimelerin örtüşme oranı.
    """
    norm_quote = _normalize_for_match(found_text)
    if not norm_quote:
        return 1.0  # alıntı yoksa grounding uygulanmaz
    if norm_quote in norm_haystack:
        return 1.0
    words = [w for w in norm_quote.split() if len(w) > 2]
    if not words:
        return 1.0
    hay_words = set(norm_haystack.split())
    hits = sum(1 for w in words if w in hay_words)
    return hits / len(words)


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
