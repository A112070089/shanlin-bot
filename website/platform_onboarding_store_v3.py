"""Engineer-only, local V3 tenant onboarding staging registry.

Never modifies V2 drafts, existing tenants, Firebase, appointments, or published
catalogs. Passwords are PBKDF2 hashes, never returned through read endpoints.
V3 readiness is administrative *review*, NOT production activation.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hmac import compare_digest
from pathlib import Path
from urllib.parse import urlsplit
import fcntl
import json
import os
import re
import secrets
import tempfile

import pilot_backend as backend
import platform_clinic_registry as drafts
from platform_console_store import FEATURES

ZERO = '0' * 32
HEX_RE = re.compile(r'[0-9a-f]{32}\Z', re.ASCII)
USERNAME_RE = re.compile(r'[a-zA-Z][a-zA-Z0-9_.-]{3,63}\Z', re.ASCII)
PHONE_RE = re.compile(r'[0-9+()\-\s]{6,30}\Z', re.ASCII)
ENV_RE = re.compile(r'[A-Z][A-Z0-9_]*\Z', re.ASCII)
STORAGE_MODES = {'unconfigured', 'firebase_rtdb'}


class RevisionConflict(Exception):
    pass


def _paths() -> tuple[Path, Path]:
    base = backend.private_dir()
    return base / 'platform_clinic_onboarding_v3.json', base / '.platform_clinic_onboarding_v3.lock'


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _default():
    return {'schemaVersion': 3, 'revision': ZERO, 'clinics': {}, 'audit': []}


def _load(path: Path):
    if not path.exists():
        return _default()
    with path.open('r', encoding='utf-8') as handle:
        data = json.load(handle)
    if (not isinstance(data, dict) or data.get('schemaVersion') != 3
            or not HEX_RE.fullmatch(str(data.get('revision', '')))
            or not isinstance(data.get('clinics'), dict)
            or not isinstance(data.get('audit'), list)):
        raise RuntimeError('v3 導入資料格式錯誤，已拒絕修改')
    for slug, obj in data['clinics'].items():
        if (not isinstance(slug, str) or not drafts.CLINIC_ID_RE.fullmatch(slug)
                or slug in drafts.EXISTING or not isinstance(obj, dict)
                or not isinstance(obj.get('profile'), dict)
                or not isinstance(obj.get('account'), dict)
                or not isinstance(obj.get('features'), dict)
                or obj.get('storageMode') not in STORAGE_MODES
                or obj.get('reviewState') not in ('draft', 'pending_review')):
            raise RuntimeError('v3 診所資料不相容，已拒絕讀取')
    return data


@contextmanager
def _exclusive():
    path, lock_file = _paths()
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield path
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _atomic(path: Path, data: dict):
    fd, filename = tempfile.mkstemp(dir=str(path.parent), prefix='.onboard-v3-', suffix='.tmp')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(filename, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)


def _draft(slug: str, *, must_be_active=False) -> dict:
    # Never onboard existing Shanlin/Yidian or reserved system clinic IDs.
    drafts._verify_slug(slug)
    result = next((item for item in drafts.read_state()['drafts']
                   if item['clinicId'] == slug), None)
    if result is None:
        raise ValueError('診所草稿不存在，請先在 v2 診所管理中心建立')
    if must_be_active and result['archived']:
        raise ValueError('此診所草稿已封存，不能修改開通設定')
    return result


def _initial():
    return {
        'profile': {'phone': '', 'address': '', 'hours': ''},
        'account': {}, 'storageMode': 'unconfigured',
        'features': {fid: False for fid in FEATURES},
        'reviewState': 'draft', 'reviewedAt': None, 'updatedAt': None,
    }


def _env_names(slug: str) -> dict:
    base = 'PILOT_TENANT_' + slug.upper().replace('-', '_') + '_'
    return {'url': base + 'FIREBASE_URL', 'credentials': base + 'FIREBASE_CREDENTIALS'}


def _firebase_host(value: str):
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port is not None:
            return None
        if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            return None
        host = (parsed.hostname or '').lower()
        if host.endswith('.firebaseio.com') or host.endswith('.firebasedatabase.app'):
            return host
    except ValueError:
        pass
    return None


def _storage_status(slug: str, mode: str):
    names = _env_names(slug)
    url = os.environ.get(names['url'], '').strip()
    creds = os.environ.get(names['credentials'], '').strip()
    hostname = _firebase_host(url) if url else None
    used = [os.environ.get(key, '').strip() for key in
            ('PILOT_SHANLIN_FIREBASE_URL', 'PILOT_YIDIAN_FIREBASE_URL', 'FIREBASE_URL')]
    # Do not allow an onboarding clinic to target the known existing tenant DB host.
    distinct = bool(hostname) and not any(_firebase_host(item) == hostname for item in used if item)
    return {
        'mode': mode, 'envNames': names,
        'urlPresent': bool(url), 'credentialsPresent': bool(creds),
        'urlFormatValid': bool(hostname), 'distinctFromKnownClinics': bool(distinct),
        # The only true check here is env presence. We deliberately DO NOT
        # claim Firebase read/write connectivity or clinical data isolation.
        'configurationPresent': mode == 'firebase_rtdb' and bool(creds) and bool(distinct),
        'connectionVerified': False, 'isolationVerified': False,
    }


def _public(slug: str, draft: dict, entry: dict, revision: str) -> dict:
    profile = entry['profile']
    account = entry['account']
    storage = _storage_status(slug, entry['storageMode'])
    profile_ready = (bool(PHONE_RE.fullmatch(profile.get('phone', '')))
                     and bool(profile.get('address', '').strip())
                     and bool(profile.get('hours', '').strip()))
    account_ready = bool(account.get('username') and account.get('passwordHash'))
    checklist = [
        {'key': 'draft', 'title': '導入草稿仍有效', 'passed': not draft['archived']},
        {'key': 'profile', 'title': '診所電話、地址、服務時間已填寫', 'passed': profile_ready},
        {'key': 'account', 'title': '獨立管理帳號已建立（密碼雜湊）', 'passed': account_ready},
        {'key': 'storage_config', 'title': '專屬 Firebase 環境變數已提供，且網域與已知診所不同', 'passed': storage['configurationPresent']},
        {'key': 'storage_verified', 'title': '獨立 Firebase 讀寫／安全規則驗證', 'passed': False},
        {'key': 'booking_verified', 'title': '預約 API、醫師時段與端到端驗收', 'passed': False},
    ]
    return {
        'clinicId': slug, 'displayName': draft['displayName'],
        'archived': draft['archived'], 'revision': revision,
        'profile': dict(profile), 'account': {
            'created': account_ready,
            'username': account.get('username', ''),
            'updatedAt': account.get('updatedAt'),
        },
        'storage': storage,
        'features': [{'id': fid, 'name': info['name'], 'description': info['description'],
                      'enabled': entry['features'].get(fid) is True,
                      'deployed': info['deployment'] == 'deployed'}
                     for fid, info in FEATURES.items()],
        'reviewState': entry['reviewState'], 'reviewedAt': entry['reviewedAt'],
        'checklist': checklist,
        'maySubmitForReview': all(item['passed'] for item in checklist[:4]),
        'readyForBooking': False, 'readyForProduction': False,
        'notice': 'v3 僅建立本機導入管理設定；不會啟用正式預約、建立 Firebase 專案或部署模組。',
    }


def read(slug: str):
    draft = _draft(slug)
    path, _ = _paths()
    data = _load(path)
    return _public(slug, draft, data['clinics'].get(slug, _initial()), data['revision'])


def audit_tail(slug: str, limit=30):
    _draft(slug)
    data = _load(_paths()[0])
    return list(reversed([a for a in data['audit'] if a.get('clinicId') == slug][-limit:]))


def _note_audit(data: dict, slug: str, action: str, actor: str):
    data['audit'] = (data['audit'] + [{'timestamp': _now(), 'clinicId': slug,
                       'actor': actor[:64], 'action': action}])[-500:]


def _mutate(slug: str, revision: str, actor: str, action: str, change):
    _draft(slug, must_be_active=True)
    with _exclusive() as path:
        # Recheck after acquiring v3 lock to reject an archived draft.
        _draft(slug, must_be_active=True)
        data = _load(path)
        if data['revision'] != revision:
            raise RevisionConflict('其他工作階段已更新此開通設定，請重新整理')
        item = data['clinics'].setdefault(slug, _initial())
        result = change(item, data)
        if result is False:
            return _public(slug, _draft(slug), item, data['revision'])
        item['reviewState'] = 'draft' if action != 'submitted_for_review' else 'pending_review'
        if action != 'submitted_for_review':
            item['reviewedAt'] = None
        item['updatedAt'] = _now()
        data['revision'] = secrets.token_hex(16)
        _note_audit(data, slug, action, actor)
        _atomic(path, data)
        return _public(slug, _draft(slug), item, data['revision'])


def save_profile(slug: str, *, phone: str, address: str, hours: str, revision: str, actor: str):
    phone = phone.strip()
    address = address.strip()
    hours = hours.strip()
    if phone and not PHONE_RE.fullmatch(phone):
        raise ValueError('診所電話格式不正確，請使用數字、空格及常見電話符號')
    if len(address) > 160 or len(hours) > 100 or any(ord(c) < 32 for c in phone + address + hours):
        raise ValueError('診所地址或營業時間格式不正確')
    def apply(item, _):
        target = {'phone': phone, 'address': address, 'hours': hours}
        if item['profile'] == target:
            return False
        item['profile'] = target
    return _mutate(slug, revision, actor, 'profile_updated', apply)


def _username_available(username: str, slug: str, data: dict):
    if not USERNAME_RE.fullmatch(username):
        raise ValueError('帳號須為 4–64 字英文、數字或 ._-，且以字母開頭')
    if username.lower() in {'shanlin_admin', 'yidian_admin', 'platform_admin'}:
        raise ValueError('不能沿用既有診所或工程師的保留帳號')
    # Existing engine account names, if actually set, also reserved.
    try:
        with backend.accounts_path().open('r', encoding='utf-8') as file:
            existing = json.load(file)
    except FileNotFoundError:
        existing = {}
    for value in existing.values():
        if isinstance(value, dict) and value.get('username', '').lower() == username.lower():
            raise ValueError('帳號名稱與已存在的管理員帳號重複')
    for other_slug, other in data['clinics'].items():
        if other_slug != slug and other.get('account', {}).get('username', '').lower() == username.lower():
            raise ValueError('帳號名稱已由其他新診所使用')


def save_account(slug: str, *, username: str, password: str, reset: bool,
                 revision: str, actor: str):
    username = username.strip()
    if not 12 <= len(password) <= 256:
        raise ValueError('密碼長度須為 12 至 256 字元')
    if type(reset) is not bool:
        raise ValueError('重設密碼選項不正確')
    def apply(item, data):
        _username_available(username, slug, data)
        if item['account'] and not reset:
            raise ValueError('此診所已建立管理帳號；重設須明確勾選重設密碼')
        item['account'] = {'username': username, 'passwordHash': backend.make_hash(password),
                           'updatedAt': _now()}
    result = _mutate(slug, revision, actor, 'account_reset' if reset else 'account_created', apply)
    # Force old staging sessions to reauthenticate after a credential rotation.
    if reset:
        backend.invalidate_sessions(slug)
    return result


def check_account(slug: str, *, username: str, password: str) -> bool:
    try:
        draft = _draft(slug)
        if draft['archived']:
            return False
    except ValueError:
        return False
    account = _load(_paths()[0])['clinics'].get(slug, {}).get('account', {})
    if not account.get('username') or not account.get('passwordHash'):
        return False
    return (compare_digest(account['username'], username)
            and backend.verify_hash(password, account['passwordHash']))


def save_storage_mode(slug: str, *, mode: str, revision: str, actor: str):
    if mode not in STORAGE_MODES:
        raise ValueError('不支援的資料庫設定模式')
    def apply(item, _):
        if item['storageMode'] == mode:
            return False
        item['storageMode'] = mode
    return _mutate(slug, revision, actor, 'storage_intent_updated', apply)


def save_feature(slug: str, *, feature_id: str, enabled: bool, revision: str, actor: str):
    if feature_id not in FEATURES or type(enabled) is not bool:
        raise ValueError('不支援的功能模組或授權值')
    def apply(item, _):
        if item['features'].get(feature_id) is enabled:
            return False
        item['features'][feature_id] = enabled
    return _mutate(slug, revision, actor, 'feature_preauthorization_updated', apply)


def submit_review(slug: str, *, revision: str, actor: str):
    def apply(item, data):
        state = _public(slug, _draft(slug), item, data['revision'])
        if not state['maySubmitForReview']:
            raise ValueError('尚未完成診所資料、管理帳號或 Firebase 設定檢查，不能送交驗收')
        if item['reviewState'] == 'pending_review':
            return False
        item['reviewedAt'] = _now()
    return _mutate(slug, revision, actor, 'submitted_for_review', apply)
