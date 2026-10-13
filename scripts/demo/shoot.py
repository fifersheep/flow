#!/usr/bin/env python3
"""Capture the README's screenshots from a live Claude Code session.

    scripts/demo/shoot.py OUT_DIR [SHOT ...]

Builds the demo repo (make-demo-repo.sh) under /tmp/flowdemo, drives Claude
Code in a detached tmux session for each shot, crops the screen to the part
that shows flow, and renders it with render.sh. Needs tmux, freeze, Chrome,
FONT (see render.sh), and flow installed in Claude Code. The first run asks
Claude Code to trust the demo folders; this answers yes.

Shots: hero gate status pane-progress pane-tasks setup blocked split gif
(default: all). `split` presses `t` with the terminal set to tmux, so flow
splits this tmux window for real; `gif` approves gate 1 for real — one model
turn — and needs ffmpeg.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# not /tmp: macOS resolves it to /private/tmp, which shows in the pane's paths
DEMO = Path("/Users/Shared/flow-demo")
REPO = DEMO / "acme-api"
WORKTREE = DEMO / "acme-api-audit-log"
SESSION = "flowshot"
COLS, ROWS = 110, 40
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def tmux(*args, check=True):
    return subprocess.run(["tmux", *args], capture_output=True, text=True, check=check).stdout


def screen(color=False):
    # -N keeps trailing spaces, so a panel's background runs to its edge
    return tmux("capture-pane", "-p", *(["-e", "-N"] if color else []), "-t", SESSION)


def wait_for(pattern, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        if re.search(pattern, screen()):
            return
        time.sleep(0.5)
    raise SystemExit(f"timed out waiting for {pattern!r}:\n{screen()}")


def keys(*k):
    tmux("send-keys", "-t", SESSION, *k)


def start(cwd, settings=None, cols=COLS, rows=ROWS):
    # tmux hides the terminal's dark background from Claude Code, which then
    # picks its light theme; say dark, as the person's terminal would
    settings = json.dumps({"theme": "dark", **(settings or {})})
    tmux("kill-session", "-t", SESSION, check=False)
    tmux("new-session", "-d", "-s", SESSION, "-x", str(cols), "-y", str(rows), "-c", str(cwd))
    # Claude Code shows a tip under the prompt when tmux lacks these
    tmux("set", "-t", SESSION, "-g", "mouse", "on")
    tmux("set", "-t", SESSION, "-g", "focus-events", "on")
    cmd = f"clear && claude --settings '{settings}'"
    keys(cmd, "Enter")
    end = time.time() + 30
    while time.time() < end:
        s = screen()
        if "trust this folder" in s:
            keys("Down", "Enter")
            time.sleep(2)
        elif "Claude Code v" in s:  # not the shell's own prompt
            break
        time.sleep(0.5)
    wait_for(r"flow\s+│")  # the band's heading: the mod has loaded and read the repo
    time.sleep(2)


def lines():
    return screen(color=True).split("\n")


def plain(line):
    return ANSI.sub("", line)


def index(ls, pattern, start=0, last=False):
    hits = [i for i in range(start, len(ls)) if re.search(pattern, plain(ls[i]))]
    if not hits:
        raise SystemExit(f"no line matches {pattern!r}:\n" + "\n".join(map(plain, ls)))
    return hits[-1] if last else hits[0]


SGR = re.compile(r"\x1b\[[0-9;]*m")


def sgr_state(state, seq):
    """Fold one SGR sequence into {fg, bg, attrs}."""
    params = (seq[2:-1] or "0").split(";")
    i = 0
    while i < len(params):
        p = params[i]
        if p in ("38", "48") and i + 2 < len(params) and params[i + 1] == "5":
            state["fg" if p == "38" else "bg"] = params[i + 2]
            i += 3
            continue
        if p in ("0", ""):
            state.update(fg=None, bg=None, attrs=set())
        elif p == "39":
            state["fg"] = None
        elif p == "49":
            state["bg"] = None
        elif p in ("1", "2", "3", "4"):
            state["attrs"].add(p)
        elif p == "22":
            state["attrs"] -= {"1", "2"}
        elif p in ("23", "24"):
            state["attrs"].discard(str(int(p) - 20))
        i += 1


def crop_cols(line, c0):
    """The part of a coloured line from visible column c0 on, its colours kept."""
    state = {"fg": None, "bg": None, "attrs": set()}
    out, col, i, started = [], 0, 0, False
    while i < len(line):
        m = SGR.match(line, i)
        if m:
            if started:
                out.append(m.group())
            else:
                sgr_state(state, m.group())
            i = m.end()
            continue
        if col == c0 and not started:
            started = True
            codes = sorted(state["attrs"]) + ([f"38;5;{state['fg']}"] if state["fg"] else []) \
                + ([f"48;5;{state['bg']}"] if state["bg"] else [])
            if codes:
                out.append(f"\x1b[{';'.join(codes)}m")
        if started:
            out.append(line[i])
        col += 1
        i += 1
    return "".join(out)


PLUGIN_ROOT = str(HERE.parent.parent)


HEADER = re.compile(r"Claude Code v\d|with \w+ effort|^\s*[▐▝▘▛▜█]{2}")


def tidy(ls, collapse=True):
    """Paths as they're configured, not as this machine expands them, and
    (with `collapse`) no run of more than one blank line."""
    out = []
    for line in ls:
        line = line.replace(PLUGIN_ROOT, "${CLAUDE_PLUGIN_ROOT}").replace(str(Path.home()), "~")
        line = re.sub(r" · Claude (Max|Pro|Team|Enterprise)\b", "", line)  # the account's plan, in the header
        if collapse and not plain(line).strip() and out and not plain(out[-1]).strip():
            continue
        out.append(line)
    return out


def save(out, name, ls):
    text = "\n".join(tidy(ls)).rstrip() + "\n"
    cap = out / f"{name}.ansi"
    cap.write_text(text)
    subprocess.run([str(HERE / "render.sh"), str(cap), str(out / f"{name}.png")], check=True,
                   stdin=subprocess.DEVNULL)
    cap.unlink()
    print(f"  {name}.png")


def band_and_prompt(ls):
    """From the band's top edge down to the rule under the composer."""
    top = index(ls, r"^\s*╭", last=True)
    prompt = index(ls, r"^❯\s", top)
    return ls[top:prompt + 2]


