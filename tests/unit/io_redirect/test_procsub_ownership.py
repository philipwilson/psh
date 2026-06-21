"""Process-substitution fd ownership lives in the resource/plan, not the
dispatch sites (reassessment 2026-06-20, #3).

The redirect backends decide one of two things for a redirect-target process
substitution's parent fd, and both are owned by RedirectPlan /
ProcessSubstitutionResource — never by manual ``active_fds`` poking in a
dispatch site:

  * close it after applying the redirect (``close_procsub`` →
    ``close_parent_fd_for_redirect``), used by the external/permanent paths; or
  * hand it to the enclosing ``process_sub_scope()`` for deferred close
    (``hand_procsub_to_scope`` → ``hand_off_to_scope``), used by the in-process
    builtin path and word expansion, because the consumer reads ``/dev/fd/N``.

Behavioral fd-leak coverage lives in
tests/integration/redirection/test_process_sub_cleanup.py; this file pins the
ownership refactor.
"""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_manager_does_not_poke_active_fds():
    """The builtin redirect setup must not reach into the handler's active_fds
    directly — it goes through plan.hand_procsub_to_scope()."""
    manager_src = (PROJECT_ROOT / "psh/io_redirect/manager.py").read_text()
    assert "active_fds" not in manager_src, (
        "manager.py manipulates active_fds directly; transfer/close ownership "
        "belongs to RedirectPlan / ProcessSubstitutionResource"
    )


def test_active_fds_only_appended_by_the_resource():
    """The single owner of `active_fds.append(...)` is the resource's
    hand_off_to_scope; the scope's cleanup only reads/clears it."""
    src = (PROJECT_ROOT / "psh/io_redirect/process_sub.py").read_text()
    appends = src.count("active_fds.append(")
    assert appends == 1, (
        f"expected exactly one active_fds.append (in hand_off_to_scope); "
        f"found {appends}"
    )


def test_redirect_plan_owns_both_transfer_and_close():
    from psh.io_redirect.planner import RedirectPlan
    assert hasattr(RedirectPlan, "close_procsub")
    assert hasattr(RedirectPlan, "hand_procsub_to_scope")


def _lowest_free_fd(script):
    """Run *script*, then probe the lowest free fd in the shell.

    The probe child inherits psh's open fds (substitution fds have CLOEXEC
    cleared), so its first os.open() reveals the lowest still-free slot — a
    leaked parent fd would push it up. Same technique as
    test_process_sub_cleanup.py.
    """
    probe = (f'"{sys.executable}" -c '
             '"import os; print(os.open(\'/dev/null\', os.O_RDONLY))"')
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script + "; " + probe],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return int(result.stdout.strip())


def test_builtin_procsub_read_does_not_leak_fds():
    """A builtin reading `< <(cmd)` in a loop must not accumulate parent fds —
    the in-process builtin's read end is handed to the scope and closed there."""
    one = _lowest_free_fd('read x < <(echo hi)')
    many = _lowest_free_fd(
        'for i in 1 2 3 4 5 6 7 8; do read x < <(echo hi); done')
    assert many <= one, (
        f"builtin <(...) leaked fds across iterations: single={one} loop={many}")


@pytest.mark.parametrize("script,expected", [
    ("read x < <(echo hello); echo $x", "hello"),
    ("while read l; do echo [$l]; done < <(printf 'a\\nb\\n')", "[a]\n[b]"),
])
def test_builtin_procsub_still_works(script, expected):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
