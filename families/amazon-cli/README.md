# Amazon CLI

`agent-toolbelt-amazon-cli` bridges agent-toolbelt into the standalone Amazon CLI installed under `%LOCALAPPDATA%\Tools\amazon-intent-cli`.

The family does not vendor Amazon scraping code or copy managed browser sessions. It only delegates commands to the local `amazon-cli` project with `uv run --project`.

```powershell
uv run agent-toolbelt-amazon-cli -- offers B0F2JCZPB4 --marketplace de --marketplaces de,fr,es
uv run agent-toolbelt-amazon-cli -- reviews B0F2JCZPB4 --marketplace de --portal retail --limit 20
```
