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

For a fresh page load or reopening the panel, use the original session URL printed by the CLI while
that server is running. A bare local address omits session authentication; restarting the command
creates a new session URL.

## Choose the interface language

The visible toolbar provides **中文 (CN)** (`zh-CN`) and **English (US)** (`en-US`). On the first
visit, the panel follows the browser language and falls back to English when neither language is
preferred. Browser `localStorage` stores only the selected language code for that local address and
port; a new random port does not share the saved preference.

Switching updates labels, provider fields, formulas, validation messages, dynamic status messages,
and USD/percentage display formats using dictionaries bundled with CatalogFlow. No AI call or
external translation service is required. Language selection leaves core pricing in USD; the
separate shipping converter below provides an optional currency comparison.

Entered costs, rates, connection names, notes, drafts, and secret fields are preserved. User-written
names and notes remain in their original language. Switching languages does not save pricing or
change which settings apply to later CLI runs.

Developers can run the bundled dashboard checks with `node --test tests/dashboard-*.test.cjs`
(Node.js 22, no npm dependencies). CI runs them alongside the Python tests.

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

## Visual pricing panel

The dashboard calculates prices locally and does not send costs to Codex, Claude, a supplier,
a store, or the exchange-rate service. Enter example product cost and shipping once to compare
both plans side by side.
Selecting a plan determines which settings the CLI will use after saving; viewing the other plan
does not change the selected plan.

- **Margin plan (default):** product cost + inbound shipping + last-mile shipping + optional
  per-unit tax/duty estimate, then payment/return/operating reserves and target margin. Minimum
  price and the existing `.95` ending remain enforced.
- **Cost-multiplier plan:** product cost multiplied by the chosen value (default `3x`, allowed
  range `1x`–`100x`), then adds inbound shipping, last-mile shipping, optional tax/duty estimate,
  and the fixed payment fee once. Shipping and tax are not multiplied.

### Read the calculation

All pricing inputs and results are **USD per unit**. A payment percentage, return reserve, and
operating reserve each apply to the final selling price. The fixed payment fee assumes
**one unit per order**; allocation across multiple items in an actual order is not implemented.
Return and operating rates are
budgeted deductions, not measured refund or expense data.

Let `C` be product cost, `S` inbound plus last-mile shipping, `T` estimated tax/duty, `F` the fixed
payment fee, and `r` the sum of payment, return, and operating rates. Let `m` be target margin.

| Result | Calculation |
| --- | --- |
| Landed cost | `C + S + T` |
| A: margin candidate | `(C + S + T + F) / (1 - r - m)` |
| A: price before ending | Maximum of the margin candidate, `C × minimum_multiplier`, and minimum price |
| B: multiplier candidate | `C × cost_multiplier + S + T + F` |
| B: price before ending | Maximum of the multiplier candidate and minimum price |
| Final selling price `P` | Round the price upward to the next price ending in `.95`; an existing `.95` stays unchanged |
| Estimated unit profit | `P - (C + S + T) - F - P × r` |
| Estimated margin | Estimated unit profit divided by `P` |
| Theoretical break-even price | `(C + S + T + F) / (1 - r)`, before price floors or `.95` adjustment |

The comparison explains whether the formula, minimum product-cost multiple, or minimum price
sets the price before the `.95` adjustment. Plan B uses no minimum product-cost-multiple floor.
The difference between that pre-ending price and the final price is shown separately.

**Plan B does not automatically ensure the target margin.** Percentage fees and reserves do not
set its price, but they are deducted when estimating its profit. A low multiplier can yield a
loss even when the selling price exceeds product cost plus freight. The displayed profit is an
estimate after the entered deductions, not accounting net profit; omitted expenses remain omitted.

For CJ, the official quote covers its quoted route for each variant. Divide its total by the quoted
quantity and enter that per-unit shipping amount **once**, for example under last-mile with inbound
set to zero. Do not enter the same complete quote in both shipping fields. Subsequent CJ imports
use each variant's actual normalized quote, not the panel's example freight.

### Convert the last-mile shipping example

The converter at the bottom of the sample-cost card uses the **Last-mile / end-to-end shipping
(USD/unit)** field directly. Select CNY, EUR, GBP, JPY, CAD, AUD, HKD, SGD, CHF, NZD, or USD to see
the original USD amount beside the converted amount. The displayed equation, **1 USD = X target
currency**, makes the rate direction explicit; changing the shipping input updates the comparison.

