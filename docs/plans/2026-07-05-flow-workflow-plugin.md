# Flow Workflow Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `flow` Claude Code plugin — 8 phase skills, 3 read-only agents, artifact templates, and a PreToolUse validator hook that mechanically enforces the phase state machine and both approval gates.

**Architecture:** A plugin repo at `/Users/scoot/dev/flow` installed via a local marketplace. Per-task state lives in the *target* repo (`docs/tasks/<date>-<slug>/workflow.md` + artifacts); skills read/write that state; one Python script (`hooks/flow_validate.py`), registered PreToolUse on Write|Edit, blocks illegal phase transitions, unapproved gate crossings, and pre-approval code edits. Spec: `docs/specs/2026-07-04-flow-workflow-design.md` (read it before starting).

**Tech Stack:** Markdown (skills/agents/templates), Python 3 stdlib (validator + unittest tests), Claude Code plugin conventions (plugin.json, marketplace.json, hooks.json).

## Global Constraints

- Work on branch `v1` in `/Users/scoot/dev/flow`; merge to `main` at the end. Never commit to `main` directly mid-plan.
- Validator: Python 3 **stdlib only**. Tests: `unittest` via `python3 -m unittest`, black-box through subprocess (stdin JSON → exit code).
- Phase enum (exact strings): `setup`, `research`, `planning`, `plan-review`, `implementation`, `code-review`, `reporting`, `wind-down`, `complete`.
- Phase chains (exact order):
  - `full`: setup → research → planning → plan-review → implementation → code-review → reporting → wind-down → complete
  - `lite`: setup → planning → plan-review → implementation → code-review → wind-down → complete
- Legal transition: same phase, one step forward in the mode's chain, or backward to any earlier phase in the chain. Mode may change only if the proposed phase exists in the new mode's chain.
- Gate log lines (exact, greppable): `gate 1:` required to enter `implementation`; `gate 2:` required to enter `wind-down` (from `reporting` in full, from `code-review` in lite).
- `workflow.md` frontmatter keys (exact): `task`, `title`, `ticket`, `mode`, `phase`, `branch`, `worktree`, `created`, `updated`. Optional: `force`.
- Escape hatch: `force: true` in `workflow.md` frontmatter (proposed or existing) → validator allows everything for that task. User-only; no skill may set or suggest it.
- Default artifacts dir: `docs/tasks`. Overridable via `artifacts-dir:` line in `.flow.md` at the target-repo root.
- Skill frontmatter: `name` + `description` only. Phase-skill descriptions must state they are normally invoked via `/flow` so they don't auto-trigger.
- Agents are read-only: `tools: Read, Grep, Glob, Bash`, no Write/Edit. Agents return findings; the main session writes artifacts.
- Skills reference artifacts by path; never re-paste file contents into announcements.
- Commit at the end of every task with the message given in that task.

---

### Task 1: Plugin scaffold

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `.gitignore`

**Interfaces:**
- Produces: plugin name `flow` (used by every later skill/agent path); marketplace id `flow` (used by Task 16 install: `/plugin install flow@flow`).

- [ ] **Step 1: Create branch**

```bash
cd /Users/scoot/dev/flow && git switch -c v1
```

- [ ] **Step 2: Write `.claude-plugin/plugin.json`**

```json
{
  "name": "flow",
  "description": "Phased development workflow: setup → research → plan → gated plan review → implement → review-against-plan → gated report → wind-down. Durable file-based state, resumable from any session.",
  "version": "0.1.0",
  "author": { "name": "Scott Laing" },
  "keywords": ["workflow", "planning", "review", "gates", "state-machine"]
}
```

- [ ] **Step 3: Write `.claude-plugin/marketplace.json`**

```json
{
  "name": "flow",
  "id": "flow",
  "owner": { "name": "Scott Laing" },
  "metadata": { "description": "Personal flow workflow plugin", "version": "0.1.0" },
  "plugins": [
    {
      "name": "flow",
      "source": "./",
      "description": "Phased development workflow with gated plan review and pre-merge, file-based resumable state, and hook-enforced gates.",
      "version": "0.1.0"
    }
  ]
}
```

- [ ] **Step 4: Write `.gitignore`**

```
__pycache__/
*.pyc
```

- [ ] **Step 5: Verify JSON parses**

Run: `python3 -m json.tool .claude-plugin/plugin.json && python3 -m json.tool .claude-plugin/marketplace.json`
Expected: both files echoed back, exit 0.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: plugin scaffold (plugin.json, marketplace.json)"
```

---

### Task 2: Artifact templates

**Files:**
- Create: `templates/workflow.md`
- Create: `templates/plan.md`
- Create: `templates/report.md`
- Create: `templates/flow-config-example.md`

**Interfaces:**
- Produces: the `workflow.md` frontmatter shape consumed by the validator (Tasks 3–5) and every skill (Tasks 8–15); `{{placeholder}}` tokens filled by `flow-start`.

- [ ] **Step 1: Write `templates/workflow.md`**

```markdown
---
task: {{slug}}
title: {{one-line title}}
ticket: {{ticket-or-blank}}
mode: {{full-or-lite}}
phase: setup
branch: {{branch}}
worktree: {{worktree-path-or-blank}}
created: {{YYYY-MM-DD}}
updated: {{YYYY-MM-DD}}
---

## Next action
Run environment checks, then advance to the first working phase.

## Decision log
<!-- gate entries look like: "- 2026-07-05 gate 1: plan approved by user" -->

## Progress
<!-- one checkbox per plan task once plan.md exists -->

## Deviations
<!-- record at the moment they happen, never reconstructed later -->
```

- [ ] **Step 2: Write `templates/plan.md`**

```markdown
# Plan — {{title}}

