---
name: amazon-cli
description: Use the local Amazon CLI for Amazon product search, exact model lookup, product specs, comparisons, review/comment extraction, cross-market offers, and managed retail or business sessions. Trigger when Claude needs Amazon marketplace data, same-ASIN price comparisons, deep Amazon reviews, or Amazon session login support.
---

# Amazon CLI

Use `scripts/invoke_amazon_cli.py` for read-only Amazon marketplace workflows through the bundled Amazon CLI client under `agent_toolbelt_amazon_cli/assets/amazon-intent-cli`.

- Prefer read-only commands: `inspect-identifier`, `search`, `similar`, `get`, `compare`, `reviews`, `address inspect`, `offers`, and `cart list`.
- Run `inspect-identifier <asin-or-url>` before `get`, `offers`, `reviews`, or cart commands when the input is a URL or ambiguous identifier; require `supported=true` and inspect any warnings before proceeding.
- Run `cart list --marketplace <code> --portal <retail|business>` before `cart add` or `cart remove` when the current cart state is unclear. It is read-only, uses stored managed-session cookies through the normal HTTP client path, must not launch a visible browser, and requires a managed session.
- Keep browser profiles, cookies, managed sessions, generated virtual environments, and account runtime state out of plugin/package files.
- Run `session login` only when the user can interact with a headed managed browser. Login completion is auto-detected from Amazon account/header markers; use `--manual-confirm` only as a fallback for unusual flows, and adjust `--login-timeout-sec` if needed. Do not launch interactive login through the agent's captured command runner when the browser must stay open; that runner may clean up child browser processes when the command finishes or is interrupted. For interactive login, start a real visible user-controlled PowerShell window with `Start-Process powershell.exe` and `-NoExit`, then let the user close it after login completes.
- Use `cart add` or `cart remove` only after explicit user approval for one selected ASIN/marketplace, and always include `--confirm-cart-add` or `--confirm-cart-remove`.
- Browser actions use targeted waits instead of generic `networkidle`; inspect `action_timing_ms`, `wait_strategy`, and `detected_marker` when debugging slow login or cart actions.
- Never checkout, never buy, never click Buy Now, never submit reviews, submit feedback, or mutate an Amazon account beyond explicit cart mutation commands.
- Use `search <base> --brand <brand> --model <model>` for exact model search; bare `"LG C4"` is plain search.
- Use `--pages` only with `search` and `similar`.
- Use managed sessions for deep reviews.
- For Business repurchase comparisons, prefer `offers --portal business --vat-mode auto` so ex-VAT prices are used when Amazon exposes them.
- Check `address_consistency` and use `trusted_best_offer`; do not recommend `raw_best_offer` when it is address-mismatched or non-deliverable unless the user explicitly accepts that risk.
- Treat top-level `warnings` from `offers`, `search`, and `reviews` as confidence signals for missing trusted offers, address mismatch, model variants, partial pagination, or review fallback evidence.
- Use `address inspect --portal <retail|business> --marketplaces <csv> --reference-marketplace <code>` when delivery costs depend on all marketplaces using the same destination.
- Inspect variant mismatch warnings in `offers` before recommending a trusted cheapest offer.

## Repurchase workflow

For known-product repurchases, search one primary marketplace first, select the same-format candidate ASIN, then run `offers` against that ASIN. For Business use `--portal business --vat-mode auto`, check `address_consistency.status`, and prefer `trusted_best_offer` over `raw_best_offer`. Do not compare capsules, drinkable vials, ampoules, shampoos, and bundles as equivalent. If the current cart may already contain the product, run `cart list --marketplace <marketplace> --portal <portal>` first and inspect `items`, `warnings`, and `safety`. If the user wants to defer buying, ask before running `cart add <asin> --marketplace <trusted_best_offer.marketplace> --portal <portal> --quantity <n> --confirm-cart-add`. If the user wants to undo a prior cart add, ask before running `cart remove <asin> --marketplace <marketplace> --portal <portal> --quantity <n> --confirm-cart-remove`. If the primary marketplace exact search fails, try fallback marketplaces after that failure instead of starting with broad multi-market searching.

```bash
python scripts/invoke_amazon_cli.py -- inspect-identifier https://www.amazon.de/dp/B0F2JCZPB4 --marketplace de
python scripts/invoke_amazon_cli.py -- search "tv" --brand LG --model C4 --marketplace de --max-price 560 --pages 2
python scripts/invoke_amazon_cli.py -- reviews B0F2JCZPB4 --marketplace de --portal retail --limit 20
python scripts/invoke_amazon_cli.py -- address inspect --portal business --marketplaces de,es,fr,it --reference-marketplace de
python scripts/invoke_amazon_cli.py -- offers B0F2JCZPB4 --marketplace de --marketplaces de,fr,es,uk --portal business --vat-mode auto
python scripts/invoke_amazon_cli.py -- cart list --marketplace de --portal business
python scripts/invoke_amazon_cli.py -- cart add B0DHVGHPF9 --marketplace es --portal business --quantity 1 --confirm-cart-add
python scripts/invoke_amazon_cli.py -- cart remove B0DHVGHPF9 --marketplace es --portal business --quantity 1 --confirm-cart-remove
python scripts/invoke_amazon_cli.py -- session login --marketplace de --portal retail --login-timeout-sec 300
python scripts/invoke_amazon_cli.py -- session login --marketplace de --portal retail --manual-confirm
```

## Interactive session login

Use this only for `session login`, not read-only commands or cart actions. The point is to keep the login browser and owning terminal under user control instead of under the agent command lifecycle.

```powershell
$skill = 'C:\Users\darka\.codex\skills\amazon-cli'
$cmd = 'Set-Location -LiteralPath "' + $skill + '"; python scripts\invoke_amazon_cli.py -- session login --marketplace de --portal business --login-timeout-sec 300'
Start-Process powershell.exe -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $cmd)
```

Safety rules:

- Use a visible window only because Amazon login is explicitly interactive. Do not use this pattern for background/read-only commands.
- Do not use `-WindowStyle Hidden` for login; the user must see and control the browser.
- Do not run checkout, Buy Now, payment, address changes, review submission, or unconfirmed cart mutations from this window.
- If the browser or terminal appears stuck, the user owns the visible window and can close it; do not kill unrelated sync/login processes from another session.
