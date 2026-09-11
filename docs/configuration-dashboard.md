# Visual connection dashboard

CatalogFlow includes a loopback-only connection center so users can configure supported services
without editing Python files or placing secrets in a Git checkout.

## Start the dashboard

After installing CatalogFlow, run:

```powershell
catalogflow configure
```

If the console-script directory is not in PATH, use the portable form:

```powershell
python -m catalogflow configure
```

CatalogFlow chooses an available local port, opens the default browser, and prints a one-time URL.
The server binds only to `127.0.0.1`. Close it with the page's stop button or `Ctrl+C`.

Useful options:

```powershell
python -m catalogflow configure --no-browser
python -m catalogflow configure --port 8765
```

## What a connection profile contains

Each profile has:

- a provider/channel;
- a unique human-readable name;
- an optional note describing the account, store, application, or purpose;
- non-secret settings such as a store URL or optional CLI path;
- secret fields appropriate to that provider;
- an optional `default` marker for that provider.

Notes must never contain a password, token, cookie, recovery code, or customer information.

The dashboard never returns a stored secret to the browser. It shows only which secret fields are
configured. While editing, a blank secret field keeps the existing value. Deleting a profile also
deletes its corresponding keyring entries.

## Where values are stored

Non-secret profile metadata is stored outside the repository:

- Windows: `%APPDATA%\CatalogFlow\profiles.json`
- macOS/Linux: `$XDG_CONFIG_HOME/catalogflow/profiles.json` or
  `~/.config/catalogflow/profiles.json`

The file contains labels, notes, provider IDs, and non-secret settings only. Secret values are sent
to the operating-system credential backend through Python Keyring: Windows Credential Manager,
macOS Keychain, or an available Linux Secret Service/keyring. CatalogFlow does not create a fallback
plaintext secret file. If no supported credential backend is available, saving secrets fails closed.

For isolated tests, `CATALOGFLOW_CONFIG_DIR` may point metadata to another directory. It does not
change where the operating system stores secrets.

## Current provider status

| Provider | Dashboard profile | Runtime connector |
| --- | --- | --- |
| WooCommerce | Available | Available; hidden drafts only |
| Codex CLI | Available | Available; reuses the CLI login |
| Claude Code CLI | Available | Available; reuses the CLI login |
| CJdropshipping API | Available to reserve credentials | Planned |
| Alibaba/1688 Open Platform | Available to reserve credentials | Planned |
| Zendrop API | Available to reserve credentials | Planned |

The dashboard labels planned connectors clearly. Saving a credential does not pretend that an
unfinished supplier adapter can already make requests.

## Use a profile

Marking a Codex, Claude, or WooCommerce profile as default lets the matching command load it
automatically. A specific profile can also be selected by its unique label or ID:

```powershell
python -m catalogflow product.json --source cj --generator codex --ai-profile "My Codex"

python -m catalogflow product.json --source cj --generator codex --draft --yes --store-profile "US WooCommerce"
```

Profile values are loaded only into the short-lived CatalogFlow process. The existing AI child
process allowlist still prevents supplier and WooCommerce credentials from reaching Codex or Claude.

## Relationship to the Alibaba selection button

The historical Alibaba workflow used two separate pieces:

1. a Tampermonkey userscript displayed the product-page selection button and sent authorized facts
   to a loopback URL;
2. a Python process received the item, managed the queue, and waited for Enter in CMD.

The configuration dashboard replaces neither piece yet. It is the secure place where future queue
ports, allowed channels, and provider profiles will be managed. The hardened public collector and
receiver remain a separately tracked implementation described in
[browser-queue-workflow.md](browser-queue-workflow.md).
