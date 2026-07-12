"""Ratchet meta-tests: the two blessed-but-deprecated test idioms may only shrink.

The reappraisal-#19 T12 slot converged two divergent-twin setups the suite had
grown two blessed ways to do (tests-infra findings M7 + M8):

* ``shell_with_temp_dir`` is now a thin alias of ``isolated_shell_with_temp_dir``
  (see ``tests/conftest.py``). New tests should request the isolated fixture
  directly.
* ``capsys`` builtin-output tests contradict CLAUDE.md's "ALWAYS use
  captured_shell for builtin output testing" rule; ``captured_shell`` is the
  blessed idiom.

Neither could be migrated wholesale in one slot (312 fixture references / 82
capsys files at the time). So instead of a big-bang rewrite, this guard freezes
the counts as ceilings that may only ever go DOWN: a new ``shell_with_temp_dir``
user or a new ``capsys`` file pushes the count over its cap and fails the gate;
migrating a call site the other way lowers the count and (once someone tightens
the cap here) locks the gain in. This is the same drift-lock the campaign uses
for its clean-advisory corpus — a ratchet, not a rewrite.

Guard-the-guard: each counter ships a self-test on synthetic input so it cannot
silently regress to counting nothing (the "accidentally green pin" failure mode
the keyword-comparison guard exhibited for its whole life).
"""

import re
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parents[2]          # .../tests
CONFTEST = (TESTS_ROOT / "conftest.py").resolve()          # fixture definition site
THIS_FILE = Path(__file__).resolve()                       # this ratchet module

# ``shell_with_temp_dir`` as a bare identifier — the negative lookbehind rejects
# ``isolated_shell_with_temp_dir`` (the ``_`` before ``shell`` is a word char)
# and the trailing ``\b`` rejects the ``test_shell_with_temp_dir_updates_pwd``
# function-name substring (followed by ``_``).
_SWT_RE = re.compile(r'(?<!\w)shell_with_temp_dir\b')
# ``capsys`` as a bare identifier (rejects ``capsysbinary``).
_CAPSYS_RE = re.compile(r'(?<!\w)capsys\b')

# Ceilings measured at reappraisal-#19 T12 (SHA 6302e73a). DIRECTION: DOWN ONLY.
# When you migrate a shell_with_temp_dir user to isolated_shell_with_temp_dir, or
# a capsys builtin-output test to captured_shell, the live count drops — lower the
# matching cap to that number so the gain is locked in and cannot be spent again.
MAX_SHELL_WITH_TEMP_DIR = 312
MAX_CAPSYS_FILES = 82


def _iter_test_sources():
    """Every ``*.py`` under tests/ except the fixture-definition conftest and
    this guard itself (both mention the idioms as data, not as usage)."""
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        rp = path.resolve()
        if rp == CONFTEST or rp == THIS_FILE:
            continue
        yield path


def _count_swt(text):
    """Number of bare ``shell_with_temp_dir`` references in *text*."""
    return len(_SWT_RE.findall(text))


def _uses_capsys(text):
    """Whether *text* requests the ``capsys`` fixture at all."""
    return bool(_CAPSYS_RE.search(text))


def count_shell_with_temp_dir():
    return sum(_count_swt(p.read_text()) for p in _iter_test_sources())


def count_capsys_files():
    return sum(1 for p in _iter_test_sources() if _uses_capsys(p.read_text()))


# --- the ratchets ----------------------------------------------------------

def test_shell_with_temp_dir_usage_does_not_grow():
    """No new ``shell_with_temp_dir`` users; migrate to isolated fixture instead."""
    n = count_shell_with_temp_dir()
    assert n <= MAX_SHELL_WITH_TEMP_DIR, (
        f"shell_with_temp_dir references rose to {n} (cap {MAX_SHELL_WITH_TEMP_DIR}). "
        "It is a deprecated alias of isolated_shell_with_temp_dir — request the "
        "isolated fixture directly in new tests.")


def test_capsys_usage_does_not_grow():
    """No new ``capsys`` files; CLAUDE.md blesses ``captured_shell`` for output."""
    n = count_capsys_files()
    assert n <= MAX_CAPSYS_FILES, (
        f"capsys test files rose to {n} (cap {MAX_CAPSYS_FILES}). CLAUDE.md's "
        "Output Capture Rules bless captured_shell for builtin/shell output — "
        "use it (or subprocess for external commands) instead of capsys.")


# --- guard-the-guard: counters must actually count -------------------------

def test_counters_are_not_vacuous():
    """The live counts are positive — a counter that silently returns 0 (e.g. a
    broken regex or a wrong root) would make both ratchets vacuously green."""
    assert count_shell_with_temp_dir() > 0
    assert count_capsys_files() > 0


def test_swt_counter_self_test():
    """The shell_with_temp_dir counter counts real refs and rejects decoys."""
    # A param and a body reference both count.
    assert _count_swt(
        "def test_a(shell_with_temp_dir):\n"
        "    shell_with_temp_dir.run_command('x')\n") == 2
    # The isolated_ fixture must NOT be counted (it's the blessed target).
    assert _count_swt("def t(isolated_shell_with_temp_dir): pass") == 0
    # The function-name substring must NOT be counted.
    assert _count_swt("def test_shell_with_temp_dir_updates_pwd(x): pass") == 0


def test_capsys_counter_self_test():
    """The capsys counter flags a real user and rejects decoys."""
    assert _uses_capsys("def test_x(capsys):\n    pass\n") is True
    assert _uses_capsys("def test_x(capsysbinary): pass") is False
    assert _uses_capsys("# a comment mentioning capture, no fixture") is False
