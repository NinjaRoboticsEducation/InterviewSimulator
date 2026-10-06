let run=null, recorder=null, chunks=[], stream=null, submitting=false, pendingSubmission=null, answerMode='text', rawTranscript=null;
let reviewCursor=null; const drafts=new Map();
const el=id=>document.getElementById(id), w=(key,args={})=>window.workspaceText?.(key,args)||key, msg=s=>el('status').textContent=s;
let sessionEpoch=0, preparationRequest=null, preparing=false;const requests=new Set();
const providerAdvice='The selected AI model is unavailable or could not complete this task. Switch to a local AI model or another provider. Your saved work is kept.';
function workspaceLocked(){return busy||window.modelTestRunning||preparing||!!run&&['preparing','ready','active','paused','preparation_failed'].includes(run.status);}
window.workspaceLocked=workspaceLocked;
const words={
en:{title:'Interview Simulator',intro:'Choose a prepared opportunity. Review your selected text providers before practice.',start:'Start practice',paused:'Practice paused. Select Resume to continue.',cancelled:'Practice cancelled. Start a new run to practice again.',fixed:'Fixed practice',adaptive:'Adaptive question order',play:'Play question',record:'Record answer',stop:'Stop recording',answer:'Confirm or correct your answer before submitting',submit:'Confirm answer',skip:'Skip question',report:'Generate report',history:'Previous practice runs',notReady:'not ready',greeting:'Play greeting',closing:'Play closing',inProgress:'Interview in progress',readyReport:'All ten questions answered. Generate your report.',transcribing:'Transcribing locally…',review:'Review and correct the transcript, then confirm.',recording:'Recording your answer…',starting:'Starting your selected assessment…',progress:'Report in progress',scored:'scored',processed:'processed',saved:'Saved',retry:'Report generation stopped. Select Generate report to retry saved work.'},
ja:{title:'面接シミュレーター',intro:'準備済みの応募先を選び、練習前にテキスト処理の接続先を確認してください。',start:'練習を開始',paused:'練習を一時停止しました。再開を選んで続けてください。',cancelled:'練習を取り消しました。新しい練習を開始してください。',fixed:'固定練習',adaptive:'適応型の質問順',play:'質問を再生',record:'回答を録音',stop:'録音を停止',answer:'音声認識の文章を確認・修正してから送信してください',submit:'回答を確定',skip:'質問を省略',report:'レポートを作成',history:'過去の練習回数',notReady:'準備未完了',greeting:'挨拶を再生',closing:'締めの言葉を再生',inProgress:'面接練習中',readyReport:'10問が終了しました。レポートを作成してください。',transcribing:'端末内で音声を文字に変換しています…',review:'認識結果を確認・修正してから確定してください。',recording:'回答を録音しています…',starting:'選択したモデルで評価を開始しています…',progress:'レポート作成中',scored:'採点済み',processed:'処理済み',saved:'保存先',retry:'レポート作成が停止しました。「レポートを作成」を押すと保存済みの結果から再開できます。'},
'zh-Hant':{title:'面試模擬器',intro:'請選擇已準備好的應徵機會，並在練習前確認文字處理的供應商。',start:'開始練習',paused:'練習已暫停。請選擇繼續。',cancelled:'練習已取消。請開始新的練習。',fixed:'固定練習',adaptive:'適應式題目順序',play:'播放題目',record:'錄製回答',stop:'停止錄音',answer:'提交前請確認或修正語音辨識文字',submit:'確認回答',skip:'略過此題',report:'產生報告',history:'過去練習次數',notReady:'尚未就緒',greeting:'播放開場白',closing:'播放結語',inProgress:'面試練習進行中',readyReport:'十道題目已完成。請產生報告。',transcribing:'正在本機轉寫語音…',review:'請檢查並修正轉寫文字，再確認回答。',recording:'正在錄製回答…',starting:'正在使用所選模型開始評估…',progress:'正在產生報告',scored:'已評分',processed:'已處理',saved:'已儲存',retry:'報告產生已中斷。按「產生報告」可接續已儲存的結果。'}};
const tr=key=>words[window.uiLocale?.()||'en'][key];
const token=document.querySelector('meta[name="interview-token"]').content;
let busy=false, acknowledged=false, playback=null, recordTimer=null, pollTimer=null;
let speechReady=null, mediaOperation=null;
const voiceWords={
 en:{ready:'Local voice is ready.',missing:'Voice setup is incomplete. Check the local whisper model, ffmpeg, and voice settings; typed answers still work.',browser:'Microphone recording is unavailable in this browser. Open this address in Safari, Chrome, or Edge.',loading:'Preparing local audio…',playing:'Playing audio…',permission:'Waiting for microphone permission. Allow access in your browser, or press Stop.',cancel:'Stop audio / cancel',stopped:'Audio stopped.',timeout:'Audio operation timed out. Check your setup and try again.',permissionError:'Microphone access failed. Check browser and macOS microphone permissions, or type your answer.'},
 ja:{ready:'ローカル音声の準備ができています。',missing:'音声設定が未完了です。whisperモデル、ffmpeg、音声設定を確認してください。文字入力は利用できます。',browser:'このブラウザーでは録音できません。Safari、Chrome、Edgeで開いてください。',loading:'音声を準備しています…',playing:'音声を再生しています…',permission:'マイクの許可を待っています。ブラウザーで許可するか、停止してください。',cancel:'音声を停止／キャンセル',stopped:'音声を停止しました。',timeout:'音声処理がタイムアウトしました。設定を確認してください。',permissionError:'マイクにアクセスできません。ブラウザーとmacOSのマイク許可を確認するか、文字で回答してください。'},
 'zh-Hant':{ready:'本機語音已就緒。',missing:'語音設定尚未完成。請檢查whisper模型、ffmpeg及語音設定；仍可輸入文字回答。',browser:'此瀏覽器無法錄音。請使用Safari、Chrome或Edge開啟。',loading:'正在準備本機語音…',playing:'正在播放語音…',permission:'正在等候麥克風權限。請在瀏覽器允許存取，或按停止。',cancel:'停止語音／取消',stopped:'語音已停止。',timeout:'語音處理逾時。請檢查設定後重試。',permissionError:'無法存取麥克風。請檢查瀏覽器及macOS的麥克風權限，或輸入文字回答。'}};
