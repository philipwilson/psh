"""
Enhanced PTY test framework for PSH interactive testing.

This framework provides improved PTY handling for testing interactive features
that require real terminal emulation, including:
- Line editing with cursor movement
- History navigation
- Tab completion
- Signal handling
- Job control

Key improvements over basic pexpect approach:
- Better escape sequence handling
- More reliable prompt detection
- Improved buffering control
- Debug output capabilities
"""

import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

try:
    import pexpect
    import ptyprocess
    HAS_PEXPECT = True
except ImportError:
    HAS_PEXPECT = False
    pexpect = None
    ptyprocess = None

import pytest

# Add PSH to path
PSH_ROOT = Path(__file__).parent.parent.parent

# Matches OSC sequences (terminal title etc., terminated by BEL or ST),
# CSI sequences (cursor movement, colors), and other two-byte escapes.
ANSI_ESCAPE_RE = re.compile(
    r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'  # OSC ... BEL/ST (e.g. \x1b]0;title\x07)
    r'|\x1b\[[0-9;?]*[ -/]*[@-~]'         # CSI (e.g. \x1b[31C, \x1b[32m)
    r'|\x1b[@-Z\\-_]'                     # other C1 two-byte escapes
)


def strip_ansi(text: str) -> str:
    """Remove ANSI/OSC escape sequences from PTY output."""
    return ANSI_ESCAPE_RE.sub('', text)


@dataclass
class PTYTestConfig:
    """Configuration for PTY tests.

    The framework forces PS1 to the sentinel ``PSH$ `` (same convention as
    tests/system/interactive/test_pty_smoke.py) so prompt detection does not
    depend on the machine's user/host/cwd or prompt colors. If you override
    PS1 via ``env``, override ``prompt_pattern`` to match.
    """
    timeout: int = 5
    prompt_pattern: str = r'PSH\$ '  # sentinel prompt (see docstring)
    continuation_pattern: str = r'> '
    debug: bool = False
    encoding: str = 'utf-8'
    columns: int = 80
    rows: int = 24
    env: Optional[dict] = None
    extra_args: Optional[List[str]] = None


