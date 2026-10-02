// Exercise browser audio failures and cancellation without using a real microphone.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(),timers=new Map();let timer=0,stopped=0,resolvePermission,clock=0;
const el=id=>{if(!elements.has(id))elements.set(id,{value:id==='locale'?'en':'',textContent:'',hidden:false,disabled:false,options:[],replaceChildren(){},append(){}});return elements.get(id);};
const context=vm.createContext({
 document:{getElementById:el,querySelector:()=>({content:'token'}),documentElement:{}},
 window:{addEventListener(){},workspaceText:(key,args={})=>key.replace(/\{(\w+)\}/g,(_,k)=>String(args[k]??'{'+k+'}'))},localStorage:{setItem(){},getItem(){return null},removeItem(){}},
 navigator:{mediaDevices:{getUserMedia:()=>new Promise(resolve=>{resolvePermission=resolve;})}},
 MediaRecorder:class {static isTypeSupported(type){return type==='audio/mp4';}},
 Audio:class {play(){return Promise.reject(new Error('Playback blocked'));}pause(){}},
 performance:{now:()=>clock},Headers,AbortController,DOMException,Blob,FormData,URL,crypto:{randomUUID:()=> 'one'},
 setTimeout:fn=>{timers.set(++timer,fn);return timer;},clearTimeout:id=>timers.delete(id),
 fetch:async(path)=>({ok:true,json:async()=>path==='/api/speech'?{}:path==='/api/runs'?{runs:[]}:[],blob:async()=>new Blob(['synthetic'],{type:'audio/wav'})})
});
const source=fs.readFileSync('src/interview_simulator/static/app.js','utf8');
vm.runInContext(source,context);
(async()=>{
 await vm.runInContext('initialization',context);
 vm.runInContext("run={run_id:'r',question:{ordinal:1,event_id:'e'},locale:'en'};speechReady={asr_ready:true,tts_by_language:{en:true}};acknowledged=true;",context);
 await vm.runInContext("play('greeting')",context);
 assert.equal(el('status').textContent,'Playback blocked');
 assert.equal(el('record').disabled,false,'playback failure must release controls');
 const request=vm.runInContext("el('record').onclick()",context);
 assert.match(el('status').textContent,/Waiting for microphone/);
 vm.runInContext("el('stop').onclick()",context);
 await request;
 assert.equal(el('record').disabled,false,'cancel permission prompt must release controls');
 resolvePermission({getTracks:()=>[{stop(){stopped++;}}]});await Promise.resolve();await Promise.resolve();
 assert.equal(stopped,1,'late permission must not leave microphone running');
 context.navigator.mediaDevices.getUserMedia=async()=>{throw new Error('NotAllowedError');};
 await vm.runInContext("el('record').onclick()",context);
 assert.match(el('status').textContent,/microphone permissions/);
 assert.equal(el('submit').disabled,false);
 context.navigator.mediaDevices=undefined;
 await vm.runInContext("el('record').onclick()",context);
 assert.match(el('status').textContent,/unavailable in this browser/);
 context.navigator.mediaDevices={getUserMedia:()=>new Promise(()=>{})};
 const timeout=vm.runInContext("el('record').onclick()",context);
 [...timers.values()].forEach(fn=>fn());await timeout;
 assert.match(el('status').textContent,/timed out/);
 assert.equal(el('submit').disabled,false,'permission timeout must release controls');
 let chosenMime,uploadedName,transcription;
 context.MediaRecorder=class {
  static isTypeSupported(type){return type==='audio/mp4';}
  constructor(stream,options){chosenMime=options.mimeType;this.mimeType=chosenMime;this.state='inactive';}
  start(){this.state='recording';}
  stop(){this.state='inactive';this.ondataavailable({data:new Blob(['audio'])});transcription=this.onstop();}
 };
 context.navigator.mediaDevices.getUserMedia=async()=>({getTracks:()=>[{stop(){stopped++;}}]});
 context.fetch=async(path,options)=>{uploadedName=options.body.get('audio').name;return {ok:true,json:async()=>({text:'Synthetic confirmed transcript'})};};
 await vm.runInContext("el('record').onclick()",context);
 assert.equal(chosenMime,'audio/mp4','choose a supported recording type for Safari');
 assert.match(el('status').textContent,/Recording/);
 vm.runInContext("el('stop').onclick()",context);await transcription;
 assert.equal(uploadedName,'answer.m4a');
 assert.equal(el('answer').value,'Synthetic confirmed transcript');
 assert.equal(el('submit').disabled,false);
 el('answer').value='My edited base answer';
 await vm.runInContext("recordAnswer(true)",context);
 assert.equal(el('answer').value,'My edited base answer','extension preserves base before success');
 vm.runInContext("el('stop').onclick()",context);await transcription;
 assert.equal(el('answer').value,'My edited base answer\n\nSynthetic confirmed transcript');
 await vm.runInContext("recordAnswer(true)",context);
 vm.runInContext("el('stop').onclick()",context);await transcription;
 assert.equal(el('answer').value,'My edited base answer\n\nSynthetic confirmed transcript\n\nSynthetic confirmed transcript');
 await vm.runInContext("recordAnswer(false)",context);
 assert.match(el('recording-clock').textContent,/03:00/);
 clock=150000;vm.runInContext('clearTimeout(recordTimer);tickCountdown()',context);
 assert.match(el('recording-clock').textContent,/00:30/);
 assert.match(el('recording-warning').textContent,/30 seconds/);
 clock=180000;vm.runInContext('clearTimeout(recordTimer);tickCountdown()',context);await transcription;
 assert.equal(el('answer').value,'Synthetic confirmed transcript','record replaces previous answer');
 assert.equal(el('recording-clock').hidden,true);
 el('answer').value='😀'.repeat(5999);vm.runInContext('controls()',context);
 assert.equal(el('extend-record').disabled,false,'count Unicode characters like Python');
 await vm.runInContext('recordAnswer(true)',context);vm.runInContext("el('stop').onclick()",context);await transcription;
 assert.equal(el('submit').disabled,true);assert.equal(el('extend-record').disabled,true);
 assert.ok(el('answer').value.endsWith('Synthetic confirmed transcript'),'over-limit draft is preserved');
 el('answer').value='Keep this edited answer';
 context.fetch=async()=>{throw new Error('Synthetic network failure');};
 await vm.runInContext('recordAnswer(true)',context);vm.runInContext("el('stop').onclick()",context);await transcription;
 assert.equal(el('answer').value,'Keep this edited answer','failure preserves the edited base');
 console.log('Repeated extensions, replacement, timer, Unicode length, overflow and failure preservation passed');
 console.log('Browser voice failure, cancellation, and recording checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
