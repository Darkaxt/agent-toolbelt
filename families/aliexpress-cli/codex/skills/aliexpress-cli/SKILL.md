---
name: aliexpress-cli
description: Use the local AliExpress CLI for AliExpress product search, item browsing, product detail extraction, reviews/comments, comparison, and optional managed login/session-backed read-only browsing. Trigger when Codex needs clean AliExpress shopping data without page bloat, including descriptions, price details, shipping/free-delivery evidence, seller data, variants, comments, and product links.
license: MIT
compatibility: Windows/local CLI oriented; targets user-driven AliExpress shopping discovery with optional managed browser session for logged-in read visibility.
metadata:
  version: "0.1.0"
---

# AliExpress CLI

Use `scripts/invoke_aliexpress_cli.py` for bounded, user-driven AliExpress product discovery.

## Commands

```powershell
python scripts/invoke_aliexpress_cli.py -- inspect-identifier 1005000000000000
python scripts/invoke_aliexpress_cli.py -- search "30L trash bin" --pages 1 --ship-to CY --currency EUR
python scripts/invoke_aliexpress_cli.py -- browse --url "https://www.aliexpress.com/wholesale?SearchText=30L+trash+bin"
python scripts/invoke_aliexpress_cli.py -- get https://www.aliexpress.com/item/1005000000000000.html --ship-to CY --currency EUR
python scripts/invoke_aliexpress_cli.py -- reviews 1005000000000000 --limit 10
python scripts/invoke_aliexpress_cli.py -- compare 1005000000000000 1005000000000001
python scripts/invoke_aliexpress_cli.py -- session login --login-timeout-sec 300 --manual-confirm
python scripts/invoke_aliexpress_cli.py -- session status
python scripts/invoke_aliexpress_cli.py -- session logout
```

## Workflow

- Run `inspect-identifier` when the user gives an AliExpress URL or ambiguous numeric item id.
- Use `search` for candidate discovery, then `get` for selected item details.
- Use `reviews` for visible buyer comments/review evidence.
- Use `compare` only for a short, user-selected set of item ids or URLs.
- Run `session login --manual-confirm` only when logged-in page visibility is needed. Launch it in a user-visible terminal so the user can enter credentials directly into AliExpress.
- After login, add `--use-session` to `search`, `browse`, `get`, or `reviews` only when public HTTP/curl extraction is blocked or when account-visible shipping/price data is required.

## Output Contract

- Prefer JSON fields over raw page text: `title`, `description`, `price_summary`, `shipping_summary`, `free_delivery`, `seller`, `variants`, `reviews`, and `product_link`.
- Treat `warnings` and `source_diagnostics` as confidence signals. If extraction is blocked, login-gated, or sparse, say that rather than inventing product data.
- `price_summary.details` and `shipping_summary.details` are the best places to inspect full price and delivery evidence.

## Safety

This skill is single-threaded and user-triggered. No cart list/add/remove support exists in this family. No checkout, buy now, payment changes, address changes, order actions, wishlist mutation, review/comment submission, bundled cookies, or hidden account-state transfer. Do not use it for background crawling or parallel scraping.

Credentials stay with the AliExpress website in the managed browser profile. Do not ask the user to paste credentials into chat.
