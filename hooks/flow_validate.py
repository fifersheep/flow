#!/usr/bin/env python3
"""flow_validate: PreToolUse gate for the flow plugin.

Exit 0 = allow. Exit 2 = block (reason on stderr). Any internal error → allow
(exit 0): a buggy validator must never wedge unrelated work.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PHASES = ["setup", "research", "planning", "plan-review", "implementation",
          "code-review", "reporting", "wind-down", "complete"]
CHAINS = {
    "full": PHASES,
    "lite": ["setup", "planning", "plan-review", "implementation",
             "code-review", "wind-down", "complete"],
}
# phase being entered -> gate line that must exist in the decision log
GATES = {"implementation": "gate 1:", "wind-down": "gate 2:"}
LOCKED_PHASES = {"setup", "research", "planning", "plan-review", "reporting"}
DEFAULT_ARTIFACTS_DIR = "docs/tasks"


def parse_frontmatter(text):
    m = re.match(r"\A---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def simulate(tool_name, tool_input, current_text):
    if tool_name == "Write":
        return tool_input.get("content", "")
    old, new = tool_input.get("old_string", ""), tool_input.get("new_string", "")
    if tool_input.get("replace_all"):
        return current_text.replace(old, new)
    return current_text.replace(old, new, 1)


def find_project_root(payload):
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return Path(root)


def artifacts_dir(root):
    cfg = root / ".flow.md"
    if cfg.is_file():
        m = re.search(r"^artifacts-dir:\s*(\S+)", cfg.read_text(), re.MULTILINE)
        if m:
            return m.group(1)
    return DEFAULT_ARTIFACTS_DIR


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") not in ("Write", "Edit"):
        return 0
    target = Path(payload["tool_input"]["file_path"]).resolve()
    root = find_project_root(payload).resolve()
    adir = (root / artifacts_dir(root)).resolve()
    if target.name == "workflow.md" and adir in target.parents:
        return check_state_machine(payload, target)
    return check_lockdown(target, root, adir)


def block(msg):
    print(f"flow: {msg}", file=sys.stderr)
    return 2


def effective_index(cur_phase, cur_mode, chain):
    """Index of cur_phase in the target chain; on a mode switch where
    cur_phase is absent, the index of its nearest predecessor (walking
    backward in the old chain) that the target chain shares."""
    if cur_phase in chain:
        return chain.index(cur_phase)
    old_chain = CHAINS.get(cur_mode, [])
    if cur_phase not in old_chain:
        return None  # unknown current phase; skip-guard cannot apply
    for p in reversed(old_chain[:old_chain.index(cur_phase)]):
        if p in chain:
            return chain.index(p)
    return None


def check_state_machine(payload, target):
    current_text = target.read_text() if target.is_file() else ""
    proposed_text = simulate(payload["tool_name"], payload["tool_input"],
                             current_text)
    cur, new = parse_frontmatter(current_text), parse_frontmatter(proposed_text)
    if cur.get("force") == "true" or new.get("force") == "true":
        return 0
    mode = new.get("mode", cur.get("mode", "full"))
    chain = CHAINS.get(mode)
    if chain is None:
        return block(f"unknown mode '{mode}' (expected full|lite)")
    new_phase = new.get("phase")
    if new_phase not in chain:
        return block(f"illegal phase '{new_phase}' for mode {mode}; "
                     f"legal: {', '.join(chain)}")
    if not current_text:
        if new_phase != "setup":
            return block("a new workflow.md must start at phase: setup")
        return 0
    cur_phase = cur.get("phase")
    cur_idx = effective_index(cur_phase, cur.get("mode", "full"), chain)
    if cur_idx is not None and chain.index(new_phase) > cur_idx + 1:
        return block(f"cannot skip from '{cur_phase}' to '{new_phase}' "
                     f"(next is '{chain[cur_idx + 1]}')")
    gate = GATES.get(new_phase)
    if gate and new_phase != cur_phase and gate not in proposed_text:
        n = "1 (plan approval)" if gate == "gate 1:" else "2 (merge approval)"
        return block(f"entering '{new_phase}' requires a decision-log entry "
                     f"containing '{gate}' — gate {n} has not been recorded")
    return 0


def current_branch(root):
    # `branch --show-current` (not `rev-parse --abbrev-ref HEAD`): it works on
    # an unborn branch (fresh repo, no commits), where rev-parse exits 128.
    try:
        r = subprocess.run(["git", "-C", str(root), "branch", "--show-current"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:
        return None


def check_lockdown(target, root, adir):
    if not adir.is_dir():
        return 0
    branch = current_branch(root)
    if branch is None:
        return 0
    for wf_file in adir.glob("*/workflow.md"):
        fm = parse_frontmatter(wf_file.read_text())
        if (fm.get("branch") != branch or fm.get("force") == "true"
                or fm.get("phase") not in LOCKED_PHASES):
            continue
        task_dir = wf_file.parent.resolve()
        if task_dir in target.parents or target == (root / ".flow.md").resolve():
            continue
        gate = "2 (pre-merge)" if fm.get("phase") == "reporting" else "1 (plan approval)"
        return block(f"task '{fm.get('task', task_dir.name)}' is in phase "
                     f"'{fm.get('phase')}' — code edits are locked until gate "
                     f"{gate} is recorded in {wf_file}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # never wedge on validator bugs
