# D-Temp Maintenance

On-demand maintenance for agent-generated leftovers in D:/Temp. One canonical
instruction-only skill works with Codex and Claude:

`codex/skills/d-temp-maintenance`

Copy that folder into the selected personal skill root. It has no runtime package,
CLI, scheduler or independent deletion engine. It uses existing Everything/file
inspection, task-owner tools, Git lifecycle and installed transactional-cleanup.
Deletion is unavailable without that helper; read-only assessment remains useful.

The workflow ranks exact targets, distinguishes generated output from unique
source/recovery state, and executes reviewed cleanup when authorized. It does not
recursively snapshot all Temp, purge by age, force-remove dirty worktrees or block
Gradle builds while reviewing artifacts. References include executable cleanup
routes and a private ledger template.

The implementation and acceptance criteria are in the repository specification
`specs/d-temp-maintenance.md`. This family intentionally omits a runtime package.
