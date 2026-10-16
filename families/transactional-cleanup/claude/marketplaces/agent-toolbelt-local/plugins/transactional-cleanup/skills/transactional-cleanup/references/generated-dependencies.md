# Generated CMake dependency clones

Use this contract for explicitly authorized, obsolete FetchContent downloads at
`<maintained-project>/.cxx/.../_deps/<name>-src`, including outside Temp. Read-only
provenance and regeneration checks replace whole-repository recovery only for
this generated-artifact class. Ordinary repository retirement is unchanged.

1. Identify the actual owner, current consumers, exact CMake declaration, origin,
   resolved Git pin and maintained patches. Preserve signing material, game assets,
   unrelated source and required offline copies. A folder name alone is not proof.
2. Begin/register one exact task scratch directory under D:/Temp or E:/Temp for
   validation indexes/objects. Keep it outside the maintained project. The helper
   writes only its isolated Git index/object store there when reproducing patches;
   it never resets or patches the real clone. Clean scratch through the normal
   ticket workflow after the final application/verification.
3. Write compact evidence outside the clone:

```json
{
  "version": 1,
  "mode": "cmake-fetchcontent",
  "repository": "C:\\Projects\\App\\Android\\app\\.cxx\\configuration\\arm64-v8a\\_deps\\example-src",
  "project": "C:\\Projects\\App",
  "producer": "C:\\Projects\\App\\cmake\\dependencies.cmake",
  "dependency": "example",
  "origin": "https://github.com/owner/example.git",
  "pin": "actual literal tag or commit hash from the declaration",
  "patches": [],
  "validation_root": "D:\\Temp\\owned-cleanup\\validation",
  "authorization": "Actual user authority and generated-cache provenance",
  "consumer_review": {
    "checked_at": "Actual ISO timestamp",
    "ownership": "Actual owner and obsolete staging evidence",
    "schedulers_services": "Actual inspection and results",
    "dependencies": "Actual build references and regeneration/offline review",
    "active_consumers": []
  }
}
```

4. Begin with each clone as an exact `--scan-root`, then register it using
   `--kind generated-dependency-repository --regenerated --dependency-evidence
   <json> --confirm-dependency-repository <exact-clone> --evidence <provenance>`.
   Use the normal separate review, inspect, ticket and apply invocations.

The first apply verifies source availability, origin/pin, refs and reflog history,
the complete expected patched tree, producer fingerprints, root identities and
consumers. HTTPS sources without embedded credentials and independent existing
local bare origins are supported. Hash pins not advertised by GitHub are checked
through its exact commit API, using an existing GitHub CLI when available or the
public endpoint otherwise. No CLI installation, login or credential output occurs;
unavailable/unsupported proof preserves the clone.
No login, fetch, source reset, source patch or full backup is performed. Local-only
branches/tags/commits, unknown edits, untracked/ignored files, alternate object
stores and additional/linked worktrees are rejected. Generated submodules require
the same checks recursively, with exact tracked gitlink pins and metadata contained
inside their generated parent. Unproven or modified submodule content is preserved.

After partial deletion, the signed root proof and exact member content/identity
checks remain binding even if Git metadata has already gone. New or changed files
survive; retry the same valid ticket only after its concrete condition resolves.
