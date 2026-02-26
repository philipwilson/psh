## Project Overview

Python Shell (psh) is an educational Unix shell implementation designed to teach shell internals through clean, readable Python code.
- Hand-written recursive descent parser for clarity
- Component-based architecture with clear separation of concerns
- Comprehensive test suite 
- Near-complete POSIX compliance (~93% measured by conformance tests)
- Visitor pattern for AST operations
- Comprehensive conformance testing framework for POSIX/bash compatibility

## Quick Start Commands

```bash
# Run tests (RECOMMENDED - uses smart test runner)
# IMPORTANT: Always redirect full test output to a file so you can inspect
# failures without re-running the entire suite:
python run_tests.py > tmp/test-results.txt 2>&1; tail -15 tmp/test-results.txt
# If failures are found, grep the saved file instead of re-running:
#   grep FAILED tmp/test-results.txt
#   grep -A 10 "FAILURES" tmp/test-results.txt

python run_tests.py --quick                # Fast tests only
python run_tests.py --parallel             # Parallel mode (~10x faster)
python run_tests.py --parallel 8           # Parallel with 8 workers
python run_tests.py --all-nocapture        # Simple mode - run all with -s

# Run tests manually (for specific scenarios)
python -m pytest tests/                    # Most tests (note: subshell tests will fail)
python -m pytest tests/integration/subshells/ -s  # Subshell tests (MUST use -s)
python -m pytest tests/test_foo.py -v     # Specific test file
python -m pytest tests/unit/builtins/ -v  # Specific test category
python -m pytest -k "test_name" -xvs      # Specific test with output

# Run conformance tests (POSIX/bash compatibility)
cd tests/conformance
python run_conformance_tests.py           # Full conformance suite
python run_conformance_tests.py --posix-only    # POSIX compliance only
python run_conformance_tests.py --bash-only     # Bash compatibility only
python run_conformance_tests.py --summary-only  # Just show summary

# Run specific test categories
python -m pytest tests/unit/              # Unit tests (builtins, expansion, lexer, parser)
python -m pytest tests/integration/       # Integration tests (pipelines, control flow)
python -m pytest tests/system/            # System tests (interactive, initialization)
python -m pytest tests/performance/       # Performance benchmarks

# Run psh
python -m psh                              # Interactive shell
python -m psh script.sh                    # Run script
python -m psh -c "echo hello"             # Run command

# Debug options
python -m psh --debug-ast                  # Show AST before execution
python -m psh --debug-tokens              # Show tokenization
python -m psh --debug-expansion           # Trace expansions
python -m psh --debug-exec                 # Debug executor (process groups, signals)
python -m psh --validate script.sh        # Validate without executing
```

## Test Organization

### Main Test Suite (`tests/`)
- **Location**: `/tests/`
- **Organization**:
  - `unit/` - Unit tests (builtins, expansion, lexer, parser)
  - `integration/` - Integration tests (pipelines, control flow, functions)
  - `system/` - System tests (interactive, initialization, scripts)
  - `conformance/` - POSIX/bash compatibility tests
- **Command**: `python -m pytest tests/`


**Interactive testing**

You can switch parsers inside a running psh session:

```bash
python -m psh --parser combinator         # Start with combinator
python -m psh --parser rd                 # Start with recursive descent (default)
```

**Lint**

Always lint combinator code after changes:

```bash
ruff check psh/parser/combinators/
```

## Critical Information

### To increment the system version after completing an enhancement:
1. Update `psh/version.py`: bump `__version__`; add a new entry to `CHANGELOG.md`
2. Update the version string in **all** of these files (they must always match):
   - `README.md` — the `**Current Version**:` line
   - `ARCHITECTURE.md` — the `**Current Version**:` line
   - `ARCHITECTURE.llm` — the `Version:` line

3. Commit changes in the git repo and tag the commit with the new version

### Architecture documentation files and what they contain

These files have version-stamped metadata that must stay in sync:

| File | Contains | Key metadata |
|------|----------|-------------|
| `psh/version.py` | Canonical version | `__version__` |
| `CHANGELOG.md` | Detailed version history | `## VERSION` entries |
| `README.md` | User-facing overview | Version, test count, LOC, file count, recent development |
| `ARCHITECTURE.md` | Detailed architecture guide | Version |
| `ARCHITECTURE.llm` | LLM-optimized architecture | Version |

