"""fd-move (`[n]>&m-`), csh-style combined redirect (`>&word`), and the
all-or-nothing rollback of a failed `exec` redirection list.

Regressions for reappraisal #16 Tier-2 (I/O). Every expected value below is
bash 5.2's output for the same script. These manipulate real fds, so psh runs
in a SUBPROCESS — which keeps them xdist-safe in the parallel phase (campaign #21).
"""

import os
import subprocess
import sys


def run_psh(script, cwd):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, cwd=cwd, timeout=10)


def read(path):
    with open(path) as f:
        return f.read()


class TestFdMove:
    """`[n]>&m-` / `[n]<&m-`: duplicate m onto n, then close the source m."""

    def test_move_stdout_onto_custom_fd_closes_source(self, temp_dir):
        # 3>&1- dups fd1 onto fd3 then closes fd1; echo's write to the closed
        # fd1 fails (empty stdout, write error, exit 1) — the '-' must NOT leak
        # as an argument (the pre-fix bug printed "x -").
        result = run_psh('echo x 3>&1-', temp_dir)
        assert result.returncode == 1
        assert result.stdout == ''
        assert 'write error' in result.stderr

    def test_move_preserves_target_and_closes_source(self, temp_dir):
        # exec 4>&3- moves fd3 to fd4; later >&4 writes to the file, >&3 fails.
        result = run_psh(
            'exec 3>f3; exec 4>&3-; echo hi >&4; echo bad >&3 2>e3; '
            'printf "e3=[%s]" "$(cat e3)"', temp_dir)
        assert read(os.path.join(temp_dir, 'f3')) == 'hi\n'
        assert 'e3=[]' in result.stdout  # e3 empty: >&3 failed before writing
        assert 'Bad file descriptor' in result.stderr

    def test_move_to_self_keeps_fd_open(self, temp_dir):
        # 1>&1- moves fd1 onto itself: bash does NOT close (no-op), x prints.
        result = run_psh('echo x 1>&1-; echo after=$?', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'x\nafter=0\n'

    def test_input_move_does_not_break_command(self, temp_dir):
        # 3<&0- moves stdin to fd3, closes fd0; echo ignores stdin.
        result = run_psh('echo x 3<&0-', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'x\n'

    def test_external_command_move(self, temp_dir):
        # An external command sees the move applied in its forked child.
        result = run_psh('/bin/echo hi 3>&1-', temp_dir)
        assert result.returncode != 0
        assert result.stdout == ''

    def test_move_target_fd_usable_after(self, temp_dir):
        # Temporary move restores both fds after the command.
        result = run_psh('echo x 3>&1-; echo restored', temp_dir)
        assert 'restored' in result.stdout


class TestCshCombinedRedirect:
    """`>&word` (fd omitted, non-numeric word) == `&>word` (both streams)."""

    def test_basic_combined_to_file(self, temp_dir):
        result = run_psh('echo hi >&out; printf done', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'done'
        assert read(os.path.join(temp_dir, 'out')) == 'hi\n'

    def test_space_before_word(self, temp_dir):
        result = run_psh('echo hi >& out2; printf done', temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'out2')) == 'hi\n'

    def test_redirects_both_streams(self, temp_dir):
        result = run_psh(
            '/bin/sh -c "echo o; echo e 1>&2" >&both', temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'both')) == 'o\ne\n'

    def test_quoted_filename(self, temp_dir):
        result = run_psh('echo hi >&"my file"; printf done', temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'my file')) == 'hi\n'

    def test_digit_prefixed_nonnumeric_word(self, temp_dir):
        # `2x` is one non-numeric word → combined redirect to file "2x",
        # not a dup to fd 2 with "x" as an argument.
        result = run_psh('echo hi >&2x', temp_dir)
        assert result.returncode == 0
        assert result.stdout == ''
        assert read(os.path.join(temp_dir, '2x')) == 'hi\n'

    def test_ambiguous_when_word_globs_to_many(self, temp_dir):
        open(os.path.join(temp_dir, 'aa'), 'w').close()
        open(os.path.join(temp_dir, 'ab'), 'w').close()
        result = run_psh('echo hi >&a*', temp_dir)
        assert result.returncode == 1
        assert 'ambiguous redirect' in result.stderr

    def test_numeric_word_still_dups(self, temp_dir):
        # `>&2` (digit word) stays an fd dup, not a combined redirect.
        result = run_psh('echo hi >&2', temp_dir)
        assert result.returncode == 0
        assert result.stdout == ''
        assert result.stderr == 'hi\n'

    def test_dash_still_closes(self, temp_dir):
        # `>&-` closes stdout; echo's write fails.
        result = run_psh('echo hi >&-', temp_dir)
        assert result.returncode == 1
        assert result.stdout == ''
        assert 'write error' in result.stderr

    def test_fd_specified_nonnumeric_is_ambiguous(self, temp_dir):
        # `2>&word` (fd specified) is NOT the combined special case — bash
        # errors "ambiguous redirect".
        result = run_psh('echo hi 2>&errword', temp_dir)
        assert result.returncode == 1
        assert 'ambiguous redirect' in result.stderr


class TestExecRedirectRollback:
    """A failed `exec` redirection list is rolled back all-or-nothing."""

    def test_earlier_fd_rolled_back_on_later_failure(self, temp_dir):
        # exec 3>ok 4>/bad/x: 4> fails, so fd3 is rolled back (closed) and ok
        # is left empty — a later `>&3` fails with Bad file descriptor.
        result = run_psh(
            'exec 3>ok 4>/nonexistent/x; echo later >&3 2>e3; '
            'printf "e3=[%s]" "$(cat e3)"', temp_dir)
        assert 'e3=[]' in result.stdout
        assert read(os.path.join(temp_dir, 'ok')) == ''  # created but not written
        assert 'Bad file descriptor' in result.stderr

    def test_exec_returns_one_and_shell_continues(self, temp_dir):
        result = run_psh('exec 3>ok 4>/nonexistent/x; echo rc=$?', temp_dir)
        assert result.stdout == 'rc=1\n'

    def test_multiple_fds_all_rolled_back(self, temp_dir):
        # exec 3>a 4>/bad 5>b: 3> applied, 4> fails → 3 rolled back, 5 never
        # applied. Both fd3 and fd5 are unusable afterward; a stays empty.
        result = run_psh(
            'exec 3>a 4>/nonexistent/x 5>b; echo x >&3 2>e; echo y >&5 2>>e; '
            'printf "e=[%s]" "$(cat e)"', temp_dir)
        assert read(os.path.join(temp_dir, 'a')) == ''
        assert 'e=[]' in result.stdout
        assert result.stderr.count('Bad file descriptor') == 2

    def test_successful_exec_list_still_applies(self, temp_dir):
        # No failure: both permanent redirects take effect.
        result = run_psh(
            'exec 3>t3 4>t4; echo three >&3; echo four >&4; echo done',
            temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'done\n'
        assert read(os.path.join(temp_dir, 't3')) == 'three\n'
        assert read(os.path.join(temp_dir, 't4')) == 'four\n'
