---
name: flow-research
description: Flow phase 2 (research). Normally invoked via /flow. Codebase recon plus optional web research; writes research.md with file:line references.
---

# Flow — research

1. **Codebase recon first** (inline): what already exists for this task —
   relevant files, conventions, constraints, prior art (existing specs/plans,
   git history). Small task area → do it all inline.
2. **Fan out only for breadth.** Up to 3 parallel `flow-researcher` agents,
   each with ONE scoped question (e.g. one per subsystem, or one for an
   unfamiliar library). Cap at 3; if you want more, the task is too big —
   say so. Web research only when the task genuinely needs outside knowledge.
   Dispatch synchronously when you'd only wait anyway; if you background
   them, end each prompt with "deliver your findings via SendMessage to
   main" — background agents otherwise idle silently with the results
   stranded in their own context.
3. **Write `research.md`** in the task folder: Findings (with file:line),
   Constraints & prior art, Open questions. Dense; no pasted file bodies.
4. **Surface open questions** that change the plan's shape to the user now —
   cheaper than a rejected plan at gate 1.
5. **Advance.** Update `updated` + `Next action`, set `phase: planning`,
   announce (reference research.md by path), invoke the `flow-plan` skill.

Idempotent resume: if research.md already has findings, extend — don't redo.
