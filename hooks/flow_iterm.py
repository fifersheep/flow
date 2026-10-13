#!/usr/bin/env python3
"""flow_iterm: split the iTerm pane Claude Code runs in, on any side, at a size.

    <venv python> flow_iterm.py SESSION_ID right|left|top|bottom PERCENT DIR
    <venv python> flow_iterm.py --check SESSION_ID

`--check` connects and finds the session's pane, splitting nothing: the last
step of /flow-term setup.

flow_open.py runs this, in a venv of its own holding the `iterm2` package,
only when the split asked for is one AppleScript can't make: left or top, or a
size other than half. AppleScript splits right or below at half the pane and
nothing else; iTerm's Python API (Settings → General → Magic → Enable Python
API) can put the pane before the session and size it.

PERCENT is the new pane's share of the pane being split. Exits 0 printing
nothing on success; non-zero with the reason on stderr, so flow_open.py can
fall back to an AppleScript split.
"""
import os
import shlex
import subprocess
import sys

import iterm2


def cookie():
    """Ask iTerm for a cookie, so connecting needs no "allow?" prompt."""
    r = subprocess.run(["osascript", "-e", 'tell application "iTerm2" to request cookie and key for app named "flow"'],
                       capture_output=True, text=True, timeout=10)
    parts = r.stdout.split()
    return parts if r.returncode == 0 and len(parts) == 2 else None


async def split(conn, sid, side, percent, path):
    app = await iterm2.async_get_app(conn)
    me = app.get_session_by_id(sid)
    if me is None:
        raise LookupError("this session's iTerm pane wasn't found")
    vertical = side in ("left", "right")
    # sizes before the split: right after it, grid sizes are stale
    before = me.grid_size.width if vertical else me.grid_size.height
    new = await me.async_split_pane(vertical=vertical, before=side in ("left", "top"))
    room = max(2, before - 1)  # one cell goes to the divider
    share = min(room - 1, max(1, room * percent // 100))
    if vertical:
        new.preferred_size = iterm2.util.Size(share, me.grid_size.height)
        me.preferred_size = iterm2.util.Size(room - share, me.grid_size.height)
    else:
        new.preferred_size = iterm2.util.Size(me.grid_size.width, share)
        me.preferred_size = iterm2.util.Size(me.grid_size.width, room - share)
    await me.tab.async_update_layout()
    await new.async_send_text(f"cd {shlex.quote(path)} && clear\n")


async def check(conn, sid):
    app = await iterm2.async_get_app(conn)
    if app.get_session_by_id(sid) is None:
        raise LookupError("connected, but this session's iTerm pane wasn't found")


def main(argv):
    c = cookie()
    if c:
        os.environ["ITERM2_COOKIE"], os.environ["ITERM2_KEY"] = c
    if argv[0] == "--check":
        iterm2.run_until_complete(lambda conn: check(conn, argv[1]), retry=False)
        return
    sid, side, percent, path = argv[0], argv[1], int(argv[2]), argv[3]
    iterm2.run_until_complete(lambda conn: split(conn, sid, side, percent, path), retry=False)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__, file=sys.stderr)
        sys.exit(1)
