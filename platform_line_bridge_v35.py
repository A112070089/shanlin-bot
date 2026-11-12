"""Local-only safe status bridge for a separately deployed v3.5 Shanlin Bot.

No sending, no patient data, no arbitrary URL, never passes tokens to browser.
"""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

STATUS_URL='https://shanlin-bot-production.up.railway.app/api/reminder/v35/status'

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_status() -> dict:
    token=os.environ.get('PLATFORM_SHANLIN_V35_STATUS_TOKEN','')
    if len(token)<32:
        return {'state':'not_configured', 'label':'尚未設定唯讀狀態金鑰；沒有連線或取得病患資料',
                'checkedAtUtc':None,'lastRun':None}
    request=urllib.request.Request(
        STATUS_URL,method='GET',
        headers={'X-Reminder-Status-Token':token, 'Accept':'application/json',
                 'User-Agent':'DOUBTS-engineer-readonly/3.5'})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request,timeout=3.0) as response:
            if response.status!=200:
                return {'state':'unverified','label':'遠端狀態 API 未確認','lastRun':None}
            content=response.read(8193)
        if len(content)>8192:
            raise ValueError('oversized')
        data=json.loads(content.decode('utf-8'))
        if not isinstance(data,dict) or data.get('schema')!=35 or data.get('clinicId')!='shanlin':
            raise ValueError('wrong service')
        last=data.get('lastRun')
        if isinstance(last,dict):
            keys=('mode','targetDate','runAtUtc','finishedAtUtc','eligible','unverifiedBinding',
                  'accepted','duplicateSkipped','rejected','uncertain','changedSkipped','limitReached')
            last={k:last.get(k) for k in keys if k in last}
        else: last=None
        return {'state':'connected','label':'已驗證 Shanlin v3.5 唯讀狀態 API（不代表已發送或已送達）',
                'sendEnabled':data.get('sendEnabled') is True,
                'schedulerVerified':False,
                'schedulerLabel':'外部每日排程需另查 Cron 執行紀錄，API 心跳不等於排程驗收',
                'deliveryVerified':False,
                'lastRun':last,
                'checkedAtUtc':datetime.now(timezone.utc).isoformat(timespec='seconds')}
    except urllib.error.HTTPError as exc:
        if exc.code in (401,403):
            return {'state':'unauthorized','label':'遠端狀態金鑰不一致或已撤銷','lastRun':None}
        if exc.code==404:
            return {'state':'not_deployed','label':'山林 Railway 尚未提供 v3.5 狀態端點','lastRun':None}
        return {'state':'unverified','label':'狀態服務暫時無法確認','lastRun':None}
    except (OSError,ValueError,UnicodeError):
        return {'state':'unverified','label':'尚未取得可信的安全發送狀態，請檢查服務連線','lastRun':None}
