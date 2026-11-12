#!/usr/bin/env python3
"""External scheduled one-shot runner. PREVIEW by default; never prints tokens."""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    base=os.getenv('REMINDER_V35_BOT_URL','').rstrip('/')
    token=os.getenv('REMINDER_V35_JOB_SECRET','')
    mode=os.getenv('REMINDER_V35_JOB_MODE','preview')
    parsed=urlparse(base)
    if (parsed.scheme!='https' or parsed.hostname!='shanlin-bot-production.up.railway.app'
        or parsed.path or parsed.query or parsed.fragment):
        raise SystemExit('需設定官方 Railway HTTPS 服務網址；拒絕其他主機')
    if len(token)<32 or mode not in ('preview','dispatch'):
        raise SystemExit('金鑰未設定或模式錯誤；未呼叫服務')
    body=json.dumps({'mode':mode}).encode('utf-8')
    req=urllib.request.Request(base+'/api/reminder/v35/run', data=body, method='POST',
        headers={'Content-Type':'application/json','X-Reminder-Job-Token':token})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=40) as response:
            data=json.loads(response.read(4096))
    except urllib.error.HTTPError as exc:
        print('提醒執行遭拒，HTTP',exc.code, '；未取得個資或金鑰')
        raise SystemExit(1) from None
    print('提醒排程執行結果（僅彙總，非實際送達）：')
    print({k:data.get(k) for k in ('mode','targetDate','eligible','unverifiedBinding',
        'accepted','duplicateSkipped','rejected','uncertain','limitReached')})

if __name__=='__main__':main()
