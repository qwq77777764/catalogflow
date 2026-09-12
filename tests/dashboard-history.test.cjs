const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {safeLink,formatTimestamp,summaryCounts,createModel,statusLabels,diagnosticText} = require('../src/catalogflow/dashboard-history.js');
const {translations,create} = require('../src/catalogflow/dashboard-i18n.js');
const deferred = () => { let resolve,reject; const promise=new Promise((yes,no)=>{resolve=yes;reject=no;}); return {promise,resolve,reject}; };
const report = run_id => ({run_id,mode:'dry-run',status:'completed',items:[],counts:{previewed:1},started_at:'2026-09-12T01:02:03+00:00',finished_at:'2026-09-12T01:02:04+00:00'});

test('report links allow web navigation and reject executable, credential-bearing, and malformed URLs', () => {
  assert.equal(safeLink('https://example.com/item/42?a=1'),'https://example.com/item/42?a=1');
  for (const value of ['javascript:alert(1)','data:text/html,<h1>test</h1>','file:///C:/private.txt',
    'https://user:password@example.com/','https://example.com/\nsecret','//example.com/x','/relative','',null])
    assert.equal(safeLink(value),null,String(value));
});

test('report timestamps require an explicit zone and are rendered consistently in UTC in both languages', () => {
  for (const locale of ['zh-CN','en-US']) {
    const value=formatTimestamp('2026-09-12T09:02:03+08:00',locale);
    assert.match(value,/UTC/);
    assert.match(value,/01:02:03/);
    for (const invalid of ['2026-09-12T01:02:03','unknown',null,'']) assert.equal(formatTimestamp(invalid,locale),'—');
  }
});

test('preview and store-draft counts remain distinct; corrupt or unknown totals are not invented', () => {
  assert.deepEqual(summaryCounts({counts:{previewed:4,drafted:2,failed:1,rejected:-1,interrupted:'3',unknown:500}}),[
    {status:'previewed',count:4},{status:'drafted',count:2},{status:'failed',count:1}
  ]);
  assert.deepEqual(summaryCounts(null),[]);
  const ui=create({languages:['en-US']});
  assert.match(ui.t(statusLabels.previewed),/Preview/);
  assert.match(ui.t(statusLabels.drafted),/Hidden draft/);
});

test('uncertain writes tell the user to reconcile the store and stable diagnostics are bilingual', () => {
  const ui=create({languages:['en-US']});
  assert.match(ui.t(statusLabels.blocked_incomplete),/Previous write unconfirmed/);
  assert.equal(ui.t(statusLabels.interrupted),'Unfinished; result unconfirmed');
  assert.match(diagnosticText('review_required',ui),/Check the store/);
  assert.match(diagnosticText('WooCommerceDraftError',ui),/product ID/);
  assert.match(diagnosticText('wordpress_media_credentials_required',ui),/application password/);
  assert.match(diagnosticText('woocommerce_existing_product',ui),/did not create a duplicate/);
  assert.match(diagnosticText('configuration_failed',ui),/selected connection profile/);
  assert.match(diagnosticText('saved_pricing_invalid',ui),/Saved pricing settings are invalid/);
  assert.match(diagnosticText('cj_logistics_unavailable',ui),/route is unavailable for this variant/);
  assert.match(diagnosticText('cj_freight_unavailable',ui),/No usable freight quote/);
  assert.match(diagnosticText('codex_cli_upgrade_required',ui),/Select a newer Codex CLI/);
  assert.equal(diagnosticText('__proto__',ui),'__proto__');
  ui.setLocale('zh-CN');
  assert.match(ui.t(statusLabels.blocked_incomplete),/上次写入结果未确认/);
  assert.equal(ui.t(statusLabels.interrupted),'尚未完成，结果待确认');
  assert.match(diagnosticText('review_required',ui),/先核对店铺/);
  assert.match(diagnosticText('configuration_failed',ui),/必填配置/);
  assert.match(diagnosticText('saved_pricing_invalid',ui),/已保存的定价设置无效/);
  assert.match(diagnosticText('cj_logistics_unavailable',ui),/该线路不可用于此变体.*核对线路后重试/);
  assert.match(diagnosticText('cj_freight_unavailable',ui),/未返回该变体的可用运费报价/);
  assert.match(diagnosticText('codex_cli_upgrade_required',ui),/当前 Codex CLI 版本过旧/);
  assert.equal(diagnosticText('unknown_safe_code',ui),'unknown_safe_code');
});

