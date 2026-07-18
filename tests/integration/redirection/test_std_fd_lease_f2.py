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
