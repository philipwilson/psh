"""Wording of the "command cannot be executed" diagnostic, pinned to bash 5.2.

reappraisal #16 Tier-2 EXECUTOR-DIAGNOSTICS #2: a missing command given as a
*pathname* (one containing a slash) reports "No such file or directory", not
"command not found" — bash reserves "command not found" for a bare name that
PATH could not resolve. Exit codes were already correct (127 not found, 126
not executable) and are unchanged.

bash prefixes "bash: line N: " to these; psh uses its "psh: " prefix. The
tests pin psh's exact message and cross-check that bash on the same host
produces the same reason phrase and exit code.
"""

import subprocess
import sys


def run_psh(cmd, timeout=15):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=timeout)


def run_bash(cmd, timeout=15):
    return subprocess.run(['bash', '-c', cmd],
                          capture_output=True, text=True, timeout=timeout)


class TestExecFailureWording:
    """"command not found" only for bare names; pathnames say "No such file...""" # noqa: E501

    def test_slash_path_says_no_such_file(self):
        psh = run_psh('/no/such/path/cmd')
        assert psh.returncode == 127
        assert psh.stderr.strip() == 'psh: /no/such/path/cmd: No such file or directory'
        bash = run_bash('/no/such/path/cmd')
        assert bash.returncode == 127
        assert 'No such file or directory' in bash.stderr
        assert '/no/such/path/cmd' in bash.stderr

    def test_relative_path_says_no_such_file(self):
        psh = run_psh('./no_such_rel_cmd')
        assert psh.returncode == 127
        assert psh.stderr.strip() == 'psh: ./no_such_rel_cmd: No such file or directory'
        bash = run_bash('./no_such_rel_cmd')
        assert bash.returncode == 127
        assert 'No such file or directory' in bash.stderr

    def test_missing_under_existing_dir_says_no_such_file(self):
        psh = run_psh('/etc/definitely_not_here_xyz')
        assert psh.returncode == 127
        assert psh.stderr.strip() == 'psh: /etc/definitely_not_here_xyz: No such file or directory'

    def test_bare_name_still_says_command_not_found(self):
        psh = run_psh('nosuchcmd_xyz_12345')
        assert psh.returncode == 127
        assert psh.stderr.strip() == 'psh: nosuchcmd_xyz_12345: command not found'
        bash = run_bash('nosuchcmd_xyz_12345')
        assert bash.returncode == 127
        assert 'command not found' in bash.stderr

    def test_command_builtin_slash_path_says_no_such_file(self):
        """`command /no/such/x` routes through the same external-exec path."""
        psh = run_psh('command /no/such/x')
        assert psh.returncode == 127
        assert psh.stderr.strip() == 'psh: /no/such/x: No such file or directory'

    def test_slash_path_in_pipeline_says_no_such_file(self):
        """The in-pipeline inline-exec path shares report_exec_failure."""
        psh = run_psh('echo hi | /no/such/path/cmd')
        assert '/no/such/path/cmd: No such file or directory' in psh.stderr
        assert 'command not found' not in psh.stderr

    def test_directory_target_is_not_executable(self):
        """A slash path to an existing directory is 126 "Is a directory",
        unchanged by the ENOENT wording fix."""
        psh = run_psh('/etc')
        assert psh.returncode == 126
        assert psh.stderr.strip() == 'psh: /etc: Is a directory'
        bash = run_bash('/etc')
        assert bash.returncode == 126
        assert 'Is a directory' in bash.stderr
