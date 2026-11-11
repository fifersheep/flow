#!/usr/bin/env python3
"""flow_herdr: flow inside the Herdr app, a terminal workspace for coding agents.

    python3 flow_herdr.py split TERMINAL SIDE DIR    flow_open.py runs this
    python3 flow_herdr.py clear                      the SessionEnd hook

Herdr runs every terminal in herdr-core (`hc`) and tells the program inside
which one it is in HC_TERMINAL_ID. Two things use that:

- **The split.** `t` and /flow-term open a terminal in a task's worktree
  beside the session's own pane: focus that pane, then `terminal.open` beside
  it, through `herdr-app do`. Herdr splits right or down at half; left and top
  swap the new pane across. There is no size: Herdr's split has none.
- **Labels.** Every write to a workflow.md puts the task's state on the
  session's terminal with `hc label` (flow_events.py calls `label_task`), and
  the session's end takes them off. Herdr's mods read a terminal's labels live
  (`terminals()[i].labels`), so a Herdr panel can show which agent is on which
  task and phase, with no polling and nothing flow has to keep running. The
  labels, all strings, are the contract such a panel reads:

      flow.task      the task's slug
      flow.phase     its phase (the chain is in flow_common.CHAINS)
      flow.mode      full or lite
      flow.progress  done/total of the Progress checklist; absent when empty
      flow.gate      the gate's number while it waits on the person; else absent
      flow.dir       the task's folder (workflow.md, plan.md, report.md)

  A completed task takes them all off: there is no flow state left to show.

Outside Herdr none of this runs. Like everything the mod does, it is display:
a failed label costs a stale panel, never a session or a gate.
"""
import json
import os
import shutil
import subprocess
import sys

KEYS = ("flow.task", "flow.phase", "flow.mode", "flow.progress", "flow.gate", "flow.dir")
TIMEOUT = 5


def terminal_id(env=os.environ):
    return env.get("HC_TERMINAL_ID") or None


def in_herdr(env=os.environ, which=shutil.which):
    """The session runs in a Herdr terminal and the app's CLI can be reached."""
    return bool(terminal_id(env)) and which("herdr-app") is not None


def labels_for(task):
    """{key: value} for `hc label`, "" taking a key off (see the module doc)."""
    if task.get("phase") == "complete":
        return {k: "" for k in KEYS}
    progress = task.get("progress") or {}
    waiting = [g["n"] for g in task.get("gates") or [] if g.get("state") == "waiting"]
    return {
        "flow.task": task.get("slug") or "",
        "flow.phase": task.get("phase") or "",
        "flow.mode": task.get("mode") or "",
        "flow.progress": f"{progress['done']}/{progress['total']}" if progress.get("total") else "",
        "flow.gate": str(waiting[0]) if waiting else "",
        "flow.dir": task.get("dir") or "",
    }


def set_labels(terminal, labels, run=subprocess.run):
    """None, or why `hc label` didn't take them."""
    argv = ["hc", "label", terminal, *(f"{k}={v}" for k, v in labels.items())]
    try:
        r = run(argv, capture_output=True, text=True, timeout=TIMEOUT)
    except Exception as exc:
        return str(exc)
    return None if r.returncode == 0 else (r.stderr or r.stdout or f"exit {r.returncode}").strip()


def label_task(task, env=os.environ, which=shutil.which, run=subprocess.run):
    """Put a task's state on the session's terminal, when there is one."""
    terminal = terminal_id(env)
    if not terminal or which("hc") is None:
        return None
    return set_labels(terminal, labels_for(task), run=run)


def clear(env=os.environ, which=shutil.which, run=subprocess.run):
    return label_task({"phase": "complete"}, env=env, which=which, run=run)


def do(command, run=subprocess.run, **args):
    """`herdr-app do`: what the command made, or raise with Herdr's reason."""
    argv = ["herdr-app", "do", command]
    for k, v in args.items():
        argv += [f"--{k}", v]
    r = run(argv, capture_output=True, text=True, timeout=TIMEOUT)
    try:
        doc = json.loads(r.stdout or "{}")
    except ValueError:
        doc = {}
    if r.returncode != 0 or (isinstance(doc, dict) and doc.get("error")):
        why = doc.get("error") if isinstance(doc, dict) else None
        raise RuntimeError(why or (r.stderr or r.stdout).strip() or f"herdr-app exit {r.returncode}")
    return doc if isinstance(doc, dict) else {}


def split(terminal, side, path, run=subprocess.run):
    """A terminal in `path` beside the pane showing `terminal`, on `side`."""
    do("pane.focus", run=run, terminal=terminal)
    made = do("terminal.open", run=run, folder=path, place="right" if side in ("left", "right") else "down")
    if side in ("left", "top") and made.get("pane"):
        do("pane.swap", run=run, pane=made["pane"], direction="left" if side == "left" else "up")
    return made


def main(argv):
    if argv[:1] == ["split"] and len(argv) == 4:
        try:
            split(argv[1], argv[2], argv[3])
        except Exception as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0
    if argv[:1] == ["clear"]:
        try:
            clear()
        except Exception:
            pass
        return 0  # the session is ending: nothing to tell it
    print("usage: flow_herdr.py split TERMINAL SIDE DIR | clear", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
