"""Same-original-template clinic homepage; fail-closed, static Shanlin."""
import sys
from html.parser import HTMLParser
from pathlib import Path

from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

SITE = Path(__file__).resolve().parents[1] / 'website'
sys.path.insert(0, str(SITE))
import integrated_clinic_routes as routes
from integrated_app_clinics import app

client = TestClient(app)


class Audit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = []
        self.attrs = []
        self.scripts = []
        self.forms = 0
        self.inputs = 0
        self.buttons = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        self.tags.append(tag)
        self.attrs.append((tag, data))
        if 'id' in data:
            self.ids.append(data['id'])
        if tag == 'script':
            self.scripts.append(data)
        if tag == 'form':
            self.forms += 1
        if tag in ('input', 'textarea', 'select'):
            self.inputs += 1
        if tag == 'button':
            self.buttons.append(data)


def get(url):
    res = client.get(url)
    assert res.status_code == 200, res.text
    return res


def test_original_css_and_dom_layout_are_shared_between_clinics():
    yi = get('/?clinic=yidian').text
    sh = get('/?clinic=shanlin').text
    same_structure = ('id="header"', 'id="scrollspyNav"', 'id="main"',
                      'id="scrollspyHero"', 'id="scrollspyAppointment"',
                      'id="scrollspyFooter"', 'elderly-booking-steps',
                      'elderly-plan-grid', 'senior-hero-actions-v14',
                      'doubts-identity-name')
    for marker in same_structure:
        assert marker in yi, marker
        assert marker in sh, marker
    css = ('./assets/css/main.css', './assets/css/index.css?v=doubts-ui-v4',
           './yidian_senior_v14.css?v=15')
    for path in css:
        assert path in yi and path in sh
    assert '山林診所' in sh and '頤典診所' in yi
    assert sh != yi


def test_shanlin_visual_buttons_have_same_placement_but_are_disabled():
    sh = get('/?clinic=shanlin').text
    assert sh.count('class="btn btn-outline-primary bsb-btn-2xl rounded-pill') == 2
    assert sh.count('class="btn btn-primary bsb-btn-2xl rounded-pill"') == 1
    assert sh.count('disabled aria-disabled="true"') == 3
    assert sh.count('class="elderly-plan-card"') == 3
    assert sh.count('aria-disabled="true">尚未開放預約') == 3
    assert 'id="integrated-clinic-home-notice"' in sh
    assert 'href="/?clinic=shanlin"' in sh
    assert '切換診所' not in sh


def test_shanlin_not_accepting_patient_data_or_booking_calls():
    sh = get('/?clinic=shanlin')
    parsed = Audit()
    parsed.feed(sh.text)
    assert parsed.forms == 0 and parsed.inputs == 0
    assert len(parsed.scripts) == 1
    assert parsed.scripts[0]['src'].endswith('/bootstrap.bundle.min.js')
    assert all('onclick' not in attrs and 'onpointerdown' not in attrs
               for _, attrs in parsed.attrs)
    assert not any('href' in attrs and 'appointment.html' in attrs['href']
                   for _, attrs in parsed.attrs)
    assert 'connect-src \'none\'' in sh.headers['content-security-policy']
    assert 'form-action \'none\'' in sh.headers['content-security-policy']
    assert '/api/booking' not in sh.text
    assert 'yidian_speech.js' not in sh.text


def test_shanlin_does_not_claim_yidian_contact_or_taipei_program():
    sh = get('/?clinic=shanlin').text
    for forbidden in ('頤典診所－提供之服務', '115年臺北市', '臺北市文山區',
                      '羅斯福路', '02 2933 2010', '胸部X光', '甲狀腺刺激素',
                      '腦肺方案', '腹部方案', '骨密肌力方案',
                      'href="./appointment.html', 'href="appointment.html'):
        assert forbidden not in sh, forbidden
    assert '地址待診所確認' in sh
    assert '電話及服務時間待診所核對' in sh
    assert '山林診所' in sh


def test_shanlin_page_inherits_real_home_template_edits(monkeypatch):
    original = routes.original_home_page
    html = original().body.decode('utf-8')
    html = html.replace('<head>', '<head><!-- shared-original-template-probe -->', 1)
    monkeypatch.setattr(routes, 'original_home_page', lambda: HTMLResponse(html))
    assert 'shared-original-template-probe' in get('/?clinic=shanlin').text


def test_template_structure_changes_block_rebranding(monkeypatch):
    original = routes.original_home_page
    html = original().body.decode('utf-8')
    broken = html.replace('id="scrollspyHero"', 'id="changedHero"', 1)
    monkeypatch.setattr(routes, 'original_home_page', lambda: HTMLResponse(broken))
    response = client.get('/?clinic=shanlin')
    assert response.status_code == 503
    assert '暫停' in response.json()['detail']


def test_shanlin_never_calls_original_firebase_for_home(monkeypatch):
    import main
    def fail(*_a, **_k):
        raise AssertionError('legacy Firebase read from static Shanlin homepage')
    monkeypatch.setattr(main, 'init_firebase', fail)
    assert get('/?clinic=shanlin').status_code == 200


def test_read_only_all_forms_of_shanlin_homepage_and_no_store():
    for path in ('/?clinic=shanlin', '/index.html?clinic=shanlin',
                 '/clinics/shanlin', '/appointment2.html?clinic=shanlin'):
        r = get(path)
        assert r.headers['cache-control'] == 'no-store'
        assert 'id="scrollspyHero"' in r.text
        assert 'src="site-config.js"' not in r.text
        assert 'src="clinic.js"' not in r.text


def test_booking_post_remains_blocked_for_both_clinics():
    for clinic in ('yidian', 'shanlin'):
        assert client.post('/api/booking/confirm?clinic=' + clinic, json={}).status_code == 423
