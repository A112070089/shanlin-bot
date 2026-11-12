"""Conservative, local-only FastAPI proxy: existing 8000 -> new 8003 MLX ASR.

Does not alter original Mandarin STT / Groq, appointments, payments, or TTS.
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from fastapi import APIRouter, File, HTTPException, UploadFile, Request

router = APIRouter(prefix="/api/taigi_stt", tags=["Taigi local STT prototype"])
UPSTREAM = "http://127.0.0.1:8003"
MAX_BODY_BYTES = 8 * 1024 * 1024


def _enabled() -> bool:
    return os.getenv("TAIGI_STT_ENABLED", "0") == "1"


def _request_json(path: str, blob: bytes | None = None) -> dict:
    url = UPSTREAM + path
    headers = {"Accept": "application/json"}
    method = "GET"
    if blob is not None:
        headers["Content-Type"] = "application/octet-stream"
        method = "POST"
    request = urllib.request.Request(url, data=blob, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=180 if blob is not None else 2.5) as response:
        payload = response.read(8192 if blob is None else 65536)
    return json.loads(payload.decode("utf-8"))


@router.get("/health")
async def health():
    if not _enabled():
        return {"enabled": False, "ready": False, "message": "請使用 TAIGI_STT_ENABLED=1 啟動 8000"}
    try:
        check = await asyncio.to_thread(_request_json, "/health")
        ok = bool(check.get("ffmpeg_ready") and check.get("mlx_whisper_ready"))
        return {"enabled": True, "ready": ok, **check}
    except Exception:
        return {"enabled": True, "ready": False, "message": "8003 台語辨識服務尚未就緒"}


@router.post("/transcribe")
async def transcribe(request: Request, file: UploadFile = File(...)):
    if not request.client or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="僅允許本機存取")
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in ("127.0.0.1", "localhost"):
            raise HTTPException(status_code=403, detail="本機測試只允許本機網頁存取")
    if not _enabled():
        raise HTTPException(status_code=503, detail="台語辨識未啟用，請使用 TAIGI_STT_ENABLED=1")
    try:
        audio = await file.read(MAX_BODY_BYTES + 1)
    finally:
        await file.close()
    if not audio:
        raise HTTPException(status_code=400, detail="沒有收到錄音")
    if len(audio) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="錄音過長或檔案過大")
    try:
        result = await asyncio.to_thread(_request_json, "/transcribe", audio)
        result["needs_confirmation"] = True
        return result
    except urllib.error.HTTPError as exc:
        # Limited and controlled error output, no raw audio or transcript logging.
        try:
            upstream = json.loads(exc.read(2048).decode("utf-8"))
            message = str(upstream.get("detail", "辨識失敗"))[:180]
        except (OSError, ValueError, UnicodeDecodeError):
            message = "辨識失敗"
        raise HTTPException(status_code=exc.code if 400 <= exc.code < 500 else 503, detail=message) from exc
    except Exception as exc:
        print("Taigi STT proxy error:", type(exc).__name__)
        raise HTTPException(status_code=503, detail="無法連接 8003 台語辨識服務") from exc
