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
