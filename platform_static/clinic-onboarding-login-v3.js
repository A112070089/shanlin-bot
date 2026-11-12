'use strict';
const el = id => document.getElementById(id);
const slug = new URLSearchParams(location.search).get('clinic') || '';
if (!/^[a-z][a-z0-9-]{2,31}$/.test(slug)) {el('loginStatus').textContent='請從工程師開通準備頁開啟此測試入口';el('loginBtn').disabled=true;}
el('clinicId').value=slug;
async function req(url, body){const r=await fetch(url,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','Origin':location.origin},body:JSON.stringify(body)});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||('HTTP '+r.status));return d;}
el('loginForm').addEventListener('submit',async e=>{e.preventDefault();el('success').hidden=true;el('loginBtn').disabled=true;el('loginStatus').textContent='正在驗證…';try{const result=await req('/api/pilot/onboarding/login',{clinicId:slug,username:el('username').value.trim(),password:el('password').value});el('password').value='';el('loginStatus').textContent='驗證成功';el('identity').textContent='診所代號：'+result.clinicId+' · 帳號：'+el('username').value;el('success').hidden=false;}catch(error){el('loginStatus').textContent=error.message;}finally{el('loginBtn').disabled=false;}});
