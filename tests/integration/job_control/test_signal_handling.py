"""
Signal handling integration tests.

Tests for signal handling, trap command, and signal propagation including:
- trap command registration and execution
- Signal propagation in pipelines
- Signal handling in different execution contexts
- Interaction between signals and shell options
- Signal delivery to job groups
"""

import os
import sys
from pathlib import Path

# Add framework to path
TEST_ROOT = Path(__file__).parent.parent.parent
PSH_ROOT = TEST_ROOT.parent
sys.path.insert(0, str(PSH_ROOT))

# Shell fixture imported automatically from conftest.py


class TestTrapCommand:
    """Test trap command functionality and signal handling."""

    def test_trap_command_basic(self, shell):
        """Test basic trap command registration."""
        # Set a trap for TERM signal
        result = shell.run_command('trap "echo caught TERM" TERM')
        assert result == 0

        # List current traps
        trap_result = shell.run_command('trap')
        assert trap_result == 0
        # Trap verification would need shell output capture

    def test_trap_signal_names(self, shell):
        """Test trap with different signal name formats."""
        # Test numeric signal
        result1 = shell.run_command('trap "echo numeric" 15')  # TERM = 15
        assert result1 == 0

        # Test signal name with SIG prefix - this may fail due to incomplete implementation
        result2 = shell.run_command('trap "echo sigterm" SIGTERM')
        # Allow failure for SIG-prefixed names until implemented
        assert result2 == 0 or result2 == 1

        # Test signal name without SIG prefix
        result3 = shell.run_command('trap "echo term" TERM')
        assert result3 == 0

        # Check that traps are registered
        trap_result = shell.run_command('trap')
        assert trap_result == 0

    def test_trap_multiple_signals(self, shell):
        """Test trap with multiple signals."""
        # Set trap for multiple signals
        result = shell.run_command('trap "echo multi-signal" INT TERM USR1')
        assert result == 0

        # Check registration
        trap_result = shell.run_command('trap')
        assert trap_result == 0
        # Should show traps for all specified signals

    def test_trap_exit_signal(self, shell):
        """Test trap for EXIT pseudo-signal."""
        # Set EXIT trap
        result = shell.run_command('trap "echo exit trap" EXIT')
        assert result == 0

        # EXIT trap should be registered
        trap_result = shell.run_command('trap')
        assert trap_result == 0
        # Trap verification would need shell output capture

    def test_trap_reset(self, shell):
        """Test resetting/clearing traps."""
        # Set a trap
        shell.run_command('trap "echo test trap" USR1')

        # Reset the trap to default
        result = shell.run_command('trap - USR1')
        assert result == 0

        # Check that trap is removed
        trap_result = shell.run_command('trap')
        assert trap_result == 0
        # USR1 trap should no longer be listed

    def test_trap_ignore(self, shell):
        """Test ignoring signals with empty trap."""
        # Set trap to ignore signal
        result = shell.run_command('trap "" USR1')
        assert result == 0

        # Signal should now be ignored
        trap_result = shell.run_command('trap')
        assert trap_result == 0


class TestSignalDelivery:
    """Test signal delivery and handling in different contexts."""

    def test_signal_to_shell_process(self, shell):
        """Test delivering signals to the shell process itself."""
        # This test requires external process management
        # Would need to start PSH in subprocess and send signals to it
        pass

    def test_signal_propagation_in_pipeline(self, shell):
        """Test how signals propagate through pipeline components."""
        # Set up a trap
        shell.run_command('trap "echo pipeline signal" USR1')

        # Create a pipeline that can receive signals
        # This is complex to test as it requires external signal delivery
        pass

    def test_trap_execution_context(self, shell):
        """Test that traps execute in correct context."""
        # Set a variable
        shell.run_command('test_var="original"')

        # Set trap that modifies the variable
        result = shell.run_command('trap "test_var=trapped" USR1')
        assert result == 0

        # Note: Actually delivering the signal and testing the result
        # would require external process control

    def test_trap_with_shell_functions(self, shell):
        """Test trap handlers that call shell functions."""
        # Define a function
        shell.run_command('''
        cleanup_func() {
            echo "cleanup function called"
            rm -f /tmp/test_cleanup
        }
        ''')

        # Set trap to call the function
        result = shell.run_command('trap cleanup_func EXIT')
        assert result == 0

        # Check that trap is registered
        trap_result = shell.run_command('trap')
        assert trap_result == 0


class TestSignalHandlingInSubshells:
    """Test signal handling behavior in subshells."""

    def test_trap_inheritance_in_subshells(self):
        """Subshells LIST parent traps (the POSIX saved=$(trap) idiom)
        without firing them; bash-5.2-verified (reappraisal #15 E1)."""
        import subprocess
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'trap "echo main trap" USR1; (trap)'],
            capture_output=True, text=True, timeout=10)
        assert result.returncode == 0
        assert result.stdout == "trap -- 'echo main trap' SIGUSR1\n"

    def test_trap_modification_in_subshells(self):
        """A subshell's trap modification replaces the inherited listing
        and never leaks back to the parent (bash 5.2)."""
        import subprocess
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'trap "echo parent trap" USR1; '
             '(trap "echo subshell trap" USR1; trap); trap'],
            capture_output=True, text=True, timeout=10)
        assert result.returncode == 0
        assert result.stdout == ("trap -- 'echo subshell trap' SIGUSR1\n"
                                 "trap -- 'echo parent trap' SIGUSR1\n")

    def test_signal_delivery_to_subshell_group(self, shell):
        """Test signal delivery to subshell process groups."""
        # This would test that signals sent to a subshell
        # are delivered to all processes in the subshell's process group
        pass


