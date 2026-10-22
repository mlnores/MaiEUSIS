'use strict';
// Identity/calibration setup runs against the actual script, with delayed replies.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(){this.value='';this.textContent='';this.disabled=false;this.children=[];this.options=[];}
 append(...items){this.children.push(...items);this.options.push(...items);}
 replaceChildren(...items){this.children=[];this.options=[];this.value='';this.append(...items);}
 set selectedIndex(i){this.value=this.options[i]?.value||'';}
 querySelectorAll(){return [];}
}
const row=(name,task,completed=true,protocol='short')=>({participant_id:name,task,completed,protocol,phase:'calibration',id:name+'_'+task+'_'+protocol,trials:task==='MAB'?40:24,created_at:'2026-10-20T12:00:00Z'});
const records=[row('zeta','MAB'),row('alpha','MAB'),row('alpha','TBS'),row('beta','MAB',false),row('zeta','TBS'),row('alpha','MAB',true,'full')];
function harness(sessions,{unavailable=false}={}){
 const ids=['participantId','knownParticipant','sessionPhase','protocol','condition','startMab','startTbs','setupStatus','setupError','mabCalibration','tbsCalibration','responseButtons','responseText','submitReply','downloadTrace','promptFrequency'];
 const el=Object.fromEntries(ids.map(id=>[id,new Element()]));
 Object.assign(el.participantId,{value:'new_participant'});el.sessionPhase.value='calibration';el.protocol.value='short';el.promptFrequency.value='standard';
 const delayed=new Map(),requests=[];
 const context=vm.createContext({by:id=>el[id],document:{createElement:()=>new Element(),addEventListener(){}},
 configs:{MAB:{},TBS:{}},session:{id:'fixture_new_session',random_seed:'fixture_seed'},console,
 fetch:async(path,options)=>{
  requests.push({path,body:options?.body===undefined?undefined:JSON.parse(options.body)});
  if(unavailable)throw Error('Offline fixture');
  const participant=path.includes('?')?decodeURIComponent(path.split('participant=')[1]):null;
  const data=options?.body!==undefined?{id:'fixture_new_session',policy:{preparation_ms:4000}}:
   participant===null?sessions:sessions.filter(s=>s.participant_id===participant);
  return {ok:true,json:async()=>delayed.has(participant)?await delayed.get(participant):data};
 }});
 vm.runInContext(fs.readFileSync('socratic_prototype/static/teammate.js','utf8'),context);
 return {el,context,requests,delayed};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const h=harness(records);await flush();
 assert.deepEqual(h.el.knownParticipant.options.map(o=>o.value),['','alpha','beta','zeta']);
 assert.equal(h.el.participantId.value,'new_participant','Loading names must not replace a typed pseudonym');
 h.el.knownParticipant.value='alpha';await h.el.knownParticipant.onchange();
 assert.equal(h.el.participantId.value,'alpha');
 assert.equal(h.el.mabCalibration.value,'alpha_MAB_short');assert.equal(h.el.tbsCalibration.value,'alpha_TBS_short');
 h.el.participantId.value='brand_new';h.el.participantId.oninput();assert.equal(h.el.knownParticipant.value,'');
 await h.el.participantId.onchange();
 assert.equal(h.el.mabCalibration.value,'');assert.equal(h.el.tbsCalibration.value,'');
 await vm.runInContext("connectTeammate('MAB')",h.context);
 assert.ok(h.el.knownParticipant.options.some(o=>o.value==='brand_new'));
 assert.equal(h.el.knownParticipant.value,'brand_new');
 assert.equal(h.requests.find(r=>r.body)?.body.participant_id,'brand_new');
 h.el.participantId.value='alpha';h.el.participantId.oninput();assert.equal(h.el.knownParticipant.value,'alpha');
 let release;h.delayed.set('alpha',new Promise(resolve=>{release=resolve;}));
 const pending=h.el.participantId.onchange();
 h.el.knownParticipant.value='zeta';await h.el.knownParticipant.onchange();
 release(records.filter(s=>s.participant_id==='alpha'));await pending;
 assert.equal(h.el.mabCalibration.value,'zeta_MAB_short','A stale participant response must not replace current calibrations');
 assert.equal(h.el.tbsCalibration.value,'zeta_TBS_short');
 h.el.participantId.value='alpha';h.delayed.delete('alpha');h.el.protocol.value='full';await h.el.participantId.onchange();
 assert.equal(h.el.mabCalibration.value,'alpha_MAB_full');assert.equal(h.el.tbsCalibration.value,'');
 const empty=harness([]);await flush();assert.equal(empty.el.knownParticipant.disabled,true);
 assert.equal(empty.el.knownParticipant.options[0].textContent,'No saved pseudonyms yet');
 assert.equal(empty.el.participantId.value,'new_participant');
 const offline=harness([],{unavailable:true});await flush();
 assert.equal(offline.el.knownParticipant.disabled,true);assert.equal(offline.el.knownParticipant.options[0].textContent,'Saved pseudonyms unavailable');
 assert.equal(offline.el.participantId.value,'new_participant');
 console.log('Pseudonym selector: saved names, manual entry, new names, calibration refresh, protocol filtering, stale replies and empty/offline stores passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
