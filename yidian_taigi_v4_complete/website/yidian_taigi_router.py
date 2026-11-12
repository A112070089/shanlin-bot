"""FastAPI port 8000 proxy to localhost:8002, limited to predetermined demo scripts.
Do NOT enable on public service. Requires TAIGI_TTS_ENABLED=1.
"""
import asyncio
import io
import wave
import json
import os
import urllib.error
import urllib.request
from functools import lru_cache
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/taigi_tts", tags=["Taigi local TTS demo"])
LOCAL_TTS = "http://127.0.0.1:8002"
LOCAL_POJ = "http://127.0.0.1:8004"

# Prototype only. These POJ/Tai-lo-style scripts require native-speaker and clinical review.
# No patient data is forwarded; the client selects a fixed phrase_id.
PHRASES = {
    "hello": "Lí hó, to-siā lí.",
    # Taiwanese readings for fixed conversation prompts. Draft pronunciation,
    # to be reviewed with a native speaker before any clinical deployment.
    "intro_budget": (
        "Lí hó. Lí ê ki-pún tsu-liāu í-king khak-jīn uân-sîng.",
        "Tsiap-lo̍h-lâi, tshiánn lí siat-tīng tsū-huì kiān-khong kiám-tsa ê ī-suàn.",
        "Guá ē àn-tsiàu lí ê su-iàu, pang-tsān lí suán-tsi̍k kiám-tsa hāng-bo̍k.",
        "Tshiánn lí siuⁿ-khòaⁿ beh ī-suàn kuí-tsē tsînn, pí-lū sann-tshing kho͘."
    ),
    "intro_options": (
        "Lí hó. Lí ê ki-pún tsu-liāu í-king khak-jīn uân-sîng.",
        "Tsiap-lo̍h-lâi, guá ē-tàng pang lí liáu-kái kah suán-tsi̍k tsū-huì kiān-khong kiám-tsa ê hāng-bo̍k.",
        "Lí beh khòaⁿ tsit-ê hāng-bo̍k--bô?"
    ),
    "health_category": (
        "Lí khah kuan-sim tó tsi̍t hāng ê kiān-khong būn-tê?",
        "Tshiánn suán tsi̍t ê, guá ē kā lí lia̍t tshut ha̍p-sik ê kiám-tsa."
    ),
    "lipid": "Tsit hāng kiám-tsa sī thiu-hueh, khòaⁿ hueh lāi ê iû-tsi. Kiám-tsa ê kiat-kó, tshing kā i-su thó-lūn.",
    "ecg": "Sim-tiān-tô sī kiám-tsa sim-tsōng ê tiān-khì sìn-hō. Kiám-tsa kiat-kó, tshing kā i-su thó-lūn.",
}


def enabled():
    return os.getenv("TAIGI_TTS_ENABLED", "0") == "1"


def _get_health():
    with urllib.request.urlopen(LOCAL_TTS + "/health", timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


@router.get("/health")
async def health():
    if not enabled():
        return {"ready": False, "enabled": False, "message": "僅供本機測試，需設定 TAIGI_TTS_ENABLED=1"}
    try:
        upstream = await asyncio.to_thread(_get_health)
        return {"ready": True, "enabled": True, "engine": upstream.get("engine")}
    except Exception:
        return {"ready": False, "enabled": True, "message": "8002 台語 TTS 服務尚未啟動"}


class SpeakRequest(BaseModel):
    phrase_id: str = Field(min_length=1, max_length=30)


def _fetch_wav(poj):
    body = json.dumps({"text": poj}).encode("utf-8")
    req = urllib.request.Request(
        LOCAL_TTS + "/synthesize", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=65) as response:
        return response.read()


def _combine_wavs(chunks):
    """Join short PCM WAV segments with 250 ms silence for clearer elder speech."""
    if len(chunks) == 1:
        return chunks[0]
    parts = []
    base = None
    for data in chunks:
        with wave.open(io.BytesIO(data), "rb") as wav:
            params = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype())
            if params[3] != "NONE":
                raise ValueError("Compressed WAV is not supported")
            if base is None:
                base = params
            elif params != base:
                raise ValueError("Inconsistent WAV format between segments")
            parts.append(wav.readframes(wav.getnframes()))
    channels, sampwidth, rate, _ = base
    silence = b"\x00" * (int(rate * 0.25) * channels * sampwidth)
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sampwidth)
        wav.setframerate(rate)
        wav.writeframes(silence.join(parts))
    return out.getvalue()


