# agent-toolbelt

`agent-toolbelt` is a family-first monorepo for local agent utilities.

Start by choosing the one family you actually need:

| Family | Use it for | Folder | Primary CLI |
| --- | --- | --- | --- |
| Gemini | public URL inspection and Codex research cross-checks | `families/gemini` | `agent-toolbelt-gemini` |
| Everything | global filename and path lookup | `families/everything` | `agent-toolbelt-everything` |
| UVRun | standalone local Python script routing through `uvrun.ps1` | `families/uvrun` | `agent-toolbelt-uvrun` |
| Media | public media download and local media file operations | `families/media` | `agent-toolbelt-media` |
| Outlook Classic Mail | local mail access through Outlook Classic COM with multi-account support | `families/outlook-classic-mail` | `agent-toolbelt-outlook-classic-mail` |
| WhatsApp Local Read | read-only WhatsApp Desktop visible-chat follow-up support | `families/whatsapp-local-read` | `agent-toolbelt-whatsapp-local-read` |

## Repo layout

- `families/`: independent tool families with their own package, tests, Codex skill, and Claude plugin
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
