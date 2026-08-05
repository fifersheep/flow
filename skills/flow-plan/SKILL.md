---
name: flow-plan
description: Flow phases 3–4 (planning + gated plan review). Normally invoked via /flow. Writes a lean plan.md, runs the plan-critic, then holds at gate 1 for user approval.
---

# Flow — plan & plan review

## Phase 3: write the plan (inline, user watching)

**Lite mode only — triage unknowns first.** Lite skips research, so this is
the only place they get caught. Sort them as `flow-research` step 4 does and
ask the shape-changing ones in ONE AskUserQuestion round before writing
anything; log the answers to the decision log. Needing a second round means
lite was the wrong mode — say so.

Write `plan.md` in the task folder from the plugin's `templates/plan.md`:
- **Intent** + **falsifiable acceptance criteria** (each checkable by a
  command, test, or observation).
- **Approach** chosen, alternatives noted in one line each.
- **Assumptions & open questions** — every unknown resolved without asking,
  marked `[answered]` / `[assumed]` / `[open — owner]`. An empty section
  claims the plan made zero judgment calls; that is rare, not the default.
- **Tasks**: file-level — every task names the files it touches and its
  verification step. Guardrail: if the Tasks section is longer than the diff
  you expect it to produce, cut it down before proceeding.
- **Out of scope** + **Verification** (machine commands AND how to drive the
  app/feature end-to-end).

Then set `phase: plan-review`, update `Next action`.

## Phase 4: gated review

1. **Critic pass (once).** Dispatch `flow-plan-critic` with the plan.md,
   research.md, and repo paths. Revise plan.md for Blocking findings; use
   judgment on Advisory ones. ONE critic pass — do not re-dispatch after
   revising.
2. **User gate.** Present: plan.md by path, a ≤5-line summary of the approach,
   one line tallying the Assumptions section ("3 assumptions — 1 you answered,
   1 repo default, 1 left open"), and the critic's verdict summary. Ask
   approve / revise (AskUserQuestion). The tally is disclosure, not a fresh
   question round — the asking already happened upstream; this only makes sure
   approval is informed. Revisions loop back to the user, not to the critic.
3. **On approval** (never before): append to the decision log
   `- YYYY-MM-DD gate 1: plan approved by user`, set
   `phase: implementation`, update `updated` + `Next action`, announce, and
   invoke the `flow-implement` skill.

The validator blocks `phase: implementation` without the gate-1 line and
without a filled Assumptions section in plan.md, and blocks all code edits
until then. A plan that genuinely made no judgment calls writes
`- none — <reason>`; an empty section is not a way out. If blocked, you
skipped a step — fix the process, never the guardrail.
