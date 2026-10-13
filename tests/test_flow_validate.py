import json, os, shutil, subprocess, tempfile, unittest
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

def bash(command, cwd=None):
    p = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
         "tool_input": {"command": command}}
    if cwd is not None: p["cwd"] = str(cwd)
    return p

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
    def destroy(self):
        subprocess.run(["git", "-C", str(self.dir), "worktree", "prune"],
                       capture_output=True)
        shutil.rmtree(self.dir, ignore_errors=True)

class TestNoOpPaths(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.destroy)

    def test_non_edit_tool_allowed(self):
        r = run_hook({"hook_event_name": "PreToolUse", "tool_name": "Read",
                      "tool_input": {"file_path": str(self.repo.dir / "a")}},
                     self.repo.dir)
        self.assertEqual(r.returncode, 0)

    def test_shell_with_no_tasks_dir_allowed(self):
        r = run_hook(bash("echo x > src/a.py", self.repo.dir), self.repo.dir)
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

PLAN = """# Plan — Demo

## Assumptions & open questions
- [assumed] the demo path is stable — src/a.py:1
"""

class TestStateMachine(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.destroy)
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
        self.repo.write("docs/tasks/2026-07-05-demo/plan.md", PLAN)
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
        self.addCleanup(self.repo.destroy)

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


