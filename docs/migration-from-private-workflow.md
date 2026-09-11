# Migration from the private workflow

The original operator workflow combined browser userscripts, a localhost queue, Codex
generation, supplier calls, pricing, remote commands, WooCommerce writes, and runtime
registries in one directory.

The public repository is a clean-room extraction, not a copy of that directory.

## Intentionally excluded

- production configuration and backups;
- API keys, access tokens, cookies, and server targets;
- supplier HTML, images, raw API responses, and product exports;
- queues, registries, logs, reports, and generated import scripts;
- automatic public publishing;
- unauthenticated localhost bridges and unrestricted URL downloaders.

Future provider adapters must use official APIs or operator-authorized input. Future
browser helpers must authenticate local requests, restrict origins and payload size, and
reject localhost/private-network downloads.

