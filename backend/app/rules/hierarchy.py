"""
GTU Organizasyon Hiyerarşisi
YÖ-0030 R5 ve gtu.edu.tr/organization-schema'dan derlenmiştir.
Hitap, kapanış ifadesi ve imza yetkisi kontrolleri için kullanılır.
"""

# Hiyerarşi seviyeleri (0 = en üst)
HIERARCHY = {
    # Seviye 0: Rektör
    "Rektör": {
        "level": 0,
        "parent": None,
        "can_sign_for": [],
    },
    # Seviye 1: Rektör Yardımcıları
    "Rektör Yardımcısı": {
        "level": 1,
        "parent": "Rektör",
        "can_sign_for": ["Rektör"],  # Rektör yokken
    },
    # Seviye 2: Genel Sekreter, Dekanlar, Enstitü Müdürleri
    "Genel Sekreter": {
        "level": 2,
        "parent": "Rektör",
        "can_sign_for": [],
    },
    "Genel Sekreter Yardımcısı": {
        "level": 3,
        "parent": "Genel Sekreter",
        "can_sign_for": ["Genel Sekreter"],
    },
    "Dekan": {
        "level": 2,
        "parent": "Rektör Yardımcısı",
        "can_sign_for": [],
    },
    "Enstitü Müdürü": {
        "level": 2,
        "parent": "Rektör Yardımcısı",
        "can_sign_for": [],
    },
    "Araştırma Merkezi Müdürü": {
        "level": 2,
        "parent": "Rektör Yardımcısı",
        "can_sign_for": [],
    },
    # Seviye 3: Daire Başkanları, Bölüm Başkanları
    "Daire Başkanı": {
        "level": 3,
        "parent": "Genel Sekreter",
        "can_sign_for": [],
    },
    "Hukuk Müşaviri": {
        "level": 3,
        "parent": "Genel Sekreter",
        "can_sign_for": [],
    },
    "Basın ve Halkla İlişkiler Müdürü": {
        "level": 3,
        "parent": "Genel Sekreter",
        "can_sign_for": [],
    },
    "Bölüm Başkanı": {
        "level": 3,
        "parent": "Dekan",
        "can_sign_for": [],
    },
    "Fakülte Sekreteri": {
        "level": 3,
        "parent": "Dekan",
        "can_sign_for": [],
    },
}

# GTU Fakülteleri
FACULTIES = [
    "Mühendislik Fakültesi",
    "Temel Bilimler Fakültesi",
    "Mimarlık Fakültesi",
    "İşletme Fakültesi",
    "Havacılık ve Uzay Bilimleri Fakültesi",
]

# GTU Enstitüleri
INSTITUTES = [
    "Lisansüstü Eğitim Enstitüsü",
    "Enerji Teknolojileri Enstitüsü",
    "Biyoteknoloji Enstitüsü",
    "Nanoteknoloji Enstitüsü",
    "Yer ve Deniz Bilimleri Enstitüsü",
    "Ulaşım Teknolojileri Enstitüsü",
    "Bilişim Teknolojileri Enstitüsü",
    "Savunma Teknoloji Enstitüsü",
]

# GTU Daire Başkanlıkları
DEPARTMENTS = [
    "Bilgi İşlem Daire Başkanlığı",
    "Kütüphane ve Dokümantasyon Dairesi Başkanlığı",
    "Personel Dairesi Başkanlığı",
    "Sağlık Kültür ve Spor Dairesi Başkanlığı",
    "Öğrenci İşleri Dairesi Başkanlığı",
    "İdari ve Mali İşler Daire Başkanlığı",
    "Strateji Geliştirme Daire Başkanlığı",
    "Yapı İşleri ve Teknik Daire Başkanlığı",
]

# Kapanış ifadesi kuralları (YÖ-0030 R5, Madde 5-e)
# Üst makama → "Arz ederim"
# Alt makama → "Rica ederim"
# Hem üst hem alt → "Arz ve rica ederim"
# Onay yazılarında → "OLUR"
CLOSING_RULES = {
    "upward": [
        "Arz ederim",
        "Bilgilerinize arz ederim",
        "Gereğini arz ederim",
        "Takdirlerinize arz ederim",
        "Uygun görüşle arz ederim",
    ],
    "downward": [
        "Rica ederim",
        "Bilgilerinize rica ederim",
        "Gereğini rica ederim",
    ],
    "mixed": [
        "Arz ve rica ederim",
    ],
    "approval": [
        "OLUR",
    ],
    # Yasaklı ifadeler
    "forbidden": [
        "Saygılarımla arz ederim",
        "Rica olunur",
        "Onay",
        "Uygundur",
        "Muvafıktır",
    ],
}


def get_level(title: str) -> int | None:
    """Unvana göre hiyerarşi seviyesini döndürür."""
    entry = HIERARCHY.get(title)
    return entry["level"] if entry else None


def is_upward(sender_title: str, recipient_title: str) -> bool | None:
    """Gönderenden alıcıya doğru hiyerarşi yönünü belirler.
    True = üst makama yazılıyor, False = alt makama, None = belirlenemedi.
    """
    sender_level = get_level(sender_title)
    recipient_level = get_level(recipient_title)
    if sender_level is None or recipient_level is None:
        return None
    if sender_level > recipient_level:
        return True   # üst makama
    elif sender_level < recipient_level:
        return False  # alt makama
    return None  # eşit seviye


def get_valid_closings(sender_title: str, recipient_title: str) -> list[str]:
    """Gönderen-alıcı ilişkisine göre geçerli kapanış ifadelerini döndürür."""
    direction = is_upward(sender_title, recipient_title)
    if direction is True:
        return CLOSING_RULES["upward"]
    elif direction is False:
        return CLOSING_RULES["downward"]
    return CLOSING_RULES["upward"] + CLOSING_RULES["downward"] + CLOSING_RULES["mixed"]
