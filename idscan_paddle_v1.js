/* DOUBTS-PP-OCRV5-INTEGRATION-V1 | local browser inference; reviewed fields only. */
(function(){
 'use strict';
 const Core=window.DoubtsIdScanCore,script=document.currentScript;
 if(!Core||!script?.src||window.DoubtsIdScan?.version==='PP-OCRv5-FRIENDLY-V4')return;
 const host=location.hostname;
 if(!(/^(localhost|127\.0\.0\.1)$/.test(host)||/^192\.168\.\d+\.\d+$/.test(host)||/^10\.\d+\.\d+\.\d+$/.test(host)||/^172\.(1[6-9]|2\d|3[01])\.\d+\.\d+$/.test(host)))return;
 const base=new URL('.',script.src),engineURL=new URL('paddle/engine_v2.mjs',base).href;
 const $=id=>document.getElementById('dls2-'+id);
 // A Taiwanese ID card displays 2- or 3-digit ROC years: YYMMDD / YYYMMDD.
 // Do not interpret an incomplete five-digit OCR result as a one-digit year.
 const birthdayValid=value=>/^\d{6,7}$/.test(value)&&!!Core.dateParts(value);
 const fieldErrors=d=>({
   name:Core.validName(d.name)?'':'姓名格式有誤，請核對並修正。',
   pid:Core.validId(d.pid)?'':'身分證字號有誤，請核對格式及檢查碼。',
   birthday:birthdayValid(d.birthday)?'':'生日格式有誤，請填入完整民國年月日（6 或 7 碼）。'
 });
 const valid=d=>Object.values(fieldErrors(d)).every(message=>!message);
 const clinic=()=>new URL(location.href).searchParams.get('clinic')||'';
 let root=null,token=0,stream=null,active=false,finished=false,mode='chat',priorFocus=null,clinicAtOpen='';
 let enginePromise=null,prediction=Promise.resolve(),inferencePending=false,ready=false,phase='prepare',prewarmScheduled=false;
 const MAX_ATTEMPTS=6,MAX_MS=38000;
 const tpl=`
 <section class="dls2-panel" role="dialog" aria-modal="true" aria-labelledby="dls2-title">
  <header class="dls2-head"><strong id="dls2-title">掃描身分證</strong><button type="button" id="dls2-close" class="dls2-close" aria-label="關閉掃描">×</button></header>
  <div class="dls2-body">
   <p id="dls2-hint" class="dls2-hint" role="status" aria-live="polite">正在準備掃描<br>請稍候</p>
   <div id="dls2-view" class="dls2-view"><video id="dls2-video" autoplay muted playsinline aria-label="即時相機預覽"></video><div class="dls2-outline" aria-hidden="true"><i></i><i></i><i></i><i></i></div></div>
   <p id="dls2-status" class="dls2-status" role="status" aria-live="polite" hidden></p>
   <p id="dls2-diagnostics" hidden></p>
   <button id="dls2-replay" type="button" class="dls2-primary">🔊 再聽一次</button>
   <div id="dls2-fields" class="dls2-fields" hidden>
    <div class="dls2-field"><label for="dls2-name">姓名</label><input id="dls2-name" autocomplete="off" type="text" aria-describedby="dls2-name-error" readonly><p id="dls2-name-error" class="dls2-field-error" role="alert" hidden></p></div>
    <div class="dls2-field"><label for="dls2-pid">身分證字號</label><input id="dls2-pid" autocomplete="off" autocapitalize="characters" type="text" aria-describedby="dls2-pid-error" readonly><p id="dls2-pid-error" class="dls2-field-error" role="alert" hidden></p></div>
    <div class="dls2-field"><label for="dls2-birthday">生日（民國）</label><input id="dls2-birthday" autocomplete="off" inputmode="numeric" type="text" aria-describedby="dls2-birthday-error" readonly><p id="dls2-birthday-error" class="dls2-field-error" role="alert" hidden></p></div>
    <label class="dls2-consent"><input id="dls2-confirm-check" type="checkbox" disabled><span>我已核對，資料正確</span></label>
    <p id="dls2-error" class="dls2-error" role="alert" hidden></p>
    <button id="dls2-apply" type="button" class="dls2-primary" disabled>確認，繼續</button>
   </div>
   <button id="dls2-retry" type="button" hidden>重新掃描</button>
   <button id="dls2-manual" type="button">返回輸入</button>
   <details id="dls2-other"><summary>其他方式</summary><button id="dls2-fallback" type="button">選擇照片辨識</button><p class="dls2-privacy">影像只在此瀏覽器內辨識。</p></details>
   <input id="dls2-file" type="file" accept="image/*" hidden aria-label="選擇照片辨識">
  </div>
 </section>`;
 const styleText=`
 #doubts-livescan-v2{position:fixed;inset:0;z-index:2147483100;display:none;align-items:center;justify-content:center;background:#102a3ac7;padding:16px;box-sizing:border-box;font-family:system-ui,-apple-system,'PingFang TC','Noto Sans TC',sans-serif;color:#193b50;font-size:20px;line-height:1.5}
 #doubts-livescan-v2.is-open{display:flex}#doubts-livescan-v2 *{box-sizing:border-box}#doubts-livescan-v2 [hidden]{display:none!important}
 #doubts-livescan-v2 .dls2-panel{display:flex;flex-direction:column;width:min(100%,570px);max-height:calc(100dvh - 32px);background:#f8fbfd;border-radius:18px;overflow:hidden;box-shadow:0 18px 58px #0005}
 #doubts-livescan-v2 .dls2-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-shrink:0;padding:12px 20px;background:#8ba8ba}
 #doubts-livescan-v2 .dls2-head strong{font-size:26px;line-height:1.5}
 #doubts-livescan-v2 button{font:600 20px/1.5 system-ui,-apple-system,'PingFang TC','Noto Sans TC',sans-serif;min-height:56px;border:2px solid #668fa7;background:#fff;color:#193b50;border-radius:12px;padding:10px 16px;white-space:normal;overflow-wrap:anywhere;cursor:pointer;width:100%}
 #doubts-livescan-v2 button:disabled{background:#d3dfe7;border-color:#b0c4d2;color:#3d596b;cursor:not-allowed}
 #doubts-livescan-v2 .dls2-close{min-width:56px;width:56px;flex:none;padding:0;font-size:32px;line-height:1;background:transparent;border-color:transparent}
 #doubts-livescan-v2 .dls2-body{display:grid;gap:12px;padding:16px 20px 20px;overflow-y:auto;min-height:0;overscroll-behavior:contain}
 #doubts-livescan-v2 .dls2-hint{margin:0;background:#294958;color:#fff;text-align:center;font-size:24px;line-height:1.5;font-weight:700;padding:12px;border-radius:12px}
 #doubts-livescan-v2 .dls2-view{position:relative;aspect-ratio:1.5;border-radius:14px;overflow:hidden;background:#122b3c}
 #doubts-livescan-v2 video{display:block;width:100%;height:100%;object-fit:cover}
 #doubts-livescan-v2 .dls2-outline{position:absolute;inset:14%;border:2px solid #ddfff2;border-radius:12px;box-shadow:0 0 0 80px #06192566;pointer-events:none}
 #doubts-livescan-v2 .dls2-outline i{position:absolute;width:25px;height:25px;border:0 solid #7ee9bd}
 #doubts-livescan-v2 .dls2-outline i:nth-child(1){left:-3px;top:-3px;border-left-width:5px;border-top-width:5px}
 #doubts-livescan-v2 .dls2-outline i:nth-child(2){right:-3px;top:-3px;border-right-width:5px;border-top-width:5px}
 #doubts-livescan-v2 .dls2-outline i:nth-child(3){left:-3px;bottom:-3px;border-left-width:5px;border-bottom-width:5px}
 #doubts-livescan-v2 .dls2-outline i:nth-child(4){right:-3px;bottom:-3px;border-right-width:5px;border-bottom-width:5px}
 #doubts-livescan-v2 .dls2-primary{background:#365c73;color:white;border-color:#365c73}
 #doubts-livescan-v2 .dls2-fields{display:grid;gap:16px}#doubts-livescan-v2 .dls2-fields label{font-size:20px;font-weight:600}
 #doubts-livescan-v2 input:not([type=checkbox]):not([type=file]){display:block;min-height:56px;width:100%;margin-top:4px;border:2px solid #799bae;border-radius:12px;padding:10px 12px;font:500 22px/1.5 system-ui,sans-serif;color:#193b50;background:#fff}
 #doubts-livescan-v2 .dls2-consent{display:flex;align-items:center;gap:12px;min-height:56px;cursor:pointer}
 #doubts-livescan-v2 input[type=checkbox]{width:32px;height:32px;flex:none;margin:0;accent-color:#365c73}
 #doubts-livescan-v2 .dls2-status{margin:0;font-size:20px;line-height:1.5;padding:10px 12px;border-radius:10px;background:#e5f2f8}
 #doubts-livescan-v2 .dls2-error{margin:0;font-size:20px;color:#942432}
 #doubts-livescan-v2 .dls2-field-error{display:block;color:#a11e2c;font-size:18px;font-weight:700;margin:4px 0 0}
 #doubts-livescan-v2 input[aria-invalid=true]{border-color:#a11e2c!important}
 #doubts-livescan-v2 summary{min-height:48px;padding:10px 0;font-size:18px;cursor:pointer}#doubts-livescan-v2 .dls2-privacy{font-size:18px;margin:12px 0 0}
 #doubts-livescan-v2 :is(button,input,summary):focus-visible{outline:3px solid #bd7c08;outline-offset:2px}
 @media(max-width:430px){#doubts-livescan-v2{padding:0}#doubts-livescan-v2 .dls2-panel{width:100%;height:100dvh;max-height:100dvh;border-radius:0}#doubts-livescan-v2 .dls2-head{padding:calc(8px + env(safe-area-inset-top)) 16px 8px}#doubts-livescan-v2 .dls2-body{padding:16px 16px calc(16px + env(safe-area-inset-bottom))}#doubts-livescan-v2 .dls2-hint{font-size:24px}}
 `;
 function status(text){if(root){$('status').textContent=text;$('status').hidden=!text;}}
 function error(text){$('error').textContent=text||'';$('error').hidden=!text;}
 function fields(){return {name:$('name').value.replace(/\s/g,''),pid:$('pid').value.toUpperCase().replace(/[\s-]/g,''),birthday:$('birthday').value.replace(/\s/g,'')};}
 function validate(){
   const problems=fieldErrors(fields());
   for(const key of ['name','pid','birthday']){
     const message=finished?problems[key]:'';
     $(key+'-error').textContent=message;$(key+'-error').hidden=!message;
     $(key).setAttribute('aria-invalid',String(!!message));
   }
   $('confirm-check').checked=false;$('confirm-check').disabled=!finished||!valid(fields());$('apply').disabled=true;
   error(finished?Object.values(problems).filter(Boolean).join(' '):'');
 }
 function showFields(data){for(const key of ['name','pid','birthday'])$(key).value=data[key]||'';validate();}
 function makeUI(){
   if(root)return;
   const style=document.createElement('style');style.textContent=styleText;document.head.appendChild(style);
   root=document.createElement('div');root.id='doubts-livescan-v2';root.innerHTML=tpl;document.body.appendChild(root);
   $('close').addEventListener('click',close);$('manual').addEventListener('click',close);
   $('retry').addEventListener('click',()=>void beginCamera());
   $('replay').addEventListener('click',()=>speakPrompt());
   $('fallback').addEventListener('click',()=>{cancel();finish(null,'請選擇照片。若取消選取，可重新掃描或返回手動輸入。');$('file').value='';$('file').click();});
   $('file').addEventListener('change',()=>{const f=$('file').files?.[0];if(f)void recognizePhoto(f);});
   $('apply').addEventListener('click',apply);
   $('confirm-check').addEventListener('change',()=>{$('apply').disabled=!finished||!valid(fields())||!$('confirm-check').checked;});
   for(const key of ['name','pid','birthday'])$(key).addEventListener('input',validate);
   root.addEventListener('click',event=>{if(event.target===root)close();});
   root.addEventListener('keydown',event=>{
     if(event.key==='Escape'){event.preventDefault();close();return;}
     if(event.key!=='Tab')return;
     const controls=[...root.querySelectorAll('button:not(:disabled),input:not(:disabled)')].filter(el=>el.getClientRects().length);
     if(!controls.length)return;
     if(event.shiftKey&&document.activeElement===controls[0]){event.preventDefault();controls.at(-1).focus();}
     else if(!event.shiftKey&&document.activeElement===controls.at(-1)){event.preventDefault();controls[0].focus();}
   });
 }
 function stopTracks(){if(stream){stream.getTracks().forEach(track=>track.stop());stream=null;}if(root){$('video').pause();$('video').srcObject=null;}}
 function cancel(){token++;active=false;stopTracks();stopPrompt();}
 function reset(){
   finished=false;phase='prepare';showFields({});$('diagnostics').textContent='';$('retry').hidden=true;$('view').hidden=false;
   $('title').textContent='掃描身分證';$('fields').hidden=true;$('hint').hidden=false;$('hint').innerHTML='正在準備掃描<br>請稍候';$('replay').hidden=false;$('other').open=false;status('');
   for(const key of ['name','pid','birthday'])$(key).readOnly=true;
 }
 function close(){
   if(!root)return;cancel();root.classList.remove('is-open');reset();$('file').value='';
   if(priorFocus?.isConnected)priorFocus.focus({preventScroll:true});
 }
 function open(which){
   makeUI();cancel();mode=which==='form'?'form':'chat';clinicAtOpen=clinic();priorFocus=document.activeElement;
   reset();root.classList.add('is-open');$('close').focus({preventScroll:true});void beginCamera();
 }
 async function getScanner(){
   if(!enginePromise)enginePromise=import(engineURL).then(module=>module.createScanner(new URL('paddle/ort/',base).href)).then(scanner=>{ready=true;return scanner;}).catch(e=>{ready=false;enginePromise=null;throw e;});
   return enginePromise;
 }
 function predict(canvas,id){
   // A cancelled prediction can finish, but cannot fill fields or overlap a new one.
   const next=prediction.catch(()=>{}).then(async()=>{
     if(token!==id)return null;inferencePending=true;
     try{return await (await getScanner()).predict(canvas,()=>token===id&&root.classList.contains('is-open'));}
     finally{inferencePending=false;}
   });
   prediction=next.then(()=>{},()=>{});return next;
 }
 function capture(video){
   const vw=video.videoWidth,vh=video.videoHeight;if(!vw||!vh)return null;
   const view=video.getBoundingClientRect(),guide=root.querySelector('.dls2-outline').getBoundingClientRect();
   if(!view.width||!view.height||!guide.width)return null;
   const scale=Math.max(view.width/vw,view.height/vh),ox=(vw*scale-view.width)/2,oy=(vh*scale-view.height)/2;
   const margin=.06*Math.max(guide.width,guide.height);
   const x=Math.max(0,(guide.left-view.left+ox-margin)/scale),y=Math.max(0,(guide.top-view.top+oy-margin)/scale);
   const w=Math.min(vw-x,(guide.width+2*margin)/scale),h=Math.min(vh-y,(guide.height+2*margin)/scale);
   if(!(w>0&&h>0))return null;
   const canvas=document.createElement('canvas'),s=Math.min(1,2560/Math.max(w,h));
   canvas.width=Math.max(1,Math.round(w*s));canvas.height=Math.max(1,Math.round(h*s));
   canvas.getContext('2d').drawImage(video,x,y,w,h,0,0,canvas.width,canvas.height);return canvas;
 }
 function diagnostics(result){return `PP-OCRv5：${result.lines} 段文字 / 有效 ${result.count}/3 / OCR ${Math.round(result.totalMs)} ms / ${result.recovery?'已執行字號局部辨識 / ':''}${result.recoveryFailed?'局部辨識失敗 / ':''}${result.idStatus}`;}
 function finish(result,message){
   active=false;stopTracks();finished=true;phase='review';$('view').hidden=true;$('retry').hidden=false;
   $('title').textContent='請核對資料';$('hint').hidden=true;$('fields').hidden=false;$('replay').hidden=true;
   for(const key of ['name','pid','birthday'])$(key).readOnly=false;
   showFields(result?.fields||{});$('diagnostics').textContent=result?diagnostics(result):'';
   status(result?.count===3?'':result?.count?'請補填空白欄位，再核對資料。':'沒有讀到資料，請重新掃描或改用輸入。');
   if(!result&&message)status(message);
   validate();
 }
 async function scanLoop(id){
   let best=null,attempt=0;const started=Date.now();
   while(active&&token===id&&attempt<MAX_ATTEMPTS&&Date.now()-started<MAX_MS){
     if($('video').readyState<2){await new Promise(resolve=>setTimeout(resolve,350));continue;}
     const snapshot=capture($('video'));if(!snapshot){await new Promise(resolve=>setTimeout(resolve,350));continue;}
     attempt++;status('');
     try{
       const result=await predict(snapshot,id);if(!result||token!==id||!active)return;
       if(!best||result.count>=best.count)best=result;
       showFields(result.fields);$('diagnostics').textContent=diagnostics(result);
       if(result.count===3&&!result.ambiguous.length){finish(result,'三項資料已辨識，請逐字核對後勾選確認，再帶入預約。');return;}
       status('');
     }catch(e){if(token===id)finish(best,'辨識暫時無法完成。您可核對、補填，或選擇照片重試。');return;}
     finally{snapshot.width=1;snapshot.height=1;}
     await new Promise(resolve=>setTimeout(resolve,650));
   }
   if(token===id&&active)finish(best,'本次掃描已結束。請核對及補填空白欄位，或重新掃描；核對後才會帶入預約。');
 }
 async function beginCamera(){
   cancel();reset();const id=token;active=true;speakPrompt();
   if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){finish(null,'相機無法開啟，請選擇照片或返回輸入。');return;}
   try{
     const opened=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}}});
     if(token!==id||!active){opened.getTracks().forEach(track=>track.stop());return;}
     stream=opened;$('video').srcObject=stream;await $('video').play();
     if(token!==id||!active)return;
     await getScanner();if(token===id&&active){phase='scan';$('hint').innerHTML='將證件放入框內<br>無須按快門';status('');await new Promise(resolve=>setTimeout(resolve,0));if(token!==id||!active)return;speakPrompt();void scanLoop(id);}
   }catch(e){if(token===id)finish(null,'掃描暫時無法使用，請重試或返回輸入。');}
 }
 async function recognizePhoto(file){
   cancel();reset();const id=token;$('view').hidden=true;let canvas=null,url=null;
   $('hint').innerHTML='正在辨識照片<br>請稍候';status('');
   try{
     if(!file.type.startsWith('image/')||file.size>12*1024*1024)throw Error('請使用 12MB 以內的圖片。');
     url=URL.createObjectURL(file);const image=new Image();
     await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('圖片無法開啟，請改用 JPG 或 PNG。'));image.src=url;});
     if(token!==id)return;
     if(!image.naturalWidth||!image.naturalHeight)throw Error('圖片尺寸無效。');
     canvas=document.createElement('canvas');const scale=Math.min(1,2560/Math.max(image.naturalWidth,image.naturalHeight));
     canvas.width=Math.round(image.naturalWidth*scale);canvas.height=Math.round(image.naturalHeight*scale);
     canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
     const result=await predict(canvas,id);if(result&&token===id)finish(result,'照片辨識完成。請逐字核對三項資料，修正後再確認帶入。');
   }catch(e){if(token===id)finish(null,e?.message||'照片辨識失敗，請重試或手動輸入。');}
   finally{if(url)URL.revokeObjectURL(url);if(canvas){canvas.width=1;canvas.height=1;}if(token===id)$('file').value='';}
 }

 function schedulePrewarm(){
   if(prewarmScheduled||ready)return;prewarmScheduled=true;
   const start=()=>{prewarmScheduled=false;if(document.visibilityState==='hidden')return;void getScanner().catch(()=>{});};
   if('requestIdleCallback' in window)window.requestIdleCallback(start,{timeout:2000});else setTimeout(start,1000);
 }
 function stopPrompt(){
   const originalStop=document.querySelector('#doubts-voice-v5 button[data-dv-role="stop"]');
   if(originalStop)originalStop.click();
   window.YidianSpeech?.stopAll?.();
   if('speechSynthesis' in window)window.speechSynthesis.cancel();
 }
 function speakPrompt(){
   if(!root?.classList.contains('is-open')||phase==='review')return;
   const text=phase==='scan'?'將證件放入框內，無須按快門。':'正在準備掃描，請稍候。';
   stopPrompt();
   try{
     // The home speech extension wraps this existing function for its selected language.
     if(typeof window.speakText==='function'){Promise.resolve(window.speakText(text)).catch(()=>{});return;}
     const speech=window.YidianSpeech;
     if(speech?.getLanguage?.()==='nan'&&speech.speakTaiwanese){Promise.resolve(speech.speakTaiwanese(text)).catch(()=>{});return;}
     if('speechSynthesis' in window&&'SpeechSynthesisUtterance' in window){
       const utterance=new SpeechSynthesisUtterance(text);utterance.lang='zh-TW';utterance.rate=speech?.getRate?.()||.85;
       utterance.onerror=()=>{};window.speechSynthesis.speak(utterance);
     }
   }catch(_){/* Visible instructions and Replay remain available when audio is blocked. */}
 }
 function setInput(node,value){node.value=value;node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));}
 function applyToForm(data){
   const form=document.querySelector('#bookingForm');if(!form)return false;
   const name=form.querySelector('[name="name"]'),pid=form.querySelector('[name="pid"]'),birthday=form.querySelector('[name="birthday"]');
   const date=Core.dateParts(data.birthday);if(!name||!pid||!birthday||!date)return false;
   const year=document.querySelector('#shanlin-dob-year'),month=document.querySelector('#shanlin-dob-month'),day=document.querySelector('#shanlin-dob-day');
   if(year&&month&&day){
     if(![...year.options].some(option=>option.value===String(date.year)))return false;
     setInput(year,String(date.year));setInput(month,String(date.month));setInput(day,String(date.day));
     if(year.value!==String(date.year)||month.value!==String(date.month)||day.value!==String(date.day))return false;
   }
   setInput(birthday,data.birthday);setInput(name,data.name);setInput(pid,data.pid);
   form.querySelector('[name="phone"]')?.focus({preventScroll:true});return true;
 }
 function apply(){
   if(!finished||active||inferencePending)return;
   const data=fields();if(!valid(data)){validate();return;}
   if(!$('confirm-check').checked){error('請先勾選已逐字核對。');return;}
   if(clinic()!==clinicAtOpen){error('診所已變更，請關閉後重新掃描。');return;}
   const flow=window.DoubtsIdScanFlow;
   if(mode==='chat'&&flow?.isElderly?.()&&Core.ageFromRoc(data.birthday)<65){error('目前選擇高齡健檢流程，請核對生日或改選合適方案。');return;}
   let accepted=false;
   try{accepted=mode==='form'?applyToForm(data):!!(flow?.canScan?.()&&flow.accept?.(data));}catch(_){accepted=false;}
   if(!accepted){error('預約步驟或欄位已變更，尚未帶入；請返回姓名步驟重試。');return;}
   close();
 }
 function relabel(){for(const label of document.querySelectorAll('.doubts-idscan-choice-camera strong'))if(label.textContent!=='掃描身分證，自動填寫')label.textContent='掃描身分證，自動填寫';}
 function setup(){
   const form=document.querySelector('#bookingForm');
   if(form&&!document.querySelector('#doubts-idscan-form-entry')){
     const button=document.createElement('button');button.type='button';button.id='doubts-idscan-form-entry';button.className='doubts-idscan-entry';
     button.textContent='📷 掃描身分證，自動填寫';button.addEventListener('click',()=>open('form'));form.insertBefore(button,form.firstElementChild);
   }
   relabel();const chat=document.querySelector('#chat-body');
   const prepare=()=>{relabel();if(form||document.querySelector('.doubts-idscan-choice-camera'))schedulePrewarm();};
   if(chat)new MutationObserver(prepare).observe(chat,{childList:true,subtree:true});prepare();
 }
 window.DoubtsIdScan={open,close,version:'PP-OCRv5-FRIENDLY-V4'};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup,{once:true});else setup();
 window.addEventListener('pagehide',()=>{if(root)close();});
})();
