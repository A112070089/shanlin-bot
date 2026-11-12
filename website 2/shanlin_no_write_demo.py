"""2026-11-20 local-only non-persistent Shanlin booking simulation."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

# SHANLIN_NONPERSISTENT_DEMO_20261120_V1
router = APIRouter()
DEMO_DATE = "2026-11-20"
DEMO_TIMES = ("09:00", "10:00")
ID_LETTERS = "ABCDEFGHJKLMNPQRSTUVXYWZIO"
ID_WEIGHTS = (1, 9, 8, 7, 6, 5, 4, 3, 2, 1, 1)


def _local_demo_only(request: Request):
    if os.getenv("PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED") != "1":
        raise HTTPException(403, "此功能僅在已啟用的合成預約測試環境中使用")
    if request.client is None or request.client.host not in ("127.0.0.1", "::1", "testclient"):
        raise HTTPException(403, "只允許本機使用")
    if request.url.hostname not in ("127.0.0.1", "localhost"):
        raise HTTPException(403, "必須透過本機網址使用")
    origin = request.headers.get("origin")
    if origin:
        parts = urlsplit(origin)
        if parts.hostname not in ("127.0.0.1", "localhost") or parts.port != 8006:
            raise HTTPException(403, "來源不符合本機展示頁面")


def _valid_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z][12][0-9]{8}", value):
        return False
    pos = ID_LETTERS.find(value[0])
    if pos < 0:
        return False
    digits = [int(char) for char in str(pos + 10) + value[1:]]
    return sum(a * b for a, b in zip(digits, ID_WEIGHTS)) % 10 == 0


def _valid_older_birthday(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 12:
        return False
    raw = value.strip()
    try:
        if re.fullmatch(r"[0-9]{6,7}", raw):
            roc = int(raw[:-4]); month = int(raw[-4:-2]); day = int(raw[-2:])
            born = date(1911 + roc, month, day)
        elif re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
            born = date.fromisoformat(raw)
        else:
            return False
    except ValueError:
        return False
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return 1850 <= born.year <= today.year and age >= 65


def _valid_name(value: object) -> bool:
    if not isinstance(value, str) or not (1 <= len(value.strip()) <= 50):
        return False
    if any(ord(char) < 32 for char in value):
        return False
    return any(unicodedata.category(char).startswith("L") for char in value)


@router.get("/api/shanlin/demo-day/info", include_in_schema=False)
async def demo_info(request: Request):
    _local_demo_only(request)
    return JSONResponse({
        "status": "success", "clinicId": "shanlin", "isSynthetic": True,
        "date": DEMO_DATE, "times": list(DEMO_TIMES), "unlimited": True,
        "demoOnly": True, "persisted": False,
        "message": "11/20 是本機不限次數模擬日，不寫入任何預約資料"
    }, headers={"Cache-Control": "no-store"})


@router.post("/api/shanlin/demo-day/confirm", include_in_schema=False)
async def demo_confirm(request: Request):
    _local_demo_only(request)
    if not request.headers.get("content-type", "").lower().startswith("application/json"):
        raise HTTPException(415, "僅接受 JSON")
    raw = await request.body()
    if not raw or len(raw) > 16384:
        raise HTTPException(413, "模擬預約資料超過限制")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, "預約資料格式不正確")
    if not isinstance(data, dict):
        raise HTTPException(422, "預約資料格式不正確")
    if (data.get("date") != DEMO_DATE or data.get("time") not in DEMO_TIMES
            or data.get("plan") not in ("A", "B", "C")):
        raise HTTPException(422, "本端點只能模擬 11/20 已指定的老人健檢方案及時段")
    if (data.get("selfPayItems") not in (None, []) or
            (data.get("selfPayTotal") not in (None, 0, "0"))):
        raise HTTPException(422, "不限次數模擬日不支援自費加購")
    if (not _valid_name(data.get("name")) or
            not isinstance(data.get("phone"), str) or
            not re.fullmatch(r"09[0-9]{8}", data["phone"].strip()) or
            not _valid_id(data.get("pid")) or
            not _valid_older_birthday(data.get("birthday")) or
            not isinstance(data.get("captcha"), str) or
            not re.fullmatch(r"[0-9]{5}", data["captcha"].strip())):
        raise HTTPException(422, "請先確認姓名、手機、身分證檢查碼、65 歲資格與驗證碼格式")
    # Intentional no-write endpoint: no import/call to Firebase, _relay,
    # 8018, LINE, or any booking store. No names or identifiers in response.
    return JSONResponse({
        "status": "success", "clinicId": "shanlin", "isSynthetic": True,
        "demoOnly": True, "persisted": False, "reservationCreated": False,
        "message": "本機模擬流程完成；未建立任何預約、未占用名額，也不會發送提醒"
    }, headers={"Cache-Control": "no-store"})
