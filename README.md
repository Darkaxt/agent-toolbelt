# agent-toolbelt

`agent-toolbelt` is a family-first monorepo for local agent utilities.

Start by choosing the one family you actually need:

| Family | Use it for | Folder | Primary CLI |
| --- | --- | --- | --- |
| Amazon CLI | Amazon product search, specs, reviews, offers, and managed session workflows through a bundled Amazon CLI client | `families/amazon-cli` | `agent-toolbelt-amazon-cli` |
| Codex Thread Recall | bounded self-recall from the current Codex thread's own raw rollout history before broad exploration | `families/codex-thread-recall` | `agent-toolbelt-codex-thread-recall` |
| Everything | global filename and path lookup | `families/everything` | `agent-toolbelt-everything` |
| Gemini | public URL inspection and Codex research cross-checks | `families/gemini` | `agent-toolbelt-gemini` |
| LinkedIn CV | local read-only LinkedIn profile evidence capture and CV/profile gap comparisons | `families/linkedin-cv` | `agent-toolbelt-linkedin-cv` |
| Media | public media download and local media file operations | `families/media` | `agent-toolbelt-media` |
| Observable Reputation | passive reputation checks for URL, domain, and IP observables | `families/observable-reputation` | `agent-toolbelt-observable-reputation` |
| Outlook Classic Mail | local mail access through Outlook Classic COM with multi-account support | `families/outlook-classic-mail` | `agent-toolbelt-outlook-classic-mail` |
| Mail Domain Quarantine | Outlook mail domain-risk reports and confirmed quarantine moves | `families/mail-domain-quarantine` | `agent-toolbelt-mail-domain-quarantine` |
| UVRun | internal standalone local Python script routing through `uvrun.ps1` | `families/uvrun` | `agent-toolbelt-uvrun` |
| WhatsApp wacli | experimental local WhatsApp access through a curated `wacli` adapter | `families/whatsapp-wacli` | `agent-toolbelt-whatsapp-wacli` |

## Install skills

The canonical skills.sh package is this repository:

```powershell
npx skills add Darkaxt/agent-toolbelt --list
npx skills add Darkaxt/agent-toolbelt --skill codex-thread-recall
npx skills add Darkaxt/agent-toolbelt --all
```

Public skill names:

- `amazon-cli`
- `codex-thread-recall`
- `everything-search`
- `gemini-cli`
- `linkedin-cv`
- `mail-domain-quarantine`
- `yt-dlp-ffmpeg`
- `observable-reputation`
- `outlook-classic-mail`
- `whatsapp-wacli`

Read [Publishing and installing from skills.sh](docs/skills-sh.md) before installing account-backed or local-machine skills. Several skills require Windows desktop apps, local CLIs, or explicit user confirmation before visible actions.

## Repo layout

- `families/`: independent tool families with their own package, tests, and agent integrations where stable; some families are intentionally Codex-only
- `packages/core/`: shared helpers and packaged assets
- `docs/`: cross-cutting install and prerequisite guidance
- `tests/`: repo-level layout, isolation, and portability checks

## How to use this repo

1. Read [Windows prerequisites](docs/windows-prerequisites.md)
2. Open the family folder you want
3. Follow that family README for CLI usage and agent integrations

## Cross-cutting guides

- [Codex install guide](docs/codex-install.md)
- [Claude install guide](docs/claude-install.md)
- [skills.sh guide](docs/skills-sh.md)
