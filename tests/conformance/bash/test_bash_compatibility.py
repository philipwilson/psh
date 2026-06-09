"""
Bash compatibility tests.

Tests PSH compatibility with bash-specific features and behaviors.
Documents areas where PSH intentionally differs or doesn't support bash extensions.
"""

import os
import sys

import pytest

# Add parent directory to path for framework import
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestBashBuiltins(ConformanceTest):
    """Test bash builtin compatibility."""

    def test_echo_builtin_flags(self):
        """Test echo builtin with bash flags."""
        self.assert_identical_behavior('echo hello')
        self.assert_identical_behavior('echo -n hello')
        self.assert_identical_behavior('echo -e "hello\\nworld"')

    def test_ansi_c_octal_escapes(self):
        r"""ANSI-C $'...' octal escapes (\nnn, 1-3 digits)."""
        self.assert_identical_behavior(r"echo $'\101\102\103'")  # ABC
        self.assert_identical_behavior(r"echo $'\7\41'")
        self.assert_identical_behavior(r"echo $'\0101'")          # \b then 1

    def test_ansi_c_short_unicode_escapes(self):
        r"""ANSI-C $'...' accepts 1-4 digits after \u and 1-8 after \U."""
        self.assert_identical_behavior(r"echo $'\u41'")
        self.assert_identical_behavior(r"echo $'\U41'")
        self.assert_identical_behavior(r"echo $'A'")

    def test_printf_builtin(self):
        """Test printf builtin compatibility."""
        self.assert_identical_behavior('printf "hello\\n"')
        self.assert_identical_behavior('printf "%s %s\\n" hello world')

        # Format specifiers might not be fully implemented
        result = self.check_behavior('printf "%d\\n" 42')
        # Both should succeed, but output might differ
        assert result.psh_result.exit_code == 0
        assert result.bash_result.exit_code == 0

    def test_read_builtin(self):
        """Test read builtin compatibility."""
        # Basic read functionality
        self.check_behavior('echo "test" | read var; echo $var')
        # Read from pipe behavior might differ

    def test_test_builtin(self):
        """Test test/[ builtin compatibility."""
        self.assert_identical_behavior('test "hello" = "hello"')
        self.assert_identical_behavior('[ "hello" = "hello" ]')
        self.assert_identical_behavior('test 5 -gt 3')
        self.assert_identical_behavior('[ 5 -gt 3 ]')
        self.assert_identical_behavior('test -f /dev/null')
        self.assert_identical_behavior('test -d /tmp')

    def test_true_false_builtins(self):
        """Test true/false builtin compatibility."""
        self.assert_identical_behavior('true')
        self.assert_identical_behavior('false')

        result1 = self.check_behavior('true; echo $?')
        result2 = self.check_behavior('false; echo $?')

        assert '0' in result1.psh_result.stdout
        assert '0' in result1.bash_result.stdout
        assert '1' in result2.psh_result.stdout
        assert '1' in result2.bash_result.stdout


class TestBashConditionals(ConformanceTest):
    """Test bash conditional compatibility."""

    def test_single_bracket_conditionals(self):
        """Test [ ] conditionals (POSIX)."""
        self.assert_identical_behavior('if [ "hello" = "hello" ]; then echo yes; fi')
        self.assert_identical_behavior('if [ 5 -gt 3 ]; then echo yes; fi')
        self.assert_identical_behavior('if [ -f /dev/null ]; then echo yes; fi')

    def test_double_bracket_conditionals(self):
        """Test [[ ]] conditionals - mostly work in PSH."""
        self.assert_identical_behavior('[[ "hello" == "hello" ]]')
        self.assert_identical_behavior('[[ 5 > 3 ]]')
        # File test has different exit codes (2 vs 1) but both fail
        result = self.check_behavior('[[ -f /dev/null ]]')
        assert result.psh_result.exit_code != 0  # PSH returns 2
        assert result.bash_result.exit_code != 0  # Bash returns 1

    def test_arithmetic_conditionals(self):
        """Test (( )) arithmetic conditionals - work identically in PSH."""
        self.assert_identical_behavior('(( 5 > 3 ))')
        self.assert_identical_behavior('(( 1 + 1 == 2 ))')


