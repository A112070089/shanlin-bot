"""Phase 6 local tests. No model calls, patient data, Firebase, or bookings."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))

from integrated_app_voice import app
from integrated_voice_diagnostics import patch_speech_js


def test_js_is_instrumented_through_original_static_url():
    response = TestClient(app).get('/yidian_speech.js')
    assert response.status_code == 200
    assert response.headers.get('cache-control') == 'no-store'
    assert 'application/javascript' in response.headers['content-type']
    js = response.text
    assert 'failure.code = "http_" + response.status' in js
    assert '"autoplay_blocked"' in js
    assert '"audio_playback_failed"' in js
    assert 'console.warn("[Yidian local Taigi TTS]"' in js
    assert 'Chrome 阻止自動播放台語音訊' in js


def test_unpatched_original_file_is_unchanged():
    original = (SITE / 'yidian_speech.js').read_text(encoding='utf-8')
    assert 'console.warn("[Yidian local Taigi TTS]"' not in original
    assert '台語譯文異常' not in original  # escaped in original legacy JS
    modified = patch_speech_js(original)
    assert len(modified) > len(original)
    assert 'window.YidianSpeech = {' in modified
    assert 'const TTS_TIMEOUT_MS = 20000' in modified


def test_unknown_speech_version_rejected():
    original = (SITE / 'yidian_speech.js').read_text(encoding='utf-8')
    unknown = original.replace('    try { await clip.play(); }', '    try { await clip.play(123); }', 1)
    try:
        patch_speech_js(unknown)
    except ValueError:
        pass
    else:
        raise AssertionError('unknown original should not be patched')


def test_browser_diagnostic_page_has_fixed_text_only():
    resp = TestClient(app).get('/integrated/voice-diagnostics')
    assert resp.status_code == 200
    assert resp.headers['cache-control'] == 'no-store'
    assert '播放三段台語測試' in resp.text
    assert '了解您的健康需求' in resp.text
    assert '/api/taigi_tts/text' in resp.text
    assert 'new Audio(url)' in resp.text
    assert 'media-src' in resp.headers['content-security-policy']
    assert 'getUserMedia' not in resp.text


def test_existing_catalog_and_booking_page_routes_still_work():
    client = TestClient(app)
    resp = client.get('/appointment2.html')
    assert resp.status_code == 200
    assert 'IntegratedCatalogGuard.checkSelection' in resp.text
    catalog = client.get('/api/integrated/catalog/source')
    assert catalog.status_code == 200
    assert catalog.json()['unitCount'] == 56
    assert catalog.json()['readOnly'] is True
    assert client.get('/integrated/health').json()['productionReady'] is False


def test_local_loopback_guard():
    # Simulate requests from a non-loopback client; all diagnostics remain private.
    class ExternalClientScope:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                scope = {**scope, "client": ("203.0.113.9", 12345)}
            await self.wrapped(scope, receive, send)

    with TestClient(ExternalClientScope(app)) as client:
        assert client.get('/integrated/voice-diagnostics').status_code == 403
        assert client.get('/yidian_speech.js').status_code == 403
