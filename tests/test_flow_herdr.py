import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))
import flow_herdr  # noqa: E402
from flow_herdr import KEYS, MOD_SRC, VERSION, clear, do, in_herdr, install, label_task, labels_for, panel, remove, session_start, snapshots, split, sync  # noqa: E402

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

    def test_a_completed_task_keeps_only_its_name_and_complete(self):
        self.assertEqual(labels_for(task(phase="complete")),
                         {**{k: "" for k in KEYS}, "flow.task": "add-widget", "flow.phase": "complete"})

    def test_label_task_is_one_hc_label_on_the_sessions_terminal(self):
        run = Recorder()
        self.assertIsNone(label_task(task(), env=HERDR, which=ON_PATH, run=run))
        self.assertEqual(run.calls[0][:4], ["hc", "label", "t3", "flow.task=add-widget"])
        self.assertEqual(run.calls[0][-1], f"{VERSION}={flow_herdr.plugin_version()}")
        self.assertEqual(len(run.calls[0]), 3 + len(KEYS) + 1)

    def test_outside_herdr_or_without_hc_nothing_runs(self):
        run = Recorder()
        label_task(task(), env={}, which=ON_PATH, run=run)
        label_task(task(), env=HERDR, which=NOT_ON_PATH, run=run)
        self.assertEqual(run.calls, [])

    def test_a_refused_label_says_why(self):
        self.assertIsNotNone(label_task(task(), env=HERDR, which=ON_PATH, run=Recorder(({"error": "no such terminal"}, 1))))

    def test_clear_takes_them_all_off_with_the_version(self):
        run = Recorder()
        clear(env=HERDR, which=ON_PATH, run=run)
        self.assertEqual(run.calls[0][3:], [f"{k}=" for k in (*KEYS, VERSION)])

    def test_a_tasks_labels_leave_the_version_alone(self):
        self.assertNotIn(VERSION, labels_for(task()))
        self.assertNotIn(VERSION, labels_for(task(phase="complete")))


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


