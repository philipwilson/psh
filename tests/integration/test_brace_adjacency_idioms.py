"""
Integration tests for brace expansion adjacent to other expansions
(reappraisal #15 B1/B2): the everyday `cp "$f"{,.bak}` backup idiom and
process-substitution adjacency. Verified against bash 5.2
(tmp/brace_truth_table.sh).
"""

import os


class TestBackupIdiom:
    def test_cp_quoted_var_brace_backup(self, isolated_shell_with_temp_dir):
        """cp "$f"{,.bak} must expand $f, copying the file — not pass a
        literal $f to cp."""
        shell = isolated_shell_with_temp_dir
        shell.run_command('f=important.txt; echo data > "$f"')
        exit_code = shell.run_command('f=important.txt; cp "$f"{,.bak}')
        assert exit_code == 0
        cwd = shell.state.variables['PWD']
        with open(os.path.join(cwd, 'important.txt.bak')) as fh:
            assert fh.read() == 'data\n'

    def test_mv_braced_var_rename(self, isolated_shell_with_temp_dir):
        """${f}{...} form: brace-delimited expansions join adjacency too."""
        shell = isolated_shell_with_temp_dir
        shell.run_command('f=log; echo x > "$f.old"')
        exit_code = shell.run_command('f=log; mv ${f}{.old,.new}')
        assert exit_code == 0
        cwd = shell.state.variables['PWD']
        assert os.path.exists(os.path.join(cwd, 'log.new'))
        assert not os.path.exists(os.path.join(cwd, 'log.old'))


class TestProcessSubAdjacency:
    def test_process_sub_with_brace_suffix(self, isolated_shell_with_temp_dir):
        """<(cmd){a,b} duplicates the process substitution per alternative
        (bash: /dev/fd/63a /dev/fd/62b)."""
        shell = isolated_shell_with_temp_dir
        shell.run_command('echo <(true){a,b} > out.txt')
        cwd = shell.state.variables['PWD']
        with open(os.path.join(cwd, 'out.txt')) as fh:
            words = fh.read().split()
        assert len(words) == 2
        assert words[0].endswith('a') and words[1].endswith('b')
        assert all(w.startswith('/dev/fd/') for w in words)
