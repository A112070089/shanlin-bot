"""Local-only Taiwanese Hanji-to-POJ and optional Mandarin-to-POJ service (port 8004).

Educational/test use only; MLX Taigi-Llama-2 translator and MMS TTS model have
non-commercial licenses. Do not expose to LAN or public internet.
"""
from __future__ import annotations
import logging
import os
import re
import threading
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

app = FastAPI(title="Local Taiwanese Text / POJ", docs_url=None, redoc_url=None)
log = logging.getLogger("taigi_text")
_lock = threading.Lock()
_model = None
_tokenizer = None
_converter = None
_HAN = re.compile(r"[\u3400-\u9fff]")


# DOUBTS-TAIGI-PRONUNCIATION-V1
# 方案: MOE Taiwanese dictionary hong-àn; the user's local converter also confirms it.
# Keep the glossary deliberately small: do not invent medical pronunciations.
PRONUNCIATION_BUILD = "hong-an-v1"
_FIXED_READINGS = {"方案": "hong-àn"}
_TERM_SPLIT = re.compile("(" + "|".join(map(re.escape, _FIXED_READINGS)) + ")")


def _term_parts(source: str) -> list[str]:
    parts = [part for part in _TERM_SPLIT.split(source) if part]
    # Frontend sends short speech chunks. Bound extra model calls on long API inputs.
    if sum(bool(_HAN.search(part)) and part not in _FIXED_READINGS for part in parts) > 8:
        raise HTTPException(422, detail="台語譯稿含過多分段，請分句後再試")
    return parts


def _convert_with_fixed_readings(source: str) -> str:
    if not any(term in source for term in _FIXED_READINGS):
        return _conv().get(source)
    return " ".join(
        _FIXED_READINGS[part] if part in _FIXED_READINGS else
        _conv().get(part) if _HAN.search(part) else part
        for part in _term_parts(source)
    )


def _translate_poj_model(source_text: str) -> str:
    # Protect terms BEFORE generation. Never replace àn-choân globally: it may
    # correctly mean 安全 elsewhere in the same sentence.
    if not any(term in source_text for term in _FIXED_READINGS):
        return _translate_poj_model_raw(source_text)
    parts = []
    for part in _term_parts(source_text):
        if part in _FIXED_READINGS:
            parts.append(_FIXED_READINGS[part])
        elif _HAN.search(part):
            parts.append(_translate_poj_model_raw(part))
        else:
            parts.append(part)
    text = " ".join(parts)
    _check_translation_quality(source_text, text)
    return _verify_poj(text)


def _only_local(request: Request) -> None:
    if not request.client or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, detail="8004 只接受同一台電腦的連線")


def _conv():
    global _converter
    with _lock:
        if _converter is None:
            try:
                from taibun import Converter
                _converter = Converter(system="POJ")
            except Exception as exc:
                raise HTTPException(503, detail="缺少 taibun：請在 8004 專用環境安裝 requirements.txt") from exc
        return _converter


def _verify_poj(raw: str) -> str:
    # Both single-item scripts and translated dialogue must contain pronounceable
    # romanized characters. If unknown Hanji remains, require review rather than
    # producing a misleading or silent MMS audio response.
    text = str(raw).strip()
    if not text or len(text) > 6000 or _HAN.search(text):
        raise HTTPException(422, detail="台語羅馬字不完整，請母語者校稿後再試")
    if not re.search(r"[A-Za-z]", text):
        raise HTTPException(422, detail="沒有有效台語羅馬字")
    return text


class ConvertInput(BaseModel):
    text: str = Field(min_length=1, max_length=1300)


class TranslateInput(BaseModel):
    text: str = Field(min_length=1, max_length=1600)
    target: Literal["POJ"] = "POJ"


@app.get("/health")
def health(request: Request):
    _only_local(request)
    try:
        _conv()
        conv_ready = True
    except HTTPException:
        conv_ready = False
    path = os.getenv("TAIGI_TRANSLATOR_MODEL", "").strip()
    return {
        "ready": conv_ready,
        "romanizer_ready": conv_ready,
        "dynamic_translation_ready": bool(_model is not None),
        "translator_model_configured": bool(path and Path(path).is_dir()),
        "only_local": True,
        "pronunciation_build": PRONUNCIATION_BUILD,
        "notice": "醫療及台語譯稿尚須校對，僅供本機測試",
    }


