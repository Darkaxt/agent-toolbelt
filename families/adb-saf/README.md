# ADB SAF

Access to Android documents providers (Storage Access Framework) over ADB. Many
apps expose their private storage through a documents provider that answers the
ADB shell user, while `run-as`, `adb pull` and shared-storage paths cannot reach
that storage.

- Reads (`providers`, `roots`, `ls`, `stat`, `sha256`, `pull`) use the platform
  `content` command, with URIs built and encoded by the helper.
- Changes (`put`, `mkdir`, `rename`, `delete`) are a reviewed `plan` followed by
  one `apply`. Apply re-verifies the plan, backs up overwritten or deleted
  content, and verifies the result by hash.
- `content call` cannot pass the Uri extras that DocumentsContract operations
  need. Changes therefore run the bundled `saf-client.dex` through
  `app_process` as the shell user, which is how `content` itself reaches
  providers.

See `codex/skills/adb-saf/SKILL.md` for the workflow.

## Development

```powershell
python -B -m unittest discover -s families/adb-saf/tests
python -B families/adb-saf/scripts/build_client_dex.py   # after editing SafClient.java
python -B families/adb-saf/scripts/install.py            # install into ~/.codex and ~/.claude skills
```

`build_client_dex.py` needs a JDK plus the Android SDK platform android-35 and
build-tools. It records the source hash in `assets/saf-client.json`; a test
fails if the committed dex is stale.
