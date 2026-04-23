# LinkedIn CV

`agent-toolbelt-linkedin-cv` captures local, read-only snapshots of one explicit LinkedIn profile at a time through an app-owned managed browser profile.

It is designed for CV/profile improvement work, not LinkedIn crawling. It does not search people, traverse connections, scrape feeds, or perform account mutations.

```powershell
uv run agent-toolbelt-linkedin-cv session login --profile personal
uv run agent-toolbelt-linkedin-cv profile capture-own --profile personal
uv run agent-toolbelt-linkedin-cv profile capture --profile personal --profile-id demo-profile --confirm-accessible-profile-capture
uv run agent-toolbelt-linkedin-cv profile compare --own C:\path\own.json --target C:\path\target.json
```

Managed browser profiles and snapshots are stored outside the repository under local app data by default.