class TestBashArrays(ConformanceTest):
    """Test bash array compatibility."""

    def test_indexed_arrays(self):
        """Test indexed arrays - work identically in PSH."""
        self.assert_identical_behavior('arr=(a b c); echo ${arr[0]}')
        self.assert_identical_behavior('arr[0]=hello; echo ${arr[0]}')

    def test_associative_arrays(self):
        """Test associative arrays - work identically in PSH."""
        self.assert_identical_behavior('declare -A arr; arr[key]=value; echo ${arr[key]}')

    def test_array_operations(self):
        """Test array operations - work identically in PSH."""
        self.assert_identical_behavior('arr=(a b c); echo ${arr[@]}')
        self.assert_identical_behavior('arr=(a b c); echo ${#arr[@]}')


class TestBashParameterExpansion(ConformanceTest):
    """Test bash parameter expansion compatibility."""

    def test_basic_parameter_expansion(self):
        """Test basic parameter expansion (POSIX)."""
        self.assert_identical_behavior('x=hello; echo ${x}')
        self.assert_identical_behavior('x=hello; echo ${x:-default}')
        self.assert_identical_behavior('x=hello; echo ${x:+set}')

    def test_substring_expansion(self):
        """Test bash substring expansion."""
        self.assert_identical_behavior('x=hello; echo ${x:1:3}')
        self.assert_identical_behavior('x=hello; echo ${x:2}')

    def test_substring_arithmetic_offsets(self):
        """Offset/length are arithmetic expressions (parens, +, variables)."""
        self.assert_identical_behavior('x=0123456789; echo "${x:(-3):2}"')
        self.assert_identical_behavior('x=0123456789; echo "${x:1+1:2}"')
        self.assert_identical_behavior('x=0123456789; echo "${x: -3:2}"')
        self.assert_identical_behavior('x=0123456789; n=2; echo "${x:n:3}"')

    def test_substring_out_of_range_offset(self):
        """A too-negative offset yields empty, not the whole string."""
        self.assert_identical_behavior('x=abc; echo "[${x: -10}]"')

    def test_substring_negative_length_bounds(self):
        """Negative length within range trims from the end like bash."""
        self.assert_identical_behavior('x=abc; echo "[${x:0:-1}]"')
        self.assert_identical_behavior('x=abcdef; echo "[${x:1:-2}]"')
        # The out-of-range error case (${x:0:-5}) differs only by the shell-name
        # stderr prefix, so it is verified for exit code + message in
        # tests/unit/expansion/test_substring_offset_length.py instead.

    def test_pattern_substitution(self):
        """Test bash pattern substitution."""
        self.assert_identical_behavior('x=hello; echo ${x/l/L}')
        self.assert_identical_behavior('x=hello; echo ${x//l/L}')

    def test_case_modification(self):
        """Test bash case modification - now supported in PSH."""
        self.assert_identical_behavior('x=hello; echo ${x^}')  # First char uppercase
        self.assert_identical_behavior('x=hello; echo ${x^^}')  # All uppercase
        self.assert_identical_behavior('x=HELLO; echo ${x,}')  # First char lowercase
        self.assert_identical_behavior('x=HELLO; echo ${x,,}')  # All lowercase


class TestBashCommandSubstitution(ConformanceTest):
    """Test bash command substitution compatibility."""

    def test_dollar_paren_substitution(self):
        """Test $() command substitution (POSIX)."""
        self.assert_identical_behavior('echo $(echo hello)')
        self.assert_identical_behavior('echo $(date +%Y)')

    def test_backtick_substitution(self):
        """Test backtick command substitution (POSIX)."""
        self.assert_identical_behavior('echo `echo hello`')
        self.assert_identical_behavior('echo `date +%Y`')

    def test_nested_substitution(self):
        """Test nested command substitution."""
        self.assert_identical_behavior('echo $(echo $(echo nested))')

    def test_process_substitution(self):
        """Test process substitution - works identically in PSH."""
        self.assert_identical_behavior('cat <(echo hello)')
        self.assert_identical_behavior('diff <(echo a) <(echo b)')


