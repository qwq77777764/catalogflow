const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {createModel,officialLink,collectorEndpoint,parseQueue,selectionCounts,aiPayload,statusLabels,diagnostics}=require('../src/catalogflow/dashboard-setup.js');
const {manualProductPayload,manualFormForItem}=require('../src/catalogflow/dashboard-import.js');
const {create,translations}=require('../src/catalogflow/dashboard-i18n.js');
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return{promise,resolve,reject};};
const ai=(override={})=>({job_id:'ai-job-1',provider:'codex',profile_id:null,phase:'complete',busy:false,status:'signed_in',code:'ai_signed_in',usage_verified:false,guidance:{},...override});
const item=(override={})=>({id:'item-1',queue_id:'queue-1',source:'cj',title:'Synthetic clock',url:'https://example.com/100001',frozen:false,importable:true,...override});
const queue=(override={})=>({active:null,queues:[],items:[],warnings:[],...override});

test('setup initial reads cannot log in, test AI, collect, or import automatically',async()=>{
  const calls=[],model=createModel(async(url,options)=>{calls.push([url,options]);return url==='/api/ai-setup'?ai():queue();});
  await model.readAI();await model.readQueue();assert.deepEqual(calls.map(([url])=>url),['/api/ai-setup','/api/selection-workflow']);
  assert.ok(calls.every(([,options])=>options===undefined));assert.equal(model.ai.usage_verified,false);
});

test('template requires no accounts and never calls the AI setup service',async()=>{
  const calls=[],model=createModel(async(...args)=>calls.push(args));model.choose('deterministic');
  await model.readAI();await model.runAI('check');await model.runAI('login');model.usageConfirmed=true;await model.runAI('test');
  assert.equal(calls.length,0);
});

test('each small AI test requires fresh explicit usage confirmation and sends a strict payload',async()=>{
  const calls=[],model=createModel(async(...args)=>{calls.push(args);return ai({status:'test_passed',code:'ai_test_passed',usage_verified:true});});
  await model.runAI('test');assert.equal(calls.length,0);assert.equal(model.aiError.message,'ai_setup_confirmation_required');
  model.usageConfirmed=true;await model.runAI('test');assert.equal(calls[0][0],'/api/ai-setup/test');
  assert.deepEqual(JSON.parse(calls[0][1].body),{provider:'codex',profile_id:null,confirm_usage:true});
  assert.equal(model.usageConfirmed,false);await model.runAI('test');assert.equal(calls.length,1);
  assert.throws(()=>aiPayload('shell','../private'),/ai_setup_invalid_request/);
});

test('login opens only on an explicit action and login detection never upgrades to quota verification',async()=>{
  const calls=[],model=createModel(async(...args)=>{calls.push(args);return ai({status:'login_opened',code:'ai_login_opened'});});
  await model.runAI('login');assert.equal(calls[0][0],'/api/ai-setup/login');
  assert.deepEqual(JSON.parse(calls[0][1].body),{provider:'codex',profile_id:null});
  assert.equal(model.ai.status,'login_opened');assert.equal(model.ai.usage_verified,false);
  assert.match(statusLabels.signed_in,/尚未验证/);
});

test('changing AI selection discards stale asynchronous results and clears confirmation',async()=>{
  const pending=deferred(),model=createModel(()=>pending.promise);const running=model.runAI('check');
  model.choose('claude');pending.resolve(ai());await running;
  assert.equal(model.provider,'claude');assert.equal(model.ai,null);assert.equal(model.aiBusy,false);assert.equal(model.usageConfirmed,false);
});

test('saved profile edits invalidate old readiness even if a refresh returns the same completed job',async()=>{
  let response=ai({status:'test_passed',code:'ai_test_passed',usage_verified:true});const model=createModel(async()=>response);
  await model.readAI();assert.equal(model.ai.status,'test_passed');model.invalidateAI();await model.readAI();assert.equal(model.ai,null);
  response=ai({job_id:'ai-job-2'});await model.runAI('check');assert.equal(model.ai.job_id,'ai-job-2');
});