@lru_cache(maxsize=10)
def _cached_wav(phrase_id):
    text = PHRASES[phrase_id]
    segments = text if isinstance(text, tuple) else (text,)
    return _combine_wavs([_fetch_wav(segment) for segment in segments])


@router.post("/speak")
async def speak(req: SpeakRequest):
    if not enabled():
        raise HTTPException(status_code=503, detail="本機台語服務未啟用")
    if req.phrase_id not in PHRASES:
        raise HTTPException(status_code=422, detail="此台語語音稿尚未製作或審核")
    try:
        wave = await asyncio.to_thread(_cached_wav, req.phrase_id)
    except Exception as exc:
        print("Taigi local proxy failed:", type(exc).__name__)
        raise HTTPException(status_code=503, detail="台語模型服務未就緒，請確認 8002 終端機") from exc
    return Response(content=wave, media_type="audio/wav", headers={"Cache-Control": "no-store"})

# =====================================================================
# 2026-10-20 add-on: clinically traceable "What is this?" explanations.
# Existing /speak and /health routes above remain unchanged.
# The client sends IDs and Mandarin text for verification ONLY.  No client
# text, personal information, item prices, or unreviewed Mandarin text is
# forwarded into the Taiwanese model.
# =====================================================================
from pathlib import Path
import re
import unicodedata
from fastapi import Request

_DIR = Path(__file__).resolve().parent
_MEDICAL_DB = _DIR / "自費項目對話資料庫.json"
_TAIGI_REVIEW = _DIR / "yidian_taigi_medical_review.json"
_AUDIO_LIMIT = 16 * 1024 * 1024
_SYNTHESIS_GATE = asyncio.Semaphore(1)  # single Apple M-series 24 GB host


