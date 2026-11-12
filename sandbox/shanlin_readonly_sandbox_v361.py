"""A separate, synthetic only API mimicking the ORIGINAL Shanlin read endpoints.

For local test use ONLY on 127.0.0.1:8017. Contains no real patient data.
NEVER deploy to Railway or attach a live Firebase connection.
"""
import os
from hmac import compare_digest
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

TAG = 'DOUBTS-SANDBOX-V361'
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# All identities, dates, telephone-like strings are synthetically invented.
_SYNTHETIC = (
    {'_key':'TEST-APPT-001','name':'測試甲','phone':'TEST-NO-PHONE-1','idNumber':'TEST-NO-ID-1',
     'date':'2026-11-03','time':'09:00','plan':'A','source':'電話','_hasSelfPay':False,'_pureSelfPay':False},
    {'_key':'TEST-APPT-002','name':'測試乙','phone':'TEST-NO-PHONE-2','idNumber':'TEST-NO-ID-2',
     'date':'2026-11-03','time':'09:00','plan':'B','source':'網站','_hasSelfPay':True,'_pureSelfPay':False},
    {'_key':'TEST-APPT-003','name':'測試丙','phone':'TEST-NO-PHONE-3','idNumber':'TEST-NO-ID-3',
     'date':'2026-11-04','time':'10:00','plan':'C','source':'Excel','_hasSelfPay':False,'_pureSelfPay':False},
    {'_key':'SELF_PAY_TEST-004','name':'測試丁','phone':'TEST-NO-PHONE-4','idNumber':'TEST-NO-ID-4',
     'date':'','time':'','selfPayDate':'2026-11-05','selfPayTime':'14:30',
     'source':'SELF_PAY_BOOKING','_hasSelfPay':True,'_pureSelfPay':True},
)


def _check(x_sandbox_token: str | None) -> None:
    expected = os.environ.get('PILOT_V361_SANDBOX_TOKEN', '')
    if len(expected) < 24 or not x_sandbox_token or not compare_digest(expected, x_sandbox_token):
        raise HTTPException(403, '模擬環境驗證失敗')


@app.get('/api/admin/clinic-config')
def sandbox_clinic_config(x_sandbox_token: str | None = Header(default=None)):
    _check(x_sandbox_token)
    return JSONResponse({'sourceTag':TAG,'configured':True,'clinic':{'name':'山林診所'}},
                        headers={'Cache-Control':'no-store'})


@app.get('/api/admin/appointments')
def sandbox_appointments(x_sandbox_token: str | None = Header(default=None)):
    _check(x_sandbox_token)
    return JSONResponse({'sourceTag':TAG,'appointments':list(_SYNTHETIC)},
                        headers={'Cache-Control':'no-store'})
