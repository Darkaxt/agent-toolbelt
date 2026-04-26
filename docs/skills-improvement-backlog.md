# Skill improvement backlog

Generated: 2026-04-26
Updated: 2026-04-26

This backlog turns the skills.sh alternative analysis into actionable follow-up
work. It is intentionally tied to `docs/skills-sh-alternatives.md` and should
be updated when that analysis changes.

Install counts and official publishers are useful evidence, but they are not
automatic replacement criteria. Local-first behavior, fail-closed safety,
explicit confirmation gates, and exact platform fit count as first-class
features for this repo.

## P1 - Active next improvements

### `skill-creator` and `skills-sh-scout`

- Current verdict: `skills-sh-scout` now exists as the repo-backed public discovery helper.
- Public inspirations: skills.sh search workflows, marketplace comparison tables, and public-source inspection before new skill design.
- Improvement requests: update the local/system `skill-creator` instructions so new skill creation and major skill expansion start with `skills-sh-scout` when the workflow may already exist publicly.
- Avoid: bloating `skill-creator` with marketplace logic or letting `skills-sh-scout` install, remove, or mutate skills.
- Recommended next action: integrate. Keep `skills-sh-scout` as the separate discovery gate and make `skill-creator` call it before design work.

### `whatsapp-wacli`

- Current verdict: strong direct competitors exist.
- Public candidates: `steipete/clawdis/wacli`, `gokapso` WhatsApp Business/API skills, WhatsApp Cloud/API and `whatsapp-web.js` skills.
- Improvement requests: explicitly document why the curated adapter remains useful compared with raw `wacli`: structured JSON, PN-vs-LID resolution, bounded backfill, seed-missing diagnostics, and explicit confirmation gates for visible actions.
- Avoid: raw passthrough that bypasses safety gates, WhatsApp Business API scope creep, session packaging, or visible sends without exact confirmation.
- Recommended next action: improve positioning and usage guidance. Keep the helper if the structured layer materially improves reliability over raw CLI calls.

### `linkedin-cv`

- Current verdict: partial alternatives exist.
- Public inspirations: LinkedIn profile optimizer, resume tailor, personal branding, and recruiter-visibility skills.
- Improvement requests: add clearer analysis templates for profile-section scoring, recruiter-visibility checks, evidence inventory, CV/profile delta reporting, and truthful rewrite prompts grounded in captured snapshots.
- Avoid: LinkedIn automation, engagement actions, scraping at scale, lead generation, generic profile advice detached from evidence, or pretending public optimizer skills replace local profile evidence capture.
- Recommended next action: improve positioning and analysis templates, not automation.

## P2 - Useful but larger or lower urgency

### `outlook-classic-mail`

- Current verdict: partial alternatives exist.
- Public candidates: `membranedev/application-skills/microsoft-outlook`, Rube/Composio Outlook automation skills, M365/Graph mail skills, IMAP/SMTP mail skills.
- Improvement requests: consider an optional Graph/M365 fallback only if local Outlook Classic is unavailable; improve diagnostics that distinguish local COM queue issues from connector-style mail access.
- Avoid: silently switching trust models from local Outlook Classic COM to cloud mailbox APIs, or performing draft/send/move/delete actions without confirmation.
- Recommended next action: keep as local-first. Treat cloud connector parity as a separate design, not an incremental patch.

### `gemini-cli`

- Current verdict: partial alternatives exist.
- Public candidates: official Google Gemini API/dev/interactions/live skills, `steipete/clawdis/gemini`, URL-to-Markdown and YouTube summarizer skills.
- Improvement requests: keep public URL/Gemini CLI inspection narrow; add clearer routing to official Google skills for API/app development; consider a URL-to-Markdown fallback when Gemini cannot inspect a public page.
- Avoid: reverse-engineered Gemini Web API flows, private/local URL submission, or broad Gemini app-development guidance.
- Recommended next action: keep and clarify routing.

### `everything-search`

- Current verdict: no meaningful direct alternative found.
- Public candidates: generic `fd`/`rg` file-search skills, RAG/file-ingest skills, desktop-search-adjacent skills.
- Improvement requests: document the difference between global Windows filename/path discovery and repo-local content search; add clearer fallback diagnostics if Everything or `es.exe` is missing.
- Avoid: turning this into a content grep, RAG indexer, or cross-platform promise.
- Recommended next action: keep. No urgent feature work.

## Watch list

### `codex-thread-recall`

- Current verdict: strong direct competitors exist.
- Public inspirations: `arjunkmrm/recall`, CASS, Supermemory, session-log and episodic-memory skills.
- Improvement requests: continue evaluating broad-history UX ideas such as transcript-reader ergonomics, optional importers, query-language polish, and search-result explainability.
- Avoid: losing exact current-thread fail-closed semantics, making imported memory a default recall source, or becoming a cloud memory system.
- Recommended next action: keep. Improve only where public recall tools expose clear audit/search UX gaps.

### `xsoar-development`

- Current verdict: partial alternatives exist.
- Public candidates: `membranedev/application-skills/cortex-xsoar`, generic SOAR workflow skills.
- Improvement requests: document live XSOAR connector skills as complements, not replacements; continue improving content-pack artifact correctness and private-overlay guidance in the separate `xsoar-development` repo.
- Avoid: mixing live XSOAR mutation workflows into a content-development guidance skill.
- Recommended next action: keep. Consider a separate live-operations helper only if needed.

## Completed or de-emphasized

### `uvrun-python`

- Decision: removed from `agent-toolbelt`; use the official Astral `uv` skill for general uv guidance.
- Follow-up: no active repo work remains unless the public skill landscape changes.

### `yt-dlp-ffmpeg`

- Decision: improved in this repo.
- Completed work: URL classification, metadata-only inspection, normalized formats, explicit playlist controls, safer refusal output, and discovery-first skill guidance.
- Follow-up: revisit only if future public media skills expose safer editing presets worth adapting.

### `amazon-cli`

- Decision: improved in this repo.
- Completed work: read-only `inspect-identifier`, advisory warnings for offers, search variant/partial-result signals, and review fallback/partial-result evidence.
- Follow-up: avoid seller/FBA scope creep; future work should stay read-only or explicitly confirmed.

### `observable-reputation`

- Decision: improved in this repo.
- Completed work: normalization, auto-detection, provider diagnostics, per-observable explanations, CSV export, STIX export, and v2 cache-key separation.
- Follow-up: keep passive-only; add providers only when they do not submit, scan, upload, or mutate reputation systems.

### `mail-domain-quarantine`

- Decision: improved in this repo.
- Completed work: compatibility with `observable-reputation` v2 payloads, normalized values, provider summaries, explanations, diagnostics, and rejected-observable reporting while keeping reputation report-only.
- Follow-up: minor report-language polish is acceptable, but reputation verdicts must not create apply-mode move decisions.

### `skills-sh-scout`

- Decision: implemented as a public package-backed helper skill.
- Completed work: skills.sh API discovery, candidate dedupe, public GitHub inspection, recommendation categories, Codex/Claude skill bundles, docs, and validation wiring.
- Follow-up: keep it advisory only; route `skill-creator` through it rather than merging marketplace discovery into `skill-creator`.

## Validation checklist

- Every module from `docs/skills-sh-alternatives.md` has an active, completed, or watch entry here.
- No local-first skill is marked for deprecation solely because a public skill has more installs.
- Replacement recommendations require workflow fit, safety fit, and no meaningful local-only advantage.
- Public skills are used for inspiration only when their feature ideas preserve this repo's safety posture.
