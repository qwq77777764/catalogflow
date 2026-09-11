# Contributing

Contributions are welcome when they keep CatalogFlow safe and reproducible.

1. Create a focused branch.
2. Add or update tests using synthetic data.
3. Run `ruff check .` and `pytest`.
4. Confirm `git status` contains no local config, output, supplier content, or credentials.
5. Explain any new network access or store-write behavior in the pull request.

Provider adapters should normalize authorized data into `Product`; they should not leak
provider-specific complexity into the pipeline interface. Avoid adding a new seam until
there are at least two meaningful adapters (normally production and test).

