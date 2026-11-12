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
