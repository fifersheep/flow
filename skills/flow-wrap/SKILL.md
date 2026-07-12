---
name: flow-wrap
description: Flow phase 8 (wind-down; also the lite-mode wrap). Normally invoked via /flow. Learnings capture + marks the task complete ON THE BRANCH, then merge + cleanup — so the completion marker rides in the original PR, never a follow-up.
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

**Order matters: everything that touches a repo file — learnings AND the
`phase: complete` marker — is committed to the task branch BEFORE the merge, so it
all rides in the original PR. Never open a separate "mark complete" follow-up PR.**

1. **Learnings capture.** Review the task for durable lessons: a gotcha hit
   twice, a correction the user made, a convention discovered. For each,
   propose a concrete diff to CLAUDE.md, a domain skill, or memory — ONE at a
   time, user approves each. No approval → no edit. Zero lessons is a valid
   outcome; never invent one. Repo-file learnings (e.g. CLAUDE.md) are committed
   to the branch; memory lives outside the repo.
2. **Close the record on the branch.** Set `phase: complete`, final `updated`
   bump, and commit ALL wind-down repo changes (approved learnings + this marker)
   to the task branch. This is the last commit before the merge, so the PR
   carries the finished task record. (If the user deferred the merge, still
   commit this, but leave `phase: wind-down` until they actually merge.)
3. **Merge** per the gate-2 decision (merge PR / local merge to the default
   branch) — the PR now includes the learnings and the completion marker. If the
   user chose not to merge yet, skip the merge and go to cleanup.
4. **Cleanup.** `git status` must be clean; remove the worktree if one was
   created; delete the merged branch if the user agrees; verify nothing
   uncommitted is stranded. The task folder stays forever as the record.
   Announce completion with the artifact paths.
