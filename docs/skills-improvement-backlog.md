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

## Active next improvements

No repo-local P1/P2 implementation items are currently selected. Keep using
this file as the parking lot for future work that survives a `skills-sh-scout`
or skills.sh alternative review.

## Watch list

### `codex-thread-recall`

- Current verdict: strong direct competitors exist.
- Public inspirations: `arjunkmrm/recall`, CASS, Supermemory, session-log and episodic-memory skills.
- Improvement requests: continue evaluating broad-history UX ideas such as transcript-reader ergonomics, optional importers, query-language polish, and search-result explainability.
- Avoid: losing exact current-thread fail-closed semantics, making imported memory a default recall source, or becoming a cloud memory system.
- Recommended next action: keep. Improve only where public recall tools expose clear audit/search UX gaps.

### `outlook-classic-mail`

- Current verdict: partial alternatives exist.
- Public candidates: `membranedev/application-skills/microsoft-outlook`, Rube/Composio Outlook automation skills, M365/Graph mail skills, IMAP/SMTP mail skills.
- Future requests: consider an optional Graph/M365 fallback only if local Outlook Classic is unavailable.
- Avoid: silently switching trust models from local Outlook Classic COM to cloud mailbox APIs, or performing draft/send/move/delete actions without confirmation.
- Recommended next action: keep as local-first. Treat cloud connector parity as a separate design, not an incremental patch.

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

### `skill-creator`

- Decision: improved locally as a system skill.
- Completed work: added a public-alternative preflight that routes new skill creation and major skill expansion through `skills-sh-scout` when appropriate.
- Follow-up: keep marketplace discovery out of core creation logic; `skill-creator` should call the scout rather than reimplementing it.

### `whatsapp-wacli`

- Decision: improved in this repo.
- Completed work: documented the curated helper value over raw `wacli`, including structured JSON, PN-vs-LID resolution, bounded backfill, seed-missing diagnostics, and explicit confirmation gates.
- Follow-up: keep the helper local-first and avoid WhatsApp Business/API scope creep unless explicitly redesigned.

### `linkedin-cv`

- Decision: improved in this repo.
- Completed work: added evidence-first analysis templates for profile-section scoring, recruiter visibility, CV/profile deltas, and truthful rewrite prompts.
- Follow-up: improve analysis templates only; avoid LinkedIn automation, scraping, search traversal, messaging, or engagement actions.

### `outlook-classic-mail`

- Decision: improved in this repo.
- Completed work: added wrapper diagnostics that distinguish local Outlook Classic COM/client failures from cloud connector availability while keeping the skill local-first.
- Follow-up: optional Graph/M365 fallback remains a separate design if needed.

### `antigravity-cli`

- Decision: replaced the retired individual-tier `gemini-cli` skill with an isolated exact-model packet-review helper.
- Completed work: helper-owned CLIProxyAPI updates/auth/runtime, foreground unbounded login, ephemeral loopback review, exact model-attribution checks, and explicit packet-only input.
- Follow-up: migrate Amazon's separately vendored Gemini CLI intent resolver only through a dedicated behavior-compatible design; do not imply it was changed here.

### `everything-search`

- Decision: improved in this repo.
- Completed work: documented filename/path scope and added diagnostics for backend selection, `es.exe` availability, and scoped fallback behavior.
- Follow-up: keep it out of content grep, symbol search, RAG indexing, and cross-platform promises.

## Validation checklist

- Every module from `docs/skills-sh-alternatives.md` has an active, completed, or watch entry here.
- No local-first skill is marked for deprecation solely because a public skill has more installs.
- Replacement recommendations require workflow fit, safety fit, and no meaningful local-only advantage.
- Public skills are used for inspiration only when their feature ideas preserve this repo's safety posture.
