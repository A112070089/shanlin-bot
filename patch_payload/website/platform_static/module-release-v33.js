'use strict';
const $=id=>document.getElementById(id);
const escapeText=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const parts=location.pathname.split('/');
const mid=parts.length===5&&parts[1]==='platform'&&parts[2]==='modules'&&parts[4]==='release'?parts[3]:'';
const API='/api/pilot/platform/console/releases/'+encodeURIComponent(mid);
let csrf='',state=null,saving=false;
let progressSaved=false;
const checkSaved=new Set();
async function request(url,options={}){
  const resp=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});
  const data=await resp.json().catch(()=>({}));
  if(!resp.ok){let error=new Error(data.detail||`HTTP ${resp.status}`);error.status=resp.status;throw error;}
  return data;
}
function message(x){$('releaseMessage').textContent=x;}
function releaseEditable(){
  if(!state || !state.release) return false;
  return !state.release.archived && !['submitted','approved'].includes(state.release.acceptance);
}
function progressDirty(){
  if(!state || !state.release) return false;
  return $('devProgress').value !== state.release.progress ||
         $('codeReference').value.trim() !== (state.release.codeReference || '');
}
function updateSaveButtons(){
  if(!state || !state.release) return;
  const editable=releaseEditable();
  const dirty=progressDirty();
  const button=$('saveProgress');
  button.disabled=saving || !editable || !dirty;
  button.textContent=saving?'儲存中…':(!dirty && progressSaved?'已儲存':'儲存進度');
  $('progressSaveStatus').hidden=!(progressSaved && !dirty && !saving);
  document.querySelectorAll('.check-row').forEach(row=>{
    const id=row.dataset.check;
    const form=row.querySelector('form');
    const original=state.release.checks[id] || {status:'pending',evidence:''};
    const changed=form.elements.status.value !== original.status ||
      form.elements.evidence.value.trim() !== (original.evidence || '');
    const btn=row.querySelector('button[type="submit"]');
    btn.disabled=saving || !editable || !changed;
    btn.textContent=saving?'儲存中…':(!changed && checkSaved.has(id)?'已儲存':'儲存檢查');
    const note=row.querySelector('.check-save-status');
    if(note) note.hidden=!(checkSaved.has(id) && !changed && !saving);
  });
}

