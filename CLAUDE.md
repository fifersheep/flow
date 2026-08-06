# flow — repo guidance

A Claude Code plugin: a phased development workflow (setup → research → plan →
gate 1 → implement → review → gate 2 → wind-down) whose gates are enforced by a
PreToolUse hook rather than by prompt discipline. See README.md for usage and
`docs/specs/2026-07-04-flow-workflow-design.md` for the design.

Layout: `skills/` (phase skills), `agents/` (subagents), `hooks/` (the
validator), `templates/` (files the skills write into target repos),
`.claude-plugin/` (manifests), `scripts/`, `tests/`.

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
    python3 scripts/check_version_bump.py      # manifests agree
    python3 scripts/check_version_bump.py main # ...and are ahead of main

CI (`.github/workflows/version-bump.yml`) runs the same script on every PR and
fails it when the version is unchanged or the manifests disagree. Escape hatch,
user-only: label the PR `no-version-bump`. The check must be marked required in
branch protection for `main` to actually block a merge.
