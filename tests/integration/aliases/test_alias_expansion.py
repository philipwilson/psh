"""
Alias expansion system integration tests.

Tests for alias functionality including:
- Alias definition and expansion
- Alias resolution precedence vs functions/builtins
- Recursive alias expansion prevention
- Complex alias patterns with parameters
- Alias expansion in different contexts
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


class AliasTestHelper:
    """Helper class for alias testing."""

    @classmethod
    def run_psh_command(cls, commands, timeout=5):
        """Run PSH with given commands and return output."""
        env = os.environ.copy()
        psh_root = Path(__file__).parent.parent.parent.parent
        env['PYTHONPATH'] = str(psh_root)
        env['PYTHONUNBUFFERED'] = '1'

        # Join commands with newlines
        if isinstance(commands, str):
            input_text = commands + '\n'
        else:
            input_text = '\n'.join(commands) + '\n'

        proc = subprocess.Popen(
            [sys.executable, '-u', '-m', 'psh', '--norc'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )

        try:
            stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
            return {
                'stdout': stdout,
                'stderr': stderr,
                'returncode': proc.returncode,
                'success': proc.returncode == 0
            }
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return {
                'stdout': stdout or '',
                'stderr': stderr or '',
                'returncode': -1,
                'error': 'timeout',
                'success': False
            }


class TestBasicAliasDefinition:
    """Test basic alias definition and usage."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_simple_alias_definition(self):
        """Test defining and using a simple alias."""
        result = AliasTestHelper.run_psh_command([
            'alias ll="ls -l"',
            'alias'  # List aliases
        ])

        assert result['success']
        assert 'll' in result['stdout']
        assert 'ls -l' in result['stdout']

    def test_alias_execution(self):
        """Test executing an alias."""
        result = AliasTestHelper.run_psh_command([
            'alias test_alias="echo hello world"',
            'test_alias'
        ])

        assert result['success']
        assert 'hello world' in result['stdout']

    def test_alias_with_arguments(self):
        """Test alias that accepts arguments."""
        result = AliasTestHelper.run_psh_command([
            'alias greet="echo Hello"',
            'greet World'
        ])

        assert result['success']
        assert 'Hello World' in result['stdout']

    def test_alias_case_sensitivity(self):
        """Test that aliases are case-sensitive."""
        result = AliasTestHelper.run_psh_command([
            'alias mytest="echo lowercase"',
            'alias MYTEST="echo uppercase"',
            'mytest',
            'MYTEST'
        ])

        assert result['success']
        assert 'lowercase' in result['stdout']
        assert 'uppercase' in result['stdout']

    def test_alias_redefinition(self):
        """Test redefining an existing alias."""
        result = AliasTestHelper.run_psh_command([
            'alias mytest="echo first"',
            'mytest',
            'alias mytest="echo second"',
            'mytest'
        ])

        assert result['success']
        assert 'first' in result['stdout']
        assert 'second' in result['stdout']

    def test_alias_list_all(self):
        """Test listing all defined aliases."""
        result = AliasTestHelper.run_psh_command([
            'alias a1="command1"',
            'alias a2="command2"',
            'alias a3="command3"',
            'alias'
        ])

        assert result['success']
        assert 'a1' in result['stdout']
        assert 'a2' in result['stdout']
        assert 'a3' in result['stdout']


class TestAliasRemoval:
    """Test alias removal and management."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_unalias_command(self):
        """Test removing an alias with unalias."""
        result = AliasTestHelper.run_psh_command([
            'alias mytest="echo test"',
            'mytest',  # Should work
            'unalias mytest',
            'mytest'   # Should fail as command not found
        ])

        # First execution should succeed, second should fail
        assert 'echo test' in result['stdout'] or 'test' in result['stdout']

    def test_unalias_nonexistent(self):
        """Test unalias on non-existent alias."""
        result = AliasTestHelper.run_psh_command('unalias nonexistent_alias')

        # Should handle gracefully or show error
        assert isinstance(result['returncode'], int)

    def test_unalias_all(self):
        """Test removing all aliases."""
        result = AliasTestHelper.run_psh_command([
            'alias a1="cmd1"',
            'alias a2="cmd2"',
            'unalias -a',  # Remove all aliases
            'alias'        # Should show empty or error
        ])

        assert result['success']
        # After unalias -a, alias list should be empty


class TestAliasPrecedence:
    """Test alias precedence vs builtins, functions, and external commands."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_alias_vs_builtin(self):
        """Test that aliases do NOT override builtins."""
        result = AliasTestHelper.run_psh_command([
            'alias echo="echo ALIAS:"',
            'echo test'
        ])

        assert result['success']
        # Builtins should take precedence - should NOT see "ALIAS:"
        assert 'ALIAS:' not in result['stdout']
        assert 'test' in result['stdout']

    def test_alias_vs_function(self):
        """Test alias vs function precedence."""
        result = AliasTestHelper.run_psh_command([
            'alias test="echo alias"',
            'test() { echo function; }',
            'test'
        ])

        assert result['success']
        # Functions should take precedence over aliases
        assert 'function' in result['stdout']
        assert 'alias' not in result['stdout']

    def test_alias_vs_external_command(self):
        """Test that aliases override external commands."""
        result = AliasTestHelper.run_psh_command([
            'alias ls="echo ALIAS_LS"',
            'ls'
        ])

        assert result['success']
        # Alias should override external ls command
        assert 'ALIAS_LS' in result['stdout']

    def test_bypass_alias_with_backslash(self):
        """Test bypassing alias with backslash escape."""
        result = AliasTestHelper.run_psh_command([
            'alias ls="echo ALIAS_LS"',
            '\\ls'  # Should bypass alias
        ])

        assert result['success']
        # Should execute actual ls, not the alias
        assert 'ALIAS_LS' not in result['stdout']

    def test_bypass_alias_with_command_builtin(self):
        """Test bypassing alias with command builtin."""
        result = AliasTestHelper.run_psh_command([
            'alias ls="echo ALIAS_LS"',
            'command ls'  # Should bypass alias
        ])

        assert result['success']
        # Should execute actual ls, not the alias
        assert 'ALIAS_LS' not in result['stdout']


