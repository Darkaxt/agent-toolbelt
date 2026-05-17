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

Run `search`, then `get`, `offers`, `reviews`, or `compare` for selected product ids. Use `cart list` before cart mutations when cart state is unclear.

Cart mutations require explicit flags:

```powershell
python scripts/invoke_skroutz_cli.py -- cart add 62956505 --quantity 1 --confirm-cart-add
python scripts/invoke_skroutz_cli.py -- cart remove 62956505 --quantity 1 --confirm-cart-remove
```

Never checkout, buy, change payment/address data, submit reviews/comments, run background crawling, or parallelize Skroutz requests. This is a single-threaded local shopping helper.
