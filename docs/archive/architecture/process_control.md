# Process Groups, Terminal Control, and Signal Handling in PSH

## Overview

PSH implements Unix job control through careful management of process groups, terminal control, and signal handling. This document explains how these mechanisms work together to provide proper interactive shell behavior.

## Process Groups

### What are Process Groups?

A process group is a collection of related processes that can be managed as a unit. In Unix shells:
- Each job (command or pipeline) runs in its own process group
- The process group ID (PGID) is typically the PID of the first process in the group
- Process groups enable job control operations like suspension, resumption, and termination

### PSH Process Group Management

#### Shell Process Group Setup

When PSH starts in interactive mode, it establishes itself as a process group leader:

```python
# In SignalManager.ensure_foreground()
shell_pid = os.getpid()
shell_pgid = os.getpgrp()

# Only set process group if we're not already the leader
if shell_pgid != shell_pid:
    os.setpgid(0, shell_pid)

# Make shell the foreground process group
os.tcsetpgrp(0, shell_pid)
```

#### Pipeline Process Groups

For pipeline execution, PSH creates a unified process group:

1. **First child becomes group leader:**
   ```python
   if i == 0:  # First command in pipeline
       os.setpgid(0, 0)  # Child sets its own process group
   ```

2. **Subsequent children join the group:**
   ```python
   # Parent sets child's process group
   os.setpgid(pid, pgid)  # pgid is first child's PID
   ```

3. **Race condition handling:**
   Both parent and child attempt to set the process group to handle timing issues.

#### External Command Process Groups

Single external commands create their own process group:

```python
# Child process
os.setpgid(0, 0)  # Create new process group

# Parent process  
os.setpgid(pid, pid)  # Ensure child is in its own group
```

## Terminal Control

### Terminal Foreground Process Group

Only the foreground process group can:
- Read from the terminal (stdin)
- Write to the terminal (stdout/stderr) without being stopped
- Receive keyboard signals (Ctrl-C, Ctrl-Z)

### PSH Terminal Control Flow

#### Interactive Mode Initialization
```python
# Shell takes terminal control
os.tcsetpgrp(0, shell_pid)
```

#### Foreground Job Execution

1. **Transfer control to job:**
   ```python
   # For pipelines - done immediately after forking
   if not is_background:
       os.tcsetpgrp(0, job.pgid)
   
   # For external commands - done before waiting
   os.tcsetpgrp(0, pid)
   ```

2. **Wait for job completion:**
   ```python
   exit_status = job_manager.wait_for_job(job)
   ```

3. **Restore control to shell:**
   ```python
   os.tcsetpgrp(0, shell_pgid)
   ```

#### Background Job Execution

Background jobs do NOT receive terminal control:
- They run in their own process group
- Terminal remains controlled by the shell
- Any terminal I/O attempts result in SIGTTOU/SIGTTIN

### Critical Timing Issue

The order of operations is crucial:

**Correct (PSH current implementation):**
1. Fork child processes
2. Set up process groups  
3. **Immediately** transfer terminal control
4. Wait for completion

**Incorrect (caused SIGTTOU):**
1. Fork child processes
2. Set up process groups
3. Wait for completion (transfer control in wait method)
4. ← Children try terminal I/O before control transfer

## Signal Handling

### Signal Types in Job Control

| Signal | Description | PSH Handling |
|--------|-------------|--------------|
| SIGINT | Interrupt (Ctrl-C) | Custom handler in shell, default in children |
| SIGTSTP | Stop (Ctrl-Z) | Ignored in shell, default in children |
| SIGTTOU | Background write to terminal | Ignored in shell and pipeline children |
| SIGTTIN | Background read from terminal | Ignored in shell, default in children |
| SIGCHLD | Child process state change | Custom handler for job tracking |
| SIGPIPE | Broken pipe | Default behavior in both modes for clean exits |

### Interactive Mode Signal Setup

```python
def _setup_interactive_mode_handlers(self):
    # Shell ignores job control signals
    signal.signal(signal.SIGTSTP, signal.SIG_IGN)
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    signal.signal(signal.SIGTTIN, signal.SIG_IGN)
    
    # Custom handlers for user signals
    signal.signal(signal.SIGINT, self._handle_signal_with_trap_check)
    signal.signal(signal.SIGCHLD, self._handle_sigchld)
    
    # Default SIGPIPE handling for clean broken pipe exits
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
```

### Script Mode Signal Setup

```python
def _setup_script_mode_handlers(self):
    # Script mode uses default behaviors for most signals
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTSTP, signal.SIG_DFL)
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    
    # Still ignore terminal control signals for robustness
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    signal.signal(signal.SIGTTIN, signal.SIG_IGN)
    
    # Default SIGPIPE handling for clean broken pipe exits
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
```

