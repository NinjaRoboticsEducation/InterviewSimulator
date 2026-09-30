// Deterministic browser-state regression checks; no microphone or live server.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
const el = id => { if (!elements.has(id)) elements.set(id, {value: id === 'locale' ? 'en' : '', textContent:'', hidden:false, disabled:false, options:[]}); return elements.get(id); };
let bodies = [];
const context = vm.createContext({
  document: {getElementById: el, querySelector: () => ({content:'token'}), documentElement:{}},
  window: {addEventListener(){}}, localStorage: {setItem(){}, getItem(){return null}, removeItem(){}},
  Headers, crypto: {randomUUID: () => 'submission-one'}, setTimeout: () => 1, clearTimeout(){},
  fetch: async (path, options) => {bodies.push(options.body); throw new Error('connection lost');},
});
let source = fs.readFileSync('src/interview_simulator/static/app.js', 'utf8');
source = source.replace('initialize().catch(e=>msg(e.message));', '');
vm.runInContext(source, context);
(async () => {
  vm.runInContext("run={run_id:'run-a',question:{ordinal:1,event_id:'event-a'},locale:'en'};acknowledged=true;el('answer').value='Original answer';", context);
  await vm.runInContext('send(false)', context);
  assert.equal(el('answer').disabled, true);
  el('answer').value = 'Changed answer';
  await vm.runInContext('send(true)', context);
  assert.equal(bodies.length, 2);
  assert.equal(bodies[0], bodies[1], 'retry must preserve exact answer and submission ID');
  context.fetch = async () => ({ok:true,json:async()=>({status:'running',processed:1,assessed:1})});
  vm.runInContext("pendingSubmission=null;run={run_id:'run-a',question:null,locale:'en'};busy=false;", context);
  await vm.runInContext("pollReport('run-a')", context);
  assert.equal(el('start').disabled, true, 'resumed report must lock new-run controls');
  vm.runInContext("busy=false;run={run_id:'run-b',question:null,locale:'en'};controls();", context);
  await vm.runInContext("pollReport('run-a')", context);
  assert.equal(el('start').disabled, false, 'stale report poll must not affect another run');
  console.log('Browser state regressions passed');
})().catch(e => {console.error(e); process.exitCode=1;});
