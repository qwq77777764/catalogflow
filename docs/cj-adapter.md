# CJ official API preview adapter

CatalogFlow can normalize one explicitly selected CJdropshipping product through the operator's
own authorized CJ API access. CatalogFlow does not provide, broker, or bypass that access and is not
affiliated with or endorsed by CJdropshipping.

## Current official API path

The preview adapter follows CJ API v2.0 documentation:

1. exchange the operator's API key at `POST /authentication/getAccessToken`;
2. keep the returned access token only in process memory;
3. request exactly one selected PID from `POST /product/productDetail/query`;
4. normalize the returned title, variants, USD costs, authorized HTTPS images, and verified facts.

Official references:

- [CJ API v2.0 authentication](https://developers.cjdropshipping.com/en/api/api2/api/auth.html)
- [CJ product APIs](https://developers.cjdropshipping.com/en/api/api2/api/product.html)
- [CJ API points rules](https://developers.cjdropshipping.com/en/api/api2/standard/points.html)

CJ documents product-detail calls as consuming API points. CatalogFlow therefore does not use the
adapter for catalog enumeration or background discovery. Check CJ's current terms, account access,
points, limits, and field definitions before use because third-party APIs can change.

## Configure without exposing the API key

Run:

```powershell
python -m catalogflow configure
```

Create a **CJdropshipping API** profile, enter a local label, and paste the API key that you obtained
from your own CJ account. The key is stored through the operating-system keyring and is not written
to `profiles.json`, returned to the dashboard, committed to Git, or placed in a product JSON file.

Then preview one CJ product:

```powershell
python -m catalogflow "CJ_PRODUCT_URL_OR_PID" --source cj `
  --supplier-profile "My CJ" --generator codex
```

Omit `--draft --yes` during validation. The normal result is a local `output/preview.json` file.

## Security and data boundary

- Only `https://developers.cjdropshipping.com` API endpoints embedded in code are allowed.
- API redirects are rejected so authorization headers are not forwarded to another host.
- JSON responses are bounded to 2 MiB and are never logged or saved as fixtures.
- Provider error messages are replaced by redacted local errors.
- Returned product IDs must match the requested PID.
- Credentials, source IDs, and acquisition costs are excluded from the AI subprocess input.
- No missing authorization, rate limit, or malformed response triggers a scraping fallback.
- Store writes remain impossible unless the operator separately supplies `--draft --yes`; even then,
  the publisher can create only a WooCommerce `draft` with `catalog_visibility=hidden`.

## Preview limitations

- Input must contain one unambiguous CJ PID, either directly or in an official HTTPS product URL.
- This adapter does not yet consume the Alibaba browser queue.
- Shipping calculation is not included in this first slice; returned variant sell price is treated
  as the USD acquisition cost supplied by CJ and deterministic pricing remains local.
- Exact source fields can drift. Contract tests use synthetic responses and live validation should
  begin with one user-selected product.
