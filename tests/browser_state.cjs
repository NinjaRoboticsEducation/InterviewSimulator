// Run the actual startup path, including a stale browser pointer to a cancelled run.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(),calls=[];let bodies=[];
const el=id=>{if(!elements.has(id))elements.set(id,{value:id==='locale'?'en':'',textContent:'',hidden:false,disabled:false,options:[],replaceChildren(){},append(){}});return elements.get(id);};
const context=vm.createContext({
 document:{getElementById:el,querySelector:()=>({content:'token'}),documentElement:{},createElement:()=>({append(){}})},
 window:{addEventListener(){}},localStorage:{setItem(){},getItem(){return 'cancelled-old';},removeItem(){}},
 navigator:{},Headers,AbortController,DOMException,crypto:{randomUUID:()=> 'submission-one'},setTimeout:()=>1,clearTimeout(){},
 fetch:async(path,options)=>{calls.push(path);if(path==='/api/speech')return {ok:true,json:async()=>({})};if(path==='/api/opportunities')return {ok:true,json:async()=>[]};if(path==='/api/runs')return {ok:true,json:async()=>({runs:[]})};bodies.push(options.body);throw new Error('connection lost');}
});
vm.runInContext(fs.readFileSync('src/interview_simulator/static/app.js','utf8'),context);
(async()=>{
 await vm.runInContext('initialization',context);
 assert.equal(vm.runInContext('run',context),null,'startup must not adopt an interview');
 assert.equal(calls.some(path=>/cancelled-old|api\/active|api\/recent/.test(path)),false);
 vm.runInContext("run={run_id:'run-a',question:{ordinal:1,event_id:'event-a'},locale:'en',status:'active'};acknowledged=true;el('answer').value='Original answer';",context);
 await vm.runInContext('send(false)',context);assert.equal(el('answer').disabled,true);
 el('answer').value='Changed answer';await vm.runInContext('send(true)',context);
 assert.equal(bodies.length,2);assert.equal(bodies[0],bodies[1],'retry must preserve exact answer and submission ID');
 context.fetch=async()=>({ok:true,json:async()=>({status:'running',processed:1,assessed:1})});
 vm.runInContext("pendingSubmission=null;run={run_id:'run-a',question:null,locale:'en',status:'answered'};busy=false;",context);
 await vm.runInContext("pollReport('run-a')",context);assert.equal(el('start').disabled,true);
 vm.runInContext("busy=false;run={run_id:'run-b',question:null,locale:'en'};controls();",context);
 await vm.runInContext("pollReport('run-a')",context);assert.equal(el('start').disabled,false);
 vm.runInContext("drafts.set('old','old text');rawTranscript='old transcript';chunks=['old'];el('report').textContent='old report';resetSession();",context);
 assert.equal(el('report').textContent,'');assert.equal(vm.runInContext('drafts.size',context),0);assert.equal(vm.runInContext('rawTranscript',context),null);
 console.log('Browser initialization, cancelled pointer, idempotent retry, stale polling and reset passed');
 const nav=['connection-screen','models-screen','job-screen'].map(id=>({dataset:{screen:id},disabled:false,setAttribute(){},removeAttribute(){}}));
 context.document.querySelectorAll=selector=>selector==='[data-screen]'?nav:[];
 vm.runInContext("run={run_id:'locked',status:'active',locale:'ja'};busy=false;window.interviewUiLocale='en';controls();",context);
 assert.equal(nav.every(button=>button.disabled),true);
 assert.equal(el('ui-locale').disabled,true);
 assert.equal(vm.runInContext("goScreen('models-screen')",context),false);
 el('ui-locale').value='ja';vm.runInContext("el('ui-locale').onchange()",context);
 assert.equal(el('ui-locale').value,'en','language is frozen until cancellation');
 vm.runInContext('resetSession()',context);assert.equal(nav.some(button=>button.disabled),false);
 context.fetch=async()=>({ok:false,status:500,json:async()=>{throw new SyntaxError('HTML response')}});
 await assert.rejects(vm.runInContext("api('/synthetic-error')",context),error=>error.status===500&&!error.message.includes('Connection lost'));
 const message=vm.runInContext("failureText({code:'TEMPORARY_UNAVAILABLE',message:'503 internal details'})",context);
 assert.match(message,/Switch to a local AI model or another provider/);assert.doesNotMatch(message,/503/);
 console.log('Navigation lock, frozen language, non-JSON server error and provider guidance passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
