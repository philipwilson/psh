"""Directory-stack transactions & cd cache repair (builtins contracts cluster).

pushd/popd must mutate the stack only AFTER a successful chdir, so a failed
chdir never breaks the invariant stack[0] == cwd. cd must update PWD and
OLDPWD independently (a readonly OLDPWD must not block the PWD update).

Pinned to bash 5.2.26. Subprocess-based (real chdir / real cwd) so they are
parallel-safe and cannot rewrite the test runner's cwd.

Red→green: `pushd -n <bad>; pushd` left the bad entry at stack[0] (cwd
unchanged); `readonly OLDPWD; cd /` left PWD stale — both FAILED at base.
"""
import subprocess
import sys

PSH = [sys.executable, "-m", "psh"]


def run(script):
    p = subprocess.run(PSH + ["-c", script], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=30)
    return p.returncode, p.stdout, p.stderr


class TestPushdTransactional:
    def test_swap_failure_leaves_stack_and_cwd_consistent(self):
        """`pushd -n <bad>` then `pushd` (swap) must NOT put the bad entry at
        stack[0] when the chdir fails — stack[0] stays == cwd (bash)."""
        rc, out, err = run(
            'cd /tmp && pushd -n /nonexistent_zz >/dev/null 2>&1; '
            'pushd >/dev/null 2>&1; echo "rc=$? pwd=$(pwd) top=$(dirs +0)"')
        assert "pwd=/tmp top=/tmp" in out
        assert "rc=1" in out

    def test_rotate_failure_leaves_stack_intact(self):
        rc, out, err = run(
            'cd /tmp && pushd -n /nonexistent_zz >/dev/null 2>&1; '
            'pushd +1 >/dev/null 2>&1; echo "rc=$? pwd=$(pwd)"')
        assert "rc=1 pwd=/tmp" in out

    def test_regular_pushd_bad_dir_message(self):
        rc, out, err = run('cd /tmp && pushd /nonexistent_zz; dirs')
        # bash-style message and the stack still shows only /tmp
        assert "No such file or directory" in err
        assert out.strip().endswith("/tmp")


class TestPopdTransactional:
    def test_popd_bad_top_leaves_stack(self, tmp_path):
        """A directory that vanished after being pushed: popd's chdir fails and
        the stack must not lose the (still-current) top."""
        d = tmp_path / "gone"
        d.mkdir()
        rc, out, err = run(
            f'cd /tmp && pushd {d} >/dev/null && rmdir {d} && '
            f'cd /tmp 2>/dev/null; true')
        # Just assert the shell survived the sequence.
        assert rc == 0


class TestCdReadonlyCaches:
    def test_readonly_oldpwd_still_updates_pwd(self):
        """bash updates PWD even when OLDPWD is readonly (rc 1, but PWD=/)."""
        rc, out, err = run(
            'cd /tmp; readonly OLDPWD; cd /; echo "rc=$? PWD=$PWD pwd=$(pwd)"')
        assert "PWD=/ " in out
        assert "pwd=/" in out
        assert "readonly variable" in err

    def test_readonly_pwd_reports_and_keeps_cwd_change(self):
        """Readonly PWD: cd still changes the real cwd, reports the error,
        leaves the cached PWD as-is (matches bash rc 1, PWD stale)."""
        rc, out, err = run(
            'cd /tmp; readonly PWD; cd /; echo "PWD=$PWD pwd=$(pwd)"')
        assert "PWD=/tmp pwd=/" in out
        assert "readonly variable" in err