function write(path,body){
  return request(API+path,{method:'POST',headers:{'Content-Type':'application/json','Origin':location.origin,'X-Pilot-CSRF':csrf},body:JSON.stringify({...body,expectedRevision:state.revision})});
}
const phaseNames={planned:'規劃中',developing:'開發中',testing:'測試中'};
const stateNames={draft:'草稿',submitted:'待驗收',approved:'驗收已核准',rejected:'退回修正'};
const checkNames={pending:'未檢查',passed:'人工回報通過',failed:'測試未通過'};
function render(){
  const r=state.release;
  $('releaseTitle').textContent=r.name+'｜版本 '+r.version+' 部署與驗收';
  $('releaseTags').innerHTML=`<span class="tag">開發：${escapeText(phaseNames[r.progress]||r.progress)}</span>
    <span class="tag ${r.deploymentVerified?'good':'warning'}">${r.deploymentVerified?'已完成程式部署驗證':'待程式部署驗證'}</span>
    <span class="tag ${r.acceptedEffective?'good':''}">驗收：${escapeText(stateNames[r.acceptance]||r.acceptance)}</span>
    <span class="tag">${r.standardIncluded?'已納入共用標準版':'尚未納入標準版'}</span>`;
  $('releaseSummary').textContent=r.note;
  const history=state.historicalVersions.filter(v=>v!==r.version);
  $('releaseVersions').textContent=history.length?'舊版紀錄：'+history.join('、')+'；更改規劃版本後，新版檢查表會重新開始。':'這是目前版本的第一份驗收紀錄。';
  $('devProgress').value=r.progress;
  $('codeReference').value=r.codeReference||'';
  const editable=!r.archived&&!['submitted','approved'].includes(r.acceptance);
  $('devProgress').disabled=!editable;$('codeReference').disabled=!editable;$('saveProgress').disabled=!editable;
  $('releaseChecks').innerHTML=Object.entries(state.checkNames).map(([id,name])=>{
    const entry=r.checks[id]||{status:'pending',evidence:''};
    return `<div class="check-row" data-check="${escapeText(id)}"><h3>${escapeText(name)}</h3>
      <form class="check-form"><label>檢查狀態<select name="status" ${editable?'':'disabled'}>
        ${Object.entries(checkNames).map(([status,label])=>`<option value="${status}" ${entry.status===status?'selected':''}>${escapeText(label)}</option>`).join('')}
      </select></label><label>測試佐證（不可包含病患資料）
        <input name="evidence" maxlength="240" value="${escapeText(entry.evidence)}" placeholder="例如 pytest 報告編號／隔離測試結果" ${editable?'':'disabled'}></label>
      <div class="release-check-save"><button type="submit" ${editable?'':'disabled'}>儲存檢查</button>
      <span class="saved-note check-save-status" role="status" hidden>✓ 已儲存。</span></div></form></div>`;
  }).join('');
  document.querySelectorAll('.check-row form').forEach(form=>{
    form.addEventListener('submit',saveCheck);
    for(const eventName of ['input','change']){
      form.addEventListener(eventName,()=>{
        checkSaved.delete(form.closest('.check-row').dataset.check);
        updateSaveButtons();
      });
    }
  });

  $('deploymentNotice').textContent=r.deploymentMessage;
  $('acceptanceNotice').textContent=(r.acceptance==='submitted'?'已送交驗收：等待工程師核對程式部署、測試佐證及資料安全。':
    r.acceptance==='approved'?'此版本已有驗收紀錄；真正使用權限仍由後端部署及診所開通條件控制。':
    r.acceptance==='rejected'?'驗收退回：'+r.rejectionReason:
    '尚未送交驗收。請填寫測試中狀態、程式參照碼及五項通過佐證，再送交審核。');
  $('submitReview').hidden=!['draft','rejected'].includes(r.acceptance);
  $('submitReview').disabled=!r.canSubmit;
  $('withdrawReview').hidden=r.acceptance!=='submitted';
  $('approveReview').hidden=r.acceptance!=='submitted';
  $('approveReview').disabled=!r.canApprove;
  $('rejectReview').hidden=r.acceptance!=='submitted';
  updateSaveButtons();
}
async function updateAudit(){
  const data=await request(API+'/audit');
  $('releaseAudit').innerHTML=data.entries.length?data.entries.map(x=>
    `<div>${escapeText(x.timestamp)} · ${escapeText(x.actor)} · ${escapeText(x.action)} · 版本 ${escapeText(x.version)}${x.checkId?' · '+escapeText(x.checkId):''}</div>`).join(''):'尚無變更紀錄';
}
async function reload(){state=await request(API);render();await updateAudit();}
async function mutate(path,body,success){
  if(saving)return;
  const isProgress=path==='/progress';
  const savedCheck=path.startsWith('/checks/')?decodeURIComponent(path.slice('/checks/'.length)):null;
  if(isProgress) progressSaved=false;
  if(savedCheck) checkSaved.delete(savedCheck);
  saving=true;
  updateSaveButtons();
  message('正在儲存驗收紀錄…');
  try{
    state=await write(path,body);
    if(isProgress) progressSaved=true;
    if(savedCheck) checkSaved.add(savedCheck);
    render();
    await updateAudit().catch(()=>{}); // saving succeeded even if optional audit refresh fails
    message(success);
  }catch(e){
    progressSaved=false;
    if(savedCheck) checkSaved.delete(savedCheck);
    message(e.status===409?'另一個視窗已修改此模組，已重新載入，請再次檢查後操作。':e.message);
    if(e.status===409) await reload().catch(()=>{}); // otherwise preserve unsaved edits for retry
  }finally{
    saving=false;
    updateSaveButtons();
  }
}
function progressChanged(){progressSaved=false;updateSaveButtons();}
$('devProgress').addEventListener('change',progressChanged);
$('codeReference').addEventListener('input',progressChanged);
$('progressForm').addEventListener('submit',e=>{
  e.preventDefault();mutate('/progress',{progress:$('devProgress').value,codeReference:$('codeReference').value.trim()},'開發進度已儲存。');
});
function saveCheck(e){
  e.preventDefault();const item=e.currentTarget.closest('.check-row');
  const form=e.currentTarget;
  mutate('/checks/'+encodeURIComponent(item.dataset.check),{status:form.elements.status.value,evidence:form.elements.evidence.value.trim()},'檢查結果已紀錄（人工回報，非自動驗證）。');
}
$('submitReview').addEventListener('click',()=>{
  if(!confirm('確定送交此版本驗收？送驗不等於部署，也不會開通診所功能。'))return;
  mutate('/submit',{},'已送交驗收；仍須完成獨立的程式部署驗證。');
});
$('withdrawReview').addEventListener('click',()=>mutate('/withdraw',{},'送驗已撤回，可修改檢查表。'));
$('approveReview').addEventListener('click',()=>{
  if(!state.release.canApprove)return;
  if(!confirm('確認部署與五項檢查皆已完成，核准這一版驗收？'))return;
  mutate('/approve',{},'此版本驗收已核准；不會自動開放臨床服務。');
});
$('rejectReview').addEventListener('click',()=>{
  const reason=prompt('請填寫退回原因（至少五字，不含病患資料）');
  if(reason===null)return;
  mutate('/reject',{reason:reason.trim()},'已退回修正。');
});
(async()=>{
  try{
    if(!mid||!/^[a-z][a-z0-9_]{2,39}$/.test(mid))throw Error('模組網址不正確');
    const sess=await request('/api/pilot/platform/console/session');csrf=sess.csrf;
    await reload();$('releaseMain').hidden=false;$('releaseContent').hidden=false;
    message('工程師 '+sess.username+' 已登入。此頁只紀錄發布／驗收，不執行部署。');
  }catch(error){
    if(error.status===401||error.status===403){location.replace('/platform/admin?next=%2Fplatform%2Fmodules');return;}
    $('releaseMain').hidden=false;message('讀取失敗：'+error.message);
  }
})();