class TestShellLockdown(unittest.TestCase):
    """Bash is held to the Write/Edit rule for the writes it visibly makes."""
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.destroy)
        self.repo.write("src/a.py", "x")

    def activate(self, phase, branch="main"):
        text = wf(phase).replace("branch: main", f"branch: {branch}")
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", text)

    def run_bash(self, command, cwd=None):
        return run_hook(bash(command, self.repo.dir if cwd is None else cwd),
                        self.repo.dir)

    def test_the_real_bypass_is_blocked_naming_file_and_gate(self):
        self.activate("planning")
        r = self.run_bash("printf 'x' > src/a.py.tmp && mv src/a.py.tmp src/a.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("flow: task 'demo' is in phase 'planning' — code edits "
                      "are locked until gate 1 (plan approval)", r.stderr)
        self.assertIn("this command writes src/a.py.tmp (via >)", r.stderr)

    def test_common_write_forms_blocked_before_gate1(self):
        self.activate("research")
        for cmd in ("echo x >> src/a.py", "echo x | tee src/b.py",
                    "sed -i '' 's/x/y/' src/a.py", "perl -pi -e 's/x/y/' src/a.py",
                    "rm src/a.py", "touch src/b.py", "mkdir src/new",
                    "cp /tmp/x src/a.py", "ln -s a.py src/b.py",
                    "dd if=/dev/zero of=src/a.py count=1", "git apply /tmp/x.patch",
                    "patch -p1 < /tmp/x.patch", "git checkout -- src/a.py",
                    "git restore src/a.py",
                    "python3 -c \"open('src/a.py', 'w').write('y')\"",
                    "cat > src/a.py <<'EOF'\nprint(1)\nEOF"):
            self.assertEqual(self.run_bash(cmd).returncode, 2, cmd)

    def test_reporting_blocks_until_gate2(self):
        self.activate("reporting")
        r = self.run_bash("echo x > src/a.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("gate 2 (merge approval)", r.stderr)

    def test_read_only_shell_allowed(self):
        self.activate("planning")
        for cmd in ("cat src/a.py", "grep -rn x src", "rg x", "ls -la src",
                    "git log --oneline", "git diff", "git status",
                    "python3 -m unittest discover tests > /tmp/flow-test.out 2>&1",
                    "ls src 2>/dev/null", "echo oops >&2", "grep x <<< 'a > b'",
                    "cat src/a.py | sort | uniq -c", 'grep ">" src/a.py',
                    "git switch -c flow/other", "git worktree list"):
            self.assertEqual(self.run_bash(cmd).returncode, 0, cmd)

    def test_flow_files_stay_writable(self):
        self.activate("planning")
        task = "docs/tasks/2026-07-05-demo"
        for cmd in (f"cat > {task}/research.md <<'EOF'\n# Research\nEOF",
                    f"echo '- note' >> {task}/workflow.md",
                    f"mkdir -p {task}/shots", f"cd {task} && touch plan.md",
                    "echo 'verify: make test' >> .flow.md",
                    f"git add {task} && git commit -m 'flow: research'"):
            self.assertEqual(self.run_bash(cmd).returncode, 0, cmd)

    def test_writes_outside_the_repo_allowed(self):
        self.activate("planning")
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        for cmd in ("echo x > /tmp/flow-scratch.txt", f"touch {scratch}/a.py",
                    f"cp src/a.py {scratch}/", f"cd {scratch} && echo x > b.py"):
            self.assertEqual(self.run_bash(cmd).returncode, 0, cmd)

    def test_cwd_comes_from_the_hook_input(self):
        self.activate("planning")
        src = self.repo.dir / "src"
        self.assertEqual(self.run_bash("echo x > a.py", cwd=src).returncode, 2)
        task = self.repo.dir / "docs/tasks/2026-07-05-demo"
        self.assertEqual(self.run_bash("echo x > notes.md", cwd=task).returncode, 0)

    def test_without_cwd_the_project_dir_is_used(self):
        self.activate("planning")
        r = run_hook(bash("echo x > src/a.py"), self.repo.dir)
        self.assertEqual(r.returncode, 2)

    def test_implementation_and_forced_and_other_branch_allowed(self):
        self.activate("implementation")
        self.assertEqual(self.run_bash("echo x > src/a.py").returncode, 0)
        self.activate("planning", branch="feature/other")
        self.assertEqual(self.run_bash("echo x > src/a.py").returncode, 0)
        text = wf("planning").replace("branch: main", "branch: main\nforce: true")
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", text)
        self.assertEqual(self.run_bash("echo x > src/a.py").returncode, 0)

    def test_unparseable_command_allowed(self):
        self.activate("planning")
        self.assertEqual(self.run_bash("echo 'x > src/a.py").returncode, 0)


class TestTemplateGate(unittest.TestCase):
    """The shipped template's example comment must not satisfy gate 1."""
    def test_shipped_template_does_not_satisfy_gate1(self):
        repo = Repo()
        self.addCleanup(repo.destroy)
        tpl = (Path(__file__).resolve().parent.parent
               / "templates" / "workflow.md").read_text()
        filled = (tpl.replace("{{slug}}", "demo")
                  .replace("{{one-line title}}", "Demo")
                  .replace("{{ticket-or-blank}}", "")
                  .replace("{{full-or-lite}}", "lite")
                  .replace("{{branch}}", "main")
                  .replace("{{worktree-path-or-blank}}", "")
                  .replace("{{YYYY-MM-DD}}", "2026-07-05")
                  .replace("phase: setup", "phase: plan-review"))
        wf_path = repo.dir / "docs/tasks/2026-07-05-demo/workflow.md"
        repo.write("docs/tasks/2026-07-05-demo/workflow.md", filled)
        repo.write("docs/tasks/2026-07-05-demo/plan.md", PLAN)
        attempt = filled.replace("phase: plan-review", "phase: implementation")
        r = run_hook(payload("Write", wf_path, content=attempt), repo.dir)
        self.assertEqual(r.returncode, 2)
        approved = attempt.replace(
            "## Decision log",
            "## Decision log\n- 2026-07-05 gate 1: plan approved by user")
        r = run_hook(payload("Write", wf_path, content=approved), repo.dir)
        self.assertEqual(r.returncode, 0)


class TestPlanAssumptions(unittest.TestCase):
    """Entering implementation requires plan.md to declare its judgment calls."""
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.destroy)
        self.wf_path = self.repo.dir / "docs/tasks/2026-07-05-demo/workflow.md"
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", wf("plan-review"))
        self.approved = wf("implementation",
                           log="- 2026-07-05 gate 1: plan approved by user")

    def attempt(self, plan=None, wf_text=None):
        if plan is not None:
            self.repo.write("docs/tasks/2026-07-05-demo/plan.md", plan)
        return run_hook(payload("Write", self.wf_path,
                                content=wf_text or self.approved),
                        self.repo.dir).returncode

    def test_missing_plan_blocked(self):
        self.assertEqual(self.attempt(), 2)

    def test_missing_section_blocked(self):
        self.assertEqual(self.attempt("# Plan — Demo\n\n## Approach\nx\n"), 2)

    def test_placeholder_entry_blocked(self):
        self.assertEqual(self.attempt(
            "## Assumptions & open questions\n"
            "- {{marker}} {{assumption}} — {{evidence or rationale}}\n"), 2)

    def test_commented_entry_blocked(self):
        self.assertEqual(self.attempt(
            "## Assumptions & open questions\n"
            "<!-- - [assumed] example that must not count -->\n"), 2)

    def test_shipped_template_does_not_satisfy(self):
        tpl = (Path(__file__).resolve().parent.parent
               / "templates" / "plan.md").read_text()
        self.assertEqual(self.attempt(tpl), 2)

    def test_section_ends_at_next_heading(self):
        # entries under ## Tasks must not be mistaken for assumptions
        self.assertEqual(self.attempt(
            "## Assumptions & open questions\n\n"
            "## Tasks\n1. do the thing — files: a.py — verify: pytest\n"
            "- stray bullet under tasks\n"), 2)

    def test_real_entry_allowed(self):
        self.assertEqual(self.attempt(
            "## Assumptions & open questions\n"
            "- [assumed] retry policy applies — config/http.rb:12\n"), 0)

    def test_explicit_none_allowed(self):
        self.assertEqual(self.attempt(
            "## Assumptions & open questions\n"
            "- none — mechanical rename, no judgment calls\n"), 0)

    def test_force_bypasses(self):
        forced = self.approved.replace("branch: main",
                                       "branch: main\nforce: true")
        self.assertEqual(self.attempt(wf_text=forced), 0)

    def test_not_checked_when_already_in_implementation(self):
        self.repo.write("docs/tasks/2026-07-05-demo/workflow.md", self.approved)
        self.assertEqual(self.attempt(wf_text=self.approved), 0)


