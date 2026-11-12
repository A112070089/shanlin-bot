const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(__dirname+'/../website/yidian_speech.js','utf8');
const sent=[], els={};
function element(id) {
 if(!els[id]) els[id]={id,style:{},dataset:{},value:'',classList:{contains:()=>true},handlers:{},setAttribute(k,v){this[k]=v},addEventListener(k,f){this.handlers[k]=f},insertBefore(){this.installed=true},querySelector(s){return s==='#selfpay-chat-body'?element('selfpay-chat-body'):null},textContent:''};
 return els[id];
}
const document={readyState:'complete',querySelector:s=>s==='.selfpay-chat-box'?element('box'):null,querySelectorAll:()=>[],createElement:()=>({id:'',innerHTML:'',setAttribute(){}}),getElementById(id){if(id==='yidian-speech-controls' && !els.box?.installed) return null;return element(id)}};
const storage={'yidian-voice-language-v1':'nan'};
const window={SITE:{isLocal:true,bookingApi:'http://127.0.0.1:8000'},localStorage:{getItem:k=>storage[k]??null,setItem:(k,v)=>{storage[k]=v}},speechSynthesis:{cancel(){},speak(){}},SpeechSynthesisUtterance:function(t){this.text=t},URL:{createObjectURL:()=> 'blob:dummy',revokeObjectURL(){}},Audio:function(){this.pause=()=>{};this.removeAttribute=()=>{};this.load=()=>{};this.play=async()=>{}}};
const mockFetch=async(u,opt)=>{const p=JSON.parse(opt.body);sent.push({url:u,payload:p});return {ok:true,status:200,headers:{get:(k)=>k==='content-type'?'audio/wav':'draft'},blob:async()=>({size:42})}};
vm.runInNewContext(code,{window,document,localStorage:window.localStorage,URL:window.URL,Audio:window.Audio,SpeechSynthesisUtterance:window.SpeechSynthesisUtterance,fetch:mockFetch,AbortController,console,Number});
const api=window.YidianSpeech;
(async()=>{
 await api.autoSpeak('這項檢查是驗尿，幫助了解腎臟的情形。');
 assert.equal(sent.at(-1).url.endsWith('/api/taigi_tts/text'),true);
 assert.equal(sent.at(-1).payload.source,'ai_reply');
 await api.autoSpeak('✅ 已加入「靜態心電圖 (EKG)」。本項價格：NT$200目前共選擇 1 項。原定預算：NT$5,000目前合計：NT$200預算尚餘：NT$4,800');
 assert.equal(sent.at(-1).url.endsWith('/api/taigi_tts/dialogue'),true);
 await api.autoSpeak('好的，請選擇下一個想了解的自費檢查分類。');
 assert.equal(sent.at(-1).url.endsWith('/api/taigi_tts/text'),true);
 assert.equal(sent.at(-1).payload.text,'好的，請選擇下一個想了解的自費檢查分類。');
 await api.autoSpeak('新的一般回覆，需要用台語講出來。');
 assert.equal(sent.at(-1).url.endsWith('/api/taigi_tts/text'),true);
 console.log('PASS: known receipt/dialogue and all new AI replies routed to Taiwanese TTS when local translator is available.');
})().catch(e=>{console.error(e);process.exitCode=1});
