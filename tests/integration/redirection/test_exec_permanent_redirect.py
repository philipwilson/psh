"""Permanent (exec) redirections: shared offset between builtins and externals.

After `exec >file`, builtins write through the shell's Python stream
(sys.stdout) while external children inherit the raw fd. Both views must
share ONE open file description — a second independent open() has its own
offset (and re-truncates in 'w' mode), so the two writers overwrite each
other. These tests pin the single-open + dup + fdopen fix (bash-verified:
every expected value below is bash 5.2's output for the same script).

CRITICAL: permanent fd redirection rewrites the shell's own fds, which in
the test runner are the pytest/xdist channel — so every test here runs psh
in a SUBPROCESS, never in-process (see CLAUDE.md "Parallel-safety rules").
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


class TestExecCombinedRedirect:
    """exec &>file / exec &>>file."""

    def test_combined_truncate_builtin_and_stderr(self, temp_dir):
        result = run_psh('exec &>out.txt; echo one; echo two >&2; echo three',
                         temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'out.txt')) == 'one\ntwo\nthree\n'

    def test_combined_interleaves_builtins_and_externals(self, temp_dir):
        result = run_psh(
            'exec &>out.txt; echo b1; /bin/echo e1; echo b2 >&2; '
            '/bin/echo e2 1>&2; echo b3', temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'out.txt')) == \
            'b1\ne1\nb2\ne2\nb3\n'

    def test_combined_append_preserves_existing(self, temp_dir):
        with open(os.path.join(temp_dir, 'out.txt'), 'w') as f:
            f.write('seed\n')
        result = run_psh('exec &>>out.txt; echo b1; echo b2 >&2; /bin/echo e1',
                         temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'out.txt')) == 'seed\nb1\nb2\ne1\n'


class TestExecStdoutRedirect:
    """exec >file / exec >>file / exec >|file."""

    def test_truncate_interleaves_builtins_and_externals(self, temp_dir):
        result = run_psh('exec >out.txt; echo b1; /bin/echo e1; echo b2',
                         temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'out.txt')) == 'b1\ne1\nb2\n'

    def test_partial_line_then_external(self, temp_dir):
        # printf without newline: bash writes 'ab' immediately; the external
        # then writes 'X\n'; final 'cd' follows. Pins flush/interleave order.
        result = run_psh('exec >out.txt; printf ab; /bin/echo X; printf cd',
                         temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'out.txt')) == 'abX\ncd'

    def test_append_mode(self, temp_dir):
        with open(os.path.join(temp_dir, 'out.txt'), 'w') as f:
            f.write('seed\n')
        result = run_psh('exec >>out.txt; echo b1; /bin/echo e1', temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'out.txt')) == 'seed\nb1\ne1\n'

    def test_clobber_redirect(self, temp_dir):
        result = run_psh('exec >|out.txt; echo b1; /bin/echo e1; echo b2',
                         temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'out.txt')) == 'b1\ne1\nb2\n'

    def test_second_exec_replaces_first(self, temp_dir):
        with open(os.path.join(temp_dir, 'out2.txt'), 'w') as f:
            f.write('pre\n')
        result = run_psh(
            'exec >out1.txt; echo a; exec >>out2.txt; echo b; /bin/echo c',
            temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'out1.txt')) == 'a\n'
        assert read(os.path.join(temp_dir, 'out2.txt')) == 'pre\nb\nc\n'

    def test_output_before_exec_goes_to_old_stdout(self, temp_dir):
        result = run_psh('echo before; exec >out.txt; echo after', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'before\n'
        assert read(os.path.join(temp_dir, 'out.txt')) == 'after\n'

    def test_stderr_unaffected_by_exec_stdout(self, temp_dir):
        result = run_psh('exec >out.txt; echo out; echo err >&2', temp_dir)
        assert result.returncode == 0
        assert result.stderr == 'err\n'
        assert read(os.path.join(temp_dir, 'out.txt')) == 'out\n'

    def test_pipeline_and_command_sub_after_exec(self, temp_dir):
        result = run_psh(
            'exec >out.txt; echo hello | tr a-z A-Z; x=$(echo sub); echo "got:$x"',
            temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'out.txt')) == 'HELLO\ngot:sub\n'


class TestExecStderrRedirect:
    """exec 2>file and fd duplication."""

    def test_stderr_interleaves_builtins_and_externals(self, temp_dir):
        result = run_psh(
            'exec 2>err.txt; echo e1 >&2; /bin/sh -c "echo e2 >&2"; echo e3 >&2',
            temp_dir)
        assert result.returncode == 0
        assert read(os.path.join(temp_dir, 'err.txt')) == 'e1\ne2\ne3\n'

    def test_exec_2_to_1(self, temp_dir):
        result = run_psh('exec 2>&1; echo err >&2; echo out', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'err\nout\n'

    def test_exec_1_to_2(self, temp_dir):
        result = run_psh('exec 1>&2; echo viaout', temp_dir)
        assert result.returncode == 0
        assert result.stderr == 'viaout\n'
        assert result.stdout == ''


class TestExecCustomFdRedirect:
    """exec n>file for n >= 3 (no Python stream counterpart)."""

    def test_custom_fd_builtin_and_external(self, temp_dir):
        result = run_psh(
            'exec 3>out3.txt; echo hi >&3; /bin/echo ext >&3; echo done',
            temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'done\n'
        assert read(os.path.join(temp_dir, 'out3.txt')) == 'hi\next\n'


class TestExecStdinRedirect:
    """exec <file / exec n<file."""

    def test_exec_stdin_then_builtin_read(self, temp_dir):
        with open(os.path.join(temp_dir, 'in.txt'), 'w') as f:
            f.write('from-file\n')
        result = run_psh('exec <in.txt; read line; echo "got:$line"', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'got:from-file\n'

    def test_exec_custom_input_fd_does_not_replace_stdin(self, temp_dir):
        with open(os.path.join(temp_dir, 'in.txt'), 'w') as f:
            f.write('custom-fd\n')
        result = run_psh(
            'exec 5<in.txt; read line <&5; echo "fd5:$line"; '
            'printf "stdin-ok\\n"',
            temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'fd5:custom-fd\nstdin-ok\n'


class TestExecWithCommandRedirect:
    """`exec CMD args redirects` — redirects apply to the exec'd program.

    Regression for reappraisal #10 R12.A: the with-command branch of
    `_handle_exec_builtin` ignored the node's redirections entirely (only the
    no-command branch applied them). Since exec replaces the process image, the
    redirections are applied permanently before the execvpe and carry into the
    new program; if the exec fails, they stay in effect (bash-verified).
    """

    def test_exec_command_stdout_to_file(self, temp_dir):
        # printf is an external here; output must land in the file, not stdout.
        result = run_psh('exec printf "hi\\n" > out.txt; echo unreached',
                         temp_dir)
        assert result.returncode == 0
        assert result.stdout == ''  # printf went to the file; exec replaced psh
        assert read(os.path.join(temp_dir, 'out.txt')) == 'hi\n'

    def test_exec_failure_diagnostic_is_redirected(self, temp_dir):
        # bash: `exec /no/such 2>/dev/null` is silent (the redirect applies even
        # though the exec fails), exit 127.
        result = run_psh('exec /no/such 2>/dev/null; echo after', temp_dir)
        assert result.returncode == 127
        assert result.stderr == ''
        assert result.stdout == ''  # 'after' is unreachable: exec consumed the line

    def test_exec_external_failure_stderr_redirected(self, temp_dir):
        result = run_psh('exec ls /nonexistent_xyz 2>err.txt', temp_dir)
        assert result.returncode != 0
        assert result.stderr == ''
        assert 'nonexistent_xyz' in read(os.path.join(temp_dir, 'err.txt'))

    def test_exec_noclobber_diagnostic_is_complete(self, temp_dir):
        """R13.A: an errno-less redirect OSError (noclobber) carries psh's own
        complete message. The exec handler previously printed the filename/
        strerror pair, which for these custom errors yielded 'psh: exec: None'.
        Now it prints the message verbatim (bash: 'TARGET: cannot overwrite
        existing file')."""
        result = run_psh(
            'set -C; echo a > ec.txt; exec > ec.txt', temp_dir)
        assert result.returncode == 1
        assert 'cannot overwrite existing file' in result.stderr
        assert 'None' not in result.stderr
        assert 'ec.txt' in result.stderr