test('unconfirmed collection items cannot be selected; selection only fills a callback after server confirmation',async()=>{
  const calls=[],selected=[],model=createModel(async(...args)=>{calls.push(args);return{item:item({frozen:true})};});
  model.queue=queue({items:[item()]});await model.select('item-1',value=>selected.push(value));assert.equal(calls.length,0);
  model.queue.items[0].frozen=true;await model.select('item-1',value=>selected.push(value));
  assert.equal(calls[0][0],'/api/selection-workflow/select');assert.deepEqual(JSON.parse(calls[0][1].body),{id:'item-1'});
  assert.equal(selected.length,1);assert.ok(calls.every(([url])=>!url.includes('/imports/') && !url.includes('/ai-setup/')));
});

test('a lost start response is not replayed and a later state read can recover the collector',async()=>{
  const calls=[],active={queue_id:'queue-1',endpoint:'http://127.0.0.1:54321',pairing_code:'CATALOGFLOW1:c3ludGhldGlj'};
  const model=createModel(async(url,options)=>{calls.push([url,options]);if(options)throw new TypeError('network');return queue({active});});
  await model.changeQueue('start');assert.equal(model.queueUncertain,true);await model.changeQueue('start');assert.equal(calls.length,1);
  await model.readQueue();assert.equal(model.queue.active.queue_id,'queue-1');assert.equal(model.queueUncertain,false);
});

test('a stale queue read cannot replace a newer explicit freeze',async()=>{
  const pending=deferred(),model=createModel(async(url)=>url==='/api/selection-workflow'?pending.promise:queue({items:[item({frozen:true})]}));
  const reading=model.readQueue();await model.changeQueue('freeze',{queue_id:'queue-1'});pending.resolve(queue({items:[item()]}));await reading;
  assert.equal(model.queue.items[0].frozen,true);
});

test('current collection counts exclude archived products, including a new empty queue',()=>{
  const old=[item({id:'old-1',queue_id:'old-queue',frozen:true}),item({id:'old-2',queue_id:'old-queue',frozen:true})];
  const snapshot=queue({active:{queue_id:'new-queue'},items:old});
  assert.deepEqual(selectionCounts(snapshot),{current:0,archived:2,total:2});
  snapshot.items=[...old,item({id:'new-1',queue_id:'new-queue'})];
  assert.deepEqual(selectionCounts(snapshot),{current:1,archived:2,total:3});
  snapshot.active=null;assert.deepEqual(selectionCounts(snapshot),{current:0,archived:3,total:3});
  assert.deepEqual(selectionCounts(null),{current:0,archived:0,total:0});
});

test('collector URLs remain exact loopback endpoints and guidance links stay on official HTTPS domains',()=>{
  assert.equal(collectorEndpoint('http://127.0.0.1:54321'),'http://127.0.0.1:54321');
  for(const value of ['https://example.com/','http://localhost:54321','http://127.0.0.1:80','http://127.0.0.1:54321/secret',
    'http://user:password@127.0.0.1:54321','javascript:alert(1)'])assert.equal(collectorEndpoint(value),null);
  assert.ok(officialLink('https://code.claude.com/docs/en/setup'));
  for(const value of ['https://example.com/install','http://developers.openai.com/','https://user:password@code.claude.com/','javascript:alert(1)'])assert.equal(officialLink(value),null);
});

test('legacy queue files accept BOM but reject oversized or non-object JSON',()=>{
  assert.deepEqual(parseQueue('\uFEFF{"items":[]}'),{items:[]});
  for(const value of ['[]','null','broken'])assert.throws(()=>parseQueue(value),/setup_invalid_queue/);
  assert.throws(()=>parseQueue('{"text":"'+'字'.repeat(20000)+'"}'),/setup_queue_too_large/);
});

