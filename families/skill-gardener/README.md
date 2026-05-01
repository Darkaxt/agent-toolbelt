# Skill Gardener

`agent-toolbelt-skill-gardener` scans recent Codex rollout history and stages review-only Agent Skill proposals.

It is intentionally not a public skills.sh skill in this phase. The package is a local maintenance utility for producing better proposals than the old keyword-based local script.

## Usage

```powershell
agent-toolbelt-skill-gardener scan --since-days 14 --max-sessions 30
```

Dry run:

```powershell
agent-toolbelt-skill-gardener scan --dry-run
```

Default output:

```text
.\skill-proposals\<timestamp>\
  REPORT.md
  manifest.json
  new-skills\<skill-name>\SKILL.md
  patches\<skill-name>.md
```

## Safety

- Proposal-only: never installs, edits, deletes, or archives active skills.
- System, plugin-cache, public, and repo-managed skills are treated as off-limits for direct mutation.
- New skill proposals require local coverage checks and a `skills-sh-scout` public-alternative gate.
- Existing-skill patch proposals must include concrete suggested instruction text.
