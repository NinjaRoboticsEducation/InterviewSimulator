let run=null, recorder=null, chunks=[], stream=null, submitting=false, pendingSubmission=null, answerMode='text', rawTranscript=null;
const el=id=>document.getElementById(id), msg=s=>el('status').textContent=s;
const words={
en:{title:'Interview Simulator',intro:'Choose a manually prepared opportunity. Practice stays on this device.',start:'Start practice',fixed:'Fixed practice',adaptive:'Adaptive question order',play:'Play question',record:'Record answer',stop:'Stop recording',answer:'Confirm or correct your answer before submitting',submit:'Confirm answer',skip:'Skip question',report:'Generate report',history:'Previous practice runs',notReady:'not ready',greeting:'Play greeting',closing:'Play closing',inProgress:'Interview in progress',readyReport:'All ten questions answered. Generate your report.',transcribing:'Transcribing locally…',review:'Review and correct the transcript, then confirm.',recording:'Recording your answer…',starting:'Starting local assessment…',progress:'Report in progress',scored:'scored',processed:'processed',saved:'Saved',retry:'Report generation stopped. Select Generate report to retry saved work.'},
ja:{title:'面接シミュレーター',intro:'準備済みの応募先を選んでください。練習データはこの端末内に保存されます。',start:'練習を開始',fixed:'固定練習',adaptive:'適応型の質問順',play:'質問を再生',record:'回答を録音',stop:'録音を停止',answer:'音声認識の文章を確認・修正してから送信してください',submit:'回答を確定',skip:'質問を省略',report:'レポートを作成',history:'過去の練習回数',notReady:'準備未完了',greeting:'挨拶を再生',closing:'締めの言葉を再生',inProgress:'面接練習中',readyReport:'10問が終了しました。レポートを作成してください。',transcribing:'端末内で音声を文字に変換しています…',review:'認識結果を確認・修正してから確定してください。',recording:'回答を録音しています…',starting:'端末内で評価を開始しています…',progress:'レポート作成中',scored:'採点済み',processed:'処理済み',saved:'保存先',retry:'レポート作成が停止しました。「レポートを作成」を押すと保存済みの結果から再開できます。'},
'zh-Hant':{title:'面試模擬器',intro:'請選擇已準備好的應徵機會。練習資料保存在這台裝置上。',start:'開始練習',fixed:'固定練習',adaptive:'適應式題目順序',play:'播放題目',record:'錄製回答',stop:'停止錄音',answer:'提交前請確認或修正語音辨識文字',submit:'確認回答',skip:'略過此題',report:'產生報告',history:'過去練習次數',notReady:'尚未就緒',greeting:'播放開場白',closing:'播放結語',inProgress:'面試練習進行中',readyReport:'十道題目已完成。請產生報告。',transcribing:'正在本機轉寫語音…',review:'請檢查並修正轉寫文字，再確認回答。',recording:'正在錄製回答…',starting:'正在本機開始評估…',progress:'正在產生報告',scored:'已評分',processed:'已處理',saved:'已儲存',retry:'報告產生已中斷。按「產生報告」可接續已儲存的結果。'}};
const tr=key=>words[el('locale').value][key];
const token=document.querySelector('meta[name="interview-token"]').content;
let busy=false, acknowledged=false, playback=null, recordTimer=null, pollTimer=null;
async function response(path, options={}) {
  const headers=new Headers(options.headers||{});
  headers.set('X-Interview-Token',token);
  const r=await fetch(path,{...options,headers});
  if(!r.ok){const value=await r.json();const error=new Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));error.status=r.status;throw error;}
  return r;
}
async function api(path,options={}){return (await response(path,options)).json();}
function controls(){
  const active=!!run?.question;
  for(const id of ['play','record','ceremony'])el(id).disabled=busy||!!pendingSubmission;
  for(const id of ['submit','skip'])el(id).disabled=busy||!acknowledged;
  el('answer').disabled=busy||!!pendingSubmission;
  el('start').disabled=busy||active;
  el('job').disabled=busy||active;
  el('locale').disabled=busy||active;el('flow').disabled=busy||active;
  el('evaluate').disabled=busy;
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
  run=v;localStorage.setItem('interviewRun',v.run_id);el('locale').value=v.locale;translateUI();
  el('flow').value=v.flow_mode||'fixed';el('question').textContent=v.question?`${v.question.ordinal}/10 — ${v.question.text}`:'';
  msg((v.flow_note?v.flow_note+' ':'')+(v.greeting||v.closing||(v.question?tr('inProgress'):tr('readyReport'))));
  el('ceremony').hidden=!(v.greeting||v.closing);
  el('ceremony').textContent=v.greeting?tr('greeting'):tr('closing');
  for(const id of ['answer','submit','skip','play','record'])el(id).hidden=!v.question;
  el('evaluate').hidden=!!v.question;el('stop').hidden=true;
  acknowledged=false;controls();
  if(v.question){const event=v.question.event_id;
    api(`/api/runs/${v.run_id}/present/${v.question.ordinal}/${event}`,{method:'POST'}).then(()=>{
      if(run?.question?.event_id===event){acknowledged=true;controls();}
    }).catch(e=>msg(e.message));
  }
}
el('job').onchange=updateHistory;
el('locale').onchange=()=>{translateUI();jobs().catch(e=>msg(e.message));};
el('start').onclick=async()=>{
  if(busy||run?.question)return;busy=true;controls();
  try{const v=await api('/api/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({opportunity:el('job').value,locale:el('locale').value,flow_mode:el('flow').value})});
    clearTimeout(pollTimer);el('report').textContent='';el('answer').value='';show(v);
  }catch(e){msg(e.message);}finally{busy=false;controls();}
};
async function send(skipped){
  if(busy||submitting||!acknowledged||!run?.question)return;
  submitting=true;busy=true;
  pendingSubmission=pendingSubmission||{runId:run.run_id,body:{ordinal:run.question.ordinal,text:skipped?'':el('answer').value,submission_id:crypto.randomUUID(),input_mode:answerMode,skipped,raw_transcript:skipped?null:rawTranscript}};
  controls();
  try{const v=await api(`/api/runs/${pendingSubmission.runId}/answers`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pendingSubmission.body)});
    pendingSubmission=null;answerMode='text';rawTranscript=null;el('answer').value='';show(v);
  }catch(e){if(e.status===400||e.status===422)pendingSubmission=null;msg(e.message);}
  finally{busy=false;submitting=false;controls();}
}
el('submit').onclick=()=>send(false);el('skip').onclick=()=>send(true);
async function play(kind){
  if(busy||pendingSubmission||!run)return;busy=true;controls();let url;
  try{const path=kind==='question'?'question-audio':`ceremony-audio/${kind}`;
    url=URL.createObjectURL(await (await response(`/api/runs/${run.run_id}/${path}`)).blob());
    playback=new Audio(url);
    await new Promise((resolve,reject)=>{playback.onended=resolve;playback.onerror=()=>reject(new Error('Audio playback failed'));playback.play().catch(reject);});
  }catch(e){msg(e.message);}finally{if(url)URL.revokeObjectURL(url);playback=null;busy=false;controls();}
}
el('play').onclick=()=>play('question');el('ceremony').onclick=()=>play(run.greeting?'greeting':'closing');
el('record').onclick=async()=>{
  if(busy||pendingSubmission||!run?.question)return;
  busy=true;controls();const context={runId:run.run_id,eventId:run.question.event_id,locale:run.locale};
  try{stream=await navigator.mediaDevices.getUserMedia({audio:true});chunks=[];recorder=new MediaRecorder(stream);
    recorder.ondataavailable=e=>chunks.push(e.data);
    recorder.onstop=async()=>{
      clearTimeout(recordTimer);stream.getTracks().forEach(t=>t.stop());el('stop').hidden=true;msg(tr('transcribing'));
      try{const form=new FormData();form.append('audio',new Blob(chunks,{type:recorder.mimeType}),'answer.webm');
        const v=await api('/api/transcribe/'+context.locale,{method:'POST',body:form});
        if(run?.run_id===context.runId&&run?.question?.event_id===context.eventId){rawTranscript=v.text;el('answer').value=v.text;answerMode='voice';msg(tr('review'));}
      }catch(e){msg(e.message);}finally{busy=false;controls();}
    };
    recorder.onerror=()=>{msg('Recording failed; retry or type your answer.');if(recorder.state==='recording')recorder.stop();};
    recorder.start();recordTimer=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},179000);el('stop').hidden=false;msg(tr('recording'));
  }catch(e){stream?.getTracks().forEach(t=>t.stop());busy=false;controls();msg(e.message);}
};
el('stop').onclick=()=>{if(recorder?.state==='recording')recorder.stop();};
async function pollReport(runId){
  const v=await api(`/api/runs/${runId}/report/status`);
  if(run?.run_id!==runId)return;
  if(v.status==='running'){busy=true;controls();msg(`${tr('progress')}: ${v.processed}/10 ${tr('processed')}, ${v.assessed}/10 ${tr('scored')}.`);pollTimer=setTimeout(()=>pollReport(runId).catch(e=>{busy=false;controls();msg(e.message);}),2000);}
  else{busy=false;controls();if(v.status==='done'){el('report').textContent=v.report;msg(tr('saved')+': '+v.path);await updateHistory();}else msg(v.error||tr('retry'));}
}
el('evaluate').onclick=async()=>{
  if(busy||!run)return;busy=true;controls();msg(tr('starting'));const runId=run.run_id;
  try{await api(`/api/runs/${runId}/report/start`,{method:'POST'});await pollReport(runId);}catch(e){busy=false;controls();msg(e.message);}
};
window.addEventListener('pagehide',()=>{stream?.getTracks().forEach(t=>t.stop());playback?.pause();clearTimeout(recordTimer);clearTimeout(pollTimer);});
async function initialize(){
  translateUI();await jobs();
  const active=await api('/api/active');const recent=active.run_id?null:await api('/api/recent');const prior=active.run_id||localStorage.getItem('interviewRun')||recent.run_id;
  if(prior){try{show(await api('/api/runs/'+prior));if(!run.question)await pollReport(prior);}catch(e){localStorage.removeItem('interviewRun');msg(e.message);}}
}
initialize().catch(e=>msg(e.message));
function translateUI(){document.documentElement.lang=el('locale').value;for(let id of ['title','intro','start','play','record','stop','submit','skip','evaluate']){let key=id==='evaluate'?'report':id;el(id).textContent=tr(key)}el('answer').placeholder=tr('answer');for(const option of el('flow').options)option.textContent=tr(option.value);if(run)el('ceremony').textContent=run.greeting?tr('greeting'):tr('closing')}
