# LinkedIn CV

`agent-toolbelt-linkedin-cv` captures local, read-only LinkedIn profile evidence for CV/profile comparison. It is for truthful, evidence-grounded improvement suggestions based on real captured profile data, not generic LinkedIn optimization advice.

It captures one explicit LinkedIn profile at a time through an app-owned managed browser profile. It does not search people, traverse connections, scrape feeds, generate posts, perform lead generation, or mutate the account.

Use it when recommendations need to be grounded in a captured own-profile snapshot or one explicit accessible comparison profile. The comparison output should call out missing evidence rather than inventing skills, roles, metrics, endorsements, or credentials.

```powershell
uv run agent-toolbelt-linkedin-cv session login --profile personal
uv run agent-toolbelt-linkedin-cv profile capture-own --profile personal
uv run agent-toolbelt-linkedin-cv profile capture --profile personal --profile-id demo-profile --confirm-accessible-profile-capture
uv run agent-toolbelt-linkedin-cv profile compare --own C:\path\own.json --target C:\path\target.json
```

## Analysis template

Use captured snapshots as the evidence source of truth. A useful report should
separate evidence from recommendations:

- Evidence inventory: summarize captured headline, About, Experience, Skills,
  Featured, education, certifications, languages, and measurable achievements.
- Profile-section scorecard: mark each visible section as strong, adequate,
  weak, missing, or not captured, and cite the snapshot fields that support the
  rating.
- Recruiter-visibility checklist: check role keywords, seniority signals,
  location/remote signals, measurable outcomes, technology/domain terms, and
  proof links or featured artifacts.
- CV/profile delta: compare the user's CV claims against the captured profile;
  flag missing profile evidence, profile-only evidence, wording mismatches, and
  unsupported claims.
- Truthful rewrite prompts: suggest wording improvements only when backed by
  captured evidence or user-provided CV facts; ask for missing metrics instead
  of inventing them.

Managed browser profiles and snapshots are stored outside the repository under local app data by default.
