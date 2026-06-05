# Subshell Integration Tests

This directory contains comprehensive integration tests for PSH subshell functionality.

## Running the Tests

As of **v0.195.0** these tests run under normal pytest capture — the `-s` flag
is **no longer required**:

```bash
# Run all subshell tests
python -m pytest tests/integration/subshells/

# Run a specific file or test
python -m pytest tests/integration/subshells/test_subshell_basics.py
python -m pytest tests/integration/subshells/test_subshell_basics.py::test_subshell_basic_execution
```

`run_tests.py` remains the recommended runner; it still passes `-s` for this
group, which is now harmless rather than necessary.

## Technical Details

### Why the `-s` flag used to be required

The historical explanation — "pytest replaces `sys.stdout`/`sys.stdin`, and
forked children inherit the capture objects instead of real file descriptors" —
was **mostly incorrect**. Forked children operate at the *file-descriptor*
level: after a redirection is applied with `os.dup2` on the real fd, the
builtins write stdout via `os.write(1)` and so file redirection works regardless
of pytest's `sys.stdout` replacement.

The single genuine failure was the `read` builtin. It decided between
`os.read(fd)` and `sys.stdin.readline()` by probing `sys.stdin.fileno()`; under
capture (pytest's `DontReadFromInput`) that probe failed and `read` fell back to
`sys.stdin` instead of the real, redirected fd 0 — so `( ... read ... ) < file`
read the wrong source (and tripped pytest's "reading from stdin while output is
captured" guard).

### The fix

`read` now prefers the real OS descriptor whenever it is valid (see
`ReadBuiltin._should_use_sys_stdin` in `psh/builtins/read_builtin.py`), falling
back to `sys.stdin` only for a genuine in-process `StringIO` replacement. With
that, the whole subshell suite passes under default capture.

Regression coverage lives in
`tests/integration/redirection/test_read_forked_fd.py` (deliberately run without
`-s`).

## Test Organization

- **test_subshell_basics.py**: Basic subshell functionality (execution, variables, I/O)
- **test_subshell_implementation.py**: Comprehensive implementation tests (isolation, inheritance, compatibility)
- **test_subshell_terminal_control.py**: Terminal control and job control integration
