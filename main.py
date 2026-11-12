import os
import json
import hmac
import hashlib
import base64
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import io

import httpx
import firebase_admin
from firebase_admin import credentials, db
from openpyxl import load_workbook

# 本機測試用：自動讀取 .env（線上 Railway 沒有這個檔案，會直接用環境變數）
try:
    from dotenv import load_dotenv
    _here = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_here, ".env"))
    load_dotenv(os.path.join(_here, "website", ".env"))  # 跟語音預約網站共用同一組 Firebase 金鑰
except Exception:
    pass

app = FastAPI(title="頤典 診所預約 LINE Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CHANNEL_SECRET       = os.environ.get("CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
FIREBASE_URL         = os.environ.get("FIREBASE_URL", "")

# 頤典資料隔離：禁止使用山林 Firebase
from urllib.parse import urlparse

firebase_host = (urlparse(FIREBASE_URL).hostname or "").lower()

if firebase_host == "shanlin-clinic-default-rtdb.firebaseio.com":
    raise RuntimeError(
        "安全保護：頤典 8001 不可連接山林 Firebase，"
        "請先設定頤典專屬資料來源"
    )
LIFF_VERIFY_URL      = os.environ.get("LIFF_URL", "https://liff.line.me/2010169963-KEjAbfsW")
LIFF_APPT_URL        = os.environ.get("LIFF_APPT_URL", "https://liff.line.me/2010169963-n8zZXE1V")
ADMIN_PASSWORD       = os.environ.get("ADMIN_PASSWORD", "shanlin2025")
DIFY_API_KEY         = os.environ.get("DIFY_API_KEY", "")
DIFY_API_URL         = "https://api.dify.ai/v1"
LINE_API             = "https://api.line.me/v2/bot/message"

SELFPAY_KEY_PREFIX = "SELFPAY::"

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


def check_admin(x_admin_password: Optional[str]):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="密碼錯誤")


# ══════════════════════════════════════
#  LINE Webhook
# ══════════════════════════════════════
async def call_dify(user_id: str, message: str) -> str:
    """呼叫 Dify AI，回傳回覆文字"""
    if not DIFY_API_KEY:
        return "AI 助理目前無法使用，請稍後再試。"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(
                f"{DIFY_API_URL}/chat-messages",
                headers={
                    "Authorization": f"Bearer {DIFY_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "inputs": {},
                    "query": message,
                    "response_mode": "blocking",
                    "conversation_id": "",
                    "user": user_id
                }
            )
            if res.status_code == 200:
                data = res.json()
                return data.get("answer", "抱歉，我暫時無法回答這個問題。")
            else:
                print(f"Dify error: {res.status_code}, {res.text}")
                return f"AI 助理暫時無法使用，請撥打 {get_clinic()['phone']} 洽詢。"
    except Exception as e:
        print(f"Dify exception: {e}")
        return f"AI 助理暫時無法使用，請撥打 {get_clinic()['phone']} 洽詢。"


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

    return JSONResponse({"status": "ok"})


async def handle_follow(user_id: str, reply_token: str):
    c = get_clinic()
    await reply_message(reply_token, [
        {
            "type": "text",
            "text": (
                f"感謝您成為{c['name']}好友 💗\n\n"
                "⭐ 門診時間\n"
                f"{c['hours']}\n\n"
                f"⭐ 診所位置：{c['address']}\n"
                f"⭐ 連絡電話：{c['phone']}\n\n"
                "請使用下方選單選擇服務 👇"
            )
        }
    ])


