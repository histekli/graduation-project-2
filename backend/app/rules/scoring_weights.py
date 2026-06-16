"""
Uyum Skoru Ağırlıkları (EKSIK 2).

Eski skor formülü `max(0, 100 − HATA×10 − UYARI×5 − BİLGİ×2)` yalnızca önem
(severity) düzeyine bakıyordu; bu yüzden tek bir font hatası (FMT-001) ile bir
hiyerarşi hatası (HIR-001) — biri ERROR diğeri WARNING olduğu için — savunulamaz
biçimde ters ağırlanabiliyordu. Ayrıca ceza sınırsızdı (yeterince bulguda skor
hep 0).

Bu modül cezayı **kural koduna** göre ağırlıklandırır ve skoru **oransal**
(0–100, doygunluk tabanlı) hesaplar.

Formül:
    skor = 100 × max(0, 1 − toplam_ağırlıklı_ceza / DOYGUNLUK_CEZASI)

────────────────────────────────────────────────────────────────────────────
AĞIRLIKLARIN KAYNAĞI (dürüst kalibrasyon notu)
────────────────────────────────────────────────────────────────────────────
Ağırlıklar, kuralların belgenin **hukuki/kurumsal geçerliliğine** etkisine göre
[yazar tarafından] üç kategoride atanmıştır. Henüz uzman anketi veya hata-frekans
analizi yapılmadığından sayısal değerler kategoriktir; ileride uzman görüşü ya da
gerçek belge hata istatistikleriyle kalibre edilmesi planlanmaktadır. Uydurma bir
literatür referansı verilmemiştir.

Kategoriler:
  • KRİTİK (20): Belgeyi geçersiz/yanlış kılan ihlaller — eksik zorunlu alan,
                 yanlış hiyerarşik kapanış, hatalı/yasaklı onay-kapanış ifadesi.
  • ORTA   (8) : Biçimsel ve içeriksel uyumsuzluklar — font, marj, konu-metin
                 tutarlılığı, ek tutarlılığı, mantıksal tutarlılık.
  • DÜŞÜK  (2) : Kozmetik / dilbilgisi / bilgilendirme — noktalama, boşluk,
                 anlatım pürüzü, tekrar, bilgilendirici hiyerarşi tespitleri.

Severity'den BAĞIMSIZ olması bilinçlidir: HIR-001 önem düzeyi "warning" olsa bile
KRİTİK ağırlık taşır; FMT-001 önem düzeyi "error" olsa bile ORTA ağırlık taşır.
"""
from __future__ import annotations

from app.models.finding import Severity

# Kategori ağırlıkları
KRITIK = 20
ORTA = 8
DUSUK = 2

# Skorun 0'a indiği doygunluk eşiği: 100 ağırlıklı ceza puanı belgenin tümüyle
# uyumsuz sayıldığı noktadır (≈ 5 kritik ihlal veya eşdeğeri). Oransal formülün
# paydası budur; cezayı sınırlandırıp skoru 0–100 aralığında tutar.
DOYGUNLUK_CEZASI = 100

# ── Kural kodu → ağırlık ─────────────────────────────────────────────────────
RULE_WEIGHTS: dict[str, int] = {
    # ── KRİTİK: belgeyi geçersiz/yanlış kılar ──
    "FLD-001": KRITIK,  # T.C. başlığı eksik
    "FLD-002": KRITIK,  # Üniversite adı eksik
    "FLD-003": KRITIK,  # Birim adı eksik
    "FLD-004": KRITIK,  # Sayı eksik
    "FLD-005": KRITIK,  # Tarih eksik/hatalı
    "FLD-006": KRITIK,  # Konu eksik
    "FLD-007": KRITIK,  # İmza bloğu eksik
    "HIR-001": KRITIK,  # Üst makama yanlış kapanış (severity 'warning' olsa da kritik)
    "CLS-001": KRITIK,  # Kapanış ifadesi eksik
    "CLS-002": KRITIK,  # Yasaklı kapanış ifadesi
    "CLS-003": KRITIK,  # Yanlış onay ifadesi (OLUR olmalı)

    # ── ORTA: biçimsel / içeriksel uyumsuzluk ──
    "FMT-001": ORTA,    # Font (severity 'error' olsa da orta — okunabilirliği bozmaz)
    "FMT-002": ORTA,    # Marj
    "SEM-001": ORTA,    # Konu-metin uyumsuzluğu
    "SEM-002": ORTA,    # Ek-metin tutarsızlığı
    "SEM-003": ORTA,    # Mantıksal tutarsızlık
    "SEM-005": ORTA,    # Belge yeterliliği
    "HIR-003": ORTA,    # İlgi sıralaması hatalı

    # ── DÜŞÜK: kozmetik / dilbilgisi / bilgilendirme ──
    "LNG-001": DUSUK, "LNG-002": DUSUK, "LNG-003": DUSUK, "LNG-004": DUSUK,
    "LNG-005": DUSUK, "LNG-006": DUSUK, "LNG-007": DUSUK, "LNG-008": DUSUK,
    "SEM-004": DUSUK,   # Anlatım bozukluğu (stilistik)
    "SEM-006": DUSUK,   # Tekrar eden ifade (stilistik)
    "HIR-002": DUSUK,   # Yetki devri tespiti (bilgilendirme)
    "HIR-004": DUSUK,   # Dağıtım Gereği/Bilgi ayrımı (bilgilendirme)
    "HIR-005": DUSUK,   # Hiyerarşi atlama (bilgilendirme)
}

# Haritada olmayan kodlar için önem düzeyine göre makul varsayılan
_DEFAULT_BY_SEVERITY: dict[Severity, int] = {
    Severity.ERROR:   ORTA,
    Severity.WARNING: DUSUK + 2,
    Severity.INFO:    DUSUK,
}


def weight_for(rule_code: str, severity: Severity) -> int:
    """Bir kural kodunun ağırlığını döndürür; bilinmiyorsa severity'ye düşer."""
    if rule_code in RULE_WEIGHTS:
        return RULE_WEIGHTS[rule_code]
    return _DEFAULT_BY_SEVERITY.get(severity, ORTA)


def compute_compliance_score(findings) -> int:
    """
    Ağırlıklı, oransal uyum skoru (0–100, tam sayı).

        skor = 100 × max(0, 1 − Σ ağırlık / DOYGUNLUK_CEZASI)

    Monotoniktir: her ek bulgu cezayı artırır → skor azalır (0'da doygunlaşır).
    """
    total_penalty = sum(weight_for(f.rule_code, f.severity) for f in findings)
    ratio = total_penalty / DOYGUNLUK_CEZASI
    score = 100.0 * max(0.0, 1.0 - ratio)
    return int(round(score))


def legacy_compliance_score(errors: int, warnings: int, infos: int) -> int:
    """Eski formül — yalnızca karşılaştırma scripti/testleri için saklanır."""
    return max(0, 100 - errors * 10 - warnings * 5 - infos * 2)
