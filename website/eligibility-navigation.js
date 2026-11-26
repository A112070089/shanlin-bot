/* Shared entry routing; no booking submissions or storage writes. */
(()=>{
 'use strict';
 const query=new URLSearchParams(location.search);
 const clinic=['shanlin','yidian'].includes(query.get('clinic'))?query.get('clinic'):'yidian';
 const home=(action,hash)=>{
   const url=new URL('index.html',location.href);
   url.searchParams.set('clinic',clinic);
   if(action)url.searchParams.set('nav',action);
   if(hash)url.hash=hash;
   return url;
 };
 const words={
  "填寫資料": "Enter details",
  "資格確認": "Eligibility",
  "確認資料": "Review details",
  "老人健檢資格確認": "Senior Checkup Eligibility",
  "請確認以下三項資格。符合資格後，即可進入下一步核對預約資料。": "Please confirm the three eligibility requirements below before reviewing your appointment details.",
  "您是設籍台北市的市民嗎？": "Is your household registration in Taipei City?",
  "您是年滿65歲以上長者或55歲以上原住民嗎？": "Are you aged 65 or older, or an Indigenous person aged 55 or older?",
  "您若不符合受檢資格及未依照特約醫事機構規定辦理登記，醫事機構將取消已取號後之登記資格，您同意嗎？": "Do you agree that the medical institution may cancel your registration if you do not meet the checkup eligibility requirements and have not registered according to its rules?",
  "下一步將核對您的預約資料。": "Next, review your appointment details.",
  "下一步：確認資料　→": "Next: Review details →",
  "是": "Yes",
  "不是": "No",
  "同意": "Agree",
  "不同意": "Disagree"
};
 function updateEligibilityLanguage(){
   const main=document.getElementById('eligibility-main');if(!main)return;
   let english=window.DoubtsMobileV7?.getInterfaceLanguage?.()==='en';
   if(!window.DoubtsMobileV7){try{english=localStorage.getItem('doubts-site-language-v1')==='en';}catch(_){}}
   main.lang=english?'en':'zh-Hant';
   for(const node of main.querySelectorAll('[data-eligibility-text]')){
     const zh=node.dataset.eligibilityText;
     node.textContent=english?(words[zh]||zh):zh;
   }
 }
 function init(){
   const eligibility=!!document.getElementById('eligibility-main');
   const nav=document.getElementById('scrollspyNav');
   if(nav){
     const brand=nav.querySelector('.navbar-brand');if(brand)brand.href=home();
     for(const link of nav.querySelectorAll('.navbar-nav .nav-link')){
       const label=link.textContent.trim();
       // Use the same homepage content and functions, without carrying patient parameters.
       if(label==='首頁'||label==='Home')link.href=home();
       if(label==='預約健檢'||label==='Book a Checkup')link.href=home(null,'scrollspyAppointment');
       if(label==='聯絡資訊'||label==='Contact')link.href=home(null,'scrollspyFooter');
       if(link.dataset.homeAction==='selfpay'||label==='自費項目'||label==='Self-pay Tests')link.href=home('selfpay');
     }
     const admin=nav.querySelector('#adminLoginLink');
     if(admin){const url=new URL('/pilot',location.origin);url.searchParams.set('clinic',clinic);url.searchParams.set('view','admin');admin.href=url;}
   }
   if(eligibility){
     updateEligibilityLanguage();
     document.addEventListener('change',event=>{if(event.target.matches('.dm-site-language select'))updateEligibilityLanguage();});
     // Enter in the eligibility form follows the existing eligibility checks.
     document.getElementById('frm2')?.addEventListener('submit',event=>{event.preventDefault();window.goNextStep();});
   }else if(query.get('nav')==='selfpay'){
     // Open the existing homepage browser, never a duplicated catalogue.
     let attempts=0;
     const open=()=>{
       if(typeof window.openSelfPayBrowser==='function'){
         window.openSelfPayBrowser();
         const clean=new URL(location.href);clean.searchParams.delete('nav');history.replaceState(history.state,'',clean);
       }else if(++attempts<40)setTimeout(open,250);
     };
     open();
   }
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