### Child Process Signal Setup

#### Pipeline Children
```python
# Reset most signals to default
signal.signal(signal.SIGINT, signal.SIG_DFL)
signal.signal(signal.SIGTSTP, signal.SIG_DFL)
signal.signal(signal.SIGTTIN, signal.SIG_DFL)

# Keep SIGTTOU ignored to prevent premature suspension
# This is key to preventing the race condition
# signal.signal(signal.SIGTTOU, signal.SIG_IGN)  # Set earlier
```

#### External Command Children
```python
# All signals reset to default
signal.signal(signal.SIGINT, signal.SIG_DFL)
signal.signal(signal.SIGTSTP, signal.SIG_DFL)
signal.signal(signal.SIGTTOU, signal.SIG_DFL)
signal.signal(signal.SIGTTIN, signal.SIG_DFL)
```

### SIGCHLD Handling

PSH uses SIGCHLD to track job state changes:

```python
def _handle_sigchld(self, signum, frame):
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
            
            job = self.job_manager.get_job_by_pid(pid)
            if job:
                job.update_process_status(pid, status)
                job.update_state()
                
                # Handle stopped foreground jobs
                if job.state == JobState.STOPPED and job.foreground:
                    os.tcsetpgrp(0, os.getpgrp())  # Return control to shell
        except OSError:
            break
```

## Job Control Integration

### Job States

```python
class JobState(Enum):
    RUNNING = "running"
    STOPPED = "stopped" 
    DONE = "done"
```

### Job Manager Responsibilities

1. **Job Creation:**
   ```python
   job = job_manager.create_job(pgid, command_string)
   job.add_process(pid, command_name)
   ```

2. **State Tracking:**
   ```python
   job.update_process_status(pid, status)
   job.update_state()
   ```

3. **Terminal Control:**
   ```python
   job_manager.set_foreground_job(job)
   ```

4. **Job Waiting:**
   ```python
   exit_status = job_manager.wait_for_job(job)
   ```

## Common Issues and Solutions

### Issue 1: Pipeline SIGTTOU (Recently Fixed)

**Problem:** Pipeline children were getting SIGTTOU when trying to write output.

**Root Cause:** Race condition between process group setup and terminal control transfer.

**Solution:**
1. Transfer terminal control immediately after forking all pipeline processes
2. Have pipeline children ignore SIGTTOU initially
3. Ensure first child sets its own process group before signal reset

### Issue 2: Background Jobs Affecting Terminal

**Problem:** Background jobs interfere with terminal I/O.

**Solution:** Background jobs never receive terminal control; shell retains it.

### Issue 3: Signal Handler Interference

**Problem:** Shell signal handlers affect child processes.

**Solution:** Children always reset signal handlers to default on fork.

### Issue 4: Broken Pipe Handling (Recently Fixed)

**Problem:** PSH would throw Python `BrokenPipeError` exceptions when output was piped to commands that exit early (like `less` or `head`), instead of handling SIGPIPE gracefully.

**Root Cause:** PSH wasn't setting up proper SIGPIPE signal handling, causing Python to raise exceptions instead of allowing the process to exit cleanly.

**Solution:** 
1. Set `signal.signal(signal.SIGPIPE, signal.SIG_DFL)` in both interactive and script modes
2. This allows PSH to handle broken pipes the same way bash does - with clean process termination
3. Enables proper pipeline behavior when PSH output is consumed by tools like `less`, `head`, or `grep`

**Example:** Before fix, `python3 script.py | less` would show Python traceback. After fix, it exits cleanly when `less` is quit.

## Script vs Interactive Mode Differences

### Script Mode
- Simpler signal handling (mostly defaults)
- No terminal control management
- No job control features
- Still ignores SIGTTOU/SIGTTIN for robustness

### Interactive Mode  
- Full signal handler setup
- Active terminal control management
- Complete job control implementation
- Process group leadership establishment

## Best Practices

1. **Always handle race conditions** in process group setup
2. **Transfer terminal control immediately** for foreground jobs
3. **Reset child signal handlers** to avoid inheriting shell behaviors
4. **Use SIGCHLD** for asynchronous job state tracking
5. **Ignore SIGTTOU/SIGTTIN** in shell and pipeline children
6. **Restore terminal control** when jobs complete or are suspended

## Implementation Files

- `psh/interactive/signal_manager.py` - Signal handler setup and management
- `psh/executor/pipeline.py` - Pipeline process group and terminal control
- `psh/executor/strategies.py` - External command process group setup
- `psh/job_control.py` - Job state management and waiting
- `psh/interactive/base.py` - Interactive mode initialization

This architecture ensures PSH provides robust, Unix-compliant job control while avoiding common pitfalls like race conditions and signal handling conflicts.