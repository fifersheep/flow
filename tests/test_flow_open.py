import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
SCRIPT = HOOKS / "flow_open.py"
sys.path.insert(0, str(HOOKS))
import flow_open  # noqa: E402
from flow_open import ITERM_HELPER, command_for, open_path, setup  # noqa: E402

ON_PATH = lambda name: f"/usr/local/bin/{name}"
NOT_ON_PATH = lambda name: None


def cmd(kind, app, platform="darwin", env=None, which=ON_PATH, side="right", size=50):
    return command_for(kind, app, "/repo-wt", side, size, platform=platform, env=env or {}, which=which)


ITERM_ENV = {"ITERM_SESSION_ID": "w0t2p0:BDC47A57-ED9A-4B89-9253-184F2B9CD615"}


class TestTerminal(unittest.TestCase):
    def test_default_splits_this_sessions_own_iterm_pane(self):
        argv, what = cmd("terminal", None, env=ITERM_ENV)
        self.assertEqual(argv[0], "osascript")
        self.assertEqual(argv[-2:], ["/repo-wt", "BDC47A57-ED9A-4B89-9253-184F2B9CD615"])
        self.assertNotIn("/repo-wt", argv[2])
        self.assertIn("split vertically", argv[2])
        self.assertEqual(what, "an iTerm split")

    def test_bottom_at_half_is_still_applescript(self):
        argv, _ = cmd("terminal", "iterm-split", env=ITERM_ENV, side="bottom")
        self.assertIn("split horizontally", argv[2])

    def test_any_other_split_runs_the_python_api_helper(self):
        env = {**ITERM_ENV, "FLOW_ITERM_VENV": "/venv"}
        for side, size in (("left", 50), ("top", 25), ("right", 30)):
            argv, _ = cmd("terminal", "iterm-split", env=env, side=side, size=size)
            self.assertEqual(argv, ["/venv/bin/python", str(ITERM_HELPER), "BDC47A57-ED9A-4B89-9253-184F2B9CD615",
                                    side, str(size), "/repo-wt"])

    def test_side_and_size_are_made_sane(self):
        argv, _ = cmd("terminal", "iterm-split", env={**ITERM_ENV, "FLOW_ITERM_VENV": "/venv"}, side="diagonal", size=99)
        self.assertEqual(argv[3:5], ["right", "90"])

    def test_a_split_outside_iterm_falls_back_to_a_tab_and_says_so(self):
        argv, what = cmd("terminal", "iterm-split")
        self.assertIn("create tab", argv[2])
        self.assertIn("no pane to split", what)

    def test_iterm_tab_with_the_path_as_an_argument(self):
        argv, what = cmd("terminal", "iterm-tab")
        self.assertEqual(argv[0], "osascript")
        self.assertEqual(argv[-1], "/repo-wt")  # passed, never spliced into the script
        self.assertNotIn("/repo-wt", argv[2])
        self.assertIn("create tab", argv[2])
        self.assertIn('"tab" is "window"', argv[2])
        self.assertEqual(what, "an iTerm tab")

    def test_iterm_window(self):
        argv, _ = cmd("terminal", "iterm-window")
        self.assertIn('"window" is "window"', argv[2])

    def test_terminal_app_and_warp_open_the_folder(self):
        self.assertEqual(cmd("terminal", "terminal")[0], ["open", "-a", "Terminal", "/repo-wt"])
        self.assertEqual(cmd("terminal", "warp")[0], ["open", "-a", "Warp", "/repo-wt"])

    def test_tmux_needs_a_tmux_session(self):
        self.assertIsNone(cmd("terminal", "tmux")[0])
        self.assertEqual(cmd("terminal", "tmux", env={"TMUX": "/tmp/tmux-1/default,1,0", "TMUX_PANE": "%3"})[0],
                         ["tmux", "split-window", "-h", "-l", "50%", "-t", "%3", "-c", "/repo-wt"])

    def test_tmux_splits_on_any_side_at_any_size(self):
        tmux = {"TMUX": "x"}
        self.assertEqual(cmd("terminal", "tmux", env=tmux, side="left", size=30)[0][2:6], ["-h", "-b", "-l", "30%"])
        self.assertEqual(cmd("terminal", "tmux", env=tmux, side="top", size=25)[0][2:6], ["-v", "-b", "-l", "25%"])
        self.assertEqual(cmd("terminal", "tmux", env=tmux, side="bottom")[0][2:5], ["-v", "-l", "50%"])

    def test_tmux_works_off_macos_and_the_others_do_not(self):
        self.assertIsNotNone(cmd("terminal", "tmux", platform="linux", env={"TMUX": "x"})[0])
        argv, why = cmd("terminal", "iterm-split", platform="linux", env=ITERM_ENV)
        self.assertIsNone(argv)
        self.assertIn("macOS", why)

    def test_unknown_terminal(self):
        argv, why = cmd("terminal", "kitty")
        self.assertIsNone(argv)
        self.assertIn("iterm-split", why)