class TestBashBraceExpansion(ConformanceTest):
    """Test bash brace expansion compatibility."""

    def test_sequence_expansion(self):
        """Test bash sequence brace expansion."""
        self.assert_identical_behavior('echo {1..3}')
        self.assert_identical_behavior('echo {a..c}')

        # Check if expansion actually happens
        result = self.check_behavior('echo {1..3}')
        # Should expand to "1 2 3"
        assert '1' in result.psh_result.stdout
        assert '2' in result.psh_result.stdout
        assert '3' in result.psh_result.stdout

    def test_list_expansion(self):
        """Test bash list brace expansion."""
        self.assert_identical_behavior('echo {a,b,c}')
        self.assert_identical_behavior('echo pre{fix1,fix2}')

        result = self.check_behavior('echo {a,b,c}')
        # Should expand to "a b c"
        assert 'a' in result.psh_result.stdout
        assert 'b' in result.psh_result.stdout
        assert 'c' in result.psh_result.stdout

    def test_nested_brace_expansion(self):
        """Test nested brace expansion."""
        self.check_behavior('echo {a,b{1,2}}')
        # Should expand properly in both shells
        # Exact format might differ but should contain all combinations


class TestBashArithmeticExpansion(ConformanceTest):
    """Test bash arithmetic expansion compatibility."""

    def test_basic_arithmetic(self):
        """Test basic arithmetic (POSIX)."""
        self.assert_identical_behavior('echo $((2 + 3))')
        self.assert_identical_behavior('echo $((10 - 4))')
        self.assert_identical_behavior('echo $((3 * 4))')
        self.assert_identical_behavior('echo $((15 / 3))')

    def test_advanced_arithmetic(self):
        """Test advanced arithmetic operations."""
        self.assert_identical_behavior('echo $((2 ** 3))')  # Power
        self.assert_identical_behavior('echo $((17 % 5))')  # Modulo
        self.assert_identical_behavior('echo $((5 & 3))')   # Bitwise AND
        self.assert_identical_behavior('echo $((5 | 3))')   # Bitwise OR

    def test_arithmetic_assignment(self):
        """Test arithmetic assignment."""
        self.assert_identical_behavior('echo $((x = 5 + 3)); echo $x')
        self.assert_identical_behavior('x=5; echo $((x += 3)); echo $x')


class TestBashGlobbing(ConformanceTest):
    """Test bash globbing compatibility."""

    def test_basic_globbing(self):
        """Test basic glob patterns (POSIX)."""
        # Create test files first
        result = self.check_behavior('touch a.txt b.txt; echo *.txt')

        assert 'a.txt' in result.psh_result.stdout
        assert 'b.txt' in result.psh_result.stdout
        assert 'a.txt' in result.bash_result.stdout
        assert 'b.txt' in result.bash_result.stdout

    def test_nullglob_for_loop(self):
        """nullglob: a non-matching glob in a for-loop yields no iterations."""
        self.assert_identical_behavior(
            'shopt -s nullglob; for f in zzz_nomatch*; do echo "iter=$f"; done; echo done'
        )
        # Without nullglob, the literal pattern is used.
        self.assert_identical_behavior(
            'for f in zzz_nomatch*; do echo "iter=$f"; done'
        )

    def test_extended_globbing(self):
        """Test bash extended globbing.

        Note: extglob must be enabled on a PREVIOUS line for the tokenizer
        to recognize the patterns. Same-line shopt+pattern won't work
        in bash or psh because tokenization happens before execution.
        """
        self.check_behavior('shopt -s extglob\necho @(a|b)')
        self.check_behavior('shopt -s extglob\necho +(a|b)')
        self.check_behavior('shopt -s extglob\necho *(a|b)')

    def test_brace_globbing_interaction(self):
        """Test interaction between braces and globbing."""
        result = self.check_behavior('touch a1 a2 b1 b2; echo {a,b}*')

        # Should expand braces then glob
        for pattern in ['a1', 'a2', 'b1', 'b2']:
            assert pattern in result.psh_result.stdout
            assert pattern in result.bash_result.stdout


