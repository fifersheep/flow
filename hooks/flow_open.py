#!/usr/bin/env python3
"""flow_open: open a task's worktree in a terminal or an editor, on request.

    python3 flow_open.py terminal|editor DIR [--app APP] [--side SIDE] [--size PCT] [--dry-run]
    python3 flow_open.py setup [--app APP] [--side SIDE] [--size PCT]

The flow mod's `t` / `e` buttons and /flow-term, /flow-code run this; nothing
runs it on its own. Which app is the person's choice (the plugin's `terminal`
and `editor` settings); how each one is driven lives here, beside the other
scripts, rather than in the mod, so it can be tested without a session.

A split (`iterm-split`, `tmux`) goes on `--side` right, left, top or bottom of
the pane Claude Code runs in, taking `--size` percent of it. AppleScript can
split iTerm only right or below at half, so any other split runs
flow_iterm.py on iTerm's Python API, in a venv this script makes the first time
(`~/.cache/flow/iterm2-venv`, the `iterm2` package from PyPI). If that can't
be had, the split falls back to AppleScript's nearest and says so, pointing
at `setup`: /flow-term setup, a checklist of what that split needs, each
missing piece with its fix, which installs the helper package when that is
the one thing missing (the person asked for setup, so that is theirs to ask).

Always exits 0 with one JSON object on stdout, `{"ok", "message", "argv"}`:
a terminal that fails to open must cost a toast, never a session.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
ITERM_HELPER = HOOKS / "flow_iterm.py"
ITERM_PACKAGE = "iterm2==2.30"
SIDES = ("right", "left", "top", "bottom")
DEFAULT_SIDE, DEFAULT_SIZE = "right", 50

TERMINALS = ("iterm-split", "iterm-tab", "iterm-window", "terminal", "warp", "tmux")
EDITORS = ("vscode", "cursor", "zed")

# iTerm takes the directory as an argument, so nothing of the path is spliced
# into the script; `quoted form of` quotes it for the shell it is typed into.
# An iTerm that wasn't running opens a window of its own on launch: that one
# is used, rather than leaving it empty beside a new tab.
ITERM = """on run argv
  set d to item 1 of argv
  set wasRunning to application "iTerm" is running
  tell application "iTerm"
    activate
    if not wasRunning then
      repeat 50 times
        if (count of windows) > 0 then exit repeat
        delay 0.1
      end repeat
    end if
    if (count of windows) = 0 or ("{mode}" is "window" and wasRunning) then
      set w to (create window with default profile)
    else if wasRunning then
      set w to current window
      tell w to create tab with default profile
    else
      set w to current window
    end if
    tell current session of w to write text "cd " & quoted form of d & " && clear"
  end tell
end run"""

# The pane split is the session's own: iTerm names it in ITERM_SESSION_ID
# (`w0t2p0:<unique id>`), so the split lands beside Claude Code even when
# another tab has the focus.
ITERM_SPLIT = """on run argv
  set d to item 1 of argv
  set sid to item 2 of argv
  tell application "iTerm"
    repeat with w in windows
      repeat with t in tabs of w
        repeat with s in sessions of t
          if unique id of s is sid then
            tell s to set n to (split {how} with default profile)
            tell n to write text "cd " & quoted form of d & " && clear"
            return
          end if
        end repeat
      end repeat
    end repeat
  end tell
  error "this session's iTerm pane wasn't found"
