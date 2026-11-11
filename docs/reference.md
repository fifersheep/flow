# flow reference

The details behind the [README](../README.md). The reasoning behind the
design is in [design.md](design.md).

## Task state

Each task is a folder under the artifacts dir (`docs/tasks/` unless `.flow.md`
says otherwise), named `<date>-<slug>`:

| File | Written by | Holds |
|---|---|---|
| `workflow.md` | every phase | frontmatter (task, mode, phase, branch, worktree, ticket, dates), next action, decision log, progress checklist, deviations |
| `research.md` | research (full mode) | findings with file:line references, constraints, open questions |
| `plan.md` | planning | intent, acceptance criteria, approach, assumptions, file-level tasks, verification |
| `report.md` | reporting (full mode) | what was built, with real command output |

`workflow.md` is the only thing `/flow` routes on. Templates are in
[`templates/`](../templates/).

## The validator

`hooks/flow_validate.py` runs before every Write, Edit and Bash call. On a
task's `workflow.md` it checks the phase change:

- the phase must be legal for the task's mode, and a new `workflow.md` starts
  at `setup`;
- no phase may be skipped;
- `implementation` needs a dated `gate 1:` entry in the decision log (the
  skills write `- 2026-10-13 gate 1: plan approved by user`) and a filled
  Assumptions section in `plan.md` (a plan that made no judgment calls writes
  `- none — <reason>`);
- `wind-down` needs a dated `gate 2:` entry.

On any other file in the repo, it refuses code edits while the task on that
branch is before implementation, or in reporting with gate 2 pending. Flow's
own files (the task folder, `.flow.md`) stay writable, and so does anything
outside the repo, such as `/tmp`.

A Bash command is held to the same rule for the files it visibly writes.
`hooks/flow_shell.py` reads the command before it runs (quotes, `&&`, `;`,
pipes, newlines, heredocs, `cd X &&`, `bash -c`) and picks out:

- redirects: `>`, `>>`, `>|`, `&>`, `>&file`;
- `tee`, `sed -i`, `perl -i`, `mv`, `cp`, `ln`, `rm`, `touch`, `mkdir`,
  `truncate`, `dd of=`;
- `git apply` and `patch` (the tree they run in), `git restore`,
  `git checkout -- <path>`;
- a `python -c`, `node -e` or `ruby -e` that opens a literal path for writing.

Each path is resolved from the hook's `cwd` and decided like a Write: refused
inside a locked checkout unless it's the task folder or `.flow.md`. Paths
outside any checkout (`/tmp`, `/dev/null`) are never locked, and reads, test
runs, `git switch`/`commit`/`worktree`, and installs aren't writes to it. The
refusal names the file and how it was written:

    flow: task 'demo' is in phase 'planning' — code edits are locked until
    gate 1 (plan approval) is recorded in …/workflow.md; this command writes
    src/a.py (via >)

It's a heuristic, not a sandbox: a path in a variable, a script file, `xargs`,
`find -exec` or a build tool writes where it can't see, and a command it can't
parse is allowed. `force: true` in the frontmatter switches the validator off
for that task.

## Tracker sync

With `tracker:` in `.flow.md` and a `ticket-id:` on the task, flow moves the
ticket at three points: In Progress at setup, In Review when the PR opens,
Done on merge. Wind-down warns if the ticket has drifted from where it should
be. Status names can be overridden in `## tracker-status`.

A failed move is never fatal: it's recorded under Deviations and announced,
and the phase carries on. Contract: [`templates/tracker-sync.md`](../templates/tracker-sync.md).

## Per-phase commands

An `## on` section in `.flow.md` maps a phase to a shell command, run once when
a task enters that phase, from the repo root, with the task in `FLOW_*`
environment variables (`FLOW_PHASE`, `FLOW_TASK`, `FLOW_BRANCH`,
`FLOW_WORKTREE`, …). A PostToolUse hook (`hooks/flow_events.py`) runs them,
never the skills.

They're side effects only: a failure is reported and dropped, never fatal and
never a gate. `.flow.md` is checked in, so its commands run for anyone who runs
flow in that repo.

## The display mod

`hooks/mod/` is a Claude Code mod. Every view reads one snapshot,
`hooks/flow_status.py --cwd <dir>`, built on the same parsing the validator
uses, so the picture can't disagree with the gates. It refreshes at session
start, after edits, shell commands and turns, and every 5 seconds while the
repo has tasks.

