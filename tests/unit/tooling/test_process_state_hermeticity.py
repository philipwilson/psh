"""Pins for the per-test process-state snapshot/restore fixture (E3).

``tests/conftest.py#_restore_signal_dispositions_and_std_fds`` must roll back
per-test drift in process signal dispositions, fds 0/1/2, and the
PROCESS-GLOBAL libc locale (``LocaleService._try_setlocale`` calls
``setlocale`` for non-C profiles; a later C-profile shell never calls
``setlocale`` at all, so a leaked worker locale would persist indefinitely).

Each pair below is a pollute-then-observe sequence: the first test drifts the
state deliberately and PROVES the drift took; the second asserts the fixture
restored the pre-test state. Order within one process is definitional
(pytest runs module tests in definition order), and the module is marked
``serial`` so xdist cannot split the pair across workers.

Red-on-base: with the fixture's locale arm absent (the pre-bounce conftest),
``test_locale_restored_after_pollution`` fails — transcript archived in
``tmp/boundary-ledgers/E23-probes/locale-restore-red-on-base.txt``.
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


@pytest.mark.skipif(_NON_C is None, reason="no non-C libc locale available")
def test_locale_pollution_takes_effect():
    """Pollute: set a non-C process-global libc locale and prove it took."""
    locale.setlocale(locale.LC_ALL, _NON_C)
    assert locale.setlocale(locale.LC_ALL) != _BASELINE_LOCALE


@pytest.mark.skipif(_NON_C is None, reason="no non-C libc locale available")
def test_locale_restored_after_pollution():
    """Observe: the fixture rolled the libc locale back for THIS test."""
    assert locale.setlocale(locale.LC_ALL) == _BASELINE_LOCALE


def test_signal_pollution_takes_effect():
    """Pollute: ignore SIGUSR1 in the runner process and prove it took."""
    signal.signal(signal.SIGUSR1, signal.SIG_IGN)
    assert signal.getsignal(signal.SIGUSR1) is signal.SIG_IGN


def test_signal_disposition_restored_after_pollution():
    """Observe: SIGUSR1 is back to its pre-test disposition (not SIG_IGN)."""
    assert signal.getsignal(signal.SIGUSR1) is not signal.SIG_IGN


_POLLUTED_FD2 = {}


def test_fd_pollution_takes_effect(tmp_path):
    """Pollute: permanently repoint fd 2 at a file (no restore here)."""
    f = os.open(str(tmp_path / "stolen-stderr"), os.O_WRONLY | os.O_CREAT)
    os.dup2(f, 2)
    os.close(f)
    st = os.fstat(2)
    _POLLUTED_FD2["id"] = (st.st_dev, st.st_ino)
    # Prove the drift: fd 2 now points at our regular file.
    target = os.stat(str(tmp_path / "stolen-stderr"))
    assert _POLLUTED_FD2["id"] == (target.st_dev, target.st_ino)


def test_fd_restored_after_pollution():
    """Observe: fd 2 no longer points at the previous test's stolen file."""
    st = os.fstat(2)
    assert "id" in _POLLUTED_FD2, "pollute test must run first"
    assert (st.st_dev, st.st_ino) != _POLLUTED_FD2["id"]