### Known Test Issues

1. **Subshell Tests Require Special Handling** (IMPORTANT):
   - Tests in `tests/integration/subshells/` MUST be run with pytest's `-s` flag
   - Reason: Pytest's output capture interferes with file descriptor operations in forked child processes
   - When PSH forks for a subshell and redirects to a file, the child inherits pytest's capture objects instead of real file descriptors
   - **Solution**: Use the provided test runner (`python run_tests.py`) which handles this automatically
   - **Manual workaround**: `python -m pytest tests/integration/subshells/ -s`
   - Affected tests: ~43 subshell tests + some function/variable tests
   - Status: All functionality works correctly; this is purely a test infrastructure issue
   - Documentation: See `tests/integration/subshells/README.md` for detailed explanation

2. **Pytest Collection Best Practices**:
   - Don't name source files starting with `test_`
   - Don't name classes starting with `Test` unless they're actual test classes
 
## Architecture Quick Reference

### Subsystem Documentation

Each major subsystem has its own CLAUDE.md with detailed guidance:

| Subsystem | Location | Purpose |
|-----------|----------|---------|
| **Lexer** | `psh/lexer/CLAUDE.md` | Tokenization, recognizers, quote/expansion parsing |
| **Parser** | `psh/parser/CLAUDE.md` | Recursive descent parsing, AST construction |
| **Executor** | `psh/executor/CLAUDE.md` | Command execution, process management, control flow |
| **Expansion** | `psh/expansion/CLAUDE.md` | Variable, command, tilde, glob expansion |
| **Core/State** | `psh/core/CLAUDE.md` | Shell state, variables, scopes, options |
| **Builtins** | `psh/builtins/CLAUDE.md` | Built-in commands, registration, adding new builtins |
| **I/O Redirect** | `psh/io_redirect/CLAUDE.md` | Redirections, heredocs, process substitution |
| **Visitor** | `psh/visitor/CLAUDE.md` | AST visitor pattern, traversal, transformation |
| **Interactive** | `psh/interactive/CLAUDE.md` | REPL, job control, history, completion |

These provide focused documentation for working within each subsystem.

### Key Files
- `psh/shell.py` - Main orchestrator (~316 lines)
- `psh/parser/` - Recursive descent parser package
- `psh/lexer/` - Modular tokenizer package with recognizer architecture
- `psh/executor/` - Execution engine with visitor pattern
- `psh/core/state.py` - Central state management
- `psh/expansion/manager.py` - Orchestrates all expansions

### Component Managers
Each manager handles a specific aspect:
- `ExpansionManager` - Variable, command substitution, globs, etc.
- `IOManager` - Redirections, pipes, heredocs
- `JobManager` - Background jobs, job control
- `ProcessLauncher` - Unified process creation with proper job control (NEW in v0.103.0)
- `FunctionManager` - Shell function definitions
- `AliasManager` - Shell aliases

### Process Execution Architecture
PSH uses a unified process creation system for all forked processes:
- **ProcessLauncher** (`psh/executor/process_launcher.py`) - Single source of truth for all process creation
- **ProcessRole Enum**: SINGLE, PIPELINE_LEADER, PIPELINE_MEMBER
- **ProcessConfig**: Configuration for launch (role, pgid, foreground, sync pipes, I/O setup)
- **Benefits**: Eliminates code duplication, consistent signal handling, centralized job control
- **Used by**: Pipelines, external commands, builtins (background), subshells, brace groups

### Word AST (SimpleCommand Arguments)
The parser always builds **Word AST nodes** for command arguments. Each
`SimpleCommand.words` list contains `Word` objects with `LiteralPart` and
`ExpansionPart` nodes carrying per-part quote context (`quoted`, `quote_char`).

As of v0.120.0, `words` is the **sole** argument metadata representation.
The legacy `arg_types`/`quote_types` string lists have been removed.
Use Word helper properties for semantic queries:

