# Skroutz CLI

`agent-toolbelt-skroutz-cli` bridges a bundled `skroutz-intent-cli` client for user-driven Skroutz Cyprus shopping workflows.

## Commands

```powershell
agent-toolbelt-skroutz-cli -- search "iphone 17"
agent-toolbelt-skroutz-cli -- get 62956505
agent-toolbelt-skroutz-cli -- offers https://www.skroutz.cy/s/62956505/product.html
agent-toolbelt-skroutz-cli -- reviews 62956505 --limit 5
agent-toolbelt-skroutz-cli -- compare 62956505 62956506
agent-toolbelt-skroutz-cli -- session login --login-timeout-sec 300
agent-toolbelt-skroutz-cli -- cart list
agent-toolbelt-skroutz-cli -- cart add 62956505 --quantity 1 --confirm-cart-add
agent-toolbelt-skroutz-cli -- cart remove 62956505 --quantity 1 --confirm-cart-remove
```

Public read-only commands use a bounded, single-threaded fetch path. Cart operations use a managed local browser profile outside the repository.

## Safety

- No checkout, buy, payment, address, review submission, or comment submission workflows.
- Cart add/remove require explicit confirmation flags.
- Do not run this as a crawler, background scraper, or parallel fetcher.
- Account state and browser profiles are stored outside the repository.
