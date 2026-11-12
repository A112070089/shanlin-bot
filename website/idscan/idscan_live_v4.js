/* DOUBTS LiveScan V2: automatic local OCR, no shutter, preview fields before booking. */
/* DOUBTS LiveScan V4: preserve fields, diagnose capture, prevent endless retry. */
(function () {
  'use strict';
  const Core = window.DoubtsIdScanCore;
  const existing = window.DoubtsIdScan;
  const script = document.currentScript;
  if (!Core || !existing || typeof existing.open !== 'function' || !script || !script.src) return;
  const h = location.hostname;
  // Limited to the already authorized private/local testing site. Do not expose as a public service.
  if (!(/^(localhost|127\.0\.0\.1)$/.test(h) || /^192\.168\.\d+\.\d+$/.test(h) || /^10\.\d+\.\d+\.\d+$/.test(h) || /^172\.(1[6-9]|2\d|3[01])\.\d+\.\d+$/.test(h))) return;
  if (window.__DOUBTS_LIVE_SCAN_V2__) return;
  window.__DOUBTS_LIVE_SCAN_V2__ = true;
  const base = new URL('.', script.src).href;
  const fallbackOpen = existing.open.bind(existing);
  const fallbackClose = typeof existing.close === 'function' ? existing.close.bind(existing) : null;
  const $ = id => document.getElementById('dls2-' + id);
  const valid = d => Core.validName(d.name) && Core.validId(d.pid) && !!Core.dateParts(d.birthday);
  let root = null, token = 0, videoStream = null, worker = null, workerLoading = null, timer = null;
  let active = false, busy = false, finished = false, mode = 'chat', priorFocus = null;
  let lastAttempt = 0, attempts = 0, lastFrame = null, steady = 0;
  // A short, rolling burst finds the clearest image even when the hand shakes.
  // Never keep the image beyond the current OCR attempt.
  let bestShot = null, bestScore = -1, burstStarted = 0, bestParsed = null, emptyBursts = 0;
  let recognizedChars=0,captureSize="",conflicts=new Set();
  const MAX_TRIES = 2, BURST_MS = 1150, SAMPLE_MS = 170;
  let seen = {name:'', pid:'', birthday:''};
  const tpl = `
    <section class="dls2-panel" role="dialog" aria-modal="true" aria-labelledby="dls2-title">
      <header class="dls2-head">
        <span><strong id="dls2-title">掃描身分證，自動填寫</strong> <small class="dls2-version">V4</small></span>
        <button id="dls2-close" class="dls2-close" type="button" aria-label="關閉掃描">×</button>
      </header>
      <div class="dls2-body">
        <p class="dls2-privacy">將<strong>虛構證件正面</strong>對準框線；只在這個瀏覽器內辨識影像，不上傳到外部 OCR 服務，也不保存原始照片。</p>
        <div class="dls2-view" id="dls2-view">
          <video id="dls2-video" autoplay muted playsinline aria-label="即時相機預覽"></video>
          <div class="dls2-outline" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
          <div class="dls2-view-caption">請把證件放在框線內，系統會自動選出清楚的畫面</div>
        </div>
        <p id="dls2-status" class="dls2-status" role="status" aria-live="polite">開啟相機中…</p>
        <p id="dls2-diagnostics" class="dls2-diagnostics" aria-live="polite"></p>
        <div id="dls2-fields" class="dls2-fields">
          <label>姓名<input id="dls2-name" type="text" autocomplete="off" placeholder="辨識後自動填入" readonly></label>
          <label>身分證字號<input id="dls2-pid" type="text" autocomplete="off" autocapitalize="characters" placeholder="辨識後自動填入" readonly></label>
          <label>出生日期（民國年）<input id="dls2-birthday" type="text" autocomplete="off" inputmode="numeric" placeholder="辨識後自動填入" readonly></label>
          <label class="dls2-consent"><input type="checkbox" id="dls2-confirm-check" disabled>我已逐字核對以上姓名、證號和生日，確認正確</label>
          <p id="dls2-error" class="dls2-error" role="alert" hidden></p>
          <button type="button" id="dls2-apply" class="dls2-primary" disabled>確認並帶入預約</button>
        </div>
        <div class="dls2-actions">
          <button type="button" id="dls2-retry" hidden>重新掃描</button>
          <button type="button" id="dls2-fallback">改用原本拍照／相簿</button>
          <button type="button" id="dls2-manual">返回打字／語音輸入</button>
        </div>
        <p class="dls2-notice">掃描時不必按快門，也不必一直拿穩。系統會自動挑選清晰畫面；如果資料不完整，最多嘗試兩次後會提供欄位供您修正。核對前不會帶入或送出預約。</p>
      </div>
    </section>`;
  const styleText = `
    #doubts-livescan-v2{position:fixed;inset:0;z-index:2147483100;display:none;align-items:center;justify-content:center;background:#102a3ac7;padding:8px;box-sizing:border-box;font-family:system-ui,-apple-system,'PingFang TC','Noto Sans TC',sans-serif}
    #doubts-livescan-v2.is-open{display:flex}#doubts-livescan-v2 *{box-sizing:border-box}
    #doubts-livescan-v2 .dls2-panel{width:min(100%,570px);max-height:calc(100dvh - 16px);overflow-y:auto;overscroll-behavior:contain;background:#f8fbfd;color:#193b50;border-radius:18px;box-shadow:0 18px 58px #0005}
    #doubts-livescan-v2 .dls2-head{display:flex;align-items:center;justify-content:space-between;gap:12px;background:#8ba8ba;padding:12px 16px}
    #doubts-livescan-v2 .dls2-head strong{font-size:23px;line-height:1.4}
    #doubts-livescan-v2 .dls2-version{font-size:14px;font-weight:700;padding:2px 6px;color:#27485b;border:1px solid #40687b;border-radius:5px}
    #doubts-livescan-v2 button{font:700 18px/1.4 inherit;border:2px solid #9fc0d1;background:white;color:#25475e;border-radius:12px;padding:11px 14px;min-height:54px;cursor:pointer}
    #doubts-livescan-v2 button:disabled{opacity:.53;cursor:not-allowed}
    #doubts-livescan-v2 .dls2-close{font-size:28px;min-width:48px;min-height:48px;padding:0}
    #doubts-livescan-v2 .dls2-body{display:grid;gap:12px;padding:16px}
    #doubts-livescan-v2 .dls2-privacy{font-size:17px;line-height:1.5;margin:0}
    #doubts-livescan-v2 .dls2-view{position:relative;border-radius:14px;overflow:hidden;background:#122b3c;aspect-ratio:1.48}
    #doubts-livescan-v2 .dls2-view video{display:block;width:100%;height:100%;object-fit:cover}
    #doubts-livescan-v2 .dls2-outline{position:absolute;inset:14%;border:2px solid #ddfff2;border-radius:13px;box-shadow:0 0 0 70px #06192577;pointer-events:none}
    #doubts-livescan-v2 .dls2-outline i{position:absolute;width:30px;height:30px;border-color:#7ee9bd;border-style:solid;border-width:0}
    #doubts-livescan-v2 .dls2-outline i:nth-child(1){left:-3px;top:-3px;border-left-width:5px;border-top-width:5px;border-top-left-radius:9px}
    #doubts-livescan-v2 .dls2-outline i:nth-child(2){right:-3px;top:-3px;border-right-width:5px;border-top-width:5px;border-top-right-radius:9px}
    #doubts-livescan-v2 .dls2-outline i:nth-child(3){left:-3px;bottom:-3px;border-left-width:5px;border-bottom-width:5px;border-bottom-left-radius:9px}
    #doubts-livescan-v2 .dls2-outline i:nth-child(4){right:-3px;bottom:-3px;border-right-width:5px;border-bottom-width:5px;border-bottom-right-radius:9px}
    #doubts-livescan-v2 .dls2-view-caption{position:absolute;left:8px;right:8px;bottom:8px;padding:6px 8px;text-align:center;color:white;background:#123446d9;font-size:15px;border-radius:8px}
    #doubts-livescan-v2 .dls2-status{margin:0;border-radius:10px;background:#e5f2f8;padding:12px;font-size:17px;font-weight:650;line-height:1.5}
    #doubts-livescan-v2 .dls2-diagnostics{margin:0;line-height:1.5;font-size:15px;color:#365c73;overflow-wrap:anywhere}
    #doubts-livescan-v2 .dls2-fields{display:grid;gap:9px}
    #doubts-livescan-v2 .dls2-fields label{font-size:17px;font-weight:700;line-height:1.45}
    #doubts-livescan-v2 input:not([type=checkbox]){display:block;width:100%;min-height:52px;border:2px solid #a5c4d4;border-radius:12px;background:white;padding:10px 12px;font:500 19px/1.4 inherit;color:#163e54;margin-top:4px}
    #doubts-livescan-v2 input[readonly]{background:#eff5f8}
    #doubts-livescan-v2 .dls2-consent{display:flex;align-items:flex-start;gap:10px}
    #doubts-livescan-v2 .dls2-consent input{height:24px;width:24px;flex:none;accent-color:#365c73;margin:2px 0 0}
    #doubts-livescan-v2 .dls2-error{color:#9f2230;font-weight:700;margin:0;font-size:16px}
    #doubts-livescan-v2 .dls2-primary{width:100%;background:#365c73;color:white;border-color:#365c73}
    #doubts-livescan-v2 .dls2-actions{display:flex;flex-wrap:wrap;gap:8px}
    #doubts-livescan-v2 .dls2-actions button{flex:1 1 185px}
    #doubts-livescan-v2 .dls2-notice{font-size:15px;line-height:1.5;color:#375a6d;margin:0}
    #doubts-livescan-v2 :is(button,input):focus-visible{outline:3px solid #d89e30;outline-offset:2px}
    @media(max-width:450px){#doubts-livescan-v2{padding:3px}#doubts-livescan-v2 .dls2-panel{max-height:calc(100dvh - 6px);border-radius:12px}#doubts-livescan-v2 .dls2-body{padding:12px}#doubts-livescan-v2 .dls2-head strong{font-size:20px}#doubts-livescan-v2 .dls2-view{aspect-ratio:1.35}#doubts-livescan-v2 .dls2-privacy{font-size:16px}#doubts-livescan-v2 .dls2-actions button{flex-basis:100%}}`;

  function makeUI() {
    if (root) return;
    const css = document.createElement('style'); css.id = 'doubts-livescan-v2-style'; css.textContent = styleText;
    document.head.appendChild(css);
    root = document.createElement('div'); root.id = 'doubts-livescan-v2'; root.innerHTML = tpl;
    document.body.appendChild(root);
    $('close').addEventListener('click', close);
    $('manual').addEventListener('click', close);
    $('fallback').addEventListener('click', () => { const target = mode; close(); fallbackOpen(target); });
    $('retry').addEventListener('click', () => { void beginCamera(); });
    $('apply').addEventListener('click', apply);
    $('confirm-check').addEventListener('change', () => { $('apply').disabled = !finished || !$('confirm-check').checked; });
    for (const id of ['name','pid','birthday']) {
      $(id).addEventListener('input', () => {
        $('confirm-check').checked=false;$('apply').disabled=true;
        const candidate={name:$('name').value.replace(/\s/g,''),pid:$('pid').value.toUpperCase().replace(/[\s-]/g,''),birthday:$('birthday').value.replace(/\s/g,'')};
        $('confirm-check').disabled=!finished||!valid(candidate);error('');
      });
    }
    root.addEventListener('click', e => { if (e.target === root) close(); });
    root.addEventListener('keydown', e => {
      if (e.key==='Escape') { e.preventDefault(); close(); }
      if (e.key==='Tab') {
        const elems = [...root.querySelectorAll('button:not(:disabled),input:not(:disabled)')].filter(n => !n.hidden && n.getClientRects().length>0);
        if (!elems.length) return;
        if (e.shiftKey && document.activeElement===elems[0]) {e.preventDefault();elems[elems.length-1].focus();}
        else if(!e.shiftKey && document.activeElement===elems[elems.length-1]) {e.preventDefault();elems[0].focus();}
      }
    });
  }
  function status(message) { if(root) $('status').textContent = message; }
  function error(message) { if(!root) return; $('error').textContent=message||''; $('error').hidden=!message; }
  function resetFields() {
    seen={name:'',pid:'',birthday:''};
    if($('diagnostics'))$('diagnostics').textContent='';
    for(const id of ['name','pid','birthday']) { $(id).value=''; $(id).readOnly=true; }
    $('confirm-check').checked=false; $('confirm-check').disabled=true; $('apply').disabled=true;
    $('retry').hidden=true; $('view').hidden=false; error('');
  }
  function stopTracks(){
    if(videoStream){for(const track of videoStream.getTracks())track.stop();videoStream=null;}
    if(root) { $('video').pause(); $('video').srcObject=null; }
  }
  function cancelScan() {
    token++; active=false; busy=false; clearTimeout(timer);timer=null; stopTracks();lastFrame=null;
    if(bestShot){bestShot.width=1;bestShot.height=1;bestShot=null;}
    bestScore=-1;burstStarted=0;bestParsed=null;emptyBursts=0;workerLoading=null;
    recognizedChars=0;captureSize="";conflicts=new Set();
    if(worker){const dying=worker;worker=null;Promise.resolve(dying.terminate()).catch(()=>{});}
  }
  function close() {
    if(!root)return;
    cancelScan();root.classList.remove('is-open');finished=false;resetFields();
    if(priorFocus?.isConnected)priorFocus.focus({preventScroll:true});
  }
  function open(which){
    mode=which==='form'?'form':'chat'; priorFocus=document.activeElement; makeUI();
    cancelScan();finished=false; resetFields(); root.classList.add('is-open');
    $('close').focus({preventScroll:true});
    // Called during the initial user tap, so mobile browsers can prompt for permission.
    void beginCamera();
  }
  async function beginCamera() {
    cancelScan();finished=false;resetFields();const id=token;active=true;attempts=0;steady=0;lastAttempt=0;
    status('正在開啟相機…');
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      active=false; status('即時掃描需 localhost 或受信任的 HTTPS。此環境可改用原本的拍照方式。');
      $('retry').hidden=false; return;
    }
    try {
      const s = await navigator.mediaDevices.getUserMedia({audio:false, video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}}});
      if(token!==id || !active){s.getTracks().forEach(t=>t.stop());return;}
      videoStream=s;$('video').srcObject=s;await $('video').play();
      if(token!==id || !active)return;
      status('請對準證件，無須按快門；正在自動挑選清楚的畫面…');
      // Prepare OCR on the same device while selecting the best image.
      void getWorker(id).catch(()=>{});
      timer=setTimeout(()=>void scanFrame(id),SAMPLE_MS);
    } catch(e){
      if(token!==id)return;
      active=false;stopTracks();status('無法使用相機：'+(e?.name||'權限或裝置問題')+'。可改用原本拍照／相簿。');$('retry').hidden=false;
    }
  }
  // Matches the visible guide even though the video uses object-fit:cover.
  // On the second try, include the full video frame in case an edge was missed.
  function regionFor(v, full) {
    const vw=v.videoWidth, vh=v.videoHeight;
    if(full)return {sx:0,sy:0,sw:vw,sh:vh};
    const box=$('view').getBoundingClientRect();
    if(!box.width||!box.height)return {sx:0,sy:0,sw:vw,sh:vh};
    const scale=Math.max(box.width/vw,box.height/vh);
    const visibleW=box.width/scale,visibleH=box.height/scale;
    const left=(vw-visibleW)/2,top=(vh-visibleH)/2;
    const margin=.035; // avoid clipping fields close to card edges
    return {sx:left+visibleW*margin,sy:top+visibleH*margin,
            sw:visibleW*(1-2*margin),sh:visibleH*(1-2*margin)};
  }
  function sampleSharpFrame(v) {
    const crop=regionFor(v,attempts>0);
    if(crop.sw<40||crop.sh<40)return;
    // Evaluate small frames; never run full-resolution OCR on every video frame.
    const small=document.createElement('canvas');small.width=192;small.height=120;
    const sc=small.getContext('2d',{willReadFrequently:true});
    if(!sc)return;
    sc.drawImage(v,crop.sx,crop.sy,crop.sw,crop.sh,0,0,192,120);
    const px=sc.getImageData(0,0,192,120).data;
    let lum=0,edges=0,samples=0;
    for(let y=2;y<118;y+=4) for(let x=2;x<188;x+=4){
      const i=4*(y*192+x),j=4*(y*192+x+2);
      const a=(px[i]*3+px[i+1]*6+px[i+2])/10;
      const b=(px[j]*3+px[j+1]*6+px[j+2])/10;
      lum+=a;edges+=Math.abs(a-b);samples++;
    }
    small.width=1;small.height=1;
    const brightness=lum/samples,sharpness=edges/samples;
    if(brightness<22||brightness>252||sharpness<1.0)return;
    // Contrast and sharpness favor legible text, not absolute stillness.
    const score=sharpness-0.018*Math.abs(brightness-145);
    if(score<=bestScore)return;
    if(bestShot){bestShot.width=1;bestShot.height=1;}
    const c=document.createElement('canvas');
    const k=Math.min(2.5,2200/Math.max(crop.sw,crop.sh));
    c.width=Math.max(1,Math.round(crop.sw*k));
    c.height=Math.max(1,Math.round(crop.sh*k));
    const ctx=c.getContext('2d',{willReadFrequently:true});
    if(!ctx)return;ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
    // First: enhanced grayscale crop; second: original color and wider view.
    if(attempts===0)ctx.filter='grayscale(1) contrast(1.24)';
    ctx.drawImage(v,crop.sx,crop.sy,crop.sw,crop.sh,0,0,c.width,c.height);
    bestShot=c;bestScore=score;
  }
  // Small recovery rules for OCR inserting spaces into Chinese names or
  // mistaking O/0, I/1 in an ID. Only accept valid Taiwan ID checksums.
  function parseEnhanced(raw) {
    const p=Core.parse(raw);
    const lines=String(raw||'').normalize('NFKC').replace(/\r/g,'').split(/\n/);
    if(!Core.validName(p.name)){
      for(let i=0;i<lines.length;i++){
        if(!/姓\s*名/.test(lines[i]))continue;
        const near=lines.slice(i,i+2).join(' ');
        const segment=near.replace(/^.*?姓\s*名[\s：:]*/,'')
          .split(/身分|證號|性別|出生|統一編號|國民/)[0];
        const name=(segment.replace(/\s/g,'').match(/^\p{Script=Han}{2,6}/u)||[])[0];
        if(Core.validName(name)){p.name=name;break;}
      }
    }
    if(!Core.validId(p.pid)) {
      const compact=String(raw||'').normalize('NFKC').toUpperCase().replace(/\s|[-－]/g,'');
      const candidates=[];
      for(const m of compact.matchAll(/[A-Z][12][0-9OILSBGZQ]{8}/g)){
        const fixed=m[0].slice(0,2)+m[0].slice(2).replace(/[OQ]/g,'0').replace(/[IL]/g,'1').replace(/S/g,'5').replace(/B/g,'8').replace(/G/g,'6').replace(/Z/g,'2');
        if(Core.validId(fixed))candidates.push(fixed);
      }
      const unique=[...new Set(candidates)];
      if(unique.length===1)p.pid=unique[0];
      if(unique.length>1)p.idAmbiguous=true;
    }
    if(!Core.dateParts(p.birthday)) {
      const flat=String(raw||'').normalize('NFKC').replace(/\s+/g,'');
      const m=flat.match(/(?:出生(?:日期|年月日)?|生日)[^\d]{0,12}(?:民國)?(\d{1,4})[.\/-年](\d{1,2})[.\/-月](\d{1,2})/);
      if(m){const year=Number(m[1])>=1912?Number(m[1])-1911:Number(m[1]);
        const v=year+String(+m[2]).padStart(2,'0')+String(+m[3]).padStart(2,'0');
        if(Core.dateParts(v))p.birthday=v;
      }
    }
    return p;
  }
  function formatCandidate(raw) {
    const p=parseEnhanced(raw);
    return {data:{
      name:Core.validName(p.name) && !/^(姓名|國民|出生|日期|證號)$/.test(p.name)?p.name:'',
      pid:Core.validId(p.pid)&&!p.idAmbiguous?p.pid:'',
      birthday:Core.dateParts(p.birthday)?p.birthday:''
    }, ambiguous:!!p.idAmbiguous};
  }
  function countFields(d){return Number(!!d.name)+Number(!!d.pid)+Number(!!d.birthday);}
  function showCandidate(d){for(const k of ['name','pid','birthday'])$(k).value=d[k]||'';}
  function mergeFields(next){
    if(!bestParsed)bestParsed={name:'',pid:'',birthday:''};
    for(const key of ['name','pid','birthday']){
      const value=next[key]||'';
      if(!value||conflicts.has(key))continue;
      if(!bestParsed[key])bestParsed[key]=value;
      else if(bestParsed[key]!==value){bestParsed[key]='';conflicts.add(key);}
    }
  }
  function updateDiagnostics(){
    if(!root)return;
    const n=countFields(bestParsed||{});
    const conflict=conflicts.size?(' / \u8fa8\u8b58\u7d50\u679c\u4e0d\u4e00\u81f4: '+conflicts.size):'';
    // These values never contain recognized personal data or images.
    $('diagnostics').textContent='OCR \u8b58\u5225\u5b57\u5143: '+recognizedChars+
      ' / \u5f71\u50cf\u5c3a\u5bf8: '+(captureSize||'--')+' / \u53ef\u8fa8\u8b58\u6b04\u4f4d: '+n+'/3'+conflict;
  }
  function finishWithReview(d,complete){
    finished=true;active=false;clearTimeout(timer);timer=null;stopTracks();
    $('view').hidden=true;$('retry').hidden=false;
    for(const k of ['name','pid','birthday'])$(k).readOnly=false;
    showCandidate(d);
    const n=countFields(d);updateDiagnostics();
    $('confirm-check').checked=false;
    $('confirm-check').disabled= !valid(d);
    $('apply').disabled=true;
    if(complete){status('已自動辨識並填入 3 項資料。請逐字核對後確認。');}
    else{
      status('掃描已結束，讀到 '+n+'/3 項資料；可直接修改空白或錯誤欄位，不必一直手持證件。');
      error('這次辨識尚未完整。請核對並補上缺少欄位，或按「重新掃描」。');
    }
    $('fields').scrollIntoView({block:'nearest',behavior:'smooth'});
    if(bestShot){bestShot.width=1;bestShot.height=1;bestShot=null;}
    if(worker){const retiring=worker;worker=null;Promise.resolve(retiring.terminate()).catch(()=>{});}
  }
  async function getWorker(id) {
    if(worker)return worker;
    if(workerLoading)return workerLoading;
    if(!window.Tesseract?.createWorker || !Core)
      throw new Error('本機 OCR 程式尚未載入，請檢查 8006 /idscan 服務。');
    status('正在初始化本機中文字庫…');
    // Share one initialization promise to avoid loading two large OCR workers.
    workerLoading=(async()=>{
      const created=await window.Tesseract.createWorker(['chi_tra','eng'],1,{
        workerPath:base+'vendor/worker.min.js',corePath:base+'vendor/core',langPath:base+'vendor/lang',
        workerBlobURL:false,cacheMethod:'write'
      });
      if(token!==id||!active){await created.terminate();return null;}
      worker=created;return created;
    })();
    try{return await workerLoading;}
    finally{workerLoading=null;}
  }
  async function scanFrame(id) {
    if(token!==id || !active || busy)return;
    const v=$('video');
    if(v.readyState<2||!v.videoWidth||!v.videoHeight){timer=setTimeout(()=>void scanFrame(id),SAMPLE_MS);return;}
    if(!burstStarted)burstStarted=Date.now();
    sampleSharpFrame(v);
    const elapsed=Date.now()-burstStarted;
    if(elapsed<BURST_MS) {
      status('正在自動挑選清楚的畫面…無須按快門，也不必一直拿穩。');
      timer=setTimeout(()=>void scanFrame(id),SAMPLE_MS);return;
    }
    if(!bestShot){
      emptyBursts++;
      if(emptyBursts>=2){
        // Do not trap patients in an endless sharpness filter.
        const w=v.videoWidth,h=v.videoHeight;
        const c=document.createElement('canvas');
        const k=Math.min(2.0,1800/Math.max(w,h));
        c.width=Math.max(1,Math.round(w*k));c.height=Math.max(1,Math.round(h*k));
        const ctx=c.getContext('2d',{willReadFrequently:true});
        if(!ctx){finishWithReview(bestParsed||{name:'',pid:'',birthday:''},false);return;}
        ctx.drawImage(v,0,0,w,h,0,0,c.width,c.height);
        bestShot=c;
      } else {
        status('\u6b63\u5728\u5617\u8a66\u53e6\u4e00\u5f35\u5f71\u50cf\uff0c\u4e0d\u9700\u6309\u5feb\u9580\u3002');
        burstStarted=Date.now();timer=setTimeout(()=>void scanFrame(id),SAMPLE_MS);return;
      }
    }
    busy=true;attempts++;
    const picture=bestShot;bestShot=null;bestScore=-1;burstStarted=0;
    try {
      const w=await getWorker(id);if(!w||token!==id||!active)return;
      // Analyze the best still from the burst, not the entire video repeatedly.
      status('已自動擷取清楚畫面，正在辨識文字…');
      if(typeof w.setParameters==='function')await w.setParameters({tessedit_pageseg_mode: attempts===1?'11':'6'});
      const result=await w.recognize(picture);
      if(token!==id||!active)return;
      const raw=result.data?.text||'';
      recognizedChars=String(raw).replace(/\s/g,'').length;
      captureSize=picture.width+'x'+picture.height;
      const p=formatCandidate(raw),data=p.data;
      mergeFields(data);
      updateDiagnostics();
      showCandidate(bestParsed);
      if(valid(bestParsed)&&!p.ambiguous&&conflicts.size===0){
        finishWithReview(bestParsed,true);
      } else if(attempts>=MAX_TRIES){
        finishWithReview(bestParsed||data,false);
      } else {
        status('\u5df2\u8fa8\u8b58 '+countFields(bestParsed)+'/3 \u9805\uff0c\u6b63\u5728\u5617\u8a66\u7b2c\u4e8c\u5f35\u5f71\u50cf\u3002');
      }
    } catch(e){
      if(token===id){
        active=false;stopTracks();
        status('辨識程式無法完成：'+(e?.message||'未知錯誤'));
        error('請使用拍照／相簿備援，或返回原本輸入流程。');
        $('retry').hidden=false;
      }
    } finally {
      picture.width=1;picture.height=1;busy=false;
      if(token===id&&active&&!finished)timer=setTimeout(()=>void scanFrame(id),SAMPLE_MS);
    }
  }
  function applyToForm(d) {
    const form=document.querySelector('#bookingForm');if(!form)return false;
    const nm=form.querySelector('[name="name"]'),pid=form.querySelector('[name="pid"]'),dob=form.querySelector('[name="birthday"]');
    if(!nm||!pid||!dob)return false;
    const p=Core.dateParts(d.birthday);if(!p)return false;
    const set=(node,value)=>{node.value=value;node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));};
    const y=document.querySelector('#shanlin-dob-year'),m=document.querySelector('#shanlin-dob-month'),day=document.querySelector('#shanlin-dob-day');
    if(y&&m&&day){
      if(![...y.options].some(opt=>opt.value===String(p.year)))return false;
      set(y,String(p.year));set(m,String(p.month));set(day,String(p.day));
    }else{set(dob,d.birthday);}
    set(nm,d.name);set(pid,d.pid);
    form.querySelector('[name="phone"]')?.focus({preventScroll:true});
    return true;
  }
  function apply() {
    if(!finished)return;
    const data={name:$('name').value.replace(/\s/g,''),pid:$('pid').value.toUpperCase().replace(/[\s-]/g,''),birthday:$('birthday').value.replace(/\s/g,'')};
    if(!valid(data)){error('欄位不完整或格式不正確，請重新核對姓名、身分證字號及出生日期。');return;}
    const age=Core.ageFromRoc(data.birthday);
    if(mode==='chat' && window.DoubtsIdScanFlow?.isElderly?.() && age!==null && age<65){error('目前選擇高齡健檢流程，請確認生日或使用適合的預約方式。');return;}
    if(!$('confirm-check').checked){error('請先勾選已逐字核對。');return;}
    let ok=false;
    try {ok=mode==='chat'?!!window.DoubtsIdScanFlow?.accept?.(data):applyToForm(data);}catch(_){ok=false;}
    if(!ok){error('預約步驟已變更或表單欄位不符，尚未帶入；請返回姓名步驟重試。');return;}
    close();
  }
  // The existing V1 file-picker remains a supported fallback. Only the entry action is replaced.
  window.DoubtsIdScan.open=open;
  window.DoubtsIdScan.close=()=>{close(); if(fallbackClose)fallbackClose();};
  function relabel(){
    for(const el of document.querySelectorAll('.doubts-idscan-choice-camera strong, .doubts-idscan-entry')){
      if(el.classList.contains('doubts-idscan-entry')){
        for(const n of el.childNodes)if(n.nodeType===Node.TEXT_NODE && n.nodeValue?.includes('拍身分證'))n.nodeValue=n.nodeValue.replace('拍身分證，快速填寫','掃描身分證，自動填寫');
      }else if(el.textContent.includes('拍身分證'))el.textContent='掃描身分證，自動填寫';
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',relabel,{once:true});else relabel();
  const target=document.querySelector('#chat-body')||document.querySelector('#bookingForm');
  if(target) new MutationObserver(()=>relabel()).observe(target,{childList:true,subtree:true});
  window.addEventListener('pagehide',()=>{if(root)cancelScan();});
})();
