"""Signal handling utilities.

This module provides utilities for safe signal handling using the self-pipe trick.
The self-pipe pattern moves complex work out of signal handler context to avoid
reentrancy issues and ensure async-signal-safety.
"""
import fcntl
import os
import signal
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# Single source of truth for signal name <-> number mapping.
#
# Built from Python's signal.Signals enum, which reflects the actual platform
# signals (including BSD-specific SIGEMT/SIGINFO on macOS). Both `kill -l` and
# `trap -l` use these helpers so the two listings can never drift apart.
# --------------------------------------------------------------------------

def _build_number_to_name() -> Dict[int, str]:
    """Map signal number -> canonical name WITHOUT the SIG prefix.

    Where the platform aliases two names to one number (e.g. SIGABRT/SIGIOT,
    SIGCHLD/SIGCLD), signal.Signals(num).name gives the canonical member, which
    matches bash's choice on the common platforms.
    """
    mapping: Dict[int, str] = {}
    for sig in signal.Signals:
        name = sig.name
        if name.startswith('SIG') and not name.startswith('SIG_'):
            mapping[int(sig.value)] = name[3:]
    return mapping


# number -> bare name (e.g. 9 -> "KILL")
SIGNAL_NUMBER_TO_NAME: Dict[int, str] = _build_number_to_name()

# bare name -> number (e.g. "KILL" -> 9)
SIGNAL_NAME_TO_NUMBER: Dict[str, int] = {
    name: num for num, name in SIGNAL_NUMBER_TO_NAME.items()
}


def signal_name_to_number(name: str) -> Optional[int]:
    """Return the signal number for a name, or None if unknown.

    Accepts names with or without the SIG prefix, case-insensitively
    ("KILL", "kill", "SIGKILL", "sigkill" -> 9).
    """
    if not name:
        return None
    upper = name.upper()
    if upper.startswith('SIG'):
        upper = upper[3:]
    return SIGNAL_NAME_TO_NUMBER.get(upper)


def signal_number_to_name(num: int, *, with_prefix: bool = False) -> Optional[str]:
    """Return the bare signal name for a number, or None if unknown.

    With with_prefix=True, the SIG prefix is included ("SIGKILL").
    """
    name = SIGNAL_NUMBER_TO_NAME.get(num)
    if name is None:
        return None
    return f"SIG{name}" if with_prefix else name


def list_all_signals() -> str:
    """Render the full signal listing exactly like bash's `kill -l`/`trap -l`.

    Lists real signals numbered 1..N (no pseudo-signals), each as
    ``NUM) SIGNAME`` with the number right-justified to width 2, five entries
    per row, tab-separated, trailing newline. Self-adjusts to the platform via
    signal.Signals.
    """
    entries = [
        f"{num:>2}) SIG{name}"
        for num, name in sorted(SIGNAL_NUMBER_TO_NAME.items())
    ]
    # bash emits each entry followed by a tab; on every 5th column that
    # trailing tab is replaced by a newline. A partial final row keeps its
    # trailing tab and a newline is appended. This reproduces `kill -l`
    # byte-for-byte.
    out = []
    for idx, entry in enumerate(entries, start=1):
        out.append(entry)
        out.append('\n' if idx % 5 == 0 else '\t')
    if not out or out[-1] != '\n':
        out.append('\n')
    return ''.join(out)


