'use strict';
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const API='/api/pilot/platform/console/modules';
let csrf='',catalog=null,editing=null,pending=false,releaseSummaries={};
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
  const active=clinics.filter(c=>c.active && c.kind==='existing');
  const draftCount=clinics.filter(c=>c.kind==='draft' && !c.active).length;
  $('moduleList').innerHTML=catalog.modules.map(m=>{
    const rel=releaseSummaries[m.id];
    const stage=(rel&&({planned:'規劃中',developing:'開發中',testing:'測試中'}[rel.progress]))||(m.stage==='testing'?'測試中':'規劃中');
    const status=m.archived?'模組已停用':m.standardIncluded?'已納入共用標準版':'未納入標準版';
    const deploy=m.deployment==='deployed'?'程式已驗證部署':'尚未部署程式';
    const applied=active.map(c=>c.name).join('、')||'尚無既有診所';
    const btn=m.standardIncluded?'移出標準版':'納入共用標準版';
    const acceptanceLabel={draft:'尚未送驗',submitted:'已送交驗收',approved:'已核准驗收',rejected:'已退回'}[rel?.acceptance]||'尚未送驗';
    return `<article class="module-item ${m.archived?'archived':''}">
      <div class="module-head"><div><h3 class="module-title">${esc(m.name)}</h3><p class="module-id">${esc(m.id)}</p></div>
      <span class="module-tag ${m.archived?'off':''}">${m.archived?'已停用':esc(stage)}</span></div>
      <p>${esc(m.description||'尚無功能說明')}</p>
      <div class="module-meta"><span class="module-tag">規劃版本 ${esc(m.plannedVersion)}</span>
        <span class="module-tag ${m.deployment==='deployed'?'':'wait'}">${esc(deploy)}</span>
        <span class="module-tag">${esc(status)}</span>
        <span class="module-tag">驗收：${esc(acceptanceLabel)}</span></div>
      <div class="module-scope"><strong>適用範圍：全平台同一標準版</strong>
        <div>已建置診所：${esc(applied)}</div>
        <div class="small">所有完成正式開通及驗收的合作診所自動使用相同功能；Demo 僅供預覽。${draftCount?' 已封存草稿 '+draftCount+' 家不提供服務。':''}</div>
        <div class="module-caption">${m.standardIncluded && !m.archived ? '此模組已納入產品規劃，但須部署程式並完成診所驗收才可實際使用。' : '目前未開放此模組。'}</div>
      </div>
      <div class="module-actions">
        <button type="button" class="module-plan-btn ${m.standardIncluded?'outline':''}" data-standard="${esc(m.id)}" ${m.archived?'disabled':''}>${esc(btn)}</button>
        <a class="module-release-link" href="/platform/modules/${encodeURIComponent(m.id)}/release">部署／驗收 →</a>
        ${m.id === 'appointment_reminders' ? '<a class="module-release-link" href="/platform/modules/appointment_reminders/line-status">既有 LINE Bot 狀態 →</a>' : ''}
        <button type="button" class="outline" data-edit="${esc(m.id)}">編輯模組</button>
        <button type="button" class="${m.archived?'outline':'danger-outline'}" data-lifecycle="${esc(m.id)}">${m.archived?'恢復模組':'停用模組'}</button>
      </div>
    </article>`;
  }).join('')||'<div class="card">還沒有建立任何功能模組。</div>';
  document.querySelectorAll('#moduleList [data-standard]').forEach(el=>el.addEventListener('click',()=>toggleStandard(el.dataset.standard)));
  document.querySelectorAll('#moduleList [data-edit]').forEach(el=>el.addEventListener('click',()=>editModule(el.dataset.edit)));
  document.querySelectorAll('#moduleList [data-lifecycle]').forEach(el=>el.addEventListener('click',()=>toggleLifecycle(el.dataset.lifecycle)));
  renderHistorical();
}
function renderHistorical(){
  const report=catalog.historicalCheck;
  if(!report){$('moduleMigration').textContent='無歷史紀錄可核對。';return;}
  const diff=report.differences||[];
  const msg=diff.length ? `發現 ${diff.length} 筆 v1 與 v3.2 的舊勾選差異，已停止採用個別診所授權。` : '舊版 v1 與 v3.2 的內建模組勾選一致，個別診所勾選已停止採用。';
  $('moduleMigration').innerHTML=`<p class="module-caption">${esc(msg)} 新版標準版開關預設不沿用舊勾選，需由工程師明確選擇。</p>`+
    (diff.length?`<details><summary>查看舊版差異（僅供核對，不自動修改）</summary><ul>`+
      diff.map(d=>`<li>${esc(d.clinicName)} / ${esc(d.moduleId)}：舊總控台 ${d.v1?'勾選':'未勾選'}、v3.2 ${d.v32?'勾選':'未勾選'}</li>`).join('')+
      `</ul><p class="module-caption">歷史差異不一定是程式錯配，也可能來自你之後自行變更。</p></details>`:'');
}
async function audit(){
  const data=await request(API+'/audit');
  $('moduleAudit').innerHTML=data.entries.length?data.entries.map(x=>`<div>${esc(x.timestamp)} · ${esc(x.actor)} · ${esc(x.action)} · ${esc(x.moduleId||'')}${x.clinicId?' / '+esc(x.clinicId):''}</div>`).join(''):'尚無模組操作紀錄';
}
async function reload(){
  catalog=await request(API);
  try{const overview=await request('/api/pilot/platform/console/releases');releaseSummaries=Object.fromEntries(overview.releases.map(x=>[x.moduleId,x]));}
  catch(error){releaseSummaries={};}
  render();await audit();
}
async function mutate(path,method,body,message,globalPolicy=false){
  if(pending)return;
  pending=true;info('正在儲存…');
  try{
    const reqbody=globalPolicy?{...body,expectedPolicyRevision:catalog.policyRevision}:{...body,expectedRevision:catalog.revision};
    const result=await updateRequest(path,method,reqbody);
    catalog=result.registry;render();await audit();info(message);
  }catch(error){
    info(error.status===409?'另一個工程師視窗已修改設定；請重新檢查後再操作。':error.message);
    await reload().catch(()=>{});
  }finally{pending=false;}
}
function editModule(mid){
  const row=catalog.modules.find(m=>m.id===mid);if(!row)return;
  editing=mid;$('moduleEditorHeading').textContent='編輯模組：'+row.name;
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
  if(archived&&!confirm('確定停用「'+item.name+'」？將停止全平台提供此模組，但保留標準版設定供日後恢復。'))return;
  await mutate(API+'/'+encodeURIComponent(mid)+'/lifecycle','POST',{archived},archived?'模組已停用，全平台停止提供。':'模組已恢復，但仍須部署與驗收。');
}
async function toggleStandard(mid){
  const item=catalog.modules.find(x=>x.id===mid);if(!item)return;
  const enabled=!item.standardIncluded;
  if(enabled&&!confirm('將「'+item.name+'」納入所有已開通診所的共用標準版？尚未部署程式的功能不會立即上線。'))return;
  if(!enabled&&!confirm('將「'+item.name+'」從全平台標準版移除？此操作影響所有診所。'))return;
  await mutate(API+'/'+encodeURIComponent(mid)+'/standard','POST',{enabled},
    enabled?'已納入全平台標準版；尚未完成部署和診所驗收的功能不會上線。':'已從全平台標準版移除。',true);
}
$('moduleForm').addEventListener('submit',async event=>{
  event.preventDefault();if(pending)return;
  const payload={name:$('modName').value.trim(),description:$('modDescription').value.trim(),
    plannedVersion:$('modVersion').value.trim(),stage:$('modStage').value};
  if(!editing)payload.id=$('modId').value.trim();
  const target=editing?API+'/'+encodeURIComponent(editing):API;
  pending=true;$('moduleSave').disabled=true;info('正在儲存…');
  try{
    const result=await updateRequest(target,editing?'PATCH':'POST',{...payload,expectedRevision:catalog.revision});
    catalog=result.registry;render();await audit();
    $('moduleEditor').hidden=true;editing=null;
    info('模組資料已保存；請依需要按「納入共用標準版」，尚未部署的程式仍不可使用。');
  }catch(error){info(error.status===409?'資料已由另一視窗更新，請重新整理。':error.message);await reload().catch(()=>{});}
  finally{$('moduleSave').disabled=false;pending=false;}
});
$('newModule').addEventListener('click',newModule);
$('moduleCancel').addEventListener('click',()=>{$('moduleEditor').hidden=true;editing=null;});
(async()=>{
  try{
    const session=await request('/api/pilot/platform/console/session');csrf=session.csrf;
    await reload();$('moduleMain').hidden=false;$('moduleContent').hidden=false;
    info('工程師 '+session.username+' 已登入。這裡統一管理所有診所的共用標準版，沒有逐診所勾選。');
  }catch(error){
    if(error.status===401||error.status===403){location.replace('/platform/admin?next=%2Fplatform%2Fmodules');return;}
    $('moduleMain').hidden=false;info('載入共用模組中心失敗：'+error.message);
  }
})();