class TestBashJobControl(ConformanceTest):
    """Test bash job control compatibility."""

    def test_background_jobs(self):
        """Test background job execution."""
        result = self.check_behavior('sleep 0.1 &')

        # Both should start background job successfully
        assert result.psh_result.exit_code == 0
        assert result.bash_result.exit_code == 0

    def test_job_control_commands(self):
        """Test job control commands."""
        # These tests are complex in non-interactive mode
        result1 = self.check_behavior('jobs')
        self.check_behavior('sleep 1 & jobs')

        # Should succeed in both shells
        assert result1.psh_result.exit_code == 0
        assert result1.bash_result.exit_code == 0


class TestBashHistory(ConformanceTest):
    """Test bash history compatibility."""

    def test_history_expansion(self):
        """Test bash history expansion behavior in non-interactive mode."""
        # Non-interactive mode should NOT apply history expansion; !! is a command token.
        command = 'echo hello; !!'
        psh_result = self.framework.run_in_psh(command)
        bash_result = self.framework.run_in_bash(command)

        # Both shells execute the first command, then fail on unknown "!!".
        assert psh_result.exit_code == 127
        assert bash_result.exit_code == 127
        assert psh_result.stdout == "hello\n"
        assert bash_result.stdout == "hello\n"
        assert 'command not found' in psh_result.stderr
        assert 'command not found' in bash_result.stderr

    def test_history_commands(self):
        """Test history-related commands."""
        self.check_behavior('history')
        # History command behavior might differ


class TestBashOptions(ConformanceTest):
    """Test bash option compatibility."""

    def test_set_options(self):
        """Test set options (POSIX and bash)."""
        self.assert_identical_behavior('set -e; true')

        # These might have different behavior
        self.check_behavior('set -o pipefail; true')
        self.check_behavior('set -u; true')

    def test_set_euo_pipefail_strict_mode(self):
        """The canonical strict-mode idiom: trailing 'o' in a cluster."""
        self.assert_identical_behavior(
            'set -euo pipefail; set -o | grep pipefail')

    def test_set_multiple_o_options(self):
        """Multiple -o arguments must all be applied."""
        self.assert_identical_behavior(
            'set -o errexit -o pipefail; set -o | grep -E "errexit|pipefail"')

    def test_set_o_vi_silent(self):
        """Changing the edit mode prints nothing."""
        self.assert_identical_behavior('set -o vi; echo done')

    def test_shopt_options(self):
        """Test bash shopt options."""
        self.assert_identical_behavior('shopt -s extglob')
        self.assert_identical_behavior('shopt -s nullglob')
        self.assert_identical_behavior('shopt -s dotglob')


