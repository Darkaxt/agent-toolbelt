---
name: cybersecurity-orchestrator
description: Select the appropriate installed security workflow for explicit audits, finding handling, detection engineering or forensic investigations. Route to specialist skills and focused primary-source references; ordinary coding does not require a security audit.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Codex and Claude. Instruction-only; specialist tools must actually be available in the current environment.
---

# Cybersecurity Orchestrator

Select a workflow in this conversation. This skill provides routing and focused investigative references, not a scanner, executable playbook or reason to spawn agents.

## Route by the requested outcome

Read the selected installed skill before using its helper. Check actual availability: Codex Security is a separate plugin and is not assumed to exist in Claude. If a required capability is unavailable, report that boundary and use discovery for that exact capability. Do not represent a manual checklist as an executed plugin scan.

| Requested outcome | Route |
| --- | --- |
| Security review of a PR, commit, branch or working-tree diff | `codex-security:security-diff-scan` |
| Standard repository or scoped-path audit | `codex-security:security-scan` |
| Explicit exhaustive or repeated independent scans | `codex-security:deep-security-scan` |
| Triage an existing finding, fix it, verify its fix, or write it up | Matching `codex-security:triage-finding`, `fix-finding`, `verify-fix` or `vulnerability-writeup`; preserve the requested operation |
| Threat model, security policy or structural hardening proposal | Matching `codex-security:threat-model`, `define-security-policy` or `propose-security-hardening` |
| Cortex XSOAR/Demisto integration, playbook or content change | `xsoar-development` first; it owns the platform contract |
| Retrieve a suspicious Outlook message | `outlook-classic-mail` for evidence access, then the phishing reference below |
| Supplied security evidence or detection-rule design | Relevant reference below, then verify current tool documentation and actual input coverage |

For an in-progress Codex Security scan, follow its phase instructions; do not start a second scan or substitute an isolated phase for the requested audit. Use additional references only to answer a concrete domain question in the primary workflow. Security-related code alone does not trigger a new audit.

## Load only the relevant reference

| Evidence or task | Reference |
| --- | --- |
| Sigma conversion, detection-rule validation or YARA pattern design | [Detection engineering](references/detection.md) |
| Sysmon injection telemetry or offline memory triage | [Host evidence](references/host.md) |
| Offline PCAP analysis or Zeek timing | [Network evidence](references/network.md) |
| CloudTrail timeline coverage or phishing headers | [Cloud and mail evidence](references/cloud-mail.md) |

These are focused, corrected reasoning aids. They do not establish detector accuracy, qualify vendor scripts or replace tool-specific documentation. Keep observed evidence, inference and untested hypotheses distinct. Resolve current versions, fields and coverage before applying a command or interpretation.

The former bulk cybersecurity collection was retired after usefulness review. There is no dependency on its disabled folders, executable scripts or catalog, and no instruction to reinstall it. Prefer the established specialist capability or the linked primary source over another large pack of overlapping skills.

Existing user scope governs account access, live capture, malware execution, external submissions, credential extraction and system changes. Selecting a reference does not authorize those actions.
