---
name: skills-sh-scout
description: Use `scripts/invoke_skills_sh_scout.py` to query skills.sh before creating, replacing, or materially expanding an agent skill. Returns public alternatives, direct-vs-partial classification, design inspirations, and an install/reuse/improve/create recommendation without installing or modifying skills.
license: MIT
compatibility: Requires public internet access to skills.sh and GitHub. Advisory only; does not install, remove, or mutate skills.
metadata:
  version: "0.1.0"
---

# Skills.sh Scout

Use this skill before creating a new skill, expanding an existing skill, or deciding whether a local skill should be replaced by a public one.

## Rules

- Run the helper before designing new skill behavior when a public alternative may already exist.
- Treat install counts and official publishers as evidence, not automatic winners.
- Preserve local-first, fail-closed, read-only, and explicit-confirmation behavior as positive differentiators.
- Do not install, remove, or mutate skills from this helper's recommendation alone.
- Do not recommend account-backed or mutation-capable public skills unless the user accepts that trust model.

## Script Interface

```bash
python scripts/invoke_skills_sh_scout.py scout --workflow "<requested workflow>" [--query "<query>"] [--compare-local-skill <name>] [--max-candidates <n>] [--max-inspect <n>] [--output <report.json>]
```

Use repeated `--query` values for important exact search terms. Use `--compare-local-skill` when evaluating an existing local skill.

## Output Use

Read the JSON `recommendation`, `candidates`, `inspected_candidates`, `warnings`, and `capped_queries`. If a query is capped, run again with narrower explicit `--query` values before making a final deprecation or replacement recommendation.
