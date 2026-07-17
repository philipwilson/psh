"""Ratchet: every bash subprocess oracle goes through resolve_bash() (E2).

``tests/harness/shell_oracle.py#resolve_bash`` is the ONE bash-resolution
ladder (BASH_PATH -> Homebrew -> PATH, version-recorded). Before this guard,
~40 test files re-derived the oracle: some hardcoded ``/opt/homebrew/bin/bash``
(FileNotFoundError on any non-Homebrew host — the Linux nightly collected them
with no skip), some ran a bare ``bash`` (stock macOS /bin/bash 3.2 whenever
Homebrew isn't first on PATH; ignores BASH_PATH), and one re-implemented the
ladder inline. This scanner flags, in every scanned file:

* any string literal EXACTLY equal to a known bash path
  (``/bin/bash``, ``/usr/bin/bash``, ``/opt/homebrew/bin/bash``,
  ``/usr/local/bin/bash``) — hardcoded oracle;
* a bare ``'bash'`` literal at an ORACLE position — head of a list/tuple
  (argv construction) or first argument of a call
  (``subprocess.run("bash" ...)``, ``shutil.which("bash")``);
* use of the ``BASH_PATH`` environment variable outside the resolver — an
  inline re-implementation of the ladder.

``'bash'`` appearing elsewhere (inside shell-script text, as a path component
like ``tmp_path / 'bash'``, in prose) is not an oracle and is not flagged.

The allowlist is SHRINKING: it may lose entries, never gain them without the
justification being recorded here.
"""
import ast
import os

import pytest

TESTS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

# Exact literals that mean "I hardcoded the oracle path".
HARDCODED_BASH_PATHS = frozenset({
    "/opt/homebrew/bin" + "/bash",
    "/usr/local/bin" + "/bash",
    "/bin" + "/bash",
    "/usr/bin" + "/bash",
})

_BARE = "ba" + "sh"          # obfuscated so this guard never flags itself
_LADDER_ENV = "BASH" + "_PATH"

# Files exempt from the ratchet, each with a reason. SHRINKING allowlist:
# removing entries is always fine; adding one requires a recorded justification.
ALLOWLIST = {
    # THE resolver: owns the ladder, the hardcoded Homebrew candidates, the
    # BASH_PATH env check, and the final PATH `which` fallback by design.
    "harness/shell_oracle.py",
}


def iter_scanned_files():
    """Every Python file under tests/ that could execute an oracle."""
    for dirpath, dirnames, filenames in os.walk(TESTS_ROOT):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def find_oracle_offenses(src):
    """Return [(lineno, kind, detail)] oracle offenses in Python source."""
    tree = ast.parse(src)
    offenses = []

    def const_is(node, value):
        return isinstance(node, ast.Constant) and node.value == value

    for node in ast.walk(tree):
        # Hardcoded oracle path literal, anywhere.
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value in HARDCODED_BASH_PATHS:
            offenses.append((node.lineno, "hardcoded-bash-path", node.value))
        # Bare 'bash' as argv head.
        if isinstance(node, (ast.List, ast.Tuple)) and node.elts \
                and const_is(node.elts[0], _BARE):
            offenses.append((node.elts[0].lineno, "bare-bash-argv", _BARE))
        # Bare 'bash' as a call's first argument (which('bash'),
        # subprocess.run('bash', shell=True), Popen('bash ...')).
        if isinstance(node, ast.Call) and node.args \
                and const_is(node.args[0], _BARE):
            offenses.append((node.args[0].lineno, "bare-bash-call-arg", _BARE))
        # BASH_PATH env access = inline ladder re-implementation.
        if isinstance(node, ast.Subscript) and const_is(node.slice, _LADDER_ENV):
            offenses.append((node.lineno, "inline-ladder-env", _LADDER_ENV))
        if isinstance(node, ast.Call) and any(
                const_is(a, _LADDER_ENV) for a in node.args):
            offenses.append((node.lineno, "inline-ladder-env", _LADDER_ENV))
        if isinstance(node, ast.Compare) and (
                const_is(node.left, _LADDER_ENV)
                or any(const_is(c, _LADDER_ENV) for c in node.comparators)):
            offenses.append((node.lineno, "inline-ladder-env", _LADDER_ENV))
    return offenses


