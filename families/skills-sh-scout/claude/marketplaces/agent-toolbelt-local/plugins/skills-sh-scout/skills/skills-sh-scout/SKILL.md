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

Run:

```bash
python scripts/invoke_skills_sh_scout.py scout --workflow "<requested workflow>" [--query "<query>"] [--compare-local-skill <name>]
```

Treat the JSON recommendation as advisory. The helper does not install, remove, or mutate skills.
