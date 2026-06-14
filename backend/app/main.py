"""
FastAPI Ana Uygulama
Dekanlık Yazışma Uyum Denetleyicisi — Backend API  v0.6.0
"""
from __future__ import annotations
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=False) or ".env")

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from pydantic import BaseModel

import os

from app.models.finding import AnalysisResult
from app.services.pipeline import Pipeline
from app.services.fixer import fix_document
from app.services.layer_c import save_config

app = FastAPI(
    title="Dekanlık Yazışma Uyum Denetleyicisi",
    description="GTU resmi yazışmalarını kontrol eden akıllı asistan API",
    version="0.6.0",
)

_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
]

# CORS_ORIGINS ortam değişkeni ile production origin'leri virgülle eklenebilir
# Örn: CORS_ORIGINS=http://192.168.1.100:3000,https://mydomain.com
_extra = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
_ALLOWED_ORIGINS = list(dict.fromkeys(_DEFAULT_ORIGINS + _extra))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

pipeline = Pipeline()

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ── Yardımcılar ───────────────────────────────────────────────────────────────

def _validate_upload(file: UploadFile, contents: bytes) -> None:
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Sadece .docx dosyaları desteklenmektedir.")
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Dosya boyutu 10 MB'ı aşamaz.")


async def _save_upload(contents: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(contents)
        return tmp.name


# ── Endpointler ───────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "Dekanlık Yazışma Uyum Denetleyicisi",
        "version": "0.6.0",
        "status": "active",
    }


def _probe_layer_c_quota() -> str:
    """Son analiz hatasına bakarak kota durumunu döndürür (API çağrısı yapmaz)."""
    last_err = getattr(pipeline, "_last_layer_c_error", None)
    if last_err and ("429" in last_err or "quota" in last_err.lower()):
        return "quota_exceeded"
    return "ok"


@app.get("/status")
def get_status():
    """
    Tüm katmanların durumunu döndürür.
    Layer C için son analiz hatasını da raporlar (gereksiz API çağrısı yapmadan).
    """
    lc = pipeline.layer_c
    lb = pipeline.layer_b

    c_quota = _probe_layer_c_quota()
    c_active = lc.is_ready and c_quota != "quota_exceeded"

    if not lc.is_ready:
        c_detail = "API anahtarı eksik — GEMINI_API_KEY veya GROQ_API_KEY gerekli"
    elif c_quota == "quota_exceeded":
        c_detail = f"Kota dolmuş — {lc.provider}/{lc.model} (farklı hesap veya gece yarısı sıfırlanır)"
    else:
        c_detail = f"{lc.provider} / {lc.model}"

    return {
        "backend": "ok",
        "version": "0.6.0",
        "layers": {
            "A": {
                "active": True,
                "label": "Deterministik Kural Motoru",
                "detail": "16 kural — her zaman aktif",
            },
            "B": {
                "active": lb is not None,
                "label": "RAG Kontrol",
                "detail": "ChromaDB hazır" if lb else "ChromaDB bulunamadı",
            },
            "C": {
                "active": c_active,
                "quota_state": c_quota,
                "label": "Semantik Analiz (LLM)",
                "provider": lc.provider if lc.is_ready else None,
                "model": lc.model if lc.is_ready else None,
                "detail": c_detail,
            },
        },
    }


class ApiKeyRequest(BaseModel):
    provider: str = "gemini"
    api_key: str
    model: str | None = None


@app.post("/admin/set-api-key")
async def set_api_key(req: ApiKeyRequest):
    """
    API anahtarını kaydeder ve Katman C'yi anında yeniden başlatır.
    Anahtar data/api_config.json dosyasına yazılır (.gitignore'da).
    Restart gerekmez.
    """
    if not req.api_key or len(req.api_key) < 10:
        raise HTTPException(status_code=400, detail="Geçersiz API anahtarı.")
    if req.provider not in ("gemini", "groq"):
        raise HTTPException(status_code=400, detail="Geçersiz sağlayıcı. 'gemini' veya 'groq' olmalı.")

    # Önce test et — geçersiz key'i kaydetme
    test_lc = __import__("app.services.layer_c", fromlist=["LayerC"]).LayerC(
        provider=req.provider, api_key=req.api_key, model=req.model
    )
    try:
        test_lc._call_llm("Test.")
    except Exception as exc:
        msg = str(exc)
        if "429" in msg or "quota" in msg.lower() or "resource_exhausted" in msg.lower():
            # Kota dolmuş ama anahtar geçerli — kaydet
            pass
        elif "401" in msg or "403" in msg or "invalid" in msg.lower() or "api_key" in msg.lower():
            raise HTTPException(status_code=400, detail=f"API anahtarı geçersiz: {msg[:120]}")
        # Diğer hatalar (ağ vb.) — yine de kaydet, kullanıcı bilgilendirilir

    # Kaydet + pipeline'ı hot-reload et
    save_config(req.provider, req.api_key, req.model)
    pipeline.reload_layer_c(provider=req.provider, api_key=req.api_key, model=req.model)

    lc = pipeline.layer_c
    return {
        "ok": True,
        "provider": lc.provider,
        "model": lc.model,
        "active": lc.is_ready,
        "message": f"Katman C güncellendi: {lc.provider}/{lc.model}",
    }