## Intent
{{1–3 sentences: what and why}}

## Acceptance criteria
<!-- falsifiable; each one checkable by command, test, or observation -->
- [ ] {{criterion}}

## Approach
{{chosen approach; alternatives considered, one line each}}

## Tasks
<!-- file-level; each task lists files touched + its verification step.
     Guardrail: if this section grows longer than the expected diff, stop and cut. -->
1. {{task}} — files: {{paths}} — verify: {{command or check}}

## Out of scope
- {{explicitly not doing}}

## Verification
- Machine: {{project verify commands}}
- Outcome: {{how to drive the app/feature end-to-end}}
```

- [ ] **Step 3: Write `templates/report.md`**

```markdown
# Report — {{title}}

## Changed vs plan
{{summary; link plan.md}}

## Deviations
<!-- every deviation + why; copy from workflow.md and expand -->

## Evidence
<!-- real command output / screenshots, pasted, not claimed -->

## Follow-ups
- {{candidate follow-up work, if any}}
```

- [ ] **Step 4: Write `templates/flow-config-example.md`**

```markdown
# Flow config (.flow.md) — copy to a repo root and edit

verify: {{e.g. flutter analyze && flutter test}}
verify-app: {{optional outcome-check command}}
artifacts-dir: docs/tasks
worktrees: {{e.g. .worktrees/<branch>}}

## domain-agents
<!-- zone → implementer agent; omit section to implement inline -->
- {{lib/ui/ → bee-ui}}
```

- [ ] **Step 5: Commit**

```bash
git add templates && git commit -m "feat: artifact templates (workflow, plan, report, config)"
```

---

### Task 3: Validator skeleton — stdin parsing, frontmatter parsing, fast no-op (TDD)

**Files:**
- Create: `hooks/flow_validate.py`
- Test: `tests/test_flow_validate.py`

**Interfaces:**
- Produces: executable `hooks/flow_validate.py`; reads PreToolUse JSON on stdin; exit 0 = allow, exit 2 = block (reason on stderr). Helpers `parse_frontmatter(text) -> dict`, `simulate(tool_name, tool_input, current_text) -> str`, `find_project_root(payload) -> Path`, `artifacts_dir(root) -> str`. Consumed by Tasks 4–5.

- [ ] **Step 1: Write failing tests**

Create `tests/test_flow_validate.py`:

```python
import json, os, subprocess, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "hooks" / "flow_validate.py"

def run_hook(payload, project_dir):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project_dir))
    return subprocess.run(
        ["python3", str(SCRIPT)], input=json.dumps(payload),
        capture_output=True, text=True, env=env)

def payload(tool, file_path, content=None, old=None, new=None, replace_all=False):
    ti = {"file_path": str(file_path)}
    if content is not None: ti["content"] = content
    if old is not None: ti.update(old_string=old, new_string=new, replace_all=replace_all)
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": ti}

class Repo:
    """Temp git repo fixture."""
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-b", "main", str(self.dir)],
                       capture_output=True, check=True)
    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

