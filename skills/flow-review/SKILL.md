---
name: flow-review
description: Flow phase 6 (code review). Normally invoked via /flow. Dispatches the flow-reviewer against the diff and plan, fixes blocking findings inline, runs outcome verification.
---

# Flow — code review

1. **Dispatch `flow-reviewer`** (once) with: diff range
   (`<default-branch>...HEAD`), plan.md path, repo root, and the project's
   verify command. Do not review your own work inline instead — the fresh
   context IS the point.
2. **Write `review.md`** in the task folder from the reviewer's findings:
   Blocking / Advisory / Acceptance-criteria table / Checked. Note next to
   each finding what was done about it.
3. **Fix Blocking findings inline** (main session, visible), one commit per
   fix. Advisory: fix cheap ones; record the rest as report follow-ups.
   NOT-MET acceptance criteria are Blocking by definition.
4. **Re-verify:** project `verify` command must pass. Then **outcome
   verification**: run `verify-app` if configured, else drive the changed
   behavior by hand (run the app, exercise the feature) — green units alone
   don't count. Capture real output/screenshots for the report.
5. **Advance.** Update `updated` + `Next action`. Full mode: set
   `phase: reporting`, announce, invoke the `flow-report` skill. Lite mode:
   stay in `code-review` and invoke the `flow-wrap` skill (it owns gate 2).

One reviewer pass. If fixes were extensive (>~30% of the diff changed),
tell the user and offer a second pass — never loop silently.
