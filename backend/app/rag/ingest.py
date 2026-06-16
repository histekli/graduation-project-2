"""
RAG Döküman Yükleme (Ingest) — v2
Tüm kılavuz/yönerge dökümanlarını chunk'lara ayırıp ChromaDB'ye yükler.

Desteklenen formatlar: .json (TDK), .pdf (pdfplumber), .docx (python-docx)

Kullanım:
  python -m app.rag.ingest                     # data/guidelines/ otomatik tara
  python -m app.rag.ingest /özel/dizin         # özel dizin
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional

import chromadb

# ── Ayarlar ──────────────────────────────────────────────────────────────────
CHROMA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chromadb"
GUIDELINES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "guidelines"
COLLECTION_NAME = "guidelines"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

# ── Dosya adı → kaynak bilgisi eşlemesi ─────────────────────────────────────
# Her giriş: (source_name, source_type)
# source_type değerleri retriever filtreleri ile eşleşmeli
_EXACT_MAP: dict[str, tuple[str, str]] = {
    "tdk_tum_kurallar.json": (
        "TDK Yazım Kılavuzu",
        "tdk_official",
    ),
    "yonetmelik_tam_metin.txt": (
        "Resmi Yazışma Yönetmeliği (2020)",
        "resmi_yazisma_yonetmeligi",
    ),
    "yonetmelik_ek_ornekler.txt": (
        "Resmi Yazışma Yönetmeliği — Ek Örnekler",
        "resmi_yazisma_yonetmeligi",
    ),
}

# Anahtar kelime bazlı eşleme (PDF/DOCX dosyaları için)
_KEYWORD_MAP: list[tuple[list[str], str, str]] = [
    # keywords,  source_name,  source_type
    (["R5", "0030"],
     "GTU YÖ-0030 R5 Yazışma Yönergesi",
     "gtu_yonerge"),
    (["Yönetmelik", "Usul ve Esaslar"],
     "Resmi Yazışma Yönetmeliği (2020)",
     "resmi_yazisma_yonetmeligi"),
    (["Cumhurba"],   # Cumhurbaşkanlığı
     "CB Resmi Yazışma Kılavuzu 2025",
     "cb_kilavuzu"),
    (["Dilekçe", "3071"],
     "Dilekçe Hakkı Kanunu (3071)",
     "dilekce_kanunu"),
]


def _detect_source_info(path: Path) -> tuple[str, str] | None:
    """Dosya adından (source_name, source_type) çifti döner; tanınmazsa None."""
    # 1. Tam eşleme
    if path.name in _EXACT_MAP:
        return _EXACT_MAP[path.name]

    # 2. Eski R0 .docx → atla (R5 PDF birincil)
    if path.suffix.lower() == ".docx":
        return None

    # 3. Anahtar kelime eşlemesi (PDF'ler)
    if path.suffix.lower() == ".pdf":
        for keywords, source_name, source_type in _KEYWORD_MAP:
            if all(kw in path.name for kw in keywords):
                return source_name, source_type

    # .txt dosyaları _EXACT_MAP üzerinden zaten eşlendi; eşleşme yoksa atla
    return None


# ── Metin parçalama ───────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Metni paragraf sınırlarına saygı göstererek chunk'lara ayırır.

    İki geçiş:
    1. Önce çift satır sonu (\\n\\n) ile büyük bölümlere ayır.
    2. Büyük bölümler hâlâ chunk_size'ı aşıyorsa tek satır sonlarına (\\n) göre
       daha küçük parçalara böl. Bu, TDK'nın dev "Noktalama İşaretleri" bölümü
       gibi \\n\\n içermeyen uzun metinleri doğru biçimde işler.
    """
    # 1. geçiş: çift satır sonlarına göre bölümle
    coarse = re.split(r'\n\s*\n', text)

    # 2. geçiş: chunk_size'ı aşan bölümleri tek satır sonlarına göre böl
    units: list[str] = []
    for block in coarse:
        block = block.strip()
        if not block:
            continue
        if len(block) > chunk_size:
            for line in block.split('\n'):
                line = line.strip()
                if line:
                    units.append(line)
        else:
            units.append(block)

    # Birimlerden chunk'lar oluştur
    chunks: list[str] = []
    current = ""

    for unit in units:
        if len(current) + len(unit) + 2 > chunk_size and current:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap and len(current) > overlap else ""
            current = (tail + "\n\n" + unit).strip() if tail else unit
        else:
            current = (current + "\n\n" + unit).strip() if current else unit

    if current.strip():
        chunks.append(current.strip())

    return chunks


