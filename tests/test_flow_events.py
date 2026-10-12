import json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "hooks" / "flow_events.py"

WORKFLOW = """---
task: add-widget
title: Add the widget
ticket-id: BEE-93
mode: full
phase: {phase}
branch: flow/add-widget
worktree: /tmp/wt
created: 2026-09-21
updated: 2026-09-21
---

## Next action
Do the thing.
"""


class EventsCase(unittest.TestCase):
    """Temp repo + isolated plugin-data dir, so state never leaks between tests."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        subprocess.run(["git", "init", "-b", "main", str(self.dir)],
                       capture_output=True, check=True)
        self.data = self.dir / "plugin-data"
        self.task_dir = self.dir / "docs" / "tasks" / "2026-09-21-add-widget"
        self.task_dir.mkdir(parents=True)
        self.sentinel = self.dir / "fired.log"

    def write_config(self, body):
        (self.dir / ".flow.md").write_text(body)

    def write_workflow(self, phase):
        p = self.task_dir / "workflow.md"
        p.write_text(WORKFLOW.format(phase=phase))
        return p

    def run_hook(self, file_path, tool="Write"):
        payload = {"hook_event_name": "PostToolUse", "tool_name": tool,
                   "cwd": str(self.dir),
                   "tool_input": {"file_path": str(file_path)}}
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.dir),
                   CLAUDE_PLUGIN_DATA=str(self.data))
        return subprocess.run(["python3", str(SCRIPT)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env)

    def fired(self):
        return self.sentinel.read_text().splitlines() if self.sentinel.is_file() else []


class TestNoOpPaths(EventsCase):
    def test_other_tool_ignored(self):
        self.write_config(f"## on\n- setup: echo x >> {self.sentinel}\n")
        self.write_workflow("setup")
        r = self.run_hook(self.dir / "src.py", tool="Bash")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.fired(), [])

    def test_non_workflow_file_ignored(self):
        self.write_config(f"## on\n- setup: echo x >> {self.sentinel}\n")
        other = self.task_dir / "plan.md"
        other.write_text("# plan")
        r = self.run_hook(other)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.fired(), [])

    def test_workflow_outside_artifacts_dir_ignored(self):
        self.write_config(f"## on\n- setup: echo x >> {self.sentinel}\n")
        stray = self.dir / "workflow.md"
        stray.write_text(WORKFLOW.format(phase="setup"))
        r = self.run_hook(stray)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.fired(), [])

    def test_no_config_is_silent(self):
        wf = self.write_workflow("setup")
        r = self.run_hook(wf)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_config_without_on_section_is_silent(self):
        self.write_config("verify: pytest\nartifacts-dir: docs/tasks\n")
        wf = self.write_workflow("setup")
        r = self.run_hook(wf)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_unconfigured_phase_does_not_fire(self):
        self.write_config(f"## on\n- complete: echo x >> {self.sentinel}\n")
        r = self.run_hook(self.write_workflow("setup"))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.fired(), [])


class TestFiring(EventsCase):
    def test_fires_on_configured_phase(self):
        self.write_config(f"## on\n- setup: echo fired >> {self.sentinel}\n")
        r = self.run_hook(self.write_workflow("setup"))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.fired(), ["fired"])
        self.assertIn("ran `on setup` hook", json.loads(r.stdout)["systemMessage"])

    def test_same_phase_written_twice_fires_once(self):
        self.write_config(f"## on\n- setup: echo fired >> {self.sentinel}\n")
        wf = self.write_workflow("setup")
        self.run_hook(wf)
        r = self.run_hook(wf, tool="Edit")  # a progress tick, not a transition
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertEqual(self.fired(), ["fired"])

    def test_each_transition_fires(self):
        self.write_config(
            f"## on\n- setup: echo setup >> {self.sentinel}\n"
            f"- implementation: echo impl >> {self.sentinel}\n")
        self.run_hook(self.write_workflow("setup"))
        self.run_hook(self.write_workflow("research"))       # no command configured
        self.run_hook(self.write_workflow("implementation"))
        self.assertEqual(self.fired(), ["setup", "impl"])

    def test_returning_to_a_phase_fires_again(self):
        self.write_config(f"## on\n- planning: echo plan >> {self.sentinel}\n")
        self.run_hook(self.write_workflow("planning"))
        self.run_hook(self.write_workflow("plan-review"))
        self.run_hook(self.write_workflow("planning"))  # sent back by the critic
        self.assertEqual(self.fired(), ["plan", "plan"])

    def test_task_frontmatter_exposed_as_env(self):
        self.write_config(
            "## on\n- implementation: "
            f'printf "%s|%s|%s|%s|%s\\n" "$FLOW_PHASE" "$FLOW_PREV_PHASE" '
            f'"$FLOW_TICKET_ID" "$FLOW_BRANCH" "$FLOW_TASK_DIR" >> {self.sentinel}\n')
        self.run_hook(self.write_workflow("plan-review"))
        self.run_hook(self.write_workflow("implementation"))
        self.assertEqual(
            self.fired(),
            [f"implementation|plan-review|BEE-93|flow/add-widget|"
             f"{self.task_dir.resolve()}"])

    def test_command_runs_in_repo_root(self):
        self.write_config(f"## on\n- setup: pwd >> {self.sentinel}\n")
        self.run_hook(self.write_workflow("setup"))
        self.assertEqual(self.fired(), [str(self.dir.resolve())])


class TestConfigParsing(EventsCase):
    def test_commented_entries_ignored(self):
        self.write_config(
            "## on\n<!-- - setup: echo commented >> /dev/null -->\n"
            f"- setup: echo real >> {self.sentinel}\n")
        self.run_hook(self.write_workflow("setup"))
        self.assertEqual(self.fired(), ["real"])

    def test_unfilled_placeholder_ignored(self):
        self.write_config("## on\n- setup: {{your command here}}\n")
        r = self.run_hook(self.write_workflow("setup"))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_unknown_key_reported_not_silently_dropped(self):
        self.write_config(
            f"## on\n- setup: echo fired >> {self.sentinel}\n"
            "- worktree-created: echo typo\n")
        r = self.run_hook(self.write_workflow("setup"))
        msg = json.loads(r.stdout)["systemMessage"]
        self.assertIn("worktree-created", msg)
        self.assertIn("aren't phases", msg)

    def test_on_section_ends_at_next_heading(self):
        self.write_config(
            f"## on\n- setup: echo fired >> {self.sentinel}\n\n"
            "## domain-agents\n- setup: echo leaked >> /dev/null\n")
        self.run_hook(self.write_workflow("setup"))
        self.assertEqual(self.fired(), ["fired"])

    def test_custom_artifacts_dir_honoured(self):
        alt = self.dir / "notes" / "2026-09-21-add-widget"
        alt.mkdir(parents=True)
        self.write_config(
            f"artifacts-dir: notes\n\n## on\n- setup: echo fired >> {self.sentinel}\n")
        wf = alt / "workflow.md"
        wf.write_text(WORKFLOW.format(phase="setup"))
        self.run_hook(wf)
        self.assertEqual(self.fired(), ["fired"])


class TestFailureIsNeverFatal(EventsCase):
    def test_failing_command_reported_and_survived(self):
        self.write_config("## on\n- setup: exit 3\n")
        r = self.run_hook(self.write_workflow("setup"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("failed", json.loads(r.stdout)["systemMessage"])

    def test_failing_command_still_advances_state(self):
        self.write_config("## on\n- setup: exit 3\n")
        wf = self.write_workflow("setup")
        self.run_hook(wf)
        r = self.run_hook(wf)  # must not retry on every later write
        self.assertEqual(r.stdout.strip(), "")

    def test_malformed_payload_survived(self):
        env = dict(os.environ, CLAUDE_PLUGIN_DATA=str(self.data))
        r = subprocess.run(["python3", str(SCRIPT)], input="not json",
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)

    def test_missing_workflow_file_survived(self):
        r = self.run_hook(self.task_dir / "workflow.md")
        self.assertEqual(r.returncode, 0)

    def test_unknown_phase_ignored(self):
        self.write_config(f"## on\n- setup: echo x >> {self.sentinel}\n")
        wf = self.task_dir / "workflow.md"
        wf.write_text(WORKFLOW.format(phase="banana"))
        r = self.run_hook(wf)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.fired(), [])


if __name__ == "__main__":
    unittest.main()
