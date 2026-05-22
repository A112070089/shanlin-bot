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

# ══════════════════════════════════════
#  初始化
# ══════════════════════════════════════
app = FastAPI(title="山林診所 LINE Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 環境變數（在 Render 上設定）
CHANNEL_SECRET       = os.environ.get("CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
FIREBASE_URL         = os.environ.get("FIREBASE_URL", "")      # 例如 https://your-project.firebaseio.com

# Firebase 初始化
firebase_cred_json = os.environ.get("FIREBASE_CREDENTIALS", "")
try:
    if firebase_cred_json and firebase_cred_json != "{}" and not firebase_admin._apps:
        cred_dict = json.loads(firebase_cred_json)
        if cred_dict.get("type") == "service_account":
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
except Exception as e:
    print(f"Firebase init skipped: {e}")

LINE_API = "https://api.line.me/v2/bot/message"

# ══════════════════════════════════════
#  工具函式
# ══════════════════════════════════════
def verify_signature(body: bytes, signature: str) -> bool:
    """驗證 LINE Webhook 簽名"""
    hash_ = hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_).decode()
    return hmac.compare_digest(expected, signature)

async def push_message(user_id: str, messages: list):
    """主動推送訊息給使用者"""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{LINE_API}/push",
            headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
            json={"to": user_id, "messages": messages}
        )

async def reply_message(reply_token: str, messages: list):
    """回覆訊息"""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{LINE_API}/reply",
            headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
            json={"replyToken": reply_token, "messages": messages}
        )

def get_liff_url():
    return os.environ.get("LIFF_URL", "https://liff.line.me/2010169963-KEjAbfsW")

# ══════════════════════════════════════
#  Webhook（接收 LINE 訊息）
# ══════════════════════════════════════
@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    if CHANNEL_SECRET and not verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    data = json.loads(body)

    for event in data.get("events", []):
        event_type = event.get("type")
        user_id    = event.get("source", {}).get("userId", "")
        reply_token = event.get("replyToken", "")

        # ── 加好友事件 ──
        if event_type == "follow":
            await handle_follow(user_id, reply_token)

        # ── 文字訊息 ──
        elif event_type == "message" and event["message"]["type"] == "text":
            text = event["message"]["text"].strip()
            await handle_text(user_id, reply_token, text)

        # ── Postback（按鈕觸發）──
        elif event_type == "postback":
            data_str = event["postback"]["data"]
            await handle_postback(user_id, reply_token, data_str)

    return JSONResponse({"status": "ok"})