# ── Format-spesifik ingest fonksiyonları ─────────────────────────────────────

def ingest_tdk_json(filepath: str | Path) -> list[dict]:
    """TDK Yazım Kuralları JSON'ını chunk'lara ayırır."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Kural içermeyen bölümleri atla:
    # SUNUŞ → yalnızca tarihsel giriş metni, kural yok (21 KB boş gürültü)
    # Kısaltmalar Dizini → sembol tablosu, aranabilir kural değil
    _SKIP_SECTIONS = {"SUNUŞ", "Kısaltmalar Dizini"}

    documents: list[dict] = []
    for title, content in data.items():
        if title in _SKIP_SECTIONS or not content or len(str(content)) < 20:
            continue
        content_str = str(content).strip()
        chunks = _chunk_text(content_str)
        for i, chunk in enumerate(chunks):
            documents.append({
                "id": f"tdk_{title.replace(' ', '_')[:40]}_{i:03d}",
                "text": chunk,
                "metadata": {
                    "source": "TDK Yazım Kılavuzu",
                    "source_type": "tdk_official",
                    "section": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                },
            })
    return documents


def ingest_pdf(filepath: str | Path, source_name: str, source_type: str) -> list[dict]:
    """pdfplumber ile PDF'ten metin çıkarıp madde bazlı chunk'lara ayırır."""
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber gerekli: pip install pdfplumber")

    filepath = Path(filepath)
    pages_text: list[str] = []

    with pdfplumber.open(str(filepath)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text and text.strip():
                pages_text.append(text)

    full_text = "\n\n".join(pages_text)
    if not full_text.strip():
        print(f"    ⚠ Metin çıkarılamadı (taranmış PDF?): {filepath.name}")
        return []

    return ingest_plain_text(full_text, source_name, source_type)


def ingest_docx(filepath: str | Path, source_name: str, source_type: str) -> list[dict]:
    """python-docx ile .docx'ten metin çıkarıp chunk'lar."""
    from docx import Document
    doc = Document(str(filepath))
    full_text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return ingest_plain_text(full_text, source_name, source_type)


def ingest_plain_text(text: str, source_name: str, source_type: str) -> list[dict]:
    """Düz metni madde numaralarına göre bölümleyip chunk'lara ayırır."""
    # Madde numaralarına göre bölümlere ayırmayı dene
    sections = re.split(r'(?=\bMadde\s+\d+)', text)
    if len(sections) < 3:
        sections = [text]

    documents: list[dict] = []
    for sec_idx, section in enumerate(sections):
        section = section.strip()
        if not section or len(section) < 30:
            continue
        madde_match = re.match(r'Madde\s+(\d+)', section)
        madde_no = madde_match.group(0) if madde_match else f"Bölüm {sec_idx + 1}"

        chunks = _chunk_text(section)
        for i, chunk in enumerate(chunks):
            doc_id = f"{source_type}_{madde_no.replace(' ', '_')}_{i:03d}"
            # ID çakışmasını önle
            if sec_idx > 0:
                doc_id = f"{source_type}_{madde_no.replace(' ', '_')}_s{sec_idx}_{i:03d}"
            documents.append({
                "id": doc_id,
                "text": chunk,
                "metadata": {
                    "source": source_name,
                    "source_type": source_type,
                    "section": madde_no,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                },
            })
    return documents


# ── Dizin otomatik tarama ────────────────────────────────────────────────────