class TestNoOpPaths(unittest.TestCase):
    def setUp(self): self.repo = Repo()

    def test_non_edit_tool_allowed(self):
        r = run_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_input": {"command": "ls"}}, self.repo.dir)
        self.assertEqual(r.returncode, 0)

    def test_write_with_no_tasks_dir_allowed(self):
        r = run_hook(payload("Write", self.repo.dir / "src/a.py", content="x"),
                     self.repo.dir)
        self.assertEqual(r.returncode, 0)

    def test_malformed_stdin_allowed(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo.dir))
        r = subprocess.run(["python3", str(SCRIPT)], input="not json",
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/scoot/dev/flow && python3 -m unittest tests.test_flow_validate -v`
Expected: FAIL/ERROR (script does not exist yet).

- [ ] **Step 3: Write the skeleton**

Create `hooks/flow_validate.py`:

```python
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
```

- [ ] **Step 4: Make it executable and run tests**

Run: `chmod +x hooks/flow_validate.py && python3 -m unittest tests.test_flow_validate -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks tests && git commit -m "feat: flow_validate skeleton — stdin parsing, no-op fast paths"
```

---

### Task 4: Validator state machine — transitions, gates, force (TDD)

**Files:**
- Modify: `hooks/flow_validate.py` (replace the `check_state_machine` stub)
- Test: `tests/test_flow_validate.py` (append)

**Interfaces:**
- Consumes: `parse_frontmatter`, `simulate`, `CHAINS`, `GATES` from Task 3.
- Produces: full state-machine enforcement used by every skill that touches `workflow.md`.

- [ ] **Step 1: Append failing tests**

Append to `tests/test_flow_validate.py`:

```python
WF = """---
task: demo
title: Demo
ticket:
mode: {mode}
phase: {phase}
branch: main
worktree:
created: 2026-07-05
updated: 2026-07-05
---

## Decision log
{log}
"""

def wf(phase, mode="full", log=""):
    return WF.format(phase=phase, mode=mode, log=log)

class TestStateMachine(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.wf_path = self.repo.dir / "docs/tasks/2026-07-05-demo/workflow.md"

    def attempt(self, new_text):
        return run_hook(payload("Write", self.wf_path, content=new_text),
                        self.repo.dir)

    def test_new_file_must_start_at_setup(self):
        self.assertEqual(self.attempt(wf("setup")).returncode, 0)
        r = self.attempt(wf("implementation"))
        self.assertEqual(r.returncode, 2)

    def test_one_step_forward_allowed(self):
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", wf("setup"))
        self.assertEqual(self.attempt(wf("research")).returncode, 0)

    def test_skip_blocked_in_full_allowed_in_lite(self):
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", wf("setup"))
        self.assertEqual(self.attempt(wf("planning")).returncode, 2)
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md",
                        wf("setup", mode="lite"))
        self.assertEqual(self.attempt(wf("planning", mode="lite")).returncode, 0)

    def test_backward_allowed(self):
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md",
                        wf("implementation", log="- 2026-07-05 gate 1: plan approved"))
        self.assertEqual(self.attempt(wf("planning")).returncode, 0)

    def test_gate1_required_for_implementation(self):
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", wf("plan-review"))
        self.assertEqual(self.attempt(wf("implementation")).returncode, 2)
        ok = wf("implementation", log="- 2026-07-05 gate 1: plan approved by user")
        self.assertEqual(self.attempt(ok).returncode, 0)

    def test_gate2_required_for_wind_down(self):
        base_log = "- 2026-07-05 gate 1: plan approved"
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md",
                        wf("reporting", log=base_log))
        self.assertEqual(self.attempt(wf("wind-down", log=base_log)).returncode, 2)
        ok = wf("wind-down", log=base_log + "\n- 2026-07-05 gate 2: merge approved")
        self.assertEqual(self.attempt(ok).returncode, 0)

    def test_invalid_phase_blocked(self):
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", wf("setup"))
        self.assertEqual(self.attempt(wf("shipping")).returncode, 2)

    def test_force_true_allows_anything(self):
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", wf("setup"))
        forced = wf("reporting").replace("branch: main", "branch: main\nforce: true")
        self.assertEqual(self.attempt(forced).returncode, 0)

    def test_edit_tool_simulated(self):
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", wf("setup"))
        r = run_hook(payload("Edit", self.wf_path,
                             old="phase: setup", new="phase: research"),
                     self.repo.dir)
        self.assertEqual(r.returncode, 0)
        r = run_hook(payload("Edit", self.wf_path,
                             old="phase: setup", new="phase: code-review"),
                     self.repo.dir)
        self.assertEqual(r.returncode, 2)
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 -m unittest tests.test_flow_validate -v`
Expected: `test_new_file_must_start_at_setup`, `test_skip_blocked_in_full_allowed_in_lite`, `test_gate1_required_for_implementation`, `test_gate2_required_for_wind_down`, `test_invalid_phase_blocked`, `test_edit_tool_simulated` FAIL (stub allows everything). Backward/forward/force tests may pass vacuously — fine.

- [ ] **Step 3: Implement `check_state_machine`**

Replace the stub in `hooks/flow_validate.py`:

```python
def block(msg):
    print(f"flow: {msg}", file=sys.stderr)
    return 2


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
    if cur_phase in chain and chain.index(new_phase) > chain.index(cur_phase) + 1:
        return block(f"cannot skip from '{cur_phase}' to '{new_phase}' "
                     f"(next is '{chain[chain.index(cur_phase) + 1]}')")
    gate = GATES.get(new_phase)
    if gate and new_phase != cur_phase and gate not in proposed_text:
        n = "1 (plan approval)" if gate == "gate 1:" else "2 (merge approval)"
        return block(f"entering '{new_phase}' requires a decision-log entry "
                     f"containing '{gate}' — gate {n} has not been recorded")
    return 0
