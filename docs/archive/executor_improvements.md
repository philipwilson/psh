# PSH Executor, Signal Handling, and Job Control Improvements

**Document Version:** 2.0 (Consolidated)
**Date:** 2025-01-18
**Status:** Master recommendations document

## Executive Summary

This document consolidates all recommendations for improving PSH's executor architecture, signal handling, and process group management. The current implementation is production-quality with correct POSIX semantics, but these improvements will enhance reliability, debuggability, observability, and maintainability.

**Key Improvement Areas:**
1. Process group synchronization (eliminate polling race condition)
2. Signal handler safety (move work out of signal context)
3. Code consolidation (unify duplicated process management logic)
4. Observability (metrics, logging, diagnostics)
5. Error handling (graceful degradation, better debugging)

All recommendations are **backward compatible** and can be implemented incrementally.

---

## Table of Contents

- [Current State Analysis](#current-state-analysis)
- [Critical Priority Recommendations](#critical-priority-recommendations)
- [High Priority Recommendations](#high-priority-recommendations)
- [Medium Priority Recommendations](#medium-priority-recommendations)
- [Low Priority Recommendations](#low-priority-recommendations)
- [Implementation Roadmap](#implementation-roadmap)
- [Testing Strategy](#testing-strategy)

---

## Current State Analysis

### Code Organization

The executor package demonstrates clear separation of concerns:

**Primary Components:**
- `psh/executor/pipeline.py:107-336` - Pipeline execution with job control
- `psh/executor/strategies.py:150-449` - Command execution strategies (builtin, external, function)
- `psh/executor/subshell.py:115-199` - Subshell isolation
- `psh/job_control.py:95-320` - Job state tracking and waiting
- `psh/interactive/signal_manager.py:39-126` - Signal disposition setup

### Current Behavior

**Pipeline Execution** (`pipeline.py:160-205`):
- Children set their own process groups via `os.setpgid(0, 0)`
- Temporarily ignore `SIGTTOU` during setup
- Reset interactive signals before execution
- Non-leader children poll for up to 50ms waiting for parent's `setpgid`

**Job Control** (`job_control.py:266-347`):
- Synchronous waiting with `waitpid(-pgid, WUNTRACED)`
- Handles both foreground and background jobs
- Restores terminal control after foreground job completion

**Signal Handling** (`signal_manager.py:39-126`):
- Interactive mode: custom handlers for traps, `SIG_IGN` for job control signals
- Script mode: mostly default handlers
- `SIGCHLD` handler does full job reaping in signal context

### Identified Issues

1. **Code Duplication**: Process creation and job control logic repeated across:
   - `pipeline.py` (pipeline children)
   - `strategies.py` (`ExternalExecutionStrategy`, `BuiltinExecutionStrategy`)
   - `subshell.py` (subshell forking)

2. **Race Conditions**:
   - Process group setup uses `time.sleep()` polling (50ms timeout)
   - SIGCHLD handler can race with explicit `wait_for_job()` calls

3. **Signal Safety**: SIGCHLD handler performs complex Python operations in signal context

4. **Silent Failures**: `tcsetpgrp` errors suppressed even with `debug-exec` enabled

5. **State Management**: Foreground job cleanup scattered across multiple code paths

---

## Critical Priority Recommendations

These address fundamental reliability and correctness issues.

### C1. Eliminate Process Group Setup Race Condition

**Problem**: Non-leader pipeline children use `time.sleep()` polling to wait for parent's `setpgid()`.

**Current Code** (`pipeline.py:173-188`):
```python
for attempt in range(50):  # Try for up to 50ms
    try:
        current_pgid = os.getpgrp()
        if current_pgid != os.getpid():
            break
    except OSError:
        pass
    time.sleep(0.001)  # Wait 1ms
```

**Issues**:
- Not guaranteed to be reliable on heavily loaded systems
- Wastes CPU cycles on polling
- Hard-coded 50ms timeout may be insufficient
- Race condition still theoretically possible

**Recommended Solution**: Use pipe-based synchronization (atomic and deterministic).

**Implementation**:

```python
def _execute_pipeline_with_forking(self, pipeline, is_background=False):
    """Execute pipeline with proper process group synchronization."""

    # Create synchronization pipe before forking
    sync_pipe_r, sync_pipe_w = os.pipe()

    pgid = None
    pids = []

    for i, command in enumerate(pipeline.commands):
        pid = os.fork()

        if pid == 0:  # Child
            # Close unused pipe end
            os.close(sync_pipe_w)

            try:
                if i == 0:
                    # First child becomes process group leader
                    os.setpgid(0, 0)
                    pgid_to_use = os.getpid()
                else:
                    # Non-leader children wait for parent signal
                    # This blocks until parent closes write end
                    try:
                        os.read(sync_pipe_r, 1)
                    except OSError:
                        pass  # EOF or error - parent closed pipe

                    pgid_to_use = None  # Will be set by parent

                os.close(sync_pipe_r)

                # Temporarily ignore SIGTTOU
                signal.signal(signal.SIGTTOU, signal.SIG_IGN)

                # Reset other signals
                self._reset_child_signals()

                # Set up pipeline I/O
                self._setup_pipeline_redirections(i, pipes, command)

                # Execute command
                exit_code = self._execute_pipeline_command(command, i, is_last)
                os._exit(exit_code)

            except Exception as e:
                print(f"psh: error: {e}", file=sys.stderr)
                os._exit(1)

        else:  # Parent
            if i == 0:
                # First child is process group leader
                pgid = pid
                os.setpgid(pid, pid)
            else:
                # Add subsequent children to group
                os.setpgid(pid, pgid)

            pids.append(pid)

    # Parent closes read end (not needed)
    os.close(sync_pipe_r)

    # Signal all children that process group is ready
    # Closing write end sends EOF to all waiting children
    os.close(sync_pipe_w)

    # Rest of pipeline management...
    return self._wait_for_pipeline(pids, pgid, is_background)
```

**Benefits**:
- ✅ Atomic and deterministic synchronization
- ✅ No polling or wasted CPU cycles
- ✅ Works reliably under any system load
- ✅ Standard Unix practice (pipe-based handshake)

**Testing**:
```bash
# Test under heavy load
$ stress-ng --cpu 8 --timeout 60s &
$ psh -c "seq 1 1000 | head -10 | tail -5"

# Test with long pipelines
$ psh -c "echo test | cat | cat | cat | cat | cat"
```

---

### C2. Improve SIGCHLD Handler Signal Safety

**Problem**: `_handle_sigchld` performs complex Python operations directly in signal handler context, which is not guaranteed to be safe and can lead to reentrancy bugs or deadlocks.

**Current Code** (`signal_manager.py:97-126`):
```python
def _handle_sigchld(self, signum, frame):
    """Handle child process state changes."""
    while True:
        try:
            wait_flags = os.WNOHANG | os.WUNTRACED
            pid, status = os.waitpid(-1, wait_flags)
            if pid == 0:
                break

            job = self.job_manager.get_job_by_pid(pid)
            if job:
                job.update_process_status(pid, status)
                job.update_state()
                # ... more Python operations ...
```

**Issues**:
- Complex Python code in signal handler (not async-signal-safe)
- Potential for reentrancy bugs
- Risk of deadlock or interpreter state corruption

**Recommended Solution**: Implement self-pipe trick to defer work to main loop.

**Implementation**:

**New File**: `psh/utils/signal_utils.py`

```python
"""Signal handling utilities."""
import os
import fcntl

class SignalNotifier:
    """Self-pipe pattern for safe signal notification.

    Signal handlers write to a pipe, main loop reads from it.
    This moves all complex work out of signal handler context.
    """

    def __init__(self):
        self._pipe_r, self._pipe_w = os.pipe()

        # Make write end non-blocking to prevent signal handler blocking
        flags = fcntl.fcntl(self._pipe_w, fcntl.F_GETFL)
        fcntl.fcntl(self._pipe_w, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def notify(self, signal_num: int):
        """Called from signal handler to notify main loop.

        This is async-signal-safe (only uses os.write).
        """
        try:
            # Write signal number to pipe
            os.write(self._pipe_w, bytes([signal_num]))
        except OSError:
            # Pipe full or other error - main loop will handle
            pass

    def get_fd(self) -> int:
        """Get file descriptor for select()/poll()."""
        return self._pipe_r

    def drain_notifications(self) -> list[int]:
        """Drain pending notifications. Call from main loop."""
        notifications = []
        try:
            while True:
                data = os.read(self._pipe_r, 1024)
                if not data:
                    break
                notifications.extend(data)
        except OSError:
            pass
        return notifications

    def close(self):
        """Clean up pipe."""
        try:
            os.close(self._pipe_r)
            os.close(self._pipe_w)
        except OSError:
            pass
```

**Update SignalManager**:

```python
import signal as sig_module
from psh.utils.signal_utils import SignalNotifier

class SignalManager(InteractiveComponent):
    """Manages signal handling for the interactive shell."""

    def __init__(self, shell):
        super().__init__(shell)
        self._original_handlers: Dict[int, Callable] = {}
        self._interactive_mode = not shell.state.is_script_mode
        self._sigchld_notifier = SignalNotifier()
        self._in_sigchld_processing = False

    def _handle_sigchld(self, signum, frame):
        """Minimal signal handler - just notify main loop.

        This is async-signal-safe (only calls os.write).
        """
        self._sigchld_notifier.notify(sig_module.SIGCHLD)

    def process_sigchld_notifications(self):
        """Process pending SIGCHLD notifications.

        This should be called from the main REPL loop periodically.
        It does the actual job reaping outside of signal handler context.
        """
        # Prevent reentrancy
        if self._in_sigchld_processing:
            return

        self._in_sigchld_processing = True
        try:
            # Drain notification pipe
            notifications = self._sigchld_notifier.drain_notifications()

            if not notifications:
                return

            # Now do the actual child reaping (safe outside signal context)
            while True:
                try:
                    wait_flags = os.WNOHANG | os.WUNTRACED
                    pid, status = os.waitpid(-1, wait_flags)
                    if pid == 0:
                        break

                    # Record metrics
                    if hasattr(self.state, 'process_metrics'):
                        self.state.process_metrics.record_sigchld()

                    # Update job state
                    job = self.job_manager.get_job_by_pid(pid)
                    if job:
                        job.update_process_status(pid, status)
                        job.update_state()

                        # Handle stopped foreground jobs
                        if job.state == JobState.STOPPED and job.foreground:
                            job.notified = False
                            if self.state.supports_job_control:
                                try:
                                    os.tcsetpgrp(self.state.terminal_fd, os.getpgrp())
                                except OSError:
                                    pass
                except OSError:
                    break
        finally:
            self._in_sigchld_processing = False

    def get_sigchld_fd(self) -> int:
        """Get file descriptor for SIGCHLD notifications.

        Can be used with select() to wait for child events.
        """
        return self._sigchld_notifier.get_fd()
```

**Update Interactive Loop**:

```python
# In psh/interactive/repl.py or equivalent:

def run_interactive_loop(self):
    """Main REPL loop."""
    while True:
        # Process any pending SIGCHLD notifications
        self.signal_manager.process_sigchld_notifications()

        # Show job notifications
        self.job_manager.notify_completed_jobs()

        # Read next command
        try:
            line = input(self.prompt_manager.get_prompt())
        except EOFError:
            break

        # Execute command
        self.execute_line(line)
```

**Benefits**:
- ✅ Strictly async-signal-safe (only `os.write()` in handler)
- ✅ No risk of deadlock or interpreter corruption
- ✅ Standard Unix practice (self-pipe trick)
- ✅ Can integrate with `select()` for efficiency
- ✅ More reliable and maintainable

**Trade-offs**:
- Slightly delayed background job notifications (until next REPL iteration)
- More complex implementation (but standard pattern)

---

### C3. Unify Process Creation and Job Control Logic

**Problem**: Significant code duplication for process and job management across multiple files.

**Current Duplication**:
- `psh/executor/pipeline.py:160-242` - Pipeline child forking
- `psh/executor/strategies.py:152-191` - Builtin background execution
- `psh/executor/strategies.py:362-407` - External command execution
- `psh/executor/subshell.py:127-199` - Subshell forking

**Each location duplicates**:
- `os.fork()` + error handling
- `os.setpgid()` coordination
- Signal reset (`signal.signal(..., SIG_DFL)`)
- Terminal control transfer
- Job object creation
- Exit code handling

**Recommended Solution**: Create unified process launcher component.

**Implementation**:

**New File**: `psh/executor/process_launcher.py`

```python
"""Unified process launcher for all command execution."""
import os
import signal
import sys
from typing import Optional, Callable, Tuple
from dataclasses import dataclass
from enum import Enum

class ProcessRole(Enum):
    """Role of process in job."""
    SINGLE = "single"              # Standalone command
    PIPELINE_LEADER = "pipeline_leader"  # First in pipeline
    PIPELINE_MEMBER = "pipeline_member"  # Non-first in pipeline

@dataclass
class ProcessConfig:
    """Configuration for launching a process."""
    role: ProcessRole
    pgid: Optional[int] = None     # Process group to join (None = create new)
    foreground: bool = True        # Foreground or background
    sync_pipe_r: Optional[int] = None  # For pipeline synchronization
    io_setup: Optional[Callable] = None  # I/O redirection callback

class ProcessLauncher:
    """Unified component for launching processes with proper job control.

    This centralizes all process creation logic to ensure consistency
    across pipelines, external commands, and background jobs.
    """

    def __init__(self, shell_state, job_manager, io_manager):
        self.state = shell_state
        self.job_manager = job_manager
        self.io_manager = io_manager

    def launch(self,
               execute_fn: Callable[[], int],
               config: ProcessConfig) -> Tuple[int, int]:
        """Launch a process with proper job control setup.

        Args:
            execute_fn: Function to execute in child (returns exit code)
            config: Process configuration

        Returns:
            (pid, pgid) tuple
        """
        pid = os.fork()

        if pid == 0:  # Child process
            self._child_setup_and_exec(execute_fn, config)
            # Does not return
        else:  # Parent process
            pgid = self._parent_setup(pid, config)
            return pid, pgid

    def _child_setup_and_exec(self, execute_fn: Callable[[], int],
                               config: ProcessConfig):
        """Child process setup and execution."""
        exit_code = 127

        try:
            # 1. Set process group
            if config.role == ProcessRole.PIPELINE_LEADER:
                os.setpgid(0, 0)  # Become leader
            elif config.role == ProcessRole.PIPELINE_MEMBER:
                # Wait for parent signal (pipe-based sync)
                if config.sync_pipe_r is not None:
                    try:
                        os.read(config.sync_pipe_r, 1)
                    except OSError:
                        pass
                    os.close(config.sync_pipe_r)
            elif config.role == ProcessRole.SINGLE:
                os.setpgid(0, 0)  # Own process group

            # 2. Reset signals to default
            self._reset_child_signals()

            # 3. Set up I/O redirections
            if config.io_setup:
                config.io_setup()

            # 4. Execute command
            exit_code = execute_fn()

            if not isinstance(exit_code, int):
                exit_code = 0 if exit_code else 1

        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1

        except KeyboardInterrupt:
            exit_code = 130  # 128 + SIGINT

        except Exception as e:
            print(f"psh: error: {e}", file=sys.stderr)
            if self.state.options.get('debug-exec'):
                import traceback
                traceback.print_exc()
            exit_code = 1

        finally:
            # Ensure we always exit cleanly
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except:
                pass
            os._exit(exit_code)

    def _parent_setup(self, pid: int, config: ProcessConfig) -> int:
        """Parent process setup after fork."""
        # Determine process group
        if config.role == ProcessRole.PIPELINE_LEADER or config.role == ProcessRole.SINGLE:
            pgid = pid
            os.setpgid(pid, pid)
        else:
            pgid = config.pgid
            if pgid is not None:
                os.setpgid(pid, pgid)

        return pgid

    def _reset_child_signals(self):
        """Reset all signals to default in child process."""
        signals_to_reset = [
            signal.SIGINT,
            signal.SIGQUIT,
            signal.SIGTSTP,
            signal.SIGTTOU,
            signal.SIGTTIN,
            signal.SIGCHLD,
        ]

        for sig in signals_to_reset:
            try:
                signal.signal(sig, signal.SIG_DFL)
            except (OSError, ValueError):
                # Signal not available on this platform
                pass

    def launch_job(self,
                   execute_fn: Callable[[], int],
                   command_str: str,
                   foreground: bool = True) -> 'Job':
        """Launch a single command as a job.

        This is a convenience method that combines process launching
        with job creation and terminal control.

        Args:
            execute_fn: Function to execute
            command_str: Command string (for job display)
            foreground: Foreground or background

        Returns:
            Job object
        """
        config = ProcessConfig(
            role=ProcessRole.SINGLE,
            foreground=foreground
        )

        pid, pgid = self.launch(execute_fn, config)

        # Create job
        job = self.job_manager.create_job([pid], command_str, pgid)
        job.foreground = foreground

        # Transfer terminal control if foreground
        if foreground and self.state.supports_job_control:
            try:
                os.tcsetpgrp(self.state.terminal_fd, pgid)
                self.state.foreground_pgid = pgid
            except OSError as e:
                if self.state.options.get('debug-exec'):
                    print(f"DEBUG: Failed to transfer terminal: {e}", file=sys.stderr)

        return job
```

**Usage in PipelineExecutor**:

```python
from psh.executor.process_launcher import ProcessLauncher, ProcessConfig, ProcessRole

class PipelineExecutor:
    def __init__(self, state, job_manager, io_manager):
        self.state = state
        self.job_manager = job_manager
        self.io_manager = io_manager
        self.launcher = ProcessLauncher(state, job_manager, io_manager)

    def execute(self, pipeline, is_background=False):
        """Execute pipeline using unified launcher."""
        # Create sync pipe for pipeline coordination
        sync_pipe_r, sync_pipe_w = os.pipe()

        pgid = None
        pids = []

        for i, command in enumerate(pipeline.commands):
            role = ProcessRole.PIPELINE_LEADER if i == 0 else ProcessRole.PIPELINE_MEMBER

            config = ProcessConfig(
                role=role,
                pgid=pgid,
                foreground=not is_background,
                sync_pipe_r=sync_pipe_r if i > 0 else None,
                io_setup=lambda: self._setup_pipeline_io(i, command)
            )

            pid, pgid = self.launcher.launch(
                lambda: self._execute_command(command),
                config
            )
            pids.append(pid)

        # Close sync pipe (signals children)
        os.close(sync_pipe_r)
        os.close(sync_pipe_w)

        # Create job and wait
        job = self.job_manager.create_job(pids, str(pipeline), pgid)
        return self._wait_for_job(job, is_background)
```

**Usage in ExternalExecutionStrategy**:

```python
def execute_external(self, command_path, args, node):
    """Execute external command using unified launcher."""

    def execute_fn():
        # Apply redirections
        self.io_manager.apply_redirections(node.redirects)
        # Execute
        os.execv(command_path, args)
        return 127  # Not reached

    job = self.launcher.launch_job(
        execute_fn,
        command_str=' '.join(args),
        foreground=not node.background
    )

    if not node.background:
        return self.job_manager.wait_for_job(job)
    else:
        return 0
```

**Benefits**:
- ✅ Single source of truth for process management
- ✅ Bug fixes apply everywhere automatically
- ✅ Consistent signal handling and job control
- ✅ Simpler executor code (delegates low-level details)
- ✅ Easier to test and maintain

---

## High Priority Recommendations

These significantly improve reliability and usability.

### H1. Add TTY Detection and Graceful Degradation

**Problem**: Terminal control errors suppressed even with `debug-exec` enabled. Tests and non-TTY environments get confusing failures.

**Implementation**: See consolidated document section "Add TTY Detection and Graceful Degradation" from previous detailed recommendations.

**Key Changes**:
- Detect TTY capabilities at startup
- Store in `ShellState.supports_job_control`
- Skip terminal control when unavailable
- Provide clear error messages

**Benefits**:
- ✅ Better error messages in non-TTY contexts (cron, CI/CD)
- ✅ Tests can detect and adapt to TTY absence
- ✅ Clear user feedback

---

### H2. Centralize Signal Disposition Tracking

**Problem**: 40+ `signal.signal()` calls across 6 files with no central tracking.

**Implementation**: Create `SignalRegistry` class (see detailed implementation in previous recommendations).

**Key Features**:
- Track all signal handler changes
- Record which component set each handler
- Provide validation and reporting
- Debug command to show current state

**Benefits**:
- ✅ Visibility into signal configuration
- ✅ Debugging tool for signal issues
- ✅ Detect conflicting handlers
- ✅ Documentation of architecture

---

### H3. Centralize Child Signal Reset Logic

**Problem**: Signal reset boilerplate duplicated across multiple fork paths.

**Solution**: Create shared helper method.

**Implementation**:

```python
# In SignalManager:

def reset_child_signals(self):
    """Reset all signals to default for child process.

    This should be called in all forked children to ensure
    they don't inherit the shell's signal handlers.
    """
    signals_to_reset = [
        signal.SIGINT,
        signal.SIGQUIT,
        signal.SIGTSTP,
        signal.SIGTTOU,
        signal.SIGTTIN,
        signal.SIGCHLD,
        signal.SIGPIPE,
    ]

    for sig in signals_to_reset:
        try:
            signal.signal(sig, signal.SIG_DFL)
        except (OSError, ValueError):
            pass
```

**Usage**:
```python
# In child process:
self.shell.signal_manager.reset_child_signals()
```

**Benefits**:
- ✅ Single source of truth for child signal disposition
- ✅ Easy to modify set of handled signals
- ✅ Reduces code duplication

---

### H4. Unify Foreground Job Cleanup

**Problem**: Terminal restoration and state cleanup scattered across multiple code paths.

**Solution**: Create unified cleanup method.

**Implementation**:

```python
# In JobManager:

def restore_shell_foreground(self):
    """Restore shell to foreground and clean up state.

    This should be called after any foreground job completes
    to ensure terminal and bookkeeping are properly reset.
    """
    shell_pgid = os.getpgrp()

    # Clear foreground job tracking
    self.set_foreground_job(None)
    if hasattr(self.shell_state, 'foreground_pgid'):
        self.shell_state.foreground_pgid = None

    # Restore terminal control to shell
    if self.shell_state.supports_job_control:
        try:
            os.tcsetpgrp(self.shell_state.terminal_fd, shell_pgid)
            if self.shell_state.options.get('debug-exec'):
                print(f"DEBUG: Restored terminal to shell (pgid {shell_pgid})",
                      file=sys.stderr)
        except OSError as e:
            if self.shell_state.options.get('debug-exec'):
                print(f"DEBUG: Failed to restore terminal: {e}", file=sys.stderr)
```

**Usage**:
```python
# After foreground job completes:
exit_status = self.job_manager.wait_for_job(job)
self.job_manager.restore_shell_foreground()
return exit_status
```

**Benefits**:
- ✅ Consistent cleanup across all code paths
- ✅ No missed terminal restoration
- ✅ Single place to add new cleanup logic

---

### H5. Surface Terminal Control Failures

**Problem**: `tcsetpgrp` failures silently ignored, making debugging difficult.

**Solution**: Log failures when debugging enabled, track metrics.

**Implementation**:

```python
def transfer_terminal_control(self, pgid: int) -> bool:
    """Transfer terminal control to process group.

    Args:
        pgid: Process group ID

    Returns:
        True if successful, False otherwise
    """
    if not self.state.supports_job_control:
        if self.state.options.get('debug-exec'):
            print(f"DEBUG: Skipping terminal transfer (no TTY)", file=sys.stderr)
        return False

    try:
        os.tcsetpgrp(self.state.terminal_fd, pgid)

        if self.state.options.get('debug-exec'):
            print(f"DEBUG: Transferred terminal to pgid {pgid}", file=sys.stderr)

        if hasattr(self.state, 'process_metrics'):
            self.state.process_metrics.record_terminal_transfer_success()

        return True

    except OSError as e:
        # Log the failure
        if self.state.options.get('debug-exec'):
            print(f"WARNING: Failed to transfer terminal to pgid {pgid}: {e}",
                  file=sys.stderr)

        if hasattr(self.state, 'process_metrics'):
            self.state.process_metrics.record_terminal_transfer_failure()

        return False
```

**Benefits**:
- ✅ Visible failures when debugging
- ✅ Metrics on terminal control issues
- ✅ Easier to diagnose problems

---

## Medium Priority Recommendations

These improve observability and debugging.

### M1. Add Process Control Metrics

**Implementation**: See detailed `ProcessMetrics` class in previous recommendations.

**Key Metrics**:
- Fork count
- Wait count
- SIGCHLD signal count
- Process group sync times
- Terminal transfer success/failure rate

**Usage**:
```bash
$ psh -c "seq 1 100 | grep 50; builtin metrics"
```

---

### M2. Implement Signal Blocking During Wait

**Implementation**: See `block_signals()` context manager in previous recommendations.

**Usage in wait_for_job**:
```python
with block_signals(signal.SIGCHLD):
    pid, status = os.waitpid(-job.pgid, os.WUNTRACED)
    job.update_process_status(pid, status)
```

**Benefits**:
- ✅ Eliminates SIGCHLD/wait race
- ✅ Simpler fallback logic

---

### M3. Add Process Group Validation Diagnostics

**Implementation**: See `validate_process_group_state()` and diagnostic functions in previous recommendations.

**Features**:
- Validate shell is process group leader
- Check terminal control state
- Verify signal dispositions
- Diagnose specific jobs

**Usage**:
```bash
$ psh -c "builtin validate-pgid"
$ psh -c "sleep 10 & builtin jobdiag %1"
```

---

## Low Priority Recommendations

These are nice-to-have improvements.

### L1. Add Comprehensive Debug Logging

**Implementation**: Categorized debug logger (see `ProcessControlLogger` in previous recommendations).

**Categories**: FORK, SIGNAL, PGID, TERMINAL, WAIT, JOB

---

### L2. Create Signal Architecture Documentation

**Implementation**: Comprehensive signal handling documentation (see previous recommendations).

**Sections**:
- Signal dispositions by mode
- Handler call graphs
- Race condition mitigation
- Trap integration
- Debugging guide

---

## Implementation Roadmap

### Phase 1: Critical Fixes (Week 1-2)
- [ ] C1: Eliminate process group setup race (pipe-based sync)
- [ ] C2: Improve SIGCHLD handler safety (self-pipe trick)
- [ ] C3: Unify process creation logic (ProcessLauncher)

### Phase 2: High Priority Improvements (Week 3-4)
- [ ] H1: Add TTY detection
- [ ] H2: Signal disposition tracking
- [ ] H3: Centralize signal reset
- [ ] H4: Unify foreground cleanup
- [ ] H5: Surface terminal control failures

### Phase 3: Observability (Week 5-6)
- [ ] M1: Process control metrics
- [ ] M2: Signal blocking during wait
- [ ] M3: Process group validation

### Phase 4: Polish (Week 7+)
- [ ] L1: Debug logging system
- [ ] L2: Signal architecture documentation
- [ ] Code review and testing
- [ ] Documentation updates

### Implementation Notes

**Dependencies**:
- C1, C2, C3 are independent and can be done in parallel
- H1-H5 should be done after C3 (use unified launcher)
- M1-M3 can be done anytime (non-invasive)
- L1-L2 are ongoing

**Testing Between Phases**:
```bash
# Run full test suite
python -m pytest tests/ -v

# Run conformance tests
cd tests/conformance
python run_conformance_tests.py

# Manual job control testing
psh
psh$ sleep 10 &
psh$ jobs
psh$ fg %1
^Z
psh$ bg %1
```

---

## Testing Strategy

### Unit Tests

**New Test Files**:
- `tests/unit/executor/test_process_launcher.py`
- `tests/unit/utils/test_signal_utils.py`
- `tests/unit/utils/test_signal_registry.py`
- `tests/unit/utils/test_process_metrics.py`

### Integration Tests

**Test Scenarios**:
```python
def test_pipeline_process_group_sync(isolated_shell):
    """Test pipe-based process group synchronization."""
    result = isolated_shell.run_command("echo a | cat | cat | cat")
    assert result == 0

def test_sigchld_self_pipe(isolated_shell):
    """Test SIGCHLD notification via self-pipe."""
    result = isolated_shell.run_command("sleep 0.1 &")
    # Wait for background job
    time.sleep(0.2)
    # Check job was reaped
    jobs = isolated_shell.job_manager.get_jobs()
    assert len(jobs) == 0 or jobs[0].state == JobState.DONE

def test_process_launcher_external(isolated_shell):
    """Test unified launcher with external command."""
    result = isolated_shell.run_command("/bin/echo test")
    assert result == 0

def test_terminal_control_without_tty(isolated_shell):
    """Test graceful degradation without TTY."""
    isolated_shell.state.supports_job_control = False
    result = isolated_shell.run_command("echo test | cat")
    assert result == 0  # Should work without terminal control
```

### System Tests

**Under Load**:
```bash
# Stress test process group synchronization
$ stress-ng --cpu 8 --timeout 60s &
$ psh -c "seq 1 1000 | xargs -P 20 -I {} echo test {}" > /dev/null

# Long pipeline test
$ psh -c "seq 1 100 | $(for i in {1..20}; do echo -n 'cat | '; done)cat"

# Background job stress test
$ psh -c "for i in {1..50}; do sleep 0.1 & done; wait"
```

**Edge Cases**:
```bash
# No TTY
$ echo "echo hello" | psh

# Process group race (should never timeout)
$ for i in {1..1000}; do psh -c "echo test | cat" > /dev/null; done

# SIGCHLD race (check all jobs reaped)
$ psh -c "for i in {1..100}; do true & done; sleep 1; jobs"
```

---

## References

### Documentation
- Stevens, W. Richard. *Advanced Programming in the UNIX Environment*, 3rd ed.
  - Chapter 9: Process Relationships
  - Chapter 10: Signals
- POSIX.1-2017, Section 2.11: Signals and Error Handling
- Bash Reference Manual, Section 3.7.6: Signals

### Related PSH Documentation
- `docs/ARCHITECTURE.md` - Overall architecture
- `docs/process_control.md` - Process control overview
- `tests/conformance/` - POSIX compliance tests

### External Resources
- [Self-pipe trick](https://cr.yp.to/docs/selfpipe.html)
- [Async-signal-safe functions](https://man7.org/linux/man-pages/man7/signal-safety.7.html)
- [Job Control](https://www.gnu.org/software/libc/manual/html_node/Job-Control.html)

---

## Appendix: Implementation Status

| ID | Recommendation | Status | Assignee | Target Date |
|----|---------------|--------|----------|-------------|
| C1 | Process group sync | Not Started | - | - |
| C2 | SIGCHLD safety | Not Started | - | - |
| C3 | Unify process creation | Not Started | - | - |
| H1 | TTY detection | Not Started | - | - |
| H2 | Signal tracking | Not Started | - | - |
| H3 | Signal reset | Not Started | - | - |
| H4 | Foreground cleanup | Not Started | - | - |
| H5 | Terminal failures | Not Started | - | - |
| M1 | Metrics | Not Started | - | - |
| M2 | Signal blocking | Not Started | - | - |
| M3 | Diagnostics | Not Started | - | - |
| L1 | Debug logging | Not Started | - | - |
| L2 | Documentation | Not Started | - | - |

---

**Document Maintenance**: This document should be updated as recommendations are implemented. Mark completed items, add lessons learned, and update code references as the codebase evolves.
