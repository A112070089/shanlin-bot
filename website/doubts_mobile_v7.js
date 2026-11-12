/* DOUBTS-MOBILE-VOICE-V7: one recorder, three languages, one control surface. */
(()=>{
 'use strict';
 if(window.DoubtsMobileV7)return;
 const KEY='doubts-mobile-language-v7';
 const stored=(key,fallback)=>{try{return localStorage.getItem(key)||fallback;}catch(_){return fallback;}};
 const save=(key,value)=>{try{localStorage.setItem(key,value);}catch(_){}};
 let language=stored(KEY,stored('yidian-voice-language-v1','zh'));
 if(!['zh','nan','en'].includes(language))language='zh';
 let rate=Number(stored('yidian-voice-speed-v1','.8'))||.8;
 rate=Math.max(.6,Math.min(1.2,rate));
 let last='',lastContext=null,auto=true,speechTurn=0,audio=null,audioURL=null,utterance=null,settleSpeech=null,paused=false;
 let pendingSpeech='',speechTimer=null,lastAuto='',lastAutoAt=0;
 let recorder=null,stream=null,recordState='idle',recordTurn=0,recordTimer=null,recordStart=0,recordTarget=null,recordRequest=null,micActivity=null;
 const translationCache=new Map();
 let naturalPlayer=null,naturalUnlocked=false,naturalRequest=null;
 const naturalCache=new Map();
 let naturalCooldown=0,autoSpeechTimer=null,naturalLimitScope='unknown';
 function voiceLimitMessage(){
   const seconds=Math.max(1,Math.ceil((naturalCooldown-Date.now())/1000));
   const minutes=Math.ceil(seconds/60);
   const reason=/day$/.test(naturalLimitScope)?tr('每日語音額度已達上限','Daily voice quota reached'):/minute$/.test(naturalLimitScope)?tr('語音請求過於密集','Voice requests are temporarily limited'):tr('語音服務達到用量限制','Voice service usage limit reached');
   return reason+tr('，約 '+minutes+' 分鐘後可再試；文字與操作仍可使用。','. Try again in about '+minutes+' minute(s). Text and controls still work.');
 }
 const api=()=>String(window.SITE?.bookingApi||location.origin).replace(/\/$/,'');
 const plain=value=>{const el=document.createElement('div');el.innerHTML=String(value||'').replace(/<br\s*\/?>/gi,'\n');return el.textContent.replace(/👉(?:[\uFE0F\u{1F3FB}-\u{1F3FF}])?/gu,'').trim();};
 const esc=value=>String(value).replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
 const textOnly=value=>String(value||'').replace(/[\p{P}\p{S}]/gu,' ').replace(/\s+/g,' ').trim();
 let interfaceLanguage=stored('doubts-site-language-v1','zh');
 if(!['zh','en'].includes(interfaceLanguage))interfaceLanguage='zh';
 // DOUBTS-DIALOG-LANGUAGE-INDEPENDENT-V1
 const dialogUILanguage=()=>language==='en'?'en':'zh';
 const siteTr=(zh,en)=>interfaceLanguage==='en'?en:zh;
 const dialogRoots='#chat-widget,#selfpay-chat-overlay,#selfpay-panel,#selfpay-chat-options,#doubts-livescan-v2';
 function uiLanguage(node){
   const el=node?.nodeType===1?node:node?.parentElement;
   return el?.closest(dialogRoots)?dialogUILanguage():interfaceLanguage;
 }
 function protectDialogLanguage(){
   for(const el of document.querySelectorAll(dialogRoots)){
     if(el.getAttribute('translate')!=='no')el.setAttribute('translate','no');
     if(!el.classList.contains('notranslate'))el.classList.add('notranslate');
     if(el.lang!==(dialogUILanguage()==='en'?'en':'zh-Hant'))el.lang=dialogUILanguage()==='en'?'en':'zh-Hant';
   }
 }
 // DOUBTS-DIALOGUE-RELIABILITY-V2
 const replySources=new WeakMap();
 function isSpeechPlaceholder(text){
   return !String(text||'').replace(/Loading\s*English|English text unavailable(?:\. Please retry)?|載入英文|正在載入英文|英文載入中/gi,'').replace(/[\s.…。!！?？:：,，-]/g,'');
 }
 function originalReply(node){
   if(!node)return '';
   if(replySources.has(node))return replySources.get(node);
   const copy=node.cloneNode(true);
   copy.querySelectorAll('button,input,select,textarea,script,style,.doubts-idscan-choice-wrap,.dm-en,.dm-manual-feedback,.dm-status').forEach(el=>el.remove());
   const value=plain(copy.textContent);
   if(!value||isSpeechPlaceholder(value))return '';
   replySources.set(node,value);return value;
 }
 function syncContactHints(){
   const stages=[['chat-input',typeof currentStep!=='undefined'?currentStep:'','senior'],
     ['selfpay-chat-input',typeof selfPayChatMode!=='undefined'?selfPayChatMode:'','selfpay']];
   for(const [id,stage,section] of stages){
     const input=document.getElementById(id);if(!input)continue;
     const name=stage==='name',phone=stage==='phone';
     const attrs={type:phone?'tel':'text',inputmode:phone?'tel':'text',
       autocomplete:name?'section-'+section+' name':phone?'section-'+section+' tel-national':'off',
       name:name?'patient_name':phone?'patient_phone':'chat_answer',autocapitalize:name?'words':'off',autocorrect:'off',spellcheck:'false',enterkeyhint:'send'};
     for(const [key,value] of Object.entries(attrs))if(input.getAttribute(key)!==value)input.setAttribute(key,value);
     if(name||phone){
       const label=name?tr('姓名','Full name'):tr('手機號碼','Mobile number');
       if(input.getAttribute('aria-label')!==label)input.setAttribute('aria-label',label);
       const placeholder=name?tr('輸入您的姓名，或使用自動填入','Enter your name, or use AutoFill'):tr('輸入手機號碼，或使用自動填入','Enter your mobile number, or use AutoFill');
       if(input.placeholder!==placeholder)input.placeholder=placeholder;
     }else if(input.hasAttribute('aria-label'))input.removeAttribute('aria-label');
   }
 }
 function stabilizeDialogueControls(){
   if(!document.getElementById('dm-dialogue-controls-v2')){
     const style=document.createElement('style');style.id='dm-dialogue-controls-v2';
     style.textContent=`
html body.dm-v7 .dm-toolbar .dm-controls{min-height:132px!important;flex-shrink:0!important;}
html.dm-keyboard body.dm-v7 .dm-toolbar .dm-controls{height:max(132px,var(--dm-controls-height,132px))!important;}
html body.dm-v7 .dm-toolbar .dm-row{flex-shrink:0!important;}
html body.dm-v7 .dm-toolbar{min-height:0!important;flex-shrink:0!important;}
html body.dm-v7 .dm-toolbar .dm-controls button{min-height:48px!important;}
`;
     document.head.append(style);
   }
 }
 document.addEventListener('focusin',event=>{if(event.target.matches?.('#chat-input,#selfpay-chat-input'))syncContactHints();},true);
 window.addEventListener('blur',()=>document.documentElement.classList.remove('dm-keyboard'));
 window.addEventListener('focus',()=>{
   document.documentElement.classList.toggle('dm-keyboard',!!document.activeElement?.matches('#chat-input,#selfpay-chat-input'));
 });

 const tr=(zh,en)=>dialogUILanguage()==='en'?en:zh;
 function status(text,error=false){document.querySelectorAll('.dm-status').forEach(el=>{el.textContent=text;el.dataset.error=String(error);});}

   const DIGITS_V12 = "零一二三四五六七八九";
  function zhNumberV12(num) {
    const n = Number(num);
    if (!Number.isSafeInteger(n) || n < 0) return String(num);
    if (n < 10) return DIGITS_V12[n];
    if (n < 20) return "十" + (n % 10 ? DIGITS_V12[n % 10] : "");
    if (n < 100) return DIGITS_V12[Math.floor(n / 10)] + "十" + (n % 10 ? DIGITS_V12[n % 10] : "");
    if (n < 1000) return DIGITS_V12[Math.floor(n / 100)] + "百" + (n % 100 === 0 ? "" : n % 100 < 10 ? "零" + DIGITS_V12[n % 100] : zhNumberV12(n % 100));
    if (n < 10000) return DIGITS_V12[Math.floor(n / 1000)] + "千" + (n % 1000 === 0 ? "" : n % 1000 < 100 ? "零" + zhNumberV12(n % 1000) : zhNumberV12(n % 1000));
    return String(n).split("").map(c => DIGITS_V12[Number(c)] || c).join("");
  }
  // Keep the displayed plan label, but read its code as a single letter.
  function preparePlanCodeSpeech(text) {
    return String(text || "").normalize("NFKC").replace(
      /(?<![A-Za-z0-9])(?:[「『"“‘]\s*)?([ABC])\s*(?:[」』"”’]\s*)?方案(?![A-Za-z0-9])/gi,
      (_match, letter) => ` ${letter.toUpperCase()} 方案 `
    ).replace(/\s{2,}/g, " ").trim();
  }
  // A reply to an information question must never count as choosing a plan.
  function parsePlanChoiceV12(value) {
    const raw = String(value || "").normalize("NFKC").replace(/[，。？！!?、,\s]/g, "");
    const m = raw.match(/^(?:(?:我要選|我想選|我選了|我選|我要|我想要|我想|想選|請幫我選|幫我選|選擇|選|要|那就選))?(?:第)?([123一二三壹貳參])(?:個|號|種)?(?:方案)?(?:就好|好了|可以|謝謝)?$/);
    if (!m) return "";
    return ({"1":"A", "一":"A", "壹":"A", "2":"B", "二":"B", "貳":"B", "3":"C", "三":"C", "參":"C"})[m[1]] || "";
  }
  function prepareTaigiSpeechV12(text) {
    let s = String(text || "").normalize("NFKC");
    // Speech-only wording: an introduction calls the assistant 助理, avoiding 小幫手 ambiguity.
    // Preserve the original screen text and any genuine references to children.
    s = s.replace(/(我是[^。！？!?\n]{0,24})小幫手/g, '$1助理');
    // During a complete booking-data review, narrate a fixed instruction only.
    // The detailed, potentially sensitive fields remain visible for visual checking.
    if (/資料核對/.test(s) && /姓名/.test(s) && /(?:證號|身分證)/.test(s)) {
      return "基本資料已整理，請核對畫面上的姓名，身分證字號，手機號碼和出生年月日，確認無誤再繼續";
    }
    // Dynamic TTS must not send patient names, IDs or mobile numbers to 8004.
    // Pronouncing uncommon names is unreliable: ask users to verify the displayed name.
    s = s.replace(/(?:已記錄姓名|姓名已記錄)\s*[：:]?\s*[「\"]?[\u3400-\u9fff]{2,5}[」\"]?/g, "姓名已記錄，請核對畫面文字");
    s = s.replace(/姓名我也記下了\s*[：:]?\s*[「\"]?[\u3400-\u9fff]{2,5}[」\"]?/g, "姓名也記下來了，請核對畫面文字");
    s = s.replace(/(?:將名字更正為|名字更正為)\s*[：:]?\s*[「\"]?[\u3400-\u9fff]{2,5}[」\"]?/g, "將姓名更新了，請核對畫面文字");
    s = s.replace(/姓名\s*[：:]\s*[「\"]?[\u3400-\u9fff]{2,5}[」\"]?/g, "姓名已記錄，請核對畫面文字");
    s = s.replace(/(?:生日|出生年月日)\s*[：:]\s*(?:民國)?\d{1,4}[-\/年]?\d{1,2}[-\/月]?\d{1,2}[號日]?/g, "出生年月日已記錄，請核對畫面文字");
    s = s.replace(/(?:手機號碼已記錄|電話已記錄)\s*[：:]?\s*09\d{8}/g, "手機號碼已記錄");
    s = s.replace(/(?:手機號碼|電話)\s*[：:]\s*09\d{8}/g, "手機號碼已記錄");
    s = s.replace(/(?:身分證字號|身分證號碼|證號)\s*[：:]?\s*[A-Z][12]\d{8}/gi, "身分證字號已記錄");
    s = s.replace(/\b09\d{8}\b/g, "手機號碼已記錄");
    s = s.replace(/\b[A-Z][12]\d{8}\b/gi, "身分證字號已記錄");
    // A/B/C are read with the English-letter voice; do not add "方案".
    s = preparePlanCodeSpeech(s);
    // ROC birthday compact format: 450101 -> 民國四十五年一月一號.
    s = s.replace(/(?<!\d)(\d{5,7})(?!\d)/g, original => {
      const match = original.match(/^(\d{1,3})(\d{2})(\d{2})$/);
      if (!match) return original;
      const year=Number(match[1]), month=Number(match[2]), day=Number(match[3]);
      if (!(year>0 && year<=200 && month>=1 && month<=12 && day>=1 && day<=31)) return original;
      return `民國${zhNumberV12(year)}年${zhNumberV12(month)}月${zhNumberV12(day)}號`;
    });
    s = s.replace(/(\d{4})\s*[年\/\-]\s*(\d{1,2})\s*[月\/\-]\s*(\d{1,2})\s*(?:日|號)?/g,
      (_m,y,mo,da) => `${[...y].map(c=>DIGITS_V12[Number(c)]).join("")}年${zhNumberV12(mo)}月${zhNumberV12(da)}號`);
    s = s.replace(/(\d{1,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日號]/g,
      (_m,y,mo,da) => `${zhNumberV12(y)}年${zhNumberV12(mo)}月${zhNumberV12(da)}號`);
    s = s.replace(/(?<!\d)(\d{1,2})\s*[\/月]\s*(\d{1,2})\s*[日號]?(?!\d)/g,
      (_m,mo,da) => `${zhNumberV12(mo)}月${zhNumberV12(da)}號`);
    s = s.replace(/(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})(?!\d)/g,
      (_m,h,m) => `${zhNumberV12(h)}點${Number(m)===0?"整":zhNumberV12(m)+"分"}`);
    s = s.replace(/(?<!\d)(\d{1,2})\s*點\s*(\d{1,2})\s*分/g,
      (_m,h,m) => `${zhNumberV12(h)}點${zhNumberV12(m)}分`);
    s = s.replace(/(?<!\d)(\d{1,2})\s*[點时時](?!\d)/g, (_m,h)=>`${zhNumberV12(h)}點`);
    s = s.replace(/(?<!\d)(\d{4})\s*年/g, (_m,y)=>`${[...y].map(c=>DIGITS_V12[Number(c)]).join("")}年`);
    s = s.replace(/(?<!\d)(\d{1,3})\s*年/g, (_m,y)=>`${zhNumberV12(y)}年`);
    // Convert all remaining Arabic numbers before sending text to the translator.
    s = s.replace(/\d+/g, number=>zhNumberV12(number));
    return s;
  }


 function protectedText(text){
   let value=String(text),fields=[];
   const data=typeof bookingData!=='undefined'?bookingData:typeof appointmentData!=='undefined'?appointmentData:{};
   for(const key of ['name','pid','phone','birthday'])if(data?.[key])fields.push(String(data[key]));
   fields=[...new Set(fields)].sort((a,b)=>b.length-a.length);
   const restore=[];
   for(const field of fields){if(value.includes(field)){const tag=`__FIELD_${restore.length}__`;value=value.split(field).join(tag);restore.push([tag,field]);}}
   return {value,restore};
 }
 async function translate(text,target){
   if(!text)return '';
   if(target==='en'&&!/[\u3400-\u9fff]/.test(text))return text;
   if(target==='zh'&&/[\u3400-\u9fff]/.test(text))return text;
   const {value,restore}=protectedText(text),key=target+'|'+value;
   if(!translationCache.has(key)){
     if(translationCache.size>120)translationCache.clear();
     translationCache.set(key,(async()=>{
       const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),22000);
       try{
         const r=await fetch(api()+'/api/mobile_voice/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:value.slice(0,2400),target}),signal:controller.signal});
         const data=await r.json();if(!r.ok||data.status!=='success'||!data.text)throw Error('translate');
         return data.text;
       }finally{clearTimeout(timer);}
     })().catch(error=>{translationCache.delete(key);throw error;}));
   }
   let result=await translationCache.get(key);
   for(const [tag,field]of restore)result=result.split(tag).join(field);
   return result.replace(/👉(?:[\uFE0F\u{1F3FB}-\u{1F3FF}])?/gu,'');
 }
 function englishAmount(value){
   let s=String(value).normalize('NFKC').toLowerCase().replace(/[-,]/g,' ').replace(/[.!?]/g,'').trim();
   s=s.replace(/^(?:(?:my|the)\s+)?budget\s*(?:is|of|:)\s*/,'').replace(/^(?:i have|i can spend|i want to spend)\s+/,'');
   s=s.replace(/\b(?:ntd|twd|dollars?|bucks?|only|please|and)\b/g,' ').replace(/\b(hundred|thousand|million)s\b/g,'$1').trim();
   if(/^\d+(?:\s+\d{3})*$/.test(s))return Number(s.replace(/\s/g,''));
   const units={zero:0,one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,eleven:11,twelve:12,thirteen:13,fourteen:14,fifteen:15,sixteen:16,seventeen:17,eighteen:18,nineteen:19,twenty:20,thirty:30,forty:40,fifty:50,sixty:60,seventy:70,eighty:80,ninety:90};
   let total=0,current=0,count=0;
   for(const token of s.split(/\s+/)){
     if(token in units){current+=units[token];count++;}
     else if(/^\d+$/.test(token)){current+=Number(token);count++;}
     else if(token==='hundred'){current=(current||1)*100;count++;}
     else if(token==='thousand'||token==='million'){total+=(current||1)*(token==='thousand'?1000:1e6);current=0;count++;}
     else return null;
   }
   return count&&Number.isSafeInteger(total+current)&&total+current<=1e8?total+current:null;
 }
 const digitWords={zero:'0',oh:'0',one:'1',two:'2',three:'3',four:'4',five:'5',six:'6',seven:'7',eight:'8',nine:'9'};
 function digitInput(text){return text.toLowerCase().replace(/\b(zero|oh|one|two|three|four|five|six|seven|eight|nine)\b/g,x=>digitWords[x]).replace(/[\s,-]/g,'');}

 function planQuestion(text,step){
   if(step!=='plan')return null;
   const raw=String(text).trim();
   if(!/\b(?:what|which|how|explain|describe|introduce|compare|difference|different|tell me|about)\b/i.test(raw))return null;
   if(!/\b(?:plans?|plants?|planes?|three[ -]points?|packages?|options?|these three)\b/i.test(raw))return null;
   if(/\b(?:plants?|planes?)\b/i.test(raw)&&!/\b(?:three|these|those|difference|different|compare|health|screening|check)\b/i.test(raw))return null;
   // Only normalize the subject of an explicit question in the plan step.
   const corrected=raw.replace(/\bplants?\b|\bplanes?\b/gi,'plans').replace(/\bthree[ -]points?\b/gi,'three plans');
   if(/\b(?:difference|different|compare)\b/i.test(corrected))return {text:corrected,value:'請介紹這三個方案的差別，不要替我選擇方案。'};
   if(/\b(?:what|explain|describe|introduce|tell me|about)\b/i.test(corrected))return {text:corrected,value:'請介紹這三個健檢方案的內容，不要替我選擇方案。'};
   return null;
 }

 let originalInput='',canonicalValue='';
 async function canonicalInput(text,step=''){
   const raw=String(text).trim();originalInput=raw;canonicalValue=raw;
   if(step==='name')return raw;
   if(step==='plan'){const choice=parsePlanChoiceV12(raw);if(choice){canonicalValue=choice;return choice;}}
   if(step==='plan'&&!/^(?:(?:i\s+)?(?:choose|select|want)(?:\s+plan)?\s+|plan\s+)?[abc][.!]?$/i.test(raw)&&!/^(?:[123]|one|two|three|yes|no|back|restart)$/i.test(raw)){canonicalValue=raw;return raw;}
   if(step==='pid'){
     const s=digitInput(raw.replace(/\b(?:letter|id|number|is)\b/gi,''));
     canonicalValue=/^[a-z]\d+$/i.test(s)?s.toUpperCase():raw;return canonicalValue;
   }
   if(step==='phone'){
     const s=digitInput(raw.replace(/\b(?:my|phone|number|is)\b/gi,''));
     if(/^\d+$/.test(s)){canonicalValue=s;return s;}
   }
   if(step==='budget'){
     const amount=englishAmount(raw);if(amount!==null){canonicalValue=String(amount);return canonicalValue;}
   }
   const plan=raw.match(/^(?:(?:i\s+)?(?:choose|select|want)(?:\s+plan)?\s+|plan\s+)?([abc])(?:\s+plan)?[.!]?$/i);
   if(plan){canonicalValue=plan[1].toUpperCase();return canonicalValue;}
   if(step==='plan'){const numbered=parsePlanChoiceV12(raw);if(numbered){canonicalValue=numbered;return numbered;}}
   const commands={'yes':'正確','correct':'正確','confirm':'正確','no':'不正確','incorrect':'不正確','back':'上一步','go back':'上一步','restart':'重新開始','start over':'重新開始','change budget':'修改預算','done':'完成','finish':'完成','not sure':'不知道'};
   const key=raw.toLowerCase().replace(/[.!?]+$/,'');
   if(commands[key]){canonicalValue=commands[key];return canonicalValue;}
   if(!/[\u3400-\u9fff]/.test(raw)&&/[a-z]{3}/i.test(raw)){
     canonicalValue=await translate(raw,'zh');
   }
   return canonicalValue;
 }

 function stopAll(){
   clearTimeout(autoSpeechTimer);
   if(naturalRequest){naturalRequest.abort();naturalRequest=null;}
   ++speechTurn;pendingSpeech='';paused=false;clearTimeout(speechTimer);
   if(settleSpeech){settleSpeech(false);settleSpeech=null;}
   if(utterance){utterance.onstart=utterance.onend=utterance.onerror=null;utterance=null;}
   if(audio){audio.onended=audio.onerror=null;audio.pause();audio=null;}
   if(audioURL){URL.revokeObjectURL(audioURL);audioURL=null;}
   if('speechSynthesis'in window)window.speechSynthesis.cancel();
   updateLabels();
 }
 function nativeSpeech(text,lang,turn){
   return new Promise(resolve=>{
     if(turn!==speechTurn)return resolve(false);
     if(!window.speechSynthesis||!window.SpeechSynthesisUtterance)return resolve(false);
     const item=new SpeechSynthesisUtterance(text);utterance=item;item.lang=lang;item.rate=rate;
     const voices=speechSynthesis.getVoices();item.voice=voices.find(v=>v.lang===lang)||voices.find(v=>v.lang.startsWith(lang.slice(0,2)))||null;
     let timer,done=false;
     const settle=ok=>{if(done)return;done=true;clearTimeout(timer);if(settleSpeech===settle)settleSpeech=null;resolve(ok);};
     settleSpeech=settle;
     item.onstart=()=>{clearTimeout(timer);status(tr('正在朗讀','Reading aloud'));};
     item.onend=()=>settle(turn===speechTurn);
     item.onerror=()=>settle(false);
     timer=setTimeout(()=>settle(false),6500);
     speechTimer=setTimeout(()=>{if(turn!==speechTurn)return settle(false);speechSynthesis.resume();speechSynthesis.speak(item);},160);
   });
 }
 // DOUBTS-PLAIN-SPEECH-V2
 function plainChineseSpeech(value){
   let s=String(value||'').normalize('NFKC');
   // Keep identifiers out of the translation request before removing Latin text.
   s=s.replace(/\b[A-Z][12]\d{8}\b/gi,'身分證字號已記錄');
   const important=/不|未|無|勿|僅|只|限|需|須|除|若|如果|可能|風險|歲|孕|空腹|過敏|禁忌|注意|非|滿|以上|以下|至少|建議|避免|但|低於|高於|超過|少於|元|%|分鐘|小時|天|日|年|次|公分|公斤|包含|含|適用/;
   // Remove asides, but keep conditions, exclusions and safety instructions.
   for(let i=0;i<8;i++){
     const next=s.replace(/\(([^()]*)\)|【([^【】]*)】/g,(_m,a,b)=>{
       const inner=a??b;return important.test(inner)?'，'+inner+'，':' ';
     });
     if(next===s)break;s=next;
   }
   const names={A:'第一方案',B:'第二方案',C:'第三方案'};
   s=s.replace(/方案\s*([ABC])(?![A-Za-z0-9])/g,(_m,c)=>names[c]);
   s=s.replace(/(?<![A-Za-z0-9])([ABC])\s*方案/g,(_m,c)=>names[c]);
   s=s.replace(/(?<![A-Za-z0-9\u3400-\u9fff])([ABC])(?![A-Za-z0-9\u3400-\u9fff])/g,(_m,c)=>names[c]);
   s=s.replace(/[A-Za-z][A-Za-z0-9]*(?:[-\/.][A-Za-z0-9]+)*/g,' ');
   s=s.replace(/\*+|`+|_+|^\s*#{1,6}\s*/gm,'');
   s=s.replace(/^\s*[-•]\s+/gm,'');
   return s.replace(/[()【】]/g,' ').replace(/[ \t]+/g,' ').replace(/\s*([，。；！？])\s*/g,'$1')
     .replace(/，+/g,'，').replace(/，([。；！？])/g,'$1').trim();
 }

 // DOUBTS-TAIGI-SMOOTH-V2
 const taigiAudioCache=new Map();
 let taigiCacheBytes=0;
 function taigiParts(text){
   const normalized=plainChineseSpeech(prepareTaigiSpeechV12(text));
   if(normalized.length>6000)throw Error('taigi_text_too_long');
   const result=[];
   const segments=normalized.split(/(?<![A-Za-z0-9])([ABC])(?![A-Za-z0-9])/g);
   for(const segment of segments){
     if(/^[ABC]$/.test(segment)){result.push({type:'en',text:segment});continue;}
     // Preserve phrase boundaries; use a shorter first clip to start sooner.
     const phrases=segment.match(/[^。！？!?；;，,、\n]+[。！？!?；;，,、\n]*/gu)||[];
     let current='';
     const emit=()=>{if(textOnly(current))result.push({type:'nan',text:current.trim()});current='';};
     for(let phrase of phrases){
       let limit=result.length?48:32;
       if(current&&current.length+phrase.length>limit)emit();
       while(phrase.length>(result.length?48:32)){
         limit=result.length?48:32;
         if(current)emit();
         // Prefer a word boundary when Chinese text includes English words.
         let cut=phrase.lastIndexOf(' ',limit);
         if(cut<Math.floor(limit/2))cut=limit;
         current=phrase.slice(0,cut);emit();phrase=phrase.slice(cut).trimStart();
       }
       current+=phrase;
     }
     emit();
   }
   return result;
 }
 async function taigiBlob(part,turn){
   if(turn!==speechTurn)throw Error('cancelled');
   const key=api()+'|'+part.type+'|'+part.text;
   const cached=taigiAudioCache.get(key);
   if(cached&&Date.now()-cached.at<300000)return cached.blob;
   if(cached){taigiAudioCache.delete(key);taigiCacheBytes-=cached.blob.size;}
   const controller=new AbortController();naturalRequest=controller;
   const timer=setTimeout(()=>controller.abort(),60000);
   try{
     const route=part.type==='en'?'/api/mobile_voice/speak':'/api/taigi_tts/text';
     const response=await fetch(api()+route,{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify(part.type==='en'?{text:part.text}:{text:part.text,source:'ai_reply'}),signal:controller.signal});
     if(!response.ok||!response.headers.get('content-type')?.includes('audio/'))throw Error('taigi_http_'+response.status);
     const blob=await response.blob();
     if(turn!==speechTurn)throw Error('cancelled');
     if(blob.size<44||blob.size>8*1024*1024)throw Error('taigi_invalid_audio');
     while(taigiAudioCache.size>=24||taigiCacheBytes+blob.size>16*1024*1024){
       const first=taigiAudioCache.keys().next().value;if(first===undefined)break;
       taigiCacheBytes-=taigiAudioCache.get(first).blob.size;taigiAudioCache.delete(first);
     }
     taigiAudioCache.set(key,{blob,at:Date.now()});taigiCacheBytes+=blob.size;
     return blob;
   }finally{clearTimeout(timer);if(naturalRequest===controller)naturalRequest=null;}
 }
 async function playTaigi(text,turn){
   const parts=taigiParts(text);if(!parts.length)return false;
   const prepare=part=>taigiBlob(part,turn).then(blob=>({blob}),error=>({error}));
   let next=prepare(parts[0]);
   try{
     for(let i=0;i<parts.length;i++){
       if(turn!==speechTurn)return false;
       status('正在準備台語語音，請稍候');
       const result=await next;
       if(turn!==speechTurn)return false;if(result.error)throw result.error;
       const player=naturalPlayer||(naturalPlayer=new Audio());
       const url=URL.createObjectURL(result.blob);audioURL=url;audio=player;
       player.src=url;player.muted=false;player.playbackRate=rate;
       if('preservesPitch'in player)player.preservesPitch=true;
       let prefetched=false;
       const prefetch=()=>{
         if(prefetched||turn!==speechTurn)return;prefetched=true;
         if(i+1<parts.length)next=prepare(parts[i+1]);
       };
       let ok;
       try{
         ok=await new Promise(resolve=>{
           let done=false,playingMs=0,waitingMs=0;
           const finish=value=>{
             if(done)return;done=true;clearInterval(timer);
             if(settleSpeech===finish)settleSpeech=null;
             player.onended=player.onerror=player.onplaying=null;resolve(value);
           };
           // User pause does not count as a stall or consume the playback budget.
           const timer=setInterval(()=>{
             if(turn!==speechTurn)return finish(false);
             if(paused)return;
             if(!player.paused){playingMs+=500;waitingMs=0;}else waitingMs+=500;
             const expected=Number.isFinite(player.duration)&&player.duration>0
               ? player.duration*1000/Math.max(.6,player.playbackRate)+10000:90000;
             if(playingMs>Math.min(180000,Math.max(20000,expected))||waitingMs>10000)finish(false);
           },500);
           settleSpeech=finish;player.onended=()=>finish(turn===speechTurn);player.onerror=()=>finish(false);
           player.onplaying=()=>{if(turn===speechTurn){status('正在朗讀台語');prefetch();}};
           Promise.resolve(player.play()).then(prefetch,()=>finish(false));
         });
       }finally{
         if(audio===player){player.pause();audio=null;}
         URL.revokeObjectURL(url);if(audioURL===url)audioURL=null;
       }
       if(!ok)return false;
     }
     return true;
   }finally{
     if(turn===speechTurn&&naturalRequest){naturalRequest.abort();naturalRequest=null;}
   }
 }

 // One unlocked HTMLAudioElement is reused on Safari; never silently fall back to a system voice.
 function primeNaturalAudio(){
   if(naturalUnlocked||audio||naturalPlayer)return;
   naturalPlayer=new Audio();naturalPlayer.muted=true;
   naturalPlayer.src='data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
   Promise.resolve(naturalPlayer.play()).then(()=>{
     if(audio===naturalPlayer)return;
     naturalPlayer.pause();naturalPlayer.currentTime=0;naturalPlayer.muted=false;naturalUnlocked=true;
   }).catch(()=>{if(audio!==naturalPlayer)naturalPlayer=null;});
 }
 document.addEventListener('pointerdown',primeNaturalAudio,true);
 document.addEventListener('keydown',primeNaturalAudio,true);
 function englishSpeechChunks(text){
   // Keep known personal data local when sending text to a speech provider.
   const safe=protectedText(text).value.replace(/__FIELD_\d+__/g,'your details')
     .replace(/\b[A-Z][12]\d{8}\b/gi,'your ID number').replace(/\b09\d{8}\b/g,'your phone number');
   const cleaned=safe.replace(/\[[^\]]*\]/g,'').trim();
   if(cleaned.length<=190)return cleaned?[cleaned]:[];
   const words=cleaned.split(/\s+/),chunks=[];let current='';
   for(let word of words){
     while(word.length>180){if(current){chunks.push(current);current='';}chunks.push(word.slice(0,180));word=word.slice(180);}
     if(current.length+word.length+1>180){chunks.push(current);current='';}
     current+=(current?' ':'')+word;
     if(/[.!?]$/.test(word)&&current.length>=65){chunks.push(current);current='';}
   }
   if(current)chunks.push(current);return chunks;
 }
 async function naturalBlob(text,turn){
   if(turn!==speechTurn)throw Error('cancelled');
   if(naturalCache.has(text))return naturalCache.get(text);
   if(Date.now()<naturalCooldown)throw Error('speech_rate_limited');
   const controller=new AbortController();naturalRequest=controller;
   const timer=setTimeout(()=>controller.abort(),30000);
   try{
     const r=await fetch(api()+'/api/mobile_voice/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text}),signal:controller.signal});
     if(!r.ok||!r.headers.get('content-type')?.includes('audio/')){
       let code='speech_failed';try{const info=await r.json();code=info.error_code||code;if(code==='speech_rate_limited'){naturalCooldown=Date.now()+Math.max(1,Math.min(86400,Number(info.retry_after)||60))*1000;naturalLimitScope=info.limit_scope||'unknown';}}catch(_){}
       throw Error(code);
     }
     const blob=await r.blob();if(turn!==speechTurn)throw Error('cancelled');
     if(blob.size<44||blob.size>8*1024*1024)throw Error('invalid_audio');
     if(naturalCache.size>=8)naturalCache.delete(naturalCache.keys().next().value);
     naturalCache.set(text,blob);return blob;
   }finally{clearTimeout(timer);if(naturalRequest===controller)naturalRequest=null;}
 }
 async function playNaturalEnglish(text,turn){
   const chunks=englishSpeechChunks(text);if(!chunks.length)return false;
   // Prefetch only one next chunk while current audio plays. Catch immediately to avoid rejected promises.
   const request=chunk=>naturalBlob(chunk,turn).then(blob=>({blob}),error=>({error}));
   let next=request(chunks[0]);
   for(let i=0;i<chunks.length;i++){
     const result=await next;if(turn!==speechTurn)return false;if(result.error)throw result.error;

     audioURL=URL.createObjectURL(result.blob);
     const player=naturalPlayer||(naturalPlayer=new Audio());audio=player;
     player.src=audioURL;player.muted=false;player.playbackRate=rate;
     const ok=await new Promise(resolve=>{
       let done=false,elapsed=0;
       const timer=setInterval(()=>{if(!player.paused)elapsed+=500;if(elapsed>90000)finish(false);},500);
       const finish=value=>{if(done)return;done=true;clearInterval(timer);if(settleSpeech===finish)settleSpeech=null;player.onended=player.onerror=player.onplaying=null;resolve(value);};
       settleSpeech=finish;player.onended=()=>finish(turn===speechTurn);player.onerror=()=>finish(false);
       player.onplaying=()=>{if(turn===speechTurn)status('Reading aloud');};
       Promise.resolve(player.play()).catch(()=>finish(false));
     });
     if(audio===player){player.pause();audio=null;}
     if(audioURL){URL.revokeObjectURL(audioURL);audioURL=null;}
     if(!ok){if(naturalRequest)naturalRequest.abort();return false;}
     if(i+1<chunks.length)next=request(chunks[i+1]);
   }
   return true;
 }

 async function speak(content,context=null,brief=false){
   const text=plain(content);if(!text||isSpeechPlaceholder(text))return false;
   stopAll();last=text;lastContext=context;const turn=speechTurn,lang=language;pendingSpeech=text;
   status(tr('正在準備朗讀','Preparing speech'));
   try{
     let spoken=preparePlanCodeSpeech(text);
     if(lang==='en'){
       const nodes=[...document.querySelectorAll('#chat-body .ai-msg,#selfpay-chat-body .selfpay-message.ai')];
       const match=nodes.reverse().find(node=>{
         const copy=node.cloneNode(true);copy.querySelectorAll('button,input,select,textarea,.doubts-idscan-choice-wrap,.dm-en').forEach(x=>x.remove());
         const raw=plain(copy.textContent).replace(/\s+/g,'');
         const wanted=text.replace(/\s+/g,'');
         return wanted.length>=20&&(raw.includes(wanted.slice(0,40))||wanted.includes(raw.slice(0,40))&&raw.length>=20);
       });
       if(match){translateMessage(match);spoken=match.dmEnglishPromise?await match.dmEnglishPromise:await translate(text,'en');}
       else spoken=await translate(text,'en');
     }
     if(turn!==speechTurn||lang!==language)return false;
     let ok=true;
     if(lang!=='en'){spoken=plainChineseSpeech(await translate(spoken,'zh'));if(!spoken.trim()){pendingSpeech='';status('這段沒有需要朗讀的中文內容，請查看畫面文字');return true;}}
     if(turn!==speechTurn||lang!==language)return false;
     if(lang==='nan')ok=await playTaigi(spoken,turn);
     else if(lang==='en')ok=await playNaturalEnglish(spoken,turn);
     else{
       const chunks=spoken.match(/[^。！？!?\n]{1,140}[。！？!?\n]?/g)||[spoken];
       for(const chunk of chunks){if(!await nativeSpeech(chunk,'zh-TW',turn)){ok=false;break;}}
     }
     if(turn===speechTurn){pendingSpeech='';status(ok?tr('朗讀完成','Finished reading'):tr('語音未完成，可按重聽回答','Audio did not finish. Select Replay to retry'),!ok);}
     return ok;
   }catch(error){if(naturalRequest)naturalRequest.abort();if(turn===speechTurn){pendingSpeech='';status(error.message==='speech_rate_limited'?voiceLimitMessage():(lang==='nan'?'台語服務暫時無法播放（'+(error.name==='AbortError'?'等待逾時':/^taigi_http_\d+$/.test(error.message)?error.message.replace('taigi_http_','HTTP '):'音訊處理失敗')+'），文字仍可使用。':tr('語音暫時無法播放，請查看文字','Speech is unavailable. Please read the displayed text')),error.message!=='speech_rate_limited');}return false;}
 }
 function autoSpeak(text,context){
   const value=plain(text);if(!value||isSpeechPlaceholder(value))return false;last=value;lastContext=context;
   if(!auto)return false;
   if(value===lastAuto&&Date.now()-lastAutoAt<1500)return false;
   lastAuto=value;lastAutoAt=Date.now();clearTimeout(autoSpeechTimer);
   if(language==='en'&&Date.now()<naturalCooldown){status(voiceLimitMessage());return false;}
   autoSpeechTimer=setTimeout(()=>void speak(value,context,true),300);return true;
 }
 function pause(){
   if(audio){paused?audio.play().catch(()=>{}):audio.pause();paused=!paused;}
   else if(window.speechSynthesis?.speaking){paused?speechSynthesis.resume():speechSynthesis.pause();paused=!paused;}
   else{status(tr('目前沒有播放中的語音','No audio is playing'));return;}
   updateLabels();status(paused?tr('已暫停，可按繼續播放','Paused. Select Resume'):tr('繼續播放','Resuming'));
 }
 function updateLabels(){
   document.documentElement.dataset.dmLanguage=dialogUILanguage();
   protectDialogLanguage();
   document.querySelectorAll('button[data-dm-language=en]').forEach(e=>e.textContent='English');
   document.querySelectorAll('button[data-dm-language=zh]').forEach(e=>e.textContent=tr('國語','Mandarin'));
   document.querySelectorAll('button[data-dm-language=nan]').forEach(e=>e.textContent=tr('台語','Taiwanese'));
   document.querySelectorAll('.dm-speed-label').forEach(el=>el.textContent=tr('語速','Speech rate'));
   document.querySelectorAll('.dm-speed input').forEach(el=>el.setAttribute('aria-label',tr('朗讀語速','Speech rate')));
   document.querySelectorAll('.dm-grip').forEach(el=>{
     el.textContent=tr('上下拖曳調整高度','Drag to adjust height');
     el.setAttribute('aria-label',tr('上下拖曳調整控制區高度，也可用方向鍵調整','Drag to adjust control height, or use the arrow keys'));
   });
   document.querySelectorAll('button[data-dm-language]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.dmLanguage===language)));
   document.querySelectorAll('[data-dm-action]').forEach(b=>{b.textContent={replay:tr('重聽回答','Replay'),pause:paused?tr('繼續播放','Resume'):tr('暫停播放','Pause'),speed:tr('語速','Speed')}[b.dataset.dmAction];});
   for(const id of ['chatMicBtn','selfpay-mic-btn']){const b=document.getElementById(id);if(b){b.textContent=recordState==='recording'&&recordTarget===id?tr('完成','Done'):tr('說話','Speak');b.setAttribute('aria-pressed',String(recordState==='recording'&&recordTarget===id));b.disabled=['requesting','processing'].includes(recordState);}}
   for(const id of ['chatSendBtn','selfpay-send-btn']){const b=document.getElementById(id);if(b)b.textContent=tr('傳送','Send');}
   const chatField=document.getElementById('chat-input');if(chatField)chatField.placeholder=tr('輸入文字，或按說話','Type, or select Speak');
   const selfField=document.getElementById('selfpay-chat-input');if(selfField)selfField.placeholder=typeof selfPayChatMode!=='undefined'&&selfPayChatMode==='budget'?tr('預算，例如 500','Budget, e.g. 500'):tr('輸入文字，或按說話','Type your answer');
   document.querySelectorAll('#chat-widget .quick-actions button').forEach(b=>{const t=b.getAttribute('onclick')||'';b.textContent=t.includes('上一步')?tr('回上一步','Back'):tr('重新開始','Restart');});
   syncContactHints();stabilizeDialogueControls();
 }
 function cancelRecording(){
   ++recordTurn;clearTimeout(recordTimer);recordRequest?.abort();recordRequest=null;
   if(recorder&&recorder.state!=='inactive'){recorder.onstop=null;try{recorder.stop();}catch(_){}}
   micActivity?.stop();micActivity=null;stream?.getTracks().forEach(t=>t.stop());stream=null;recorder=null;recordState='idle';updateLabels();
 }
 function activityGate(opened){
   const Context=window.AudioContext||window.webkitAudioContext;if(!Context)return null;
   try{
     const context=new Context(),source=context.createMediaStreamSource(opened),analyser=context.createAnalyser();
     analyser.fftSize=2048;source.connect(analyser);const frames=new Float32Array(2048);let active=0,running=false,closed=false;
     void context.resume().catch(()=>{});
     const clock=setInterval(()=>{if(context.state!=='running')return;running=true;analyser.getFloatTimeDomainData(frames);let sum=0;for(const sample of frames)sum+=sample*sample;if(Math.sqrt(sum/frames.length)>.006)active++;},60);
     return {hasSpeech:()=>!running||active>=2,stop(){if(closed)return;closed=true;clearInterval(clock);source.disconnect();void context.close().catch(()=>{});}};
   }catch(_){return null;}
 }
 async function microphone(id){
   if(recordState==='recording'){if(id===recordTarget&&recorder?.state==='recording'){recordState='processing';clearTimeout(recordTimer);status(tr('正在辨識，請稍候','Recognizing speech'));recorder.stop();updateLabels();}return;}
   if(recordState!=='idle')return;
   const draftField=document.getElementById(id==='selfpay-mic-btn'?'selfpay-chat-input':'chat-input'),draftBefore=draftField?.value;
   stopAll();recordTarget=id;recordState='requesting';const turn=++recordTurn,lang=language;updateLabels();
   try{
     if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw Error('unsupported');
     const opened=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
     if(turn!==recordTurn){opened.getTracks().forEach(t=>t.stop());return;}
     stream=opened;const gate=activityGate(opened);micActivity=gate;const types=['audio/mp4','audio/webm;codecs=opus','audio/webm','audio/ogg'];
     const mime=types.find(t=>MediaRecorder.isTypeSupported(t));const rec=new MediaRecorder(stream,mime?{mimeType:mime}:{});recorder=rec;const chunks=[];
     rec.ondataavailable=event=>{if(event.data?.size)chunks.push(event.data);};
     rec.onerror=()=>{if(turn!==recordTurn)return;cancelRecording();status(tr('錄音未完成，請再試一次','Recording failed. Please try again'),true);};
     rec.onstop=async()=>{
       const hadVoice=gate?gate.hasSpeech():true;gate?.stop();if(micActivity===gate)micActivity=null;
       opened.getTracks().forEach(t=>t.stop());if(stream===opened)stream=null;
       if(turn!==recordTurn)return;
       recordState='processing';updateLabels();
       try{
         const blob=new Blob(chunks,{type:rec.mimeType||mime||'audio/mp4'});
         if(!hadVoice||Date.now()-recordStart<450||blob.size<32)throw Error('short');
         const ext=blob.type.includes('mp4')?'m4a':blob.type.includes('ogg')?'ogg':'webm';
         const fd=new FormData();fd.append('file',blob,'speech.'+ext);fd.append('language',lang==='en'?'en':'zh');
         const controller=new AbortController();recordRequest=controller;const timeout=setTimeout(()=>controller.abort(),90000);
         let result;
         try{const r=await fetch(api()+(lang==='nan'?'/api/taigi_stt/transcribe':'/api/mobile_voice/transcribe'),{method:'POST',body:fd,signal:controller.signal});result=await r.json();if(!r.ok||result.status==='error')throw Error('recognition');}
         finally{clearTimeout(timeout);}
         if(turn!==recordTurn)return;
         const rawTranscript=String(result.text||result.raw_text||'').trim();
         const question=lang==='en'?planQuestion(rawTranscript,typeof currentStep!=='undefined'?currentStep:''):null;
         const text=question?.text||rawTranscript;
         if(!text||/^[嗯啊呃哦喔。.?!？！，、]+$/u.test(text))throw Error('empty');
         recordState='idle';updateLabels();
         if(!draftField)throw Error('missing_input');
         if(draftField.value!==draftBefore){status(tr('辨識已完成，但輸入內容已變更，未覆寫；請重新錄音或手動修改','The draft changed during recording. It was kept; please record again or edit it'),true);return;}
         draftField.value=text;draftField.dispatchEvent(new Event('input',{bubbles:true}));
         draftField.focus({preventScroll:true});
         if(text!==rawTranscript){draftField.dataset.dmOriginalTranscript=rawTranscript;status('Possible plan-related word corrected. Originally recognized: '+rawTranscript+'. Review the draft, then select Send');}else{delete draftField.dataset.dmOriginalTranscript;status(tr('已填入辨識文字，可修改後按「傳送」','Transcript filled in. Review or edit it, then select Send'));}
       }catch(_){if(turn===recordTurn)status(tr('沒有取得完整語音，請再按說話或改用文字輸入','Could not recognize the recording. Select Speak or type your answer'),true);}
       finally{if(turn===recordTurn){recorder=null;recordRequest=null;recordState='idle';updateLabels();}}
     };
     rec.start(250);recordStart=Date.now();recordState='recording';updateLabels();
     status(tr('正在錄音，說完按「完成」','Recording. Select Done when finished'));
     recordTimer=setTimeout(()=>{if(turn===recordTurn&&recordState==='recording')void microphone(id);},30000);
   }catch(_){if(turn===recordTurn){cancelRecording();status(tr('無法啟動錄音，請允許麥克風權限','Cannot start recording. Please allow microphone access'),true);}}
 }
 // DOUBTS-LANGUAGE-AUTOPLAY-V1
 function setLanguage(next,container=null){
   if(!['zh','nan','en'].includes(next))return;
   // Read the clicked dialogue's latest assistant reply, never user inputs or button labels.
   const messages=container?[...container.querySelectorAll('.ai-msg,.selfpay-message.ai')]:[];
   const latest=messages.at(-1);let reply=container?'':last;
   if(latest)reply=originalReply(latest);
   ++catalogueTurn;catalogueRequest?.abort();cancelRecording();stopAll();
   language=next;save(KEY,next);save('yidian-voice-language-v1',next);
   updateLabels();decorateChoices();prepareEnglish();
   if(reply)void speak(reply,lastContext);
   else status(tr('語言已切換，目前沒有可朗讀的回答','Language selected. There is no response to read yet.'));
 }
 function attachToolbar(container,body){
   const panel=document.createElement('section');panel.className='dm-toolbar';panel.setAttribute('aria-label','語音與輸入語言');
   panel.innerHTML='<div class="dm-controls"><div class="dm-row"><button type="button" data-dm-language="zh">國語</button><button type="button" data-dm-language="nan">台語</button><button type="button" data-dm-language="en">English</button></div><div class="dm-row"><button type="button" data-dm-action="replay"></button><button type="button" data-dm-action="pause"></button><button type="button" data-dm-action="speed"></button></div><label class="dm-speed" hidden><span class="dm-speed-label"></span><input type="range" min="0.6" max="1.2" step="0.1"><output></output></label></div><div class="dm-grip" role="separator" aria-label="上下拖曳調整控制區高度，也可用方向鍵調整" aria-orientation="horizontal" tabindex="0" aria-valuemin="56" aria-valuemax="320" aria-valuenow="122">上下拖曳調整高度</div><p class="dm-status" role="status" aria-live="polite"></p>';
   container.insertBefore(panel,body);
   panel.querySelectorAll('[data-dm-language]').forEach(b=>b.onclick=()=>setLanguage(b.dataset.dmLanguage,container));
   panel.querySelector('[data-dm-action=replay]').onclick=()=>{if(last)void speak(last,lastContext);};
   panel.querySelector('[data-dm-action=pause]').onclick=pause;
   const speed=panel.querySelector('.dm-speed'),slider=speed.querySelector('input'),out=speed.querySelector('output');
   slider.value=String(rate);out.textContent=Math.round(rate*100)+'%';
   panel.querySelector('[data-dm-action=speed]').onclick=()=>{speed.hidden=!speed.hidden;if(!speed.hidden){panel.style.setProperty('--dm-controls-height','210px');requestAnimationFrame(()=>panel.style.setProperty('--dm-controls-height',Math.max(210,panel.querySelector('.dm-controls').scrollHeight)+'px'));}};
   slider.oninput=()=>{rate=Number(slider.value);out.textContent=Math.round(rate*100)+'%';save('yidian-voice-speed-v1',String(rate));if(audio)audio.playbackRate=rate;};
   const grip=panel.querySelector('.dm-grip');let startY=0,startHeight=122,drag=false;
   const size=value=>{const h=Math.round(Math.max(56,Math.min(320,value)));panel.style.setProperty('--dm-controls-height',h+'px');grip.setAttribute('aria-valuenow',String(h));};
   grip.onpointerdown=e=>{drag=true;startY=e.clientY;startHeight=panel.querySelector('.dm-controls').getBoundingClientRect().height||122;grip.setPointerCapture?.(e.pointerId);e.preventDefault();};
   grip.onpointermove=e=>{if(drag){size(startHeight+e.clientY-startY);e.preventDefault();}};
   grip.onpointerup=grip.onpointercancel=()=>{drag=false;};
   grip.onkeydown=e=>{if(e.key==='ArrowUp'||e.key==='ArrowDown'){size(Number(grip.getAttribute('aria-valuenow'))+(e.key==='ArrowUp'?-16:16));e.preventDefault();}};
 }
 function markError(message){
   if(!message)return;const text=message.textContent||'';
   if(/格式錯誤|格式還沒有辨識清楚|檢查碼.*(?:錯誤|不符|未通過)|無效日期|生日.*(?:不正確|有誤)/.test(text)){
     message.classList.add('dm-field-error');message.setAttribute('role','alert');
     if(!message.querySelector('.dm-error-label')){
       const label=document.createElement('strong');label.className='dm-error-label';label.textContent=/身分證|證號/.test(text)?'身分證字號格式錯誤':/生日|日期/.test(text)?'生日格式錯誤':'資料格式錯誤';message.prepend(label);
     }
     const input=document.getElementById('chat-input');input?.setAttribute('aria-invalid','true');
   }
 }

 function paragraphText(text){
   return String(text||'').replace(/👉(?:[\uFE0F\u{1F3FB}-\u{1F3FF}])?/gu,'').trim()
     .split(/\n\s*\n|(?<=。)\s*|(?<=[.!?])\s+(?=Before\b|May I\b|Next\b|Please enter\b)/).map(s=>s.trim()).filter(Boolean);
 }
 function fillParagraphs(el,text){
   el.replaceChildren();
   for(const part of paragraphText(text)){const p=document.createElement('span');p.className='dm-copy-paragraph';p.textContent=part;el.append(p,document.createTextNode('\n\n'));}
 }
 function decorateChoices(){
   for(const root of document.querySelectorAll('#chat-body .ai-msg,#selfpay-chat-body .selfpay-message.ai')){
     const walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;
     while((n=walk.nextNode()))if(n.textContent.includes('👉'))n.textContent=n.textContent.replace(/👉(?:[\uFE0F\u{1F3FB}-\u{1F3FF}])?/gu,'');
     if(!root.querySelector('.doubts-idscan-choice-wrap')||root.querySelector('.dm-choice-intro'))continue;
     const nodes=[...root.childNodes].filter(n=>n.nodeType===3||n.nodeType===1&&n.tagName==='BR');
     if(!nodes.length)continue;
     const text=nodes.map(n=>n.nodeType===3?n.textContent:'\n').join('');
     const intro=document.createElement('span');intro.className='dm-choice-intro';fillParagraphs(intro,text);
     root.insertBefore(intro,nodes[0]);nodes.forEach(n=>n.remove());
   }
 }

 function translateMessage(node){
   if(node)originalReply(node);
   if(!node||uiLanguage(node)!=='en'||node.dataset.dmTranslated)return;
   decorateChoices();
   node.dataset.dmTranslated='true';node.classList.add('dm-translating');
   const source=originalReply(node);if(!source||!/[\u3400-\u9fff]/.test(source)){node.classList.remove('dm-translating');return;}
   node.dmEnglishPromise=translate(source,'en');
   void node.dmEnglishPromise.then(text=>{
     if(!node.isConnected)return;
     const original=document.createElement('span');original.className='dm-original';
     for(const child of [...node.childNodes]){
       if(child.nodeType===1&&(child.matches('button,input,select,textarea,.doubts-idscan-choice-wrap')||child.querySelector('button,input,select,textarea')))continue;
       original.append(child);
     }
     node.prepend(original);
     const en=document.createElement('div');en.className='dm-en';en.lang='en';fillParagraphs(en,text);const controls=[...node.children].find(x=>x!==original&&(x.matches('button,input,select,textarea,.doubts-idscan-choice-wrap')||x.querySelector('button,input,select,textarea')));node.insertBefore(en,controls||null);node.classList.remove('dm-translating','dm-translation-failed');
   }).catch(()=>{delete node.dataset.dmTranslated;node.classList.remove('dm-translating');node.classList.add('dm-translation-failed');status('English translation is unavailable; the original text is retained.',true);});
 }
 function installSpeechAPI(){
   window.YidianSpeech={remember(text,context){last=plain(text);lastContext=context;},getLanguage:()=>language,getRate:()=>rate,cleanSpeechText:textOnly,speakTaiwanese:speak,autoSpeak,replay:()=>speak(last,lastContext),stopAll};
   window.speakText=(text,force=false)=>force?speak(text):autoSpeak(text);
   window.speakSelfPayText=speak;
   window.replaySpeaking=()=>speak(last,lastContext);window.toggleSpeaking=pause;
 }

 const cleanChecks=text=>String(text||'').replace(/[✅☑✔👉](?:[\uFE0F\u{1F3FB}-\u{1F3FF}])?/gu,'').trim();
 const uiOriginal=new WeakMap(),uiNodes=new Set(),uiCache=new Map();let uiTimer=null,uiBusy=false,uiRetryAfter=0,uiDirty=false;
 const uiWords={'首頁':'Home','預約健檢':'Book a Checkup','自費項目':'Self-pay Tests','聯絡資訊':'Contact','登入':'Log in','健康檢查預約服務':'Health Check Appointment Service','健康檢查':'Health Check','預約服務':'Appointment Service','一般預約':'General Booking','先了解三個步驟，再選擇健檢方案。':'Learn the three steps, then choose your checkup plan.','科技，讓醫療更有溫度':'Technology with a human touch','科技，讓醫療更有溫度。':'Technology with a human touch','先預約':'Book First','先填表':'Complete the Form','當天注意':'On the Day','可透過網站、LINE 或電話':'Via website, LINE or phone','填寫失智症及憂鬱症篩檢':'Complete the cognitive and mood screening forms','高齡健檢語音助理':'Senior Checkup Voice Assistant','自費健檢語音助理':'Self-pay Checkup Voice Assistant','高齡健檢':'Senior Health Check','自費健檢':'Self-pay Checkup','🧾 自費健檢語音助理':'Self-pay Health Check Voice Assistant','🏥 高齡健檢語音助理':'Senior Health Check Voice Assistant','請核對資料': 'Review your details', '姓名': 'Full name', '身分證字號': 'Taiwan national ID number', '生日（民國）': 'Date of birth (ROC calendar)', '我已核對，資料正確': 'I have checked these details and confirm they are correct', '確認，繼續': 'Confirm and continue', '重新掃描': 'Scan again', '返回輸入': 'Return to typing', '其他方式': 'Other methods', '選擇照片辨識': 'Choose an ID photo', '姓名格式有誤，請核對並修正。': 'Invalid name format. Please check and correct it.', '身分證字號有誤，請核對格式及檢查碼。': 'Invalid Taiwan ID number. Check the format and checksum.', '生日格式有誤，請填入完整民國年月日（6 或 7 碼）。': 'Invalid date of birth. Enter 6 or 7 digits in ROC year, month and day format.', '確定刪除': 'Confirm removal', '取消刪除': 'Cancel removal', '掃描身分證，自動填寫': 'Scan ID to fill in your details', '西元年': 'Year (AD)', '月': 'Month', '日': 'Day', '選擇西元年': 'Select year', '選擇月': 'Select month', '選擇日': 'Select day', '手機號碼': 'Mobile number', '預約日期': 'Appointment date', '預約時間': 'Appointment time', '請依序選擇西元年、月、日': 'Select year, month and day', '請選擇西元年、月、日，系統會依完整出生日期確認是否年滿65歲。': 'Select your complete date of birth. The system will check whether you are at least 65.', '出生年月日（西元）＊年滿65歲': 'Date of birth (AD) — age 65 or older', '--請等候測試名額載入--': 'Waiting for test availability…', '請輸入姓名': 'Enter your full name', '請輸入手機號碼': 'Enter your mobile number','自費健檢語音助理':'Self-pay Health Check Assistant','高齡健檢語音助理':'Senior Health Check Assistant','掃描身分證，自動填寫':'Scan ID to fill in your details','辨識姓名、證號、出生日期後核對':'Review your name, ID number and date of birth','打字／語音輸入':'Type or speak','在下方輸入，也可按麥克風說姓名':'Enter your name below or select Speak','自費檢查項目選單':'Self-pay Checkup List','心臟與血管':'Heart & Blood Vessels','肺部與呼吸':'Lungs & Breathing','肝膽與腸胃':'Liver & Digestive Health','腎臟與泌尿':'Kidneys & Urinary Health','抽血與全身健康':'Blood Tests & General Health','參考預算':'Budget','還可以用':'Remaining','超出':'Over budget','這是什麼？':'Details','＋ 加入':'Add','+ 加入':'Add','已加入':'Added','加入中…':'Adding…','刪除':'Remove','繼續選其他項目':'Browse more items','查看與修改已選項目':'Review selected items','完成自費選擇':'Finish selection','修改預算':'Change budget','← 修改預算':'Change budget','不知道選什麼？':'Not sure what to choose?','換一個方面':'Choose another category','‹ 換一個方面':'Choose another category','收起 ▾':'Collapse','展開 ▴':'Expand','載入中…':'Loading…'};
 // DOUBTS-SHANLIN-PROPER-NAME-V1
 // Proper names bypass automatic translation; the trailing space separates the small Clinic label.
 Object.assign(uiWords,{'山林':'Shanlin ','山林診所':'Shanlin Clinic','山林 診所':'Shanlin Clinic','診所':'Clinic'});
 // DOUBTS-SELFPAY-BROWSER-EN-V1
 Object.assign(uiWords,{
   '自費健康管理':'Self-pay Health Management',
   '選擇自費檢查類型':'Choose a Test Category',
   '請先選擇您想了解的檢查大分類':'Choose a category to explore the available tests.',
   '自費加購首頁':'Self-pay Tests',
   '心血管相關':'Heart & Blood Vessels',
   '肺部相關':'Lungs & Breathing',
   '肝膽胃腸相關':'Liver & Digestive Health',
   '腎臟與泌尿相關':'Kidneys & Urinary Health',
   '其他 / 加值檢測':'Other Tests',
   '其他／加值檢測':'Other Tests',
   '查看檢查項目':'View tests',
   '← 回到檢查分類':'← Back to categories',
   '回到檢查分類':'Back to categories',
   '請選擇您想了解或加購的檢查項目':'Choose a test to view its details or add it to your list.',
   '查看詳細內容':'View details',
   '加入':'Add',
   '請洽診所了解檢查內容。':'Please contact the clinic for test details.',
   '關閉':'Close',
   '提醒：':'Please note:',
   '本頁提供檢查項目與價格資訊； 是否適合加做，仍應由醫師或診所專業人員評估。':'This page lists tests and prices. A doctor or clinic professional should assess whether additional tests are appropriate.',
   '正在載入自費項目……':'Loading self-pay tests…',
   '正在載入……':'Loading…',
   '價格需確認':'Price to be confirmed',
   '重新載入':'Reload'
 });
 // DOUBTS-SELFPAY-READONLY-V2
 const browseRoots='#selfPayModal,#selfPayDetailDialog';
 const browsePurchase='.self-pay-add-btn,.self-pay-cart-remove,.self-pay-summary-button';
 function isSelfPayBrowser(node){return !!node?.parentElement?.closest(browseRoots);}
 function browserTranslationFailure(node){
   writeUI(node,isSelfPayBrowser(node)?(uiOriginal.get(node)||''): 'English text unavailable. Please retry.');
 }
 function prepareSelfPayBrowser(){
   for(const root of document.querySelectorAll(browseRoots)){
     if(root.getAttribute('translate')!=='no')root.setAttribute('translate','no');
     if(!root.classList.contains('notranslate'))root.classList.add('notranslate');
   }
   const modal=document.getElementById('selfPayModal');
   if(!modal)return;
   const browseOpen=modal.classList.contains('is-open')||modal.getAttribute('aria-hidden')==='false';
   const detail=document.getElementById('selfPayDetailDialog');
   if(detail&&browseOpen&&detail.dataset.dmBrowseOnly!=='true')detail.dataset.dmBrowseOnly='true';
   const roots=[modal,...document.querySelectorAll('#selfPayDetailDialog[data-dm-browse-only="true"]')];
   for(const root of roots){
     for(const button of root.querySelectorAll(browsePurchase)){
       if(!button.hidden)button.hidden=true;
       if(!button.disabled)button.disabled=true;
       if(button.getAttribute('aria-hidden')!=='true')button.setAttribute('aria-hidden','true');
     }
   }
   const target=modal.querySelector('.self-pay-footer');
   if(target){
     let notice=document.getElementById('dm-selfpay-browse-notice');
     if(!notice){notice=document.createElement('p');notice.id='dm-selfpay-browse-notice';notice.setAttribute('role','note');target.prepend(notice);}
     const text=siteTr('此處僅供查看檢查資訊與參考價格，無法加入或購買。','For information and reference prices only. Purchases are unavailable here.');
     if(notice.textContent!==text)notice.textContent=text;
   }
   if(!document.getElementById('dm-selfpay-readable-style')){
     const style=document.createElement('style');style.id='dm-selfpay-readable-style';
     style.textContent=`
#selfPayModal,#selfPayDetailDialog {font-family:system-ui,-apple-system,"Noto Sans TC",sans-serif!important;}
#selfPayModal :is(h2,h3,p,button,div,span,strong),#selfPayDetailDialog :is(h3,p,button,div,span,strong){font-family:inherit!important;}
#selfPayModal .self-pay-panel{width:min(94vw,1320px);max-width:94vw;}
#selfPayModal #selfPayTitle{font-size:clamp(32px,3vw,42px)!important;line-height:1.4!important;}
#selfPayModal :is(.self-pay-item-name,.self-pay-category-name,.self-pay-items-heading h3),#selfPayDetailDialog h3{font-size:30px!important;line-height:1.45!important;}
#selfPayModal :is(.self-pay-item-description,.self-pay-category-count,.self-pay-items-heading p,#selfPaySubtitle,.self-pay-breadcrumb),#selfPayDetailDialog .self-pay-detail-description{font-size:26px!important;line-height:1.7!important;}
#selfPayModal :is(.self-pay-item-note,.self-pay-header-label,.self-pay-footer),#selfPayDetailDialog .self-pay-item-note{font-size:22px!important;line-height:1.7!important;}
#selfPayModal button,#selfPayDetailDialog button{font-size:24px!important;line-height:1.5!important;min-height:56px;white-space:normal;}
#selfPayModal .self-pay-item-list{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:24px!important;}
#selfPayModal .self-pay-category-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important;}
#selfPayModal .self-pay-item-top{display:flex!important;flex-direction:column!important;align-items:flex-start!important;gap:12px!important;}
#selfPayModal :is(.self-pay-item-name,.self-pay-item-description),#selfPayDetailDialog h3{min-width:0;max-width:100%;word-break:normal!important;overflow-wrap:break-word!important;}
#selfPayModal .self-pay-item-price{font-size:24px!important;white-space:nowrap;max-width:100%;align-self:flex-start!important;}
#selfPayModal .self-pay-item-card{min-width:0;padding:24px!important;}
#selfPayModal .self-pay-item-actions{display:block!important;}
#selfPayModal .self-pay-detail-btn{width:100%;margin-top:0;}
#selfPayModal .self-pay-footer{display:flex;flex-wrap:wrap;gap:12px;padding:20px!important;}
#dm-selfpay-browse-notice{flex-basis:100%;margin:0;font-weight:700;font-size:24px;line-height:1.6;}
#selfPayModal :is(.self-pay-add-btn,.self-pay-summary-button,.self-pay-cart-remove),#selfPayDetailDialog[data-dm-browse-only="true"] .self-pay-add-btn{display:none!important;}
@media(max-width:700px){#selfPayModal :is(.self-pay-item-list,.self-pay-category-grid){grid-template-columns:minmax(0,1fr)!important;}#selfPayModal .self-pay-item-name{font-size:28px!important;}#selfPayModal .self-pay-content{padding:18px!important;} }
`;
     document.head.append(style);
   }
 }
 document.addEventListener('click',event=>{
   const button=event.target.closest?.(browsePurchase);if(!button)return;
   const modal=button.closest('#selfPayModal');
   const detail=button.closest('#selfPayDetailDialog');
   const browser=document.getElementById('selfPayModal');
   if(modal||detail&&(detail.dataset.dmBrowseOnly==='true'||browser?.classList.contains('is-open')||browser?.getAttribute('aria-hidden')==='false')){
     event.preventDefault();event.stopImmediatePropagation();
   }
 },true);
 Object.assign(uiWords,{
   '請選擇您想了解或加購的檢查項目':'Choose a test to view its details. This catalogue is for browsing only.',
   '此處僅提供資訊瀏覽，無法購買。':'For information only. Purchases are unavailable here.',
   '請選擇您想了解的檢查項目':'Choose a test to view its details.',
   '自費檢查項目':'Self-pay Tests',
   '套組包含：':'Package contents:'
 });
 function queueUI(){uiDirty=true;scheduleLanguageRefresh();}
 function uiTargets(){return [...document.querySelectorAll('#selfPayModal,#selfPayDetailDialog,#selfpay-panel,#selfpay-chat-options,.selfpay-message.ai,#chat-body .ai-msg,#chat-header,.selfpay-chat-header,#bookingForm,#header,#main,#scrollspyFooter,#plan_display,#doubts-livescan-v2,.selfpay-message.user,#chat-body .user-msg')];}

 const uiRendered=new WeakMap();
 function localUI(raw){
   const key=raw.replace(/\s+/g,' ').trim();if(uiWords[key])return uiWords[key];
   if(/^共\s*\d+\s*項檢查/.test(key)){
     const count=key.match(/\d+/)[0];
     return key.includes('可查看詳細內容')?count+' tests. View test details below.':count+' tests';
   }
   if(key.startsWith('自費加購首頁 ／ ')){
     const category=key.slice('自費加購首頁 ／ '.length);if(uiWords[category])return 'Self-pay Tests / '+uiWords[category];
   }
   if(/^查看檢查項目\s*[➜➔➝➞➙➡→]?$/.test(key))return 'View tests →';
   if(/^已選\s*(\d+)\s*項$/.test(key))return 'Selected '+key.match(/\d+/)[0]+' items';
   if(/^\d{1,4}年$/.test(key))return key.replace('年','');
   if(/^\d{1,2}月$/.test(key))return key.replace('月','');
   if(/^\d{1,2}日$/.test(key))return key.replace('日','');
   if(/^出生年月日.*西元.*65/.test(key))return 'Date of birth (AD) — age 65 or older';
   if(/^\(\s*範例[：:]\s*09\d{8}\s*\)$/.test(key))return '(Example: 0912345678)';
   return null;
 }
 function writeUI(node,text){
   if(node.textContent===text){uiRendered.set(node,text);return;}
   // Drop only our own pending notifications, leaving other app observers intact.
   node.textContent=text;uiRendered.set(node,text);
   languageObserver?.takeRecords();
 }
 async function translateUI(){
   uiDirty=false;const pending=new Map();
   for(const node of [...uiNodes])if(!node.isConnected)uiNodes.delete(node);
   for(const root of uiTargets()){
     const narrative=root.matches('.ai-msg,.selfpay-message.ai');
     if(narrative&&!root.querySelector('button,input,select,textarea'))continue;
     const user=root.matches('.user-msg,.selfpay-message.user');
     const walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let node;
     while((node=walk.nextNode())){
       if(root.matches('#main,#header,#scrollspyFooter')&&node.parentElement?.closest('#chat-widget,#selfpay-chat-overlay,#selfpay-panel'))continue;
       if(node.parentElement?.closest('script,style,#dm-selfpay-browse-notice,.dm-en,.dm-original,.dm-manual-feedback,input,textarea,.dm-toolbar,[data-clinic],.navbar-brand,.dm-site-language'))continue;
       if(node.parentElement?.closest('.ai-msg,.selfpay-message.ai')&&!node.parentElement?.closest('button,.doubts-idscan-choice-wrap'))continue;
       const current=node.textContent;let raw=uiOriginal.get(node);
       if(raw===undefined||uiRendered.has(node)&&current!==uiRendered.get(node)){
         if(!/[\u3400-\u9fff]/.test(current)){uiOriginal.delete(node);uiNodes.delete(node);continue;}
         raw=cleanChecks(current);if(isSelfPayBrowser(node))raw=raw.replace('請選擇您想了解或加購的檢查項目','請選擇您想了解的檢查項目').replace('或直接加入自費清單。','此處僅提供資訊瀏覽，無法購買。');uiOriginal.set(node,raw);uiNodes.add(node);
       }
       if(raw===undefined)continue;
       if(uiLanguage(node)!=='en'){writeUI(node,raw);continue;}
       const ready=localUI(raw)||uiCache.get(raw);
       if(user&&!ready)continue; // User-entered names and text remain verbatim.
       if(ready){writeUI(node,ready);continue;}
       if(raw.length>1500){writeUI(node,'English text unavailable. Please retry.');continue;}
       writeUI(node,'Loading English…');
       if(!pending.has(raw))pending.set(raw,[]);pending.get(raw).push(node);
     }
   }
   if(!pending.size)return;
   if(uiBusy){uiDirty=true;return;}
   if(Date.now()<uiRetryAfter){for(const nodes of pending.values())for(const n of nodes)browserTranslationFailure(n);return;}
   uiBusy=true;
   let total=0;const batch=[...pending.keys()].slice(0,24).filter(s=>{total+=s.length;return total<=5500;});
   const guarded=batch.map(raw=>protectedText(raw));
   const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),22000);
   try{
     const response=await fetch(api()+'/api/mobile_voice/translate-ui',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texts:guarded.map(x=>x.value)}),signal:ctl.signal});
     const result=await response.json();if(!response.ok||result.status!=='success'||result.translations?.length!==batch.length)throw Error('ui_translation');
     batch.forEach((raw,i)=>{
       let translated=result.translations[i];for(const [tag,value] of guarded[i].restore)translated=translated.split(tag).join(value);
       uiCache.set(raw,translated);
       for(const n of pending.get(raw)||[])if(uiLanguage(n)==='en'&&n.isConnected&&uiOriginal.get(n)===raw&&n.textContent===uiRendered.get(n))writeUI(n,translated);
     });
   }catch(_){uiRetryAfter=Date.now()+30000;for(const nodes of pending.values())for(const n of nodes)if(n.isConnected&&uiLanguage(n)==='en')browserTranslationFailure(n);}
   finally{clearTimeout(timer);uiBusy=false;if(uiDirty||pending.size>batch.length)queueUI();}
 }
 const placeholderOriginal=new WeakMap();
 let languageRefreshTimer=null,languageRefreshing=false,languageObserver=null;
 const languageObservation={subtree:true,childList:true,characterData:true};
 function scheduleLanguageRefresh(){
   if(languageRefreshTimer!==null)return;
   languageRefreshTimer=setTimeout(()=>{languageRefreshTimer=null;prepareEnglish();},80);
 }
 function prepareEnglish(){
   if(languageRefreshing){scheduleLanguageRefresh();return;}
   languageRefreshing=true;
   // Own synchronous DOM writes must not trigger another observer pass.
   languageObserver?.disconnect();
   try{refreshEnglishNow();}
   finally{languageRefreshing=false;if(languageObserver&&document.body)languageObserver.observe(document.body,languageObservation);}
 }
 function refreshEnglishNow(){
   syncContactHints();stabilizeDialogueControls();
   protectDialogLanguage();
   prepareSelfPayBrowser();
   document.querySelectorAll('#bookingForm input[placeholder],#doubts-livescan-v2 input[placeholder]').forEach(input=>{
     if(!placeholderOriginal.has(input))placeholderOriginal.set(input,input.getAttribute('placeholder'));
     const raw=placeholderOriginal.get(input);const value=uiLanguage(input)==='en'?(localUI(raw)||'Enter your details'):raw;
     if(input.getAttribute('placeholder')!==value)input.setAttribute('placeholder',value);
   });
   document.querySelectorAll('.dm-manual-feedback').forEach(el=>{
     const p=el.querySelector('p'),b=el.querySelector('button');
     const text=tr('已選擇打字／語音輸入。請在下方輸入姓名，或按「說話」。','Type or speak selected. Enter your full name below, or select Speak.');
     if(p&&p.textContent!==text)p.textContent=text;
     const label=tr('更換輸入方式','Change input method');if(b&&b.textContent!==label)b.textContent=label;
   });
   if(dialogUILanguage()==='en')document.querySelectorAll('#chat-body .ai-msg,#selfpay-chat-body .selfpay-message.ai').forEach(translateMessage);
   void translateUI();
 }
 function installManualFeedback(){
   document.addEventListener('click',event=>{
     const button=event.target.closest?.('.doubts-idscan-choice-manual');if(!button)return;
     const wrap=button.closest('.doubts-idscan-choice-wrap');if(!wrap)return;
     wrap.querySelectorAll('.doubts-idscan-choice-btn').forEach(b=>b.hidden=true);
     wrap.classList.add('dm-manual-selected');
     let feedback=wrap.querySelector('.dm-manual-feedback');
     if(!feedback){feedback=document.createElement('div');feedback.className='dm-manual-feedback';feedback.setAttribute('role','status');wrap.append(feedback);}
     feedback.replaceChildren();const text=document.createElement('p');text.textContent=tr('已選擇打字／語音輸入。請在下方輸入姓名，或按「說話」。','Type or speak selected. Enter your full name below, or select Speak.');feedback.append(text);
     const change=document.createElement('button');change.type='button';change.textContent=tr('更換輸入方式','Change input method');feedback.append(change);
     change.onclick=()=>{wrap.classList.remove('dm-manual-selected');wrap.querySelectorAll('.doubts-idscan-choice-btn').forEach(b=>b.hidden=false);feedback.remove();wrap.querySelector('.doubts-idscan-choice-manual')?.focus();};
     const input=document.getElementById('chat-input');input?.focus({preventScroll:true});input?.scrollIntoView?.({block:'nearest',behavior:'smooth'});
   });
 }
 let selfPayQueue=Promise.resolve(),selfPayEpoch=0,selfPayRequest=null;
 async function selfPayQuestion(raw){
   const item=typeof currentSelfPayItem!=='undefined'?currentSelfPayItem:null;
   const bill=typeof currentSelfPayBillable!=='undefined'?currentSelfPayBillable:null;
   const facts={};
   if(item)for(const key of ['id','name','description','plain_explanation','price','price_note'])if(item[key]!==undefined)facts[key]=String(item[key]).slice(0,500);
   if(bill)for(const key of ['name','price','type'])if(bill[key]!==undefined)facts['billable_'+key]=String(bill[key]).slice(0,250);
   status(tr('正在理解您的問題','Understanding your question'));
   const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),21000);selfPayRequest=ctl;
   try{
     const r=await fetch(api()+'/api/mobile_voice/selfpay-question',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:protectedText(raw).value.slice(0,700),context:JSON.stringify(facts).slice(0,3000)}),signal:ctl.signal});
     const result=await r.json();if(!r.ok||result.status!=='success'||!result.text)throw Error('selfpay_question');
     return result;
   }finally{clearTimeout(timer);if(selfPayRequest===ctl)selfPayRequest=null;}
 }
 function installSelfPayReliability(){
   const flow=window.DoubtsIdScanFlow;
   if(flow&&!flow.dmPhonePrompt){
     const original=flow.accept;flow.dmPhonePrompt=true;
     flow.accept=function(...args){const ok=original.apply(this,args);if(ok)setTimeout(()=>{
       if(typeof currentStep!=='undefined'&&currentStep==='phone')void speak('姓名、證號及生日已核對。接下來請輸入您的手機號碼。');
     },350);return ok;};
   }
   const observeRoot=document.getElementById('selfpay-chat-overlay')||document.getElementById('selfpay-chat-body')?.parentElement||document.getElementById('chat-widget');
   if(observeRoot){
     languageObserver=new MutationObserver(records=>{
       // Never perform translation or DOM writes inside a mutation microtask.
       const relevant=records.some(record=>{
         const el=record.target.nodeType===1?record.target:record.target.parentElement;
         if(!el||el.closest('script,style,.dm-toolbar,.dm-en,.dm-original,.dm-manual-feedback'))return false;
         return !!el.closest('#selfPayModal,#selfPayDetailDialog,#chat-body,#selfpay-chat-body,#selfpay-panel,#selfpay-chat-options,#chat-header,.selfpay-chat-header,#bookingForm,#doubts-livescan-v2,#header,#main,#scrollspyFooter,#plan_display')||[...record.addedNodes].some(n=>n.nodeType===1&&n.matches?.('#selfPayModal,#selfPayDetailDialog,#doubts-livescan-v2,#selfpay-panel'));
       });
       if(relevant)scheduleLanguageRefresh();
     });
     languageObserver.observe(document.body,languageObservation);
   }
   document.addEventListener('click',e=>{if(e.target.closest?.('#selfPayModal,#selfpay-panel,#selfpay-chat-options'))queueUI();},true);
   installManualFeedback();prepareEnglish();
 }

 let catalogueTurn=0,catalogueRequest=null,lastItemIds=[];
 function installCatalogueQuestions(){
   const bridge=window.ClinicDialogueV10;
   if(!bridge||bridge.dmCatalogueBuild)return;
   const previous=bridge.homePreflight;
   if(typeof previous!=='function')return;
   bridge.dmCatalogueBuild='7.4';

   let history=[],lastRequestedPlans=[];
   bridge.homePreflight=async function(raw,parsed){
     const step=typeof currentStep!=='undefined'?currentStep:'';
     const input=String(raw||'').trim();
     // DOUBTS-PLAN-SELECTION-V1
     // Exact choices belong to booking; never pass model intent or stale QA data through.
     if(step==='plan'){
       const choiceInput=input.normalize('NFKC').trim().replace(/[。！!．.]+$/u,'').trim();
       const choice=choiceInput.match(/^(?:(?:(?:我想|我要|請幫我|幫我|決定|直接|選擇|選|要|預約)){0,2}(?:選|預約)?(?:第)?([ABC123一二三壹貳參])(?:個|號|種)?(?:方案)?(?:就好|好了|喔|哦)?|(?:(?:i\s+)?(?:choose|select|want)(?:\s+(?:the|plan))?\s+|(?:the\s+)?plan\s+)?([abc123]|one|two|three|first|second|third)(?:\s+plan)?)$/i);
       if(choice){
         const token=(choice[1]||choice[2]).toUpperCase();
         const code=({1:'A',2:'B',3:'C','一':'A','二':'B','三':'C','壹':'A','貳':'B','參':'C',ONE:'A',TWO:'B',THREE:'C',FIRST:'A',SECOND:'B',THIRD:'C'})[token]||token;
         ++catalogueTurn;catalogueRequest?.abort();catalogueRequest=null;stopAll();
         history=[];lastRequestedPlans=[];
         return {handled:false,parsed:{data:{plan:code}}};
       }
     }
     if(step!=='plan'||/^(?:yes|no|back|restart|上一步|重新開始|正確|不正確)$/i.test(input))return previous.call(this,raw,parsed);
     const turn=++catalogueTurn;catalogueRequest?.abort();const controller=new AbortController();catalogueRequest=controller;
     const timer=setTimeout(()=>controller.abort(),25000);status(tr('正在核對方案並回答您的問題','Checking the plans and answering your question'));
     try{
       const response=await fetch(api()+'/api/mobile_voice/plan-dialogue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:protectedText(input).value.slice(0,700),language:dialogUILanguage(),history:history.slice(-4),previous_plans:lastRequestedPlans}),signal:controller.signal});
       const result=await response.json();if(!response.ok||result.status!=='success'||!result.text)throw Error('dialogue');
       if(turn!==catalogueTurn||step!==(typeof currentStep!=='undefined'?currentStep:''))return {handled:true};
       history.push({question:protectedText(input).value.slice(0,700),answer:result.text.slice(0,2000)});history=history.slice(-4);lastRequestedPlans=result.plans||[];
       window.addMsg(esc(input),'user');window.addMsg(esc(result.text).replace(/\n/g,'<br>'),'ai');
     }catch(_){if(turn===catalogueTurn)window.addMsg(tr('這次無法取得方案問答，請稍後重試。您的預約資料仍保留。','The plan question service is unavailable. Please retry shortly. Your booking details are preserved.'),'ai');}
     finally{clearTimeout(timer);if(catalogueRequest===controller)catalogueRequest=null;}
     return {handled:true};
   };

 }


 function setInterfaceLanguage(next){
   if(!['zh','en'].includes(next))return;
   interfaceLanguage=next;save('doubts-site-language-v1',next);
   document.documentElement.lang=next==='en'?'en':'zh-Hant';
   document.querySelectorAll('.dm-site-language select').forEach(el=>el.value=next);
   updateLabels();decorateChoices();prepareEnglish();
 }
 function installSiteLanguage(){
   const nav=document.querySelector('#scrollspyNav > .container');
   if(nav&&!document.getElementById('dm-site-language')){
     const wrap=document.createElement('label');wrap.id='dm-site-language';wrap.className='dm-site-language';
     const label=document.createElement('span');label.className='dm-visually-hidden';label.textContent='網站語言 / Website language';
     const select=document.createElement('select');select.setAttribute('aria-label','網站語言 / Website language');
     for(const [value,text] of [['zh','繁體中文'],['en','English']]){const option=document.createElement('option');option.value=value;option.textContent=text;option.lang=value==='zh'?'zh-Hant':'en';select.append(option);}
     select.value=interfaceLanguage;select.addEventListener('change',()=>setInterfaceLanguage(select.value));
     wrap.append(label,select);nav.append(wrap);
   }
   // Keep the original node for existing event bindings; remove its visual and keyboard entry points.
   const floating=document.getElementById('open-chat-btn');
   if(floating){floating.hidden=true;floating.setAttribute('aria-hidden','true');floating.tabIndex=-1;}
   document.documentElement.lang=interfaceLanguage==='en'?'en':'zh-Hant';
 }

 function init(){
   document.body.classList.add('dm-v7');installSiteLanguage();
   const widget=document.getElementById('chat-widget'),chat=document.getElementById('chat-body');
   if(widget&&chat)attachToolbar(widget,chat);
   const formBody=document.getElementById('selfpay-chat-body');if(formBody)attachToolbar(formBody.parentElement,formBody);
   if(typeof window.addMsg==='function'){
     const original=window.addMsg;window.addMsg=function(text,type){
       if(type==='ai')text=cleanChecks(text);
       if(type==='user'&&originalInput&&plain(text)===canonicalValue)text=esc(originalInput);
       const result=original.call(this,text,type);
       if(type==='ai'){const node=[...chat.querySelectorAll('.ai-msg')].at(-1);originalReply(node);markError(node);translateMessage(node);}syncContactHints();return result;
     };
   }
   if(typeof window.addSelfPayAIMessage==='function'){
     const original=window.addSelfPayAIMessage;window.addSelfPayAIMessage=function(...args){args[0]=cleanChecks(args[0]);const result=original.apply(this,args);originalReply(result);markError(result);translateMessage(result);syncContactHints();return result;};
   }
   if(typeof window.handleSelfPayAnswer==='function'){
     const original=window.handleSelfPayAnswer;
     window.handleSelfPayAnswer=function(value,display){
       const epoch=selfPayEpoch;
       const run=async()=>{
         if(epoch!==selfPayEpoch)return;
         const raw=String(value??'');
         const internal=(display!==undefined&&raw!==String(display))||/^(?:[a-z]+:[A-Za-z0-9_-]+|[a-z]+(?:-[a-z0-9]+)+|add|finish|continue|yes|no|cancel)$/i.test(raw);
         const mode=typeof selfPayChatMode!=='undefined'?selfPayChatMode:'';
         if(!internal&&['category','item','afterAdd'].includes(mode)&&!/^(?:加入|刪除|取消|完成|選好了|繼續|回分類|修改預算|查看已選項目|查看與修改已選項目)$/i.test(raw.trim())){
           window.addSelfPayUserMessage?.(display??raw);
           try{
             const reply=await selfPayQuestion(raw);
             if(epoch!==selfPayEpoch)return;
             window.addSelfPayAIMessage(esc(reply.text).replace(/\n/g,'<br>'));
             if(reply.category_ids?.length&&typeof showSelfPayOptions==='function'){
               const labels={cardiovascular:'心臟與血管',pulmonary:'肺部與呼吸',hepatobiliary_gastrointestinal:'肝膽與腸胃',renal_urology:'腎臟與泌尿',other_value_added:'抽血與全身健康'};
               showSelfPayOptions(reply.category_ids.map(id=>({label:labels[id],value:'category:'+id})));
             }
           }catch(_){if(epoch!==selfPayEpoch)return;window.addSelfPayAIMessage('這次未能完成問題判斷。您剛才的問題已保留，請稍後再試，或先查看檢查清單；沒有更改已選項目。');}
           queueUI();return;
         }
         if(!internal){
           try{value=await canonicalInput(raw,mode);}
           catch(_){status(tr('無法理解英文內容，請保留文字並重試','Could not translate your answer. Please try again'),true);return;}
         }
         return original.call(this,value,display);
       };
       const task=selfPayQueue.then(run);selfPayQueue=task.catch(()=>{});return task;
     };
   }
   installSpeechAPI();installCatalogueQuestions();installSelfPayReliability();
   for(const key of ['closeChat','closeSelfPayChat'])if(typeof window[key]==='function'){
     const original=window[key];window[key]=function(...args){++selfPayEpoch;selfPayRequest?.abort();++catalogueTurn;catalogueRequest?.abort();cancelRecording();stopAll();return original.apply(this,args);};
   }
   updateLabels();
   if(dialogUILanguage()==='en')document.querySelectorAll('#chat-body .ai-msg,#selfpay-chat-body .selfpay-message.ai').forEach(translateMessage);
   document.querySelectorAll('.dm-toolbar').forEach(p=>p.style.setProperty('--dm-controls-height','122px'));
   const resize=()=>document.documentElement.style.setProperty('--dm-viewport-height',(window.visualViewport?.height||window.innerHeight)+'px');
   resize();window.visualViewport?.addEventListener('resize',resize);window.addEventListener('resize',resize);
   document.addEventListener('focusin',e=>{if(e.target.matches('#chat-input,#selfpay-chat-input'))document.documentElement.classList.add('dm-keyboard');});
   document.addEventListener('focusout',e=>{if(e.target.matches('#chat-input,#selfpay-chat-input'))document.documentElement.classList.remove('dm-keyboard');});
   document.addEventListener('input',e=>{if(e.target.matches('#chat-input,#selfpay-chat-input'))e.target.removeAttribute('aria-invalid');});
 }
 // Capture before target/document handlers. No native recognizer is started by this path.
 for(const event of ['pointerdown','pointerup','pointercancel','click'])window.addEventListener(event,e=>{
   const button=e.target?.closest?.('#chatMicBtn,#selfpay-mic-btn');
   if(button){e.stopImmediatePropagation();if(event==='click'){e.preventDefault();void microphone(button.id);}return;}
   if(event==='click'&&e.target?.closest?.('#selfpay-close-btn,.chat-close-btn,#dls2-close')){cancelRecording();stopAll();}
   if(event==='click'&&e.target?.closest?.('#chatSendBtn,#selfpay-send-btn')){if(recordState!=='idle')cancelRecording();stopAll();}
 },true);
 window.addEventListener('keypress',e=>{
   if(e.key!=='Enter'||e.isComposing||e.target?.id!=='chat-input'||typeof e.target.onkeypress!=='function')return;
   e.preventDefault();e.stopImmediatePropagation();if(recordState!=='idle')cancelRecording();stopAll();void e.target.onkeypress({key:'Enter',preventDefault(){}});
 },true);
 window.addEventListener('pagehide',()=>{cancelRecording();stopAll();});
 window.DoubtsMobileV7={catalogueBuild:"7.6.7",siteLanguageBuild:"7.6.8",setInterfaceLanguage,getInterfaceLanguage:()=>interfaceLanguage,autoSpeak,canonicalInput,englishAmount,translate,setLanguage,getLanguage:()=>language,stopAll,speak,pause,
   getRecordingState:()=>recordState,microphone,cancelRecording,markError};
 installSpeechAPI();
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
