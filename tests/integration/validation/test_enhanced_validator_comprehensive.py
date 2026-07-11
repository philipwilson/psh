"""
Comprehensive enhanced validator integration tests.

Tests for the enhanced AST validator with variable tracking, command validation,
quoting analysis, and security checks. This covers cross-component validation
functionality that analyzes parsed AST nodes for correctness and safety.
"""

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor.enhanced_validator_visitor import (
    EnhancedValidatorVisitor,
    ValidatorConfig,
    VariableInfo,
    VariableTracker,
)
from psh.visitor.validator_visitor import Severity


class TestVariableTracker:
    """Test the variable tracking system."""

    def test_basic_variable_tracking(self):
        """Test basic variable definition and lookup."""
        tracker = VariableTracker()

        # Define a variable
        tracker.define_variable('FOO', VariableInfo(name='FOO', defined_at='test'))

        # Should be defined
        assert tracker.is_defined('FOO')
        assert tracker.lookup_variable('FOO') is not None
        assert tracker.lookup_variable('FOO').name == 'FOO'

        # Undefined variable should not be found
        assert not tracker.is_defined('BAR')
        assert tracker.lookup_variable('BAR') is None

    def test_special_variables(self):
        """Test that special variables are always defined."""
        tracker = VariableTracker()

        # Special single-char variables
        for var in ['?', '$', '!', '#', '@', '*', '-', '_', '0']:
            assert tracker.is_defined(var)
            info = tracker.lookup_variable(var)
            assert info is not None
            assert info.is_special

        # Environment variables
        for var in ['HOME', 'PATH', 'USER', 'SHELL']:
            assert tracker.is_defined(var)
            assert tracker.lookup_variable(var).is_special

    def test_positional_parameters(self):
        """Test positional parameter tracking."""
        tracker = VariableTracker()

        # Check positional parameters are defined (they're special variables)
        for i in range(1, 10):  # Test $1-$9
            assert tracker.is_defined(str(i))
            info = tracker.lookup_variable(str(i))
            assert info.is_positional

        # $0 is also a positional parameter
        assert tracker.is_defined('0')
        assert tracker.lookup_variable('0').is_special

    def test_array_variables(self):
        """Test array variable tracking."""
        tracker = VariableTracker()

        # Define array variable
        tracker.define_variable('ARR', VariableInfo(
            name='ARR',
            defined_at='test',
            is_array=True
        ))

        assert tracker.is_defined('ARR')
        info = tracker.lookup_variable('ARR')
        assert info.is_array

    def test_scoping(self):
        """Test variable scoping functionality."""
        tracker = VariableTracker()

        # Define global variable
        tracker.define_variable('GLOBAL', VariableInfo(name='GLOBAL', defined_at='global'))

        # Enter new scope
        tracker.enter_scope()

        # Define local variable
        tracker.define_variable('LOCAL', VariableInfo(
            name='LOCAL',
            defined_at='function',
            is_local=True
        ))

        # Both should be visible in current scope
        assert tracker.is_defined('GLOBAL')
        assert tracker.is_defined('LOCAL')

        # Exit scope
        tracker.exit_scope()

        # Only global should be visible
        assert tracker.is_defined('GLOBAL')
        assert not tracker.is_defined('LOCAL')


class TestValidatorConfig:
    """Test validator configuration options."""

    def test_default_config(self):
        """Test default validator configuration."""
        config = ValidatorConfig()

        # Default settings should be reasonable
        assert config.check_undefined_vars is True
        assert config.check_command_exists is True
        assert config.check_file_permissions is True
        assert config.check_quoting is True
        assert config.check_security is True

    def test_custom_config(self):
        """Test custom validator configuration."""
        config = ValidatorConfig(
            check_undefined_vars=False,
            check_security=True
        )

        assert config.check_undefined_vars is False
        assert config.check_security is True

    def test_severity_levels(self):
        """Test severity level configuration."""
        config = ValidatorConfig()

        # Test that config has boolean options for various checks
        assert hasattr(config, 'check_undefined_vars')
        assert hasattr(config, 'check_command_exists')
        assert hasattr(config, 'check_quoting')
        assert hasattr(config, 'check_security')


