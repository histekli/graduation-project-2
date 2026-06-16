"""
Türkçe-duyarlı metin işleme yardımcıları.

Python'un yerleşik ``str.lower()`` / ``str.upper()`` metotları Türkçe'nin
nokta'lı/noktasız "i" ayrımını YANLIŞ işler. Latin alfabesinde 'I' harfinin
küçüğü 'i' kabul edilir; Türkçe'de ise:

    Büyük   Küçük
    ──────  ──────
      I  →    ı      (noktasız)
      İ  →    i      (noktalı)

Örnekler (yerleşik metotlarla HATALI sonuç):
    "İLGİ".lower()   → "i̇lgi"   (i + birleşik nokta — bozuk karşılaştırma)
    "ılık".upper()   → "ILIK"    (doğru görünür ama  "ilik".upper() → "ILIK" beklenenden farklı)
    "Bilgi".upper()  → "BILGI"   ("BİLGİ" olması gerekirdi)

Bu modül Türkçe locale kurallarına uygun, locale'den bağımsız (yalnızca ``re``
kullanan) dönüşüm sağlar. Tüm metin KARŞILAŞTIRMALARINDA (LNG kuralları, kapanış
tespiti, parser bölüm tespiti, RAG metin normalizasyonu) bu yardımcılar
``str.lower()`` / ``str.upper()`` yerine kullanılmalıdır.

Ayrıca Türkçe'nin sondan eklemeli (agglutinative) yapısı nedeniyle sabit string
eşleşmesi yetersizdir: "arz ederim", "arz ederiz", "arz edilmektedir", "arz
olunur" hep aynı kapanış ailesindendir. Bu modül kök ("arz" / "rica") + onaylı
fiil gövdesi ("ed-" / "olun-") yaklaşımıyla çekim-toleranslı kapanış tespiti de
sağlar.
"""
from __future__ import annotations

import re
import unicodedata

# ── Büyük/küçük harf dönüşümü ────────────────────────────────────────────────

# Türkçe'ye özgü harfler için açık eşleme. Geri kalan harfler standart
# .lower()/.upper() ile dönüştürülür (bu harfler i/I dışında sorun çıkarmaz).
_TR_LOWER_MAP = {"İ": "i", "I": "ı"}
_TR_UPPER_MAP = {"i": "İ", "ı": "I"}


def tr_lower(text: str) -> str:
    """Türkçe-duyarlı küçük harfe çevirir.

    "İ" → "i", "I" → "ı". Diğer karakterler standart küçük harfe iner.

    >>> tr_lower("İLGİ")
    'ilgi'
    >>> tr_lower("BAŞKANLIK")
    'başkanlık'
    """
    if not text:
        return text
    # Önce Türkçe'ye özgü 'I'/'İ' dönüşümünü uygula; ardından kalanı .lower() ile.
    # Bu sıralama, "İ".lower() → "i̇" (birleşik nokta) bozulmasını engeller.
    out = []
    for ch in text:
        out.append(_TR_LOWER_MAP.get(ch, ch.lower()))
    return "".join(out)


def tr_upper(text: str) -> str:
    """Türkçe-duyarlı büyük harfe çevirir.

    "i" → "İ", "ı" → "I". Diğer karakterler standart büyük harfe çıkar.

    >>> tr_upper("ığdır")
    'IĞDIR'
    >>> tr_upper("bilgi")
    'BİLGİ'
    """
    if not text:
        return text
    out = []
    for ch in text:
        out.append(_TR_UPPER_MAP.get(ch, ch.upper()))
    return "".join(out)


def tr_capitalize(text: str) -> str:
    """İlk harfi Türkçe-duyarlı biçimde büyütür, kalanını olduğu gibi bırakır."""
    if not text:
        return text
    return tr_upper(text[0]) + text[1:]


# ── Normalizasyon (aksan/boşluk) ─────────────────────────────────────────────

# Türkçe karakter → ASCII karşılığı (aksan kaldırma; gevşek karşılaştırma için).
_FOLD_MAP = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a",
    "î": "i", "û": "u",
})


