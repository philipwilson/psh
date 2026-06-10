# Test Improvement Plan (v0.106.0)

*Last updated: 2025-11-25*

## Current State

| Category | Count | Notes |
|----------|-------|-------|
| Passed | 2,616 | Main tests (excluding subshells, interactive) |
| Skipped | 80 | Various reasons |
| XFailed | 52 | Expected failures |
| XPassed | 1 | Stale xfail marker |
| **Total** | **2,889** | Collected tests |

Subshell tests (run separately with `-s`): 43 passed, 1 skipped, 5 xfailed, 1 xpassed

## Categories of Skipped/XFailed Tests

### Category 1: PTY/Interactive Tests (~25 tests)
**Priority: Low** (functionality works, testing is hard)

| Files | Issue |
|-------|-------|
| `tests/system/interactive/test_line_editing.py` | ANSI escape sequences don't work in PTY |
| `tests/system/interactive/test_pty_job_control.py` | Job control not fully working in PTY mode |
| `tests/system/interactive/test_pty_line_editing.py` | Arrow keys, backspace, history issues |
| `tests/system/interactive/test_basic_interactive.py` | Line editing support |

**Root Cause:** PSH's line editor uses a custom implementation that doesn't properly handle ANSI escape sequences when running under pexpect/PTY. The functionality works correctly in actual interactive use.

**Recommended Action:**
1. **Accept as test infrastructure limitation** - functionality works in real use
2. **Alternative:** Create mock-based unit tests for LineEditor internals
3. **Long-term:** Implement test mode in PSH that bypasses raw terminal requirements

---

### Category 2: Pytest I/O Capture Conflicts (~15 tests)
**Priority: Medium** (test infrastructure issue, not bugs)

| Files | Issue |
|-------|-------|
| `tests/integration/subshells/test_subshell_implementation.py` | File descriptor conflicts in forked processes |
| `tests/integration/control_flow/test_c_style_for_loops.py` | pytest I/O capture interferes with redirection |
| `tests/integration/control_flow/test_while_loops.py` | `read` builtin conflicts with capture |
| `tests/integration/control_flow/test_nested_structures_io_conservative.py` | Complex redirection issues |

**Root Cause:** When pytest captures output, the child processes inherit pytest's capture file descriptors instead of real ones. When the shell redirects to a file, the child writes to pytest's buffer, not the file.

**Recommended Action:**
1. **Use `python run_tests.py`** - already handles this with `-s` flag for subshell tests
2. **Mark tests appropriately** - tests requiring real FDs should use subprocess isolation
3. **Document the pattern** - explain why `-s` is needed for certain tests

---

### Category 3: Unimplemented Features (~20 tests)
**Priority: High** (real functionality gaps)

| Feature | Files | Effort |
|---------|-------|--------|
| **Negated character classes `[!...]`** | `tests/unit/expansion/test_glob_expansion.py` | Medium |
| **Extended globbing (`shopt`)** | `tests/conformance/bash/test_bash_compatibility.py` | High |
| **History expansion (`!!`, `!$`)** | `tests/integration/interactive/test_history.py` | Medium |
| **Tab completion** | `tests/integration/interactive/test_completion.py` | Medium |
| **`errexit` option enforcement** | `tests/integration/command_resolution/test_command_resolution.py` | Medium |

**Recommended Actions:**

#### 3.1 Negated Character Classes (Glob)
```bash
# Currently fails:
ls [!abc]*   # Should match files NOT starting with a, b, or c
```
- **Location:** `psh/expansion/glob.py`
- **Effort:** ~2 hours
- **Impact:** POSIX compliance

#### 3.2 History Expansion
```bash
# Currently not implemented:
!!       # Repeat last command
!$       # Last argument of previous command
!-2      # Second-to-last command
```
- **Location:** `psh/interactive/history.py`
- **Effort:** ~1 day
- **Impact:** User experience

#### 3.3 `errexit` Option (`set -e`)
```bash
# Currently not enforced:
set -e
false    # Should exit immediately
echo "not reached"
```
- **Location:** `psh/executor/` (execution engine)
- **Effort:** ~4 hours
- **Impact:** Script compatibility

---

### Category 4: Known Behavior Differences (~10 tests)
**Priority: Low** (intentional or documented differences)

