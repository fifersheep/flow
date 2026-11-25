#!/usr/bin/env python3
"""flow_herdr: flow inside the Herdr app, a terminal workspace for coding agents.

    python3 flow_herdr.py split TERMINAL SIDE DIR    flow_open.py runs this
    python3 flow_herdr.py start                      the SessionStart hook (payload on stdin)
    python3 flow_herdr.py clear                      the SessionEnd hook
    python3 flow_herdr.py install | remove | panel   /flow-herdr runs these
    python3 flow_herdr.py snapshots DIR              the Herdr panel runs this
    python3 flow_herdr.py repos DIR                  the board's start bar runs this
    python3 flow_herdr.py keys                       /flow-herdr keys: the boards' shortcuts

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
- **The board.** `board` opens a board tab, and records the folder it was
  opened from (the session's) in ~/.cache/flow/herdr-board.json, as the
  board's folder menu does. A board tab has no terminal of its own, so that
  folder is where it reads tasks from, and
  `repos DIR` lists where its start bar can start one: DIR's repo, or every
  repo directly under DIR, tasks or not. The board's header menu moves it.
  `keys` binds ⌘⇧B and ⌘⇧U in Herdr's keys.json to open the boards, so
  neither needs a Claude Code session: a board opened again closes itself
  and shows the one already there.

Outside Herdr none of this runs. Like everything the mod does, it is display:
a failed label costs a stale panel, never a session or a gate.
"""
import json
import os
import shutil
import subprocess
import sys
import time
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
REPOS = 200  # repos a board's start bar offers under a folder that isn't one
# the board's two views, each a tab of its own named so it can be found again
# (herdr/flow/model.js BOARDS)
BOARDS = {"stages": "flow · stages", "next": "flow · next up"}
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


def board_file(env=os.environ):
    """Where `board` records the folder the boards read (herdr/flow/main.js BOARD_FILE)."""
    return Path(env.get("HOME") or Path.home()) / ".cache" / "flow" / "herdr-board.json"


RECENT = 8  # folders the board's folder menu offers again (herdr/flow/model.js RECENT)


def record_folder(folder, env=os.environ):
    """Point both boards at a folder: {folder, recent}, the folder heading the
    recent ones, once (herdr/flow/model.js movedTo, which the menu writes)."""
    f = board_file(env)
    try:
        old = json.loads(f.read_text())
        old = old if isinstance(old, dict) else {}
    except Exception:
        old = {}
    recent = [r for r in [folder, *(old.get("recent") or []), old.get("folder")] if isinstance(r, str) and r]
    recent = list(dict.fromkeys(recent))[:RECENT]
    f.parent.mkdir(parents=True, exist_ok=True)
    put(f, (json.dumps({"folder": folder, "recent": recent}) + "\n").encode())


# Herdr keys that open the boards (tab.new with the mod: a board already open
# closes the copy and shows itself, herdr/flow/main.js)
KEYS_BOUND = {
    "cmd-shift-b": {"command": "tab.new", "args": {"name": BOARDS["stages"], "mod": MOD, "props": {"view": "stages"}}},
    "cmd-shift-u": {"command": "tab.new", "args": {"name": BOARDS["next"], "mod": MOD, "props": {"view": "next"}}},
}


