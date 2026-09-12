const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {currencies, convertUsd, formatMoney, createModel} = require('../src/catalogflow/dashboard-fx.js');
const {translations} = require('../src/catalogflow/dashboard-i18n.js');
const snapshot = () => ({base:'USD',date:'2026-09-11',rates:{USD:1,CNY:7,EUR:0.9,GBP:0.8,JPY:150,CAD:1.4,AUD:1.5,HKD:7.8,SGD:1.3,CHF:0.8,NZD:1.6}});
const deferred = () => { let resolve,reject; const promise=new Promise((yes,no)=>{resolve=yes;reject=no;}); return {promise,resolve,reject}; };

test('USD freight multiplies by target units per USD, including zero and currency minor units', () => {
  assert.ok(Math.abs(convertUsd(4.71,7)-32.97)<1e-10);
  assert.equal(convertUsd(0,7),0);
  assert.equal(formatMoney(convertUsd(4.71,7),'CNY','en-US').replace(/\s/g,' '),'CNY 32.97');
  assert.equal(formatMoney(convertUsd(4.71,150),'JPY','en-US').replace(/\s/g,' '),'JPY 707');
  assert.equal(formatMoney(4.71,'USD','zh-CN').replace(/\s/g,' '),'USD 4.71');
  assert.equal(formatMoney(12,'invalid','en-US'),'—');
});

test('invalid inputs clear conversions instead of showing a stale or made-up amount', () => {
  for (const amount of [-1,1000001,NaN,Infinity,null,'4.71']) assert.equal(convertUsd(amount,7),null);
  for (const rate of [0,-1,1000001,NaN,Infinity,null,true,'7']) assert.equal(convertUsd(4.71,rate),null);
});

test('reference rates apply to any supported currency; USD is fixed at one', async () => {
  const model=createModel();
  assert.equal(model.rate,null);
  await model.refresh(async()=>snapshot());
  assert.equal(model.rate,7);
  for (const code of currencies) { assert.equal(model.setCurrency(code),true); assert.equal(model.rate,snapshot().rates[code]); }
  assert.equal(model.setCurrency('INVALID'),false);
  assert.equal(model.currency,'USD');
  assert.equal(model.setMode('manual'),false);
  assert.equal(model.rate,1);
  await model.refresh(()=> { throw new Error('USD should not fetch'); });
  assert.equal(model.failed,false);
});

test('manual rates stay specific to each currency and survive a delayed reference response', async () => {
  const model=createModel(),pending=deferred();
  const fetch=model.refresh(()=>pending.promise);
  model.setMode('manual'); model.setManualInput('7.2500');
  model.setCurrency('EUR'); assert.equal(model.manualInput,''); assert.equal(model.rate,null);
  model.setManualInput('0.88');
  pending.resolve(snapshot()); await fetch;
  assert.equal(model.mode,'manual'); assert.equal(model.rate,0.88);
  model.setCurrency('CNY'); assert.equal(model.manualInput,'7.2500'); assert.equal(model.rate,7.25);
  model.setMode('reference'); assert.equal(model.rate,7);
  model.setMode('manual'); assert.equal(model.rate,7.25);
});

test('directly editing a fetched rate selects manual use until explicitly restored', async () => {
  const model=createModel();
  await model.refresh(async()=>snapshot());
  assert.equal(model.rate,7);
  model.setManualInput('7.123456789');
  assert.equal(model.mode,'manual'); assert.equal(model.rate,7.123456789);
  model.setCurrency('EUR'); assert.equal(model.mode,'reference'); assert.equal(model.rate,0.9);
  model.setCurrency('CNY'); assert.equal(model.mode,'manual'); assert.equal(model.manualInput,'7.123456789');
  model.useReference(); assert.equal(model.mode,'reference'); assert.equal(model.rate,7);
  model.setCurrency('EUR'); model.setCurrency('CNY'); assert.equal(model.mode,'reference');
  model.setManualInput(''); assert.equal(model.mode,'manual'); assert.equal(model.rate,null);
});

test('older responses cannot replace newer rates, and failed refreshes discard previous rates', async () => {
  const model=createModel(),old=deferred(),fresh=deferred();
  const first=model.refresh(()=>old.promise),second=model.refresh(()=>fresh.promise);
  const newer=snapshot(); newer.rates.CNY=7.1;
  fresh.resolve(newer); await second;
  old.resolve(snapshot()); await first;
  assert.equal(model.rate,7.1);
  const failure=deferred(),third=model.refresh(()=>failure.promise);
  assert.equal(model.rate,null); assert.equal(model.loading,true);
  failure.reject(new Error('Synthetic private detail')); await third;
  assert.equal(model.failed,true); assert.equal(model.rate,null); assert.equal(model.loading,false);
});

test('failed automatic requests do not disable manual calculations', async () => {
  const model=createModel(),pending=deferred();
  const fetch=model.refresh(()=>pending.promise);
  model.setMode('manual'); model.setManualInput('6.9');
  pending.reject(new Error('Unavailable')); await fetch;
  assert.equal(model.mode,'manual'); assert.equal(model.rate,6.9);
  model.setManualInput(''); assert.equal(model.rate,null);
});

test('malformed public snapshots are rejected', async () => {
  for (const edit of [s=>s.base='EUR',s=>s.date='bad',s=>delete s.rates.JPY,s=>s.rates.CNY=true,s=>s.rates.USD=2,s=>s.rates.CNY=0]) {
    const model=createModel(),data=snapshot(); edit(data);
    await model.refresh(async()=>data);
    assert.equal(model.failed,true); assert.equal(model.rate,null);
  }
});

test('all converter copy has matching bilingual placeholders', () => {
  const script=fs.readFileSync(path.join(__dirname,'../src/catalogflow/dashboard-fx.js'),'utf8');
  const strings=[...script.matchAll(/'([^'\n]*)'/g)].map(match=>match[1]);
  assert.deepEqual(strings.filter(value=>/[\u4e00-\u9fff]/.test(value) && !Object.hasOwn(translations,value)),[]);
});