class TestBashRedirection(ConformanceTest):
    """Test bash redirection compatibility."""

    def test_basic_redirection(self):
        """Test basic I/O redirection (POSIX)."""
        self.assert_identical_behavior('echo hello > /dev/null')
        self.assert_identical_behavior('echo hello 2> /dev/null')
        self.assert_identical_behavior('cat < /dev/null')

    def test_here_documents(self):
        """Test here documents (POSIX)."""
        # Here document tests are complex - check basic syntax
        self.check_behavior('cat << EOF\nhello\nEOF')
        # Both should handle here documents

    def test_here_strings(self):
        """Here-strings (<<<) including bareword operands."""
        self.assert_identical_behavior('cat <<< hello')
        self.assert_identical_behavior('cat <<<hello')
        self.assert_identical_behavior('cat <<< "hello world"')
        self.assert_identical_behavior('cat <<< 123')
        self.assert_identical_behavior('x=hi; cat <<< $x')
        # A bareword here-string must not swallow surrounding commands.
        self.assert_identical_behavior('echo before; cat <<< hello; echo after')

    def test_advanced_redirection(self):
        """Test bash advanced redirection."""
        self.assert_identical_behavior(
            'exec 3> file.txt; echo hello >&3; exec 3>&-; cat file.txt'
        )

        # Writing to closed fd should fail in both shells.
        command = 'exec 3> file.txt; exec 3>&-; echo hello >&3'
        psh_result = self.framework.run_in_psh(command)
        bash_result = self.framework.run_in_bash(command)
        assert psh_result.exit_code != 0
        assert bash_result.exit_code != 0

    def test_high_fd_redirection(self):
        """A command-level redirect to fd>=3 leaves stdout alone and the file
        empty (the command doesn't write to that fd)."""
        # Builtin: stdout still gets 'hi', the fd-3 file is empty.
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; echo hi 3>f; printf "[%s]" "$(cat f)"'
        )
        # External command with a high fd must not crash before running.
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; /bin/echo hi 7>f; printf "[%s]" "$(cat f)"'
        )
        # Explicitly writing to a high fd (open fd 3 first, then point stdout
        # at it) lands the output in the file.
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; echo content 3>f >&3; printf "[%s]" "$(cat f)"'
        )


class TestBashGlobBrackets(ConformanceTest):
    """Glob bracket features: [^...], POSIX classes, nocaseglob, globstar.

    Multi-match patterns use LC_ALL=C so sort order is byte-collation in both
    shells (the default-locale ordering difference is a separate, documented
    low-severity item).
    """

    C = {"LC_ALL": "C"}

    def _in_tmp(self, body: str) -> str:
        # Run in a fresh temp dir with a known set of files.
        setup = (
            'd=$(mktemp -d); cd "$d"; '
            'touch file1 file2 fileX Foo.TXT bar.txt Baz123; '
            'mkdir -p sub; touch sub/x.txt; '
        )
        return setup + body

    def test_bracket_negation_caret(self):
        self.assert_identical_behavior(self._in_tmp('echo file[^0-9]'), env=self.C)

    def test_bracket_negation_in_case(self):
        self.assert_identical_behavior(
            'case fileX in file[^0-9]) echo match;; *) echo no;; esac'
        )

    def test_posix_character_classes(self):
        self.assert_identical_behavior(self._in_tmp('echo *[[:upper:]]*'), env=self.C)
        self.assert_identical_behavior(self._in_tmp('echo [[:alpha:]]*'), env=self.C)

    def test_posix_class_in_double_bracket(self):
        self.assert_identical_behavior('[[ Baz123 == *[[:digit:]]* ]] && echo yes || echo no')

    def test_nocaseglob(self):
        self.assert_identical_behavior(
            self._in_tmp('shopt -s nocaseglob; echo f*'), env=self.C
        )

    def test_globstar(self):
        self.assert_identical_behavior(
            self._in_tmp('shopt -s globstar; echo **/*.txt'), env=self.C
        )


class TestBashFunctions(ConformanceTest):
    """Test bash function compatibility."""

    def test_posix_function_syntax(self):
        """Test POSIX function syntax."""
        self.assert_identical_behavior('f() { echo function; }; f')
        self.assert_identical_behavior('greet() { echo hello $1; }; greet world')

    def test_bash_function_syntax(self):
        """Test bash function keyword syntax."""
        self.assert_identical_behavior('function f { echo function; }; f')
        self.assert_identical_behavior('function greet() { echo hello $1; }; greet world')

    def test_local_variables(self):
        """Test local variables in functions - works identically in PSH."""
        self.assert_identical_behavior('f() { local x=local; echo $x; }; x=global; f; echo $x')

    def test_function_return_values(self):
        """Test function return values."""
        result1 = self.check_behavior('f() { return 42; }; f; echo $?')
        result2 = self.check_behavior('f() { true; }; f; echo $?')

        # Return values should work the same
        assert '42' in result1.psh_result.stdout
        assert '42' in result1.bash_result.stdout
        assert '0' in result2.psh_result.stdout
        assert '0' in result2.bash_result.stdout