test('overlapping list refreshes cannot restore stale results; a failed refresh clears the old list', async () => {
  const old=deferred(),current=deferred(); let calls=0;
  const model=createModel(()=>++calls===1 ? old.promise : current.promise);
  const first=model.refresh(),second=model.refresh();
  current.resolve({reports:[report('current'),{run_id:'../private'}]}); await second;
  old.resolve({reports:[report('old')]}); await first;
  assert.deepEqual(model.reports.map(value=>value.run_id),['current']);
  assert.equal(model.loading,false);
  const broken=createModel(async()=> { throw new Error('invalid_session'); });
  broken.reports=[report('previous')]; await broken.refresh();
  assert.equal(broken.error.message,'invalid_session'); assert.deepEqual(broken.reports,[]);
});

test('switching or closing detail ignores earlier responses and never interpolates unsafe run paths', async () => {
  const first=deferred(),second=deferred(),calls=[];
  const model=createModel(url=>{calls.push(url); return url.endsWith('first') ? first.promise : second.promise;});
  await model.open('../private'); assert.deepEqual(calls,[]);
  const one=model.open('first'),two=model.open('second');
  second.resolve(report('second')); await two;
  first.resolve(report('first')); await one;
  assert.equal(model.selected,'second'); assert.equal(model.detail.run_id,'second');
  const later=deferred(),closed=createModel(()=>later.promise),pending=closed.open('third');
  closed.close(); later.resolve(report('third')); await pending;
  assert.equal(closed.selected,null); assert.equal(closed.detail,null); assert.equal(closed.detailLoading,false);
});

test('report details must match the requested run and list refresh invalidates a pending detail', async () => {
  const invalid=createModel(async()=>report('different'));
  await invalid.open('expected'); assert.equal(invalid.detail,null); assert.equal(invalid.detailError.message,'reports_invalid');
  const pending=deferred(),model=createModel(url=>url==='/api/reports' ? Promise.resolve({reports:[]}) : pending.promise);
  const detail=model.open('old'); await model.refresh(); pending.resolve(report('old')); await detail;
  assert.equal(model.selected,null); assert.equal(model.detail,null);
});

test('TXT is fetched through the authenticated API helper, filenames cannot become paths, and failures permit retry', async () => {
  const calls=[],saved=[],model=createModel(async url=>{calls.push(url);return {text:'Synthetic report\n原链接: https://example.com/item/42',filename:'../../private.txt'};});
  await model.download('test-run',(text,filename)=>saved.push({text,filename}));
  assert.deepEqual(calls,['/api/reports/test-run/text']);
  assert.equal(saved[0].filename,'catalogflow_test-run.txt'); assert.match(saved[0].text,/原链接/);
  assert.equal(model.downloading,null); assert.equal(model.downloadError,null);
  await model.download('../private',()=>assert.fail('invalid run should not download'));
  assert.equal(calls.length,1);
  const failed=createModel(async()=>{throw new Error('invalid_session');});
  await failed.download('test-run',()=>assert.fail('failed request should not save'));
  assert.equal(failed.downloading,null); assert.equal(failed.downloadError.error.message,'invalid_session');
});

test('work-history UI copy is bilingual and uses the same interpolation keys', () => {
  const source=fs.readFileSync(path.join(__dirname,'../src/catalogflow/dashboard-history.js'),'utf8');
  const strings=[...source.matchAll(/'([^'\n]*)'/g)].map(match=>match[1]);
  const missing=[...new Set(strings.filter(value=>/[\u4e00-\u9fff]/.test(value) && !Object.hasOwn(translations,value)))];
  assert.deepEqual(missing,[]);
  for (const value of strings.filter(value=>Object.hasOwn(translations,value))) {
    assert.deepEqual([...value.matchAll(/\{\w+\}/g)].map(match=>match[0]).sort(),
      [...translations[value].matchAll(/\{\w+\}/g)].map(match=>match[0]).sort());
  }
});