end run"""

# editor -> (CLI on PATH, macOS app name, what the person reads)
EDITOR_APPS = {
    "vscode": ("code", "Visual Studio Code", "VS Code"),
    "cursor": ("cursor", "Cursor", "Cursor"),
    "zed": ("zed", "Zed", "Zed"),
}
TERMINAL_NAMES = {
    "iterm-split": "an iTerm split",
    "iterm-tab": "an iTerm tab",
    "iterm-window": "an iTerm window",
    "terminal": "a Terminal window",
    "warp": "Warp",
    "tmux": "a tmux split",
}


def venv_python(env=os.environ):
    root = Path(env.get("FLOW_ITERM_VENV") or Path.home() / ".cache" / "flow" / "iterm2-venv")
    return root / "bin" / "python"


def split_args(side, size):
    """The side and size asked, made sane: an unknown side is right, sizes 10–90."""
    side = side if side in SIDES else DEFAULT_SIDE
    try:
        size = min(90, max(10, int(size)))
    except (TypeError, ValueError):
        size = DEFAULT_SIZE
    return side, size


def command_for(kind, app, path, side=DEFAULT_SIDE, size=DEFAULT_SIZE,
                platform=sys.platform, env=os.environ, which=shutil.which):
    """(argv, what) to open `path`, or (None, why not)."""
    mac = platform == "darwin"
    side, size = split_args(side, size)
    if kind == "terminal":
        app = app or "iterm-split"
        if app not in TERMINALS:
            return None, f"unknown terminal '{app}' — one of {', '.join(TERMINALS)}"
        what = TERMINAL_NAMES[app]
        if app == "tmux":
            if not env.get("TMUX"):
                return None, "the terminal setting is tmux, but this session isn't inside tmux"
            pane = ["-t", env["TMUX_PANE"]] if env.get("TMUX_PANE") else []
            how = ["-h" if side in ("left", "right") else "-v", *(["-b"] if side in ("left", "top") else [])]
            return ["tmux", "split-window", *how, "-l", f"{size}%", *pane, "-c", path], what
        if not mac:
            return None, f"{what} needs macOS — set the terminal to tmux"
        if app == "iterm-split":
            sid = env.get("ITERM_SESSION_ID", "").partition(":")[2]
            if sid:
                if size == DEFAULT_SIZE and side in ("right", "bottom"):
                    how = "vertically" if side == "right" else "horizontally"
                    return ["osascript", "-e", ITERM_SPLIT.replace("{how}", how), path, sid], what
                return [str(venv_python(env)), str(ITERM_HELPER), sid, side, str(size), path], what
            app, what = "iterm-tab", "an iTerm tab (this session isn't in iTerm, so there's no pane to split)"
        if app.startswith("iterm"):
            mode = app.split("-")[1]
            return ["osascript", "-e", ITERM.replace("{mode}", mode), path], what
        return ["open", "-a", "Terminal" if app == "terminal" else "Warp", path], what
    if kind == "editor":
        app = app or "vscode"
        if app not in EDITORS:
            return None, f"unknown editor '{app}' — one of {', '.join(EDITORS)}"
        cli, mac_app, name = EDITOR_APPS[app]
        if which(cli):
            return [cli, path], name
        if mac:
            return ["open", "-a", mac_app, path], name
        return None, f"`{cli}` isn't on PATH"
    return None, f"unknown kind '{kind}' — terminal or editor"


def api_enabled():
    """iTerm's Settings → General → Magic → Enable Python API, as iTerm keeps it."""
    r = subprocess.run(["defaults", "read", "com.googlecode.iterm2", "EnableAPIServer"],
                       capture_output=True, text=True, timeout=5)
    return r.returncode == 0 and r.stdout.strip() == "1"


def has_package(python):
    return python.is_file() and run([str(python), "-c", "import iterm2"]) is None


def needs_api(side, size):
    return not (size == DEFAULT_SIZE and side in ("right", "bottom"))


