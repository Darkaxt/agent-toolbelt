# Specification-Gated Implementation

Instruction-only workflow for multi-stage implementation controlled by an authoritative specification.

This family intentionally has no runtime package or CLI. Its canonical cross-agent skill is:

`codex/skills/spec-gated-implementation`

Install that same folder in Codex or a Claude-compatible personal skill root. The workflow requires repeated specification reconciliation, blocker closure before stage advancement, and zero tracked deferrals before completion.
