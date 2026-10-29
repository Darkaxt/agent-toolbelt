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
2. Source-bound release, installation and final verification (LP5): ACTIVE.

No tracked deferrals. LP1-LP4: saved/reopened 404-unit Unicode source and explicit
extended Windows path preserve filename, bytes and original; exact owned probes
removed from Drafts, no sends. Long-path/error/corruption/duplicate-name/storage
regressions and existing draft, sender and wrapper checks pass. Closure review:
one existing attachment context serves all five save paths; no required refactor.
LP5 remains an acceptance blocker until actual release/install readback and sync.

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