@app.post("/convert")
def convert(req: ConvertInput, request: Request):
    """Transliterate *Taiwanese-written* Hanji, not Mandarin translation."""
    _only_local(request)
    converted = _convert_with_fixed_readings(req.text)
    try:
        return {"poj": _verify_poj(converted), "kind": "hanji_transliteration_draft"}
    except HTTPException:
        # Some Taiwanese Hanji or medical terms may not exist in the
        # transliterator's dictionary. Only in draft mode, try the local MLX
        # translator instead; the result still needs human medical review.
        if os.getenv("TAIGI_DYNAMIC_DRAFT", "0") != "1":
            raise
        poj = _translate_poj_model(req.text)
        return {"poj": poj, "kind": "unreviewed_translation_fallback"}


def _ensure_translator():
    global _model, _tokenizer
    if _model is not None:
        return
    model_dir = os.getenv("TAIGI_TRANSLATOR_MODEL", "").strip()
    if not model_dir or not Path(model_dir).is_dir():
        raise HTTPException(503, detail="未設定 TAIGI_TRANSLATOR_MODEL 或模型尚未轉成 MLX 4bit")
    try:
        from mlx_lm import load
        _model, _tokenizer = load(model_dir)
    except Exception as exc:
        log.error("MLX translator model load error: %s", type(exc).__name__)
        raise HTTPException(503, detail="台語翻譯模型載入失敗，請查看 8004 Terminal") from exc


@app.post("/warmup")
def warmup(request: Request):
    """Load the local model before an elder uses the web page."""
    _only_local(request)
    with _lock:
        _ensure_translator()
    return {"ready": True, "model_loaded": True}


def _check_translation_quality(source_text: str, output: str) -> None:
    """Fail closed if a model starts repeating rather than translating."""
    normalized = re.sub(r"\s+", " ", str(output)).strip()
    if len(normalized) > max(350, min(4000, len(source_text) * 18)):
        raise HTTPException(422, detail="Translator generated excessive text")
    words = normalized.lower().split()
    for size, threshold in ((4, 4), (6, 3), (9, 3)):
        seen = {}
        for at in range(max(0, len(words) - size + 1)):
            key = tuple(words[at:at+size])
            seen[key] = seen.get(key, 0) + 1
            if seen[key] >= threshold:
                raise HTTPException(422, detail="Translator output repeats phrases")
    # Detect a model endlessly copying full clauses, including no-space output.
    for span in range(20, min(90, len(normalized)//3 + 1)):
        if normalized.endswith(normalized[-span:] * 3):
            raise HTTPException(422, detail="Translator output loops at its end")


@app.post("/translate")
def translate(req: TranslateInput, request: Request):
    _only_local(request)
    if os.getenv("TAIGI_DYNAMIC_DRAFT", "0") != "1":
        raise HTTPException(403, detail="動態台語翻譯只允許本機草稿測試")
    if len(req.text) > 1600:
        raise HTTPException(413, detail="單次台語翻譯文字太長")
    text = _translate_poj_model(req.text)
    return {"poj": text, "kind": "unreviewed_llm_translation", "review_status": "draft"}


def _translate_poj_model_raw(source_text: str) -> str:
    """Run quantized local translator; never call a cloud API."""
    prompt = f"[TRANS]\n{source_text.strip()}\n[/TRANS]\n[POJ]\n"
    with _lock:
        _ensure_translator()
        try:
            from mlx_lm import generate
            # Bound the output to the source length to avoid runaway generation.
            max_tokens = min(420, max(100, int(len(source_text) * 5.3) + 64))
            result = generate(_model, _tokenizer, prompt=prompt,
                              max_tokens=max_tokens, verbose=False)
        except Exception as exc:
            log.error("MLX translator generation error: %s", type(exc).__name__)
            raise HTTPException(503, detail="本機台語翻譯暫時失敗") from exc
    # Reject remaining Mandarin characters, prompts, and unparseable output.
    text = str(result)
    for delimiter in ("[/TRANS]", "[TRANS]", "[ZH]", "[/POJ]", "</s>", "<|endoftext|>"):
        text = text.split(delimiter, 1)[0]
    text = re.sub(r"^\s*\[POJ\]\s*", "", text.strip())
    _check_translation_quality(source_text, text)
    return _verify_poj(text)
