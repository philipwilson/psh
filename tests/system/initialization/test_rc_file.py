"""
RC file loading and initialization tests.

Tests for PSH initialization file (.pshrc) loading in different modes.
"""

import os
import tempfile

import pytest

from psh.interactive.rc_loader import load_rc_file


@pytest.fixture(autouse=True)
def clean_test_env():
    """Clean up TEST_RC_VAR and other test variables from environment after each test."""
    # Save original values
    original_vars = {}
    test_vars = ['TEST_RC_VAR', 'TEST_VAR', 'ENV_VAR', 'TEST_AFTER_ERROR', 'MY_VAR', 'MY_FUNC_RAN']
    for var in test_vars:
        if var in os.environ:
            original_vars[var] = os.environ[var]

    yield

    # Restore original environment
    for var in test_vars:
        if var in original_vars:
            os.environ[var] = original_vars[var]
        elif var in os.environ:
            del os.environ[var]


def test_rc_file_not_loaded_in_script_mode():
    """RC file should not be loaded when running scripts."""
    from psh.shell import Shell

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc', delete=False) as f:
        f.write('export TEST_RC_VAR=loaded\n')
        rc_file = f.name

    try:
        # Script mode should not load RC file
        shell = Shell(script_name="test.sh", rcfile=rc_file)
        assert 'TEST_RC_VAR' not in shell.env
    finally:
        os.unlink(rc_file)


def test_rc_file_loaded_in_interactive_mode():
    """RC file should be loaded in interactive mode."""
    from psh.shell import Shell

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc', delete=False) as f:
        f.write('export TEST_RC_VAR=loaded\n')
        f.write('alias test_alias="echo aliased"\n')
        rc_file = f.name

    try:
        # Interactive mode should load RC file
        shell = Shell(rcfile=rc_file)
        shell._force_interactive = True
        load_rc_file(shell)  # Force load since we're in test environment
        assert shell.env.get('TEST_RC_VAR') == 'loaded'
        assert 'test_alias' in shell.alias_manager.aliases
    finally:
        os.unlink(rc_file)


def test_norc_flag_prevents_loading():
    """--norc flag should prevent RC file loading."""
    from psh.shell import Shell

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc', delete=False) as f:
        f.write('export TEST_RC_VAR=loaded\n')
        rc_file = f.name

    try:
        # norc flag should prevent loading
        shell = Shell(rcfile=rc_file, norc=True)
        assert 'TEST_RC_VAR' not in shell.env
    finally:
        os.unlink(rc_file)


def test_rc_file_syntax_error_doesnt_crash_shell():
    """Syntax errors in RC file should not crash the shell."""
    from psh.shell import Shell

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc', delete=False) as f:
        f.write('invalid syntax {{{\n')
        rc_file = f.name

    try:
        # Shell should start despite RC file errors
        shell = Shell(rcfile=rc_file)
        # Shell should be created successfully
        assert shell is not None
    finally:
        os.unlink(rc_file)


def test_rc_file_runtime_error_doesnt_crash_shell():
    """Runtime errors in RC file should not crash the shell."""
    from psh.shell import Shell

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc', delete=False) as f:
        f.write('cd /nonexistent/directory\n')
        f.write('export TEST_AFTER_ERROR=yes\n')
        rc_file = f.name

    try:
        # Shell should continue despite runtime errors
        shell = Shell(rcfile=rc_file)
        shell._force_interactive = True
        load_rc_file(shell)  # Force load since we're in test environment
        # Commands after error should still execute
        assert shell.env.get('TEST_AFTER_ERROR') == 'yes'
    finally:
        os.unlink(rc_file)


def test_rc_file_sets_variables_and_functions():
    """RC file should be able to set variables and define functions."""
    from psh.shell import Shell

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc', delete=False) as f:
        f.write('TEST_VAR=hello_world\n')
        f.write('export ENV_VAR=exported\n')
        f.write('test_func() { echo "function works"; }\n')
        rc_file = f.name

    try:
        shell = Shell(rcfile=rc_file)
        shell._force_interactive = True
        load_rc_file(shell)  # Force load since we're in test environment
        # Shell variable should be set
        assert shell.state.variables.get('TEST_VAR') == 'hello_world'
        # Environment variable should be exported
        assert shell.env.get('ENV_VAR') == 'exported'
        # Function should be defined
        assert 'test_func' in shell.function_manager.functions
    finally:
        os.unlink(rc_file)


