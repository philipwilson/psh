"""
Unit tests for alias builtins (alias, unalias).

Tests cover:
- Creating aliases
- Listing aliases
- Using aliases
- Removing aliases
- Error conditions
"""



class TestAliasBuiltin:
    """Test alias builtin functionality."""

    def test_create_simple_alias(self, shell, capsys):
        """Test creating a simple alias."""
        shell.run_command('alias ll="ls -l"')
        # Verify alias was created by running it
        shell.run_command('alias')
        captured = capsys.readouterr()
        assert 'll=' in captured.out
        assert 'ls -l' in captured.out

    def test_list_all_aliases(self, shell, capsys):
        """Test listing all aliases."""
        # Create some aliases
        shell.run_command('alias l="ls"')
        shell.run_command('alias la="ls -a"')

        # List all aliases
        shell.run_command('alias')
        captured = capsys.readouterr()
        assert 'l=' in captured.out
        assert 'la=' in captured.out

    def test_show_specific_alias(self, shell, capsys):
        """Test showing a specific alias."""
        shell.run_command('alias mytest="echo test"')
        shell.run_command('alias mytest')
        captured = capsys.readouterr()
        assert 'mytest=' in captured.out
        assert 'echo test' in captured.out

    def test_use_alias(self, shell, capsys):
        """Test using an alias."""
        shell.run_command('alias greet="echo Hello"')
        shell.run_command('greet World')
        captured = capsys.readouterr()
        assert captured.out.strip() == "Hello World"

    def test_alias_with_quotes(self, shell, capsys):
        """Test alias with quotes in command."""
        shell.run_command('alias say=\'echo "Hello World"\'')
        shell.run_command('say')
        captured = capsys.readouterr()
        assert captured.out.strip() == 'Hello World'

    def test_alias_with_pipe(self):
        """Test alias with pipe.

        Uses subprocess because alias-expanded pipelines fork child
        processes whose output isn't captured by in-process fixtures.
        """
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'alias count="echo 1 2 3 | wc -w"\ncount'],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "3"

    def test_alias_expansion_at_start_only(self, shell, capsys):
        """Test alias expansion only happens at command start."""
        shell.run_command('alias myecho="echo"')
        shell.run_command('myecho test')  # Should expand
        captured = capsys.readouterr()
        assert captured.out.strip() == "test"

        shell.run_command('echo myecho')  # Should not expand
        captured = capsys.readouterr()
        assert captured.out.strip() == "myecho"

    def test_alias_recursive_prevention(self, shell, capsys):
        """A self-referential alias expands once, not infinitely."""
        shell.run_command('alias echo="echo x"')
        capsys.readouterr()
        result = shell.run_command('echo hi')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == 'x hi'
        # Command should complete (not hang)

    def test_alias_overwrite(self, shell, capsys):
        """Test overwriting an existing alias."""
        shell.run_command('alias mytest="echo old"')
        shell.run_command('alias mytest="echo new"')
        shell.run_command('mytest')
        captured = capsys.readouterr()
        assert captured.out.strip() == "new"

    def test_invalid_alias_name(self, shell, capsys):
        """Test invalid alias names."""
        # Numeric names should fail
        exit_code = shell.run_command('alias 123="echo test"')
        assert exit_code != 0

        # Names with dashes might be accepted by some shells
        # PSH accepts them, which is okay

    def test_alias_reserved_word(self, shell, capsys):
        """Test aliasing reserved words."""
        # Should not be able to alias reserved words
        exit_code = shell.run_command('alias if="echo if"')
        assert exit_code != 0