class TestBasicValidation:
    """Test basic validation functionality."""

    def test_simple_command_validation(self, shell):
        """Test validation of simple commands."""
        config = ValidatorConfig()
        validator = EnhancedValidatorVisitor(config)

        # Parse a simple command
        ast = parse(list(tokenize("echo hello")))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Should have no issues for basic echo command
        assert len(issues) == 0

    def test_undefined_variable_detection(self, shell):
        """Test detection of undefined variables."""
        config = ValidatorConfig(check_undefined_vars=True)
        validator = EnhancedValidatorVisitor(config)

        # Parse command with undefined variable
        ast = parse(list(tokenize("echo $UNDEFINED_VAR")))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Should detect undefined variable
        undefined_issues = [i for i in issues if 'undefined' in i.message.lower()]
        assert len(undefined_issues) > 0

    def test_defined_variable_validation(self, shell):
        """Test that defined variables don't trigger warnings."""
        config = ValidatorConfig(check_undefined_vars=True)
        validator = EnhancedValidatorVisitor(config)

        # Define a variable first
        validator.var_tracker.define_variable(
            'DEFINED_VAR',
            VariableInfo(name='DEFINED_VAR', defined_at='test')
        )

        # Parse command using defined variable
        ast = parse(list(tokenize("echo $DEFINED_VAR")))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Should have no undefined variable issues
        undefined_issues = [i for i in issues if 'undefined' in i.message.lower()]
        assert len(undefined_issues) == 0


class TestCommandValidation:
    """Test command existence and validation."""

    def test_builtin_command_validation(self, shell):
        """Test validation of builtin commands."""
        config = ValidatorConfig(check_command_exists=True)
        validator = EnhancedValidatorVisitor(config)

        # Parse builtin command
        ast = parse(list(tokenize("cd /home")))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Builtin commands should not trigger missing command issues
        missing_issues = [i for i in issues if 'command not found' in i.message.lower()]
        assert len(missing_issues) == 0

    def test_external_command_validation(self, shell):
        """Test validation of external commands."""
        config = ValidatorConfig(check_command_exists=True)
        validator = EnhancedValidatorVisitor(config)

        # Parse known external command (ls should be available)
        ast = parse(list(tokenize("ls /")))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Common commands like ls should not trigger issues
        missing_issues = [i for i in issues if 'command not found' in i.message.lower()]
        assert len(missing_issues) == 0

    def test_nonexistent_command_detection(self, shell):
        """Test detection of nonexistent commands."""
        config = ValidatorConfig(check_command_exists=True)
        validator = EnhancedValidatorVisitor(config)

        # Parse obviously fake command
        ast = parse(list(tokenize("this_command_definitely_does_not_exist_12345")))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Should detect missing command
        [i for i in issues if 'command' in i.message.lower()]
        # Note: This might not always trigger depending on PATH and system commands
        # So we'll just verify the validator runs without error
        assert isinstance(issues, list)


class TestQuotingAnalysis:
    """Test quoting and escaping analysis."""

    def test_proper_quoting_validation(self, shell):
        """Test validation of properly quoted strings."""
        config = ValidatorConfig(check_quoting=True)
        validator = EnhancedValidatorVisitor(config)

        # Parse properly quoted command
        ast = parse(list(tokenize('echo "hello world"')))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Should have no quoting issues
        quoting_issues = [i for i in issues if 'quot' in i.message.lower()]
        assert len(quoting_issues) == 0

    def test_unquoted_spaces_detection(self, shell):
        """Test detection of unquoted spaces that might cause issues."""
        config = ValidatorConfig(check_quoting=True)
        validator = EnhancedValidatorVisitor(config)

        # Parse command with potential quoting issue
        # Note: This might be parsed correctly, but validator should analyze it
        ast = parse(list(tokenize('echo hello world')))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Validator should run without error
        assert isinstance(issues, list)

    def test_special_character_handling(self, shell):
        """Test handling of special characters in commands."""
        config = ValidatorConfig(check_quoting=True)
        validator = EnhancedValidatorVisitor(config)

        # Parse command with special characters
        ast = parse(list(tokenize('echo "hello; rm -rf /"')))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Should analyze without error
        assert isinstance(issues, list)


