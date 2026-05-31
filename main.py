import os
import json
import hmac
import hashlib
import base64
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import httpx
import firebase_admin
from firebase_admin import credentials, db

app = FastAPI(title="山林診所 LINE Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CHANNEL_SECRET       = os.environ.get("CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
FIREBASE_URL         = os.environ.get("FIREBASE_URL", "")
LIFF_VERIFY_URL      = os.environ.get("LIFF_URL", "https://liff.line.me/2010169963-KEjAbfsW")
LIFF_APPT_URL        = os.environ.get("LIFF_APPT_URL", "https://liff.line.me/2010169963-n8zZXE1V")
LINE_API             = "https://api.line.me/v2/bot/message"

firebase_cred_json = os.environ.get("FIREBASE_CREDENTIALS", "")
try:
    if firebase_cred_json and firebase_cred_json != "{}" and not firebase_admin._apps:
        cred_dict = json.loads(firebase_cred_json)
        if cred_dict.get("type") == "service_account":
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
except Exception as e:
    print(f"Firebase init skipped: {e}")


def verify_signature(body: bytes, signature: str) -> bool:
    hash_ = hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_).decode()
    return hmac.compare_digest(expected, signature)


async def push_message(user_id: str, messages: list):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{LINE_API}/push",
            headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
            json={"to": user_id, "messages": messages}
        )
        print(f"Push status: {res.status_code}, body: {res.text}")


async def reply_message(reply_token: str, messages: list):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{LINE_API}/reply",
            headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
            json={"replyToken": reply_token, "messages": messages}
        )
        print(f"Reply status: {res.status_code}, body: {res.text}")


def make_liff_button(label: str, url: str) -> dict:
    return {
        "type": "template",
        "altText": label,
        "template": {
            "type": "buttons",
            "text": label,
            "actions": [{
                "type": "uri",
                "label": label[:20],
                "uri": url
            }]
        }
    }


def check_bound(user_id: str) -> bool:
    """檢查此 LINE User ID 是否已完成身分驗證綁定"""
    try:
        users = db.reference("appointments").get() or {}
        for uid, data in users.items():
            if isinstance(data, dict) and data.get("lineUserId") == user_id:
                return True
    except Exception as e:
        print(f"check_bound error: {e}")
    return False


@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    if CHANNEL_SECRET and not verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    data = json.loads(body)

    for event in data.get("events", []):
        event_type  = event.get("type")
        user_id     = event.get("source", {}).get("userId", "")
        reply_token = event.get("replyToken", "")

        if event_type == "follow":
            await handle_follow(user_id, reply_token)
        elif event_type == "message" and event["message"]["type"] == "text":
            text = event["message"]["text"].strip()
            await handle_text(user_id, reply_token, text)
        elif event_type == "postback":
            await handle_postback(user_id, reply_token, event["postback"]["data"])

    return JSONResponse({"status": "ok"})


async def handle_follow(user_id: str, reply_token: str):
    await reply_message(reply_token, [
        {
            "type": "text",
            "text": (
                "感謝您成為山林診所好友 💗\n\n"
                "⭐ 門診時間\n"
                "週一至週五 早上 8:30-12:30、下午 13:30-17:30\n"
                "週六 早上 8:30-12:30\n"
                "週日公休\n\n"
                "⭐ 診所位置：台北市文山區羅斯福路六段 407 號 2 樓\n"
                "⭐ 連絡電話：02-2933-2010\n\n"
                "請使用下方選單選擇服務 👇"
            )
        }
    ])


async def handle_text(user_id: str, reply_token: str, text: str):
    keywords_booking = ["預約", "體檢", "健檢", "掛號"]
    keywords_report  = ["報告", "檢查結果"]
    keywords_verify  = ["綁定", "驗證", "身分"]
    keywords_hours   = ["時間", "門診", "幾點"]
    keywords_address = ["地址", "位置", "在哪", "怎麼去"]

    if any(k in text for k in keywords_booking):
        # ── 一條龍流程：檢查是否已綁定 ──
        is_bound = check_bound(user_id)

        if is_bound:
            # 已綁定 → 直接給預約按鈕
            await reply_message(reply_token, [
                {
                    "type": "text",
                    "text": "您已完成身分驗證 ✅\n請點下方按鈕進行健檢預約 📋"
                },
                make_liff_button("📅 立即預約健檢", LIFF_APPT_URL)
            ])
        else:
            # 未綁定 → 先驗證，驗證成功後再預約
            await reply_message(reply_token, [
                {
                    "type": "text",
                    "text": (
                        "您好！要預約老人健檢嗎？😊\n\n"
                        "第一步：請先完成身分驗證綁定\n"
                        "驗證成功後即可直接預約健檢，以後說「預約」就會直接跳到預約頁面！"
                    )
                },
                make_liff_button("🔐 第一步：身分驗證綁定", LIFF_VERIFY_URL)
            ])

    elif any(k in text for k in keywords_verify):
        await reply_message(reply_token, [
            {"type": "text", "text": "請點下方按鈕完成身分驗證綁定 🔐"},
            make_liff_button("🔐 身分驗證綁定", LIFF_VERIFY_URL)
        ])

    elif any(k in text for k in keywords_report):
        await reply_message(reply_token, [
            {
                "type": "text",
                "text": "您的健檢報告可在綁定後查閱，系統會以 AI 白話文解讀紅字數值 📋"
            },
            make_liff_button("📄 查看我的報告", LIFF_VERIFY_URL)
        ])

    elif any(k in text for k in keywords_hours):
        await reply_message(reply_token, [{
            "type": "text",
            "text": (
                "⭐ 門診時間\n"
                "週一至週五 早上 8:30-12:30、下午 13:30-17:30\n"
                "週六 早上 8:30-12:30\n"
                "週日公休\n"
                "國定假日門診半天"
            )
        }])

    elif any(k in text for k in keywords_address):
        await reply_message(reply_token, [{
            "type": "text",
            "text": "📍 台北市文山區羅斯福路六段 407 號 2 樓\n（由車前路門口上樓）\n\n📞 02-2933-2010"
        }])

    else:
        await reply_message(reply_token, [{
            "type": "text",
            "text": "感謝您的訊息！如需協助請使用下方選單，或撥打 02-2933-2010 🙏"
        }])


