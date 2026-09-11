# CatalogFlow 中文说明

**把你有权使用的 CJ 或 Alibaba/1688 商品资料和图片，交给本机已登录的 Codex 或
Claude Code，生成可审核的原创 WooCommerce 商品草稿。**

[English README](README.md) · [可视化连接面板](docs/configuration-dashboard.md) ·
[本地 AI 接入](docs/local-ai.md) ·
[Agent 工作流](docs/agent-workflow.md) · [浏览器到 CMD 队列](docs/browser-queue-workflow.md)

这个项目来自一套真实使用过的半自动流程：在已经登录的供应商网页挑选商品，点击
“丢入本地队列”，链接、标题和可见图片进入同一台电脑上的队列；回到 CMD 按 Enter，
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

WooCommerce、Codex 与 Claude 连接档案现在即可使用；CJ、Alibaba/1688 和 Zendrop 会明确
显示“连接器开发中”，不会假装保存后已经能够调用。完整说明见
[docs/configuration-dashboard.md](docs/configuration-dashboard.md)。

CatalogFlow 采用“官方 API 优先”，不是批量爬虫。网页按钮只代表操作者主动选择某个商品；
正式发布的供应商适配器必须使用下载者本人合法申请并获得授权的官方 API 凭据获取资料，
不得遍历站点、绕过登录、验证码、访问控制或限流。没有官方 API 权限时，只接受操作者有权
使用的结构化资料，不会在后台悄悄退化为网页爬取。

## 第二步：连接本机 Codex 或 Claude

二选一即可，不需要两个都装。

### 使用 Codex CLI

按照 [OpenAI 官方 Codex CLI 文档](https://developers.openai.com/codex/cli/)安装；第一次
运行 `codex`，选择 **Sign in with ChatGPT** 完成登录，然后退出。以后 CatalogFlow 会
自己调用 `codex exec`，不需要再把项目交给 Codex 修改一次。

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source cj --generator codex
```

### 使用 Claude Code CLI

按照 [Anthropic 官方安装文档](https://code.claude.com/docs/en/setup)安装；第一次运行
`claude` 并用支持的 Claude/Anthropic 账号登录。CatalogFlow 会使用非交互、JSON Schema
校验模式，同时禁用 shell、编辑、写文件和联网工具。

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source cj --generator claude
```

`--doctor` 只执行版本检查，不会发起 AI 请求。如果 CLI 不在 PATH，可把完整可执行文件
路径放入 `CATALOGFLOW_CODEX_COMMAND` 或 `CATALOGFLOW_CLAUDE_COMMAND`。完整排错见
[docs/local-ai.md](docs/local-ai.md)。

## 第三步：准备商品 JSON

输入必须来自你自己拥有、已获授权、手工导出、登录页面合法采集或官方 API 获得的资料。
商品 JSON 不能包含 Cookie、API Key、账号密码或客户信息。

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
python -m catalogflow product.json --source cj --generator codex
# 或
python -m catalogflow product.json --source alibaba-manual --generator claude
```

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

但旧版油猴脚本和 Python 控制器混有网站 DOM 细节、视觉点击、生产配置和商店写入，不能
直接原样公开。安全版的交互、边界和重建计划见
[docs/browser-queue-workflow.md](docs/browser-queue-workflow.md)。公开接收器完成前，下载者
应先使用规范化 JSON，不能复制私人旧脚本。

## CJ、Alibaba/1688 与 WooCommerce API

需要分清两类接口：

- **AI API：不需要。** 已登录的 Codex CLI 或 Claude Code CLI 可以直接工作；CatalogFlow
  不索取 OpenAI/Anthropic API Key。
- **CJ API：手工输入时不需要。** 如果要稳定读取完整变体、库存或运费，应由使用者用
  自己的合法 CJ 账号申请官方权限，并遵守 CJ 当时的条款、配额和收费。
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
