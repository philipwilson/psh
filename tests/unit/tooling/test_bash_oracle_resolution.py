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

**Campaign Q2 (§13, "Bash-oracle bypasses") — the two evasion forms the E2
docstring flagged are now caught:**

* a ``shell=True`` command STRING whose first whitespace token is ``bash``
  (``subprocess.run('bash -c ...', shell=True)`` — arg0 is a multi-word
  constant, not exactly ``'bash'``), and
* ``os.system('bash ...')`` / ``os.popen('bash ...')``.

Verified at Q2 adoption that NO current test uses either form (tree grep for
``shell=True`` with bash / ``os.system`` / ``os.popen`` — zero hits), so closing
the gap keeps the tree green while removing the completeness caveat.

Q2 nit-1 hardening: the ``shell=1`` truthy-int form (not just ``shell=True``) is
now caught. Declared OUT OF SCOPE (no live instance): an ABSOLUTE bash path NOT
in the four-entry ``HARDCODED_BASH_PATHS`` set (an exotic install prefix like
``/opt/local/bin/bash``) — the set cannot enumerate every prefix, and the
bare-``bash`` command-word rules catch the common case; if one appears, add the
path to ``HARDCODED_BASH_PATHS``.

Residual known-unflagged forms (documented, not currently used): an oracle
assembled by string concatenation/format at runtime (``f"{sh} -c ..."``), or
launched via a helper that hides the literal. These are dynamic, not static
literals; if one appears, extend ``find_oracle_offenses`` rather than
allowlisting it.

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


def _cmd_string_first_token_is_bash(node):
    """True if *node* is a string literal whose first whitespace token is
    exactly ``bash`` (so ``"bash -c ..."`` and ``"bash"`` match, but
    ``"rebash"`` / ``"/bin/bash x"`` / script text like ``"exec bash"`` do
    not — the command word must LEAD)."""
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        return False
    toks = node.value.split()
    return bool(toks) and toks[0] == _BARE


def _call_has_shell_true(node):
    # shell=True OR the truthy shell=1 form (Q2 nit-1 — evasion via an int).
    for kw in node.keywords:
        if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
            v = kw.value.value
            if v is True or (isinstance(v, int) and not isinstance(v, bool) and v != 0):
                return True
    return False


def _callee_attr(node):
    """The called attribute name (``run`` for ``subprocess.run(...)``,
    ``system`` for ``os.system(...)``), or '' for a bare-name/other call."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def find_oracle_offenses(src):
    """Return [(lineno, kind, detail)] oracle offenses in Python source."""
    tree = ast.parse(src)
    offenses = []

    def const_is(node, value):
        return isinstance(node, ast.Constant) and node.value == value

    for node in ast.walk(tree):
        # os.system('bash ...') / os.popen('bash ...') — a shell-string oracle.
        if isinstance(node, ast.Call) and _callee_attr(node) in ("system", "popen") \
                and node.args and _cmd_string_first_token_is_bash(node.args[0]):
            offenses.append((node.args[0].lineno, "os-system-bash-string",
                             node.args[0].value))
        # subprocess.<run|Popen|call|check_output|check_call>('bash ...',
        # shell=True) — a multi-word command string the argv-head rule misses.
        if isinstance(node, ast.Call) and _call_has_shell_true(node) \
                and node.args and _cmd_string_first_token_is_bash(node.args[0]) \
                and not const_is(node.args[0], _BARE):
            offenses.append((node.args[0].lineno, "shell-true-bash-string",
                             node.args[0].value))
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


def test_guard_flags_shell_true_command_string():
    """Q2: a multi-word 'bash -c ...' string with shell=True is caught (the
    argv-head/arg0 rules miss it because arg0 is not exactly 'bash')."""
    snippet = (
        "import subprocess\n"
        "subprocess.run('" + _BARE + " -c \"echo hi\"', shell=True)\n"
    )
    kinds = {k for _, k, _ in find_oracle_offenses(snippet)}
    assert "shell-true-bash-string" in kinds


def test_guard_flags_shell_one_truthy_int():
    """Q2 nit-1: shell=1 (truthy int, not shell=True) is caught."""
    snippet = (
        "import subprocess\n"
        "subprocess.run('" + _BARE + " -c true', shell=1)\n"
    )
    kinds = {k for _, k, _ in find_oracle_offenses(snippet)}
    assert "shell-true-bash-string" in kinds


def test_guard_flags_os_system_bash_string():
    """Q2: os.system('bash ...') / os.popen('bash ...') is caught."""
    snip1 = "import os\nos.system('" + _BARE + " -c true')\n"
    snip2 = "import os\nos.popen('" + _BARE + " -lc \"echo\"')\n"
    assert "os-system-bash-string" in {k for _, k, _ in find_oracle_offenses(snip1)}
    assert "os-system-bash-string" in {k for _, k, _ in find_oracle_offenses(snip2)}


def test_guard_ignores_shell_true_non_bash_and_leading_path():
    """shell=True with a NON-bash command, and a command whose first token is a
    PATH (not the bare word 'bash'), are not flagged by the new rules — the
    command WORD must lead, and only the bare-word oracle counts here."""
    snippet = (
        "import subprocess, os\n"
        "subprocess.run('sh -c true', shell=True)\n"          # not bash
        "subprocess.run('re" + _BARE + " -c x', shell=True)\n"  # 'rebash', not bash
        "os.system('echo " + _BARE + "')\n"                     # bash not the command word
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
