# Skills.sh Scout Family

Public-alternative discovery for agent skill creation and expansion.

Use this family when you want a repeatable skills.sh check before building,
expanding, or deprecating a skill. The helper queries skills.sh, dedupes
candidates, optionally inspects public GitHub `SKILL.md` files, and returns an
advisory JSON recommendation.

CLI:

```bash
uv run --package agent-toolbelt-skills-sh-scout agent-toolbelt-skills-sh-scout scout --workflow "create a skill for Python package management" --query uv
```

The helper is advisory only. It does not install, remove, or mutate skills.