class HomeCase(unittest.TestCase):
    """A Herdr app folder of its own, so nothing touches the real one."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.env = {"HERDR_APP_HOME": str(self.home), "HC_TERMINAL_ID": "t3"}
        self.dest = self.home / "mods" / "flow"

    def flow_json(self):
        return json.loads((self.dest / "flow.json").read_text())


class TestInstall(HomeCase):
    def test_install_copies_the_mod_and_names_this_plugin(self):
        run = Recorder(({}, 0))
        doc = install(self.env, which=ON_PATH, run=run)
        self.assertTrue(doc["ok"], doc)
        self.assertEqual(sorted(f.name for f in flow_herdr.MOD_FILES()), ["main.js", "mod.json", "model.js"])
        for f in flow_herdr.MOD_FILES():
            self.assertEqual((self.dest / f.name).read_text(), f.read_text())
        self.assertEqual(self.flow_json()["root"], str(flow_herdr.PLUGIN))
        self.assertEqual(run.calls, [["herdr-app", "check", str(self.dest)]])

    def test_a_reinstall_replaces_each_file_whole(self):
        install(self.env, check=False)
        main = self.home / "mods" / "flow" / "main.js"
        before = main.stat().st_ino
        install(self.env, check=False)
        self.assertNotEqual(main.stat().st_ino, before)  # a new file, renamed in: never half-written
        self.assertEqual(main.read_text(), (MOD_SRC / "main.js").read_text())
        self.assertEqual([f.name for f in main.parent.iterdir() if f.name.endswith(".tmp")], [])

    def test_a_failed_check_is_said(self):
        doc = install(self.env, which=ON_PATH, run=Recorder(({}, 1)))
        self.assertFalse(doc["ok"])
        self.assertIn("check failed", doc["message"])

    def test_no_herdr_folder_no_install(self):
        doc = install({"HERDR_APP_HOME": str(self.home / "nowhere")}, which=ON_PATH, run=Recorder())
        self.assertFalse(doc["ok"])
        self.assertIn("install and open the Herdr app", doc["message"])

    def test_someone_elses_flow_mod_is_left_alone(self):
        self.dest.mkdir(parents=True)
        (self.dest / "main.js").write_text("theirs")
        self.assertFalse(install(self.env, which=ON_PATH, run=Recorder())["ok"])
        self.assertFalse(remove(self.env)["ok"])
        self.assertEqual((self.dest / "main.js").read_text(), "theirs")

    def test_remove(self):
        install(self.env, which=NOT_ON_PATH)
        self.assertTrue(remove(self.env)["ok"])
        self.assertFalse(self.dest.exists())


class TestSync(HomeCase):
    def put(self, root, version):
        install(self.env, which=NOT_ON_PATH)
        (self.dest / "main.js").write_text("old")
        (self.dest / "flow.json").write_text(json.dumps({"root": root, "version": version}))

    def test_nothing_installed_nothing_synced(self):
        self.assertIsNone(sync(self.env))
        self.assertFalse(self.dest.exists())

    def test_an_older_or_moved_copy_is_refreshed(self):
        for root, version in ((str(flow_herdr.PLUGIN), "0.0.1"), ("/gone/flow/0.9.0", "99.0.0")):
            self.put(root, version)
            self.assertTrue(sync(self.env)["ok"])
            self.assertNotEqual((self.dest / "main.js").read_text(), "old")
            self.assertEqual(self.flow_json()["root"], str(flow_herdr.PLUGIN))

    def test_a_newer_flows_copy_is_left(self):
        self.put(str(self.home), "99.0.0")
        self.assertIsNone(sync(self.env))
        self.assertEqual((self.dest / "main.js").read_text(), "old")


LS = {"spaces": [{"tabs": [{"terminals": [{"terminal": "t1", "pane": "p1"}, {"terminal": "t3", "pane": "p3"}]}]}]}


class TestPanel(HomeCase):
    def test_opens_beside_the_sessions_own_pane(self):
        install(self.env, which=NOT_ON_PATH)
        run = Recorder((LS, 0), ({"pane": "p9"}, 0))
        self.assertTrue(panel(self.env, which=ON_PATH, run=run)["ok"])
        self.assertEqual(run.calls[1], ["herdr-app", "do", "pane.split", "--pane", "p3", "--direction", "right", "--mod", "flow"])

    def test_not_installed_says_how(self):
        doc = panel(self.env, which=ON_PATH, run=Recorder())
        self.assertIn("/flow-herdr install", doc["message"])

    def test_outside_herdr(self):
        self.assertFalse(panel({}, which=ON_PATH, run=Recorder())["ok"])


class TestSessionStart(HomeCase):
    def snap(self, current):
        tasks = [task(folder="2026-11-11-add-widget")]
        return {"tasks": tasks, "current": current}

    def test_labels_the_task_the_session_is_on(self):
        run = Recorder()
        with mock.patch("flow_status.snapshot", return_value=self.snap("2026-11-11-add-widget")):
            session_start({"cwd": "/r"}, self.env, which=ON_PATH, run=run)
        self.assertIn("flow.task=add-widget", run.calls[0])
        self.assertIn(f"{VERSION}={flow_herdr.plugin_version()}", run.calls[0])
        self.assertEqual(len(run.calls), 1)

    def test_no_task_here_clears_the_task_but_says_which_flow(self):
        run = Recorder()
        with mock.patch("flow_status.snapshot", return_value=self.snap(None)):
            session_start({"cwd": "/r"}, self.env, which=ON_PATH, run=run)
        self.assertEqual(run.calls[0][3:], [*(f"{k}=" for k in KEYS), f"{VERSION}={flow_herdr.plugin_version()}"])

    def test_outside_herdr_nothing_is_read(self):
        with mock.patch("flow_status.snapshot") as snap:
            session_start({"cwd": "/r"}, {"HERDR_APP_HOME": str(self.home)}, which=ON_PATH, run=Recorder())
        snap.assert_not_called()


class TestSnapshots(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.dir)

    def repo(self, path, tasks=True):
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        if tasks:
            (path / "docs" / "tasks").mkdir(parents=True)
        return path

    def roots(self, cwd):
        return [s["root"] for s in snapshots(cwd)]

    def test_inside_a_repo_its_own(self):
        r = self.repo(self.dir / "app")
        (r / "src").mkdir()
        self.assertEqual(self.roots(r / "src"), [str(r)])

    def test_a_repo_without_tasks_is_still_its_own(self):
        r = self.repo(self.dir / "app", tasks=False)
        self.assertEqual(self.roots(r), [str(r)])

    def test_a_folder_of_repos_reads_those_with_flow_tasks(self):
        a = self.repo(self.dir / "android")
        self.repo(self.dir / "web", tasks=False)
        b = self.repo(self.dir / "ios")
        (self.dir / "notes").mkdir()
        self.assertEqual(self.roots(self.dir), [str(a), str(b)])

    def test_a_folder_with_no_repos_is_itself(self):
        (self.dir / "notes").mkdir()
        self.assertEqual(self.roots(self.dir), [str(self.dir)])

    def test_at_most_a_few_repos_below(self):
        for i in range(flow_herdr.BELOW + 2):
            self.repo(self.dir / f"r{i:02}")
        self.assertEqual(len(self.roots(self.dir)), flow_herdr.BELOW)


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