def tr_fold(text: str) -> str:
    """Türkçe metni gevşek karşılaştırma için sadeleştirir.

    Küçük harfe indirir (Türkçe-duyarlı), Türkçe karakterleri ASCII'ye katlar ve
    art arda boşlukları teke indirir. Argo/kısaltma/OCR varyasyonlarını
    eşitlemek için kullanılır (örn. "İ̇ŞLEM" ≈ "islem").
    """
    folded = tr_lower(text).translate(_FOLD_MAP)
    # Birleşik aksan işaretlerini (ör. "i̇") temizle
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", folded).strip()


# ── Çekim-toleranslı kapanış ifadesi tespiti ─────────────────────────────────
#
# Türkçe sondan eklemeli olduğundan kapanış ifadeleri tek bir sabit string
# değildir. "arz" / "rica" kökleri ile "ed-" / "olun-" fiil gövdeleri ve onları
# izleyen serbest ekler tüm aşağıdaki biçimleri kapsar:
#
#   arz ederim · arz ederiz · arz edilmektedir · arz ediyorum · arz olunur
#   rica ederim · rica ederiz · rica olunur · rica edilmektedir
#   arz ve rica ederim · bilgilerinize arz ederim · gereğini rica ederim ...
#
# Onay yazıları için: OLUR · Uygundur · Muvafıktır (tek kelime).

_ARZ_RE = re.compile(
    r"\barz(?:\s+ve\s+rica)?\s+(?:ed|olun)[a-zçğıöşü]*", re.IGNORECASE
)
_RICA_RE = re.compile(
    r"\brica\s+(?:ed|olun)[a-zçğıöşü]*", re.IGNORECASE
)
_APPROVAL_RE = re.compile(r"\b(?:olur|uygundur|muvafıktır)\b", re.IGNORECASE)

# Bir paragrafın kapanış satırı olup olmadığını anlamak için genel kalıp.
CLOSING_PATTERN = re.compile(
    r"(?:"
    r"\b(?:arz(?:\s+ve\s+rica)?|rica)\s+(?:ed|olun)[a-zçğıöşü]*"   # arz/rica + çekim
    r"|\b(?:olur|uygundur|muvafıktır)\b"                            # onay ifadeleri
    r")",
    re.IGNORECASE,
)


def closing_uses_arz(text: str) -> bool:
    """Metin 'arz' köklü (üst makama) bir kapanış içeriyor mu? (çekim-toleranslı)"""
    return bool(_ARZ_RE.search(text or ""))


def closing_uses_rica(text: str) -> bool:
    """Metin 'rica' köklü (alt makama) bir kapanış içeriyor mu? (çekim-toleranslı)"""
    return bool(_RICA_RE.search(text or ""))


def closing_uses_approval(text: str) -> bool:
    """Metin onay kapanışı (OLUR / Uygundur / Muvafıktır) içeriyor mu?"""
    return bool(_APPROVAL_RE.search(text or ""))


def find_closing(text: str) -> re.Match | None:
    """Metindeki ilk kapanış ifadesi eşleşmesini döndürür (yoksa None)."""
    return CLOSING_PATTERN.search(text or "")


def is_closing_line(text: str) -> bool:
    """Bir paragrafın kapanış ifadesi *satırı* olup olmadığını söyler.

    Kapanış ifadeleri cümle/paragraf sonunda yer alır. Bu nedenle gövde
    metnindeki ("arz edilen konular", "rica edilen belgeler" gibi) çekimlerin
    yanlışlıkla kapanış sayılmaması için eşleşmenin paragraf SONUNA yakın
    bitmesi aranır (eşleşmeden sonra yalnızca nokta/boşluk kalmalı).

    >>> is_closing_line("Gereğini arz ederim.")
    True
    >>> is_closing_line("Arz edilen konuların incelenmesi gerekmektedir.")
    False
    """
    t = (text or "").strip()
    if not t:
        return False
    last_end = -1
    for m in CLOSING_PATTERN.finditer(t):
        last_end = m.end()
    if last_end < 0:
        return False
    tail = t[last_end:].strip(" .!?……")
    return tail == ""
