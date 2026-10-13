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
- Shows where you are (a Claude Code mod, `hooks/mod/`), all display, never a
  gate: the phase rail above the prompt (straw-framed with approve / request
  changes while a gate waits on you — the buttons only draft the reply, you
  press Enter); `/flow-pane` for progress, plan, decisions, deviations and
  every task across worktrees; `/flow-status` with no model turn; toasts when
  a phase moves, a gate opens or the validator blocks an edit; the phase on the
  status line and under the spinner. Colours are the four of the status line's
  progress bars (ANSI-256 67/108/186/210). Read from one snapshot,
  `hooks/flow_status.py`. With mods off, flow works exactly as without it.
- Opens a task's worktree on request: `t` (terminal) and `e` (editor) on the
  rail — gate or not — and at the top of `/flow-pane` for the task shown
  there, or `/flow-term [task]` and `/flow-code [task]`. With no task on the
  branch they open the session's own checkout. The terminal is an iTerm pane
  split beside this session, and the editor VS Code, unless the plugin's
  settings (`/config`) say otherwise: terminal is `iterm-split`, `iterm-tab`,
  `iterm-window`, `terminal`, `warp` or `tmux` (also a split); editor is
  `vscode`, `cursor` or `zed`. A split's side (`splitSide`: right, left, top,
  bottom) and share of Claude Code's pane (`splitSize`, %) are settings too.
  iTerm's AppleScript only splits right or below at half, so any other iTerm
  split uses its Python API (Settings → General → Magic → Enable Python
  API), with the `iterm2` package flow installs into `~/.cache/flow` on first
  use; if that can't be had it splits right or below at half and points at
  `/flow-term setup`, a checklist of what the chosen split needs — iTerm, the
  API setting, the package (installed there if missing), a test connection —
  with the fix beside each missing piece. The opening is
  `hooks/flow_open.py`; nothing opens unasked.
- Spec: `docs/specs/2026-07-04-flow-workflow-design.md`.

Install:
    /plugin marketplace add /Users/scoot/dev/flow
    /plugin install flow@flow

Usage: `/flow <task description>` to start; `/flow` to resume; `/flow status` to list;
`/flow shape <idea>` to brainstorm an idea into tracker tickets (upstream of the
workflow — no branch, no state file; ends by offering `/flow start`).
Tests: `python3 -m unittest discover tests -v` and `claude plugin test .` (the mod)
