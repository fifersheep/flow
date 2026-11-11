import json, subprocess, sys, unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))
from flow_herdr import KEYS, clear, do, in_herdr, label_task, labels_for, split  # noqa: E402

ON_PATH = lambda name: f"/usr/local/bin/{name}"
NOT_ON_PATH = lambda name: None
HERDR = {"HC_TERMINAL_ID": "t3"}


class Recorder:
    """A stand-in for subprocess.run: records argv, answers from a queue."""

    def __init__(self, *answers):
        self.calls, self.answers = [], list(answers)

    def __call__(self, argv, **_):
        self.calls.append(argv)
        out, code = self.answers.pop(0) if self.answers else ({"ok": True}, 0)
        return subprocess.CompletedProcess(argv, code, json.dumps(out), "")


def task(**over):
    return {"slug": "add-widget", "phase": "implementation", "mode": "full", "dir": "/r/docs/tasks/x",
            "progress": {"done": 2, "total": 5}, "gates": [{"n": 1, "state": "passed"}], **over}


class TestLabels(unittest.TestCase):
    def test_an_active_task(self):
        self.assertEqual(labels_for(task()), {
            "flow.task": "add-widget", "flow.phase": "implementation", "flow.mode": "full",
            "flow.progress": "2/5", "flow.gate": "", "flow.dir": "/r/docs/tasks/x"})

    def test_a_waiting_gate_is_its_number(self):
        self.assertEqual(labels_for(task(gates=[{"n": 1, "state": "waiting"}]))["flow.gate"], "1")

    def test_an_empty_checklist_takes_progress_off(self):
        self.assertEqual(labels_for(task(progress={"done": 0, "total": 0}))["flow.progress"], "")

    def test_a_completed_task_takes_every_label_off(self):
        self.assertEqual(labels_for(task(phase="complete")), {k: "" for k in KEYS})

    def test_label_task_is_one_hc_label_on_the_sessions_terminal(self):
        run = Recorder()
        self.assertIsNone(label_task(task(), env=HERDR, which=ON_PATH, run=run))
        self.assertEqual(run.calls[0][:4], ["hc", "label", "t3", "flow.task=add-widget"])
        self.assertEqual(len(run.calls[0]), 3 + len(KEYS))

    def test_outside_herdr_or_without_hc_nothing_runs(self):
        run = Recorder()
        label_task(task(), env={}, which=ON_PATH, run=run)
        label_task(task(), env=HERDR, which=NOT_ON_PATH, run=run)
        self.assertEqual(run.calls, [])

    def test_a_refused_label_says_why(self):
        self.assertIsNotNone(label_task(task(), env=HERDR, which=ON_PATH, run=Recorder(({"error": "no such terminal"}, 1))))

    def test_clear_takes_them_all_off(self):
        run = Recorder()
        clear(env=HERDR, which=ON_PATH, run=run)
        self.assertEqual(run.calls[0][3:], [f"{k}=" for k in KEYS])


class TestSplit(unittest.TestCase):
    MADE = ({"pane": "p9", "terminal": "t9"}, 0)

    def test_right_focuses_the_sessions_pane_then_opens_beside_it(self):
        run = Recorder(({"ok": True}, 0), self.MADE)
        self.assertEqual(split("t3", "right", "/wt", run=run), {"pane": "p9", "terminal": "t9"})
        self.assertEqual(run.calls, [
            ["herdr-app", "do", "pane.focus", "--terminal", "t3"],
            ["herdr-app", "do", "terminal.open", "--folder", "/wt", "--place", "right"]])

    def test_bottom_opens_down(self):
        run = Recorder(({"ok": True}, 0), self.MADE)
        split("t3", "bottom", "/wt", run=run)
        self.assertEqual(run.calls[1][-1], "down")
        self.assertEqual(len(run.calls), 2)

    def test_left_and_top_swap_the_new_pane_across(self):
        for side, place, direction in (("left", "right", "left"), ("top", "down", "up")):
            run = Recorder(({"ok": True}, 0), self.MADE)
            split("t3", side, "/wt", run=run)
            self.assertEqual(run.calls[1][-1], place)
            self.assertEqual(run.calls[2], ["herdr-app", "do", "pane.swap", "--pane", "p9", "--direction", direction])

    def test_herdrs_refusal_is_the_error(self):
        with self.assertRaisesRegex(RuntimeError, "no such terminal"):
            do("pane.focus", run=Recorder(({"error": "no such terminal"}, 1)), terminal="t3")

    def test_in_herdr_needs_the_terminal_and_the_cli(self):
        self.assertTrue(in_herdr(HERDR, ON_PATH))
        self.assertFalse(in_herdr({}, ON_PATH))
        self.assertFalse(in_herdr(HERDR, NOT_ON_PATH))


class TestScript(unittest.TestCase):
    def test_clear_outside_herdr_exits_quietly(self):
        r = subprocess.run(["python3", str(HOOKS / "flow_herdr.py"), "clear"], capture_output=True, text=True,
                           env={"PATH": "/usr/bin:/bin"})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_bad_arguments(self):
        r = subprocess.run(["python3", str(HOOKS / "flow_herdr.py"), "split"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