def test_no_bash_oracle_outside_resolver():
    """No scanned file resolves a bash oracle outside resolve_bash()."""
    problems = []
    for path in iter_scanned_files():
        rel = os.path.relpath(path, TESTS_ROOT)
        if rel in ALLOWLIST or os.path.abspath(path) == os.path.abspath(__file__):
            continue
        with open(path, encoding="utf-8") as f:
            src = f.read()
        for lineno, kind, detail in find_oracle_offenses(src):
            problems.append(f"tests/{rel}:{lineno}: {kind}: {detail!r}")
    assert not problems, (
        "bash oracle resolved outside tests/harness/shell_oracle.py"
        ".resolve_bash() — route through the resolver (or, with a recorded "
        "justification, extend the ALLOWLIST):\n  " + "\n  ".join(problems))


def test_allowlist_entries_exist():
    """A stale allowlist entry (file removed/renamed) must be pruned."""
    for rel in ALLOWLIST:
        assert os.path.isfile(os.path.join(TESTS_ROOT, rel)), (
            f"ALLOWLIST entry {rel!r} does not exist — prune it")


# ---------------------------------------------------------------------------
# Guard-the-guard: synthetic offenders must fire; blessed usage must not.
# ---------------------------------------------------------------------------

def test_guard_flags_bare_bash_subprocess():
    snippet = (
        "import subprocess\n"
        "subprocess.run(['" + _BARE + "', '-c', 'echo hi'])\n"
    )
    kinds = {k for _, k, _ in find_oracle_offenses(snippet)}
    assert "bare-bash-argv" in kinds


def test_guard_flags_bare_bash_call_arg():
    snippet = (
        "import shutil\n"
        "shutil.which('" + _BARE + "')\n"
    )
    kinds = {k for _, k, _ in find_oracle_offenses(snippet)}
    assert "bare-bash-call-arg" in kinds


def test_guard_flags_hardcoded_path():
    snippet = "BASH = '/opt/homebrew/bin/" + _BARE + "'\n"
    kinds = {k for _, k, _ in find_oracle_offenses(snippet)}
    assert "hardcoded-bash-path" in kinds


def test_guard_flags_inline_ladder():
    snippet = (
        "import os\n"
        "p = os.environ['" + _LADDER_ENV + "']\n"
        "q = os.environ.get('" + _LADDER_ENV + "')\n"
    )
    kinds = [k for _, k, _ in find_oracle_offenses(snippet)]
    assert kinds.count("inline-ladder-env") == 2


def test_guard_accepts_resolver_usage():
    snippet = (
        "from shell_oracle import resolve_bash\n"
        "BASH = resolve_bash().path\n"
        "import subprocess\n"
        "subprocess.run([BASH, '-c', 'echo hi'])\n"
    )
    assert find_oracle_offenses(snippet) == []


def test_guard_ignores_non_oracle_bash_strings():
    """'bash' as script text or a path component is not an oracle."""
    snippet = (
        "d = tmp_path / '" + _BARE + "'\n"
        "cmd = 'exec " + _BARE + " -c true'\n"
        "label = '" + _BARE + "'\n"
    )
    assert find_oracle_offenses(snippet) == []


def test_scanner_scope_includes_known_tree():
    """The walk really covers the trees the offenders lived in."""
    rels = {os.path.relpath(p, TESTS_ROOT) for p in iter_scanned_files()}
    for probe in (
            "conformance/conformance_framework.py",
            "behavioral/test_golden_behavior.py",
            "harness/shell_oracle.py",
            "integration/redirection/test_process_sub_closed_fds.py",
            "unit/tooling/test_bash_oracle_resolution.py",
    ):
        assert probe in rels, f"scanner scope lost {probe}"


@pytest.mark.parametrize("rel", sorted(ALLOWLIST))
def test_allowlisted_files_still_needed(rel):
    """An allowlisted file that no longer contains any oracle pattern should
    leave the allowlist (shrinking ratchet)."""
    path = os.path.join(TESTS_ROOT, rel)
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert find_oracle_offenses(src), (
        f"{rel} no longer needs its ALLOWLIST entry — remove it")
