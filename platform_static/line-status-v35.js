'use strict';
const el = id => document.getElementById(id);
const API = '/api/pilot/platform/console/line-bot';
async function request(url){
  const res=await fetch(url,{credentials:'same-origin',cache:'no-store'});
  const body=await res.json().catch(()=>({}));
  if(!res.ok){const e=new Error(typeof body.detail==='string'?body.detail:`HTTP ${res.status}`);e.status=res.status;throw e;}
  return body;
}
function redirectIfUnauthorized(err){
  if(err.status===401||err.status===403){
    location.replace('/platform/admin?next='+encodeURIComponent('/platform/modules/appointment_reminders/line-status'));
    return true;
  }
  return false;
}
const checkLabels=[['binding','LINE 電話綁定'],['reminder','前一天提醒程式'],['scheduler','自動排程'],['delivery','實際發送與送達'],['deduplication','重複發送防護'],['security','發送端點授權']];
function renderSource(summary){
  el('sourceContext').textContent=summary.source;
  const grid=el('checkGrid');grid.replaceChildren();
  for(const [key,heading] of checkLabels){
    const item=summary[key];
    const card=document.createElement('div');card.className='line-check';
    const h=document.createElement('strong');h.textContent=heading;
    const badge=document.createElement('span');badge.className='tag '+(item.state==='source_found'?'source':'warn');
    badge.textContent=item.state==='source_found'?'程式碼中存在':item.state==='needs_review'?'需要安全修正':'尚未驗證';
    const note=document.createElement('p');note.textContent=item.label;note.className='muted';
    card.append(h,badge,note);grid.append(card);
  }
  el('codeLink').href=summary.sourceUrl;
}
let checking=false;
el('checkService').addEventListener('click',async()=>{
  if(checking)return;
  checking=true;el('checkService').disabled=true;el('checkService').textContent='檢查中…';
  el('serviceState').textContent='正在唯讀確認服務首頁…';
  try{
    const state=await request(API+'/probe');
    el('serviceState').textContent=state.service.label;
    el('lastChecked').textContent='檢查時間（UTC）：'+state.checkedAtUtc+'；不代表每日提醒已成功。';
  }catch(error){
    if(redirectIfUnauthorized(error))return;
    el('serviceState').textContent='檢查失敗：'+error.message;
  }finally{
    checking=false;el('checkService').disabled=false;el('checkService').textContent='重新檢查連線';
  }
});
(async()=>{
  try{
    const sess=await request('/api/pilot/platform/console/session');
    const data=await request(API+'/overview');
    renderSource(data.integration);
    el('lineMain').hidden=false;el('lineContent').hidden=false;
    el('pageMessage').textContent='工程師 '+sess.username+' 已登入。此頁只讀，不會發送提醒或變更資料。';
  }catch(error){
    if(redirectIfUnauthorized(error))return;
    el('lineMain').hidden=false;el('pageMessage').textContent='狀態載入失敗：'+error.message;
  }
})();

// v3.5: second, independent, authenticated server-to-server READ-ONLY check.
let v35Pending=false;
el('checkV35Status').addEventListener('click', async()=>{
  if(v35Pending)return;
  v35Pending=true;
  el('checkV35Status').disabled=true;
  el('checkV35Status').textContent='核對中…';
  el('v35StatusText').textContent='正在向山林服務查詢（不發送訊息）…';
  el('v35Details').hidden=true;
  try{
    const data=await request('/api/pilot/platform/console/line-bot/v35/status');
    el('v35StatusText').textContent=data.label||'狀態未知';
    if(data.state==='connected'){
      el('v35Details').hidden=false;
      el('v35SendEnabled').textContent='正式發送：'+(data.sendEnabled?'已設定允許（仍需通過授權及發送時段）':'關閉；預設僅可預覽');
      el('v35Scheduler').textContent='每日排程：尚未獨立驗證；請確認 Cron 工作紀錄。';
      const last=data.lastRun;
      el('v35LastRun').textContent=last?
        '最近執行：'+(last.runAtUtc||'時間未知')+'（'+(last.mode==='dispatch'?'發送模式':'預覽模式')+'），預約日 '+(last.targetDate||'未知'):
        '目前尚無可讀取的受授權執行紀錄。';
      el('v35Counts').textContent=last?
        `符合綁定資格 ${last.eligible||0} · 綁定待驗證 ${last.unverifiedBinding||0} · LINE 已接受 ${last.accepted||0} · 避免重複 ${last.duplicateSkipped||0} · 失敗 ${last.rejected||0} · 未確定 ${last.uncertain||0}`:
        '尚無發送彙總資料。';
    }
  }catch(error){
    if(redirectIfUnauthorized(error))return;
    el('v35StatusText').textContent='狀態核對失敗：'+error.message;
  }finally{
    v35Pending=false;
    el('checkV35Status').disabled=false;
    el('checkV35Status').textContent='重新核對 v3.5 安全狀態';
  }
});