class SignalNotifier:
    """Self-pipe pattern for safe signal notification.

    Signal handlers write to a pipe, main loop reads from it.
    This moves all complex work out of signal handler context.

    The self-pipe trick is the standard Unix pattern for handling signals
    safely in event-driven programs. The signal handler only performs
    async-signal-safe operations (os.write), while the main loop handles
    the actual work.

    Example:
        notifier = SignalNotifier()

        # In signal handler:
        signal.signal(signal.SIGCHLD, lambda s, f: notifier.notify(s))

        # In main loop:
        notifications = notifier.drain_notifications()
        for sig in notifications:
            handle_signal(sig)
    """

    # Keep internal signal pipe descriptors away from user-facing low FDs
    # so "exec 3>file" style redirections don't clobber shell internals.
    _INTERNAL_FD_MIN = 64

    def __init__(self):
        """Create a self-pipe for signal notifications."""
        pipe_r, pipe_w = os.pipe()

        # Make both ends non-blocking:
        # - Write end: prevents signal handler from blocking (signal safety)
        # - Read end: prevents drain_notifications() from blocking when
        #   no signals are pending (called from the REPL loop)
        for fd in (pipe_r, pipe_w):
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Relocate to high-numbered FDs to avoid collisions with shell
        # scripts that intentionally manipulate low FDs like 3, 4, etc.
        self._pipe_r = self._promote_internal_fd(pipe_r)
        self._pipe_w = self._promote_internal_fd(pipe_w)

    def _promote_internal_fd(self, fd: int) -> int:
        """Move an FD into the reserved internal range if needed."""
        if fd >= self._INTERNAL_FD_MIN:
            return fd

        dup_cmd = getattr(fcntl, "F_DUPFD_CLOEXEC", fcntl.F_DUPFD)
        promoted_fd = fcntl.fcntl(fd, dup_cmd, self._INTERNAL_FD_MIN)

        # F_DUPFD doesn't preserve CLOEXEC, so set it explicitly.
        if dup_cmd == fcntl.F_DUPFD:
            fd_flags = fcntl.fcntl(promoted_fd, fcntl.F_GETFD)
            fcntl.fcntl(promoted_fd, fcntl.F_SETFD, fd_flags | fcntl.FD_CLOEXEC)

        os.close(fd)
        return promoted_fd

    def notify(self, signal_num: int):
        """Called from signal handler to notify main loop.

        This is async-signal-safe (only uses os.write).

        Args:
            signal_num: Signal number that was received
        """
        try:
            # Write signal number to pipe
            # Using bytes() is async-signal-safe
            os.write(self._pipe_w, bytes([signal_num]))
        except OSError:
            # Pipe full or other error - main loop will handle
            # Don't raise exception in signal handler
            pass

    def get_fd(self) -> int:
        """Get file descriptor for select()/poll().

        This allows integration with event loops.

        Returns:
            Read file descriptor for the notification pipe
        """
        return self._pipe_r

    def drain_notifications(self) -> List[int]:
        """Drain pending notifications. Call from main loop.

        This is safe to call from normal (non-signal) context.

        Returns:
            List of signal numbers that were notified
        """
        notifications = []
        try:
            while True:
                # Read in chunks for efficiency
                data = os.read(self._pipe_r, 1024)
                if not data:
                    break
                # Convert bytes to signal numbers
                notifications.extend(data)
        except OSError:
            # EAGAIN/EWOULDBLOCK - no more data
            pass
        return notifications

    def close(self):
        """Clean up pipe resources (idempotent).

        The fds are marked closed (-1) so a second close() — e.g. explicit
        cleanup followed by __del__ at garbage collection — cannot close an
        unrelated fd that was since allocated the same number.
        """
        for attr in ('_pipe_r', '_pipe_w'):
            fd = getattr(self, attr, -1)
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, attr, -1)

    def __del__(self):
        """Automatic cleanup on garbage collection."""
        try:
            self.close()
        except Exception:
            # Don't raise exceptions in __del__
            pass


@dataclass
class SignalHandlerRecord:
    """Record of a signal handler registration."""
    signal_num: int
    signal_name: str
    handler: Any  # Handler function or SIG_DFL/SIG_IGN
    component: str  # Which component set this handler
    timestamp: datetime
    call_stack: Optional[str] = None  # Stack trace for debugging