```

- [ ] **Step 4: Run all tests**

Run: `python3 -m unittest tests.test_flow_validate -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks tests && git commit -m "feat: flow_validate state machine — transitions, gates, force override"
```

---

### Task 5: Validator edit lockdown — pre-gate and reporting phases (TDD)

**Files:**
- Modify: `hooks/flow_validate.py` (replace the `check_lockdown` stub)
- Test: `tests/test_flow_validate.py` (append)

**Interfaces:**
- Consumes: `parse_frontmatter`, `artifacts_dir`, `LOCKED_PHASES` from Tasks 3–4.
- Produces: deterministic gate integrity — no code edits while the active task (same git branch, phase in LOCKED_PHASES) awaits a gate.

- [ ] **Step 1: Append failing tests**

Append to `tests/test_flow_validate.py`:

```python
class TestLockdown(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def activate(self, phase, branch="main", mode="full"):
        text = wf(phase, mode=mode).replace("branch: main", f"branch: {branch}")
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", text)

    def edit_code(self):
        return run_hook(payload("Write", self.repo.dir / "src/a.py", content="x"),
                        self.repo.dir)

    def test_planning_phase_blocks_code_edits(self):
        self.activate("planning")
        self.assertEqual(self.edit_code().returncode, 2)

    def test_reporting_phase_blocks_code_edits(self):
        self.activate("reporting")
        self.assertEqual(self.edit_code().returncode, 2)

    def test_implementation_phase_allows_code_edits(self):
        self.activate("implementation")
        self.assertEqual(self.edit_code().returncode, 0)

    def test_task_folder_and_flow_md_exempt(self):
        self.activate("planning")
        inside = self.repo.dir / "docs/tasks/2026-07-05-demo/research.md"
        r = run_hook(payload("Write", inside, content="notes"), self.repo.dir)
        self.assertEqual(r.returncode, 0)
        r = run_hook(payload("Write", self.repo.dir / ".flow.md", content="cfg"),
                     self.repo.dir)
        self.assertEqual(r.returncode, 0)

    def test_other_branch_task_ignored(self):
        self.activate("planning", branch="feature/other")
        self.assertEqual(self.edit_code().returncode, 0)

    def test_complete_and_forced_tasks_ignored(self):
        self.activate("complete")
        self.assertEqual(self.edit_code().returncode, 0)
        text = wf("planning").replace("branch: main",
                                      "branch: main\nforce: true")
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", text)
        self.assertEqual(self.edit_code().returncode, 0)

    def test_artifacts_dir_override(self):
        self.repo.write(".flow.md", "artifacts-dir: docs/work\n")
        text = wf("planning")
        self.repo.write("docs/work/2026-07-05-demo/workflow.md", text)
        self.assertEqual(self.edit_code().returncode, 2)
```

- [ ] **Step 2: Run tests to verify the blocking ones fail**

Run: `python3 -m unittest tests.test_flow_validate -v`
Expected: `test_planning_phase_blocks_code_edits`, `test_reporting_phase_blocks_code_edits`, `test_artifacts_dir_override` FAIL (stub allows everything); the allow-path tests pass vacuously.

- [ ] **Step 3: Implement `check_lockdown`**

Replace the stub in `hooks/flow_validate.py`:

```python
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
```

- [ ] **Step 4: Run all tests**

Run: `python3 -m unittest tests.test_flow_validate -v`
Expected: all PASS (≈20 tests).

- [ ] **Step 5: Commit**

```bash
git add hooks tests && git commit -m "feat: flow_validate edit lockdown — pre-gate phases block code edits"
```

---

### Task 6: Hook registration

**Files:**
- Create: `hooks/hooks.json`

**Interfaces:**
- Consumes: `hooks/flow_validate.py` (Tasks 3–5).
- Produces: live PreToolUse registration once the plugin is installed (Task 16).

- [ ] **Step 1: Write `hooks/hooks.json`**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/flow_validate.py\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Verify JSON + end-to-end stdin simulation**

Run:
```bash
python3 -m json.tool hooks/hooks.json && \
echo '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"}}' \
  | python3 hooks/flow_validate.py; echo "exit=$?"
```
Expected: JSON echoed; `exit=0`.

- [ ] **Step 3: Commit**

```bash
git add hooks/hooks.json && git commit -m "feat: register flow_validate as PreToolUse hook on Write|Edit"
```

---

### Task 7: The three read-only agents

**Files:**
- Create: `agents/flow-researcher.md`
- Create: `agents/flow-plan-critic.md`
- Create: `agents/flow-reviewer.md`

**Interfaces:**
- Produces: agent names `flow-researcher`, `flow-plan-critic`, `flow-reviewer` dispatched by skills in Tasks 10, 11, 13. Each returns structured text findings; none writes files.

- [ ] **Step 1: Write `agents/flow-researcher.md`**

```markdown
---
name: flow-researcher
description: Read-only breadth scout for the flow workflow. Dispatched by /flow research with a scoped question about a codebase or an external topic. Returns structured findings with file:line references. Never edits.
tools: Read, Grep, Glob, Bash, WebSearch, WebFetch
---

You are a research scout. You receive ONE scoped question plus the paths or topic to
investigate. Answer only that question.

Rules:
- Read-only. Bash is for inspection (`git log`, `grep`, `ls`) — never modify anything.
- Every codebase claim carries a `file:line` reference.
- Prefer primary sources: the code itself, then repo docs, then the web.
- Note constraints and prior art you encounter (existing helpers, conventions,
  past specs/plans touching the same area) even if not asked — one line each.

Return format (your final message IS the deliverable):
## Findings
- <claim> — <file:line or URL>
## Constraints & prior art
- <one line each>
## Open questions
- <anything you could not resolve>

Be dense. Summaries only — never paste file contents wholesale.
```

- [ ] **Step 2: Write `agents/flow-plan-critic.md`**

```markdown
---
name: flow-plan-critic
description: Read-only adversarial plan reviewer for the flow workflow. Dispatched once by /flow plan-review with a plan.md path. Attacks the plan against a fixed rubric; grounded findings only. Never edits, never rewrites the plan.
tools: Read, Grep, Glob, Bash
---

You attack an implementation plan before any code exists. You get the paths to
plan.md, research.md (if present), and the repo. One pass; no follow-ups.

Rubric — check exactly these, in order:
1. **Falsifiable acceptance criteria** — could each criterion be checked by a
   command, test, or observation? Flag any that are elastic ("works well").
2. **Hidden assumptions** — what must be true for this plan to work that the
   plan doesn't state? Verify against the actual code (cite file:line).
3. **Untestable or unverifiable steps** — tasks with no verification step.
4. **YAGNI / over-engineering** — work not required by the intent; plan prose
   longer than the code it describes.
5. **Missing files** — grep for callers/consumers of everything the plan
   touches; list files that will need changes the plan doesn't mention.
6. **Failure modes** — what breaks at runtime if a task is subtly wrong;
   concrete scenarios only.

Rules:
- Grounded findings only: every finding points at THIS plan or THIS codebase
  (file:line). No abstract methodology advice. No style opinions.
- Do not manufacture findings; an empty section is a valid result.
- You have no authority to rewrite the plan. Findings only.

Return format:
## Blocking
- <finding> — <evidence>
## Advisory
- <finding> — <evidence>
## Clean
<one line: what you checked and found sound>
```

- [ ] **Step 3: Write `agents/flow-reviewer.md`**

```markdown
---
name: flow-reviewer
description: Read-only code reviewer for the flow workflow. Dispatched once by /flow review with a diff range and plan.md path. Checks conformance to the plan first, then correctness. Never edits; fixes happen in the main session.
tools: Read, Grep, Glob, Bash
---

You review a completed implementation against its plan. You get: the diff range
(e.g. `main...HEAD`), the plan.md path, and the repo. One pass; no follow-ups.
Bash is for inspection only (`git diff`, `git log`, grep, running the project's
verify commands if asked).

Order of review:
1. **Conformance** (before correctness):
   - Scope creep — changes not traceable to a plan task; flag each.
   - Silent deviations — plan said X, code does Y, workflow.md Deviations
     section doesn't mention it.
   - Weakened verification — removed/skipped tests, loosened assertions,
     lowered thresholds, CI/test-config edits. Inspect these diffs FIRST.
   - Unimplemented acceptance criteria — walk plan.md criteria one by one.
2. **Correctness**: bugs, unhandled edge cases, hidden coupling (grep for other
   callers/consumers of every changed symbol), regressions.

Rules:
- No style/nitpick findings. Correctness and requirement gaps only.
- Every finding: severity (BLOCKING | ADVISORY), file:line, one-sentence
  failure scenario (concrete input/state → wrong outcome).
- Do not manufacture findings. "Clean, here is what I checked" is valid.

Return format:
## Blocking
- <severity, file:line, scenario>
## Advisory
- ...
## Acceptance criteria
- <criterion> → MET | NOT MET | PARTIAL (evidence)
## Checked
<one paragraph: what you examined>
```

- [ ] **Step 4: Verify frontmatter parses**

Run: `head -6 agents/*.md | grep -c "name: flow-"`
Expected: `3`.

- [ ] **Step 5: Commit**

```bash
git add agents && git commit -m "feat: flow-researcher, flow-plan-critic, flow-reviewer agents"
```

---

### Task 8: Driver skill — `/flow`

**Files:**
- Create: `skills/flow/SKILL.md`

**Interfaces:**
- Consumes: `workflow.md` frontmatter (Task 2), phase chains (Global Constraints).
- Produces: the routing contract every phase skill relies on: driver reads state → invokes phase skill by name via the Skill tool.

- [ ] **Step 1: Write `skills/flow/SKILL.md`**

```markdown
---
name: flow
description: Phased development workflow driver. Use when starting /flow, resuming flow work, or asking "where was I?" on a flow task. Reads docs/tasks/*/workflow.md state and routes to the right phase skill.
---

# Flow — driver

You route; phase skills do the work. Never perform a phase's work inline here.

## Locate state

1. Artifacts dir: `artifacts-dir:` from `.flow.md` at the repo root, else `docs/tasks`.
2. Active tasks: every `<artifacts-dir>/*/workflow.md` with `phase` ≠ `complete`.
3. Current branch: `git rev-parse --abbrev-ref HEAD`.

## Route

- **`/flow` with a task description** (no matching active task): invoke the
  `flow-start` skill with the description as argument.
- **`/flow` bare, one active task on this branch**: announce
  `<task> — phase <phase>; next: <Next action from workflow.md>`, then invoke
  the skill for that phase (table below).
- **`/flow` bare, several active tasks (any branch)**: list them
  (`task / phase / branch / updated`) and ask which to resume. If the chosen
  task's branch ≠ current branch, tell the user to switch branch/worktree
  first — do not switch for them.
- **`/flow status`**: print the list; route nowhere.

| phase          | skill          |
|----------------|----------------|
| setup          | flow-start     |
| research       | flow-research  |
| planning       | flow-plan      |
| plan-review    | flow-plan      |
| implementation | flow-implement |
| code-review    | flow-review    |
| reporting      | flow-report    |
| wind-down      | flow-wrap      |

## Rules

- `workflow.md` is the single routing input. Never infer phase from git or vibes.
- Trust `Next action` for intra-phase resume; phases are internally idempotent.
- Never edit `phase:` here — phase skills own their transitions.
- Announcements reference artifact files by path; never paste their contents.
```

- [ ] **Step 2: Commit**

```bash
git add skills/flow && git commit -m "feat: /flow driver skill — state-based routing"
```

---

### Task 9: Skill — `flow-start` (phase 1: setup)

**Files:**
- Create: `skills/flow-start/SKILL.md`

**Interfaces:**
- Consumes: `templates/workflow.md` (Task 2); `.flow.md` config keys (Task 2 example).
- Produces: task folder + `workflow.md` at `phase: setup`, branch/worktree; hands off to `flow-research` (full) or `flow-plan` (lite).

- [ ] **Step 1: Write `skills/flow-start/SKILL.md`**

```markdown
---
name: flow-start
description: Flow phase 1 (setup). Normally invoked via /flow with a new task description. Creates branch/worktree, task folder, workflow.md; recommends full or lite mode.
---

# Flow — setup

Argument: a task description, optionally with a ticket ref (e.g. "BEE-93: …").

1. **Read config.** `.flow.md` at repo root: `verify`, `verify-app`,
   `artifacts-dir` (default `docs/tasks`), `worktrees`, `domain-agents`.
   Missing file → defaults; ask for the verify command once and offer to
   save a `.flow.md`.
2. **Recommend a mode.** lite = small, well-understood, few files, no design
   questions; full = everything else. Recommend one with a one-line reason;
   the user confirms (AskUserQuestion, options full/lite).
3. **Create isolation.** Branch `flow/<slug>` from the default branch
   (worktree at the `.flow.md` `worktrees` path if configured; plain branch
   otherwise). Slug: kebab-case, ≤5 words, from the task description.
4. **Baseline checks.** Working tree clean; run `verify` — record pass/fail
   in workflow.md `Next action` (a red baseline is not fatal but MUST be
   recorded, so later failures are attributable).
5. **Create the task folder** `<artifacts-dir>/YYYY-MM-DD-<slug>/` and write
   `workflow.md` from the plugin's `templates/workflow.md`, filling every
   `{{placeholder}}`. `phase: setup`, `mode` as confirmed, `ticket` free text.
6. **Advance.** Set `updated`, set `phase: research` (full) or
   `phase: planning` (lite), write `Next action`, announce the transition,
   then invoke the `flow-research` or `flow-plan` skill.

Rules: never start on the default branch; never set `force:`; if a workflow.md
write is blocked by the validator, fix the transition — never work around it.
```

- [ ] **Step 2: Commit**

```bash
git add skills/flow-start && git commit -m "feat: flow-start skill — setup phase"
```

---

### Task 10: Skill — `flow-research` (phase 2)

**Files:**
- Create: `skills/flow-research/SKILL.md`

**Interfaces:**
- Consumes: `flow-researcher` agent (Task 7); `workflow.md` state.
- Produces: `research.md` in the task folder; transition to `planning`; invokes `flow-plan`.

- [ ] **Step 1: Write `skills/flow-research/SKILL.md`**

```markdown
---
name: flow-research
description: Flow phase 2 (research). Normally invoked via /flow. Codebase recon plus optional web research; writes research.md with file:line references.
---

# Flow — research

1. **Codebase recon first** (inline): what already exists for this task —
   relevant files, conventions, constraints, prior art (existing specs/plans,
   git history). Small task area → do it all inline.
2. **Fan out only for breadth.** Up to 3 parallel `flow-researcher` agents,
   each with ONE scoped question (e.g. one per subsystem, or one for an
   unfamiliar library). Cap at 3; if you want more, the task is too big —
   say so. Web research only when the task genuinely needs outside knowledge.
3. **Write `research.md`** in the task folder: Findings (with file:line),
   Constraints & prior art, Open questions. Dense; no pasted file bodies.
4. **Surface open questions** that change the plan's shape to the user now —
   cheaper than a rejected plan at gate 1.
5. **Advance.** Update `updated` + `Next action`, set `phase: planning`,
   announce (reference research.md by path), invoke the `flow-plan` skill.

Idempotent resume: if research.md already has findings, extend — don't redo.
```

- [ ] **Step 2: Commit**

```bash
git add skills/flow-research && git commit -m "feat: flow-research skill — recon + capped fan-out"
```

---

### Task 11: Skill — `flow-plan` (phases 3–4: planning + gated plan review)

**Files:**
- Create: `skills/flow-plan/SKILL.md`

**Interfaces:**
- Consumes: `templates/plan.md` (Task 2); `flow-plan-critic` agent (Task 7); gate-1 log format (Global Constraints).
- Produces: approved `plan.md`; decision-log `gate 1:` entry; transition to `implementation`; invokes `flow-implement`.

- [ ] **Step 1: Write `skills/flow-plan/SKILL.md`**

```markdown
---
name: flow-plan
description: Flow phases 3–4 (planning + gated plan review). Normally invoked via /flow. Writes a lean plan.md, runs the plan-critic, then holds at gate 1 for user approval.
---

# Flow — plan & plan review

## Phase 3: write the plan (inline, user watching)

Write `plan.md` in the task folder from the plugin's `templates/plan.md`:
- **Intent** + **falsifiable acceptance criteria** (each checkable by a
  command, test, or observation).
- **Approach** chosen, alternatives noted in one line each.
- **Tasks**: file-level — every task names the files it touches and its
  verification step. Guardrail: if the Tasks section is longer than the diff
  you expect it to produce, cut it down before proceeding.
- **Out of scope** + **Verification** (machine commands AND how to drive the
  app/feature end-to-end).

Then set `phase: plan-review`, update `Next action`.

## Phase 4: gated review

1. **Critic pass (once).** Dispatch `flow-plan-critic` with the plan.md,
   research.md, and repo paths. Revise plan.md for Blocking findings; use
   judgment on Advisory ones. ONE critic pass — do not re-dispatch after
   revising.
2. **User gate.** Present: plan.md by path, a ≤5-line summary of the approach,
   and the critic's verdict summary. Ask approve / revise (AskUserQuestion).
   Revisions loop back to the user, not to the critic.
3. **On approval** (never before): append to the decision log
   `- YYYY-MM-DD gate 1: plan approved by user`, set
   `phase: implementation`, update `updated` + `Next action`, announce, and
   invoke the `flow-implement` skill.

The validator blocks `phase: implementation` without the gate-1 line, and
blocks all code edits until then. If blocked, you skipped a step — fix the
process, never the guardrail.
```

- [ ] **Step 2: Commit**

```bash
git add skills/flow-plan && git commit -m "feat: flow-plan skill — lean plan + critic + gate 1"
```

---

### Task 12: Skill — `flow-implement` (phase 5)

**Files:**
- Create: `skills/flow-implement/SKILL.md`

**Interfaces:**
- Consumes: approved `plan.md`; `.flow.md` `domain-agents` map; `workflow.md` Progress/Deviations sections.
- Produces: implementation commits, ticked Progress entries, recorded deviations; transition to `code-review`; invokes `flow-review`.

- [ ] **Step 1: Write `skills/flow-implement/SKILL.md`**

```markdown
---
name: flow-implement
description: Flow phase 5 (implementation). Normally invoked via /flow. Executes plan.md task-by-task with per-task commits and live progress/deviation tracking in workflow.md.
---

# Flow — implement

Before the first task: copy plan.md's task list into workflow.md `## Progress`
as unchecked boxes (one per plan task), if not already there.

Per plan task, in order:
1. Implement exactly what the task says. TDD where the task has testable
   logic: failing test → minimal code → green.
2. Run the task's verification step from plan.md.
3. Commit (`<type>: <plan task title>`).
4. Tick the task in `## Progress` (add the commit sha) and bump `updated`.

**Deviations:** the moment reality diverges from plan.md (extra file, changed
approach, dropped step), record one line in `## Deviations` — in the same
turn, not later. Big divergence (approach invalidated, scope grew) → stop,
set `phase` back to `planning`, tell the user why.

**Delegation:** if `.flow.md` maps the task's file zone to a domain agent,
dispatch that agent with: the plan task text verbatim, the worktree path +
branch, and "report files touched + verification output". Verify its report
against `git diff` before ticking. Otherwise implement inline — one coherent
context beats a fleet.

When every Progress box is ticked: run the project `verify` command, set
`phase: code-review`, update `Next action`, announce, invoke the
`flow-review` skill.

Resume: on entry, trust `## Progress` — start at the first unticked task.
```

- [ ] **Step 2: Commit**

```bash
git add skills/flow-implement && git commit -m "feat: flow-implement skill — task-by-task execution with live state"
```

---

### Task 13: Skill — `flow-review` (phase 6)

**Files:**
- Create: `skills/flow-review/SKILL.md`

**Interfaces:**
- Consumes: `flow-reviewer` agent (Task 7); `plan.md`; `.flow.md` `verify` / `verify-app`.
- Produces: `review.md`; fixes committed; transition to `reporting` (full) or hand-off to `flow-wrap` (lite).

- [ ] **Step 1: Write `skills/flow-review/SKILL.md`**

```markdown
---
name: flow-review
description: Flow phase 6 (code review). Normally invoked via /flow. Dispatches the flow-reviewer against the diff and plan, fixes blocking findings inline, runs outcome verification.
---

# Flow — code review

1. **Dispatch `flow-reviewer`** (once) with: diff range
   (`<default-branch>...HEAD`), plan.md path, repo root, and the project's
   verify command. Do not review your own work inline instead — the fresh
   context IS the point.
2. **Write `review.md`** in the task folder from the reviewer's findings:
   Blocking / Advisory / Acceptance-criteria table / Checked. Note next to
   each finding what was done about it.
3. **Fix Blocking findings inline** (main session, visible), one commit per
   fix. Advisory: fix cheap ones; record the rest as report follow-ups.
   NOT-MET acceptance criteria are Blocking by definition.
4. **Re-verify:** project `verify` command must pass. Then **outcome
   verification**: run `verify-app` if configured, else drive the changed
   behavior by hand (run the app, exercise the feature) — green units alone
   don't count. Capture real output/screenshots for the report.
5. **Advance.** Update `updated` + `Next action`. Full mode: set
   `phase: reporting`, announce, invoke the `flow-report` skill. Lite mode:
   stay in `code-review` and invoke the `flow-wrap` skill (it owns gate 2).

One reviewer pass. If fixes were extensive (>~30% of the diff changed),
tell the user and offer a second pass — never loop silently.
```

- [ ] **Step 2: Commit**

```bash
git add skills/flow-review && git commit -m "feat: flow-review skill — diff-vs-plan review + outcome verification"
```

---

### Task 14: Skill — `flow-report` (phase 7, full mode)

**Files:**
- Create: `skills/flow-report/SKILL.md`

**Interfaces:**
- Consumes: `templates/report.md`; plan.md, review.md, workflow.md Deviations; gate-2 log format.
- Produces: `report.md`; a PR; decision-log `gate 2:` entry; transition to `wind-down`; invokes `flow-wrap`.

- [ ] **Step 1: Write `skills/flow-report/SKILL.md`**

```markdown
---
name: flow-report
description: Flow phase 7 (reporting, full mode). Normally invoked via /flow. Writes report.md with real evidence, opens the PR, then holds at gate 2 for merge approval.
---

# Flow — report (gate 2)

1. **Write `report.md`** from the plugin's `templates/report.md`:
   - Changed vs plan — from plan.md tasks + Progress.
   - Deviations — copy workflow.md `## Deviations`, expand each with why.
   - Evidence — paste the ACTUAL verify output and outcome-verification
     results captured in review. Re-run rather than claim from memory.
   - Follow-ups — advisory review findings + anything deferred.
2. **Open the PR** (`gh pr create` if a remote exists; otherwise present the
   description and note the merge will be local). Description generated from
   the artifact trail: intent (plan.md), approach summary, deviations, test
   evidence, links to the task folder artifacts.
3. **Gate 2.** Present to the user: report.md path, PR link, one-paragraph
   summary. Ask approve-merge / request-changes (AskUserQuestion). Changes →
   make them, update report evidence, ask again.
4. **On approval** (never before): append
   `- YYYY-MM-DD gate 2: merge approved by user`, set `phase: wind-down`,
   update `updated` + `Next action`, announce, invoke the `flow-wrap` skill.

The validator blocks `wind-down` without the gate-2 line, and blocks code
edits during `reporting`. Fix the process, never the guardrail.
```

- [ ] **Step 2: Commit**

```bash
git add skills/flow-report && git commit -m "feat: flow-report skill — evidence-based report + PR + gate 2"
```

---

### Task 15: Skill — `flow-wrap` (phase 8 + lite wrap)

**Files:**
- Create: `skills/flow-wrap/SKILL.md`

**Interfaces:**
- Consumes: gate-2 log format (lite path); workflow.md; merge decision from gate 2.
- Produces: learnings proposals, merged+cleaned workspace, `phase: complete`.

- [ ] **Step 1: Write `skills/flow-wrap/SKILL.md`**

```markdown
---
name: flow-wrap
description: Flow phase 8 (wind-down; also the lite-mode wrap). Normally invoked via /flow. Learnings capture, merge + cleanup, marks the task complete.
---

# Flow — wrap

## Lite mode entry (arriving from code-review)

Gate 2 hasn't run yet — run it first, in miniature:
1. Append a `## Quick report` section to workflow.md: 3–6 lines — what
   changed, verify output (pasted), deviations if any.
2. Open the PR (or present the local merge) as in flow-report step 2.
3. Ask approve-merge / request-changes. On approval append
   `- YYYY-MM-DD gate 2: merge approved by user`, THEN set
   `phase: wind-down`.

## Wind-down (both modes)

1. **Merge** per the gate-2 decision (merge PR / local merge to the default
   branch). If the user chose not to merge yet, skip merge but finish the rest.
2. **Learnings capture.** Review the task for durable lessons: a gotcha hit
   twice, a correction the user made, a convention discovered. For each,
   propose a concrete diff to CLAUDE.md, a domain skill, or memory — ONE at a
   time, user approves each. No approval → no edit. Zero lessons is a valid
   outcome; never invent one.
3. **Cleanup.** `git status` must be clean; remove the worktree if one was
   created; delete the merged branch if the user agrees; verify nothing
   uncommitted is stranded.
4. **Close.** Set `phase: complete`, final `updated` bump. The task folder
   stays forever as the record. Announce completion with the artifact paths.
```

- [ ] **Step 2: Commit**

```bash
git add skills/flow-wrap && git commit -m "feat: flow-wrap skill — lite gate 2, learnings, cleanup, complete"
```

---

### Task 16: README, merge, install + live smoke test

**Files:**
- Create: `README.md`
- Modify: (merge `v1` → `main`)

**Interfaces:**
- Consumes: everything above.
- Produces: installed, working plugin.

- [ ] **Step 1: Write `README.md`**

```markdown
# flow

Personal phased development workflow for Claude Code:
setup → research → plan → **gate 1** → implement → review-vs-plan → **gate 2** → wind-down.

- State: `docs/tasks/<date>-<slug>/workflow.md` in the target repo (resumable from any session).
- Gates enforced by a PreToolUse hook (`hooks/flow_validate.py`) — illegal phase
  transitions and pre-approval code edits are blocked, not discouraged.
- Escape hatch (user-only): add `force: true` to a task's workflow.md frontmatter.
- Per-repo config: `.flow.md` (see `templates/flow-config-example.md`).
- Spec: `docs/specs/2026-07-04-flow-workflow-design.md`.

Install:
    /plugin marketplace add /Users/scoot/dev/flow
    /plugin install flow@flow

Usage: `/flow <task description>` to start; `/flow` to resume; `/flow status` to list.
Tests: `python3 -m unittest discover tests -v`
```

- [ ] **Step 2: Full test suite + merge**

```bash
python3 -m unittest discover tests -v          # expected: all pass
git add README.md && git commit -m "docs: README"
git switch main && git merge --no-ff v1 -m "Merge v1: flow plugin implementation"
```

- [ ] **Step 3: Install (requires the user's session)**

In a Claude Code session: `/plugin marketplace add /Users/scoot/dev/flow`, then `/plugin install flow@flow`, then restart the session so skills + hooks load.
Expected: `/flow` appears as a command; `claude plugin list` (or `/plugin`) shows `flow`.

- [ ] **Step 4: Live smoke test (fresh session, scratch repo)**

```bash
mkdir -p ~/dev/flow-smoke && cd ~/dev/flow-smoke && git init -b main
```
In the session:
1. `/flow add a hello command` → expect: mode question, branch `flow/…` created, task folder + workflow.md written, research/planning begins. (Approve the trivial plan at gate 1.)
2. While a *second* scratch task is parked in `planning`: ask Claude to edit a code file → expect the hook to block with "code edits are locked".
3. Ask Claude to set that task's `phase:` straight to `reporting` → expect the hook to block the skip.
4. Add `force: true` by hand to that workflow.md → expect edits now allowed.
Record any friction found as issues in the flow repo (`docs/issues.md`) — they seed the bee-topia shakedown.

- [ ] **Step 5: Commit anything the smoke test changed**

```bash
cd /Users/scoot/dev/flow && git add -A && git commit -m "docs: smoke-test notes" || true
```

---

### Task 17: Bee-topia shakedown prep — `.flow.md`

**Files:**
- Create: `/Users/scoot/dev/bee-topia/.flow.md` (bee-topia repo — branch + PR, never direct to main)

**Interfaces:**
- Consumes: `templates/flow-config-example.md` format.
- Produces: bee-topia ready for the real shakedown (one lite + one full ticket, run interactively after this plan).

- [ ] **Step 1: Branch in bee-topia**

```bash
cd /Users/scoot/dev/bee-topia && git switch -c flow-config
```

- [ ] **Step 2: Write `.flow.md`**

```markdown
# Flow config

verify: flutter analyze && flutter test
verify-app: node scripts/screenshot_dock.js
artifacts-dir: docs/tasks
worktrees: .worktrees/<branch>

## domain-agents
- lib/game/rendering/ → bee-sprites
- lib/models/, lib/state/, lib/constants/, lib/services/ → bee-game-logic
- lib/ui/ → bee-ui
- lib/game/components/, lib/game/behaviors/, lib/game/meadow_game.dart → bee-world
```

- [ ] **Step 3: Commit + PR**

```bash
git add .flow.md && git commit -m "chore: add .flow.md config for the flow workflow plugin"
git push -u origin flow-config && gh pr create --title "Add .flow.md flow-workflow config" \
  --body "Config for the new flow plugin (verify commands, artifact dir, domain-agent map). Part of the flow shakedown."
```

Expected: PR opens; merge after review. The shakedown itself (one lite ticket, one full ticket through the whole workflow) happens interactively afterwards and is intentionally not a task in this plan.
