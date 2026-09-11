# Connect CatalogFlow to a local Codex or Claude CLI

CatalogFlow does not ask for an OpenAI or Anthropic API key. It starts a CLI that is already
installed and signed in on the same computer, sends it a constrained listing task, and validates
the returned JSON.

This is a local command-line integration, not offline inference. The selected CLI may send the
product facts and up to five authorized images to its provider under the user's own account,
subscription, terms, and usage limits.

## 1. Install CatalogFlow

CatalogFlow requires Python 3.11 or newer and Git.

```powershell
git clone https://github.com/qwq77777764/catalogflow.git
cd catalogflow
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

On macOS or Linux, activate the environment with `source .venv/bin/activate`.

## 2A. Connect Codex

1. Install Codex using the [official Codex CLI guide](https://developers.openai.com/codex/cli/).
2. Open a normal terminal and run `codex`.
3. Choose **Sign in with ChatGPT** and finish the provider's login flow.
4. Exit the interactive session. CatalogFlow can now reuse that CLI login state.
5. In the CatalogFlow directory, run:

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source alibaba-manual --generator codex
```

CatalogFlow invokes `codex exec` in read-only, ephemeral mode, requires JSON matching its schema,
and passes only the normalized listing facts plus temporary authorized image files. The supplier
reference and variant costs are intentionally excluded from the AI prompt.

An optional model override can be set for the current shell:

```powershell
$env:CATALOGFLOW_CODEX_MODEL = "your-supported-model-name"
```

Omitting it lets the installed CLI use its configured default.

## 2B. Connect Claude Code

1. Install Claude Code using the [official setup guide](https://code.claude.com/docs/en/setup).
2. Open a normal terminal and run `claude`.
3. Complete the supported Anthropic/Claude login flow for your own account.
4. Exit the interactive session. CatalogFlow can now reuse that CLI login state.
5. In the CatalogFlow directory, run:

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source alibaba-manual --generator claude
```

CatalogFlow calls Claude in non-interactive print mode with a JSON Schema. Session persistence and
automatic project customization are disabled. No built-in tool is available for text-only input;
for image input, only `Read` is exposed for the temporary authorized files. MCP tools are denied.
See Anthropic's
[CLI reference](https://code.claude.com/docs/en/cli-usage) and
[programmatic usage guide](https://code.claude.com/docs/en/headless).

An optional model override can be set for the current shell:

```powershell
$env:CATALOGFLOW_CLAUDE_MODEL = "your-supported-model-name"
```

## 3. Diagnose command discovery

`--doctor` is read-only. It locates the two commands and asks each installed executable for its
version. It does not submit a product, call a model, verify billing, or consume an AI request.
The first actual generation is therefore the final login and entitlement test.

On Windows:

```powershell
where.exe codex
where.exe claude
python -m catalogflow --doctor
```

On macOS or Linux:

```bash
command -v codex
command -v claude
python -m catalogflow --doctor
```

If a command was just installed, close and reopen the terminal so PATH is refreshed. If it is
installed in a non-standard location, set the full executable path:

```powershell
$env:CATALOGFLOW_CODEX_COMMAND = "C:\full\path\to\codex.exe"
$env:CATALOGFLOW_CLAUDE_COMMAND = "C:\full\path\to\claude.exe"
python -m catalogflow --doctor
```

Equivalent bash syntax:

```bash
export CATALOGFLOW_CODEX_COMMAND=/full/path/to/codex
export CATALOGFLOW_CLAUDE_COMMAND=/full/path/to/claude
python -m catalogflow --doctor
```

These values belong in the local environment only. Do not commit machine-specific paths or CLI
authentication files.

## 4. What is and is not shared with the AI provider

CatalogFlow's child process receives a deliberately small environment allowlist for operating
system, locale, proxy, and the CLI's own authentication-state location. Supplier/store variables
such as CJ credentials and WooCommerce secrets are not copied to the child process.

The generated prompt contains normalized product facts and public-facing variant attributes. It
does not contain source IDs, acquisition costs, store credentials, cookies, customer records, or
raw supplier responses. If authorized public image URLs are present, CatalogFlow downloads at most
five bounded images into an automatically deleted temporary directory and supplies those files to
the selected CLI.

Use `--generator deterministic` if no product information should be sent to a model service.

## 5. Common failures

- **Command not found:** reopen the terminal, use `where.exe`/`command -v`, or set the command-path
  override above.
- **Not authenticated or subscription error:** run the relevant CLI interactively and complete its
  official login/account flow. CatalogFlow never repairs or copies login tokens.
- **Invalid JSON response:** retry once, then keep the failed item for manual review. Do not bypass
  validation.
- **Image rejected:** use an authorized public HTTPS image. Private IPs, localhost, URL credentials,
  unsupported media types, redirects to private networks, and files over the configured bound are
  rejected.
- **No console-script command:** use `python -m catalogflow ...`; it is the portable fallback.