| Property | Replaces | Purpose |
|----------|----------|---------|
| `word.is_quoted` | `arg_type == 'STRING'` | True if wholly quoted |
| `word.is_unquoted_literal` | `arg_type == 'WORD'` | Plain unquoted word |
| `word.is_variable_expansion` | `arg_type == 'VARIABLE'` | Single `$VAR` expansion |
| `word.has_expansion_parts` | checking for expansion types | Any expansion present |
| `word.has_unquoted_expansion` | unquoted + `$` in arg | Vulnerable to splitting |
| `word.effective_quote_char` | `quote_types[i]` | The quote char (`'`, `"`, `$'`, or None) |

### Execution Flow
```
Input → Line Continuation → Tokenization → Parsing → AST → Expansion → Execution
                                                                         ↓
                                                                   ProcessLauncher
                                                                   (fork + job control)
```

## Development Guidelines

### Testing

**Test Writing Guidelines**

Choose the right fixture based on test type:

1. **Unit Tests** (use `captured_shell`):
   - Testing builtin command output
   - Testing parser/lexer components  
   - Testing expansion logic
   - No file I/O or process spawning

2. **Integration Tests** (use `isolated_shell_with_temp_dir`):
   - Testing I/O redirection
   - Testing pipelines
   - Testing job control
   - Testing subshells
   - File system operations
   - **IMPORTANT**: Tests with subshells + file redirections MUST be run with `-s` flag
   - Use the test runner (`python run_tests.py`) to handle this automatically

3. **System Tests** (use `subprocess`):
   - Testing full shell behavior
   - Comparing with bash
   - Testing process lifecycle
   - Interactive features (when possible)

**Output Capture Rules**:
1. NEVER use capsys with shell tests that do I/O redirection
2. ALWAYS use captured_shell for builtin output testing
3. PREFER subprocess.run for external command testing
4. AVOID mixing capture methods in the same test

**Example Patterns**:

```python
# Unit test with captured_shell
def test_echo_output(captured_shell):
    result = captured_shell.run_command("echo hello")
    assert result == 0
    assert captured_shell.get_stdout() == "hello\n"
    assert captured_shell.get_stderr() == ""

# Integration test with isolated shell
def test_file_redirection(isolated_shell_with_temp_dir):
    shell = isolated_shell_with_temp_dir
    shell.run_command("echo test > file.txt")
    
    # Read file directly, not through shell output
    import os
    with open(os.path.join(shell.state.variables['PWD'], 'file.txt')) as f:
        assert f.read() == "test\n"

# Conformance test with subprocess
def test_posix_compliance():
    import subprocess
    cmd = "echo $((1 + 1))"
    
    psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd], 
                        capture_output=True, text=True)
    bash = subprocess.run(['bash', '-c', cmd], 
                         capture_output=True, text=True)
    
    assert psh.stdout == bash.stdout
```

**For conformance tests**:
- Add to `tests/conformance/posix/` or `tests/conformance/bash/`
- Inherit from `ConformanceTest` base class
- Use `assert_identical_behavior()` for exact PSH/bash matching
- Use `assert_documented_difference()` for known differences

**Best Practices**:
- Clear output between tests: `captured_shell.clear_output()`
- Check both stdout and stderr
- Always verify exit codes
- Use appropriate test markers (@pytest.mark.serial, @pytest.mark.isolated)

See `docs/test_pattern_guide.md` for examples and patterns.

### Error Handling
- Use `self.error()` in builtins for consistent error messages
- Return appropriate exit codes (0=success, 1=general error, 2=usage error)
- For control flow, use exceptions (LoopBreak, LoopContinue, FunctionReturn)

## Current Development Status

**Version**: 0.192.1 (see CHANGELOG.md for detailed history)

## Debugging Tips

1. **Import Errors**: Clear `__pycache__` directories if you see module import issues
2. **Test Failures**: Run failing tests individually to check for test pollution
3. **Parser Issues**: Use `--debug-ast` and `--debug-tokens` to see parsing details
4. **Expansion Issues**: Use `--debug-expansion` to trace variable/command expansion

## Important Notes

- Use `tmp/` subdirectory for temporary files, not system `/tmp`
- Educational focus means clarity over performance in implementation choices

## Development Principles
- If we assert that a feature of psh is POSIX or bash conformant in the user's guide (docs/user_guide/*) then we must have a test in conformance_tests which proves it.