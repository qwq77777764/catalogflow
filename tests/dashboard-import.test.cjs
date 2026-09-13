const test=require('node:test');
const assert=require('node:assert/strict');
const {MAX_JSON_BYTES,safeLink,parseProductJSON,previewPayload,draftEdits,validateJob,shippingCost,productImages,
  diagnosticLabels,errorText,createModel}=require('../src/catalogflow/dashboard-import.js');
const {create,translations}=require('../src/catalogflow/dashboard-i18n.js');
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const product={source:'alibaba-manual',source_id:'synthetic-1',title:'Synthetic clock',currency:'USD',
  source_url:'https://example.com/1001',images:['https://example.com/1001.jpg'],
  variants:[{sku:'synthetic-red',cost:8,attributes:{Color:'Red'},shipping_quote:{quantity:2,total_cost_usd:10}}]};
const form={source:'alibaba-manual',source_input:product,generator:'deterministic',store_profile_id:null};
function job(id='job-1',status='ready') {return {id,status,phase:status==='running'?'fetching':'finished',revision:'revision-1',
  preview:status==='running'?null:{product,listing:{title:'Synthetic clock',description_html:'<p>A synthetic clock.</p>',
    category:'Clocks',tags:['Clock'],prices_by_sku:{'synthetic-red':30.95}},pricing:{scheme:'margin',target_margin:.45},
    store:{label:'Synthetic store',base_url:'https://example.com'}},error:null,report_run_id:'run-1'};}

test('JSON input is one bounded UTF-8 object, accepts BOM, and counts bytes instead of characters',()=>{
  assert.equal(parseProductJSON('\uFEFF'+JSON.stringify(product)).source_id,'synthetic-1');
  for(const value of ['[]','null','42','"text"','{broken',null])assert.throws(()=>parseProductJSON(value),/import_invalid_json/);
  assert.equal(MAX_JSON_BYTES,48*1024);
  assert.throws(()=>parseProductJSON(JSON.stringify({title:'字'.repeat(MAX_JSON_BYTES/3)})),/import_json_too_large/);
});

test('image and store links cannot run scripts, navigate local files, expose credentials, or target local IPs',()=>{
  assert.equal(safeLink('https://example.com/products/1001'),'https://example.com/products/1001');
  for(const value of ['javascript:alert(1)','data:text/html,hi','http://example.com/x','https://secret:password@example.com/',
    'file:///C:/private.txt','https://127.0.0.1/','https://0x7f000001/','https://[::1]/',
    'https://thing.local/','https://local.internal/','https://a.localhost/','https://example.com/\nsecret',null])
    assert.equal(safeLink(value),null,String(value));
});

test('preview request admits only selected IDs and product data, strips ignored profiles and arbitrary command/path fields',()=>{
  const payload=previewPayload({...form,command:'untrusted command',output:'C:/private',publish:true,
    source_profile_id:'not-used',ai_profile_id:'not-used'});
  assert.deepEqual(payload,{source:'alibaba-manual',source_input:product,source_profile_id:null,
    generator:'deterministic',ai_profile_id:null,store_profile_id:null});
  const cj=previewPayload({source:'cj',source_input:'  CJ-TEST-1  ',source_profile_id:'cj-profile',generator:'codex',ai_profile_id:'codex-profile'});
  assert.equal(cj.source_input,'CJ-TEST-1');assert.equal(cj.store_profile_id,null);
  assert.throws(()=>previewPayload({...form,store_profile_id:'../../secrets'}),/import_profile_invalid/);
  assert.throws(()=>previewPayload({...form,source:'cj',source_input:'CJ-1'}),/import_profile_required/);
  assert.throws(()=>previewPayload({...form,source:'unknown'}),/import_invalid_request/);
  assert.throws(()=>previewPayload({...form,generator:'shell'}),/import_invalid_request/);
});

test('unsaved pricing blocks preview before any request is sent',async()=>{
  const calls=[],model=createModel(async(...args)=>calls.push(args),{pricingIsDirty:()=>true});
  await model.start(form);assert.equal(model.error.message,'import_pricing_dirty');assert.deepEqual(calls,[]);
});

test('a locally invalid new preview attempt invalidates the previously reviewed product before validation',async()=>{
  const calls=[],model=createModel(async(url)=>{calls.push(url);return {job:job()};});
  model.accept(job());model.edit('title','Keep old text for comparison');model.reviewed=true;
  await model.start({...form,source_input:null});
  assert.equal(model.error.message,'import_invalid_source');assert.equal(model.reviewed,false);
  assert.equal(model.previewInvalidated,true);assert.equal(model.canDraft,false);assert.equal(model.job.id,'job-1');
  assert.equal(model.edits.title,'Keep old text for comparison');
  model.reviewed=true;await model.draft();assert.equal(calls.length,0);
  await model.recover();assert.equal(model.canDraft,false);assert.equal(model.previewInvalidated,true);
});

