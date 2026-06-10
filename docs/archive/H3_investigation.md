# H3 Signal Reset Investigation

## Problem Statement

After fixing the critical signal ordering bug (commit a5440f8), attempting to re-apply H3 (Centralize Child Signal Reset Logic) causes the shell to hang again. This document investigates why.

## Timeline

1. **Initial State (commit 4b74dfe)**: Shell works but has latent signal ordering bug
2. **H3/H4/H5 Applied**: Shell starts hanging - bug becomes apparent
3. **All Reverted to 4b74dfe**: Shell works again
4. **Signal Ordering Fix Applied (a5440f8)**: Shell works ✅
5. **H3 Re-applied on top of Signal Fix**: Shell hangs again ❌

## The Signal Ordering Fix

**File**: `psh/interactive/base.py` (lines 59-65)

**Root Cause**: Shell tried to take terminal control via `tcsetpgrp()` before ignoring SIGTTOU/SIGTTIN, causing the kernel to suspend the process.

**Fix**: Reordered initialization:
```python
if not skip_signals:
    # Set up signal handlers FIRST to ignore SIGTTOU/SIGTTIN
    # This must happen before ensure_foreground() to avoid being stopped
    self.signal_manager.setup_signal_handlers()

    # Now safe to ensure shell is in its own process group for job control
    self.signal_manager.ensure_foreground()
```

## H3 Changes (commit 2389229)

### Summary
Centralized child process signal reset logic into `SignalManager.reset_child_signals()`.

### Key Changes:

1. **psh/interactive/signal_manager.py**:
   - Added `reset_child_signals()` method that resets SIGINT, SIGQUIT, SIGTSTP, SIGTTOU, SIGTTIN, SIGCHLD, SIGPIPE to SIG_DFL
   - This method is called in child processes after fork()

2. **psh/shell.py**:
   - Added `signal_manager` property that returns `self.interactive_manager.signal_manager`
   - Allows easy access to SignalManager from anywhere in the codebase

3. **psh/executor/process_launcher.py**:
   - Added optional `signal_manager` parameter to constructor
   - Updated `_child_setup()` to use `signal_manager.reset_child_signals()` if available
   - Renamed old method to `_reset_child_signals_fallback()`

4. **Updated ProcessLauncher Instantiation** (4 locations):
   - `psh/executor/pipeline.py`: `ProcessLauncher(..., shell.signal_manager)`
   - `psh/executor/subshell.py`: `ProcessLauncher(..., shell.signal_manager)`
   - `psh/executor/strategies.py` (2x): `ProcessLauncher(..., shell.signal_manager)`

## Why Does H3 Break the Shell?

### Investigation Areas

#### 1. Initialization Order
**Question**: Does accessing `shell.signal_manager` during initialization cause issues?

**Analysis**:
- Shell initialization order (shell.py lines 84-91):
  1. `expansion_manager = ExpansionManager(self)`
  2. `io_manager = IOManager(self)`
  3. `script_manager = ScriptManager(self)`
  4. `interactive_manager = InteractiveManager(self)` ← signal_manager created here
  5. RC file loaded (line 136)

- ProcessLauncher is created during ExecutorVisitor initialization:
  - ExecutorVisitor creates SubshellExecutor (executor/core.py:97)
  - SubshellExecutor.__init__ creates ProcessLauncher (executor/subshell.py:40)
  - This happens LAZILY when executing commands, not during Shell.__init__

- **Hypothesis 1**: ProcessLauncher creation happens after interactive_manager exists, so `shell.signal_manager` should work fine.

#### 2. Property Access Side Effects
**Question**: Does the `shell.signal_manager` property have unintended side effects?

**Property Code**:
```python
@property
def signal_manager(self):
    """Access signal manager through interactive manager."""
    if hasattr(self, 'interactive_manager') and self.interactive_manager:
        return self.interactive_manager.signal_manager
    return None
```