async def handle_text(user_id: str, reply_token: str, text: str):
    keywords_booking = ["預約", "體檢", "健檢", "掛號"]
    keywords_verify  = ["綁定", "驗證", "身分證"]
    keywords_query   = ["我的預約", "查詢預約", "預約資料", "預約紀錄", "查預約"]
    keywords_report  = ["報告", "檢查結果"]
    keywords_hours   = ["時間", "門診", "幾點"]
    keywords_address = ["地址", "位置", "在哪", "怎麼去"]

    if any(k in text for k in keywords_query):
        appt_data = None
        try:
            all_appts = db.reference("appointments").get() or {}
            for id_num, data in all_appts.items():
                if isinstance(data, dict) and data.get("lineUserId") == user_id:
                    appt_data = data
                    break
        except Exception as e:
            print(f"query error: {e}")

        if appt_data:
            plan_names = {
                "A": "A 方案（腦肺方案）",
                "B": "B 方案（腹部方案）",
                "C": "C 方案（骨密肌力方案）"
            }
            await reply_message(reply_token, [{
                "type": "text",
                "text": (
                    f"📋 您的預約資料\n\n"
                    f"👤 姓名：{appt_data.get('name', '—')}\n"
                    f"📅 日期：{appt_data.get('date', '—')}\n"
                    f"⏰ 時段：{appt_data.get('time', '—')}\n"
                    f"🏥 方案：{plan_names.get(appt_data.get('plan', ''), appt_data.get('plan', '—'))}\n\n"
                    f"如需修改請撥打 {get_clinic()['phone']}"
                )
            }])
        else:
            await reply_message(reply_token, [{
                "type": "text",
                "text": f"目前查無您的預約紀錄。\n如需預約請說「預約」，或撥打 {get_clinic()['phone']} 😊"
            }])

    elif any(k in text for k in keywords_booking):
        await reply_message(reply_token, [
            {
                "type": "text",
                "text": "您好！請點下方按鈕進行健檢預約 📋"
            },
            make_liff_button("📅 立即預約健檢", LIFF_APPT_URL)
        ])

    elif any(k in text for k in keywords_verify):
        await reply_message(reply_token, [
            {
                "type": "text",
                "text": (
                    "如果您已在診所完成預約，\n"
                    "請點下方按鈕綁定 LINE 帳號，\n"
                    "之後即可收到禁食提醒與報告通知 🔔"
                )
            },
            make_liff_button("🔐 綁定 LINE 帳號", LIFF_VERIFY_URL)
        ])

    elif any(k in text for k in keywords_report):
        await reply_message(reply_token, [
            {
                "type": "text",
                "text": "您的健檢報告可在綁定後查閱，AI 會用白話文解讀紅字數值 📋"
            },
            make_liff_button("📄 查看我的報告", LIFF_VERIFY_URL)
        ])

    elif any(k in text for k in keywords_hours):
        await reply_message(reply_token, [{
            "type": "text",
            "text": (
                "⭐ 門診時間\n"
                f"{get_clinic()['hours']}"
            )
        }])

    elif any(k in text for k in keywords_address):
        await reply_message(reply_token, [{
            "type": "text",
            "text": (
                f"📍 {get_clinic()['address']}\n"
                + (f"（{get_clinic()['addressNote']}）\n" if get_clinic()['addressNote'] else "")
                + f"\n📞 {get_clinic()['phone']}"
            )
        }])

    else:
        # 其他問題轉發給 Dify AI 智能回覆
        ai_reply = await call_dify(user_id, text)
        await reply_message(reply_token, [{
            "type": "text",
            "text": ai_reply
        }])


