"""
Tests for the env builtin command.

Tests environment variable display and export/env synchronization.
"""

import os
from pathlib import Path

import pytest


class TestEnvBuiltin:
    """Test the env builtin functionality."""

    def test_env_shows_environment(self, shell, clean_env, temp_dir):
        """Test that env displays environment variables."""
        out = Path(temp_dir) / 'env_output.txt'
        # Export a test variable through the shell
        result = shell.run_command('export TEST_ENV_VAR=test_value')
        assert result == 0

        # Run env and capture output
        result = shell.run_command(f'env > "{out}"')
        assert result == 0

        # Check output contains our variable
        assert 'TEST_ENV_VAR=test_value' in out.read_text()

    def test_export_env_sync(self, shell, temp_dir):
        """Test that exported variables appear in env output."""
        # Export a variable
        result = shell.run_command('export SYNC_TEST=synchronized')
        assert result == 0

        # Check env shows it
        out = Path(temp_dir) / 'sync_test.txt'
        result = shell.run_command(f'env > "{out}"')
        assert result == 0
        assert 'SYNC_TEST=synchronized' in out.read_text()

    def test_env_in_pipeline(self, shell, temp_dir):
        """Test that env works correctly in pipelines."""
        # Export variables
        shell.run_command('export PIPE_VAR1=value1')
        shell.run_command('export PIPE_VAR2=value2')

        # Test in pipeline
        out = Path(temp_dir) / 'pipe_test.txt'
        result = shell.run_command(f'env | /usr/bin/grep PIPE_VAR > "{out}"')
        assert result == 0

        output = out.read_text()
        assert 'PIPE_VAR1=value1' in output
        assert 'PIPE_VAR2=value2' in output

    def test_env_external_command_compatibility(self, shell, temp_dir):
        """Test that exported variables are visible to external commands."""
        # Export a variable
        shell.run_command('export EXTERNAL_VAR=visible')

        # Use external env command
        out = Path(temp_dir) / 'external_test.txt'
        result = shell.run_command(f'/usr/bin/env | /usr/bin/grep EXTERNAL_VAR > "{out}"')
        assert result == 0
        assert 'EXTERNAL_VAR=visible' in out.read_text()

    def test_env_builtin_priority(self, shell):
        """Test that env builtin is used instead of external command."""
        # This is a bit tricky to test directly, but we can check behavior
        # The builtin should work even if PATH is empty
        result = shell.run_command('PATH="" env > /dev/null')
        assert result == 0  # Should succeed with builtin

    def test_export_without_value(self, shell, temp_dir):
        """Test exporting existing variable."""
        # Set variable without export
        shell.run_command('NO_EXPORT_YET=test')

        # Variable shouldn't be in env yet
        # Use grep -c which always returns 0, and check the count
        count1 = Path(temp_dir) / 'count1.txt'
        shell.run_command(f'env | /usr/bin/grep -c NO_EXPORT_YET > "{count1}" || echo "0" > "{count1}"')
        assert count1.read_text().strip() == '0'

        # Export it
        shell.run_command('export NO_EXPORT_YET')

        # Now it should be in env
        out = Path(temp_dir) / 'export_test.txt'
        result = shell.run_command(f'env | /usr/bin/grep NO_EXPORT_YET > "{out}"')
        assert result == 0
        assert 'NO_EXPORT_YET=test' in out.read_text()

    def test_multiple_exports(self, shell, temp_dir):
        """Test multiple variables exported at once."""
        # Export multiple variables. Use unique names: generic names like
        # A/B leaked into later tests' subshells before os.environ writes
        # were removed (v0.312); unique names stay good hygiene since
        # state.env is still inherited by this shell's own children.
        result = shell.run_command('export MULTI_A=1 MULTI_B=2 MULTI_C=3')
        assert result == 0

        # Check all are in env
        out = Path(temp_dir) / 'multi_test.txt'
        result = shell.run_command(f'env | /usr/bin/grep -E "^MULTI_[ABC]=" | /usr/bin/sort > "{out}"')
        assert result == 0

        output = out.read_text()
        assert 'MULTI_A=1\n' in output
        assert 'MULTI_B=2\n' in output
        assert 'MULTI_C=3\n' in output

        shell.run_command('unset MULTI_A MULTI_B MULTI_C')

    def test_env_command_override_visible_to_executed_command(self, shell, temp_dir):
        """env NAME=value command should expose NAME only to that command."""
        output_path = Path(temp_dir) / "env_command_scope.txt"
        check_path = Path(temp_dir) / "env_after_scope.txt"

        result = shell.run_command(
            f'env CMD_SCOPE=visible /bin/sh -c \'echo "$CMD_SCOPE" > "{output_path}"\''
        )
        assert result == 0

        assert output_path.read_text().strip() == "visible"

        # Ensure override did not persist into parent shell.
        result = shell.run_command(f'echo "${{CMD_SCOPE:-unset}}" > "{check_path}"')
        assert result == 0
        assert check_path.read_text().strip() == "unset"

    def test_env_assignments_without_command_print_modified_environment(self, shell, temp_dir):
        """env NAME=value (no command) should print modified env without persisting."""
        output_path = Path(temp_dir) / "env_print_override.txt"
        check_path = Path(temp_dir) / "env_print_after.txt"

        result = shell.run_command(f'env ONLY_FOR_PRINT=1 > "{output_path}"')
        assert result == 0
        output = output_path.read_text()
        assert 'ONLY_FOR_PRINT=1' in output

        # No-command override should not mutate shell variables.
        result = shell.run_command(f'echo "${{ONLY_FOR_PRINT:-missing}}" > "{check_path}"')
        assert result == 0
        assert check_path.read_text().strip() == "missing"

    def test_env_command_respects_outer_redirection_for_external_commands(self, shell, temp_dir):
        """env NAME=value command should honor redirection when command is external."""
        output_path = Path(temp_dir) / "env_external_redirection.txt"

        result = shell.run_command(f'env REDIR_SCOPE=ok /usr/bin/env > "{output_path}"')
        assert result == 0
        output = output_path.read_text()
        assert "REDIR_SCOPE=ok" in output

    def test_env_does_not_resolve_shell_builtins(self, shell, temp_dir):
        """env runs commands EXTERNALLY — it does not resolve shell builtins
        (bash-faithful: /usr/bin/env is external). `env export X=42` therefore
        fails to find an external `export` (status 127) and cannot mutate the
        parent shell. (v0.656 replaced the in-process child that used to run
        the builtin; the old test pinned the divergent rc=0.)"""
        check_path = Path(temp_dir) / "env_builtin_leak_check.txt"

        result = shell.run_command('env TEMP_ENV=1 export INNER_ONLY=42')
        assert result == 127  # bash: "env: export: No such file or directory"

        result = shell.run_command(f'echo "${{INNER_ONLY:-missing}}" > "{check_path}"')
        assert result == 0
        assert check_path.read_text().strip() == "missing"

    def test_env_command_not_found_preserves_parent_state(self, shell, temp_dir):
        """Command-not-found in env mode should not persist assignment overrides."""
        check_path = Path(temp_dir) / "env_not_found_check.txt"

        result = shell.run_command('env NO_LEAK=value definitely_not_a_real_command_12345')
        assert result == 127

        result = shell.run_command(f'echo "${{NO_LEAK:-unset}}" > "{check_path}"')
        assert result == 0
        assert check_path.read_text().strip() == "unset"

    def test_env_ignore_environment_without_command(self, shell, temp_dir):
        """env -i should print an empty environment when no command is provided."""
        output_path = Path(temp_dir) / "env_ignore_print.txt"

        result = shell.run_command(f'env -i > "{output_path}"')
        assert result == 0
        assert output_path.read_text().strip() == ""

    def test_env_ignore_environment_with_assignment_and_command(self, shell, temp_dir):
        """env -i NAME=value command should pass only explicit variables."""
        output_path = Path(temp_dir) / "env_ignore_command.txt"

        result = shell.run_command(f'env -i ONLY_VAR=1 /usr/bin/env > "{output_path}"')
        assert result == 0

        lines = [line.strip() for line in output_path.read_text().splitlines() if line.strip()]
        assert "ONLY_VAR=1" in lines
        assert not any(line.startswith("HOME=") for line in lines)
        assert not any(line.startswith("PATH=") for line in lines)

    def test_env_unset_option_for_command_scope(self, shell, temp_dir):
        """env -u NAME command should hide NAME only for that command."""
        output_path = Path(temp_dir) / "env_unset_command.txt"
        check_path = Path(temp_dir) / "env_unset_parent_check.txt"

        result = shell.run_command('export TEMP_UNSET_VAR=present')
        assert result == 0

        result = shell.run_command(f'env -u TEMP_UNSET_VAR /usr/bin/env > "{output_path}"')
        assert result == 0
        output = output_path.read_text()
        assert "TEMP_UNSET_VAR=present" not in output

        result = shell.run_command(f'echo "${{TEMP_UNSET_VAR:-missing}}" > "{check_path}"')
        assert result == 0
        assert check_path.read_text().strip() == "present"

    def test_env_unset_option_without_command_prints_modified_environment(self, shell, temp_dir):
        """env -u NAME should omit NAME from printed environment only."""
        output_path = Path(temp_dir) / "env_unset_print.txt"
        check_path = Path(temp_dir) / "env_unset_print_parent_check.txt"

        result = shell.run_command('export TEMP_UNSET_PRINT=show')
        assert result == 0

        result = shell.run_command(f'env -u TEMP_UNSET_PRINT > "{output_path}"')
        assert result == 0
        output = output_path.read_text()
        assert "TEMP_UNSET_PRINT=show" not in output

        result = shell.run_command(f'echo "${{TEMP_UNSET_PRINT:-missing}}" > "{check_path}"')
        assert result == 0
        assert check_path.read_text().strip() == "show"

    def test_env_unset_missing_argument_errors(self, shell, temp_dir):
        """env -u without a variable name should fail with an error."""
        error_path = Path(temp_dir) / "env_unset_error.txt"

        result = shell.run_command(f'env -u 2> "{error_path}"')
        assert result == 1
        assert "requires an argument" in error_path.read_text()

    def test_env_unknown_option_errors(self, shell, temp_dir):
        """Unknown env options should return an error."""
        error_path = Path(temp_dir) / "env_option_error.txt"

        result = shell.run_command(f'env -z 2> "{error_path}"')
        assert result == 1
        assert "invalid option" in error_path.read_text()


@pytest.fixture
def clean_env():
    """Fixture to clean up test environment variables."""
    # Store original env
    original_env = os.environ.copy()
    yield
    # Restore original env
    for key in list(os.environ.keys()):
        if key not in original_env:
            del os.environ[key]
    for key, value in original_env.items():
        os.environ[key] = value
