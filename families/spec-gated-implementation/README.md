# Specification-Gated Implementation

Instruction-only workflow for multi-stage implementation controlled by an authoritative specification.

This family intentionally has no runtime package or CLI. Its canonical cross-agent skill is:

`codex/skills/spec-gated-implementation`

Install that same folder in Codex or a Claude-compatible personal skill root. The workflow requires repeated specification reconciliation, blocker closure before stage advancement, and zero tracked deferrals before completion.

Version 0.3.0 adds a lightweight refactoring assessment at verified stage closure
and final reconciliation, not automatic refactoring after every stage. Material,
authorized debt may justify a bounded consolidation stage with preserved behavior,
observable acceptance and affected complete-workflow verification. Current acceptance
fixes stay current-stage blockers; required later work uses named-stage deferrals.
Assessments reuse the existing ledger; unchanged evidence does not need another audit.

The workflow distinguishes advancement blockers from a genuinely BLOCKED stage,
preserves standing parking/dependency rules, and favors cohesive integrated patches.
Verification is evidence- and risk-driven: reuse inspected applicable results,
rerun affected checks when needed, and never skip required integration/recovery.
Deferrals belong to named stages; an empty remediation stage is not required.
Existing tasks should explicitly reread updated guidance instead of assuming that
deploying a file hot-reloads a running operation.
