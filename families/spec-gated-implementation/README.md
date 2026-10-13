# Specification-Gated Implementation

Instruction-only workflow for multi-stage implementation controlled by an authoritative specification.

This family intentionally has no runtime package or CLI. Its canonical cross-agent skill is:

`codex/skills/spec-gated-implementation`

Install that same folder in Codex or a Claude-compatible personal skill root. The workflow requires repeated specification reconciliation, blocker closure before stage advancement, and zero tracked deferrals before completion.

Version 0.2.0 distinguishes advancement blockers from a genuinely BLOCKED stage,
preserves standing parking/dependency rules, and favors cohesive integrated patches.
Verification is evidence- and risk-driven: reuse inspected applicable results,
rerun affected checks when needed, and never skip required integration/recovery.
Deferrals belong to named stages; an empty remediation stage is not required.
Existing tasks should explicitly reread updated guidance instead of assuming that
deploying a file hot-reloads a running operation.
