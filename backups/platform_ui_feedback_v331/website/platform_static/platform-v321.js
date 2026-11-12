'use strict';
const $ = id => document.getElementById(id);
const esc = t => String(t ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const requested = new URLSearchParams(location.search).get('next');
const AFTER_LOGIN = ['/platform/clinics','/platform/modules'].includes(requested) ? requested : '';
const BASE = '/api/pilot/platform/console';
let csrf = '';
async function req(path, options={}){
  const response = await fetch(path,{credentials:'same-origin',cache:'no-store',...options});
  const result = await response.json().catch(()=>({}));
  if(!response.ok){const err=new Error(result.detail||'HTTP '+response.status);err.status=response.status;throw err;}
  return result;
}
function showDashboard(value){$('login').hidden=value;$('dashboard').hidden=!value;$('logout').hidden=!value;}
async function loadDashboard(){
  const [state,modules,health,audit]=await Promise.all([
    req(BASE+'/state'),req(BASE+'/modules'),req(BASE+'/health'),req(BASE+'/modules/audit')]);
  $('clinics').innerHTML=state.clinics.map(c=>`<article class="card"><h3>${esc(c.name)}</h3><span class="pill">${esc(c.role)}</span><p>公版儲存模式：${esc(c.pilotStorageMode)}</p><p>正式預約：尚未開放</p><a href="${esc(c.adminUrl)}">開啟診所後台</a></article>`).join('');
  $('features').innerHTML=modules.modules.map(m=>`<div class="feature-summary"><div><b>${esc(m.name)}</b><small class="muted">${esc(m.id)} · 規劃版本 ${esc(m.plannedVersion)} · ${m.archived?'已停用':m.stage==='testing'?'測試中':'規劃中'} · ${m.standardIncluded?'標準版包含':'未納入標準版'}</small></div><span class="module-tag ${m.deployment==='deployed'?'':'wait'}">${m.deployment==='deployed'?'已驗證部署':'尚未部署'}</span></div>`).join('')||'尚無模組';
  $('health').innerHTML=health.services.map(s=>`<div class="status"><b>${esc(s.name)}</b>（${esc(s.port)}） <span class="${s.state==='ready'?'good':'bad'}">${esc(s.state)}</span></div>`).join('');
  $('audit').innerHTML=audit.entries.length?audit.entries.slice(0,20).map(a=>`<div>${esc(a.timestamp)} · ${esc(a.actor)} · ${esc(a.action)} · ${esc(a.moduleId||'')}</div>`).join(''):'尚無模組操作紀錄';
}
async function init(){
  try{
    const s=await req(BASE+'/session');csrf=s.csrf;
    if(AFTER_LOGIN){location.replace(AFTER_LOGIN);return;}
    showDashboard(true);await loadDashboard();
  }catch(err){
    if(err.status!==401 && err.status!==403){$('dashboardMessage').textContent=err.message;}
    showDashboard(false);
    try{const b=await req('/platform/api/bootstrap');$('accountHint').textContent=b.accountConfigured?'使用既有工程師帳號登入。':'尚未建立工程師帳號，請先由 Terminal 設定。';}catch{}
  }
}
$('loginForm').addEventListener('submit',async e=>{
  e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;
  $('loginMessage').textContent='正在驗證工程師身分…';
  try{
    const s=await req('/api/pilot/platform/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('username').value.trim(),password:$('password').value})});
    csrf=s.csrf;$('password').value='';$('loginMessage').textContent='';
    if(AFTER_LOGIN){location.replace(AFTER_LOGIN);return;}
    showDashboard(true);await loadDashboard();
  }catch(error){$('loginMessage').textContent=error.message;}finally{button.disabled=false;}
});
$('logout').addEventListener('click',async()=>{
  try{await req('/api/pilot/admin/logout',{method:'POST',headers:{'X-Pilot-CSRF':csrf,'Origin':location.origin}});}catch{}
  csrf='';showDashboard(false);
});
init();
