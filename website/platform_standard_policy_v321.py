"""Engineer-only global standard-plan feature switches for DOUBTS v3.2.1.

There is ONE platform-wide toggle per module; no clinic-specific paid-plan
entitlements. Existing v3.2 individual selections are read-only historical
information, never silently promoted to platform-wide grants.

A standard-plan selection is NOT a runtime deployment. Real clinical access
additionally requires trusted, verified module code and a verified active
clinic, neither of which can be enabled through operator-editable JSON.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
import secrets
import tempfile
from pathlib import Path

import pilot_backend as backend
import platform_module_store_v32 as modules_v32
import platform_console_store as original_v1
import platform_clinic_registry as clinic_registry

SCHEMA = 321
ZERO = modules_v32.ZERO
REV_RE = modules_v32.REV_RE

# Only a future reviewed code release and completed clinic onboarding can
# populate this set. An editable checkbox / JSON entry cannot do so.
VERIFIED_LIVE_CLINICS: frozenset[str] = frozenset()

class RevisionConflict(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _paths() -> tuple[Path, Path]:
    root = backend.private_dir()
    return root / 'platform_standard_policy_v321.json', root / '.platform_standard_policy_v321.lock'


def _default() -> dict:
    return {'schemaVersion': SCHEMA, 'revision': ZERO,
            'standardIncluded': {}, 'audit': [],
            'migration': 'v32_individual_grants_preserved_read_only_not_auto_applied'}


def _load(path: Path) -> dict:
    if not path.exists():
        return _default()
    with path.open('r', encoding='utf-8') as f:
        obj = json.load(f)
    if (not isinstance(obj, dict) or obj.get('schemaVersion') != SCHEMA
            or not REV_RE.fullmatch(str(obj.get('revision', '')))
            or not isinstance(obj.get('standardIncluded'), dict)
            or not isinstance(obj.get('audit'), list)):
        raise RuntimeError('全平台標準版設定格式不相容，拒絕讀取及修改')
    for module_id, flag in obj['standardIncluded'].items():
        if (not isinstance(module_id, str)
                or not modules_v32.MODULE_ID_RE.fullmatch(module_id)
                or type(flag) is not bool):
            raise RuntimeError('標準版模組開關資料格式錯誤，拒絕修改')
    return obj


@contextmanager
def _exclusive():
    path, lock_path = _paths()
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield path
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _atomic(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.standard-v321-', suffix='.tmp')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def legacy_diagnostics() -> dict:
    """Compare source clinic IDs, never infer a wrong grant from names/order.

    The v1 and v3.2 files may have been edited separately after migration.
    Differing values need review; they do NOT prove a tenant-ID swap.
    """
    old = original_v1.read_state()['flags']
    v32 = modules_v32.read_state()
    historical = []
    differences = []
    for mod in v32['modules']:
        mid = mod['id']
        if mid not in modules_v32.BUILTINS:
            continue
        old_flags = {cid: old.get(cid, {}).get(mid) is True for cid in clinic_registry.EXISTING}
        recent_flags = {cid: v32['grants'].get(cid, {}).get(mid) is True
                        for cid in clinic_registry.EXISTING}
        row = {'moduleId': mid, 'name': mod['name'],
               'v1Flags': old_flags, 'v32Flags': recent_flags}
        historical.append(row)
        for cid in clinic_registry.EXISTING:
            if old_flags[cid] != recent_flags[cid]:
                differences.append({'clinicId': cid, 'clinicName': clinic_registry.EXISTING[cid],
                                    'moduleId': mid, 'v1': old_flags[cid],
                                    'v32': recent_flags[cid]})
    return {'historical': historical, 'differences': differences,
            'differenceCount': len(differences),
            'explanation': '舊版逐診所勾選僅供核對，版本差異可能來自後續人工修改，不能直接判定資料對應錯誤；不自動轉為全平台開通。'}


def read_state() -> dict:
    registry = modules_v32.read_state()
    policy = _load(_paths()[0])
    modules = []
    for m in registry['modules']:
        row = dict(m)
        included = bool(policy['standardIncluded'].get(row['id'], False))
        row['standardIncluded'] = included
        row['clinicalAvailable'] = False  # Below: requires verified live tenant and adapter.
        row['releaseStatus'] = ('已停用' if row['archived'] else
                                '未納入標準版' if not included else
                                '已納入標準版，尚未部署' if row['deployment'] != 'deployed' else
                                '程式已驗證，待診所開通確認')
        modules.append(row)
    clinics = []
    for c in registry['clinics']:
        row = dict(c)
        row['canUseClinicalModules'] = bool(
            c['kind'] == 'existing' and c['active']
            and c['id'] in VERIFIED_LIVE_CLINICS)
        row['standardPlan'] = c['kind'] == 'existing'
        clinics.append(row)
    return {'revision': registry['revision'],  # Module metadata CAS
            'policyRevision': policy['revision'],  # Global plan CAS
            'modules': modules, 'clinics': clinics,
            'standardModuleIds': [m['id'] for m in modules
                                  if m['standardIncluded'] and not m['archived']],
            'maxModules': registry['maxModules'],
            'scope': 'all_activated_clinics_same_standard_plan',
            'historicalCheck': legacy_diagnostics(),
            'notice': '所有已正式開通的同方案診所採相同模組；目前開關是標準版規劃。未部署或未完成診所驗收時不提供實際功能。'}


def set_standard(*, module_id: str, enabled: bool, expected_revision: str, actor: str) -> dict:
    if type(enabled) is not bool:
        raise ValueError('標準版開關格式錯誤')
    if not isinstance(expected_revision, str) or not REV_RE.fullmatch(expected_revision):
        raise ValueError('設定版本格式錯誤')
    with _exclusive() as path:
        data = _load(path)
        if data['revision'] != expected_revision:
            raise RevisionConflict('另一個工程師視窗已修改標準版設定，請重新載入')
        # Resolve current module ID under lock; cannot enable archived/unknown ID.
        registry = modules_v32.read_state()
        module = next((x for x in registry['modules'] if x['id'] == module_id), None)
        if module is None:
            raise modules_v32.MissingModule('找不到此功能模組')
        if enabled and module['archived']:
            raise ValueError('已停用的模組不可納入標準版')
        if data['standardIncluded'].get(module_id, False) == enabled:
            return read_state()
        data['standardIncluded'][module_id] = enabled
        data['revision'] = secrets.token_hex(16)
        data['audit'] = (data['audit'] + [{'timestamp': _now(), 'actor': actor[:64],
                                         'action': 'standard_plan_module_included' if enabled
                                         else 'standard_plan_module_excluded',
                                         'moduleId': module_id}])[-500:]
        _atomic(path, data)
    return read_state()


def audit_tail(limit: int = 40) -> list[dict]:
    legacy = modules_v32.audit_tail(limit)
    policy = _load(_paths()[0])['audit']
    return sorted([*legacy, *policy], key=lambda a: a['timestamp'], reverse=True)[:limit]


def clinic_entitlements(clinic_id: str) -> dict:
    state = read_state()
    c = next((x for x in state['clinics'] if x['id'] == clinic_id), None)
    if not c:
        raise ValueError('診所不存在或已刪除')
    standard = state['standardModuleIds']
    # All existing clinics share identical standard-plan registry; drafts may
    # view the plan but are never granted a real medical service.
    eligible = c['canUseClinicalModules']
    available = [m['id'] for m in state['modules']
                 if (eligible and m['id'] in standard
                     and m['deployment'] == 'deployed' and not m['archived'])]
    return {'clinicId': clinic_id, 'standardPlanFeatures': list(standard),
            'preauthorizedFeatures': list(standard) if c['kind'] == 'existing' else [],
            'availableFeatures': available,
            'clinicVerifiedForClinicalUse': eligible,
            'note': state['notice']}
