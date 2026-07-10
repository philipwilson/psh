"""Unit tests for the ``hash`` builtin and the command hash table.

Every behavior here is pinned to bash 5.2 probes (2026-06-13) — see the
probe ledger in psh/builtins/hash_builtin.py. The executor-side pieces
(table population on execution, hit counts, the checkhash re-verify and
the default stale-path 127) are covered in
tests/integration/command_resolution/test_hash_execution.py.
"""


class TestHashListing:
    def test_empty_table_message_on_stdout(self, captured_shell):
        """bash: `hash` with an empty table prints the message on STDOUT
        (not stderr) and succeeds."""
        rc = captured_shell.run_command('hash')
        assert rc == 0
        assert captured_shell.get_stdout() == 'hash: hash table empty\n'
        assert captured_shell.get_stderr() == ''

    def test_listing_format(self, captured_shell):
        """bash format: a 'hits\\tcommand' header, then %4d\\t%s rows."""
        rc = captured_shell.run_command('hash ls')
        assert rc == 0
        captured_shell.clear_output()
        rc = captured_shell.run_command('hash')
        assert rc == 0
        lines = captured_shell.get_stdout().splitlines()
        assert lines[0] == 'hits\tcommand'
        # `hash NAME` remembers with ZERO hits (bash)
        assert lines[1] == '   0\t' + captured_shell.state.command_hash.entries()[0][1]
        assert lines[1].endswith('/ls')


class TestHashNames:
    def test_hash_name_caches_path(self, captured_shell):
        rc = captured_shell.run_command('hash ls')
        assert rc == 0
        assert 'ls' in captured_shell.state.command_hash

    def test_miss_reports_not_found_rc_1(self, captured_shell):
        rc = captured_shell.run_command('hash nosuchcmd_zz9')
        assert rc == 1
        assert 'hash: nosuchcmd_zz9: not found' in captured_shell.get_stderr()

    def test_mixed_hit_and_miss(self, captured_shell):
        """bash: found names are still hashed; status reflects the miss."""
        rc = captured_shell.run_command('hash ls nosuchcmd_zz9 cat')
        assert rc == 1
        table = captured_shell.state.command_hash
        assert 'ls' in table and 'cat' in table

    def test_builtin_function_and_slash_names_skipped_silently(
            self, captured_shell):
        """bash: `hash echo` (builtin), `hash f` (function) and
        `hash /bin/ls` succeed without adding table entries."""
        captured_shell.run_command('f() { :; }')
        rc = captured_shell.run_command('hash echo f /bin/ls')
        assert rc == 0
        assert len(captured_shell.state.command_hash) == 0


