# Flow — Phased Development Workflow (Design)

**Date:** 2026-07-04
**Status:** Approved (design), pending spec review
**Repo:** `~/dev/flow` (personal plugin)

## Goal

A personal, project-agnostic workflow system that guides every non-trivial development task
through eight phases — **setup → research → planning → plan review → implementation → code
review → reporting → wind-down** — with the user in control at the two boundaries that matter
(plan approval, pre-merge) and durable file-based state so any session can resume any task.

Inspired by superpowers, owned by the user. Replaces "remember which skill to invoke" with a
driver that always knows the next step.

## Requirements (decided during brainstorming)

- **Ownership:** personal plugin, usable across all projects. Project-specific pieces (domain
  agents, verify commands) plug in via per-repo config; nothing project-specific is baked in.
- **Control:** hard gates at plan approval and pre-merge only. All other phase transitions flow
  automatically but announce themselves. Every phase skill is also individually invocable, so
  the user can drive manually at any time.
- **Artifacts:** repo files only. No ticket-system automation in v1 (Linear stays manual).
- **Wind-down produces:** final report artifact, PR with rich generated description, learnings
  capture (proposed CLAUDE.md/skill/memory updates), workspace cleanup.

## Research basis

Three research sweeps (Claude Code orchestration guidance, spec-driven-development frameworks,
review/reporting practices) converged on:

1. **Files on disk are the interface between phases** — durable artifacts, not conversation
   history, carry state; this is also what makes work resumable. (Anthropic best-practices,
   Tyler Burleigh's research→plan→implement→review, Huginn's crash-recovery labels.)
2. **Two human gates pay: intent/plan and pre-merge.** Gating every phase is ceremony.
   (Spec Kit, Kiro, GitHub HITL guidance.)
3. **Right-size ceremony or it kills solo workflows.** Spec Kit measured at 2,000+ lines of
   markdown / 3.5 h review for ~700 LOC vs 8 min iterative prompting (Scott Logic). Every
   successful solo adaptation has a lite escape hatch. Plans should be file-level task lists,
   not prose; "if the plan is longer than the code, it's over-specified."
4. **Review: one fresh-context reviewer, diff-vs-plan, correctness-only.** Reviewer ≠ writer.
   Check conformance (scope creep, silent deviations, weakened tests) before correctness.
   Superpowers v6 itself replaced multi-subagent review loops with a single read-only reviewer
   at comparable defect detection. Verification must be outcome-based (drive the app), not
   green-tests-based.
5. **Reporting has a standard shape:** changed-vs-plan, deviations + why, verification evidence
   (real output, not claims), follow-ups. PR body generated from the artifact trail. A codify
   step promotes learnings to CLAUDE.md/skills/memory (compound engineering).
6. **Implementation wants one coherent context; fan-out is for breadth** (research, review).
   Multi-agent underperforms on tightly-coupled coding (Anthropic multi-agent research system).

Full citations in **References** below.

## Architecture

### Packaging

A plugin in its own git repo (`~/dev/flow`), installed via `/plugin`. Versioned, portable,
cannot collide with project-level `.claude/` content.

```
flow/
├── skills/
│   ├── flow/            # driver: reads state, routes to the right phase skill
│   ├── flow-start/      # phase 1: setup
│   ├── flow-research/   # phase 2
│   ├── flow-plan/       # phases 3–4 (planning + plan-review orchestration)
│   ├── flow-implement/  # phase 5
│   ├── flow-review/     # phase 6
│   ├── flow-report/     # phase 7
│   └── flow-wrap/       # phase 8: wind-down
├── agents/
│   ├── flow-researcher.md   # read-only breadth scout
│   ├── flow-plan-critic.md  # read-only rubric-driven plan attacker
│   └── flow-reviewer.md     # read-only diff-vs-plan reviewer
├── hooks/
│   ├── hooks.json           # hook registrations (PostToolUse, PreToolUse)
│   └── flow-validate        # state-machine validator + edit lockdown script
├── templates/               # workflow.md, plan.md, report.md skeletons
└── docs/specs/              # this document
```

