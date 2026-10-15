# Compressed Codex rollout compatibility

Authority: the selected AYN Thor takeover requires preserving and retiring the
actual Codex-managed rollout files, including compressed files. This repair is
limited to that transfer boundary; no live database writes or source expansion.

## Requirements

- R1: Resolve a missing database `.jsonl` pointer to its exact `.jsonl.zst`
  sibling; discover resumed compressed segments and verify session identity.
- R2: Read compressed headers for inherited owners and surviving fork references.
  Compression must not hide lineage or make an independent destination a fork.
- R3: Catalogue compressed content with explicit decompressed byte offsets.
- R4: Archive, hash, restore and retire the actual compressed bytes using existing
  identity, activity, acceptance, archive and exact-path ticket safeguards.
- R5: Preserve ordinary uncompressed behavior. On runtimes without a Zstandard
  reader, fail explicitly for compressed files rather than claiming missing history.

## Execution and reconciliation

One stage: compressed transfer compatibility — COMPLETE.
Acceptance: reproducible regression tests for R1–R3/R5; existing complete transfer
suite for R4; installed runtime read-back and actual selected-source inventory,
catalogue, verified recovery, acceptance and leaf-first retirement.
No tracked deferrals. The AYN Thor group ledger records actual migration gates.

Verified: the complete context-transfer suite passed, including compressed-pointer,
catalogue, fork-lineage, activity-fingerprint and unavailable-reader regressions.
The selected installed runtime matched all changed source modules byte-for-byte.
All four real compressed sources were catalogued, archived and integrity checked,
including scoped database read-back. The MTP fork's parent was separately
preserved before leaf-first retirement. Archival moved three compressed files;
fresh inventory and archive/ticket bindings covered their actual final paths.
All four exact rollout offloads completed with zero residual bytes; original
database history and local recovery archives remain intact. The destination title
and original archived states were read back through the supported application API.
No device mutation, deployment or underlying project publication was performed.

No scope-related design debt or unresolved transfer requirement remains. This
compatibility repair shares only the exact path resolver and decoded stream reader
needed by inventory, lineage, catalogue and activity checks; archive/restore and
retirement retain their existing byte-preserving safety contracts.