- **The rail**, above the prompt: phases, gates, progress, next action. At a
  waiting gate the frame turns straw and offers open plan / approve / request
  changes. Those only draft the reply; you press Enter.
- **`/flow-pane`**: Progress, Plan, Decisions, Deviations, Tasks (1–5).
- **`/flow-status`**: the same as text, with no model turn.
- **Toasts** when a phase moves, a gate opens or is approved, a deviation is
  recorded, or the validator refuses an edit or a shell write.
- **The status line and the spinner** carry the phase.

Colour has one meaning each: periwinkle (ANSI 67) is where the task is, sage
(108) is done, straw (186) is waiting on you, rose (210) is blocked or a
deviation; dim is not reached yet. The terminal gets the ANSI-256 index
itself, since hex there is downsampled to a different colour.

## Opening a worktree

`t` / `/flow-term [task]` opens a terminal there, and `e` / `/flow-code [task]`
your editor. A task is named by slug, folder or ticket id. With none named it's
the session's task, else the session's own checkout. `hooks/flow_open.py` does
the opening.

| Setting | Values |
|---|---|
| `terminal` | `iterm-split` (default), `iterm-tab`, `iterm-window`, `terminal`, `warp`, `tmux`, `herdr` |
| `editor` | `vscode` (default), `cursor`, `zed` |
| `splitSide` | `right` (default), `left`, `top`, `bottom` |
| `splitSize` | the new pane's share of Claude Code's pane, 10–90 (default 50) |

`iterm-split` splits the pane Claude Code runs in, found by `ITERM_SESSION_ID`,
so it lands there even when another tab has focus. iTerm's AppleScript only
splits right or below at half; anything else goes through iTerm's Python API
(`hooks/flow_iterm.py`), in a venv flow creates in `~/.cache/flow/iterm2-venv`
with the `iterm2` package from PyPI, on first use. If the API is off or the
install fails, flow splits right or below at half and says why.

`/flow-term setup` checks what the chosen split needs: Claude Code running in
iTerm, the API setting, the package (installing it if missing), and a test
connection. Each missing piece comes with its fix.

## In Herdr

[Herdr](https://herdr.dev) runs every terminal in herdr-core and names the
session's own in `HC_TERMINAL_ID`. When that's set and `herdr-app` is on
PATH, flow uses it (`hooks/flow_herdr.py`):

- **The split.** `herdr` splits the pane Claude Code runs in, through
  `herdr-app do`, and so does the default `iterm-split` when the session
  isn't in iTerm. Herdr splits right or down at half: `left` and `top` swap
  the new pane across, and `splitSize` doesn't apply. `/flow-term setup`
  says which split it will make.
- **Labels.** Every write to a `workflow.md` labels the session's terminal
  with `hc label`, the session's start labels the task it's on, and its end
  takes them off. A Herdr mod reads them live from `terminals()[i].labels`:

  | Label | Value |
  |---|---|
  | `flow.task` | the task's slug |
  | `flow.phase` | its phase |
  | `flow.mode` | `full` or `lite` |
  | `flow.progress` | `done/total` of the Progress checklist; absent when it's empty |
  | `flow.gate` | the waiting gate's number; absent when no gate waits |
  | `flow.dir` | the task's folder |

  A completed task keeps only `flow.task` and `flow.phase=complete`. Like
  the rest of the mod, they're display: a failed label never touches the
  session or a gate.
- **The panel.** `herdr/flow/` is a Herdr mod. `/flow-herdr install` copies
  it to `~/.config/herdr-app/mods/flow/` with a `flow.json` naming the
  plugin's folder, so it can run `hooks/flow_status.py`; `/flow-herdr` opens
  it beside the session's own pane; `/flow-herdr remove` takes it away.
  Each session's start refreshes an installed copy when the plugin is
  newer, and never installs one you didn't ask for.

  It shows a card per task: every active task in the repos of the agents
  labelled with one, and in the focused space's repo. A card has the phase
  rail (the current phase breathes while its agent works), the checklist's
  progress, the next action, deviations, the sessions on it, and a straw
  block while a gate waits, with **Go to agent**. Click a card for its
  progress, plan (as markdown), decisions and deviations. It never answers
  a gate: that stays in the session, where the validator holds it.

  While a copy of the panel is running (open in any tab, or opened once and
  hidden), it posts a Herdr notification when a gate opens, a phase moves
  or a task completes, unless you're looking at that agent. Clicking one
  goes to the agent. Herdr starts a mod the first time it's shown, so the
  notifications start once the panel has been on screen.
