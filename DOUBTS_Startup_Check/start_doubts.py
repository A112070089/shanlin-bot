#!/usr/bin/env python3
"""DOUBTS local-only one-click starter. Stdlib-only, never deploys or writes appointments.

Services: 8002 TTS, 8003 STT, 8004 translator, 8018 isolated synthetic API,
8006 current integrated frontend. Only starts absent local ports; refuses unsafe 8018 config.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, ProxyHandler, build_opener

ROOT = Path(os.environ.get('DOUBTS_PROJECT_ROOT') or (
    Path(__file__).resolve().parent
)).expanduser()

PRIVATE = Path.home() / '.config' / 'doubts-shanlin-test'
STATE = Path.home() / '.config' / 'doubts-oneclick'
LOGS = Path.home() / 'Library' / 'Logs' / 'DOUBTS-OneClick'
CONFIG = PRIVATE / 'oneclick-local.json'
PIDFILE = STATE / 'started_services.json'
HOST = '127.0.0.1'
OPENER = build_opener(ProxyHandler({}))
PROJECT = 'doubts-shanlin-test'
LOGIN = 'https://shanlin-bot-production.up.railway.app/api/admin/login'


def line(s=''):
    print(s, flush=True)


def port_open(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=0.7):
            return True
    except OSError:
        return False


def get_status(port: int, path: str) -> tuple[int, bytes]:
    try:
        with OPENER.open(Request(f'http://{HOST}:{port}{path}', method='GET'), timeout=4) as r:
            return r.status, r.read(8192)
    except HTTPError as e:
        return e.code, e.read(2048)
    except (URLError, TimeoutError, OSError):
        return 0, b''


def safe_status(port: int, path='/health') -> str:
    code, _ = get_status(port, path)
    return f'HTTP {code}' if code else '無法讀取 HTTP'


def service_secret() -> str | None:
    p = PRIVATE / 'service-secret'
    try:
        s = p.read_text(encoding='utf-8').strip()
        return s if len(s) >= 40 else None
    except OSError:
        return None


def test_credential() -> dict | None:
    try:
        p = PRIVATE / 'firebase-service-account.json'
        creds = json.loads(p.read_text(encoding='utf-8'))
        if (isinstance(creds, dict) and creds.get('project_id') == PROJECT
                and creds.get('type') == 'service_account' and creds.get('private_key')):
            return creds
    except (OSError, ValueError, TypeError):
        pass
    return None


def valid_db_url(s: str) -> bool:
    try:
        u = urlparse(s)
        host = (u.hostname or '').lower()
        suffix_ok = host.endswith('.firebasedatabase.app') or host.endswith('.firebaseio.com')
        return bool(u.scheme == 'https' and suffix_ok and host.startswith(PROJECT)
                    and 'test' in host and not u.username and not u.password
                    and not u.port and u.path in ('', '/')
                    and not u.query and not u.fragment)
    except (TypeError, ValueError, AttributeError):
        return False


def config_db_url() -> str | None:
    try:
        settings = json.loads(CONFIG.read_text(encoding='utf-8'))
        url = settings.get('firebase_database_url')
        if settings.get('enable_8018_autostart') is True and isinstance(url, str) and valid_db_url(url):
            return url.rstrip('/') + '/'
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def signed_8018() -> str:
    secret = service_secret()
    if not secret:
        return '未設定有效的測試簽章金鑰'
    path = '/api/integration/v365/appointments'
    stamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    digest = hashlib.sha256(b'').hexdigest()
    message = '\n'.join(['GET', path, stamp, nonce, digest]).encode()
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    req = Request('http://127.0.0.1:8018' + path, method='GET', headers={
        'X-DOUBTS-Timestamp': stamp, 'X-DOUBTS-Nonce': nonce,
        'X-DOUBTS-Signature': signature,
    })
    try:
        with OPENER.open(req, timeout=7) as r:
            data = json.load(r)
        if data.get('clinicId') == 'shanlin' and data.get('isSynthetic') is True:
            return 'PASS：8018 已驗證為山林合成測試來源'
        return 'STOP：8018 回應未通過合成資料識別'
    except HTTPError as e:
        return f'STOP：8018 讀取 HTTP {e.code}'
    except (URLError, TimeoutError, ValueError, OSError, TypeError):
        return 'STOP：8018 來源驗證失敗'


def project_python() -> Path:
    return ROOT / '.venv' / 'bin' / 'python'


def available_exec(p: Path) -> bool:
    return p.is_file() and os.access(p, os.X_OK)


def find_8002() -> tuple[Path, Path] | None:
    preferred = [
        ROOT / 'Taigi-MMS-Test',
        ROOT / 'Taigi-MMS-Test' / 'website',
        Path.home() / 'Downloads' / 'Taigi-MMS-Test',
        Path.home() / 'Downloads' / 'Taigi-MMS-Test' / 'website',
        ROOT / 'website',
        ROOT,
    ]
    explicit = os.environ.get('DOUBTS_8002_DIR')
    if explicit:
        preferred.insert(0, Path(explicit).expanduser())
    for d in preferred:
        if not (d / 'yidian_taigi_server.py').is_file():
            continue
        choices = [d / 'venv/bin/python', d / '.venv/bin/python',
                   d.parent / 'venv/bin/python', d.parent / '.venv/bin/python']
        py = next((p for p in choices if available_exec(p)), None)
        # No fallback to the main .venv: some previously had torch missing.
        if py:
            return d, py
    return None


def groq_api_key() -> str | None:
    """Read only the speech API key; never import database credentials from .env."""
    inherited = os.environ.get('GROQ_API_KEY', '').strip()
    if inherited:
        return inherited
    for path in (ROOT / '.env', ROOT / 'website' / '.env'):
        try:
            rows = path.read_text(encoding='utf-8-sig').splitlines()
        except (OSError, UnicodeError):
            continue
        selected = None
        for row in rows:
            row = row.strip()
            if row.startswith('export '):
                row = row[7:].lstrip()
            name, separator, raw = row.partition('=')
            if not separator or name.strip() != 'GROQ_API_KEY':
                continue
            try:
                lexer = shlex.shlex(raw, posix=True)
                lexer.whitespace_split = True
                lexer.commenters = '#'
                parts = list(lexer)
            except ValueError:
                continue
            if len(parts) == 1 and parts[0] and not any(c.isspace() for c in parts[0]):
                selected = parts[0]
        if selected:
            return selected
    return None


def build_service(port: int):
    """Return (cwd, python, uvicorn module, env, reload) or (None, reason)."""
    base = os.environ.copy()
    base['PYTHONUNBUFFERED'] = '1'
    base['NO_PROXY'] = 'localhost,127.0.0.1'
    base['no_proxy'] = 'localhost,127.0.0.1'
    if port == 8766:
        cwd = ROOT / 'website'
        py = ROOT / 'DOUBTS_Local_English/.venv/bin/python'
        script = cwd / 'doubts_local_english_server.py'
        if not (available_exec(py) and script.is_file()):
            return None, '英文專用 Python 或語音程式不存在'
        return (cwd, py, 'doubts_local_english_server.py', base, False), None
    if port == 8002:
        found = find_8002()
        if not found:
            return None, '找不到 8002 的 yidian_taigi_server.py 與專用 Python 環境；未猜測或安裝模型'
        cwd, py = found
        return (cwd, py, 'yidian_taigi_server:app', base, False), None
    if port == 8003:
        cwd = ROOT / 'yidian_breeze_asr_stt'
        py = cwd / '.venv/bin/python'
        if not ((cwd / 'asr_service.py').is_file() and available_exec(py)):
            return None, '8003 的 Breeze-ASR 程式或專用 .venv 不存在'
        return (cwd, py, 'asr_service:app', base, False), None
    if port == 8004:
        cwd = ROOT / 'yidian_taigi_v4_complete' / 'translator'
        py = cwd / '.venv/bin/python'
        model = cwd / 'models/taigi-translator-7b-mlx-4bit'
        if not ((cwd / 'taigi_text_service.py').is_file() and available_exec(py) and model.is_dir()):
            return None, '8004 翻譯服務、專用 .venv 或 MLX 模型路徑不存在'
        base['TAIGI_TRANSLATOR_MODEL'] = str(model)
        base['TAIGI_DYNAMIC_DRAFT'] = '1'
        return (cwd, py, 'taigi_text_service:app', base, False), None
    if port == 8018:
        db_url = config_db_url()
        secret = service_secret()
        creds = test_credential()
        if not db_url:
            return None, '8018 尚未完成一次性的測試資料庫網址設定；請執行「設定測試資料庫.command」'
        if not secret or creds is None:
            return None, '8018 測試服務帳戶或簽章金鑰不存在／身分不符；禁止啟動'
        cwd = ROOT
        py = project_python()
        if not ((cwd / 'shanlin_booking_stage/booking_api.py').is_file() and available_exec(py)):
            return None, '8018 測試交易程式或主 .venv 不存在'
        base.update({
            'PYTHONPATH': os.pathsep.join([str(ROOT / 'shanlin_booking_stage'),
                                           str(ROOT / 'shanlin_v363_staging')]),
            'SHANLIN_V363_STAGING_ENABLED': '1',
            'SHANLIN_V363_TEST_FIREBASE_HOST': urlparse(db_url).hostname,
            'SHANLIN_V363_TEST_PROJECT_ID': PROJECT,
            'FIREBASE_URL': db_url,
            'FIREBASE_CREDENTIALS': json.dumps(creds, ensure_ascii=False),
            'SHANLIN_V363_READ_ENABLED': '1',
            'SHANLIN_V365_SYNTHETIC_WRITE_ENABLED': '1',
            'SHANLIN_V363_SERVICE_SECRET': secret,
        })
        return (cwd, py, 'booking_api:app', base, False), None
    if port == 8006:
        key = groq_api_key()
        if key:
            base['GROQ_API_KEY'] = key
        cwd = ROOT
        py = project_python()
        secret = service_secret()
        if not ((cwd / 'website/integrated_app_platform_patient_stage.py').is_file() and available_exec(py)):
            return None, '8006 整合入口或主 .venv 不存在'
        if not secret:
            return None, '8006 缺少既有本機服務金鑰；安全停止'
        base.update({
            'PYTHONPATH': str(ROOT / 'website'),
            'TAIGI_STT_ENABLED': '1',
            'TAIGI_TTS_ENABLED': '1',
            'TAIGI_TTS_DRAFT_MODE': '1',
            'TAIGI_DYNAMIC_DRAFT': '1',
            'PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED': '1',
            'PILOT_V363_SERVICE_SECRET': secret,
            'PILOT_SHANLIN_LEGACY_AUTH': '1',
            'PILOT_SHANLIN_LEGACY_URL': LOGIN,
        })
        return (cwd, py, 'integrated_app_platform_patient_stage:app', base, True), None
    return None, '未支援的服務埠'


def status(port: int):
    labels = {8002: '台語合成 TTS', 8003: '台語辨識 STT',
              8004: '台語翻譯', 8018: '合成測試預約 API', 8006: '診所網站'}
    if not port_open(port):
        return '未啟動'
    if port == 8018:
        return signed_8018()
    if port == 8006:
        web = safe_status(port, '/appointment2.html?clinic=shanlin&p=A')
        a = safe_status(port, '/api/availability?clinic=shanlin')
        stt = safe_status(port, '/api/taigi_stt/health')
        return f'已在運行（預約頁 {web}；名額 API {a}；STT {stt}）'
    return f'已在運行（/health {safe_status(port)}）'


def load_pidfile() -> dict:
    try:
        saved = json.loads(PIDFILE.read_text(encoding='utf-8'))
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        return {}


def save_pidfile(saved: dict):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = PIDFILE.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)
    tmp.replace(PIDFILE)


def launch(port: int, saved: dict) -> None:
    spec, reason = build_service(port)
    if spec is None:
        line(f'  {port} 未啟動：{reason}')
        return
    cwd, py, module, env, reload = spec
    LOGS.mkdir(mode=0o700, parents=True, exist_ok=True)
    logpath = LOGS / f'{port}.log'
    cmd = [str(py), '-m', 'uvicorn', module, '--host', HOST, '--port', str(port)]
    if port == 8766:
        cmd = [str(py), str(cwd / module)]
    if port == 8006:
        cmd.extend(['--app-dir', str(ROOT / 'website')])
    if reload:
        cmd.extend(['--reload', '--reload-dir', str(ROOT / 'website')])
    # private logs: local server may log data from UI debug handlers
    with logpath.open('ab') as log:
        log.write(f'\n===== one-click startup {time.strftime("%Y-%m-%d %H:%M:%S")} =====\n'.encode())
        try:
            proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as e:
            line(f'  {port} 啟動失敗：{type(e).__name__}；詳見專案 Python 環境')
            return
    saved[str(port)] = {'pid': proc.pid, 'module': module}
    save_pidfile(saved)
    line(f'  {port} 正在啟動，背景 PID {proc.pid}（記錄：{logpath}）')
    deadline = time.monotonic() + (18 if port in (8004, 8018, 8006) else 11)
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            line(f'  {port} 已停止（returncode={proc.returncode}），請查看上方 log')
            return
        if port_open(port):
            line(f'  {port} 已監聽 localhost')
            return
        time.sleep(0.6)
    line(f'  {port} 仍在載入；如需檢查：tail -n 30 "{logpath}"')


def verify_pid(pid: int, module: str) -> bool:
    try:
        if module == 'doubts_local_english_server.py':
            result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='],
                                    capture_output=True, text=True, timeout=3)
            return (result.returncode == 0 and
                    str(ROOT / 'website' / module) in shlex.split(result.stdout))
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='],
                                capture_output=True, text=True, timeout=3)
        return result.returncode == 0 and 'uvicorn' in result.stdout and module.split(':')[0] in result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def stop_own():
    saved = load_pidfile()
    if not saved:
        line('找不到由一鍵啟動器建立的服務紀錄；未停止任何服務。')
        return
    for port, entry in sorted(saved.items(), reverse=True):
        pid = entry.get('pid')
        module = entry.get('module', '')
        if type(pid) is not int or not isinstance(module, str) or not verify_pid(pid, module):
            line(f'{port} 不屬於這次啟動器管理的有效程序，已跳過。')
            continue
        try:
            if os.getpgid(pid) != pid:
                line(f'{port} 程序群組不符合預期，已跳過。')
                continue
            os.killpg(pid, signal.SIGTERM)
            line(f'{port} 已送出正常停止訊號。')
        except (OSError, ProcessLookupError, PermissionError):
            line(f'{port} 無法確認停止狀態，請檢查 Terminal。')
    save_pidfile({})
    line('不會停止原本手動啟動的服務，也沒有修改任何預約資料。')


def stop_web_for_restart() -> bool:
    """Stop only a recorded, verified 8006 process group. Never kill by port alone."""
    listening = port_open(8006)
    saved = load_pidfile()
    entry = saved.get('8006')
    if not isinstance(entry, dict):
        if not listening:
            return True
        line('STOP：8006 並非由此啟動器管理，未停止任何程序。請先關閉原本手動啟動 8006 的 Terminal 服務。')
        return False
    pid, module = entry.get('pid'), entry.get('module')
    expected = 'integrated_app_platform_patient_stage:app'
    if type(pid) is not int or module != expected or not verify_pid(pid, module):
        if not listening:
            return True
        line('STOP：8006 程序識別不符，未停止任何程序。')
        return False
    try:
        if os.getpgid(pid) != pid:
            line('STOP：8006 程序群組不符，未停止任何程序。')
            return False
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        line('STOP：8006 無法確認停止，未啟動第二份服務。')
        return False
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not port_open(8006):
            saved.pop('8006', None)
            save_pidfile(saved)
            line('8006 已正常停止；其他服務繼續執行。')
            return True
        time.sleep(0.25)
    line('STOP：8006 尚未釋放服務埠，未重複啟動。')
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='只檢查不啟動')
    parser.add_argument('--stop', action='store_true', help='只停止本工具啟動的服務')
    parser.add_argument('--restart-web', action='store_true', help='只重新啟動本工具管理的 8006，重新載入語音金鑰')
    parser.add_argument('--no-open', action='store_true', help='不開啟瀏覽器')
    args = parser.parse_args()
    os.umask(0o077)
    line('DOUBTS 本機一鍵啟動｜只使用 127.0.0.1，不部署 Railway')
    line(f'專案路徑：{ROOT}')
    if args.stop:
        stop_own()
        return 0
    if not (ROOT / 'website').is_dir():
        line('STOP：專案資料夾不存在。可設定 DOUBTS_PROJECT_ROOT 指向實際專案路徑。')
        return 2
    line('語音辨識金鑰：' + ('已讀取設定（不顯示內容）' if groq_api_key() else '尚未讀到有效設定'))
    if args.restart_web and not args.check:
        if not groq_api_key():
            line('STOP：請先在專案根目錄 .env 設定 GROQ_API_KEY；目前服務未停止。')
            return 2
        if not stop_web_for_restart():
            return 2
        saved = load_pidfile()
        launch(8006, saved)
        line(f'8006：{status(8006)}')
        return 0 if port_open(8006) else 2
    saved = load_pidfile()
    ports = [8002, 8003, 8004, 8766, 8018, 8006]
    for port in ports:
        if port_open(port):
            line(f'{port}：{status(port)}；不重複啟動。')
        elif args.check:
            spec, reason = build_service(port)
            line(f'{port}：未啟動；' + ('已備妥啟動條件' if spec else reason))
        else:
            line(f'{port}：目前未執行。')
            launch(port, saved)
    line('\n=== 啟動結果 ===')
    for port in ports:
        line(f'{port}：{status(port)}')
    line('\n診所首頁：http://127.0.0.1:8006/?clinic=shanlin')
    # Existing older pages may still call 8000 directly. Do not start the old
    # app automatically because its Firebase configuration is not isolated here.
    if not port_open(8000):
        line('注意：舊前端若仍請求 8000，可能顯示連線失敗；本工具為保護資料，不自動開舊 8000。')
    line('管理後台：http://127.0.0.1:8006/pilot?clinic=shanlin&view=admin')
    line('11/20 模擬預約：http://127.0.0.1:8006/appointment2.html?clinic=shanlin&p=A')
    if not args.check and not args.no_open and port_open(8006):
        code, _ = get_status(8006, '/?clinic=shanlin')
        if code == 200 and sys.platform == 'darwin':
            try:
                subprocess.Popen(['open', 'http://127.0.0.1:8006/?clinic=shanlin'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass
    if not config_db_url():
        line('\n注意：8018 下次重新開機若未自動啟動，請先執行一次「設定測試資料庫.command」。')
    line('已執行中的服務不會被重新設定；若舊 8006 少了設定，須先手動停止舊 8006 後再雙擊啟動。')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        line('\n使用者中斷檢查；已啟動的背景服務不會被關閉。')
        raise SystemExit(130)

# DOUBTS_ENGLISH_ONECLICK_V2