class TestUnaliasBuiltin:
    """Test unalias builtin functionality."""

    def test_unalias_single(self, shell, capsys):
        """Test removing a single alias."""
        # Create and remove alias
        shell.run_command('alias mytest="echo test"')
        shell.run_command('unalias mytest')

        # Verify it's gone
        exit_code = shell.run_command('mytest')
        assert exit_code != 0
        # Note: error message may not be captured due to output handling issue

    def test_unalias_multiple(self, shell, capsys):
        """Test removing multiple aliases."""
        # Create multiple aliases
        shell.run_command('alias a1="echo 1"')
        shell.run_command('alias a2="echo 2"')
        shell.run_command('alias a3="echo 3"')

        # Remove two of them
        shell.run_command('unalias a1 a3')

        # Verify a1 and a3 are gone
        exit_code = shell.run_command('a1')
        assert exit_code != 0
        exit_code = shell.run_command('a3')
        assert exit_code != 0

        # Verify a2 still works
        shell.run_command('a2')
        captured = capsys.readouterr()
        assert captured.out.strip() == "2"

    def test_unalias_all(self, shell, capsys):
        """Test removing all aliases."""
        # Create some aliases
        shell.run_command('alias a1="echo 1"')
        shell.run_command('alias a2="echo 2"')

        # Remove all
        shell.run_command('unalias -a')

        # Verify all are gone
        shell.run_command('alias')
        captured = capsys.readouterr()
        # Output should be empty or minimal
        assert 'a1=' not in captured.out
        assert 'a2=' not in captured.out

    def test_unalias_nonexistent(self, shell, capsys):
        """Test removing non-existent alias."""
        exit_code = shell.run_command('unalias nonexistent')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'not found' in captured.err or 'no such' in captured.err

    def test_unalias_no_args(self, shell, capsys):
        """Test unalias with no arguments."""
        exit_code = shell.run_command('unalias')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'usage' in captured.err.lower() or 'operand' in captured.err


class TestAliasExpansion:
    """Test alias expansion behavior."""

    def test_alias_with_args(self, tmp_path):
        """Test alias with additional arguments.

        Uses subprocess because alias-expanded external commands fork
        child processes whose output isn't captured by in-process fixtures.
        """
        import subprocess
        import sys
        file1 = tmp_path / "file1"
        file2 = tmp_path / "file2"
        file1.touch()
        file2.touch()
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             f'alias myls="ls"\nmyls {file1} {file2}'],
            capture_output=True, text=True
        )
        assert 'file1' in result.stdout
        assert 'file2' in result.stdout

    def test_alias_chain(self, shell, capsys):
        """Test chained aliases."""
        shell.run_command('alias a1="echo"')
        shell.run_command('alias a2="a1"')
        shell.run_command('a2 test')
        captured = capsys.readouterr()
        assert captured.out.strip() == "test"

    def test_alias_trailing_space(self, shell, capsys):
        """A trailing space in an alias makes the next word alias-expandable too."""
        shell.run_command('alias a="echo "')
        shell.run_command('alias b="hi"')
        capsys.readouterr()
        result = shell.run_command('a b')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == 'hi'
        # This is complex behavior that PSH might not support


