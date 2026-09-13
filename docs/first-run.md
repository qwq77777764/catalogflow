# First run: from a selected product to an AI preview

CatalogFlow coordinates a local CLI task. It does not post messages to an existing Codex or
Claude chat and does not require the operator to write a separate prompt.

## 1. Choose how to generate copy

Open the Windows EXE and use **Getting started**. Select a saved Codex/Claude connection, or local CLI
defaults. **Check installation and login** locates the selected program and asks its CLI for
version and sign-in status. Missing, unsupported, signed-out and unknown states have different explanations. Follow
the official installation guide when missing; sign in through the CLI's own flow, then check again.
The app does not install software or copy authentication files. **Open official login** can open
a login console for a supported native Windows CLI executable. Other command formats or platforms
show a command to run yourself and official instructions. Complete any terminal/browser steps,
then click **Check installation and login** again. **Refresh check status** only reads the last
check; it does not run a new login check. Being signed in to a desktop chat app alone does not
establish that this computer's CLI is installed and signed in.

For an optional **Run small AI test**, first check the usage acknowledgment and then click the
test button. It sends only a small synthetic sample and can consume usage or incur provider fees. It
does not read the current product, contact a supplier, or connect to a store. A successful sample
proves that one request worked at that time, not that future quota is guaranteed. Changing the
selected connection, its saved command/model or the resolved default invalidates its displayed
readiness. The test uses the selected generator and model; it does not silently switch providers
or retry a different model. Template generation needs no AI account.

## 2. Bring in a product

- **CJ link:** choose CJ in the import wizard, paste one product detail link/PID, and select your
  own saved CJ official API connection. Create that connection in the configuration panel first
  if it is not in the list. A link alone does not grant API access.
- **Browser selection:** follow the steps below to collect links and review them in the inbox.
- **Manual product:** choose **Manual product form / JSON** and **Fill in a form** in the import
  wizard. Enter a stable product reference and title, verified facts as one `Name: Value` per line,
  and each variant's USD cost and shipping per unit. Confirm the two-letter origin/destination
  country codes. For several variants, give each a distinct name; use advanced JSON for several
  separately named attributes. SKU can be left blank for automatic numbering. Add only authorized
  HTTPS image links, one per line. Leave unknown facts blank; do not enter zero freight unless
  you have confirmed it is zero. This form does not read the linked supplier page.
- **Existing files:** advanced normalized product JSON and bounded legacy selection queue files
  are supported through their separate file inputs. Each uploaded file is limited to 48 KiB.
  Product JSON supplies one normalized product; queue JSON supplies selections and is frozen
  for review when explicitly imported. Neither uploading a file nor filling a form starts AI.

For browser selection, use a browser with a compatible userscript extension on the same computer:

1. In CatalogFlow, click **Start collection**. If needed, use the userscript-extension setup link
   to install an extension yourself, then click **Install / update collector script** and confirm
   installation in that extension. The script is separate from the EXE.
2. Click **Copy pairing code**. Open a product detail page on `www.cjdropshipping.com`,
   `cjdropshipping.com`, or `www.alibaba.com`. Reload an already-open product page after installing
   the script if its button is missing. 1688 pages and search results are not supported.
3. Click **Add to CatalogFlow** on the product page. Inspect and confirm the displayed link and
   title, then paste the complete one-line code when asked. It supplies both the temporary loopback
   address and collection-only token; do not share it or enter the dashboard's token instead.
4. Wait for **Added ✓** or **Already queued**, then return to CatalogFlow to inspect the list.

Pairing survives only in that page's memory. A new tab, a newly loaded product page or a refresh
requires pasting again. Reuse the same code while its collector is active; a new collection uses
a new code. No pairing data is written to extension storage. The request contains only schema
version, source, canonical link and page title—not cookies, HTML, costs, images or login data.

## 3. Finish selecting before processing

Selected links appear in the inbox while collecting. **Finish and confirm collection** stops
accepting new selections and freezes that queue. The command-line collector retains its Enter
confirmation. Closing the application or cancelling collection does not silently approve a queue;
after reopening, click **Confirm this unfinished queue** before using its items. That button
appears when no collection is active; finish the current collection first if necessary.

Choose **Use in import wizard** on one confirmed CJ item, or **Fill in product details** on an
Alibaba item. A CJ item fills the CJ input. Alibaba fills the manual product form
with the selected link/title; supply the missing facts before continuing. This is not an automatic
Alibaba/1688 API adapter. Selecting an item never starts AI or writes a store. There is no automatic
batch import. The saved queue preserves source links and selection timestamps across restarts.

## 4. Generate, inspect, then decide

Choose Codex, Claude or the local template and click **Generate preview**. For CJ, CatalogFlow
fetches official product/freight information. When Codex or Claude is selected, it passes permitted
facts and bounded images to that CLI, which may send them to its model provider under your account;
running the CLI locally does not mean offline inference. Supplier/store credentials and source
costs are not included in that task. The template generates locally without an AI request.
The program validates the generated copy and calculates USD prices locally.

