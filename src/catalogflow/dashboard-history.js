/* Read-only local reports. Session authentication stays in the caller's API helper. */
(function (root) {
  'use strict';
  const statusLabels = Object.freeze({
    previewed:'预览已生成', drafted:'隐藏草稿已创建', skipped_duplicate:'已跳过重复商品',
    blocked_incomplete:'上次写入结果未确认，已阻止重建', failed:'处理失败', rejected:'请求已拒绝', interrupted:'尚未完成，结果待确认'
  });
  const diagnosticLabels = Object.freeze({
    codex_cli_upgrade_required:'当前 Codex CLI 版本过旧，请在 AI 连接中选择更新的 Codex CLI。',
    cj_logistics_unavailable:'该线路不可用于此变体；核对线路后重试。',
    cj_freight_unavailable:'CJ 未返回该变体的可用运费报价；核对目的地与物流设置后重试。',
    configuration_failed:'连接或运行配置未能加载，请检查所选连接档案与必填配置。',
    saved_pricing_invalid:'已保存的定价设置无效，请修正本机定价设置后重试。',
    woocommerce_invalid_response:'店铺返回的数据格式无效。',
    woocommerce_request_failed:'店铺请求未能完成，请核对本批次记录。',
    woocommerce_existing_product:'店铺已有对应商品，请核对记录中的商品 ID；本次未创建重复商品。',
    woocommerce_ambiguous_term:'店铺存在多个同名分类或标签，需要先核对。',
    woocommerce_term_search_limit:'分类或标签查询已达到限制，处理未完成。',
    woocommerce_draft_state_unconfirmed:'无法确认商品仍为隐藏草稿，请核对店铺商品。',
    woocommerce_image_limit:'商品图片数量超过单次处理限制。',
    wordpress_media_credentials_required:'请在店铺连接中填写有媒体上传权限的 WordPress 用户名和应用程序密码。',
    woocommerce_image_download_failed:'无法读取全部授权商品图片，处理已停止。',
    woocommerce_draft_failed:'隐藏草稿处理未完成；如已记录店铺商品 ID，请先核对该商品。',
    woocommerce_variant_limit:'商品变体数量超过单次处理限制。',
    woocommerce_invalid_variants:'商品变体的 SKU 或属性无效。',
    woocommerce_invalid_prices:'商品变体的价格无效。',
    woocommerce_invalid_terms:'商品分类或标签无效。',
    review_required:'先核对店铺与历史记录，确认上次处理结果后再继续。',
    ValueError:'数据未通过有效性检查。', TypeError:'数据类型不符合要求。', KeyError:'缺少处理所需的字段。',
    OSError:'本机文件或系统操作失败。', PermissionError:'没有所需的本机文件权限。',
    FileNotFoundError:'找不到所需的本机文件。', TimeoutError:'操作超时，结果可能尚未确认。',
    ConnectionError:'连接中断，结果可能尚未确认。', RuntimeError:'操作未能完成。', operation_failed:'操作未能完成。',
    CjApiError:'供应商 API 请求未能完成。',
    WooCommerceDraftError:'隐藏草稿未完整创建；如已记录店铺商品 ID，请先核对该商品。',
    CostFormulaError:'成本公式未通过检查。', JSONDecodeError:'返回的数据不是有效 JSON。',
    UnicodeDecodeError:'文件或返回数据的文字编码无效。',
    'source adapter not configured':'尚未配置所需的供应商连接器。',
    'source does not match the requested adapter':'商品来源与所选连接器不一致。',
    'source_id is required':'缺少来源商品 ID。', 'title is required':'缺少商品标题。',
    'at least one variant is required':'商品至少需要一个变体。',
    'variant costs cannot be negative':'变体成本不能小于 0。',
    'every CJ variant requires a shipping quote before pricing':'每个 CJ 变体都需要运费报价才能定价。',
    'every CJ variant requires a positive shipping cost before pricing':'每个 CJ 变体的运费都必须大于 0。',
    'variant shipping quotes must have a positive quantity and finite cost':'变体运费报价的数量或金额无效。',
    'listing title must contain 1-80 characters':'生成的商品标题必须为 1–80 个字符。',
    'listing prices must match the product variant SKUs':'生成的价格必须与商品变体 SKU 一一对应。'
  });
  function diagnosticText(value, i18n) {
    return Object.hasOwn(diagnosticLabels,value) ? i18n.t(diagnosticLabels[value]) : value;
  }
  const count = value => Number.isSafeInteger(value) && value >= 0 ? value : 0;
  const validRunId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value);
  function safeLink(value) {
    if (typeof value !== 'string' || /[\x00-\x20\x7f]/.test(value)) return null;
    try {
      const url = new URL(value);
      return ['http:','https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
    } catch (_) { return null; }
  }
  function formatTimestamp(value, locale) {
    if (typeof value !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(value)) return '—';
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return '—';
    return new Intl.DateTimeFormat(locale, {
      year:'numeric', month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit',
      second:'2-digit', hourCycle:'h23', timeZone:'UTC', timeZoneName:'short'
    }).format(date);
  }
  function summaryCounts(report) {
    return Object.keys(statusLabels).filter(status=>count(report?.counts?.[status]) > 0)
      .map(status=>({status, count:count(report.counts[status])}));
  }
  function createModel(api) {
    let listRevision=0, detailRevision=0;
    const model = {
      reports:[], loading:false, error:null, selected:null, detail:null, detailLoading:false,
      detailError:null, downloading:null, downloadError:null,
      async refresh(changed=()=>{}) {
        const revision=++listRevision;
        ++detailRevision;
        this.loading=true; this.error=null; this.detailLoading=false; this.detail=null;
        this.detailError=null; this.selected=null; this.downloadError=null; changed();
        try {
          const result=await api('/api/reports');
          if (revision !== listRevision) return;
          if (!Array.isArray(result?.reports)) throw new Error('reports_invalid');
          this.reports=result.reports.filter(report=>report && validRunId(report.run_id));
        } catch (error) {
          if (revision === listRevision) { this.error=error; this.reports=[]; }
        } finally {
          if (revision === listRevision) { this.loading=false; changed(); }
        }
      },
      async open(runId, changed=()=>{}) {
        if (!validRunId(runId)) return;
        const revision=++detailRevision;
        this.selected=runId; this.detail=null; this.detailError=null; this.detailLoading=true; changed();
        try {
          const result=await api('/api/reports/'+encodeURIComponent(runId));
          if (revision !== detailRevision) return;
          if (result?.run_id !== runId || !Array.isArray(result.items)) throw new Error('reports_invalid');
          this.detail=result;
        } catch (error) {
          if (revision === detailRevision) this.detailError=error;
        } finally {
          if (revision === detailRevision) { this.detailLoading=false; changed(); }
        }
      },
      close(changed=()=>{}) {
        ++detailRevision; this.selected=null; this.detail=null; this.detailLoading=false; this.detailError=null; changed();
      },
      async download(runId, saveText, changed=()=>{}) {
        if (!validRunId(runId) || this.downloading) return;
        this.downloading=runId; this.downloadError=null; changed();
        try {
          const result=await api('/api/reports/'+encodeURIComponent(runId)+'/text');
          if (typeof result?.text !== 'string') throw new Error('reports_invalid');
          // A server-provided filename is display data, never a path or a URL.
          const filename=typeof result.filename === 'string' && /^[A-Za-z0-9_-]{1,150}\.txt$/.test(result.filename)
            ? result.filename : 'catalogflow_'+runId+'.txt';
          await saveText(result.text, filename);
        } catch (error) { this.downloadError={runId,error}; }
        finally { this.downloading=null; changed(); }
      }
    };
    return model;
  }
  function mount({container, i18n, api, saveText}) {
    const doc=container.ownerDocument, model=createModel(api), el=id=>doc.getElementById(id);
    const t=(source,params)=>i18n.t(source,params);
    function node(tag, text='', className='') {
      const element=doc.createElement(tag);
      element.textContent=String(text ?? '');
      if (className) element.className=className;
      return element;
    }
    const downloader=saveText || ((text, filename)=> {
      const url=URL.createObjectURL(new Blob(['\uFEFF',text],{type:'text/plain;charset=utf-8'}));
      const link=node('a'); link.href=url; link.download=filename;
      doc.body.append(link);
      try { link.click(); }
      finally { link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000); }
    });
    function button(source, action) {
      const result=node('button',t(source),'secondary'); result.type='button'; result.onclick=action; return result;
    }
    function errorMessage(error) {
      if (['report_not_found','reports_invalid','reports_unavailable'].includes(error?.message))
        return t(error.message==='report_not_found' ? '找不到这份报告，请刷新工作记录。' : '无法读取工作记录，请重试并检查本机报告目录。');
      return i18n.errorText(error);
    }
    function fact(list, label, value, link=false) {
      if (value === undefined || value === null || value === '') return;
      const description=node('dd');
      const href=link ? safeLink(value) : null;
      if (href) {
        const anchor=node('a',value); anchor.href=href; anchor.target='_blank'; anchor.rel='noopener noreferrer';
        description.append(anchor);
      } else description.textContent=String(value);
      list.append(node('dt',t(label)),description);
    }
    function renderItem(item) {
      const entry=node('li','','history-item');
      entry.append(node('h4',t('第 {index} 项 · {title}',{index:count(item.index),title:item.title || t('未记录标题')})));
      const facts=node('dl','','history-facts');
      fact(facts,'处理结果',t(Object.hasOwn(statusLabels,item.status) ? statusLabels[item.status] : '未识别状态'));
      fact(facts,'开始时间',formatTimestamp(item.started_at,i18n.locale));
      fact(facts,'结束时间',formatTimestamp(item.finished_at,i18n.locale));
      fact(facts,'供应商',item.source); fact(facts,'来源商品 ID',item.source_id);
      fact(facts,'原商品链接',item.source_url,true);
      if (item.canonical_source_url && item.canonical_source_url !== item.source_url)
        fact(facts,'规范化商品链接',item.canonical_source_url,true);
      fact(facts,'店铺商品 ID',item.store_id); fact(facts,'店铺商品链接',item.store_url,true);
      fact(facts,'生成文件',item.artifact_path);
      const errors=Array.isArray(item.errors) ? item.errors.filter(value=>typeof value==='string')
        .map(value=>diagnosticText(value,i18n)).join('\n') : '';
      fact(facts,'原因 / 诊断',errors);
      entry.append(facts); return entry;
    }
    function renderDetails(card) {
      const details=node('div','','history-details');
      details.id='history-detail-'+model.selected;
      details.setAttribute('aria-busy',String(model.detailLoading));
      if (model.detailLoading) details.append(node('p',t('正在读取报告详情…'),'hint'));
      else if (model.detailError) {
        const error=node('p',errorMessage(model.detailError),'pricing-error'); error.setAttribute('role','alert');
        details.append(error,button('重新读取详情',()=>model.open(model.selected,render)));
      } else if (model.detail) {
        const facts=node('dl','','history-facts');
        fact(facts,'TXT 报告文件',model.detail.report_path);
        details.append(facts);
        const items=node('ol','','history-items');
        for (const item of model.detail.items) if (item && typeof item==='object') items.append(renderItem(item));
        details.append(items);
        if (!items.children.length) details.append(node('p',t('此批次尚无逐项记录。'),'hint'));
      }
      card.append(details);
    }
    function render() {
      const focusedId=el('history-list').contains(doc.activeElement) ? doc.activeElement?.id : null;
      el('history-refresh').disabled=model.loading;
      el('history-list').setAttribute('aria-busy',String(model.loading));
      el('history-status').textContent=t(model.loading ? '正在读取工作记录…' : '已读取 {count} 个批次（最近记录）', {count:model.reports.length});
      el('history-error').hidden=!model.error;
      el('history-error').textContent=model.error ? errorMessage(model.error) : '';
      const list=el('history-list'); list.replaceChildren();
      if (model.loading || model.error) return;
      if (!model.reports.length) {
        list.append(node('p',t('暂无工作记录。完成一次本机导入后，这里会显示自动归档的报告。'),'empty')); return;
      }
      for (const report of model.reports) {
        const card=node('article','','card history-card'), head=node('div','','history-card-head');
        const title=node('div');
        title.append(node('h3',t(report.mode==='draft' ? '隐藏草稿批次' : '本机预览批次')),
          node('p',report.run_id,'history-run-id'));
        head.append(title,node('span',t(report.status==='completed' ? '批次已结束' : '批次尚未结束'),'history-chip'));
        card.append(head);
        const facts=node('dl','','history-facts');
        fact(facts,'开始时间',formatTimestamp(report.started_at,i18n.locale));
        fact(facts,'结束时间',formatTimestamp(report.finished_at,i18n.locale));
        card.append(facts);
        const counts=node('div','','history-counts');
        for (const item of summaryCounts(report)) {
          const caution=['failed','rejected','interrupted','blocked_incomplete'].includes(item.status);
          counts.append(node('span',t('{status}：{count}',{status:t(statusLabels[item.status]),count:item.count}),
            'history-chip'+(caution ? ' caution' : '')));
        }
        card.append(counts);
        const actions=node('div','','history-actions'), selected=model.selected===report.run_id;
        const toggle=button(selected ? '收起详情' : '查看逐项详情',()=>selected ? model.close(render) : model.open(report.run_id,render));
        toggle.id='history-toggle-'+report.run_id;
        toggle.setAttribute('aria-expanded',String(selected));
        if (selected) toggle.setAttribute('aria-controls','history-detail-'+report.run_id);
        const download=button(model.downloading===report.run_id ? '正在准备 TXT…' : '下载 TXT 报告',
          ()=>model.download(report.run_id,downloader,render));
        download.id='history-download-'+report.run_id;
        download.disabled=Boolean(model.downloading); actions.append(toggle,download); card.append(actions);
        if (model.downloadError?.runId===report.run_id) {
          const error=node('p',errorMessage(model.downloadError.error),'pricing-error'); error.setAttribute('role','alert'); card.append(error);
        }
        if (selected) renderDetails(card);
        list.append(card);
      }
      if (focusedId) el(focusedId)?.focus({preventScroll:true});
    }
    el('history-refresh').onclick=()=>model.refresh(render);
    model.refresh(render);
    return {model,localize:render,refresh:()=>model.refresh(render)};
  }
  const exported={statusLabels,diagnosticText,validRunId,safeLink,formatTimestamp,summaryCounts,createModel,mount};
  if (typeof module !== 'undefined' && module.exports) module.exports=exported;
  else root.CatalogFlowHistory=exported;
})(globalThis);
