# flow

Personal phased development workflow for Claude Code:
setup → research → plan → **gate 1** → implement → review-vs-plan → **gate 2** → wind-down.

- State: `docs/tasks/<date>-<slug>/workflow.md` in the target repo (resumable from any session).
- Gates enforced by a PreToolUse hook (`hooks/flow_validate.py`) — illegal phase
  transitions and pre-approval code edits are blocked, not discouraged. Gate 1
  also requires plan.md to declare its assumptions, so a plan can't reach
  implementation on an unstated guess.
- Escape hatch (user-only): add `force: true` to a task's workflow.md frontmatter.
- Per-repo config: `.flow.md` (see `templates/flow-config-example.md`).
- Optional tracker status sync: with `tracker:` in `.flow.md` and a `ticket-id:`
  on the task, flow moves the ticket In Progress at setup → In Review when the
  PR opens → Done on merge, and warns at wind-down if the ticket drifted from
  where it should be. Off unless configured; a failed move is recorded in
  Deviations and announced, never fatal. Contract: `templates/tracker-sync.md`.
- Optional per-phase hooks: an `## on` section in `.flow.md` maps a phase name
  to a shell command, run once when a task enters that phase (PostToolUse hook,
  `hooks/flow_events.py`). Side effects only — a failure is reported and
  dropped, never fatal, never a gate. `.flow.md` is checked in, so its commands
  run for anyone who runs flow in that repo.
- Spec: `docs/specs/2026-07-04-flow-workflow-design.md`.

Install:
    /plugin marketplace add /Users/scoot/dev/flow
    /plugin install flow@flow

Usage: `/flow <task description>` to start; `/flow` to resume; `/flow status` to list;
`/flow shape <idea>` to brainstorm an idea into tracker tickets (upstream of the
workflow — no branch, no state file; ends by offering `/flow start`).
Tests: `python3 -m unittest discover tests -v`
