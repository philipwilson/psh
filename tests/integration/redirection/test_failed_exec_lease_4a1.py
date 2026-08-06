"""A failed permanent redirect must not leave the STD_FDS lease behind.

Slot 4A.1 (the LOW, charter item 5). ``apply_permanent_redirections``
acquires the STD_FDS lease from the redirect list's SHAPE, before anything
is known about whether the redirect can succeed — measured from both sides
at base a64eb6e8: a failing target still took the lease, and a rejected
acquisition never created the target file. So ``exec >/nonexistent-dir/f``
left the lease, three parked backup fds (>= 63) and the ``_std_baseline``
registration behind although fds 0/1/2 were never touched — and that phantom
holding made the coordinator reject unrelated live shells.

The discrimination matters in both directions and both are pinned here: a
lease THIS command acquired is released when its redirect fails, while a
lease an EARLIER successful ``exec >f`` holds is untouched by a later
failing one.

Every test runs psh EMBEDDED in a fresh python subprocess: permanent fd
redirection in the test-runner process would rewrite the xdist worker's own
channel fds (the standing in-process ban), and a fresh process also gives
each case its own ProcessLeaseCoordinator singleton.
"""

import os
import sys

from shell_oracle import (
    Completed,
    hermetic_shell_env,
    is_comparable,
    run_shell_case,
)

TREE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

# No bash oracle for any case in this file: bash has no analogue for
# in-process multi-shell ownership of the standard descriptors. These are
# embedding-semantics pins, and the compare-bash floor is the regression net
# elsewhere, not an oracle here.

PRELUDE = """
import os, sys, tempfile
from psh.shell import Shell
from psh.core.process_lease import ComponentKind, LeaseError, get_coordinator
d = tempfile.mkdtemp()
coord = get_coordinator()

def leases():
    return sorted(c.kind.name for c in coord._components if not c.released)

def parked():
    out = []
    for fd in range(63, 96):
        try:
            os.fstat(fd)
            out.append(fd)
        except OSError:
            pass
    return out
"""


def _run_embedded(code: str) -> Completed:
    r = run_shell_case([sys.executable, '-c', code], cwd=TREE,
                       env=hermetic_shell_env({'PYTHONPATH': TREE,
                                               'LC_ALL': 'C', 'LANG': 'C'}),
                       timeout=90)
    assert is_comparable(r), r
    return r


