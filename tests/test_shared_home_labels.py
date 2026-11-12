"""Check exactly three approved visible wording changes for BOTH clinic homes."""
from pathlib import Path
import sys

from fastapi.testclient import TestClient

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))
from integrated_app_home_restored import app


def test_both_homepages_show_same_requested_labels():
    with TestClient(app) as client:
        for clinic in ('yidian', 'shanlin'):
            response = client.get(f'/?clinic={clinic}')
            assert response.status_code == 200, (clinic, response.text[:300])
            html = response.text
            assert '<h1 class="display-3 fw-bolder mb-3">健康檢查<br />預約服務</h1>' in html
            assert '高齡健檢語音助理' in html
            assert '自費健檢語音助理' in html
            assert '115年臺北市<br />老人健康檢查' not in html
            assert '老人健檢語音助理' not in html
            assert '自費加購語音助理' not in html
            assert '一般預約' in html
            assert '<h2 id="elderlyBookingTitle">預約健檢</h2>' in html


def test_protect_existing_clinic_identity_and_separation():
    with TestClient(app) as client:
        yi = client.get('/?clinic=yidian').text
        sh = client.get('/?clinic=shanlin').text
        assert '頤典診所' in yi and '山林診所' in sh
        assert '尚未建立方案' in yi
        assert '腦肺方案' not in yi
        assert '<h3 id="elderlyPlanA">腦肺方案</h3>' in sh
        assert '臺北市文山區羅斯福路六段407號2樓' in sh
        assert client.post('/api/booking/confirm?clinic=shanlin', json={'name':'dummy'}).status_code == 423
        assert client.post('/api/booking/confirm?clinic=yidian', json={'name':'dummy'}).status_code == 423


def test_original_html_remains_unmodified():
    original = (SITE / 'index.html').read_text(encoding='utf-8')
    assert '115年臺北市<br />老人健康檢查' in original
    assert '老人健檢語音助理' in original
    assert '自費加購語音助理' in original
