"""Local-only draft clinic onboarding registry for the DOUBTS engineer console.

Draft registrations NEVER provision users, modify clinic settings, touch Firebase,
change live routing, grant feature entitlements, or accept patient data.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import json
import os
import re
import secrets
import tempfile

import pilot_backend

REVISION_ZERO = '0' * 32
MAX_DRAFTS = 50
EXISTING = {'yidian': '頤典診所', 'shanlin': '山林診所'}
RESERVED = {'platform', 'api', 'pilot', 'admin', 'static', 'website', 'health', 'login', 'system'}
CLINIC_ID_RE = re.compile(r'[a-z][a-z0-9-]{2,31}\Z', re.ASCII)
REVISION_RE = re.compile(r'[a-f0-9]{32}\Z', re.ASCII)


def _paths() -> tuple[Path, Path]:
    root = pilot_backend.private_dir()
    return root / 'platform_clinic_registry_v2.json', root / '.platform_clinic_registry_v2.lock'


def _default() -> dict:
    return {'schemaVersion': 2, 'revision': REVISION_ZERO, 'drafts': {}, 'tombstones': {}, 'audit': []}


def _load(path: Path) -> dict:
    if not path.exists():
        return _default()
    with path.open('r', encoding='utf-8') as file:
        data = json.load(file)
    if (not isinstance(data, dict) or data.get('schemaVersion') != 2
            or not REVISION_RE.fullmatch(str(data.get('revision', '')))
            or not isinstance(data.get('drafts'), dict)
            or not isinstance(data.get('audit'), list)):
        raise RuntimeError('新診所草稿資料版本不相容，已拒絕讀取與修改')
    # Tombstones preserve only the retired clinic ID and audit metadata.  This
    # prevents silently reusing a purged tenant ID with stale browser bookmarks
    # or legacy sessions after the local staging data has been removed.
    if not isinstance(data.get('tombstones', {}), dict):
        raise RuntimeError('已刪除診所識別碼紀錄格式錯誤，已拒絕修改')
    data.setdefault('tombstones', {})
    for retired_id in data['tombstones']:
        if not isinstance(retired_id, str) or not CLINIC_ID_RE.fullmatch(retired_id):
            raise RuntimeError('已刪除診所識別碼紀錄格式錯誤，已拒絕修改')
    for slug, draft in data['drafts'].items():
        if (not isinstance(slug, str) or not CLINIC_ID_RE.fullmatch(slug)
                or not isinstance(draft, dict) or draft.get('clinicId') != slug
                or not isinstance(draft.get('displayName'), str)
                or not isinstance(draft.get('notes'), str)
                or type(draft.get('archived')) is not bool):
            raise RuntimeError('診所草稿資料格式異常，已停止操作')
    return data


def _public(data: dict) -> dict:
    drafts = sorted(data['drafts'].values(), key=lambda d: (d['archived'], d['clinicId']))
    # Read-only clients must not receive credentials or full audit data.
    return {'revision': data['revision'], 'drafts': [dict(d) for d in drafts],
            'existingClinics': [{'clinicId': k, 'displayName': v, 'draft': False}
                                for k, v in EXISTING.items()],
            'maxDrafts': MAX_DRAFTS,
            'notice': '此清單僅儲存工程師本機的診所導入草稿；不會建立診所帳號、Firebase 資料庫或正式預約。'}


def read_state() -> dict:
    path, _ = _paths()
    return _public(_load(path))


def audit_tail(limit: int = 40) -> list[dict]:
    path, _ = _paths()
    data = _load(path)
    return list(reversed(data['audit'][-limit:]))


@contextmanager
def _exclusive():
    data_path, lock_path = _paths()
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield data_path
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _write_atomic(path: Path, data: dict) -> None:
    fd, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix='.clinic-v2-', suffix='.tmp')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class RevisionConflict(Exception):
    pass


def _ensure_revision(expected: str, actual: str) -> None:
    if expected != actual:
        raise RevisionConflict('其他工程師工作階段已更新草稿，請重新整理後再儲存')


def _verify_name(name: str) -> str:
    value = name.strip()
    if not 2 <= len(value) <= 80 or any(ord(ch) < 32 for ch in value):
        raise ValueError('診所名稱應為 2 至 80 字，且不得包含控制字元')
    return value


def _verify_notes(notes: str) -> str:
    value = notes.strip()
    if len(value) > 240 or any(ord(ch) < 32 and ch not in '\n\t' for ch in value):
        raise ValueError('備註不得超過 240 字或包含控制字元')
    return value


def _verify_slug(slug: str) -> None:
    if not CLINIC_ID_RE.fullmatch(slug) or slug in EXISTING or slug in RESERVED:
        raise ValueError('診所識別碼須為 3 至 32 個小寫英數或連字號，且不得使用保留名稱')


def _append_audit(data: dict, *, slug: str, action: str, actor: str) -> None:
    data['audit'] = (data['audit'] + [{
        'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'actor': actor[:64], 'clinicId': slug, 'action': action,
    }])[-300:]


def create_draft(*, clinic_id: str, display_name: str, notes: str,
                 expected_revision: str, actor: str) -> dict:
    _verify_slug(clinic_id)
    name = _verify_name(display_name)
    note = _verify_notes(notes)
    with _exclusive() as path:
        data = _load(path)
        _ensure_revision(expected_revision, data['revision'])
        if clinic_id in data['tombstones']:
            raise ValueError('這個診所識別碼已被永久刪除並保留封存識別，不能重複使用')
        if clinic_id in data['drafts']:
            raise ValueError('診所識別碼已存在，請使用其他識別碼')
        if len(data['drafts']) >= MAX_DRAFTS:
            raise ValueError('已達本機草稿上限，請先整理現有草稿')
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        data['drafts'][clinic_id] = {
            'clinicId': clinic_id, 'displayName': name, 'notes': note,
            'archived': False, 'readyForBooking': False,
            'accountCreated': False, 'storageConnected': False,
            'createdAt': now, 'updatedAt': now,
        }
        _append_audit(data, slug=clinic_id, action='draft_created', actor=actor)
        data['revision'] = secrets.token_hex(16)
        _write_atomic(path, data)
        return _public(data)


def update_draft(*, clinic_id: str, display_name: str, notes: str, archived: bool,
                 expected_revision: str, actor: str) -> dict:
    _verify_slug(clinic_id)
    name = _verify_name(display_name)
    note = _verify_notes(notes)
    if type(archived) is not bool:
        raise ValueError('封存狀態格式錯誤')
    with _exclusive() as path:
        data = _load(path)
        _ensure_revision(expected_revision, data['revision'])
        draft = data['drafts'].get(clinic_id)
        if draft is None:
            raise ValueError('找不到這個導入草稿')
        if (draft['displayName'] == name and draft['notes'] == note
                and draft['archived'] == archived):
            return _public(data)
        action = ('draft_archived' if archived and not draft['archived'] else
                  'draft_restored' if not archived and draft['archived'] else
                  'draft_updated')
        draft.update(displayName=name, notes=note, archived=archived,
                     updatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'))
        _append_audit(data, slug=clinic_id, action=action, actor=actor)
        data['revision'] = secrets.token_hex(16)
        _write_atomic(path, data)
        return _public(data)
