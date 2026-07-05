---
name: flow-plan
description: Flow phases 3–4 (planning + gated plan review). Normally invoked via /flow. Writes a lean plan.md, runs the plan-critic, then holds at gate 1 for user approval.
---

# Flow — plan & plan review

## Phase 3: write the plan (inline, user watching)

Write `plan.md` in the task folder from the plugin's `templates/plan.md`:
- **Intent** + **falsifiable acceptance criteria** (each checkable by a
  command, test, or observation).
- **Approach** chosen, alternatives noted in one line each.
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
   and the critic's verdict summary. Ask approve / revise (AskUserQuestion).
   Revisions loop back to the user, not to the critic.
3. **On approval** (never before): append to the decision log
   `- YYYY-MM-DD gate 1: plan approved by user`, set
   `phase: implementation`, update `updated` + `Next action`, announce, and
   invoke the `flow-implement` skill.

The validator blocks `phase: implementation` without the gate-1 line, and
blocks all code edits until then. If blocked, you skipped a step — fix the
process, never the guardrail.