async def handle_postback(user_id: str, reply_token: str, data_str: str):
    if data_str == "action=checkup":
        is_bound = check_bound(user_id)
        if is_bound:
            await reply_message(reply_token, [
                {"type": "text", "text": "請點下方按鈕進行健檢預約 📋"},
                make_liff_button("📅 立即預約健檢", LIFF_APPT_URL)
            ])
        else:
            await reply_message(reply_token, [
                {"type": "text", "text": "請先完成身分驗證綁定 🔐"},
                make_liff_button("🔐 身分驗證綁定", LIFF_VERIFY_URL)
            ])


# ══════════════════════════════════════
#  LIFF 身分驗證 API
# ══════════════════════════════════════
class VerifyRequest(BaseModel):
    id_number:    str
    phone:        str
    line_user_id: str


@app.post("/api/liff/verify")
async def liff_verify(req: VerifyRequest):
    id_num = req.id_number.upper().strip()
    phone  = req.phone.strip()

    try:
        ref  = db.reference(f"appointments/{id_num}")
        data = ref.get()
    except Exception:
        raise HTTPException(status_code=404, detail="查無資料")

    if not data:
        raise HTTPException(status_code=404, detail="查無此身分證資料")

    stored_phone = str(data.get("phone", ""))
    if not stored_phone.startswith("0"):
        stored_phone = "0" + stored_phone
    if stored_phone != phone:
        raise HTTPException(status_code=401, detail="手機號碼不符")

    ref.update({"lineUserId": req.line_user_id, "boundAt": datetime.now().isoformat()})

    # 驗證成功後推播，並直接附上預約按鈕
    await push_message(req.line_user_id, [
        {
            "type": "text",
            "text": (
                f"✅ 身分驗證綁定成功！\n\n"
                f"您好，{data.get('name', '')}！\n"
                f"以後說「預約」就可以直接預約健檢了 😊\n\n"
                f"現在要立即預約嗎？"
            )
        },
        make_liff_button("📅 立即預約健檢", LIFF_APPT_URL)
    ])

    return {
        "name": data.get("name"),
        "date": data.get("date"),
        "time": data.get("time"),
        "plan": data.get("plan"),
    }


# ══════════════════════════════════════
#  語音預約 API
# ══════════════════════════════════════
class AppointmentRequest(BaseModel):
    id_number:    str
    plan:         str
    date:         str
    time_slot:    str
    line_user_id: str = ""


@app.post("/api/appointment/book")
async def book_appointment(req: AppointmentRequest):
    plan_names = {
        "A": "A 方案（腦肺方案）",
        "B": "B 方案（腹部方案）",
        "C": "C 方案（骨密肌力方案）"
    }

    # 用 line_user_id 找到對應的預約資料
    line_user_id = req.line_user_id
    target_ref   = None
    target_data  = None

    try:
        all_appts = db.reference("appointments").get() or {}
        for id_num, data in all_appts.items():
            if isinstance(data, dict) and data.get("lineUserId") == line_user_id:
                target_ref  = db.reference(f"appointments/{id_num}")
                target_data = data
                break
    except Exception as e:
        print(f"book error: {e}")

    if target_ref:
        target_ref.update({
            "plan":     req.plan,
            "date":     req.date,
            "time":     req.time_slot,
            "bookedAt": datetime.now().isoformat()
        })

    # 推播預約成功通知
    if line_user_id:
        await push_message(line_user_id, [{
            "type": "text",
            "text": (
                f"✅ 預約成功！\n\n"
                f"📋 方案：{plan_names.get(req.plan, req.plan)}\n"
                f"📅 日期：{req.date}\n"
                f"⏰ 時段：{req.time_slot}\n\n"
                f"健檢前請記得空腹 8 小時，我們會在前一天再次提醒您 😊"
            )
        }])

    return {"status": "success", "message": "預約成功"}


# ══════════════════════════════════════
#  診前提醒
# ══════════════════════════════════════
@app.post("/api/reminder/send")
async def send_reminders():
    import datetime as dt
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()

    try:
        all_appts = db.reference("appointments").get() or {}
    except Exception:
        return {"status": "error", "message": "Firebase 連線失敗"}

    sent = 0
    for id_num, data in all_appts.items():
        if not isinstance(data, dict):
            continue
        if data.get("date") == tomorrow and data.get("lineUserId"):
            await push_message(data["lineUserId"], [{
                "type": "text",
                "text": (
                    f"⏰ 健檢提醒\n\n"
                    f"{data.get('name', '您好')}，明天 {tomorrow} 您有健檢預約！\n\n"
                    f"📌 注意事項：\n"
                    f"• 今晚 10 點後請禁食禁水\n"
                    f"• 請攜帶健保卡與身分證\n"
                    f"• 穿著輕便衣物\n\n"
                    f"健檢時間：{data.get('time', '')}，請準時到達 🏥"
                )
            }])
            sent += 1

    return {"status": "success", "sent": sent}


@app.get("/")
async def root():
    return {"status": "ok", "service": "山林診所 LINE Bot API"}
