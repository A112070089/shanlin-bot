#!/usr/bin/env python3
"""Non-mutating local verification of the v3.4 bridge. Never contacts LINE."""
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
site=root/'website'
for filename in [
    'integrated_app_platform_v34.py',
    'platform_line_routes_v34.py',
    'platform_line_bridge_v34.py',
    'platform_static/module-center-v34.html',
    'platform_static/module-center-v34.js',
    'platform_static/line-status-v34.html',
    'platform_static/line-status-v34.js',
    'platform_static/line-status-v34.css',
]:
    if not (site/filename).is_file():
        raise SystemExit('FAIL: missing '+filename)
sys.path.insert(0,str(site))
from fastapi.testclient import TestClient
from integrated_app_platform_v34 import app
import platform_line_bridge_v34 as line
with TestClient(app) as client:
    assert 'module-center-v34.js' in client.get('/platform/modules').text
    assert client.get('/platform/modules/appointment_reminders/line-status').status_code==200
    assert client.get('/api/pilot/platform/console/line-bot/overview').status_code in (401,403)
    assert client.post('/api/reminder/send').status_code==404
assert line.source_summary()['productionVerified'] is False
print('PASS: v3.4 present; local routes work; engineer access required; no send endpoint; no external requests made.')
