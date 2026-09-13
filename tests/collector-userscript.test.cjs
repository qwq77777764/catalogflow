const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const script = fs.readFileSync(path.join(__dirname, '../src/catalogflow/browser/catalogflow-collector.user.js'), 'utf8');
const token = 'synthetic-collection-token-01234567890123456789';
const pairing = (endpoint = 'http://127.0.0.1:45678') => 'CATALOGFLOW1:' + Buffer.from(JSON.stringify({endpoint, token})).toString('base64url');

function page(url, code = pairing()) {
  const location = new URL(url), buttons = [], sent = [], prompts = [], alerts = [];
  const context = {
    location, URLSearchParams,
    atob: value => Buffer.from(value, 'base64').toString('ascii'),
    document: {
      title: 'Synthetic product',
      createElement: () => ({style: {}, addEventListener(event, callback) {this[event] = callback;}}),
      body: {appendChild: element => buttons.push(element)},
    },
    window: {
      confirm: () => true,
      prompt: prompt => {prompts.push(prompt); return code;},
      alert: value => alerts.push(value),
    },
    GM_xmlhttpRequest: request => sent.push(request),
  };
  vm.runInNewContext(script, context);
  return {buttons, sent, prompts, alerts};
}

test('CJ selector pairs once and sends only canonical URL and title', () => {
  const fixture = page('https://www.cjdropshipping.com/product/clock-p-123456789012.html?tracking=remove#details');
  assert.equal(fixture.buttons.length, 1);
  fixture.buttons[0].click();
  fixture.buttons[0].click();
  assert.equal(fixture.prompts.length, 1);
  const request = fixture.sent[0], data = JSON.parse(request.data);
  assert.equal(request.url, 'http://127.0.0.1:45678/api/selections');
  assert.equal(request.headers['X-CatalogFlow-Token'], token);
  assert.equal(request.headers['X-CatalogFlow-Page-Origin'], 'https://www.cjdropshipping.com');
  assert.equal(request.anonymous, true);
  assert.deepEqual(Object.keys(data).sort(), ['page_title', 'product_url', 'source', 'version']);
  assert.equal(data.source, 'cj');
  assert.equal(data.product_url, 'https://www.cjdropshipping.com/product/clock-p-123456789012.html');
});

test('CJ query PID and bare official host remain supported', () => {
  const fixture = page('https://cjdropshipping.com/product/detail?pid=123456789012&tracking=remove');
  fixture.buttons[0].click();
  assert.equal(JSON.parse(fixture.sent[0].data).product_url,
    'https://cjdropshipping.com/product/detail?pid=123456789012');
});

test('Alibaba selector stays collect-only and uses the same one-paste pairing', () => {
  const fixture = page('https://www.alibaba.com/product-detail/Clock_123456.html?tracking=remove');
  fixture.buttons[0].click();
  assert.equal(JSON.parse(fixture.sent[0].data).source, 'alibaba');
  assert.equal(fixture.prompts.length, 1);
});

test('unrelated supplier pages, lookalike hosts and ambiguous CJ IDs fail closed', () => {
  for (const url of [
    'https://www.cjdropshipping.com/product/search',
    'https://www.cjdropshipping.com/product/a-123456789012-b-234567890123.html',
    'https://www.cjdropshipping.com/category/clock-p-123456789012.html',
    'https://www.cjdropshipping.com.evil.example/product/clock-p-123456789012.html',
    'https://www.alibaba.com/trade/search?SearchText=clock',
    'https://detail.1688.com/offer/123456789012.html',
  ]) assert.equal(page(url).buttons.length, 0, url);
});

test('pairing cannot point to a remote or privileged endpoint', () => {
  for (const code of ['plain-token', pairing('https://evil.example'), pairing('http://localhost:45678'),
    pairing('http://127.0.0.1:0'), pairing('http://127.0.0.1:45678/api/imports')]) {
    const fixture = page('https://www.cjdropshipping.com/product/clock-p-123456789012.html', code);
    fixture.buttons[0].click();
    assert.equal(fixture.sent.length, 0);
    assert.equal(fixture.alerts.length, 1);
  }
});

test('frozen session asks to pair again without saving its token', () => {
  const fixture = page('https://www.cjdropshipping.com/product/clock-p-123456789012.html');
  fixture.buttons[0].click();
  fixture.sent[0].onload({status: 409});
  fixture.buttons[0].click();
  assert.equal(fixture.prompts.length, 2);
  assert.equal(script.includes('localStorage'), false);
  assert.equal(script.includes('sessionStorage'), false);
  assert.equal(script.includes('GM_setValue'), false);
});
