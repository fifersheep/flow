---
name: flow
description: Phased development workflow driver. Use when starting /flow, resuming flow work, or asking "where was I?" on a flow task. Reads docs/tasks/*/workflow.md state and routes to the right phase skill.
---

# Flow — driver

You route; phase skills do the work. Never perform a phase's work inline here.

## Locate state

1. Artifacts dir: `artifacts-dir:` from `.flow.md` at the repo root, else `docs/tasks`.
2. Active tasks: every `<artifacts-dir>/*/workflow.md` with `phase` ≠ `complete`.
3. Current branch: `git branch --show-current`.

## Route

- **`/flow` with a task description** (no matching active task): invoke the
  `flow-start` skill with the description as argument.
- **`/flow` bare, one active task on this branch**: announce
  `<task> — phase <phase>; next: <Next action from workflow.md>`, then invoke
  the skill for that phase (table below).
- **`/flow` bare, several active tasks (any branch)**: list them
  (`task / phase / branch / updated`) and ask which to resume. If the chosen
  task's branch ≠ current branch, tell the user to switch branch/worktree
  first — do not switch for them.
- **`/flow status`**: print the list; route nowhere.

| phase          | skill          |
|----------------|----------------|
| setup          | flow-start     |
| research       | flow-research  |
| planning       | flow-plan      |
| plan-review    | flow-plan      |
| implementation | flow-implement |
| code-review    | flow-review    |
| reporting      | flow-report    |
| wind-down      | flow-wrap      |

## Rules

- `workflow.md` is the single routing input. Never infer phase from git or vibes.
- Trust `Next action` for intra-phase resume; phases are internally idempotent.
- Never edit `phase:` here — phase skills own their transitions.
- Announcements reference artifact files by path; never paste their contents.
