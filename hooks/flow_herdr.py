#!/usr/bin/env python3
"""flow_herdr: flow inside the Herdr app, a terminal workspace for coding agents.

    python3 flow_herdr.py split TERMINAL SIDE DIR    flow_open.py runs this
    python3 flow_herdr.py start                      the SessionStart hook (payload on stdin)
    python3 flow_herdr.py clear                      the SessionEnd hook
    python3 flow_herdr.py install | remove | panel   /flow-herdr runs these
    python3 flow_herdr.py snapshots DIR              the Herdr panel runs this

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

  A completed task keeps only `flow.task` and `flow.phase=complete`, so a
  panel can say so; the session's end takes them all off. The session's
  start labels the task the session is on, so a resumed task shows before
  its first write. Both put on one more, which the start puts on task or not:

      flow.version   the flow that labels this session

  so a panel can tell a session with no task from one whose flow predates
  the labels (Claude Code reads hooks when a session starts: one started
  before the plugin was updated runs the old ones until it restarts).
- **The panel.** herdr/flow/ is a Herdr mod: a panel of flow tasks beside
  the session, and Herdr notifications when a gate opens, a phase moves or a
  task completes. `install` copies it to ~/.config/herdr-app/mods/flow/ (or
  $HERDR_APP_HOME's) with flow.json, which names this plugin's folder so the
  panel can run flow_status.py. Mods are trusted code, so only the person
  installs it; each session's start then refreshes an installed copy when
  the plugin is newer. `panel` opens it beside the session's own pane.
  `snapshots DIR` is what the panel reads: flow_status.py's snapshot of the
  repo DIR is in, or, when DIR is in none (a folder holding several repos),
  of each repo directly under it that has flow tasks.

Outside Herdr none of this runs. Like everything the mod does, it is display:
a failed label costs a stale panel, never a session or a gate.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
MOD_SRC = PLUGIN / "herdr" / "flow"
MOD = "flow"
# Herdr writes jsconfig.json and its .d.ts into a mod's folder: never copy those
MOD_FILES = lambda: sorted(f for f in MOD_SRC.iterdir() if f.is_file() and f.suffix in (".js", ".json", ".svg")
                           and f.name not in ("jsconfig.json", "flow.json"))
KEYS = ("flow.task", "flow.phase", "flow.mode", "flow.progress", "flow.gate", "flow.dir")
VERSION = "flow.version"  # on from the session's start to its end, task or not
BELOW = 12  # repos read under a folder that isn't one
TIMEOUT = 5


def terminal_id(env=os.environ):
    return env.get("HC_TERMINAL_ID") or None


def in_herdr(env=os.environ, which=shutil.which):
    """The session runs in a Herdr terminal and the app's CLI can be reached."""
    return bool(terminal_id(env)) and which("herdr-app") is not None


def labels_for(task):
    """{key: value} for `hc label`, "" taking a key off (see the module doc)."""
    if task.get("phase") == "complete":
        return {**{k: "" for k in KEYS}, "flow.task": task.get("slug") or "", "flow.phase": "complete"}
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
    return set_labels(terminal, {**labels_for(task), VERSION: plugin_version()}, run=run)


def clear(env=os.environ, which=shutil.which, run=subprocess.run):
    terminal = terminal_id(env)
    if not terminal or which("hc") is None:
        return None
    return set_labels(terminal, {k: "" for k in (*KEYS, VERSION)}, run=run)


def app_home(env=os.environ):
    return Path(env.get("HERDR_APP_HOME") or Path.home() / ".config" / "herdr-app")


def plugin_version():
    try:
        return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]
    except Exception:
        return "0"


