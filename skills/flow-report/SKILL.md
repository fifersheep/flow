---
name: flow-report
description: Flow phase 7 (reporting, full mode). Normally invoked via /flow. Writes report.md with real evidence, opens the PR, then holds at gate 2 for merge approval.
---

# Flow — report (gate 2)

1. **Write `report.md`** from the plugin's `templates/report.md`:
   - Changed vs plan — from plan.md tasks + Progress.
   - Deviations — copy workflow.md `## Deviations`, expand each with why.
   - Evidence — paste the ACTUAL verify output and outcome-verification
     results captured in review. Re-run rather than claim from memory.
   - Follow-ups — advisory review findings + anything deferred.
2. **Open the PR** (`gh pr create` if a remote exists; otherwise present the
   description and note the merge will be local). Description generated from
   the artifact trail: intent (plan.md), approach summary, deviations, test
   evidence, links to the task folder artifacts.
3. **Gate 2.** Present to the user: report.md path, PR link, one-paragraph
   summary. Ask approve-merge / request-changes (AskUserQuestion). Changes →
   make them, update report evidence, ask again.
4. **On approval** (never before): append
   `- YYYY-MM-DD gate 2: merge approved by user`, set `phase: wind-down`,
   update `updated` + `Next action`, announce, invoke the `flow-wrap` skill.

The validator blocks `wind-down` without the gate-2 line, and blocks code
edits during `reporting`. Fix the process, never the guardrail.
