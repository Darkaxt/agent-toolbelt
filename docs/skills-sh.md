# Publishing and installing from skills.sh

`agent-toolbelt` is published for skills.sh as a GitHub-hosted skill package. There is no separate registry submission step: users install from the public repository with the `skills` CLI, and skills.sh can discover the package through install telemetry.

## Install

List the skills in this package:

```powershell
npx skills add Darkaxt/agent-toolbelt --list
```

Install one skill:

```powershell
npx skills add Darkaxt/agent-toolbelt --skill codex-thread-recall
```

Install all public skills:

```powershell
npx skills add Darkaxt/agent-toolbelt --all
```

Update installed skills:

```powershell
npx skills update
```

## Public skills

| Skill | Compatibility | Local prerequisites | Safety notes |
| --- | --- | --- | --- |
| `amazon-cli` | Windows/local CLI oriented | `agent-toolbelt-amazon-cli`; Amazon session setup for authenticated workflows | Authenticated retail or business sessions are user-managed. |
| `skroutz-cli` | Windows/local CLI oriented | `agent-toolbelt-skroutz-cli`; optional managed Skroutz session for cart workflows | Cart list is read-only; add/remove require explicit confirmation; no checkout or buy workflows. |
| `aliexpress-cli` | Windows/local CLI oriented | `agent-toolbelt-aliexpress-cli`; optional managed AliExpress session for logged-in read visibility | Read-only discovery only; no cart, checkout, buy, payment, address, order, wishlist, or review submission workflows. |
| `codex-thread-recall` | Codex only | `CODEX_THREAD_ID`, local Codex `state_5.sqlite`, readable rollout JSONL files | Current-thread first; workspace expansion is explicit. |
| `everything-search` | Windows only | Everything and `es.exe` for best results | Falls back safely when Everything is unavailable. |
| `gemini-cli` | Public URL inspection | Node.js/npm and `npx @google/gemini-cli` | Do not use for local files, private URLs, or private-network targets without explicit approval. |
| `linkedin-cv` | Local LinkedIn profile evidence capture and CV/profile comparison | Local package install and one explicit accessible LinkedIn profile capture | Read-only by default; no search traversal, scraping, content generation, or engagement automation. |
| `mail-domain-quarantine` | Windows Outlook Classic | Outlook Classic, mailbox access, RDAP/DNS reputation dependencies | Dry-run by default; mailbox moves require explicit confirmation. |
| `yt-dlp-ffmpeg` | Public media and local file operations | `yt-dlp`, `ffmpeg`, and `ffprobe` | Do not use to bypass access controls or private media restrictions. |
| `observable-reputation` | Passive OSINT only | Provider access as configured by the family | No active scans, URL submissions, file uploads, or phishing reports. |
| `outlook-classic-mail` | Windows Outlook Classic COM | Outlook Classic desktop profile and mailbox access | Reply, forward, move, and other mailbox actions require explicit confirmation. |
| `whatsapp-wacli` | Experimental local WhatsApp adapter | Local `wacli` setup and active WhatsApp session | WhatsApp-visible sends require explicit confirmation. |
| `skills-sh-scout` | skills.sh discovery helper | Public internet access to skills.sh and GitHub | Advisory only; it does not install, remove, or mutate skills. |

## Package shape

The canonical skills.sh install target is `Darkaxt/agent-toolbelt`. The `skills` CLI discovers the public Codex skill folders inside each family. Claude plugin copies remain repo artifacts for Claude marketplace packaging, but they are not the documented skills.sh target.

## Maintainer validation

Before advertising a release, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_skills_sh.ps1
```

The validator checks canonical skill frontmatter, name/folder matches, local-path leakage, and both local and GitHub `skills` CLI discovery. Set `DISABLE_TELEMETRY=1` when running ad hoc skills CLI checks outside the validator.
