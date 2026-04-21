---
name: amazon-cli
description: Use the local Amazon CLI for Amazon product search, exact model lookup, product specs, comparisons, review/comment extraction, cross-market offers, and managed retail or business sessions. Trigger when Claude needs Amazon marketplace data, same-ASIN price comparisons, deep Amazon reviews, or Amazon session login support.
---

# Amazon CLI

Use `scripts/invoke_amazon_cli.py` for read-only Amazon marketplace workflows through the bundled Amazon CLI client under `agent_toolbelt_amazon_cli/assets/amazon-intent-cli`.

- Prefer `search`, `similar`, `get`, `compare`, `reviews`, `address inspect`, and `offers`.
- Keep browser profiles, cookies, managed sessions, generated virtual environments, and account runtime state out of plugin/package files.
- Run `session login` only when the user can interact with a headed managed browser. Login completion is auto-detected from Amazon account/header markers; use `--manual-confirm` only as a fallback for unusual flows, and adjust `--login-timeout-sec` if needed.
- Use `cart add` or `cart remove` only after explicit user approval for one selected ASIN/marketplace, and always include `--confirm-cart-add` or `--confirm-cart-remove`.
- Browser actions use targeted waits instead of generic `networkidle`; inspect `action_timing_ms`, `wait_strategy`, and `detected_marker` when debugging slow login or cart actions.
- Never checkout, never buy, never click Buy Now, never submit reviews, submit feedback, or mutate an Amazon account beyond explicit cart mutation commands.
- Use `search <base> --brand <brand> --model <model>` for exact model search; bare `"LG C4"` is plain search.
- Use `--pages` only with `search` and `similar`.
- Use managed sessions for deep reviews.
- For Business repurchase comparisons, prefer `offers --portal business --vat-mode auto` so ex-VAT prices are used when Amazon exposes them.
- Check `address_consistency` and use `trusted_best_offer`; do not recommend `raw_best_offer` when it is address-mismatched or non-deliverable unless the user explicitly accepts that risk.
- Use `address inspect --portal <retail|business> --marketplaces <csv> --reference-marketplace <code>` when delivery costs depend on all marketplaces using the same destination.
- Inspect variant mismatch warnings in `offers` before recommending a trusted cheapest offer.

## Repurchase workflow

For known-product repurchases, search one primary marketplace first, select the same-format candidate ASIN, then run `offers` against that ASIN. For Business use `--portal business --vat-mode auto`, check `address_consistency.status`, and prefer `trusted_best_offer` over `raw_best_offer`. Do not compare capsules, drinkable vials, ampoules, shampoos, and bundles as equivalent. If the user wants to defer buying, ask before running `cart add <asin> --marketplace <trusted_best_offer.marketplace> --portal <portal> --quantity <n> --confirm-cart-add`. If the user wants to undo a prior cart add, ask before running `cart remove <asin> --marketplace <marketplace> --portal <portal> --quantity <n> --confirm-cart-remove`. If the primary marketplace exact search fails, try fallback marketplaces after that failure instead of starting with broad multi-market searching.

```bash
python scripts/invoke_amazon_cli.py -- search "tv" --brand LG --model C4 --marketplace de --max-price 560 --pages 2
python scripts/invoke_amazon_cli.py -- reviews B0F2JCZPB4 --marketplace de --portal retail --limit 20
python scripts/invoke_amazon_cli.py -- address inspect --portal business --marketplaces de,es,fr,it --reference-marketplace de
python scripts/invoke_amazon_cli.py -- offers B0F2JCZPB4 --marketplace de --marketplaces de,fr,es,uk --portal business --vat-mode auto
python scripts/invoke_amazon_cli.py -- cart add B0DHVGHPF9 --marketplace es --portal business --quantity 1 --confirm-cart-add
python scripts/invoke_amazon_cli.py -- cart remove B0DHVGHPF9 --marketplace es --portal business --quantity 1 --confirm-cart-remove
python scripts/invoke_amazon_cli.py -- session login --marketplace de --portal retail --login-timeout-sec 300
python scripts/invoke_amazon_cli.py -- session login --marketplace de --portal retail --manual-confirm
```
