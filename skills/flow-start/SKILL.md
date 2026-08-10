---
name: flow-start
description: Flow phase 1 (setup). Normally invoked via /flow with a new task description. Creates branch/worktree, task folder, workflow.md; recommends full or lite mode.
---

# Flow — setup

Argument: a task description, optionally with a ticket ref (e.g. "BEE-93: …").

1. **Read config.** `.flow.md` at repo root: `verify`, `verify-app`,
   `setup` (dependency-install command for fresh checkouts), `artifacts-dir`
   (default `docs/tasks`), `worktrees`, `domain-agents`, `tracker` and
   `## tracker-status` (see the plugin's `templates/tracker-sync.md`).
   Missing file → defaults; ask for the verify command once and offer to
   save a `.flow.md`.
2. **Check the ticket.** Parse the leading identifier out of the argument
   ("BEE-93: …" → `BEE-93`); no identifier → skip this step, `ticket-id`
   stays blank. With a tracker configured, read the ticket and report its
   title + current status on one line. **A ticket already in a completed or
   canceled status stops setup** — say so and confirm with the user before
   going further; it usually means the work is already done and this is a
   re-run.
3. **Recommend a mode.** lite = small, well-understood, few files, no design
   questions; full = everything else. Recommend one with a one-line reason;
   the user confirms (AskUserQuestion, options full/lite). If the user
   already stated a mode ("a lite ticket", "run this full"), don't re-ask —
   announce the mode with your reason and move on.
4. **Create isolation.** Branch `flow/<slug>` from the default branch
   (worktree at the `.flow.md` `worktrees` path if configured; plain branch
   otherwise). Slug: kebab-case, ≤5 words, from the task description.
5. **Baseline checks.** Working tree clean; run `setup` first if configured
   (a fresh worktree has no installed dependencies), then `verify` — record
   pass/fail in workflow.md `Next action` (a red baseline is not fatal but
   MUST be recorded, so later failures are attributable).
6. **Create the task folder** `<artifacts-dir>/YYYY-MM-DD-<slug>/` and write
   `workflow.md` from the plugin's `templates/workflow.md`, filling every
   `{{placeholder}}`. `phase: setup`, `mode` as confirmed, `ticket` free text,
   `ticket-id` the bare identifier from step 2 (blank if none). Then move the
   ticket to the `start` status per `templates/tracker-sync.md` and record
   `tracker-synced`.
7. **Advance.** Set `updated`, set `phase: research` (full) or
   `phase: planning` (lite), write `Next action`, announce the transition,
   then invoke the `flow-research` or `flow-plan` skill.

Rules: never start on the default branch; never set `force:`; if a workflow.md
write is blocked by the validator, fix the transition — never work around it.
A failed tracker move is recorded and announced, never fatal — full rules in
`templates/tracker-sync.md`.
