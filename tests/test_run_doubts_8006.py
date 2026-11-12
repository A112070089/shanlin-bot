"""Offline launcher guard tests: never connects to real Firebase or Railway."""
import importlib.util
import json
from pathlib import Path
import hashlib
import hmac
import types

import pytest

RUNNER = Path(__file__).resolve().parents[1] / 'scripts' / 'run_doubts_8006.py'
spec = importlib.util.spec_from_file_location('local_8006_runner_for_test', RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    root = tmp_path / 'project'
    for rel in (
        'website/integrated_app_platform_main.py',
        'website/integrated_app_platform_booking_unified.py',
        'website/platform_shanlin_unified_ui.py',
        'website/platform_shanlin_booking_stage.py',
        'website/shanlin_admin_booking_stage.html',
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('test-only fixture')
    (root / 'website/database.json').write_text('{"NAME_DB":{}}')
    (root / 'website/自費項目對話資料庫.json').write_text('{"items":[]}')
    key_dir = tmp_path / '.config' / 'doubts-shanlin-test'
    key_dir.mkdir(parents=True)
    (key_dir / 'firebase-service-account.json').write_text(
        json.dumps({'type': 'service_account', 'project_id': 'doubts-shanlin-test'}))
    secret = 'a' * 64
    (key_dir / 'service-secret').write_text(secret)
    monkeypatch.setattr(runner, 'ROOT', root)
    monkeypatch.setattr(runner, 'SITE', root / 'website')
    monkeypatch.setattr(runner, 'KEY_DIR', key_dir)
    for key in ('PILOT_STORAGE', 'PILOT_SHANLIN_STORAGE', 'PILOT_YIDIAN_STORAGE'):
        monkeypatch.delenv(key, raising=False)
    return root, key_dir, secret


def test_signed_readonly_preflight_success(fixture, monkeypatch):
    _, _, secret = fixture

    class Reply:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return json.dumps({'clinicId': 'shanlin', 'isSynthetic': True}).encode()

    class Opener:
        def open(self, req, timeout):
            assert timeout == 4
            assert req.method == 'GET'
            assert req.full_url == runner.API
            stamp = req.headers['X-doubts-timestamp']
            nonce = req.headers['X-doubts-nonce']
            digest = hashlib.sha256(b'').hexdigest()
            msg = f'GET\n{runner.PATH}\n{stamp}\n{nonce}\n{digest}'
            sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
            assert hmac.compare_digest(sig, req.headers['X-doubts-signature'])
            return Reply()

    monkeypatch.setattr(runner, 'build_opener', lambda *args: Opener())
    assert runner.ready() == secret


def test_refuses_wrong_project_even_if_upstream_online(fixture, monkeypatch):
    _, key_dir, _ = fixture
    (key_dir / 'firebase-service-account.json').write_text(
        json.dumps({'type': 'service_account', 'project_id': 'shanlin-real'}))
    with pytest.raises(SystemExit, match='身分不符'):
        runner.ready()


def test_refuses_production_storage_mode(fixture, monkeypatch):
    monkeypatch.setenv('PILOT_SHANLIN_STORAGE', 'firebase')
    with pytest.raises(SystemExit, match='local-demo'):
        runner.ready()


def test_refuses_wrong_upstream_identity(fixture, monkeypatch):
    class Reply:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return b'{"clinicId":"yidian","isSynthetic":true}'
    monkeypatch.setattr(runner, 'build_opener', lambda *args: types.SimpleNamespace(open=lambda *args, **kw: Reply()))
    with pytest.raises(SystemExit, match='並非山林合成測試'):
        runner.ready()
