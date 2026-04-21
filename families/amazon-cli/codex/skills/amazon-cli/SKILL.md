---
name: amazon-cli
description: Use the local Amazon CLI for Amazon product search, exact model lookup, product specs, comparisons, review/comment extraction, cross-market offers, and managed retail or business sessions. Trigger when Codex needs Amazon marketplace data, same-ASIN price comparisons, deep Amazon reviews, or Amazon session login support.
---

# Amazon CLI

## Overview

Use `scripts/invoke_amazon_cli.py` to call the bundled Amazon CLI client. The wrapper delegates into the `amazon-cli` family package in this repo, which runs the packaged client under `agent_toolbelt_amazon_cli/assets/amazon-intent-cli`.

This skill vendors the Amazon CLI source code, but must not package browser profiles, cookies, managed sessions, generated virtual environments, or user account data. Runtime state stays outside the repo.

## Routing Rules

Use this skill when:

- The user asks for Amazon product search, exact model lookup, specs, comparisons, reviews/comments, or same-ASIN cross-market offers.
- The user asks to use managed Amazon retail or business sessions for deep reviews.
- The task is read-only Amazon browsing, extraction, ranking, or summarization.

Do not use this skill when:

- The task is not about Amazon marketplaces.
- The user asks to buy, add to cart, checkout, submit feedback, submit reviews, or mutate an Amazon account.
- The user needs general shopping research outside the locally supported Amazon CLI workflows.

## Behavior

- Prefer read-only commands: `search`, `similar`, `get`, `compare`, `reviews`, and `offers`.
- Run `session login` only when the user can interact with a headed managed browser.
- Do not add products to cart, do not checkout, do not submit reviews, and do not submit forms beyond explicit login.
- For exact product search, use `search <base> --brand <brand> --model <model>`; bare queries like `search "LG C4"` are plain search.
- Use `--pages` only with `search` and `similar`, and keep the CLI maximum in mind.
- For deep reviews, use managed sessions first: `session login --marketplace <code> --portal retail` or `--portal business`.
- For `offers`, inspect title/model/size signals and any variant mismatch warnings before calling an offer trusted or cheapest.
- Keep marketplace query language explicit; do not assume the CLI translates product terms.

## Script Interface

```bash
python scripts/invoke_amazon_cli.py -- search "tv" --brand LG --model C4 --marketplace de --max-price 560 --pages 2
python scripts/invoke_amazon_cli.py -- search "microondas" --marketplace es --max-price 100
python scripts/invoke_amazon_cli.py -- get https://www.amazon.de/dp/B0F2JCZPB4 --marketplace de
python scripts/invoke_amazon_cli.py -- compare https://www.amazon.de/dp/B0F2JCZPB4 https://www.amazon.fr/dp/B0F2JCZPB4
python scripts/invoke_amazon_cli.py -- reviews B0F2JCZPB4 --marketplace de --portal retail --limit 20
python scripts/invoke_amazon_cli.py -- offers B0F2JCZPB4 --marketplace de --marketplaces de,fr,es,uk
python scripts/invoke_amazon_cli.py -- session login --marketplace de --portal retail
```

The script prints normalized JSON with `ok`, `operation`, `result`, `warnings`, `stderr`, and `exit_code`.