def auto_ingest_directory(guidelines_dir: Path) -> list[dict]:
    """Dizindeki tüm tanınan dosyaları yükler, sonuç döner."""
    all_docs: list[dict] = []

    candidates = sorted(guidelines_dir.iterdir())
    for path in candidates:
        if path.name.startswith(".") or path.is_dir():
            continue

        info = _detect_source_info(path)
        if info is None:
            print(f"    ↷ atlandı: {path.name}")
            continue

        source_name, source_type = info
        print(f"    → yükleniyor: {path.name}")
        try:
            if path.suffix.lower() == ".json":
                docs = ingest_tdk_json(path)
            elif path.suffix.lower() == ".pdf":
                docs = ingest_pdf(path, source_name, source_type)
            elif path.suffix.lower() == ".docx":
                docs = ingest_docx(path, source_name, source_type)
            elif path.suffix.lower() == ".txt":
                text = path.read_text(encoding="utf-8")
                docs = ingest_plain_text(text, source_name, source_type)
            else:
                continue

            all_docs.extend(docs)
            print(f"    ✓ {source_name}: {len(docs)} chunk")
        except Exception as exc:  # noqa: BLE001
            print(f"    ✗ {path.name}: {exc}")

    return all_docs


# ── Embedding ────────────────────────────────────────────────────────────────
# Embedding sağlayıcıları app.rag.embeddings içinde tanımlıdır. SimpleHashEmbedding
# yalnızca fallback'tir; varsayılan SentenceTransformerEmbedding (multilingual-e5).
from app.rag.embeddings import (  # noqa: E402  (geriye dönük import yolu için)
    SimpleHashEmbedding,
    SentenceTransformerEmbedding,
    get_embedding_provider,
)


def read_collection_embedding_model(persist_dir: str | Path) -> str | None:
    """Var olan koleksiyonun metadata'sındaki embedding model adını döndürür (yoksa None)."""
    try:
        client = chromadb.PersistentClient(path=str(persist_dir))
        col = client.get_collection(COLLECTION_NAME)
        meta = col.metadata or {}
        return meta.get("embedding_model")
    except Exception:
        return None


# ── ChromaDB koleksiyon yönetimi ─────────────────────────────────────────────

def build_collection(
    documents: list[dict],
    persist_dir: str | Path | None = None,
    provider=None,
) -> chromadb.Collection:
    """
    Koleksiyonu oluşturur veya mevcut olanı temizleyip günceller.

    Embedding modeli koleksiyon metadata'sına ("embedding_model") yazılır. Mevcut
    koleksiyon FARKLI bir modelle oluşturulmuşsa (boyut/uzay uyumsuz olabilir)
    koleksiyon silinip yeniden yaratılır. Aksi halde get_or_create + clear + upsert
    kullanılır; böylece koleksiyonun UUID'si korunur ve çalışan server süreçleri
    yeniden başlatılmadan güncellemeyi görür.
    """
    client = (
        chromadb.PersistentClient(path=str(persist_dir))
        if persist_dir
        else chromadb.Client()
    )

    embedding_fn = provider or get_embedding_provider()
    model_name = embedding_fn.name()
    col_metadata = {
        "description": "GTU resmi yazışma kılavuz ve yönergeleri",
        "embedding_model": model_name,
        "embedding_dim": getattr(embedding_fn, "dim", 384),
    }

    # Model değiştiyse eski koleksiyonu sil (vektör uzayı uyumsuz) — yeniden yarat.
    try:
        existing = client.get_collection(COLLECTION_NAME)
        prev_model = (existing.metadata or {}).get("embedding_model")
        if prev_model is not None and prev_model != model_name:
            print(f"    ⟳ embedding modeli değişti ({prev_model} → {model_name}); "
                  f"koleksiyon yeniden oluşturuluyor")
            client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # koleksiyon yok — get_or_create yaratacak

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata=col_metadata,
        embedding_function=embedding_fn,
    )
    # get_or_create var olan koleksiyonun metadata'sını güncellemez; modeli yaz.
    try:
        collection.modify(metadata=col_metadata)
    except Exception:
        pass

    # Mevcut tüm dökümanları temizle (UUID değişmez)
    existing_ids = collection.get(include=[])["ids"]
    if existing_ids:
        batch_size = 100
        for i in range(0, len(existing_ids), batch_size):
            collection.delete(ids=existing_ids[i:i + batch_size])

    # Tekrarlanan ID'leri filtrele
    seen_ids: set[str] = set()
    unique_docs: list[dict] = []
    for d in documents:
        if d["id"] not in seen_ids:
            seen_ids.add(d["id"])
            unique_docs.append(d)

    # Yeni dökümanları ekle
    batch_size = 100
    for i in range(0, len(unique_docs), batch_size):
        batch = unique_docs[i:i + batch_size]
        collection.add(
            ids=[d["id"] for d in batch],
            documents=[d["text"] for d in batch],
            metadatas=[d["metadata"] for d in batch],
        )

    return collection


