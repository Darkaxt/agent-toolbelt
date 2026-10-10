# Operational Recordkeeping v1

## Authoritative scope

Provide an agent-neutral skill and self-contained Python helper that make durable
record reconciliation part of completing bills, payments, correspondence,
decisions, observations and purchases. Reuse existing records; no duplicate company ledger,
mail sender, payment tool, accounting authority or background monitor.

Requirements:
- R1: Route an event through a local project profile to all affected records.
  Missing required records, unknown event kinds and omitted checks fail closed.
- R2: Read back text sections, JSON values and keyed XLSX rows. Bind checks to
  shared event facts, so different records cannot silently use different values.
- R3: Require readable local evidence and verify its content with the same proof
  mechanism. Distinguish evidence of a user report from independent verification.
- R4: Prepare a pre-record-update packet after outcome evidence exists, then
  check current records without modifying
  them. Report changed versus already-consistent records. Detect changed evidence
  and changes during reads. No requirement to rewrite correct records.
- R5: Instructions must handle supersession, pending obligations, historical
  records, cross-project handoffs, missing evidence and concurrent writers.
- R6: Install identical public resources for Codex and Claude. Keep private
  project paths and business data in local profiles, never the public repository.
- R7: Test missed updates, contradictions, evidence loss, duplicate keys, invalid
  inputs, successful/no-op reconciliation and installed execution. Do not mutate
  actual business records during validation.

The helper verifies declared facts against selected evidence. It cannot decide
whether a proposed fact is true, discover every affected record, force skill
invocation or guarantee atomicity across independently edited files. Those remain
explicit manager responsibilities; do not describe this as automatic enforcement
of all bookkeeping or a financial audit.

## Staged execution (already authorized)

1. Contract and helper (R1-R4, R7): COMPLETE. Behavioral verification covers
   missed/partial updates, historical section isolation, typed values, XLSX keys,
   formula rejection, evidence changes, concurrent reads and input preservation.
2. Skill and profiles (R5-R6): COMPLETE. Skill validation passed. Company bindings
   are readable; the actual workbook's four worksheets parse read-only. Apartment
   observation binding is readable; its current operations register is explicitly
   unbound, so no archived roadmap is falsely treated as a live order register.
   The owning task must identify that source during its pilot; this is exposed
   configuration state, not an implementation deferral or a completed register.
3. Integration and delivery (R6-R7): COMPLETE. Installed Codex execution passed
   behavioral checks; Claude execution read the company profile; both bundles
   passed skill validation and file-hash comparison. Root layout/isolation/CLI/
   portability checks passed. Local skills.sh discovery includes the new skill.
   Final review clarified that preparation follows outcome evidence but precedes
   record updates, and added hashed binary originals alongside extracted proofs.

This targets readiness for the two owning tasks' pilot feedback, not a claim of
independently audited financial accuracy. No implementation blockers or tracked
deferrals. Business records were not modified; only private profiles and a
company-workspace routing instruction were added outside the public repository.

## Public alternative preflight

skills-sh-scout inspected davidlee/doctrine/reconcile, a software governance
workflow with revision surfaces, not local financial/correspondence reconciliation.
Exact operational-recordkeeping and local-invoice/correspondence searches returned
no candidates. Keep the local-first existing-record design.

## v0.1.1: Separate Apartment Operations Register

The user authorized a separate apartment register on 11 October 2026. An absent
operations binding must be resolved by reusing a real current register or creating
and binding a minimal separate one, not left indefinitely as intentional setup.
The company financial workbook remains authoritative for company accounting.

Acceptance: require creation/binding in the skill; provide a reusable template;
create and bind the private register without inventing business events; distinguish
file creation from reconciliation of current task context with an explicit helper
readiness gate checked during inspection, preparation and closure; verify a simulated
apartment event through the existing helper; deploy both bundles and sync source.

1. Register contract, template and profile: COMPLETE. The separate private register
   exists and is bound. Inspection distinguishes readable from initialized; an
   isolated purchase scenario proves preparation and closure reject an
   uninitialized register and accept a verified entry after initialization.
2. Verification and installation: COMPLETE. Canonical and both installed helpers
   passed the focused behavioral suite; both bundles passed structural validation
   and hash comparison. Root layout/isolation/CLI/portability checks passed. Live
   read-only profile inspection confirms company readiness and apartment
   initialization pending, not an unbound register or falsely completed review.

Final delivery requires committing and synchronizing this verified update to
GitHub; do not report synchronization before confirming remote integration.

No tracked deferrals. Populating real current items remains the owning task's
explicit initialization duty, not something an empty file can claim satisfied.

## v0.1.2: Accurate Readability Diagnostics

Fix the pilot finding that initialization validation failures were misreported
as file-read failures. Acceptance: readable records with missing or duplicate
initialization headings retain their path and report readable=true, ready=false
with the validation error; missing files remain unreadable. Routes, preparation
and closure must continue to fail closed. Tests must not modify business records.
Deploy matching Codex/Claude bundles and synchronize the verified source update.

This is a narrow diagnostic correction; no new business-context reconciliation,
record mutation, routing change or broader workflow is authorized by this patch.

Verification: the regression failed for both missing and duplicate headings
before the correction and passes afterward. Canonical and both installed helpers
pass focused behavioral checks; root wiring checks and installed structural/hash
validation pass. No business records or private profile bindings were changed.
