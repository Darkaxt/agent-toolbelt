# Codex install guide

Each family ships its own Codex skill bundle. Install only the family you want.

## Skill locations

- Gemini: `families/gemini/codex/skills/gemini-cli`
- Everything: `families/everything/codex/skills/everything-search`
- Media: `families/media/codex/skills/yt-dlp-ffmpeg`
- Outlook Classic Mail: `families/outlook-classic-mail/codex/skills/outlook-classic-mail`
- Observable Reputation: `families/observable-reputation/codex/skills/observable-reputation`
- Mail Domain Quarantine: `families/mail-domain-quarantine/codex/skills/mail-domain-quarantine`
- LinkedIn CV: `families/linkedin-cv/codex/skills/linkedin-cv`
- Codex Thread Recall: `families/codex-thread-recall/codex/skills/codex-thread-recall`
- Skills.sh Scout: `families/skills-sh-scout/codex/skills/skills-sh-scout`
- Skroutz CLI: `families/skroutz-cli/codex/skills/skroutz-cli`

## Install flow

1. Open the family README you want.
2. Copy that family skill folder into your Codex home skills directory.
3. Keep the clone intact so the wrapper scripts can bootstrap the matching family package plus `packages/core`.
