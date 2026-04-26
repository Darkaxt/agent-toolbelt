# Skill improvement backlog

Generated: 2026-04-26

This backlog turns the skills.sh alternative analysis into actionable follow-up
work. It is intentionally tied to `docs/skills-sh-alternatives.md` and should
be updated when that analysis changes.

Install counts and official publishers are useful evidence, but they are not
automatic replacement criteria. Local-first behavior, fail-closed safety,
explicit confirmation gates, and exact platform fit count as first-class
features for this repo.

## P1 - Highest-value improvements

### `yt-dlp-ffmpeg`

- Current verdict: strong direct competitors exist, but our combined local workflow is still useful.
- Public inspirations: `lwmxiaobei/yt-dlp-skill/yt-dlp`, `mapleshaw/yt-dlp-downloader-skill/yt-dlp-downloader`, `digitalsamba/claude-code-video-toolkit/ffmpeg`, `sundial-org/awesome-openclaw-skills/ffmpeg-video-editor`, `composiohq/awesome-claude-skills/youtube-downloader`.
- Improvement requests: add list-formats support, metadata-only inspection, playlist controls, safer URL classification, clearer refusal output, and better format-selection guidance.
- Avoid: private/authenticated/cookie-based media workflows, site-specific downloader sprawl, or instructions that encourage bypassing platform access controls.
- Recommended next action: improve. Preserve the single safe local interface for public download, probe, clip, audio extraction, remux, and transcode.

### `amazon-cli`

- Current verdict: strong direct competitors exist.
- Public inspirations: BrowserAct Amazon product/review/search/ASIN API skills, `amazon-product-finder`, Amazon shopping/product-research skills.
- Improvement requests: improve structured product extraction, review/comment summarization, product comparison reports, ASIN lookup ergonomics, and seller-vs-retail positioning.
- Avoid: turning the skill into a seller/FBA management tool, affiliate-marketing workflow, captcha bypasser, or automated purchase workflow.
- Recommended next action: improve. Keep the local retail/business-session workflow and explicit cart-confirmation model.

### `observable-reputation`

- Current verdict: no meaningful direct alternative found.
- Public inspirations: threat-intelligence feed analysis skills, domain-research skills, OSINT workflow skills.
- Improvement requests: add IOC normalization, optional STIX/CSV export, provider coverage diagnostics, richer skip/error reporting, and cleaner integration payloads for mail quarantine.
- Avoid: active scans, URL submissions, file uploads, phishing reports, browser visits, or provider actions that mutate reputation systems.
- Recommended next action: improve incrementally. This skill has a clear niche and should stay passive-only.

## P2 - Useful but larger or lower urgency

### `outlook-classic-mail`

- Current verdict: partial alternatives exist.
- Public candidates: `membranedev/application-skills/microsoft-outlook`, Rube/Composio Outlook automation skills, M365/Graph mail skills, IMAP/SMTP mail skills.
- Improvement requests: consider an optional Graph/M365 fallback only if local Outlook Classic is unavailable; improve diagnostics that distinguish local COM queue issues from connector-style mail access.
- Avoid: silently switching trust models from local Outlook Classic COM to cloud mailbox APIs, or performing draft/send/move/delete actions without confirmation.
- Recommended next action: keep as local-first. Treat cloud connector parity as a separate design, not an incremental patch.

### `mail-domain-quarantine`

- Current verdict: no meaningful direct alternative found.
- Public inspirations: suspicious-email-analyzer, email-classifier, Gmail triage, domain-research skills.
- Improvement requests: consume improved `observable-reputation` outputs, refine report language, and improve policy explainability for young-domain/blocklist decisions.
- Avoid: generic phishing-analysis sprawl, automatic mailbox mutation, link opening, unsubscribe/report-spam actions, or cloud-mailbox assumptions.
- Recommended next action: improve through integration only. Keep dry-run default and Outlook Classic quarantine scope.

## Watch list

### `everything-search`

- Current verdict: no meaningful direct alternative found.
- Public candidates: generic `fd`/`rg` file-search skills, RAG/file-ingest skills, desktop-search-adjacent skills.
- Improvement requests: document the difference between global Windows filename/path discovery and repo-local content search; add clearer fallback diagnostics if Everything or `es.exe` is missing.
- Avoid: turning this into a content grep, RAG indexer, or cross-platform promise.
- Recommended next action: keep. No urgent feature work.

### `xsoar-development`

- Current verdict: partial alternatives exist.
- Public candidates: `membranedev/application-skills/cortex-xsoar`, generic SOAR workflow skills.
- Improvement requests: document live XSOAR connector skills as complements, not replacements; continue improving content-pack artifact correctness and private-overlay guidance in the separate `xsoar-development` repo.
- Avoid: mixing live XSOAR mutation workflows into a content-development guidance skill.
- Recommended next action: keep. Consider a separate live-operations helper only if needed.