async def handle_follow(user_id: str, reply_token: str):
    """新好友加入"""
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
    """處理文字訊息"""
    keywords_booking = ["預約", "體檢", "健檢", "掛號"]
    keywords_report  = ["報告", "檢查結果"]
    keywords_hours   = ["時間", "門診", "幾點"]
    keywords_address = ["地址", "位置", "在哪", "怎麼去"]

    if any(k in text for k in keywords_booking):
        await reply_message(reply_token, [
            {
                "type": "text",
                "text": "您好！要預約老人健檢嗎？\n請先完成身分驗證綁定，之後就能隨時預約 😊"
            },
            make_liff_button("🔐 進行身分驗證綁定", get_liff_url())
        ])

    elif any(k in text for k in keywords_report):
        await reply_message(reply_token, [
            {
                "type": "text",
                "text": "您的健檢報告可在綁定後查閱，系統會以 AI 白話文解讀紅字數值 📋"
            },
            make_liff_button("📄 查看我的報告", get_liff_url())
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
    """處理 Postback 按鈕"""
    if data_str == "action=checkup":
        await reply_message(reply_token, [
            {"type": "text", "text": "請點下方按鈕進行身分驗證，驗證後即可預約健檢 🏥"},
            make_liff_button("🔐 身分驗證綁定", get_liff_url())
        ])


def make_liff_button(label: str, url: str) -> dict:
    """產生開啟 LIFF 的按鈕訊息"""
    return {
        "type": "template",
        "altText": label,
        "template": {
            "type": "buttons",
            "actions": [{
                "type": "uri",
                "label": label,
                "uri": url
            }]
        }
    }

# ══════════════════════════════════════
#  LIFF 身分驗證 API
# ══════════════════════════════════════
class VerifyRequest(BaseModel):
    id_number:    str
    phone:        str
    line_user_id: str

@app.post("/api/liff/verify")
async def liff_verify(req: VerifyRequest):
    """
    LIFF 身分驗證：比對 Firebase 預約資料
    比對成功後將 LINE User ID 寫入資料庫完成綁定
    """
    id_num = req.id_number.upper().strip()
    phone  = req.phone.strip()

    try:
        ref = db.reference(f"appointments/{id_num}")
        data = ref.get()
    except Exception:
        # Firebase 未設定時回傳 404
        raise HTTPException(status_code=404, detail="查無資料")

    if not data:
        raise HTTPException(status_code=404, detail="查無此身分證資料")

    if data.get("phone") != phone:
        raise HTTPException(status_code=401, detail="手機號碼不符")

    # 綁定 LINE User ID
    ref.update({"lineUserId": req.line_user_id, "boundAt": datetime.now().isoformat()})

    # 推送綁定成功訊息
    await push_message(req.line_user_id, [
        {
            "type": "text",
            "text": (
                f"✅ 身分驗證綁定成功！\n\n"
                f"您好，{data.get('name', '')}！\n"
                f"以後可以直接透過 LINE 使用以下服務：\n"
                f"• 語音預約健檢\n"
                f"• 查看健檢報告\n"
                f"• 診前禁食提醒\n"
                f"• AI 護理師問答"
            )
        }
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
    id_number: str
    plan:      str   # A / B / C
    date:      str   # 2025-06-08
    time_slot: str   # 09:00

@app.post("/api/appointment/book")
async def book_appointment(req: AppointmentRequest):
    """寫入預約資料並發送 LINE 確認通知"""
    id_num = req.id_number.upper().strip()

    try:
        ref  = db.reference(f"appointments/{id_num}")
        data = ref.get()
    except Exception:
        raise HTTPException(status_code=404, detail="查無資料")

    if not data:
        raise HTTPException(status_code=404, detail="查無此身分證資料")

    plan_names = {
        "A": "A 方案（腦肺方案）",
        "B": "B 方案（腹部方案）",
        "C": "C 方案（骨密肌力方案）"
    }

    ref.update({
        "plan":      req.plan,
        "date":      req.date,
        "time":      req.time_slot,
        "bookedAt":  datetime.now().isoformat()
    })

    line_user_id = data.get("lineUserId")
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
#  診前提醒推播 API（可由排程呼叫）
# ══════════════════════════════════════
@app.post("/api/reminder/send")
async def send_reminders():
    """
    找出明天有預約的人，發送禁食提醒
    建議用 Render Cron Job 每天晚上 8 點呼叫
    """
    tomorrow = (datetime.now().date().__add__(__import__("datetime").timedelta(days=1))).isoformat()

    try:
        all_appts = db.reference("appointments").get() or {}
    except Exception:
        return {"status": "error", "message": "Firebase 連線失敗"}

    sent = 0
    for id_num, data in all_appts.items():
        if data.get("date") == tomorrow and data.get("lineUserId"):
            await push_message(data["lineUserId"], [{
                "type": "text",
                "text": (
                    f"⏰ 健檢提醒\n\n"
                    f"{data.get('name', '您好')}，明天 {tomorrow} 您有健檢預約！\n\n"
                    f"📌 注意事項：\n"
                    f"• 今晚 10 點後請禁食禁水（可喝少量白開水）\n"
                    f"• 請攜帶健保卡與身分證\n"
                    f"• 穿著輕便衣物\n\n"
                    f"健檢時間：{data.get('time', '')}，請準時到達 🏥"
                )
            }])
            sent += 1

    return {"status": "success", "sent": sent}


# ══════════════════════════════════════
#  健康檢查
# ══════════════════════════════════════
@app.get("/")
async def root():
    return {"status": "ok", "service": "山林診所 LINE Bot API"}
