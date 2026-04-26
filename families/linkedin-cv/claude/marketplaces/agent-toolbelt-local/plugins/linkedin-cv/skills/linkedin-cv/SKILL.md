---
name: linkedin-cv
description: "Use `scripts/invoke_linkedin_cv.py` for safe local LinkedIn evidence capture: read-only own-profile snapshots, one explicitly accessible profile capture at a time, and CV/profile gap comparisons grounded in captured data. Prefer this over generic LinkedIn optimization when recommendations must be based on real profile evidence; do not use it for LinkedIn search, scraping, messaging, posting, or engagement automation."
---

# LinkedIn CV

Use `scripts/invoke_linkedin_cv.py` for local, read-only LinkedIn profile evidence capture and CV/profile comparison workflows. The wrapper bootstraps the LinkedIn family from the local `agent-toolbelt` workspace; if the workspace lives somewhere else, set `AGENT_TOOLBELT_HOME`.

This is not a generic LinkedIn optimizer, content generator, lead-generation tool, or automation skill. Use it when the user wants truthful CV/profile improvement suggestions grounded in a captured LinkedIn profile snapshot.

## Allowed Workflows

- Use `session login --profile <name>` when the user can complete LinkedIn login in a headed managed browser.
- Use `profile capture-own --profile <name>` to capture the user's own LinkedIn profile.
- Use `profile capture --profile <name> --profile-id <slug> --confirm-accessible-profile-capture` or `--url <profile-url>` only for one explicit profile the logged-in account can already access.
- Use `profile compare --own <snapshot.json> --target <snapshot.json>` to identify improvement areas, wording patterns, missing sections, seniority signals, and skills gaps.

## Comparison Guidance

- Ground all suggestions in the captured snapshot or user-provided CV. If evidence is missing, say what is missing instead of inventing profile content.
- Organize recommendations by profile/CV section when useful: headline, About, Experience, Skills, Featured, education, certifications, and measurable achievements.
- Suggest truthful wording improvements, prioritization, and gap-filling prompts. Do not copy another profile verbatim or imply credentials, metrics, roles, or endorsements that are not supported.
- Treat public LinkedIn optimization advice as optional framing only; the captured profile evidence is the source of truth.

## Safety Rules

- Read-only is the default. Do not connect, follow, message, endorse, react, comment, save, apply, or submit forms.
- Capture one explicit profile per command; no search traversal, no people-search pagination, no connection graph extraction, no feed scraping, and no batch mode.
- Reject `/search/`, `/feed/`, `/mynetwork/`, `/jobs/`, `/company/`, `/sales/`, `/recruiter/`, messaging, and non-profile URLs.
- For accessible profiles that are not the user's own, require `--confirm-accessible-profile-capture`.
- Do not copy another profile verbatim. Use comparisons only to propose truthful improvements to the user's own CV/profile.
- Do not package or commit managed browser profiles, cookies, sessions, snapshots, raw HTML, caches, or local runtime state.

## Command Examples

```powershell
python scripts/invoke_linkedin_cv.py session login --profile personal
python scripts/invoke_linkedin_cv.py profile capture-own --profile personal
python scripts/invoke_linkedin_cv.py profile capture --profile personal --profile-id demo-profile --confirm-accessible-profile-capture
python scripts/invoke_linkedin_cv.py profile compare --own C:\snapshots\own.json --target C:\snapshots\target.json
```
