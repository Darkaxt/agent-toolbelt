# Skills.sh Scout Family

Public-alternative discovery for missing repository-required skills, skill creation, and expansion.

Use this family when you want a repeatable skills.sh check before building,
expanding, deprecating, or resolving a named unavailable skill. The helper queries skills.sh, dedupes
candidates, optionally inspects public GitHub `SKILL.md` files, and returns an
advisory JSON recommendation.

CLI:

```bash
uv run --package agent-toolbelt-skills-sh-scout agent-toolbelt-skills-sh-scout scout --workflow "create a skill for Python package management" --query uv
```

The skill first checks exact local and disabled locations. When no local copy exists, the helper provides the public discovery result and the skill routes an approved exact candidate through the platform `skill-installer`. The helper itself remains advisory and does not install, remove, or mutate skills.
