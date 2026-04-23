# Claude install guide

Each family ships its own self-contained local marketplace with one plugin.

## Marketplace locations

- Gemini: `families/gemini/claude/marketplaces/agent-toolbelt-local`
- Everything: `families/everything/claude/marketplaces/agent-toolbelt-local`
- UVRun: `families/uvrun/claude/marketplaces/agent-toolbelt-local`
- Media: `families/media/claude/marketplaces/agent-toolbelt-local`
- Outlook Classic Mail: `families/outlook-classic-mail/claude/marketplaces/agent-toolbelt-local`
- Observable Reputation: `families/observable-reputation/claude/marketplaces/agent-toolbelt-local`
- Mail Domain Quarantine: `families/mail-domain-quarantine/claude/marketplaces/agent-toolbelt-local`
- LinkedIn CV: `families/linkedin-cv/claude/marketplaces/agent-toolbelt-local`

## Install flow

1. Open the family README you want.
2. Validate that family marketplace path with `claude plugins validate`.
3. Add that marketplace path with `claude plugins marketplace add ... --scope user`.
4. Install the single plugin exposed by that family marketplace.
