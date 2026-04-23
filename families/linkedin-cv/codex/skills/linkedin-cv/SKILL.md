---
name: linkedin-cv
description: Use `scripts/invoke_linkedin_cv.py` for local, read-only LinkedIn own-profile snapshots, one explicit accessible profile capture at a time, and CV improvement comparisons.
---

# LinkedIn CV

Use `scripts/invoke_linkedin_cv.py` for local, read-only LinkedIn profile snapshot and CV improvement workflows. The wrapper bootstraps the LinkedIn family from the local `agent-toolbelt` workspace; if the workspace lives somewhere else, set `AGENT_TOOLBELT_HOME`.

## Allowed Workflows

- Use `session login --profile <name>` when the user can complete LinkedIn login in a headed managed browser.
- Use `profile capture-own --profile <name>` to capture the user's own LinkedIn profile.
- Use `profile capture --profile <name> --profile-id <slug> --confirm-accessible-profile-capture` or `--url <profile-url>` only for one explicit profile the logged-in account can already access.
- Use `profile compare --own <snapshot.json> --target <snapshot.json>` to identify improvement areas, wording patterns, missing sections, seniority signals, and skills gaps.

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