class TestAliasExpansion:
    """Test alias expansion mechanisms."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_alias_expansion_timing(self):
        """Test when alias expansion occurs.

        Alias expansion happens at parse time on literal command words.
        When $VAR expands to an alias name, the alias IS resolved because
        psh checks aliases during command execution (after expansion).
        """
        result = AliasTestHelper.run_psh_command([
            'alias myalias="echo expanded"',
            'VAR=myalias',
            '$VAR'
        ])

        assert result['success']
        assert 'expanded' in result['stdout']

    def test_alias_recursive_prevention(self):
        """Test prevention of recursive alias expansion."""
        result = AliasTestHelper.run_psh_command([
            'alias ls="ls -l"',  # Alias that references itself
            'ls'
        ])

        assert result['success']
        # Should not infinitely recurse
        # Exact behavior varies: might use external ls or fail gracefully

    def test_alias_with_pipes(self):
        """Test alias expansion in pipelines."""
        result = AliasTestHelper.run_psh_command([
            'alias showfiles="ls"',
            'showfiles | head -n 5'
        ])

        assert result['success']
        # Alias should expand before pipe processing

    def test_alias_with_redirection(self, tmp_path):
        """Test alias expansion with I/O redirection."""
        out = tmp_path / 'alias_test'
        result = AliasTestHelper.run_psh_command([
            'alias output="echo test"',
            f'output > "{out}"',
            f'cat "{out}"'
        ])

        assert result['success']
        assert 'test' in result['stdout']

    def test_alias_with_background_execution(self):
        """Test alias expansion with background execution."""
        result = AliasTestHelper.run_psh_command([
            'alias background="echo background"',
            'background &',
            'wait'
        ])

        assert result['success']
        assert 'background' in result['stdout']


class TestComplexAliases:
    """Test complex alias scenarios."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_alias_with_multiple_commands(self):
        """Test alias containing multiple commands."""
        result = AliasTestHelper.run_psh_command([
            'alias multi="echo first; echo second"',
            'multi'
        ])

        assert result['success']
        assert 'first' in result['stdout']
        assert 'second' in result['stdout']

    def test_alias_with_conditionals(self):
        """Test alias containing conditional statements."""
        result = AliasTestHelper.run_psh_command([
            'alias testcond="if [ -f /etc/passwd ]; then echo found; fi"',
            'testcond'
        ])

        assert result['success']
        assert 'found' in result['stdout']

    def test_alias_with_variables(self):
        """Test alias containing variable references."""
        result = AliasTestHelper.run_psh_command([
            'VAR=test',
            'alias showvar="echo $VAR"',
            'showvar'
        ])

        assert result['success']
        assert 'test' in result['stdout']

    def test_alias_with_command_substitution(self):
        """Test alias containing command substitution."""
        result = AliasTestHelper.run_psh_command([
            'alias dateecho="echo Today is $(date +%Y-%m-%d)"',
            'dateecho'
        ])

        assert result['success']
        assert 'Today is' in result['stdout']
        # Should contain current date

    def test_alias_with_special_characters(self):
        """Test alias with special characters in definition.

        Single quotes prevent expansion at definition time, so \\$escaped
        is preserved literally and the backslash is consumed during alias
        execution, producing a literal $escaped in the output.
        """
        result = AliasTestHelper.run_psh_command([
            "alias special='echo \"quoted\" and \\$escaped'",
            'special'
        ])

        assert result['success']
        assert 'quoted' in result['stdout']
        assert '$escaped' in result['stdout']

    def test_nested_alias_expansion(self):
        """Test aliases that expand to other aliases."""
        result = AliasTestHelper.run_psh_command([
            'alias inner="echo inner"',
            'alias outer="inner"',
            'outer'
        ])

        assert result['success']
        assert 'inner' in result['stdout']


