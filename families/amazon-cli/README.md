# Amazon CLI

`agent-toolbelt-amazon-cli` bridges agent-toolbelt into the bundled Amazon CLI client shipped with this family.

The family vendors the Amazon CLI source under `src/agent_toolbelt_amazon_cli/assets/amazon-intent-cli` and delegates commands to that client with `uv run --project`. It does not copy managed browser sessions, browser profiles, cookies, or local runtime storage. The bridge routes uv's project environment to local runtime storage so the bundled source tree stays clean after use.

```powershell
uv run agent-toolbelt-amazon-cli -- inspect-identifier https://www.amazon.de/dp/B0F2JCZPB4 --marketplace de
uv run agent-toolbelt-amazon-cli -- offers B0F2JCZPB4 --marketplace de --marketplaces de,fr,es
uv run agent-toolbelt-amazon-cli -- reviews B0F2JCZPB4 --marketplace de --portal retail --limit 20
```

Use `inspect-identifier` before `get`, `offers`, `reviews`, or cart operations when the input is a URL or ambiguous ASIN. The bridge also promotes advisory warnings from offer trust signals, search variant/partial-result signals, and review fallback/partial-result signals into the normalized top-level `warnings` array.
