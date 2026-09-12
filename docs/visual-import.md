# Visual single-product import

The v0.9.0 dashboard connects product input, listing review, and an explicitly confirmed hidden
draft. Open it from **CatalogFlow.exe**, or run `python -m catalogflow configure`. The browser
talks to an authenticated server bound to `127.0.0.1`; opening the application does not start a
supplier request or store write. The toolbar switches between **中文 (CN)** and **English (US)**.

## Before the first preview

Save the connections you intend to use in the dashboard. The wizard selects those saved profiles;
it does not ask for credentials in product JSON or listing text.

| Choice | What is needed |
| --- | --- |
| CJ product URL or PID | Your saved CJ official-API profile, with authorized API access and the intended freight destination/route settings |
| Manual product JSON | One normalized `alibaba-manual` product you are authorized to use; no supplier API required |
| Codex or Claude | Your installed, signed-in CLI and the appropriate saved AI profile or supported local CLI configuration |
| Template generation | No AI account or AI request; deterministic copy still needs your review |
| Preview only | No store connection required |
| Hidden WooCommerce draft | A saved WooCommerce profile selected before preview; consumer key/secret for product writes and WordPress username/application password for image uploads |

Secrets saved through connection profiles remain in the operating-system keyring. A WordPress
application password is separate from both a WooCommerce consumer secret and the account's login
password. Media uploads need a user permitted to upload files and edit the draft. With no images,
the media credential fields can remain empty. See [connection storage](configuration-dashboard.md)
and [image export requirements](work-reports.md#images-and-variants).

Save the pricing plan before generating a preview. Pending pricing edits must be saved or undone
before the wizard will start another preview. Costs, freight, and final selling prices are
**USD per unit**. The pricing panel's sample costs and manual currency converter are comparisons;
they do not become the imported product's costs, shipping, or store currency.

## 1. Select the product and connections

For **CJ**, enter one supported product detail URL or PID and select the saved CJ profile.
CatalogFlow uses CJ's official single-product and freight APIs. A missing quote, permission, or
route produces an error; the wizard does not fall back to scraping. It does not import an entire
catalog or normalize an Alibaba/1688 URL. See [CJ adapter](cj-adapter.md).

For **manual JSON**, choose a local UTF-8 file, with or without a BOM, of at most **48 KiB
(49,152 bytes)**. The top-level value must describe one normalized product, not an array, queue
export, raw webpage, or raw supplier response. The wizard uses source `alibaba-manual` for this
input. Start with [the synthetic example](../examples/synthetic_product.json) and replace its
facts with information you are authorized to use. Never include credentials or customer data.

The normalized product contains `source_id`, `title`, `currency: "USD"`, and `variants`, where
each variant has a distinct `sku`, a numeric `cost`, and optional `attributes`. Optional `facts`,
product `images`, variant `image_url`, and `source_url` retain authorized supporting information.
If freight is supplied, use each variant's normalized `shipping_quote`; a local filename is not
an original product link. The preview shows the actual normalized freight, so check it before
confirming a draft. Image URLs must meet CatalogFlow's bounded public-HTTPS rules.

Choose **Codex**, **Claude**, or **template** generation. Codex and Claude may send authorized
product facts and images to their provider under your CLI account. Costs, supplier IDs, pricing
rules, and credentials remain outside the AI prompt. Template generation makes no AI request;
choosing CJ still requires supplier network access.

Choose a WooCommerce profile now if this preview should be eligible for a hidden draft. A preview
without a store is valid, but cannot later be redirected to a newly selected store. Generate a
new preview with the intended target instead.

## 2. Generate and review the preview

Generation runs in the background. Only one import task runs in a dashboard session at a time.
The server captures the normalized product, generated listing, saved pricing policy, and chosen
store for review. It records the preview through the same report archive used by CLI imports.

Review the following before continuing:

- Original source link, when known, and the product identity you intended to import.
- Each variant's attributes, acquisition cost, freight, and calculated USD selling price.
- Image count and safe links to authorized images; opening a link contacts that image host.
- Listing title, description HTML shown as editable text, category, and tags.

The listing copy fields can be edited. These edits are validated before creating a draft; the
description editor is not an execution surface for supplied HTML. Variant pricing and product
facts are not editable in this review step. To change costs, freight settings, saved pricing, or
the target store, correct the input/settings and generate another preview. The existing snapshot
does not silently change when you save settings elsewhere in the dashboard.

The title is limited to 80 characters, category to 120, and description to 16,000. Tags are
comma- or newline-separated, with at most 20 tags of 80 characters each. Descriptions accept
balanced basic markup such as paragraphs, headings, lists, emphasis, and tables, without HTML
attributes. Scripts, embedded media, links, comments, and styling attributes are rejected. The
listing must still satisfy the same factual and source-disclosure checks after editing. Editing
any field clears the review acknowledgment so you must review the changed copy again.

The conversion panel does not change these USD prices. It is still a separate comparison using
either a dated reference rate or your manually entered rate.

## 3. Confirm a hidden draft

Check the explicit review acknowledgment and click the create-hidden-draft button. Neither
opening the wizard nor generating or editing a preview creates a store product.

Confirmation uses the cached product, selected target, reviewed listing text, and price snapshot.
It does **not** fetch CJ again, call AI again, or recalculate prices. The store boundary retains
the existing image/variant validation, draft reservations, and duplicate protection. Repeated
confirmation clicks cannot start a second concurrent write for the same task.

The only product state CatalogFlow creates is `draft` with `catalog_visibility=hidden`;
variations stay drafts too. Image uploads create WordPress attachments that may have directly
accessible URLs even while their parent product is hidden. An interrupted upload or variation
write may leave an incomplete draft; review its report and store link instead of assuming the
entire operation failed without side effects. There is no public-publish action or force-create
override in this wizard.

Results appear in **Work history**, including timestamped TXT/JSON reports, known source links,
outcomes, and draft IDs/check links when available. A completed duplicate is skipped according to
the existing store-scoped registry. Uncertain prior writes remain blocked until reconciled;
the registry is local to the configuration directory, not a lock shared across computers.
See [Work reports and draft history](work-reports.md).

## Reopening and recovery

Keep the application running during an import. Closing only the browser page does not stop its
server. The launcher's Exit and the dashboard's stop action refuse to stop an active preview or
draft write; wait for the task to finish. Use the launcher's **Open interface** button, or the
original CLI session URL, to reopen
an authenticated page. The wizard can recover the server's current task or unconfirmed preview
while that same session remains alive.

The page removes its token from the address after loading. A normal F5 refresh of that cleaned
address does not guarantee authenticated recovery. Unsaved browser edits are not a persistent
record; after reopening, review the recovered listing again.

Closing the launcher or restarting the server discards unconfirmed previews held in memory.
Written reports persist, but a historical TXT/JSON report cannot be used to resume confirmation.
If a store write was in progress, inspect the report and existing store draft before starting a
new attempt; the durable reservation is designed to block uncertain duplication.

## Current scope

This release supports one CJ API product or one normalized manual JSON product per task.
Alibaba/1688 URL normalization, batch wizard imports, WP-CLI over SSH, Shopify writes, old private
history migration, and cross-restart restoration of unconfirmed previews are not implemented.
The existing command-line interface remains available.

## 中文操作说明

v0.9.0 可在浏览器里完成“选择商品 → 生成并审核 → 确认隐藏草稿”。双击 **CatalogFlow.exe**，
或执行 `python -m catalogflow configure` 打开本机认证页面。界面支持中文 (CN) 与 English (US)。
仅打开程序不会请求供应商商品，也不会写入店铺。

### 导入前准备

先在连接面板保存需要的 CJ、本机 AI 和 WooCommerce 档案，再保存定价设置。向导选择的是这些
已保存档案，不要把密钥写进商品 JSON 或 listing 文案。密钥保存在系统凭据库。

定价有未保存修改时，须先保存或撤销才能开始新的预览。
Codex、Claude 需在当前电脑安装并登录相应 CLI；授权商品事实与图片可能发送给其模型服务，成本、
来源编号、定价规则及凭据不进入 AI 提示词。模板生成不调用 AI，但文案仍需人工审核。
只做预览不需要店铺；CJ 官方 API 方式仍需要自己的 CJ 授权与网络。

### 第一步：选择商品与连接

选择以下一种商品输入：

- **CJ 链接/PID：**输入一个支持的商品详情链接或 PID，选择已保存的 CJ 档案，并核对档案中的
  运费目的地、数量与线路。系统通过官方详情与运费 API 取数；无权限、无报价或无可用线路会报错，
  不会转成网页爬取。
- **授权 JSON：**上传一个规范化商品，来源为 `alibaba-manual`。文件必须为 UTF-8，可带 BOM，
  最大 **48 KiB（49,152 字节）**；不接受商品数组、网页、队列导出或原始供应商响应。可参考
  [公开合成示例](../examples/synthetic_product.json)。应含 `source_id`、`title`、USD 币种与变体的
  唯一 `sku`、数字成本，按需提供属性、已核实事实、授权图片和 `source_url`。运费应使用每个
  变体的规范化 `shipping_quote`，确认时核对预览中的实际金额；本地文件名不会被当作原商品链接。

选择 Codex、Claude 或模板生成。如需审核后创建草稿，必须在生成预览前选好 WooCommerce 档案；
不选店铺可以预览，但不能把这份预览临时改投到另一个店铺，需要重新生成预览。

### 第二步：生成并审核

生成在后台执行，一个面板会话同时只运行一个导入任务。检查原商品链接、图片数量和授权图片链接、
每个变体的属性、成本、运费与 **USD/件售价**。打开图片链接会访问对应图片主机。
可编辑标题、以文本显示的 HTML 描述、分类和标签，写店铺前会校验修改后的文案。
这里不编辑变体价格或事实数据；HTML 编辑框也不会执行提供的 HTML。

标题最多 80 字符，分类最多 120，描述最多 16,000；标签以逗号或换行分隔，最多 20 个，单个最多
80 字符。描述只接受配对完整的基础段落、标题、列表、强调、表格等 HTML，不允许任何 HTML 属性、
脚本、嵌入媒体、链接、注释或样式；修改后仍须通过事实与来源信息校验。编辑任一字段都会取消审核
勾选，需重新确认修改后的内容。

定价来自开始预览时的已保存设置。试算成本、试算运费和手动汇率不会成为该商品的实际成本或改变
USD 售价。系统保留商品、文案、定价与目标店铺快照；之后修改其他设置不会悄悄改变这份预览。
需要变更成本、运费、定价或店铺时，修正输入或设置后重新生成。

### 第三步：确认隐藏草稿

先勾选已完成审核，再点击创建隐藏草稿。确认使用已缓存的商品、已选店铺、审核文案及价格，
不会重新请求 CJ、调用 AI 或重新定价。重复点击不会为同一任务启动第二个并行写入。
生成预览和编辑文案本身都不创建店铺商品。

WooCommerce 商品写入使用 Consumer Key/Secret；上传图片还需同一连接中的 WordPress 用户名与
**应用程序密码**，用户须有媒体上传及对应草稿编辑权限。应用程序密码不是网站登录密码，也不等于
WooCommerce Consumer Secret。无图片时可不填媒体凭据。

商品始终为 `draft + catalog_visibility=hidden`，变体也保持草稿。已上传图片的直接链接可能公开
可访问，即使商品仍隐藏；中断或部分失败可能留下不完整草稿及媒体，需查看报告与店铺检查链接。
界面没有公开发布、强制重建或自动清理已有草稿的操作。

结果共用原有工作记录与防重复机制，TXT/JSON 报告保留具体时间、已知原链接、结果及草稿编号。
已完成的重复导入会跳过，结果不确定的旧写入会阻止直接重建。登记仅属于本机配置目录，不是多台
电脑共享的锁。详见[工作记录与草稿历史](work-reports.md)。

### 关闭页面与恢复

只关闭网页不会停止服务。预览或草稿写入执行中，启动器“退出”与面板“停止”会要求等待任务完成。
程序仍运行时，用启动器“打开界面”或 CLI 最初提供的会话链接重开
认证页面，可恢复当前任务或未确认预览。页面加载后会清除地址里的令牌，普通 F5 不保证恢复认证。
网页里未提交的编辑也不是持久化记录，重开后应重新核对文案。

关闭启动器或重启服务器会丢失内存中的未确认预览；已写入报告继续保留，但不能从历史 TXT/JSON
直接恢复草稿确认。若退出时正在写店铺，先核对报告与已有商品，防重复登记会阻止不确定的重建。

本版尚未实现 Alibaba/1688 网页链接自动归一化、批量向导、SSH/Shopify 写店铺、旧私人历史迁移、
未确认预览跨重启恢复；原命令行接口仍可使用。
