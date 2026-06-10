"""Terminal raw-mode management for the interactive line editor."""

import sys
import termios
import tty


class TerminalManager:
    """Manages terminal mode for raw input handling."""

    def __init__(self):
        self.old_settings = None
        self.is_raw = False

    def enter_raw_mode(self):
        """Put terminal in raw mode to capture individual keystrokes."""
        # Enter raw mode for any TTY (including PTYs)
        # Note: isatty() returns True for both real terminals and pseudo-terminals
        # TCSANOW everywhere: the default TCSAFLUSH/TCSADRAIN wait for the
        # terminal's output queue to drain, which BLOCKS on a pty whose
        # master isn't currently being read (pexpect between expects, a
        # wedged terminal emulator). bash stays responsive there; so must we.
        if sys.stdin.isatty() and not self.is_raw:
            try:
                self.old_settings = termios.tcgetattr(sys.stdin)
                tty.setraw(sys.stdin.fileno(), termios.TCSANOW)
                self.is_raw = True
            except (termios.error, OSError):
                # If we can't set raw mode, continue without it
                pass

    def exit_raw_mode(self):
        """Restore normal terminal mode."""
        if self.old_settings is not None and self.is_raw:
            termios.tcsetattr(sys.stdin, termios.TCSANOW, self.old_settings)
            self.is_raw = False

    def __enter__(self):
        self.enter_raw_mode()
        return self

    def __exit__(self, exc_type, _exc_val, _exc_tb):
        self.exit_raw_mode()