const vt=key=>voiceWords[window.uiLocale?.()||'en'][key];
function microphoneSupported(){return !!(navigator.mediaDevices?.getUserMedia&&typeof MediaRecorder!=='undefined');}
function voiceStatus(){
 if(!speechReady)return;
 el('voice-status').textContent=!microphoneSupported()?vt('browser'):speechReady.asr_ready&&speechReady.tts_by_language?.[run?.locale||el('locale').value]?vt('ready'):vt('missing');
}

async function response(path, options={}) {
  const headers=new Headers(options.headers||{});
  headers.set('X-Interview-Token',token);
  const epoch=sessionEpoch, controller=new AbortController();requests.add(controller);
  const abort=()=>controller.abort();options.signal?.addEventListener('abort',abort,{once:true});
  try{
    const r=await fetch(path,{...options,signal:controller.signal,headers});
    if(epoch!==sessionEpoch)throw new DOMException('Stale operation','AbortError');
    if(!r.ok){let value;try{value=await r.json();}catch{value={detail:w('The server could not complete this request. Your saved work is kept. Reload and try again.')};}const failure=value.failure;
      const detail=failure?failureText(failure):w(value.detail);
      const error=new Error(detail===value.detail&&window.uiLocale?.()!=='en'?w('Request needs attention. Check settings and saved interview state.'):detail||w('Request needs attention. Check settings and saved interview state.'));
      error.status=r.status;error.failure=failure;throw error;}
    return r;
  }catch(e){if(e.name==='AbortError'||e.status)throw e;throw new Error(w('Connection lost. Check the server and try again.'));}
  finally{requests.delete(controller);options.signal?.removeEventListener('abort',abort);}

}
async function api(path,options={}){const epoch=sessionEpoch,body=await (await response(path,options)).json();if(epoch!==sessionEpoch)throw new DOMException('Stale operation','AbortError');return body;}
function controls(){
  const active=!!run&&['active','paused'].includes(run.status);
  const locked=workspaceLocked();
  if(document.querySelectorAll)for(const button of document.querySelectorAll('[data-screen]'))button.disabled=!!window.modelTestRunning||!!locked&&['connection-screen','models-screen','job-screen'].includes(button.dataset.screen);
  if(el('ui-locale'))el('ui-locale').disabled=!!locked||!!run;
  if(el('home-link'))el('home-link').setAttribute?.('aria-disabled',String(!!locked));
  if(el('review-nav'))el('review-nav').disabled=!!window.modelTestRunning||preparing||!run;
  for(const id of ['play','ceremony'])el(id).disabled=busy||!!pendingSubmission||!speechReady?.tts_by_language?.[run?.locale||el('locale').value];
  el('record').disabled=busy||!!pendingSubmission||!speechReady?.asr_ready||!microphoneSupported();
  for(const id of ['submit','skip'])el(id).disabled=busy||!acknowledged;
  el('answer').disabled=busy||!!pendingSubmission;
  el('start').disabled=busy||active;
  el('job').disabled=busy||active;
  el('locale').disabled=busy||active;el('flow').disabled=busy||active;
  el('evaluate').disabled=busy||run?.status!=='answered';
  for(const id of ['retry-report'])if(el(id))el(id).hidden=!run||run.status!=='answered'||run.report_state==='complete';
  for(const id of ['download-md','download-html','print-report'])if(el(id))el(id).disabled=busy||run?.status!=='answered';
  for(const id of ['previous','review-answers','pause-run','cancel-run','restart-run']) if(el(id))el(id).disabled=busy||!!pendingSubmission;
  if(el('pause-run'))el('pause-run').hidden=!run||run.status!=='active'||run.editable===false;
  if(el('cancel-run')){el('cancel-run').hidden=!preparing&&(!run||(run.editable===false&&run.status!=='preparation_failed')||run.status==='cancelled');el('cancel-run').disabled=busy&&!preparing||!!pendingSubmission;}
  if(el('resume-run'))el('resume-run').hidden=run?.status!=='paused';
  if(el('resume-job'))el('resume-job').hidden=run?.status!=='paused';
  if(el('extend-record'))el('extend-record').disabled=!!(el('record').disabled||!el('answer').value.trim()||answerLength()>=6000||el('answer').readOnly);
  if(el('answer-count'))el('answer-count').textContent=w('{n} / 6,000 characters',{n:answerLength()});
  if(answerLength()>6000&&!pendingSubmission)el('submit').disabled=true;
}
async function jobs(){
  const selected=el('job').value;
  const items=await api('/api/opportunities');el('job').innerHTML='';
  for(const j of items){const o=document.createElement('option');o.value=j.reference;o.textContent=j.company+' — '+j.role+(j.ready?'':' ('+tr('notReady')+': '+j.reasons.join('; ')+')');o.disabled=!j.ready;el('job').append(o);}
  if(selected)el('job').value=selected;
  await updateHistory();
}
async function updateHistory(){
  if(!el('job').value)return;
  try{const v=await api('/api/history?opportunity='+encodeURIComponent(el('job').value)+'&locale='+encodeURIComponent(el('locale').value));el('history').textContent=tr('history')+': '+v.runs;}catch(e){el('history').textContent='';}
}
function show(v){
  window.interviewUiLocale??=window.uiLocale?.()||'en';
  reviewCursor=null;el('answer').readOnly=false;if(run?.question?.event_id!==v.question?.event_id){rawTranscript=null;answerMode='text';}run=v;if(el('job')&&v.opportunity)el('job').value=v.opportunity;el('locale').value=v.locale;translateUI();
  el('flow').value=v.flow_mode||'fixed';el('question').textContent=v.question?`${v.question.ordinal}/10 — ${v.question.text}`:'';
  msg((v.flow_note?v.flow_note+' ':'')+(v.greeting||v.closing||(v.status==='paused'?tr('paused'):v.status==='cancelled'?tr('cancelled'):v.question?tr('inProgress'):tr('readyReport'))));
  el('ceremony').hidden=!(v.greeting||v.closing);
  el('ceremony').textContent=v.greeting?tr('greeting'):tr('closing');
  for(const id of ['answer','submit','skip','play','record','extend-record'])el(id).hidden=!v.question;
  el('evaluate').hidden=v.status!=='answered';el('stop').hidden=true;
  if(el('progress'))el('progress').textContent=v.question?w('Question {n} of 10',{n:v.question.ordinal}):w('{n} of 10 confirmed',{n:v.answered||0});
  if(el('interview-progress'))el('interview-progress').value=v.answered||0;
  if(el('run-label'))el('run-label').textContent=v.opportunity||'';
  if(el('continue-forward'))el('continue-forward').hidden=true;
  if(el('answer-review'))el('answer-review').hidden=true;
  if(v.question)el('answer').value=drafts.get(v.question.event_id)||'';
  goScreen(v.status==='cancelled'?'job-screen':'interview-screen');
  for(const id of ['retry-preparation','baseline-preparation'])if(el(id))el(id).hidden=v.status!=='preparation_failed';
  if(v.status==='preparation_failed')msg(w('Preparation needs attention. Retry or use native fixed questions.')+' '+failureText(v.preparation_error));
  acknowledged=false;controls();
  if(v.question){const event=v.question.event_id;
    api(`/api/runs/${v.run_id}/present/${v.question.ordinal}/${event}`,{method:'POST'}).then(()=>{
      if(run?.question?.event_id===event){acknowledged=true;controls();}
    }).catch(e=>{if(e.name!=='AbortError')msg(e.message);});
  }
}
el('job').onchange=()=>{preparationRequest=null;updateHistory();};
el('locale').onchange=()=>{translateUI();jobs().catch(e=>{if(e.name!=='AbortError')msg(e.message);});};
el('start').onclick=async()=>{
  if(busy||run?.question||run?.status==='paused')return;window.interviewUiLocale=window.uiLocale?.()||'en';busy=true;preparing=true;controls();goScreen('interview-screen');msg(w('Preparing the interview. Please wait…'));preparationRequest??=crypto.randomUUID();
  try{const v=await api('/api/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({opportunity:el('job').value,locale:el('locale').value,flow_mode:el('flow').value,cloud_consent:!!el('cloud-consent')?.checked,request_id:preparationRequest})});
    resetSession();show(v);await savedRuns();
  }catch(e){if(e.name!=='AbortError')msg(e.message);}finally{preparing=false;busy=false;controls();}
};
async function send(skipped){
  if(busy||submitting||!acknowledged||!run?.question)return;
  if(!skipped&&!pendingSubmission&&answerLength()>6000){msg(w('Shorten your answer to 6,000 characters before confirming. Your full draft is kept.'));return;}
  submitting=true;busy=true;
  pendingSubmission=pendingSubmission||{runId:run.run_id,url:reviewCursor!==null?`/api/runs/${run.run_id}/answers/${reviewCursor}`:`/api/runs/${run.run_id}/answers`,method:reviewCursor!==null?'PUT':'POST',body:reviewCursor!==null?{text:skipped?'':el('answer').value,submission_id:crypto.randomUUID(),revision:run.revision,skipped}:{ordinal:run.question.ordinal,text:skipped?'':el('answer').value,submission_id:crypto.randomUUID(),input_mode:answerMode,skipped,raw_transcript:skipped?null:rawTranscript,revision:run.revision}};
  controls();
  try{const v=await api(pendingSubmission.url||`/api/runs/${pendingSubmission.runId}/answers`,{method:pendingSubmission.method||'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pendingSubmission.body)});
    const edited=reviewCursor!==null;drafts.delete(run.question.event_id);pendingSubmission=null;answerMode='text';rawTranscript=null;el('answer').value='';show(edited?await api('/api/runs/'+run.run_id):v);if(edited)await reviewAnswers(true);if(el('save-state'))el('save-state').textContent=w('Answer saved');
  }catch(e){if(e.status===400||e.status===409||e.status===422)pendingSubmission=null;msg(e.message);}
  finally{busy=false;submitting=false;controls();}
}
el('submit').onclick=()=>send(false);el('skip').onclick=()=>send(true);
function beginMedia(milliseconds){
  const operation={controller:new AbortController(),timer:null,cancelled:false,cancelPlayback:null};
  operation.timer=setTimeout(()=>operation.controller.abort(new Error(vt('timeout'))),milliseconds);
  mediaOperation=operation;busy=true;controls();el('stop').hidden=false;el('stop').textContent=vt('cancel');
  return operation;
}
function endMedia(operation){
  stopCountdown();clearTimeout(operation.timer);
  if(mediaOperation===operation){mediaOperation=null;busy=false;el('stop').hidden=true;controls();}
}
function mediaMessage(error,operation){
  if(operation.cancelled)return;
  msg(operation.controller.signal.aborted?vt('timeout'):error.message);
}
async function play(kind){
  if(busy||pendingSubmission||!run)return;
  const operation=beginMedia(120000);let url;msg(vt('loading'));
  try{
    const path=kind==='question'?'question-audio'+(reviewCursor!==null?'?ordinal='+reviewCursor:''):`ceremony-audio/${kind}`;
    const result=await response(`/api/runs/${run.run_id}/${path}`,{signal:operation.controller.signal});
    url=URL.createObjectURL(await result.blob());
    if(operation.controller.signal.aborted)throw new Error(vt('stopped'));
    clearTimeout(operation.timer);operation.timer=setTimeout(()=>operation.controller.abort(),240000);
    playback=new Audio(url);msg(vt('playing'));
    await new Promise((resolve,reject)=>{
      operation.cancelPlayback=()=>{playback?.pause();reject(new Error(vt('stopped')));};
      operation.controller.signal.addEventListener('abort',operation.cancelPlayback,{once:true});
      playback.onended=resolve;playback.onerror=()=>reject(new Error(w('Audio playback failed. Check your browser audio output.')));
      playback.play().catch(reject);
    });
    if(!operation.cancelled)msg(run.question?tr('inProgress'):tr('readyReport'));
  }catch(e){mediaMessage(e,operation);}finally{
    playback?.pause();if(url)URL.revokeObjectURL(url);playback=null;endMedia(operation);
  }
}
el('play').onclick=()=>play('question');el('ceremony').onclick=()=>play(run.greeting?'greeting':'closing');
async function recordAnswer(append=false){
  if(busy||pendingSubmission||!run?.question)return;
  if(append&&(!el('answer').value.trim()||answerLength()>=6000))return;
  if(!microphoneSupported()){msg(vt('browser'));return;}
  const operation=beginMedia(30000);
  const context={runId:run.run_id,eventId:run.question.event_id,locale:run.locale,base:el('answer').value,raw:rawTranscript};
  msg(vt('permission'));
  try{
    // getUserMedia itself cannot be aborted: close any stream granted after cancellation.
    const requested=navigator.mediaDevices.getUserMedia({audio:true}).then(value=>{
      if(operation.controller.signal.aborted){value.getTracks().forEach(t=>t.stop());throw new Error(vt('stopped'));}
      return value;
    });
    stream=await Promise.race([requested,new Promise((_,reject)=>operation.controller.signal.addEventListener('abort',()=>reject(new Error(vt('timeout'))),{once:true}))]);
    clearTimeout(operation.timer);
    const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(type=>MediaRecorder.isTypeSupported(type));
    chunks=[];recorder=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream);
    let recordingError=null;
    recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
    recorder.onstop=async()=>{
      stopCountdown();stream.getTracks().forEach(t=>t.stop());stream=null;
      el('stop').hidden=false;el('stop').textContent=vt('cancel');msg(tr('transcribing'));
      operation.timer=setTimeout(()=>operation.controller.abort(new Error(vt('timeout'))),300000);
      try{
        if(recordingError)throw recordingError;
        if(!chunks.length)throw new Error('No audio was recorded. Try again or type your answer.');
        const type=recorder.mimeType||mime||'audio/webm';
        const extension=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':'webm';
        const form=new FormData();form.append('audio',new Blob(chunks,{type}),`answer.${extension}`);
        const v=await api('/api/transcribe/'+context.locale,{method:'POST',body:form,signal:operation.controller.signal});
        if(!operation.controller.signal.aborted&&mediaOperation===operation&&run?.run_id===context.runId&&run?.question?.event_id===context.eventId){
          if(typeof v.text!=='string'||!v.text.trim())throw new Error(w('No speech was recognized. Your previous answer is kept.'));
          el('answer').value=append?context.base+'\n\n'+v.text:v.text;
          // Raw audio text excludes the typed/edited base; report labels it as recorded segments only.
          rawTranscript=v.text;
          drafts.set(context.eventId,el('answer').value);answerMode='voice';
          if(v.limited)el('recording-warning').textContent=w('This segment reached three minutes. Only the first three minutes were transcribed.');
          msg(answerLength()>6000?w('Shorten your answer to 6,000 characters before confirming. Your full draft is kept.'):tr('review'));
        }
      }catch(e){mediaMessage(e,operation);}finally{endMedia(operation);}
    };
    recorder.onerror=()=>{recordingError=new Error('Recording failed; retry or type your answer.');if(recorder.state==='recording')recorder.stop();};
    recorder.start();startCountdown();
    el('stop').hidden=false;el('stop').textContent=tr('stop');msg(tr('recording'));
  }catch(e){stream?.getTracks().forEach(t=>t.stop());stream=null;if(!operation.cancelled)msg(operation.controller.signal.aborted?vt('timeout'):vt('permissionError')+' '+e.message);endMedia(operation);}
}
el('record').onclick=()=>recordAnswer(false);
el('extend-record').onclick=()=>recordAnswer(true);
el('stop').onclick=()=>{
  if(recorder?.state==='recording'){recorder.stop();return;}
  if(mediaOperation){mediaOperation.cancelled=true;mediaOperation.controller.abort();msg(vt('stopped'));}
};
async function pollReport(runId){
  const v=await api(`/api/runs/${runId}/report/status`);
  if(run?.run_id!==runId)return;
  run.report_state=v.report_state;run.assessment_version=v.assessment_version;
  if(v.status==='running'){if(el('report-progress'))el('report-progress').textContent=w('{scored}/10 scored · {examples}/10 examples ready',{scored:v.assessed,examples:v.examples_ready||0});if(el('stop-report'))el('stop-report').hidden=false;busy=true;controls();msg(`${tr('progress')}: ${v.processed}/10 ${tr('processed')}, ${v.assessed}/10 ${tr('scored')}.`);pollTimer=setTimeout(()=>pollReport(runId).catch(e=>{busy=false;controls();msg(e.message);}),2000);}
  else{busy=false;controls();if(el('stop-report'))el('stop-report').hidden=true;if(v.status==='done'){if(el('report-progress'))el('report-progress').textContent=w('{scored}/10 scored · {examples}/10 examples ready',{scored:v.assessed,examples:v.examples_ready||0})+' · '+w(v.report_state==='complete'?'Final report':'Draft report')+failureText(v.failure);el('report').innerHTML=v.html||'';if(!v.html)el('report').textContent=v.report;for(const [id,name] of [['download-md','Markdown'],['download-html','HTML']])el(id).textContent=w(v.report_state==='complete'?'Download {format}':'Download draft {format}',{format:name});goScreen('report-screen');msg(tr('saved')+': '+v.path);await updateHistory();}else msg(v.error||tr('retry'));}
}
el('evaluate').onclick=async()=>{
  if(busy||!run)return;busy=true;controls();msg(tr('starting'));const runId=run.run_id;
  try{goScreen('report-screen');await api(`/api/runs/${runId}/report/start`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:run.revision})});run=await api('/api/runs/'+runId);reviewCursor=null;controls();await pollReport(runId);}catch(e){busy=false;controls();msg(e.message);}
};
window.addEventListener('pagehide',()=>{mediaOperation?.controller.abort();stream?.getTracks().forEach(t=>t.stop());playback?.pause();stopCountdown();clearTimeout(pollTimer);});
async function initialize(){
  translateUI();try{speechReady=await api('/api/speech');}catch(e){speechReady={};msg(e.message);}
  voiceStatus();controls();await jobs();
  localStorage.removeItem('interviewRun');await savedRuns();
}
const initialization=initialize().catch(e=>{if(e.name!=='AbortError')msg(e.message);});
function translateUI(){window.applyWorkspaceLanguage?.();voiceStatus();document.documentElement.lang=window.uiLocale?.()||'en';for(let id of ['title','intro','start','play','record','stop','submit','skip','evaluate']){let key=id==='evaluate'?'report':id;el(id).textContent=tr(key)}el('answer').placeholder=tr('answer');for(const option of el('flow').options)option.textContent=tr(option.value);if(run){el('ceremony').textContent=run.greeting?tr('greeting'):tr('closing');if(el('progress'))el('progress').textContent=run.question?w('Question {n} of 10',{n:run.question.ordinal}):w('{n} of 10 confirmed',{n:run.answered||0});if(run.status==='preparation_failed')msg(w('Preparation needs attention. Retry or use native fixed questions.')+' '+failureText(run.preparation_error));}}

