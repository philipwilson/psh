"""Construction purity: building a Shell mutates NOTHING process-global.

Campaign F2's headline pin (continuation finding B + #20 H18, demonstrated
red on base 909a79b9 — tmp/boundary-ledgers/F2-probes/base-battery.txt): on
the base tree, CONSTRUCTING a second shell called libc ``setlocale``,
re-pointed the module-global active locale (silently changing the FIRST
shell's pattern classification), and raised the process recursion limit.
Now every process-global mutation waits for ACTIVATION (implicit on first
execution) under the ProcessLeaseCoordinator, so constructing a second shell
changes nothing observable about the first.

Serial: these tests deliberately touch the process libc locale and the
active-locale slot (under save/restore), which xdist siblings share.
Order-independence: every test snapshots and restores libc locale, the
active-locale slot, and os.environ state it changes, in ``finally`` blocks —
symmetric at entry and exit.
"""

import locale as _pylocale
import os
import signal
import subprocess
import sys

import pytest

from psh.core.locale_service import active_locale, set_process_active_locale
from psh.shell import Shell

pytestmark = pytest.mark.serial

UTF8_NAME = "en_US.UTF-8"


def _utf8_available() -> bool:
    saved = _pylocale.setlocale(_pylocale.LC_CTYPE)
    try:
        _pylocale.setlocale(_pylocale.LC_CTYPE, UTF8_NAME)
        return True
    except _pylocale.Error:
        return False
    finally:
        _pylocale.setlocale(_pylocale.LC_CTYPE, saved)


class _EnvPatch:
    """Set/restore os.environ keys symmetrically (order-independent)."""

    def __init__(self, **values):
        self.values = values
        self.saved = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.saved[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return self

    def __exit__(self, *exc):
        for key, prior in self.saved.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


@pytest.fixture
def locale_guard():
    """Snapshot/restore libc locale + the active-locale slot around a test."""
    saved_ctype = _pylocale.setlocale(_pylocale.LC_CTYPE)
    saved_collate = _pylocale.setlocale(_pylocale.LC_COLLATE)
    saved_active = active_locale()
    try:
        yield
    finally:
        set_process_active_locale(saved_active)
        for category, name in ((_pylocale.LC_CTYPE, saved_ctype),
                               (_pylocale.LC_COLLATE, saved_collate)):
            try:
                _pylocale.setlocale(category, name)
            except _pylocale.Error:
                pass


def test_second_shell_construction_changes_nothing_utf8_first(locale_guard):
    """The C-locale-shell-vs-UTF-8-shell probe (red on base).

    A UTF-8 shell classifies ``é`` as alpha; CONSTRUCTING a second, C-locale
    shell must not change the libc locale, the active-locale slot, or the
    first shell's classification.
    """
    if not _utf8_available():
        pytest.skip(f"{UTF8_NAME} unavailable on this host")
    with _EnvPatch(LC_ALL=UTF8_NAME):
        s1 = Shell(norc=True)
    try:
        assert s1.run_command('[[ é == [[:alpha:]] ]]') == 0
        libc_before = _pylocale.setlocale(_pylocale.LC_CTYPE)
        active_before = active_locale()
        with _EnvPatch(LC_ALL="C"):
            s2 = Shell(norc=True)                    # CONSTRUCTION ONLY
        try:
            assert _pylocale.setlocale(_pylocale.LC_CTYPE) == libc_before
            assert active_locale() is active_before
            # The first shell's pattern behavior is untouched (base: rc 1).
            assert s1.run_command('[[ é == [[:alpha:]] ]]') == 0
        finally:
            s2.close()
    finally:
        s1.close()


def test_second_shell_construction_changes_nothing_c_first(locale_guard):
    """Reverse direction (red on base): constructing a UTF-8 shell must not
    call setlocale or flip the C shell's classification."""
    if not _utf8_available():
        pytest.skip(f"{UTF8_NAME} unavailable on this host")
    with _EnvPatch(LC_ALL="C"):
        s1 = Shell(norc=True)
    try:
        assert s1.run_command('[[ é == [[:alpha:]] ]]') == 1
        libc_before = _pylocale.setlocale(_pylocale.LC_CTYPE)
        with _EnvPatch(LC_ALL=UTF8_NAME):
            s2 = Shell(norc=True)                    # CONSTRUCTION ONLY
        try:
            assert _pylocale.setlocale(_pylocale.LC_CTYPE) == libc_before
            assert s1.run_command('[[ é == [[:alpha:]] ]]') == 1
        finally:
            s2.close()
    finally:
        s1.close()


def test_utf8_locale_applies_at_activation(locale_guard):
    """The deferral is not a lobotomy: the FIRST EXECUTION of a UTF-8 shell
    applies the locale (under the LOCALE lease) and classification works —
    and close() hands the host its libc locale back."""
    if not _utf8_available():
        pytest.skip(f"{UTF8_NAME} unavailable on this host")
    host_ctype = _pylocale.setlocale(_pylocale.LC_CTYPE)
    with _EnvPatch(LC_ALL=UTF8_NAME):
        s1 = Shell(norc=True)
    try:
        assert s1.run_command('[[ é == [[:alpha:]] ]]') == 0
        assert _pylocale.setlocale(_pylocale.LC_CTYPE) == UTF8_NAME
    finally:
        s1.close()
    # Deactivation restored the hosting process's libc locale (the LOCALE
    # component lease's whole point — an embedded shell leaves no residue).
    assert _pylocale.setlocale(_pylocale.LC_CTYPE) == host_ctype


def test_construction_installs_no_signal_handlers():
    """Control (green on base since F1): handler installs are entry-point
    and trap-time only, never construction."""
    watched = (signal.SIGINT, signal.SIGTERM, signal.SIGCHLD,
               signal.SIGUSR1, signal.SIGTSTP)
    before = {sig: signal.getsignal(sig) for sig in watched}
    shell = Shell(norc=True)
    try:
        after = {sig: signal.getsignal(sig) for sig in watched}
        assert after == before
    finally:
        shell.close()


def test_construction_does_not_raise_recursion_limit():
    """Red on base: Shell() raised the limit 1000 -> 40000 at construction.

    Needs a FRESH interpreter (the suite's own activations already raised
    this process's limit), so it runs as a subprocess pin: construction
    leaves the limit alone; the first execution raises it.
    """
    code = (
        "import sys\n"
        "base = sys.getrecursionlimit()\n"
        "from psh.shell import Shell\n"
        "s = Shell(norc=True)\n"
        "assert sys.getrecursionlimit() == base, 'construction raised the limit'\n"
        "s.run_command('true')\n"
        "from psh.core.process_lease import RECURSION_LIMIT\n"
        "assert sys.getrecursionlimit() >= RECURSION_LIMIT, 'activation must raise it'\n"
        "print('PURE')\n"
    )
    tree = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    env = dict(os.environ)
    env['PYTHONPATH'] = tree
    result = subprocess.run([sys.executable, '-c', code], cwd=tree, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert 'PURE' in result.stdout
