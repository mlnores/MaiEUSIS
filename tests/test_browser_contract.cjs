// Executes the actual browser scripts with a minimal DOM and accelerated clocks.
// Actual Python validation/persistence runs behind a file-backed bridge.
// This checks task completion and API contracts; it is NOT visual/browser QA.
const vm=require('node:vm'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),dataDir=fs.mkdtempSync(path.join(os.tmpdir(),'socratic-ui-'));
// Avoid requiring tests to be an installed package.
function bridge(url,body){const r=spawnSync(process.env.PYTHON||'python3',[path.join(root,'tests/ui_bridge.py'),dataDir],{cwd:root,env:{...process.env,PYTHONPATH:root},input:JSON.stringify({path:url,body}),encoding:'utf8',maxBuffer:30*1024*1024});
 if(r.status!==0)throw Error(r.stderr);const output=JSON.parse(r.stdout);if(!output.ok)throw Error(output.error);return output.data;}
const fixture=bridge('/fixture');
function runtime(task){
 let now=0,timerID=0,scheduled=[],pumping=false,context,complete=false;
 const errors=[],requests=[];
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
 const elements=new Map();const html=fs.readFileSync(path.join(root,'socratic_prototype/static/index.html'),'utf8');
 for(const m of html.matchAll(/id="([^"]+)"/g))elements.set(m[1],new Element(m[1]));
 for(const [id,value] of Object.entries({participantId:'synthetic_ui',sessionPhase:'calibration',protocol:'short',condition:'A',promptFrequency:'standard',taskSeed:'browser-contract-test'}))elements.get(id).value=value;
 const responseButtons=elements.get('responseButtons');for(const feedback of ['helpful','disagree','fewer','dismiss']){const button=new Element('', 'BUTTON');button.dataset.feedback=feedback;responseButtons.append(button);}
 const listeners=new Map();const document={getElementById:id=>elements.get(id),createElement:tag=>new Element('',tag.toUpperCase()),body:new Element(),
  addEventListener:(type,fn)=>{if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn);
    if(type==='keydown'&&listeners.get(type).size===2)schedule(()=>document.dispatchEvent({type:'keydown',key:task==='MAB'?'8':'1',target:{tagName:'BODY'},preventDefault(){}}),30);},
  removeEventListener:(type,fn)=>listeners.get(type)?.delete(fn),dispatchEvent:event=>{for(const fn of [...(listeners.get(event.type)||[])])fn(event);}};
 const sandbox={document,performance:{now:()=>now},setTimeout:schedule,clearTimeout:cancel,requestAnimationFrame:fn=>schedule(fn,16),cancelAnimationFrame:cancel,
  Date,Math,JSON,Promise,console:{log:console.log,error:e=>errors.push(e)},Blob,URL,KeyboardEvent:class{constructor(type,options){this.type=type;Object.assign(this,options);this.target={tagName:'BODY'};}preventDefault(){}},alert:e=>errors.push(e),confirm:()=>true,
  fetch:async(url,options)=>{const body=options?JSON.parse(options.body):undefined;requests.push({url,body});try{return{ok:true,json:async()=>bridge(url,body)};}catch(e){return{ok:false,json:async()=>({error:e.message})};}}};
 context=vm.createContext(sandbox);vm.runInContext(html.split('<script>')[1].split('</script>')[0],context);
 vm.runInContext(fs.readFileSync(path.join(root,'socratic_prototype/static/teammate.js'),'utf8'),context);
 return {context,elements,requests,errors,now:()=>now};
}
(async()=>{
 try{
  for(const task of ['MAB','TBS']){
   const r=runtime(task);await new Promise(resolve=>setImmediate(resolve));
   r.elements.get('sessionPhase').value='assisted';r.elements.get('condition').value='F';
   r.elements.get('mabCalibration').value=fixture.MAB;r.elements.get('tbsCalibration').value=fixture.TBS;
   await vm.runInContext(`start('${task}')`,r.context);
   const deadline=Date.now()+120000;
   while(vm.runInContext('alive',r.context)&&Date.now()<deadline)await new Promise(resolve=>setImmediate(resolve));
   assert.equal(vm.runInContext('session.completed',r.context),true,task+' did not complete: '+r.errors.join(' '));
   assert.deepEqual(r.errors,[]);
   const count=vm.runInContext('session.trials.length',r.context);assert.equal(count,task==='MAB'?40:24);
   const evaluations=r.requests.filter(x=>x.body?.kind==='evaluation');assert.equal(evaluations.length,count);
   for(const request of evaluations){assert.equal('volatility_checks' in request.body,false);assert.equal('stage' in request.body,false);assert.equal('random_draw' in request.body,false);for(const o of request.body.options)assert.equal('probabilities' in o,false);}
   const sid=vm.runInContext('session.id',r.context), exported=bridge('/api/sessions/'+sid+'/export');
   assert.equal(exported.completed,true);assert.equal(bridge('/api/sessions/'+sid+'/replay').matches,true);
   const deliveries=exported.events.filter(e=>e.input.kind==='delivery');assert.equal(deliveries.length,count);
   assert.ok(deliveries.some(e=>e.input.delivered));
   // The four-second preparation and original five-second choice limit remain configured.
   assert.equal(exported.policy.preparation_ms,4000);
   const prepEvents=vm.runInContext("session.events.filter(e=>e.event==='PREPARATION_END')",r.context);
   assert.equal(prepEvents.length,count);assert.ok(prepEvents.every(e=>e.duration_ms===4000));
   assert.ok(prepEvents.every(e=>e.reading_exposure_ms<=4000));assert.equal(vm.runInContext(`configs.${task}.response_timeout_ms`,r.context),5000);
   console.log(task+': actual browser task script completed '+count+' trials; Python event validation, persistence, exposure and replay passed.');
  }
 }finally{fs.rmSync(dataDir,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
