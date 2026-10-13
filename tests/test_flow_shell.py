import shutil, sys, tempfile, unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))
from flow_shell import tokenize, writes  # noqa: E402


class ShellCase(unittest.TestCase):
    """writes() against a real temp dir as cwd, so paths resolve as they would
    in a checkout; results come back relative to it where they're inside."""
    def setUp(self):
        self.cwd = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.cwd, ignore_errors=True)
        (self.cwd / "src").mkdir()
        (self.cwd / "src" / "a.py").write_text("x")

    def w(self, command):
        out = []
        for path, how in writes(command, str(self.cwd)):
            shown = (str(path.relative_to(self.cwd))
                     if path == self.cwd or self.cwd in path.parents else str(path))
            out.append((shown, how))
        return out

    def paths(self, command):
        return [p for p, _ in self.w(command)]


class TestReadOnly(ShellCase):
    """The research and planning phases' everyday shell: nothing written."""
    def test_reads_write_nothing(self):
        for cmd in (
                "cat src/a.py", "grep -rn 'def ' src", "rg -n foo src/",
                "ls -la", "ls src | wc -l", "head -20 src/a.py",
                "git log --oneline -10", "git diff main...HEAD -- src/",
                "git status --short", "git show HEAD:src/a.py | less",
                "git branch --show-current", "npm test", "python3 -m pytest -q",
                "python3 -m unittest discover tests -v",
                "find . -name '*.py' | xargs grep -n foo",
                "cat <<< \"$x\"", "grep foo <<< 'a > b'",
                "diff <(git show HEAD:src/a.py) src/a.py",
                "if [[ $a > $b ]]; then echo yes; fi",
                "echo $(( 3 > 2 ))", "(( n > 0 )) && echo positive",
                "echo hi >&2", "cmd 2>&1 | tail -5", "exec 3>&1",
                "git log --format='%h > %s'", 'grep ">" src/a.py',
                "grep -E '<|>' src/a.py", "awk -F'|' '{print $1}' src/a.py",
                "sed -n '1,20p' src/a.py", "sed 's/a/b/' src/a.py",
                "perl -ne 'print if /x/' src/a.py",
                "python3 -c \"print(open('src/a.py').read())\"",
                "node -e \"console.log(require('fs').readFileSync('a.js'))\""):
            self.assertEqual(self.w(cmd), [], cmd)

    def test_writes_outside_the_repo_are_reported_outside_it(self):
        # the validator allows these: no checkout holds them
        self.assertEqual(self.paths("npm test > /tmp/out 2>&1"),
                         [str(Path("/tmp/out").resolve())])
        self.assertEqual(self.paths("cmd 2>/dev/null"), ["/dev/null"])
        self.assertEqual(self.paths("make &> /dev/null"), ["/dev/null"])
        self.assertEqual(self.paths("cd /tmp && echo x > a.txt"),
                         [str(Path("/tmp/a.txt").resolve())])
        self.assertEqual(self.paths("cp src/a.py /tmp/"),
                         [str(Path("/tmp").resolve())])

    def test_setup_and_wrap_git_is_not_a_write(self):
        for cmd in ("git switch -c flow/demo main", "git checkout -b flow/demo",
                    "git checkout main", "git worktree add .worktrees/demo -b flow/demo",
                    "git add docs/tasks/2026-10-13-demo && git commit -m 'flow: setup'",
                    "git push -u origin flow/demo", "git fetch && git pull --ff-only",
                    "git restore --staged src/a.py", "git apply --check fix.patch",
                    "git apply --stat fix.patch", "patch --dry-run -p1 < fix.patch",
                    "npm install", "npm ci", "pip install -e .",
                    "gh pr create --title x --body-file /tmp/body.md"):
            self.assertEqual(self.w(cmd), [], cmd)

    def test_mkdir_of_an_existing_folder_is_a_no_op(self):
        self.assertEqual(self.w("mkdir -p src"), [])