class TestBashAliases(ConformanceTest):
    """Test bash alias compatibility."""

    def test_basic_aliases(self):
        """Test basic alias functionality."""
        # Test that type recognizes aliases
        # Note: bash requires 'shopt -s expand_aliases' in non-interactive mode
        result = self.check_behavior('shopt -s expand_aliases 2>/dev/null; alias ll="ls -l"; type ll')
        # PSH always recognizes aliases, bash needs expand_aliases in non-interactive mode
        # Both should succeed when aliases are properly enabled
        assert result.psh_result.exit_code == 0
        assert 'aliased to' in result.psh_result.stdout or 'aliased to' in result.bash_result.stdout

        # Test alias creation (this should work in both)
        result = self.check_behavior('alias test_alias="echo aliased"; alias test_alias')
        assert 'test_alias=' in result.psh_result.stdout
        assert 'test_alias=' in result.bash_result.stdout

    def test_alias_with_arguments(self):
        """Test aliases with arguments.

        Bash disables alias expansion in non-interactive mode by default,
        so this is a PSH extension (PSH always expands aliases).
        """
        self.assert_psh_extension('alias greet="echo hello"; greet world')

    def test_unalias(self):
        """Test removing aliases."""
        result = self.check_behavior('alias test="echo test"; unalias test; test 2>/dev/null || echo gone')

        # After unalias, command should not be found
        assert 'gone' in result.psh_result.stdout
        assert 'gone' in result.bash_result.stdout


class TestBashMiscellaneous(ConformanceTest):
    """Test miscellaneous bash compatibility features."""

    def test_variable_assignment_formats(self):
        """Test various variable assignment formats."""
        self.assert_identical_behavior('x=value; echo $x')
        self.assert_identical_behavior('x="value with spaces"; echo $x')
        self.assert_identical_behavior('x=$(echo dynamic); echo $x')

    def test_export_functionality(self):
        """Test export functionality."""
        # Basic export
        self.check_behavior('export VAR=value; env | grep VAR')
        # Should appear in environment

    def test_env_option_compatibility(self):
        """Test env option compatibility for ignore/unset behavior."""
        result = self.check_behavior('env -i FOO=bar /usr/bin/env | /usr/bin/grep "^FOO=bar$"')
        assert 'FOO=bar' in result.psh_result.stdout
        assert 'FOO=bar' in result.bash_result.stdout

        result = self.check_behavior('env -u HOME /usr/bin/env | /usr/bin/grep "^HOME=" || echo nohome')
        assert 'nohome' in result.psh_result.stdout
        assert 'nohome' in result.bash_result.stdout

    def test_readonly_functionality(self):
        """Test readonly functionality."""
        # Test that readonly variables can be created and accessed
        result = self.check_behavior('readonly VAR=value; echo $VAR')
        assert 'value' in result.psh_result.stdout
        assert 'value' in result.bash_result.stdout

        # Test readonly variable listing
        result = self.check_behavior('readonly TEST=test; readonly | grep TEST')
        # Both should show the readonly variable
        assert 'TEST' in result.psh_result.stdout
        assert 'TEST' in result.bash_result.stdout

    def test_command_builtin(self):
        """Test command builtin."""
        result = self.check_behavior('alias echo="echo aliased"; command echo normal')

        # command should bypass alias
        assert 'normal' in result.psh_result.stdout
        assert 'normal' in result.bash_result.stdout
        assert 'aliased' not in result.psh_result.stdout
        assert 'aliased' not in result.bash_result.stdout


