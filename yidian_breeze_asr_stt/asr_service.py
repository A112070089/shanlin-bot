"""Local-only Breeze-ASR-26 / MLX Taiwanese Hokkien STT service on 127.0.0.1:8003.

Do not publicly expose this prototype. Audio is deleted immediately after transcription.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

MODEL_ID = "doggy8088/Breeze-ASR-26-MLX-4bit"
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 25

app = FastAPI(title="Yidian Taigi STT local evaluation service")
_infer_lock = threading.Lock()
_model_used = False


class Health(BaseModel):
    status: str
    model_id: str
    ffmpeg_ready: bool
    mlx_whisper_ready: bool
    model_loaded_once: bool
    privacy: str


@app.get("/health", response_model=Health)
def health():
    return Health(
        status="ok", model_id=MODEL_ID,
        ffmpeg_ready=shutil.which("ffmpeg") is not None,
        mlx_whisper_ready=importlib.util.find_spec("mlx_whisper") is not None,
        model_loaded_once=_model_used,
        privacy="Audio processed locally; temporary recordings removed after each request",
    )


def _inference(blob: bytes) -> str:
    global _model_used
    with _infer_lock:
        import mlx_whisper
        with tempfile.TemporaryDirectory(prefix="yidian_taigi_stt_") as folder:
            original = Path(folder) / "captured.audio"
            wavfile = Path(folder) / "clip.wav"
            original.write_bytes(blob)
            cmd = [
                "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
                "-i", str(original), "-t", str(MAX_SECONDS),
                "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le", str(wavfile),
            ]
            try:
                subprocess.run(cmd, check=True, timeout=35, capture_output=True)
            except subprocess.TimeoutExpired as exc:
                raise ValueError("音訊轉檔逾時") from exc
            except subprocess.CalledProcessError as exc:
                raise ValueError("無法讀取錄音格式，請重新錄音") from exc
            if not wavfile.exists() or wavfile.stat().st_size <= 44:
                raise ValueError("錄音內容為空")
            # The upstream model emits Mandarin Chinese characters for spoken Taiwanese.
            result = mlx_whisper.transcribe(
                str(wavfile), path_or_hf_repo=MODEL_ID,
                language="zh", task="transcribe", verbose=False,
            )
            _model_used = True
            return str(result.get("text", "")).strip()


@app.post("/transcribe")
async def transcribe(request: Request):
    # Extra layer of defense in addition to binding Uvicorn to 127.0.0.1.
    if not request.client or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="僅允許本機存取")
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="錄音檔案過大")
    blob = await request.body()
    if not blob:
        raise HTTPException(status_code=400, detail="沒有收到錄音內容")
    if len(blob) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="錄音檔案過大")
    if shutil.which("ffmpeg") is None:
        raise HTTPException(status_code=503, detail="找不到 FFmpeg，請先安裝")
    if importlib.util.find_spec("mlx_whisper") is None:
        raise HTTPException(status_code=503, detail="找不到 mlx-whisper 套件")
    try:
        text = await asyncio.to_thread(_inference, blob)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Never log the patient's audio or transcribed text.
        print("Taigi STT error:", type(exc).__name__)
        raise HTTPException(status_code=503, detail="台語辨識未成功；請檢查 8003 終端機的模型下載或載入狀態") from exc
    if not text:
        raise HTTPException(status_code=422, detail="沒有辨識到清楚語音，請重說一次")
    return {"text": text, "language": "nan", "model": MODEL_ID, "needs_confirmation": True}
