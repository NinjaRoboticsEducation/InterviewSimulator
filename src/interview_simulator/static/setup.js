// Credentials are sent to the application server and cleared from the form.
(() => {
  let plan=null, settingBusy=false, connections=[], modelTestId=null;
  const taskNames={questions:'Question preparation',evaluation:'Answer evaluation',coaching:'Career coaching',summary:'Overall summary',localization:'Question localization'};
  const providers=['local','google','openai','anthropic','ollama'];
  const note=(id,key,args={})=>{el(id).textContent=w(key,args);};
  function options(select,models,selected){select.replaceChildren();for(const model of models){const option=document.createElement('option');option.value=model.id;option.textContent=model.name+(model.compatible||model.tested?'':' — '+w('Test required'));select.append(option);}if(models.some(m=>m.id===selected))select.value=selected;}
  function profileOptions(select,selected){options(select,connections.map(p=>({id:p.id,name:p.endpoint+' · '+w(p.mode==='cloud'?'Official cloud':'Own computer'),compatible:true})),selected);}
  const connection=()=>el('ollama-connection').value;
  async function loadModels(provider,profile){
    if(provider==='ollama'){if(!profile)throw new Error(w('Choose or create an Ollama connection first.'));return (await api(`/api/ollama/${profile}/models`)).models;}
    return (await api(`/api/providers/${provider}/models?refresh=true`)).models;
  }
  async function binding(task,main=false){
    const provider=main?el('provider').value:el(task+'-provider').value;
    const value={provider,model:main?el('main-model').value:el(task+'-model').value,max_output_tokens:Number(el(task+'-tokens').value),reasoning:el(task+'-reasoning').value||null};
    if(provider==='ollama'){
      value.connection=main?connection():el(task+'-connection').value;
      const info=await api('/api/ollama/inspect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});value.locality=info.locality;
    }
    return value;
  }
  async function guard(fn){if(settingBusy||workspaceLocked())return;settingBusy=true;try{await fn();}catch(e){if(e.name!=='AbortError'){note('provider-status',e.message);note('settings-status',e.message);}}finally{settingBusy=false;}}
  async function testModel(selected){
    modelTestId=crypto.randomUUID();window.modelTestRunning=true;for(const node of document.querySelectorAll('#connection-screen input,#connection-screen select,#connection-screen button,#models-screen input,#models-screen select,#models-screen button'))if(node.id!=='stop-model-test')node.disabled=true;controls();el('stop-model-test').hidden=false;
    const id=modelTestId;
    try{
      let result=await api('/api/model-tests',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:id,binding:selected})});
      while(result.status==='running'){
        note('settings-status','Model check: {n} of {total} passed. Keep this page open, or stop the test.',{n:result.completed,total:result.total});
        await new Promise(resolve=>setTimeout(resolve,500));
        result=await api(`/api/model-tests/${id}`);
      }
      if(result.status==='cancelled'){note('settings-status','Model test stopped.');return;}
      if(result.status!=='passed')throw new Error(result.failure?.code==='VALIDATION_FAILED'?w('Model test did not pass. Choose another model or provider.'):failureText(result.failure)||w('Model test did not pass. Choose another model or provider.'));
      await mainModels();note('settings-status','Synthetic structured-output check passed.');
    }finally{if(modelTestId===id)modelTestId=null;window.modelTestRunning=false;for(const node of document.querySelectorAll('#connection-screen input,#connection-screen select,#connection-screen button,#models-screen input,#models-screen select,#models-screen button'))node.disabled=false;el('stop-model-test').hidden=true;controls();}
  }
  el('stop-model-test').onclick=async()=>{if(!modelTestId)return;try{await api(`/api/model-tests/${modelTestId}`,{method:'DELETE'});}catch(error){note('settings-status',error.message);}};
  window.addEventListener('pagehide',()=>{if(modelTestId)fetch(`/api/model-tests/${modelTestId}`,{method:'DELETE',headers:{'X-Interview-Token':token},keepalive:true}).catch(()=>{});});
  function providerUI(){const provider=el('provider').value;el('cloud-key').hidden=provider==='local';el('local-help').hidden=provider!=='local';el('ollama-setup').hidden=provider!=='ollama';note('provider-status',provider==='local'?'Local speech and inference use this computer.':'Connect this provider to discover your account models.');}
  function describePlan(){if(!plan)return;const bindings=[plan.evaluation,plan.coaching,plan.localization||plan.questions];if(plan.generate_questions)bindings.push(plan.questions);if(plan.generate_summary)bindings.push(plan.summary);
    const names=[...new Set(bindings.map(b=>b.provider+(b.provider==='ollama'?' ('+w(b.locality==='local'?'Own computer':'Official cloud')+')':'')))];
    const cloud=[...new Set(bindings.filter(b=>b.provider!=='local'&&!(b.provider==='ollama'&&b.locality==='local')).map(b=>b.provider))];
    note('connection-summary','Text: {providers} · local speech',{providers:names.join(', ')});
    note('data-disclosure',cloud.length?'Selected job/profile facts and confirmed answer text go to {providers}. Audio and local transcription stay on this device.':'Selected text tasks and speech stay on this device.',{providers:cloud.join(', ')});el('consent-wrap').hidden=!cloud.length;
  }
  async function mainModels(){
    const provider=el('provider').value,models=await loadModels(provider,connection());options(el('main-model'),models,plan?.evaluation.provider===provider?plan.evaluation.model:null);
    note('model-note',models.length?'API charges depend on your provider and model. A timeout may still be billed. Unknown models require a successful synthetic schema check.':'No models were returned. Check your account access.');
    for(const task of Object.keys(taskNames)){
      if(el('advanced-models').open&&el(task+'-provider').value!==provider)continue;
      el(task+'-provider').value=provider;el(task+'-connection').value=connection();el(task+'-connection').hidden=provider!=='ollama';options(el(task+'-model'),models,plan?.[task]?.provider===provider?plan[task].model:el('main-model').value);
    }
  }
  function makeTasks(){for(const [task,title] of Object.entries(taskNames)){
    const row=document.createElement('section');row.className='task-model-row';const heading=document.createElement('h3');heading.textContent=title;row.append(heading);
    const controls=document.createElement('div');controls.className='task-model-controls';
    const provider=document.createElement('select');provider.id=task+'-provider';provider.setAttribute('aria-label',title+' provider');for(const name of providers){const option=document.createElement('option');option.value=name;option.textContent=name;provider.append(option);}
    const profile=document.createElement('select');profile.id=task+'-connection';profile.hidden=true;profile.setAttribute('aria-label','Ollama connection');
    const model=document.createElement('select');model.id=task+'-model';model.setAttribute('aria-label',title+' model');controls.append(provider,profile,model);row.append(controls);
    const tokenLabel=document.createElement('label');tokenLabel.htmlFor=task+'-tokens';tokenLabel.textContent='Output token limit';row.append(tokenLabel);
    const tokens=document.createElement('input');tokens.id=task+'-tokens';tokens.type='number';tokens.min='256';tokens.max='8192';tokens.value=task==='questions'?'4096':task==='evaluation'?'1024':'2048';row.append(tokens);
    const reasonLabel=document.createElement('label');reasonLabel.htmlFor=task+'-reasoning';reasonLabel.textContent='Reasoning effort (if supported)';row.append(reasonLabel);
    const reasoning=document.createElement('select');reasoning.id=task+'-reasoning';for(const name of ['','low','medium','high']){const option=document.createElement('option');option.value=name;option.textContent=name||'Provider default';reasoning.append(option);}row.append(reasoning);
    const check=document.createElement('button');check.className='secondary';check.textContent='Test this model (may incur charges)';check.onclick=()=>guard(async()=>testModel(await binding(task)));row.append(check);el('task-models').append(row);
    provider.onchange=()=>guard(async()=>{reasoning.value='';profile.hidden=provider.value!=='ollama';profileOptions(profile,connection());options(model,await loadModels(provider.value,profile.value),null);});
    profile.onchange=()=>guard(async()=>{reasoning.value='';options(model,await loadModels(provider.value,profile.value),null);});
    model.onchange=()=>{reasoning.value='';};
  }}
  makeTasks();window.registerWorkspaceLanguage?.(el('task-models'));window.applyWorkspaceLanguage?.();
  el('provider').onchange=()=>{if(workspaceLocked())return;for(const task of Object.keys(taskNames))el(task+'-reasoning').value='';providerUI();};
  el('ollama-mode').onchange=()=>{const cloud=el('ollama-mode').value==='cloud';el('ollama-endpoint').value=cloud?'https://ollama.com':'http://127.0.0.1:11434';el('ollama-endpoint').readOnly=cloud;el('ollama-context').disabled=cloud;};
  el('ollama-connection').onchange=()=>guard(mainModels);
  el('connect').onclick=()=>guard(async()=>{const key=el('api-key').value;note('provider-status','Checking key and discovering models…');
    try{
      if(el('provider').value==='ollama'){
        const result=await api('/api/ollama/connections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:el('ollama-mode').value,endpoint:el('ollama-endpoint').value,key:key||null,remember:el('remember-key').checked,context_tokens:Number(el('ollama-context').value)})});
        connections.push(result.connection);profileOptions(el('ollama-connection'),result.connection.id);for(const task of Object.keys(taskNames))profileOptions(el(task+'-connection'),result.connection.id);
      }else await api(`/api/providers/${el('provider').value}/connect`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key,remember:el('remember-key').checked})});
      await mainModels();note('provider-status','Connected. Choose your model next.');goScreen('models-screen');
    }finally{el('api-key').value='';}
  });
  el('reconnect-saved').onclick=()=>guard(async()=>{const provider=el('provider').value,path=provider==='ollama'?`/api/ollama/${connection()}/reconnect`:`/api/providers/${provider}/reconnect`;const key=el('api-key').value;
    try{await api(path,{method:'POST',...(provider==='ollama'&&key?{headers:{'Content-Type':'application/json'},body:JSON.stringify({key,remember:el('remember-key').checked})}:{})});await mainModels();note('provider-status','Saved key reconnected.');goScreen('models-screen');}finally{el('api-key').value='';}});
  el('connection-next').onclick=()=>guard(async()=>{await mainModels();goScreen('models-screen');});
  el('refresh-models').onclick=()=>guard(mainModels);
  el('main-model').onchange=()=>{for(const task of Object.keys(taskNames))if(el(task+'-provider').value===el('provider').value){el(task+'-model').value=el('main-model').value;el(task+'-reasoning').value='';}};
  el('probe-main').onclick=()=>guard(async()=>{note('settings-status','Running a synthetic check. No candidate data is sent.');await testModel(await binding('evaluation',true));});
  for(const [id,forget] of [['disconnect',false],['forget-key',true]])el(id).onclick=()=>guard(async()=>{const provider=el('provider').value,path=provider==='ollama'?`/api/ollama/${connection()}/disconnect`:`/api/providers/${provider}/disconnect`;await api(path+`?forget=${forget}`,{method:'POST'});el('api-key').value='';note('provider-status',forget?'Saved key forgotten.':'Session disconnected.');});
  el('save-models').onclick=()=>guard(async()=>{const next={...plan},main=!el('advanced-models').open;for(const task of Object.keys(taskNames))next[task]=await binding(task,main);
    next.generate_questions=el('generate-questions').checked;next.generate_summary=el('generate-summary').checked;next.max_calls=Number(el('call-budget').value);
    const result=await api('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(next)});plan=result.plan;el('cloud-consent').checked=false;describePlan();goScreen('job-screen');});
  window.refreshSetupLanguage=describePlan;
  async function initializeSettings(){
    const settings=await api('/api/settings');plan=settings.plan;connections=settings.ollama_connections||[];window.workspaceId=settings.workspace_id;
    const preference=localStorage.getItem('interview-ui:'+settings.workspace_id);if(['en','ja','zh-Hant'].includes(preference))el('ui-locale').value=preference;translateUI();
    profileOptions(el('ollama-connection'),plan.evaluation.connection);el('provider').value=plan.evaluation.provider;providerUI();describePlan();el('generate-questions').checked=plan.generate_questions;el('generate-summary').checked=plan.generate_summary;el('call-budget').value=plan.max_calls;
    for(const task of Object.keys(taskNames)){const saved=plan[task]||plan.questions;el(task+'-provider').value=saved.provider;el(task+'-tokens').value=saved.max_output_tokens;el(task+'-reasoning').value=saved.reasoning||'';profileOptions(el(task+'-connection'),saved.connection);el(task+'-connection').hidden=saved.provider!=='ollama';try{options(el(task+'-model'),await loadModels(saved.provider,saved.connection),saved.model);}catch(e){note('provider-status',e.message);}}
    try{options(el('main-model'),await loadModels(plan.evaluation.provider,plan.evaluation.connection),plan.evaluation.model);}catch(e){note('provider-status',e.message);}
  }
  initializeSettings().catch(e=>note('provider-status',e.message));
})();