@app.get("/check-api-key")
async def check_api_key():
    """
    Katman C API anahtarının durumunu test eder.
    Son bilinen kota hatası varsa gereksiz API isteği göndermez.
    """
    lc = pipeline.layer_c

    if not lc.is_ready:
        return {
            "ok": False,
            "provider": lc.provider,
            "error": "API anahtarı yapılandırılmamış",
            "error_type": "no_key",
        }

    # Son analiz sırasında kota hatası oluştuysa tekrar istek gönderme
    last_err = getattr(pipeline, "_last_layer_c_error", None)
    if last_err and ("429" in last_err or "quota" in last_err.lower() or "resource_exhausted" in last_err.lower()):
        return {
            "ok": False,
            "provider": lc.provider,
            "model": lc.model,
            "error": "API kotası aşıldı — anahtar geçerli ama istek limiti dolmuş. Farklı Google hesabı veya gece yarısı sıfırlanır.",
            "error_type": "quota_exceeded",
            "tip": "Aynı Google hesabından yeni key oluştursan da kota paylaşılır. Farklı bir Google hesabı oluştur.",
        }

    try:
        test_prompt = "Merhaba. Bu bir bağlantı testidir. Sadece 'OK' yaz."
        response = lc._call_llm(test_prompt)
        pipeline._last_layer_c_error = None  # Başarılı → temizle
        return {
            "ok": True,
            "provider": lc.provider,
            "model": lc.model,
            "response_preview": response[:80] if response else "",
        }
    except Exception as exc:
        msg = str(exc)
        pipeline._last_layer_c_error = msg
        # Kota aşımı → anahtar geçerli ama sınır dolmuş
        if "429" in msg or "quota" in msg.lower() or "resource_exhausted" in msg.lower():
            return {
                "ok": False,
                "provider": lc.provider,
                "model": lc.model,
                "error": "API kotası aşıldı — anahtar geçerli ama istek limiti dolmuş",
                "error_type": "quota_exceeded",
                "tip": "Kota key'e değil Google projesine aittir. Aynı hesaptan yeni key açsan da kota paylaşılır. Çözüm: farklı bir Google hesabıyla aistudio.google.com'dan yeni key al.",
            }
        # Geçersiz anahtar
        if "401" in msg or "403" in msg or "api_key" in msg.lower() or "invalid" in msg.lower():
            return {
                "ok": False,
                "provider": lc.provider,
                "model": lc.model,
                "error": "Geçersiz API anahtarı",
                "error_type": "invalid_key",
            }
        return {
            "ok": False,
            "provider": lc.provider,
            "model": lc.model,
            "error": msg[:200],
            "error_type": "unknown",
        }


@app.post("/analyze", response_model=AnalysisResult)
async def analyze_document(
    file: UploadFile = File(...),
    mode: str = "full",
):
    contents = await file.read()
    _validate_upload(file, contents)
    tmp_path = await _save_upload(contents)
    try:
        return pipeline.analyze(tmp_path, mode=mode, original_filename=file.filename)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analiz hatası: {exc}") from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/analyze-and-fix")
async def analyze_and_fix(
    file: UploadFile = File(...),
    mode: str = "full",
):
    contents = await file.read()
    _validate_upload(file, contents)
    tmp_path = await _save_upload(contents)

    try:
        result = pipeline.analyze(tmp_path, mode=mode, original_filename=file.filename)
        summary = fix_document(
            source_path=tmp_path,
            parsed=result.parsed_document,
            findings=result.findings,
        )
    except Exception as exc:
        Path(tmp_path).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Düzeltme hatası: {exc}") from exc

    def _cleanup():
        Path(tmp_path).unlink(missing_ok=True)
        shutil.rmtree(str(summary.fixed_path.parent), ignore_errors=True)

    original_stem = Path(file.filename or "belge").stem
    download_name = f"{original_stem}_duzeltilmis.docx"

    return FileResponse(
        path=str(summary.fixed_path),
        filename=download_name,
        media_type=_DOCX_MIME,
        background=BackgroundTask(_cleanup),
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}
