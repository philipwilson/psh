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
import shlex
import sys

from shell_oracle import (
    Completed,
    hermetic_shell_env,
    is_comparable,
    resolve_bash,
    run_shell_case,
)

TREE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

# ORACLE STATUS, PER GROUP. The earlier blanket claim — "no bash oracle for
# any case in this file" — was FALSE, and it hid a real parity regression
# (R8 BL-1: every permanent redirect failed under `ulimit -n <= 64` while
# bash succeeded, and no cell here could see it).
#
#   * OWNERSHIP cells (lease retained/released, sibling shells, GC handover)
#     genuinely have NO bash oracle: bash has no analogue for in-process
#     multi-shell ownership of the standard descriptors. There the
#     compare-bash floor is a regression net, not an oracle.
#   * RLIMIT cells DO have a bash oracle and are pinned BOTH SIDES against
#     live bash. A permanent redirect under a low `ulimit -n` is ordinary
#     shell behaviour that bash performs successfully; psh failing it was
#     observable to any user, not an embedding detail.

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


def _run_at_rlimit(limit: int, script: str, *, bash: bool = False) -> str:
    """Run *script* under `ulimit -n <limit>` in psh or bash; return stdout.

    The limit must be imposed by an outer shell BEFORE the interpreter
    starts. Lowering RLIMIT_NOFILE from inside the process under test would
    leave descriptors already open above the new limit and measure a
    different situation than a user's `ulimit -n` does. Explicit argv
    throughout (the zsh unquoted-`$var` trap).
    """
    oracle = resolve_bash().path
    inner_shell = (shlex.quote(oracle) if bash
                   else f"{shlex.quote(sys.executable)} -m psh")
    inner = (f"ulimit -n {limit}; exec {inner_shell} --norc -c "
             f"{shlex.quote(script)}")
    r = run_shell_case([oracle, '-c', inner], cwd=TREE,
                       env=hermetic_shell_env({'PYTHONPATH': TREE}),
                       timeout=90)
    assert is_comparable(r), r
    return r.stdout


def _assert_low_rlimit_parity(limit: int) -> None:
    """psh and bash must agree on a permanent redirect at *limit*."""
    script = f'exec 3> {TREE}/tmp/rlimit-parity-{limit}.txt; echo after=$?'
    psh_out = _run_at_rlimit(limit, script)
    bash_out = _run_at_rlimit(limit, script, bash=True)
    assert psh_out == bash_out, (limit, psh_out, bash_out)
    assert 'after=0' in psh_out, (limit, psh_out)


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


def test_low_rlimit_permanent_redirect_matches_bash():
    """BOTH-SIDES bash pin, BELOW the old parking threshold (R8 BL-1).

    A permanent redirect under a low `ulimit -n` is ordinary shell
    behaviour. psh parked its lease backups at a fixed fd 63, so under
    RLIMIT_NOFILE <= 64 the dup failed — EINVAL below 64, EMFILE at 64,
    neither of which means the table is exhausted — and treating that as
    exhaustion made psh fail a redirect bash performs happily. The parking
    base now adapts to the limit.
    """
    _assert_low_rlimit_parity(50)


def test_normal_rlimit_permanent_redirect_matches_bash():
    """The same pin ABOVE the threshold: the ordinary case is untouched."""
    _assert_low_rlimit_parity(70)


