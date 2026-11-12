"""V3.1 strictly local draft lifecycle; never touches live clinics or Firebase.

The public interface deliberately distinguishes archive (reversible) from purge
(application-level deletion of an UNPROVISIONED staging record). Existing
shanlin/yidian are categorically excluded. Tombstones prevent ID reuse.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import secrets

import pilot_backend as backend
import platform_clinic_registry as registry
import platform_onboarding_store_v3 as onboarding


class DeletionBlocked(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _ensure_slug(slug: str) -> None:
    registry._verify_slug(slug)
    # Also safeguard against a future registered tenant in the actual backend.
    if slug in backend.CLINICS:
        raise ValueError('現有正式診所不能在草稿管理中心停用或刪除')


def _stage_and_blockers(slug: str, draft: dict, entry: dict, audit: list) -> list[str]:
    problems = []
    if not draft['archived']:
        problems.append('請先停用（封存）草稿，才能永久刪除')
    if entry.get('reviewState') == 'pending_review' or any(
        a.get('clinicId') == slug and a.get('action') == 'submitted_for_review' for a in audit
    ):
        problems.append('曾送交驗收，請先由工程師完成正式資料與授權核對')
    if entry.get('storageMode', 'unconfigured') != 'unconfigured':
        problems.append('已規劃 Firebase 資料來源；請先完成獨立資料庫與保存義務核對')
    names = onboarding._env_names(slug)
    if os.environ.get(names['url'], '').strip() or os.environ.get(names['credentials'], '').strip():
        problems.append('環境中已有該診所 Firebase 設定，不可直接刪除')
    # No case claims there is no data in an external service: the only
    # documented guarantee is that V2/V3 staging cannot write clinical data.
    return problems


def deletion_check(slug: str) -> dict:
    _ensure_slug(slug)
    registry_path, _ = registry._paths()
    reg = registry._load(registry_path)
    draft = reg['drafts'].get(slug)
    if draft is None:
        raise ValueError('此診所草稿不存在或已刪除')
    stage = onboarding._load(onboarding._paths()[0])
    entry = stage['clinics'].get(slug, onboarding._initial())
    blockers = _stage_and_blockers(slug, draft, entry, stage['audit'])
    return {
        'clinicId': slug, 'displayName': draft['displayName'],
        'archived': draft['archived'], 'canPurge': not blockers,
        'blockers': blockers, 'registryRevision': reg['revision'],
        'onboardingRevision': stage['revision'],
        'hasLocalAccount': bool(entry.get('account', {}).get('passwordHash')),
        'notice': '刪除僅清除本機導入草稿與本機測試帳密；不刪除 Firebase、Railway、正式診所或備份。診所識別碼會保留停用紀錄，不能重新使用。',
    }


def set_disabled(*, slug: str, disabled: bool, expected_revision: str, actor: str) -> dict:
    _ensure_slug(slug)
    if type(disabled) is not bool:
        raise ValueError('診所停用設定格式不正確')
    # V2 mutation obtains a file lock and validates optimistic revision.
    current = registry.read_state()
    draft = next((d for d in current['drafts'] if d['clinicId'] == slug), None)
    if not draft:
        raise ValueError('診所草稿不存在')
    result = registry.update_draft(
        clinic_id=slug, display_name=draft['displayName'],
        notes=draft['notes'], archived=disabled,
        expected_revision=expected_revision, actor=actor)
    if disabled:
        # Session endpoint also checks archived status at every request.
        backend.invalidate_sessions(slug)
    return result


def purge(*, slug: str, confirmation: str, registry_revision: str,
          onboarding_revision: str, actor: str) -> dict:
    _ensure_slug(slug)
    if confirmation != slug:
        raise DeletionBlocked('請完整輸入診所識別碼以確認永久刪除')
    if not registry.REVISION_RE.fullmatch(registry_revision) or not onboarding.HEX_RE.fullmatch(onboarding_revision):
        raise ValueError('資料版本格式錯誤')
    # Lock V3 staging first (same lock order used by V3 writers), then V2.
    # The records are separate files; remove V3 first, V2 second.  On a crash
    # between writes the V2 draft remains and can be retried safely, while no
    # staging credential is left behind for a deleted draft.
    with onboarding._exclusive() as stage_path:
        with registry._exclusive() as registry_path:
            reg = registry._load(registry_path)
            stage = onboarding._load(stage_path)
            if reg['revision'] != registry_revision or stage['revision'] != onboarding_revision:
                raise registry.RevisionConflict('其他視窗已修改草稿或開通設定，請重新整理再執行刪除')
            draft = reg['drafts'].get(slug)
            if not draft:
                raise ValueError('草稿不存在或已經刪除')
            entry = stage['clinics'].get(slug, onboarding._initial())
            blockers = _stage_and_blockers(slug, draft, entry, stage['audit'])
            if blockers:
                raise DeletionBlocked('；'.join(blockers))
            if slug in stage['clinics']:
                del stage['clinics'][slug]
                stage['revision'] = secrets.token_hex(16)
                onboarding._note_audit(stage, slug, 'local_staging_data_purged', actor)
                onboarding._atomic(stage_path, stage)
            # The tombstone has no name, phone, address, notes, or password.
            reg['tombstones'][slug] = {'deletedAt': _now(), 'actor': actor[:64]}
            del reg['drafts'][slug]
            registry._append_audit(reg, slug=slug, action='draft_permanently_deleted', actor=actor)
            reg['revision'] = secrets.token_hex(16)
            registry._write_atomic(registry_path, reg)
            final = registry._public(reg)
    backend.invalidate_sessions(slug)
    return {'success': True, 'clinicId': slug, 'registry': final,
            'notice': '已刪除本機導入資料並撤銷本機工作階段；保留最小操作紀錄與禁止重用的診所識別碼。外部資料庫及備份未處理。'}
