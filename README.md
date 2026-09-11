# CatalogFlow

[![CI](https://github.com/qwq77777764/catalogflow/actions/workflows/ci.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/ci.yml)
[![Secret scan](https://github.com/qwq77777764/catalogflow/actions/workflows/secret-scan.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/secret-scan.yml)
[![CodeQL](https://github.com/qwq77777764/catalogflow/actions/workflows/codeql.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/codeql.yml)

CatalogFlow is a safety-first, human-approved pipeline that turns authorized supplier
product facts into consistent WooCommerce drafts.

It grew out of a private workflow used to process thousands of catalog records from
multiple suppliers. The open-source edition deliberately removes production secrets,
stored supplier pages, customer data, and automatic public publishing.

> **Alpha:** the current release provides a provider-neutral core, deterministic offline
> previews, and an opt-in WooCommerce hidden-draft adapter. It does not scrape supplier
> websites and never publishes products publicly.

## Why CatalogFlow

- One provider-neutral product model for CJ and user-authorized Alibaba exports.
- Deterministic pricing and listing validation that can be reviewed and tested.
- `dry-run` is the default; external writes require both `--draft` and `--yes`.
- WooCommerce output is hard-coded to `status=draft` and
  `catalog_visibility=hidden`.
- Credentials come from environment variables and are never accepted in product files.
- Synthetic fixtures run without supplier, store, or AI accounts.

## Five-minute local demo

```bash
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[dev]"
catalogflow examples/synthetic_product.json --source cj
pytest
```

The preview is written to `output/preview.json`, which is ignored by Git.

To opt into structured generation with an installed and authenticated Codex CLI:

```bash
catalogflow examples/synthetic_product.json --source cj --generator codex
```

Codex receives normalized merchandising facts, not supplier credentials, source IDs,
store credentials, or cost values. The deterministic pricing policy runs locally after
generation.

## Explicit hidden-draft write

Set the three `WOOCOMMERCE_*` environment variables shown in `.env.example`, review the
local input, then run:

```bash
catalogflow product.json --source cj --draft --yes
```

This interface can only create a hidden draft. Public publishing remains a separate,
manual store-admin decision.

## Architecture

```text
authorized product data
        |
        v
SourceAdapter -> Product -> ListingGenerator -> validation -> ImportReport
                                                        |
                                           dry-run -----+----- hidden draft
```

The primary interface is:

```python
import_products(requests, sources=..., generator=..., mode="dry-run") -> ImportReport
```

Complexity stays behind that small interface. The seams that genuinely vary are
`SourceAdapter`, `ListingGenerator`, and `StorePublisher`. Tests use local adapters; a
store write cannot happen accidentally in the default mode.

See [docs/architecture.md](docs/architecture.md) and
[docs/migration-from-private-workflow.md](docs/migration-from-private-workflow.md).
Planned work is tracked in [ROADMAP.md](ROADMAP.md).

## Supplier and data policy

CatalogFlow is for data you own, are authorized to process, or obtain through an official
API under its applicable terms. This repository does not include copied supplier pages,
images, cookies, access tokens, production exports, or a bulk scraper. The
`alibaba-manual` source accepts normalized facts explicitly supplied by the operator.

## Security

Please read [SECURITY.md](SECURITY.md). Never open an issue containing a token, store URL,
customer record, raw supplier response, or production log.

## Contributing

Small merchants should be able to run the complete test suite without any external
account. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