| Difference | Files | Notes |
|------------|-------|-------|
| Brace expansion edge cases | `tests/unit/expansion/test_brace_expansion.py` | PSH handles special chars differently |
| Command-prefixed env vars | `tests/integration/variables/test_variable_assignment.py` | `FOO=bar cmd` scoping |
| Alias expansion in non-interactive | `tests/unit/builtins/test_alias_builtins.py` | Bash-specific behavior |

**Recommended Action:**
1. **Document as intentional differences** where PSH behavior is reasonable
2. **Fix actual bugs** where behavior is clearly wrong
3. **Add to conformance documentation** for transparency

---

### Category 5: Stale XFail Markers (~3 tests)
**Priority: High** (easy cleanup)

These tests pass but still have `@pytest.mark.xfail`:

| Test | Current Status |
|------|----------------|
| `test_subshell_basics.py::test_nested_subshell_parsing` | xpassed |

**Recommended Action:**
1. Run tests to identify all xpassed tests
2. Remove stale xfail markers
3. Verify tests pass reliably

---

## Prioritized Action Items

### Phase 1: Quick Wins (1-2 hours)

1. **Clean up stale xfail markers**
   ```bash
   python -m pytest tests/ -v --tb=no 2>&1 | grep XPASS
   ```
   - Remove xfail from tests that now pass
   - Commit cleanup

2. **Verify test infrastructure**
   - Ensure `python run_tests.py` handles all edge cases
   - Update CLAUDE.md if needed

### Phase 2: Feature Implementation (1-2 days)

1. **Implement negated character classes in globs**
   - File: `psh/expansion/glob.py`
   - Add `[!...]` and `[^...]` support
   - Enable 3 tests in `test_glob_expansion.py`

2. **Fix `errexit` option enforcement**
   - File: `psh/executor/`
   - Check `set -e` flag after each command
   - Enable 2 tests

3. **Implement command-prefixed environment variables**
   - Pattern: `FOO=bar command`
   - Variable should only be set for that command
   - Enable 2 tests

### Phase 3: Medium-Term Improvements (1 week)

1. **History expansion** (`!!`, `!$`, `!-n`)
   - Add expansion in input processing
   - Enable 10 tests in `test_history.py`

2. **Tab completion framework**
   - Basic file/command completion
   - Enable 2 tests in `test_completion.py`

3. **Improve test isolation**
   - Create better subprocess test fixtures
   - Document when to use which approach

### Phase 4: Long-Term Considerations

1. **Extended globbing (`shopt -s extglob`)**
   - Requires parser changes for patterns like `@(foo|bar)`
   - May not be worth the complexity for educational shell

2. **Interactive test framework**
   - Consider separate test runner for PTY tests
   - Mock-based testing for LineEditor internals

---

## Files to Modify

### To Enable Tests (by removing xfail/skip)

| File | Tests | Prerequisite |
|------|-------|--------------|
| `tests/unit/expansion/test_glob_expansion.py` | 3 | Implement `[!...]` |
| `tests/integration/command_resolution/test_command_resolution.py` | 1 | Fix `errexit` |
| `tests/integration/variables/test_variable_assignment.py` | 2 | Command-prefixed vars |
| `tests/integration/interactive/test_history.py` | 10 | History expansion |
| `tests/integration/subshells/test_subshell_basics.py` | 1 | Remove stale xfail |

### To Document as Intentional

| File | Tests | Reason |
|------|-------|--------|
| `tests/unit/expansion/test_brace_expansion.py` | 6 | Different edge case handling |
| `tests/conformance/bash/test_bash_compatibility.py` | 4 | Bash-only features |

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Skipped tests | 80 | <30 |
| XFailed tests | 52 | <25 |
| XPassed tests | 1-2 | 0 |
| Skip rate | 2.8% | <1% |

---

## Testing Commands

```bash
# Run full test suite with proper handling
python run_tests.py

# Find xpassed tests (stale markers)
python -m pytest tests/ --ignore=tests/system/interactive -v --tb=no 2>&1 | grep XPASS

# Run specific categories
python -m pytest tests/unit/expansion/test_glob_expansion.py -v
python -m pytest tests/integration/interactive/test_history.py -v

# Run subshell tests (requires -s flag)
python -m pytest tests/integration/subshells/ -s -v
```

---

## Related Documentation

- `CLAUDE.md` - Main development guide
- `tests/integration/subshells/README.md` - Subshell test infrastructure
- `tests/system/interactive/README.md` - Interactive test issues
- `docs/posix/posix_compliance_summary.md` - POSIX compliance status
