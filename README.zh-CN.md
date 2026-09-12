# CatalogFlow 中文说明

**把你有权使用的 CJ 或 Alibaba/1688 商品资料和图片，交给本机已登录的 Codex 或
Claude Code，生成可审核的原创 WooCommerce 商品草稿。**

[English README](README.md) · [可视化连接面板](docs/configuration-dashboard.md) ·
[本地 AI 接入](docs/local-ai.md) ·
[Agent 工作流](docs/agent-workflow.md) · [浏览器到 CMD 队列](docs/browser-queue-workflow.md)

这个项目来自一套真实使用过的半自动流程：在已经登录的供应商网页挑选商品，点击
“丢入本地队列”，商品链接和页面标题进入同一台电脑上的队列；回到 CMD 按 Enter，
本地 Codex 或 Claude Code 根据已核实事实和图片重写 listing；人工检查后，最多只创建
隐藏草稿。

公开仓库是重新整理的干净版本，不包含任何私人 API、账号、Cookie、服务器地址、商店
数据、客户数据、供应商页面存档或自动公开发布代码。

## 最大优势

- **AI 不需要单独填写 API Key。** 可以直接复用本机 Codex CLI 或 Claude Code CLI
  自己保存的登录状态。
- **不用编辑代码就能配置渠道。** 可视化面板允许选择渠道、填写自定义名称和备注；
  密钥进入操作系统凭据库，不进入源代码或 Git。
- **不需要先让 Codex/Claude 帮你改项目。** 安装 CatalogFlow 后，用
  `--generator codex` 或 `--generator claude` 即可选择；`--doctor` 会自动检查命令。
- **可以看授权商品图后写 listing。** 最多 5 张公网 HTTPS 图片只下载到临时目录；
  程序会拒绝 localhost、内网地址、带账号密码的 URL 和过大的文件。
- **AI 不决定售价。** 成本不发送给模型，售价由本地固定公式计算。
- **默认不写商店。** 普通运行只生成 `output/preview.json`；同时提供 `--draft --yes`
  才会创建 `draft + hidden` 商品。
- **供应商可替换。** CJ、Alibaba 手工数据、Codex、Claude 和离线演示都使用同一套结构。

“本地 Codex/Claude”表示 CatalogFlow 调用你电脑上的 `codex` 或 `claude` 命令，登录和
用量由对应 CLI 管理。它不等于完全离线：除非你另外配置受支持的本地模型，否则商品
事实与授权图片仍会通过你的账号发送给对应模型服务。

## 第一步：安装 CatalogFlow

需要 Python 3.11+ 和 Git。

