# Codex install guide

Windows Elevation Gate: run `python families/windows-elevation-gate/scripts/install.py`.
This installs the shared runtime and canonical
`families/windows-elevation-gate/codex/skills/windows-elevation-gate` for Codex and Claude.

Each runtime family ships its own Codex skill bundle. Instruction-only skills use one canonical cross-agent directory. Install only what you want.

## Skill locations

- Diagnostics-First UI: `families/ui-diagnostics-first/codex/skills/ui-diagnostics-first`; copy the identical instruction-only folder to personal Codex, agents and Claude skill roots. No runtime or settings changes.

- ADB Archive Transfer: `families/adb-archive-transfer/codex/skills/adb-archive-transfer`
- Gradle Build Gate: run `python families/gradle-build-gate/scripts/install.py` for shared runtime and Codex/Claude personal skill deployment.
- Antigravity Review: `families/antigravity/codex/skills/antigravity-cli`
- Everything: `families/everything/codex/skills/everything-search`
- Media: `families/media/codex/skills/yt-dlp-ffmpeg`
- Outlook Classic Mail: `families/outlook-classic-mail/codex/skills/outlook-classic-mail`
- Observable Reputation: `families/observable-reputation/codex/skills/observable-reputation`
- Mail Domain Quarantine: `families/mail-domain-quarantine/codex/skills/mail-domain-quarantine`
- LinkedIn CV: `families/linkedin-cv/codex/skills/linkedin-cv`
- Codex Thread Recall: `families/codex-thread-recall/codex/skills/codex-thread-recall`
- Context Transfer: `families/context-transfer/codex/skills/context-transfer`
- Transactional Cleanup: run `python families/transactional-cleanup/scripts/install.py` for the independent runtime and Codex/Claude skill deployment.
- C-Drive Maintenance: run `python families/c-drive-maintenance/scripts/install.py` for its helper and identical Codex, agents and Claude personal skills.
- Skills.sh Scout: `families/skills-sh-scout/codex/skills/skills-sh-scout`
- Skroutz CLI: `families/skroutz-cli/codex/skills/skroutz-cli`
- AliExpress CLI: `families/aliexpress-cli/codex/skills/aliexpress-cli`
- Specification-Gated Implementation: `families/spec-gated-implementation/codex/skills/spec-gated-implementation`
- D-Temp Maintenance: `families/d-temp-maintenance/codex/skills/d-temp-maintenance`; copy the same canonical folder to Codex, agents or Claude personal roots. Uses installed transactional-cleanup, not a new runtime.
- Approach Recovery Ledger: `families/approach-recovery-ledger/codex/skills/approach-recovery-ledger`; copy the identical self-contained Python bundle to the personal Codex or agents skill root. Installation does not connect a live recovery controller or change account settings.

## Install flow

Operational Recordkeeping: copy
`families/operational-recordkeeping/codex/skills/operational-recordkeeping` to the
personal skills directory. Its bundled helper needs no checkout bootstrap. Keep
private profiles outside the bundle as described in the family README.

1. Open the family README you want.
2. Copy that family skill folder into your Codex home skills directory.
3. Keep the clone intact so the wrapper scripts can bootstrap the matching family package plus `packages/core`.