# ══════════════════════════════════════
#  LIFF 身分驗證綁定 API
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

    await push_message(req.line_user_id, [
        {
            "type": "text",
            "text": (
                f"✅ LINE 帳號綁定成功！\n\n"
                f"您好，{data.get('name', '')}！\n"
                f"之後健檢前我們會主動提醒您禁食注意事項，\n"
                f"健檢完成後也可以在 LINE 查看報告 📋"
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
    name:         str
    phone:        str
    plan:         str
    date:         str
    time_slot:    str
    line_user_id: str = ""
    birth:        str = ""
    id_number:    str = ""
    veg:          str = "葷"


@app.post("/api/appointment/book")
async def book_appointment(req: AppointmentRequest):
    plan_names = {
        "A": "A 方案（腦肺方案）",
        "B": "B 方案（腹部方案）",
        "C": "C 方案（骨密肌力方案）"
    }

    phone = req.phone.strip()
    if not phone.startswith("0"):
        phone = "0" + phone

    try:
        all_appts = db.reference("appointments").get() or {}
        target_key = None
        for id_num, data in all_appts.items():
            if isinstance(data, dict):
                stored = str(data.get("phone", ""))
                if not stored.startswith("0"):
                    stored = "0" + stored
                if stored == phone:
                    target_key = id_num
                    break

        record = {
            "name":     req.name,
            "phone":    phone,
            "plan":     req.plan,
            "date":     req.date,
            "time":     req.time_slot,
            "bookedAt": datetime.now().isoformat(),
            "source":   "LINE",
        }
        if req.birth:
            record["birth"] = req.birth
        if req.id_number:
            record["idNumber"] = req.id_number.upper()
        if req.veg:
            record["veg"] = req.veg
        if req.line_user_id:
            record["lineUserId"] = req.line_user_id

        if target_key:
            db.reference(f"appointments/{target_key}").update(record)
        else:
            new_key = req.id_number.upper().strip() if req.id_number else f"LIFF_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            db.reference(f"appointments/{new_key}").set(record)

    except Exception as e:
        print(f"book error: {e}")

    if req.line_user_id:
        await push_message(req.line_user_id, [{
            "type": "text",
            "text": (
                f"✅ 預約成功！\n\n"
                f"📋 方案：{plan_names.get(req.plan, req.plan)}\n"
                f"📅 日期：{req.date}\n"
                f"⏰ 時段：{req.time_slot}\n\n"
                f"健檢前我們會提醒您禁食注意事項 😊"
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


# ══════════════════════════════════════
#  後台管理 API
# ══════════════════════════════════════
@app.post("/api/admin/login")
async def admin_login(payload: dict):
    password = payload.get("password", "")
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="密碼錯誤")
    return {"status": "ok"}


def _extract_self_pay_items(raw: dict) -> list:
    """把 self_pay_booking 裡的 selfPayItems 整理成一個字串陣列（項目名稱）。
    Firebase 有時會把陣列存成 {0: ..., 1: ...} 這種物件形式，這裡一併處理。"""
    items = raw.get("selfPayItems")
    if not items:
        return []
    if isinstance(items, dict):
        try:
            items = [items[k] for k in sorted(items.keys(), key=lambda x: str(x))]
        except Exception:
            items = list(items.values())
    result = []
    for it in items:
        if isinstance(it, dict):
            name = it.get("name") or it.get("item") or it.get("itemName") or it.get("title")
            result.append(str(name) if name else json.dumps(it, ensure_ascii=False))
        elif it is not None:
            result.append(str(it))
    return result


@app.get("/api/admin/appointments")
async def admin_list_appointments(x_admin_password: Optional[str] = Header(None)):
    check_admin(x_admin_password)
    try:
        all_appts = db.reference("appointments").get() or {}
    except Exception:
        all_appts = {}
    try:
        all_selfpay = db.reference("self_pay_booking").get() or {}
    except Exception:
        all_selfpay = {}

    def _norm_phone(p):
        p = str(p or "").strip()
        if p and not p.startswith("0"):
            p = "0" + p
        return p

    # self_pay_booking 的 key 有時候是身分證字號、有時候是手機號碼，不固定，
    # 所以除了直接用 key 對應之外，再額外用「身分證字號」「手機號碼」欄位本身
    # 建立索引，兩邊都對不到才算真的沒有自費資料，避免同一個人被拆成
    # 「appointments 裡沒有自費項目」+「另一筆獨立的純自費」兩筆紀錄
    selfpay_by_idnumber = {}
    selfpay_by_phone = {}
    if isinstance(all_selfpay, dict):
        for sp_key, sp_val in all_selfpay.items():
            if not isinstance(sp_val, dict):
                continue
            sp_id = str(sp_val.get("idNumber") or "").strip().upper()
            sp_phone = _norm_phone(sp_val.get("phone"))
            if sp_id and sp_id not in selfpay_by_idnumber:
                selfpay_by_idnumber[sp_id] = sp_key
            if sp_phone and sp_phone not in selfpay_by_phone:
                selfpay_by_phone[sp_phone] = sp_key

    def _find_selfpay_key(appt_key, appt_data):
        if isinstance(all_selfpay, dict) and isinstance(all_selfpay.get(appt_key), dict):
            return appt_key
        appt_id = str(appt_data.get("idNumber") or "").strip().upper()
        if appt_id and appt_id in selfpay_by_idnumber:
            return selfpay_by_idnumber[appt_id]
        appt_phone = _norm_phone(appt_data.get("phone"))
        if appt_phone and appt_phone in selfpay_by_phone:
            return selfpay_by_phone[appt_phone]
        return None

    result = []
    matched_selfpay_keys = set()

    # 一般健檢預約（有些人同時也有自費項目，用身分證字號／手機號碼對應 self_pay_booking）
    for key, data in all_appts.items():
        if not isinstance(data, dict):
            continue
        item = dict(data)
        item["_key"] = key
        item["_bound"] = bool(data.get("lineUserId"))
        item["_pureSelfPay"] = False

        # 有些預約是「健檢＋自費」合在同一筆 appointments 資料裡，自費欄位
        # （selfPayItems / selfPayDate / ...）直接內嵌在這筆資料本身，根本不需要
        # 也不會出現在 self_pay_booking 節點裡。這種情況要優先採用，
        # 不然下面「去 self_pay_booking 找不到就清空」的邏輯會把它已經有的自費資料蓋掉。
        own_sp_items = _extract_self_pay_items(data)
        has_own_selfpay = bool(own_sp_items) or bool(data.get("selfPayDate")) or bool(data.get("selfPayTotal"))

        if has_own_selfpay:
            item["selfPayItems"] = own_sp_items
            item["selfPayTotal"] = data.get("selfPayTotal")
            item["selfPayCount"] = data.get("selfPayCount")
            item["selfPayDate"]  = data.get("selfPayDate")
            item["selfPayTime"]  = data.get("selfPayTime")
            item["_hasSelfPay"]  = bool(own_sp_items)
            # 如果剛好也能對應到 self_pay_booking 裡的一筆，順便標記掉，
            # 避免它又被當成一筆獨立的「純自費」重複出現
            sp_key = _find_selfpay_key(key, data)
            if sp_key:
                matched_selfpay_keys.add(sp_key)
        else:
            sp_key = _find_selfpay_key(key, data)
            sp = all_selfpay.get(sp_key) if sp_key and isinstance(all_selfpay, dict) else None
            if isinstance(sp, dict):
                matched_selfpay_keys.add(sp_key)
                sp_items = _extract_self_pay_items(sp)
                item["selfPayItems"] = sp_items
                item["selfPayTotal"] = sp.get("selfPayTotal")
                item["selfPayCount"] = sp.get("selfPayCount")
                item["selfPayDate"]  = sp.get("selfPayDate")
                item["selfPayTime"]  = sp.get("selfPayTime")
                item["_hasSelfPay"]  = bool(sp_items)
            else:
                item["selfPayItems"] = []
                item["_hasSelfPay"] = False

        result.append(item)

    # 純自費（沒有對應健檢預約）的紀錄，一樣顯示在同一張表，標記起來方便前端區分
    if isinstance(all_selfpay, dict):
        for key, sp in all_selfpay.items():
            if key in matched_selfpay_keys or not isinstance(sp, dict):
                continue
            sp_items = _extract_self_pay_items(sp)
            item = {
                "_key":         f"{SELFPAY_KEY_PREFIX}{key}",
                "_bound":       False,
                "_pureSelfPay": True,
                "_hasSelfPay":  bool(sp_items),
                "name":         sp.get("name", ""),
                "phone":        sp.get("phone", ""),
                "idNumber":     sp.get("idNumber", key),
                "birth":        sp.get("birth", ""),
                "plan":         "",
                "date":         "",
                "time":         "",
                "veg":          "",
                "source":       sp.get("source", "SELF_PAY_BOOKING"),
                "bookedAt":     sp.get("bookedAt", ""),
                "selfPayItems": sp_items,
                "selfPayTotal": sp.get("selfPayTotal"),
                "selfPayCount": sp.get("selfPayCount"),
                "selfPayDate":  sp.get("selfPayDate"),
                "selfPayTime":  sp.get("selfPayTime"),
                "extraAnswers": sp.get("extraAnswers"),
            }
            result.append(item)

    result.sort(key=lambda x: x.get("date") or x.get("selfPayDate") or "", reverse=True)
    return {"appointments": result}


class AdminCreateRequest(BaseModel):
    name:      str
    phone:     str
    plan:      str
    date:      str
    time:      str
    source:    str = "電話"
    birth:     str = ""
    id_number: str = ""
    note:      str = ""
    veg:       str = "葷"


@app.post("/api/admin/appointments")
async def admin_create_appointment(req: AdminCreateRequest, x_admin_password: Optional[str] = Header(None)):
    check_admin(x_admin_password)

    phone = req.phone.strip()
    if phone and not phone.startswith("0"):
        phone = "0" + phone

    record = {
        "name":     req.name,
        "phone":    phone,
        "plan":     req.plan,
        "date":     req.date,
        "time":     req.time,
        "source":   req.source,
        "bookedAt": datetime.now().isoformat(),
    }
    if req.birth:
        record["birth"] = req.birth
    if req.id_number:
        record["idNumber"] = req.id_number.upper()
    if req.note:
        record["note"] = req.note
    if req.veg:
        record["veg"] = req.veg

    key = req.id_number.upper().strip() if req.id_number else f"ADMIN_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    try:
        # 用 update 而非 set：若這個身分證字號原本就有資料（例如之前 Excel 匯入過），
        # update 只會覆蓋這次填寫的欄位，不會把其他既有欄位清空
        db.reference(f"appointments/{key}").update(record)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "success", "key": key}


class AdminUpdateRequest(BaseModel):
    name:      Optional[str] = None
    phone:     Optional[str] = None
    plan:      Optional[str] = None
    date:      Optional[str] = None
    time:      Optional[str] = None
    source:    Optional[str] = None
    birth:     Optional[str] = None
    id_number: Optional[str] = None
    note:      Optional[str] = None
    veg:       Optional[str] = None


@app.put("/api/admin/appointments/{key}")
async def admin_update_appointment(key: str, req: AdminUpdateRequest, x_admin_password: Optional[str] = Header(None)):
    check_admin(x_admin_password)

    if key.startswith(SELFPAY_KEY_PREFIX):
        raise HTTPException(status_code=400, detail="純自費紀錄目前不支援在後台編輯，請直接於 Firebase 修改")

    update_data = {}
    if req.name is not None: update_data["name"] = req.name
    if req.phone is not None:
        p = req.phone.strip()
        if p and not p.startswith("0"):
            p = "0" + p
        update_data["phone"] = p
    if req.plan is not None: update_data["plan"] = req.plan
    if req.date is not None: update_data["date"] = req.date
    if req.time is not None: update_data["time"] = req.time
    if req.source is not None: update_data["source"] = req.source
    if req.birth is not None: update_data["birth"] = req.birth
    if req.id_number is not None: update_data["idNumber"] = req.id_number.upper()
    if req.note is not None: update_data["note"] = req.note
    if req.veg is not None: update_data["veg"] = req.veg

    try:
        db.reference(f"appointments/{key}").update(update_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "success"}


@app.delete("/api/admin/appointments/{key}")
async def admin_delete_appointment(key: str, x_admin_password: Optional[str] = Header(None)):
    check_admin(x_admin_password)
    try:
        if key.startswith(SELFPAY_KEY_PREFIX):
            real_key = key[len(SELFPAY_KEY_PREFIX):]
            db.reference(f"self_pay_booking/{real_key}").delete()
        else:
            db.reference(f"appointments/{key}").delete()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "success"}


# ══════════════════════════════════════
#  診所設定（公版化）：名稱、電話、地址、門診時間、老人健檢可預約日期與時段
#  資料存放：Firebase  booking_config/clinic
#  沒設定時一律使用 CLINIC_DEFAULTS（也就是頤典診所原本的資料）
# ══════════════════════════════════════
CLINIC_DEFAULTS = {
    "name":         "頤典診所",
    "phone":        "02-2933-2010",
    "address":      "臺北市文山區羅斯福路六段407號2樓",
    "addressNote":  "由車前路門口上樓",
    "hours":        "週一至週五 早上 8:30-12:30、下午 13:30-17:30\n週六 早上 8:30-12:30\n週日公休\n國定假日門診半天",
    "elderlyDates": ["2026-11-02", "2026-11-04", "2026-11-09"],
    "elderlyTimes": ["08:00", "09:00", "10:00"],
    # 共用門診：星期 × 上午／下午／晚上，控制老人與自費健檢可預約日期
    "selfPayWeekly": {
        "sun": [], "mon": ["morning", "afternoon"], "tue": ["morning", "afternoon"],
        "wed": ["morning", "afternoon"], "thu": ["morning", "afternoon"],
        "fri": ["morning", "afternoon"], "sat": ["morning"],
    },
    "selfPaySessions": {"morning": "08:30-12:30", "afternoon": "13:30-17:30", "evening": "18:30-21:00"},
    "closedDates": [],
    "selfPayDailyLimit": 0,
    "elderlyDailyLimit": 0,
}

CLINIC_REQUIRED = {"name", "phone", "elderlyDates", "elderlyTimes"}

_clinic_cache = {"data": None, "at": 0.0}


def get_clinic(force: bool = False) -> dict:
    """讀取診所設定（快取 60 秒）；讀不到就用預設值。"""
    import time as _time
    now = _time.time()
    if not force and _clinic_cache["data"] and now - _clinic_cache["at"] < 60:
        return _clinic_cache["data"]
    merged = dict(CLINIC_DEFAULTS)
    try:
        saved = db.reference("booking_config/clinic").get() or {}
        if isinstance(saved, dict):
            for k, v in saved.items():
                if k not in CLINIC_DEFAULTS or v is None:
                    continue
                # 名稱、電話、日期、時段不可空白（空白就用預設）；地址補充等選填欄位允許留空
                if k in CLINIC_REQUIRED and v in ("", []):
                    continue
                merged[k] = v
    except Exception as e:
        print(f"讀取診所設定失敗，使用預設值：{e}")
    _clinic_cache.update(data=merged, at=now)
    return merged


class ClinicConfig(BaseModel):
    name:         str
    phone:        str
    address:      str = ""
    addressNote:  str = ""
    hours:        str = ""
    elderlyDates: list[str] = []
    elderlyTimes: list[str] = []
    selfPayWeekly: dict[str, list[str]] = {}
    selfPaySessions: dict[str, str] = {}
    closedDates: list[str] = []
    selfPayDailyLimit: int = 0
    elderlyDailyLimit: int = 0


@app.get("/api/clinic-config")
async def public_clinic_config():
    """公開讀取（後台登入頁、LINE 頁面顯示診所名稱用）"""
    return {"status": "success", "clinic": get_clinic()}


@app.get("/api/admin/clinic-config")
async def admin_get_clinic_config(x_admin_password: Optional[str] = Header(None)):
    check_admin(x_admin_password)
    # configured = 這家診所是否已經在後台儲存過設定（沒有的話，後台會顯示首次設定引導）
    try:
        configured = bool(db.reference("booking_config/clinic").get())
    except Exception:
        configured = False
    return {"clinic": get_clinic(force=True), "defaults": CLINIC_DEFAULTS, "configured": configured}


@app.put("/api/admin/clinic-config")
async def admin_save_clinic_config(cfg: ClinicConfig, x_admin_password: Optional[str] = Header(None)):
    import re as _re
    check_admin(x_admin_password)
    d = cfg.model_dump() if hasattr(cfg, "model_dump") else cfg.dict()
    for k in ("name", "phone", "address", "addressNote", "hours"):
        d[k] = (d.get(k) or "").strip()
    if not d["name"]:
        raise HTTPException(status_code=400, detail="診所名稱不可空白")
    if not d["phone"]:
        raise HTTPException(status_code=400, detail="電話不可空白")
    dates = sorted({x.strip() for x in d["elderlyDates"] if x and x.strip()})
    times = sorted({x.strip() for x in d["elderlyTimes"] if x and x.strip()})
    if any(not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", x) for x in dates):
        raise HTTPException(status_code=400, detail="日期格式需為 YYYY-MM-DD")
    if any(not _re.fullmatch(r"\d{2}:\d{2}", x) for x in times):
        raise HTTPException(status_code=400, detail="時段格式需為 HH:MM")
    if not dates or not times:
        raise HTTPException(status_code=400, detail="至少要有一個可預約日期和一個時段")
    d["elderlyDates"], d["elderlyTimes"] = dates, times

    # 共用門診時段：sun~sat × morning/afternoon/evening
    weekly = {}
    for day in ("sun", "mon", "tue", "wed", "thu", "fri", "sat"):
        sessions = (d.get("selfPayWeekly") or {}).get(day) or []
        weekly[day] = [x for x in ("morning", "afternoon", "evening") if x in sessions]
    if not any(weekly.values()):
        raise HTTPException(status_code=400, detail="自費健檢至少要開放一個門診時段")
    d["selfPayWeekly"] = weekly
    sess = d.get("selfPaySessions") or {}
    d["selfPaySessions"] = {
        "morning": (sess.get("morning") or CLINIC_DEFAULTS["selfPaySessions"]["morning"]).strip(),
        "afternoon": (sess.get("afternoon") or CLINIC_DEFAULTS["selfPaySessions"]["afternoon"]).strip(),
        "evening": (sess.get("evening") or CLINIC_DEFAULTS["selfPaySessions"]["evening"]).strip(),
    }
    closed = sorted({x.strip() for x in d.get("closedDates") or [] if x and x.strip()})
    if any(not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", x) for x in closed):
        raise HTTPException(status_code=400, detail="休診日格式需為 YYYY-MM-DD")
    d["closedDates"] = closed
    # 老人健檢日期必須與共用排班同步，無門診或臨時休診不得預約。
    from datetime import date as _date
    weekday_keys = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    valid_dates = []
    for value in dates:
        try:
            day = _date.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="老人健檢日期不是有效日曆日期")
        if weekly[weekday_keys[day.weekday()]] and value not in closed:
            valid_dates.append(value)
    if not valid_dates:
        raise HTTPException(status_code=400, detail="老人健檢沒有可預約日期，請先安排門診並選擇開診日")
    d["elderlyDates"] = valid_dates
    d["selfPayDailyLimit"] = max(0, int(d.get("selfPayDailyLimit") or 0))
    d["elderlyDailyLimit"] = max(0, int(d.get("elderlyDailyLimit") or 0))
    d["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    try:
        db.reference("booking_config/clinic").set(d)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"儲存失敗：{e}")
    get_clinic(force=True)
    return {"status": "success", "clinic": d}


# ══════════════════════════════════════
#  問診題目設定 API（診所後台可自行新增 / 修改 AI 要問的題目）
#  資料存放：Firebase  booking_config/questions
#  語音預約網站（website/main.py）會從同一位置讀取
# ══════════════════════════════════════
QUESTION_TYPES = {"text", "number", "choice", "yesno", "bmi"}
QUESTION_SCOPES = {"all", "elderly", "self_pay"}


class BookingQuestion(BaseModel):
    id:        str
    label:     str                     # 欄位名稱，例如「BMI」「過敏史」
    prompt:    str                     # AI 實際說出的問句
    type:      str = "text"            # text / number / choice / yesno / bmi
    options:   list[str] = []          # 單選題的選項
    unit:      str = ""                # 數字題單位，例如「公斤」
    min:       Optional[float] = None
    max:       Optional[float] = None
    followUp:  str = ""                # 是否題：回答「是／有」時追問
    required:  bool = True
    appliesTo: str = "all"             # all / elderly / self_pay
    enabled:   bool = True


class QuestionConfig(BaseModel):
    questions: list[BookingQuestion]


def _clean_questions(items: list[BookingQuestion]) -> list[dict]:
    cleaned, seen = [], set()
    for q in items:
        d = q.model_dump() if hasattr(q, "model_dump") else q.dict()
        d["id"] = (d.get("id") or "").strip()
        d["label"] = (d.get("label") or "").strip()
        d["prompt"] = (d.get("prompt") or "").strip()
        if not d["id"] or not d["label"] or not d["prompt"]:
            raise HTTPException(status_code=400, detail="每一題都需要填寫「欄位名稱」與「AI 問句」")
        if d["id"] in seen:
            raise HTTPException(status_code=400, detail=f"題目代號重複：{d['id']}")
        seen.add(d["id"])
        if d["type"] not in QUESTION_TYPES:
            d["type"] = "text"
        if d["appliesTo"] not in QUESTION_SCOPES:
            d["appliesTo"] = "all"
        d["options"] = [str(o).strip() for o in (d.get("options") or []) if str(o).strip()]
        if d["type"] == "choice" and len(d["options"]) < 2:
            raise HTTPException(status_code=400, detail=f"「{d['label']}」是選擇題，至少需要 2 個選項")
        cleaned.append(d)
    return cleaned


@app.get("/api/admin/questions")
async def admin_get_questions(x_admin_password: Optional[str] = Header(None)):
    check_admin(x_admin_password)
    try:
        data = db.reference("booking_config/questions").get() or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取題目失敗：{e}")
    items = data.get("items") if isinstance(data, dict) else data
    if isinstance(items, dict):  # Firebase 有時會把陣列存成 {0:...,1:...}
        items = [items[k] for k in sorted(items, key=lambda x: int(x))]
    return {
        "questions": [q for q in (items or []) if isinstance(q, dict)],
        "updatedAt": data.get("updatedAt", "") if isinstance(data, dict) else "",
    }


@app.put("/api/admin/questions")
async def admin_save_questions(cfg: QuestionConfig, x_admin_password: Optional[str] = Header(None)):
    check_admin(x_admin_password)
    cleaned = _clean_questions(cfg.questions)
    payload = {"items": cleaned, "updatedAt": datetime.now().isoformat(timespec="seconds")}
    try:
        db.reference("booking_config/questions").set(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"儲存題目失敗：{e}")
    return {"status": "success", "count": len(cleaned), "updatedAt": payload["updatedAt"]}


# ══════════════════════════════════════
#  Excel 批次匯入 API
#  欄位順序對應範本：姓名、手機號碼、身分證字號、出生年月日(民國)、
#  健檢方案(A/B/C)、葷素(葷/素)、預約日期、預約時段、來源、備註
# ══════════════════════════════════════
@app.post("/api/admin/import")
async def admin_import_excel(file: UploadFile = File(...), x_admin_password: Optional[str] = Header(None)):
    check_admin(x_admin_password)

    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="請上傳 Excel 檔案（.xlsx 或 .xls）")

    contents = await file.read()
    try:
        wb = load_workbook(io.BytesIO(contents), data_only=True)
        sheet = wb.worksheets[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"無法讀取 Excel 檔案：{e}")

    rows = list(sheet.iter_rows(min_row=2, values_only=True))

    imported = 0
    skipped = 0
    errors = []

    for idx, row in enumerate(rows, start=2):
        if not row or not row[0]:
            continue

        try:
            name      = str(row[0]).strip() if row[0] else ""
            phone     = str(row[1]).strip() if len(row) > 1 and row[1] else ""
            id_number = str(row[2]).strip().upper() if len(row) > 2 and row[2] else ""
            birth     = str(row[3]).strip() if len(row) > 3 and row[3] else ""
            plan      = str(row[4]).strip().upper() if len(row) > 4 and row[4] else ""
            veg       = str(row[5]).strip() if len(row) > 5 and row[5] else "葷"
            date_val  = row[6] if len(row) > 6 else None
            time_val  = row[7] if len(row) > 7 else None
            source    = str(row[8]).strip() if len(row) > 8 and row[8] else "Excel匯入"
            note      = str(row[9]).strip() if len(row) > 9 and row[9] else ""

            if not name or not phone or plan not in ("A", "B", "C"):
                skipped += 1
                errors.append(f"第 {idx} 列：缺少必填欄位或方案格式錯誤")
                continue

            # 葷素欄位標準化，避免 Excel 填寫時多打字或格式不一致
            if "葷" in veg:
                veg = "葷"
            elif "素" in veg:
                veg = "素"
            else:
                veg = "葷"

            # 處理日期格式（可能是 datetime 物件或字串）
            if hasattr(date_val, "strftime"):
                date_str = date_val.strftime("%Y-%m-%d")
            else:
                date_str = str(date_val).strip() if date_val else ""

            if hasattr(time_val, "strftime"):
                time_str = time_val.strftime("%H:%M")
            else:
                time_str = str(time_val).strip() if time_val else ""

            if not phone.startswith("0"):
                phone = "0" + phone

            record = {
                "name":     name,
                "phone":    phone,
                "plan":     plan,
                "date":     date_str,
                "time":     time_str,
                "veg":      veg,
                "source":   source,
                "bookedAt": datetime.now().isoformat(),
            }
            if birth:
                record["birth"] = birth
            if id_number:
                record["idNumber"] = id_number
            if note:
                record["note"] = note

            key = id_number if id_number else f"IMPORT_{datetime.now().strftime('%Y%m%d%H%M%S')}_{idx}"
            # 用 update 而非 set：同一位受檢者若被重複匯入（例如身分證字號相同），
            # 只會覆蓋這次表格帶來的欄位，不會清空該筆資料原本其他欄位
            db.reference(f"appointments/{key}").update(record)
            imported += 1

        except Exception as e:
            skipped += 1
            errors.append(f"第 {idx} 列：{str(e)}")

    return {
        "status": "success",
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:20]
    }


@app.get("/")
async def root():
    return {"status": "ok", "service": f"{get_clinic()['name']} LINE Bot API"}
