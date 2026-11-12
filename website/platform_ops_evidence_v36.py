"""Evidence-only DOUBTS v3.6 clinic operations report.

No external I/O, no credentials, no patient details, no booking writes.
This is a read-only completion gate; a configuration checkbox is not deployment.
"""
from __future__ import annotations

CLINICS = {'yidian': ('頤典診所', 'demo'), 'shanlin': ('山林診所', 'partner')}


def _item(key: str, label: str, status: str, detail: str) -> dict:
    assert status in ('verified_local', 'pending', 'blocked')
    return {'id': key, 'label': label, 'status': status, 'detail': detail}


def clinic_report(clinic: str, *, authenticated: bool = False,
                  shanlin_source_verified: bool = False,
                  shanlin_catalog_available: bool = False,
                  shanlin_catalog_count: int = 0,
                  platform_module_count: int | None = None) -> dict:
    """Make conservative readiness statements. These inputs are non-PII evidence.

    Authentication evidence is limited to this request's VALIDATED session.
    A local source preview is not proof that clinical prices have been released.
    """
    if clinic not in CLINICS:
        raise ValueError('不支援的診所')
    name, role = CLINICS[clinic]
    source_state = ('verified_local' if clinic == 'shanlin' and shanlin_source_verified
                    else 'pending')
    source_detail = ('目前這次診所登入已核對山林舊後台的基本資料來源（唯讀快照）；不是正式預約串接。'
                     if source_state == 'verified_local'
                     else '頤典是公版 Demo，並無正式診所來源需要連接。' if clinic == 'yidian' else '尚未在目前這次登入中驗證山林正式來源與資料隔離。')
    catalog_state = ('verified_local' if clinic == 'shanlin' and shanlin_catalog_available
                     else 'pending')
    if clinic == 'yidian':
        catalog_detail = '頤典為公版 Demo，沒有可對外發布的真實健檢目錄。'
    elif shanlin_catalog_available:
        catalog_detail = f'已有山林來源目錄唯讀快照（{max(shanlin_catalog_count,0)} 項）；仍待診所確認發布。'
    else:
        catalog_detail = '尚未在此環境確認山林來源目錄，不能自動使用頤典資料。'

    module_detail = ('工程師模組登錄狀態目前無法確認；不能推論已部署。'
                     if platform_module_count is None else
                     f'工程師平台有 {max(platform_module_count,0)} 個模組登錄；登錄／標準版勾選不代表程式已部署及臨床可用。')
    checks = [
        _item('session', '診所管理登入', 'verified_local' if authenticated else 'pending',
              '本次請求已通過診所工作階段驗證。' if authenticated else '只有開發時的登入程式，尚未驗證本次診所工作階段。'),
        _item('source', '診所正式資料來源核對', source_state, source_detail),
        _item('catalog', '診所專屬健檢目錄來源', catalog_state, catalog_detail),
        _item('staff', '科別／醫師設定', 'pending',
              '公版已具獨立的科別及醫師資料管理；尚未與山林正式後台雙向同步，不能宣稱正式可用。'),
        _item('bookings', '正式預約讀寫及取消／改期', 'blocked',
              '8006 的雙診所展示禁止正式預約寫入；山林 Railway 目前仍是另一個營運服務。'),
        _item('capacity', '多通路一致名額與防重複', 'blocked',
              '網站、櫃台、Excel 匯入與 LINE 尚未共用相同的交易名額服務。'),
        _item('modules', '功能模組正式開通', 'pending', module_detail),
        _item('release', '診所驗收與正式切換', 'blocked',
              '需要獨立測試資料、權限隔離、醫護核可、復原計畫；本機工具不得自動開通。'),
    ]
    return {
        'clinicId': clinic, 'clinicName': name, 'role': role,
        'readiness': 'not_ready_for_live_booking',
        'bookingWritesEnabled': False,
        'patientDataIncluded': False,
        'adminUrl': f'/pilot?clinic={clinic}&view=admin',
        'checks': checks,
    }


def all_reports(*, shanlin_catalog_available: bool, shanlin_catalog_count: int,
                module_count: int | None) -> dict:
    return {
        'environment': 'local_pilot_only',
        'productionReady': False,
        'patientsIncluded': False,
        'clinics': [clinic_report(
            clinic,
            shanlin_catalog_available=shanlin_catalog_available,
            shanlin_catalog_count=shanlin_catalog_count,
            platform_module_count=module_count,
        ) for clinic in CLINICS],
        'notice': '這是有來源依據的開發驗收清單。不能把登入頁、目錄預覽或模組勾選視為正式預約已開通。',
    }
