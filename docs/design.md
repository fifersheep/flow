# flow design

Why flow is built the way it is. What it does is in the [README](../README.md)
and the [reference](reference.md). This file holds the reasoning, so a change
that undoes one of these choices does so on purpose.

## Principles

These come from research done before v1: Claude Code orchestration guidance,
spec-driven development frameworks, and review and reporting practice.

1. **Files on disk are the interface between phases.** State lives in the
   task folder, not in the conversation, which is what makes a task resumable.
   `workflow.md` is written before each transition, so a crash costs at most
   part of one phase, never a gate decision.
   ([Anthropic best practices](https://code.claude.com/docs/en/best-practices))
2. **Two human gates: the plan and the merge.** A gate on every phase is
   ceremony. Every other transition just announces itself.
   ([Spec Kit](https://github.com/github/spec-kit),
   [Kiro](https://kiro.dev/docs/specs))
3. **Keep the ceremony small, or it kills solo work.** One measurement had
   Spec Kit producing 2,000+ lines of markdown and 3.5 hours of review for
   about 700 lines of code. Hence lite mode, and plans that are file-level
   task lists rather than prose: if the plan is longer than the code, it's
   over-specified. (Scott Logic, "Radical Idea or Reinvented Waterfall?")
4. **One fresh reviewer, checking the diff against the plan.** The reviewer
   isn't the writer. It checks conformance first (scope creep, silent
   deviations, weakened tests), then correctness. A single read-only pass
   finds about as much as a loop of reviewers. Verification is by outcome
   (run the thing), not by green tests.
   ([superpowers](https://github.com/obra/superpowers),
   [adversarial review](https://asdlc.io/practices/adversarial-code-review))
5. **Reports quote real output.** Changed versus planned, deviations and why,
   evidence, follow-ups. The PR body is built from the task folder, and
   wind-down proposes learnings for CLAUDE.md, skills or memory.
   ([compound engineering](https://every.to/guides/compound-engineering))
6. **Fan out for breadth only.** Research and review use subagents;
   implementation stays in one context, where multiple agents do worse on
   tightly coupled code.
   ([Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system))
7. **Gates are enforced by a hook, not by prompt wording.** A long session
   forgets instructions; a PreToolUse hook doesn't. It has to be PreToolUse,
   because only that can refuse a write before the file changes.

## Guardrails in the skills' wording

The validator can't check these, so the skills say them:

- The reviewer and the plan critic flag correctness and requirement gaps
  only: no nitpicks, no findings made up to have something to say.
- Research breadth is proportional to the task, and capped.
- Each phase writes its artifact, announces it with a file reference, and
  moves on, without pasting the content back into the chat.
- No phase loops more than once without bringing it to the user.
- Evidence over assertion: reports quote real command output.
- Tracker moves and `## on` commands are side effects. They never block or
  reverse a phase.

## Known limits

- **The hooks defend against drift, not forgery.** They check state the
  model writes itself, the same trust model as CI. The realistic failure is
  a long session getting sloppy, and that's what they catch.
- **Between the gates the skills are advisory.** During implementation,
  `workflow.md` can fall behind the code; the fix is editing `phase:` by
  hand, which is one line.
- **A validator bug could block real work.** `force: true` in a task's
  frontmatter turns the validator off for that task. It's for the user only:
  no skill may tell the model to set it. The validator stays small and
  covered by its own tests.
- **The shell reading is a heuristic.** See the README's "What the gates do
  and don't cover".
- **Ceremony creeps back.** It's what killed Spec Kit for solo developers.
  Lite mode, the plan-length rule and single-pass critics are the defence; a
  change that adds a phase, a gate or a review loop should say why it's
  worth it.