function goScreen(id){
  if(window.modelTestRunning&&id!=='models-screen'){msg(w('Cancel the interview or stop the current task before changing setup.'));return false;}
  if(workspaceLocked()&&['connection-screen','models-screen','job-screen'].includes(id)){msg(w('Cancel the interview or stop the current task before changing setup.'));return false;}
  if(document.querySelectorAll){for(const screen of document.querySelectorAll('.screen'))screen.hidden=screen.id!==id;
    for(const button of document.querySelectorAll('[data-screen]')){if(button.dataset.screen===id)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');}
    if(el(id)?.scrollIntoView)el(id).scrollIntoView({block:'start'});}
}
function wire(id,handler){if(el(id))el(id).onclick=handler;}
if(document.querySelectorAll)for(const button of document.querySelectorAll('[data-screen]'))button.onclick=()=>goScreen(button.dataset.screen);
el('answer').oninput=()=>{if(run?.question)drafts.set(run.question.event_id,el('answer').value);};
async function reviewAnswers(force=false){
  if((busy&&!force)||!run)return;
  const history=await api(`/api/runs/${run.run_id}/review`);run.revision=history.revision;
  goScreen('interview-screen');el('answer-review').hidden=false;el('review-list').replaceChildren();
  const editable=history.report_state==='idle'&&history.status!=='cancelled';
  if(el('review-title'))el('review-title').textContent=editable?w('Review before scoring'):w('Saved answer history');
  if(el('review-note'))el('review-note').textContent=editable?w('Correct earlier answers before generating a report. Existing later questions keep their order.'):w('Answers are locked because scoring started or the run was cancelled. Start a new run to practise different answers.');
  for(const answer of history.answers){const row=document.createElement('div');row.className='review-row';
    const content=document.createElement('div'),title=document.createElement('strong'),text=document.createElement('p');
    title.textContent=`${answer.ordinal}. ${history.questions[answer.ordinal-1].text}`;text.textContent=answer.skipped?w('[Skipped]'):answer.text;
    content.append(title,text);row.append(content);const button=document.createElement('button');button.className='secondary';button.textContent=editable?w('Review / edit'):w('View answer');
    button.onclick=()=>visitQuestion(answer.ordinal);row.append(button);el('review-list').append(row);}
}
async function visitQuestion(ordinal){
  if(busy||!run)return;const history=await api(`/api/runs/${run.run_id}/review`);
  const answer=history.answers.find(a=>a.ordinal===ordinal);if(!answer)throw new Error(w('Only confirmed answers can be reviewed.'));
  rawTranscript=answer.raw_transcript||null;answerMode=answer.input_mode||'text';reviewCursor=ordinal;run.revision=history.revision;run.question={...history.questions[ordinal-1],ordinal,event_id:`${run.run_id}-q${String(ordinal).padStart(2,'0')}`};
  el('question').textContent=`${ordinal}/10 — ${run.question.text}`;el('progress').textContent=w('Reviewing question {n} of 10',{n:ordinal});
  el('answer').hidden=false;el('answer').value=drafts.get(run.question.event_id)??answer.text;
  const editable=history.report_state==='idle'&&history.status!=='cancelled';
  el('answer').readOnly=!editable;el('submit').hidden=!editable;el('skip').hidden=!editable;el('play').hidden=false;el('record').hidden=!editable;el('extend-record').hidden=!editable;
  el('continue-forward').hidden=false;el('answer-review').hidden=true;el('ceremony').hidden=true;
  el('submit').textContent=editable?w('Save corrected answer'):tr('submit');acknowledged=true;goScreen('interview-screen');controls();
}
wire('previous',()=>{const ordinal=(reviewCursor??run?.question?.ordinal??11)-1;if(ordinal>=1)visitQuestion(ordinal).catch(e=>{if(e.name!=='AbortError')msg(e.message);});});
wire('review-answers',()=>reviewAnswers().catch(e=>{if(e.name!=='AbortError')msg(e.message);}));wire('review-nav',()=>reviewAnswers().catch(e=>{if(e.name!=='AbortError')msg(e.message);}));
wire('continue-forward',async()=>{try{el('answer').readOnly=false;show(await api('/api/runs/'+run.run_id));}catch(e){if(e.name!=='AbortError')msg(e.message);}});
async function runAction(action){
  if(action==='cancel'&&preparing){if(!(await confirmAction(w('Cancel this interview? Saved answers remain available.'))))return;const requestId=preparationRequest;try{await api(`/api/preparations/${requestId}/cancel`,{method:'POST'});resetSession();await savedRuns();goScreen('job-screen');msg(w('Practice cancelled. Select a job and start a new run.'));}catch(e){msg(e.message);}return;}
  if(busy||!run)return;
  if(action==='cancel'&&!(await confirmAction(w('Cancel this interview? Saved answers remain available.'))))return;
  busy=true;controls();
  try{show(await api(`/api/runs/${run.run_id}/actions/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:run.revision})}));
    if(action==='pause'||action==='cancel'){await savedRuns();if(action==='cancel'){resetSession();goScreen('job-screen');}msg(action==='pause'?w('Practice saved and paused. Choose Resume practice to continue.'):w('Practice cancelled. Select a job and start a new run.'));}}catch(e){if(e.name!=='AbortError')msg(e.message);}finally{busy=false;controls();}
}
wire('pause-run',()=>runAction('pause'));wire('cancel-run',()=>runAction('cancel'));wire('resume-run',()=>runAction('resume'));wire('resume-job',()=>runAction('resume'));
wire('restart-run',async()=>{if(busy||!run)return;if(!(await confirmAction(w('Start a new practice run for this job? The existing interview is kept.'))))return;
  try{if(run.editable&&run.status!=='cancelled')await api(`/api/runs/${run.run_id}/actions/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:run.revision})});
    resetSession();await savedRuns();goScreen('job-screen');}catch(e){if(e.name!=='AbortError')msg(e.message);}});