class TestHashOptions:
    def test_dash_r_clears(self, captured_shell):
        captured_shell.run_command('hash ls cat')
        rc = captured_shell.run_command('hash -r')
        assert rc == 0
        assert len(captured_shell.state.command_hash) == 0

    def test_dash_r_then_names_hashes_them(self, captured_shell):
        """bash: `hash -r NAME` clears, then hashes NAME."""
        captured_shell.run_command('hash cat')
        rc = captured_shell.run_command('hash -r ls')
        assert rc == 0
        table = captured_shell.state.command_hash
        assert 'ls' in table and 'cat' not in table

    def test_dash_t_single_prints_bare_path(self, captured_shell):
        captured_shell.run_command('hash ls')
        captured_shell.clear_output()
        rc = captured_shell.run_command('hash -t ls')
        assert rc == 0
        out = captured_shell.get_stdout()
        assert out.endswith('/ls\n') and '\t' not in out

    def test_dash_t_multiple_prints_name_tab_path(self, captured_shell):
        captured_shell.run_command('hash ls cat')
        captured_shell.clear_output()
        rc = captured_shell.run_command('hash -t ls cat')
        assert rc == 0
        lines = captured_shell.get_stdout().splitlines()
        assert lines[0].startswith('ls\t') and lines[0].endswith('/ls')
        assert lines[1].startswith('cat\t') and lines[1].endswith('/cat')

    def test_dash_t_does_not_path_search(self, captured_shell):
        """bash: -t consults only the table — an unhashed ls is
        'not found', rc 1."""
        rc = captured_shell.run_command('hash -t ls')
        assert rc == 1
        assert 'hash: ls: not found' in captured_shell.get_stderr()

    def test_dash_t_lookup_counts_as_hit(self, captured_shell):
        """bash quirk: the -t lookup itself increments the hit count."""
        captured_shell.run_command('hash ls; hash -t ls')
        captured_shell.clear_output()
        captured_shell.run_command('hash')
        assert '   1\t' in captured_shell.get_stdout()

    def test_dash_t_without_names_errors(self, captured_shell):
        """bash: 'hash: -t: option requires an argument', rc 1."""
        rc = captured_shell.run_command('hash -t')
        assert rc == 1
        assert '-t: option requires an argument' in captured_shell.get_stderr()

    def test_dash_d_deletes_one(self, captured_shell):
        captured_shell.run_command('hash ls cat')
        rc = captured_shell.run_command('hash -d ls')
        assert rc == 0
        table = captured_shell.state.command_hash
        assert 'ls' not in table and 'cat' in table

    def test_dash_d_missing_name_rc_1(self, captured_shell):
        """bash: a populated table reports the miss..."""
        captured_shell.run_command('hash ls')
        rc = captured_shell.run_command('hash -d nosuchcmd_zz9')
        assert rc == 1
        assert 'hash: nosuchcmd_zz9: not found' in captured_shell.get_stderr()

    def test_dash_d_on_empty_table_silently_succeeds(self, captured_shell):
        """...but -d against an EMPTY table is rc 0, no message (bash
        quirk, probe-verified)."""
        rc = captured_shell.run_command('hash -d nosuchcmd_zz9')
        assert rc == 0
        assert captured_shell.get_stderr() == ''

    def test_dash_l_reusable_format(self, captured_shell):
        captured_shell.run_command('hash ls')
        captured_shell.clear_output()
        rc = captured_shell.run_command('hash -l')
        assert rc == 0
        out = captured_shell.get_stdout()
        assert out.startswith('builtin hash -p ') and out.endswith(' ls\n')

    def test_dash_l_empty_table_prints_nothing(self, captured_shell):
        """bash: -l on an empty table prints nothing (no 'empty' message)."""
        rc = captured_shell.run_command('hash -l')
        assert rc == 0
        assert captured_shell.get_stdout() == ''

    def test_dash_p_hashes_explicit_path_unverified(self, captured_shell):
        """bash: -p records the path without checking it exists."""
        rc = captured_shell.run_command('hash -p /nonexistent/xyz myname')
        assert rc == 0
        captured_shell.clear_output()
        rc = captured_shell.run_command('hash -t myname')
        assert rc == 0
        assert captured_shell.get_stdout() == '/nonexistent/xyz\n'

    def test_invalid_option_usage_rc_2(self, captured_shell):
        rc = captured_shell.run_command('hash -v')
        assert rc == 2
        err = captured_shell.get_stderr()
        assert 'hash: -v: invalid option' in err
        assert 'usage: hash [-lr] [-p pathname] [-dt] [name ...]' in err


class TestHashingDisabled:
    def test_set_plus_h_disables_hash_builtin(self, captured_shell):
        """bash: with `set +h`, hash fails with 'hashing disabled', rc 1."""
        rc = captured_shell.run_command('set +h; hash ls')
        assert rc == 1
        assert 'hash: hashing disabled' in captured_shell.get_stderr()

    def test_hashall_on_by_default(self, captured_shell):
        """bash has -h (hashall) ON by default; $- contains 'h'."""
        captured_shell.run_command('echo $-')
        assert 'h' in captured_shell.get_stdout()


class TestPathInvalidation:
    def test_plain_path_assignment_clears(self, captured_shell):
        """bash: even `PATH=$PATH` empties the table."""
        captured_shell.run_command('hash ls')
        assert 'ls' in captured_shell.state.command_hash
        captured_shell.run_command('PATH=$PATH')
        assert len(captured_shell.state.command_hash) == 0

    def test_export_path_clears(self, captured_shell):
        captured_shell.run_command('hash ls')
        captured_shell.run_command('export PATH="$PATH"')
        assert len(captured_shell.state.command_hash) == 0

    def test_unset_path_clears(self, captured_shell):
        captured_shell.run_command('hash ls')
        captured_shell.run_command('unset PATH')
        assert len(captured_shell.state.command_hash) == 0

    def test_local_path_in_function_clears(self, captured_shell):
        """bash clears on `local PATH=...` too (probe-verified)."""
        captured_shell.run_command('hash ls')
        captured_shell.run_command('f() { local PATH=/usr/bin; }; f')
        assert len(captured_shell.state.command_hash) == 0

    def test_cd_does_not_clear(self, isolated_shell_with_temp_dir):
        """bash keeps the table across cd (absolute paths stay valid)."""
        shell = isolated_shell_with_temp_dir
        shell.run_command('hash ls')
        shell.run_command('cd /')
        assert 'ls' in shell.state.command_hash