class TestWorktreeRoot(unittest.TestCase):
    """Validator must enforce inside a git worktree when CLAUDE_PROJECT_DIR
    points at the main checkout."""
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.destroy)
        self.repo.write("seed.txt", "x")
        for cmd in (["add", "."],
                    ["-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-m", "seed"]):
            subprocess.run(["git", "-C", str(self.repo.dir)] + cmd,
                           capture_output=True, check=True)
        self.wt = self.repo.dir / ".worktrees" / "flow-demo"
        subprocess.run(["git", "-C", str(self.repo.dir), "worktree", "add",
                        "-b", "flow/demo", str(self.wt)],
                       capture_output=True, check=True)
        text = wf("planning").replace("branch: main", "branch: flow/demo")
        p = self.wt / "docs" / "tasks" / "2026-07-05-demo" / "workflow.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_lockdown_applies_inside_worktree(self):
        r = run_hook(payload("Write", self.wt / "src" / "a.py", content="x"),
                     self.repo.dir)
        self.assertEqual(r.returncode, 2)

    def test_shell_lockdown_applies_inside_worktree(self):
        r = run_hook(bash("echo x > .worktrees/flow-demo/src/a.py", self.repo.dir),
                     self.repo.dir)
        self.assertEqual(r.returncode, 2)
        r = run_hook(bash("echo x > src/a.py", self.wt), self.repo.dir)
        self.assertEqual(r.returncode, 2)
        # main's own files aren't locked: the task is on flow/demo
        r = run_hook(bash("echo x > src/a.py", self.repo.dir), self.repo.dir)
        self.assertEqual(r.returncode, 0)

    def test_state_machine_applies_inside_worktree(self):
        p = self.wt / "docs" / "tasks" / "2026-07-05-demo" / "workflow.md"
        skip = wf("implementation").replace("branch: main", "branch: flow/demo")
        r = run_hook(payload("Write", p, content=skip), self.repo.dir)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
