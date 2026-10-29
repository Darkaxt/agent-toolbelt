# Long-path draft attachments

Authorization: user requested helper support on 29 October 2026.

## Required outcome

- LP1: Existing draft/reply/forward/create commands accept readable Windows source
  paths exceeding legacy MAX_PATH, including extended local/UNC paths. Preserve
  the source file, original Unicode filename and attachment bytes.
- LP2: Select short-path staging before COM admission of an attachment; never
  retry an uncertain Attachments.Add. Preserve ordinary short-path behavior.
  Keep staged input through draft Save and verify the saved attachment's name
  and exported content before reporting success. Retain existing sender, recipient,
  quote and placement verification. No mail is sent.
- LP3: Use an isolated, application-owned E:/Temp workspace (D:/Temp only when
  E: is unavailable). Clean internal staging on success or failure after its
  consumers finish. Expose transport/content-verification diagnostics. Do not
  change global settings, user files or unrelated drafts.
- LP4: Regression tests cover long Unicode names, content/name corruption,
  failure cleanup, one Add only, ordinary attachments and all existing draft
  entry points. Demonstrate the real native path limitation and saved/reopened
  result using an explicitly disposable probe.
- LP5: Deliver source-bound versioned client via Coordinator's normal local
  release/installer; verify installed content and helper discovery, commit and
  synchronize both repositories. Update installed usage guidance.

## Stages / reconciliation

1. Complete attachment implementation and verification (LP1-LP4): COMPLETE.
2. Source-bound release, installation and final verification (LP5): COMPLETE.

No tracked deferrals. LP1-LP4: saved/reopened 404-unit Unicode source and explicit
extended Windows path preserve filename, bytes and original; exact owned probes
removed from Drafts, no sends. Long-path/error/corruption/duplicate-name/storage
regressions and existing draft, sender and wrapper checks pass. Closure review:
one existing attachment context serves all five save paths; no required refactor.
LP5: Coordinator 0.16.3/a0eb32e6e700bb9e installed and verified against the
independently extracted 183-member Release archive. Installed client and all
Codex/shared/Claude skill files match the package; all three resolvers select it,
and the installed launcher passes diagnostics through the Coordinator gate.
Installed native extended-path probe saved/reopened the same 404-unit path with
matching name and bytes, unchanged source, one attachment and no send.
Native desktop ProductVersion matches b4421d9; broker PID 20516 was preserved and
is accepting, Helium debugging remains disabled. GitHub branch/tag readback
confirms agent-toolbelt 044d4c0 and Coordinator b4421d9/v0.16.3.
No blockers, tracked deferrals or required consolidation remain.

Release archive: D:/Tools/llm-coordinator/releases/0.16.3/
LLM-Coordinator-0.16.3-win-x64.zip; SHA-256
`5c8e9cbd6023fb4ca1ae99ce866e59e742447f019a05a22193655f6adde25d1a`.
Exact E: and D: task scratch removed through transaction
59e213f207c19343b1e9d36dc210ffa6: 1,868 members / 138,366,876 logical bytes,
no warnings/errors; both roots independently absent. Runtime internal staging
was removed after Save/export on native success and error paths. The isolated
source probes used the installed FIFO/COM lock and only disposable owned items;
normal installed launcher gate routing was independently verified.

## Constraints and evidence

Microsoft documents legacy MAX_PATH and that Attachments.Add DisplayName is
ignored for HTML/plain text. A shortened transport filename therefore needs the
original basename preserved in its short staging path, not just DisplayName.
Native probing also showed Outlook refuses changes to PR_ATTACH_LONG_FILENAME.
The original filename plus short staging directory must fit Outlook's native
path budget; report this specific constraint before Add rather than renaming a
near-filesystem-limit basename or claiming unrestricted filename support.
Filesystem component limits, unreadable paths and mailbox/provider size limits
remain actual errors; support does not imply unlimited filename length.

Agent verification scratch: E:/Temp/outlook-long-path-20261029. Native package
build uses D:/Temp/outlook-long-path-20261029 for sustained small-file I/O.
Task scratch uses transactional cleanup; product-internal staging has its own
lexical consumer lifetime. Retain compact reports in D:/Tools/llm-coordinator/
verification/20261029/outlook-long-path.