def ensure_venv(python):
    """Make the venv flow_iterm.py runs in, the first time. None, or why not."""
    if python.is_file():
        return None
    root = python.parent.parent
    steps = [[sys.executable, "-m", "venv", str(root)],
             [str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", ITERM_PACKAGE]]
    try:
        root.parent.mkdir(parents=True, exist_ok=True)
        for step in steps:
            why = run(step, timeout=240)
            if why is not None:
                shutil.rmtree(root, ignore_errors=True)
                return f"setting up iTerm's Python API failed: {why}"
    except Exception as exc:
        shutil.rmtree(root, ignore_errors=True)
        return str(exc)
    return None


def run(argv, timeout=20):
    """None, or the last line of why it failed."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        return str(exc)
    if r.returncode == 0:
        return None
    lines = (r.stderr or r.stdout).strip().splitlines()
    return lines[-1] if lines else f"exit {r.returncode}"


def open_path(kind, app, path, side=DEFAULT_SIDE, size=DEFAULT_SIZE, dry_run=False):
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        return {"ok": False, "message": f"no folder at {path}", "argv": None}
    argv, what = command_for(kind, app, str(p), side, size)
    if argv is None:
        return {"ok": False, "message": what, "argv": None}
    side, size = split_args(side, size)
    is_split = kind == "terminal" and (app or "iterm-split") in ("iterm-split", "tmux") and "tab" not in what
    where = f" ({side}, {size}%)" if is_split else ""
    is_api = argv[1:2] == [str(ITERM_HELPER)]
    if dry_run:
        # `setup`: this press will install the helper first, so the mod can say so
        return {"ok": True, "message": f"would open {what}{where} in {p}", "argv": argv,
                "setup": is_api and not Path(argv[0]).is_file()}
    if is_api:
        # an API that's off can't be reached: go straight to the fallback
        why = "off" if not api_enabled() else ensure_venv(Path(argv[0])) or run(argv)
    else:
        why = run(argv)
    if why is None:
        return {"ok": True, "message": f"opened {what}{where} in {p}", "argv": argv}
    if is_api:
        # AppleScript's nearest: the same axis, at half
        near = "right" if side in ("left", "right") else "bottom"
        argv, _ = command_for(kind, app, str(p), near, DEFAULT_SIZE)
        if run(argv) is None:
            return {"ok": True, "argv": argv, "needsSetup": True, "message": (
                f"split {near} at 50% — {side} at {size}% needs setup: run /flow-term setup")}
    return {"ok": False, "message": f"couldn't open {what}: {why}", "argv": argv}


FIX = "      ▸ "


def tilde(path):
    """A path under the home folder as ~/…, the way the person would type it."""
    home = str(Path.home())
    p = str(path)
    return "~" + p[len(home):] if p == home or p.startswith(home + os.sep) else p


def setup(app, side, size, platform=sys.platform, env=os.environ):
    """/flow-term setup: what the terminal setting's split needs, and each fix.

    Lines lead with flow's glyphs, which the mod colours: ✓ in place, ▲
    missing, ▸ what to do about it, ○ not checked (it waits on a line above).
    """
    side, size = split_args(side, size)
    app = app or "iterm-split"
    lines = [f"▌ terminal setup — {app}" + (f", {side} at {size}%" if app in ("iterm-split", "tmux") else "")]
    if app == "tmux":
        if env.get("TMUX"):
            lines += ["  ✓ Claude Code runs inside tmux", f"  ✓ ready — t and /flow-term split {side} at {size}%"]
            return {"ok": True, "lines": lines}
        lines += ["  ▲ Claude Code isn't running inside tmux", FIX + "start it in a tmux session, or pick another terminal in /config"]
        return {"ok": False, "lines": lines}
    if app != "iterm-split":
        lines += [f"  ✓ {TERMINAL_NAMES[app]} needs no setup" + (" beyond macOS" if platform != "darwin" else "")]
        if platform != "darwin":
            lines += ["  ▲ it needs macOS", FIX + "on this machine, set the terminal to tmux in /config"]
            return {"ok": False, "lines": lines}
        lines += ["  ○ macOS may ask once whether Claude Code can control it — allow it"]
        return {"ok": True, "lines": lines}

    if platform != "darwin":
        lines += ["  ▲ an iTerm split needs macOS", FIX + "on this machine, set the terminal to tmux in /config"]
        return {"ok": False, "lines": lines}
    sid = env.get("ITERM_SESSION_ID", "").partition(":")[2]
    if not sid:
        lines += ["  ▲ Claude Code isn't running in iTerm, so there's no pane to split",
                  FIX + "start Claude Code in iTerm — until then, t opens an iTerm tab"]
        return {"ok": False, "lines": lines}
    lines += ["  ✓ Claude Code runs in iTerm"]
    if not needs_api(side, size):
        lines += [f"  ✓ {side} at 50% is AppleScript's own split — nothing more to set up",
                  "  ○ macOS may ask once whether Claude Code can control iTerm — allow it",
                  "  ○ any other side or size needs iTerm's Python API; run this again after changing it"]
        return {"ok": True, "lines": lines}

    later = ["  ○ helper package — waits on the API", "  ○ connection — waits on the API"]
    fallback = f"  ▸ until then, t splits {'right' if side in ('left', 'right') else 'bottom'} at 50%"
    if not api_enabled():
        lines += [f"  ▲ iTerm's Python API is off — {side} at {size}% needs it",
                  FIX + "iTerm → Settings → General → Magic → tick \"Enable Python API\"",
                  FIX + "then run /flow-term setup again", *later, fallback]
        return {"ok": False, "lines": lines}
    lines += ["  ✓ iTerm's Python API is on"]

    python = venv_python(env)
    if has_package(python):
        lines += [f"  ✓ helper package in {tilde(python.parent.parent)}"]
    else:
        why = ensure_venv(python)
        if why:
            lines += [f"  ▲ couldn't install the helper package: {why}",
                      FIX + "check the network (it comes from PyPI), then run /flow-term setup again",
                      "  ○ connection — waits on the package", fallback]
            return {"ok": False, "lines": lines}
        lines += [f"  ✓ helper package installed in {tilde(python.parent.parent)}"]

    why = run([str(python), str(ITERM_HELPER), "--check", sid])
    if why:
        lines += [f"  ▲ couldn't reach iTerm's API: {why}",
                  FIX + "if iTerm or macOS asked whether to allow flow or Claude Code, allow it",
                  FIX + "otherwise quit and reopen iTerm, then run /flow-term setup again", fallback]
        return {"ok": False, "lines": lines}
    lines += ["  ✓ connected to this session's pane", f"  ✓ ready — t and /flow-term split {side} at {size}%"]
    return {"ok": True, "lines": lines}


def main(argv):
    args = [a for a in argv if a != "--dry-run"]
    opts = {}
    for flag in ("--app", "--side", "--size"):
        if flag in args:
            i = args.index(flag)
            opts[flag[2:]] = args[i + 1] if i + 1 < len(args) else None
            del args[i:i + 2]
    if args[:1] == ["setup"]:
        try:
            doc = setup(opts.get("app"), opts.get("side") or DEFAULT_SIDE, opts.get("size") or DEFAULT_SIZE)
        except Exception as exc:
            doc = {"ok": False, "lines": [f"⛔ setup couldn't run: {exc}"]}
    elif len(args) != 2:
        doc = {"ok": False, "argv": None,
               "message": "usage: flow_open.py terminal|editor DIR [--app APP] [--side SIDE] [--size PCT]"}
    else:
        try:
            doc = open_path(args[0], opts.get("app"), args[1], opts.get("side") or DEFAULT_SIDE,
                            opts.get("size") or DEFAULT_SIZE, dry_run="--dry-run" in argv)
        except Exception as exc:
            doc = {"ok": False, "message": str(exc), "argv": None}
    print(json.dumps(doc))


if __name__ == "__main__":
    main(sys.argv[1:])
    sys.exit(0)