# ── Ana ingest fonksiyonu ────────────────────────────────────────────────────

def run_ingest(
    data_dir: str | Path | None = None,
    persist_dir: str | Path | None = None,
    # Legacy parametreler (geriye dönük uyumluluk)
    tdk_json_path: str | Path | None = None,
    yonerge_docx_path: str | Path | None = None,
    extra_texts: list[tuple[str, str, str]] | None = None,
) -> dict:
    """
    Tüm kaynakları işleyip ChromaDB'ye yükler.

    data_dir verilirse data_dir/guidelines/ otomatik taranır.
    Verilmezse legacy parametreler kullanılır.

    Returns:
        {"total_chunks": int, "sources": {name: count}, "persist_dir": str}
    """
    all_docs: list[dict] = []

    if data_dir is not None:
        # Yeni davranış: dizin otomatik tarama
        g_dir = Path(data_dir) / "guidelines"
        if g_dir.exists():
            all_docs.extend(auto_ingest_directory(g_dir))
        else:
            print(f"  ⚠ guidelines dizini bulunamadı: {g_dir}")
    else:
        # Legacy davranış
        if tdk_json_path and Path(tdk_json_path).exists():
            docs = ingest_tdk_json(tdk_json_path)
            all_docs.extend(docs)
            print(f"  ✓ TDK Yazım Kuralları: {len(docs)} chunk")

        if yonerge_docx_path and Path(yonerge_docx_path).exists():
            docs = ingest_docx(
                yonerge_docx_path,
                "GTU YÖ-0030 R5 Yazışma Yönergesi",
                "gtu_yonerge",
            )
            all_docs.extend(docs)
            print(f"  ✓ GTU Yönerge: {len(docs)} chunk")

        if extra_texts:
            for text, name, stype in extra_texts:
                docs = ingest_plain_text(text, name, stype)
                all_docs.extend(docs)
                print(f"  ✓ {name}: {len(docs)} chunk")

    if not all_docs:
        print("  ⚠ Hiç döküman bulunamadı!")
        return {"total_chunks": 0, "sources": {}, "persist_dir": str(persist_dir or CHROMA_DIR)}

    p_dir = persist_dir or CHROMA_DIR
    build_collection(all_docs, persist_dir=p_dir)

    stats: dict = {"total_chunks": len(all_docs), "sources": {}, "persist_dir": str(p_dir)}
    for d in all_docs:
        src = d["metadata"]["source"]
        stats["sources"][src] = stats["sources"].get(src, 0) + 1

    return stats


# ── CLI giriş noktası ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("═" * 60)
    print("  RAG Veritabanı Oluşturucu v2")
    print("═" * 60)

    base = Path(__file__).resolve().parent.parent.parent
    custom_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    if custom_dir:
        print(f"\nÖzel dizin: {custom_dir}\n")
        stats = run_ingest(data_dir=str(custom_dir))
    else:
        print(f"\nVarsayılan dizin: {base / 'data'}\n")
        stats = run_ingest(data_dir=str(base / "data"))

    print(f"\n{'─' * 60}")
    print(f"  TOPLAM: {stats['total_chunks']} chunk → {stats['persist_dir']}")
    print(f"{'─' * 60}")
    print("\nKaynak dağılımı:")
    for src, count in sorted(stats["sources"].items(), key=lambda x: -x[1]):
        print(f"  {src:<45} {count:>4} chunk")
