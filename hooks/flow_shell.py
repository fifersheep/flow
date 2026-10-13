"""flow_shell: the files a shell command would write, read off the command.

The validator's Bash check. It reads a command the way a reviewer would —
redirects, tee, sed -i / perl -i, mv/cp/rm/touch/mkdir/ln, dd of=, patch,
git apply / restore / checkout -- <path>, an interpreter one-liner that opens a
literal path for writing — and lists the paths those would change, resolved
from the command's own cwd (a `cd X &&` moves it).

It's a heuristic, not a sandbox. A path in a variable, a script file, xargs,
find -exec or a build tool writes where this can't see; and a command it can't
parse yields nothing, so the hook allows it, as the validator does on any
error of its own.
"""
import os
import re
from pathlib import Path

OPERATORS = sorted(["&>>", "<<<", "&&", "||", ";;", "|&", ">>", ">|", "&>",
                    ">&", "<&", "<<", "<>", ";", "&", "|", "(", ")", "<", ">",
                    "\n"], key=len, reverse=True)
OP_CHARS = set("".join(OPERATORS))
SEPARATORS = {";", "&", "&&", "||", "|", "|&", ";;", "(", ")", "\n"}
WRITE_OPS = {">", ">>", ">|", "&>", "&>>", "<>"}
# `(?<!<)<<(?!<)`: a heredoc, not a <<< here-string
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z_][\w.-]*)\2")
WRAPPERS = {"sudo", "env", "command", "builtin", "exec", "nohup", "time", "nice"}
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{"}
SHELLS = {"sh", "bash", "zsh", "dash"}
INTERPRETER_RE = re.compile(r"(python[\d.]*|node|ruby)$")
# literal paths an interpreter one-liner opens for writing
INTERPRETER_WRITES = [re.compile(p) for p in (
    r"""open\(\s*(['"])(?P<path>[^'"]+)\1\s*,\s*(?:mode\s*=\s*)?['"][rbt]*[wax+]""",
    r"""Path\(\s*(['"])(?P<path>[^'"]+)\1\s*\)\s*\.\s*write_(?:text|bytes)\(""",
    r"""(?:writeFile|appendFile)(?:Sync)?\(\s*(['"`])(?P<path>[^'"`]+)\1""",
    r"""File\.write\(\s*(['"])(?P<path>[^'"]+)\1""",
)]
GIT_APPLY_READONLY = {"--check", "--stat", "--numstat", "--summary"}


def writes(command, cwd):
    """[(path, how)] for each file the command would write, each path
    resolved; [] for a command that can't be parsed."""
    try:
        text, bodies = strip_heredocs(command)
        commands = list(simple_commands(tokenize(text)))
    except (ValueError, IndexError):
        return []
    out = []
    for words, redirects in commands:
        words = unwrap(words)
        for op, target in redirects:
            if op in WRITE_OPS or (op == ">&" and not target.isdigit()
                                   and target != "-"):
                out.append((resolve(target, cwd), op))
        if words[:1] in (["cd"], ["pushd"]):
            if len(words) == 1:
                cwd = Path.home()
            else:  # `cd -` goes back somewhere unknown, so later paths are too
                cwd = resolve(words[1], cwd) if words[1] != "-" else None
        elif words:
            out += command_writes(words, redirects, cwd, bodies)
    return [(p, how) for p, how in out if p is not None]


def strip_heredocs(command):
    """The command without its heredoc bodies, plus the bodies by delimiter.
    A body is data, not shell: a `>` or a stray quote in one must not count.
    The usual case is a commit message passed as "$(cat <<'EOF' … EOF)"."""
    lines, out, bodies, i = command.split("\n"), [], {}, 0
    while i < len(lines):
        out.append(lines[i])
        i += 1
        for dash, _, delim in HEREDOC_RE.findall(out[-1]):
            body = []
            while i < len(lines) and (lines[i].lstrip("\t") if dash
                                      else lines[i]) != delim:
                body.append(lines[i])
                i += 1
            i += 1  # the delimiter line
            bodies.setdefault(delim, []).append("\n".join(body))
    return "\n".join(out), bodies


def tokenize(text):
    """[("word", …) | ("op", …)], quotes removed. Not shlex: shlex hands back
    a quoted ">" and a real redirect as the same string, and `grep ">" a.py`
    must not read as a write to a.py. Raises on an unclosed quote."""
    tokens, word, i = [], None, 0

    def flush():
        nonlocal word
        if word is not None:
            tokens.append(("word", word))
        word = None

    while i < len(text):
        c = text[i]
        if c == "\\":
            if text[i + 1:i + 2] != "\n":  # backslash-newline joins lines
                word = (word or "") + text[i + 1:i + 2]
            i += 2
        elif c == "'":
            end = text.index("'", i + 1)
            word, i = (word or "") + text[i + 1:end], end + 1
        elif c == '"':
            j, s = i + 1, ""
            while text[j] != '"':
                if text[j] == "\\" and text[j + 1] in '\\"$`\n':
                    j += 1
                s, j = s + text[j], j + 1
            word, i = (word or "") + s, j + 1
        elif text.startswith("$((", i) or (word is None
                                          and text.startswith("((", i)):
            end = text.index("))", i)  # arithmetic: its < and > compare
            word, i = (word or "") + text[i:end + 2], end + 2
        elif c in " \t\r":
            flush()
            i += 1
        elif c == "#" and word is None:
            # a comment, up to (not including) the newline that ends it
            i = text.find("\n", i) if "\n" in text[i:] else len(text)
        elif c in OP_CHARS:
            if c in "<>" and word and word.isdigit():
                word = None  # the 2 of 2>: a file descriptor, not a word
            flush()
            op = next(o for o in OPERATORS if text.startswith(o, i))
            tokens.append(("op", op))
            i += len(op)
        else:
            word, i = (word or "") + c, i + 1
    flush()
    return tokens


def simple_commands(tokens):
    """(words, redirects) per simple command, split at ; && || | & ( ) and
    newlines; redirects are (op, word) pairs, reads and writes both."""
    words, redirects, i = [], [], 0
    while i < len(tokens):
        kind, val = tokens[i]
        if kind == "word":
            words.append(val)
        elif val in SEPARATORS:
            yield words, redirects
            words, redirects = [], []
        elif "[[" in words and "]]" not in words:
            words.append(val)  # [[ a > b ]] compares strings
        elif i + 1 < len(tokens) and tokens[i + 1][0] == "word":
            redirects.append((val, tokens[i + 1][1]))
            i += 1
        i += 1
    yield words, redirects


def unwrap(words):
    """The command under leading assignments, keywords and wrappers:
    `do FOO=1 sudo rm x` is rm. A wrapper's own options go with it."""
    words = list(words)
    while words and (words[0] in KEYWORDS
                     or re.match(r"[A-Za-z_]\w*=", words[0])
                     or os.path.basename(words[0]) in WRAPPERS):
        if os.path.basename(words.pop(0)) in WRAPPERS:
            while words and words[0].startswith("-"):
                words.pop(0)
    if words:
        words[0] = os.path.basename(words[0])
    return words


def resolve(path, cwd):
    """path as the shell would open it from cwd; None when that can't be known
    from the text (a variable, a substitution, a cwd lost to `cd $X`)."""
    if not path or "$" in path or "`" in path:
        return None
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        if cwd is None:
            return None
        path = os.path.join(cwd, path)
    return Path(path).resolve()


def operands(args, takes_value=()):
    """The non-option arguments, skipping the values of options that take one."""
    out, i, done = [], 0, False
    while i < len(args):
        a = args[i]
        if done or not a.startswith("-") or a == "-":
            out.append(a)
        elif a == "--":
            done = True
        elif a in takes_value:
            i += 1
        i += 1
    return out


def target_dir(args):
    """The -t DIR / --target-directory=DIR of cp, mv and ln, if given."""
    for i, a in enumerate(args):
        if a == "-t" and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--target-directory="):
            return a.partition("=")[2]
    return None


def command_writes(words, redirects, cwd, bodies):
    """The files a simple command writes by what it is, not by redirection."""
    name, args = words[0], words[1:]
    at = lambda paths, how=name: [(resolve(p, cwd), how) for p in paths]
    if name in ("rm", "rmdir", "unlink", "tee"):
        return at(operands(args))
    if name == "touch":
        return at(operands(args, {"-r", "-t", "-d"}))
    if name == "truncate":
        return at(operands(args, {"-s", "-r"}))
    if name == "mkdir":  # mkdir -p of a folder that's already there is a no-op
        return [(p, how) for p, how in at(operands(args, {"-m"}))
                if p is None or not p.is_dir()]
    if name in ("mv", "cp", "ln"):
        files, into = operands(args, {"-t", "-S", "--suffix"}), target_dir(args)
        if name == "mv":  # a move changes both ends
            return at(files + ([into] if into else []))
        if into:
            return at([into])
        if name == "ln" and len(files) == 1:
            return at([os.path.basename(files[0].rstrip("/"))])
        return at(files[-1:] if len(files) > 1 else [])
    if name == "dd":
        return at([a[3:] for a in args if a.startswith("of=")])
    if name == "sed":
        return at(sed_files(args), "sed -i")
    if name == "perl":
        return at(perl_files(args), "perl -i")
    if name == "patch":
        return at(patch_targets(args, cwd))
    if name == "git":
        return git_writes(args, cwd)
    if name in SHELLS or name == "eval":
        if name == "eval":
            scripts = [" ".join(args)]
        else:  # bash -c '…', bash -lc '…', or a script on stdin
            scripts = [args[i + 1] for i, a in enumerate(args[:-1])
                       if re.match(r"-[a-z]*c[a-z]*$", a)][:1]
            scripts = scripts or heredocs(redirects, bodies)
        return [w for s in scripts for w in writes(s, cwd)]
    if INTERPRETER_RE.match(name):
        code = [args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-c", "-e")]
        return at([m.group("path") for s in code + heredocs(redirects, bodies)
                   for rx in INTERPRETER_WRITES for m in rx.finditer(s)])
    return []


def heredocs(redirects, bodies):
    """The text a command reads on stdin from a heredoc or here-string."""
    return ([b for op, d in redirects if op == "<<" for b in bodies.get(d, [])]
            + [w for op, w in redirects if op == "<<<"])


def sed_files(args):
    """The files `sed -i` edits in place; [] without -i. -i[SUFFIX] is GNU,
    `-i ''` is BSD; -e/-f mean the first operand is a file, not the script."""
    in_place, scripted, files, i = False, False, [], 0
    while i < len(args):
        a = args[i]
        if a in ("-e", "-f", "--expression", "--file"):
            scripted, i = True, i + 1
        elif a.startswith(("--expression=", "--file=")):
            scripted = True
        elif a.startswith("--in-place"):
            in_place = True
        elif a.startswith("-") and len(a) > 1 and not a.startswith("--"):
            flags = a[1:].split("i")[0]
            if "i" in a[1:]:
                in_place = True
                if a == "-i" and i + 1 < len(args) and args[i + 1] == "":
                    i += 1
            if flags[-1:] in ("e", "f"):
                scripted, i = True, i + 1
        else:
            files.append(a)
        i += 1
    return (files if scripted else files[1:]) if in_place else []


def perl_files(args):
    """The files `perl -i` edits in place: -pi -e '…' a.txt, -i.bak, -pie."""
    in_place, scripted, files, i = False, False, [], 0
    while i < len(args):
        a = args[i]
        if a.startswith("-") and not a.startswith("--") and len(a) > 1:
            for j, letter in enumerate(a[1:]):
                if letter == "i":
                    in_place = True
                    break  # the rest is a backup suffix
                if letter in "eE":  # the code is the rest, or the next word
                    scripted, i = True, i + (0 if a[j + 2:] else 1)
                    break
                if letter in "IMmdDx0l":
                    break  # the rest is this option's value
        else:
            files.append(a)
        i += 1
    return (files if scripted else files[1:]) if in_place else []


def patch_targets(args, cwd):
    """What patch writes: -o FILE, a named original, or else the tree it runs
    in (-d DIR, or cwd) — its real targets are inside the patch."""
    if any(a in ("--dry-run", "-C", "--check") for a in args):
        return []
    for i, a in enumerate(args):
        if a in ("-o", "--output") and i + 1 < len(args):
            return [args[i + 1]]
        if a.startswith("--output="):
            return [a.partition("=")[2]]
    files = operands(args, {"-p", "-i", "-d", "-D", "-o", "-r", "-B", "-F",
                            "-V", "-z", "--input", "--directory"})
    if files:
        return files[:1]
    for i, a in enumerate(args):
        if a in ("-d", "--directory") and i + 1 < len(args):
            return [args[i + 1]]
    return ["."]


def git_writes(args, cwd):
    """git apply, git restore, and git checkout of paths. Branch switches,
    commits, worktrees and the rest of git are left alone."""
    args = list(args)
    while args and args[0].startswith("-"):
        opt = args.pop(0)
        if opt == "-C" and args:
            cwd = resolve(args.pop(0), cwd)
        elif opt in ("-c", "--git-dir", "--work-tree", "--namespace") and args:
            args.pop(0)
    if not args:
        return []
    sub, rest = args[0], args[1:]
    at = lambda paths: [(resolve(p, cwd), f"git {sub}") for p in paths]
    if sub == "apply":
        if GIT_APPLY_READONLY & set(rest) and "--apply" not in rest:
            return []
        return at(["."])  # the patch names the files; the tree is the target
    if sub == "restore":
        staged = {"--staged", "-S"} & set(rest)
        if staged and not {"--worktree", "-W"} & set(rest):
            return []  # the index only
        return at(operands(rest, {"-s", "--source"}))
    if sub == "checkout":
        if "--" in rest:
            return at(rest[rest.index("--") + 1:])
        if {"-b", "-B", "--orphan"} & set(rest):
            return []
        # `git checkout main` switches branch; `git checkout a.py` (a file
        # that's there) puts the file back
        return [(p, how) for p, how in at(operands(rest))
                if p is not None and p.exists()]
    return []
