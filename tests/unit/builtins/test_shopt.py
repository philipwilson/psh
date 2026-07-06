"""Tests for the shopt builtin."""



class TestShoptBasic:
    """Test basic shopt functionality."""

    def test_shopt_list_all(self, captured_shell):
        """Test listing all shopt options."""
        shell = captured_shell
        result = shell.run_command('shopt')
        assert result == 0
        output = shell.get_stdout()
        assert 'dotglob' in output
        assert 'nullglob' in output
        assert 'extglob' in output
        assert 'nocaseglob' in output
        assert 'globstar' in output

    def test_shopt_all_default_off(self, captured_shell):
        """Test that all shopt options default to off.

        Exceptions default ON: expand_aliases (psh always expands aliases — a
        parse-time token transform, the deliberate divergence from bash's
        interactive-only default) and globasciiranges (bash 5 default ON —
        bracket ranges use ASCII bounds regardless of locale).
        """
        shell = captured_shell
        result = shell.run_command('shopt')
        assert result == 0
        output = shell.get_stdout()
        for line in output.strip().split('\n'):
            if line.startswith(('expand_aliases', 'globasciiranges')):
                assert line.endswith('on')
            else:
                assert line.endswith('off')

    def test_shopt_show_specific(self, captured_shell):
        """Test showing a specific (unset) option.

        bash: the query form exits 1 when the named option is unset
        (the exit code reflects the option's state).
        """
        shell = captured_shell
        result = shell.run_command('shopt dotglob')
        assert result == 1
        output = shell.get_stdout().strip()
        # bash left-justifies the option name in a 15-char field before the tab.
        assert output == f"{'dotglob':<15}\toff"

    def test_shopt_invalid_option(self, captured_shell):
        """Test invalid option name."""
        shell = captured_shell
        result = shell.run_command('shopt nosuchoption')
        assert result == 1
        assert 'invalid shell option name' in shell.get_stderr()


class TestShoptSetUnset:
    """Test shopt -s and -u."""

    def test_shopt_set(self, captured_shell):
        """Test enabling an option."""
        shell = captured_shell
        result = shell.run_command('shopt -s dotglob')
        assert result == 0
        assert shell.state.options['dotglob'] is True

    def test_shopt_unset(self, captured_shell):
        """Test disabling an option."""
        shell = captured_shell
        shell.state.options['dotglob'] = True
        result = shell.run_command('shopt -u dotglob')
        assert result == 0
        assert shell.state.options['dotglob'] is False

    def test_shopt_set_multiple(self, captured_shell):
        """Test enabling multiple options at once."""
        shell = captured_shell
        result = shell.run_command('shopt -s dotglob nullglob')
        assert result == 0
        assert shell.state.options['dotglob'] is True
        assert shell.state.options['nullglob'] is True

    def test_shopt_set_shows_on(self, captured_shell):
        """Test that set option shows as on."""
        shell = captured_shell
        shell.run_command('shopt -s dotglob')
        shell.clear_output()
        result = shell.run_command('shopt dotglob')
        assert result == 0
        assert 'on' in shell.get_stdout()


class TestShoptPrint:
    """Test shopt -p (reusable form)."""

    def test_shopt_print_all(self, captured_shell):
        """Test printing all options in reusable form."""
        shell = captured_shell
        result = shell.run_command('shopt -p')
        assert result == 0
        output = shell.get_stdout()
        assert 'shopt -u dotglob' in output
        assert 'shopt -u nullglob' in output

    def test_shopt_print_enabled(self, captured_shell):
        """Test printing enabled option in reusable form."""
        shell = captured_shell
        shell.state.options['dotglob'] = True
        result = shell.run_command('shopt -p dotglob')
        assert result == 0
        assert 'shopt -s dotglob' in shell.get_stdout()


class TestShoptQuery:
    """Test shopt -q (silent query)."""

    def test_shopt_query_disabled(self, captured_shell):
        """Test querying disabled option returns 1."""
        shell = captured_shell
        result = shell.run_command('shopt -q dotglob')
        assert result == 1
        assert shell.get_stdout() == ''

    def test_shopt_query_enabled(self, captured_shell):
        """Test querying enabled option returns 0."""
        shell = captured_shell
        shell.state.options['dotglob'] = True
        result = shell.run_command('shopt -q dotglob')
        assert result == 0
        assert shell.get_stdout() == ''

    def test_shopt_query_multiple_all_enabled(self, captured_shell):
        """Test querying multiple enabled options returns 0."""
        shell = captured_shell
        shell.state.options['dotglob'] = True
        shell.state.options['nullglob'] = True
        result = shell.run_command('shopt -q dotglob nullglob')
        assert result == 0

    def test_shopt_query_multiple_one_disabled(self, captured_shell):
        """Test querying multiple options with one disabled returns 1."""
        shell = captured_shell
        shell.state.options['dotglob'] = True
        shell.state.options['nullglob'] = False
        result = shell.run_command('shopt -q dotglob nullglob')
        assert result == 1


class TestNullglobBehavior:
    """Test that nullglob option affects glob expansion."""

    def test_nullglob_default_literal(self, captured_shell):
        """Test default behavior: no matches returns literal pattern."""
        shell = captured_shell
        result = shell.run_command('echo /nonexistent_path_xyz_*.foo')
        assert result == 0
        assert '/nonexistent_path_xyz_*.foo' in shell.get_stdout()

    def test_nullglob_enabled_empty(self, captured_shell):
        """Test nullglob: no matches returns nothing."""
        shell = captured_shell
        shell.state.options['nullglob'] = True
        result = shell.run_command('echo /nonexistent_path_xyz_*.foo')
        assert result == 0
        output = shell.get_stdout().strip()
        # echo with no args prints empty line
        assert output == ''
        shell.state.options['nullglob'] = False
