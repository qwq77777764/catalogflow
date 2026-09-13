/* Novice setup and explicit browser selection. No automatic login, AI use, or import. */
(function(root) {
  'use strict';
  const providers=new Set(['codex','claude']);
  const officialGuidance=Object.freeze({codex:{install_url:'https://developers.openai.com/codex/cli/',login_url:'https://developers.openai.com/codex/auth/'},
    claude:{install_url:'https://code.claude.com/docs/en/setup',login_url:'https://code.claude.com/docs/en/authentication'}});
  const validId=value=>typeof value==='string' && /^[A-Za-z0-9_-]{1,100}$/.test(value);
  const object=value=>value!==null && typeof value==='object' && !Array.isArray(value);
  const statusLabels=Object.freeze({
    idle:'尚未检查',checking:'正在检查安装与登录…',missing:'尚未找到本机 AI 程序',outdated:'AI 程序版本需要更新',
    logged_out:'尚未登录',auth_unknown:'登录状态未能确认',signed_in:'已检测到登录状态；尚未验证本次可用额度',
    testing:'正在运行小型 AI 测试…',test_passed:'小型 AI 测试已通过',test_failed:'小型 AI 测试未通过',
    login_opened:'已打开登录流程；完成后请重新检查',manual_login_required:'需要按官方说明手动登录',
    stale:'连接已变更，请重新检查'
  });
  const diagnostics=Object.freeze({
    ai_setup_invalid_request:'检查请求无效，请重新选择 AI 与连接。',
    ai_setup_profile_invalid:'AI 连接不可用，请选择相符的已保存连接。',
    ai_setup_busy:'AI 检查正在运行，请等它完成。',
    ai_setup_confirmation_required:'请先确认小型 AI 测试可能消耗额度。',
    ai_cli_missing:'先按官方说明安装程序，然后点击检查安装与登录。',
    ai_cli_upgrade_required:'请更新所选 AI 程序，再重新检查。',
    ai_auth_required:'点击打开登录，完成官方登录后重新检查。',
    ai_auth_unknown:'无法可靠判断登录状态。可以重新登录，或自行选择运行小型 AI 测试。',
    ai_check_timeout:'安装或登录检查超时，请确认程序可用后重试。',
    ai_test_timeout:'小型 AI 测试超时；无法确认本次额度是否已消耗。',
    ai_test_failed:'测试未完成，请核对登录、订阅与网络后再试。',
    ai_test_invalid_output:'AI 返回未通过格式检查，请更新程序后重试。',
    ai_subscription_or_quota:'提供方拒绝了本次测试，请核对订阅或额度。',
    ai_login_opened:'在打开的官方登录流程中完成登录，再回到这里重新检查。',
    ai_login_manual_required:'请按官方登录说明操作。完成后回到这里重新检查。',
    ai_signed_in:'已检测到登录状态；尚未验证本次可用额度',
    ai_test_passed:'小型 AI 测试已通过；这不保证之后的请求或剩余额度。',
    ai_connection_changed:'已保存的 AI 连接已变更，旧检查与测试结果不再适用。请重新检查。',
    setup_invalid_response:'本机返回的状态无效，请刷新状态重试。',
    selection_invalid_request:'采集请求无效，请重新检查所选队列或文件。',
    selection_not_found:'找不到所选商品或队列，请刷新列表。',
    selection_not_frozen:'请先结束采集并确认，再使用商品。',
    selection_busy:'采集状态正在变更，请稍后重试。',
    setup_queue_too_large:'队列文件不能超过 48 KiB。',
    setup_invalid_queue:'请选择有效的采集队列 JSON 文件。',
    workflow_busy:'AI 检查、测试或商品处理正在运行，请等待完成后再操作。',
    workflow_closed:'本机服务正在关闭，请重新打开程序。',
    workflow_invalid_request:'请求无效，请重新选择并操作。',
    workflow_unavailable:'本机服务暂时不可用，请刷新状态重试。',
    queue_unavailable:'无法读取或保存采集队列，请检查本机文件权限后重试。',
    queue_archive_limit:'采集队列数量已达到上限，请先整理本机已归档队列。',
    queue_invalid_archive:'部分采集记录无效，已跳过。请检查原队列文件。',
    queue_invalid_request:'采集请求无效，请重新检查所选队列或文件。',
    queue_invalid_item:'所选商品无效，请刷新列表。',
    queue_not_found:'找不到所选商品或队列，请刷新列表。',
    queue_not_frozen:'请先结束采集并确认，再使用商品。'
  });
  function diagnostic(error,i18n) {
    const code=typeof error==='string'?error:error?.message;
    return Object.hasOwn(diagnostics,code)?i18n.t(diagnostics[code]):i18n.errorText(typeof error==='string'?new Error(error):error);
  }
  function officialLink(value) {
    try {const url=new URL(value);return url.protocol==='https:' && !url.username && !url.password
      && ['developers.openai.com','learn.chatgpt.com','help.openai.com','code.claude.com','docs.anthropic.com','claude.com'].includes(url.hostname)?url.href:null;}catch(_){return null;}
  }
  function collectorEndpoint(value) {
    try {const url=new URL(value);return url.protocol==='http:' && url.hostname==='127.0.0.1' && /^\d+$/.test(url.port)
      && Number(url.port)>1023 && Number(url.port)<=65535 && !url.username && !url.password && url.pathname==='/' && !url.search && !url.hash
      ?url.origin:null;}catch(_){return null;}
  }
  function aiPayload(provider,profile_id) {
    if(!providers.has(provider) || profile_id && !validId(profile_id))throw new Error('ai_setup_invalid_request');
    return {provider,profile_id:profile_id || null};
  }
  function validateAI(value) {
    if(!object(value) || !['idle','running','complete'].includes(value.phase) || typeof value.busy!=='boolean'
      || !Object.hasOwn(statusLabels,value.status))throw new Error('setup_invalid_response');
    return value;
  }
  function validateQueue(value) {
    if(!object(value) || !Array.isArray(value.items) || !Array.isArray(value.queues)
      || value.active!==null && (!object(value.active) || !validId(value.active.queue_id) || !collectorEndpoint(value.active.endpoint)
        || typeof value.active.pairing_code!=='string' || !/^CATALOGFLOW1:[A-Za-z0-9_-]+$/.test(value.active.pairing_code)))throw new Error('setup_invalid_response');
    return value;
  }
  function parseQueue(text) {
    if(typeof text!=='string')throw new Error('setup_invalid_queue');
    if(new TextEncoder().encode(text).length>49152)throw new Error('setup_queue_too_large');
    let value;try{value=JSON.parse(text.replace(/^\uFEFF/,''));}catch(_){throw new Error('setup_invalid_queue');}
    if(!object(value))throw new Error('setup_invalid_queue');return value;
  }
  function selectionCounts(snapshot) {
    const items=Array.isArray(snapshot?.items)?snapshot.items.filter(item=>object(item) && validId(item.id)):[];
    const current=snapshot?.active?items.filter(item=>item.queue_id===snapshot.active.queue_id).length:0;
    return {current,archived:items.length-current,total:items.length};
  }
  function createModel(api) {
    let aiRevision=0,queueRevision=0;const invalidAIJobs=new Set();
    return {provider:'codex',profileId:null,ai:null,aiBusy:false,aiReading:false,aiError:null,usageConfirmed:false,
      queue:null,queueBusy:false,queueReading:false,queueError:null,queueUncertain:false,
      choose(provider,profileId=null) {
        if(![...providers,'deterministic'].includes(provider))return;
        if(this.provider===provider && this.profileId===(profileId || null))return;
        ++aiRevision;this.provider=provider;this.profileId=profileId || null;this.ai=null;
        this.aiError=null;this.usageConfirmed=false;this.aiReading=false;
      },
      invalidateAI() {if(this.ai?.job_id)invalidAIJobs.add(this.ai.job_id);++aiRevision;this.ai=null;this.aiError=null;this.aiReading=false;this.usageConfirmed=false;},
      async readAI(changed=()=>{}) {
        if(this.aiReading || this.aiBusy || this.provider==='deterministic')return;
        const revision=++aiRevision;this.aiReading=true;changed();
        try {const value=validateAI(await api('/api/ai-setup'));if(revision!==aiRevision)return;
          // A result for another provider/profile must not imply readiness for the current choice.
          this.ai=value.provider===this.provider && (value.profile_id || null)===this.profileId && !invalidAIJobs.has(value.job_id)?value:null;this.aiError=null;
        }catch(error){if(revision===aiRevision)this.aiError=error;}
        finally{if(revision===aiRevision){this.aiReading=false;changed();}}
      },
      async runAI(operation,changed=()=>{}) {
        if(this.aiBusy || this.ai?.busy || this.provider==='deterministic' || !['check','test','login'].includes(operation))return;
        if(operation==='test' && !this.usageConfirmed){this.aiError=new Error('ai_setup_confirmation_required');changed();return;}
        let payload;try{payload=aiPayload(this.provider,this.profileId);}catch(error){this.aiError=error;changed();return;}
        if(operation==='test')payload.confirm_usage=true;
        const revision=++aiRevision;this.aiBusy=true;this.aiReading=false;this.aiError=null;this.usageConfirmed=false;changed();
        try{const value=validateAI(await api('/api/ai-setup/'+operation,{method:'POST',body:JSON.stringify(payload)}));
          if(revision!==aiRevision)return;this.ai=value;
        }catch(error){if(revision===aiRevision)this.aiError=error;}
        finally{this.aiBusy=false;changed();}
      },
      async readQueue(changed=()=>{}) {
        if(this.queueReading || this.queueBusy)return;
        const revision=++queueRevision;this.queueReading=true;changed();
        try{const value=validateQueue(await api('/api/selection-workflow'));if(revision!==queueRevision)return;
          this.queue=value;this.queueError=null;this.queueUncertain=false;
        }catch(error){if(revision===queueRevision)this.queueError=error;}
        finally{if(revision===queueRevision){this.queueReading=false;changed();}}
      },
      async changeQueue(operation,payload={},changed=()=>{}) {
        if(this.queueBusy || this.queueUncertain || !['start','freeze','import'].includes(operation))return;
        if(operation==='start' && this.queue?.active)return;
        const revision=++queueRevision;this.queueBusy=true;this.queueReading=false;this.queueError=null;changed();
        try{const value=validateQueue(await api('/api/selection-workflow/'+operation,{method:'POST',body:JSON.stringify(payload)}));
          if(revision===queueRevision)this.queue=value;
        }catch(error){if(revision===queueRevision){this.queueError=error;this.queueUncertain=error?.name==='TypeError' || error?.message==='setup_invalid_response';}}
        finally{if(revision===queueRevision){this.queueBusy=false;changed();}}
      },
      async select(id,selected,changed=()=>{}) {
        const item=this.queue?.items.find(item=>item.id===id);
        if(this.queueBusy || this.queueUncertain || !validId(id) || !item?.frozen)return;
        this.queueBusy=true;this.queueError=null;changed();
        try{const value=await api('/api/selection-workflow/select',{method:'POST',body:JSON.stringify({id})});
          if(value?.item?.id!==id || !value.item.frozen)throw new Error('setup_invalid_response');
          selected(value.item);
        }catch(error){this.queueError=error;}
        finally{this.queueBusy=false;changed();}
      }
    };
  }
  function mount({container,i18n,api,getProfiles=()=>[],importWizard,clipboard}) {
    const doc=container.ownerDocument,model=createModel(api),t=(source,params)=>i18n.t(source,params),localized=[];
    let aiTimer=null,queueTimer=null,signature=null,disposed=false;
    const element=(tag,text='',className='')=>{const node=doc.createElement(tag);node.textContent=String(text??'');if(className)node.className=className;return node;};
    const copy=(tag,source,className='')=>{const node=element(tag,t(source),className);localized.push({node,source});return node;};
    const button=(source,action,style='secondary')=>{const node=copy('button',source,style);node.type='button';node.onclick=action;return node;};
    const field=(id,label,tag='select')=>{const wrapper=element('div','','field'),caption=copy('label',label),input=element(tag);input.id=id;caption.htmlFor=id;wrapper.append(caption,input);return {wrapper,input};};
    const option=(select,value,label)=>{const node=element('option',label);node.value=value;select.append(node);};
    const heading=copy('h2','第一次使用，从这里开始');heading.id='setup-title';container.append(heading,
      copy('p','先检查本机内容生成工具，再采集商品并生成预览。保存连接档案只表示配置已保存，不代表安装、登录、网络或额度已验证。','setup-intro'));
    const aiSection=element('section','','setup-section');aiSection.append(copy('h3','1. 选择内容生成工具'));
    const grid=element('div','','setup-controls'),provider=field('setup-provider','内容生成方式'),profile=field('setup-profile','已保存的 AI 连接');
    for(const [value,label] of [['codex','Codex'],['claude','Claude'],['deterministic',t('本机模板（无需 AI）')]])option(provider.input,value,label);
    grid.append(provider.wrapper,profile.wrapper);aiSection.append(grid);
    const template=copy('p','本机模板可以直接使用，不需要 AI 账号或额度。生成后仍需审核商品文案。','warning');template.hidden=true;aiSection.append(template);
    const aiDetails=element('div');
    const status=element('p','','setup-status');status.id='setup-ai-status';status.setAttribute('role','status');aiDetails.append(status);
    const detail=element('p','','hint');detail.id='setup-ai-detail';aiDetails.append(detail);
    const issue=element('p','','pricing-error');issue.id='setup-ai-error';issue.hidden=true;issue.setAttribute('role','alert');aiDetails.append(issue);
    const actions=element('div','','setup-actions');
    const check=button('检查安装与登录',()=>model.runAI('check',render),'primary');check.id='setup-check';
    const login=button('打开官方登录',()=>model.runAI('login',render));login.id='setup-login';
    const refresh=button('刷新检查状态',()=>model.readAI(render));
    const install=copy('a','官方安装说明');install.target='_blank';install.rel='noopener noreferrer';install.hidden=true;
    const loginGuide=copy('a','官方登录说明');loginGuide.target='_blank';loginGuide.rel='noopener noreferrer';loginGuide.hidden=true;
    actions.append(check,login,refresh,install,loginGuide);aiDetails.append(actions);
    const command=element('p','','setup-command');command.id='setup-login-command';command.hidden=true;aiDetails.append(command);
    const small=element('div','','setup-small-test');small.append(copy('h4','可选：运行一次小型 AI 测试'),
      copy('p','使用内置合成商品，不读取店铺商品，也不会创建草稿。真实调用所选 AI，可能消耗订阅额度或产生提供方费用。登录成功不等于额度可用；测试通过也只说明这一次请求成功。','hint'));
    const usageLabel=element('label','','check'),usage=element('input');usage.type='checkbox';usage.id='setup-confirm-usage';
    usage.onchange=()=>{model.usageConfirmed=usage.checked;renderControls();};usageLabel.append(usage,copy('span','我了解测试可能消耗额度，主动授权这一次测试。'));
    const test=button('运行小型 AI 测试',()=>model.runAI('test',render));test.id='setup-test';small.append(usageLabel,test);aiDetails.append(small);aiSection.append(aiDetails);container.append(aiSection);
    const inbox=element('section','','setup-section');inbox.id='selection-inbox';inbox.append(copy('h3','2. 从浏览器选择商品'),
      copy('p','先开始采集，再将配对码粘贴到商品页面上的 CatalogFlow 采集按钮中。只记录你主动选择的商品链接和标题；结束采集并确认后，才能送入搬运向导。','setup-intro'));
    const queueStatus=element('p','','setup-status');queueStatus.id='setup-queue-status';queueStatus.setAttribute('role','status');inbox.append(queueStatus);
    const queueError=element('p','','pricing-error');queueError.id='setup-queue-error';queueError.hidden=true;queueError.setAttribute('role','alert');inbox.append(queueError);
    const queueWarnings=element('p','','warning');queueWarnings.id='setup-queue-warnings';queueWarnings.hidden=true;inbox.append(queueWarnings);
    const queueActions=element('div','','setup-actions'),start=button('开始采集',()=>model.changeQueue('start',{},render),'primary');start.id='setup-start';
    const freeze=button('结束采集并确认',()=>model.changeQueue('freeze',{queue_id:model.queue?.active?.queue_id},render));freeze.id='setup-freeze';
    const queueRefresh=button('刷新商品列表',()=>model.readQueue(render));queueActions.append(start,freeze,queueRefresh);inbox.append(queueActions);
    const pairing=element('div','','setup-pairing');pairing.id='setup-pairing';pairing.hidden=true;
    const pairField=field('setup-pairing-code','采集配对码（仅供这次采集使用）','textarea');pairField.input.readOnly=true;pairField.input.spellcheck=false;pairing.append(pairField.wrapper);
    const pairingActions=element('div','','setup-actions'),pairCopy=button('复制配对码',async()=>{
      try{await (clipboard || root.navigator?.clipboard).writeText(pairField.input.value);pairHint.textContent=t('配对码已复制。请在商品页的采集按钮中粘贴一次。');}
      catch(_){pairField.input.focus();pairField.input.select();pairHint.textContent=t('已选中配对码，请按 Ctrl+C 复制。');}
    });pairCopy.id='setup-copy-pairing';
    const script=copy('a','安装 / 更新采集脚本');script.id='setup-script';script.target='_blank';script.rel='noopener noreferrer';pairingActions.append(pairCopy,script);pairing.append(pairingActions);
    const pairHint=copy('p','配对码只用于当前本机采集器，不是店铺或 AI 密钥。结束采集后失效。','hint');pairing.append(pairHint);
    const instructions=element('ol','','setup-instructions');
    for(const text of ['浏览器需要支持用户脚本的扩展。已有扩展时，点击安装 / 更新采集脚本并确认安装。',
      '打开 CJ 或 Alibaba 商品详情页，点击 CatalogFlow 采集按钮，首次粘贴配对码。',
      '每次点击只加入当前商品。回到这里核对列表，然后点击结束采集并确认。'])instructions.append(copy('li',text));
    const managerGuide=copy('a','用户脚本扩展安装说明（Tampermonkey）');managerGuide.href='https://www.tampermonkey.net/';managerGuide.target='_blank';managerGuide.rel='noopener noreferrer';pairing.append(managerGuide);
    pairing.append(instructions);inbox.append(pairing);
    const empty=copy('p','还没有采集商品。也可以直接在下方粘贴 CJ 链接，或手动填写商品资料。','hint');inbox.append(empty);
    const list=element('div','','setup-items');list.id='setup-items';inbox.append(list);
    const legacy=element('details');legacy.append(copy('summary','已有采集队列文件？'));const upload=field('setup-queue-file','导入采集队列 JSON（最多 48 KiB）','input');upload.input.type='file';upload.input.accept='.json,application/json';
    upload.input.onchange=async()=>{const file=upload.input.files?.[0];if(!file)return;
      try{if(file.size>49152)throw new Error('setup_queue_too_large');const value=parseQueue(await file.text());if(upload.input.files?.[0]!==file)return;await model.changeQueue('import',{queue:value},render);}
      catch(error){model.queueError=error;render();}};
    legacy.append(upload.wrapper,copy('p','导入后会固定这份队列供审核，不会自动读取供应商 API、调用 AI 或创建商品。','hint'));inbox.append(legacy);container.append(inbox);
    function syncSelection() {
      if(importWizard?.selectGenerator(provider.input.value,profile.input.value || null)===false){provider.input.value=model.provider;refreshProfiles(true);profile.input.value=model.profileId || '';render();return;}
      model.choose(provider.input.value,profile.input.value || null);render();
    }
    provider.input.onchange=()=>{refreshProfiles(true);syncSelection();};profile.input.onchange=syncSelection;
    function refreshProfiles(force=false) {
      const profiles=getProfiles(),key=JSON.stringify([model.provider,profiles.map(value=>[value.id,value.provider,value.label])]);
      if(!force && signature===key)return;signature=key;
      const previous=profile.input.value,preferred=model.provider===provider.input.value?model.profileId:previous;profile.input.replaceChildren();option(profile.input,'',t('使用本机 CLI 默认设置'));
      for(const entry of profiles.filter(value=>value.provider===provider.input.value))option(profile.input,entry.id,entry.label);
      if([...profile.input.options].some(value=>value.value===preferred))profile.input.value=preferred;
      else if([...profile.input.options].some(value=>value.value===previous))profile.input.value=previous;
      if(model.profileId && profile.input.value!==model.profileId)model.choose(provider.input.value,profile.input.value || null);
    }
    function renderControls() {
      const busy=model.aiBusy || model.ai?.busy,importBusy=importWizard?.processing();
      importWizard?.setExternalBusy(busy);
      provider.input.disabled=busy || importBusy;profile.input.disabled=busy || importBusy;check.disabled=busy || importBusy;login.disabled=busy || importBusy;refresh.disabled=model.aiReading || busy;
      usage.checked=model.usageConfirmed;usage.disabled=busy || importBusy;test.disabled=busy || importBusy || !model.usageConfirmed;
      start.disabled=model.queueBusy || model.queueUncertain || Boolean(model.queue?.active);
      freeze.disabled=model.queueBusy || model.queueUncertain || !model.queue?.active;
      queueRefresh.disabled=model.queueBusy || model.queueReading;upload.input.disabled=model.queueBusy || model.queueUncertain;
      for(const use of list.querySelectorAll('[data-item-select]'))use.disabled=use.dataset.frozen!=='true' || model.queueBusy || model.queueUncertain || importBusy;
    }
    function render() {
      if(disposed)return;refreshProfiles();renderControls();
      const templateSelected=model.provider==='deterministic';template.hidden=!templateSelected;aiDetails.hidden=templateSelected;profile.wrapper.hidden=templateSelected;
      status.textContent=t(statusLabels[model.ai?.status] || statusLabels.idle);
      detail.textContent=model.ai?.code?diagnostic(model.ai.code,i18n):t('检查安装与登录不会运行商品生成，也不验证可用额度。');
      detail.hidden=detail.textContent===status.textContent;
      issue.hidden=!model.aiError;issue.textContent=model.aiError?diagnostic(model.aiError,i18n):'';
      const guidance=model.ai?.guidance && Object.keys(model.ai.guidance).length?model.ai.guidance:officialGuidance[model.provider] || {},installURL=officialLink(guidance.install_url),loginURL=officialLink(guidance.login_url);
      install.hidden=!installURL;if(installURL)install.href=installURL;
      loginGuide.hidden=!loginURL;if(loginURL)loginGuide.href=loginURL;
      command.hidden=model.ai?.status!=='manual_login_required';command.textContent=command.hidden?'':t('请在 {shell} 运行：{command}',{
        shell:guidance.login_shell==='PowerShell'?'PowerShell':t('终端'),command:typeof guidance.login_command==='string'?guidance.login_command:''});
      queueError.hidden=!model.queueError;queueError.textContent=model.queueError?diagnostic(model.queueError,i18n):'';
      const warnings=Array.isArray(model.queue?.warnings)?model.queue.warnings:[];
      queueWarnings.hidden=warnings.length===0;queueWarnings.textContent=warnings.map(code=>diagnostic(code,i18n)).join('\n');
      const active=model.queue?.active,items=model.queue?.items || [];
      const counts=selectionCounts(model.queue);
      queueStatus.textContent=t(active?'正在采集 · 已收到 {count} 个商品':'已保存 {count} 个采集商品',{count:active?counts.current:counts.total});
      pairing.hidden=!active;pairField.input.value=active?.pairing_code || '';
      const endpoint=active?collectorEndpoint(active.endpoint):null;script.hidden=!endpoint;if(endpoint)script.href=endpoint+'/collector.user.js';
      empty.hidden=items.length>0;list.replaceChildren();
      const itemButton=(source,action)=>{const value=element('button',t(source),'secondary');value.type='button';value.onclick=action;return value;};
      for(const item of items) {
        if(!object(item) || !validId(item.id))continue;
        const card=element('article','','setup-item'),title=element('h4',item.title || t('未记录标题'));card.append(title);
        const url=root.CatalogFlowImport?.safeLink(item.url),link=element(url?'a':'p',item.url || '');
        if(url){link.href=url;link.target='_blank';link.rel='noopener noreferrer';}card.append(link);
        if(item.selected_at)card.append(element('p',t('采集时间：{time}',{time:root.CatalogFlowHistory?.formatTimestamp(item.selected_at,i18n.locale) || '—'}),'hint'));
        card.append(element('p',t(item.frozen?'已确认，可选择商品':'采集尚未结束，暂不能使用'),'hint'));
        if(item.source!=='cj')card.append(element('p',t('Alibaba 目前需要你手动补充已获授权的商品事实、成本和图片，尚无官方 API 自动搬运。'),'hint'));
        const use=itemButton(item.source==='cj'?'填入搬运向导':'手动补充商品资料',()=>model.select(item.id,selected=>{
          importWizard?.selectSourceItem(selected);doc.getElementById('import-title')?.scrollIntoView({behavior:'smooth'});
        },render));use.dataset.itemSelect=item.id;use.dataset.frozen=String(item.frozen);use.disabled=!item.frozen || model.queueBusy || model.queueUncertain || importWizard?.processing();card.append(use);
        if(!item.frozen && !active){const confirm=itemButton('确认这份未完成队列',()=>model.changeQueue('freeze',{queue_id:item.queue_id},render));confirm.disabled=model.queueBusy || model.queueUncertain;card.append(confirm);}
        list.append(card);
      }
      clearTimeout(aiTimer);clearTimeout(queueTimer);
      if(model.ai?.busy)aiTimer=setTimeout(()=>model.readAI(render),1500);
      if(active || model.queueUncertain)queueTimer=setTimeout(()=>model.readQueue(render),1500);
    }
    function localize(){for(const {node,source} of localized)if(node.isConnected)node.textContent=t(source);provider.input.options[2].textContent=t('本机模板（无需 AI）');refreshProfiles(true);render();}
    function reflectGenerator(generator,profileId){provider.input.value=generator;model.choose(generator,profileId);refreshProfiles(true);profile.input.value=profileId || '';render();}
    importWizard?.onGeneratorChange(reflectGenerator);
    model.readAI(render);model.readQueue(render);
    return {model,localize,refreshProfiles,refreshControls:renderControls,reflectGenerator,invalidateAI:()=>{model.invalidateAI();render();},processing:()=>model.aiBusy || model.ai?.busy || model.queueBusy,
      dispose:()=>{disposed=true;clearTimeout(aiTimer);clearTimeout(queueTimer);}};
  }
  const exported={statusLabels,diagnostics,officialLink,collectorEndpoint,aiPayload,validateAI,validateQueue,parseQueue,selectionCounts,createModel,mount};
  if(typeof module!=='undefined' && module.exports)module.exports=exported;else root.CatalogFlowSetup=exported;
})(globalThis);
