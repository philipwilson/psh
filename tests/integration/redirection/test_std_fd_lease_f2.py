"""Permanent-exec std-fd/stream ownership under the coordinator (campaign F2).

Continuation finding B, bullets 2-3 (red on base 909a79b9 — probe B5 in
tmp/boundary-ledgers/F2-probes/base-battery.txt): ``exec >file`` rebinds
fd 1 and ``sys.stdout`` PROCESS-WIDE, ``close()`` deliberately did not
restore them, and a second in-process shell then wrote into the first
shell's file.  Now the first permanent redirect acquires the STD_FDS
component lease (baseline = CLOEXEC high dups of fds 0/1/2 + the stream
objects); redirects stay permanent INSIDE the active shell, and the
baseline restores when the embedded shell deactivates — so the hosting
process gets its descriptors back and a second shell is either rejected
(while the lease is held) or writes to the real stdout (after close).

Every test runs psh EMBEDDED in a fresh python subprocess: permanent fd
redirection in the test-runner process itself would rewrite the xdist
worker's own channel fds (the standing in-process ban).  The exec-CLOEXEC
pin compares against live bash where the behavior is observable.
"""

import os
import subprocess
import sys

TREE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def _run_embedded(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env['PYTHONPATH'] = TREE
    return subprocess.run([sys.executable, '-c', code], cwd=TREE, env=env,
                          capture_output=True, text=True, timeout=90)


PRELUDE = """
import os, sys, tempfile
from psh.shell import Shell
d = tempfile.mkdtemp()
f1 = os.path.join(d, 'first.txt')
f2 = os.path.join(d, 'second.txt')
"""


def test_close_restores_fds_and_second_shell_is_not_hijacked():
    result = _run_embedded(PRELUDE + """
s1 = Shell(norc=True)
s1.run_command('exec > %s' % f1)
s1.run_command('echo one')
s1.close()
s2 = Shell(norc=True)
s2.run_command('echo two-on-real-stdout')
s2.close()
content = open(f1).read()
assert content == 'one\\n', 'first file hijacked: %r' % content
print('marker-on-real-stdout')
""")
    assert result.returncode == 0, result.stderr
    # Both the second shell's output and the post-close print land on the
    # REAL stdout (the captured pipe), not in the first shell's file.
    assert 'two-on-real-stdout' in result.stdout
    assert 'marker-on-real-stdout' in result.stdout


def test_competing_shell_rejected_while_lease_held():
    result = _run_embedded(PRELUDE + """
from psh.core.process_lease import LeaseError
s1 = Shell(norc=True)
s1.run_command('exec > %s' % f1)
s2 = Shell(norc=True)
try:
    s2.run_command('echo hijack')
    raise SystemExit('expected LeaseError')
except LeaseError:
    pass
s1.close()
s2.close()
content = open(f1).read()
assert content == '', 'rejection must precede any mutation: %r' % content
print('rejected-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'rejected-ok' in result.stdout


def test_repeated_permanent_redirects_keep_first_baseline():
    """`exec >f1` then `exec >f2`: one lease, FIRST baseline wins at close —
    deactivation restores the pre-exec stdout, not an intermediate file."""
    result = _run_embedded(PRELUDE + """
s1 = Shell(norc=True)
s1.run_command('exec > %s' % f1)
s1.run_command('echo into-one')
s1.run_command('exec > %s' % f2)
s1.run_command('echo into-two')
s1.close()
print('restored-after-close')
assert open(f1).read() == 'into-one\\n'
assert open(f2).read() == 'into-two\\n'
""")
    assert result.returncode == 0, result.stderr
    assert 'restored-after-close' in result.stdout
    assert 'into-one' not in result.stdout
    assert 'into-two' not in result.stdout


def test_permanent_redirect_stays_permanent_inside_active_shell():
    """The lease must NOT weaken exec semantics: between commands of the
    active shell the redirect persists (nothing restores per-command)."""
    result = _run_embedded(PRELUDE + """
s1 = Shell(norc=True)
s1.run_command('exec > %s' % f1)
s1.run_command('echo a')
s1.run_command('echo b')
s1.close()
assert open(f1).read() == 'a\\nb\\n', open(f1).read()
print('permanence-ok')
""")
    assert result.returncode == 0, result.stderr
    assert 'permanence-ok' in result.stdout


def test_stdin_redirect_baseline_restores():
    result = _run_embedded(PRELUDE + """
data = os.path.join(d, 'data.txt')
open(data, 'w').write('from-file\\n')
s1 = Shell(norc=True)
s1.run_command('exec < %s' % data)
s1.run_command('read line; echo "got:$line" > %s' % f1)
s1.close()
assert open(f1).read() == 'got:from-file\\n'
print('stdin-restored')
""")
    assert result.returncode == 0, result.stderr
    assert 'stdin-restored' in result.stdout


# --- parking-range composition pins (bounce blocker; red at 0ecb03f3) ------
#
# The lease parks its CLOEXEC backups at first-free >= 63.  A user redirect
# targeting that range must DISPLACE the parked backup (relocation), never
# silently replace it — on the pre-fix tip, `exec 63>f` dup2'd the user's
# file over the parked backup of host fd 0, and the shutdown restore then
# installed the USER'S FILE as the host's stdin.  Each pin asserts the host
# fds' identity across close() with the composition applied.

FD_GUARD_PRELUDE = PRELUDE + """
def ident(fd):
    try:
        st = os.fstat(fd)
        return (st.st_dev, st.st_ino, st.st_mode)
    except OSError:
        return None
host_fds = {fd: ident(fd) for fd in (0, 1, 2)}
"""

FD_GUARD_CHECK = """
after = {fd: ident(fd) for fd in (0, 1, 2)}
assert after == host_fds, 'host std fds not restored: %r vs %r' % (after, host_fds)
print('host-fds-restored')
"""


def _assert_restored(result):
    assert result.returncode == 0, result.stderr
    assert 'host-fds-restored' in result.stdout


def test_user_redirect_into_parking_range_first_slot():
    """`exec 63>f` (the very first parked slot = host fd 0's backup)."""
    result = _run_embedded(FD_GUARD_PRELUDE + """
s1 = Shell(norc=True)
s1.run_command('exec > %s' % f1)
s1.run_command('exec 63> %s' % f2)
s1.run_command('echo user-file >&63')
s1.close()
assert open(f2).read() == 'user-file\\n'
""" + FD_GUARD_CHECK)
    _assert_restored(result)


def test_user_redirect_into_parking_range_before_lease():
    """`exec 63>f` as the FIRST permanent redirect: acquisition parks
    around the range, then the user's own dup2 must still displace the
    just-parked backup (acquisition happens before application)."""
    result = _run_embedded(FD_GUARD_PRELUDE + """
s1 = Shell(norc=True)
s1.run_command('exec 63> %s' % f2)
s1.run_command('echo direct >&63')
s1.close()
assert open(f2).read() == 'direct\\n'
""" + FD_GUARD_CHECK)
    _assert_restored(result)


def test_user_redirect_second_parking_slot_after_exec_log():
    """`exec >log` then `exec 64>f` (host fd 1's parked backup)."""
    result = _run_embedded(FD_GUARD_PRELUDE + """
s1 = Shell(norc=True)
s1.run_command('exec > %s' % f1)
s1.run_command('exec 64> %s' % f2)
s1.run_command('echo one; echo user >&64')
s1.close()
assert open(f1).read() == 'one\\n'
assert open(f2).read() == 'user\\n'
""" + FD_GUARD_CHECK)
    _assert_restored(result)


def test_user_close_into_parking_range():
    """`exec 2>errlog` then `exec 65>&-`: a CLOSE targeting a parked slot
    (65 = host fd 2's backup) displaces the backup instead of destroying
    it — with stderr REDIRECTED, a destroyed backup would leave the host's
    fd 2 pointing at the user's errlog after close (red at the pre-fix
    tip)."""
    result = _run_embedded(FD_GUARD_PRELUDE + """
s1 = Shell(norc=True)
s1.run_command('exec > %s' % f1)
s1.run_command('exec 2> %s' % f2)
s1.run_command('exec 65>&-')
s1.run_command('echo still-logging; echo err-line >&2')
s1.close()
assert open(f1).read() == 'still-logging\\n'
assert open(f2).read() == 'err-line\\n'
""" + FD_GUARD_CHECK)
    _assert_restored(result)


def test_temporary_redirect_window_into_parking_range():
    """A PER-COMMAND redirect into the range (`echo x 63>f`) also
    displaces; the window's restore re-closes the vacated fd."""
    result = _run_embedded(FD_GUARD_PRELUDE + """
s1 = Shell(norc=True)
s1.run_command('exec > %s' % f1)
s1.run_command('echo tmp 63> %s' % f2)
s1.run_command('echo after')
s1.close()
assert open(f1).read() == 'tmp\\nafter\\n'
""" + FD_GUARD_CHECK)
    _assert_restored(result)


def test_named_fd_allocation_walks_around_parking_range():
    """{v} allocations that climb past 63 skip the parked slots (F_DUPFD
    takes the first FREE fd) and every allocated fd works."""
    result = _run_embedded(FD_GUARD_PRELUDE + """
s1 = Shell(norc=True)
s1.run_command('exec > %s' % f1)
script = 'fds=""; for i in $(seq 1 60); do exec {v}>%s/nf$i.txt; fds="$fds $v"; echo n$i >&$v; done; echo $fds > %s' % (d, f2)
s1.run_command(script)
s1.close()
allocated = open(f2).read().split()
assert len(allocated) == 60, allocated
assert len(set(allocated)) == 60, 'duplicate fd allocated'
assert any(int(fd) > 63 for fd in allocated), allocated
for i in (1, 30, 60):
    assert open(os.path.join(d, 'nf%d.txt' % i)).read() == 'n%d\\n' % i
""" + FD_GUARD_CHECK)
    _assert_restored(result)


def test_parking_range_neighbors_stay_clean():
    """Controls: fds 62 and 70 (outside the parked slots) compose cleanly."""
    result = _run_embedded(FD_GUARD_PRELUDE + """
s1 = Shell(norc=True)
s1.run_command('exec > %s' % f1)
s1.run_command('exec 62> %s' % f2)
f3 = os.path.join(d, 'third.txt')
s1.run_command('exec 70> %s' % f3)
s1.run_command('echo a >&62; echo b >&70; echo log')
s1.close()
assert open(f2).read() == 'a\\n'
assert open(f3).read() == 'b\\n'
assert open(f1).read() == 'log\\n'
""" + FD_GUARD_CHECK)
    _assert_restored(result)


def _fd_lister(tmp_path) -> str:
    helper = tmp_path / "list_fds.py"
    helper.write_text(
        "import os\n"
        "def is_open(fd):\n"
        "    try:\n"
        "        os.fstat(fd)\n"
        "        return True\n"
        "    except OSError:\n"
        "        return False\n"
        "print('fds:', sorted(fd for fd in range(3, 30) if is_open(fd)))\n"
    )
    return str(helper)


def test_exec_image_sees_no_backup_descriptors_matches_bash(tmp_path):
    """Successful ``os.exec`` closes every internal backup via CLOEXEC.

    Pinned as identical to bash (probe B6, green control on base): after
    ``exec 5>/dev/null; exec >file`` the replacement image sees the USER
    fd 5 (bash keeps user fds) and NO psh-internal descriptors — in
    particular not the STD_FDS lease's high backups, which are created
    with ``F_DUPFD_CLOEXEC``.
    """
    from tests.harness.shell_oracle import resolve_bash
    bash = resolve_bash()
    helper = _fd_lister(tmp_path)
    out = tmp_path / "out.txt"
    script = f"exec 5>/dev/null; exec > {out}; exec {sys.executable} {helper}"
    results = {}
    for name, argv in (('oracle', [bash.path]),
                       ('psh', [sys.executable, '-m', 'psh', '--norc'])):
        out.write_text('')
        env = dict(os.environ)
        env['PYTHONPATH'] = TREE
        proc = subprocess.run(argv + ['-c', script], cwd=TREE, env=env,
                              capture_output=True, text=True, timeout=90)
        assert proc.returncode == 0, (name, proc.stderr)
        results[name] = out.read_text().strip()
    assert results['psh'] == results['oracle'], results
    assert results['psh'].startswith('fds:')