Review the result and editable copy in the same window. No store is needed for preview. An operator
who actually wants store output must choose their own WooCommerce connection before preview and
explicitly confirm a hidden draft after review. Software development and offline acceptance tests
do not require a developer's personal store connection.

Failed operations show a bounded explanation and a next step; errors do not expose raw CLI output
or credentials. Existing import reports retain source links, timestamps and results. See
[visual import](visual-import.md), [local AI](local-ai.md) and [work reports](work-reports.md).

## 中文操作流程

1. **打开 EXE，选择生成方式。** 在“新手开始”选择 Codex/Claude 及已保存连接或本机默认设置，
   点击“检查安装与登录”。调用的是本机 CLI；登录了桌面聊天应用，不代表 CLI 已安装并登录。
   缺少程序时按“官方安装说明”自行安装。点击“打开官方登录”可启动支持的 Windows 原生 CLI 登录窗口，
   其他情况会显示手动命令；按官方终端/浏览器流程完成后，再点“检查安装与登录”。“刷新检查状态”只读取
   上次检查，不重新检查登录。程序不会代装 CLI、代替你登录或复制认证文件。
2. **可选择测试一次 AI。** 先勾选用量确认，再点击“运行小型 AI 测试”。测试使用内置合成资料，可能消耗
   账号额度或产生提供方费用，不使用当前商品、供应商 API 或店铺；沿用选定生成器和模型，不自动切换或重试。
   成功只说明这一次调用成功，不保证以后请求或剩余额度。改变连接、已保存命令/模型或默认连接后须重新检查。
   也可直接选择无需账号的本机模板。
3. **准备商品。** CJ 可在向导粘贴详情链接/PID，并选择自己已保存的 CJ 官方 API 连接；没有连接时先在
   配置面板添加。也可选“手动填写商品 / JSON”→“直接填写表单”：填写稳定商品编号、标题、已核实事实、
   变体、USD 成本与每件运费，核对发货/收货国家代码。事实每行“名称: 内容”，授权 HTTPS 图片每行一条。
   多变体分别取不同名称，SKU 可留空自动编号；多属性变体可使用高级 JSON。未知事实留空，只有确认运费为零
   才填 0。高级商品 JSON 与采集队列文件使用不同入口，各限 48 KiB；导入文件不会自动调用 AI。
4. **需要浏览器选品时，先开始采集再安装脚本。** 点击“开始采集”。浏览器没有兼容的用户脚本扩展时，先按
   页面提供的说明自行安装扩展，再点击“安装 / 更新采集脚本”并在扩展中确认。点击“复制配对码”，到
   `www.cjdropshipping.com`、`cjdropshipping.com` 或 `www.alibaba.com` 的商品详情页点击
   **Add to CatalogFlow**。安装前已打开的商品页可刷新后再找按钮；1688 和搜索结果页不支持。
   核对发送内容并确认，再在提示框粘贴整行配对码，无需分开填写地址和令牌。看到 **Added ✓** 或
   **Already queued** 后回到面板核对列表。
5. **每个新页面都要配对，完成后明确确认队列。** 配对只保存在当前网页内存中，不跨标签页、重新加载页面
   或刷新保留；同一采集器运行期间可复用原配对码，新一轮采集要用新码。配对码仅授权本机采集，不能分享。
   采集只发送协议版本、来源、链接和标题，不发送 Cookie、HTML、成本、图片或登录信息。点击“结束采集并确认”
   后，CJ 选“填入搬运向导”，Alibaba 选“手动补充商品资料”。Alibaba 只预填来源信息，缺少的事实需自行补齐。
   关闭程序不会自动确认；重开后，在没有正在采集的队列时，点击“确认这份未完成队列”即可继续。
   命令行仍用 Enter 冻结队列；冻结和选择商品都不会请求 AI、取供应商资料或写店铺，也没有自动批量导入。
6. **点击生成预览。** CJ 此时才通过使用者自己的官方 API 获取商品及运费；选择 Codex/Claude 时，软件将获授权的
   事实和图片交给对应 CLI，可通过你的账号发送给模型提供方，本机调用不等于离线推理。本机模板则不请求 AI。
   软件接回文案并在本地计算价格。成本、来源编号、供应商及店铺凭据不会发送给 AI。用户不需要另去聊天
   窗口说“我连接好了”。审核与修改在面板完成，预览不需要店铺。Alibaba/1688 自动 API 取数仍未实现。
7. **需要时才创建隐藏草稿。** 使用者自行配置自己的 WooCommerce 连接，在生成预览前选定店铺，审核后勾选确认
   并明确点击创建。确认使用服务器保存的商品、价格和文案，不再次调用 AI 或读取 CJ。结果继续自动记录时间戳、
   原链接和报告。开发及离线验收不要求开发者连接个人店铺；本软件不提供公开发布。
