"""T3b: cd/pushd/popd converge on ONE PWD updater and ONE cwd read.

`navigation.update_pwd_vars` is the single OLDPWD/PWD writer (cd's readonly
semantics, previously missing from pushd/popd's verbatim twins) and
`navigation.current_logical_dir` the single cwd read (previously cd read the
shell variable while the stack builtins read `shell.env`). The stack's top now
tracks the current directory like bash's dirs.

All shapes probe-pinned vs bash 5.2 (tmp/r19-ledgers/T3-probes/t3b*-*.txt).
Subprocess-based: the diagnostics carry the `psh: line N:` location prefix
and readonly state must not leak between tests.
"""
import subprocess
import sys

import pytest


def _run(script, cwd=None):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, cwd=cwd)


class TestReadonlyPwdBattery:
    """bash: the chdir STANDS, the diagnostic is BARE (report_error — no
    builtin-name prefix), rc 1, and the stack mutation follows bash's
    internal model (push rolled back, pop kept, swap/rotate stand)."""

    def test_pushd_readonly_pwd_bare_message_and_rollback(self):
        # Red-on-base: the ReadonlyVariableError escaped the builtin and the
        # guard printed a `pushd: `-prefixed message; the push also stood.
        r = _run('cd /tmp; readonly PWD; pushd /var; echo rc=$?; dirs; pwd')
        assert 'PWD: readonly variable' in r.stderr
        assert 'pushd:' not in r.stderr
        out = r.stdout.splitlines()
        assert out[0] == 'rc=1'
        # bash: the failed push is rolled back — the old top is REPLACED,
        # so dirs shows the new cwd alone.
        assert out[1] == '/var'

    def test_pushd_readonly_oldpwd_same_shape(self):
        r = _run('cd /tmp; readonly OLDPWD; pushd /var; echo rc=$?; dirs')
        assert 'OLDPWD: readonly variable' in r.stderr
        assert 'pushd:' not in r.stderr
        assert r.stdout.splitlines() == ['rc=1', '/var']

    def test_popd_readonly_pwd_keeps_entry(self):
        # bash: the failed pop KEEPS the entry; the top tracks the new cwd.
        r = _run('cd /tmp; pushd /var >/dev/null; readonly PWD; '
                 'popd; echo rc=$?; dirs')
        assert 'PWD: readonly variable' in r.stderr
        assert 'popd:' not in r.stderr
        assert r.stdout.splitlines() == ['rc=1', '/tmp /tmp']

    def test_pushd_swap_readonly_pwd_swap_stands(self):
        r = _run('cd /tmp; pushd /var >/dev/null; readonly PWD; '
                 'pushd; echo rc=$?; dirs')
        assert 'PWD: readonly variable' in r.stderr
        assert r.stdout.splitlines() == ['rc=1', '/tmp /var']

    def test_pushd_rotate_readonly_pwd_rotation_stands(self):
        r = _run('cd /; pushd /tmp >/dev/null; pushd /var >/dev/null; '
                 'readonly PWD; pushd +1; echo rc=$?; dirs')
        assert 'PWD: readonly variable' in r.stderr
        assert r.stdout.splitlines() == ['rc=1', '/tmp / /var']

    def test_cd_dash_prints_dir_before_readonly_error(self):
        # Red-on-base: cd - used to skip the directory print when the
        # variable update failed; bash prints the dir FIRST, then the error.
        r = _run('cd /tmp; cd /var; readonly PWD; cd -; echo rc=$?')
        assert r.stdout.splitlines() == ['/tmp', 'rc=1']
        assert 'PWD: readonly variable' in r.stderr


class TestCwdReadConvergence:
    def test_dirs_top_tracks_cwd_after_plain_cd(self):
        # Red-on-base: dirs showed the stale pushd target at the top.
        # bash: `pushd /var; cd /; dirs` -> "/ /tmp".
        r = _run('cd /tmp; pushd /var >/dev/null; cd /; dirs')
        assert r.stdout.strip() == '/ /tmp'

    def test_pushd_swap_after_plain_cd_uses_real_cwd(self):
        # Red-on-base: the swap exchanged the STALE top; bash swaps the cwd.
        r = _run('cd /tmp; pushd /var >/dev/null; cd /private; pushd; pwd')
        assert r.stdout.splitlines() == ['/tmp /private', '/tmp']

    def test_dirs_ignores_pwd_variable_override(self):
        # bash's dirs shows its internal cwd, NOT a manually assigned $PWD
        # (probe: `cd /; PWD=/tmp; dirs` -> "/").
        r = _run('cd /; PWD=/tmp; dirs')
        assert r.stdout.strip() == '/'

    def test_pushd_relative_from_symlinked_cwd_stays_logical(self, tmp_path):
        # Red-on-base: relative operands resolved via os.path.abspath
        # (physical); bash records the symlink-named logical path.
        real = tmp_path / 'real'
        (real / 'sub').mkdir(parents=True)
        link = tmp_path / 'link'
        link.symlink_to(real)
        r = _run(f'cd {link}; pushd sub; dirs')
        expected = f'{link}/sub {link}'
        assert r.stdout.splitlines() == [expected, expected]


class TestPushdOperandShapes:
    def test_quoted_tilde_is_not_expanded(self):
        # Red-on-base: pushd expanded a QUOTED '~' itself; bash does not
        # (the expansion stage handles unquoted ~; quoted stays literal).
        r = _run("cd /tmp; pushd '~'; echo rc=$?")
        assert r.stdout.strip() == 'rc=1'
        assert '~: No such file or directory' in r.stderr

    def test_error_reports_operand_as_typed(self):
        # Red-on-base: the diagnostic showed the resolved absolute path;
        # bash reports the operand as typed.
        r = _run('cd /tmp; pushd no_such_dir_xyz; echo rc=$?')
        assert r.stdout.strip() == 'rc=1'
        assert 'pushd: no_such_dir_xyz: No such file or directory' in r.stderr
        assert '/tmp/no_such_dir_xyz' not in r.stderr

    def test_unquoted_tilde_still_works(self):
        r = _run('cd /; pushd ~ >/dev/null; dirs')
        assert r.stdout.strip() == '~ /'


@pytest.mark.parametrize('cmd', ['pushd /var', 'popd', 'dirs'])
def test_stack_builtins_share_one_updater_and_reader(cmd):
    """Smoke: every stack builtin runs against the shared helpers without
    error in a fresh shell (popd correctly errors on an empty stack)."""
    r = _run(f'cd /tmp; {cmd}; echo rc=$?')
    assert r.returncode == 0
    assert r.stdout.endswith(('rc=0\n', 'rc=1\n'))