const manual={source_id:'synthetic-manual-1',source_url:'https://example.com/product/100001',title:'Synthetic clock',
  facts:'Material: Wood\nDimensions: 30 cm',images:'https://example.com/1001.jpg',origin_country:'cn',destination_country:'us',
  variants:[{name:'Red',cost:'8.5',shipping_cost:'4.25',image_url:'https://example.com/1002.jpg'}]};

test('novice product fields become the existing normalized schema with explicit USD unit costs and freight',()=>{
  const value=manualProductPayload(manual);assert.equal(value.source,'alibaba-manual');assert.equal(value.currency,'USD');
  assert.deepEqual(value.facts,{Material:'Wood',Dimensions:'30 cm'});assert.equal(value.variants[0].cost,8.5);
  assert.deepEqual(value.variants[0].shipping_quote,{origin_country:'CN',destination_country:'US',quantity:1,method:'Manual quote',total_cost_usd:4.25,estimated_days:''});
  assert.deepEqual(value.variants[0].attributes,{Option:'Red'});assert.equal(value.variants[0].sku,'manual-1');
});

test('manual form rejects missing/negative amounts, duplicate variants, unsafe images, and invalid facts',()=>{
  for(const change of [{variants:[{...manual.variants[0],cost:''}]},{variants:[{...manual.variants[0],shipping_cost:-1}]},
    {variants:[manual.variants[0],manual.variants[0]]},{images:'http://127.0.0.1/x'},
    {facts:'Material:Wood\nMaterial:Metal'},{facts:'Unstructured text'},{source_id:''},{destination_country:'USA'}])
    assert.throws(()=>manualProductPayload({...manual,...change}),/import_invalid_product/);
  const value=manualProductPayload({...manual,facts:'__proto__: harmless text'});
  assert.equal(Object.getPrototypeOf(value.facts),Object.prototype);assert.equal(Object.hasOwn(value.facts,'__proto__'),true);
});

test('selecting a different Alibaba item discards all previous product facts, variants, images and monetary values',()=>{
  const previous=manualFormForItem(item({source:'alibaba',id:'item-a',title:'Product A'}));
  previous.facts='Material: Wood';previous.images='https://example.com/product-a.jpg';previous.variants=[{name:'Red',cost:'40',shipping_cost:'8',image_url:'https://example.com/red.jpg'}];
  previous.origin_country='DE';previous.destination_country='HK';
  const next=manualFormForItem(item({source:'alibaba',id:'item-b',title:'Product B',url:'https://example.com/product/200002'}));
  assert.equal(next.title,'Product B');assert.equal(next.source_id,'200002');assert.equal(next.facts,'');assert.equal(next.images,'');
  assert.deepEqual(next.variants,[{name:'',sku:'',cost:'',shipping_cost:'',image_url:''}]);
  assert.equal(next.origin_country,'CN');assert.equal(next.destination_country,'US');
  assert.throws(()=>manualProductPayload(next),/import_invalid_product/);
  assert.equal(previous.variants[0].cost,'40');
});

test('setup and manual form copy is bilingual and quota claims remain bounded to the actual test',()=>{
  const ui=create({languages:['en-US']});
  for(const source of [...Object.values(statusLabels),...Object.values(diagnostics)])assert.ok(Object.hasOwn(translations,source),source);
  for(const filename of ['dashboard-setup.js','dashboard-import.js']){
    const source=fs.readFileSync(new URL('../src/catalogflow/'+filename,'file://'+__filename),'utf8');
    for(const match of source.matchAll(/'([^'\n]*[\u4e00-\u9fff][^'\n]*)'/g))assert.ok(Object.hasOwn(translations,match[1]),match[1]);
  }
  assert.match(ui.t(statusLabels.signed_in),/not been verified/);
  assert.match(ui.t(diagnostics.ai_test_passed),/does not guarantee/);
});
