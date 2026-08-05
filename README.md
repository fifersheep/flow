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
- Spec: `docs/specs/2026-07-04-flow-workflow-design.md`.

Install:
    /plugin marketplace add /Users/scoot/dev/flow
    /plugin install flow@flow

Usage: `/flow <task description>` to start; `/flow` to resume; `/flow status` to list;
`/flow shape <idea>` to brainstorm an idea into tracker tickets (upstream of the
workflow — no branch, no state file; ends by offering `/flow start`).
Tests: `python3 -m unittest discover tests -v`