class TestAliasBashConformance:
    """Probe battery pinned against bash 5.2 (stdout/stderr/rc).

    Each test mirrors a bash probe; the expected values are bash's
    (modulo bash's "bash: line N: " stderr prefix, which psh renders
    as just the builtin name prefix).
    """

    def test_list_empty(self, captured_shell):
        assert captured_shell.run_command('alias') == 0
        assert captured_shell.get_stdout() == ""
        assert captured_shell.get_stderr() == ""

    def test_dash_p_empty_table(self, captured_shell):
        assert captured_shell.run_command('alias -p') == 0
        assert captured_shell.get_stdout() == ""

    def test_dash_p_empty_table_skips_operands(self, captured_shell):
        # bash quirk: with -p and an empty alias table, operands are
        # skipped entirely and the return code is 0.
        assert captured_shell.run_command('alias -p nosuch') == 0
        assert captured_shell.get_stdout() == ""
        assert captured_shell.get_stderr() == ""

    def test_dash_p_lists_all(self, captured_shell):
        captured_shell.run_command("alias x='echo hi'")
        captured_shell.clear_output()
        assert captured_shell.run_command('alias -p') == 0
        assert captured_shell.get_stdout() == "alias x='echo hi'\n"

    def test_dash_p_with_name_operand(self, captured_shell):
        # bash: -p prints all aliases, then the operand is shown too.
        captured_shell.run_command("alias x='echo hi'")
        captured_shell.clear_output()
        assert captured_shell.run_command('alias -p x') == 0
        assert captured_shell.get_stdout() == (
            "alias x='echo hi'\nalias x='echo hi'\n")

    def test_dash_p_nosuch_nonempty_table(self, captured_shell):
        captured_shell.run_command("alias x='echo hi'")
        captured_shell.clear_output()
        assert captured_shell.run_command('alias -p nosuch') == 1
        assert captured_shell.get_stdout() == "alias x='echo hi'\n"
        assert "alias: nosuch: not found" in captured_shell.get_stderr()

    def test_invalid_option_rc2(self, captured_shell):
        assert captured_shell.run_command('alias -q') == 2
        err = captured_shell.get_stderr()
        assert "alias: -q: invalid option" in err
        assert "usage: alias [-p] [name[=value] ... ]" in err

    def test_invalid_option_in_cluster_rc2(self, captured_shell):
        assert captured_shell.run_command('alias -pq') == 2
        assert "alias: -q: invalid option" in captured_shell.get_stderr()

    def test_show_one(self, captured_shell):
        captured_shell.run_command("alias x='echo hi'")
        captured_shell.clear_output()
        assert captured_shell.run_command('alias x') == 0
        assert captured_shell.get_stdout() == "alias x='echo hi'\n"

    def test_nosuch_rc1(self, captured_shell):
        assert captured_shell.run_command('alias nosuch') == 1
        assert "alias: nosuch: not found" in captured_shell.get_stderr()

    def test_multiple_definitions_one_call(self, captured_shell):
        assert captured_shell.run_command(
            "alias x='echo hi' y='echo y'") == 0
        captured_shell.clear_output()
        captured_shell.run_command('alias')
        assert captured_shell.get_stdout() == (
            "alias x='echo hi'\nalias y='echo y'\n")

    def test_embedded_single_quote_bash_quoting(self, captured_shell):
        # bash renders an embedded single quote as '\'' in reusable output:
        #   alias q='it'\''s'
        captured_shell.run_command("alias q='it'\\''s'")
        captured_shell.clear_output()
        assert captured_shell.run_command('alias q') == 0
        assert captured_shell.get_stdout() == "alias q='it'\\''s'\n"

    def test_quoted_value_keeps_inner_quotes(self, captured_shell):
        # alias x="'echo hi'" -- the single quotes are part of the value.
        captured_shell.run_command('alias x="\'echo hi\'"')
        captured_shell.clear_output()
        assert captured_shell.run_command('alias x') == 0
        assert captured_shell.get_stdout() == "alias x=''\\''echo hi'\\'''\n"

    def test_escaped_quote_words_treated_independently(self, captured_shell):
        # alias x=\'foo bar\'  -- two operands after tokenization: the
        # first defines x with value 'foo (literal quote retained); the
        # second is a lookup of "bar'" which is not found (bash behavior;
        # the old cross-argument quote-rejoin scanner glued these).
        assert captured_shell.run_command("alias x=\\'foo bar\\'") == 1
        assert "alias: bar': not found" in captured_shell.get_stderr()
        captured_shell.clear_output()
        captured_shell.run_command('alias x')
        assert captured_shell.get_stdout() == "alias x=''\\''foo'\n"

    def test_double_dash_ends_options(self, captured_shell):
        assert captured_shell.run_command("alias -- x='echo dd'") == 0
        captured_shell.clear_output()
        captured_shell.run_command('alias x')
        assert captured_shell.get_stdout() == "alias x='echo dd'\n"

    def test_empty_value(self, captured_shell):
        assert captured_shell.run_command('alias x=') == 0
        captured_shell.clear_output()
        assert captured_shell.run_command('alias x') == 0
        assert captured_shell.get_stdout() == "alias x=''\n"

    def test_leading_equals_is_lookup_not_assignment(self, captured_shell):
        # bash treats '=foo' as a name lookup, not an empty-name assignment.
        assert captured_shell.run_command('alias =foo') == 1
        assert "alias: =foo: not found" in captured_shell.get_stderr()

    def test_invalid_name_message_and_rc(self, captured_shell):
        assert captured_shell.run_command("alias 'a b'=foo") == 1
        assert "alias: `a b': invalid alias name" in captured_shell.get_stderr()

    def test_invalid_name_does_not_block_valid(self, captured_shell):
        assert captured_shell.run_command(
            "alias 'a b'=foo good='echo g'") == 1
        captured_shell.clear_output()
        assert captured_shell.run_command('alias good') == 0
        assert captured_shell.get_stdout() == "alias good='echo g'\n"

    def test_show_and_define_same_call(self, captured_shell):
        captured_shell.run_command("alias x='echo 1'")
        captured_shell.clear_output()
        assert captured_shell.run_command("alias x y='echo 2'") == 0
        assert captured_shell.get_stdout() == "alias x='echo 1'\n"
        captured_shell.clear_output()
        assert captured_shell.run_command('alias y') == 0
        assert captured_shell.get_stdout() == "alias y='echo 2'\n"

    def test_listing_is_sorted(self, captured_shell):
        captured_shell.run_command("alias zz='2' aa='1'")
        captured_shell.clear_output()
        captured_shell.run_command('alias')
        assert captured_shell.get_stdout() == "alias aa='1'\nalias zz='2'\n"


