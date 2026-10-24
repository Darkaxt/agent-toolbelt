---
name: recodex-policy-diagnostics
description: Diagnose a blocked or rejected execution using observed evidence and the installed ReCodex Policy Inspector; record cybersecurity rejections in the shared recovery ledger and identify permitted next work. Does not override enforcement or retry denied operations.
license: MIT
metadata:
  version: "0.1.0"
  compatibility: Windows; existing ReCodex Policy Inspector and approach-recovery-ledger. Identical instructions for Codex and Claude.
---

# ReCodex Policy Diagnostics

Use after an actual execution rejection, or an explicit request to inspect a
command. A failed build, transport disconnect or Windows access error alone is
not evidence of a cybersecurity rejection. Do not stop the whole assignment
when only one operation or acceptance criterion is affected.

## Retain evidence and consult the rejection register

Keep the exact tool result/code, command or scoped evidence reference, operation,
time and known execution outcome. Separate a command denied before launch from
a completed tool call followed by rejected model generation. An unknown outcome
needs inspection, not replay. Do not infer a rejection trigger from timing alone.

For cybersecurity or other policy rejections, read the installed
`approach-recovery-ledger` skill and its `references/rejections.md`. It is the
shared rejection register; do not create a second database. Query by relevant
objective/method before selecting the next approach. Record the observed
rejection even when Inspector is unavailable or the cause remains unknown.
The recovered/resumed chat performs the write when execution is available;
this skill does not intercept backend rejections or guarantee it can write
while generation itself is blocked.

## Inspect PowerShell without executing the command

Resolve the user's installed shortcut, currently
`E:/ReCodex/releases/ReCodex Policy Inspector.lnk`. Read its target, arguments
and working directory; do not launch its GUI. Verify these identify the same
trusted installed release and that `inspector.py` exists beside the `.pyw` entry.
Read that release's README and CLI help if its interface has changed. Do not
guess a historical version directory, download another analyzer or alter rules.

```powershell
$inspectorLink = (New-Object -ComObject WScript.Shell).CreateShortcut('E:/ReCodex/releases/ReCodex Policy Inspector.lnk')
$inspectorLink | Select-Object TargetPath, Arguments, WorkingDirectory
$inspectorPython = Join-Path (Split-Path -Parent $inspectorLink.TargetPath) 'python.exe'
$inspectorCli = Join-Path $inspectorLink.WorkingDirectory 'inspector.py'
& $inspectorPython -B $inspectorCli --help
```

Save the exact command as UTF-8 **data** through a file-editing tool, in a private
task-owned D:/E: evidence folder. Do not interpolate it into a shell command,
dot-source it or execute it to feed the Inspector. Review for secrets; when exact
input cannot be retained safely, keep a digest/reference and mark diagnosis
incomplete rather than claiming a redacted variant is equivalent.

```powershell
# Substitute actual private evidence paths and the known scenario.
& $inspectorPython -B $inspectorCli --file 'D:/Temp/exact-task/command.txt' --approval never --output 'D:/Temp/exact-task/inspection.json'
```

Supply the original known approval scenario (`never`, `on-request`, `untrusted`)
and shell, plus `--restricted` when applicable. If unknown, label the chosen
scenario hypothetical. Pass `--rules` only for deliberately selected exact rule
files; repeat it for each file. CLI mode does not automatically load user rules.
`--codex-cli` selects an already trusted local checker when needed. Selected
files are not proof of every active policy layer. Unsupported shell/platform
diagnostics stay unavailable; still record the actual rejection and next decision.

Inspect exit status and JSON: `submitted_command_executed`, `input.sha256`,
`engine.parsing`, `engine.findings`, `engine_identity`, `explicit_rules`,
`scenario` and `coverage`. Exit 0 means a report was produced, not execution
permission. Exit 2 means analysis failed; retain its diagnostic. A local match
is a conditional prediction. Historical classifier/source equivalence is not
established; Guardian/server cybersecurity, managed host policy, antivirus and
Windows execution are outside coverage. Never attribute those causes to a local
match or interpret `no_block_identified` as clearance to rerun.

## Preserve progress and select the next permitted step

Record the rejection through the ledger's rejection contract, linking the local
Inspector report separately from the observed denial. Keep the original criteria
and any successfully completed work. Explain which layer is observed, what the
Inspector predicts, what remains unknown, and the affected criterion.

Continue genuinely independent permitted work under the standing stage rules,
or a substantively different permissible approach with an explicit rationale.
Do not repackage the denied action, change shells/tools/models/access programs,
weaken rules or repeatedly vary commands to obtain execution. If no permitted
next action exists, park only the affected work with its concrete resolution
condition. Later verified outcomes become linked ledger entries; old denials
remain historical observations, not universal bans or permission grants.

Keep reports private: they may contain full commands, paths and rule contents.
Clean expendable inputs through transactional-cleanup when no longer needed;
preserve evidence still needed by a ledger record or an unresolved diagnosis.
