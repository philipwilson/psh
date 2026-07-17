"""Pins for the per-test process-state snapshot/restore fixture (E3).

``tests/conftest.py#_restore_signal_dispositions_and_std_fds`` must roll back
per-test drift in process signal dispositions, fds 0/1/2, and the
PROCESS-GLOBAL libc locale (``LocaleService._try_setlocale`` calls
``setlocale`` for non-C profiles; a later C-profile shell never calls
``setlocale`` at all, so a leaked worker locale would persist indefinitely).

Design constraint — ORDER INDEPENDENCE: these pins must hold under
``run_tests.py --shuffle-seed`` (the Phase-E identical-census exit runs the
suite under three seeds). The first version of this file used
pollute-then-observe pairs that assumed definition order and failed the very
first seeded exit run (seed 101 reordered a pair). The symmetric design below
has no ordering assumption: EVERY test first asserts the state at entry equals
the module-import baseline (proving the fixture restored whatever any earlier
test — in this file or elsewhere — polluted), then pollutes the state itself
and proves the pollution took. Whichever test of a kind runs second therefore
observes the fixture's restore of the first; under any order, and even in
isolation, no test can pass while the fixture is broken for its entry state.

Baselines are captured at module import, which happens at collection — before
any test in the serial phase has run — so the import-time state IS the
pristine state the fixture keeps restoring to. The module stays ``serial`` so
xdist cannot give each test of a pair its own worker (where each would only
ever see its own import-time baseline and the restore would go unobserved).

Red-on-base: with the fixture's locale arm absent (the pre-bounce conftest),
the locale entry assertions fail — transcript archived in
``tmp/boundary-ledgers/E23-probes/locale-restore-red-on-base.txt``. The
order-dependence failure itself is archived in
``tmp/boundary-ledgers/E/exit-seed101-red.txt`` (seed 101 at v0.726.0).
"""
import locale
import os
import signal

import pytest

pytestmark = pytest.mark.serial

# A non-C locale available on the gate host (macOS) and the Linux nightly.
_CANDIDATE_LOCALES = ("en_US.UTF-8", "C.UTF-8", "en_US.utf8")


def _settable_non_c_locale():
    saved = locale.setlocale(locale.LC_ALL)
    try:
        for name in _CANDIDATE_LOCALES:
            try:
                locale.setlocale(locale.LC_ALL, name)
                return name
            except locale.Error:
                continue
        return None
    finally:
        locale.setlocale(locale.LC_ALL, saved)


_NON_C = _settable_non_c_locale()
_BASELINE_LOCALE = locale.setlocale(locale.LC_ALL)
_BASELINE_SIGUSR1 = signal.getsignal(signal.SIGUSR1)
_BASELINE_FD2_ID = (os.fstat(2).st_dev, os.fstat(2).st_ino)


def _assert_entry_locale_pristine():
    assert locale.setlocale(locale.LC_ALL) == _BASELINE_LOCALE, (
        "fixture failed to restore libc locale before this test"
    )


def _pollute_locale():
    locale.setlocale(locale.LC_ALL, _NON_C)
    assert locale.setlocale(locale.LC_ALL) != _BASELINE_LOCALE


@pytest.mark.skipif(_NON_C is None, reason="no non-C libc locale available")
def test_locale_hermetic_a():
    """Entry is pristine (proves any earlier pollution was restored); pollute."""
    _assert_entry_locale_pristine()
    _pollute_locale()


@pytest.mark.skipif(_NON_C is None, reason="no non-C libc locale available")
def test_locale_hermetic_b():
    """Symmetric twin of _a: whichever runs second observes the restore."""
    _assert_entry_locale_pristine()
    _pollute_locale()


def _assert_entry_sigusr1_pristine():
    assert signal.getsignal(signal.SIGUSR1) == _BASELINE_SIGUSR1, (
        "fixture failed to restore SIGUSR1 disposition before this test"
    )


def _pollute_sigusr1():
    signal.signal(signal.SIGUSR1, signal.SIG_IGN)
    assert signal.getsignal(signal.SIGUSR1) is signal.SIG_IGN


def test_signal_hermetic_a():
    """Entry disposition is the import baseline; then ignore SIGUSR1."""
    _assert_entry_sigusr1_pristine()
    _pollute_sigusr1()


def test_signal_hermetic_b():
    """Symmetric twin of _a: whichever runs second observes the restore."""
    _assert_entry_sigusr1_pristine()
    _pollute_sigusr1()


def _assert_entry_fd2_pristine():
    st = os.fstat(2)
    assert (st.st_dev, st.st_ino) == _BASELINE_FD2_ID, (
        "fixture failed to restore fd 2 before this test"
    )


def _pollute_fd2(tmp_path, name):
    f = os.open(str(tmp_path / name), os.O_WRONLY | os.O_CREAT)
    os.dup2(f, 2)
    os.close(f)
    st = os.fstat(2)
    target = os.stat(str(tmp_path / name))
    assert (st.st_dev, st.st_ino) == (target.st_dev, target.st_ino)


def test_fd2_hermetic_a(tmp_path):
    """Entry fd 2 is the import-time descriptor; then repoint it at a file."""
    _assert_entry_fd2_pristine()
    _pollute_fd2(tmp_path, "stolen-stderr-a")


def test_fd2_hermetic_b(tmp_path):
    """Symmetric twin of _a: whichever runs second observes the restore."""
    _assert_entry_fd2_pristine()
    _pollute_fd2(tmp_path, "stolen-stderr-b")
