import json, shutil, subprocess, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "hooks" / "flow_status.py"

WORKFLOW = """---
task: {slug}
title: Add the widget
ticket: https://linear.app/x/BEE-93
ticket-id: BEE-93
mode: {mode}
phase: {phase}
branch: {branch}
worktree:
created: 2026-09-21
updated: {updated}
---

## Next action
Finish task 3 —
  the retry wrapper.

## Decision log
<!-- gate entries look like: "- 2026-07-05 gate 1: plan approved by user" -->
{log}

## Progress
- [x] Task 1: scaffold (abc123)
- [x] Task 2: parser (def456)
- [ ] Task 3: retry wrapper
- [ ] Task 4: docs

## Deviations
{deviations}
"""


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, check=True)


class StatusCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        git(self.dir, "init", "-b", "main")
        git(self.dir, "config", "user.email", "t@t")
        git(self.dir, "config", "user.name", "t")

    def task(self, folder, root=None, slug="add-widget", mode="full",
             phase="implementation", branch="main", updated="2026-09-22",
             log="- 2026-09-21 gate 1: plan approved by user", deviations="",
             plan=None):
        d = (root or self.dir) / "docs" / "tasks" / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / "workflow.md").write_text(WORKFLOW.format(
            slug=slug, mode=mode, phase=phase, branch=branch, updated=updated,
            log=log, deviations=deviations))
        if plan is not None:
            (d / "plan.md").write_text(plan)
        return d

    def snap(self, cwd=None):
        r = subprocess.run(["python3", str(SCRIPT), "--cwd", str(cwd or self.dir)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)


class TestSnapshot(StatusCase):
    def test_no_tasks_is_an_empty_snapshot(self):
        doc = self.snap()
        self.assertEqual(doc["tasks"], [])
        self.assertIsNone(doc["current"])
        self.assertEqual(doc["branch"], "main")

    def test_task_fields(self):
        self.task("2026-09-21-add-widget", plan="# Plan\n\n## Assumptions\n- none — x\n")
        doc = self.snap()
        t = doc["tasks"][0]
        self.assertEqual(doc["current"], "2026-09-21-add-widget")
        self.assertEqual((t["slug"], t["mode"], t["phase"]), ("add-widget", "full", "implementation"))
        self.assertEqual(t["phaseIndex"], 4)
        self.assertEqual(t["ticketId"], "BEE-93")
        self.assertEqual(t["nextAction"], "Finish task 3 — the retry wrapper.")
        self.assertEqual((t["progress"]["done"], t["progress"]["total"]), (2, 4))
        self.assertEqual(t["progress"]["items"][2], {"text": "Task 3: retry wrapper", "done": False})
        self.assertTrue(t["plan"].startswith("# Plan"))
        self.assertIsNone(t["reportPath"])

    def test_commented_examples_are_not_decisions(self):
        self.task("t", log="")
        self.assertEqual(self.snap()["tasks"][0]["decisions"], [])

    def test_deviations_listed(self):
        self.task("t", deviations="- 2026-09-22 used a queue, not a lock")
        self.assertEqual(self.snap()["tasks"][0]["deviations"],
                         ["2026-09-22 used a queue, not a lock"])

    def test_output_is_stable_between_runs(self):
        self.task("t")
        a = subprocess.run(["python3", str(SCRIPT), "--cwd", str(self.dir)],
                           capture_output=True, text=True).stdout
        b = subprocess.run(["python3", str(SCRIPT), "--cwd", str(self.dir)],
                           capture_output=True, text=True).stdout
        self.assertEqual(a, b)

    def test_long_plan_is_capped(self):
        self.task("t", plan="x" * 50000)
        self.assertLess(len(self.snap()["tasks"][0]["plan"]), 41000)

    def test_not_a_repo_still_answers(self):
        bare = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        doc = self.snap(bare)
        self.assertEqual(doc["tasks"], [])


class TestGates(StatusCase):
    def gates(self, **kw):
        self.task("t", **kw)
        return {g["n"]: g for g in self.snap()["tasks"][0]["gates"]}

    def test_gate_one_waiting_at_plan_review(self):
        g = self.gates(phase="plan-review", log="")
        self.assertEqual(g[1]["state"], "waiting")
        self.assertEqual(g[2]["state"], "ahead")

    def test_gate_one_passed_carries_its_date(self):
        g = self.gates(phase="implementation")
        self.assertEqual((g[1]["state"], g[1]["date"]), ("passed", "2026-09-21"))

    def test_gate_two_waiting_at_reporting_in_full(self):
        g = self.gates(phase="reporting")
        self.assertEqual(g[2]["state"], "waiting")

    def test_gate_two_waiting_at_code_review_in_lite(self):
        g = self.gates(mode="lite", phase="code-review")
        self.assertEqual(g[2]["state"], "waiting")

    def test_lite_chain_has_no_research(self):
        self.task("t", mode="lite", phase="planning", log="")
        t = self.snap()["tasks"][0]
        self.assertNotIn("research", t["chain"])
        self.assertEqual(t["phaseIndex"], 1)


class TestWhichTask(StatusCase):
    def test_current_is_the_active_task_on_this_branch(self):
        self.task("a", slug="a", branch="flow/a")
        self.task("b", slug="b", branch="main")
        self.assertEqual(self.snap()["current"], "b")

    def test_complete_task_is_never_current(self):
        self.task("a", phase="complete")
        doc = self.snap()
        self.assertIsNone(doc["current"])
        self.assertFalse(doc["tasks"][0]["isActive"])

    def test_active_tasks_sort_first_newest_first(self):
        self.task("old", slug="old", branch="x", updated="2026-09-01")
        self.task("new", slug="new", branch="y", updated="2026-09-30")
        self.task("done", slug="done", phase="complete", updated="2026-10-01")
        self.assertEqual([t["folder"] for t in self.snap()["tasks"]], ["new", "old", "done"])

    def test_tasks_in_other_worktrees_are_found(self):
        (self.dir / "README").write_text("x")
        git(self.dir, "add", ".")
        git(self.dir, "commit", "-m", "init")
        wt = self.dir.parent / (self.dir.name + "-wt")
        self.addCleanup(shutil.rmtree, wt, ignore_errors=True)
        git(self.dir, "worktree", "add", "-b", "flow/side", str(wt))
        self.task("side", root=wt, slug="side", branch="flow/side", phase="planning")
        doc = self.snap()
        side = [t for t in doc["tasks"] if t["folder"] == "side"]
        self.assertEqual(len(side), 1)
        self.assertEqual(Path(side[0]["worktree"]), wt.resolve())
        self.assertFalse(side[0]["isHere"])
        # ...and from inside that worktree it is the current task
        self.assertEqual(self.snap(wt)["current"], "side")

    def test_copy_on_the_tasks_own_branch_wins(self):
        (self.dir / "README").write_text("x")
        git(self.dir, "add", ".")
        git(self.dir, "commit", "-m", "init")
        wt = self.dir.parent / (self.dir.name + "-wt2")
        self.addCleanup(shutil.rmtree, wt, ignore_errors=True)
        git(self.dir, "worktree", "add", "-b", "flow/dup", str(wt))
        self.task("dup", slug="dup", branch="flow/dup", phase="planning")
        self.task("dup", root=wt, slug="dup", branch="flow/dup", phase="code-review")
        dup = [t for t in self.snap()["tasks"] if t["folder"] == "dup"]
        self.assertEqual([t["phase"] for t in dup], ["code-review"])


if __name__ == "__main__":
    unittest.main()
