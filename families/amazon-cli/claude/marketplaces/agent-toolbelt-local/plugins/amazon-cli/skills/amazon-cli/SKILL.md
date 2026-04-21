---
name: amazon-cli
description: Use the local Amazon CLI for Amazon product search, exact model lookup, product specs, comparisons, review/comment extraction, cross-market offers, and managed retail or business sessions. Trigger when Claude needs Amazon marketplace data, same-ASIN price comparisons, deep Amazon reviews, or Amazon session login support.
---

# Amazon CLI

Use `scripts/invoke_amazon_cli.py` for read-only Amazon marketplace workflows through the local Amazon CLI under `%LOCALAPPDATA%\Tools\amazon-intent-cli`.

- Prefer `search`, `similar`, `get`, `compare`, `reviews`, and `offers`.
- Run `session login` only when the user can interact with a headed managed browser.
- Do not add products to cart, checkout, submit reviews, submit feedback, or mutate an Amazon account.
- Use `search <base> --brand <brand> --model <model>` for exact model search; bare `"LG C4"` is plain search.
- Use `--pages` only with `search` and `similar`.
- Use managed sessions for deep reviews.
- Inspect variant mismatch warnings in `offers` before recommending a trusted cheapest offer.

```bash
python scripts/invoke_amazon_cli.py -- search "tv" --brand LG --model C4 --marketplace de --max-price 560 --pages 2
python scripts/invoke_amazon_cli.py -- reviews B0F2JCZPB4 --marketplace de --portal retail --limit 20
python scripts/invoke_amazon_cli.py -- offers B0F2JCZPB4 --marketplace de --marketplaces de,fr,es,uk
python scripts/invoke_amazon_cli.py -- session login --marketplace de --portal retail
```
