// Executes the actual browser scripts with a minimal DOM and accelerated clocks.
// Actual Python validation/persistence runs behind a file-backed bridge.
// This checks task completion and API contracts; it is NOT visual/browser QA.
const vm=require('node:vm'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),dataDir=fs.mkdtempSync(path.join(os.tmpdir(),'socratic-ui-'));
// Avoid requiring tests to be an installed package.
function bridge(url,body){const r=spawnSync(process.env.PYTHON||'python3',[path.join(root,'tests/ui_bridge.py'),dataDir],{cwd:root,env:{...process.env,PYTHONPATH:root},input:JSON.stringify({path:url,body}),encoding:'utf8',maxBuffer:30*1024*1024});
 if(r.status!==0)throw Error(r.stderr);const output=JSON.parse(r.stdout);if(!output.ok)throw Error(output.error);return output.data;}
const fixture=bridge(process.env.TASK==='REFERENCE'?'/fixture_reference':'/fixture');
function runtime(task){
 let now=0,timerID=0,scheduled=[],pumping=false,context,complete=false;
 const errors=[],requests=[],screens=[],paints=[];
 function schedule(fn,delay=0){const id=++timerID;scheduled.push({id,at:now+delay,fn});pump();return id;}
 function cancel(id){scheduled=scheduled.filter(t=>t.id!==id);}
 function pump(){if(pumping)return;pumping=true;setImmediate(()=>{pumping=false;if(!scheduled.length)return;scheduled.sort((a,b)=>a.at-b.at||a.id-b.id);const t=scheduled.shift();now=t.at;try{t.fn();}catch(e){errors.push(e);}if(scheduled.length)pump();});}
 class Element{
  constructor(id='',tag='DIV'){this.id=id;this.tagName=tag;this.value='';this.textContent='';this.dataset={};this.children=[];this.options=[];this.attrs={};this.disabled=false;
   const classes=new Set();this.classList={add:(...xs)=>xs.forEach(x=>classes.add(x)),remove:(...xs)=>xs.forEach(x=>classes.delete(x)),toggle:(x,on)=>{if(on===undefined)on=!classes.has(x);on?classes.add(x):classes.delete(x);},contains:x=>classes.has(x)};}
  set innerHTML(value){this.html=value;this.children=[];for(const match of value.matchAll(/<button[^>]*(?:id="([^"]+)"|data-key="([^"]+)")[^>]*>/g)){const e=new Element(match[1]||'', 'BUTTON');this.children.push(e);if(e.id)elements.set(e.id,e);}
   // Block-summary and pause buttons resolve their original runner callbacks.
   if(value.includes('id="continueBlock"'))schedule(()=>elements.get('continueBlock')?.onclick?.(),1);}
  get innerHTML(){return this.html||'';}
  set selectedIndex(index){this.value=this.options[index]?.value||'';}
  get selectedIndex(){return this.options.findIndex(o=>o.value===this.value);}
  setAttribute(k,v){this.attrs[k]=v;}removeAttribute(k){delete this.attrs[k];}
  replaceChildren(...items){this.children=[];this.options=[];for(const x of items)this.append(x);}
  append(...items){this.children.push(...items);this.options.push(...items.filter(x=>x.tagName==='OPTION'));}
  querySelectorAll(selector){return selector==='button'?this.children.filter(x=>x.tagName==='BUTTON'):[];}
  click(){this.onclick?.();}remove(){}
 }
 const elements=new Map();const html=process.env.TASK==='REFERENCE'?bridge('/reference_page'):fs.readFileSync(path.join(root,'socratic_prototype/static/index.html'),'utf8');
 for(const m of html.matchAll(/id="([^"]+)"/g))elements.set(m[1],new Element(m[1]));
 for(const [id,value] of Object.entries({participantId:'synthetic_ui',sessionPhase:'calibration',protocol:'short',condition:'A',promptFrequency:'standard',taskSeed:'browser-contract-test'}))elements.get(id).value=value;
 const responseButtons=elements.get('responseButtons');for(const feedback of ['helpful','disagree','fewer','dismiss']){const button=new Element('', 'BUTTON');button.dataset.feedback=feedback;responseButtons.append(button);}
 const listeners=new Map();const document={getElementById:id=>elements.get(id),createElement:tag=>new Element('',tag.toUpperCase()),body:new Element(),
  addEventListener:(type,fn)=>{if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn);
    // Leave the first TBS choice unanswered to exercise the full response limit.
    if(type==='keydown'&&listeners.get(type).size===2){
     schedule(()=>document.dispatchEvent({type:'keydown',key:'9',target:{tagName:'INPUT'},preventDefault(){}}),10);
     if(!(task==='TBS'&&screens.filter(s=>s.event==='EVALUATION_ONSET').length===1))schedule(()=>document.dispatchEvent({type:'keydown',key:task==='MAB'?'8':'1',target:{tagName:'BODY'},preventDefault(){}}),30);
    }},
  removeEventListener:(type,fn)=>listeners.get(type)?.delete(fn),dispatchEvent:event=>{for(const fn of [...(listeners.get(event.type)||[])])fn(event);}};
 const sandbox={document,performance:{now:()=>now},setTimeout:schedule,clearTimeout:cancel,requestAnimationFrame:fn=>schedule(()=>{paints.push({at:now,html:elements.get('taskarea').innerHTML});fn();},16),cancelAnimationFrame:cancel,
  observeScreen:(event,state)=>{
   const panel=elements.get('teammatePanel');
   screens.push({...event,...state,html:elements.get('taskarea').innerHTML,panelHidden:panel.classList.contains('hidden'),
    panelActive:panel.classList.contains('is-active'),panelSilent:panel.classList.contains('is-silent'),message:elements.get('teammateMessage').textContent});
   if(['COMMITMENT_RESPONSE','NO_RESPONSE_TIMEOUT'].includes(event.event)&&panel.classList.contains('is-active')){
    elements.get('responseText').value='I considered 19 outcomes.';elements.get('responseText').oninput();
    elements.get('responseButtons').children[0].onclick();elements.get('submitReply').onclick();
   }
   if(event.event==='PREPARATION_ONSET'){
    schedule(()=>document.dispatchEvent({type:'keydown',key:'1',target:{tagName:'BODY'},preventDefault(){}}),20);
    schedule(()=>vm.runInContext("clickChoice('9')",context),40);
   }
  },
  Date,Math,JSON,Promise,console:{log:console.log,error:e=>errors.push(e)},Blob,URL,KeyboardEvent:class{constructor(type,options){this.type=type;Object.assign(this,options);this.target={tagName:'BODY'};}preventDefault(){}},alert:e=>errors.push(e),confirm:()=>true,
  fetch:async(url,options)=>{const body=options?.body===undefined?undefined:JSON.parse(options.body);requests.push({url,body});try{return{ok:true,json:async()=>bridge(url,body)};}catch(e){return{ok:false,json:async()=>({error:e.message})};}}};
 context=vm.createContext(sandbox);require('./browser_scripts.cjs').loadScripts(html,context,root);
 vm.runInContext(`const originalLogEvent=logEvent;logEvent=function(...args){const event=originalLogEvent(...args);if(event)observeScreen(event,{preparing:teammate.preparing,input_ready:inputResolver!==null});return event;};`,context);
 return {context,elements,requests,errors,screens,paints,now:()=>now};
}
(async()=>{
 try{
  for(const task of process.env.TASK?[process.env.TASK]:['MAB','TBS'])for(const condition of (process.env.CONDITIONS||'F').split(',')){
   const r=runtime(task);await new Promise(resolve=>setImmediate(resolve));
   r.elements.get('sessionPhase').value='assisted';r.elements.get('condition').value=condition;
   const missingTask=task==='REFERENCE'?'REFERENCE':'TBS',missingField=task==='REFERENCE'?'referenceCalibration':'tbsCalibration';
   for(const [id,value] of Object.entries(fixture))r.elements.get(id==='REFERENCE'?'referenceCalibration':id==='MAB'?'mabCalibration':'tbsCalibration').value=value;
   r.elements.get(missingField).value='';
   await vm.runInContext(`start('${task}')`,r.context);
   assert.match(r.elements.get('setupError').textContent,new RegExp('Missing: '+missingTask));
   assert.equal(vm.runInContext('alive',r.context),false);
   assert.equal(r.requests.filter(x=>x.url==='/api/sessions'&&x.body).length,0,'Missing calibration must be caught before session creation');
   r.elements.get(missingField).value=fixture[missingTask];
   await vm.runInContext(`start('${task}')`,r.context);
   const deadline=Date.now()+120000;
   while(vm.runInContext('alive',r.context)&&Date.now()<deadline)await new Promise(resolve=>setImmediate(resolve));
   assert.equal(vm.runInContext('session.completed',r.context),true,task+' did not complete: '+r.errors.join(' '));
   assert.deepEqual(r.errors,[]);
   assert.equal(r.elements.get('taskWorkspace').classList.contains('hidden'),false);
   assert.equal(r.elements.get('taskPanel').classList.contains('hidden'),true);
   assert.equal(r.elements.get('finish').classList.contains('hidden'),false);
   const count=vm.runInContext('session.trials.length',r.context);assert.equal(count,task==='MAB'?40:task==='TBS'?24:4);
   const evaluations=r.requests.filter(x=>x.body?.kind==='evaluation');assert.equal(evaluations.length,count);
   for(const request of evaluations){assert.equal('volatility_checks' in request.body,false);assert.equal('stage' in request.body,false);assert.equal('random_draw' in request.body,false);for(const o of request.body.options)assert.equal('probabilities' in o,false);}
   const sid=vm.runInContext('session.id',r.context), exported=bridge('/api/sessions/'+sid+'/export');
   assert.equal(exported.completed,true);assert.equal(bridge('/api/sessions/'+sid+'/replay').matches,true);
   const deliveries=exported.events.filter(e=>e.input.kind==='delivery');assert.equal(deliveries.length,count);
   if(condition==='A')assert.ok(deliveries.every(e=>!e.input.delivered));
   else assert.ok(deliveries.some(e=>e.input.delivered));
   // The four-second preparation and original five-second choice limit remain configured.
   assert.equal(exported.policy.preparation_ms,4000);
   const prepEvents=vm.runInContext("session.events.filter(e=>e.event==='PREPARATION_END')",r.context);
   assert.equal(prepEvents.length,count);assert.ok(prepEvents.every(e=>e.duration_ms===4000));
   assert.ok(prepEvents.every(e=>e.reading_exposure_ms<=4000));assert.equal(vm.runInContext(`configs.${task}.response_timeout_ms`,r.context),5000);
   const preparation=r.screens.filter(s=>s.event==='PREPARATION_ONSET'),onsets=r.screens.filter(s=>s.event==='EVALUATION_ONSET');
   assert.equal(preparation.length,count);assert.equal(onsets.length,count);
   for(let i=0;i<count;i++){
    const prep=preparation[i],onset=onsets[i];
    assert.equal(prep.options_visible,false);assert.equal(prep.preparing,true);assert.equal(prep.input_ready,false);
    assert.doesNotMatch(prep.html,/<button|Win chance:|Press [19]/);
    assert.ok(onset.monotonic_ms>=prep.monotonic_ms+4000);
    assert.equal(onset.preparing,false);assert.match(onset.html,/<button/);
    const frames=r.paints.filter(p=>p.at>=prep.monotonic_ms&&p.at<prep.monotonic_ms+4000);
    assert.ok(frames.length>0);assert.ok(frames.every(p=>!p.html.includes('<button')),'Choices appeared during preparation');
    const early=r.screens.filter(s=>s.event==='PREPARATION_EARLY_RESPONSE_ATTEMPT'&&s.trial_uid===prep.trial_uid);
    assert.equal(early.length,2);assert.equal(prepEvents[i].early_attempts,2);
    const response=r.screens.find(s=>['COMMITMENT_RESPONSE','NO_RESPONSE_TIMEOUT'].includes(s.event)&&s.trial_uid===prep.trial_uid);
    assert.ok(response.monotonic_ms>=onset.monotonic_ms);
    if(task==='TBS'){
     assert.match(prep.html,/Progress:.*Target gap:/s);
     assert.match(onset.html,/SAFE/);assert.match(onset.html,/RISKY/);
     assert.equal((onset.html.match(/class="option /g)||[]).length,2);
     // The timeout marker follows the two animation frames used to paint feedback.
     assert.equal(response.monotonic_ms-onset.monotonic_ms,i===0?5000+2*16:30);
    }
   }
   assert.equal(deliveries.every(e=>e.input.early_attempts===2),true);
   const stages=r.screens.filter(s=>['PREPARATION_ONSET','EVALUATION_ONSET','COMMITMENT_RESPONSE','FIXATION_ONSET','FEEDBACK_ONSET','NO_RESPONSE_TIMEOUT','INTERTRIAL_FIXATION_ONSET','BLOCK_SUMMARY'].includes(s.event));
   assert.ok(stages.every(s=>!s.panelHidden),'The teammate panel must remain visible in every task stage');
   for(const d of deliveries){
    const trialScreens=stages.filter(s=>s.global_trial===d.input.index&&!['PREPARATION_ONSET','BLOCK_SUMMARY'].includes(s.event));
    assert.ok(trialScreens.every(s=>d.input.delivered?s.panelActive:s.panelSilent));
    if(d.input.delivered){
     assert.ok(d.input.reading_exposure_ms>4000,'Exposure must include choice and feedback stages');
     assert.equal(r.screens.find(s=>s.event==='INTERVENTION_ACTIVE_END'&&s.decision_id===d.input.decision_id).reading_exposure_ms,d.input.reading_exposure_ms);
    }else assert.equal(d.input.reading_exposure_ms,0);
   }
   if(condition!=='A')assert.ok(exported.events.some(e=>e.input.kind==='response'&&e.input.text==='I considered 19 outcomes.'),'Responses entered after preparation must be saved');
   else assert.ok(exported.events.every(e=>e.input.kind!=='response'),'Silent baseline must not solicit replies');
   if(task==='TBS'){
    const trials=vm.runInContext('JSON.stringify(session.trials)',r.context);
    const first=JSON.parse(trials)[0];assert.equal(first.chosen_option,'NO_RESPONSE');assert.equal(first.response_time_ms,5000);assert.equal(first.earned_points,0);
   }
   console.log(task+' '+condition+': '+count+' trials passed: choices hidden throughout preparation, early input blocked/logged, choice timing, Python validation, persistence and replay.');
  }
 }finally{fs.rmSync(dataDir,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
