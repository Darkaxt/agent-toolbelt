# AliExpress CLI

`agent-toolbelt-aliexpress-cli` packages a local AliExpress discovery helper for product search and item browsing. It mirrors the Amazon/Skroutz family architecture while deliberately excluding cart, checkout, payment, order, address, wishlist, and review-submission workflows.

Use it for:

- AliExpress product search with clean JSON results
- item detail extraction, including descriptions, images, specs, variants, price ranges, shipping/free-delivery evidence, and product links
- review/comment extraction where visible
- comparing a short list of selected item URLs or IDs
- optional managed login for user-controlled logged-in page visibility

The bundled `aliexpress-intent-cli` is web-first: normal reads try HTTP, then a `curl` browser-user-agent fallback, and only use a managed Playwright profile for explicit `session login` or read-only commands where `--use-session` is passed. It is single-threaded and user-triggered; it is not a crawler.

## Examples

```powershell
python scripts/invoke_aliexpress_cli.py -- inspect-identifier https://www.aliexpress.com/item/1005000000000000.html
python scripts/invoke_aliexpress_cli.py -- search "30L trash bin" --ship-to CY --currency EUR --pages 1
python scripts/invoke_aliexpress_cli.py -- browse --url "https://www.aliexpress.com/wholesale?SearchText=30L+trash+bin"
python scripts/invoke_aliexpress_cli.py -- get https://www.aliexpress.com/item/1005000000000000.html --ship-to CY --currency EUR
python scripts/invoke_aliexpress_cli.py -- reviews 1005000000000000 --limit 10
python scripts/invoke_aliexpress_cli.py -- compare 1005000000000000 https://www.aliexpress.com/item/1005000000000001.html
python scripts/invoke_aliexpress_cli.py -- session login --login-timeout-sec 300
python scripts/invoke_aliexpress_cli.py -- session status
python scripts/invoke_aliexpress_cli.py -- session logout
```

## Safety

- No cart list/add/remove support in this family.
- No checkout, buy-now, payment, order, address, wishlist, review submission, or account mutation actions.
- No bundled cookies, browser profiles, credentials, sessions, generated virtual environments, or account data.
- Use is bounded, single-threaded, and user-directed.
