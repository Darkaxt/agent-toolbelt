# agent-toolbelt

`agent-toolbelt` is a family-first monorepo for local agent utilities and lightweight instruction-only workflows.

Start by choosing the one family you actually need:

| Family | Use it for | Folder | Primary CLI |
| --- | --- | --- | --- |
| F3D Viewer | visual model reading with F3D; measured scene/rig inspection through the existing Blender gate | `families/f3d-viewer` | installed F3D console |
| ReCodex Policy Diagnostics | explain blocked PowerShell execution and record cybersecurity rejections in the existing private ledger | `families/recodex-policy-diagnostics` | installed Inspector CLI |
| Cybersecurity Orchestrator | focused routing to existing security workflows and corrected investigative references | `families/cybersecurity-orchestrator` | - |
| FedEx Tracking | read-only public tracking, travel history and package versus shipment facts | `families/fedex-tracking` | - |
| Diagnostics-First UI | app-owned debugging actions, rendered state and measured UI readiness instead of screenshot polling | `families/ui-diagnostics-first` | - |
| Windows Elevation Gate | FIFO administrator prompts with top-most explanation, Accept/Cancel and user feedback | `families/windows-elevation-gate` | `agent-toolbelt-windows-elevation-gate` |
| ADB Archive Transfer | endpoint-bound Android file transfer with uncompressed tiny-file bundles, direct large-file transfer, and manifest verification | `families/adb-archive-transfer` | `agent-toolbelt-adb-archive-transfer` |
| Gradle Build Gate | shared Windows Gradle build serialization and evidence-backed low-memory supervision | `families/gradle-build-gate` | `agent-toolbelt-gradle-build-gate` |
| Antigravity Review | independent exact-model review plus bounded public-page and prepared-video evidence analysis | `families/antigravity` | `agent-toolbelt-antigravity` |
| Amazon CLI | Amazon product search, specs, reviews, offers, and managed session workflows through a bundled Amazon CLI client | `families/amazon-cli` | `agent-toolbelt-amazon-cli` |
| Skroutz CLI | Skroutz.cy product search, offers, reviews, comparisons, and safe cart workflows | `families/skroutz-cli` | `agent-toolbelt-skroutz-cli` |
| AliExpress CLI | AliExpress product search, item details, reviews/comments, price and delivery evidence, and optional managed logged-in read-only browsing | `families/aliexpress-cli` | `agent-toolbelt-aliexpress-cli` |
| Codex Thread Recall | bounded self-recall from the current Codex thread's own raw rollout history before broad exploration | `families/codex-thread-recall` | `agent-toolbelt-codex-thread-recall` |
| Context Transfer | independent single-chat transfer or multi-chat consolidation, verified rollout/database archives, exact retirement and restore | `families/context-transfer` | `agent-toolbelt-context-transfer` |
| Transactional Cleanup | reviewed generated-output snapshots and Windows identity-bound deletion tickets | `families/transactional-cleanup` | `agent-toolbelt-transactional-cleanup` |
| C-Drive Maintenance | active lifecycle-specific cleanup and compatible toolchain consolidation with existing task owners | `families/c-drive-maintenance` | `agent-toolbelt-c-drive-maintenance` |
| D-Temp Maintenance | owner-driven sweeps and verified cleanup of agent temporary clones, worktrees and outputs | `families/d-temp-maintenance` | - |
| Everything | global filename and path lookup | `families/everything` | `agent-toolbelt-everything` |
| LinkedIn CV | local read-only LinkedIn profile evidence capture and CV/profile gap comparisons | `families/linkedin-cv` | `agent-toolbelt-linkedin-cv` |
| Media | transcript-first public video analysis preparation and local media operations | `families/media` | `agent-toolbelt-media` |
| Observable Reputation | passive reputation checks for URL, domain, and IP observables | `families/observable-reputation` | `agent-toolbelt-observable-reputation` |
| Outlook Classic Mail | local mail access through Outlook Classic COM with multi-account support | `families/outlook-classic-mail` | `agent-toolbelt-outlook-classic-mail` |
| Mail Domain Quarantine | Outlook mail domain-risk reports and confirmed quarantine moves | `families/mail-domain-quarantine` | `agent-toolbelt-mail-domain-quarantine` |
| WhatsApp wacli | experimental local WhatsApp access through a curated `wacli` adapter | `families/whatsapp-wacli` | `agent-toolbelt-whatsapp-wacli` |
| Skills.sh Scout | public skill alternative discovery before creating or expanding skills | `families/skills-sh-scout` | `agent-toolbelt-skills-sh-scout` |
| Specification-Gated Implementation | staged implementation with repeated specification reconciliation and zero unresolved deferrals at completion | `families/spec-gated-implementation` | - |
| Operational Recordkeeping | event-scoped reconciliation of existing bills, correspondence, decisions and purchases | `families/operational-recordkeeping` | bundled Python helper |
| Approach Recovery Ledger | shared dated execution plans, interruption evidence and preserved acceptance criteria | `families/approach-recovery-ledger` | bundled Python helper |
| Thread Cleanup | permanent exact inactive conversation retirement, database and session artifacts | `families/thread-cleanup` | bundled Python helper |

## Install skills

The canonical skills.sh package is this repository:

```powershell
npx skills add Darkaxt/agent-toolbelt --list
npx skills add Darkaxt/agent-toolbelt --skill codex-thread-recall
npx skills add Darkaxt/agent-toolbelt --all
```

Public skill names:

- `f3d-viewer`
- `recodex-policy-diagnostics`
- `cybersecurity-orchestrator`
- `fedex-tracking`
- `adb-archive-transfer`
- `ui-diagnostics-first`
- `windows-elevation-gate`
- `gradle-build-gate`
- `amazon-cli`
- `skroutz-cli`
- `aliexpress-cli`
- `codex-thread-recall`
- `context-transfer`
- `transactional-cleanup`
- `c-drive-maintenance`
- `d-temp-maintenance`
- `everything-search`
- `antigravity-cli`
- `linkedin-cv`
- `mail-domain-quarantine`
- `yt-dlp-ffmpeg`
- `observable-reputation`
- `outlook-classic-mail`
- `whatsapp-wacli`
- `skills-sh-scout`
- `spec-gated-implementation`
- `operational-recordkeeping`
- `approach-recovery-ledger`
- `thread-cleanup`

Read [Publishing and installing from skills.sh](docs/skills-sh.md) before installing account-backed or local-machine skills. Several skills require Windows desktop apps, local CLIs, or explicit user confirmation before visible actions.

## Repo layout

- `families/`: independent tool families with their own package where needed, tests, and agent integrations; instruction-only families intentionally omit a runtime package
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
