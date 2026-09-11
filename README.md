# CatalogFlow

[![CI](https://github.com/qwq77777764/catalogflow/actions/workflows/ci.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/ci.yml)
[![Secret scan](https://github.com/qwq77777764/catalogflow/actions/workflows/secret-scan.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/secret-scan.yml)
[![CodeQL](https://github.com/qwq77777764/catalogflow/actions/workflows/codeql.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/codeql.yml)

**Turn authorized CJ or Alibaba product facts and images into reviewable,
original WooCommerce listing drafts with a locally installed Codex or Claude Code CLI.**

[中文说明](README.zh-CN.md) · [Connection dashboard](docs/configuration-dashboard.md) ·
[Local AI setup](docs/local-ai.md) ·
[Agent workflow](docs/agent-workflow.md) · [Browser-to-CMD workflow](docs/browser-queue-workflow.md)

CatalogFlow grew out of a working merchant workflow: select a product while logged in to a
supplier site, send its authorized URL and visible facts to a queue on the same computer,
press Enter in the CMD window, let a local AI CLI rewrite the listing from the product facts
and images, review the result, and only then create a hidden store draft.

The public repository is a clean-room extraction. It contains no operator credentials,
supplier-page archives, customer data, production store records, or automatic public
publishing.

## Why it is different

- **No OpenAI or Anthropic API key is required.** CatalogFlow can reuse the login already
  managed by an installed Codex CLI or Claude Code CLI.
- **Visual connection center.** Add a provider, your own profile name, notes, and the required
  fields without editing source code. Secrets go to the operating-system keyring, not Git.
- **Image-aware listing generation.** Up to five operator-authorized public HTTPS product
  images are downloaded into a temporary directory, checked against private-network URLs,
  and supplied to the selected local CLI for analysis.
- **The agent is provider-neutral.** Codex, Claude Code, and the deterministic offline demo
  all return the same validated listing shape.
- **Pricing remains deterministic.** The AI never sees source costs and does not decide final
  prices.
- **Safe by default.** Every run starts as a local preview. A WooCommerce write requires both
  `--draft` and `--yes`, and the adapter can create only `draft + hidden` products.
- **No bulk scraper is included.** Inputs must be owned by the operator, explicitly exported,
  captured from an authorized logged-in session, or obtained through an official API.

## What “local AI” means

CatalogFlow starts the `codex` or `claude` command installed on **your computer**. It does not
read API keys from this repository and does not ask an agent to modify CatalogFlow before the
first run. The CLI itself handles account sign-in and usage.

This is not the same as offline inference: unless you configure a supported local model
provider separately, the chosen CLI sends the supplied product facts and authorized images
to its model service under your account. Do not process images or data you are not allowed to
send.

## Install CatalogFlow

Python 3.11 or newer and Git are required.

```powershell
git clone https://github.com/qwq77777764/catalogflow.git
cd catalogflow
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS/Linux activation is `source .venv/bin/activate`.

## Configure connections visually

```powershell
python -m catalogflow configure
```

The browser panel runs only on `127.0.0.1`. Choose WooCommerce, CJ, Alibaba/1688, Zendrop,
Codex, or Claude; give the connection a name and note; then enter the corresponding fields.
Non-secret metadata stays in the user's configuration directory and secrets go to Windows
Credential Manager, macOS Keychain, or the available Linux keyring. Existing secrets are never
returned to the page.

WooCommerce, Codex, and Claude profiles can be used now. Supplier API profiles are clearly marked
as reserved for their planned adapters. See
[docs/configuration-dashboard.md](docs/configuration-dashboard.md) for storage details, profile
selection, and failure behavior.

## Connect Codex or Claude Code without an API key

Choose **one** provider. You do not need both.

### Option A — Codex CLI

Install Codex using the [official Codex CLI guide](https://developers.openai.com/codex/cli/),
then run `codex` once and choose **Sign in with ChatGPT**. Exit after sign-in; CatalogFlow will
call `codex exec` itself.

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source cj --generator codex
```

### Option B — Claude Code CLI

Install Claude Code using the
[official setup guide](https://code.claude.com/docs/en/setup), then run `claude` once and sign
in with a supported Claude/Anthropic account. CatalogFlow uses Claude's non-interactive,
schema-validated print mode and disables shell, edit, write, and web tools.

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source cj --generator claude
```

`--doctor` only runs `--version`; it makes no model request. If a command is installed outside
`PATH`, set `CATALOGFLOW_CODEX_COMMAND` or `CATALOGFLOW_CLAUDE_COMMAND` to that executable's
full path. See [docs/local-ai.md](docs/local-ai.md) for Windows, macOS, Linux, authentication,
PATH, privacy, and troubleshooting details.

## Prepare an authorized product input

CatalogFlow currently consumes normalized JSON. Use a manual export, your own authorized
browser collector, or an official supplier API. Never put cookies or credentials in this file.

```json
{
  "source_id": "your-local-reference",
  "title": "Product title visible to you",
  "currency": "USD",
  "variants": [
    {
      "sku": "YOUR-SKU",
      "cost": 8.5,
      "attributes": {"finish": "walnut"}
    }
  ],
  "images": ["https://public-image-host.example/authorized-image.jpg"],
  "facts": {"material": "verified material", "power": "verified power source"}
}
```

Run a local preview:

```powershell
python -m catalogflow product.json --source cj --generator codex
# or
python -m catalogflow product.json --source alibaba-manual --generator claude
```

The result is written to `output/preview.json`, which is ignored by Git.

## The CJ/Alibaba browser-to-CMD workflow

The operator workflow behind CatalogFlow uses three replaceable parts:

```text
logged-in CJ/Alibaba page
        │ click “Add to local queue”
        ▼
127.0.0.1 browser collector → local queue → press Enter in CMD
                                              │
                                              ▼
                           Codex CLI / Claude Code CLI
                                              │
                                              ▼
                        validate → preview → hidden draft
```

The old private userscript and Python controller are **not copied into this repository**:
they mixed site-specific DOM selectors, local automation, production configuration, and store
writes. [docs/browser-queue-workflow.md](docs/browser-queue-workflow.md) documents the proven
interaction and the security requirements for the clean public replacement. Until that
replacement ships, use normalized JSON rather than copying the private script.

## Which APIs are optional?

| Connection | Required for a local preview? | Rule |
|---|---:|---|
| OpenAI API key | No | Use an already signed-in Codex CLI. Never paste a key into this repo. |
| Anthropic API key | No | Use an already signed-in Claude Code CLI. Never paste a key into this repo. |
| CJ API | No for manual input; useful for exact variants/inventory/shipping | Apply through your own legitimate CJ account and follow CJ's current terms. |
| Alibaba/1688 API | No for manual input; useful for structured catalog data | Apply through your own legitimate Alibaba/1688 account or approved provider and follow its terms. |
| WooCommerce REST API | No for previews; yes for hidden-draft writes | Create least-privilege credentials in your own store and keep them in local environment variables. |

CatalogFlow does not distribute, broker, share, or help bypass access to supplier APIs. API
approval, account eligibility, data rights, quotas, and fees belong to each user and provider.

## Optional hidden-draft write

Set the three `WOOCOMMERCE_*` variables shown in `.env.example` in your local environment,
review the preview, and then explicitly acknowledge the write:

```powershell
python -m catalogflow product.json --source cj --generator codex --draft --yes
```

This interface cannot publish publicly. Public publication remains a separate manual action in
the store administrator.

## Agent contract

The reusable listing and image-analysis rules are published in
[docs/agent-workflow.md](docs/agent-workflow.md). The short version:

1. accept only authorized product facts and images;
2. never invent dimensions, material, certification, or safety claims;
3. produce original, brand-neutral English copy in the JSON schema;
4. keep supplier names, source URLs, IDs, costs, and credentials out of public copy;
5. calculate prices locally after generation;
6. stop at preview unless a human explicitly requests a hidden draft.

Repository-level instructions for Codex and Claude contributors are in [AGENTS.md](AGENTS.md).

## Security and contributing

Read [SECURITY.md](SECURITY.md) before adding providers or browser helpers. Never open a public
issue containing a token, store URL, customer record, raw supplier response, or production log.
Small, testable contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) and
[ROADMAP.md](ROADMAP.md).

## License

[MIT](LICENSE)