class SignalRegistry:
    """Central registry for tracking signal handler changes.

    This provides visibility into which components are managing signals,
    helps detect conflicts, and enables debugging of signal-related issues.

    The registry tracks every signal.signal() call, recording:
    - Which signal was modified
    - What handler was set (function, SIG_DFL, SIG_IGN)
    - Which component made the change
    - When the change was made
    - Stack trace (for debugging)

    Example:
        registry = SignalRegistry()

        # Register handler changes
        registry.register(signal.SIGINT, my_handler, "SignalManager")

        # Get report
        print(registry.report())

        # Validate configuration
        issues = registry.validate()
        if issues:
            print("Signal configuration issues:", issues)
    """

    # Well-known signal names for better reporting
    SIGNAL_NAMES = {
        signal.SIGINT: "SIGINT",
        signal.SIGTERM: "SIGTERM",
        signal.SIGHUP: "SIGHUP",
        signal.SIGQUIT: "SIGQUIT",
        signal.SIGTSTP: "SIGTSTP",
        signal.SIGTTOU: "SIGTTOU",
        signal.SIGTTIN: "SIGTTIN",
        signal.SIGCHLD: "SIGCHLD",
        signal.SIGPIPE: "SIGPIPE",
    }

    def __init__(self, capture_stack: bool = False):
        """Initialize signal registry.

        Args:
            capture_stack: If True, capture stack trace on each registration
                          (useful for debugging but has performance cost)
        """
        # Map of signal number -> list of records (chronological)
        self._history: Dict[int, List[SignalHandlerRecord]] = {}

        # Map of signal number -> current record
        self._current: Dict[int, SignalHandlerRecord] = {}

        self._capture_stack = capture_stack
        self._enabled = True

    def register(self, sig: int, handler: Any, component: str) -> Any:
        """Register a signal handler change and set it.

        This is a wrapper around signal.signal() that also records the change.

        Args:
            sig: Signal number
            handler: Handler function or SIG_DFL/SIG_IGN
            component: Name of component setting the handler

        Returns:
            Previous handler (same as signal.signal())
        """
        if not self._enabled:
            return signal.signal(sig, handler)

        # Capture stack if enabled
        call_stack = None
        if self._capture_stack:
            # Skip the first two frames (this function and signal.signal)
            call_stack = ''.join(traceback.format_stack()[:-2])

        # Get signal name
        signal_name = self.SIGNAL_NAMES.get(sig, f"Signal-{sig}")

        # Create record
        record = SignalHandlerRecord(
            signal_num=sig,
            signal_name=signal_name,
            handler=handler,
            component=component,
            timestamp=datetime.now(),
            call_stack=call_stack
        )

        # Add to history
        if sig not in self._history:
            self._history[sig] = []
        self._history[sig].append(record)

        # Update current
        self._current[sig] = record

        # Actually set the handler
        try:
            previous = signal.signal(sig, handler)
            return previous
        except (OSError, ValueError):
            # Signal not valid on this platform
            # Remove the record we just added
            self._history[sig].pop()
            if not self._history[sig]:
                del self._history[sig]
            if sig in self._current:
                del self._current[sig]
            raise

    def get_handler(self, sig: int) -> Optional[SignalHandlerRecord]:
        """Get current registered handler for signal.

        Args:
            sig: Signal number

        Returns:
            SignalHandlerRecord if signal has been registered, None otherwise
        """
        return self._current.get(sig)

    def get_all_handlers(self) -> Dict[int, SignalHandlerRecord]:
        """Get all currently registered handlers.

        Returns:
            Dictionary mapping signal number to current record
        """
        return self._current.copy()

    def get_history(self, sig: Optional[int] = None) -> List[SignalHandlerRecord]:
        """Get history of signal handler changes.

        Args:
            sig: Signal number, or None for all signals

        Returns:
            List of records in chronological order
        """
        if sig is not None:
            return self._history.get(sig, []).copy()

        # Return all records sorted by timestamp
        all_records = []
        for records in self._history.values():
            all_records.extend(records)
        return sorted(all_records, key=lambda r: r.timestamp)

    def validate(self) -> List[str]:
        """Validate signal configuration and detect issues.

        Returns:
            List of issue descriptions (empty if no issues)
        """
        issues = []

        # Check for signals that changed multiple times
        for sig, records in self._history.items():
            if len(records) > 5:
                signal_name = self.SIGNAL_NAMES.get(sig, f"Signal-{sig}")
                issues.append(
                    f"{signal_name} has been modified {len(records)} times - "
                    "this may indicate a configuration issue"
                )

        # Check for rapid changes (multiple changes in short time)
        for sig, records in self._history.items():
            if len(records) < 2:
                continue

            # Look for multiple changes within 1 second
            rapid_changes = []
            for i in range(1, len(records)):
                time_diff = (records[i].timestamp - records[i-1].timestamp).total_seconds()
                if time_diff < 1.0:
                    rapid_changes.append((i-1, i))

            if rapid_changes:
                signal_name = self.SIGNAL_NAMES.get(sig, f"Signal-{sig}")
                issues.append(
                    f"{signal_name} had {len(rapid_changes)} rapid changes - "
                    "this may indicate signal handler conflicts"
                )

        return issues

    def report(self, verbose: bool = False) -> str:
        """Generate human-readable report of signal state.

        Args:
            verbose: Include full history and stack traces

        Returns:
            Formatted report string
        """
        lines = ["Signal Handler Registry Report", "=" * 50, ""]

        if not self._current:
            lines.append("No signal handlers registered.")
            return '\n'.join(lines)

        # Current handlers
        lines.append("Current Signal Handlers:")
        lines.append("-" * 50)

        for sig in sorted(self._current.keys()):
            record = self._current[sig]
            handler_str = self._format_handler(record.handler)

            lines.append(f"{record.signal_name:10} -> {handler_str}")
            lines.append(f"             Set by: {record.component}")
            lines.append(f"             At: {record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

            if verbose and record.call_stack:
                lines.append(f"             Stack trace:")
                for line in record.call_stack.split('\n'):
                    if line.strip():
                        lines.append(f"               {line}")

            lines.append("")

        # Validation
        issues = self.validate()
        if issues:
            lines.append("Validation Issues:")
            lines.append("-" * 50)
            for issue in issues:
                lines.append(f"⚠️  {issue}")
            lines.append("")

        # History summary if verbose
        if verbose:
            lines.append("Signal Handler History:")
            lines.append("-" * 50)

            for sig in sorted(self._history.keys()):
                signal_name = self.SIGNAL_NAMES.get(sig, f"Signal-{sig}")
                records = self._history[sig]

                lines.append(f"{signal_name}: {len(records)} changes")
                for i, record in enumerate(records, 1):
                    handler_str = self._format_handler(record.handler)
                    timestamp = record.timestamp.strftime('%H:%M:%S')
                    lines.append(f"  {i}. [{timestamp}] {record.component} -> {handler_str}")
                lines.append("")

        # Summary
        lines.append("Summary:")
        lines.append("-" * 50)
        lines.append(f"Total signals registered: {len(self._current)}")
        lines.append(f"Total handler changes: {sum(len(h) for h in self._history.values())}")

        return '\n'.join(lines)

    def _format_handler(self, handler: Any) -> str:
        """Format handler for display.

        Args:
            handler: Handler function or constant

        Returns:
            Human-readable string
        """
        if handler == signal.SIG_DFL:
            return "SIG_DFL (default)"
        elif handler == signal.SIG_IGN:
            return "SIG_IGN (ignore)"
        elif callable(handler):
            # Try to get function name
            if hasattr(handler, '__name__'):
                return f"{handler.__name__}()"
            else:
                return f"<handler at {hex(id(handler))}>"
        else:
            return str(handler)

    def clear(self):
        """Clear all records (for testing)."""
        self._history.clear()
        self._current.clear()

    def enable(self):
        """Enable registry tracking."""
        self._enabled = True

    def disable(self):
        """Disable registry tracking (for performance)."""
        self._enabled = False


# Global signal registry instance
# This is used by SignalManager and other components
_global_registry: Optional[SignalRegistry] = None


def get_signal_registry(create: bool = True) -> Optional[SignalRegistry]:
    """Get the global signal registry instance.

    Args:
        create: If True, create registry if it doesn't exist

    Returns:
        SignalRegistry instance, or None if not created
    """
    global _global_registry

    if _global_registry is None and create:
        _global_registry = SignalRegistry(capture_stack=False)

    return _global_registry


def set_signal_registry(registry: Optional[SignalRegistry]):
    """Set the global signal registry instance.

    Args:
        registry: SignalRegistry instance, or None to disable tracking
    """
    global _global_registry
    _global_registry = registry