class TestUnaliasBashConformance:
    """unalias probe battery pinned against bash 5.2."""

    def test_no_args_usage_rc2(self, captured_shell):
        assert captured_shell.run_command('unalias') == 2
        assert ("unalias: usage: unalias [-a] name [name ...]"
                in captured_shell.get_stderr())

    def test_invalid_option_rc2(self, captured_shell):
        assert captured_shell.run_command('unalias -q') == 2
        err = captured_shell.get_stderr()
        assert "unalias: -q: invalid option" in err
        assert "usage: unalias [-a] name [name ...]" in err

    def test_invalid_option_in_cluster_rc2(self, captured_shell):
        assert captured_shell.run_command('unalias -aq') == 2
        assert "unalias: -q: invalid option" in captured_shell.get_stderr()

    def test_nosuch_rc1(self, captured_shell):
        assert captured_shell.run_command('unalias nosuch') == 1
        assert "unalias: nosuch: not found" in captured_shell.get_stderr()

    def test_mixed_removes_found_rc1(self, captured_shell):
        captured_shell.run_command("alias a='1' b='2'")
        captured_shell.clear_output()
        assert captured_shell.run_command('unalias a nosuch b') == 1
        assert "unalias: nosuch: not found" in captured_shell.get_stderr()
        captured_shell.clear_output()
        captured_shell.run_command('alias')
        assert captured_shell.get_stdout() == ""

    def test_dash_a_ignores_operands(self, captured_shell):
        captured_shell.run_command("alias x='a'")
        captured_shell.clear_output()
        assert captured_shell.run_command('unalias -a nosuch') == 0
        assert captured_shell.get_stderr() == ""

    def test_dash_a_empty_table_rc0(self, captured_shell):
        assert captured_shell.run_command('unalias -a') == 0

    def test_double_dash_ends_options(self, captured_shell):
        assert captured_shell.run_command('unalias -- nosuch2') == 1
        assert "unalias: nosuch2: not found" in captured_shell.get_stderr()
