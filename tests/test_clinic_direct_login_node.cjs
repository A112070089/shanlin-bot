'use strict';
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
const root = path.resolve(__dirname, '..', 'website', 'platform_static');
const tick = () => new Promise(resolve => setImmediate(resolve));
function createDom() {
  const nodes = new Map();
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {
      hidden: id === 'clinicCenterMain' || id === 'content',
      value: '', textContent: '', innerHTML: '', disabled: false,
      listeners: {},
      addEventListener(type, fn) { this.listeners[type] = fn; },
      querySelector() { return {disabled:false}; },
      querySelectorAll() { return []; },
      reset() {}, scrollIntoView() {}, append() {},
    });
    return nodes.get(id);
  }
  return { node, document: {getElementById: node,querySelectorAll:()=>[]} };
}
function response(ok, status, object) {
  return {ok,status,json:async()=>object};
}
async function runClinicSignedOut() {
  const {node,document}=createDom();
  let redirected = '';
  const sandbox={document,console,URLSearchParams,
    location:{search:'',replace:(to)=>{redirected=to;}},
    fetch:async()=>response(false,401,{detail:'需登入'})};
  vm.runInNewContext(fs.readFileSync(path.join(root,'clinic-center.js'),'utf8'),sandbox);
  await tick(); await tick();
  assert.equal(redirected,'/platform/admin?next=%2Fplatform%2Fclinics');
  assert.equal(node('clinicCenterMain').hidden,true);
  console.log('PASS: signed-out clinic center redirects to login without intermediary');
}
async function runEngineerLogin(returnPath, alreadyAuthed=false) {
  const {node,document}=createDom();
  let redirected='';
  const sandbox={document,console,URLSearchParams,
    location:{search:returnPath?`?next=${encodeURIComponent(returnPath)}`:'',replace:(to)=>{redirected=to;}},
    fetch:async(url)=>{
      if(url==='/api/pilot/platform/console/session')return response(alreadyAuthed,alreadyAuthed?200:401,alreadyAuthed?{csrf:'test'}:{detail:'未登入'});
      if(url==='/platform/api/bootstrap')return response(true,200,{accountConfigured:true});
      if(url==='/api/pilot/platform/login')return response(true,200,{csrf:'test'});
      if(url==='/api/pilot/platform/console/state')return response(true,200,{policy:{revision:'0',features:[],flags:{yidian:{},shanlin:{}}},clinics:[]});
      if(url==='/api/pilot/platform/console/health')return response(true,200,{services:[]});
      if(url==='/api/pilot/platform/console/audit')return response(true,200,{entries:[]});
      throw Error('Unexpected fetch '+url);
    }};
  vm.runInNewContext(fs.readFileSync(path.join(root,'platform.js'),'utf8'),sandbox);
  await tick(); await tick();
  if(alreadyAuthed)return {redirected, node};
  assert.equal(node('login').hidden,false);
  const ev={preventDefault(){},target:{querySelector(){return {disabled:false};}}};
  await node('loginForm').listeners.submit(ev);
  return {redirected,node};
}
(async()=>{
  await runClinicSignedOut();
  assert.equal((await runEngineerLogin('/platform/clinics')).redirected,'/platform/clinics');
  console.log('PASS: successful engineer login returns to clinic center');
  assert.equal((await runEngineerLogin('/platform/clinics',true)).redirected,'/platform/clinics');
  console.log('PASS: existing engineer session bypasses login');
  const openRedirect=(await runEngineerLogin('https://untrusted.example')).redirected;
  assert.equal(openRedirect,'');
  console.log('PASS: external next URL cannot trigger open redirect');
  assert.equal((await runEngineerLogin('')).redirected,'');
  console.log('PASS: regular /platform/admin remains on engineering dashboard');
})().catch(e=>{console.error(e);process.exitCode=1;});
