# Interactive Tests

These tests use `pexpect` to test PSH in an interactive terminal environment.

## Requirements

- Python 3.6+
- pexpect module (`pip install pexpect`)
- Unix-like system (Linux, macOS, BSD)

## Known Issues

### Timing Sensitivity
Interactive tests can be sensitive to system load and timing. If tests fail intermittently:
1. Check system load
2. Try increasing timeouts in `spawn_psh()` methods
3. Add small delays after sending commands

### Terminal Environment
The tests expect a standard terminal environment. If running in unusual environments (CI, containers, etc.), you may need to:
1. Set `TERM=xterm` or similar
2. Ensure proper locale settings (UTF-8)
3. Check that Python can detect TTY properly

## Debugging Failed Tests

If a test fails:

1. Run the specific test with verbose output:
   ```bash
   python -m pytest tests/system/interactive/test_name.py::TestClass::test_method -xvs
   ```

2. Check the debug output added to test_echo_simple for clues

3. Run the test outside pytest:
   ```bash
   python tmp/debug_test_name.py
   ```

## Test Categories

- **test_pty_smoke.py** - The canonical PTY suite (runs by default): prompt,
  execution, line editing, wrapped lines, vi mode, history, job control,
  plus behaviors ported from the deleted legacy suites (Ctrl-R search,
  Ctrl-L, tab completion, pipelines). The old blanket-skipped files
  (test_basic_interactive.py, test_line_editing.py, test_simple_commands.py,
  test_working_interactive.py, test_subprocess_commands.py) were removed
  once their "PTY doesn't work under pytest" skip reasons stopped being
  true; anything they uniquely covered lives in TestPtyPortedLegacy.
- **test_basic_spawn.py** - Low-level PSH spawning tests
- **test_interactive_features.py** - Opt-in extras (--run-interactive)
