---
name: flow-start
description: Flow phase 1 (setup). Normally invoked via /flow with a new task description. Creates branch/worktree, task folder, workflow.md; recommends full or lite mode.
---

# Flow — setup

Argument: a task description, optionally with a ticket ref (e.g. "BEE-93: …").

1. **Read config.** `.flow.md` at repo root: `verify`, `verify-app`,
   `setup` (dependency-install command for fresh checkouts), `artifacts-dir`
   (default `docs/tasks`), `worktrees`, `domain-agents`.
   Missing file → defaults; ask for the verify command once and offer to
   save a `.flow.md`.
2. **Recommend a mode.** lite = small, well-understood, few files, no design
   questions; full = everything else. Recommend one with a one-line reason;
   the user confirms (AskUserQuestion, options full/lite). If the user
   already stated a mode ("a lite ticket", "run this full"), don't re-ask —
   announce the mode with your reason and move on.
3. **Create isolation.** Branch `flow/<slug>` from the default branch
   (worktree at the `.flow.md` `worktrees` path if configured; plain branch
   otherwise). Slug: kebab-case, ≤5 words, from the task description.
4. **Baseline checks.** Working tree clean; run `setup` first if configured
   (a fresh worktree has no installed dependencies), then `verify` — record
   pass/fail in workflow.md `Next action` (a red baseline is not fatal but
   MUST be recorded, so later failures are attributable).
5. **Create the task folder** `<artifacts-dir>/YYYY-MM-DD-<slug>/` and write
   `workflow.md` from the plugin's `templates/workflow.md`, filling every
   `{{placeholder}}`. `phase: setup`, `mode` as confirmed, `ticket` free text.
6. **Advance.** Set `updated`, set `phase: research` (full) or
   `phase: planning` (lite), write `Next action`, announce the transition,
   then invoke the `flow-research` or `flow-plan` skill.

Rules: never start on the default branch; never set `force:`; if a workflow.md
write is blocked by the validator, fix the transition — never work around it.