```powershell
git clone https://github.com/qwq77777764/catalogflow.git
cd catalogflow
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS/Linux 激活虚拟环境使用：`source .venv/bin/activate`。

## 用可视化面板配置渠道

```powershell
python -m catalogflow configure
```

面板只监听 `127.0.0.1`，并把连接分成“商店发布、供应商来源、本地 AI”三组。商店发布
包括已经可用的 WooCommerce REST API，以及规划中的 WordPress WP-CLI over SSH 和
Shopify Admin API。为连接填写自己看得懂的名称和备注，再填写该渠道对应的字段。备注与非敏感设置
保存在用户配置目录；真正的密钥进入 Windows Credential Manager、macOS Keychain 或
Linux 可用的系统 keyring。已保存密钥只显示“已配置”，不会回显原值。

工具栏的**语言 / Language**选择器可把整个面板切换为 **中文 (CN)** 或 **English (US)**。
首次访问按浏览器语言选择，无匹配偏好时使用英语；浏览器仅为当前本机地址和端口记住语言代码。
切换语言会保留已填数值和未保存修改，核心定价仍以 USD 计算，不会自动保存定价。

WooCommerce、Codex 与 Claude 连接档案现在即可使用；CJ 单商品官方 API adapter 已进入
预览版，Alibaba/1688 和 Zendrop 仍会明确显示“连接器开发中”。完整说明见
[docs/configuration-dashboard.md](docs/configuration-dashboard.md)。

CatalogFlow 采用“官方 API 优先”，不是批量爬虫。网页按钮只代表操作者主动选择某个商品；
正式发布的供应商适配器必须使用下载者本人合法申请并获得授权的官方 API 凭据获取资料，
不得遍历站点、绕过登录、验证码、访问控制或限流。没有官方 API 权限时，只接受操作者有权
使用的结构化资料，不会在后台悄悄退化为网页爬取。

## 可视化选择定价方案

同一个本机面板里有“可视化定价方案”窗口，用相同示例成本并排比较两种确定性方案。
每种结果都会显示售价、费用与预留扣除、预估每件利润和利润率、理论保本价、`.95` 调整额，
以及最低售价或最低成本倍数是否抬高了售价：

- **方案 A：完整利润率（默认）。** 把商品成本、每件运费、可选的用户预估税费/关税、支付费、
  退货预留、运营预留、目标利润率、最低售价和最低商品成本倍数纳入计算，并保留 `.95` 尾数。
- **方案 B：商品成本倍数。** 先算“商品成本 × 倍数”（默认 `3×`，可填写 `1×`–`100×`），
  再加一次运费、可选预估税费/关税和固定支付费；运费和税费不会被悄悄重复放大，同样保留 `.95` 尾数。

方案 B 的售价不使用百分比费用或预留，但预估利润会扣除这些项目；它不会自动达到目标利润率，
倍数过低时可能亏损。这里的预估利润仅覆盖已填写的成本与预留，不是会计净利润。

定价金额都按 **USD/件** 填写。固定支付费按“一件商品一笔订单”估算，尚未分摊多件订单的固定费。
CJ 整段运费报价应先折算每件运费，再填入一次，不要同时重复计入入境运费和尾程运费。
税费/关税由操作者估算，系统不会自动查询税率。

成本试算区底部的汇率换算器可将上方**尾程 / 整段运费**换算为所选货币，同时展示 USD 原值、
目标金额、汇率、来源和参考日期。可使用 Frankfurter 每日参考汇率，也可手动填写汇率；
切换语言会保留所选货币和手动输入。参考汇率不是银行实时成交报价。换算仅供对照，不改变两套
定价方案、商店币种或已保存设置，也不会向汇率服务发送运费金额或密钥。详情见
[汇率换算说明](docs/configuration-dashboard.md#convert-the-last-mile-shipping-example)。

商品成本与运费只用于试算，不会保存。恢复默认或撤销修改只改变表单，必须点击**保存**才会用于
后续 CLI 运行，不会改动已有预览或商店商品。设置保存在与连接档案并列的非秘密 `pricing.json`，
没有该文件时继续使用旧的默认利润率方案。完整公式和试算例子见
[面板配置文档](docs/configuration-dashboard.md#visual-pricing-panel)。

## 第二步：连接本机 Codex 或 Claude

二选一即可，不需要两个都装。

### 使用 Codex CLI

按照 [OpenAI 官方 Codex CLI 文档](https://developers.openai.com/codex/cli/)安装；第一次
运行 `codex`，选择 **Sign in with ChatGPT** 完成登录，然后退出。以后 CatalogFlow 会
自己调用 `codex exec`，不需要再把项目交给 Codex 修改一次。

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source alibaba-manual --generator codex
```

### 使用 Claude Code CLI

