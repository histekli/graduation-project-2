"""
Embedding Karşılaştırma Scripti (EKSIK 1 kabul kriteri #1).

Anlamsal (SentenceTransformer / multilingual-e5) embedding ile hash tabanlı
fallback embedding'i, anlamca YAKIN sorgu–doküman çiftleri üzerinde karşılaştırır
ve cosine benzerliklerini sayısal olarak basar.

Çiftler bilinçli olarak DÜŞÜK SÖZCÜKSEL ÖRTÜŞMELİ seçilmiştir: doküman, sorgunun
eş anlamlısı/çekimli yeniden ifadesidir (Türkçe'nin gerçek durumu). Hash embedding
karakter trigram örtüşmesine dayandığından, kelimeler değişince benzerlik sinyali
çöker; anlamsal model bunu öğrenilmiş temsille korur.

Ek olarak her sorgu, tamamen ALAKASIZ (alan dışı) bir cümleye karşı da ölçülür;
böylece her iki yöntemin "gürültü tabanı" görülür.

Beklenti: anlamsal model, ilgili çiftte hash'ten belirgin biçimde YÜKSEK ve
gürültü tabanından net biçimde AYRIK benzerlik üretir.

Çalıştırma:
  cd backend
  python -m scripts.embedding_compare
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from app.rag.embeddings import (  # noqa: E402
    SimpleHashEmbedding,
    SentenceTransformerEmbedding,
)

# (sorgu, anlamca İLGİLİ doküman [farklı kelimelerle], alan dışı İLGİSİZ cümle)
PAIRS: list[tuple[str, str, str]] = [
    (
        "üst makama yazılan yazıda yanlış kapanış ifadesi",
        "Astından üstüne gönderilen belgeler 'Arz ederim' ibaresiyle tamamlanır.",
        "Patatesin haşlanma süresi yaklaşık yirmi dakikadır.",
    ),
    (
        "resmi yazıda yazı tipi ve punto kuralı",
        "Belgeler Times New Roman karakteriyle on iki puntoda hazırlanır.",
        "Yarın sahil kesiminde aralıklı sağanak yağış bekleniyor.",
    ),
    (
        "ilgi satırlarının tarih sırasına göre dizilmesi",
        "İlgi bölümü kronolojik biçimde eskiden yeniye doğru düzenlenir.",
        "Basketbol maçında ev sahibi takım farkla galip geldi.",
    ),
    (
        "dağıtım bölümünde gereği ve bilgi ayrımı",
        "İşlem yapacak birimler Gereği, haberdar edilecekler Bilgi başlığına yazılır.",
        "Akşam yemeği için sebzeli güveç hazırlandı.",
    ),
    (
        "rektör adına yetki devriyle imza",
        "Rektör yerine imzalayan yetkili unvanının üzerine 'Rektör a.' kısaltmasını koyar.",
        "Dağcılık kulübü hafta sonu zirve tırmanışı düzenledi.",
    ),
]


def _cos(a, b) -> float:
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb)) or 1.0
    return float(np.dot(va, vb) / denom)


def _eval(provider) -> dict:
    rel_sims, irr_sims, rows = [], [], []
    for q, rel, irr in PAIRS:
        qv = provider.embed_query(q)
        rv, iv = provider.embed_documents([rel, irr])
        s_rel, s_irr = _cos(qv, rv), _cos(qv, iv)
        rel_sims.append(s_rel)
        irr_sims.append(s_irr)
        rows.append((q[:40], s_rel, s_irr, s_rel - s_irr))
    n = len(PAIRS)
    return {
        "rows": rows,
        "avg_rel": sum(rel_sims) / n,
        "avg_irr": sum(irr_sims) / n,
        "avg_gap": sum(r - i for r, i in zip(rel_sims, irr_sims)) / n,
    }


def _print_block(title: str, res: dict) -> None:
    print(f"\n{'═' * 82}\n  {title}\n{'═' * 82}")
    print(f"  {'Sorgu':<42} {'ilgili':>8} {'alan-dışı':>10} {'ayrım':>8}")
    print(f"  {'-'*42} {'-'*8} {'-'*10} {'-'*8}")
    for q, rel, irr, gap in res["rows"]:
        print(f"  {q:<42} {rel:>8.3f} {irr:>10.3f} {gap:>8.3f}")
    print(f"  {'-'*42} {'-'*8} {'-'*10} {'-'*8}")
    print(f"  {'ORTALAMA':<42} {res['avg_rel']:>8.3f} {res['avg_irr']:>10.3f} {res['avg_gap']:>8.3f}")


def main() -> None:
    print("Embedding karşılaştırması: hash fallback vs. anlamsal (multilingual-e5)")
    print("Çiftler düşük sözcüksel örtüşmelidir (eş anlamlı/çekimli yeniden ifade).")

    hash_res = _eval(SimpleHashEmbedding())
    _print_block("HASH (SimpleHashEmbedding) — anlamsal DEĞİL", hash_res)

    try:
        sem = SentenceTransformerEmbedding()
    except Exception as exc:
        print(f"\n⚠ Anlamsal model yüklenemedi: {exc}")
        print("  (internet/paket eksik) — yalnızca hash sonucu gösterildi.")
        return
    sem_res = _eval(sem)
    _print_block(f"ANLAMSAL ({sem.name()})", sem_res)

    print(f"\n{'═' * 82}\n  ÖZET\n{'═' * 82}")
    print(f"  İlgili çiftte ortalama cosine:   hash={hash_res['avg_rel']:.3f}   "
          f"anlamsal={sem_res['avg_rel']:.3f}   "
          f"(×{sem_res['avg_rel']/max(hash_res['avg_rel'],1e-6):.1f} daha yüksek)")
    print(f"  İlgili / alan-dışı ayrım:        hash={hash_res['avg_gap']:.3f}   "
          f"anlamsal={sem_res['avg_gap']:.3f}")
    win = sum(1 for (_, r, _, _), (_, hr, _, _) in zip(sem_res["rows"], hash_res["rows"]) if r > hr)
    print(f"  Anlamsal modelin ilgili çiftte daha yüksek olduğu sorgu: {win}/{len(PAIRS)}")
    print("\n  → Kelimeler değişse de (Türkçe çekim/eş anlamlı) anlamsal model ilgili")
    print("    maddeye yüksek benzerlik verir; hash embedding sinyali kaybeder.")


if __name__ == "__main__":
    main()
