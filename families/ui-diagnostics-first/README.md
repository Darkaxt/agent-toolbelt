# Diagnostics-First UI

An instruction-only skill for app-owned UI debugging and acceptance evidence,
especially Android interfaces where screenshot/action polling becomes expensive.
It guides real remote UI actions, actual rendered hierarchy exports and measured
loading/layout/item-resolution timings while retaining targeted visual review.

Canonical cross-agent bundle: `codex/skills/ui-diagnostics-first`.
Install that identical folder in personal Codex, agents and Claude skill roots.
No CLI, runtime package, service, plugin or application setting is installed.

The included project-contract template is adapted inside an authorized application
task. This skill does not instrument arbitrary apps, enforce agent behavior or
authorize device actions. Existing tasks must reread the installed skill before
using it; file deployment alone does not establish adoption or app integration.
