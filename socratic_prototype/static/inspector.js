'use strict';
const el=id=>document.getElementById(id);let current=null,selected=0,visible=[];
const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
async function read(path){const r=await fetch(path);const v=await r.json();if(!r.ok)throw Error(v.error||'Request failed');return v;}
function report(e){el('error').textContent=e.message||String(e);}
async function refresh(){
 const sessions=await read('/api/sessions');const previous=el('sessionSelect').value;el('sessionSelect').replaceChildren();
 if(!sessions.length){el('sessionSelect').append(node('option','No sessions recorded'));return;}
 for(const s of sessions){const o=node('option',`${s.participant_id} · ${s.task} · ${s.phase} ${s.condition} · ${s.trials}/${s.total_trials} · ${s.completed?'complete':s.finished?'ended':'active'}`);o.value=s.id;el('sessionSelect').append(o);}
 if(sessions.some(x=>x.id===previous))el('sessionSelect').value=previous;
 await load();
}
async function load(){
 current=await read('/api/sessions/'+el('sessionSelect').value);selected=0;el('error').textContent='';el('replayStatus').textContent='';
 el('sessionMeta').textContent=`${current.id} · ${current.protocol} protocol · ${current.schema_version} · ${current.model_version} · ${current.policy.version} · ${current.network.backend} · ${current.events.length} events`;
 filter();
}
function filter(){visible=current.events.filter(e=>e.snapshot&&(el('eventFilter').value==='all'||e.input.kind===el('eventFilter').value));selected=Math.min(selected,Math.max(0,visible.length-1));renderList();render();}
function renderList(){
 el('eventList').replaceChildren();visible.forEach((e,i)=>{const d=e.snapshot.decision;const b=node('button',`Trial ${e.input.index} · ${e.input.kind}${d?' · '+d.action:''}`,i===selected?'selected':'');b.onclick=()=>{selected=i;renderList();render();};el('eventList').append(b);});
 el('prev').disabled=selected===0;el('next').disabled=selected>=visible.length-1;
}
function details(parent,title,data){const d=node('details');d.append(node('summary',title),node('pre',JSON.stringify(data,null,2)));parent.append(d);}
function paragraph(parent,text,cls){parent.append(node('p',text,cls));}
function table(parent,columns,rows){const t=node('table');const head=node('tr');for(const c of columns)head.append(node('th',c));t.append(head);for(const row of rows){const tr=node('tr');for(const cell of row)tr.append(node('td',String(cell)));t.append(tr);}parent.append(t);}
function render(){
 const root=el('detail');root.replaceChildren();if(!visible.length){paragraph(root,'No state updates yet.');return;}
 const e=visible[selected],s=e.snapshot,d=s.decision;root.append(node('h2',`Trial ${e.input.index} · ${e.input.kind}`));
 paragraph(root,e.timestamp+' · '+e.id,'muted small');
 if(d){
  root.append(node('h3','Policy decision · '+d.action));paragraph(root,d.message||'No message generated.');paragraph(root,d.rationale);
  const exposure=current.events.find(x=>x.input.kind==='delivery'&&x.input.decision_id===d.id);
  paragraph(root,exposure?`Delivered: ${exposure.input.delivered?'yes':'no'} · generation latency ${exposure.input.generation_latency_ms.toFixed(1)} ms · reading exposure ${exposure.input.reading_exposure_ms.toFixed(1)} ms · early attempts ${exposure.input.early_attempts}`:'Delivery acknowledgement not yet recorded.','small muted');
  const responses=current.events.filter(x=>x.input.kind==='response'&&x.input.decision_id===d.id);
  for(const response of responses)paragraph(root,`Participant feedback (${response.input.feedback}): ${response.input.text||'(no text)'} · ${response.attribution}`);
  if(d.candidates.length)table(root,['Candidate','Action','Score','Interpretation'],d.candidates.map(c=>[c.name,c.action,c.score,c.argument_evaluation]));
  details(root,'Full decision and validated language output',d);
 }else paragraph(root,s.policy_status,'muted');
 root.append(node('h3','Claims and epistemic annotations'));
 for(const c of s.claims){
  const section=node('div',undefined,'claim');section.append(node('h3',c.type+' · '+c.id.split('_event_')[1]));paragraph(section,c.content);
  const tags=node('div',undefined,'tags');for(const status of c.statuses)tags.append(node('span',status,'tag '+status));section.append(tags);
  paragraph(section,`Source: ${c.provenance} · Scope: ${c.scope}`,'small muted');
  paragraph(section,'Evidence: '+c.evidence.join(', '),'small muted');
  if(c.confidence!==undefined)paragraph(section,`Posterior ${c.confidence.toFixed(3)} · ${c.confidence_interpretation}`,'small');
  if(c.alternatives){const ul=node('ul');for(const a of c.alternatives)ul.append(node('li',a));section.append(node('strong','Competing explanations'),ul);}
  if(c.revision_conditions)paragraph(section,'Reconsider when: '+c.revision_conditions.join(' '),'small');
  details(section,'Relations and provenance',c);root.append(section);
 }
 root.append(node('h3','Supporting and opposing reasons'));
 if(!s.arguments.length)paragraph(root,'No candidate arguments at this point.','muted');
 for(const a of s.arguments)paragraph(root,`${a.status} · ${a.conclusion}: ${a.reason}`);
 if(s.environment.arms)table(root,['Arm','Samples','Estimated value','P(change)'],s.environment.arms.map(a=>[a.arm,a.samples,a.estimated_value,a.change.samples<6?'insufficient evidence':a.change.posterior]));
 details(root,'Environment model',s.environment);details(root,'Participant model and calibration',s.participant);
 details(root,'Record validation',s.validation);details(root,'SHACL validation report',s.shacl);
 details(root,'Exact permitted input event',e.input);details(root,'Fixed policy parameters',current.policy);details(root,'Provisional Bayesian network CPTs',current.network);
 details(root,'Calibration sources',current.calibration_sources);details(root,'Descriptive session summary',current.summary);
}
function download(name,data,type){const url=URL.createObjectURL(new Blob([data],{type}));const a=node('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
el('refresh').onclick=()=>refresh().catch(report);el('sessionSelect').onchange=()=>load().catch(report);el('eventFilter').onchange=filter;
el('prev').onclick=()=>{selected--;renderList();render();};el('next').onclick=()=>{selected++;renderList();render();};
el('verify').onclick=async()=>{if(!current)return;try{el('replayStatus').textContent='Recomputing models and decisions…';const r=await read('/api/sessions/'+current.id+'/replay');el('replayStatus').textContent=`Replay matches · ${r.events_replayed} events · ${r.api_calls} API calls · SHA-256 ${r.digest}`;}catch(e){el('replayStatus').textContent='Replay failed';report(e);}};
el('exportJson').onclick=()=>{if(current)download(current.id+'_teammate.json',JSON.stringify(current,null,2),'application/json');};
el('exportRdf').onclick=async()=>{if(!current)return;try{const r=await fetch('/api/sessions/'+current.id+'/knowledge.ttl');if(!r.ok)throw Error('RDF export failed');download(current.id+'_knowledge.ttl',await r.text(),'text/turtle');}catch(e){report(e);}};
refresh().catch(report);
