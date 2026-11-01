'use strict';
// Execute the real UI scripts with a controllable clock and delayed API responses.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(task){
 let now=0,timer=0,scheduled=[],late=null,nextAction='ask',failResponses=0;const requests=[],listeners=new Map(),elements=new Map();
 class Element{
  constructor(){this.value='';this.textContent='';this.dataset={};this.children=[];this.options=[];this.html='';
   const classes=new Set();this.classList={add:(...xs)=>xs.forEach(x=>classes.add(x)),remove:(...xs)=>xs.forEach(x=>classes.delete(x)),contains:x=>classes.has(x),toggle:(x,on)=>{if(on===undefined)on=!classes.has(x);on?classes.add(x):classes.delete(x);}};}
  set innerHTML(html){this.html=html;}get innerHTML(){return this.html;}
  append(x){this.children.push(x);this.options.push(x);}replaceChildren(){this.children=[];this.options=[];}
  querySelectorAll(){return this.children;}setAttribute(){}removeAttribute(){}
 }
 const by=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
 for(const [id,value] of Object.entries({participantId:'fixture',sessionPhase:'calibration',protocol:'short',condition:'A',promptFrequency:'standard',taskSeed:'fixed'}))by(id).value=value;
 for(const feedback of ['helpful','disagree','fewer','dismiss']){const b=new Element();b.dataset.feedback=feedback;by('responseButtons').children.push(b);}
 const schedule=(fn,delay=0)=>{scheduled.push({id:++timer,at:now+delay,fn});return timer;};
 const document={getElementById:by,createElement:()=>new Element(),addEventListener:(type,fn)=>{if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn);},
  removeEventListener:(type,fn)=>listeners.get(type)?.delete(fn),dispatchEvent:event=>{for(const fn of [...(listeners.get(event.type)||[])])fn(event);}};
 const context=vm.createContext({document,performance:{now:()=>now},Date,Math,JSON,Promise,console,
  setTimeout:schedule,clearTimeout:id=>scheduled=scheduled.filter(x=>x.id!==id),requestAnimationFrame:fn=>schedule(fn,16),cancelAnimationFrame:id=>scheduled=scheduled.filter(x=>x.id!==id),
  fetch:async(path,options)=>{const body=options?.body?JSON.parse(options.body):undefined;requests.push({path,body});
   if(body?.kind==='response'&&failResponses>0){failResponses--;return {ok:false,json:async()=>({error:'Simulated network failure'})};}
   let data=[];
   if(body?.kind==='evaluation'){
    const action=nextAction,decision={id:body.trial_id+'_decision',action,message:action==='silence'?null:'What supports this choice?',hypothesis:null,language:{generation_ms:5}};
    if(late)await late;
    data={record:{id:body.trial_id+'_event',snapshot:{decision}}};
   }else if(body)data={record:{input:body}};
   return {ok:true,json:async()=>data};
  }});
 const html=fs.readFileSync('socratic_prototype/static/index.html','utf8');
 require('./browser_scripts.cjs').loadScripts(html,context);
 const run=code=>vm.runInContext(code,context),flush=async()=>{for(let i=0;i<16;i++)await Promise.resolve();};
 async function advance(ms){const target=now+ms;await flush();while(true){scheduled.sort((a,b)=>a.at-b.at||a.id-b.id);const next=scheduled[0];if(!next||next.at>target)break;scheduled.shift();now=next.at;next.fn();await flush();}now=target;await flush();}
 function trial(index){run(`activeTrial=createTrial({global_trial:${index},trial:${index},block:1,score_before:0,score_after:0,points_before:0,points_after:0,target:595,remaining_trials_including_current:${9-index},multiplier:1.1,selected_option:session.task==='MAB'?'blue1':null,chosen_option:session.task==='TBS'?'safe':null,outcome:0,earned_points:0,response_time_ms:100,available_options:session.task==='MAB'?baseArms.map(([id,color,key,shade,probs,outcomes])=>({id,key,outcomes})):[{option_id:'safe',key:'1',amount:100,probability:.9},{option_id:'risky',key:'9',amount:265,probability:.35}]});`);}
 run(`newSession('${task}');alive=true;runId=1;session.teammate_configuration={policy:{preparation_ms:4000}};session.teammate_events=[];teammate.id=session.id;`);trial(1);
 return {run,by,advance,trial,requests,failNextResponse:()=>failResponses++,setAction:a=>nextAction=a,delay:()=>{let release;late=new Promise(r=>release=r);return ()=>{release();late=null;};},key:(key,tag='BODY')=>document.dispatchEvent({type:'keydown',key,target:{tagName:tag},preventDefault(){}})};
}
(async()=>{
 for(const task of ['MAB','TBS']){
  const h=harness(task),panel=h.by('teammatePanel');
  h.run('renderReplies()');
  assert.equal(h.by('teammateResponse').classList.contains('hidden'),false);
  assert.equal(h.by('responseText').disabled,true);assert.equal(h.by('submitReply').disabled,true);
  assert.ok(h.by('responseButtons').children.every(b=>b.disabled));
  const prep=h.run('teammatePreparation(activeTrial,runId)');await h.advance(4032);await prep;
  assert.equal(panel.classList.contains('hidden'),false);assert.equal(panel.classList.contains('is-active'),true);
  assert.equal(h.by('prepCountdown').textContent,'');assert.equal(h.by('responseText').disabled,false);assert.ok(h.by('responseButtons').children.every(b=>!b.disabled));
  assert.equal(h.by('teammateResponse').classList.contains('hidden'),false);
  assert.equal(await h.run('submitTeammateReply()'),false);
  assert.match(h.by('replyStatus').textContent,/Write a reply or choose feedback/);
  const message=h.by('teammateMessage').textContent;
  let selected=false;const choice=h.run("waitChoice(['1','9'],5000)").then(r=>{selected=true;return r;});
  h.key('9','INPUT');await h.advance(100);assert.equal(selected,false,'Typing a digit must not choose an option');
  assert.equal(panel.classList.contains('hidden'),false);h.key('1');await choice;
  h.by('responseText').value='I considered 19 outcomes.';h.by('responseText').oninput();
  const submitting=h.run('submitTeammateReply()');
  assert.match(h.by('replyStatus').textContent,/queued/);assert.equal(h.requests.some(r=>r.body?.kind==='response'),false);
  assert.equal(h.run('submitTeammateReply()'),submitting,'Double clicks must reuse the pending submission');
  for(const phase of ['commit','feed']){h.run(`phase('${phase}')`);assert.equal(panel.classList.contains('is-active'),true);assert.equal(h.by('teammateMessage').textContent,message);}
  await h.advance(3000);await h.run('teammateFeedback(activeTrial)');
  assert.equal(await submitting,true);assert.match(h.by('replyStatus').textContent,/Reply closed · Response saved/);
  const delivery=h.requests.find(r=>r.body?.kind==='delivery').body;
  assert.equal(delivery.delivered,true);assert.ok(delivery.reading_exposure_ms>4000);
  const kinds=h.requests.filter(r=>r.body?.kind).map(r=>r.body.kind);
  assert.deepEqual(kinds,['evaluation','delivery','response','feedback']);
  assert.equal(h.requests.find(r=>r.body?.kind==='response').body.text,'I considered 19 outcomes.');
  assert.equal(h.requests.find(r=>r.body?.kind==='response').body.feedback,'reply');
  assert.equal(panel.classList.contains('is-silent'),true);assert.equal(h.by('teammateMessage').textContent,message);
  await h.advance(70000); // A between-trial pause does not erase the last message.
  h.trial(2);h.setAction('silence');const silent=h.run('teammatePreparation(activeTrial,runId)');await h.advance(4032);await silent;
  assert.equal(panel.classList.contains('is-silent'),true);assert.equal(h.by('teammateMessage').textContent,message);
  assert.match(h.by('teammateContext').textContent,/Previous intervention · trial 1/);
  assert.equal(h.by('teammateResponse').classList.contains('hidden'),false);
  assert.equal(h.by('responseText').disabled,true);assert.ok(h.by('responseButtons').children.every(b=>b.disabled));
  assert.match(h.by('replyStatus').textContent,/Reply closed · Response saved/);
  await h.run('teammateFeedback(activeTrial)');await h.run('finishTeammate(false)');
  const visibility=JSON.parse(h.run("JSON.stringify(session.events.find(e=>e.event==='INTERVENTION_VISIBILITY_END'))"));
  assert.ok(visibility.visible_ms>70000);assert.equal(visibility.active_exposure_ms,delivery.reading_exposure_ms);
  assert.equal(h.requests.filter(r=>r.body?.kind==='delivery')[1].body.reading_exposure_ms,0);
  // A previous question is read-only and cannot accept a new reply.
  const draft=harness(task);let preparation=draft.run('teammatePreparation(activeTrial,runId)');await draft.advance(4032);await preparation;
  const original=draft.run('teammate.replyTarget');
  draft.by('responseText').value='An unfinished draft';draft.by('responseText').oninput();
  await draft.run('teammateFeedback(activeTrial)');
  assert.equal(draft.by('teammateResponse').classList.contains('hidden'),false);assert.equal(draft.by('responseText').disabled,true);
  assert.equal(draft.by('submitReply').disabled,true);assert.match(draft.by('replyStatus').textContent,/draft was not submitted/);
  assert.equal(await draft.run('submitTeammateReply()'),false);assert.equal(draft.requests.some(r=>r.body?.kind==='response'),false);
  draft.trial(2);preparation=draft.run('teammatePreparation(activeTrial,runId)');await draft.advance(4032);await preparation;
  const latest=draft.run('teammate.replyTarget');assert.notEqual(latest,original);
  assert.equal(draft.by('responseText').value,'');assert.equal(draft.by('teammateResponse').classList.contains('hidden'),false);assert.equal(draft.by('responseText').disabled,false);
  draft.run(`teammate.replyTarget=${JSON.stringify(original)}`);
  assert.equal(await draft.run('submitTeammateReply()'),false,'An old target must not be usable during a new active trial');
  draft.run(`teammate.replyTarget=${JSON.stringify(latest)};renderReplies()`);
  draft.by('responseText').value='A current reply, 19 samples.';draft.by('responseText').oninput();
  draft.failNextResponse();const saving=draft.run('submitTeammateReply()');
  await draft.run('teammateFeedback(activeTrial)');assert.equal(await saving,false);
  assert.match(draft.by('replyStatus').textContent,/already-submitted response/);
  assert.equal(draft.by('responseText').disabled,true,'Retries must not invite a new answer to an expired question');
  draft.by('responseText').value='Attempt to change an expired reply';draft.by('responseText').oninput();
  assert.equal(await draft.run('submitTeammateReply()'),true);
  const attempts=draft.requests.filter(r=>r.body?.kind==='response');assert.deepEqual(attempts[0].body,attempts[1].body);
  assert.equal(attempts[1].body.decision_id,latest);assert.equal(attempts[1].body.text,'A current reply, 19 samples.');
  draft.trial(3);preparation=draft.run('teammatePreparation(activeTrial,runId)');await draft.advance(4032);await preparation;
  draft.by('responseText').value='Not submitted before the run ended';draft.by('responseText').oninput();
  await draft.run('finishTeammate(false)');const count=draft.requests.filter(r=>r.body?.kind==='response').length;
  assert.equal(await draft.run('submitTeammateReply()'),false);
  assert.equal(draft.requests.filter(r=>r.body?.kind==='response').length,count,'No new replies after task completion');
  const late=harness(task),release=late.delay();const pending=late.run('teammatePreparation(activeTrial,runId)');await late.advance(4032);await pending;
  release();await late.advance(100);assert.equal(late.by('teammatePanel').classList.contains('is-active'),false);
  assert.equal(late.run("session.events.some(e=>e.event==='INTERVENTION_DISPLAY')"),false);
  await late.run('teammateFeedback(activeTrial)');
  const missed=late.requests.find(r=>r.body?.kind==='delivery').body;assert.equal(missed.delivered,false);assert.equal(missed.reading_exposure_ms,0);
  const cancelled=harness(task),releaseCancelled=cancelled.delay();
  const oldId=cancelled.run('session.id'),oldPrep=cancelled.run('teammatePreparation(activeTrial,runId)');await cancelled.advance(200);
  const finishing=cancelled.run('finishTeammate(false)');cancelled.run('alive=false;runId++');
  // Replace the local run before the old evaluation returns. Its acknowledgement
  // must still go to its original server session and must not repaint the panel.
  cancelled.run(`newSession('${task}');teammate.id=session.id;teammate.presentation=null;teammate.visibleMessage=null;`);
  cancelled.by('teammateMessage').textContent='New session';releaseCancelled();await cancelled.advance(100);await oldPrep;await finishing;
  assert.equal(cancelled.by('teammateMessage').textContent,'New session');
  assert.equal(cancelled.requests.find(r=>r.body?.kind==='delivery').path,'/api/sessions/'+oldId+'/events');
  assert.equal(cancelled.requests.find(r=>r.body?.kind==='delivery').body.reading_exposure_ms,0);
  assert.equal(cancelled.run("session.events.some(e=>e.event==='PREPARATION_END')"),false);
  console.log(task+': current-trial replies, expiry, fresh drafts, immutable save retries, input focus, active/silent display and cancelled-run isolation passed.');
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
