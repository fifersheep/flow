# Plan — {{title}}

## Intent
{{1–3 sentences: what and why}}

## Acceptance criteria
<!-- falsifiable; each one checkable by command, test, or observation -->
- [ ] {{criterion}}

## Approach
{{chosen approach; alternatives considered, one line each}}

## Assumptions & open questions
<!-- every entry carries a marker:
     [answered YYYY-MM-DD]  user decided this — mirrored in workflow.md's decision log
     [assumed]              taken as repo default; cite the evidence (file:line)
     [open — <owner>]       deliberately unresolved; name who resolves it and when
     Empty only if the task genuinely required zero judgment calls. -->
- {{marker}} {{assumption}} — {{evidence or rationale}}

## Tasks
<!-- file-level; each task lists files touched + its verification step.
     Guardrail: if this section grows longer than the expected diff, stop and cut. -->
1. {{task}} — files: {{paths}} — verify: {{command or check}}

## Out of scope
- {{explicitly not doing}}

## Verification
- Machine: {{project verify commands}}
- Outcome: {{how to drive the app/feature end-to-end}}
