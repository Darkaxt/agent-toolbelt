---
name: skills-sh-scout
description: Use when a repository instruction names a required skill that is missing, disabled, unavailable, or not advertised, and before creating, replacing, or materially expanding a skill. Resolve exact local and skills.sh candidates, inspect trust and coverage, and route installation without silently approximating required guidance.
license: MIT
metadata:
  compatibility: Requires public internet access to skills.sh and GitHub. Advisory only; does not install, remove, or mutate skills.
  version: "0.2.0"
---

# Skills.sh Scout

Use this skill when authoritative repository instructions reference a skill that is not available in the current registry, and before creating, expanding, or replacing a skill.

## Missing Required Skill

When a repository instruction names an unavailable skill:

1. Do not silently approximate its intent or announce that you will bypass it.
2. Normalize the exact requested name, check the advertised registry, and then check exact repository-local, `~/.codex/skills`, `~/.codex/skills.disabled`, `~/.agents/skills`, `~/.agents/skills.disabled`, and `~/.claude/skills` locations. Confirm `SKILL.md` frontmatter rather than trusting only the folder name.
3. If an active copy exists but is not advertised, do not install a duplicate. Report an advertisement, enablement, or skill-cap problem. A validated local file may be read as current-task repository guidance without claiming it became advertised.
4. If a disabled copy exists, route restoration through current user authorization and account for the active-skill cap.
5. If no local copy exists, run the scout with the exact name as the first query and inspect the candidate source and `SKILL.md`.
6. Route an approved exact installation through `skill-installer` and validate it. A repository reference is authorization to search and inspect, not blanket authorization to install an arbitrary third-party result; current authorization must cover the exact source.
7. If a mandatory skill remains unresolved, record a blocker. Use locally stated equivalent guidance only when the skill is optional and the complete rule is present.

Run:

```bash
python scripts/invoke_skills_sh_scout.py scout --workflow "<requested workflow>" [--query "<query>"] [--compare-local-skill <name>]
```

Treat the JSON recommendation as advisory. The helper does not install, remove, or mutate skills. Prefer exact-name direct matches over popular partial matches.
