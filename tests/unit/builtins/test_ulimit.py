"""Unit tests for the ulimit builtin (reappraisal #18 Tier-2 T2-G).

Query, format, and error paths are safe in-process (they only read limits).
Anything that SETS a limit runs in a subprocess: an in-process set would lower
the pytest runner's own rlimits (e.g. NOFILE) and break unrelated tests — the
same permanent-process-state hazard that exec-redirection tests avoid.
"""

import os
import resource
import subprocess
import sys

import pytest

PSH = [sys.executable, '-m', 'psh']
# Repo root (…/tests/unit/builtins/test_ulimit.py -> 3 parents). Subprocess psh
# must import THIS worktree, not the editable-installed MAIN tree.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


def _run(script):
    env = os.environ.copy()
    env['PYTHONPATH'] = _ROOT + os.pathsep + env.get('PYTHONPATH', '')
    return subprocess.run(PSH + ['-c', script], capture_output=True, text=True,
                          timeout=15, env=env)


class TestUlimitQuery:
    def test_bare_ulimit_reports_file_size_soft(self, captured_shell):
        soft, _ = resource.getrlimit(resource.RLIMIT_FSIZE)
        expected = 'unlimited' if soft == resource.RLIM_INFINITY else str(soft // 512)
        rc = captured_shell.run_command('ulimit')
        assert rc == 0
        assert captured_shell.get_stdout().strip() == expected

    def test_query_open_files_soft(self, captured_shell):
        soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        expected = 'unlimited' if soft == resource.RLIM_INFINITY else str(soft)
        rc = captured_shell.run_command('ulimit -n')
        assert rc == 0
        assert captured_shell.get_stdout().strip() == expected

    def test_query_hard_open_files(self, captured_shell):
        _, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        expected = 'unlimited' if hard == resource.RLIM_INFINITY else str(hard)
        rc = captured_shell.run_command('ulimit -Hn')
        assert rc == 0
        assert captured_shell.get_stdout().strip() == expected

    def test_all_lists_supported_resources(self, captured_shell):
        rc = captured_shell.run_command('ulimit -a')
        assert rc == 0
        out = captured_shell.get_stdout()
        # A representative sampling every Unix exposes.
        assert 'open files' in out and '(-n)' in out
        assert 'core file size' in out and '(blocks, -c)' in out
        assert 'cpu time' in out and '(seconds, -t)' in out
        # Layout: the option/unit group's ")" lands in a fixed column.
        for line in out.splitlines():
            assert line[39] == ')', repr(line)

    def test_multiple_resources_are_labelled(self, captured_shell):
        rc = captured_shell.run_command('ulimit -n -c')
        assert rc == 0
        out = captured_shell.get_stdout()
        assert 'open files' in out
        assert 'core file size' in out


class TestUlimitErrors:
    def test_invalid_option(self, captured_shell):
        rc = captured_shell.run_command('ulimit -Z')
        assert rc == 2
        err = captured_shell.get_stderr()
        assert '-Z: invalid option' in err
        assert 'usage:' in err

    def test_invalid_number(self, captured_shell):
        rc = captured_shell.run_command('ulimit -n notanumber')
        assert rc == 1
        assert 'notanumber: invalid number' in captured_shell.get_stderr()

    def test_pipe_size_honest_error(self, captured_shell):
        # -p is a real bash option with no portable Python API: honest error,
        # never a silent no-op or misleading message.
        rc = captured_shell.run_command('ulimit -p')
        assert rc == 2
        assert 'pipe size' in captured_shell.get_stderr()
        assert 'not supported' in captured_shell.get_stderr()

    def test_platform_absent_resource_is_invalid_option(self, captured_shell):
        # RLIMIT_LOCKS (-x) does not exist on macOS; on Linux it does. When the
        # platform lacks it psh rejects it like bash does (invalid option).
        if getattr(resource, 'RLIMIT_LOCKS', None) is not None:
            pytest.skip('RLIMIT_LOCKS present on this platform')
        rc = captured_shell.run_command('ulimit -x')
        assert rc == 2
        assert '-x: invalid option' in captured_shell.get_stderr()


class TestUlimitSet:
    """Setting a limit changes the psh process; run out-of-process."""

    def test_set_soft_open_files_round_trips(self):
        r = _run('ulimit -S -n 256; ulimit -n')
        assert r.returncode == 0
        assert r.stdout.strip() == '256'

    def test_no_hs_sets_both_soft_and_hard(self):
        r = _run('ulimit -n 256; echo "$(ulimit -Sn) $(ulimit -Hn)"')
        assert r.returncode == 0
        assert r.stdout.strip() == '256 256'

    def test_file_size_block_factor_round_trip(self):
        # -f value is in 512-byte blocks; setting 100 then querying must give 100.
        r = _run('ulimit -S -f 100; ulimit -f')
        assert r.returncode == 0
        assert r.stdout.strip() == '100'

    def test_soft_only_leaves_hard_untouched(self):
        r = _run('ulimit -S -c 0; ulimit -Hc')
        assert r.returncode == 0
        # Hard core limit is unchanged (still whatever the platform default is);
        # only assert the command succeeded and printed a value.
        assert r.stdout.strip() != ''

    def test_set_limit_is_inherited_by_children(self):
        # A limit set in psh is inherited by external commands it forks.
        script = 'ulimit -S -n 256; ' + sys.executable + \
            ' -c "import resource;print(resource.getrlimit(resource.RLIMIT_NOFILE)[0])"'
        r = _run(script)
        assert r.returncode == 0
        assert r.stdout.strip() == '256'
