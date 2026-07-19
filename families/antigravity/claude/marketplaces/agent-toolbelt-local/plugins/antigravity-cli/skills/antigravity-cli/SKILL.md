---
name: antigravity-cli
description: Use the local Antigravity helper for independent exact-model review of an explicit plan, design, code-review, or evidence packet, with isolated OAuth/runtime state and no model fallback.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows/local CLI oriented; requires helper-owned CLIProxyAPI runtime and explicit Antigravity login.
---

# Antigravity CLI

Use `scripts/invoke_antigravity.py` to review one explicit UTF-8 packet. Run
`status`, `update --check`, `update`, interactive `login`, and `models` as
needed before `review`.

```powershell
python scripts/invoke_antigravity.py review --packet C:\path\review-packet.md --instruction "Review for requirement drift and missing tests." --model <exact-model-id>
```

Accept output only when `ok=true` and `model_verified=true`. On authentication
failure, request interactive login. On model capacity failure, wait and retry
the same exact model; never accept fallback. Login is foreground and unbounded,
so never time it out or kill it.

The helper owns `%LOCALAPPDATA%\Tools\antigravity-review`. Never touch or reuse
Claude's CLIProxyAPI binary, auth, config, process, or port `8317`; never expose
a general proxy or install persistence.
