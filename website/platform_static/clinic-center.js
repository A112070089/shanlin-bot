'use strict';
const $=id=>document.getElementById(id);
const esc=t=>String(t??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api='/api/pilot/platform/console/clinic-registry';
let csrf='',registry=null,editing=null,pendingDelete=null;
async function req(url,opts={}){const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...opts});const obj=await r.json().catch(()=>({}));if(!r.ok){const e=new Error(obj.detail||('HTTP '+r.status));e.status=r.status;throw e;}return obj;}
function message(text){$('status').textContent=text;}
function render(){
  $('existing').innerHTML=registry.existingClinics.map(c=>`<article class="card"><h3>${esc(c.displayName)}</h3><span class="pill">${esc(c.clinicId)}</span><p>既有診所：沿用現行獨立後台與資料；此處不修改。</p></article>`).join('');
  $('drafts').innerHTML=registry.drafts.length?registry.drafts.map(d=>`<article class="card draft-card"><h3>${esc(d.displayName)}</h3><span class="pill">${esc(d.clinicId)}</span><p>${d.archived?'已封存':'導入草稿（未開通）'}</p><p class="muted">${esc(d.notes||'尚無備註')}</p><p class="muted-warning">正式預約尚未開放；開通準備與驗收請進入設定頁</p><div class="draft-actions"><button type="button" data-edit="${esc(d.clinicId)}" class="outline">編輯資料</button><button type="button" data-lifecycle="${esc(d.clinicId)}" class="outline">${d.archived?'恢復草稿':'停用草稿'}</button><button type="button" data-purge="${esc(d.clinicId)}" class="danger-outline" ${d.archived?'':'disabled title="請先停用草稿"'}>永久刪除</button></div><a class="back-link smaller" href="/platform/clinics/${encodeURIComponent(d.clinicId)}/setup">開通準備 →</a></article>`).join(''):'<div class="card">尚未建立新診所草稿。</div>';
  $('drafts').querySelectorAll('[data-edit]').forEach(btn=>btn.addEventListener('click',()=>openEditor(btn.dataset.edit)));
  $('drafts').querySelectorAll('[data-lifecycle]').forEach(btn=>btn.addEventListener('click',()=>changeLifecycle(btn.dataset.lifecycle)));
  $('drafts').querySelectorAll('[data-purge]').forEach(btn=>btn.addEventListener('click',()=>openDelete(btn.dataset.purge)));

}
async function reload(){registry=await req(api);render();const audit=await req(api+'/audit');$('clinicAudit').innerHTML=audit.entries.length?audit.entries.map(a=>`<div>${esc(a.timestamp)} · ${esc(a.actor)} · ${esc(a.clinicId)} · ${esc(a.action)}</div>`).join(''):'尚無草稿操作紀錄。';}
function openEditor(slug){const obj=registry.drafts.find(x=>x.clinicId===slug);if(!obj)return;editing=slug;$('editingClinic').textContent='· '+slug;$('editName').value=obj.displayName;$('editNotes').value=obj.notes;$('archived').checked=obj.archived;$('editor').hidden=false;$('editor').scrollIntoView({behavior:'smooth',block:'start'});}
$('editCancelBtn').onclick=()=>{editing=null;$('editor').hidden=true;};
function closeDelete(){pendingDelete=null;$('deletePanel').hidden=true;$('deleteConfirm').value='';}
$('deleteCancel').onclick=closeDelete;
$('deleteConfirm').addEventListener('input',()=>{$('deleteSubmit').disabled=!pendingDelete||$('deleteConfirm').value.trim()!==pendingDelete.clinicId;});
function mutation(url, method, payload){return req(url,{method,headers:{'Content-Type':'application/json','X-Pilot-CSRF':csrf,'Origin':location.origin},body:JSON.stringify(payload)});}
async function changeLifecycle(slug){
  const draft=registry.drafts.find(d=>d.clinicId===slug);
  if(!draft)return;
  const disabling=!draft.archived;
  if(disabling&&!confirm('停用「'+draft.displayName+'」的本機導入草稿？導入帳號將不能繼續使用；未來可恢復。'))return;
  message(disabling?'正在停用草稿…':'正在恢復草稿…');
  try{
    await mutation(api+'/drafts/'+encodeURIComponent(slug)+'/lifecycle','POST',{disabled:disabling,expectedRevision:registry.revision});
    closeDelete();await reload();message(disabling?'草稿已停用，相關本機導入工作階段已撤銷。':'草稿已恢復；正式服務仍未開放。');
  }catch(e){message(e.message);if(e.status===409)await reload();}
}
async function openDelete(slug){
  closeDelete();
  try{
    const review=await req(api+'/drafts/'+encodeURIComponent(slug)+'/deletion-check');
    if(!review.canPurge){message('目前不可刪除：'+review.blockers.join('；'));return;}
    pendingDelete=review;
    $('deleteId').textContent=review.clinicId;
    $('deleteDetails').textContent='將刪除：'+review.displayName+' ('+review.clinicId+')'+(review.hasLocalAccount?'，包含本機導入管理帳號。':'，目前沒有本機導入帳號。');
    $('deletePanel').hidden=false;
    $('deleteSubmit').disabled=true;
    $('deleteConfirm').value='';
    $('deletePanel').scrollIntoView({behavior:'smooth',block:'center'});
    $('deleteConfirm').focus();
    message('請確認永久刪除範圍，並輸入完整診所識別碼。');
  }catch(e){message(e.message);}
}
$('deleteForm').addEventListener('submit',async event=>{
  event.preventDefault();if(!pendingDelete)return;
  const expected=pendingDelete;
  if($('deleteConfirm').value.trim()!==expected.clinicId){message('診所識別碼不符，未執行刪除');return;}
  $('deleteSubmit').disabled=true;message('正在刪除本機導入草稿…');
  try{
    await mutation(api+'/drafts/'+encodeURIComponent(expected.clinicId),'DELETE',{
      confirmation:$('deleteConfirm').value.trim(),
      expectedRegistryRevision:expected.registryRevision,
      expectedOnboardingRevision:expected.onboardingRevision
    });
    closeDelete();await reload();message('已永久刪除本機草稿；不影響正式診所與外部 Firebase，識別碼不可重用。');
  }catch(e){message(e.message);if(e.status===409)await reload();$('deleteSubmit').disabled=false;}
});
$('createForm').addEventListener('submit',async event=>{event.preventDefault();const btn=$('createBtn');btn.disabled=true;message('正在建立草稿…');try{await req(api+'/drafts',{method:'POST',headers:{'Content-Type':'application/json','X-Pilot-CSRF':csrf,'Origin':location.origin},body:JSON.stringify({clinicId:$('clinicId').value.trim(),displayName:$('displayName').value.trim(),notes:$('notes').value,expectedRevision:registry.revision})});$('createForm').reset();await reload();message('草稿已儲存（尚未建立正式診所帳號或預約功能）');}catch(e){message(e.message);if(e.status===409)await reload();}finally{btn.disabled=false;}});
$('editForm').addEventListener('submit',async event=>{event.preventDefault();if(!editing)return;const btn=$('editSaveBtn');btn.disabled=true;message('正在更新草稿…');try{await req(api+'/drafts/'+encodeURIComponent(editing),{method:'PATCH',headers:{'Content-Type':'application/json','X-Pilot-CSRF':csrf,'Origin':location.origin},body:JSON.stringify({displayName:$('editName').value.trim(),notes:$('editNotes').value,archived:$('archived').checked,expectedRevision:registry.revision})});$('editor').hidden=true;editing=null;await reload();message('診所導入草稿已更新');}catch(e){message(e.message);if(e.status===409)await reload();}finally{btn.disabled=false;}});
(async()=>{try{const s=await req('/api/pilot/platform/console/session');csrf=s.csrf;await reload();$('clinicCenterMain').hidden=false;$('content').hidden=false;message('已登入工程師總控台；此頁僅管理新診所本機草稿及停用／刪除。');}catch(e){if(e.status===401||e.status===403){location.replace('/platform/admin?next=%2Fplatform%2Fclinics');return;}$('clinicCenterMain').hidden=false;message('目前無法載入診所管理中心：'+e.message);}})();
