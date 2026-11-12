#!/usr/bin/env python3
"""Local read-only validation, never connects to LINE or Firebase."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'website'))
from fastapi.testclient import TestClient
from integrated_app_platform_v35 import app
import platform_line_bridge_v35 as bridge
import pilot_backend as auth

assert bridge.STATUS_URL == 'https://shanlin-bot-production.up.railway.app/api/reminder/v35/status'
assert bridge._NoRedirect().redirect_request(None,None,302,'',{},'https://example.org') is None
with TestClient(app) as client:
    assert client.get('/platform/modules').status_code==200
    page=client.get('/platform/modules/appointment_reminders/line-status')
    assert page.status_code==200 and 'v3.5 安全排程' in page.text
    assert client.get('/api/pilot/platform/console/line-bot/v35/status').status_code in (401,403)
    assert client.post('/api/reminder/v35/run').status_code==404
    assert client.post('/api/reminder/send').status_code==404
    for route in ('module-center-v35.js','line-status-v35.js'):
        assert client.get('/platform/assets/'+route).status_code==200
print('PASS: 工程師頁面與權限正常；未連線 LINE Bot、未存取病患、未發送訊息')
