"""Durable local-only operator policy store. No patient or clinic source data here.

All writes use one advisory flock + atomic JSON replacement. A revision protects
against concurrent edits from two engineering browsers or Uvicorn workers.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import json
import os
import secrets
import tempfile

import pilot_backend

CLINICS = {'yidian': '頤典診所', 'shanlin': '山林診所'}
# The initial registry contains ONLY future, not-yet-deployed modules. An
# authorization flag does not automatically release or install feature code.
FEATURES = {
    'ai_health_summary': {
        'name': 'AI 健檢摘要',
        'description': '未來提供經核准的健檢結果摘要草稿。',
        'deployment': 'not_deployed',
    },
    'staff_worklist': {
        'name': '醫護工作清單',
        'description': '未來提供診所內部任務與工作進度。',
        'deployment': 'not_deployed',
    },
    'appointment_reminders': {
        'name': '預約提醒',
        'description': '未來提供診所授權的預約通知功能。',
        'deployment': 'not_deployed',
    },
}
INITIAL_REVISION = '0' * 32


def _paths() -> tuple[Path, Path]:
    home = pilot_backend.private_dir()
    return home / 'platform_console_v1.json', home / '.platform_console_v1.lock'


def _default() -> dict:
    return {'schemaVersion': 1, 'revision': INITIAL_REVISION,
            'flags': {clinic: {feature: False for feature in FEATURES} for clinic in CLINICS},
            'audit': []}


def _load(path: Path) -> dict:
    if not path.exists():
        return _default()
    with path.open('r', encoding='utf-8') as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or data.get('schemaVersion') != 1:
        raise RuntimeError('平台功能設定版本無法辨識，已停止修改')
    if not isinstance(data.get('flags'), dict) or not isinstance(data.get('audit'), list):
        raise RuntimeError('平台功能設定格式不正確，已停止修改')
    return data


def _public(data: dict) -> dict:
    src = data.get('flags') or {}
    return {
        'revision': data['revision'],
        'flags': {clinic: {fid: src.get(clinic, {}).get(fid) is True for fid in FEATURES}
                  for clinic in CLINICS},
        'features': [{'id': k, **v} for k, v in FEATURES.items()],
    }


def read_state() -> dict:
    path, _ = _paths()
    return _public(_load(path))


def audit_tail(limit: int = 40) -> list[dict]:
    path, _ = _paths()
    return list(reversed(_load(path).get('audit', [])[-limit:]))


@contextmanager
def _exclusive():
    path, lock_file = _paths()
    descriptor = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield path
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _atomic_replace(path: Path, data: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix='.console-v1-', suffix='.tmp', dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RevisionConflict(Exception):
    pass


def update_flag(*, clinic: str, feature: str, enabled: bool,
                expected_revision: str, actor: str) -> dict:
    if clinic not in CLINICS or feature not in FEATURES or type(enabled) is not bool:
        raise ValueError('不支援的診所、模組或狀態')
    with _exclusive() as path:
        data = _load(path)
        if data['revision'] != expected_revision:
            raise RevisionConflict('設定已由另一台電腦更新，請重新讀取後再操作')
        old = data['flags'].setdefault(clinic, {}).get(feature) is True
        # Do not create an artificial write if the switch was not changed.
        if old == enabled:
            return _public(data)
        data['flags'][clinic][feature] = enabled
        data['revision'] = secrets.token_hex(16)
        data['audit'] = (data['audit'] + [{
            'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'actor': actor[:64], 'clinicId': clinic, 'featureId': feature,
            'before': old, 'after': enabled,
        }])[-300:]
        _atomic_replace(path, data)
        return _public(data)


def clinic_entitlements(clinic: str) -> dict:
    if clinic not in CLINICS:
        raise ValueError('Unknown clinic')
    current = read_state()['flags'][clinic]
    # An enablement policy is NOT a deployment. No planned feature is usable yet.
    return {
        'clinicId': clinic,
        'preauthorizedFeatures': [fid for fid, enabled in current.items() if enabled],
        'availableFeatures': [fid for fid, enabled in current.items()
                              if enabled and FEATURES[fid]['deployment'] == 'deployed'],
        'note': '預先授權不等於功能已部署；未上線模組不會出現在醫護工作頁面。',
    }
