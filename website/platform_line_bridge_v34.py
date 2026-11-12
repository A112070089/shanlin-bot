"""v3.4 read-only inspection of Shanlin's existing LINE Bot.

Never posts, sends, reads patient data, or treats public source code as
proof that the production scheduler or delivery has been verified.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
import urllib.error
import urllib.request

# Fixed and reviewed external endpoint. This module does not accept user URLs,
# credentials, or clinic IDs. No reminder dispatch endpoint is ever accessed.
SHANLIN_ROOT = 'https://shanlin-bot-production.up.railway.app/'
EXPECTED_SERVICE = '山林診所 LINE Bot API'
REPO = 'https://github.com/A112070089/shanlin-bot/blob/main/main.py'

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def source_summary() -> dict:
    """Static, conservative source-review notes (NOT a runtime verification)."""
    return {
        'clinicId': 'shanlin',
        'featureId': 'appointment_reminders',
        'title': '山林 LINE Bot｜電話綁定與診前提醒',
        'source': '公開 GitHub main 分支靜態檢視（2026-10-24），不代表 Railway 已部署相同版本',
        'sourceUrl': REPO,
        'binding': {'state': 'source_found', 'label': 'LIFF 綁定邏輯在原始碼中'},
        'reminder': {'state': 'source_found', 'label': '預約前一天推播邏輯在原始碼中'},
        'scheduler': {'state': 'unverified', 'label': '每日排程尚未驗證'},
        'delivery': {'state': 'unverified', 'label': '實際送達／重試紀錄尚未驗證'},
        'deduplication': {'state': 'unverified', 'label': '防重複發送尚未驗證'},
        'security': {'state': 'needs_review', 'label': '原始碼的提醒發送入口未見授權檢查，需先修正及驗證'},
        'productionVerified': False,
        'standardFeatureActive': False,
        'note': '此頁只顯示來源檢視與唯讀連線狀態，不會連結 Firebase、觸發 LINE 發送或開通任何診所。',
    }


def _probe_root() -> dict:
    """Single bounded read-only GET. Fail closed on all unexpected responses."""
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(
        SHANLIN_ROOT, method='GET',
        headers={'Accept': 'application/json', 'User-Agent': 'DOUBTS-readonly-line-check/3.4'},
    )
    try:
        with opener.open(request, timeout=2.5) as response:
            if response.status != 200:
                return {'state':'unverified', 'label':'無法確認服務狀態'}
            content = response.read(8193)
            if len(content) > 8192:
                return {'state':'unverified', 'label':'回應不符合預期'}
            payload = json.loads(content.decode('utf-8'))
        if isinstance(payload, dict) and payload.get('status') == 'ok' and payload.get('service') == EXPECTED_SERVICE:
            return {'state':'reachable', 'label':'服務入口可連線（不代表提醒已排程或成功發送）'}
        return {'state':'unverified', 'label':'連線成功但服務身分未經確認'}
    except (OSError, ValueError, UnicodeError, urllib.error.HTTPError):
        return {'state':'unreachable', 'label':'本機目前無法確認遠端連線，不能據此判斷是否停機'}


def probe_status() -> dict:
    value = _probe_root()
    return {'service': value, 'checkedAtUtc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'schedulerVerified': False, 'deliveryVerified': False,
            'productionVerified': False, 'sendsMessages': False}