def test_failing_exec_leaves_no_lease_no_parked_fds_no_baseline():
    """The LOW itself: nothing acquired survives a redirect that failed."""
    result = _run_embedded(PRELUDE + """
sh = Shell(norc=True)
rc = sh.run_command('exec > /nonexistent-dir-4a1/out.txt')
assert rc != 0, 'the redirect was supposed to fail'
assert 'STD_FDS' not in leases(), 'lease retained: %r' % leases()
assert parked() == [], 'parked backup fds leaked: %r' % parked()
baseline = sh.io_manager.file_redirector._std_baseline
assert baseline is None, 'stale _std_baseline registered'
sh.close()
print('no-residue-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'no-residue-ok' in result.stdout


def test_failing_exec_does_not_block_an_unrelated_shell():
    """The behavioural consequence, which the internals check alone would
    not have caught: shell A redirected nothing, so shell B must run.

    Under LC_ALL=C the activation glue takes no LOCALE lease, so A's only
    possible holding is the STD_FDS one this test is about — otherwise B's
    rejection could never distinguish the fix."""
    result = _run_embedded(PRELUDE + """
a = Shell(norc=True)
a.run_command('exec 3> /nonexistent-dir-4a1/out.txt')
assert leases() == [], 'A holds %r; cell cannot discriminate' % leases()
b = Shell(norc=True)
assert b.run_command('true') == 0
b.close(); a.close()
print('sibling-ran-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'sibling-ran-ok' in result.stdout


def test_failing_exec_after_a_successful_one_keeps_the_first_lease():
    """MUST-HOLD discrimination: only a lease THIS command acquired may go.
    An earlier successful `exec >f` genuinely owns fd 1."""
    result = _run_embedded(PRELUDE + """
f1 = os.path.join(d, 'first.txt')
sh = Shell(norc=True)
assert sh.run_command('exec 3> %s' % f1) == 0
assert 'STD_FDS' in leases()
before = parked()
rc = sh.run_command('exec 4> /nonexistent-dir-4a1/out.txt')
assert rc != 0
assert 'STD_FDS' in leases(), 'the FIRST exec\\'s lease was released'
assert parked() == before, 'parked backups disturbed: %r vs %r' % (parked(), before)
assert sh.io_manager.file_redirector._std_baseline is not None
sh.close()
print('first-lease-intact')
""")
    assert result.returncode == 0, result.stderr
    assert 'first-lease-intact' in result.stdout


def test_successful_shell_still_blocks_a_second_shell():
    """MUST-HOLD: the designed protection must not weaken. The twin of the
    sibling test above, differing ONLY in whether the exec succeeded."""
    result = _run_embedded(PRELUDE + """
a = Shell(norc=True)
assert a.run_command('exec 3> %s' % os.path.join(d, 'ok.txt')) == 0
assert leases() == ['STD_FDS']
b = Shell(norc=True)
try:
    b.run_command('true')
    raise SystemExit('expected LeaseError: A genuinely holds the std fds')
except LeaseError:
    pass
b.close(); a.close()
print('protection-intact')
""")
    assert result.returncode == 0, result.stderr
    assert 'protection-intact' in result.stdout


def test_baseline_dup_failure_aborts_transactionally():
    """Fault injection at the baseline-dup boundary.

    With RLIMIT_NOFILE below the parking base every ``F_DUPFD_CLOEXEC``
    fails. Recording ``None`` for those is what ``restore`` reads as "this
    fd was CLOSED at baseline, close it again" — so at base the exec
    reported SUCCESS and ``close()`` then closed the HOST's fds 0, 1 and 2.
    Only a genuinely closed descriptor (EBADF) may record None; any other
    errno means the baseline is unknowable, so the acquisition aborts
    transactionally and the redirect fails."""
    result = _run_embedded(PRELUDE + """
import resource
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (32, hard))
sh = Shell(norc=True)
rc = sh.run_command('exec 3> %s' % os.path.join(d, 'out.txt'))
resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
assert rc != 0, 'exec reported success on an unknowable baseline'
assert 'STD_FDS' not in leases(), 'half-acquired lease: %r' % leases()
assert sh.io_manager.file_redirector._std_baseline is None

def alive(fd):
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False

sh.close()
assert all(alive(fd) for fd in (0, 1, 2)), 'close() closed the host std fds'
print('transactional-abort-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'transactional-abort-ok' in result.stdout


def test_baseline_dup_failure_on_an_exhausted_fd_table_also_aborts():
    """The other non-EBADF route: EMFILE.

    The two failures reach ``F_DUPFD_CLOEXEC`` differently — EINVAL when the
    parking base is above RLIMIT_NOFILE (the case above), EMFILE when the
    table is full below it — and both mean the same thing: the baseline is
    unknowable. Pinned separately so the rule is "not EBADF", not "not the
    one errno I happened to reproduce"."""
    result = _run_embedded(PRELUDE + """
import resource
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (200, hard))
sh = Shell(norc=True)
assert sh.run_command('true') == 0     # warm psh's lazy imports FIRST:
assert leases() == []                  # they need fds, and take no lease
held = []
try:
    while True:
        held.append(os.dup(1))            # fill the table BELOW the limit
except OSError:
    pass
assert len(held) > 100, 'the table did not fill'
# Free a few LOW slots so any remaining import/allocation can proceed. They
# cannot satisfy the lease's dup, which needs a free fd >= 63 (_PARKING_BASE)
# — so F_DUPFD_CLOEXEC still fails EMFILE, which is the point of the cell.
for fd in held[:8]:
    os.close(fd)
held = held[8:]
rc = sh.run_command('exec 3> %s' % os.path.join(d, 'out.txt'))
for fd in held:
    os.close(fd)
resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
assert rc != 0, 'exec reported success on an unknowable baseline'
assert 'STD_FDS' not in leases(), 'half-acquired lease: %r' % leases()
assert sh.io_manager.file_redirector._std_baseline is None

def alive(fd):
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False

sh.close()
assert all(alive(fd) for fd in (0, 1, 2)), 'close() closed the host std fds'
print('emfile-abort-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'emfile-abort-ok' in result.stdout


def test_closed_std_fd_still_records_a_closed_baseline():
    """The other half of the errno split: a GENUINELY closed descriptor
    (EBADF) must still record None and still be closed again at restore —
    the encoding stays meaningful, it just stops doubling as "we could not
    dup it"."""
    result = _run_embedded(PRELUDE + """
os.close(0)                       # stdin genuinely closed before the lease
sh = Shell(norc=True)
assert sh.run_command('exec 3> %s' % os.path.join(d, 'out.txt')) == 0
baseline = sh.io_manager.file_redirector._std_baseline
assert baseline is not None
assert baseline.fds[0] is None, 'a closed fd must record None'
assert baseline.fds[1] is not None and baseline.fds[2] is not None
sh.close()
print('closed-baseline-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'closed-baseline-ok' in result.stdout


def test_dropped_shell_without_close_does_not_poison_the_next():
    """GC handover, the A5 headline consequence: a shell that did permanent
    redirects and was dropped WITHOUT close() used to be kept alive by the
    coordinator's own component list (the baseline held its state strongly),
    so it never collected and rejected every later shell."""
    result = _run_embedded(PRELUDE + """
import gc
a = Shell(norc=True)
a.run_command('exec 3> %s' % os.path.join(d, 'keep3.txt'))
assert 'STD_FDS' in leases()
del a
gc.collect()
c = Shell(norc=True)
assert c.run_command('true') == 0, 'a dropped shell poisoned the next one'
c.close()
print('handover-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'handover-ok' in result.stdout


def test_relocation_then_failure_keeps_the_earlier_lease_and_host_fds():
    """Composition: a failing exec whose plan ALREADY displaced a parked
    backup (the relocation protocol) must still leave the earlier lease and
    the host's descriptors intact."""
    result = _run_embedded(PRELUDE + """
def ident(fd):
    st = os.fstat(fd)
    return (st.st_dev, st.st_ino)
host = {fd: ident(fd) for fd in (0, 1, 2)}
sh = Shell(norc=True)
assert sh.run_command('exec 3> %s' % os.path.join(d, 'first.txt')) == 0
slot = parked()[0]
rc = sh.run_command('exec %d> %s 4>/nonexistent-dir-4a1/x'
                    % (slot, os.path.join(d, 'second.txt')))
assert rc != 0
assert 'STD_FDS' in leases(), 'the earlier lease was released'
sh.close()
assert {fd: ident(fd) for fd in (0, 1, 2)} == host, 'host std fds not restored'
print('relocation-compose-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'relocation-compose-ok' in result.stdout
