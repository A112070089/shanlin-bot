'use strict';
const $ = id => document.getElementById(id);
const safe = value => String(value ?? '');
const STATUS = {verified_local:'已確認本機能力',pending:'尚待驗收',blocked:'尚未整合'};
function elem(tag, text, cls){
  const e = document.createElement(tag);
  if(text !== undefined)e.textContent=safe(text);
  if(cls)e.className=cls;
  return e;
}
function clinicCard(row){
  const card=elem('article');card.className='card';
  card.append(elem('h2',row.clinicName+' · '+(row.role==='demo'?'公版 Demo':'合作診所')));
  card.append(elem('p','正式預約：尚未開放','muted'));
  const link=elem('a','開啟原有診所管理入口 →');link.href=row.adminUrl;
  card.append(link);
  const list=elem('ul');
  for(const check of row.checks){
    const item=elem('li');
    item.append(elem('strong',check.label+'：'+(STATUS[check.status]||'待核對')));
    item.append(elem('p',check.detail,'muted'));
    list.append(item);
  }
  card.append(list);return card;
}
async function init(){
  const out=$('status');
  try{
    const r=await fetch('/api/pilot/platform/operations/v36/summary',{credentials:'same-origin',cache:'no-store'});
    if(r.status===401||r.status===403){out.textContent='請先登入工程師總控台，再開啟此頁。';return;}
    if(!r.ok)throw new Error('無法取得整合驗收資訊（HTTP '+r.status+'）');
    const state=await r.json();
    if(state.productionReady !== false || !Array.isArray(state.clinics))throw new Error('驗收格式不相容，已停止展示');
    out.textContent='本機整合清單已載入；目前不是正式營運驗收通過。';
    const root=$('clinics');root.replaceChildren(...state.clinics.map(clinicCard));
  }catch(err){out.textContent=err.message||'無法讀取整合驗收狀態';}
}
init();