wire('practice-again',async()=>{if(busy)return;resetSession();await savedRuns();goScreen('job-screen');});
wire('retry-report',()=>el('evaluate').onclick());
wire('stop-report',async()=>{if(!run)return;try{await api(`/api/runs/${run.run_id}/report/stop`,{method:'POST'});clearTimeout(pollTimer);busy=false;controls();el('stop-report').hidden=true;msg(w('Stopped. Scores stay saved and answers remain locked; you can resume the report.'));}catch(e){if(e.name!=='AbortError')msg(e.message);}});
async function downloadReport(format){if(!run)return;try{const result=await response(`/api/runs/${run.run_id}/report/download?format=${format}`);
  const url=URL.createObjectURL(await result.blob()),link=document.createElement('a');link.href=url;link.download=`interview-${run.report_state==='complete'?'report':'draft'}.${format}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){if(e.name!=='AbortError')msg(e.message);}}
wire('download-md',()=>downloadReport('md'));wire('download-html',()=>downloadReport('html'));wire('print-report',()=>window.print());

function failureText(failure){
  if(!failure)return '';
  if(failure.stage==='localization')return w('A question translation needs correction. Retry preparation or use native fixed questions. Saved work is preserved.')+(Number.isInteger(failure.ordinal)?' '+w('Question {n} of 10',{n:failure.ordinal}):'');
  if(failure.code==='CALL_BUDGET')return w('The task allowance is exhausted. Stop the simulator and use the documented report-allowance terminal command, then resume this draft.');
  if(failure.recovery==='switch_provider'||['RATE_LIMITED','TEMPORARY_UNAVAILABLE','PROVIDER_UNAVAILABLE','TIMEOUT','AUTHENTICATION_FAILED','PROVIDER_REFUSAL'].includes(failure.code))return w(providerAdvice);
  const message=w(failure.code),wait=Math.max(0,Math.ceil((failure.retry_at?failure.retry_at-Date.now()/1000:failure.retry_after_seconds)||0));
  return ' '+(message===failure.code?failure.message:message)+(wait?' '+w('Retry after {n} seconds.',{n:wait}):'');
}
function resetSession(){
  sessionEpoch++;for(const controller of requests)controller.abort();requests.clear();
  mediaOperation?.controller.abort();mediaOperation=null;stream?.getTracks().forEach(t=>t.stop());stream=null;
  if(recorder&&recorder.state!=='inactive'){recorder.onstop=null;recorder.stop();}recorder=null;
  playback?.pause();playback=null;stopCountdown();clearTimeout(pollTimer);
  run=null;reviewCursor=null;drafts.clear();pendingSubmission=null;preparationRequest=null;preparing=false;window.interviewUiLocale=null;
  answerMode='text';rawTranscript=null;chunks=[];submitting=false;acknowledged=false;busy=false;
  el('answer').value='';el('answer').readOnly=false;el('report').textContent='';el('question').textContent='';
  for(const id of ['save-state','progress','report-progress','run-label'])if(el(id))el(id).textContent='';
  for(const id of ['answer-review','stop-report','ceremony','stop','retry-preparation','baseline-preparation'])if(el(id))el(id).hidden=true;
  controls();
}
async function savedRuns(){
  if(!el('saved-runs'))return;
  const rows=(await api('/api/runs')).runs;el('saved-runs').replaceChildren();
  if(!rows.some(saved=>saved.status!=='cancelled'))el('saved-runs').textContent=w('Your interview reports will appear here after you practise.');
  for(const saved of rows){
    if(saved.status==='cancelled')continue;
    const row=document.createElement('div'),label=document.createElement('p');row.className='review-row';
    label.textContent=`${saved.opportunity} · ${saved.locale} · ${w(saved.status)} · ${saved.created_at}`;row.append(label);
    const resumable=['active','paused','preparation_failed'].includes(saved.status);
    const view=document.createElement('button');view.className='secondary';view.textContent=w(resumable?'Resume interview':saved.status==='answered'?(saved.report_state==='complete'?'View report':'View draft'):'View history');
    view.onclick=async()=>{if(workspaceLocked()){msg(w('Cancel the interview or stop the current task before changing setup.'));return;}try{
      resetSession();
      if(resumable){let value=await api('/api/runs/'+saved.run_id);if(value.status==='paused')value=await api(`/api/runs/${saved.run_id}/actions/resume`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:value.revision})});show(value);}
      else{run=await api(`/api/runs/${saved.run_id}/view`);if(saved.status==='answered'){goScreen('report-screen');await pollReport(saved.run_id);}else await reviewAnswers();}
    }catch(e){if(e.name!=='AbortError')msg(e.message);}};
    row.append(view);el('saved-runs').append(row);
  }
}
for(const [id,baseline] of [['retry-preparation',false],['baseline-preparation',true]])wire(id,async()=>{
  if(busy||!run)return;busy=true;controls();try{show(await api(`/api/runs/${run.run_id}/preparation/retry?baseline=${baseline}`,{method:'POST'}));await savedRuns();}catch(e){if(e.name!=='AbortError')msg(e.message);}finally{busy=false;controls();}
});
if(el('ui-locale'))el('ui-locale').onchange=()=>{if(workspaceLocked()||run){el('ui-locale').value=window.interviewUiLocale||'en';return;}const workspace=window.workspaceId||'default';localStorage.setItem('interview-ui:'+workspace,el('ui-locale').value);translateUI();updateHistory();window.refreshSetupLanguage?.();savedRuns().catch(e=>msg(e.message));};

async function confirmAction(message){
  const dialog=el('confirm-dialog');
  if(!dialog?.showModal)return window.confirm(message);
  if(dialog.open)return false;
  el('confirm-message').textContent=message;el('confirm-cancel').textContent=w('Back');el('confirm-proceed').textContent=w('Continue');
  return new Promise(resolve=>{const finish=accepted=>{dialog.oncancel=null;if(dialog.open)dialog.close();resolve(accepted);};
    dialog.oncancel=event=>{event.preventDefault();finish(false);};
    el('confirm-cancel').onclick=()=>finish(false);el('confirm-proceed').onclick=()=>finish(true);dialog.showModal();
  });
}

wire('home-link',event=>{event.preventDefault();goScreen('connection-screen');});
window.addEventListener('beforeunload',event=>{if(workspaceLocked()){event.preventDefault();event.returnValue='';}});
window.addEventListener('pagehide',()=>{for(const controller of requests)controller.abort();if(run&&busy)fetch(`/api/runs/${run.run_id}/report/stop`,{method:'POST',headers:{'X-Interview-Token':token},keepalive:true}).catch(()=>{});});

function answerLength(){return [...el('answer').value].length;}
let recordingDeadline=0,recordingWarned=false;
function stopCountdown(){clearTimeout(recordTimer);recordTimer=null;if(el('recording-clock'))el('recording-clock').hidden=true;}
function tickCountdown(){
  if(recorder?.state!=='recording')return;
  const remaining=Math.max(0,Math.ceil((recordingDeadline-performance.now())/1000));
  el('recording-clock').textContent=w('{time} remaining',{time:String(Math.floor(remaining/60)).padStart(2,'0')+':'+String(remaining%60).padStart(2,'0')});
  if(remaining<=30&&!recordingWarned){recordingWarned=true;el('recording-warning').textContent=w('30 seconds remaining. You can extend after this segment.');}
  if(!remaining){recorder.stop();return;}recordTimer=setTimeout(tickCountdown,200);
}
function startCountdown(){stopCountdown();recordingWarned=false;recordingDeadline=performance.now()+180000;el('recording-warning').textContent='';el('recording-clock').hidden=false;tickCountdown();}
window.addEventListener('visibilitychange',()=>{if(recorder?.state==='recording'){clearTimeout(recordTimer);tickCountdown();}});
const priorAnswerInput=el('answer').oninput;
el('answer').oninput=event=>{priorAnswerInput?.(event);controls();};
