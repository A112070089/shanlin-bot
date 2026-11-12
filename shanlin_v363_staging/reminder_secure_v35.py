"""DOUBTS v3.5 safe *opt-in* one-day LINE appointment reminders.

For the separately deployed Shanlin LINE Bot, NOT the DOUBTS local UI.
No cron thread is started here. A separately authorized external scheduler
must call /api/reminder/v35/run. Sending is disabled by default.

Data policy: Firebase reminder_v35 stores only pseudonymous HMAC keys, claim
state, HTTP codes, times and aggregate counts; never phone, name, ID number,
LINE user ID, text body or raw credentials. LINE 2xx means API *accepted*,
not proof the person received or read the message.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
TAIPEI = ZoneInfo('Asia/Taipei')
API = 'https://api.line.me/v2/bot/message/push'
CANCELLED = {'cancelled','canceled','cancel','void','已取消','取消','退訂','作廢'}


@dataclass(frozen=True)
class Settings:
    job_token: str
    status_token: str
    hash_secret: str
    channel_token: str
    live_enabled: bool
    start_hour: int
    end_hour: int
    limit: int

    @classmethod
    def load(cls):
        def hour(key, default):
            try: return int(os.getenv(key, str(default)))
            except ValueError: return -1
        def cap():
            try: return max(1, min(100, int(os.getenv('REMINDER_V35_MAX_PER_RUN', '50'))))
            except ValueError: return 50
        return cls(
            os.getenv('REMINDER_V35_JOB_SECRET', ''),
            os.getenv('REMINDER_V35_STATUS_TOKEN', ''),
            os.getenv('REMINDER_V35_HASH_SECRET', ''),
            os.getenv('CHANNEL_ACCESS_TOKEN', ''),
            os.getenv('REMINDER_V35_SEND_ENABLED', '0') == '1',
            hour('REMINDER_V35_SEND_START_HOUR', 17),
            hour('REMINDER_V35_SEND_END_HOUR', 21),
            cap(),
        )


def _authenticate(provided: str | None, expected: str):
    # Fail closed on missing/short secrets; never use the old ADMIN_PASSWORD.
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail='安全金鑰尚未設定')
    if not provided or not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail='未獲授權')


def _db():
    from urllib.parse import urlparse
    parsed=urlparse(os.environ.get('FIREBASE_URL',''))
    if (parsed.scheme != 'https' or parsed.hostname != 'shanlin-clinic-default-rtdb.firebaseio.com'
            or parsed.path not in ('','/') or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise HTTPException(503,'山林專屬 Firebase 設定尚未驗證，已拒絕存取')
    from firebase_admin import db
    return db


def _pseudonym(secret: str, key: str, day: str) -> str:
    content = f'shanlin\x1f{key}\x1f{day}'.encode('utf-8')
    return hmac.new(secret.encode('utf-8'), content, hashlib.sha256).hexdigest()


def binding_proof(secret: str, appointment_key: str, line_user_id: str, phone: str) -> str:
    """Proof created ONLY after backend verifies a real LIFF access token.

    v3.5 does not issue these proofs. Do not self-approve old LINE bindings.
    HMAC ties the verified recipient to a specific appointment key, so the
    legacy booking API cannot silently swap the recipient while preserving
    an existing 'verified' boolean.
    """
    body=f'LINE_BIND_V352\x1fshanlin\x1f{appointment_key}\x1f{line_user_id}\x1f{phone}'
    return hmac.new(secret.encode('utf-8'),body.encode('utf-8'),hashlib.sha256).hexdigest()


def _verified_binding(item: dict, appointment_key: str, settings: Settings) -> bool:
    if len(settings.hash_secret)<32 or item.get('lineBindingVerified') is not True:
        return False
    proof=item.get('lineBindingProofV35')
    uid=item.get('lineUserId')
    phone=str(item.get('phone') or '').strip()
    if phone and not phone.startswith('0'):
        phone='0'+phone
    return (item.get('lineBindingVersion') == 352 and isinstance(proof,str) and len(proof)==64
            and isinstance(uid,str) and re.fullmatch(r'U[0-9a-fA-F]{32}',uid) is not None
            and re.fullmatch(r'09[0-9]{8}',phone) is not None
            and hmac.compare_digest(proof,binding_proof(settings.hash_secret,appointment_key,uid,phone)))


def _safe_item(item: object, target_date: str) -> bool:
    if not isinstance(item, dict) or item.get('date') != target_date:
        return False
    states = (str(item.get(key) or '').strip().lower() for key in ('status','appointmentStatus'))
    if any(state in CANCELLED for state in states) or item.get('cancelled') is True:
        return False
    user_id = item.get('lineUserId')
    if not isinstance(user_id, str) or not re.fullmatch(r'U[0-9a-fA-F]{32}', user_id):
        return False
    return True


def _safe_message(date_str: str, item: dict) -> str:
    # Do not invent or auto-push generic fasting/medication medical advice.
    time_slot = str(item.get('time') or '').strip()
    if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9](?:\s*-\s*(?:[01][0-9]|2[0-3]):[0-5][0-9])?', time_slot):
        time_slot = '請以診所確認的時間為準'
    return ('山林診所健檢預約提醒\n'
            f'提醒您明日 {date_str} 有預約，時間：{time_slot}。\n'
            '請攜帶預約所需證件。健檢準備及飲食注意事項，'
            '請以診所提供的個別衛教指示為準；如有疑問請聯絡診所。')


def _claim(claims, key: str, run_id: str, now_utc: str):
    ref = claims.child(key)
    retry_key = str(uuid.uuid4())
    initial = {'runId': run_id, 'state': 'reserved', 'atUtc': now_utc,
               'retryKey': retry_key, 'schema': 35}
    # Firebase transaction is atomic across workers/processes. No LINE call
    # occurs within a transaction callback (which Firebase may retry).
    value = ref.transaction(lambda existing: existing if existing is not None else initial)
    if not isinstance(value, dict) or value.get('runId') != run_id:
        return None
    return ref, retry_key


async def _line_push(settings: Settings, user_id: str, message: str, retry_key: str) -> tuple[str, int]:
    # No retries here. A timeout may mean LINE already accepted the request;
    # reserving the claim permanently prevents accidental duplicate sends.
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            response = await client.post(
                API,
                headers={'Authorization': f'Bearer {settings.channel_token}',
                         'Content-Type': 'application/json', 'X-Line-Retry-Key': retry_key},
                json={'to': user_id, 'messages': [{'type':'text','text':message}]},
            )
        if 200 <= response.status_code < 300:
            return 'accepted', response.status_code
        if response.status_code == 409 and response.headers.get('x-line-accepted-request-id'):
            return 'accepted', 409
        if response.status_code >= 500 or response.status_code in (408, 429):
            return 'uncertain', response.status_code
        return 'rejected', response.status_code
    except httpx.HTTPError:
        return 'uncertain', 0


async def execute(mode: str, settings: Settings | None = None, *, now: datetime | None = None,
                  database=None, sender=None) -> dict:
    """Run authorized preview/live dispatch; explicit injected test dependencies."""
    settings = settings or Settings.load()
    if mode not in ('preview', 'dispatch'):
        raise HTTPException(422, '未知執行模式')
    if mode == 'dispatch':
        # v3.5.2 is STAGING / PREVIEW ONLY; the live release needs a separate review.
        raise HTTPException(409, 'v3.5.2 測試版禁止正式發送 LINE')
    now = now or datetime.now(TAIPEI)
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    local = now.astimezone(TAIPEI)
    target = (local.date() + timedelta(days=1)).isoformat()
    if mode == 'dispatch':
        if not settings.live_enabled:
            raise HTTPException(409, '正式發送尚未啟用；預設僅可預覽')
        if len(settings.hash_secret) < 32 or len(settings.channel_token) < 16:
            raise HTTPException(503, '發送所需金鑰尚未完整設定')
        if not (0 <= settings.start_hour <= local.hour <= settings.end_hour <= 23):
            raise HTTPException(409, '不在允許的排程發送時段')
    database = database or _db()
    run_id = uuid.uuid4().hex
    now_utc = local.astimezone(timezone.utc).isoformat(timespec='seconds')
    appt_ref = database.reference('appointments')
    try:
        appts = appt_ref.get() or {}
        if not isinstance(appts, dict):
            raise TypeError('appointments is not a mapping')
    except Exception:
        raise HTTPException(503, '預約資料讀取失敗') from None

    summary = {'schema': 35, 'clinicId': 'shanlin', 'mode': mode,
               'targetDate': target, 'runAtUtc': now_utc,
               'eligible': 0, 'unverifiedBinding': 0, 'accepted': 0,
               'duplicateSkipped': 0, 'changedSkipped': 0, 'rejected': 0,
               'uncertain': 0, 'limitReached': 0, 'processed': 0}
    claims = database.reference('reminder_v35/claims') if mode == 'dispatch' else None
    sender = sender or _line_push
    for appt_key, item in appts.items():
        if not _safe_item(item, target):
            continue
        if not _verified_binding(item, str(appt_key), settings):
            summary['unverifiedBinding'] += 1
            continue
        summary['eligible'] += 1
        if mode != 'dispatch':
            continue
        if summary['processed'] >= settings.limit:
            summary['limitReached'] += 1
            continue
        try:
            claim = _claim(claims, _pseudonym(settings.hash_secret, str(appt_key), target), run_id, now_utc)
        except Exception:
            # No LINE call without a durable atomic claim.
            raise HTTPException(503, '防重複發送紀錄無法寫入，已停止發送') from None
        if claim is None:
            summary['duplicateSkipped'] += 1
            continue
        summary['processed'] += 1
        claim_ref, retry_key = claim
        # Check recent appointment state after taking claim; do not send a
        # cancelled/changed appointment that the first snapshot contained.
        try:
            latest = appt_ref.child(str(appt_key)).get()
        except Exception:
            latest = None
        if not _safe_item(latest, target) or not _verified_binding(latest,str(appt_key),settings) or any(
                latest.get(k) != item.get(k) for k in ('time', 'lineUserId', 'date')):
            summary['changedSkipped'] += 1
            claim_ref.update({'state':'changed_skipped','finishedAtUtc':now_utc})
            continue
        result, code = await sender(settings, latest['lineUserId'], _safe_message(target, latest), retry_key)
        if result not in ('accepted','rejected','uncertain'):
            result, code = 'uncertain', 0
        summary[result] += 1
        try:
            claim_ref.update({'state': result, 'httpStatus': int(code), 'finishedAtUtc':
                              datetime.now(timezone.utc).isoformat(timespec='seconds')})
        except Exception:
            # A reserved claim remains and blocks repeat sends. The recipient
            # may have received a message; don't claim a confirmed result.
            summary['uncertain'] += 1
            summary[result] -= 1
            break
    # Persist only aggregate run history and last-run state, never raw PII.
    # Failure to write does not allow duplicate sending; claims are durable.
    summary['finishedAtUtc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        database.reference('reminder_v35/runs').child(run_id).set(summary)
        database.reference('reminder_v35/last_run').set(summary)
    except Exception:
        raise HTTPException(503, '提醒狀態紀錄保存失敗；請先檢查防重複紀錄，勿重送') from None
    return summary


class RunRequest(BaseModel):
    mode: str = 'preview'


@router.post('/api/reminder/v35/run', include_in_schema=False)
async def authorized_run(body: RunRequest, x_reminder_job_token: str | None = Header(default=None)):
    settings = Settings.load()
    _authenticate(x_reminder_job_token, settings.job_token)
    return await execute(body.mode, settings)


@router.get('/api/reminder/v35/status', include_in_schema=False)
def authorized_status(x_reminder_status_token: str | None = Header(default=None)):
    settings = Settings.load()
    _authenticate(x_reminder_status_token, settings.status_token)
    try:
        last = _db().reference('reminder_v35/last_run').get()
    except Exception:
        raise HTTPException(503, '排程紀錄暫時無法讀取') from None
    if not isinstance(last, dict):
        last = None
    # No secrets, patient fields or recipient IDs in the status response.
    allowed = ('schema','clinicId','mode','targetDate','runAtUtc','finishedAtUtc','eligible',
               'unverifiedBinding','accepted','duplicateSkipped','changedSkipped',
               'rejected','uncertain','limitReached','processed')
    last = {key:last[key] for key in allowed if key in last} if last else None
    return {'schema':35,'clinicId':'shanlin','sendEnabled':settings.live_enabled,
            'authorizationConfigured':len(settings.job_token)>=32,
            'scheduler':{'type':'external','verified':False,
                         'note':'最近一次受授權執行不等於外部定時排程已設定；請核對 Cron 日誌'},
            'lastRun':last,'deliveryVerified':False,
            'messageStatusMeaning':'accepted = LINE Messaging API 接受，不代表實際送達或已讀'}

class BindingProofRequest(BaseModel):
    """Opt-in migration endpoint for LIFF: never accept client-supplied user IDs."""
    id_number: str = Field(min_length=10,max_length=12)
    phone: str = Field(min_length=10,max_length=16)
    line_access_token: str = Field(min_length=32,max_length=4096)


async def _verified_line_user(access_token: str, expected_channel: str) -> str | None:
    """Verify LINE Login token ownership, then fetch userId FROM LINE."""
    if not (32 <= len(access_token) <= 4096) or not expected_channel.isdigit():
        return None
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            verify = await client.get('https://api.line.me/oauth2/v2.1/verify',
                                      params={'access_token':access_token})
            if verify.status_code != 200:
                return None
            info=verify.json()
            if (not isinstance(info,dict) or str(info.get('client_id')) != expected_channel
                    or not isinstance(info.get('expires_in'), (int,float))
                    or info['expires_in'] <= 0):
                return None
            response=await client.get('https://api.line.me/v2/profile',
                headers={'Authorization':f'Bearer {access_token}'})
            if response.status_code != 200:
                return None
            profile=response.json()
            uid=profile.get('userId') if isinstance(profile,dict) else None
            return uid if isinstance(uid,str) and re.fullmatch(r'U[0-9a-fA-F]{32}',uid) else None
    except (httpx.HTTPError,ValueError,TypeError):
        return None


@router.post('/api/reminder/v35/binding/verify', include_in_schema=False)
async def verify_binding(body: BindingProofRequest):
    """Secure opt-in LIFF binding, only usable when linked frontend passes a
    real LIFF access token and service owner configures LIFF channel ID.

    The old /api/liff/verify remains for legacy flows but cannot issue proof.
    """
    settings=Settings.load()
    channel=os.environ.get('REMINDER_V35_LIFF_CHANNEL_ID','')
    if len(settings.hash_secret)<32 or not channel.isdigit():
        raise HTTPException(503,'安全 LINE 綁定尚未設定')
    key=body.id_number.upper().strip()
    phone=body.phone.strip()
    if (not re.fullmatch(r'[A-Z][12][0-9]{8}',key)
        or not re.fullmatch(r'09[0-9]{8}',phone)):
        raise HTTPException(400,'請確認輸入資料')
    uid=await _verified_line_user(body.line_access_token,channel)
    if not uid:
        raise HTTPException(403,'無法完成 LINE 身分驗證或預約資料核對')
    # Firebase-backed rate limit across service workers; no raw LINE ID stored.
    database=_db()
    now_epoch=int(datetime.now(timezone.utc).timestamp())
    rl_key=hmac.new(settings.hash_secret.encode(), ('RATE\x1f'+uid).encode(),hashlib.sha256).hexdigest()
    rl_ref=database.reference('reminder_v35/binding_rate').child(rl_key)
    def rate(current):
        if not isinstance(current,dict) or now_epoch-int(current.get('window',0)) >= 900:
            return {'window':now_epoch,'count':1}
        return {'window':int(current.get('window',now_epoch)),
                'count':min(1000,int(current.get('count',0))+1)}
    try:
        limit=rl_ref.transaction(rate)
    except Exception:
        raise HTTPException(503,'安全綁定檢查暫時無法使用') from None
    if int(limit.get('count',1000)) > 5:
        raise HTTPException(429,'綁定嘗試過多，請稍後再試')
    id_key=hmac.new(settings.hash_secret.encode(), ('TARGET\x1f'+key).encode(),hashlib.sha256).hexdigest()
    try:
        id_limit=database.reference('reminder_v35/binding_rate_target').child(id_key).transaction(rate)
    except Exception:
        raise HTTPException(503,'安全綁定檢查暫時無法使用') from None
    if int(id_limit.get('count',1000)) > 8:
        raise HTTPException(429,'綁定嘗試過多，請稍後再試')
    ref=database.reference('appointments').child(key)
    proof=binding_proof(settings.hash_secret,key,uid,phone)
    utc=datetime.now(timezone.utc).isoformat(timespec='seconds')
    def update(current):
        if not isinstance(current,dict):
            return current
        stored_phone=str(current.get('phone') or '').strip()
        if stored_phone and not stored_phone.startswith('0'):
            stored_phone='0'+stored_phone
        if stored_phone!=phone:
            return current
        # Prevent another LINE account from replacing an already verified binding.
        if (current.get('lineBindingVerified') is True
                and _verified_binding(current,key,settings)
                and current.get('lineUserId') != uid):
            return current
        return {**current,'lineUserId':uid,'lineBindingVerified':True,
                'lineBindingVersion':352,
                'lineBindingProofV35':proof,'lineVerifiedAtUtc':utc}
    try:
        result=ref.transaction(update)
    except Exception:
        raise HTTPException(503,'安全綁定目前無法完成') from None
    if (not isinstance(result,dict) or result.get('lineUserId')!=uid
            or not _verified_binding(result,key,settings)):
        raise HTTPException(403,'無法完成 LINE 身分驗證或預約資料核對')
    return {'status':'verified','clinicId':'shanlin','message':'LINE 帳號已安全綁定'}