class TestCaught(ShellCase):
    def test_redirects(self):
        self.assertEqual(self.w("echo x > src/b.py"), [("src/b.py", ">")])
        self.assertEqual(self.w("echo x >> src/a.py"), [("src/a.py", ">>")])
        self.assertEqual(self.w("echo x >| src/a.py"), [("src/a.py", ">|")])
        self.assertEqual(self.w("make &> build.log"), [("build.log", "&>")])
        self.assertEqual(self.w("make >& build.log"), [("build.log", ">&")])
        self.assertEqual(self.w("echo x 1>out.txt 2>&1"), [("out.txt", ">")])
        self.assertEqual(self.w("echo x>src/a.py"), [("src/a.py", ">")])
        self.assertEqual(self.w('echo x > "src/my file.py"'),
                         [("src/my file.py", ">")])

    def test_the_real_run_printf_then_mv(self):
        self.assertEqual(self.w("printf 'x' > src/a.py.tmp && mv src/a.py.tmp src/a.py"),
                         [("src/a.py.tmp", ">"), ("src/a.py.tmp", "mv"),
                          ("src/a.py", "mv")])

    def test_heredoc_into_a_file(self):
        self.assertEqual(self.w("cat > src/a.py <<'EOF'\nprint('hi')\nEOF"),
                         [("src/a.py", ">")])
        self.assertEqual(self.w("cat <<-EOF > src/a.py\n\tx\n\tEOF\nls"),
                         [("src/a.py", ">")])

    def test_tee(self):
        self.assertEqual(self.w("echo x | tee src/a.py"), [("src/a.py", "tee")])
        self.assertEqual(self.w("echo x | tee -a a.log b.log"),
                         [("a.log", "tee"), ("b.log", "tee")])

    def test_in_place_editors(self):
        self.assertEqual(self.w("sed -i 's/a/b/' src/a.py"), [("src/a.py", "sed -i")])
        self.assertEqual(self.w("sed -i '' 's/a/b/' src/a.py"), [("src/a.py", "sed -i")])
        self.assertEqual(self.w("sed -i.bak -e 's/a/b/' src/a.py"),
                         [("src/a.py", "sed -i")])
        self.assertEqual(self.w("sed -Ei 's/a/b/' src/a.py"), [("src/a.py", "sed -i")])
        self.assertEqual(self.w("sed --in-place 's/a/b/' src/a.py"),
                         [("src/a.py", "sed -i")])
        self.assertEqual(self.w("perl -pi -e 's/a/b/' src/a.py"),
                         [("src/a.py", "perl -i")])
        self.assertEqual(self.w("perl -i.bak -pe 's/a/b/' src/a.py"),
                         [("src/a.py", "perl -i")])

    def test_file_commands(self):
        self.assertEqual(self.w("rm -rf src"), [("src", "rm")])
        self.assertEqual(self.w("touch src/new.py"), [("src/new.py", "touch")])
        self.assertEqual(self.w("mkdir -p src/new"), [("src/new", "mkdir")])
        self.assertEqual(self.w("cp /tmp/a.py src/a.py"), [("src/a.py", "cp")])
        self.assertEqual(self.w("cp -t src /tmp/a.py"), [("src", "cp")])
        self.assertEqual(self.w("ln -s ../shared/x.py src/x.py"),
                         [("src/x.py", "ln")])
        self.assertEqual(self.w("ln -s /opt/tool"), [("tool", "ln")])
        self.assertEqual(self.w("mv src/a.py /tmp/"),
                         [("src/a.py", "mv"), (str(Path("/tmp").resolve()), "mv")])
        self.assertEqual(self.w("dd if=/dev/zero of=disk.img bs=1k count=1"),
                         [("disk.img", "dd")])
        self.assertEqual(self.w("truncate -s 0 src/a.py"), [("src/a.py", "truncate")])

    def test_patches_write_the_tree_they_run_in(self):
        self.assertEqual(self.w("git apply /tmp/fix.patch"), [(".", "git apply")])
        self.assertEqual(self.w("patch -p1 < /tmp/fix.patch"), [(".", "patch")])
        self.assertEqual(self.w("patch src/a.py /tmp/fix.patch"), [("src/a.py", "patch")])
        self.assertEqual(self.w("git -C src apply /tmp/fix.patch"), [("src", "git apply")])

    def test_git_puts_files_back(self):
        self.assertEqual(self.w("git checkout -- src/a.py"),
                         [("src/a.py", "git checkout")])
        self.assertEqual(self.w("git checkout HEAD~1 -- ."), [(".", "git checkout")])
        self.assertEqual(self.w("git checkout src/a.py"), [("src/a.py", "git checkout")])
        self.assertEqual(self.w("git restore src/a.py"), [("src/a.py", "git restore")])
        self.assertEqual(self.w("git restore -s HEAD~2 --worktree --staged src/a.py"),
                         [("src/a.py", "git restore")])

    def test_interpreter_one_liners(self):
        self.assertEqual(self.w("python3 -c \"open('src/a.py', 'w').write('x')\""),
                         [("src/a.py", "python3")])
        self.assertEqual(self.w("python -c \"open('a.txt', mode='a').write('x')\""),
                         [("a.txt", "python")])
        self.assertEqual(self.w("python3 -c \"from pathlib import Path; "
                                "Path('src/a.py').write_text('x')\""),
                         [("src/a.py", "python3")])
        self.assertEqual(self.w("node -e \"require('fs').writeFileSync('a.js', 'x')\""),
                         [("a.js", "node")])
        self.assertEqual(self.w("ruby -e \"File.write('a.rb', 'x')\""), [("a.rb", "ruby")])
        self.assertEqual(self.w("python3 - <<'EOF'\nopen('src/b.py', 'w')\nEOF"),
                         [("src/b.py", "python3")])

    def test_nested_shells(self):
        self.assertEqual(self.w("bash -c 'echo x > src/a.py'"), [("src/a.py", ">")])
        self.assertEqual(self.w("sh -lc \"rm src/a.py\""), [("src/a.py", "rm")])
        self.assertEqual(self.w("bash <<'EOF'\ntouch src/b.py\nEOF"),
                         [("src/b.py", "touch")])
        self.assertEqual(self.w("eval 'echo x > src/a.py'"), [("src/a.py", ">")])

    def test_wrappers_keywords_and_lists(self):
        self.assertEqual(self.w("FOO=1 sudo -E rm -f src/a.py"), [("src/a.py", "rm")])
        self.assertEqual(self.w("/bin/rm src/a.py"), [("src/a.py", "rm")])
        self.assertEqual(self.w("for f in a b; do rm src/a.py; done"),
                         [("src/a.py", "rm")])
        self.assertEqual(self.w("ls; echo x > a.txt"), [("a.txt", ">")])
        self.assertEqual(self.w("ls || touch a.txt"), [("a.txt", "touch")])
        self.assertEqual(self.w("ls\ntouch a.txt"), [("a.txt", "touch")])
        self.assertEqual(self.w("x=$(cat src/a.py > b.txt)"), [("b.txt", ">")])