class PTYTestFramework:
    """Enhanced framework for PTY-based interactive testing."""

    def __init__(self, config: Optional[PTYTestConfig] = None):
        """Initialize framework with configuration."""
        if not HAS_PEXPECT:
            raise ImportError("pexpect required for PTY tests. Install with: pip install pexpect")

        self.config = config or PTYTestConfig()
        self.shell = None
        self.logfile = None
        self._output_buffer = []

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()

    def cleanup(self):
        """Clean up shell process and resources."""
        if self.shell:
            try:
                if self.shell.isalive():
                    # Try graceful exit
                    self.shell.sendline('exit')
                    self.shell.expect(pexpect.EOF, timeout=1)
            except Exception:
                pass

            try:
                if self.shell.isalive():
                    self.shell.terminate(force=True)
                self.shell.wait()
            except Exception:
                pass

            self.shell = None

        if self.logfile:
            try:
                self.logfile.close()
            except Exception:
                pass
            self.logfile = None

    def spawn_shell(self) -> pexpect.spawn:
        """Spawn PSH with proper PTY settings."""
        # Set up environment
        env = os.environ.copy()
        if self.config.env:
            env.update(self.config.env)

        # Force unbuffered I/O
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONPATH'] = str(PSH_ROOT)

        # Disable readline if it causes issues
        env['INPUTRC'] = '/dev/null'

        # Deterministic sentinel prompt unless the test supplied its own.
        if not (self.config.env and 'PS1' in self.config.env):
            env['PS1'] = 'PSH$ '

        # Build command
        cmd = [sys.executable, '-u', '-m', 'psh', '--norc', '--force-interactive']
        if self.config.extra_args:
            cmd.extend(self.config.extra_args)

        # Enable debug logging if requested
        if self.config.debug:
            self.logfile = sys.stdout

        # Spawn with specific terminal dimensions
        self.shell = pexpect.spawn(
            cmd[0], cmd[1:],
            timeout=self.config.timeout,
            encoding=self.config.encoding,
            dimensions=(self.config.rows, self.config.columns),
            env=env,
            logfile=self.logfile
        )

        # Set more aggressive buffering options
        self.shell.setecho(False)  # Don't echo input
        self.shell.delaybeforesend = 0.05  # Small delay between sends

        # Align the stream exactly past a fresh prompt (see method docstring)
        self._sync_initial_prompt()

        return self.shell

    def _sync_initial_prompt(self):
        """Align the pexpect stream exactly past a fresh primary prompt.

        psh prints its first prompt at startup AND another one in response
        to the wake-up CR, so a single expect() against the prompt pattern
        leaves a stale prompt in the stream — after which every
        run_command() slices its output one prompt-cycle behind (the cause
        of the historical test_interactive_features.py failures).

        Run a sentinel command whose expected output text never appears in
        its own echo (the arithmetic-sentinel trick from test_pty_smoke.py),
        match the output, then match the prompt that follows it: the stream
        is now deterministically aligned regardless of how many prompts the
        startup sequence produced.
        """
        time.sleep(0.1)
        self.shell.send('\r')
        self.shell.send('echo __PTY_SYNC__$((40+2))\r')
        self.shell.expect('__PTY_SYNC__42', timeout=self.config.timeout)
        self._wait_for_prompt()

    def _drain_stale_output(self):
        """Discard any output already buffered from previous interactions.

        Out-of-band prompts (e.g. the one psh prints after a Ctrl-C at the
        prompt) would otherwise satisfy run_command()'s prompt wait early.
        Draining immediately before sending a command makes the next prompt
        in the stream necessarily the post-command one.
        """
        try:
            while True:
                if not self.shell.read_nonblocking(size=4096, timeout=0.1):
                    break
        except (pexpect.TIMEOUT, pexpect.EOF):
            pass

    def _wait_for_prompt(self, timeout: Optional[int] = None):
        """Wait for prompt with better error handling."""
        timeout = timeout or self.config.timeout

        try:
            index = self.shell.expect([
                self.config.prompt_pattern,
                self.config.continuation_pattern,
                pexpect.TIMEOUT,
                pexpect.EOF
            ], timeout=timeout)

            if index == 2:  # TIMEOUT
                raise TimeoutError(f"Prompt timeout. Buffer: {self.shell.buffer}")
            elif index == 3:  # EOF
                raise EOFError("Shell terminated unexpectedly")

            return index == 0  # True if normal prompt, False if continuation

        except Exception as e:
            if self.config.debug:
                print(f"Prompt wait failed: {e}")
                print(f"Buffer: {repr(self.shell.buffer)}")
                print(f"Before: {repr(self.shell.before)}")
            raise

    def send_line(self, line: str):
        """Send a line with proper line ending."""
        self.shell.send(line + '\r')

    def send_text(self, text: str):
        """Send text without line ending."""
        self.shell.send(text)

    def send_key_sequence(self, sequence: str):
        """Send raw escape sequence."""
        self.shell.send(sequence)

    def send_arrow_key(self, direction: str):
        """Send arrow key escape sequence."""
        sequences = {
            'up': '\033[A',
            'down': '\033[B',
            'right': '\033[C',
            'left': '\033[D'
        }
        if direction not in sequences:
            raise ValueError(f"Unknown arrow direction: {direction}")
        self.shell.send(sequences[direction])

    def send_ctrl(self, char: str):
        """Send control character."""
        if len(char) != 1:
            raise ValueError("Control character must be single character")
        # Convert to control code
        ctrl_code = ord(char.upper()) - ord('A') + 1
        self.shell.send(chr(ctrl_code))

    def expect_output(self, pattern: Union[str, re.Pattern], timeout: Optional[int] = None) -> str:
        """Expect pattern and return matched output."""
        timeout = timeout or self.config.timeout

        if isinstance(pattern, str):
            # For exact string match, look for it anywhere in the output
            self.shell.expect([re.escape(pattern)], timeout=timeout)
        else:
            self.shell.expect([pattern], timeout=timeout)

        # Return everything before the match plus the match itself
        return self.shell.before + (self.shell.match.group(0) if self.shell.match else "")

    def run_command(self, cmd: str) -> str:
        """Run command and return its cleaned output.

        Robustness measures (each fixing a historical fragility):
        - drain stale buffered output first, so an out-of-band prompt
          (e.g. after Ctrl-C) can't satisfy the prompt wait early;
        - keep waiting while continuation prompts (PS2) arrive, so
          multiline commands return the full output;
        - strip ANSI/OSC escapes (prompt colors, title sequences,
          line-editor cursor movement) before returning;
        - drop echoed command lines from the output.
        """
        self._drain_stale_output()
        self.send_line(cmd)

        # Collect output across continuation prompts until the primary
        # prompt returns.
        segments = []
        while True:
            at_primary = self._wait_for_prompt()
            segments.append(self.shell.before or '')
            if at_primary:
                break

        output = strip_ansi(''.join(segments))

        # Normalize line endings; a bare CR repositions to column 0
        # (line-editor redraw), so keep only what follows the last CR.
        lines = []
        for line in output.replace('\r\n', '\n').split('\n'):
            lines.append(line.rsplit('\r', 1)[-1])

        # Remove echoed command lines (the editor echoes typed input).
        echoed = {part.strip() for part in cmd.split('\n')}
        lines = [ln for ln in lines if ln.strip() not in echoed]

        return '\n'.join(lines).strip()


class PTYTest:
    """Base class for PTY-based tests."""

    @pytest.fixture
    def pty_framework(self):
        """Provide PTY test framework."""
        config = PTYTestConfig(debug=False)  # Set True for debugging
        framework = PTYTestFramework(config)
        yield framework
        framework.cleanup()

    @pytest.fixture
    def shell(self, pty_framework):
        """Provide spawned shell."""
        return pty_framework.spawn_shell()


# Helper functions for common test patterns

@contextmanager
def interactive_shell(config: Optional[PTYTestConfig] = None):
    """Context manager for interactive shell testing."""
    framework = PTYTestFramework(config)
    try:
        framework.spawn_shell()
        yield framework
    finally:
        framework.cleanup()
