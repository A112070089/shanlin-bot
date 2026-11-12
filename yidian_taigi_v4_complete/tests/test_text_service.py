"""Mocked REST API smoke tests; does not load an actual MLX model."""
import sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'translator'))
from fastapi.testclient import TestClient
import taigi_text_service as m
os.environ['TAIGI_DYNAMIC_DRAFT']='1'
class FakeConverter:
 def get(self,text):return 'Tsit hāng kiám-tsa kah tsit ê tshing-tuann.'
m._conv=lambda: FakeConverter()
m._translate_poj_model=lambda text:'Góa beh liáu-kái tsit-ê.'
m._only_local=lambda req:None
client=TestClient(m.app)
a=client.post('/convert',json={'text':'這項檢查可以了解這個選單。'})
assert a.status_code==200,(a.status_code,a.text)
a=client.post('/translate',json={'text':'請選擇其他項目。'})
assert a.status_code==200,(a.status_code,a.text)
a=client.post('/convert',json={'text':''}); assert a.status_code==422
os.environ['TAIGI_DYNAMIC_DRAFT']='0'
a=client.post('/translate',json={'text':'請選擇其他項目。'});assert a.status_code==403
print('PASS: 8004 convert/translate, invalid length, draft gate (mocked converter/model).')
