# Claude install guide

Each runtime family ships its own self-contained local marketplace with one plugin. Instruction-only skills can be copied directly to the Claude-compatible personal skill root.

## Marketplace locations

- ADB Archive Transfer: `families/adb-archive-transfer/claude/marketplaces/agent-toolbelt-local`
- Gradle Build Gate: `families/gradle-build-gate/claude/marketplaces/agent-toolbelt-local`; the family's `scripts/install.py` also deploys the shared runtime and personal Claude skill.
- Transactional Cleanup: `families/transactional-cleanup/claude/marketplaces/agent-toolbelt-local`; run the family's `scripts/install.py` for its local runtime and personal skills.
- C-Drive Maintenance: `families/c-drive-maintenance/claude/marketplaces/agent-toolbelt-local`; run the family's `scripts/install.py` for the shared runtime and personal skills.
- Antigravity Review: `families/antigravity/claude/marketplaces/agent-toolbelt-local`
- Everything: `families/everything/claude/marketplaces/agent-toolbelt-local`
- Media: `families/media/claude/marketplaces/agent-toolbelt-local`
- Outlook Classic Mail: `families/outlook-classic-mail/claude/marketplaces/agent-toolbelt-local`
- Observable Reputation: `families/observable-reputation/claude/marketplaces/agent-toolbelt-local`
- Mail Domain Quarantine: `families/mail-domain-quarantine/claude/marketplaces/agent-toolbelt-local`
- LinkedIn CV: `families/linkedin-cv/claude/marketplaces/agent-toolbelt-local`
- Skills.sh Scout: `families/skills-sh-scout/claude/marketplaces/agent-toolbelt-local`
- Skroutz CLI: `families/skroutz-cli/claude/marketplaces/agent-toolbelt-local`
- AliExpress CLI: `families/aliexpress-cli/claude/marketplaces/agent-toolbelt-local`

## Instruction-only skills

- Diagnostics-First UI: `families/ui-diagnostics-first/codex/skills/ui-diagnostics-first`; copy the same canonical folder. No plugin, helper or application changes are installed.

- Specification-Gated Implementation: `families/spec-gated-implementation/codex/skills/spec-gated-implementation`
- D-Temp Maintenance: `families/d-temp-maintenance/codex/skills/d-temp-maintenance`; use the identical canonical skill with the installed transactional-cleanup helper.

## Install flow

Windows Elevation Gate: run `python families/windows-elevation-gate/scripts/install.py`
to deploy its shared runtime and identical agent-neutral personal skills. Its canonical
folder is `families/windows-elevation-gate/codex/skills/windows-elevation-gate`;
no Claude plugin or application settings change is required.

Operational Recordkeeping: copy the same agent-neutral
`families/operational-recordkeeping/codex/skills/operational-recordkeeping` folder
to the personal Claude skills directory. It includes its own standard-library
helper and needs no plugin, repository bootstrap or account credentials.

1. Open the family README you want.
2. Validate that family marketplace path with `claude plugins validate`.
3. Add that marketplace path with `claude plugins marketplace add ... --scope user`.
4. Install the single plugin exposed by that family marketplace.

For an instruction-only skill, copy its canonical folder directly into the Claude-compatible personal skills directory instead of creating a marketplace plugin.
