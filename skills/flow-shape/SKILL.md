---
name: flow-shape
description: Ticket shaping — collaborative brainstorm that turns a raw feature idea into agreed, code-grounded tracker tickets. Use for "shape this", "let's plan a ticket for X", "brainstorm this into tickets". Not a flow phase (no branch, no workflow.md); hands off to /flow start. Not for quick bug filing — file those directly.
---

# Flow — shape

Turns an idea into tickets the user has agreed to. Conversational — checkpoints
and rules, not a script. One hard gate: **no tracker writes until the user
agrees to the shape.**

Argument: a feature idea, optionally with constraints ("expand prestige to 25 levels").

## 1. Ground

Before offering any opinion:
- Read the code the idea touches. Collect file:line facts; hunt quirks —
  dead/unreachable content, hardcoded caps, serialized enums and formats,
  asset gaps.
- Recon the tracker: near-duplicates, related tickets, and **intent buried in
  old ticket text** (a "we'll do X later" note is a design input, not trivia).
- Report findings compactly, with file:line refs, before the first question.

## 2. Decide

- Extract the 3–6 genuinely open decisions. Anything with a conventional
  answer: recommend it in passing and move on — don't put it to a vote.
- AskUserQuestion, ≤4 questions per round; recommended option listed first
  and marked "(Recommended)"; multiSelect when choices aren't exclusive.
- "Other" answers are first-class design moves — re-derive everything they
  touch (schedules, counts, dependencies) before continuing.
- Rounds cascade (an answer can open a new decision); 2–3 rounds is typical.
  If decisions keep multiplying, the appetite is wrong — shrink the shape or
  split it.

## 3. Shape

- Scope: one ticket, parent + subs, or siblings. Parent + subs when domains
  differ or one PR would bloat. Write the parent's acceptance criteria to
  cover ONLY its own scope, so it can close on its own PR.
- Order the work; name dependencies between tickets.
- Rabbit holes: name known risks inside the ticket (fragile save formats,
  exhaustive switches, migration paths) so the implementer walks in warned.
- No-gos: defer explicitly — each deferred item points at the sibling or
  follow-up ticket that owns it, or says "not doing this" outright.

## 4. Gate — agreement

Summarize the shape: scope split, key numbers, what's deliberately left
tunable or open. Tracker writes happen only after clear agreement — a final
decision round that covered the whole shape counts; silence does not.

## 5. Write

- One ticket per work unit, from `templates/ticket.md`. Parent first — subs
  need its ID.
- Every implementation note cites file:line. Every guessed number is marked
  tunable, with an owner named (usually a tuning ticket or phase).
- Acceptance criteria are testable; include compat checks ("old saves load
  cleanly") whenever a serialized format is touched.
- Use the tracker's generated branch names so PRs auto-link.

## 6. Aftercare

- Update project memory: ticket ids + one-line design rationale (decisions,
  not transcript).
- Offer blocking relations matching the dependency order.
- Offer the handoff: `/flow start <first implementable ticket>`.

Rules:
- Never write a ticket referencing code you haven't read this session.
- No tracker writes before the agreement gate. Edits after (the user refines
  a decision) are normal — tickets are living documents; keep memory in sync.
- Every option list carries a marked recommendation.
- Tickets record decisions and their date ("agreed YYYY-MM-DD"), never the
  discussion itself.
- Tracker specifics (team, project, labels) come from recon of existing
  tickets or the user — never assumed.
- Not a flow phase: no branch, no worktree, no workflow.md. One shaping
  session may yield many tickets; each becomes its own /flow task later.
