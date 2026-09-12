// Run with: node --test tests/dashboard-i18n.test.cjs (no npm dependencies).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {translations, resolveLocale, create} = require('../src/catalogflow/dashboard-i18n.js');

test('saved supported locale wins; otherwise use the first browser language', () => {
  assert.equal(resolveLocale('en-US', ['zh-CN']), 'en-US');
  assert.equal(resolveLocale('zh-CN', ['en-US']), 'zh-CN');
  assert.equal(resolveLocale('fr-FR', ['zh-TW']), 'zh-CN');
  assert.equal(resolveLocale(null, ['en-GB', 'zh-CN']), 'en-US');
  assert.equal(resolveLocale(undefined, []), 'en-US');
});

test('switching persists only a supported language code and preserves the current locale for invalid values', () => {
  const writes=[];
  const ui=create({storage:{getItem:()=> 'zh-CN',setItem:(...args)=>writes.push(args)},languages:['en-US']});
  assert.equal(ui.locale, 'zh-CN');
  assert.equal(ui.setLocale('en-US'), true);
  assert.deepEqual(writes, [['catalogflow.locale','en-US']]);
  assert.equal(ui.setLocale('de-DE'), false);
  assert.equal(ui.locale, 'en-US');
  assert.equal(writes.length, 1);
});

test('blocked storage still permits in-memory language switching', () => {
  const denied=()=> { throw new Error('Storage denied'); };
  const ui=create({storage:{getItem:denied,setItem:denied},languages:['zh-CN']});
  assert.equal(ui.locale, 'zh-CN');
  assert.doesNotThrow(()=>ui.setLocale('en-US'));
  assert.equal(ui.t('定价工作台'), 'Pricing workbench');
});

test('interpolation works in both languages without changing user-supplied text', () => {
  const ui=create({languages:['en-US']});
  assert.equal(ui.t('当前选用方案 {plan}', {plan:'B'}), 'Plan B selected');
  assert.equal(ui.t('请检查「{label}」的网址格式。', {label:'我的商店'}), 'Check the URL format for “我的商店”.');
  ui.setLocale('zh-CN');
  assert.equal(ui.t('当前选用方案 {plan}', {plan:'B'}), '当前选用方案 B');
});

test('currency stays USD with the same values, and percentages retain one decimal', () => {
  const ui=create({languages:['en-US']});
  for (const locale of ['zh-CN','en-US']) {
    ui.setLocale(locale);
    assert.equal(ui.money(1234.95), '$1,234.95');
    assert.equal(ui.money(-12.5), '-$12.50');
    assert.equal(ui.percent(0.357), '35.7%');
    for (const invalid of [NaN, Infinity, null, '12']) {
      assert.equal(ui.money(invalid), '—');
      assert.equal(ui.percent(invalid), '—');
    }
  }
});

test('provider metadata and known or unknown errors have localized display copy', () => {
  const ui=create({languages:['zh-CN']});
  assert.equal(ui.providerText('Store URL'), '商店网址');
  assert.match(ui.errorText(new Error('invalid_session')), /本机会话/);
  assert.match(ui.errorText(new TypeError('Failed to fetch')), /无法连接/);
  ui.setLocale('en-US');
  assert.equal(ui.providerText('Store URL'), 'Store URL');
  assert.match(ui.errorText(new Error('invalid_session')), /session is invalid/);
  assert.match(ui.errorText(new Error('Connection profile labels must be unique')), /already exists/);
  assert.doesNotMatch(ui.errorText(new Error('unrecognized server detail')), /unrecognized server detail/);
});

test('all initial dashboard copy has an English translation, except bilingual language choices', () => {
  let html=fs.readFileSync(path.join(__dirname,'../src/catalogflow/dashboard.html'),'utf8').replace(/\r\n/g,'\n');
  html=html.replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi,'').replace(/<select id="ui-language"[\s\S]*?<\/select>/,'');
  const copy=[...html.matchAll(/>([^<>]+)</g)].map(match=>match[1].trim());
  copy.push(...[...html.matchAll(/(?:placeholder|aria-label)="([^"]+)"/g)].map(match=>match[1]));
  const missing=[...new Set(copy.filter(value=>/[\u4e00-\u9fff]/.test(value) && !Object.hasOwn(translations,value)))];
  assert.deepEqual(missing, []);
  for (const [source, english] of Object.entries(translations)) {
    assert.ok(english.trim(), source);
    assert.doesNotMatch(english, /[\u4e00-\u9fff]/, source);
    assert.deepEqual([...source.matchAll(/\{\w+\}/g)].map(m=>m[0]).sort(), [...english.matchAll(/\{\w+\}/g)].map(m=>m[0]).sort(), source);
  }
});

test('dynamic Chinese source strings also have English translations', () => {
  const html=fs.readFileSync(path.join(__dirname,'../src/catalogflow/dashboard.html'),'utf8');
  const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const strings=[...script.matchAll(/'([^'\n]*)'/g)].map(match=>match[1]);
  const missing=[...new Set(strings.filter(value=>/[\u4e00-\u9fff]/.test(value) && !Object.hasOwn(translations,value)))];
  assert.deepEqual(missing, []);
});