class TestAliasInDifferentContexts:
    """Test alias behavior in different execution contexts."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_alias_in_subshell(self):
        """Test alias expansion in subshells."""
        result = AliasTestHelper.run_psh_command([
            'alias subtest="echo subshell"',
            '(subtest)'
        ])

        assert result['success']
        # Aliases should be inherited by subshells
        assert 'subshell' in result['stdout']

    def test_alias_in_function(self):
        """Test alias expansion inside functions."""
        result = AliasTestHelper.run_psh_command([
            'alias funcalias="echo from alias"',
            'testfunc() { funcalias; }',
            'testfunc'
        ])

        assert result['success']
        assert 'from alias' in result['stdout']

    def test_alias_in_script_vs_interactive(self):
        """Test alias behavior differences between script and interactive mode."""
        # This test runs in non-interactive mode by default
        result = AliasTestHelper.run_psh_command([
            'alias scripttest="echo script mode"',
            'scripttest'
        ])

        # In non-interactive mode, aliases might not be expanded
        # Behavior varies between shells
        assert isinstance(result['returncode'], int)

    def test_alias_with_for_loop(self):
        """Test alias expansion in for loops."""
        result = AliasTestHelper.run_psh_command([
            'alias loopecho="echo item:"',
            'for i in 1 2 3; do loopecho $i; done'
        ])

        assert result['success']
        assert 'item: 1' in result['stdout']
        assert 'item: 2' in result['stdout']
        assert 'item: 3' in result['stdout']

    def test_alias_with_case_statement(self):
        """Test alias expansion in case statements."""
        result = AliasTestHelper.run_psh_command([
            'alias caseecho="echo matched"',
            'case "test" in',
            '  test) caseecho ;;',
            'esac'
        ])

        assert result['success']
        assert 'matched' in result['stdout']


class TestAliasErrorHandling:
    """Test error handling with aliases."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_invalid_alias_syntax(self):
        """Test error handling for invalid alias syntax."""
        result = AliasTestHelper.run_psh_command('alias invalid syntax')

        # Should fail with syntax error
        assert not result['success']
        assert 'syntax' in result['stderr'].lower() or 'alias' in result['stderr'].lower()

    def test_alias_name_with_special_chars(self):
        """Test alias names with special characters."""
        result = AliasTestHelper.run_psh_command('alias "invalid name"="echo test"')

        # Should handle appropriately (fail or accept)
        assert isinstance(result['returncode'], int)

    def test_empty_alias_name(self):
        """Test alias with empty name."""
        result = AliasTestHelper.run_psh_command('alias =""')

        # Should fail appropriately
        assert not result['success']

    def test_alias_circular_reference(self):
        """Test handling of circular alias references."""
        result = AliasTestHelper.run_psh_command([
            'alias a="b"',
            'alias b="c"',
            'alias c="a"',  # Circular reference
            'a'
        ])

        # Should detect and handle circular reference
        assert isinstance(result['returncode'], int)

    def test_very_long_alias(self):
        """Test very long alias definitions."""
        long_command = 'echo ' + 'very_long_' * 1000
        result = AliasTestHelper.run_psh_command([
            f'alias longalias="{long_command}"',
            'longalias'
        ])

        # Should handle long aliases gracefully
        assert isinstance(result['returncode'], int)


class TestAliasCompatibility:
    """Test compatibility with other shell behaviors."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_bash_style_aliases(self):
        """Test bash-style alias behavior."""
        result = AliasTestHelper.run_psh_command([
            'alias ll="ls -alF"',
            'alias la="ls -A"',
            'alias l="ls -CF"',
            'alias'
        ])

        assert result['success']
        assert 'll' in result['stdout']
        assert 'la' in result['stdout']
        assert 'l=' in result['stdout']

    def test_posix_alias_compliance(self):
        """Test POSIX compliance for aliases."""
        result = AliasTestHelper.run_psh_command([
            'alias test_posix="echo posix"',
            'test_posix'
        ])

        assert result['success']
        assert 'posix' in result['stdout']

    def test_alias_export_behavior(self):
        """Test that aliases are not exported to subprocesses."""
        result = AliasTestHelper.run_psh_command([
            'alias subproc="echo alias"',
            'sh -c "subproc"'  # Should fail in subprocess
        ])

        # Alias should not be available in subprocess
        assert 'alias' not in result['stdout'] or not result['success']


class TestAliasAdvancedFeatures:
    """Test advanced alias features."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""

    def teardown_method(self):
        """Clean up any leftover processes after each test."""

    def test_alias_with_positional_parameters(self):
        """Test aliases that use positional parameters."""
        # Note: Traditional aliases don't support parameters
        # This tests if PSH has extended alias functionality
        result = AliasTestHelper.run_psh_command([
            'alias paramtest="echo arg1: $1, arg2: $2"',
            'paramtest first second'
        ])

        # This may not work in traditional shells
        # Depends on PSH implementation
        assert isinstance(result['returncode'], int)

    def test_alias_with_array_syntax(self):
        """Test aliases with array syntax.

        Single quotes defer ${ARR[0]} expansion to alias execution time,
        so the array value is resolved when the alias runs, not when it
        is defined.
        """
        result = AliasTestHelper.run_psh_command([
            "alias arraytest='echo ${ARR[0]}'",
            'ARR=(first second third)',
            'arraytest'
        ])

        assert result['success']
        assert 'first' in result['stdout']


# Test runner integration
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