### Task state (in the target repo)

Each task gets one folder, default `docs/tasks/YYYY-MM-DD-<slug>/`, containing `workflow.md`
(the state anchor) plus phase artifacts `research.md`, `plan.md`, `review.md`, `report.md`.

`workflow.md` format:

```markdown
---
task: <slug>
title: <one line>
ticket: BEE-93            # free text, optional
mode: full                # full | lite
phase: implementation     # setup | research | planning | plan-review | implementation
                          # | code-review | reporting | wind-down | complete
branch: <branch name>
worktree: <path, optional>
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

## Next action
<one sentence: what the next /flow invocation should do>

## Decision log
- YYYY-MM-DD  plan approved by user (gate 1)

## Progress
- [x] Task 1 — <name> (commit <sha>)
- [ ] Task 2 — <name>

## Deviations
- <recorded at the moment they happen, not reconstructed later>
```

Rules:
- `workflow.md` is updated **before** each phase transition and after each implementation
  task — recorded state is never ahead of reality.
- Announcements reference artifact files; they never re-paste file contents into context.
- Gate decisions are logged with dates and never re-asked.
- On completion the folder remains as the permanent record (`phase: complete`).

### Project config (`.flow.md`, optional)

Plain markdown read by the flow skills at setup (advisory config, no parser). A repo may
declare at its root:

```markdown
# Flow config
verify: flutter analyze && flutter test         # machine gate commands
verify-app: <command>                           # outcome check (drive the app), optional
artifacts-dir: docs/tasks                       # override artifact location
worktrees: .worktrees/<branch>                  # worktree convention
domain-agents:                                  # zone → implementer agent map
  - lib/game/rendering/ → bee-sprites
  - lib/ui/ → bee-ui
```

No `.flow.md` → sensible defaults: artifacts in `docs/tasks/`, plain feature branch, inline
implementation, verify command discovered from the project (or asked once and offered to save).

## Phases

| # | Phase | Runs | Artifact | Exit |
|---|-------|------|----------|------|
| 1 | Setup (`/flow:start`) | inline | task folder + `workflow.md` | flows |
| 2 | Research | inline + researcher fan-out | `research.md` | flows |
| 3 | Planning | inline | `plan.md` | flows |
| 4 | Plan review | critic subagent, then user | revised `plan.md` + critic summary | 🚧 **HARD GATE** |
| 5 | Implementation | inline (or domain agents via `.flow.md`) | code + commits + progress in `workflow.md` | flows |
| 6 | Code review | reviewer subagent; fixes inline | `review.md` | flows |
| 7 | Reporting | inline | `report.md` + PR | 🚧 **HARD GATE** |
| 8 | Wind-down | inline | learnings diffs + cleanup | complete |

**1 — Setup.** Branch/worktree per project convention; task folder + `workflow.md`; environment
checks (deps present, baseline tests green so later failures are attributable); capture task
statement; recommend full/lite mode, user confirms.

**2 — Research.** Codebase recon first (what exists, files involved, constraints, prior art in
specs/plans/git history); web research only when the task warrants. Breadth fans out to parallel
read-only `flow-researcher` subagents, capped proportional to task size. Findings in
`research.md` with `file:line` references.

**3 — Planning.** One lean `plan.md`: intent + **falsifiable acceptance criteria**; chosen
approach (alternatives noted briefly); **file-level task list** (each task: files touched,
verification step); out-of-scope list; end-to-end verification plan including outcome checks.
Guardrail: a plan longer than the code it describes is over-specified.

**4 — Plan review (gate).** Pass 1: fresh `flow-plan-critic` attacks the plan against a fixed
rubric — falsifiable criteria, hidden assumptions, untestable steps, YAGNI/over-engineering,
missing files, failure modes. Grounded findings only (must point at this codebase); one bounded
pass; the planner revises (the critic never edits). Pass 2: revised plan + critic summary
presented to the user. Nothing proceeds without approval.

