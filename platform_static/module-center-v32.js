'use strict';
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const API='/api/pilot/platform/console/modules';
let csrf='',catalog=null,editing=null,pending=false;
async function request(path,options={}){
  const res=await fetch(path,{credentials:'same-origin',cache:'no-store',...options});
  const value=await res.json().catch(()=>({}));
  if(!res.ok){const err=new Error(value.detail||('HTTP '+res.status));err.status=res.status;throw err;}
  return value;
}
function info(message){$('moduleStatus').textContent=message;}
function updateRequest(path,method,body){
  return request(path,{method,headers:{'Content-Type':'application/json','Origin':location.origin,'X-Pilot-CSRF':csrf},body:JSON.stringify(body)});
}
function render(){
  const clinics=catalog.clinics;
  $('moduleList').innerHTML=catalog.modules.map(m=>{
    const stage=m.stage==='testing'?'測試中':'規劃中';
    const checked=clinics.filter(c=>catalog.grants[c.id]?.[m.id]).length;
    const options=clinics.map(c=>{
      const disabled=!!m.archived||!c.active;
      const isChecked=!!catalog.grants[c.id]?.[m.id];
      return `<label class="module-clinic ${disabled?'disabled':''}" title="${disabled?'此模組或診所已停用': '只會儲存預先授權，不會自動部署'}"><span>${esc(c.name)}${c.kind==='draft'?'（導入草稿）':''}${!c.active?' · 已停用':''}</span><input type="checkbox" data-module="${esc(m.id)}" data-clinic="${esc(c.id)}" ${isChecked?'checked':''} ${disabled?'disabled':''} aria-label="${esc(m.name)} 授權給 ${esc(c.name)}"></label>`;
    }).join('');
    return `<article class="module-item ${m.archived?'archived':''}">
      <div class="module-head"><div><h3 class="module-title">${esc(m.name)}</h3><p class="module-id">${esc(m.id)}</p></div>
      <span class="module-tag ${m.archived?'off':''}">${m.archived?'已停用':stage}</span></div>
      <p>${esc(m.description||'尚無功能說明')}</p>
      <div class="module-meta"><span class="module-tag">規劃版本 ${esc(m.plannedVersion)}</span><span class="module-tag wait">${m.deployment==='deployed'?'已驗證部署':'尚未部署程式'}</span><span class="module-tag">已預先授權 ${checked} 家</span></div>
      <div class="module-clinics">${options}</div>
      <div class="module-actions"><button type="button" class="outline" data-edit="${esc(m.id)}">編輯模組</button>
      <button type="button" class="${m.archived?'outline':'danger-outline'}" data-lifecycle="${esc(m.id)}">${m.archived?'恢復模組':'停用模組'}</button></div>
    </article>`;
  }).join('')||'<div class="card">還沒有建立任何功能模組。</div>';
  document.querySelectorAll('#moduleList input[data-module]').forEach(el=>el.addEventListener('change',()=>toggleGrant(el)));
  document.querySelectorAll('#moduleList [data-edit]').forEach(el=>el.addEventListener('click',()=>editModule(el.dataset.edit)));
  document.querySelectorAll('#moduleList [data-lifecycle]').forEach(el=>el.addEventListener('click',()=>toggleLifecycle(el.dataset.lifecycle)));
}
async function audit(){
  const data=await request(API+'/audit');
  $('moduleAudit').innerHTML=data.entries.length?data.entries.map(x=>`<div>${esc(x.timestamp)} · ${esc(x.actor)} · ${esc(x.action)} · ${esc(x.moduleId||'')}${x.clinicId?' / '+esc(x.clinicId):''}</div>`).join(''):'尚無模組操作紀錄';
}
async function reload(){catalog=await request(API);render();await audit();}
async function mutate(path,method,body,message){
  if(pending)return;
  pending=true;
  info('正在儲存…');
  try{
    const result=await updateRequest(path,method,{...body,expectedRevision:catalog.revision});
    catalog=result.registry;render();await audit();info(message);
  }catch(error){
    info(error.status===409?'其他工程師視窗已修改設定，已重新載入資料，請再操作。':error.message);
    await reload().catch(()=>{});
  }finally{pending=false;}
}
function editModule(mid){
  const row=catalog.modules.find(m=>m.id===mid);if(!row)return;
  editing=mid;
  $('moduleEditorHeading').textContent='編輯模組：'+row.name;
  $('modId').value=row.id;$('modId').readOnly=true;
  $('modName').value=row.name;$('modDescription').value=row.description;
  $('modVersion').value=row.plannedVersion;$('modStage').value=row.stage;
  $('moduleSave').textContent='儲存模組資料';$('moduleEditor').hidden=false;
  $('moduleEditor').scrollIntoView({behavior:'smooth',block:'start'});
}
function newModule(){
  editing=null;$('moduleForm').reset();
  $('moduleEditorHeading').textContent='新增功能模組';$('modId').readOnly=false;
  $('modVersion').value='0.1.0';$('modStage').value='planned';
  $('moduleSave').textContent='建立模組';$('moduleEditor').hidden=false;
  $('moduleEditor').scrollIntoView({behavior:'smooth',block:'start'});
}
async function toggleLifecycle(mid){
  const item=catalog.modules.find(x=>x.id===mid);if(!item)return;
  const archived=!item.archived;
  if(archived&&!confirm('確定停用「'+item.name+'」？停用後不再允許新增診所授權，所有診所的功能也會停止提供。'))return;
  await mutate(API+'/'+encodeURIComponent(mid)+'/lifecycle','POST',{archived},archived?'已停用模組，原授權紀錄保留供日後恢復。':'已恢復模組，但尚未部署程式。');
}
async function toggleGrant(input){
  const clinicId=input.dataset.clinic,mid=input.dataset.module,enabled=input.checked;
  input.disabled=true;
  await mutate(API+'/'+encodeURIComponent(mid)+'/grants','POST',{clinicId,enabled},
      '已儲存診所預先授權；未部署模組不會開放給醫護人員。');
}
$('moduleForm').addEventListener('submit',async event=>{
  event.preventDefault();if(pending)return;
  const mid=$('modId').value.trim();
  const payload={name:$('modName').value.trim(),description:$('modDescription').value.trim(),
    plannedVersion:$('modVersion').value.trim(),stage:$('modStage').value};
  if(!editing){payload.id=mid;}
  const target=editing?API+'/'+encodeURIComponent(editing):API;
  const method=editing?'PATCH':'POST';
  const label=editing?'模組資料已更新。':'新模組已加入登錄表；尚未部署程式。';
  if(pending)return;
  pending=true;$('moduleSave').disabled=true;info('正在儲存…');
  try{
    const result=await updateRequest(target,method,{...payload,expectedRevision:catalog.revision});
    catalog=result.registry;render();await audit();
    $('moduleEditor').hidden=true;editing=null;info(label);
  }catch(error){info(error.status===409?'資料已由另一視窗更新，請重新整理後確認變更。':error.message);await reload().catch(()=>{});}
  finally{$('moduleSave').disabled=false;pending=false;}
});
$('newModule').addEventListener('click',newModule);
$('moduleCancel').addEventListener('click',()=>{$('moduleEditor').hidden=true;editing=null;});
(async()=>{
  try{
    const session=await request('/api/pilot/platform/console/session');csrf=session.csrf;
    await reload();$('moduleMain').hidden=false;$('moduleContent').hidden=false;
    info('已登入工程師帳號 '+session.username+'，此處只管理模組登錄與預先授權。');
  }catch(error){
    if(error.status===401||error.status===403){location.replace('/platform/admin?next=%2Fplatform%2Fmodules');return;}
    $('moduleMain').hidden=false;info('載入功能模組中心失敗：'+error.message);
  }
})();
