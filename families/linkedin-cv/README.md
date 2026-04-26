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

Managed browser profiles and snapshots are stored outside the repository under local app data by default.