**5 — Implementation.** Task-by-task against the plan; progress markers in `workflow.md` after
each task (mid-implementation resume). Inline by default — one coherent context. Where
`.flow.md` maps the touched zone to a domain agent, delegate per zone. TDD where it fits;
commit per plan task; deviations recorded in `workflow.md` as they happen.

**6 — Code review.** Fresh `flow-reviewer` reads the full diff **against `plan.md`**:
conformance first (scope creep, silent deviations, weakened tests/CI, unimplemented acceptance
criteria), then correctness (bugs, edge cases, hidden coupling). Explicitly not style. One pass;
the session records findings by severity in `review.md`; blocking findings fixed inline and
re-verified. Then
outcome verification: project verify commands, plus `verify-app` where defined.

**7 — Reporting (gate).** `report.md`: what changed vs plan; every deviation and why;
verification evidence (actual command output / screenshots); follow-up candidates. PR opened
with description generated from the artifact trail (intent + plan + report). User reviews
report + PR; merge only on approval.

**8 — Wind-down.** Learnings capture: propose concrete diffs to CLAUDE.md / domain skills /
memory — user approves each; flow never edits config unprompted. Workspace cleanup: worktree
removed, branches tidied, nothing uncommitted left behind, `workflow.md` marked complete.
Ticket updates manual.

### Lite mode

For small, well-understood changes: skips phase 2 and phase 4's critic pass, shrinks `plan.md`
to a task list (user still approves it — gate 1 survives in miniature), merges 7+8 into a
single quick wrap. Mode is chosen at setup and recorded in `workflow.md`; it can be upgraded
mid-task if scope grows.

## Agents

Three, all read-only:

- **flow-researcher** — parallel breadth scout; returns structured findings with `file:line`
  refs; summaries only, never raw file dumps.
- **flow-plan-critic** — rubric-driven plan attacker; grounded findings only; single bounded
  pass; no authority to rewrite the plan.
- **flow-reviewer** — diff-vs-plan conformance + correctness; returns findings by severity; no
  edit tools — fixes happen in the main session where the user can see them.

Agents return structured findings; the main session writes the phase artifacts
(`research.md`, `review.md`, …) from them. Agents never write repo files.

Implementation deliberately has **no** flow agent: it runs inline or through project domain
agents. Writer and critic stay separate; the writer stays visible.

## Resume & failure model

- `/flow` with no arguments = "where was I?": lists active task folders across the repo, reads
  `workflow.md`, offers to continue from the recorded phase.
- A phase that dies mid-way (crash, compaction, closed laptop) re-runs from its last recorded
  checkpoint; artifact generation is idempotent.
- Because state is written before transitions, the worst case after a crash is repeating part
  of one phase — never losing a gate decision or completed work.

## Deterministic enforcement (v1 hooks)

The state machine and both gates are enforced by the harness via hooks, not by skill wording.
Both hooks are served by one script, `hooks/flow-validate`, shipped and registered by the
plugin.

**State-machine validation — PostToolUse on writes to `**/workflow.md`.** The script parses
the new frontmatter and rejects the write (exit 2 — the edit is blocked and the error returned
to the model) when:

- the `phase:` value is not in the legal enum;
- the transition skips a phase for the recorded `mode` (full/lite have different legal chains);
- a transition **past a gate** (plan-review → implementation, reporting → wind-down) has no
  matching dated entry in the decision log.

A skipped phase or unapproved gate is therefore impossible to *record*, not merely visible.

**Edit lockdown — PreToolUse on Edit/Write.** When the active task's recorded phase is
setup / research / planning / plan-review, edits to files **outside the task folder** (and
`.flow.md`) are blocked with "gate 1 not passed — code edits locked". The same rule blocks
edits while phase is `reporting` (gate 2 pending). This mechanically enforces what the gates
are for: no implementation before plan approval.