### `whatsapp-wacli`

- Current verdict: strong direct competitors exist.
- Public candidates: `steipete/clawdis/wacli`, `gokapso` WhatsApp Business/API skills, WhatsApp Cloud/API and `whatsapp-web.js` skills.
- Improvement requests: compare our curated adapter against `steipete/clawdis/wacli`; explicitly document the value of structured JSON, PN-vs-LID resolution, backfill behavior, and confirmation semantics.
- Avoid: raw passthrough that bypasses safety gates, WhatsApp Business API scope creep, session packaging, or visible sends without exact confirmation.
- Recommended next action: compare before changing. Keep ours if the helper layer materially improves reliability over raw `wacli`.

### `linkedin-cv`

- Current verdict: partial alternatives exist.
- Public inspirations: LinkedIn profile optimizer, resume tailor, personal branding, post optimizer skills.
- Improvement requests: borrow profile-section scoring, recruiter-visibility checklists, CV/profile delta reporting, and clearer marketing language around read-only local capture.
- Avoid: LinkedIn automation, engagement actions, scraping at scale, lead generation, or pretending public optimizer skills replace local profile evidence capture.
- Recommended next action: improve positioning and analysis templates, not automation.

### `gemini-cli`

- Current verdict: partial alternatives exist.
- Public candidates: official Google Gemini API/dev/interactions/live skills, `steipete/clawdis/gemini`, URL-to-Markdown and YouTube summarizer skills.
- Improvement requests: keep public URL/Gemini CLI inspection narrow; add clearer routing to official Google skills for API/app development; consider a URL-to-Markdown fallback when Gemini cannot inspect a public page.
- Avoid: reverse-engineered Gemini Web API flows, private/local URL submission, or broad Gemini app-development guidance.
- Recommended next action: keep and clarify routing.

### `codex-thread-recall`

- Current verdict: strong direct competitors exist.
- Public inspirations: `arjunkmrm/recall`, CASS, Supermemory, session-log and episodic-memory skills.
- Improvement requests: continue evaluating broad-history UX ideas such as transcript-reader ergonomics, optional importers, query-language polish, and search-result explainability.
- Avoid: losing exact current-thread fail-closed semantics, making imported memory a default recall source, or becoming a cloud memory system.
- Recommended next action: keep. Improve only where public recall tools expose clear audit/search UX gaps.

## Helper skill: `skills-sh-scout`

Purpose: run a public skills.sh discovery gate before creating a new skill or
materially expanding an existing one. This should be a separate helper skill,
not an overhaul of `skill-creator`.

Trigger examples:

- "create a skill for X"
- "improve this skill"
- "is there already a skill for X?"
- "design a new skill capability"
- "should we build or install a public skill?"

Expected workflow:

1. Convert the requested workflow into multiple skills.sh query variants.
2. Search `https://skills.sh/api/search?q=<query>&limit=100`.
3. Dedupe results by skill id and preserve install counts, owner/repo, and source URLs.
4. If any query returns exactly 100 rows, run narrower follow-up queries.
5. Inspect the strongest direct candidates and high-install partial candidates.
6. Compare candidates against the requested workflow, safety model, platform needs, and local-first requirements.
7. Return a concise decision table plus design inspirations.

Recommendation categories:

- `Install public skill`
- `Use public skill as inspiration`
- `Improve existing local skill`
- `Create new skill`
- `Do not create; public alternative is clearly better`

Safety rules:

- Do not recommend account-backed or mutation-capable public skills unless the user explicitly accepts that trust model.
- Preserve local-first, fail-closed, read-only, and explicit-confirmation behavior as positive differentiators when relevant.
- Treat official publisher, install count, and marketplace popularity as supporting evidence only.
- Prefer public alternatives when they clearly cover the workflow with safer or broader behavior and no local-only advantage exists.

Implementation notes:

- `skills-sh-scout` is implemented as a public package-backed helper skill in this repo.
- Keep `SKILL.md` concise and put longer query/evaluation examples in directly linked reference files if needed.
- Update `skill-creator` after `skills-sh-scout` exists so skill creation starts with a public-alternative check when appropriate.

## Validation checklist

- Every module from `docs/skills-sh-alternatives.md` has one entry here.
- No local-first skill is marked for deprecation solely because a public skill has more installs.
- Replacement recommendations require workflow fit, safety fit, and no meaningful local-only advantage.
- Public skills are used for inspiration only when their feature ideas preserve this repo's safety posture.