def version_key(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def installed(env=os.environ):
    """flow.json of the installed panel, or None: no panel, or a mod that isn't flow's."""
    try:
        doc = json.loads((app_home(env) / "mods" / MOD / "flow.json").read_text())
        return doc if isinstance(doc, dict) else None
    except Exception:
        return None


def tilde(path):
    home = str(Path.home())
    p = str(path)
    return "~" + p[len(home):] if p == home or p.startswith(home + os.sep) else p


def put(path, data):
    """Write a file whole: a hidden temporary beside it (Herdr ignores those), then a rename."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def install(env=os.environ, which=shutil.which, run=subprocess.run, check=True):
    """Copy the panel into Herdr's mods. {ok, message}."""
    home = app_home(env)
    if not home.is_dir():
        return {"ok": False, "message": f"Herdr's folder isn't at {tilde(home)}: install and open the Herdr app first"}
    dest = home / "mods" / MOD
    if dest.exists() and installed(env) is None:
        return {"ok": False, "message": f"{tilde(dest)} holds a mod that isn't flow's, so it was left alone"}
    dest.mkdir(parents=True, exist_ok=True)
    # Herdr reloads on every save: main.js last, so it never runs ahead of its
    # modules, and each whole, by rename: rewritten in place, a file can be read
    # half-written, and Herdr keeps the old build without saying so
    for f in sorted(MOD_FILES(), key=lambda f: f.name == "main.js"):
        put(dest / f.name, f.read_bytes())
    put(dest / "flow.json", (json.dumps({"root": str(PLUGIN), "version": plugin_version()}, indent=2) + "\n").encode())
    if check and which("herdr-app"):
        r = run(["herdr-app", "check", str(dest)], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return {"ok": False, "message": f"installed, but Herdr's check failed: {(r.stderr or r.stdout).strip()}"}
    return {"ok": True, "message": f"installed the flow panel in {tilde(dest)}. Open it beside this session with /flow-herdr"}


def remove(env=os.environ):
    dest = app_home(env) / "mods" / MOD
    if installed(env) is None:
        return {"ok": False, "message": f"no flow panel installed in {tilde(dest)}"}
    shutil.rmtree(dest)
    return {"ok": True, "message": f"removed the flow panel from {tilde(dest)}. Close any flow panes left open"}


def sync(env=os.environ):
    """Refresh an installed panel from this plugin when this one is newer, or
    the folder it names is gone. Never installs one nobody asked for."""
    doc = installed(env)
    if doc is None:
        return None
    if doc.get("root") == str(PLUGIN) and doc.get("version") == plugin_version():
        return None
    if Path(str(doc.get("root"))).is_dir() and version_key(doc.get("version")) > version_key(plugin_version()):
        return None  # a newer flow put it there: leave it
    return install(env, check=False)


def pane_of(terminal, run=subprocess.run):
    """The pane showing a terminal, from `herdr-app ls`."""
    r = run(["herdr-app", "ls"], capture_output=True, text=True, timeout=TIMEOUT)
    for space in json.loads(r.stdout or "{}").get("spaces", []):
        for tab in space.get("tabs", []):
            for t in tab.get("terminals", []):
                if t.get("terminal") == terminal and t.get("pane"):
                    return t["pane"]
    return None


def panel(env=os.environ, which=shutil.which, run=subprocess.run):
    """Open the panel beside the session's own pane, never wherever focus is."""
    if not in_herdr(env, which):
        return {"ok": False, "message": "this session isn't in a Herdr terminal"}
    if installed(env) is None:
        return {"ok": False, "message": "the flow panel isn't installed: run /flow-herdr install"}
    pane = pane_of(terminal_id(env), run=run)
    if not pane:
        return {"ok": False, "message": f"Herdr shows no pane for terminal {terminal_id(env)}"}
    do("pane.split", run=run, pane=pane, direction="right", mod=MOD)
    return {"ok": True, "message": "opened the flow panel beside this session"}


def session_start(payload, env=os.environ, which=shutil.which, run=subprocess.run):
    """Refresh an installed panel; label the session with the task it's on."""
    sync(env)
    terminal = terminal_id(env)
    if not terminal or which("hc") is None:
        return None
    from flow_status import snapshot  # only in Herdr: it runs git
    snap = snapshot(payload.get("cwd") or os.getcwd())
    task = next((t for t in snap["tasks"] if t["folder"] == snap.get("current")), None)
    labels = labels_for(task) if task else {k: "" for k in KEYS}
    return set_labels(terminal, {**labels, VERSION: plugin_version()}, run=run)


def snapshots(cwd):
    """The snapshots the panel shows for a folder: its repo's, or, in a folder
    that holds repos rather than sitting in one, those of the repos under it
    that have flow tasks (at most BELOW of them)."""
    from flow_common import artifacts_dir
    from flow_status import root_of, snapshot
    here = Path(cwd).resolve()
    is_root = lambda d: (d / ".git").exists() or (d / ".flow.md").is_file()
    if root_of(here) != here or is_root(here):
        return [snapshot(here)]
    try:
        below = sorted(d for d in here.iterdir() if d.is_dir() and not d.name.startswith(".")
                       and is_root(d) and (d / artifacts_dir(d)).is_dir())
    except OSError:
        below = []
    return [snapshot(d) for d in below[:BELOW]] or [snapshot(here)]


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
    if argv[:1] in (["clear"], ["start"]):
        try:
            if argv[0] == "clear":
                clear()
            else:
                session_start(json.load(sys.stdin))
        except Exception:
            pass
        return 0  # display only: nothing here may disturb a session
    if argv[:1] == ["snapshots"] and len(argv) == 2:
        try:
            print(json.dumps(snapshots(argv[1])))
        except Exception:
            print("[]")
        return 0
    if argv[:1] in (["install"], ["remove"], ["panel"]):
        try:
            doc = {"install": install, "remove": remove, "panel": panel}[argv[0]]()
        except Exception as exc:
            doc = {"ok": False, "message": str(exc)}
        print(json.dumps(doc))
        return 0
    print("usage: flow_herdr.py split TERMINAL SIDE DIR | start | clear | install | remove | panel | snapshots DIR", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
