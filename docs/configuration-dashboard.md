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
| WooCommerce REST API | Available | Available; hidden drafts only |
| WordPress WP-CLI over SSH | Available to reserve settings | Planned advanced fallback |
| Shopify Admin API | Available to reserve settings | Planned GraphQL adapter |
| Codex CLI | Available | Available; reuses the CLI login |
| Claude Code CLI | Available | Available; reuses the CLI login |
| CJdropshipping API | Available to reserve credentials | Planned |
| Alibaba/1688 Open Platform | Available to reserve credentials | Planned |
| Zendrop API | Available to reserve credentials | Planned |

The dashboard labels planned connectors clearly. Saving a credential does not pretend that an
unfinished supplier adapter can already make requests.

## Store publishing paths

The current WordPress/WooCommerce publisher is **not WP-CLI**. It uses the WooCommerce REST API v3
over HTTPS with a Consumer Key and Consumer Secret created for a WordPress user. WooCommerce states
that API permissions follow that user's role and capabilities, so a dedicated least-privilege user
is preferable to reusing a full administrator account. See the
[official WooCommerce authentication guide](https://developer.woocommerce.com/docs/apis/rest-api/authentication).

The planned WP-CLI-over-SSH adapter is an advanced recovery or self-hosted deployment path. Its
profile stores only an SSH config alias, remote WordPress path, and optional command name. SSH
passwords and private keys stay in the user's existing SSH agent/config and never enter CatalogFlow.
A restricted SSH user or forced command should be used; root access is unnecessary for routine
product draft creation.

For a Shopify store you control, the planned adapter will use the GraphQL Admin API. Shopify's
current Dev Dashboard flow gives an own-organization server integration a Client ID and Client
Secret; the app exchanges them for a short-lived access token instead of asking the user to paste a
permanent token. Shopify says the token from this client-credentials grant lasts 24 hours. Apps for
other merchants require an installation/OAuth flow and are outside the first adapter's scope. See
[Shopify's authentication overview](https://shopify.dev/docs/apps/build/authentication-authorization)
and [client-credentials guide](https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant).

## Why this exists when suppliers already offer direct push

Supplier-native push normally copies the source title, images, attributes, and description straight
to a store. CatalogFlow inserts a controlled differentiation layer:

1. the operator visibly selects a product;
2. the authorized adapter retrieves facts through the official provider API;
3. a locally installed Codex or Claude CLI creates an original, evidence-bound listing;
4. validation and human review run before an unpublished hidden draft is created.

This is not unattended magic: the local AI CLI must already be signed in and have sufficient usage
available. If generation fails or quota is exhausted, CatalogFlow must stop with an explicit error;
it must never silently publish the supplier's original duplicate content.

CatalogFlow is official-API-first, not a bulk crawler. A future browser selector may submit a chosen
product identifier or URL, but it must not enumerate a marketplace, bypass authentication, CAPTCHA,
access controls, or rate limits. Without authorized official API access, the accepted fallback is
operator-supplied structured data.

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

The configuration dashboard replaces neither piece. The hardened selector and receiver now ship as
the separate `catalogflow collect` command, while the dashboard manages provider and store profiles.
This separation prevents a page helper from ever receiving store or supplier API credentials. See
[browser-queue-workflow.md](browser-queue-workflow.md).