The default reference mode fetches daily rates through the local authenticated dashboard from
[Frankfurter's v1 API](https://frankfurter.dev/v1/). The server requests the fixed endpoint
`https://api.frankfurter.dev/v1/latest?base=USD` and caches the validated response in memory for
one hour. It sends no cost, shipping amount, pricing setting, credential, or user-selected URL to
the service. The reference date and source stay visible: these are daily working-day reference
rates, not live bank execution quotes. Weekends and holidays may show the last available date.

Choose manual mode to enter your own positive rate in the same **1 USD = X** direction. Manual
values are retained when switching languages, and a late reference response cannot replace them.
A failed reference lookup clears the reference conversion and offers retry or manual input;
it does not silently present an old result as a fresh rate.

Only the last-mile trial amount is converted. The converter does not change the USD input,
product cost, inbound freight, either pricing formula, selling prices, or the store currency.
The selected currency, rate, and converted result are not written to `pricing.json`; saving
pricing does not turn this comparison into a currency setting for subsequent imports.

### Worked example

Consider a synthetic product costing **$8.50**, with **$4.71** shipping per unit and **$1.00**
estimated tax/duty. Keep the other defaults: 3.5% payment fee, $0.40 fixed payment fee, 7% return
reserve, 5% operating reserve, 45% target margin, $9.95 minimum price, a 2× minimum product-cost
multiple for A, and a 3× product-cost multiple for B.

| Per-unit result | A: margin | B: 3× product cost |
| --- | ---: | ---: |
| Landed cost | $14.21 | $14.21 |
| Price before `.95` ending | $36.9873 | $31.61 |
| `.95` adjustment | About $0.9627 | $0.34 |
| Final price | **$37.95** | **$31.95** |
| Payment percentage fee | About $1.33 | About $1.12 |
| Fixed payment fee | $0.40 | $0.40 |
| Return reserve | About $2.66 | About $2.24 |
| Operating reserve | About $1.90 | About $1.60 |
| Estimated profit | **$17.46** | **$12.39** |
| Estimated margin | **46.0%** | **38.8%** |
| Theoretical break-even price | About $17.29 | About $17.29 |

Neither price floor changes this example. The upward `.95` adjustment puts A above its 45% target;
B remains below that target. Displayed amounts are rounded, so adding the displayed deductions
can differ by a cent from calculations using full precision. Changing the synthetic inputs changes
both comparisons without importing a product or writing to a store.

### Save, undo, and restore defaults

Product cost and both shipping fields are trial inputs and are not saved. The chosen plan, rates,
multipliers, price floor, fixed payment fee, and per-unit tax/duty estimate are saved settings.
Undo discards pending edits and returns the form to its last saved settings; restoring defaults
loads the original margin defaults into the form. Neither action writes the settings file. To make
restored defaults or other changes apply to later CLI runs, click **Save**.

An invalid trial input clears the old comparison instead of leaving a stale price on screen;
otherwise-valid policy settings can still be saved without a valid trial cost. Invalid selected-plan
settings block saving. If only the alternative plan is invalid, that card is unavailable while the
selected plan remains usable. Rapid edits cancel older previews so late responses cannot overwrite
the current result. Refreshing connection profiles preserves pending pricing edits, and a failed
save leaves those edits available for retry.

Saving validates the settings and atomically writes non-secret `pricing.json` next to the profile
metadata. Only subsequent CLI runs load those saved settings; existing previews and store products
are unchanged. API keys, tokens, cookies, and SSH material are never written there. If the settings
file is absent, the runtime uses the legacy margin defaults. Invalid saved settings stop the CLI
before listing generation rather than silently selecting another price.

Tax/duty values are operator estimates only; CatalogFlow does not query customs, determine a tax
rate, or provide tax advice. Both pricing formulas and the existing settings format remain
compatible with earlier saved settings.

## Current provider status

| Provider | Dashboard profile | Runtime connector |
| --- | --- | --- |
| WooCommerce REST API | Available | Available; hidden drafts only |
| WordPress WP-CLI over SSH | Available to reserve settings | Planned advanced fallback |
| Shopify Admin API | Available to reserve settings | Planned GraphQL adapter |
| Codex CLI | Available | Available; reuses the CLI login |
| Claude Code CLI | Available | Available; reuses the CLI login |
| CJdropshipping API | Available | Preview; one product URL/PID plus per-variant freight |
| Alibaba/1688 Open Platform | Available to reserve credentials | Planned |
| Zendrop API | Available to reserve credentials | Planned |

The dashboard labels preview and planned connectors separately. Saving credentials for an
unfinished Alibaba/1688 or Zendrop adapter does not pretend that it can already make requests.

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
python -m catalogflow product.json --source alibaba-manual --generator codex --ai-profile "My Codex"

python -m catalogflow product.json --source alibaba-manual --generator codex --draft --yes --store-profile "US WooCommerce"

python -m catalogflow "CJ_PRODUCT_URL_OR_PID" --source cj --supplier-profile "My CJ" --generator codex
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
