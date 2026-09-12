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
2. Normalize the exact requested skill name and check the advertised registry first.
3. Check exact local locations without broadly loading every skill: repository-local `.codex/skills` and `.claude/skills`, `$CODEX_HOME/skills`, `$CODEX_HOME/skills.disabled`, `~/.agents/skills`, `~/.agents/skills.disabled`, and `~/.claude/skills`. Confirm the `name` in `SKILL.md`, not only the folder name.
4. If an active local copy exists but is not advertised, do not install a duplicate. Report an advertisement, enablement, or skill-cap problem. After validating the file, it may be read as repository guidance for the current task, but do not claim it became advertised mid-task.
5. If only a disabled copy exists, report that exact source and route restoration through the user's current authorization. Account for the active-skill cap before enabling it.
6. If no exact local copy exists, run the scout with the exact skill name as the first `--query`, then relevant domain terms. Inspect the candidate `SKILL.md` and source before recommending it.
7. Route an approved exact installation through `skill-installer`, then validate the installed skill. A repository reference is authorization to search and inspect; it is not blanket authorization to install an arbitrary third-party result. Existing user authorization or an authoritative setup instruction must identify or cover the exact source.
8. If a mandatory skill cannot be resolved or safely installed, record a blocker. Only apply equivalent guidance directly when the repository makes the skill optional and supplies the complete rule locally; identify that fallback explicitly.

## Rules

- Run the helper before designing new skill behavior when a public alternative may already exist.
- Treat install counts and official publishers as evidence, not automatic winners.
- Preserve local-first, fail-closed, read-only, and explicit-confirmation behavior as positive differentiators.
- Do not install, remove, or mutate skills from this helper's recommendation alone.
- Do not recommend account-backed or mutation-capable public skills unless the user accepts that trust model.
- Prefer an exact-name direct match over a popular partial match when resolving a repository requirement.

## Script Interface

```bash
python scripts/invoke_skills_sh_scout.py scout --workflow "<requested workflow>" [--query "<query>"] [--compare-local-skill <name>] [--max-candidates <n>] [--max-inspect <n>] [--output <report.json>]
```

Use repeated `--query` values for important exact search terms. Use `--compare-local-skill` when evaluating an existing local skill.

## Output Use

Read the JSON `recommendation`, `candidates`, `inspected_candidates`, `warnings`, and `capped_queries`. If a query is capped, run again with narrower explicit `--query` values before making a final deprecation or replacement recommendation.
