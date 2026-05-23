# Amazon CLI

`agent-toolbelt-amazon-cli` bridges agent-toolbelt into the bundled Amazon CLI client shipped with this family.

The family vendors the Amazon CLI source under `src/agent_toolbelt_amazon_cli/assets/amazon-intent-cli` and delegates commands to that client with `uv run --project`. It does not copy managed browser sessions, browser profiles, cookies, or local runtime storage. The bridge routes uv's project environment to local runtime storage so the bundled source tree stays clean after use.

```powershell
uv run agent-toolbelt-amazon-cli -- inspect-identifier https://www.amazon.de/dp/B0F2JCZPB4 --marketplace de
uv run agent-toolbelt-amazon-cli -- offers B0F2JCZPB4 --marketplace de --marketplaces de,fr,es
uv run agent-toolbelt-amazon-cli -- reviews B0F2JCZPB4 --marketplace de --portal retail --limit 20
uv run agent-toolbelt-amazon-cli -- cart list --marketplace de --portal business
```

Use `inspect-identifier` before `get`, `offers`, `reviews`, or cart operations when the input is a URL or ambiguous ASIN. Use `cart list` before `cart add` or `cart remove` when the current managed-session cart state is unclear. `cart list` is read-only, account-backed, and uses stored managed-session cookies over the normal HTTP client path, similar to search/offers; it must not launch a visible browser, checkout, buy, delete, change quantity, submit forms, or mutate the cart.

For `session login`, use a real visible user-controlled terminal when the headed login browser must stay open. Do not run interactive login through an agent captured command runner if that runner may clean up child browser processes when the command finishes or is interrupted. A safe Windows pattern is:

```powershell
$skill = 'C:\Users\darka\.codex\skills\amazon-cli'
$cmd = 'Set-Location -LiteralPath "' + $skill + '"; python scripts\invoke_amazon_cli.py -- session login --marketplace de --portal business --login-timeout-sec 300'
Start-Process powershell.exe -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $cmd)
```

Use this visible-window exception only for interactive login. Keep read-only commands and cart actions in the normal wrapper path.

The bridge also promotes advisory warnings from offer trust signals, search variant/partial-result signals, and review fallback/partial-result signals into the normalized top-level `warnings` array.