def test_low_rlimit_baseline_records_real_fds_and_close_keeps_host_fds():
    """The transactional guarantee, restated for the case that now SUCCEEDS.

    The old shape of this pin expected the redirect to FAIL under a low
    limit; that expectation was itself the regression. What must hold is
    that the baseline is REAL — actual parked descriptors, not the `None`
    that `restore` reads as "was closed, close it again" — so `close()`
    hands the host its fds back instead of closing them.
    """
    result = _run_embedded(PRELUDE + """
import resource
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (50, hard))
sh = Shell(norc=True)
rc = sh.run_command('exec 3> %s' % os.path.join(d, 'out.txt'))
assert rc == 0, 'a merely-low limit must not fail the redirect'
baseline = sh.io_manager.file_redirector._std_baseline
assert baseline is not None
assert all(v is not None for v in baseline.fds.values()), (
    'a dup failure was recorded as a CLOSED baseline: %r' % baseline.fds)
assert all(v >= 10 for v in baseline.fds.values()), (
    'parked below the named-fd save area: %r' % baseline.fds)

def alive(fd):
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False

sh.close()
resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
assert all(alive(fd) for fd in (0, 1, 2)), 'close() closed the host std fds'
print('low-limit-baseline-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'low-limit-baseline-ok' in result.stdout


def test_low_rlimit_keeps_bash_named_fd_numbering():
    """The floor under the adaptive base, pinned against bash.

    bash's `{v}>file` returns 10 at EVERY limit — its named-fd numbering
    does not degrade — so the lease must never park into the >=10 save
    area, however low the limit goes. This is the measured fact the
    `_PARKING_FLOOR` constant encodes.
    """
    for limit in (24, 50, 70):
        script = (f'exec 3> {TREE}/tmp/nf-a-{limit}.txt; '
                  f'exec {{v}}> {TREE}/tmp/nf-b-{limit}.txt; echo v=$v')
        psh_out = _run_at_rlimit(limit, script)
        bash_out = _run_at_rlimit(limit, script, bash=True)
        assert psh_out == bash_out, (limit, psh_out, bash_out)
        assert 'v=10' in psh_out, (limit, psh_out)


def test_sub_16_rlimit_envelope_is_recorded_not_claimed():
    """RECORD-ONLY: where the adaptive base runs out of room.

    The floor refuses to park below fd 10, because bash's named-fd numbering
    starts there at EVERY limit. Under a limit low enough that three backups
    plus relocation headroom do not fit above 10, psh cannot park at all.
    This cell RECORDS the measured envelope rather than asserting a parity
    that does not hold there:

      * limit >= 13 — full parity, psh and bash both succeed;
      * limit <= 12 — bash succeeds; psh fails the redirect CLEANLY (clear
        diagnostic, non-zero status, nothing half-acquired) instead of
        recording a `None` baseline that would later close the host's std
        fds, which is what it used to do.

    A shell under `ulimit -n 12` has ~9 usable descriptors; the honest
    statement is that psh declines rather than corrupts.
    """
    parity, divergent = [], []
    for limit in (11, 12, 13, 14, 16):
        script = f'exec 3> {TREE}/tmp/sub16-{limit}.txt; echo after=$?'
        psh_out = _run_at_rlimit(limit, script)
        bash_out = _run_at_rlimit(limit, script, bash=True)
        (parity if psh_out == bash_out else divergent).append(limit)
        if psh_out != bash_out:
            # A divergence here may be a CLEAN refusal, never a silent
            # success on an unknowable baseline.
            assert 'after=1' in psh_out, (limit, psh_out)
    assert parity, 'the envelope must have a parity region'
    assert all(limit >= 13 for limit in parity), parity
    assert all(limit <= 12 for limit in divergent), divergent


def test_genuine_exhaustion_still_aborts_transactionally():
    """The transactional abort survives — for REAL exhaustion only.

    When the fd table is actually full there is no slot at any base, so the
    baseline is genuinely unknowable and the acquisition must abort with
    nothing half-acquired (the B-13b guarantee), rather than recording a
    `None` that would later close the host's descriptors.
    """
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
        held.append(os.dup(1))            # fill the table COMPLETELY
except OSError:
    pass
assert len(held) > 100, 'the table did not fill'
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
print('exhaustion-abort-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'exhaustion-abort-ok' in result.stdout


def test_relocation_protocol_at_the_adaptive_parking_base():
    """COMPOSITION: adaptive parking x the relocation protocol.

    The relocation protocol is base-agnostic in theory. Under a low limit
    the backups park LOW (e.g. 21/22/23 at soft=24), so a user redirect
    into that range must displace them there exactly as it does at 63 —
    otherwise the shutdown restore would install the USER's file as a host
    std fd, which is the F2 bounce blocker resurfacing at a new base.
    """
    result = _run_embedded(PRELUDE + """
import resource
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
# 50, not 24: this cell lowers the limit from INSIDE a running interpreter,
# which already holds descriptors, so the usable window is smaller than a
# user's `ulimit -n` of the same number. 50 still moves the parking base well
# below 63 (measured: base 47), which is what the cell is about.
resource.setrlimit(resource.RLIMIT_NOFILE, (50, hard))

def ident(fd):
    st = os.fstat(fd)
    return (st.st_dev, st.st_ino)

host = {fd: ident(fd) for fd in (0, 1, 2)}
sh = Shell(norc=True)
assert sh.run_command('exec 3> %s' % os.path.join(d, 'a.txt')) == 0
baseline = sh.io_manager.file_redirector._std_baseline
parked = sorted(v for v in baseline.fds.values() if v is not None)
assert parked and max(parked) < 63, 'not parked under the low limit: %r' % parked
assert min(parked) >= 10, 'parked into the save area: %r' % parked
target = parked[0]
assert sh.run_command('exec %d> %s' % (target, os.path.join(d, 'b.txt'))) == 0
moved = sorted(v for v in sh.io_manager.file_redirector._std_baseline.fds.values()
               if v is not None)
assert target not in moved, 'backup not displaced: %r' % moved
sh.close()
resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
assert {fd: ident(fd) for fd in (0, 1, 2)} == host, 'host std fds not restored'
print('relocation-at-adaptive-base-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'relocation-at-adaptive-base-ok' in result.stdout


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