**Analysis**:
- Property is read-only (no setter)
- Simply returns existing object or None
- No observable side effects from reading the property

- **Hypothesis 2**: Property itself doesn't cause issues.

#### 3. Signal Handler Conflicts
**Question**: Could reset_child_signals() be called in the parent process somehow?

**Analysis**:
- `reset_child_signals()` is only called in `ProcessLauncher._child_setup()`
- `_child_setup()` is only called AFTER fork() in the child process
- Child process calling reset_child_signals() shouldn't affect parent

- **Hypothesis 3**: reset_child_signals() shouldn't affect parent shell.

#### 4. Timing Issue with Signal Setup
**Question**: Could accessing signal_manager trigger signal setup at the wrong time?

**Analysis**:
- Accessing the property just returns the existing SignalManager object
- Doesn't call any methods or trigger initialization
- Signal handlers are set up in InteractiveManager.__init__ before ensure_foreground()

- **Hypothesis 4**: Property access shouldn't trigger signal setup.

#### 5. RC File Loading
**Question**: Could the RC file load trigger H3 code in a way that breaks signals?

**Analysis**:
- RC file is loaded at line 136 of Shell.__init__
- This is AFTER interactive_manager is created and signal handlers are set up
- If RC file executes commands with subshells/pipelines, it would create ExecutorVisitor
- ExecutorVisitor would create ProcessLauncher with shell.signal_manager
- But signals should already be set up correctly by this point

- **Hypothesis 5**: RC file timing might be involved, but unclear how.

#### 6. Pytest-Specific Interactions
**Question**: Could the issue only manifest in certain environments?

**Analysis**:
- User ran `python -m psh` in an interactive terminal
- Issue reproduced outside pytest environment
- Not specific to test infrastructure

- **Hypothesis 6**: Issue is real, not test-specific.

## Debugging Strategy

To understand why H3 breaks the shell, we need to:

1. **Add Debug Logging**: Insert print statements at key points:
   - Shell.__init__ start/end
   - InteractiveManager.__init__ start/end
   - signal_manager property access
   - ensure_foreground() entry/exit
   - setup_signal_handlers() entry/exit
   - ProcessLauncher.__init__ when signal_manager is passed
   - SubshellExecutor.__init__ when ProcessLauncher is created

2. **Test Minimal H3**: Apply H3 changes incrementally:
   - First: Just add the property to Shell
   - Second: Add reset_child_signals() to SignalManager (don't use it yet)
   - Third: Update ProcessLauncher to accept signal_manager (don't pass it yet)
   - Fourth: Update one ProcessLauncher instantiation site
   - Fifth: Update remaining sites

3. **Check Signal State**: Use `signals` builtin to check signal disposition:
   - Before and after signal ordering fix
   - After applying H3
   - When shell hangs

4. **Strace Analysis**: Run with strace to see system calls:
   ```bash
   strace -o /tmp/psh.strace python -m psh
   ```
   Look for:
   - tcsetpgrp() calls
   - Signal-related system calls
   - Where process gets stopped (SIGTTOU/SIGTTIN)

## Next Steps

1. **Immediate**: Apply debug logging to H3 changes
2. **Test**: Re-apply H3 with logging and capture output
3. **Analyze**: Determine exact point of failure
4. **Fix**: Modify H3 approach based on findings
5. **Verify**: Ensure fix works and doesn't break signal ordering

## Open Questions

1. Why does the property access break signal ordering?
2. Is there a circular dependency or initialization race?
3. Could the issue be in how InteractiveManager creates SignalManager?
4. Does the RC file play a role in triggering the bug?
5. Is there a missing initialization guard somewhere?

## Recommendations

- Consider alternative approaches to H3 that don't use the property pattern
- Maybe pass signal_manager explicitly during Shell.__init__() instead of via property
- Or create signal_manager earlier in the initialization sequence
- Or defer ProcessLauncher creation until it's actually needed (lazy initialization)
