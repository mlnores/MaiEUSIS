// Runs the standalone demo's actual inline script. No packages or browser needed.
// Accelerated timers verify mechanics/logging; this is not rendered-browser QA.
// Optional differential run: node tests/test_demo_visuals.cjs --baseline /path/to/original.html
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const demo=path.join(__dirname,'../mab_tbs_web_demo/index.html');
const source=fs.readFileSync(demo,'utf8');
const baselineArg=process.argv.indexOf('--baseline');
const baseline=baselineArg<0?null:fs.readFileSync(process.argv[baselineArg+1],'utf8');
const plain=value=>JSON.parse(JSON.stringify(value));

function runtime(html=source,plan=()=>null){
 let now=0,timerId=0,queue=[],pumping=false,context;
 const errors=[],renders=[],elements=new Map(),listeners=new Map();
 function schedule(fn,delay=0){const id=++timerId;queue.push({id,at:now+delay,fn});pump();return id;}
 function cancel(id){queue=queue.filter(timer=>timer.id!==id);}
 function pump(){if(pumping)return;pumping=true;setImmediate(()=>{pumping=false;queue.sort((a,b)=>a.at-b.at||a.id-b.id);const next=queue.shift();if(next){now=next.at;try{next.fn();}catch(e){errors.push(e);}if(queue.length)pump();}});}
 class Element{
  constructor(id){this.id=id;this.textContent='';this.onclick=null;this.html='';this.children=[];const classes=new Set();this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,on)=>on?classes.add(x):classes.delete(x)};}
  set innerHTML(value){this.html=value;this.children=[];let arm=null;
   for(const match of value.matchAll(/<(button|div)\b([^>]*)>/g)){
    const attrs=Object.fromEntries([...match[2].matchAll(/([\w-]+)="([^"]*)"/g)].map(m=>[m[1],m[2]]));
    if(match[1]==='div'&&attrs.class!=='arm')continue;
    const e=new Element(attrs.id||'');e.attrs=attrs;e.tag=match[1];const parent=attrs.class==='arm-choice'?arm:null;
    e.click=()=>attrs.onclick?vm.runInContext(attrs.onclick,context):parent?.click();
    if(attrs.class==='arm')arm=e;
    this.children.push(e);if(e.id)elements.set(e.id,e);
   }
   if(this.id==='taskarea')renders.push({html:value,trials:context?vm.runInContext('session?.trials.length??0',context):0});
   if(value.includes('id="continueBlock"'))schedule(()=>elements.get('continueBlock').onclick(),1);
   if(value.includes('id="resumeMid"'))schedule(()=>elements.get('resumeMid').onclick(),1);
  }
  get innerHTML(){return this.html;}
  querySelectorAll(selector){return selector==='.ball-viewport'?[...this.html.matchAll(/class="ball-viewport"/g)].map(()=>({scrollTop:0,scrollHeight:0})):[];}
 }
 for(const match of html.matchAll(/id="([^"]+)"/g))elements.set(match[1],new Element(match[1]));
 const document={getElementById:id=>elements.get(id),
  addEventListener(type,fn){if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn);
   if(type==='keydown'){
    const trial=plain(vm.runInContext('activeTrial',context));const action=plan(trial);
    if(action)schedule(()=>{
     if(action.click){const targets=elements.get('taskarea').children.filter(e=>e.attrs['data-key']===action.key||e.attrs.onclick===`clickChoice('${action.key}')`);
      const target=trial.global_trial%4===0?targets.at(-1):targets[0];assert.ok(target,'Missing clickable shortcut '+action.key);target.click();}
     else document.dispatchEvent({type:'keydown',key:action.key,preventDefault(){}});
    },30);
   }
  },removeEventListener:(type,fn)=>listeners.get(type)?.delete(fn),
  dispatchEvent(event){for(const fn of [...(listeners.get(event.type)||[])])fn(event);}};
 const NativeDate=Date;
 class FixedDate extends NativeDate{constructor(...args){super(...(args.length?args:[1767225600000+now]));}static now(){return 1767225600000+now;}}
 const math=Object.create(Math);math.random=()=>.123456789;
 context=vm.createContext({document,performance:{now:()=>now},setTimeout:schedule,clearTimeout:cancel,
  requestAnimationFrame:fn=>schedule(fn,16),cancelAnimationFrame:cancel,Date:FixedDate,Math:math,
  console:{error:e=>errors.push(e)},confirm:()=>true,alert:e=>errors.push(e),
  KeyboardEvent:class{constructor(type,attrs){this.type=type;Object.assign(this,attrs);}preventDefault(){}}});
 vm.runInContext(html.split('<script>')[1].split('</script>')[0],context);
 return {context,elements,errors,renders,eval:code=>vm.runInContext(code,context),
  async complete(task,full=false){
   if(full)this.eval(task==='MAB'?'configs.MAB.stable_trials=50;configs.MAB.volatile_trials=150':'configs.TBS.blocks=24');
   this.eval(`start('${task}')`);
   const deadline=NativeDate.now()+10000;
   while(this.eval('alive')&&NativeDate.now()<deadline)await new Promise(resolve=>setImmediate(resolve));
   assert.deepEqual(errors,[]);assert.equal(this.eval('session.completed'),true,'Demo did not finish');
   return plain(this.eval('({...session,rng:undefined})'));
  }};
}

