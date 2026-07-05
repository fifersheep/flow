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

    def test_mode_switch_cannot_skip_ahead(self):
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", wf("research"))
        r = self.attempt(wf("wind-down", mode="lite",
                            log="- 2026-07-05 gate 2: merge approved"))
        self.assertEqual(r.returncode, 2)

    def test_mode_switch_one_step_allowed(self):
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", wf("research"))
        self.assertEqual(self.attempt(wf("planning", mode="lite")).returncode, 0)

    def test_force_in_existing_file_allows(self):
        text = wf("setup").replace("branch: main", "branch: main\nforce: true")
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", text)
        self.assertEqual(self.attempt(wf("reporting")).returncode, 0)

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

if __name__ == "__main__":
    unittest.main()