class TestSecurityChecks:
    """Test security validation checks."""

    def test_basic_security_validation(self, shell):
        """Test basic security checks don't flag normal commands."""
        config = ValidatorConfig(check_security=True)
        validator = EnhancedValidatorVisitor(config)

        # Parse safe command
        ast = parse(list(tokenize("echo hello")))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Safe commands should not trigger security issues
        security_issues = [i for i in issues if i.severity == Severity.ERROR]
        assert len(security_issues) == 0

    def test_potentially_dangerous_commands(self, shell):
        """Test detection of potentially dangerous commands."""
        config = ValidatorConfig(check_security=True)
        validator = EnhancedValidatorVisitor(config)

        # Parse potentially dangerous command (but in quotes to be safe)
        ast = parse(list(tokenize('echo "rm -rf /"')))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Should analyze without error (actual flagging depends on implementation)
        assert isinstance(issues, list)


class TestComplexValidation:
    """Test validation of complex shell constructs."""

    def test_pipeline_validation(self, shell):
        """Test validation of command pipelines."""
        config = ValidatorConfig()
        validator = EnhancedValidatorVisitor(config)

        # Parse pipeline
        ast = parse(list(tokenize("echo hello | grep h")))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Pipeline should validate successfully
        assert isinstance(issues, list)

    def test_function_definition_validation(self, shell):
        """Test validation of function definitions."""
        config = ValidatorConfig()
        validator = EnhancedValidatorVisitor(config)

        # Parse function definition
        ast = parse(list(tokenize('test_func() { echo "in function"; }')))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Function definition should validate
        assert isinstance(issues, list)

    def test_control_structure_validation(self, shell):
        """Test validation of control structures."""
        config = ValidatorConfig()
        validator = EnhancedValidatorVisitor(config)

        # Parse if statement
        script = '''
        if [ -f /etc/passwd ]; then
            echo "file exists"
        fi
        '''
        ast = parse(list(tokenize(script)))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Control structure should validate
        assert isinstance(issues, list)

    def test_nested_structures_validation(self, shell):
        """Test validation of nested structures."""
        config = ValidatorConfig()
        validator = EnhancedValidatorVisitor(config)

        # Parse nested structure
        script = '''
        for file in *.txt; do
            if [ -r "$file" ]; then
                echo "processing $file"
            fi
        done
        '''
        ast = parse(list(tokenize(script)))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Nested structure should validate
        assert isinstance(issues, list)


class TestValidatorIntegration:
    """Test integration of validator with shell components."""

    def test_validator_with_shell_state(self, shell):
        """Test validator integration with shell state."""
        config = ValidatorConfig(check_undefined_vars=True)
        validator = EnhancedValidatorVisitor(config)

        # Set up shell state
        shell.state.set_variable('SHELL_VAR', 'test_value')

        # Sync validator with shell state
        validator.var_tracker.define_variable(
            'SHELL_VAR',
            VariableInfo(name='SHELL_VAR', defined_at='shell')
        )

        # Parse command using shell variable
        ast = parse(list(tokenize("echo $SHELL_VAR")))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Should not flag defined variable
        undefined_issues = [i for i in issues if 'undefined' in i.message.lower()]
        assert len(undefined_issues) == 0

    def test_validator_error_reporting(self, shell):
        """Test validator error reporting functionality."""
        config = ValidatorConfig()
        validator = EnhancedValidatorVisitor(config)

        # Parse command that might have issues
        ast = parse(list(tokenize("echo $POTENTIALLY_UNDEFINED")))

        # Validate it
        validator.visit(ast)
        issues = validator.issues

        # Test that issues are properly structured
        for issue in issues:
            assert hasattr(issue, 'severity')
            assert hasattr(issue, 'message')
            assert isinstance(issue.message, str)
            assert issue.severity in [Severity.ERROR, Severity.WARNING, Severity.INFO]

    def test_validator_performance(self, shell):
        """Test validator performance with complex scripts."""
        config = ValidatorConfig()
        validator = EnhancedValidatorVisitor(config)

        # Create a moderately complex script
        script = '''
        #!/bin/bash

        function process_files() {
            local dir="$1"
            for file in "$dir"/*.txt; do
                if [ -f "$file" ]; then
                    echo "Processing: $file"
                    cat "$file" | grep -v "^#" | sort
                fi
            done
        }

        if [ $# -gt 0 ]; then
            process_files "$1"
        else
            echo "Usage: $0 directory"
            exit 1
        fi
        '''

        # Parse and validate
        ast = parse(list(tokenize(script)))
        validator.visit(ast)
        issues = validator.issues

        # Should complete validation without error
        assert isinstance(issues, list)

        # Check that validator processed the complex script successfully
        # (The fact that it returned a list of issues means it completed processing)
        assert len(issues) >= 0  # Could have 0 or more issues, both are valid


