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


def check_state_machine(payload, target):  # completed in Task 4
    return 0


def check_lockdown(target, root, adir):  # completed in Task 5
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # never wedge on validator bugs
