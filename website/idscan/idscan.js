/* DOUBTS-IDSCAN-V1 | ID-front OCR with same-origin, locally hosted Tesseract. */
(function() {
  'use strict';
  const scriptURL = document.currentScript && document.currentScript.src;
  const base = scriptURL ? new URL('.', scriptURL).href : new URL('idscan/', document.baseURI).href;
  const Core = window.DoubtsIdScanCore;
  let modal=null, input=null, previewUrl=null, worker=null, running=false, jobId=0, previousFocus=null, mode='chat';
  const $ = sel => modal && modal.querySelector(sel);
  const q = sel => document.querySelector(sel);
  if (!Core) return;
  // This patch is strictly for the local Mac / private-LAN demonstration.
  const host=location.hostname;
  if (host && !(/^localhost$|^127\.0\.0\.1$|^192\.168\.\d+|^10\.\d+|^172\.(1[6-9]|2\d|3[01])\./.test(host))) return;
  function el(tag,attr={},text='') {
    const x=document.createElement(tag);
    for(const [key,val] of Object.entries(attr)) {
      if(key==='className') x.className=val;
      else if(key==='type') x.type=val;
      else x.setAttribute(key,val);
    }
    if(text) x.textContent=text;
    return x;
  }
  function setup() {
    if(modal) return;
    modal=el('div',{id:'doubts-idscan-root',role:'presentation'});
    modal.innerHTML=`
      <section class="ids-panel" role="dialog" aria-modal="true" aria-labelledby="ids-title" aria-describedby="ids-desc">
        <header class="ids-top"><strong id="ids-title">📷 拍身分證，快速填資料</strong><button class="ids-x" type="button" id="ids-close" aria-label="關閉掃描">×</button></header>
        <div class="ids-body">
          <p id="ids-desc">拍攝<strong>身分證正面</strong>，系統會辨識姓名、證號與出生日期。資料一定要經過您確認才會填入預約。</p>
          <div class="ids-privacy">🔒 照片只在這個瀏覽器內辨識，不會上傳到外部 OCR 服務。系統不儲存原始證件照片。請勿拍攝他人的證件，除非已取得本人同意。</div>
          <div class="ids-start" id="ids-start">
            <label class="ids-check" for="ids-consent"><input id="ids-consent" type="checkbox"> <span>我已了解拍照用途，並同意使用本次照片辨識資料。</span></label>
            <div class="ids-actions"><button type="button" id="ids-pick" class="ids-primary">📷 拍攝身分證正面</button><button type="button" id="ids-manual">不用拍照，返回輸入</button></div>
            <p class="ids-help">建議在光線充足的地方橫向拍攝，讓證件四角都在畫面中。部分手機也可選擇相簿照片。</p>
          </div>
          <div class="ids-photo" id="ids-photo" hidden></div>
          <div class="ids-status" id="ids-status" role="status" aria-live="polite"></div>
          <p class="ids-error" id="ids-error" role="alert" hidden></p>
          <div id="ids-fields" class="ids-fields" hidden>
            <p><strong>請確認辨識結果</strong>（若有錯字，請直接修改）</p>
            <div><label for="ids-name">姓名</label><input id="ids-name" autocomplete="off" maxlength="12" placeholder="例如：王小明"></div>
            <div><label for="ids-pid">身分證字號</label><input id="ids-pid" autocomplete="off" spellcheck="false" maxlength="12" placeholder="例如：A123456789" autocapitalize="characters"><span class="ids-help">請核對全部 10 碼，系統會檢查格式及檢查碼。</span></div>
            <div><label for="ids-birth">出生日期（民國年）</label><input id="ids-birth" inputmode="numeric" autocomplete="off" placeholder="例如：450101"><span class="ids-help">民國 45 年 1 月 1 日請填 450101。</span></div>
            <label class="ids-check" for="ids-verified"><input id="ids-verified" type="checkbox"><span>我已核對以上三項資料，確認正確。</span></label>
            <div class="ids-actions"><button type="button" id="ids-retry">↻ 重新拍攝</button><button type="button" id="ids-apply" class="ids-primary">確認並帶入預約</button></div>
          </div>
        </div>
      </section>
      <input id="ids-file" type="file" accept="image/jpeg,image/png,image/webp,image/*" capture="environment" style="display:none" aria-label="選取身分證正面照片">`;
    document.body.appendChild(modal);
    input=$('#ids-file');
    $('#ids-close').addEventListener('click',close);
    $('#ids-manual').addEventListener('click',close);
    $('#ids-pick').addEventListener('click',()=>{
      if(!$('#ids-consent').checked) return error('請先勾選同意拍照辨識，再開始拍攝。');
      error('');input.value='';input.click();
    });
    input.addEventListener('change',()=>{if(input.files && input.files[0]) void recognize(input.files[0]);});
    $('#ids-retry').addEventListener('click',()=>{ reset(); if($('#ids-consent').checked){input.value='';input.click();}});
    $('#ids-apply').addEventListener('click',apply);
    for(const id of ['ids-name','ids-pid','ids-birth']) $("#"+id).addEventListener('input',()=>{
      $('#ids-verified').checked=false;error('');
    });
    modal.addEventListener('click', e=>{if(e.target===modal)close();});
    modal.addEventListener('keydown', e=>{
      if(e.key==='Escape') {e.preventDefault();close();}
      if(e.key==='Tab') {const xs=[...modal.querySelectorAll('button:not(:disabled),input:not(:disabled)')].filter(x=>x.offsetParent!==null);if(!xs.length)return;const fst=xs[0],lst=xs[xs.length-1];if(e.shiftKey && document.activeElement===fst){e.preventDefault();lst.focus();} else if(!e.shiftKey && document.activeElement===lst){e.preventDefault();fst.focus();}}
    });
  }
  function error(s){if(!modal)return;const x=$('#ids-error');x.textContent=s||'';x.hidden=!s;}
  function status(s){if(modal)$('#ids-status').textContent=s||'';}
  function reset() {
    if(!modal)return;
    jobId++;running=false;
    if(input)input.value='';
    if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl=null;}
    const ph=$('#ids-photo');ph.replaceChildren();ph.hidden=true;
    $('#ids-fields').hidden=true;
    $('#ids-start').hidden=false;
    $('#ids-verified').checked=false;
    ['ids-name','ids-pid','ids-birth'].forEach(k=>$('#'+k).value='');
    status('');error('');
  }
  function open(which) {
    setup();mode=which;previousFocus=document.activeElement;
    reset();$('#ids-consent').checked=false;
    modal.classList.add('is-open');
    $('#ids-close').focus();
  }
  function close() {
    if(!modal)return;
    jobId++;modal.classList.remove('is-open');
    reset();
    if(worker){const active=worker;worker=null;Promise.resolve(active.terminate()).catch(()=>{});}
    if(previousFocus && previousFocus.isConnected)previousFocus.focus();
  }
  async function canvasFromPhoto(file) {
    if(file.size>12*1024*1024) throw new Error('圖片超過 12MB，請重新拍攝較小的照片。');
    if(!/^image\/(jpeg|png|webp|heic|heif)$/i.test(file.type)) throw new Error('請選擇手機拍攝的照片（JPG、PNG 或 WEBP）。');
    const url=URL.createObjectURL(file);
    const im=new Image();
    try{
      await new Promise((resolve,reject)=>{im.onload=resolve;im.onerror=()=>reject(new Error('照片無法開啟，請改用 JPG 或 PNG 再試。'));im.src=url;});
      if(!im.naturalWidth || !im.naturalHeight)throw new Error('無法讀取照片尺寸。');
      const scale=Math.min(1,2300/Math.max(im.naturalWidth,im.naturalHeight));
      const canvas=document.createElement('canvas');canvas.width=Math.round(im.naturalWidth*scale);canvas.height=Math.round(im.naturalHeight*scale);
      const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(im,0,0,canvas.width,canvas.height);
      const pixels=ctx.getImageData(0,0,canvas.width,canvas.height),p=pixels.data;
      for(let i=0;i<p.length;i+=4){for(let c=0;c<3;c++){p[i+c]=Math.max(0,Math.min(255,128+(p[i+c]-128)*1.20));}}
      ctx.putImageData(pixels,0,0);
      return {canvas,url};
    }catch(e){URL.revokeObjectURL(url);throw e;}
  }
  async function recognize(file){
    if(running) return;
    if(!window.Tesseract || !window.Tesseract.createWorker)return error('本機 OCR 程式尚未載入，請重新整理頁面或檢查安裝。');
    const token=++jobId;running=true;$('#ids-fields').hidden=true;$('#ids-start').hidden=true;
    error('');status('正在準備辨識照片，請稍候…');
    let image=null, currentWorker=null;
    try{
      image=await canvasFromPhoto(file);
      if(jobId!==token)return;
      previewUrl=image.url;$('#ids-photo').hidden=false;
      const img=el('img',{alt:'您選擇的證件照片預覽'});img.src=previewUrl;$('#ids-photo').replaceChildren(img);
      // All OCR program assets and language data are served from the same DOUBTS origin.
      currentWorker=await window.Tesseract.createWorker(['chi_tra','eng'],1,{
        workerPath:base+'vendor/worker.min.js', corePath:base+'vendor/core', langPath:base+'vendor/lang',
        workerBlobURL:false,cacheMethod:'none',logger:m=>{if(jobId===token && m && m.status)status('本機辨識中：'+({'loading tesseract core':'載入辨識核心','loading language traineddata':'載入中文字庫','initializing api':'初始化','recognizing text':'辨識文字'}[m.status]||'處理影像')+(typeof m.progress==='number'?' '+Math.round(m.progress*100)+'%':''));}
      });
      worker=currentWorker;
      if(jobId!==token)return;
      const res=await currentWorker.recognize(image.canvas);
      if(jobId!==token)return;
      const data=Core.parse(res.data && res.data.text||'');
      $('#ids-name').value=data.name;
      $('#ids-pid').value=data.pid;
      $('#ids-birth').value=data.birthday;
      $('#ids-fields').hidden=false;
      status('✅ 辨識結束。請核對姓名、證號與生日；看不清楚的欄位可重新拍攝。');
      if(!data.name || !data.pid || !data.birthday) error('部分資料未能可靠辨識。請檢查證件照片，或修正空白欄位。'+(data.idAmbiguous?' 偵測到不只一組證號，需人工核對。':''));
      $('#ids-name').focus();
      // The recognized text is intentionally neither logged nor persisted.
      image.canvas.width=1;image.canvas.height=1;
    }catch(err){
      if(jobId===token){status('');error(err && err.message ? err.message : '照片辨識失敗，請重新拍攝。');$('#ids-start').hidden=false;}
    }finally{
      if(jobId===token) running=false;
      if(currentWorker){try{await currentWorker.terminate();}catch(_){/* ignore */} if(worker===currentWorker)worker=null;}
      if(image && image.url && previewUrl!==image.url)URL.revokeObjectURL(image.url);
    }
  }
  function setInputValue(inp,val){if(!inp)return;inp.value=val;inp.dispatchEvent(new Event('input',{bubbles:true}));inp.dispatchEvent(new Event('change',{bubbles:true}));}
  function applyToForm(data){
    const form=q('#bookingForm');if(!form)return false;
    const fields={name:form.querySelector('[name="name"]'),pid:form.querySelector('[name="pid"]'),birthday:form.querySelector('[name="birthday"]')};
    if(!fields.name||!fields.pid||!fields.birthday)return false;
    const p=Core.dateParts(data.birthday); if(!p)return false;
    const pickerYear=q('#shanlin-dob-year'),pickerMonth=q('#shanlin-dob-month'),pickerDay=q('#shanlin-dob-day');
    if(pickerYear&&pickerMonth&&pickerDay){
      if(![...pickerYear.options].some(o=>o.value===String(p.year))){error('日期超出目前預約頁面的選擇範圍，請改用手動填表。');return false;}
      pickerYear.value=String(p.year);pickerYear.dispatchEvent(new Event('change',{bubbles:true}));
      pickerMonth.value=String(p.month);pickerMonth.dispatchEvent(new Event('change',{bubbles:true}));
      pickerDay.value=String(p.day);pickerDay.dispatchEvent(new Event('change',{bubbles:true}));
    } else setInputValue(fields.birthday,data.birthday);
    setInputValue(fields.name,data.name);setInputValue(fields.pid,data.pid);
    const ph=form.querySelector('[name="phone"]');if(ph)ph.focus();
    return true;
  }
  function apply(){
    if(running)return;
    const data={name:$('#ids-name').value.trim().replace(/\s/g,''),pid:$('#ids-pid').value.trim().toUpperCase().replace(/[\s-]/g,''),birthday:$('#ids-birth').value.trim().replace(/\s/g,'')};
    if(!Core.validName(data.name))return error('姓名需為 2 至 6 個中文字，請逐字確認。');
    if(!Core.validId(data.pid))return error('身分證字號格式或檢查碼不正確，請重新核對。');
    const age=Core.ageFromRoc(data.birthday);
    if(age===null)return error('出生日期不正確，請輸入民國年月日，例如 450101。');
    if(age<65 && mode==='chat' && window.DoubtsIdScanFlow?.isElderly?.())return error('此高齡健檢流程限滿 65 歲。請確認生日，或改選合適方案。');
    if(!$('#ids-verified').checked)return error('請先確認三項資料都正確，並勾選已核對。');
    let ok=false;
    try{ok=mode==='chat' ? !!(window.DoubtsIdScanFlow && window.DoubtsIdScanFlow.accept(data)) : applyToForm(data);}catch(_){ok=false;}
    if(!ok)return error('目前預約步驟已改變，請返回姓名步驟再重新操作。');
    close();
  }
  function newEntry(){const b=el('button',{type:'button',className:'doubts-idscan-entry','data-idscan-version':'1'});b.append(document.createTextNode('📷 拍身分證，快速填寫'));const sm=el('span',{className:'ids-sub'},'不想打字？拍照辨識後再確認');b.append(sm);return b;}
  function setupForm(){
    const form=q('#bookingForm');if(!form || q('#doubts-idscan-form-entry'))return;
    const b=newEntry();b.id='doubts-idscan-form-entry';b.addEventListener('click',()=>open('form'));
    form.insertBefore(b,form.firstElementChild);
  }
  let scheduled=false;
  function setupChat(){
    const body=q('#chat-body');if(!body)return;
    function sync(){
      scheduled=false;
      const flow=window.DoubtsIdScanFlow;
      const old=body.querySelector('.doubts-idscan-entry');
      if(!flow || !flow.canScan || !flow.canScan()) {if(old)old.remove();return;}
      const ai=[...body.querySelectorAll('.ai-msg')];const last=ai[ai.length-1];
      if(!last || !/姓名|大名/.test(last.textContent||'')) {if(old)old.remove();return;}
      if(old && old.parentElement===last)return;
      if(old)old.remove();
      const b=newEntry();b.addEventListener('click',()=>open('chat'));last.appendChild(b);
    }
    const schedule=()=>{if(!scheduled){scheduled=true;requestAnimationFrame(sync);}};
    new MutationObserver(schedule).observe(body,{childList:true,subtree:true});
    schedule();
  }
  function start(){setup();setupForm();setupChat();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  window.DoubtsIdScan = {open,close};
})();