test('a synchronously rejected new preview cannot submit the old job; only a new successful preview unlocks review',async()=>{
  let rejected=true;const calls=[],model=createModel(async(url,options)=>{
    calls.push([url,options]);if(rejected)throw new Error('import_invalid_product');return {job:job('job-2')};
  });
  model.accept(job());model.reviewed=true;await model.start(form);
  assert.equal(model.error.message,'import_invalid_product');assert.equal(model.uncertain,false);
  assert.equal(model.previewInvalidated,true);assert.equal(model.reviewed,false);
  model.reviewed=true;await model.draft();assert.equal(calls.length,1);
  rejected=false;await model.start(form);assert.equal(model.job.id,'job-2');assert.equal(model.previewInvalidated,false);
  assert.equal(model.canDraft,false);model.reviewed=true;assert.equal(model.canDraft,true);
});

test('source or connection input changes invalidate the current preview even if the old checkbox is rechecked',async()=>{
  const calls=[],model=createModel(async(url)=>{calls.push(url);return {job:job()};});
  model.accept(job());model.reviewed=true;assert.equal(model.canDraft,true);
  model.inputChanged();assert.equal(model.reviewed,false);assert.equal(model.previewInvalidated,true);
  model.reviewed=true;await model.draft();assert.equal(calls.length,0);
  await model.poll();assert.equal(model.canDraft,false);assert.equal(model.previewInvalidated,true);
});

test('an uncertain new preview never revives the old reviewed job or automatically replays the request',async()=>{
  const calls=[],model=createModel(async(url,options)=>{
    calls.push([url,options]);if(options?.method==='POST')throw new TypeError('connection lost');return {job:job()};
  });
  model.accept(job());model.reviewed=true;await model.start(form);
  assert.equal(model.uncertain,true);assert.equal(model.previewInvalidated,true);assert.equal(model.reviewed,false);
  await model.start(form);model.reviewed=true;await model.draft();assert.equal(calls.length,1);
  await model.recover();assert.equal(model.uncertain,false);assert.equal(model.canDraft,false);
  assert.equal(calls.filter(([,options])=>options?.method==='POST').length,1);
});

test('input changes while recovering an uncertain preview cannot bind its eventual result to different inputs',async()=>{
  const model=createModel(async(url,options)=>{
    if(options?.method==='POST')throw new TypeError('connection lost');return {job:job('job-2')};
  });
  model.accept(job());await model.start(form);model.inputChanged();await model.recover();
  assert.equal(model.job.id,'job-2');assert.equal(model.previewInvalidated,true);
  model.reviewed=true;assert.equal(model.canDraft,false);
});

test('preview is a single mutation and cannot submit twice or draft before ready and review',async()=>{
  const pending=deferred(),calls=[],model=createModel((...args)=>{calls.push(args);return pending.promise;});
  const request=model.start(form);await model.start(form);await model.draft();
  assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/imports/preview');
  assert.equal(JSON.parse(calls[0][1].body).store_profile_id,null);
  pending.resolve({job:job('job-1','running')});await request;
  await model.start(form);model.reviewed=true;await model.draft();assert.equal(calls.length,1);
});

test('draft requires a selected store and review, sends only allowlisted edits with exact revision',async()=>{
  const calls=[],model=createModel(async(...args)=>{calls.push(args);return {job:{...job(),status:'drafting'}};});
  model.accept(job());await model.draft();assert.equal(calls.length,0);
  model.job.preview.store=null;model.reviewed=true;assert.equal(model.canDraft,false);await model.draft();
  model.job.preview.store={label:'Synthetic'};
  model.edit('title','Reviewed clock');model.edit('tags','Clock， Home\nDecor');
  assert.equal(model.reviewed,false);model.edit('prices',{anything:0});model.reviewed=true;
  await model.draft();await model.draft();assert.equal(calls.length,1);
  assert.equal(calls[0][0],'/api/imports/job-1/draft');
  assert.deepEqual(JSON.parse(calls[0][1].body),{revision:'revision-1',confirm_hidden_draft:true,
    edits:{title:'Reviewed clock',description_html:'<p>A synthetic clock.</p>',category:'Clocks',tags:['Clock','Home','Decor']}});
  assert.equal(model.canDraft,false);
});

