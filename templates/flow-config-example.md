# Flow config (.flow.md) — copy to a repo root and edit

verify: {{e.g. flutter analyze && flutter test}}
verify-app: {{optional outcome-check command}}
setup: {{optional dependency install for fresh checkouts, e.g. flutter pub get}}
artifacts-dir: docs/tasks
worktrees: {{e.g. .worktrees/<branch>}}
tracker: {{optional, e.g. linear — omit for no ticket-status sync}}

## tracker-status
<!-- optional; omit the section for the defaults shown. Use the tracker's own
     status NAMES, not types — "In Progress" and "In Review" are usually the
     same type. See templates/tracker-sync.md -->
- start → In Progress
- pr-open → In Review
- merged → Done

## domain-agents
<!-- zone → implementer agent; omit section to implement inline -->
- {{lib/ui/ → bee-ui}}

## on
<!-- optional; phase name → shell command, run ONCE when a task enters that
     phase. Phases: setup, research, planning, plan-review, implementation,
     code-review, reporting, wind-down, complete.

     The command runs from the repo root with FLOW_PHASE, FLOW_PREV_PHASE,
     FLOW_TASK, FLOW_TITLE, FLOW_MODE, FLOW_BRANCH, FLOW_WORKTREE,
     FLOW_TICKET_ID, FLOW_TASK_DIR and FLOW_REPO set. Side effects only: a
     failure is reported to you and dropped, never fatal, and never a gate.

     .flow.md is checked in, so anything here runs automatically for anyone who
     runs flow in this repo. Keep machine-specific commands out of it.

     "Open the new worktree in my editor" does NOT belong here: flow makes a
     worktree at setup, but so do --worktree, EnterWorktree and agent isolation,
     and none of those are flow phases. That wants a user-level Claude Code hook
     on PostToolUse/Bash + CwdChanged. -->
- {{implementation: osascript -e 'display notification "flow: plan approved"'}}
- {{complete: gh pr view --web}}
