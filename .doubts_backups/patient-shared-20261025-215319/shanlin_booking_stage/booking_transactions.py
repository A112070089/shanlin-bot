"""Atomic CRUD on the ORIGINAL Shanlin appointments/self_pay_booking nodes.

TEST FIREBASE ONLY. A transaction at '/' is intentional: both legacy record
nodes and the clinic's explicit slot limits must be in one Firebase RTDB CAS.
For live use, migrate every writer to a bounded common booking node; never run
this root transaction against production or real patient data.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
import json
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
import os
from shanlin_v363_readonly import check_staging_configuration

SLOT_RE = re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d\Z')
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
KEY_RE = re.compile(r'[A-Za-z0-9_-]{1,90}\Z')
CANCELLED = {'cancelled', 'canceled', 'cancel', 'void', '已取消', '取消', '退訂', '作廢'}
MAX_RECORDS = 1000
MAX_DB_BYTES = 1024 * 1024  # Never start a root transaction on a large database.


def fail(status: int, message: str):
    raise HTTPException(status, message)


def _active(row: dict) -> bool:
    return row.get('cancelled') is not True and all(
        str(row.get(f) or '').strip().lower() not in CANCELLED
        for f in ('status', 'appointmentStatus')
    )


def _check_slot(day: object, slot: object, *, future: bool = False) -> tuple[str, str]:
    if not isinstance(day, str) or not DATE_RE.fullmatch(day):
        fail(422, '日期必須使用 YYYY-MM-DD')
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        fail(422, '日期不存在')
    if future and (parsed < datetime.now(ZoneInfo('Asia/Taipei')).date() or
                   parsed.year > datetime.now(ZoneInfo('Asia/Taipei')).year + 2):
        fail(422, '預約日期不在允許範圍')
    if not isinstance(slot, str) or not SLOT_RE.fullmatch(slot):
        fail(422, '預約時段必須使用 24 小時 HH:MM')
    return day, slot


def _normalize_phone(value: object) -> str:
    if not isinstance(value, str): fail(422, '手機號碼格式不正確')
    value = re.sub(r'[\s-]', '', value)
    if value and not value.startswith('0'): value = '0' + value
    if not re.fullmatch(r'09\d{8}', value): fail(422, '手機號碼格式不正確')
    return value


def _normalize_record(data: dict, *, for_create: bool) -> dict:
    allowed = {'name', 'phone', 'plan', 'date', 'time', 'source', 'birth',
               'id_number', 'note', 'veg', 'expectedRevision'}
    if not isinstance(data, dict) or set(data) - allowed: fail(422, '預約欄位不符')
    result = {}
    fields = allowed - {'expectedRevision'}
    for key in fields:
        if key not in data: continue
        val = data[key]
        if not isinstance(val, str): fail(422, '預約欄位必須為文字')
        val = val.strip()
        if len(val) > (500 if key == 'note' else 120): fail(422, '預約資料過長')
        result['idNumber' if key == 'id_number' else key] = val
    if for_create and not all(result.get(k) for k in ('name', 'phone', 'plan', 'date', 'time')):
        fail(422, '姓名、手機、方案、日期與時段皆為必填')
    if 'name' in result and not result['name']: fail(422, '姓名不可為空')
    if 'phone' in result: result['phone'] = _normalize_phone(result['phone'])
    if 'idNumber' in result:
        ident = result['idNumber'].upper()
        if ident and not re.fullmatch(r'[A-Z][12]\d{8}', ident): fail(422, '證件字號格式不正確')
        result['idNumber'] = ident
    if 'plan' in result and result['plan'] not in ('A', 'B', 'C'):
        fail(422, '僅可選擇 A、B、C 健檢方案')
    if 'date' in result or 'time' in result:
        if for_create:
            _check_slot(result.get('date'), result.get('time'), future=True)
    if for_create:
        result['clinicId'] = 'shanlin'
        result['doubtsSyntheticV363'] = True
        result['status'] = 'confirmed'
        result['source'] = result.get('source') or '電話'
        result['bookedAt'] = datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
    return result


def _validated_root(raw: object) -> dict:
    if not isinstance(raw, dict) or len(json.dumps(raw, ensure_ascii=False, default=str).encode('utf-8')) > MAX_DB_BYTES:
        fail(503, '獨立測試資料庫結構過大或不正確，禁止預約交易')
    config = raw.get('booking_config')
    clinic = config.get('clinic') if isinstance(config, dict) else None
    if not isinstance(clinic, dict) or clinic.get('clinicId') != 'shanlin' or clinic.get('name') != '山林診所' or clinic.get('integrationV363TestOnly') is not True:
        fail(409, '獨立測試診所身分未確認')
    for node in ('appointments', 'self_pay_booking'):
        rows = raw.get(node) or {}
        if not isinstance(rows, dict) or len(rows) > MAX_RECORDS:
            fail(503, '測試預約資料節點格式不正確')
        for key, item in rows.items():
            if not isinstance(key, str) or not KEY_RE.fullmatch(key) or not isinstance(item, dict):
                fail(503, '測試預約資料格式不正確')
            if item.get('clinicId') not in (None, 'shanlin') or item.get('doubtsSyntheticV363') is not True:
                fail(409, '資料含非山林或非合成預約，拒絕所有寫入')
    return raw


def _capacity(root: dict, day: str, slot: str) -> int:
    config = root['booking_config']['clinic']
    caps = config.get('capacityBySlot')
    value = (caps.get(day) or {}).get(slot) if isinstance(caps, dict) and isinstance(caps.get(day), dict) else None
    if type(value) is not int or value < 1 or value > 100:
        fail(409, '該日期時段尚未設定明確名額，禁止預約')
    # A separate explicit allowlist prevents adding slots just by guessing.
    if day not in (config.get('elderlyDates') or []) or slot not in (config.get('elderlyTimes') or []):
        fail(409, '診所尚未正式開放此測試日期及時段')
    return value


def _row_slot(row: dict, *, selfpay: bool) -> tuple[str, str]:
    date_field, time_field = ('selfPayDate','selfPayTime') if selfpay else ('date','time')
    return _check_slot(row.get(date_field),row.get(time_field))


def _occupied(root: dict, day: str, slot: str, *, exclude: tuple[str, str] | None = None) -> int:
    """Original two-node matching: no undercounts when contacts are ambiguous."""
    checkups = root.get('appointments') or {}
    selfpay = root.get('self_pay_booking') or {}
    on_slot = {}
    excluded_row = checkups.get(exclude[1]) if exclude and exclude[0] == 'appointments' else None
    for key, row in checkups.items():
        if not _active(row): continue
        at = _row_slot(row, selfpay=False)
        if exclude == ('appointments', key): continue
        if at == (day, slot): on_slot[key] = row
    count = len(on_slot)
    for key, row in selfpay.items():
        if not _active(row): continue
        at = _row_slot(row, selfpay=True)
        if exclude == ('self_pay_booking', key) or at != (day, slot): continue
        # The legacy backend joins self-pay by exact key, then ID or phone.
        if key in on_slot: continue
        # A checkup being edited is excluded from occupancy, but its linked
        # self-pay charge must also be excluded or a no-op edit looks 'full'.
        if isinstance(excluded_row,dict) and (
            key == exclude[1] or
            (row.get('idNumber') and str(row['idNumber']).strip().upper()==str(excluded_row.get('idNumber') or '').strip().upper()) or
            (row.get('phone') and str(row['phone']).strip().replace('-','')==str(excluded_row.get('phone') or '').strip().replace('-',''))
        ):
            continue
        identity = str(row.get('idNumber') or '').strip().upper()
        phone = str(row.get('phone') or '').strip().replace('-', '')
        if phone and not phone.startswith('0'): phone='0'+phone
        hits_by_id = [k for k,r in on_slot.items() if identity and
                      str(r.get('idNumber') or '').strip().upper() == identity]
        if len(hits_by_id)>1: fail(409, '自費與健檢預約關聯不明，無法保證名額')
        if hits_by_id: continue
        hits_by_phone = [k for k,r in on_slot.items() if phone and
                         str(r.get('phone') or '').strip().replace('-', '') == phone]
        if len(hits_by_phone)>1: fail(409, '同電話有多筆健檢預約，自費名額需人工核對')
        if hits_by_phone: continue
        count += 1
    return count


def _duplicate(root: dict, phone: str, identity: str, *, ignore_key: str | None = None):
    existing = (root.get('appointments') or {}).get(ignore_key) if ignore_key else None
    for node in ('appointments','self_pay_booking'):
        for key,row in (root.get(node) or {}).items():
            if not _active(row) or (node == 'appointments' and key == ignore_key): continue
            other_phone = str(row.get('phone') or '').strip().replace('-','')
            if other_phone and not other_phone.startswith('0'): other_phone='0'+other_phone
            other_id = str(row.get('idNumber') or '').strip().upper()
            if (phone and other_phone == phone) or (identity and other_id == identity):
                # On an UPDATE, the original self-pay row may legitimately be
                # joined to the target checkup. Do not block that person's edit.
                if node == 'self_pay_booking' and existing and (
                    key == ignore_key or (other_id and other_id == str(existing.get('idNumber') or '').strip().upper())
                    or (other_phone and other_phone == str(existing.get('phone') or '').strip().replace('-',''))
                ):
                    continue
                fail(409, '已有相同聯絡資料的預約，請人工核對避免覆寫')


def _revision(row: dict) -> str:
    if row.get('_bookingRevisionV365'):
        return str(row['_bookingRevisionV365'])
    return sha256(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


class BookingStore:
    """Same original RTDB schema, no new source of truth."""
    def __init__(self, database):
        # Enforce test Firebase ownership even when this class is used directly,
        # not just through the localhost HMAC HTTP router.
        check_staging_configuration()
        self.database = database

    def _read(self): return _validated_root(self.database.reference('/').get() or {})

    def list(self):
        """Reproduce the ORIGINAL Shanlin admin's paired self-pay display."""
        root = self._read()
        appts = root.get('appointments') or {}
        selfpay = root.get('self_pay_booking') or {}
        out = []
        claimed = set()
        for key, raw in appts.items():
            row = {**raw, '_key': key, '_revision': _revision(raw),
                   '_pureSelfPay': False, '_bound': bool(raw.get('lineUserId'))}
            matched = None
            if key in selfpay:
                matched = key
            else:
                id_value = str(raw.get('idNumber') or '').strip().upper()
                phone_value = str(raw.get('phone') or '').strip().replace('-', '')
                if phone_value and not phone_value.startswith('0'): phone_value='0'+phone_value
                ids = [k for k,v in selfpay.items() if id_value and
                       str(v.get('idNumber') or '').strip().upper() == id_value]
                phones = [k for k,v in selfpay.items() if phone_value and
                          str(v.get('phone') or '').strip().replace('-', '') == phone_value]
                if len(ids)>1 or len(phones)>1:
                    fail(409, '健檢與自費資料關聯不明，拒絕合併')
                matched = (ids or phones or [None])[0]
            if matched is not None:
                if matched in claimed: fail(409, '同一筆自費預約對應多筆健檢，拒絕合併')
                claimed.add(matched)
                extra = selfpay[matched]
                raw_items = extra.get('selfPayItems') or []
                if isinstance(raw_items, dict):
                    raw_items = [raw_items[k] for k in sorted(raw_items)]
                if not isinstance(raw_items, list): fail(503, '自費項目格式不正確')
                row['selfPayItems'] = [
                    str(x.get('name') or x.get('itemName') or x.get('item') or x.get('title') or '')
                    if isinstance(x,dict) else str(x) for x in raw_items
                ]
                row['selfPayTotal'] = extra.get('selfPayTotal')
                row['selfPayCount'] = extra.get('selfPayCount')
                row['selfPayDate'] = extra.get('selfPayDate')
                row['selfPayTime'] = extra.get('selfPayTime')
            else:
                row['selfPayItems'] = raw.get('selfPayItems') or []
            row['_hasSelfPay'] = bool(row['selfPayItems'])
            out.append(row)
        for key, raw in selfpay.items():
            if key in claimed: continue
            row = {**raw, '_key':'SELFPAY::'+key, '_revision':_revision(raw),
                   '_pureSelfPay':True, '_bound':False, '_hasSelfPay':bool(raw.get('selfPayItems')),
                   'date':raw.get('selfPayDate',''), 'time':raw.get('selfPayTime',''),
                   'plan':'SELF_PAY'}
            out.append(row)
        return {'clinicId':'shanlin','isSynthetic':True,'appointments':out,
                'capacitySource':'booking_config/clinic/capacityBySlot'}

    def change(self, action: str, payload: dict, key: str | None = None):
        if os.getenv('SHANLIN_V365_SYNTHETIC_WRITE_ENABLED') != '1':
            fail(423, '合成資料預約交易尚未開放')
        if action not in ('create','update','cancel'): fail(422, '未知預約操作')
        if key is not None and (not KEY_RE.fullmatch(key) or key.startswith('SELFPAY::')):
            fail(422, '無效的預約識別碼')
        data = _normalize_record(payload, for_create=(action == 'create')) if action != 'cancel' else {}
        expected = payload.get('expectedRevision')
        if action != 'create' and (not isinstance(expected, str) or len(expected) < 32 or len(expected) > 64):
            fail(428, '修改／取消需要預約的最新版本識別碼')
        if action == 'create':
            key = 'TEST_' + uuid4().hex.upper()
        now = datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
        def transact(current):
            # Work on a deep copy: a rejected transaction never mutates the supplied object.
            root = deepcopy(_validated_root(current))
            if root.get('appointments') is None: root['appointments'] = {}
            rows = root['appointments']
            old = rows.get(key)
            if action == 'create':
                if old is not None: fail(409, '預約識別碼已存在')
                _duplicate(root, data['phone'], data.get('idNumber',''))
                _capacity(root, data['date'], data['time'])
                if _occupied(root, data['date'], data['time']) >= _capacity(root,data['date'],data['time']):
                    fail(409, '時段名額已滿')
                new = data.copy()
                new['_bookingRevisionV365'] = uuid4().hex
                rows[key] = new
            else:
                if not isinstance(old, dict): fail(404, '找不到預約紀錄')
                if _revision(old) != expected: fail(409, '資料已被其他人更新，請重新載入')
                if not _active(old): fail(409, '此筆預約已取消，不可再次編輯')
                if action == 'cancel':
                    new = {**old,'status':'cancelled','cancelled':True,
                           'cancelledAt':now, 'cancelledBy':'verified_shanlin_admin'}
                else:
                    new = {**old, **data}
                    if ('phone' in data and data['phone'] != str(old.get('phone') or '')) and old.get('lineBindingVerified') is True:
                        fail(409, '已驗證 LINE 綁定的電話不可直接變更，請先重新驗證')
                    if any(
                        _active(sp) and (
                            sp_key==key or
                            (sp.get('idNumber') and str(sp.get('idNumber')).strip().upper()==str(old.get('idNumber') or '').strip().upper()) or
                            (sp.get('phone') and str(sp.get('phone')).strip().replace('-','')==str(old.get('phone') or '').strip().replace('-',''))
                        ) for sp_key,sp in (root.get('self_pay_booking') or {}).items()
                    ) and (new.get('phone') != old.get('phone') or new.get('idNumber') != old.get('idNumber')):
                        fail(409,'健檢已連結自費預約，修改身分資料須先人工核對')
                    _duplicate(root, new.get('phone',''),new.get('idNumber',''),ignore_key=key)
                    day,slot = _check_slot(new.get('date'),new.get('time'),future=True)
                    limit = _capacity(root,day,slot)
                    if _occupied(root,day,slot,exclude=('appointments',key)) >= limit:
                        fail(409, '時段名額已滿')
                    new['updatedAt'] = now
                new['_bookingRevisionV365'] = uuid4().hex
                rows[key] = new
            return root
        try:
            result = self.database.reference('/').transaction(transact)
        except HTTPException: raise
        except Exception:
            fail(503, '獨立測試 Firebase 預約交易失敗，沒有成功確認')
        # Firebase transaction returns the new snapshot; never echo patients.
        updated = (result.get('appointments') or {}).get(key) if isinstance(result,dict) else None
        if not isinstance(updated,dict): fail(503, '交易回應無法確認，請人工檢查資料')
        return {'status':'success','clinicId':'shanlin','isSynthetic':True,
                'key':key,'revision':_revision(updated),'action':action}
