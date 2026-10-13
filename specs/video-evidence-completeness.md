# Video Evidence Completeness

Authorization: user approved the transcript-first/browser-fallback workflow.
Scope: existing media and Antigravity helpers and Codex/Claude skills only.
No model/provider/configuration changes, interactive login or external model call.

## Requirements

- R1: Keep public subtitle acquisition model-free. Analyze evidence in the current
  task; Antigravity is optional independent analysis, never required acquisition.
- R2: Report missing, partial or unverified transcript coverage, selected caption
  source, character count and available cue bounds versus video duration. File
  presence or successful extraction must not imply complete spoken coverage.
- R3: If extraction fails or coverage is inadequate, guide public browser transcript
  capture, including lazy loading, deduplication, first/last timestamps and gaps.
  Do not export cookies or bypass access controls. If no transcript is available,
  report that limit; explicit audio preparation remains an optional next step.
- R4: Antigravity must expose original/supplied character counts and truncation in
  its packet and returned warnings. Missing/unknown source coverage remains visible;
  successful model attribution is not evidence of whole-video coverage.
- R5: Validate source and installed Codex/Claude copies, preserve exact model rules,
  synchronize verified changes to GitHub, and leave no disposable test artifacts.

## Stages

1. COMPLETE: implement R2/R4 and focused regression tests. Verify missing captions,
   acquisition failure with a surviving file, successful but unverified captions,
   and bounded Antigravity input. No full-coverage inference from cue timing.
   Evidence: focused media/evidence tests passed; source/supplied counts and cue
   bounds verified with fixtures, including failed acquisition and unverified tails.
2. COMPLETE: implement R1/R3 guidance, deploy R5, verify routing, installed
   launchers and skill parity, reconcile all requirements, commit and sync.

No required deferrals. Browser recovery is agent-guided, not a new browser CLI.
No live video or external reviewer request is necessary for these contract tests.

## Verification And Reconciliation

- R1/R3: Codex/Claude media guidance matches, including public browser recovery,
  lazy loading, language/timestamp checks, missing-coverage reporting and optional
  independent analysis. Antigravity instructions preserve mandatory explicit reviews.
- R2/R4: Media and Antigravity suites passed, followed by affected evidence tests
  after minimizing local path details in the external packet. Fixtures cover missing,
  partial and unverified coverage, prefix truncation and frame-only evidence.
- R5: Root family CLI/isolation/layout checks passed. All five existing installed
  copies passed structural validation, exact source-file hash parity and launcher
  help checks: Codex media/Antigravity, shared agents Antigravity, Claude's registered
  media/Antigravity plugin skill paths. Installed wrappers resolve the changed repo
  packages. Codex config and Claude settings hashes stayed unchanged.
- Task-owned fixture scratch was removed through a reviewed cleanup ticket.
- Browser recovery guidance was reviewed, not live-tested against a particular video.
  No media was downloaded, no model was called, and no credentials were changed.
- Git delivery is verified against the remote commit after push and recorded in
  the task completion report. No release or model/provider change is requested.

Required blockers: none. Required deferrals: none.
