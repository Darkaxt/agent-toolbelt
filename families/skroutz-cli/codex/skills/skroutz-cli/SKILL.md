---
name: skroutz-cli
description: Use the local Skroutz CLI for Skroutz.cy product search, product detail lookup, offers, reviews, comparisons, managed login, cart listing, and explicitly confirmed cart add/remove workflows.
license: MIT
compatibility: Windows/local CLI oriented; targets Skroutz.cy shopping workflows with optional managed browser session for cart operations.
metadata:
  version: "0.1.0"
---

# Skroutz CLI

Use `scripts/invoke_skroutz_cli.py` for user-driven Skroutz Cyprus shopping workflows.

## Commands

```powershell
python scripts/invoke_skroutz_cli.py -- inspect-identifier 62956505
python scripts/invoke_skroutz_cli.py -- search "iphone 17" --pages 1
python scripts/invoke_skroutz_cli.py -- get 62956505
python scripts/invoke_skroutz_cli.py -- offers https://www.skroutz.cy/s/62956505/product.html
python scripts/invoke_skroutz_cli.py -- reviews 62956505 --limit 5
python scripts/invoke_skroutz_cli.py -- compare 62956505 62956506
python scripts/invoke_skroutz_cli.py -- session login --login-timeout-sec 300 --manual-confirm
python scripts/invoke_skroutz_cli.py -- cart list
python scripts/invoke_skroutz_cli.py -- cart add 62956505 --quantity 1 --confirm-cart-add
python scripts/invoke_skroutz_cli.py -- cart remove 62956505 --quantity 1 --confirm-cart-remove
```

## Workflow

- Run `inspect-identifier` when the user gives a Skroutz URL or ambiguous numeric id.
- Use `search` to find candidates, then `get` or `offers` for selected product ids.
- Use `reviews` for visible review evidence and `compare` for a small set of selected product ids.
- Use `cart list` before cart mutations when current cart state is unclear.
- Use cart mutations only with explicit user confirmation and the required confirmation flag.

## Safety

This skill is single-threaded and user-triggered. Do not use it for background crawling, parallel scraping, review/comment submission, checkout, buy now, payment changes, address changes, bundled cookies, or hidden account-state transfer.

`cart list` is read-only but account-backed. `cart add` and `cart remove` are the only cart mutations and require `--confirm-cart-add` or `--confirm-cart-remove`. Never checkout or buy.

Skroutz robots/API restrictions should be treated as a caution for abuse prevention. This local helper is for bounded user-directed shopping actions, not automated crawling.