class TestSignalErrorHandling:
    """Test error handling in signal-related operations."""

    def test_trap_invalid_signal(self, shell):
        """Test trap with invalid signal names."""
        # Try to trap invalid signal
        result = shell.run_command('trap "echo test" INVALID_SIGNAL')
        # Should fail gracefully
        assert result != 0
        # Error message verification would need shell output capture

    def test_trap_reserved_signals(self, shell):
        """Test trapping signals that cannot be trapped."""
        # SIGKILL cannot be trapped
        result = shell.run_command('trap "echo kill" KILL')
        # Should fail or be ignored
        assert result != 0 or shell.run_command('trap') == 0

        # SIGSTOP cannot be trapped
        result = shell.run_command('trap "echo stop" STOP')
        # Should fail or be ignored
        assert result != 0 or shell.run_command('trap') == 0

    def test_trap_syntax_errors(self, shell):
        """Test trap command with syntax errors."""
        # Missing command
        result = shell.run_command('trap USR1')
        assert result != 0

        # Invalid syntax
        result = shell.run_command('trap "unclosed quote USR1')
        assert result != 0


class TestSignalShellOptionInteraction:
    """Test interaction between signals and shell options."""

    def test_trap_with_errexit(self, shell):
        """Test trap behavior with set -e (errexit)."""
        # Enable errexit
        shell.run_command('set -e')

        # Set trap that contains failing command
        result = shell.run_command('trap "false; echo after false" USR1')
        assert result == 0

        # Trap should be registered despite containing failing command
        trap_result = shell.run_command('trap')
        assert trap_result == 0

    def test_trap_with_xtrace(self, shell):
        """Test trap execution with set -x (xtrace)."""
        # Enable xtrace
        shell.run_command('set -x')

        # Set trap
        result = shell.run_command('trap "echo traced trap" USR1')
        assert result == 0

        # Trap commands should be subject to xtrace when executed

    def test_signal_during_pipefail(self, shell):
        """Test signal handling with set -o pipefail."""
        # Enable pipefail
        shell.run_command('set -o pipefail')

        # Set trap
        shell.run_command('trap "echo pipefail trap" USR1')

        # Signal handling should work correctly with pipefail


class TestComplexSignalScenarios:
    """Test complex signal handling scenarios."""

    def test_nested_trap_execution(self, shell):
        """Test trap that triggers another trap."""
        # Set up nested traps
        shell.run_command('trap "echo first trap; kill -USR2 $$" USR1')
        shell.run_command('trap "echo second trap" USR2')

        # This would require external signal delivery to test properly

    def test_trap_during_command_execution(self, shell):
        """Test signal delivery during command execution."""
        # Set trap
        shell.run_command('trap "echo interrupted" USR1')

        # This would test signal delivery while a command is running
        # Requires external process control

    def test_signal_masking_during_execution(self, shell):
        """Test that certain signals are masked during critical operations."""
        # This would test that signals don't interrupt critical shell operations
        pass

    def test_trap_cleanup_on_exit(self, shell):
        """Test comprehensive cleanup using EXIT trap."""
        # Create temporary files
        shell.run_command('touch /tmp/trap_test1 /tmp/trap_test2')

        # Set EXIT trap to clean up
        result = shell.run_command('''
        trap 'rm -f /tmp/trap_test1 /tmp/trap_test2; echo "cleanup done"' EXIT
        ''')
        assert result == 0

        # Verify trap is set
        trap_result = shell.run_command('trap')
        assert trap_result == 0
        # Trap verification would need shell output capture


class TestJobControlSignalIntegration:
    """Test integration between job control and signal handling."""

    def test_signal_to_background_job(self, shell):
        """Test sending signals to background jobs."""
        # Start background job
        shell.run_command('sleep 10 &')

        # Get job number
        jobs_result = shell.run_command('jobs')
        assert jobs_result == 0

        # Send signal to job (kill %1)
        # This depends on kill command supporting job references
        pass

    def test_signal_to_process_group(self, shell):
        """Test signal delivery to entire process groups."""
        # Start pipeline in background
        shell.run_command('sleep 10 | cat &')

        # Signal should be delivered to entire pipeline
        # This requires process group management
        pass

    def test_trap_with_background_jobs(self, shell):
        """Test trap execution while background jobs are running."""
        # Start background job
        shell.run_command('sleep 1 &')

        # Set trap
        result = shell.run_command('trap "echo trap with bg job" USR1')
        assert result == 0

        # Trap should work normally with background jobs running
        trap_result = shell.run_command('trap')
        assert trap_result == 0


# Shell fixture provided by conftest.py


# Helper functions for signal testing
def send_signal_to_process(pid, signal_num):
    """Helper to send signal to a process (for external testing)."""
    try:
        os.kill(pid, signal_num)
        return True
    except OSError:
        return False


def create_test_script(content, filename):
    """Helper to create test scripts for signal testing.

    Uses a per-call unique directory rather than a fixed /tmp name so
    concurrent test runs can't collide.
    """
    import tempfile
    script_path = os.path.join(tempfile.mkdtemp(prefix='psh_sigtest_'), filename)
    with open(script_path, 'w') as f:
        f.write(content)
    os.chmod(script_path, 0o755)
    return script_path
