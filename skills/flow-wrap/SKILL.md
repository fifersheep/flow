---
name: flow-wrap
description: Flow phase 8 (wind-down; also the lite-mode wrap). Normally invoked via /flow. Learnings capture, merge + cleanup, marks the task complete.
---

# Flow — wrap

## Lite mode entry (arriving from code-review)

Gate 2 hasn't run yet — run it first, in miniature:
1. Append a `## Quick report` section to workflow.md: 3–6 lines — what
   changed, verify output (pasted), deviations if any.
2. Open the PR (or present the local merge) as in flow-report step 2.
3. Ask approve-merge / request-changes. On approval append
   `- YYYY-MM-DD gate 2: merge approved by user`, THEN set
   `phase: wind-down`.

## Wind-down (both modes)

1. **Merge** per the gate-2 decision (merge PR / local merge to the default
   branch). If the user chose not to merge yet, skip merge but finish the rest.
2. **Learnings capture.** Review the task for durable lessons: a gotcha hit
   twice, a correction the user made, a convention discovered. For each,
   propose a concrete diff to CLAUDE.md, a domain skill, or memory — ONE at a
   time, user approves each. No approval → no edit. Zero lessons is a valid
   outcome; never invent one.
3. **Cleanup.** `git status` must be clean; remove the worktree if one was
   created; delete the merged branch if the user agrees; verify nothing
   uncommitted is stranded.
4. **Close.** Set `phase: complete`, final `updated` bump. The task folder
   stays forever as the record. Announce completion with the artifact paths.
