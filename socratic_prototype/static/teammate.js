'use strict';
const teammate={id:null,preparing:false,early:0,decision:null,feedback:null,response:'',deliveryPending:Promise.resolve(),pending:new Set()};
const knownPseudonyms=new Set();
let calibrationRefreshVersion=0;
async function api(path,body){
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw Error(data.error||'Server request failed');return data;
}
function track(promise){teammate.pending.add(promise);promise.finally(()=>teammate.pending.delete(promise)).catch(()=>{});return promise;}
function configureProtocol(){
  const full=by('protocol').value==='full';configs.MAB.stable_trials=full?50:10;configs.MAB.volatile_trials=full?150:30;configs.TBS.blocks=full?24:3;
}
function syncPseudonymSelection(){
  const participant=by('participantId').value.trim();
  by('knownParticipant').value=knownPseudonyms.has(participant)?participant:'';
}
function renderPseudonyms(){
  const select=by('knownParticipant');select.replaceChildren();
  const blank=document.createElement('option');blank.value='';
  blank.textContent=knownPseudonyms.size?'Choose a saved pseudonym':'No saved pseudonyms yet';select.append(blank);
  for(const participant of [...knownPseudonyms].sort((a,b)=>a.localeCompare(b))){
    const option=document.createElement('option');option.value=participant;option.textContent=participant;select.append(option);
  }
  select.disabled=!knownPseudonyms.size;syncPseudonymSelection();
}
async function refreshPseudonyms(){
  try{
    const sessions=await api('/api/sessions');
    for(const session of sessions)knownPseudonyms.add(session.participant_id);
    renderPseudonyms();
  }catch(e){
    const select=by('knownParticipant'),notice=document.createElement('option');
    notice.value='';notice.textContent='Saved pseudonyms unavailable';select.replaceChildren(notice);select.disabled=true;
  }
}
function changeParticipant(){
  syncPseudonymSelection();by('setupError').textContent='';
  for(const id of ['mabCalibration','tbsCalibration'])by(id).value='';
  return refreshCalibration();
}
async function refreshCalibration(){
  const version=++calibrationRefreshVersion,participant=by('participantId').value.trim(),protocol=by('protocol').value;
  try{
    const sessions=await api('/api/sessions?participant='+encodeURIComponent(participant));
    if(version!==calibrationRefreshVersion||participant!==by('participantId').value.trim()||protocol!==by('protocol').value)return;
    for(const task of ['MAB','TBS']){
      const select=by(task==='MAB'?'mabCalibration':'tbsCalibration');const current=select.value;select.replaceChildren();
      const blank=document.createElement('option');blank.value='';blank.textContent='Choose a completed '+task+' calibration';select.append(blank);
      for(const s of sessions.filter(x=>x.task===task&&x.phase==='calibration'&&x.completed&&x.protocol===protocol)){
        const option=document.createElement('option');option.value=s.id;option.textContent=s.trials+' trials · '+new Date(s.created_at).toLocaleString();select.append(option);
      }
      if([...select.options].some(x=>x.value===current)&&current)select.value=current;
      else if(select.options.length>1)select.selectedIndex=1;
    }
    const calibrated=!!by('mabCalibration').value&&!!by('tbsCalibration').value;
    by('setupStatus').textContent=calibrated?'Both calibration tasks are ready for comparison sessions.':'Complete unassisted calibration in both tasks before running comparison sessions.';
  }catch(e){if(version===calibrationRefreshVersion&&participant===by('participantId').value.trim()&&protocol===by('protocol').value)by('setupError').textContent='Start the local Python server to connect: '+e.message;}
}
function updateSetup(){
  const calibration=by('sessionPhase').value==='calibration';by('condition').disabled=calibration;if(calibration)by('condition').value='A';
  by('startMab').textContent='Start MAB '+(calibration?'calibration':'comparison');by('startTbs').textContent='Start TBS '+(calibration?'calibration':'comparison');
  void refreshCalibration();
}
async function connectTeammate(task){
  const participant=by('participantId').value.trim();
  const calibrationIds={MAB:by('mabCalibration').value,TBS:by('tbsCalibration').value};
  if(by('sessionPhase').value==='assisted'){
    const missing=Object.keys(calibrationIds).filter(task=>!calibrationIds[task]);
    if(missing.length)throw Error('Comparison sessions require completed MAB and TBS calibrations. Missing: '+missing.join(' and ')+'. Complete and select them using the same participant pseudonym and protocol.');
  }
  const response=await api('/api/sessions',{
    id:session.id,participant_id:participant,task,condition:by('condition').value,
    phase:by('sessionPhase').value,protocol:by('protocol').value,preference:by('promptFrequency').value,
    calibration_ids:calibrationIds,seed:session.random_seed});
  teammate.id=response.id;teammate.preparing=false;teammate.pending.clear();teammate.deliveryPending=Promise.resolve();
  session.teammate_configuration=response;session.teammate_events=[];
  knownPseudonyms.add(participant);renderPseudonyms();
}
function publicEvaluation(t){
  const base={kind:'evaluation',trial_id:t.trial_uid,index:t.global_trial};
  if(session.task==='MAB')return {...base,score:t.score_before,options:t.available_options.map(o=>({id:o.id,key:o.key,outcomes:o.outcomes}))};
  return {...base,points:t.points_before,target:t.target,remaining:t.remaining_trials_including_current,block:t.block,multiplier:t.multiplier,
    options:t.available_options.map(o=>({id:o.option_id,key:o.key,amount:o.amount,probability:o.probability}))};
}
function publicFeedback(t){
  const base={kind:'feedback',trial_id:t.trial_uid,index:t.global_trial,timed_out:(t.selected_option||t.chosen_option)==='NO_RESPONSE',response_ms:t.response_time_ms};
  if(session.task==='MAB')return {...base,choice:t.selected_option,outcome:t.outcome,score_after:t.score_after};
  return {...base,choice:t.chosen_option,outcome:t.earned_points,points_after:t.points_after};
}
function sendEvent(event){const sid=teammate.id,owner=session;return track(api('/api/sessions/'+sid+'/events',event).then(response=>{owner.teammate_events.push(response.record);return response;}));}
function recordEarlyAttempt(key){
  if(!['1','2','3','7','8','9'].includes(key))return;
  teammate.early++;logEvent('PREPARATION_EARLY_RESPONSE_ATTEMPT',{key});
}
document.addEventListener('keydown',e=>{
  if(teammate.preparing&&!['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)&&['1','2','3','7','8','9'].includes(e.key)){
    e.preventDefault();recordEarlyAttempt(e.key);
  }
});
for(const button of by('responseButtons').querySelectorAll('button'))button.onclick=()=>{
  teammate.feedback=button.dataset.feedback;
  for(const other of by('responseButtons').querySelectorAll('button'))other.classList.toggle('selected',other===button);
};
async function teammatePreparation(t,token){
  teammate.preparing=true;teammate.early=0;teammate.feedback=null;teammate.decision=null;
  by('responseText').value='';for(const b of by('responseButtons').querySelectorAll('button'))b.classList.remove('selected');
  by('teammateResponse').classList.add('hidden');by('teammatePanel').classList.remove('hidden');
  by('teammateHeading').textContent='Preparation window';by('teammateMessage').textContent='Take a moment to prepare. Choices open after this window.';
  if(session.task==='MAB')content('<div class="big">+</div>');
  for(const b of by('taskarea').querySelectorAll('button'))b.setAttribute('aria-disabled','true');
  by('timingNote').textContent='Choice input disabled during preparation';
  await nextPaint();const startMs=clock();logEvent('PREPARATION_ONSET',{duration_ms:session.teammate_configuration.policy.preparation_ms,options_visible:session.task==='TBS'});
  let shownAt=null,result=null,error=null,windowOpen=true,receivedAt=null;
  const request=track(sendEvent(publicEvaluation(t)).then(r=>{
    result=r;receivedAt=clock();const d=r.record.snapshot.decision;teammate.decision=d;
    if(windowOpen&&alive&&token===runId&&d.action!=='silence'){
      shownAt=clock();by('teammateMessage').textContent=d.message;by('teammateHeading').textContent='Teammate · '+d.action;
      by('teammateResponse').classList.remove('hidden');logEvent('INTERVENTION_DISPLAY',{decision_id:d.id,action:d.action});
    }
  }).catch(e=>{error=e;}));
  const duration=session.teammate_configuration.policy.preparation_ms;
  while(alive&&token===runId&&clock()-startMs<duration){
    by('prepCountdown').textContent=((duration-(clock()-startMs))/1000).toFixed(1)+' s';await sleep(Math.min(50,duration-(clock()-startMs)));
  }
  windowOpen=false;teammate.preparing=false;
  const endedAt=clock();by('teammatePanel').classList.add('hidden');
  const responseText=by('responseText').value.trim();const feedback=teammate.feedback;
  // Delivery acknowledgements are queued without extending the fixed window.
  // A late result is recorded as unexposed and cannot change the next choice.
  teammate.deliveryPending=track(request.then(async()=>{
    if(!alive||token!==runId)return;
    if(error)throw error;
    const d=result.record.snapshot.decision;
    const latency=d.language?.generation_ms||0;
    logEvent('PREPARATION_END',{decision_id:d.id,delivered:shownAt!==null,generation_latency_ms:latency,
      reading_exposure_ms:shownAt===null?0:endedAt-shownAt,early_attempts:teammate.early,
      request_roundtrip_ms:receivedAt-startMs,duration_ms:endedAt-startMs,result_late:receivedAt>endedAt});
    await sendEvent({kind:'delivery',decision_id:d.id,index:t.global_trial,delivered:shownAt!==null,
      generation_latency_ms:latency,reading_exposure_ms:shownAt===null?0:endedAt-shownAt,early_attempts:teammate.early});
    if(shownAt!==null&&(feedback||responseText))await sendEvent({kind:'response',decision_id:d.id,index:t.global_trial,
      feedback:feedback||'dismiss',text:responseText,hypothesis:d.hypothesis,...(session.task==='TBS'?{block:t.block}:{})});
  }));
  teammate.deliveryPending.catch(e=>{if(alive&&token===runId)showError(e);});
  for(const b of by('taskarea').querySelectorAll('button'))b.removeAttribute('aria-disabled');
}
async function teammateFeedback(t){
  // Called after score fields and final-trial scoring are finalized.
  await teammate.deliveryPending;await sendEvent(publicFeedback(t));
}
async function finishTeammate(completed){
  if(!teammate.id)return;const sid=teammate.id;await Promise.all([...teammate.pending]);
  await api('/api/sessions/'+sid+'/finish',{completed});void refreshCalibration();
}
async function downloadTrace(){
  if(!teammate.id){by('setupError').textContent='Run a session first, or export an earlier session in the inspector.';return;}
  const s=await api('/api/sessions/'+teammate.id+'/export');blobDownload(s.id+'_teammate.json',JSON.stringify(s,null,2),'application/json');
}
by('downloadTrace').onclick=()=>downloadTrace().catch(e=>by('setupError').textContent=e.message);
by('sessionPhase').onchange=updateSetup;by('protocol').onchange=updateSetup;
by('participantId').oninput=syncPseudonymSelection;by('participantId').onchange=changeParticipant;
by('knownParticipant').onchange=()=>{
  if(!by('knownParticipant').value)return;
  by('participantId').value=by('knownParticipant').value;return changeParticipant();
};
void refreshPseudonyms();
updateSetup();
