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
