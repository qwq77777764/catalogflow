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
2. Open a normal terminal and run `codex login`.
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
2. Open a normal terminal and run `claude auth login`.
3. Complete the supported Anthropic/Claude login flow for your own account.
4. Exit the interactive session. CatalogFlow can now reuse that CLI login state.
5. In the CatalogFlow directory, run:

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source alibaba-manual --generator claude
```

CatalogFlow calls Claude in non-interactive print mode with a JSON Schema and `--safe-mode`.
This keeps the CLI's own authentication while disabling automatic customizations. Session hooks
are explicitly disabled, an empty strict MCP configuration is supplied, and session persistence
is disabled. No built-in tool is available for text-only input;
for image input, only `Read` is exposed for the temporary authorized files. MCP tools are denied.
See Anthropic's
[CLI reference](https://code.claude.com/docs/en/cli-usage) and
[programmatic usage guide](https://code.claude.com/docs/en/headless).

`--bare` is not used: Anthropic documents that it bypasses subscription OAuth and the system
keychain. A Claude version without `--safe-mode` must be updated; CatalogFlow does not silently
retry with broader permissions or ask you to supply an API key.

An optional model override can be set for the current shell:

```powershell
$env:CATALOGFLOW_CLAUDE_MODEL = "your-supported-model-name"
```

## 3. Diagnose command discovery

The dashboard's **Check AI setup** action checks the same saved Codex/Claude profile selected in
the import wizard. An empty selection resolves the provider's default saved profile, then PATH,
exactly as preview does. It does not switch to an unrelated command or model from environment
overrides. These actions do not read authentication files or display account email, tokens,
raw command output, or automatically discovered executable paths. Manual login guidance may show
the command value you already saved in the selected profile.

The check runs the selected CLI's fixed `--version` and official authentication-status command:
`codex login status`, or `claude auth status` (JSON is the default; no `--json` flag is needed).
It distinguishes a missing CLI, an unsupported command/version, a known logged-out state, an
unrecognized authentication result, and a signed-in session. Each status command has a ten-second
timeout, bounded output, a temporary working directory, and the same restricted environment as
listing generation. A version number is not proof of login, and login is not proof of remaining
usage or model access. See the official
[Codex commands](https://developers.openai.com/codex/cli/reference/) and
[Claude commands](https://code.claude.com/docs/en/cli-reference).

The separate **Test AI** action requires explicit usage confirmation. It submits one tiny
synthetic ceramic-cup listing through the selected generator, with no images, supplier request,
store connection, or real product facts. This may consume the selected account's AI allowance or
incur charges under its billing arrangement. It runs only on your click, has a sixty-second CLI
timeout, does not retry automatically, and does not save the generated copy. A passing test means
that this one request worked; it cannot promise future quota or account eligibility.

**Log in** opens the official CLI login in a visible console for a native Windows executable.
Finish that login yourself, then click **Check AI setup** again. Opening the console is not a
successful login. Script launchers and other operating systems receive the official command and
manual instructions instead. A custom saved command is used in those instructions too, with
PowerShell quoting on Windows; it does not redirect you to a different global CLI. The displayed
command is never evaluated by CatalogFlow. CatalogFlow does not install software, change subscriptions, log
out another account, copy credentials, or silently complete an authentication flow.

Only one setup job runs at a time. Reading or polling its state never starts another command.
If the selected profile's program/model changes, is removed, or resolves to a different default,
the previous readiness result becomes stale and must be checked again. An already-running job
keeps its original settings and cannot mark the edited connection ready when it finishes.
Close the panel after a running check or test has finished; its shutdown guard prevents an
in-flight test from being abandoned without notice. A login console is user-controlled and may
remain open until you finish or close it.

`--doctor` is read-only. It locates the two commands and asks each installed executable for its
version. It does not submit a product, call a model, verify billing, or consume an AI request.
The first actual generation is therefore the final login and entitlement test.

An installed CLI can still be too old for its configured model. If a run reports
`codex_cli_upgrade_required`, update that CLI using the official installation guide, or select
an already installed compatible executable in the Codex connection's command field. CatalogFlow
does not silently change the model or copy login credentials. On Windows, an older npm `codex.cmd`
can appear before a newer native `codex.exe` on PATH; check both versions before selecting a path.
The Windows EXE clears its bundled DLL search path for external CLI processes and suppresses their
console windows while preserving the existing account login locations.

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
- **Not authenticated:** use the explicit login action or run `codex login` / `claude auth login`
  in a normal terminal, then recheck. CatalogFlow never repairs or copies login tokens.
- **Subscription or quota error:** check usage and account eligibility with the provider. This
  diagnostic is shown only for a recognized provider error; a generic exit code is not treated
  as proof of billing failure.
- **Unknown authentication state:** the CLI's result was unrecognized, timed out, or could not be
  read safely. Recheck after reviewing the official installation/login guide; no success is inferred.
- **Invalid JSON response:** retry once, then keep the failed item for manual review. Do not bypass
  validation.
- **Image rejected:** use an authorized public HTTPS image. Private IPs, localhost, URL credentials,
  unsupported media types, redirects to private networks, and files over the configured bound are
  rejected.
- **No console-script command:** use `python -m catalogflow ...`; it is the portable fallback.