按照 [Anthropic 官方安装文档](https://code.claude.com/docs/en/setup)安装；第一次运行
`claude` 并用支持的 Claude/Anthropic 账号登录。CatalogFlow 会使用非交互、JSON Schema
校验模式，同时禁用 shell、编辑、写文件和联网工具。

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source alibaba-manual --generator claude
```

`--doctor` 只执行版本检查，不会发起 AI 请求。如果 CLI 不在 PATH，可把完整可执行文件
路径放入 `CATALOGFLOW_CODEX_COMMAND` 或 `CATALOGFLOW_CLAUDE_COMMAND`。完整排错见
[docs/local-ai.md](docs/local-ai.md)。

## 第三步：准备商品 JSON

输入必须来自你自己拥有或获授权的结构化资料、明确导出文件或本人获准使用的官方 API。
浏览器选品器只排队商品标识/URL，不会凭空补齐商品事实。商品 JSON 不能包含 Cookie、
API Key、账号密码或客户信息。

```json
{
  "source_id": "your-local-reference",
  "title": "页面上可见的商品标题",
  "currency": "USD",
  "variants": [
    {
      "sku": "YOUR-SKU",
      "cost": 8.5,
      "attributes": {"finish": "walnut"}
    }
  ],
  "images": ["https://public-image-host.example/authorized-image.jpg"],
  "facts": {"material": "已经核实的材质", "power": "已经核实的供电方式"}
}
```

生成本地预览：

```powershell
python -m catalogflow product.json --source alibaba-manual --generator claude
```

如果规范化 JSON 标记为 `--source cj`，则每个变体都必须包含完整、供应商无关的
`shipping_quote`；缺少 CJ 运费时会直接拒绝，不会按 `$0` 运费定价。若输入是 CJ 链接或
PID，优先使用下方的官方 CJ 档案流程。

### 用你自己的 CJ API 预览一个商品

先在 `catalogflow configure` 中建立 CJ 档案，填入从你本人 CJ 账号取得的 API Key；然后
明确传入一个 CJ 商品详情链接或 PID：

```powershell
python -m catalogflow "CJ商品链接或PID" --source cj `
  --supplier-profile "我的 CJ" --generator codex
```

预览版 adapter 只在内存中用 API Key 换取 Access Token，调用 CJ 官方单商品详情接口，
并为每个变体调用官方运费试算。档案默认按 `CN` → `US`、数量 `1` 报价，可选填目的地
邮编和精确物流名称；没有指定线路时，会把接口返回的最低有效线路记录进本地预览。
它不会遍历商品目录、持久化 Access Token、记录原始响应，也不会把 CJ 凭据、成本或
运费发送给 Codex/Claude。授权失败、配额不足、无可用线路、数据异常或返回了不同商品
时都会明确停止。详见 [docs/cj-adapter.md](docs/cj-adapter.md)。

## 你记得的“登录 CJ → 点按钮 → CMD 回车”流程

原工作流确实如此：

```text
已登录的 CJ / Alibaba 页面
        │ 点击“丢入本地队列”
        ▼
127.0.0.1 本地接收器 → 队列 → CMD 按 Enter
                                  │
                                  ▼
                         Codex / Claude
                                  │
                                  ▼
                       校验 → 预览 → 隐藏草稿
```

安全重写版的 Alibaba 油猴选品按钮和本机认证接收器已经随 CatalogFlow 提供：

```powershell
python -m catalogflow collect
```

命令会显示本机油猴脚本安装地址、一次性会话令牌和队列文件位置。安装脚本后，在
Alibaba 商品详情页点击 **Add to CatalogFlow**，输入终端显示的接收器地址和令牌；令牌只
保留在当前页面油猴脚本的内存闭包中，不写入扩展存储。选完后回到终端按 Enter 冻结队列。

第一版采集器刻意只发送 `source`、商品详情 URL 和页面标题，不发送整页 HTML、Cookie、
图片、价格、变体或登录信息。当前采集器面向 Alibaba，因此冻结队列尚未连接 CJ adapter。
CJ 预览请把一个 CJ URL/PID 配合 `--supplier-profile` 使用；Alibaba 队列归一化仍需要后续
独立 adapter。规范化 JSON 继续可用。

旧版私人油猴脚本和 Python 控制器没有复制进仓库，因为它们混有脆弱 DOM 选择器、视觉
点击、生产配置和商店写入。新版协议见
[docs/browser-queue-workflow.md](docs/browser-queue-workflow.md)。

## CJ、Alibaba/1688 与 WooCommerce API

需要分清两类接口：

- **AI API：不需要。** 已登录的 Codex CLI 或 Claude Code CLI 可以直接工作；CatalogFlow
  不索取 OpenAI/Anthropic API Key。
- **CJ API：手工输入时不需要，CJ adapter 预览时需要。** 使用者必须用自己的合法 CJ
  账号申请官方权限，并遵守 CJ 当时的条款、积分、配额和收费。
- **Alibaba/1688 API：手工输入时不需要。** 自动读取结构化数据时，必须由使用者通过
  自己的 Alibaba/1688 账号或获批准的服务合法申请。
- **WooCommerce REST API：预览不需要。** 只有创建隐藏草稿时才需要自己商店的最小权限
  凭据，并且只能保存在本机环境变量中。

本项目不提供、转卖、共享或绕过任何供应商 API 权限。

## Agent 工作流

[docs/agent-workflow.md](docs/agent-workflow.md) 已公开去隐私化的规则，包括：授权检查、
事实归一化、图片分析、原创标题/描述/标签、禁用品牌与夸大声明、固定定价、JSON 校验、
本地预览、人工确认和隐藏草稿边界。供 Codex/Claude 维护此仓库时遵循的规则在
[AGENTS.md](AGENTS.md)。

## 安全

不要在 Issue、商品 JSON 或 Git 提交中放入 API Key、Token、Cookie、商店地址、客户
记录、原始供应商响应或生产日志。详见 [SECURITY.md](SECURITY.md)。

许可证：[MIT](LICENSE)。