@pytest.mark.skipif(os.name == 'nt', reason="Unix file permissions test")
def test_rc_file_unsafe_permissions_warning(capsys):
    """RC file with unsafe permissions should show warning."""
    from psh.shell import Shell

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc', delete=False) as f:
        f.write('export TEST_RC_VAR=loaded\n')
        rc_file = f.name

    try:
        # Make file world-writable
        os.chmod(rc_file, 0o666)

        shell = Shell(rcfile=rc_file)
        shell._force_interactive = True
        load_rc_file(shell)  # Force load since we're in test environment
        captured = capsys.readouterr()

        # Should show warning
        assert "unsafe permissions" in captured.err
        # Should not load the file
        assert 'TEST_RC_VAR' not in shell.env
    finally:
        os.unlink(rc_file)


def test_rc_file_preserves_dollar_zero():
    """RC file loading should preserve $0 after execution."""
    from psh.shell import Shell

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc', delete=False) as f:
        f.write('echo "Loading RC file: $0"\n')
        rc_file = f.name

    try:
        shell = Shell(rcfile=rc_file)
        shell._force_interactive = True
        load_rc_file(shell)  # Force load since we're in test environment
        # $0 should be restored to 'psh' after RC file execution
        assert shell.state.variables.get('0', shell.state.script_name) == 'psh'
    finally:
        os.unlink(rc_file)


def test_rcfile_option_overrides_default():
    """--rcfile should override default ~/.pshrc location."""
    from psh.shell import Shell

    # Create two RC files
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc1', delete=False) as f1:
        f1.write('export FROM_FILE1=yes\n')
        rc_file1 = f1.name

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc2', delete=False) as f2:
        f2.write('export FROM_FILE2=yes\n')
        rc_file2 = f2.name

    try:
        # Load with specific rcfile
        shell = Shell(rcfile=rc_file2)
        shell._force_interactive = True
        load_rc_file(shell)  # Force load since we're in test environment

        # Should only load the specified file
        assert 'FROM_FILE1' not in shell.env
        assert shell.env.get('FROM_FILE2') == 'yes'
    finally:
        os.unlink(rc_file1)
        os.unlink(rc_file2)


def test_nonexistent_rc_file_silently_ignored():
    """Non-existent RC file should be silently ignored."""
    from psh.shell import Shell

    # Specify a non-existent RC file
    shell = Shell(rcfile="/tmp/nonexistent_rc_file_12345")

    # Shell should start normally
    assert shell is not None
    # No crash or errors


def test_rc_file_with_complex_commands():
    """Test RC file with complex shell constructs."""
    from psh.shell import Shell

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc', delete=False) as f:
        f.write('''# Complex RC file
# Set some variables
EDITOR=nano
export EDITOR
PATH=$PATH:/usr/local/bin

# Define aliases
alias ll="ls -la"
alias grep="grep --color=auto"

# Define functions
greet() {
    echo "Hello, $USER!"
}

# Set some options
set -o vi  # May not be implemented yet
''')
        rc_file = f.name

    try:
        shell = Shell(rcfile=rc_file)
        shell._force_interactive = True
        load_rc_file(shell)

        # Check variables
        assert shell.env.get('EDITOR') == 'nano'
        assert '/usr/local/bin' in shell.env.get('PATH', '')

        # Check aliases
        assert 'll' in shell.alias_manager.aliases
        assert 'grep' in shell.alias_manager.aliases

        # Check functions
        assert 'greet' in shell.function_manager.functions
    finally:
        os.unlink(rc_file)


def test_rc_file_with_conditionals():
    """Test RC file with conditional statements."""
    from psh.shell import Shell

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pshrc', delete=False) as f:
        f.write('''# RC file with conditionals
if [ -d "/usr/local/bin" ]; then
    export HAS_LOCAL_BIN=yes
else
    export HAS_LOCAL_BIN=no
fi

# Set based on environment
if [ "$TERM" = "xterm" ]; then
    export TERM_TYPE=xterm
fi
''')
        rc_file = f.name

    try:
        shell = Shell(rcfile=rc_file)
        shell._force_interactive = True
        load_rc_file(shell)

        # Should have executed conditionals
        assert 'HAS_LOCAL_BIN' in shell.env
        # Value depends on system but should be set
        assert shell.env['HAS_LOCAL_BIN'] in ['yes', 'no']
    finally:
        os.unlink(rc_file)
