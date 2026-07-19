---
name: antigravity-cli
description: Use the local Antigravity helper for independent exact-model review of an explicit plan, design, code-review, or evidence packet, with isolated OAuth/runtime state and no model fallback.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows/local CLI oriented; requires helper-owned CLIProxyAPI runtime and explicit Antigravity login.
---

# Antigravity CLI

Use `scripts/invoke_antigravity.py` for bounded independent review. This skill
reviews one explicit UTF-8 packet; it does not crawl the workspace, browse URLs,
or expose a general-purpose local proxy.

## Workflow

1. Run `status` when setup or authentication is uncertain.
2. Run `update --check`; use `update` only when the helper runtime is missing or an update is wanted.
3. Run `login` only as an explicit interactive setup step. Never impose a timeout, close its browser, or kill the login process.
4. Run `models` and select the exact model id required for the review.
5. Write the complete review packet to a file, then run `review` with that path, an explicit instruction, and the exact model id.
6. Accept a review only when `ok=true` and `model_verified=true`.

```powershell
python scripts/invoke_antigravity.py status
python scripts/invoke_antigravity.py update --check
python scripts/invoke_antigravity.py update
python scripts/invoke_antigravity.py login
python scripts/invoke_antigravity.py models
python scripts/invoke_antigravity.py review --packet C:\path\review-packet.md --instruction "Review for requirement drift, missing tests, and unsafe assumptions." --model <exact-model-id>
```

## Failure Rules

- If authentication is unavailable, stop and ask for the interactive `login` step.
- If the requested model is unavailable or capacity-limited, stop, wait, and retry the same exact model later. Never switch to a weaker model or accept fallback output.
- Treat `model_attribution_missing` and `model_mismatch` as failed review gates even when response text exists.
- Do not send private/local content unless the user explicitly selected the packet for review.

## Isolation

The helper owns `%LOCALAPPDATA%\Tools\antigravity-review` and an ephemeral
loopback process per command. Never read, alter, stop, restart, or reuse the
Claude CLIProxyAPI installation, auth state, process, configuration, or port
`8317`. Never create a scheduled task, service, startup entry, or persistent
proxy for this skill.
