---
name: amazon-cli
description: Use the local Amazon CLI for Amazon product search, exact model lookup, product specs, comparisons, review/comment extraction, cross-market offers, and managed retail or business sessions. Trigger when Claude needs Amazon marketplace data, same-ASIN price comparisons, deep Amazon reviews, or Amazon session login support.
---

# Amazon CLI

Use `scripts/invoke_amazon_cli.py` for read-only Amazon marketplace workflows through the bundled Amazon CLI client under `agent_toolbelt_amazon_cli/assets/amazon-intent-cli`.

- Prefer `search`, `similar`, `get`, `compare`, `reviews`, `address inspect`, and `offers`.
- Keep browser profiles, cookies, managed sessions, generated virtual environments, and account runtime state out of plugin/package files.
- Run `session login` only when the user can interact with a headed managed browser.
- Do not add products to cart, checkout, submit reviews, submit feedback, or mutate an Amazon account.
- Use `search <base> --brand <brand> --model <model>` for exact model search; bare `"LG C4"` is plain search.
- Use `--pages` only with `search` and `similar`.
- Use managed sessions for deep reviews.
- For Business repurchase comparisons, prefer `offers --portal business --vat-mode auto` so ex-VAT prices are used when Amazon exposes them.
- Check `address_consistency` and use `trusted_best_offer`; do not recommend `raw_best_offer` when it is address-mismatched or non-deliverable unless the user explicitly accepts that risk.
- Use `address inspect --portal <retail|business> --marketplaces <csv> --reference-marketplace <code>` when delivery costs depend on all marketplaces using the same destination.
- Inspect variant mismatch warnings in `offers` before recommending a trusted cheapest offer.

## Repurchase workflow

For known-product repurchases, search one primary marketplace first, select the same-format candidate ASIN, then run `offers` against that ASIN. For Business use `--portal business --vat-mode auto`, check `address_consistency.status`, and prefer `trusted_best_offer` over `raw_best_offer`. Do not compare capsules, drinkable vials, ampoules, shampoos, and bundles as equivalent. If the primary marketplace exact search fails, try fallback marketplaces after that failure instead of starting with broad multi-market searching.

```bash
python scripts/invoke_amazon_cli.py -- search "tv" --brand LG --model C4 --marketplace de --max-price 560 --pages 2
python scripts/invoke_amazon_cli.py -- reviews B0F2JCZPB4 --marketplace de --portal retail --limit 20
python scripts/invoke_amazon_cli.py -- address inspect --portal business --marketplaces de,es,fr,it --reference-marketplace de
python scripts/invoke_amazon_cli.py -- offers B0F2JCZPB4 --marketplace de --marketplaces de,fr,es,uk --portal business --vat-mode auto
python scripts/invoke_amazon_cli.py -- session login --marketplace de --portal retail
```
