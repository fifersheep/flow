---
name: flow-implement
description: Flow phase 5 (implementation). Normally invoked via /flow. Executes plan.md task-by-task with per-task commits and live progress/deviation tracking in workflow.md.
---

# Flow — implement

Before the first task: copy plan.md's task list into workflow.md `## Progress`
as unchecked boxes (one per plan task), if not already there.

Per plan task, in order:
1. Implement exactly what the task says. TDD where the task has testable
   logic: failing test → minimal code → green.
2. Run the task's verification step from plan.md.
3. Commit (`<type>: <plan task title>`).
4. Tick the task in `## Progress` (add the commit sha) and bump `updated`.

**Deviations:** the moment reality diverges from plan.md (extra file, changed
approach, dropped step), record one line in `## Deviations` — in the same
turn, not later. Big divergence (approach invalidated, scope grew) → stop,
set `phase` back to `planning`, tell the user why.

**Delegation:** if `.flow.md` maps the task's file zone to a domain agent,
dispatch that agent with: the plan task text verbatim, the worktree path +
branch, and "report files touched + verification output". Verify its report
against `git diff` before ticking. Otherwise implement inline — one coherent
context beats a fleet.

When every Progress box is ticked: run the project `verify` command, set
`phase: code-review`, update `Next action`, announce, invoke the
`flow-review` skill.

Resume: on entry, trust `## Progress` — start at the first unticked task.
