#!/usr/bin/env python3
"""flow_events: PostToolUse lifecycle-event runner for the flow plugin.

A task's phase transitions are already a durable event stream — they are the
thing workflow.md records and the thing flow_validate gates. This hook reads
that stream and runs the commands a repo declares under `## on` in .flow.md,
keyed by the phase being entered:

    ## on
    - implementation: osascript -e 'display notification "plan approved"'
    - complete: gh pr view --web

Deliberately NOT prompt discipline: the skills don't have to remember to fire
anything, so a forgotten step can't silently skip a side effect.

Always exits 0. Commands here are side effects, never gates — a failing or
missing editor, notifier or script must not disturb the session, so failures
are reported to the user and then dropped.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from flow_common import PHASES, artifacts_dir, find_project_root, parse_frontmatter

ON_RE = re.compile(r"^##\s+on\b[^\n]*\n(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
ENTRY_RE = re.compile(r"^\s*-\s*([a-z-]+)\s*:\s*(.+?)\s*$")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
TIMEOUT = 30


def parse_on_section(root):
    """{phase: command} from `## on` in .flow.md, plus keys that aren't phases.

    Unknown keys are returned rather than dropped: a typo'd phase name would
    otherwise be a command that simply never runs, with nothing to show why."""
    cfg = root / ".flow.md"
    if not cfg.is_file():
        return {}, []
    m = ON_RE.search(COMMENT_RE.sub("", cfg.read_text()))
    if not m:
        return {}, []
    events, unknown = {}, []
    for line in m.group(1).splitlines():
        entry = ENTRY_RE.match(line)
        if not entry:
            continue
        key, command = entry.group(1), entry.group(2)
        if "{{" in command:
            continue  # unfilled template placeholder
        if key in PHASES:
            events[key] = command
        else:
            unknown.append(key)
    return events, unknown


def state_file():
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or str(Path.home() / ".claude" / "flow")
    return Path(base) / "phase-state.json"


def load_state():
    try:
        return json.loads(state_file().read_text())
    except Exception:
        return {}


def save_state(state):
    """Prune tasks whose folder is gone, so a deleted task can't pin state
    forever and a recreated one starts clean."""
    try:
        path = state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        live = {k: v for k, v in state.items() if os.path.isdir(k)}
        path.write_text(json.dumps(live, indent=2, sort_keys=True))
    except Exception:
        pass  # a lost state file costs one duplicate event, never correctness


def run(command, root, env_extra):
    env = dict(os.environ, **{k: v for k, v in env_extra.items() if v is not None})
    try:
        r = subprocess.run(command, shell=True, cwd=str(root), env=env,
                           capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"timed out after {TIMEOUT}s"
    except Exception as exc:
        return str(exc)
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip().splitlines()
        return f"exit {r.returncode}" + (f": {detail[0]}" if detail else "")
    return None


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") not in ("Write", "Edit"):
        return
    target = Path(payload["tool_input"]["file_path"]).resolve()
    if target.name != "workflow.md" or not target.is_file():
        return
    root = find_project_root(payload).resolve()
    adir = (root / artifacts_dir(root)).resolve()
    if adir not in target.parents:
        return

    fm = parse_frontmatter(target.read_text())
    phase = fm.get("phase")
    if phase not in PHASES:
        return
    task_dir = str(target.parent)

    state = load_state()
    previous = state.get(task_dir)
    if previous == phase:
        return  # same phase, just a progress tick or an `updated` bump
    state[task_dir] = phase
    save_state(state)

    events, unknown = parse_on_section(root)
    command = events.get(phase)
    if not command:
        return

    error = run(command, root, {
        "FLOW_PHASE": phase,
        "FLOW_PREV_PHASE": previous or "",
        "FLOW_TASK": fm.get("task", ""),
        "FLOW_TITLE": fm.get("title", ""),
        "FLOW_MODE": fm.get("mode", ""),
        "FLOW_BRANCH": fm.get("branch", ""),
        "FLOW_WORKTREE": fm.get("worktree", ""),
        "FLOW_TICKET_ID": fm.get("ticket-id", ""),
        "FLOW_TASK_DIR": task_dir,
        "FLOW_REPO": str(root),
    })
    note = (f"flow: `on {phase}` failed — {error}" if error
            else f"flow: ran `on {phase}` hook")
    if unknown:
        note += (f" (ignoring .flow.md `## on` keys that aren't phases: "
                 f"{', '.join(sorted(set(unknown)))})")
    print(json.dumps({"systemMessage": note}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)  # side effects never gate a session