def keys(env=os.environ):
    """Bind KEYS_BOUND in Herdr's keys.json; a key already bound to something
    else is left as it is, and said."""
    path = app_home(env) / "keys.json"
    try:
        doc = json.loads(path.read_text())
    except FileNotFoundError:
        return {"ok": False, "message": f"no Herdr keys at {tilde(path)}: open the Herdr app first"}
    except ValueError as exc:
        return {"ok": False, "message": f"couldn't read {tilde(path)}: {exc}"}
    keymap = doc.setdefault("global", {})
    added, taken = [], []
    for key, action in KEYS_BOUND.items():
        if key not in keymap:
            keymap[key] = action
            added.append(key)
        elif keymap[key] != action:
            taken.append(key)
    if added:
        put(path, (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode())
    names = {"cmd-shift-b": "⌘⇧B the stages board", "cmd-shift-u": "⌘⇧U next up"}
    parts = []
    if added:
        parts.append("bound " + ", ".join(names[k] for k in added))
    if taken:
        parts.append(", ".join(k for k in taken) + " already do something else, so left alone")
    if not added and not taken:
        parts.append("⌘⇧B and ⌘⇧U already open the boards")
    return {"ok": not taken or bool(added), "message": "; ".join(parts)}


def board(view, env=os.environ, which=shutil.which, run=subprocess.run, folder=None):
    """Show a board's tab in the shown space, making it when there isn't one.
    With a folder, the boards read that folder's repos from now on."""
    if view not in BOARDS:
        return {"ok": False, "message": f"no \"{view}\" board: stages or next"}
    if not in_herdr(env, which):
        return {"ok": False, "message": "this session isn't in a Herdr terminal"}
    if installed(env) is None:
        return {"ok": False, "message": "the flow panel isn't installed: run /flow-herdr install"}
    if folder:
        record_folder(str(Path(folder).resolve()), env)
    name = BOARDS[view]
    r = run(["herdr-app", "ls"], capture_output=True, text=True, timeout=TIMEOUT)
    try:
        spaces = json.loads(r.stdout).get("spaces", []) if r.returncode == 0 else None
    except (ValueError, AttributeError):
        spaces = None
    if spaces is None:  # can't see the tabs: making one could make a second
        why = (r.stderr or r.stdout or "").strip() or f"exit {r.returncode}"
        return {"ok": False, "message": f"couldn't list Herdr's tabs: {why}"}
    space = next((s for s in spaces if s.get("active")), {})
    tab = next((t for t in space.get("tabs", []) if t.get("name") == name), None)
    if tab:
        do("tab.select", run=run, id=tab["id"])
        return {"ok": True, "message": f"showed the {name} tab"}
    do("tab.new", run=run, name=name, mod=MOD, props=json.dumps({"view": view}))
    return {"ok": True, "message": f"opened the {name} board in a tab"}


def agent_state(terminal, run=subprocess.run):
    """(live, state) from `hc get`: whether the terminal is there, and its
    program's reported state (working, idle, done, blocked) or None."""
    r = run(["hc", "get", terminal, "--json"], capture_output=True, text=True, timeout=TIMEOUT)
    if r.returncode != 0:
        return False, None
    doc = json.loads(r.stdout or "{}")
    return doc.get("state") == "live", (doc.get("status") or {}).get("state")


def end(terminal, run=subprocess.run, sleep=time.sleep, wait=20.0):
    """End a Claude Code session as a person would: type /exit, wait for
    claude to quit, then close its pane. Never while it's working or asking
    something: /exit would interrupt a turn or land in the question."""
    live, state = agent_state(terminal, run)
    if not live:
        return {"ok": False, "message": f"no live terminal {terminal}"}
    if state in ("working", "blocked"):
        why = "working" if state == "working" else "waiting on an answer from you"
        return {"ok": False, "message": f"{terminal} is {why}: left it running"}
    if state is not None:
        # sent as a person would type it: from inside a terminal (a session
        # running this), hc wraps a message as <hc from="tN">, a note
        # between agents, and claude would read /exit as a message
        quiet = {k: v for k, v in os.environ.items() if k not in ("HC_TERMINAL_ID", "HC_TERMINAL_SOCKET")}
        r = run(["hc", "send", terminal, "/exit"], capture_output=True, text=True, timeout=60, env=quiet)
        if r.returncode != 0:
            return {"ok": False, "message": (r.stderr or r.stdout).strip() or f"couldn't type /exit into {terminal}"}
        for _ in range(int(wait / 0.5)):
            live, state = agent_state(terminal, run)
            if not live or state is None:
                break
            sleep(0.5)
        else:
            return {"ok": False, "message": f"sent /exit to {terminal}, but it hasn't quit: left it open"}
    pane = pane_of(terminal, run=run) if live else None
    if pane:
        do("pane.close", run=run, pane=pane)
    return {"ok": True, "message": f"ended the session in {terminal}"}


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
    here = Path(cwd).resolve()
    if in_a_repo(here):
        return [snapshot(here)]
    below = [d for d in roots_below(here) if (d / artifacts_dir(d)).is_dir()]
    return [snapshot(d) for d in below[:BELOW]] or [snapshot(here)]


def is_root(d):
    return (d / ".git").exists() or (d / ".flow.md").is_file()


def in_a_repo(here):
    from flow_status import root_of
    return root_of(here) != here or is_root(here)


def roots_below(here):
    """The checkouts directly under a folder, by name."""
    try:
        return sorted(d for d in here.iterdir() if d.is_dir() and not d.name.startswith(".") and is_root(d))
    except OSError:
        return []


def repos(cwd):
    """Where a board's start bar can start a task: the repo cwd is in, or, in a
    folder that holds repos, every repo directly under it, tasks or not (at
    most REPOS). Each is its main checkout (repo_of), so a worktree under the
    folder offers the repo it's of, once."""
    from flow_status import root_of
    here = Path(cwd).resolve()
    if in_a_repo(here):
        return [repo_of(root_of(here))]
    out = []
    for d in roots_below(here):
        r = str(d) if (d / ".git").is_dir() or not (d / ".git").exists() else repo_of(d)
        if r not in out:
            out.append(r)
    return out[:REPOS]


def repo_of(root):
    """The repo a checkout belongs to: its main checkout, so a worktree's tasks
    group with the repo's own. A folder that isn't in git is its own."""
    from flow_status import git
    common = (git(root, "rev-parse", "--path-format=absolute", "--git-common-dir") or "").strip()
    if not common:
        return str(root)
    common = Path(common)
    return str(common.parent if common.name == ".git" else common)


def snapshot(cwd):
    """flow_status's snapshot, with the repo it's of (repo_of) for grouping."""
    from flow_status import snapshot as read
    s = read(cwd)
    return {**s, "repo": repo_of(s["root"])}


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
    if argv[:1] == ["repos"] and len(argv) == 2:
        try:
            print(json.dumps(repos(argv[1])))
        except Exception:
            print("[]")
        return 0
    if argv[:1] == ["board"]:
        rest, folder = argv[1:], None
        if "--cwd" in rest[:-1]:
            i = rest.index("--cwd")
            folder, rest = rest[i + 1], rest[:i] + rest[i + 2:]
        if len(rest) <= 1:
            try:
                doc = board(rest[0] if rest else "stages", folder=folder)
            except Exception as exc:
                doc = {"ok": False, "message": str(exc)}
            print(json.dumps(doc))
            return 0
    if argv[:1] == ["end"] and len(argv) == 2:
        try:
            doc = end(argv[1])
        except Exception as exc:
            doc = {"ok": False, "message": str(exc)}
        print(json.dumps(doc))
        return 0
    if argv[:1] in (["install"], ["remove"], ["panel"], ["keys"]):
        try:
            doc = {"install": install, "remove": remove, "panel": panel, "keys": keys}[argv[0]]()
        except Exception as exc:
            doc = {"ok": False, "message": str(exc)}
        print(json.dumps(doc))
        return 0
    print("usage: flow_herdr.py split TERMINAL SIDE DIR | start | clear | install | remove | panel | keys | board [stages|next] [--cwd DIR] | end TERMINAL | snapshots DIR | repos DIR", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