function optionFixtures(r){return plain(r.eval('baseArms.map(([id,color,key,shade,probabilities,outcomes])=>({id,color,key,shade,probabilities,outcomes}))'));}
function armPanels(html){return [...html.matchAll(/<div class="arm" data-option="([^"]+)"[^>]*>([\s\S]*?)(?=<div class="arm"|<\/section>)/g)].map(m=>({id:m[1],html:m[0]}));}
function balls(html){return [...html.matchAll(/class="outcome-ball"/g)].length;}
function groupIds(html){return [...html.matchAll(/<section class="arm-group"[^>]*>([\s\S]*?)<\/section>/g)].map(m=>armPanels(m[1]+'</section>').map(a=>a.id));}
function rectangleValues(html){return [...html.matchAll(/class="probframe" style="height:([\d.e+-]+)px" data-points="([\d.e+-]+)" data-pixels-per-point="([\d.e+-]+)"><div class="probfill" style="height:([\d.e+-]+)%"/g)].map(m=>m.slice(1).map(Number));}
function approx(actual,expected){assert.ok(Math.abs(actual-expected)<1e-10,`${actual} != ${expected}`);}

function checkPresentation(){
 const r=runtime(),options=optionFixtures(r);r.context.options=options;r.eval("newSession('MAB')");
 let html=r.eval('mabOptionsMarkup(options)');
 assert.deepEqual(groupIds(html),[['blue2','blue3','blue1'],['red1','red2','red3']]);
 assert.deepEqual(Object.fromEntries(options.map(arm=>[arm.id,arm.key])),{blue1:'3',blue2:'1',blue3:'2',red1:'7',red2:'8',red3:'9'});
 assert.equal([...html.matchAll(/<div class="arm"[^>]*onclick="clickChoice\('[123789]'\)"/g)].length,6,'Every entire panel must handle clicks');
 assert.equal([...html.matchAll(/<button class="arm-choice"[^>]*onclick=/g)].length,0,'Header click bubbles to its panel exactly once');
 for(const arm of options){const panel=armPanels(html).find(p=>p.id===arm.id);assert.ok(panel.html.includes(`data-key="${arm.key}"`));assert.ok(panel.html.includes(`clickChoice('${arm.key}')`));}
 assert.equal(balls(html),0);assert.equal([...html.matchAll(/class="ball-viewport"/g)].length,18);
 assert.ok(html.includes('One ball = one observed outcome.'));assert.ok(!html.includes('<img'));
 // Group by actual magnitudes, including identities whose colors no longer match.
 const swapped=plain(options);[swapped[0].outcomes,swapped[3].outcomes]=[swapped[3].outcomes,swapped[0].outcomes];r.context.swapped=swapped;
 const groups=groupIds(r.eval('mabOptionsMarkup(swapped)'));
 assert.ok(groups[0].includes('red1')&&!groups[0].includes('blue1'));
 assert.ok(groups[1].includes('blue1')&&!groups[1].includes('red1'));
 const trials=[100,0,-100].map(outcome=>({task:'MAB',selected_option:'blue1',outcome}));
 trials.push({task:'MAB',selected_option:'NO_RESPONSE',outcome:-200});r.context.trials=trials;
 html=r.eval('mabOptionsMarkup(options,trials)');assert.equal(balls(html),3);
 for(const panel of armPanels(html))assert.equal(balls(panel.html),panel.id==='blue1'?3:0);
 const blue=armPanels(html).find(p=>p.id==='blue1').html;
 for(const label of ['positive','zero','negative']){
  const bin=blue.match(new RegExp(`outcome-container outcome-${label}([\\s\\S]*?)(?=<div class="outcome-container|$)`))[1];
  assert.equal(balls(bin),1);
 }
 assert.equal(r.eval('mabOptionsMarkup(options,trials)'),html,'Rendering must not mutate history');
 // Entire full protocol can accumulate in one bin; every ball has its own cell.
 r.context.trials=Array.from({length:200},()=>({task:'MAB',selected_option:'blue1',outcome:100}));
 html=r.eval('mabOptionsMarkup(options,trials)');assert.equal(balls(html),200);
 const cells=[...html.matchAll(/grid-row:(\d+);grid-column:(\d+)/g)].map(m=>m[1]+','+m[2]);
 assert.equal(new Set(cells).size,200);assert.ok(cells.includes('50,1'));assert.ok(cells.includes('1,4'));
 r.eval('session.trials=trials');assert.equal(balls(r.eval('mabOptionsMarkup(options)')),200);
 r.eval("newSession('MAB')");assert.equal(balls(r.eval('mabOptionsMarkup(options)')),0);
 const pairs=plain(r.eval('configs.TBS.options'));
 for(const pair of [...pairs,[{amount:145,prob:0},{amount:245,prob:100}]]){
  r.context.tbsOptions=pair.map((o,i)=>({option_id:i?'risky':'safe',key:i?'9':'1',amount:o.amount,probability:o.prob/100}));
  const markup=r.eval('tbsOptionsMarkup(tbsOptions)'),rects=rectangleValues(markup);assert.equal(rects.length,2);
  approx(rects[0][0]/rects[1][0],pair[0].amount/pair[1].amount);
  for(let i=0;i<2;i++){approx(rects[i][2],160/350);approx(rects[i][0],pair[i].amount*160/350);approx(rects[i][3],pair[i].prob);}
  assert.ok(markup.includes('Rectangle size = possible points · Filled fraction = win probability.'));
 }
 const css=source.split('<style>')[1].split('</style>')[0];
 assert.match(css,/grid-template-columns:repeat\(4,10px\)/);assert.match(css,/overflow-y:auto/);
 assert.match(css,/\.ball-viewport\{[^}]*border-top:0/);
 assert.match(css,/\.reward-stage\{height:160px;display:flex;align-items:flex-end/);
 assert.match(css,/\.probframe\{[^}]*border:0/);assert.match(css,/\.probfill\{position:absolute;bottom:0/);
 assert.ok(!source.includes('slot.png')&&!source.includes('armhistory'));
 console.log('Presentation: reward grouping/shortcuts, exact per-outcome balls, reset, 200-ball packing and all TBS ratios/fills (including 0%/100%) passed.');
}

const inputPlan=t=>t.global_trial%7===0?null:{key:t.task==='MAB'?['1','2','3','7','8','9'][(t.global_trial-1)%6]:(t.global_trial%2?'1':'9'),click:t.global_trial%2===0};
async function checkRun(task,full){
 const r=runtime(source,inputPlan),s=await r.complete(task,full),count=task==='MAB'?(full?200:40):(full?192:24);
 assert.equal(s.trials.length,count);assert.equal(s.options.length,count*(task==='MAB'?6:2));
 assert.equal(s.events.filter(e=>e.event==='EVALUATION_ONSET').length,count);
 const timeouts=s.trials.filter(t=>(t.selected_option||t.chosen_option)==='NO_RESPONSE');assert.equal(timeouts.length,Math.floor(count/7));
 for(const t of s.trials){
  if(task==='MAB')assert.equal(t.score_after,t.score_before+t.outcome);
  else {assert.equal(t.points_after,t.points_before+t.earned_points);if(t.trial===8)approx(t.final_block_score,t.points_after*(t.is_win?t.multiplier:1));}
 }
 if(task==='MAB'){
  assert.equal(s.trials.filter(t=>t.stage==='stable').length,full?50:10);
  assert.equal(s.events.filter(e=>e.event==='STAGE_START').length,2);
  assert.equal(s.events.filter(e=>e.event==='VOLATILITY_CHECK').length,(full?150:30)*2);
  const screens=r.renders.filter(render=>render.html.includes('class="mab-display"'));assert.equal(screens.length,count);
  for(let i=0;i<count;i++){
   const prior=s.trials.slice(0,i).filter(t=>t.selected_option!=='NO_RESPONSE');assert.equal(balls(screens[i].html),prior.length);
   for(const panel of armPanels(screens[i].html))assert.equal(balls(panel.html),prior.filter(t=>t.selected_option===panel.id).length);
  }
  r.context.options=optionFixtures(r);assert.equal(balls(r.eval('mabOptionsMarkup(options)')),count-timeouts.length);
 }else{
  assert.equal(s.blocks.length,full?24:3);
  for(const screen of r.renders.filter(render=>render.html.includes('class="choose"'))){const rects=rectangleValues(screen.html);assert.equal(rects.length,2);approx(rects[0][0]/rects[1][0],rects[0][1]/rects[1][1]);}
 }
 if(baseline){const old=await runtime(baseline,inputPlan).complete(task,full);assert.deepEqual(s,old,'Mechanics, RNG, scoring, timing or logs changed');}
 console.log(`${task} ${full?'full':'short'}: ${count} trials, mouse/keyboard choices, timeouts, transitions, scores and logs passed${baseline?'; identical to pre-change run':''}.`);
}
(async()=>{checkPresentation();for(const task of ['MAB','TBS'])for(const full of [false,true])await checkRun(task,full);})().catch(e=>{console.error(e);process.exitCode=1;});
