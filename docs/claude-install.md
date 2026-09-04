# Claude install guide

Each runtime family ships its own self-contained local marketplace with one plugin. Instruction-only skills can be copied directly to the Claude-compatible personal skill root.

## Marketplace locations

- ADB Archive Transfer: `families/adb-archive-transfer/claude/marketplaces/agent-toolbelt-local`
- Transactional Cleanup: `families/transactional-cleanup/claude/marketplaces/agent-toolbelt-local`; run the family's `scripts/install.py` for its local runtime and personal skills.
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

- Specification-Gated Implementation: `families/spec-gated-implementation/codex/skills/spec-gated-implementation`

## Install flow

1. Open the family README you want.
2. Validate that family marketplace path with `claude plugins validate`.
3. Add that marketplace path with `claude plugins marketplace add ... --scope user`.
4. Install the single plugin exposed by that family marketplace.

For an instruction-only skill, copy its canonical folder directly into the Claude-compatible personal skills directory instead of creating a marketplace plugin.
