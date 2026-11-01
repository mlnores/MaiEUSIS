'use strict';
configs.REFERENCE={trials:4,response_timeout_ms:5000,fixation_ms:1000,feedback_ms:1000,intertrial_fixation_ms:1000};
async function runReference(token){
 const cfg=configs.REFERENCE;let points=0;
 for(let index=1;index<=cfg.trials;index++){
  if(!alive||token!==runId)return;await checkPause(token);if(!alive||token!==runId)return;
  const ps=index%2?[.75,.25]:[.25,.75];
  const options=['left','right'].map((id,i)=>({id,key:i?'9':'1',probability:ps[i]}));
  by('taskProgress').textContent=`Trial ${index}/${cfg.trials}`;metrics([['Points',points],['Trials remaining',cfg.trials-index+1]]);
  const t=createTrial({global_trial:index,trial:index,phase:'evaluation',available_options:deep(options),points_before:points,points_after:null,chosen_option:null,response_time_ms:null,earned_points:0});
  appendOptions(t,options.map(o=>({...o,option_id:o.id})));
  await teammatePreparation(t,token);if(!alive||token!==runId)return;
  content('<div class="choose">'+options.map(o=>`<button class="option" data-key="${o.key}" onclick="clickChoice('${o.key}')"><strong>${o.id.toUpperCase()}</strong><p>Win chance: ${o.probability*100}%</p><p>1 point · Press ${o.key}</p></button>`).join('')+'</div>');phase('eval');
  await nextPaint();if(!alive||token!==runId)return;
  const onset=screenEvent('EVALUATION_ONSET',{options:deep(options),points_before:points});t.evaluation_iso=onset.iso_time;t.evaluation_monotonic_ms=onset.monotonic_ms;
  const result=await waitChoice(options.map(o=>o.key),cfg.response_timeout_ms,left=>{by('timingNote').textContent=`Time remaining: ${(left/1000).toFixed(1)} s`;});
  if(result.cancelled||!alive||token!==runId)return;
  t.response_time_ms=result.response_ms;
  if(result.key){
   const option=options.find(o=>o.key===result.key);t.chosen_option=option.id;phase('commit');screenEvent('COMMITMENT_RESPONSE',{choice:option.id,key:option.key,response_time_ms:result.response_ms});
   content('<div class="big">+</div>');await nextPaint();screenEvent('FIXATION_ONSET');await sleep(cfg.fixation_ms);if(!alive||token!==runId)return;
   t.random_draw=rnd();t.earned_points=Number(t.random_draw<option.probability);points+=t.earned_points;
   phase('feed');content(`<div class="big">${t.earned_points?'WIN · +1':'NO GAIN'}</div>`);await nextPaint();screenEvent('FEEDBACK_ONSET',{choice:option.id,earned_points:t.earned_points,points_after:points});
  }else{
   t.chosen_option='NO_RESPONSE';phase('feed');content('<div class="big">TIMEOUT</div>');await nextPaint();screenEvent('NO_RESPONSE_TIMEOUT',{points_after:points});
  }
  await sleep(cfg.feedback_ms);if(!alive||token!==runId)return;
  content('<div class="big">+</div>');await nextPaint();screenEvent('INTERTRIAL_FIXATION_ONSET');await sleep(cfg.intertrial_fixation_ms);
  t.points_after=points;await finalizeTrial(t);
 }
 if(alive&&token===runId)await finishTask(`Reference environment complete: ${points} points. Engineering extension check, not a validated research task.`);
}
registerBrowserTask('REFERENCE',{
 title:'Reference public-probability choice',startId:'startReference',calibrationId:'referenceCalibration',run:runReference,
 configureProtocol:protocol=>{if(protocol!=='mini')throw Error('Unknown reference protocol');configs.REFERENCE.trials=4;},
 prepare:()=>content('<div class="big">+</div>'),responseScope:()=>({}),
 evaluation:(t,base)=>({...base,points:t.points_before,options:t.available_options.map(o=>({id:o.id,key:o.key,probability:o.probability}))}),
 feedback:(t,base)=>({...base,timed_out:t.chosen_option==='NO_RESPONSE',choice:t.chosen_option,outcome:t.earned_points,points_after:t.points_after})
});
