"""DOUBTS v3.2 dynamic MODULE REGISTRY (local engineer-only prototype).

Runtime features are NEVER installed by writing this registry.  Authorization
policy and executable deployment are different controls. Existing v1 feature
selections are read only at initial migration; no legacy file is overwritten.
Never include patient data, passwords or Firebase secrets in this registry.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
import re
import secrets
import tempfile
from pathlib import Path

import pilot_backend as backend
import platform_clinic_registry as clinics_v2
import platform_console_store as legacy
import platform_onboarding_store_v3 as onboarding_v3

SCHEMA = 32
ZERO = '0' * 32
MAX_MODULES = 80
MODULE_ID_RE = re.compile(r'[a-z][a-z0-9_]{2,39}\Z', re.ASCII)
VERSION_RE = re.compile(r'(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})(?:-[a-z0-9]+(?:[.\-][a-z0-9]+)*)?\Z', re.ASCII)
REV_RE = re.compile(r'[0-9a-f]{32}\Z', re.ASCII)
STAGES = {'planned', 'testing'}

# Externally executable implementations MUST be registered by audited code in
# a subsequent release. This map is intentionally empty in v3.2. It is NOT
# stored in writable JSON and the UI offers no "mark deployed" action.
VERIFIED_RUNTIME_ADAPTERS: dict[str, dict] = {}

BUILTINS = {
    'ai_health_summary': ('AI 健檢摘要', '未來提供經核准的健檢結果摘要草稿。'),
    'staff_worklist': ('醫護工作清單', '未來提供診所內部任務與工作進度。'),
    'appointment_reminders': ('預約提醒', '未來提供診所授權的預約通知功能。'),
}

class RevisionConflict(Exception):
    pass

class MissingModule(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _paths() -> tuple[Path, Path]:
    root = backend.private_dir()
    return root / 'platform_modules_v32.json', root / '.platform_modules_v32.lock'


def _legacy_flags() -> dict[str, dict[str, bool]]:
    # V1 stores only the three historical feature checkboxes for yidian/shanlin.
    # Accessing the read-only public v1 snapshot does NOT change v1 state.
    data = legacy.read_state()
    result = {cid: {fid: row.get(fid) is True for fid in BUILTINS}
              for cid, row in data['flags'].items() if cid in clinics_v2.EXISTING}
    # Import existing v3 *draft* feature flags too; never migrate credential data.
    staging = onboarding_v3._load(onboarding_v3._paths()[0])
    for cid, row in staging['clinics'].items():
        result[cid] = {fid: row['features'].get(fid) is True for fid in BUILTINS}
    return result


def _default() -> dict:
    return {
        'schemaVersion': SCHEMA,
        'revision': ZERO,
        'modules': {
            fid: {'id': fid, 'name': name, 'description': description,
                  'plannedVersion': '0.1.0', 'stage': 'planned', 'archived': False,
                  'source': 'builtin', 'createdAt': None, 'updatedAt': None}
            for fid, (name, description) in BUILTINS.items()
        },
        'grants': _legacy_flags(),
        'audit': [],
        'migration': 'legacy_v1_v3_flags_imported_read_only',
    }


def _load(path: Path) -> dict:
    if not path.exists():
        return _default()
    with path.open('r', encoding='utf-8') as handle:
        data = json.load(handle)
    if (not isinstance(data, dict) or data.get('schemaVersion') != SCHEMA
            or not REV_RE.fullmatch(str(data.get('revision', '')))
            or not isinstance(data.get('modules'), dict)
            or not isinstance(data.get('grants'), dict)
            or not isinstance(data.get('audit'), list)):
        raise RuntimeError('v3.2 模組儲存格式不符，拒絕修改')
    for mid, row in data['modules'].items():
        if (not isinstance(mid, str) or not MODULE_ID_RE.fullmatch(mid)
                or not isinstance(row, dict) or row.get('id') != mid
                or not isinstance(row.get('name'), str)
                or not isinstance(row.get('description'), str)
                or not isinstance(row.get('plannedVersion'), str)
                or not VERSION_RE.fullmatch(row['plannedVersion'])
                or row.get('stage') not in STAGES
                or type(row.get('archived')) is not bool
                or row.get('source') not in ('builtin', 'custom')):
            raise RuntimeError('v3.2 模組資料格式異常，拒絕修改')
    for cid, flags in data['grants'].items():
        if (not isinstance(cid, str) or not isinstance(flags, dict)
                or any(not isinstance(fid, str) or type(flag) is not bool
                       for fid, flag in flags.items())):
            raise RuntimeError('v3.2 授權資料格式異常，拒絕修改')
    return data


def _clinics() -> list[dict]:
    result = [
        {'id': cid, 'name': name, 'kind': 'existing', 'active': True}
        for cid, name in clinics_v2.EXISTING.items()
    ]
    reg = clinics_v2.read_state()
    result.extend(
        {'id': d['clinicId'], 'name': d['displayName'], 'kind': 'draft',
         'active': not d['archived']}
        for d in reg['drafts']
    )
    return result


def _runtime_verified(row: dict) -> bool:
    # This is a defense-in-depth gate, not a deploy mechanism.  Later developer
    # releases may register a tested adapter in source code.  The record in the
    # writable operator JSON cannot set this flag.
    entry = VERIFIED_RUNTIME_ADAPTERS.get(row['id'])
    return bool(entry and entry.get('verified') is True
                and entry.get('codeIntegrated') is True
                and entry.get('version') == row['plannedVersion'])


def _public(data: dict) -> dict:
    tenants = _clinics()
    tenant_ids = {c['id'] for c in tenants}
    modules = []
    for item in data['modules'].values():
        m = dict(item)
        m['deployment'] = 'deployed' if _runtime_verified(item) else 'not_deployed'
        modules.append(m)
    modules.sort(key=lambda m: (m['source'] != 'builtin', m['id']))
    grants = {
        cid: {mid: data['grants'].get(cid, {}).get(mid) is True
              for mid in data['modules']}
        for cid in tenant_ids
    }
    return {'revision': data['revision'], 'modules': modules, 'clinics': tenants,
            'grants': grants, 'maxModules': MAX_MODULES,
            'notice': '新增或預先授權模組不會安裝程式；只有後端已整合並驗證的模組才可能開放。'}


def read_state() -> dict:
    return _public(_load(_paths()[0]))


def audit_tail(limit: int = 50) -> list[dict]:
    return list(reversed(_load(_paths()[0])['audit'][-limit:]))


@contextmanager
def _exclusive():
    path, lockpath = _paths()
    fd = os.open(lockpath, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield path
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _atomic(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.modules-v32-', suffix='.tmp')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _change(expected_revision: str, actor: str, operation: str, apply):
    if not REV_RE.fullmatch(expected_revision):
        raise ValueError('設定版本格式不正確')
    with _exclusive() as path:
        data = _load(path)
        if data['revision'] != expected_revision:
            raise RevisionConflict('模組設定已由另一個視窗更改，請重新載入後操作')
        changed, meta = apply(data)
        if not changed:
            return _public(data)
        data['revision'] = secrets.token_hex(16)
        data['audit'] = (data['audit'] + [{
            'timestamp': _now(), 'actor': actor[:64], 'action': operation,
            **meta,
        }])[-500:]
        _atomic(path, data)
        return _public(data)


def _valid_details(mid: str, name: str, description: str, version: str, stage: str):
    if not MODULE_ID_RE.fullmatch(mid):
        raise ValueError('模組代號須為 3–40 字元的小寫英文、數字及底線，且須以英文開頭')
    if (not 2 <= len(name.strip()) <= 80 or not 0 <= len(description.strip()) <= 500
            or any(ord(ch) < 32 for ch in name)
            or any(ord(ch) < 32 and ch not in '\n\t' for ch in description)):
        raise ValueError('模組名稱或說明格式錯誤')
    if not VERSION_RE.fullmatch(version):
        raise ValueError('規劃版本須使用 1.0.0 之類的 SemVer 格式')
    if stage not in STAGES:
        raise ValueError('不支援的開發狀態')


def create_module(*, module_id: str, name: str, description: str, planned_version: str,
                  stage: str, expected_revision: str, actor: str) -> dict:
    _valid_details(module_id, name, description, planned_version, stage)
    def apply(data):
        if module_id in data['modules']:
            raise ValueError('此模組代號已存在，不可重複建立')
        if len(data['modules']) >= MAX_MODULES:
            raise ValueError('模組數量已達安全上限')
        data['modules'][module_id] = {
            'id': module_id, 'name': name.strip(), 'description': description.strip(),
            'plannedVersion': planned_version, 'stage': stage, 'archived': False,
            'source': 'custom', 'createdAt': _now(), 'updatedAt': _now(),
        }
        return True, {'moduleId': module_id}
    return _change(expected_revision, actor, 'module_created', apply)


def update_module(*, module_id: str, name: str, description: str, planned_version: str,
                  stage: str, expected_revision: str, actor: str) -> dict:
    _valid_details(module_id, name, description, planned_version, stage)
    def apply(data):
        row = data['modules'].get(module_id)
        if not row:
            raise MissingModule('找不到此功能模組')
        updated = dict(name=name.strip(), description=description.strip(),
                       plannedVersion=planned_version, stage=stage)
        if all(row.get(k) == v for k, v in updated.items()):
            return False, {}
        row.update(updated)
        row['updatedAt'] = _now()
        return True, {'moduleId': module_id}
    return _change(expected_revision, actor, 'module_updated', apply)


def set_archived(*, module_id: str, archived: bool, expected_revision: str,
                 actor: str) -> dict:
    if type(archived) is not bool:
        raise ValueError('模組停用狀態格式不正確')
    def apply(data):
        row = data['modules'].get(module_id)
        if not row:
            raise MissingModule('找不到此功能模組')
        if row['archived'] == archived:
            return False, {}
        row['archived'] = archived
        row['updatedAt'] = _now()
        return True, {'moduleId': module_id}
    return _change(expected_revision, actor,
                   'module_archived' if archived else 'module_restored', apply)


def set_grant(*, clinic_id: str, module_id: str, enabled: bool,
              expected_revision: str, actor: str) -> dict:
    if type(enabled) is not bool:
        raise ValueError('功能開關格式不正確')
    def apply(data):
        row = data['modules'].get(module_id)
        if not row:
            raise MissingModule('找不到此功能模組')
        tenant = next((x for x in _clinics() if x['id'] == clinic_id), None)
        if not tenant:
            raise ValueError('診所不存在或已永久刪除')
        if enabled and (row['archived'] or not tenant['active']):
            raise ValueError('停用中的模組或診所不可新增授權')
        selected = data['grants'].get(clinic_id, {}).get(module_id) is True
        if selected == enabled:
            return False, {}
        data['grants'].setdefault(clinic_id, {})[module_id] = enabled
        return True, {'moduleId': module_id, 'clinicId': clinic_id, 'enabled': enabled}
    return _change(expected_revision, actor, 'clinic_feature_grant_changed', apply)



def remove_deleted_draft_grants(*, clinic_id: str, actor: str) -> bool:
    """Remove v3.2 grant data after V3.1 has ALREADY tombstoned a draft.

    No patient data is stored here. This operation must never undelete or
    reactivate a tenant. If the registry is missing, there is nothing to clean.
    """
    # Do not treat a missing draft as proof of deletion: demand a tombstone.
    raw = clinics_v2._load(clinics_v2._paths()[0])
    if clinic_id not in raw.get('tombstones', {}):
        raise ValueError('沒有永久刪除紀錄，拒絕清除診所授權')
    with _exclusive() as path:
        if not path.exists():
            return False
        data = _load(path)
        if clinic_id not in data['grants']:
            return False
        del data['grants'][clinic_id]
        data['revision'] = secrets.token_hex(16)
        data['audit'] = (data['audit'] + [{
            'timestamp': _now(), 'actor': actor[:64],
            'action': 'deleted_draft_grants_purged', 'clinicId': clinic_id,
        }])[-500:]
        _atomic(path, data)
        return True


def clinic_entitlements(clinic_id: str) -> dict:
    state = read_state()
    clinic = next((x for x in state['clinics'] if x['id'] == clinic_id), None)
    if clinic is None:
        raise ValueError('診所不存在')
    grants = state['grants'][clinic_id]
    enabled = [m['id'] for m in state['modules']
               if grants.get(m['id']) and not m['archived'] and clinic['active']]
    # Draft tenants, even if provisioned for onboarding, have NO production API.
    available = [m['id'] for m in state['modules']
                 if clinic['kind'] == 'existing' and m['id'] in enabled
                 and m['deployment'] == 'deployed']
    return {'clinicId': clinic_id, 'preauthorizedFeatures': enabled,
            'availableFeatures': available, 'note': state['notice']}