def _normalized_zh(text):
    """Allow harmless whitespace/Unicode representation differences only."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text or "")))


@lru_cache(maxsize=8)
def _load_json_snapshot(path_str, mtime_ns, size):
    with open(path_str, "r", encoding="utf-8") as fp:
        return json.load(fp)


def _read_json(path: Path):
    if not path.is_file():
        raise HTTPException(
            status_code=503,
            detail="台語檢查說明資料尚未安裝，請確認網站資料庫與翻譯稿檔案",
        )
    try:
        st = path.stat()
        return _load_json_snapshot(str(path), st.st_mtime_ns, st.st_size)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="台語檢查說明檔案無法讀取") from exc


def _verify_pair(source_entry, real_entry, label):
    if not source_entry or not real_entry:
        raise HTTPException(status_code=422, detail="找不到此檢查項目或套組")
    if (_normalized_zh(source_entry.get("name_zh")) != _normalized_zh(real_entry.get("name")) or
        _normalized_zh(source_entry.get("explanation_zh")) != _normalized_zh(real_entry.get("plain_explanation"))):
        raise HTTPException(
            status_code=409,
            detail=f"{label}資料已更新，請重新核對台語譯稿後再朗讀",
        )


def _can_read_script(entry):
    if not isinstance(entry, dict):
        return False
    segments = entry.get("taigi_tts_segments", [])
    scripts_ok = (isinstance(segments, list) and 1 <= len(segments) <= 10 and
                  all(isinstance(s, str) and 5 <= len(s.strip()) <= 1600 for s in segments))
    status = entry.get("review_status")
    if status == "approved":
        # An approved version must contain an explicit reviewed POJ script.
        return scripts_ok and all(str(entry.get(key) or "").strip()
                                  for key in ("language_reviewer", "clinical_reviewer", "reviewed_on"))
    if status == "draft" and os.getenv("TAIGI_TTS_DRAFT_MODE", "0") == "1":
        # Missing POJ may be converted from an *unreviewed Taiwanese Hanji draft*
        # by local port 8004. Never call this production-ready.
        hanji = entry.get("taigi_hanji_draft")
        return scripts_ok or (isinstance(hanji, str) and 5 <= len(hanji.strip()) <= 1300)
    return False


def _tts_scripts(entry):
    if not isinstance(entry, dict):
        return []
    scripts = entry.get("taigi_tts_segments", [])
    if scripts:
        return scripts
    hanji = entry.get("taigi_hanji_draft", "").strip()
    return ["__TAIGI_HANJI_V4__:" + hanji] if hanji else []


@lru_cache(maxsize=512)
def _hanji_to_poj(text):
    if not text or len(text) > 1300:
        raise ValueError("Untrusted Taiwanese Hanji text length")
    data = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(LOCAL_POJ + "/convert", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=18) as response:
        result = json.loads(response.read().decode("utf-8"))
    poj = str(result.get("poj") or "").strip()
    if not poj or len(poj) > 6000 or re.search(r"[\u3400-\u9fff]", poj):
        raise ValueError("Hanji-to-POJ output is not ready for TTS")
    return poj


def _require_local_test(request: Request):
    # Protect the test endpoint even if the host's CORS rules are permissive.
    if not enabled():
        raise HTTPException(status_code=503, detail="本機台語服務未啟用；請設定 TAIGI_TTS_ENABLED=1")
    client = request.client
    if not client or client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="此端點僅限同一台 Mac 的本機連線")


class ExplanationRequest(BaseModel):
    item_id: str = Field(min_length=4, max_length=15, pattern=r"^[IP][0-9]{3}$")
    item_name: str = Field(default="", max_length=256)
    plain_explanation: str = Field(min_length=1, max_length=1800)
    package_explanation: str = Field(default="", max_length=1800)


@lru_cache(maxsize=12)
def _cached_explanation_wav(segments):
    chunks = []
    for script in segments:
        if script.startswith("__TAIGI_HANJI_V4__:"):
            script = _hanji_to_poj(script.split(":", 1)[1])
        wav_data = _fetch_wav(script)  # only POJ scripts reach MMS-TTS
        if len(wav_data) > _AUDIO_LIMIT or not wav_data.startswith(b"RIFF"):
            raise ValueError("Invalid or excessively large upstream WAV")
        chunks.append(wav_data)
    return _combine_wavs(chunks)


@router.post("/explanation")
async def explanation(req: ExplanationRequest, request: Request):
    """Synthesize only matching, reviewed or explicitly demo-enabled Taiwanese scripts.

    Both the data file and text visible to the client must match the saved
    authoritative Mandarin source; mismatch => error and full Mandarin fallback.
    """
    _require_local_test(request)
    db = _read_json(_MEDICAL_DB)
    review = _read_json(_TAIGI_REVIEW)
    db_items = {it.get("id"): it for it in db.get("items", [])}
    db_packages = {it.get("package_id"): it for it in db.get("packages", [])}
    item = db_items.get(req.item_id)
    package = db_packages.get(req.item_id)
    segments = []
    review_entries = []

    if item:
        recorded = review.get("items", {}).get(req.item_id)
        _verify_pair(recorded, item, "檢查項目")
        if _normalized_zh(req.plain_explanation) != _normalized_zh(item["plain_explanation"]):
            raise HTTPException(status_code=409, detail="畫面檢查說明與資料庫不一致，請重新整理後再試")
        review_entries.append(recorded)
        segments.extend(_tts_scripts(recorded))
        if req.package_explanation.strip():
            package_id = item.get("package_id")
            package = db_packages.get(package_id)
            recorded_package = review.get("packages", {}).get(package_id)
            _verify_pair(recorded_package, package, "檢查套組")
            if _normalized_zh(req.package_explanation) != _normalized_zh(package["plain_explanation"]):
                raise HTTPException(status_code=409, detail="畫面套組說明與資料庫不一致，請重新整理後再試")
            review_entries.append(recorded_package)
            segments.extend(_tts_scripts(recorded_package))
    elif package:
        recorded = review.get("packages", {}).get(req.item_id)
        _verify_pair(recorded, package, "檢查套組")
        if _normalized_zh(req.plain_explanation) != _normalized_zh(package["plain_explanation"]):
            raise HTTPException(status_code=409, detail="畫面套組說明與資料庫不一致，請重新整理後再試")
        if req.package_explanation.strip() and _normalized_zh(req.package_explanation) != _normalized_zh(package["plain_explanation"]):
            raise HTTPException(status_code=409, detail="畫面套組說明重複欄位與資料庫不一致")
        review_entries.append(recorded)
        segments.extend(_tts_scripts(recorded))
    else:
        raise HTTPException(status_code=404, detail="找不到指定檢查項目")

    # Prevent partial narration: item and package must both be fully reviewed,
    # or both explicitly available for local draft preview.
    if not all(_can_read_script(entry) for entry in review_entries):
        raise HTTPException(
            status_code=422,
            detail="此檢查項目的完整台語說明尚未通過審核；將以國語朗讀完整原文",
        )

    mode = "draft" if any(r["review_status"] == "draft" for r in review_entries) else "approved"
    try:
        async with _SYNTHESIS_GATE:
            wav_data = await asyncio.to_thread(_cached_explanation_wav, tuple(segments))
    except Exception as exc:
        print("Taigi explanation synthesis failed:", type(exc).__name__)
        raise HTTPException(status_code=503, detail="8002 台語模型暫時無法合成，將以國語朗讀") from exc

    return Response(
        content=wav_data,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "X-Taigi-Review": mode,
            "Access-Control-Expose-Headers": "X-Taigi-Review",
        },
    )


@router.get("/explanation/coverage")
async def explanation_coverage(request: Request):
    """Local-only overview; no patient information or synthesis requests."""
    _require_local_test(request)
    review = _read_json(_TAIGI_REVIEW)
    categories = {}
    for key in ("items", "packages"):
        entries = review.get(key, {})
        counts = {"total": len(entries), "pending": 0, "draft": 0, "approved": 0}
        for entry in entries.values():
            status = entry.get("review_status", "pending")
            counts[status] = counts.get(status, 0) + 1
        categories[key] = counts
    return {
        "enabled": True,
        "draft_mode": os.getenv("TAIGI_TTS_DRAFT_MODE", "0") == "1",
        "coverage": categories,
        "hanji_drafts": {
            kind: sum(bool(e.get("taigi_hanji_draft")) for e in review.get(kind, {}).values())
            for kind in ("items", "packages")
        },
        "warning": "110 份漢字草稿尚未經母語或醫療審核；需本機 8004 轉台羅才能試聽",
    }


# =====================================================================
# V3: explicitly reviewed/draft dialogue scenarios for automatic speech.
# Each intent represents a predictable clinic UI response; accepting arbitrary
# Mandarin text would falsely imply that MMS-TTS translates Mandarin to Taigi.
# User-entered text, medical histories, patient IDs are NEVER sent here.
# Transliteration below is a LOCAL DEMO DRAFT and must be language-reviewed.
# =====================================================================

from typing import Optional

DIALOGUE_DRAFTS = {
    "next_category": (
        "Hó, tshiánn lí suán ē tsi̍t ê lí siūnn beh liáu-kái ê tsū-huì kiám-tsa hun-luī.",
    ),
    "unknown_category": (
        "Guá iáu-buē piān-sik tio̍h lí beh khòaⁿ ê hun-luī.",
        "Lí ē-tàng ti̍t-tsiap tiám ē-bīn ê hun-luī.",
    ),
    "retry_category": (
        "Hó, tshiánn lí koh suán lí beh liáu-kái ê tsū-huì kiám-tsa hun-luī.",
    ),
    "category_items": (
        "Hó, sio̍k-tāng ê kiám-tsa í-king lia̍t tī ē-bīn á-sī iū-pinn ê suán-tuann lāi.",
        "M̄ bat ê hāng-bo̍k, lí ē-sái tiám tsit sī siánn-mih, guá ē kā lí kóng bîng-pe̍h.",
        "Lí beh tsò ê, tiám ka-ji̍p tō ē-sái.",
    ),
    "health_category_full": (
        "Lí khah kuan-sim tó tsi̍t hāng ê kiān-khong būn-tê?",
        "Tshiánn tī ē-bīn á-sī iū-pinn suán tsi̍t ê hun-luī, guá ē lia̍t tshut ha̍p-sik ê kiám-tsa.",
        "Nā m̄ tsai suán tó tsi̍t ê, mā ē-sái suán m̄ tsai beh suán siánn-mih.",
    ),
    "ask_add_item": (
        "Tshiánn-mn̄g, lí beh kā tsit hāng tsū-huì kiám-tsa ka-ji̍p tshing-tuann--bô?",
    ),
    "no_items": (
        "Hiān-tsāi iáu-buē ka-ji̍p jīm-hô tsū-huì kiám-tsa ê hāng-bo̍k.",
    ),
    "empty_category": (
        "Tsit ê hun-luī hiān-tsāi bô ē-sái suán ê kiám-tsa hāng-bo̍k.",
    ),
    "not_added": (
        "Hó, tsit hāng kiám-tsa tshiat-sî bē ka-ji̍p.",
    ),
    "unknown_operation": (
        "Guá iáu-buē piān-sik tio̍h tsit ê tsōng-tsok, tshiánn iōng ē-bīn ê liú-á lâi kè-sio̍k.",
    ),
    "budget_retry": (
        "Hiān-tsāi iáu-buē khak-jīn lí ê ī-suàn kim-gia̍h.",
        "Lí ē-sái ti̍t-tsiap siá gōo bān, á-sī kóng gōo bān khoo.",
        "Nā gí-im piān-sik bô uân-tsuân, tshiánn koh kóng tsi̍t pái, á-sī iōng sòo-jī su-ji̍p.",
    ),
}

# Fixed item-name pronunciations, not a machine translation of the catalogue.
# Each new item must be transliterated and verified before being added here.
DIALOGUE_ITEM_NAMES = {
    "靜態心電圖 (EKG)": "tsīng-thài sim-tiān-tôo",
    "靜態心電圖(EKG)": "tsīng-thài sim-tiān-tôo",
    "靜態心電圖": "tsīng-thài sim-tiān-tôo",
    "血脂肪檢查": "hueh-tsi-hong kiám-tsa",
}


class DialogueRequest(BaseModel):
    intent: str = Field(min_length=3, max_length=60, pattern=r"^[a-z_]+$")
    item_name: str = Field(default="", max_length=160)
    price: Optional[int] = Field(default=None, ge=0, le=99999999)
    count: Optional[int] = Field(default=None, ge=0, le=1000)
    budget: Optional[int] = Field(default=None, ge=0, le=99999999)
    total: Optional[int] = Field(default=None, ge=0, le=99999999)
    remaining: Optional[int] = Field(default=None, ge=0, le=99999999)
    over: Optional[int] = Field(default=None, ge=0, le=99999999)


_TAIGI_DIGITS = ("khòng", "tsi̍t", "nn̄g", "sann", "sì", "gōo", "la̍k", "tshit", "peh", "káu")


def _taigi_below_10000(value):
    assert 0 <= value < 10000
    if value == 0:
        return _TAIGI_DIGITS[0]
    parts = []
    missing_place = False
    for divisor, unit in ((1000, "tshing"), (100, "pah"), (10, "tsa̍p")):
        digit, value = divmod(value, divisor)
        if digit:
            if missing_place:
                parts.append("lîng")  # zero between nonzero place values
                missing_place = False
            if divisor == 10 and digit == 1 and not parts:
                parts.append(unit)
            else:
                parts.extend((_TAIGI_DIGITS[digit], unit))
        elif parts and value:
            missing_place = True
    if value:
        if missing_place:
            parts.append("lîng")
        parts.append(_TAIGI_DIGITS[value])
    return " ".join(parts)


def _taigi_number(value):
    if not isinstance(value, int) or not 0 <= value <= 99999999:
        raise ValueError("Unsupported number")
    if value < 10000:
        return _taigi_below_10000(value)
    high, low = divmod(value, 10000)
    part = _taigi_below_10000(high) + " bān"
    return part + ((" lîng " if low < 1000 else " ") + _taigi_below_10000(low) if low else "")


def _dialogue_segments(req):
    if req.intent in DIALOGUE_DRAFTS:
        return DIALOGUE_DRAFTS[req.intent]
    if req.intent != "item_added":
        raise HTTPException(status_code=422, detail="尚無此類回覆的台語對照稿")
    name = DIALOGUE_ITEM_NAMES.get(req.item_name.strip())
    if not name:
        # Verify the item against the known clinic catalog before converting
        # its Taiwanese name. Never accept an arbitrary user-provided phrase.
        review = _read_json(_TAIGI_REVIEW)
        all_rows = list(review.get("items", {}).values()) + list(review.get("packages", {}).values())
        match = next((row for row in all_rows if _normalized_zh(row.get("name_zh")) == _normalized_zh(req.item_name)), None)
        if not match:
            raise HTTPException(status_code=422, detail="此檢查項目名稱無法從診所資料庫核對")
        # English test codes are visible in the GUI but need not be read in
        # the Taiwanese item label; the medical explanation remains separate.
        hanji_name = re.sub(r"\s*[（(][^）)]*[）)]", "", str(match["name_zh"]))
        hanji_name = re.sub(r"[A-Za-z0-9/\-]+", " ", hanji_name).strip()
        if not hanji_name:
            raise HTTPException(status_code=422, detail="檢查名稱無有效台語漢字")
        name = _hanji_to_poj(hanji_name)
    if any(value is None for value in (req.price, req.count, req.budget, req.total)):
        raise HTTPException(status_code=422, detail="金額或數量不完整，無法準確朗讀")
    if req.count < 1 or (req.remaining is None and req.over is None):
        raise HTTPException(status_code=422, detail="預算餘額不完整")
    if (req.remaining is not None and req.over is not None) or req.total != req.budget - (req.remaining or 0) + (req.over or 0):
        raise HTTPException(status_code=422, detail="預算數字不一致，請確認畫面資料")
    parts = [
        f"Í-king kā {name} ka-ji̍p kiám-tsa tshing-tuann.",
        f"Tsit hāng kè-tsînn sī {_taigi_number(req.price)} khoo. Hiān-tsāi tsóng-kiōng suán {_taigi_number(req.count)} hāng.",
        f"Lí siat-tīng ê ī-suàn sī {_taigi_number(req.budget)} khoo. Hiān-tsāi tsóng ha̍p-kè {_taigi_number(req.total)} khoo.",
    ]
    if req.remaining is not None:
        parts.append(f"Ī-suàn iáu tshuà {_taigi_number(req.remaining)} khoo.")
    else:
        parts.append(f"Hiān-tsāi tshiau-kuè ī-suàn {_taigi_number(req.over)} khoo.")
    return tuple(parts)


@lru_cache(maxsize=24)
def _cached_dialogue_wav(segments):
    chunks = []
    for segment in segments:
        wav_data = _fetch_wav(segment)
        if len(wav_data) > _AUDIO_LIMIT or not wav_data.startswith(b"RIFF"):
            raise ValueError("Invalid Taiwanese speech audio")
        chunks.append(wav_data)
    return _combine_wavs(chunks)


@router.post("/dialogue")
async def dialogue(req: DialogueRequest, request: Request):
    _require_local_test(request)
    if os.getenv("TAIGI_TTS_DRAFT_MODE", "0") != "1":
        raise HTTPException(status_code=422, detail="這些對話台語稿仍在草稿測試階段，需本機啟用 TAIGI_TTS_DRAFT_MODE=1")
    segments = _dialogue_segments(req)
    try:
        async with _SYNTHESIS_GATE:
            audio_bytes = await asyncio.to_thread(_cached_dialogue_wav, segments)
    except Exception as exc:
        print("Taigi dialogue synthesis failed:", type(exc).__name__)
        raise HTTPException(status_code=503, detail="8002 台語模型服務目前無法合成") from exc
    return Response(content=audio_bytes, media_type="audio/wav", headers={
        "Cache-Control": "no-store", "X-Taigi-Review": "draft",
        "Access-Control-Expose-Headers": "X-Taigi-Review",
    })


@router.get("/dialogue/coverage")
async def dialogue_coverage(request: Request):
    _require_local_test(request)
    return {
        "enabled": True,
        "draft_mode": os.getenv("TAIGI_TTS_DRAFT_MODE", "0") == "1",
        "fixed_intents": sorted(DIALOGUE_DRAFTS),
        "receipt_item_names": sorted(DIALOGUE_ITEM_NAMES),
        "warning": "所有台語羅馬字稿仍需母語審核；未列項目完整國語備援",
    }

# =====================================================================
# V4: optional, LOCAL-ONLY and DRAFT-ONLY dynamic Mandarin -> Taiwanese POJ.
# This enables responses that cannot be represented by V3 fixed intent phrases.
# To actually enable it you MUST run the 8004 MLX Taigi translator separately.
# The authoritative visible text remains Traditional Chinese; the generated
# Taiwanese audio is experimental and not clinically reviewed.
# =====================================================================

class DynamicTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    source: str = Field(default="ai_reply", pattern=r"^(ai_reply)$")


def _ask_local_translator(text):
    request = urllib.request.Request(
        LOCAL_POJ + "/translate",
        data=json.dumps({"text": text, "target": "POJ"}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=150) as response:
        value = json.loads(response.read().decode("utf-8"))
    poj = str(value.get("poj") or "").strip()
    if not poj or len(poj) > 6000 or re.search(r"[\u3400-\u9fff]", poj):
        raise ValueError("Invalid Taiwanese POJ translation")
    return poj


def _chunk_poj(text):
    # Keep segments short so the non-streaming 8002 server can synthesize them.
    parts = re.split(r"(?<=[.!?;])\s+|\n+", text)
    chunks=[]
    for line in parts:
        line = line.strip()
        while len(line) > 450:
            at = line.rfind(" ", 0, 450)
            if at < 80: at = 450
            chunks.append(line[:at].strip())
            line = line[at:].strip()
        if line: chunks.append(line)
    if not chunks or len(chunks) > 16:
        raise ValueError("Translated reply is too long")
    return tuple(chunks)


def _synthesize_local_dynamic(text):
    translated = _ask_local_translator(text)
    return _cached_dialogue_wav(_chunk_poj(translated))


@router.post("/text")
async def dynamic_taigi_text(req: DynamicTextRequest, request: Request):
    _require_local_test(request)
    if os.getenv("TAIGI_TTS_DRAFT_MODE", "0") != "1" or os.getenv("TAIGI_DYNAMIC_DRAFT", "0") != "1":
        raise HTTPException(422, detail="動態台語翻譯尚未啟用，本機測試需 TAIGI_DYNAMIC_DRAFT=1")
    text = req.text.strip()
    # Do not automatically speak personally identifiable booking details or
    # users' sensitive free text. This path is only for AI-generated UI replies.
    if (re.search(r"[A-Z][12][0-9]{8}", text) or
        re.search(r"09[0-9]{8}", text) or
        re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)):
        raise HTTPException(422, detail="含有可能的個人識別資訊，僅顯示文字，不執行動態台語合成")
    try:
        async with _SYNTHESIS_GATE:
            wave_data = await asyncio.to_thread(_synthesize_local_dynamic, text)
    except Exception as exc:
        print("Taigi dynamic translation unavailable:", type(exc).__name__)
        raise HTTPException(503, detail="8004 本機台語翻譯尚未就緒，將保留國語全文朗讀") from exc
    return Response(content=wave_data, media_type="audio/wav", headers={
        "Cache-Control": "no-store", "X-Taigi-Review": "draft",
        "Access-Control-Expose-Headers": "X-Taigi-Review"
    })
