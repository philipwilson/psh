"""Batch 10: redirection to file descriptors >= 3.

Builtins used to clobber stdout for any fd != 2, and external commands crashed
with EBADF before running when redirecting an unopened high fd. A command-level
`N>file` (N>=3) should open that fd to the file without touching stdout; since
the command doesn't write to fd N, the file ends up empty.
"""

import os


def _read(shell, name):
    with open(os.path.join(shell.state.variables['PWD'], name)) as f:
        return f.read()


class TestBuiltinHighFd:
    def test_echo_fd3_leaves_stdout_and_empties_file(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('echo hi 3>f3 > out.txt')
        assert _read(shell, "out.txt") == "hi\n"   # stdout unaffected
        assert _read(shell, "f3") == ""             # fd 3 file opened but unwritten

    def test_printf_fd5(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('printf "x\\n" 5>f5 > out.txt')
        assert _read(shell, "out.txt") == "x\n"
        assert _read(shell, "f5") == ""


class TestExternalHighFd:
    def test_external_fd7_does_not_crash(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        rc = shell.run_command('/bin/echo hi 7>f7 > out.txt')
        assert rc == 0
        assert _read(shell, "out.txt") == "hi\n"
        assert _read(shell, "f7") == ""

    def test_external_fd3(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        rc = shell.run_command('/bin/echo hi 3>f3 > out.txt')
        assert rc == 0
        assert _read(shell, "out.txt") == "hi\n"

# Note: explicitly writing to a high fd (e.g. `echo x 3>f >&3`) is verified
# against bash in tests/conformance/bash (subprocess), since a builtin writing
# to a raw fd via >&N can't be observed cleanly under pytest's in-process fd
# capture.
