# Work reports and draft history

CLI imports and the visual import wizard use the same run archive under the CatalogFlow
configuration directory:

- Windows: `%APPDATA%\CatalogFlow\reports\`.
- Other systems: the normal CatalogFlow user configuration directory, followed by `reports/`.
- `CATALOGFLOW_CONFIG_DIR` selects an alternate configuration root for isolated testing.

The run ID combines a UTC timestamp with a random ID. Completed runs have UTF-8 `report.txt` and
structured `report.json` files. Creating another run never overwrites an earlier run. The existing
`--output` JSON preview remains available and can still overwrite that explicitly selected path.
The report archive is independent of that compatibility output.

The visual wizard records its preview and the result of an explicitly confirmed draft through
this reporting system. It reuses the reviewed product and price snapshot for confirmation rather
than fetching the supplier, invoking AI, or recalculating prices again. These reports are evidence
of what happened; they are not a resumable saved import session.

## What is recorded

Reports include run and item timestamps with timezone offsets, preview/draft mode, the supplier,
supplier product ID, source URL when known, title, item outcome, bounded diagnostic messages,
and the store ID/check link when a draft is known to exist. Per-item records survive an interrupted
batch; an unfinished operation is not represented as a successful draft.

Supply `source_url` in authorized normalized JSON to retain an original supplier link. A local
JSON filename is not a supplier URL; when no original link is known, the report leaves it absent
rather than inventing one. CJ URL imports retain the supplied product link; a PID alone does not
prove an original URL, so that link remains absent when the provider does not supply one. URL
credentials and tracking/session/fragment data are excluded from source links; strictly validated
CJ product-ID query parameters are retained when needed to identify the item. Reports contain
operator data, so keep them local and out of a public repository.

The dashboard's **工作记录 / Work history** section reads the archive and can download a TXT copy.
Times identify their timezone. Preview, completed draft, duplicate, and failure are separate
outcomes. The viewer shows the most recent 30 readable runs; older report files remain on disk.
The viewer does not initiate store writes. Use a local filesystem with hard-link support (such
as the normal NTFS Windows profile directory) for atomic report storage.

## Duplicate protection

The local `import-history.sqlite3` registry associates the store's normalized identity, supplier,
and supplier product ID with a durable draft reservation. The application reserves a product
before sending a store write. A completed reservation skips a repeat draft and refers to its
original store ID. Preview runs do not reserve anything and can be repeated after pricing edits.

A timeout, interrupted request, partial image/variation failure, or interrupted process may leave
an uncertain reservation. It blocks another automatic creation because a draft may already exist.
Review the report and the store before reconciling it. This release does not provide a force-create
button, automatic deletion, or automatic retry of uncertain writes. Keep the history database when
moving or backing up a configuration directory. It is local to that configuration, not a shared
cross-computer lock; use one active importer per store. A stable CatalogFlow SKU provides an
additional check against previously created parent products at the store boundary.

Old private TXT reports and registries are not automatically imported. They are evidence of past
operations, not confirmation that a particular product still exists in the store today.

## Images and variants

Multi-variant exports create a variable parent and individual variants with their own attributes
and prices. Product and variant images come only from authorized HTTPS inputs. Downloads are
bounded and temporary; uploads use media IDs instead of asking the store to fetch arbitrary URLs.
Exports accept at most 100 variants and 20 distinct images, each at most 8 MiB. Exceeding these
limits rejects the export instead of silently discarding variants or pictures.

WooCommerce consumer keys authorize product/term operations. WordPress media uploads separately
require `WOOCOMMERCE_MEDIA_USERNAME` and `WOOCOMMERCE_MEDIA_APPLICATION_PASSWORD`, or the corresponding
WooCommerce connection fields. Use a WordPress application password for a user with `upload_files`
permission and access to edit the associated draft. Do not use the account's login password.
Secrets stay in the operating-system keyring
and never enter reports or AI prompts. When required image credentials are missing, export stops
before creating a product.

Products remain hidden drafts and variants remain drafts. Media URLs can be directly accessible
even while their parent product is a draft. A failed run may leave an incomplete hidden draft and
uploaded attachments for review; the program does not delete them automatically.

## Scope

The CLI and [single-product visual wizard](visual-import.md) provide report-producing imports.
The dashboard also provides configuration, pricing, and report review. The [Windows EXE](windows.md)
opens that dashboard and also accepts CLI arguments. Closing a browser page does not stop a running
import. Reopening the authenticated page can recover the current task while the same server runs;
restarting the application discards unconfirmed in-memory previews and keeps the written reports.
The wizard does not resume a preview from a historical TXT or JSON report. Batch imports in the
wizard, uncertain-write reconciliation controls, and private-history migration remain follow-up work.
None of these reports authorize public publishing or production actions.
