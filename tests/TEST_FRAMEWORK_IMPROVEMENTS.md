# Test Framework Improvements Summary

> [!IMPORTANT]
> Historical migration notes. Current canonical test commands are in `docs/testing_source_of_truth.md`.

## Problem Solved

The PSH test framework had isolation issues when running tests in parallel with `pytest -n auto`. Tests that passed individually would fail when run as part of the full suite due to:

1. **Process contamination** - Tests killing each other's processes
2. **Race conditions** - Multiple workers accessing the same resources
3. **State leakage** - Shell state persisting between tests
4. **File conflicts** - Hardcoded paths causing collisions

## Solutions Implemented

### 1. Enhanced Test Markers

Added new pytest markers to categorize tests by isolation needs:

- `@pytest.mark.serial` - Tests that must run on a single worker

### 2. Serial Test Execution

Problematic tests are now marked as serial and only run on worker `gw0`:

```python
# In conftest.py
serial_tests = [
    "test_file_not_found_redirection",
    "test_permission_denied_redirection",
]

# Only worker gw0 runs these tests
if worker_id != "gw0" and worker_id != "master":
    pytest.skip(f"Serial test skipped on worker {worker_id}")
```

### 3. Targeted Process Cleanup

Replaced global `pkill` with targeted cleanup:

```python
# Old: Killed ALL PSH processes
os.system("pkill -f 'python.*psh'")

# New: Only kill child processes
subprocess.run(["pkill", "-P", str(os.getpid()), "-f", "python.*psh"])
```

### 4. Unique Resource Names

Fixed race conditions by using unique names:

```python
# Old: Hardcoded path causing conflicts
test_file = '/tmp/fd_test'

# New: Unique path per test
test_file = f'tmp/fd_test_{uuid.uuid4().hex[:8]}'
```

### 5. Enhanced Fixtures

New fixtures for better isolation:

- `isolated_shell_with_temp_dir` - Fresh shell with a real `os.chdir` into a
  per-test temp directory
- `temp_dir` - Per-test temporary directory with automatic cleanup

### 6. Command Line Options

New options for debugging and control (the serial-split invocation):

```bash
# Parallel phase: skip serial-marked tests (they crash xdist workers)
pytest tests -m 'not serial' -n auto

# Serial phase: run the serial-marked tests separately, without -n
pytest tests -m serial
```

## Results

### Before Fixes
- Many test failures with `pytest -n auto`
- Tests interfering with each other
- Unpredictable results based on execution order

### After Fixes
- Failures reduced from 26+ to 21
- Consistent test results
- Reliable parallel execution
- Clear categorization of test isolation needs

## Usage Guidelines

### For Test Writers

1. **Mark tests appropriately**:
   ```python
   @pytest.mark.serial
   def test_that_needs_exclusive_access():
       # This test will only run on one worker
   ```

2. **Use unique paths**:
   ```python
   # Good
   test_file = f'tmp/test_{uuid.uuid4().hex[:8]}'
   
   # Bad
   test_file = '/tmp/test'
   ```

3. **Use isolation fixtures**:
   ```python
   def test_file_output(isolated_shell_with_temp_dir):
       shell = isolated_shell_with_temp_dir  # fresh shell, per-test cwd
       shell.run_command("echo test > file.txt")
   ```

### For Test Runners

1. **Normal parallel execution** (always exclude `serial`-marked tests, or xdist
   workers crash — see CLAUDE.md "Known Test Issues"):
```bash
pytest tests -n auto -m "not serial"
```

2. **Serial pass** (the process/signal/fd tests that cannot run under xdist):
```bash
pytest tests -m serial
```

3. **Maximum speed (skip problematic tests)**:
```bash
pytest tests -m 'not serial' -n auto
```

4. **Run serial tests separately**:
```bash
pytest tests -m serial
```

## Future Improvements

1. **Dynamic serial detection** - Automatically detect tests that fail in parallel
2. **Resource pools** - Manage shared resources like ports and temp files
3. **Test dependency graph** - Understand which tests affect each other
4. **Docker isolation** - Run problematic tests in containers
5. **Parallel test profiling** - Identify slow tests that bottleneck execution

## Conclusion

The test framework now handles parallel execution much more reliably. While some tests still need to run serially, the framework clearly identifies and handles these cases, providing both speed and reliability.