# Test suite for documenting differences
class TestDocumentedDifferences(ConformanceTest):
    """Test and document known differences between PSH and bash."""

    def test_psh_extensions(self):
        """Test PSH-specific extensions."""
        # PSH provides these, bash doesn't
        self.assert_psh_extension('version')
        # Note: help exists in both shells but with different behavior
        # This is better tested as documented difference

    def test_bash_specific_features(self):
        """Test features that work identically in PSH and bash."""
        # These features are actually supported by PSH!
        self.assert_identical_behavior('declare -a array')
        self.assert_identical_behavior('[[ 5 -gt 3 ]]')
        self.assert_identical_behavior('(( 5 > 3 ))')

    def test_documented_behavioral_differences(self):
        """Test documented behavioral differences."""
        # These might have subtle differences in behavior
        # but both shells should succeed

        self.check_behavior('pushd /tmp')
        self.check_behavior('popd')

        # Both should work but might have different output formats
        # This documents the differences rather than asserting sameness


def generate_bash_compatibility_report():
    """Generate comprehensive bash compatibility report."""
    import json
    import tempfile

    test_classes = [
        TestBashBuiltins,
        TestBashConditionals,
        TestBashArrays,
        TestBashParameterExpansion,
        TestBashCommandSubstitution,
        TestBashBraceExpansion,
        TestBashArithmeticExpansion,
        TestBashGlobbing,
        TestBashJobControl,
        TestBashHistory,
        TestBashOptions,
        TestBashRedirection,
        TestBashFunctions,
        TestBashAliases,
        TestBashMiscellaneous,
        TestDocumentedDifferences
    ]

    all_results = []

    for test_class in test_classes:
        test_instance = test_class()
        methods = [method for method in dir(test_instance) if method.startswith('test_')]

        for method in methods:
            try:
                getattr(test_instance, method)()
            except Exception as e:
                print(f"Test {test_class.__name__}.{method} failed: {e}")

        all_results.extend(test_instance.results)

    # Categorize results
    from conformance_framework import ConformanceResult

    categories = {
        "identical": 0,
        "documented_differences": 0,
        "psh_extensions": 0,
        "bash_specific": 0,
        "psh_bugs": 0,
        "test_errors": 0
    }

    for result in all_results:
        if result.conformance == ConformanceResult.IDENTICAL:
            categories["identical"] += 1
        elif result.conformance == ConformanceResult.DOCUMENTED_DIFFERENCE:
            categories["documented_differences"] += 1
        elif result.conformance == ConformanceResult.PSH_EXTENSION:
            categories["psh_extensions"] += 1
        elif result.conformance == ConformanceResult.BASH_SPECIFIC:
            categories["bash_specific"] += 1
        elif result.conformance == ConformanceResult.PSH_BUG:
            categories["psh_bugs"] += 1
        else:
            categories["test_errors"] += 1

    total_tests = len(all_results)
    compatibility_score = (categories["identical"] + categories["documented_differences"]) / total_tests * 100 if total_tests > 0 else 0

    report = {
        "bash_compatibility_summary": categories,
        "total_tests": total_tests,
        "compatibility_score": compatibility_score,
        "areas_of_concern": {
            "psh_bugs": categories["psh_bugs"],
            "test_errors": categories["test_errors"]
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(report, f, indent=2)
        print(f"Bash compatibility report saved to: {f.name}")

    return report


if __name__ == "__main__":
    # Generate compatibility report
    report = generate_bash_compatibility_report()
    print(f"Bash Compatibility Score: {report['compatibility_score']:.1f}%")
    print(f"Identical behavior: {report['bash_compatibility_summary']['identical']}")
    print(f"Documented differences: {report['bash_compatibility_summary']['documented_differences']}")
    print(f"PSH extensions: {report['bash_compatibility_summary']['psh_extensions']}")
    print(f"Bash-specific features: {report['bash_compatibility_summary']['bash_specific']}")
    print(f"Potential PSH bugs: {report['bash_compatibility_summary']['psh_bugs']}")