class TestEditor(unittest.TestCase):
    def test_default_is_vs_code_by_its_cli(self):
        self.assertEqual(cmd("editor", None), (["code", "/repo-wt"], "VS Code"))

    def test_no_cli_on_macos_falls_back_to_the_app(self):
        self.assertEqual(cmd("editor", "vscode", which=NOT_ON_PATH)[0],
                         ["open", "-a", "Visual Studio Code", "/repo-wt"])
        self.assertEqual(cmd("editor", "cursor", which=NOT_ON_PATH)[0], ["open", "-a", "Cursor", "/repo-wt"])

    def test_no_cli_off_macos_says_so(self):
        argv, why = cmd("editor", "zed", platform="linux", which=NOT_ON_PATH)
        self.assertIsNone(argv)
        self.assertIn("zed", why)


class TestApiFallback(unittest.TestCase):
    """A split the Python API can't make falls back to AppleScript's nearest."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        env = {**ITERM_ENV, "FLOW_ITERM_VENV": str(self.dir / "venv")}
        self.api = mock.patch.object(flow_open, "api_enabled", return_value=True)
        for patch in (mock.patch.dict(flow_open.os.environ, env), mock.patch.object(flow_open.sys, "platform", "darwin"),
                      self.api):
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_api_split_when_it_works(self):
        with mock.patch.object(flow_open, "ensure_venv", return_value=None), \
             mock.patch.object(flow_open, "run", return_value=None) as run:
            doc = open_path("terminal", "iterm-split", str(self.dir), "left", 30)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["message"], f"opened an iTerm split (left, 30%) in {self.dir}")
        self.assertEqual(run.call_args_list[0].args[0][1], str(ITERM_HELPER))

    def test_api_off_falls_back_to_the_same_axis_at_half_and_says_why(self):
        calls = []
        def run(argv, timeout=20):
            calls.append(argv)
            return "ConnectionRefusedError" if argv[1] == str(ITERM_HELPER) else None
        with mock.patch.object(flow_open, "ensure_venv", return_value=None), mock.patch.object(flow_open, "run", run):
            doc = open_path("terminal", "iterm-split", str(self.dir), "top", 25)
        self.assertTrue(doc["ok"])
        self.assertIn("split horizontally", calls[1][2])
        self.assertTrue(doc["needsSetup"])
        self.assertEqual(doc["message"], "split bottom at 50% — top at 25% needs setup: run /flow-term setup")

    def test_an_api_that_is_off_is_not_tried(self):
        flow_open.api_enabled.return_value = False
        with mock.patch.object(flow_open, "ensure_venv") as venv, mock.patch.object(flow_open, "run", return_value=None) as run:
            doc = open_path("terminal", "iterm-split", str(self.dir), "left", 30)
        venv.assert_not_called()
        self.assertEqual(len(run.call_args_list), 1)
        self.assertIn("split vertically", run.call_args_list[0].args[0][2])
        self.assertTrue(doc["needsSetup"])

    def test_a_dry_run_says_when_the_press_will_install(self):
        doc = open_path("terminal", "iterm-split", str(self.dir), "left", 30, dry_run=True)
        self.assertTrue(doc["setup"])
        self.assertFalse(open_path("terminal", "iterm-split", str(self.dir), dry_run=True)["setup"])

    def test_a_failed_setup_falls_back_too(self):
        with mock.patch.object(flow_open, "ensure_venv", return_value="no network"), \
             mock.patch.object(flow_open, "run", return_value=None) as run:
            doc = open_path("terminal", "iterm-split", str(self.dir), "left", 30)
        self.assertTrue(doc["ok"])
        self.assertIn("split vertically", run.call_args_list[0].args[0][2])
        self.assertTrue(doc["needsSetup"])


class TestSetup(unittest.TestCase):
    """/flow-term setup: each missing piece named, with its fix, in order."""

    def setUp(self):
        self.env = {**ITERM_ENV, "FLOW_ITERM_VENV": "/nowhere/venv"}

    def setup_lines(self, side="left", size=30, app=None, env=None, api=True, package=True, install=None, connect=None):
        with mock.patch.object(flow_open, "api_enabled", return_value=api), \
             mock.patch.object(flow_open, "has_package", return_value=package), \
             mock.patch.object(flow_open, "ensure_venv", return_value=install) as venv, \
             mock.patch.object(flow_open, "run", return_value=connect):
            doc = setup(app, side, size, platform="darwin", env=self.env if env is None else env)
        self.installed = venv.called
        return doc["ok"], doc["lines"]

    def test_all_in_place_is_ready(self):
        ok, lines = self.setup_lines()
        self.assertTrue(ok)
        self.assertEqual(lines[-1], "  ✓ ready — t and /flow-term split left at 30%")
        self.assertFalse(self.installed)

    def test_api_off_names_the_setting_and_skips_the_rest(self):
        ok, lines = self.setup_lines(api=False)
        self.assertFalse(ok)
        text = "\n".join(lines)
        self.assertIn("▲ iTerm's Python API is off", text)
        self.assertIn('Settings → General → Magic → tick "Enable Python API"', text)
        self.assertIn("○ helper package — waits on the API", text)
        self.assertIn("until then, t splits right at 50%", text)
        self.assertFalse(self.installed)

    def test_a_missing_package_is_installed_by_setup(self):
        ok, lines = self.setup_lines(package=False)
        self.assertTrue(ok)
        self.assertTrue(self.installed)
        self.assertIn("  ✓ helper package installed in /nowhere/venv", lines)

    def test_a_failed_install_says_why_and_what_to_do(self):
        ok, lines = self.setup_lines(package=False, install="no network")
        self.assertFalse(ok)
        self.assertIn("  ▲ couldn't install the helper package: no network", lines)

    def test_a_failed_connection_says_what_to_allow(self):
        ok, lines = self.setup_lines(connect="ConnectionRefusedError")
        self.assertFalse(ok)
        self.assertTrue(any("allow it" in line for line in lines))

    def test_outside_iterm(self):
        ok, lines = self.setup_lines(env={})
        self.assertFalse(ok)
        self.assertIn("isn't running in iTerm", lines[1])

    def test_right_at_half_needs_nothing_more(self):
        ok, lines = self.setup_lines(side="right", size=50, api=False)
        self.assertTrue(ok)
        self.assertIn("nothing more to set up", lines[2])

    def test_paths_under_home_read_as_tilde(self):
        self.env["FLOW_ITERM_VENV"] = str(Path.home() / ".cache" / "flow" / "iterm2-venv")
        _, lines = self.setup_lines()
        self.assertIn("  ✓ helper package in ~/.cache/flow/iterm2-venv", lines)

    def test_every_line_leads_with_a_glyph_the_mod_colours(self):
        _, lines = self.setup_lines(api=False)
        for line in lines:
            self.assertIn(line.strip()[0], "▌✓▲▸○", line)


class TestScript(unittest.TestCase):
    def run_script(self, *args):
        r = subprocess.run(["python3", str(SCRIPT), *args], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_dry_run_names_the_resolved_folder_and_opens_nothing(self):
        d = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        doc = self.run_script("terminal", str(d), "--app", "terminal", "--dry-run")
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["argv"], ["open", "-a", "Terminal", str(d)])
        self.assertIn(str(d), doc["message"])

    def test_a_missing_folder_is_an_answer_not_a_crash(self):
        doc = self.run_script("editor", "/no/such/worktree", "--dry-run")
        self.assertFalse(doc["ok"])
        self.assertIn("/no/such/worktree", doc["message"])

    def test_bad_arguments_are_an_answer_not_a_crash(self):
        self.assertFalse(self.run_script("terminal")["ok"])
        self.assertFalse(self.run_script("browser", ".", "--dry-run")["ok"])


if __name__ == "__main__":
    unittest.main()
