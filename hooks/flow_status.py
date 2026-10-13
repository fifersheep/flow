#!/usr/bin/env python3
"""flow_status: one JSON snapshot of every flow task, for the flow mod to draw.

    python3 flow_status.py [--cwd DIR]

The mod (hooks/mod/) draws the phase rail, the pane, /flow-status, the toasts
and the status line from this one document. It never parses workflow.md
itself: the parsing lives here, beside the validator's, on flow_common, so the
picture can't drift from what the gates enforce.

Read-only, and always exits 0 with a JSON object on stdout: a broken snapshot
must cost a missing drawing, never a session. The output holds no timestamps
of its own, so the mod can compare two runs as strings to see a change.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from flow_common import CHAINS, GATES, artifacts_dir, parse_frontmatter

SCHEMA = 1
PLAN_CAP = 40000  # characters of plan.md carried; the pane draws this much
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
BOX_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.*?)\s*$")
ENTRY_RE = re.compile(r"^\s*-\s+(.*?)\s*$")
GATE_LINE_RE = r"^\s*-\s+(\d{4}-\d{2}-\d{2})\s+.*"


def git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=5)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def root_of(cwd):
    """The checkout cwd sits in: nearest ancestor holding .git (a dir, or a
    file in a worktree) or .flow.md — the same test find_project_root uses."""
    here = Path(cwd).resolve()
    for p in (here, *here.parents):
        if (p / ".git").exists() or (p / ".flow.md").is_file():
            return p
    return here


def worktrees(root):
    """(path, branch) for every worktree of root's repo, root first."""
    out = git(root, "worktree", "list", "--porcelain")
    found, path = [], None
    for line in (out or "").splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):]).resolve()
            found.append([path, None])
        elif line.startswith("branch ") and found:
            found[-1][1] = line[len("branch "):].removeprefix("refs/heads/")
    found = [(p, b) for p, b in found if p.is_dir()]
    if not any(p == root for p, _ in found):
        found.insert(0, (root, (git(root, "branch", "--show-current") or "").strip() or None))
    found.sort(key=lambda pb: pb[0] != root)
    return found


def section(text, name):
    m = re.search(rf"^##\s+{re.escape(name)}\b[^\n]*\n(.*?)(?=^##\s|\Z)",
                  text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else ""


def entries(body):
    return [m.group(1) for m in map(ENTRY_RE.match, body.splitlines())
            if m and m.group(1) and "{{" not in m.group(1)]


def gates(chain, phase, log_text):
    out = []
    for n, (before, line) in enumerate(GATES.items(), start=1):
        if before not in chain:
            continue
        hit = re.search(GATE_LINE_RE + re.escape(line), log_text, re.MULTILINE)
        i = chain.index(before)
        if hit:
            state = "passed"
        elif phase in chain and chain.index(phase) == i - 1:
            state = "waiting"  # the next step is the user's, not Claude's
        else:
            state = "ahead"
        out.append({"n": n, "before": before, "state": state,
                    "date": hit.group(1) if hit else None})
    return out


def read_task(wf, worktree, branch_here):
    raw = wf.read_text()
    fm = parse_frontmatter(raw)
    text = COMMENT_RE.sub("", raw)
    mode = fm.get("mode", "full")
    chain = CHAINS.get(mode, CHAINS["full"])
    phase = fm.get("phase", "")
    idx = chain.index(phase) if phase in chain else -1

    items = [{"text": m.group(2), "done": m.group(1) != " "}
             for m in map(BOX_RE.match, section(text, "Progress").splitlines()) if m]
    log = section(text, "Decision log")
    plan = wf.parent / "plan.md"
    report = wf.parent / "report.md"
    plan_text = None
    if plan.is_file():
        plan_text = plan.read_text()
        if len(plan_text) > PLAN_CAP:
            plan_text = plan_text[:PLAN_CAP] + "\n\n… plan.md continues; open the file for the rest."

    return {
        "slug": fm.get("task") or wf.parent.name,
        "folder": wf.parent.name,
        "title": fm.get("title", ""),
        "ticket": fm.get("ticket", ""),
        "ticketId": fm.get("ticket-id", ""),
        "mode": mode,
        "phase": phase,
        "phaseIndex": idx,
        "chain": chain,
        "branch": fm.get("branch", ""),
        "worktree": str(worktree),
        "created": fm.get("created", ""),
        "updated": fm.get("updated", ""),
        "isActive": phase != "complete",
        "isHere": bool(branch_here) and fm.get("branch") == branch_here,
        "dir": str(wf.parent),
        "workflowPath": str(wf),
        "planPath": str(plan) if plan.is_file() else None,
        "reportPath": str(report) if report.is_file() else None,
        "nextAction": " ".join(section(text, "Next action").split()),
        "progress": {"done": sum(i["done"] for i in items), "total": len(items),
                     "items": items},
        "gates": gates(chain, phase, log),
        "decisions": entries(log),
        "deviations": entries(section(text, "Deviations")),
        "plan": plan_text,
    }


def snapshot(cwd):
    root = root_of(cwd)
    branch = (git(root, "branch", "--show-current") or "").strip() or None
    tasks = {}
    for wt, wt_branch in worktrees(root):
        adir = wt / artifacts_dir(wt)
        if not adir.is_dir():
            continue
        for wf in sorted(adir.glob("*/workflow.md")):
            try:
                task = read_task(wf, wt, branch if wt == root else None)
            except Exception:
                continue
            # one task can sit in several checkouts (main holds a copy of a
            # merged one); keep the copy on the task's own branch, else root's
            key = task["folder"]
            held = tasks.get(key)
            owns = task["branch"] == (branch if wt == root else wt_branch)
            if held is None or (owns and not held["_owns"]):
                tasks[key] = {**task, "_owns": owns}
    for t in tasks.values():
        t.pop("_owns")
    # active first; within each group most recently updated first
    newest = lambda t: (t["updated"], t["folder"])
    out = (sorted([t for t in tasks.values() if t["isActive"]], key=newest, reverse=True)
           + sorted([t for t in tasks.values() if not t["isActive"]], key=newest, reverse=True))
    here = [t for t in out if t["isHere"] and t["isActive"]]
    return {
        "schema": SCHEMA,
        "root": str(root),
        "branch": branch,
        "current": here[0]["folder"] if here else None,
        "tasks": out,
    }


def main(argv):
    cwd = "."
    if "--cwd" in argv:
        i = argv.index("--cwd")
        if i + 1 < len(argv):
            cwd = argv[i + 1]
    try:
        doc = snapshot(cwd)
    except Exception as exc:
        doc = {"schema": SCHEMA, "error": str(exc), "tasks": [], "current": None}
    print(json.dumps(doc, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
    sys.exit(0)
