/* Single-product preview and explicit hidden-draft review. All requests use the authenticated caller. */
(function (root) {
  'use strict';
  const MAX_JSON_BYTES=49152;
  const statuses=new Set(['running','ready','drafting','completed','failed']);
  const validId=value=>typeof value==='string' && /^[A-Za-z0-9_-]{1,100}$/.test(value);
  const object=value=>value !== null && typeof value==='object' && !Array.isArray(value);
  const diagnosticLabels=Object.freeze({
    import_busy:'另一个搬运任务正在运行，请等它完成。',
    import_invalid_request:'导入内容无效，请检查来源、文件和所选连接。',
    import_invalid_source:'请输入 CJ 商品链接或产品 ID，或选择有效的规范化商品 JSON。',
    import_json_too_large:'JSON 文件不能超过 48 KiB。',
    import_invalid_json:'请选择包含单个规范化商品对象的 UTF-8 JSON 文件。',
    import_profile_required:'请先保存所需连接，再回到这里选择。',
    import_profile_invalid:'所选连接已变更或不可用，请重新选择并生成预览。',
    import_profile_not_found:'所选连接已变更或不可用，请重新选择并生成预览。',
    import_invalid_product:'商品资料未通过检查，请检查商品事实、图片与变体。',
    import_ai_profile_invalid:'所选 AI 连接无效，请检查生成方式与连接是否匹配。',
    import_confirmation_required:'请勾选已审核商品内容与价格。',
    import_revision_mismatch:'预览或连接已变更，请重新生成预览后审核。',
    import_configuration_failed:'连接配置未能加载，请检查档案和系统凭据库。',
    import_reports_unavailable:'无法保存工作记录，请检查本机报告目录后重试。',
    import_store_required:'仅预览无需店铺连接。如需创建隐藏草稿，请选择店铺并重新生成预览。',
    import_not_ready:'请先完成预览并审核，再创建隐藏草稿。',
    import_review_required:'请勾选已审核商品内容与价格。',
    import_stale_preview:'预览或连接已变更，请重新生成预览后审核。',
    import_not_found:'找不到本次任务，请重新连接本机面板。',
    import_invalid_edits:'请检查标题、描述、分类和标签的内容与长度。',
    import_invalid_response:'本机返回的任务数据无效，请重新读取任务状态。',
    import_pricing_dirty:'定价工作台有未保存修改。请先保存或撤销，再生成商品预览。',
    import_request_uncertain:'请求结果尚未确认。正在重新读取任务状态，请勿重复提交。',
    import_failed:'本次处理未完成，请查看工作记录并检查所选连接。',
    import_unavailable:'暂时无法连接本机服务。已保留当前预览与编辑，请重新连接。'
  });
  function errorText(error,i18n) {
    const code=typeof error==='string' ? error : error?.message;
    if (Object.hasOwn(diagnosticLabels,code)) return i18n.t(diagnosticLabels[code]);
    if (root.CatalogFlowHistory) {
      const label=root.CatalogFlowHistory.diagnosticText(code,i18n);
      if(label!==code)return label;
    }
    // Unknown server errors are never echoed: they could include remote response text.
    return i18n.errorText(typeof error==='string' ? new Error(error) : error);
  }
  function safeLink(value) {
    if (typeof value!=='string' || /[\x00-\x20\x7f]/.test(value)) return null;
    try {
      const url=new URL(value);
      if (url.protocol!=='https:' || url.username || url.password || !url.hostname.includes('.')) return null;
      const host=url.hostname.toLowerCase();
      if (host==='localhost' || host.endsWith('.localhost') || host.endsWith('.local') || host.endsWith('.internal') || host.startsWith('[')) return null;
      if (/^\d+(\.\d+){3}$/.test(host)) return null;
      return url.href;
    } catch (_) { return null; }
  }
  function parseProductJSON(text) {
    if (typeof text!=='string') throw new Error('import_invalid_json');
    if (new TextEncoder().encode(text).byteLength>MAX_JSON_BYTES) throw new Error('import_json_too_large');
    let data;
    try { data=JSON.parse(text.replace(/^\uFEFF/,'')); } catch (_) { throw new Error('import_invalid_json'); }
    if (!object(data)) throw new Error('import_invalid_json');
    return data;
  }
  function previewPayload(form) {
    if (!['cj','alibaba-manual'].includes(form.source) || !['codex','claude','deterministic'].includes(form.generator))
      throw new Error('import_invalid_request');
    const input=form.source==='cj' ? String(form.source_input || '').trim() : form.source_input;
    if (form.source==='cj' ? !input || input.length>2048 : !object(input)) throw new Error('import_invalid_source');
    const profile=value=> { if (value===null || value===undefined || value==='') return null;
      if (!validId(value)) throw new Error('import_profile_invalid'); return value; };
    const payload={source:form.source,source_input:input,
      source_profile_id:form.source==='cj' ? profile(form.source_profile_id) : null,
      generator:form.generator,ai_profile_id:form.generator==='deterministic' ? null : profile(form.ai_profile_id),
      store_profile_id:profile(form.store_profile_id)};
    if (payload.source==='cj' && !payload.source_profile_id) throw new Error('import_profile_required');
    if (payload.source==='alibaba-manual' && new TextEncoder().encode(JSON.stringify(input)).byteLength>MAX_JSON_BYTES)
      throw new Error('import_json_too_large');
    return payload;
  }
  function listingEdits(listing={}) {
    return {title:String(listing.title ?? ''),description_html:String(listing.description_html ?? ''),
      category:String(listing.category ?? ''),tags:Array.isArray(listing.tags) ? listing.tags.filter(tag=>typeof tag==='string').join(', ') : ''};
  }
  function draftEdits(edits) {
    const tags=String(edits.tags || '').split(/[,，\n]/).map(tag=>tag.trim()).filter(Boolean);
    const result={title:String(edits.title || '').trim(),description_html:String(edits.description_html || '').trim(),
      category:String(edits.category || '').trim(),tags};
    if (!result.title || result.title.length>80 || !result.description_html || result.description_html.length>16000
      || !result.category || result.category.length>120 || tags.length>20 || tags.some(tag=>tag.length>80))
      throw new Error('import_invalid_edits');
    return result;
  }
  function validateJob(job) {
    if (!object(job) || !validId(job.id) || !statuses.has(job.status) || typeof job.revision!=='string'
      || (job.preview !== null && job.preview !== undefined && (!object(job.preview) || !object(job.preview.product) || !object(job.preview.listing))))
      throw new Error('import_invalid_response');
    return job;
  }
  function createModel(api,{pricingIsDirty=()=>false}={}) {
    let sequence=0,editsJobId=null,originalEdits=listingEdits(),inputVersion=0,pendingPreviewInputs=null;
    const previewInputs=new Map();
    const model={job:null,edits:listingEdits(),reviewed:false,busy:false,reading:false,error:null,uncertain:false,previewInvalidated:false,
      get active() { return ['running','drafting'].includes(this.job?.status); },
      get hasEdits() { return JSON.stringify(this.edits)!==JSON.stringify(originalEdits); },
      get canDraft() { return this.job?.status==='ready' && Boolean(this.job.preview?.store)
        && Boolean(this.job.preview?.listing) && this.reviewed && !this.busy && !this.uncertain && !this.previewInvalidated; },
      inputChanged() {
        ++inputVersion; this.reviewed=false; this.previewInvalidated=true;
      },
      accept(job,requestInputVersion=inputVersion) {
        if (job===null) { this.job=null; return; }
        validateJob(job);
        if (!previewInputs.has(job.id)) previewInputs.set(job.id,requestInputVersion);
        this.previewInvalidated=previewInputs.get(job.id)!==inputVersion;
        this.job=job;
        if (job.preview && editsJobId!==job.id) {
          this.edits=listingEdits(job.preview.listing); originalEdits={...this.edits}; this.reviewed=false; editsJobId=job.id;
        }
      },
      edit(key,value) {
        if (Object.hasOwn(this.edits,key) && !this.active && !this.busy) { this.edits[key]=String(value); this.reviewed=false; }
      },
      async recover(changed=()=>{}) {
        if (this.busy || this.reading) return;
        const request=++sequence,requestInputs=pendingPreviewInputs ?? inputVersion; this.reading=true; changed();
        try {
          const result=await api('/api/imports/current');
          if (request!==sequence) return;
          if (!object(result) || !Object.hasOwn(result,'job')) throw new Error('import_invalid_response');
          this.accept(result.job,requestInputs); pendingPreviewInputs=null; this.error=null; this.uncertain=false;
        } catch (error) { if (request===sequence) this.error=error; }
        finally { if (request===sequence) { this.reading=false; changed(); } }
      },
      async poll(changed=()=>{}) {
        if (this.busy || this.reading || !validId(this.job?.id)) return;
        const request=++sequence,id=this.job.id; this.reading=true;
        try {
          const result=await api('/api/imports/'+encodeURIComponent(id));
          if (request!==sequence) return;
          if (result?.job?.id!==id) throw new Error('import_invalid_response');
          this.accept(result.job); this.error=null; this.uncertain=false;
        } catch (error) { if (request===sequence) this.error=error; }
        finally { if (request===sequence) { this.reading=false; changed(); } }
      },
      async start(form,changed=()=>{}) {
        if (this.busy || this.active || this.uncertain) return;
        // Even a rejected new attempt must never leave the previous product approved.
        this.inputChanged();
        let payload;
        try { if (pricingIsDirty()) throw new Error('import_pricing_dirty'); payload=previewPayload(form); }
        catch (error) { this.error=error; changed(); return; }
        const requestInputs=inputVersion;
        pendingPreviewInputs=requestInputs;
        ++sequence; this.reading=false; this.busy=true; this.error=null; changed();
        try { const result=await api('/api/imports/preview',{method:'POST',body:JSON.stringify(payload)});
          this.accept(validateJob(result?.job),requestInputs); pendingPreviewInputs=null; this.reviewed=false;
        } catch (error) { this.error=error; this.uncertain=!(Object.hasOwn(diagnosticLabels,error?.message) && error.message!=='import_invalid_response') && error?.message!=='invalid_session'; if(!this.uncertain)pendingPreviewInputs=null; }
        finally { this.busy=false; changed(); }
      },
      async draft(changed=()=>{}) {
        if (!this.canDraft) return;
        let edits;
        try { edits=draftEdits(this.edits); } catch (error) { this.error=error; changed(); return; }
        ++sequence; this.reading=false; this.busy=true; this.error=null; changed();
        try {
          const result=await api('/api/imports/'+encodeURIComponent(this.job.id)+'/draft',{
            method:'POST',body:JSON.stringify({revision:this.job.revision,confirm_hidden_draft:true,edits})});
          if (result?.job?.id!==this.job.id) throw new Error('import_invalid_response');
          this.accept(result.job); this.reviewed=false;
        } catch (error) { this.error=error; this.uncertain=!(Object.hasOwn(diagnosticLabels,error?.message) && error.message!=='import_invalid_response') && error?.message!=='invalid_session'; this.reviewed=false; }
        finally { this.busy=false; changed(); }
      }
    };
    return model;
  }
  function shippingCost(variant) {
    if (Number.isFinite(variant?.shipping_cost)) return variant.shipping_cost;
    const quote=variant?.shipping_quote;
    return quote && Number.isFinite(quote.total_cost_usd) && Number.isFinite(quote.quantity) && quote.quantity>0
      ? quote.total_cost_usd/quote.quantity : null;
  }
  function productImages(product={}) {
    const gallery=Array.isArray(product.images) ? product.images : [];
    const variants=Array.isArray(product.variants) ? product.variants : [];
    return [...new Set([...gallery,...variants.map(variant=>variant?.image_url)].filter(url=>typeof url==='string' && url.length>0))];
  }
  function manualProductPayload(form) {
    const text=value=>String(value ?? '').trim(),sourceId=text(form.source_id),title=text(form.title),url=text(form.source_url);
    if(!sourceId || sourceId.length>200 || !title || title.length>500 || url && !safeLink(url))throw new Error('import_invalid_product');
    const images=[...new Set(text(form.images).split(/\r?\n/).map(text).filter(Boolean))];
    if(images.length>20 || images.some(url=>!safeLink(url)))throw new Error('import_invalid_product');
    const pairs=text(form.facts).split(/\r?\n/).filter(line=>line.trim()).map(line=>{
      const match=line.match(/^([^:：]+)[:：](.*)$/);if(!match)throw new Error('import_invalid_product');
      const key=match[1].trim(),value=match[2].trim();if(!key || key.length>100 || value.length>2000)throw new Error('import_invalid_product');return [key,value];
    });
    if(pairs.length>50 || new Set(pairs.map(([key])=>key)).size!==pairs.length)throw new Error('import_invalid_product');
    const origin=text(form.origin_country).toUpperCase(),destination=text(form.destination_country).toUpperCase();
    if(!/^[A-Z]{2}$/.test(origin) || !/^[A-Z]{2}$/.test(destination) || !Array.isArray(form.variants) || !form.variants.length || form.variants.length>100)
      throw new Error('import_invalid_product');
    const variants=form.variants.map((row,index)=>{
      const amount=value=>{if(text(value)==='')throw new Error('import_invalid_product');const number=Number(value);
        if(!Number.isFinite(number) || number<0 || number>1000000)throw new Error('import_invalid_product');return number;};
      const name=text(row.name),image=text(row.image_url),sku=text(row.sku) || 'manual-'+(index+1);
      if(sku.length>200 || name.length>200 || image && !safeLink(image))throw new Error('import_invalid_product');
      if(form.variants.length>1 && !name)throw new Error('import_invalid_product');
      return {sku,cost:amount(row.cost),attributes:name?{Option:name}:{},image_url:image,
        shipping_quote:{origin_country:origin,destination_country:destination,quantity:1,method:'Manual quote',total_cost_usd:amount(row.shipping_cost),estimated_days:''}};
    });
    if(new Set(variants.map(row=>row.sku)).size!==variants.length || new Set(variants.map(row=>row.attributes.Option)).size!==variants.length)
      throw new Error('import_invalid_product');
    const result={source:'alibaba-manual',source_id:sourceId,source_url:url,title,currency:'USD',facts:Object.fromEntries(pairs),images,variants};
    if(productImages(result).length>20)throw new Error('import_invalid_product');
    if(new TextEncoder().encode(JSON.stringify(result)).length>MAX_JSON_BYTES)throw new Error('import_json_too_large');
    return result;
  }
  function manualFormForItem(item={}) {
    let sourceId=item.id || '';
    try{sourceId=new URL(item.url).pathname.match(/\d{5,}/)?.[0] || sourceId;}catch(_){}
    return {source_url:item.url || '',source_id:sourceId,title:item.title || '',facts:'',images:'',origin_country:'CN',destination_country:'US',
      variants:[{name:'',sku:'',cost:'',shipping_cost:'',image_url:''}]};
  }
  function mount({container,i18n,api,getProfiles=()=>[],pricingIsDirty=()=>false,onHistoryRefresh=()=>{},onStateChange=()=>{}}) {
    const doc=container.ownerDocument,model=createModel(api,{pricingIsDirty});
    const t=(source,params)=>i18n.t(source,params),el=id=>doc.getElementById(id),localized=[];
    let pollTimer=null,renderedPreviewId=null,finishedKey=null,profileSignature=null,fileData=null,generatorChanged=()=>{},externalBusy=false;
    function node(tag,text='',className='') {
      const value=doc.createElement(tag); value.textContent=String(text ?? ''); if(className)value.className=className; return value;
    }
    function copy(tag,source,className='') { const value=node(tag,t(source),className); localized.push({value,source}); return value; }
    function button(id,source,action,style='secondary') { const value=copy('button',source,style); value.id=id; value.type='button'; value.onclick=action; return value; }
    function field(id,source,tag='input') {
      const wrapper=node('div','','field'),label=copy('label',source),input=node(tag); label.htmlFor=id; input.id=id;
      wrapper.append(label,input); return {wrapper,input};
    }
    function option(select,value,label) { const item=node('option',label); item.value=value; select.append(item); }
    const heading=copy('h2','商品搬运向导'); heading.id='import-title';
    container.append(heading,copy('p','填写来源，先生成预览；审核后再创建隐藏草稿。每次只处理一个商品。','import-intro'));
    const steps=node('ol','','import-steps');
    for (const source of ['1 · 选择商品','2 · 预览与审核','3 · 创建隐藏草稿']) steps.append(copy('li',source));
    container.append(steps);
    const inputSection=node('section','','import-section'); inputSection.append(copy('h3','1. 选择商品与连接'));
    const form=node('form'); form.id='import-form'; form.autocomplete='off';
    const controls=node('fieldset'); controls.id='import-inputs';
    const grid=node('div','','import-controls');
    const source=field('import-source','商品来源','select');
    option(source.input,'cj','CJdropshipping'); option(source.input,'alibaba-manual',t('手动填写商品 / JSON'));
    const reference=field('import-reference','CJ 商品链接 / 产品 ID'); reference.input.maxLength=2048;
    const file=field('import-file','规范化商品 JSON（最多 48 KiB）'); file.input.type='file'; file.input.accept='.json,application/json';
    file.wrapper.id='import-file-field'; file.wrapper.hidden=true; reference.wrapper.id='import-reference-field';
    const cj=field('import-source-profile','CJ API 连接','select'); cj.wrapper.id='import-source-profile-field';
    const generator=field('import-generator','内容生成方式','select');
    option(generator.input,'codex','Codex'); option(generator.input,'claude','Claude'); option(generator.input,'deterministic',t('本机模板（无需 AI）'));
    const ai=field('import-ai-profile','AI 连接','select'); ai.wrapper.id='import-ai-profile-field';
    const store=field('import-store-profile','目标 WooCommerce 店铺（可选）','select');
    grid.append(source.wrapper,reference.wrapper,file.wrapper,cj.wrapper,generator.wrapper,ai.wrapper,store.wrapper);
    controls.append(grid);
    const manualMode=field('import-manual-mode','商品资料填写方式','select');
    option(manualMode.input,'form',t('直接填写表单'));option(manualMode.input,'json',t('高级：导入规范化 JSON'));
    manualMode.wrapper.hidden=true;controls.append(manualMode.wrapper);
    const manual=elementManualForm();controls.append(manual.box);
    const fileNote=node('p','','hint'); fileNote.id='import-file-status'; controls.append(fileNote);
    const disclosure=copy('p','点击生成预览，即允许所选 AI 处理这个商品已获授权的事实与图片。成本、来源 ID 和店铺密钥不会发送给 AI。','warning');
    disclosure.id='import-ai-disclosure'; controls.append(disclosure);
    const templateNote=copy('p','本机模板不调用 AI，请在预览中审核并完善商品文案。','hint');
    templateNote.id='import-template-note'; templateNote.hidden=true; controls.append(templateNote);
    const settingsNote=copy('p','使用定价工作台中已保存的设置。修改连接或定价后，请重新生成预览。','hint'); controls.append(settingsNote);
    const actions=node('div','','import-actions'),previewButton=button('import-preview','生成预览',()=>{},'primary'); previewButton.type='submit';
    const connections=copy('a','配置连接'); connections.href='#connections';
    const pricing=copy('a','查看定价设置'); pricing.href='#pricing-title';
    actions.append(previewButton,connections,pricing); controls.append(actions); form.append(controls); inputSection.append(form); container.append(inputSection);
    const status=node('p','','import-status'); status.id='import-status'; status.setAttribute('role','status'); status.setAttribute('aria-live','polite');
    const error=node('p','','pricing-error'); error.id='import-error'; error.hidden=true; error.setAttribute('role','alert');
    const reconnect=button('import-reconnect','重新读取任务状态',()=>model.recover(render)); reconnect.hidden=true;
    container.append(status,error,reconnect);
    const review=node('section','','import-section'); review.id='import-review'; review.hidden=true;
    review.append(copy('h3','2. 预览与审核'));
    const stalePreview=copy('p','当前输入已改变或新预览未成功，以下旧预览仅供对照。请重新生成预览后再审核创建。','warning');
    stalePreview.id='import-stale-preview'; stalePreview.hidden=true; review.append(stalePreview);
    const facts=node('dl','','history-facts'); facts.id='import-facts'; review.append(facts);
    const edits=node('div','','import-edit-grid');
    for (const [key,label,tag,max] of [ ['title','商品标题','input',80],['category','商品分类','input',120],
      ['description_html','商品描述（HTML 源码，仅显示文本）','textarea',16000],['tags','标签（逗号分隔）','textarea',1700] ]) {
      const item=field('import-edit-'+key,label,tag); item.input.maxLength=max; item.input.dataset.edit=key;
      if(tag==='textarea')item.wrapper.classList.add('import-full');
      item.input.oninput=()=> { model.edit(key,item.input.value); el('import-reviewed').checked=false; renderControls(); };
      edits.append(item.wrapper);
    }
    review.append(edits,copy('p','图片仅提供 HTTPS 外链供人工核对；此页面不会自动加载供应商图片或执行商品描述中的 HTML。','hint'));
    const images=node('details'); images.id='import-images'; images.append(copy('summary','查看商品图片链接'));
    const imageList=node('ol','','import-image-links'); imageList.id='import-image-list'; images.append(imageList); review.append(images);
    review.append(copy('h4','变体与最终单价（USD / 件）'));
    const tableWrap=node('div','','import-table-wrap'),table=node('table','','import-variants');
    const thead=node('thead'),tr=node('tr');
    for(const label of ['变体 / SKU','商品成本','供应商运费','最终售价'])tr.append(copy('th',label));
    thead.append(tr); const tbody=node('tbody'); tbody.id='import-variant-rows'; table.append(thead,tbody); tableWrap.append(table); review.append(tableWrap);
    review.append(copy('p','供应商运费按报价总额 ÷ 数量显示。最终售价使用实际商品成本、供应商运费和已保存的定价费用；不使用下方试算成本。','hint'));
    const policy=node('details'); policy.append(copy('summary','本次定价设置快照')); const policyFacts=node('dl','','history-facts'); policyFacts.id='import-pricing-snapshot'; policy.append(policyFacts); review.append(policy);
    const draftSection=node('div','','import-draft'); draftSection.append(copy('h3','3. 创建隐藏草稿'));
    const noStore=copy('p','仅预览无需店铺连接。如需创建隐藏草稿，请选择店铺并重新生成预览。','hint'); noStore.id='import-no-store'; draftSection.append(noStore);
    const check=node('label','','check'); const checkInput=node('input'); checkInput.type='checkbox'; checkInput.id='import-reviewed';
    checkInput.onchange=()=> { model.reviewed=checkInput.checked; renderControls(); };
    check.append(checkInput,copy('span','我已审核标题、描述、图片、变体与 USD 价格，同意创建隐藏草稿。')); draftSection.append(check);
    const draft=button('import-draft','创建隐藏草稿',()=>{if(!externalBusy)model.draft(render);},'primary'); draftSection.append(draft);
    draftSection.append(copy('p','只创建 draft + hidden 草稿，不公开发布。使用本次已审核预览，不会再次调用 AI。','hint'));
    review.append(draftSection); container.append(review);
    const result=node('section','','import-result'); result.id='import-result'; result.hidden=true; container.append(result);
    const reportActions=node('div','','import-actions'); reportActions.id='import-report-actions'; reportActions.hidden=true;
    reportActions.append(button('import-report','查看本次工作记录',async()=>{ await onHistoryRefresh(model.job?.report_run_id); el('history-title')?.scrollIntoView({behavior:'smooth'}); }),
      button('import-report-download','下载 TXT 报告',()=>downloadReport())); container.append(reportActions);
    function fact(list,label,value,link=false) {
      if(value===undefined || value===null || value==='')return;
      const dd=node('dd'); const href=link ? safeLink(value) : null;
      if(href) { const anchor=node('a',value); anchor.href=href; anchor.target='_blank'; anchor.rel='noopener noreferrer'; dd.append(anchor); }
      else dd.textContent=String(value);
      list.append(node('dt',t(label)),dd);
    }
    function refreshProfiles(force=false) {
      const profiles=getProfiles(); const signature=JSON.stringify(profiles.map(item=>[item.id,item.provider,item.label,item.is_default]));
      if (!force && signature===profileSignature)return; profileSignature=signature;
      for(const [select,provider,blank] of [[cj.input,'cj','请选择 CJ 连接'],[ai.input,generator.input.value,'使用本机 CLI 默认设置'],[store.input,'woocommerce','仅预览，不选择店铺']]) {
        const previous=select.value,hadOptions=select.options.length>0,entries=profiles.filter(item=>item.provider===provider); select.replaceChildren(); option(select,'',t(blank));
        for(const item of entries)option(select,item.id,item.label);
        if((hadOptions && previous==='') || entries.some(item=>item.id===previous))select.value=previous;
        else if(select===cj.input || select===ai.input)select.value=entries.find(item=>item.is_default)?.id || '';
        if(hadOptions && previous!==select.value)model.inputChanged();
      }
    }
    function sourceFields() {
      const manual=source.input.value==='alibaba-manual',template=generator.input.value==='deterministic';
      file.wrapper.hidden=!manual || manualMode.input.value!=='json'; reference.wrapper.hidden=manual; cj.wrapper.hidden=manual;
      manualMode.wrapper.hidden=!manual;
      el('import-manual-form').hidden=!manual || manualMode.input.value!=='form';
      ai.wrapper.hidden=template; disclosure.hidden=template; templateNote.hidden=!template;
      refreshProfiles(true);
    }
    source.input.onchange=sourceFields; manualMode.input.onchange=sourceFields;
    generator.input.onchange=()=>{sourceFields();generatorChanged(generator.input.value,ai.input.value || null);};
    ai.input.onchange=()=>generatorChanged(generator.input.value,ai.input.value || null);
    for(const eventName of ['input','change']) controls.addEventListener(eventName,event=>{
      if(event.target.matches('input,select,textarea')) {model.inputChanged();render();}
    });
    file.input.onchange=async()=> {
      fileData=null; model.error=null; const selected=file.input.files?.[0];
      if(!selected) { fileNote.textContent=''; return; }
      try {
        if(selected.size>MAX_JSON_BYTES)throw new Error('import_json_too_large');
        const parsed=parseProductJSON(await selected.text());
        if(file.input.files?.[0]!==selected)return;
        fileData=parsed; fileNote.textContent=t('已读取文件：{name}',{name:selected.name});
      } catch(error) { if(file.input.files?.[0]!==selected)return; model.error=error; fileNote.textContent=''; }
      render();
    };
    form.onsubmit=event=> {event.preventDefault();if(externalBusy)return;let sourceInput;
      try{sourceInput=source.input.value==='cj'?reference.input.value:manualMode.input.value==='form'?manualProductPayload(manual.read()):fileData;}
      catch(error){model.inputChanged();model.error=error;render();return;}
      model.start({source:source.input.value,source_input:sourceInput,source_profile_id:cj.input.value,
        generator:generator.input.value,ai_profile_id:ai.input.value,store_profile_id:store.input.value},render);
    };
    function elementManualForm() {
      const box=node('div','','import-manual');box.id='import-manual-form';box.hidden=true;
      box.append(copy('p','填写你已获授权并核实的商品资料。金额统一为 USD，每个变体填写单件运费；此表单不会抓取商品网页。','hint'));
      const fields={},grid=node('div','','import-edit-grid');
      for(const [key,label,tag,max] of [['source_url','原商品链接','input',2048],['source_id','商品编号（用于识别重复商品）','input',200],
        ['title','来源商品标题','input',500],['origin_country','发货国家代码','input',2],['destination_country','收货国家代码','input',2],
        ['facts','已核实的事实（每行 名称: 内容）','textarea',12000],['images','授权图片 HTTPS 链接（每行一条）','textarea',20000]]) {
        const item=field('import-manual-'+key,label,tag);item.input.maxLength=max;fields[key]=item.input;
        if(tag==='textarea')item.wrapper.classList.add('import-full');grid.append(item.wrapper);
      }
      fields.origin_country.value='CN';fields.destination_country.value='US';
      fields.source_url.onchange=()=>{if(!fields.source_id.value){try{const id=new URL(fields.source_url.value).pathname.match(/\d{5,}/)?.[0];if(id)fields.source_id.value=id;}catch(_){}}};
      box.append(grid,copy('p','例如 Material: Wood、Dimensions: 30 × 30 cm。只填写已核实信息；未知内容留空。多属性变体可使用高级 JSON。','hint'));
      const rows=node('div','','import-manual-variants');rows.id='import-manual-variants';box.append(rows);
      let count=0;
      function addVariant() {
        if(rows.children.length>=100)return;const row=node('div','','import-manual-variant');const values={};
        for(const [key,label] of [['name','变体名称（单规格可留空）'],['sku','变体 SKU（可留空自动编号）'],['cost','商品成本（USD / 件）'],['shipping_cost','运费（USD / 件，确认为零时填 0）'],['image_url','该变体图片 HTTPS 链接（可选）']]) {
          const item=field('import-manual-variant-'+count+'-'+key,label);values[key]=item.input;item.input.dataset.manualVariant=key;
          if(['cost','shipping_cost'].includes(key)){item.input.type='number';item.input.min='0';item.input.max='1000000';item.input.step='any';}
          else item.input.maxLength=key==='image_url'?2048:200;row.append(item.wrapper);
        }
        const remove=button('import-manual-remove-'+count,'删除这个变体',()=>{if(rows.children.length<=1)return;row.remove();model.inputChanged();render();});row.append(remove);rows.append(row);count++;
      }
      const add=button('import-manual-add','增加一个变体',()=>{addVariant();model.inputChanged();render();});box.append(add);addVariant();
      return {box,fields,reset:item=>{const clean=manualFormForItem(item);for(const [key,input] of Object.entries(fields))input.value=clean[key];rows.replaceChildren();addVariant();},
        read:()=>({...Object.fromEntries(Object.entries(fields).map(([key,input])=>[key,input.value])),
        variants:[...rows.children].map(row=>Object.fromEntries([...row.querySelectorAll('[data-manual-variant]')].map(input=>[input.dataset.manualVariant,input.value])))} )};
    }
    function renderPreview() {
      const preview=model.job?.preview; review.hidden=!preview;
      if(!preview)return;
      facts.replaceChildren();
      fact(facts,'供应商',preview.product.source); fact(facts,'来源商品 ID',preview.product.source_id);
      fact(facts,'原商品链接',preview.product.source_url,true);
      fact(facts,'来源标题',preview.product.title);
      fact(facts,'目标店铺',preview.store?.label); fact(facts,'店铺网址',preview.store?.base_url,true);
      const images=productImages(preview.product);
      fact(facts,'商品图片数量',images.length); imageList.replaceChildren();
      for(const [index,url] of images.entries()) {
        const item=node('li'),href=safeLink(url);
        if(href) {const link=node('a',t('图片 {index}',{index:index+1})+' · '+url);link.href=href;link.target='_blank';link.rel='noopener noreferrer';item.append(link);}
        else item.textContent=t('图片 {index}：链接不可打开',{index:index+1});
        imageList.append(item);
      }
      tbody.replaceChildren();
      const variants=Array.isArray(preview.product.variants) ? preview.product.variants : [];
      const prices=preview.listing.prices_by_sku || preview.listing.prices || {};
      for(const variant of variants) {
        if(!object(variant))continue;
        const row=node('tr'); const attrs=object(variant.attributes) ? Object.entries(variant.attributes).map(([key,value])=>key+': '+String(value)).join(' · ') : '';
        for(const [label,value] of [['变体 / SKU',attrs+'\n'+String(variant.sku ?? '')],['商品成本',i18n.money(variant.cost)],
          ['供应商运费',i18n.money(shippingCost(variant))],['最终售价',i18n.money(Object.hasOwn(prices,variant.sku) ? prices[variant.sku] : null)]]) {
          const cell=node('td',value); cell.dataset.label=t(label); row.append(cell);
        }
        tbody.append(row);
      }
      policyFacts.replaceChildren(); const policy=preview.pricing || {};
      fact(policyFacts,'定价方案',t(policy.scheme==='margin' ? '方案 A · 目标利润率' : '方案 B · 自定义成本公式'));
      const labels={target_margin:'目标利润率',cost_formula:'商品成本公式',cost_multiplier:'成本倍率',
        payment_fee_rate:'支付费率',payment_fixed_fee:'固定支付费',return_rate:'退货预留',operating_rate:'运营预留',
        tax_duties_per_unit:'预估税费（USD / 件）',minimum_price:'最低售价',minimum_multiplier:'最低成本倍率'};
      const percentages=new Set(['target_margin','payment_fee_rate','return_rate','operating_rate']);
      const dollars=new Set(['payment_fixed_fee','tax_duties_per_unit','minimum_price']);
      for(const [key,label] of Object.entries(labels)) if(Object.hasOwn(policy,key))
        fact(policyFacts,label,percentages.has(key) ? i18n.percent(policy[key]) : dollars.has(key) ? i18n.money(policy[key]) : policy[key]);
      if(renderedPreviewId!==model.job.id) {
        for(const [key,value] of Object.entries(model.edits))el('import-edit-'+key).value=value;
        renderedPreviewId=model.job.id;
      }
    }
    function renderControls() {
      controls.disabled=model.busy || model.active || model.uncertain || externalBusy;
      previewButton.disabled=model.busy || model.active || model.uncertain || externalBusy;
      el('import-reviewed').disabled=model.job?.status!=='ready' || !model.job?.preview?.store || model.busy || model.uncertain || model.previewInvalidated || externalBusy;
      el('import-reviewed').checked=model.reviewed;
      draft.disabled=!model.canDraft || externalBusy;
      for(const key of Object.keys(model.edits))el('import-edit-'+key).disabled=model.job?.status!=='ready' || model.busy || model.previewInvalidated;
      noStore.hidden=Boolean(model.job?.preview?.store);
      stalePreview.hidden=!model.previewInvalidated;
    }
    function render() {
      refreshProfiles(); renderControls();
      container.setAttribute('aria-busy',String(model.active || model.busy));
      const labels={fetching:'正在读取商品与运费…',generating:'正在生成商品文案…',pricing:'正在计算逐变体价格…',drafting:'正在创建隐藏草稿，请勿重复提交…'};
      const statusLabel=model.busy ? '正在提交请求…' : model.active ? labels[model.job.phase] || '任务正在处理中…'
        : model.previewInvalidated && model.job?.preview ? '旧预览已失效，请重新生成预览。'
        : model.job?.status==='ready' ? '预览已完成，请审核后创建隐藏草稿。'
        : model.job?.status==='completed' ? '本次任务已完成。' : model.job?.status==='failed' ? '本次任务未完成，请核对工作记录。'
        : model.reading ? '正在恢复本机会话中的任务…' : '尚未开始：先填写商品来源并生成预览。';
      status.textContent=t(statusLabel);
      const issue=model.error || model.job?.error;
      error.hidden=!issue && !model.uncertain;
      error.textContent=issue ? errorText(issue,i18n) : model.uncertain ? t(diagnosticLabels.import_request_uncertain) : '';
      reconnect.hidden=!model.uncertain && (!model.error || Object.hasOwn(diagnosticLabels,model.error?.message)
        && model.error.message!=='import_invalid_response');
      reconnect.disabled=model.reading || model.busy;
      renderPreview();
      result.replaceChildren(); result.hidden=!model.job?.result;
      if(model.job?.result) {
        const value=model.job.result,statuses={drafted:'隐藏草稿已创建',skipped_duplicate:'已跳过重复商品',blocked_incomplete:'上次写入结果未确认，已阻止重建',failed:'处理失败',previewed:'预览已生成'};
        result.append(node('h3',t(statuses[value.status] || '处理结果')));
        const list=node('dl','','history-facts'); fact(list,'店铺商品 ID',value.store_id); fact(list,'店铺商品链接',value.store_url,true);
        if(Array.isArray(value.errors)) for(const code of value.errors) fact(list,'原因 / 诊断',errorText(code,i18n));
        result.append(list);
      }
      reportActions.hidden=!validId(model.job?.report_run_id);
      const key=model.job && !model.active ? model.job.id+':'+model.job.status : null;
      if(key && finishedKey!==key) {finishedKey=key; onHistoryRefresh();}
      clearTimeout(pollTimer);
      if(model.uncertain)pollTimer=setTimeout(()=>model.recover(render),1800);
      else if(model.active)pollTimer=setTimeout(()=>model.poll(render),1500);
      onStateChange();
    }
    async function downloadReport() {
      const runId=model.job?.report_run_id;if(!validId(runId))return;
      const button=el('import-report-download');button.disabled=true;
      try {
        const value=await api('/api/reports/'+encodeURIComponent(runId)+'/text');
        if(typeof value?.text!=='string')throw new Error('import_invalid_response');
        const url=URL.createObjectURL(new Blob(['\uFEFF',value.text],{type:'text/plain;charset=utf-8'}));
        const link=node('a');link.href=url;link.download='catalogflow_'+runId+'.txt';doc.body.append(link);
        try {link.click();} finally {link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
      } catch(error) {model.error=error;render();} finally {button.disabled=false;}
    }
    function localize() {
      for(const {value,source} of localized)value.textContent=t(source);
      source.input.options[1].textContent=t('手动填写商品 / JSON');generator.input.options[2].textContent=t('本机模板（无需 AI）');
      manualMode.input.options[0].textContent=t('直接填写表单');manualMode.input.options[1].textContent=t('高级：导入规范化 JSON');
      if(fileData && file.input.files?.[0])fileNote.textContent=t('已读取文件：{name}',{name:file.input.files[0].name});
      refreshProfiles(true);render();
    }
    sourceFields();model.recover(render);
    return {model,localize,refreshProfiles,refresh:()=>model.recover(render),dispose:()=>clearTimeout(pollTimer),
      setExternalBusy:value=>{externalBusy=Boolean(value);renderControls();},
      invalidateInputs:()=>{model.inputChanged();render();},
      onGeneratorChange:callback=>{generatorChanged=callback;callback(generator.input.value,ai.input.value || null);},
      selectGenerator:(value,profileId=null)=>{
        if(!['codex','claude','deterministic'].includes(value) || model.active || model.busy || model.uncertain || externalBusy)return false;
        if(generator.input.value===value && (ai.input.value || null)===profileId)return true;
        generator.input.value=value;sourceFields();ai.input.value=profileId || '';model.inputChanged();render();return true;
      },
      selectSourceItem:item=>{
        if(!item?.frozen || model.active || model.busy || model.uncertain || externalBusy)return;
        if(item.source==='cj'){source.input.value='cj';reference.input.value=item.url;}
        else{source.input.value='alibaba-manual';manualMode.input.value='form';manual.reset(item);}
        sourceFields();model.inputChanged();render();
      },
      processing:()=>model.active || model.busy || model.uncertain,
      havePendingChanges:()=>model.hasEdits && model.job?.status==='ready'};
  }
  const exported={MAX_JSON_BYTES,validId,safeLink,parseProductJSON,previewPayload,draftEdits,validateJob,shippingCost,productImages,manualProductPayload,manualFormForItem,diagnosticLabels,errorText,createModel,mount};
  if(typeof module!=='undefined' && module.exports)module.exports=exported;
  else root.CatalogFlowImport=exported;
})(globalThis);
