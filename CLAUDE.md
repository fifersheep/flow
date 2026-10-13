# flow — repo guidance

A Claude Code plugin: a phased development workflow (setup → research → plan →
gate 1 → implement → review → gate 2 → wind-down) whose gates are enforced by a
PreToolUse hook rather than by prompt discipline. See README.md for usage and
`docs/design.md` for why it's built that way.

Layout: `skills/` (phase skills), `agents/` (subagents), `hooks/` (the
validator and its shell-command reader `flow_shell.py`, the snapshot script,
the worktree opener, and the display mod in `hooks/mod/`), `types/` (the mod's state contract), `templates/` (files the
skills write into target repos), `.claude-plugin/` (manifests), `scripts/`
(`scripts/demo/` retakes the README's screenshots), `tests/`.

## Version bumps — every change, no exceptions

Every PR bumps the plugin version. Installed copies have no other signal that
they are stale, so an unbumped change ships invisibly.

Bump **all three** version fields together — they must always be equal:

- `.claude-plugin/plugin.json` → `version`
- `.claude-plugin/marketplace.json` → `metadata.version`
- `.claude-plugin/marketplace.json` → `plugins[0].version`

Which digit:

- **patch** (0.3.0 → 0.3.1) — fixes, docs, test-only changes, wording that
  doesn't change what a skill does.
- **minor** (0.3.0 → 0.4.0) — a new skill, agent, or template; any change to
  what the workflow asks of the user or what the validator blocks.
- **major** — a breaking change to state-file format, config, or gate
  semantics: an in-flight task in a target repo would break on upgrade.

Bumping is the last edit before committing, so it reflects everything in the
PR. One bump per PR, not one per commit.

## Checks

    python3 -m unittest discover tests -v      # full suite
    claude plugin test .                       # the mod (tests/mod/)
    claude plugin validate .                   # manifest + mod scan
    python3 scripts/check_version_bump.py      # manifests agree
    python3 scripts/check_version_bump.py main # ...and are ahead of main

CI (`.github/workflows/version-bump.yml`) runs the same script on every PR and
fails it when the version is unchanged or the manifests disagree. Escape hatch,
user-only: label the PR `no-version-bump`. The check must be marked required in
branch protection for `main` to actually block a merge.

## README images

The images in `docs/images/` are captured from a live Claude Code session,
never drawn by hand. Retake them in the PR that changes what they show:

| Image | Shot | Shows | Retake after changing |
|---|---|---|---|
| `hero.png` | `hero` | the rail mid-implementation | the band (`hooks/mod/band.tsx`, `look.tsx`), the snapshot (`hooks/flow_status.py`) |
| `gate.png` | `gate` | the rail at gate 1 | the band, gate actions |
| `gate.gif` | `gif` | approving gate 1 (one model turn) | the band, gate actions, phase toasts |
| `blocked.png` | `blocked` | a refused edit (one model turn) | the validator's message, the refusal toast |
| `pane-progress.png`, `pane-tasks.png` | `pane-progress`, `pane-tasks` | `/flow-pane` | `hooks/mod/pane.tsx` |
| `status.png` | `status` | `/flow-status` | `hooks/mod/status.tsx`, `hooks/flow_status.py` |
| `split.png` | `split` | `t` opening a terminal | `hooks/flow_open.py`, the band's key hints |
| `setup.png` | `setup` | `/flow-term setup` (iTerm only) | `hooks/flow_iterm.py`, the setup checklist |

    scripts/demo/shoot.py --check     # what's missing, with install commands
    scripts/demo/shoot.py             # every shot, into docs/images (~6 min)
    scripts/demo/shoot.py gate hero   # just these

- It loads flow from this checkout, so run it from the branch or worktree
  being changed, after the code change.
- It needs tmux, freeze, Chrome or Chromium, claude and ffmpeg. The font is
  fetched and hash-checked on first run.
- The `setup` shot runs only inside iTerm with its Python API on. Elsewhere it
  is skipped and the old image stays.
- Seven shots are byte-identical from run to run, so if one of their files
  changed, the picture changed. `blocked` and `gif` include a model turn and
  differ every run, so retake them only when what they show has changed.
- Open every image it wrote before committing. Each one should show what the
  README text next to it says, with no stray toasts, a light theme or cut-off
  rows. If the README text no longer matches the UI, fix the text too.
- The demo repo is rebuilt from `scripts/demo/make-demo-repo.sh` each run.
  Change the fictional tasks there, not by hand.
