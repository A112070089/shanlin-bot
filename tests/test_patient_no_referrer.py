"""Regression: browser Referrer-Policy no-referrer must not block synthetic test booking."""
import re
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'website'))
import integrated_app_platform_patient_stage as stage

PATH='/api/patient/shanlin/booking-test/confirm?clinic=shanlin'
DATA={'name':'DOUBTS病患測試05','phone':'0999999905','pid':'A123456789',
      'birthday':'1950-01-01','plan':'A','date':'2026-11-18','time':'09:00',
      'breakfast':'葷','selfPayItems':[],'selfPayDate':'','selfPayTime':'',
      'extraAnswers':[]}

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED','1')
    seen=[]
    def relay(method,*,payload=None):
        seen.append((method,payload))
        return {'status':'success','clinicId':'shanlin','isSynthetic':True,
                'action':'create','key':'TEST_05'}
    monkeypatch.setattr(stage,'_relay',relay)
    with TestClient(stage.app) as c:
        yield c,seen


def page_token(client):
    page=client.get('/appointment2.html?clinic=shanlin&p=A')
    assert page.status_code==200
    assert page.headers['referrer-policy']=='no-referrer'  # keep private values out of URLs
    match=re.search(r"X-DOUBTS-Patient-Test-Page', '([A-Za-z0-9_-]+)'",page.text)
    assert match, 'the browser bridge must add the page token to the POST'
    return match.group(1)


def test_real_browser_without_referer_can_submit_fake_appointment(client):
    c,seen=client
    token=page_token(c)
    headers={'Origin':'http://testserver','X-DOUBTS-Patient-Test-Page':token}
    response=c.post(PATH,json=DATA,headers=headers)  # deliberately NO Referer
    assert response.status_code==200,response.text
    assert response.json()['isSynthetic'] is True
    assert len(seen)==1 and seen[0][0]=='POST'
    assert seen[0][1]['name']=='DOUBTS病患測試05'
    assert 'pid' not in seen[0][1] and 'birthday' not in seen[0][1]


@pytest.mark.parametrize('headers',[
    {'Origin':'http://testserver'},
    {'Origin':'http://testserver','X-DOUBTS-Patient-Test-Page':'incorrect'},
    {'Origin':'https://evil.example','X-DOUBTS-Patient-Test-Page':'correct'},
])
def test_missing_or_invalid_proof_is_rejected(client,headers):
    c,seen=client
    response=c.post(PATH,json=DATA,headers=headers)
    assert response.status_code==403
    assert seen==[]


def test_form_sample_roc_dummy_birthday_is_accepted_without_referer(client):
    c,seen=client
    token=page_token(c)
    response=c.post(PATH,json={**DATA,'birthday':'450101'},headers={
        'Origin':'http://testserver','X-DOUBTS-Patient-Test-Page':token})
    assert response.status_code==200,response.text
    assert len(seen)==1 and 'birthday' not in seen[0][1]


def test_other_roc_birthday_stays_blocked(client):
    c,seen=client
    token=page_token(c)
    response=c.post(PATH,json={**DATA,'birthday':'600101'},headers={
        'Origin':'http://testserver','X-DOUBTS-Patient-Test-Page':token})
    assert response.status_code==422
    assert seen==[]


def test_cross_origin_rejected_even_with_genuine_page_token(client):
    c,seen=client
    token=page_token(c)
    response=c.post(PATH,json=DATA,headers={'Origin':'http://evil.example',
                                             'X-DOUBTS-Patient-Test-Page':token})
    assert response.status_code==403
    assert seen==[]


def test_real_patient_and_selfpay_rejected_even_with_proof(client):
    c,seen=client
    token=page_token(c)
    headers={'Origin':'http://testserver','X-DOUBTS-Patient-Test-Page':token}
    for changes,code in [({'name':'實際病患'},422),({'phone':'0912345678'},422),
                         ({'plan':'SELF_PAY'},423),({'selfPayItems':[{'name':'X'}]},423)]:
        response=c.post(PATH,json={**DATA,**changes},headers=headers)
        assert response.status_code==code,response.text
    assert seen==[]
