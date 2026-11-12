import os, sys, io, wave, json, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WEBSITE=ROOT/'website'
DB=WEBSITE/'自費項目對話資料庫.json'
SRC=ROOT/'tests/clinic_db_reference.json'
created_db=not DB.exists()
if created_db: shutil.copy2(SRC,DB)
os.environ['TAIGI_TTS_ENABLED']='1'
os.environ['TAIGI_TTS_DRAFT_MODE']='1'
os.environ['TAIGI_DYNAMIC_DRAFT']='1'
sys.path.insert(0,str(WEBSITE))
try:
 import yidian_taigi_router as r
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 # simulate voice server and Hanji converter, not a real native-speaker test.
 def fake_wav(text):
  out=io.BytesIO()
  with wave.open(out,'wb') as w:
   w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b'\x00\x00'*64)
  return out.getvalue()
 r._fetch_wav=fake_wav
 r._hanji_to_poj=lambda text: "Tsit hāng kiám-tsa beh khòaⁿ ê tsōng-hóng."
 r._require_local_test=lambda request: None
 r._ask_local_translator=lambda text: "Tshiánn lí khòaⁿ tsit-ê."
 app=FastAPI();app.include_router(r.router)
 client=TestClient(app)
 db=json.loads(DB.read_text())
 review=json.loads((WEBSITE/'yidian_taigi_medical_review.json').read_text())
 assert set(review['items'])=={x['id'] for x in db['items']}
 assert set(review['packages'])=={x['package_id'] for x in db['packages']}
 assert sum(bool(e.get('taigi_hanji_draft')) for kind in ('items','packages') for e in review[kind].values())==110
 passed=0
 for item in db['items']:
  payload={'item_id':item['id'],'item_name':item['name'],'plain_explanation':item['plain_explanation']}
  # item explanations may include entire package too (the user's actual button behavior).
  pkg=next((p for p in db['packages'] if p['package_id']==item.get('package_id')),None)
  if pkg:
   payload['package_explanation']=pkg['plain_explanation']
  response=client.post('/api/taigi_tts/explanation',json=payload)
  assert response.status_code==200,(item['id'],response.status_code,response.text)
  assert response.headers.get('X-Taigi-Review')=='draft'
  passed+=1
 for p in db['packages']:
  response=client.post('/api/taigi_tts/explanation',json={'item_id':p['package_id'],'item_name':p['name'],'plain_explanation':p['plain_explanation']})
  assert response.status_code==200,(p['package_id'],response.status_code,response.text)
  passed+=1
 assert passed==110
 info=client.get('/api/taigi_tts/explanation/coverage').json()
 assert info['coverage']['items']['draft']==101, info
 assert info['coverage']['packages']['draft']==9, info
 assert info['hanji_drafts']=={'items':101,'packages':9}
 dynamic=client.post('/api/taigi_tts/text',json={'text':'請選擇下一項檢查。','source':'ai_reply'})
 assert dynamic.status_code==200,(dynamic.status_code,dynamic.text)
 sensitive=client.post('/api/taigi_tts/text',json={'text':'請輸入 A123456789 身分證','source':'ai_reply'})
 assert sensitive.status_code==422
 mismatch=client.post('/api/taigi_tts/explanation',json={'item_id':'I001','plain_explanation':'不相符的資料'})
 assert mismatch.status_code==409
 os.environ['TAIGI_TTS_DRAFT_MODE']='0'
 unavailable=client.post('/api/taigi_tts/explanation',json={'item_id':'I036','plain_explanation':db['items'][35]['plain_explanation']})
 assert unavailable.status_code==422
 print('PASS: 110 item/package IDs, draft coverage, combined explanations, dynamic text, privacy guard, source mismatch, production draft gate.')
finally:
 if created_db and DB.exists():DB.unlink()
