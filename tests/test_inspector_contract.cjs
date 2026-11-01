'use strict';
// Execute the actual inspector script against a small DOM and HTTP contract.
// This verifies review controls and safe text rendering, not browser appearance.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag='DIV'){this.tagName=tag;this.children=[];this.textContent='';this.value='';this.disabled=false;this.attrs={};}
 append(...items){this.children.push(...items);}replaceChildren(...items){this.children=[...items];}
 setAttribute(key,value){this.attrs[key]=value;}click(){return this.onclick?.();}
}
const ids=['sessionSelect','error','replayStatus','sessionMeta','eventFilter','eventList','prev','next','detail',
 'refresh','verify','exportJson','exportRdf'];
const elements=new Map(ids.map(id=>[id,new Element()]));elements.get('eventFilter').value='all';
const decision={id:'d1',action:'ask',message:'What evidence would change your approach?',rationale:'Uncertain task evidence',candidates:[],
 language:{mode:'ollama-generated'},evidence_package:{condition:'F'}};
const snapshot={decision,claims:[],arguments:[],environment:{},participant:{},validation:{conforms:true},shacl:{conforms:true}};
snapshot.graph_argumentation={status:'complete',mode:'shadow',semantics:'grounded',backend:'rdflib-sparql',
 notice:'Researcher-only; argument labels do not establish truth.',
 assertions:[{id:'premise1',content:'Observed sampling',kind:'calculation',source:'urn:observed-history'},
             {id:'conclusion1',content:'Exploration warrants discussion',kind:'derived'}],
 arguments:[{id:'argument1',rule:'urn:exploration-rule',rule_kind:'defeasible',label:'undecided',priority:0,
  reason:'Exploration warrants discussion',conclusion:'conclusion1',premises:['premise1'],subarguments:[],
  critical_questions:['Is persistence intentional?']}],
 attacks:[],critical_questions:['Is persistence intentional?']};
const source={id:'s1',protocol:'short',schema_version:'ontology-0.1',model_version:'models-0.1',policy:{version:'policy-0.2'},
 network:{backend:'exact-enumeration'},events:[
 {id:'evaluation1',timestamp:'2026-10-15',input:{kind:'evaluation',index:7},snapshot},
 {id:'delivery1',input:{kind:'delivery',decision_id:'d1',delivered:true,generation_latency_ms:1200,reading_exposure_ms:2500,early_attempts:0}},
 {id:'response1',input:{kind:'response',decision_id:'d1',feedback:'dismiss',text:'I deliberately explore alternatives.'},
  attribution:'participant self-report; not established fact',interpretation:{status:'pending-review',proposal:{updates:[
    {kind:'reported_strategy',quote:'I deliberately explore alternatives.',hypothesis:null}]}}}]};
const originalDecision=JSON.stringify(decision),requests=[];
const sandbox={document:{getElementById:id=>elements.get(id),createElement:tag=>new Element(tag.toUpperCase())},
 fetch:async(path,options)=>{
  requests.push({path,options});let data;
  if(options){const body=JSON.parse(options.body);assert.equal(path,'/api/sessions/s1/events');
   assert.deepEqual(body,{kind:'interpretation-review',response_event_id:'response1',accept:true,reviewer:'local_researcher'});
   source.events.push({id:'review1',input:body});data={record:source.events.at(-1)};
  }else if(path==='/api/sessions')data=[{id:'s1',participant_id:'synthetic',task:'MAB',phase:'assisted',condition:'F',trials:7,total_trials:40,completed:false}];
  else if(path==='/api/sessions/s1')data=source;
  else throw Error('Unexpected endpoint: '+path);
  return {ok:true,json:async()=>JSON.parse(JSON.stringify(data))};
 },console,JSON,Blob,URL,setTimeout};
function find(root,predicate){if(predicate(root))return root;for(const child of root.children){const found=find(child,predicate);if(found)return found;}return null;}
(async()=>{
 const context=vm.createContext(sandbox);
 // A real select automatically selects the first appended option.
 const select=elements.get('sessionSelect');select.append=(...items)=>{select.children.push(...items);if(!select.value&&items[0])select.value=items[0].value;};
 vm.runInContext(fs.readFileSync('socratic_prototype/static/inspector.js','utf8'),context);
 for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));
 const root=elements.get('detail');const accept=find(root,e=>e.tagName==='BUTTON'&&e.textContent==='Accept proposed interpretation');
 assert.ok(find(root,e=>e.textContent==='Graph argumentation · shadow analysis'));
 assert.ok(find(root,e=>e.tagName==='TD'&&e.textContent==='undecided'));
 assert.ok(find(root,e=>e.tagName==='PRE'&&e.textContent.includes('urn:observed-history')));
 assert.ok(find(root,e=>e.tagName==='LI'&&e.textContent==='Is persistence intentional?'));
 assert.ok(accept,'Pending interpretation must show its review controls');
 await accept.click();
 assert.equal(requests.filter(r=>r.options).length,1);
 assert.ok(find(root,e=>e.textContent.startsWith('Researcher review: accepted')));
 assert.equal(find(root,e=>e.tagName==='BUTTON'&&e.textContent==='Accept proposed interpretation'),null);
 assert.equal(JSON.stringify(source.events[0].snapshot.decision),originalDecision);
 source.events[0].snapshot.graph_argumentation.mode='live';
 source.events[0].snapshot.decision.reasoning_source='graph';
 source.events[0].snapshot.decision.argument_ids=['argument1'];
 source.events[0].snapshot.decision.opposing_argument_ids=[];
 await elements.get('refresh').click();
 assert.ok(find(root,e=>e.textContent==='Graph argumentation · intervention source'));
 assert.ok(find(root,e=>e.tagName==='SUMMARY'&&e.textContent==='Selected proof and objection links'));
 source.synthetic_profile={description:'Scripted broad sampling.',version:'fixture'};
 await elements.get('refresh').click();
 assert.ok(find(root,e=>e.textContent==='Synthetic calibration fixture · Scripted broad sampling.'));
 delete source.synthetic_profile;source.uses_synthetic_calibration=true;
 await elements.get('refresh').click();
 assert.ok(find(root,e=>e.textContent.startsWith('This session uses synthetic calibration profiles.')));
 source.synthetic_run={version:'fixture-simulation'};await elements.get('refresh').click();
 assert.ok(find(root,e=>e.textContent.startsWith('Synthetic agent simulation')));
 console.log('Inspector: historical/live proofs, premise provenance, critical questions, decision links, quote review and immutable past decisions passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
