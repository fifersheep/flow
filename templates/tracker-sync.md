# Tracker sync — shared contract

How flow keeps a tracker ticket's status in step with the workflow phase.
Referenced by `flow-start`, `flow-report`, and `flow-wrap`; those skills own
*when* a move happens, this file owns *how* and *what happens when it fails*.

## Enabled or not

Sync runs only when BOTH hold:
- `.flow.md` has a `tracker:` key naming a tracker with an available MCP
  (e.g. `tracker: linear`), and
- the task's workflow.md has a non-blank `ticket-id:`.

Either missing → skip silently. A repo with no tracker, or a task with no
ticket, behaves exactly as it did before this existed. Never invent a ticket
id, and never create a ticket here — shaping owns ticket creation.

## Status map

`.flow.md` may carry a `## tracker-status` section mapping the three sync
events to that tracker's status names. Omitted → these defaults:

| event   | when                              | default status |
|---------|-----------------------------------|----------------|
| `start` | task folder created (flow-start)  | In Progress    |
| `pr-open` | PR opened (flow-report step 2, and the lite wrap's miniature gate 2) | In Review |
| `merged` | merge landed (flow-wrap step 3)  | Done           |

Match the tracker's own status **names**, not a generic type — "In Progress"
and "In Review" are usually the same underlying type, so only the name
distinguishes them. Read the team's real status list once rather than
assuming a name exists; a name that doesn't match is a failure (below), not a
reason to guess a near-neighbour.

## Recording a move

After a move succeeds, set `tracker-synced:` in workflow.md frontmatter to the
status just written. That is the record of what the tracker actually says —
`flow-wrap` compares it against the expected terminal status to catch drift.

## Failure is never fatal

**A tracker sync must never block, stall, or reverse a phase.** Auth lapses
(several trackers need re-authorising each session), a renamed status, an
ambiguous id, a tracker that's simply down — all are expected.

On any failure:
1. Do NOT retry in a loop and do NOT ask the user to authorise mid-phase.
2. Append one line to workflow.md `## Deviations`:
   `- YYYY-MM-DD tracker sync failed (<event> → <status>): <reason>; ticket left at <last known status or "unknown">`
3. Leave `tracker-synced:` at its previous value — it records what the tracker
   says, not what was attempted.
4. Tell the user in one line, and carry on with the phase.

The user can always move the ticket by hand; the Deviations line and the
wind-down drift check are what stop that from being forgotten.