class TestCwd(ShellCase):
    def test_cd_moves_later_paths(self):
        self.assertEqual(self.paths("cd src && echo x > b.py"), ["src/b.py"])
        self.assertEqual(self.paths("cd src; cd ..; touch c.py"), ["c.py"])

    def test_unknown_cwd_drops_relative_paths_only(self):
        self.assertEqual(self.paths("cd $DIR && touch a.py"), [])
        self.assertEqual(self.paths("cd - && touch a.py /tmp/b"),
                         [str(Path("/tmp/b").resolve())])

    def test_git_dash_c(self):
        self.assertEqual(self.paths("git -C src checkout -- a.py"), ["src/a.py"])


class TestParsing(ShellCase):
    def test_quoted_operators_are_words(self):
        self.assertEqual(tokenize('a ">" b'), [("word", "a"), ("word", ">"), ("word", "b")])
        self.assertEqual(tokenize("a '|' b"), [("word", "a"), ("word", "|"), ("word", "b")])
        self.assertEqual(tokenize("a \\> b"), [("word", "a"), ("word", ">"), ("word", "b")])

    def test_operators_and_fds(self):
        self.assertEqual(tokenize("a 2>&1|b>>c"),
                         [("word", "a"), ("op", ">&"), ("word", "1"), ("op", "|"),
                          ("word", "b"), ("op", ">>"), ("word", "c")])
        self.assertEqual(tokenize("echo 2 > f"),
                         [("word", "echo"), ("word", "2"), ("op", ">"), ("word", "f")])

    def test_quotes_and_escapes(self):
        self.assertEqual(tokenize('a"b c"\'d\' "e\\"f"'),
                         [("word", "ab cd"), ("word", 'e"f')])
        self.assertEqual(tokenize("a \\\nb"), [("word", "a"), ("word", "b")])

    def test_heredoc_bodies_are_data(self):
        # Claude's usual commit: the message is data, whatever it says
        msg = ("git commit -m \"$(cat <<'EOF'\nWrite \"x > src/a.py\" and don't\n"
               "rm -rf src\nEOF\n)\"")
        self.assertEqual(self.w(msg), [])
        self.assertEqual(self.w("cat <<EOF\n> src/a.py\nEOF"), [])

    def test_comments(self):
        self.assertEqual(self.w("ls # > src/a.py"), [])
        self.assertEqual(self.w("ls # note\ntouch a.txt"), [("a.txt", "touch")])
        self.assertEqual(self.w("echo a#b > c.txt"), [("c.txt", ">")])

    def test_unparseable_fails_open(self):
        self.assertEqual(self.w("echo 'unclosed > src/a.py"), [])
        self.assertEqual(self.w('echo "unclosed > src/a.py'), [])
        self.assertEqual(self.w("echo $(( 1 > src/a.py"), [])

    def test_variables_and_substitutions_are_unknown(self):
        self.assertEqual(self.w("echo x > $OUT"), [])
        self.assertEqual(self.w('echo x > "$(git rev-parse --show-toplevel)/a"'), [])
        self.assertEqual(self.w("for f in *.py; do rm $f; done"), [])


if __name__ == "__main__":
    unittest.main()
