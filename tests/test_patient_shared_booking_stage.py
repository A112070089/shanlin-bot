"""No network/Firebase: Shanlin patient booking is HMAC-stage-only and synthetic."""
from __future__ import annotations

import sys
from pathlib import Path
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'website'))
import integrated_app_platform_patient_stage as patient
from integrated_app_platform_patient_stage import app

DAY = '2026-11-19'


def upstream_data():
    return {
        'clinicId':'shanlin', 'isSynthetic':True,
        'testSchedule':{
            'elderlyDates':['2026-11-18','2026-11-19'],
            'elderlyTimes':['09:00','10:00'],
            'capacityBySlot':{'2026-11-18':{'09:00':1},'2026-11-19':{'09:00':2,'10:00':1}}
        },
        'appointments':[
            {'name':'DOUBTS甲', 'phone':'0999999901','plan':'A', 'date':DAY,'time':'09:00','status':'confirmed'},
            {'name':'DOUBTS乙', 'phone':'0999999902','plan':'A', 'date':DAY,'time':'09:00','status':'confirmed'},
            {'name':'DOUBTS丙','phone':'0999999903','plan':'A', 'date':DAY,'time':'09:00','status':'cancelled'},
        ],
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED', '1')
    def relay(method, *, payload=None):
        if method=='GET': return upstream_data()
        if method=='POST': return {'status':'success','clinicId':'shanlin','isSynthetic':True,
                                   'key':'TEST_ABC','action':'create','revision':'version'}
        raise AssertionError(method)
    monkeypatch.setattr(patient, '_relay', relay)
    with TestClient(app) as c:
        yield c


def test_synthetic_availability_counts_only_active_slots_and_no_identity(client):
    res = client.get('/api/availability?clinic=shanlin')
    assert res.status_code == 200
    j = res.json()
    assert j['elderly'][DAY] == 2
    assert j['slots'][DAY]['09:00'] == {'capacity':2,'occupied':2,'remaining':0,'full':True}
    assert j['slots'][DAY]['10:00']['remaining'] == 1
    assert not any(s in res.text for s in ('DOUBTS甲','0999999901','idNumber','appointments'))
    assert client.get('/api/availability?clinic=yidian').json()['elderly'] == {}
    assert client.get('/api/availability').status_code == 423


def test_config_is_always_sourced_from_test_schedule_not_old_demo_dates(client):
    res=client.get('/api/clinic-config?clinic=shanlin')
    assert res.status_code==200
    c=res.json()['clinic']
    assert c['name']=='山林診所'
    assert c['elderlyDates']==['2026-11-18','2026-11-19']
    assert c['elderlyTimes']==['09:00','10:00']
    assert c['capacityBySlot'][DAY]['09:00']==2
    assert 'morning' in c['selfPayWeekly']['thu']
    assert c['elderlyDates']!=['2026-11-02','2026-11-04','2026-11-09']
    assert client.get('/api/clinic-config?clinic=yidian').json()['clinic']['elderlyDates']==[]


def test_original_web_post_remains_blocked(client):
    assert client.post('/api/booking/confirm?clinic=shanlin',json={}).status_code == 423
    assert client.post('/api/booking/confirm?clinic=yidian',json={}).status_code == 423


def test_clinic_identity_kept_on_two_page_navigation_and_confirm(client):
    a=client.get('/appointment.html?clinic=shanlin&p=A')
    assert a.status_code==200
    assert 'appointment2.html?clinic=shanlin&p=' in a.text
    b=client.get('/appointment2.html?clinic=shanlin&p=A')
    assert b.status_code==200
    assert '/api/patient/shanlin/booking-test/confirm?clinic=shanlin' in b.text
    assert 'booking_success.html?clinic=shanlin' in b.text
    assert '不得輸入任何真實病患資料' in b.text
    assert client.get('/appointment2.html?clinic=yidian&p=A', follow_redirects=False).status_code == 303
    assert client.get('/appointment2.html', follow_redirects=False).status_code == 303


def fake():
    return {'name':'DOUBTS病患測試05','phone':'0999999905','pid':'A123456789',
            'birthday':'1950-01-01','plan':'A','date':'2026-11-19','time':'10:00',
            'breakfast':'1','selfPayItems':[], 'selfPayDate':'','selfPayTime':'', 'extraAnswers':[]}

HEADERS = {'Origin':'http://testserver',
           'Referer':'http://testserver/appointment2.html?clinic=shanlin&p=A'}
PATH='/api/patient/shanlin/booking-test/confirm?clinic=shanlin'


def test_dummy_patient_booking_uses_exact_staff_transaction_transport(monkeypatch, client):
    sent = []
    def relay(method, *, payload=None):
        sent.append((method,payload))
        return {'status':'success','clinicId':'shanlin','isSynthetic':True,
                'key':'TEST_ABC','action':'create','revision':'rev'}
    monkeypatch.setattr(patient, '_relay', relay)
    res=client.post(PATH,json=fake(),headers=HEADERS)
    assert res.status_code==200, res.text
    assert res.json()['isSynthetic'] is True
    assert sent == [('POST',{'name':'DOUBTS病患測試05','phone':'0999999905',
                'plan':'A','date':'2026-11-19','time':'10:00',
                'source':'網站合成測試','veg':'葷'})]
    assert 'A123456789' not in res.text and '0999999905' not in res.text


@pytest.mark.parametrize('patch,code',[
    ({'name':'真實病患姓名'},422),
    ({'phone':'0912345678'},422),
    ({'pid':'B123456789'},422),
    ({'plan':'SELF_PAY'},423),
    ({'selfPayItems':[{'name':'自費項目'}]},423),
    ({'extraAnswers':[{'label':'病歷','value':'機密'}]},423),
    ({'birthday':'1972-08-16'},422),
])
def test_real_or_selfpay_data_denied(monkeypatch, client, patch, code):
    def no_write(*a,**kw):raise AssertionError('should not relay unsafe input')
    monkeypatch.setattr(patient,'_relay',no_write)
    data=fake();data.update(patch)
    assert client.post(PATH,json=data,headers=HEADERS).status_code==code


def test_cross_clinic_cross_origin_and_wrong_page_denied(monkeypatch, client):
    monkeypatch.setattr(patient,'_relay',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('unsafe relay')))
    assert client.post(PATH.replace('clinic=shanlin','clinic=yidian'),json=fake(),headers=HEADERS).status_code==423
    assert client.post(PATH,json=fake()).status_code==403
    assert client.post(PATH,json=fake(),headers={**HEADERS,'Origin':'https://evil.example'}).status_code==403
    assert client.post(PATH,json=fake(),headers={**HEADERS,'Referer':'http://testserver/appointment2.html?clinic=yidian'}).status_code==403


def test_fail_closed_when_schedule_missing(monkeypatch, client):
    monkeypatch.setattr(patient,'_relay',lambda method:{'clinicId':'shanlin','isSynthetic':True,'appointments':[]})
    assert client.get('/api/availability?clinic=shanlin').status_code==503
    assert client.get('/api/clinic-config?clinic=shanlin').status_code==503


def test_explicit_opt_in_required_for_public_test_endpoints(monkeypatch, client):
    monkeypatch.setenv('PILOT_V365_SYNTHETIC_BOOKINGS_ENABLED', '0')
    assert client.get('/api/availability?clinic=shanlin').status_code == 423
    assert client.get('/api/clinic-config?clinic=shanlin').status_code == 423
    assert client.post(PATH, json=fake(), headers=HEADERS).status_code == 423
    assert client.get('/api/availability?clinic=yidian').status_code == 200