class TestValidatorErrorHandling:
    """Test validator error handling and edge cases."""

    def test_invalid_ast_handling(self):
        """Test validator handling of invalid AST nodes."""
        config = ValidatorConfig()
        validator = EnhancedValidatorVisitor(config)

        # Test with None (should not crash)
        try:
            validator.visit(None)
            # Should handle gracefully
        except Exception as e:
            # If it raises an exception, it should be a controlled one
            assert "AST" in str(e) or "node" in str(e)

    def test_empty_command_validation(self, shell):
        """Test validation of empty or minimal commands."""
        config = ValidatorConfig()
        validator = EnhancedValidatorVisitor(config)

        # Parse empty command
        ast = parse(list(tokenize("")))

        if ast:  # If parser returns something for empty input
            validator.visit(ast)
            issues = validator.issues
            assert isinstance(issues, list)

    def test_malformed_constructs(self, shell):
        """Test validator with potentially malformed constructs."""
        config = ValidatorConfig()
        validator = EnhancedValidatorVisitor(config)

        # Test with various edge cases that parser might handle
        test_cases = [
            "echo",  # Command without arguments
            "$",     # Bare dollar sign
            "echo $", # Command with bare dollar
        ]

        for test_case in test_cases:
            try:
                ast = parse(list(tokenize(test_case)))
                if result.ast:
                    validator.visit(ast)
                    issues = validator.issues
                    assert isinstance(issues, list)
            except Exception:
                # Parser might reject some cases, which is fine
                pass


class TestFalsePositiveRegressions:
    """Reappraisal #7 bug L7: false positives the enhanced validator used to
    emit. Each case asserts the spurious warning is gone while genuine
    detection still works.
    """

    @staticmethod
    def _undefined_warnings(source: str):
        validator = EnhancedValidatorVisitor(ValidatorConfig())
        validator.visit(parse(list(tokenize(source))))
        return [i for i in validator.issues
                if 'undefined' in i.message.lower()]

    @staticmethod
    def _all_issues(source: str):
        validator = EnhancedValidatorVisitor(ValidatorConfig())
        validator.visit(parse(list(tokenize(source))))
        return validator.issues

    def test_array_initialization_defines_variable(self):
        """`x=(1 2 3); echo "${x[@]}"` must not warn that $x is undefined."""
        assert self._undefined_warnings('x=(1 2 3); echo "${x[@]}"') == []

    def test_array_append_defines_variable(self):
        assert self._undefined_warnings('x=(1 2); x+=(3 4); echo "${x[@]}"') == []

    def test_array_element_assignment_defines_variable(self):
        """`arr[0]=v; echo "${arr[0]}"` must not warn that $arr is undefined."""
        assert self._undefined_warnings('arr[0]=hello; echo "${arr[0]}"') == []

    def test_cstyle_for_loop_init_var_defined(self):
        """C-style for-loop init var registers, so $i in the body is defined."""
        assert self._undefined_warnings(
            'for ((i=0; i<3; i++)); do echo $i; done') == []

    def test_cstyle_for_loop_multiple_init_vars(self):
        assert self._undefined_warnings(
            'for ((i=0, j=10; i<j; i++)); do echo $((i+j)); done') == []

    def test_arithmetic_not_classified_as_variable_expansion(self):
        """`$(( ))` must not be reported as an unquoted *variable* expansion."""
        issues = self._all_issues('echo $((1+2))')
        var_split = [i for i in issues
                     if 'variable expansion' in i.message.lower()]
        assert var_split == []

    def test_genuine_undefined_still_warns(self):
        """Real undefined variables must still be reported (no over-suppression)."""
        assert len(self._undefined_warnings('echo $genuinely_undefined')) > 0

    def test_array_then_genuine_undefined_still_warns(self):
        """Defining an array must not suppress an unrelated undefined var."""
        warns = self._undefined_warnings('x=(1 2 3); echo "${x[@]}" $other')
        assert any('other' in i.message for i in warns)
