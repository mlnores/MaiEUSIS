'use strict';
const teammate={id:null,preparing:false,early:0,decision:null,feedback:null,response:'',deliveryPending:Promise.resolve(),pending:new Set(),presentation:null,visibleMessage:null,replies:new Map(),replyTarget:null};
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
  teammate.presentation=null;teammate.visibleMessage=null;teammate.replies.clear();teammate.replyTarget=null;
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
function sendEvent(event,sid=teammate.id,owner=session){return track(api('/api/sessions/'+sid+'/events',event).then(response=>{owner.teammate_events.push(response.record);return response;}));}
function recordEarlyAttempt(key){
  if(!['1','2','3','7','8','9'].includes(key))return;
  teammate.early++;logEvent('PREPARATION_EARLY_RESPONSE_ATTEMPT',{key});
}
document.addEventListener('keydown',e=>{
  if(teammate.preparing&&!['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)&&['1','2','3','7','8','9'].includes(e.key)){
    e.preventDefault();recordEarlyAttempt(e.key);
  }
});
function presentationContext(p){
  return {trial_uid:p.trial.trial_uid,global_trial:p.trial.global_trial,block:p.trial.block??'',
    stage:p.trial.stage??'',trial:p.trial.trial??''};
}
function teammateState(state,decision=null){
  const panel=by('teammatePanel'),p=teammate.presentation;
  panel.classList.remove('hidden');panel.classList.toggle('is-active',state==='active');panel.classList.toggle('is-silent',state!=='active');
  panel.dataset.state=state;
  by('teammateHeading').textContent=state==='active'?'Teammate · active · '+decision.action:state==='pending'?'Teammate · preparing':'Teammate · silent';
  by('teammateMessage').textContent=teammate.visibleMessage?.message||'No intervention for this trial.';
  by('teammateContext').textContent=state==='active'?'Current intervention · trial '+p.trial.global_trial:
    teammate.visibleMessage?'Previous intervention · trial '+teammate.visibleMessage.trial.global_trial+' · no active intervention.':
    state==='pending'?'Choices open after preparation.':'No active intervention.';
  renderReplies();
}
function endMessageVisibility(reason){
  const message=teammate.visibleMessage;if(!message)return;
  logEvent('INTERVENTION_VISIBILITY_END',{...presentationContext(message),decision_id:message.decision_id,
    visible_ms:clock()-message.shownAt,active_exposure_ms:(message.activeEndedAt??clock())-message.shownAt,reason});
  teammate.visibleMessage=null;
}
function currentReply(){return teammate.replies.get(teammate.replyTarget);}
function replyIsActive(entry){
  return !!entry&&entry.p===teammate.presentation&&!entry.p.closed&&entry.p.owner===session&&entry.p.sid===teammate.id;
}
function captureReplyDraft(){
  const entry=currentReply();if(entry&&!entry.payload&&replyIsActive(entry))entry.text=by('responseText').value;
}
function renderReplies(){
  const entry=currentReply(),active=replyIsActive(entry),retry=entry?.status==='error'&&!!entry.payload;
  by('teammateResponse').classList.remove('hidden');
  by('replyQuestion').textContent=entry?.decision.message||'';
  by('responseText').value=entry?.text||'';
  const locked=!active||['saving','saved'].includes(entry?.status)||retry;
  by('responseText').disabled=locked;by('submitReply').disabled=retry?false:locked;
  by('submitReply').textContent=retry?'Retry saving':'Save response';
  for(const button of by('responseButtons').querySelectorAll('button')){
    button.disabled=locked;button.classList.toggle('selected',!!entry&&entry.feedback===button.dataset.feedback);
  }
  const status=by('replyStatus');status.classList.remove('hidden');
  status.textContent=!entry?'No active intervention. Replies are disabled.':active?(entry.notice||'Optional. Save your response before this trial ends.'):
    entry.status==='saved'?'Reply closed · Response saved.':
    entry.status==='saving'?'Reply closed · Your submitted response is being saved.':
    retry?'Reply closed · Save not confirmed. Retry saving your already-submitted response.':
    entry.text||entry.feedback?'Reply closed · This trial has ended. Your draft was not submitted.':
    'Reply closed · No response is expected for this previous intervention.';
}
function addReply(p,decision){
  const entry={p,decision,text:'',feedback:null,status:'draft',notice:'',submission:null,payload:null};
  teammate.replies.set(decision.id,entry);
  // A new intervention starts a fresh response window; previous drafts stay closed.
  teammate.replyTarget=decision.id;
}
by('responseText').oninput=captureReplyDraft;
for(const button of by('responseButtons').querySelectorAll('button'))button.onclick=()=>{
  const entry=currentReply();if(!replyIsActive(entry)||entry.payload)return;
  captureReplyDraft();entry.feedback=entry.feedback===button.dataset.feedback?null:button.dataset.feedback;renderReplies();
};
function submitTeammateReply(){
  captureReplyDraft();const entry=currentReply();if(!entry)return Promise.resolve(false);
  if(entry.status==='saving')return entry.submission;
  // Retrying an immutable, timely submission is distinct from answering a closed question.
  if(!replyIsActive(entry)&&!entry.payload){renderReplies();return Promise.resolve(false);}
  if(entry.status==='saved')return Promise.resolve(true);
  const text=entry.text.trim();if(!text&&!entry.feedback){entry.notice='Write a reply or choose feedback before saving.';renderReplies();return Promise.resolve(false);}
  const p=entry.p,decision=entry.decision;
  const payload=entry.payload||{kind:'response',decision_id:decision.id,index:p.trial.global_trial,feedback:entry.feedback||'reply',
    text,hypothesis:decision.hypothesis,...(p.owner.task==='TBS'?{block:p.trial.block}:{})};
  entry.payload=payload;entry.status='saving';entry.notice=p.closed?'Saving response…':'Response queued; saving when this trial ends…';renderReplies();
  entry.submission=track((async()=>{
    try{
      await p.deliveryReady;
      const result=await sendEvent(payload,p.sid,p.owner);
      entry.status='saved';entry.notice=result.record.interpretation?.status==='pending-review'?
        'Response saved · interpretation awaiting researcher review.':'Response saved.';
      return true;
    }catch(error){entry.status='error';entry.notice='Response not confirmed. Your draft is retained. Retry saving: '+error.message;return false;}
    finally{
      if(session===p.owner&&teammate.replies.get(decision.id)===entry)renderReplies();
    }
  })());
  return entry.submission;
}
by('submitReply').onclick=()=>{void submitTeammateReply();};
async function teammatePreparation(t,token){
  captureReplyDraft();teammate.preparing=true;teammate.early=0;teammate.decision=null;
  const p={trial:t,token,sid:teammate.id,owner:session,shownAt:null,result:null,error:null,receivedAt:null,
    windowOpen:true,closed:false,request:null,delivery:null,early:0};
  teammate.presentation=p;
  p.deliveryReady=new Promise((resolve,reject)=>{p.resolveDelivery=resolve;p.rejectDelivery=reject;});
  p.deliveryReady.catch(()=>{});
  teammateState('pending');
  if(session.task==='MAB')content('<div class="big">+</div>');
  for(const b of by('taskarea').querySelectorAll('button'))b.setAttribute('aria-disabled','true');
  by('timingNote').textContent='Choice input disabled during preparation';
  await nextPaint();if(p.closed||!alive||token!==runId)return;p.startedAt=clock();logEvent('PREPARATION_ONSET',{duration_ms:session.teammate_configuration.policy.preparation_ms,options_visible:false});
  p.request=track(sendEvent(publicEvaluation(t),p.sid,p.owner).then(r=>{
    p.result=r;p.receivedAt=clock();const d=r.record.snapshot.decision;
    if(!p.closed&&teammate.presentation===p)teammate.decision=d;
    if(p.windowOpen&&!p.closed&&alive&&token===runId){
      if(d.action==='silence')teammateState('silent');
      else{
        endMessageVisibility('replaced');p.shownAt=clock();
        teammate.visibleMessage={trial:t,decision_id:d.id,message:d.message,shownAt:p.shownAt,activeEndedAt:null};
        addReply(p,d);teammateState('active',d);logEvent('INTERVENTION_DISPLAY',{decision_id:d.id,action:d.action,presentation:'persistent-trial'});
      }
    }else if(!p.closed){
      logEvent('INTERVENTION_RESULT_LATE',{...presentationContext(p),decision_id:d.id,request_roundtrip_ms:p.receivedAt-p.startedAt});
    }
  }).catch(e=>{p.error=e;}));
  const duration=session.teammate_configuration.policy.preparation_ms;
  while(alive&&token===runId&&clock()-p.startedAt<duration){
    by('prepCountdown').textContent='Preparation · '+((duration-(clock()-p.startedAt))/1000).toFixed(1)+' s';await sleep(Math.min(50,duration-(clock()-p.startedAt)));
  }
  if(teammate.presentation!==p||session!==p.owner)return;
  p.windowOpen=false;p.prepEndedAt=clock();p.early=teammate.early;
  // A cancelled run must not change the panel or countdown of a newer run.
  if(teammate.presentation===p){
    teammate.preparing=false;by('prepCountdown').textContent='';
    if(p.shownAt===null)teammateState('silent');
  }
  logEvent('PREPARATION_END',{...presentationContext(p),decision_id:p.result?.record.snapshot.decision.id??null,
    delivered:p.shownAt!==null,generation_latency_ms:p.result?.record.snapshot.decision.language?.generation_ms??null,
    reading_exposure_ms:p.shownAt===null?0:p.prepEndedAt-p.shownAt,early_attempts:p.early,
    request_roundtrip_ms:p.receivedAt===null?null:p.receivedAt-p.startedAt,duration_ms:p.prepEndedAt-p.startedAt,
    result_late:p.receivedAt===null||p.receivedAt>p.prepEndedAt});
  for(const b of by('taskarea').querySelectorAll('button'))b.removeAttribute('aria-disabled');
}
function closeTeammatePresentation(reason){
  const p=teammate.presentation;if(!p)return Promise.resolve();if(p.closed)return p.delivery||Promise.resolve();
  captureReplyDraft();p.closed=true;p.windowOpen=false;p.endedAt=clock();teammate.preparing=false;
  const early=p.prepEndedAt===undefined?teammate.early:p.early;
  const exposure=p.shownAt===null?0:p.endedAt-p.shownAt;
  if(teammate.visibleMessage&&teammate.visibleMessage.decision_id===p.result?.record.snapshot.decision.id)teammate.visibleMessage.activeEndedAt=p.endedAt;
  if(p.shownAt!==null)logEvent('INTERVENTION_ACTIVE_END',{...presentationContext(p),decision_id:p.result.record.snapshot.decision.id,
    reading_exposure_ms:exposure,reason});
  teammateState('silent');
  // Acknowledge full active exposure before saving any explicitly submitted reply.
  p.delivery=track(Promise.resolve(p.request).then(async()=>{
    if(p.error)throw p.error;if(!p.result)return;
    const d=p.result.record.snapshot.decision;
    await sendEvent({kind:'delivery',decision_id:d.id,index:p.trial.global_trial,delivered:p.shownAt!==null,
      generation_latency_ms:d.language?.generation_ms||0,reading_exposure_ms:exposure,early_attempts:early},p.sid,p.owner);
    p.resolveDelivery();
    const entry=teammate.replies.get(d.id);if(entry?.submission)await entry.submission;
  }).catch(error=>{p.rejectDelivery(error);throw error;}));
  teammate.deliveryPending=p.delivery;return p.delivery;
}
async function teammateFeedback(t){
  // The message stays active through choice, commitment, feedback and intertrial fixation.
  await closeTeammatePresentation('trial-complete');await sendEvent(publicFeedback(t));
}
async function finishTeammate(completed){
  if(!teammate.id)return;const sid=teammate.id;
  const closing=closeTeammatePresentation('session-ended');endMessageVisibility('session-ended');
  const pending=[...teammate.pending];await closing;await Promise.all(pending);
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