**Escape hatch (required):** `flow-validate` honors a documented manual override (e.g.
`FLOW_FORCE=1` on the invoking command or a `force: true` line the user adds to
`workflow.md` frontmatter by hand) so a validator bug can never wedge legitimate work. The
override is for the user, not for skills — no flow skill may instruct its use.

**Trust model:** hooks check state the model itself writes; they defend against drift and
sloppiness (the realistic failure mode), not adversarial forgery — the same trust model as CI.
Verify-stamp enforcement (phase advance requires a fresh passing verify run recorded against
current HEAD) is deliberately deferred to v2.

## Guardrails (baked into skill wording)

- Reviewer and critic: "flag only correctness/requirement gaps" — no nitpicks, no manufactured
  findings.
- Research fan-out capped; breadth proportional to task size.
- Every phase: write artifact → announce with a file reference → move on. No re-pasting.
- No phase loops more than once without surfacing to the user.
- Evidence over assertion everywhere: reports quote real command output.

## Rollout

1. Build the plugin repo (skills, agents, templates) and install via `/plugin`.
2. Shakedown on real bee-topia tickets: one **lite** task, one **full** task; fix friction as
   found.
3. Bee-topia gets a `.flow.md` mapping its domain agents and verify commands; its existing
   `docs/superpowers/` history and the superpowers plugin remain untouched — flow owns only its
   own artifacts, so the two coexist and superpowers habits can be retired gradually.

## Out of scope (v1)

- Linear/ticket automation (manual).
- Verify-stamp enforcement and Stop-hook gates on verify commands (natural v2 extensions of
  `flow-validate`; the two v1 hooks above are in scope).
- Dynamic-workflow/ultracode integration.
- Multi-machine sync beyond git.

## Risks

- **Driver drift** — skills are advisory; the driver could skip a phase. Mitigated
  mechanically: the PostToolUse validator makes illegal transitions and unapproved gate
  crossings impossible to record, and the PreToolUse lockdown blocks pre-approval code edits.
- **State/reality divergence** — if a session edits code without updating `workflow.md`, resume
  misroutes. Pre-approval divergence is blocked by the edit lockdown; during implementation it
  remains advisory (write-before-transition rule). Worst case the user corrects `phase:` by
  hand (it's one line of markdown).
- **Validator bug blocks legitimate work** — a buggy `flow-validate` could reject valid
  transitions or edits. Mitigated by the documented user-only escape hatch and by keeping the
  script small and covered by its own tests.
- **Ceremony creep** — the same failure that killed Spec Kit for solo devs. Mitigated by lite
  mode, the plan-length guardrail, and single-pass critics/reviewers.
- **Two workflow plugins installed** (flow + superpowers) both wanting to drive. Mitigated:
  flow is invoked explicitly (`/flow…`); superpowers' auto-triggering skills mostly govern
  inline work and don't read flow's artifacts. If conflicts surface in shakedown, disable the
  overlapping superpowers skills.

## References

- Anthropic best practices / subagents / skills: code.claude.com/docs/en/best-practices,
  /sub-agents, /skills
- Anthropic multi-agent research system: anthropic.com/engineering/multi-agent-research-system
- Superpowers (phases, v6 review-loop lessons): github.com/obra/superpowers
- Spec Kit + critiques: github.com/github/spec-kit; Scott Logic (Eberhardt) "Radical Idea or
  Reinvented Waterfall?"; spec-kit discussion #1784 ("illusion of work")
- Kiro (EARS requirements, approval prompts): kiro.dev/docs/specs
- OpenSpec (delta/change-folder model): github.com/Fission-AI/OpenSpec
- Adversarial code review (builder vs critic, spec contracts): asdlc.io/practices/adversarial-code-review
- GitHub agent-PR review framework (scope-creep triggers, CI-gaming, evidence):
  github.blog "Agent pull requests are everywhere"
- Compound engineering (codify/learnings): every.to/guides/compound-engineering
- Loop engineering (budget/stop/report contract): explainx.ai loop-engineering guide
- Linear agent lessons (durable state, crash recovery): daily.dev "How we built a Linear coding
  agent"
