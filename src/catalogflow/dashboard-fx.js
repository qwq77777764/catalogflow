/* Display-only USD freight conversion. No pricing writes or external amount transmission. */
(function (root) {
  'use strict';
  const currencies = Object.freeze(['CNY','EUR','GBP','JPY','CAD','AUD','HKD','SGD','CHF','NZD','USD']);
  const validRate = value => typeof value === 'number' && Number.isFinite(value) && value > 0 && value <= 1000000;
  function convertUsd(amount, rate) {
    if (typeof amount !== 'number' || !Number.isFinite(amount) || amount < 0 || amount > 1000000 || !validRate(rate)) return null;
    return amount * rate;
  }
  function formatMoney(amount, currency, locale) {
    if (!currencies.includes(currency) || typeof amount !== 'number' || !Number.isFinite(amount)) return '—';
    // Currency codes avoid ambiguous dollar/yen symbols; Intl applies each currency's minor units.
    return new Intl.NumberFormat(locale, {style:'currency',currency,currencyDisplay:'code'}).format(amount);
  }
  function createModel() {
    const manualRates = new Map();
    let request = 0;
    const model = {
      currency:'CNY', mode:'reference', snapshot:null, loading:false, failed:false,
      get manualInput() { return manualRates.get(this.currency) || ''; },
      get rate() {
        if (this.currency === 'USD') return 1;
        const value = this.mode === 'manual'
          ? (this.manualInput.trim() ? Number(this.manualInput) : NaN)
          : this.snapshot?.rates[this.currency];
        return validRate(value) ? value : null;
      },
      setCurrency(value) {
        if (!currencies.includes(value)) return false;
        this.currency=value;
        if (value === 'USD') this.mode='reference';
        return true;
      },
      setMode(value) {
        if (!['reference','manual'].includes(value) || this.currency === 'USD') return false;
        this.mode=value;
        return true;
      },
      setManualInput(value) { manualRates.set(this.currency, String(value)); },
      async refresh(loadRates, changed = () => {}) {
        if (this.currency === 'USD') { changed(); return; }
        const revision=++request;
        this.loading=true; this.failed=false; this.snapshot=null; changed();
        try {
          const snapshot=await loadRates();
          if (revision !== request) return;
          if (snapshot?.base !== 'USD' || !/^\d{4}-\d{2}-\d{2}$/.test(snapshot.date || '')
              || !currencies.every(code=>validRate(snapshot.rates?.[code])) || snapshot.rates.USD !== 1)
            throw new Error('Invalid reference rates');
          this.snapshot=snapshot;
        } catch (_) {
          if (revision === request) { this.failed=true; this.snapshot=null; }
        } finally {
          if (revision === request) { this.loading=false; changed(); }
        }
      }
    };
    return model;
  }
  function mount({container, amountInput, i18n, loadRates}) {
    const model=createModel(), doc=container.ownerDocument;
    const el=id=>doc.getElementById(id), t=(source,params)=>i18n.t(source,params);
    const currency=el('fx-currency'), mode=el('fx-mode'), rate=el('fx-rate');
    function render() {
      const amount=amountInput.validity.valid ? amountInput.valueAsNumber : NaN;
      const converted=convertUsd(amount,model.rate);
      currency.value=model.currency; mode.value=model.mode;
      mode.disabled=model.currency==='USD';
      el('fx-manual-field').hidden=model.mode!=='manual';
      rate.setAttribute('aria-invalid',String(model.mode==='manual' && model.rate===null));
      el('fx-rate-label').textContent=t('每 1 USD 可兑换的 {currency}',{currency:model.currency});
      el('fx-from').textContent=Number.isFinite(amount) && amount>=0 ? formatMoney(amount,'USD',i18n.locale) : '—';
      el('fx-result').textContent=converted===null ? '—' : formatMoney(converted,model.currency,i18n.locale);
      el('fx-result').classList.toggle('fx-muted',converted===null);
      el('fx-equation').textContent=model.rate===null ? '—' : t('1 USD = {rate} {currency}',{
        rate:new Intl.NumberFormat(i18n.locale,{maximumSignificantDigits:8}).format(model.rate),currency:model.currency});
      const status=el('fx-status');
      status.classList.toggle('fx-caution',model.currency!=='USD' && model.mode==='reference' && model.failed);
      if (model.currency==='USD') status.textContent=t('相同币种，无需换算。');
      else if (model.mode==='manual') status.textContent=t('手动汇率 · 仅用于当前页面试算');
      else if (model.loading) status.textContent=t('正在获取参考汇率…');
      else if (model.failed) status.textContent=t('参考汇率暂不可用。请重试，或选择手动汇率。');
      else if (model.snapshot) status.textContent=t('Frankfurter · 参考日期 {date}',{date:model.snapshot.date});
      else status.textContent=t('等待参考汇率…');
      const issue=(!Number.isFinite(amount) || amount<0 || amount>1000000)
        ? t('请先填写有效的尾程 / 整段运费（0–1,000,000 USD）。')
        : model.mode==='manual' && model.rate===null ? t('请输入大于 0 且不超过 1,000,000 的汇率。') : '';
      el('fx-error').textContent=issue; el('fx-error').hidden=!issue;
      el('fx-refresh').disabled=model.loading || model.currency==='USD';
      el('fx-refresh').textContent=t(model.mode==='manual' ? '使用参考汇率' : '刷新参考汇率');
      el('fx-result-row').setAttribute('aria-busy',String(model.mode==='reference' && model.loading && model.currency!=='USD'));
    }
    function localize() {
      const names=new Intl.DisplayNames([i18n.locale],{type:'currency'});
      currency.replaceChildren(...currencies.map(code=> {
        const option=doc.createElement('option'); option.value=code; option.textContent=code+' · '+names.of(code); return option;
      }));
      render();
    }
    currency.onchange=()=> { model.setCurrency(currency.value); rate.value=model.manualInput; render(); };
    mode.onchange=()=> { model.setMode(mode.value); rate.value=model.manualInput; render(); };
    rate.oninput=()=> { model.setManualInput(rate.value); render(); };
    // Enter in the converter must not submit the surrounding pricing settings form.
    container.addEventListener('keydown',event=> { if(event.key==='Enter' && event.target.matches('input')) event.preventDefault(); });
    el('fx-refresh').onclick=()=> { model.setMode('reference'); model.refresh(loadRates,render); };
    amountInput.addEventListener('input',render);
    localize();
    model.refresh(loadRates,render);
    return {localize};
  }
  const api={currencies,validRate,convertUsd,formatMoney,createModel,mount};
  if (typeof module !== 'undefined' && module.exports) module.exports=api;
  else root.CatalogFlowFX=api;
})(globalThis);