def shot_hero(out):
    start(REPO)
    save(out, "hero", band_and_prompt(lines()))


def shot_gate(out):
    start(WORKTREE)
    wait_for(r"gate 1 · plan approval")
    save(out, "gate", band_and_prompt(lines()))


def shot_status(out):
    start(REPO)
    keys("/flow-status")
    time.sleep(1)
    keys("Enter")
    wait_for(r"other active tasks")
    time.sleep(1)
    ls = lines()
    first = index(ls, r"^❯\s/flow-status")
    return save(out, "status", ls[first:index(ls, r"^\s*╭", first, last=True)])


def pane(out, name, tab_key=None):
    start(REPO, cols=170, rows=50)
    keys("/flow-pane")
    time.sleep(1)
    keys("Enter")
    wait_for(r"Phases")
    if tab_key:
        keys(tab_key)
        time.sleep(1.5)
    ls = lines()
    first = index(ls, r"Progress.*Plan.*Decisions")
    # the pane docks on the right: keep its columns, from its tab row down to
    # the last row before the composer's rule
    left = plain(ls[first]).index("│") + 1
    bottom = index(ls, r"^─{40,}", first) - 1
    while bottom > first and not plain(ls[bottom])[left:].strip():
        bottom -= 1
    save(out, name, [crop_cols(line, left) for line in ls[first:bottom + 1]])


def shot_pane_progress(out):
    pane(out, "pane-progress")


def shot_pane_tasks(out):
    pane(out, "pane-tasks", "5")


def shot_setup(out):
    start(REPO, {"pluginConfigs": {"flow@flow": {"options": {"splitSide": "left", "splitSize": 30}}}})
    keys("/flow-term setup")
    time.sleep(1)
    keys("Enter")
    wait_for(r"✓ ready|▲ .*\n.*▸", 120)
    time.sleep(1)
    ls = lines()
    first = index(ls, r"^❯\s/flow-term setup")
    save(out, "setup", ls[first:index(ls, r"^\s*╭", first, last=True)])


def shot_blocked(out):
    start(WORKTREE)
    keys("Use the Edit tool to add a one-line comment at the top of src/server.ts saying what it does.")
    time.sleep(1)
    keys("Enter")
    wait_for(r"flow blocked", 180)
    time.sleep(0.3)
    # the refused edit in the transcript, down to the straw band below it
    ls = lines()
    first = index(ls, r"^❯\s*Use the Edit tool")
    save(out, "blocked", ls[first:index(ls, r"^\s*╰", first, last=True) + 1])
    keys("Escape")


