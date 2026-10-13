"""Helpers shared by the flow hooks.

Both hooks answer the same two questions about a Write/Edit payload — which
checkout is this, and is the target a task's workflow.md — so they answer them
with one implementation. A disagreement between them would silently mean the
validator gating one task folder while the event runner watches another.
"""
import os
import re
from pathlib import Path

DEFAULT_ARTIFACTS_DIR = "docs/tasks"
PHASES = ["setup", "research", "planning", "plan-review", "implementation",
          "code-review", "reporting", "wind-down", "complete"]
CHAINS = {
    "full": PHASES,
    "lite": ["setup", "planning", "plan-review", "implementation",
             "code-review", "wind-down", "complete"],
}
# phase being entered -> gate line that must exist in the decision log
GATES = {"implementation": "gate 1:", "wind-down": "gate 2:"}


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


def checkout_root(path):
    """The nearest of path and its ancestors that looks like a checkout root
    (contains .git — a dir, or a file in worktrees — or .flow.md); None
    outside any. path itself counts: a shell command can write a whole tree."""
    path = Path(path).resolve()
    for d in (path, *path.parents):
        if (d / ".git").exists() or (d / ".flow.md").is_file():
            return d
    return None


def find_project_root(payload):
    """The checkout_root of the target file. Falls back to CLAUDE_PROJECT_DIR
    / cwd, so worktree checkouts get their own root instead of the session's
    launch directory."""
    try:
        root = checkout_root(payload["tool_input"]["file_path"])
        if root is not None:
            return root
    except Exception:
        pass
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return Path(root)


def artifacts_dir(root):
    cfg = root / ".flow.md"
    if cfg.is_file():
        m = re.search(r"^artifacts-dir:\s*(\S+)", cfg.read_text(), re.MULTILINE)
        if m:
            return m.group(1)
    return DEFAULT_ARTIFACTS_DIR