test('a poll or same-session restore preserves edited text and review state without supplier HTML execution',async()=>{
  const fresh=job(),model=createModel(async()=>({job:{...fresh,revision:'updated-revision'}}));
  model.accept(job());const text='<img src=x onerror=alert(1)> Untrusted text';
  model.edit('description_html',text);model.reviewed=true;await model.poll();
  assert.equal(model.edits.description_html,text);assert.equal(model.reviewed,true);
  await model.recover();assert.equal(model.edits.description_html,text);assert.equal(model.hasEdits,true);
  model.accept(job('job-2'));assert.equal(model.edits.description_html,'<p>A synthetic clock.</p>');assert.equal(model.hasEdits,false);
});

test('disconnection retains the old preview and edits and never automatically resubmits a mutation',async()=>{
  let current=job(),calls=[];
  const model=createModel(async(url,options)=>{calls.push([url,options]);if(options?.method==='POST')throw new TypeError('network failure');return {job:current};});
  model.accept(job());model.edit('title','Keep this edit');model.reviewed=true;
  await model.draft();assert.equal(model.uncertain,true);assert.equal(model.edits.title,'Keep this edit');
  await model.draft();await model.start(form);assert.equal(calls.length,1);
  current={...job(),status:'drafting'};await model.recover();assert.equal(model.job.status,'drafting');
  assert.equal(model.uncertain,false);assert.equal(model.edits.title,'Keep this edit');
  assert.equal(calls.filter(([,options])=>options?.method==='POST').length,1);
});

test('a stale poll cannot replace a newly submitted preview',async()=>{
  const pending=deferred(),model=createModel(async(url)=>url==='/api/imports/job-1'?pending.promise:{job:job('job-2','running')});
  model.accept(job());const poll=model.poll();await model.start(form);
  pending.resolve({job:job()});await poll;assert.equal(model.job.id,'job-2');assert.equal(model.job.status,'running');
});

test('invalid server data and mismatched job IDs fail closed while preserving existing edits',async()=>{
  const model=createModel(async()=>({job:job('wrong-job')}));model.accept(job());model.edit('title','Preserve me');
  await model.poll();assert.equal(model.error.message,'import_invalid_response');assert.equal(model.job.id,'job-1');
  assert.equal(model.edits.title,'Preserve me');
  for(const value of [null,{...job(),id:'../job'},{...job(),status:'published'},{...job(),revision:undefined},
    {...job(),preview:{product:[],listing:{}}}])assert.throws(()=>validateJob(value),/import_invalid_response/);
});

test('draft edit limits are enforced and unrelated immutable pricing cannot be supplied',()=>{
  const edits={title:'Clock',description_html:'<p>Text</p>',category:'Clocks',tags:'Home'};
  assert.deepEqual(Object.keys(draftEdits({...edits,prices:{sku:1},status:'publish'})),['title','description_html','category','tags']);
  for(const override of [{title:'a'.repeat(81)},{description_html:'a'.repeat(16001)},{category:'a'.repeat(121)},
    {tags:Array.from({length:21},(_,i)=>'tag'+i).join(',')},{tags:'a'.repeat(81)}])
    assert.throws(()=>draftEdits({...edits,...override}),/import_invalid_edits/);
});

test('shipping cost is quoted per unit and unavailable estimates are never invented',()=>{
  assert.equal(shippingCost(product.variants[0]),5);assert.equal(shippingCost({shipping_cost:2}),2);
  assert.equal(shippingCost({shipping_quote:{total_cost_usd:10,quantity:0}}),null);
  assert.equal(shippingCost({}),null);
});

test('image review includes unique variant images as well as gallery images',()=>{
  assert.deepEqual(productImages({images:['https://example.com/1.jpg','https://example.com/1.jpg'],
    variants:[{image_url:'https://example.com/2.jpg'},{image_url:'https://example.com/1.jpg'},{image_url:''},null]}),
  ['https://example.com/1.jpg','https://example.com/2.jpg']);
});

test('all stable diagnostics have English copy and unknown raw errors are redacted',()=>{
  const i18n=create({languages:['en-US']});
  for(const [code,label] of Object.entries(diagnosticLabels)) {
    assert.ok(Object.hasOwn(translations,label),code);assert.doesNotMatch(errorText(new Error(code),i18n),/[\u4e00-\u9fff]/);
  }
  const secret='secret remote response payload';assert.ok(!errorText(new Error(secret),i18n).includes(secret));
  assert.match(errorText(new Error('invalid_session'),i18n),/CatalogFlow launch window, click Open interface/);
  i18n.setLocale('zh-CN');assert.match(errorText(new Error('import_store_required'),i18n),/仅预览无需店铺连接/);
});