def shot_gif(out):
    """Gate 1, start to finish: straw band, `a` drafts the approval, Enter, and
    the band turns periwinkle as flow records the gate and moves on."""
    import shutil, tempfile
    work = Path(tempfile.mkdtemp())
    frames = []  # (plain text, coloured lines, seconds)

    def grab(hold):
        ls = lines()
        # bottom-anchored, a fixed height: down to the composer's lower rule,
        # leaving out the status line under it
        bottom = index(ls, r"^─{40,}", last=True)
        window = ls[max(0, bottom - GIF_ROWS + 1):bottom + 1]
        text = "\n".join(map(plain, window))
        if frames and frames[-1][0] == text:
            frames[-1] = (text, window, frames[-1][2] + hold)
        else:
            frames.append((text, window, hold))

    start(WORKTREE, cols=GIF_COLS, rows=GIF_ROWS + 6)
    grab(2.5)
    keys("C-x"); time.sleep(0.3); keys("Tab"); time.sleep(0.8)
    keys("a"); time.sleep(1.2)
    grab(2.5)
    keys("Enter")
    end = time.time() + 240
    while time.time() < end:
        time.sleep(1)
        grab(0.6)
        s = screen()
        if "● impl" in s and "gate 1 approved" in s:
            break
    time.sleep(1.5)
    grab(5)
    tmux("kill-session", "-t", SESSION, check=False)

    listing = []
    for i, (_, window, hold) in enumerate(frames):
        cap = work / f"f{i:03}.ansi"
        # every frame the same height: blank rows kept, a space so none is trimmed
        rows = [" " if HEADER.search(plain(line)) else line for line in tidy(window, collapse=False)]
        cap.write_text("\n".join(line if plain(line).strip() else " " for line in rows) + "\n")
        png = work / f"f{i:03}.png"
        subprocess.run([str(HERE / "render.sh"), str(cap), str(png)], check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        listing += [f"file '{png}'", f"duration {hold:.2f}"]
    listing.append(f"file '{work / f'f{len(frames) - 1:03}.png'}'")  # concat needs the last one twice
    (work / "frames.txt").write_text("\n".join(listing) + "\n")
    gif = out / "gate.gif"
    scale = "scale=1100:-2:flags=lanczos,pad=ceil(iw/2)*2:ceil(ih/2)*2"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(work / "frames.txt"),
                    "-vf", f"{scale},split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=none",
                    "-loop", "0", str(gif)], check=True)
    shutil.rmtree(work, ignore_errors=True)
    print(f"  gate.gif ({len(frames)} frames)")


GIF_COLS, GIF_ROWS = 104, 26


def shot_split(out):
    """`t` beside the session: flow's terminal setting at tmux, a split on the
    right at 40%, and a command run there, both panes captured side by side."""
    start(REPO, {"pluginConfigs": {"flow@flow": {"options": {"terminal": "tmux", "splitSide": "right", "splitSize": 40}}}},
          cols=190, rows=26)
    first = tmux("display", "-p", "-t", SESSION, "#{pane_id}").strip()
    keys("C-x"); time.sleep(0.3); keys("Tab"); time.sleep(0.8); keys("t")
    end = time.time() + 20
    while time.time() < end and len(tmux("list-panes", "-t", SESSION).splitlines()) < 2:
        time.sleep(0.5)
    panes = tmux("list-panes", "-t", SESSION, "-F", "#{pane_id}").split()
    other = next(p for p in panes if p != first)
    time.sleep(4)  # the new shell's own start-up
    tmux("send-keys", "-t", other, "clear && git status -sb && git --no-pager log --oneline -3 && git worktree list", "Enter")
    end = time.time() + 20
    while time.time() < end and "acme-api-audit-log" not in tmux("capture-pane", "-p", "-t", other):
        time.sleep(0.5)
    time.sleep(1)
    cap = lambda p: tmux("capture-pane", "-p", "-e", "-N", "-t", p).split("\n")
    left, right = cap(first), cap(other)
    bottom = index(left, r"^─{30,}", last=True)  # the composer's lower rule; the status line goes
    width = max(len(plain(l)) for l in left[:bottom + 1])
    rows = []
    for i in range(bottom + 1):
        l = left[i] if i < len(left) else ""
        if HEADER.search(plain(l)):  # blank the header's columns, keep a toast beside it
            l = " " * 58 + crop_cols(l, 58)
        pad = " " * max(0, width - len(plain(l)))
        r = right[i] if i < len(right) else ""
        rows.append(f"{l}\x1b[0m{pad}\x1b[38;5;240m│\x1b[0m {r}")
    save(out, "split", rows)

SHOTS = {
    "hero": shot_hero, "gate": shot_gate, "status": shot_status,
    "pane-progress": shot_pane_progress, "pane-tasks": shot_pane_tasks,
    "setup": shot_setup, "blocked": shot_blocked, "split": shot_split, "gif": shot_gif,
}


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    out = Path(argv[0]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("FONT", "")
    if not os.environ["FONT"]:
        raise SystemExit("set FONT to a JetBrains Mono .ttf (see render.sh)")
    subprocess.run([str(HERE / "make-demo-repo.sh"), str(DEMO)], check=True, stdout=subprocess.DEVNULL)
    try:
        for name in argv[1:] or SHOTS:
            SHOTS[name](out)
    finally:
        tmux("kill-session", "-t", SESSION, check=False)


if __name__ == "__main__":
    main(sys.argv[1:])
