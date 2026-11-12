"""DOUBTS v3.3 engineer-only software release/acceptance record store.

This is an *operator-reported* QA workflow. It never deploys code, changes
Firebase, grants clinic access, or marks runtime ready. Real deployment is
read independently from the audited, code-defined v3.2 runtime adapter list.
No patient data or secrets belong in this local private JSON store.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import tempfile

import pilot_backend as backend
import platform_module_store_v32 as registry
import platform_standard_policy_v321 as standard

SCHEMA = 330
ZERO = registry.ZERO
REV = registry.REV_RE
PROGRESS = {'planned': '規劃中', 'developing': '開發中', 'testing': '測試中'}
CHECKS = {
    'unit_tests': '自動化單元測試',
    'integration_tests': 'API 與整合測試',
    'authorization': '登入與操作權限測試',
    'tenant_isolation': '診所資料隔離測試',
    'rollback': '版本回復及異常處理演練',
}
CHECK_STATUSES = {'pending', 'passed', 'failed'}
REF_RE = re.compile(r'[0-9a-f]{7,64}\Z', re.ASCII)


class RevisionConflict(Exception):
    pass


class MissingModule(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _paths() -> tuple[Path, Path]:
    private = backend.private_dir()
    return private / 'platform_releases_v33.json', private / '.platform_releases_v33.lock'


def _initial() -> dict:
    return {'schemaVersion': SCHEMA, 'revision': ZERO, 'releases': {}, 'audit': []}


def _fresh_record(mid: str, version: str) -> dict:
    return {'moduleId': mid, 'version': version, 'progress': 'planned',
            'codeReference': '', 'acceptance': 'draft',
            'checks': {key: {'status': 'pending', 'evidence': '', 'updatedAt': None,
                              'actor': None} for key in CHECKS},
            'createdAt': _now(), 'updatedAt': None,
            'submittedAt': None, 'approvedAt': None, 'rejectedAt': None,
            'rejectionReason': ''}


def _load(path: Path) -> dict:
    if not path.is_file():
        return _initial()
    try:
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeError) as e:
        raise RuntimeError('v3.3 驗收紀錄檔無法解析，已停止讀寫，請先檢查備份') from e
    if (not isinstance(data, dict) or data.get('schemaVersion') != SCHEMA
            or not REV.fullmatch(str(data.get('revision', '')))
            or not isinstance(data.get('releases'), dict)
            or not isinstance(data.get('audit'), list)):
        raise RuntimeError('v3.3 驗收資料格式不符，拒絕讀寫')
    for mid, versions in data['releases'].items():
        if (not registry.MODULE_ID_RE.fullmatch(str(mid)) or
                not isinstance(versions, dict)):
            raise RuntimeError('v3.3 驗收資料不完整')
        for version, record in versions.items():
            if (not registry.VERSION_RE.fullmatch(str(version)) or
                    not isinstance(record, dict) or
                    record.get('moduleId') != mid or record.get('version') != version or
                    record.get('progress') not in PROGRESS or
                    record.get('acceptance') not in ('draft','submitted','approved','rejected') or
                    not isinstance(record.get('checks'), dict) or
                    set(record['checks']) != set(CHECKS) or
                    not isinstance(record.get('codeReference'), str)):
                raise RuntimeError('v3.3 驗收紀錄驗證失敗')
            for check in record['checks'].values():
                if (not isinstance(check, dict) or check.get('status') not in CHECK_STATUSES
                        or not isinstance(check.get('evidence'), str)):
                    raise RuntimeError('v3.3 驗收檢查表格式不正確')
    return data


@contextmanager
def _exclusive():
    path, lock = _paths()
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield path
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _atomic(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix='.release-v33-', suffix='.tmp', dir=path.parent)
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


def _module(mid: str) -> dict:
    if not registry.MODULE_ID_RE.fullmatch(mid):
        raise MissingModule('模組代號不正確')
    state = standard.read_state()
    item = next((m for m in state['modules'] if m['id'] == mid), None)
    if item is None:
        raise MissingModule('找不到模組')
    return item


def _check_all_pass(rec: dict) -> bool:
    return all(item['status'] == 'passed' and item['evidence'].strip()
               for item in rec['checks'].values())


def _record_response(mid: str, version: str, rec: dict, item: dict) -> dict:
    # Only the trusted backend registry can confirm that runnable code is present.
    installed = (item['deployment'] == 'deployed' and
                 item['plannedVersion'] == version and not item['archived'])
    standard_enabled = bool(item['standardIncluded'] and not item['archived'])
    submitted = rec['acceptance'] in ('submitted','approved')
    accepted_effective = (rec['acceptance'] == 'approved'
                          and installed and standard_enabled)
    return {**rec, 'name': item['name'], 'currentVersion': item['plannedVersion'],
            'isCurrentVersion': version == item['plannedVersion'],
            'standardIncluded': standard_enabled, 'archived': item['archived'],
            'deploymentVerified': installed,
            'deploymentMessage': ('後端已驗證同版本程式' if installed
                                  else '尚未驗證程式已部署；填寫測試紀錄無法改變此狀態'),
            'allChecksReportedPassed': _check_all_pass(rec),
            'canSubmit': (not item['archived'] and standard_enabled and
                          version == item['plannedVersion'] and
                          rec['progress'] == 'testing' and
                          _check_all_pass(rec) and
                          bool(REF_RE.fullmatch(rec['codeReference'])) and
                          rec['acceptance'] in ('draft','rejected')),
            'canApprove': (submitted and installed and standard_enabled and
                           _check_all_pass(rec) and
                           rec['acceptance'] == 'submitted'),
            'acceptedEffective': accepted_effective,
            'note': '測試結果及程式版本為工程師填報；部署須由後端獨立驗證。驗收不會自動安裝程式、開放病患資料或啟用正式預約。'}


def read_release(mid: str) -> dict:
    item = _module(mid)
    version = item['plannedVersion']
    state = _load(_paths()[0])
    entry = state['releases'].get(mid, {}).get(version)
    if entry is None:
        entry = _fresh_record(mid, version)
    historical = sorted(state['releases'].get(mid, {}).keys(), reverse=True)
    return {'revision': state['revision'],
            'release': _record_response(mid, version, entry, item),
            'historicalVersions': historical,
            'checkNames': CHECKS, 'progressNames': PROGRESS}


def list_releases() -> dict:
    data = _load(_paths()[0])
    modules = standard.read_state()['modules']
    releases = []
    for item in modules:
        mid, version = item['id'], item['plannedVersion']
        entry = data['releases'].get(mid, {}).get(version) or _fresh_record(mid, version)
        row = _record_response(mid, version, entry, item)
        releases.append({'moduleId': mid, 'version': version, 'progress': row['progress'],
                         'acceptance': row['acceptance'], 'deploymentVerified': row['deploymentVerified'],
                         'acceptedEffective': row['acceptedEffective']})
    return {'revision': data['revision'], 'releases': releases}


def audit_tail(mid: str, limit: int = 60) -> list[dict]:
    _module(mid)
    data = _load(_paths()[0])
    return list(reversed([a for a in data['audit'] if a.get('moduleId') == mid][-limit:]))


def _validate_text(text: str, *, max_chars: int = 240, required=False) -> str:
    if not isinstance(text, str):
        raise ValueError('紀錄格式不正確')
    cleaned = text.strip()
    if ((required and len(cleaned) < 5) or len(cleaned) > max_chars or
            any(ord(x) < 32 and x not in '\t\n' for x in cleaned)):
        raise ValueError('佐證內容長度或格式不正確，請勿填寫個資或密碼')
    return cleaned


def _change(*, mid: str, expected_revision: str, actor: str, operation: str, apply) -> dict:
    if not isinstance(expected_revision, str) or not REV.fullmatch(expected_revision):
        raise ValueError('版本欄位格式不正確')
    with _exclusive() as path:
        data = _load(path)
        if data['revision'] != expected_revision:
            raise RevisionConflict('其他工程師視窗已修改驗收紀錄，請重新整理')
        item = _module(mid)
        if item['archived']:
            raise ValueError('停用中的模組不可修改部署與驗收紀錄')
        version = item['plannedVersion']
        old = data['releases'].get(mid, {}).get(version)
        rec = json.loads(json.dumps(old)) if old is not None else _fresh_record(mid, version)
        updated, details = apply(rec, item)
        if not updated:
            return read_release(mid)
        rec['updatedAt'] = _now()
        data['releases'].setdefault(mid, {})[version] = rec
        data['revision'] = secrets.token_hex(16)
        data['audit'] = (data['audit'] + [{
            'timestamp': _now(), 'actor': actor[:64], 'moduleId': mid,
            'version': version, 'action': operation, **details,
        }])[-800:]
        _atomic(path, data)
    return read_release(mid)


def set_progress(*, mid: str, progress: str, code_reference: str,
                 expected_revision: str, actor: str) -> dict:
    if progress not in PROGRESS:
        raise ValueError('開發進度不正確')
    if code_reference and not REF_RE.fullmatch(code_reference):
        raise ValueError('程式參照碼須為 Git commit 或 SHA256 的 7–64 位十六進位字元')
    def mutate(rec, item):
        if rec['acceptance'] in ('submitted','approved'):
            raise ValueError('已送驗／已核准版本不可直接修改，請撤回或建立新版本')
        before = (rec['progress'], rec['codeReference'])
        if before == (progress, code_reference):
            return False, {}
        # Test evidence is bound to the exact code reference. A new build
        # cannot inherit old pass reports and obtain a false release sign-off.
        if rec['codeReference'] != code_reference or (rec['progress'] == 'testing' and progress != 'testing'):
            rec['checks'] = _fresh_record(mid, item['plannedVersion'])['checks']
        rec['progress'] = progress
        rec['codeReference'] = code_reference
        if rec['acceptance'] == 'rejected':
            rec['acceptance'] = 'draft'
        return True, {'progress': progress, 'checksReset': before[1] != code_reference}
    return _change(mid=mid, expected_revision=expected_revision, actor=actor,
                   operation='release_progress_updated', apply=mutate)


def set_check(*, mid: str, check_id: str, status: str, evidence: str,
              expected_revision: str, actor: str) -> dict:
    if check_id not in CHECKS:
        raise ValueError('未知驗收項目')
    if status not in CHECK_STATUSES:
        raise ValueError('測試狀態不正確')
    note = _validate_text(evidence, required=(status != 'pending'))
    def mutate(rec, item):
        if rec['acceptance'] in ('submitted','approved'):
            raise ValueError('已送驗／已核准版本不可變更檢查表，請先撤回或建立新版本')
        old = rec['checks'][check_id]
        if old['status'] == status and old['evidence'] == note:
            return False, {}
        rec['checks'][check_id] = {'status': status, 'evidence': note,
                                   'updatedAt': _now(), 'actor': actor[:64]}
        if rec['acceptance'] == 'rejected':
            rec['acceptance'] = 'draft'
        return True, {'checkId': check_id, 'reportedStatus': status}
    return _change(mid=mid, expected_revision=expected_revision, actor=actor,
                   operation='release_check_recorded', apply=mutate)


def submit_review(*, mid: str, expected_revision: str, actor: str) -> dict:
    def mutate(rec, item):
        if rec['acceptance'] == 'submitted':
            return False, {}
        result = _record_response(mid, item['plannedVersion'], rec, item)
        if not result['canSubmit']:
            raise ValueError('送交驗收須先納入標準版、填寫程式參照碼，並完成全部五項測試佐證')
        rec['acceptance'] = 'submitted'
        rec['submittedAt'] = _now()
        return True, {}
    return _change(mid=mid, expected_revision=expected_revision, actor=actor,
                   operation='release_review_submitted', apply=mutate)


def withdraw_review(*, mid: str, expected_revision: str, actor: str) -> dict:
    def mutate(rec, item):
        if rec['acceptance'] != 'submitted':
            raise ValueError('只有送交中的驗收可撤回')
        rec['acceptance'] = 'draft'
        rec['submittedAt'] = None
        return True, {}
    return _change(mid=mid, expected_revision=expected_revision, actor=actor,
                   operation='release_review_withdrawn', apply=mutate)


def approve_review(*, mid: str, expected_revision: str, actor: str) -> dict:
    def mutate(rec, item):
        result = _record_response(mid, item['plannedVersion'], rec, item)
        if not result['canApprove']:
            raise ValueError('未通過獨立部署驗證，或尚未完成送驗檢查，不可核准上線')
        rec['acceptance'] = 'approved'
        rec['approvedAt'] = _now()
        return True, {}
    return _change(mid=mid, expected_revision=expected_revision, actor=actor,
                   operation='release_review_approved', apply=mutate)


def reject_review(*, mid: str, reason: str, expected_revision: str, actor: str) -> dict:
    note = _validate_text(reason, required=True)
    def mutate(rec, item):
        if rec['acceptance'] != 'submitted':
            raise ValueError('只有送交中的驗收可退回')
        rec['acceptance'] = 'rejected'
        rec['rejectionReason'] = note
        rec['rejectedAt'] = _now()
        return True, {}
    return _change(mid=mid, expected_revision=expected_revision, actor=actor,
                   operation='release_review_rejected', apply=mutate)


def clinic_entitlements(clinic_id: str) -> dict:
    """Canonical v3.3 clinic capability list adds acceptance to v3.2.1 gates.

    It does not create sessions, install code or grant a clinic access by itself.
    Individual module endpoints must ALSO enforce their own authorization.
    """
    base = standard.clinic_entitlements(clinic_id)
    base['availableFeatures'] = [mid for mid in base['availableFeatures']
                                if read_release(mid)['release']['acceptedEffective']]
    base['note'] = ('v3.3 加上驗收核准關卡。程式部署、標準版、診所開通與驗收均須符合，'
                    '而且各醫護 API 仍須單獨驗證使用者授權。')
    return base
