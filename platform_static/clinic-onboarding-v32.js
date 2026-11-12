'use strict';
const el = id => document.getElementById(id);
const enc = s => encodeURIComponent(s);
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const slug = /^\/platform\/clinics\/([a-z][a-z0-9-]{2,31})\/setup$/.exec(location.pathname)?.[1] || '';
const base = '/api/pilot/platform/console/onboarding/' + enc(slug);
let csrf = '', state = null;
async function req(url, opts={}) {
  const res = await fetch(url, {credentials:'same-origin',cache:'no-store',...opts});
  const data = await res.json().catch(()=>({}));
  if (!res.ok) {const e = new Error(data.detail||('HTTP '+res.status));e.status=res.status;throw e;}
  return data;
}
function message(text){el('status').textContent=text;}
function mutation(url, payload){return req(url,{method:'POST',headers:{'Content-Type':'application/json','X-Pilot-CSRF':csrf,'Origin':location.origin},body:JSON.stringify({...payload,expectedRevision:state.revision})});}
function render(){
  el('clinicTitle').textContent = state.displayName;
  el('clinicSubtitle').textContent = '診所識別碼：'+state.clinicId+' · '+(state.archived?'已封存':'本機開通準備');
  el('stageChip').textContent = state.reviewState==='pending_review' ? '待驗收（非正式開通）' : '導入草稿';
  el('phone').value=state.profile.phone;
  el('address').value=state.profile.address;
  el('hours').value=state.profile.hours;
  el('accountInfo').textContent=state.account.created?'已建立管理帳號：'+state.account.username:'尚未建立管理帳號';
  if(state.account.created && !el('username').value)el('username').value=state.account.username;
  el('storageMode').value=state.storage.mode;
  el('envUrl').textContent=state.storage.envNames.url;
  el('envCredentials').textContent=state.storage.envNames.credentials;
  el('urlState').textContent=state.storage.urlPresent?(state.storage.urlFormatValid?'已設定（格式可辨識）':'已設定但格式不符'):'尚未提供';
  el('credentialsState').textContent=state.storage.credentialsPresent?'已提供（未顯示內容）':'尚未提供';
  el('storageStatus').textContent=state.storage.configurationPresent?'已找到兩個環境變數且網域未與已知診所相同；尚未驗證 Firebase 實際連線及資料隔離。':'尚未完成專屬資料來源設定；不會嘗試連線或寫入 Firebase。';
  el('stagingLoginLink').href='/platform/clinic-onboarding-login?clinic='+enc(slug);
  // V3.2 has one authoritative feature registry; do not render stale V3 flags.
  el('features').innerHTML='<p>所有功能模組與新診所授權，改由工程師「功能模組管理中心」統一管理。</p><a class="back-link" href="/platform/modules">開啟功能模組管理中心 →</a>';
  el('checklist').innerHTML=state.checklist.map(i=>`<div class="checklist-row"><span class="${i.passed?'check-ok':'check-pending'}">${i.passed?'✓':'○'}</span><span>${esc(i.title)}</span></div>`).join('');
  el('submitReview').disabled=!state.maySubmitForReview || state.reviewState==='pending_review' || state.archived;
  el('submitReview').textContent=state.reviewState==='pending_review'?'已送交驗收（非正式開通）':'完成準備，送交工程師驗收';
  el('content').querySelectorAll('form button, #refreshStorage').forEach(b=>b.disabled=state.archived);
}
async function refresh(){state=await req(base);render();const a=await req(base+'/audit');el('audit').innerHTML=a.entries.length?a.entries.map(x=>`<div>${esc(x.timestamp)} · ${esc(x.actor)} · ${esc(x.action)}</div>`).join(''):'尚無 v3 操作紀錄';}
async function write(url, payload, ok){
  message('儲存中…');try{state=await mutation(url,payload);await refresh();message(ok);}catch(e){message(e.message);if(e.status===409)await refresh();}
}
el('profileForm').addEventListener('submit',e=>{e.preventDefault();write(base+'/profile',{phone:el('phone').value,address:el('address').value,hours:el('hours').value},'診所基本資訊已儲存（僅本機導入資料）');});
el('accountForm').addEventListener('submit',e=>{e.preventDefault();const pwd=el('newPassword').value;if(pwd!==el('confirmPassword').value){message('兩次輸入的密碼不一致');return;}write(base+'/account',{username:el('username').value.trim(),password:pwd,reset:el('resetAccount').checked},'管理帳號已建立／更新（只儲存密碼雜湊）').finally(()=>{el('newPassword').value='';el('confirmPassword').value='';el('resetAccount').checked=false;});});
el('storageForm').addEventListener('submit',e=>{e.preventDefault();write(base+'/storage',{mode:el('storageMode').value},'資料來源規劃已儲存（尚未連接 Firebase）');});
el('refreshStorage').addEventListener('click',()=>refresh().then(()=>message('已重新檢查環境變數存在狀態，未執行連線')).catch(e=>message(e.message)));
el('submitReview').addEventListener('click',()=>write(base+'/review',{},'已送交本機工程師驗收；沒有啟用正式服務'));
(async()=>{if(!slug){location.replace('/platform/clinics');return;}try{const session=await req('/api/pilot/platform/console/session');csrf=session.csrf;await refresh();el('root').hidden=false;el('content').hidden=false;message('已登入工程師帳號：'+session.username+'。本頁只修改新診所導入設定。');}catch(e){if(e.status===401||e.status===403){location.replace('/platform/admin?next=%2Fplatform%2Fclinics');return;}el('root').hidden=false;message('無法載入開通設定：'+e.message);}})();
