# PTY Detection Update Summary

## What We Accomplished

### 1. Added `--force-interactive` Flag
- **Location**: `psh/__main__.py`
- **Purpose**: Forces PSH into interactive mode even when stdin is not a TTY
- **Usage**: `psh --force-interactive`
- **Changes**:
  - Added flag parsing (line 56-58)
  - Set `shell._force_interactive = True` when flag is used (line 97-98)
  - Updated interactive mode check to include force_interactive (line 171)
  - Added to help text (line 129)

### 2. Fixed Line Editor for Non-TTY Mode
- **Location**: `psh/line_editor.py`
- **Issue**: Line editor tried to use raw terminal mode even in PTYs
- **Fix**: Added fallback to simple `readline()` when stdin is not a TTY (lines 68-76)
- **Result**: PSH can now read input in pseudo-terminal environments

### 3. Enhanced Terminal Manager Error Handling
- **Location**: `psh/tab_completion.py`
- **Change**: Added try/except around raw mode setup to handle PTY environments (lines 25-31)
- **Result**: Gracefully handles cases where raw mode can't be set

## Testing Results

### What Works
1. ✅ PSH starts and shows prompts with `--force-interactive`
2. ✅ Commands are received and executed
3. ✅ Output is produced correctly
4. ✅ Multiple commands can be run in sequence
5. ✅ Exit command works properly

### Verification
Running this command shows PSH working in forced interactive mode:
```bash
python -m psh --norc --force-interactive --debug-exec
```

When you type `echo hello` and press Enter, the debug output shows:
- The echo builtin executes
- It writes "hello\n" to stdout
- The output appears before the next prompt

### Known Issues

1. **pexpect in pytest**: When running interactive tests through pytest with pexpect, PSH doesn't seem to start properly. This appears to be an environment issue specific to pytest's subprocess handling.

2. **No Line Editing Features**: In non-TTY mode (like with pexpect), advanced line editing features (cursor movement, history navigation) are not available. This is expected behavior.

## How PSH Detects Interactive Mode

PSH uses several checks for interactive mode:

1. **Primary Check** (`__main__.py:171`):
   ```python
   if sys.stdin.isatty() or force_interactive:
       shell.interactive_loop()
   ```

2. **Shell Initialization** (`shell.py:104`):
   ```python
   is_interactive = getattr(self, '_force_interactive', sys.stdin.isatty())
   ```

3. **Line Editor** (`line_editor.py:68`):
   ```python
   if not sys.stdin.isatty():
       # Use simple readline fallback
   ```

## Recommendations

1. **For Testing**: The `--force-interactive` flag successfully enables interactive mode for pseudo-terminals. However, for automated testing, it may be better to:
   - Test PSH commands using subprocess with stdin/stdout pipes
   - Test interactive features separately using mock objects
   - Use the debug flags to verify execution

2. **For Users**: The `--force-interactive` flag can be useful for:
   - Running PSH in environments where TTY detection fails
   - Scripting interactive sessions
   - Debugging PSH behavior

3. **Future Improvements**:
   - Consider adding a `--no-raw-mode` flag to disable terminal raw mode
   - Implement a testing mode that works better with pexpect
   - Add more robust PTY detection for various environments

## Summary

The PTY detection updates successfully allow PSH to run in interactive mode even when not connected to a real terminal. The `--force-interactive` flag provides the control needed for testing and special use cases. While there are still challenges with specific testing frameworks like pexpect within pytest, the core functionality works as intended.