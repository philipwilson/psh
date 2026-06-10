# PSH Architecture Roadmap

This document outlines planned architectural improvements and enhancements for PSH (Python Shell). These items represent longer-term improvements that would enhance PSH's compatibility, performance, and educational value.

## Progress Summary

**Completed Features**:
- ✅ **Alias Expansion Precedence Fix** (v0.83.0) - Fixed critical POSIX compliance issue

**High Priority Remaining**:
- Variable expansion in redirect targets (8 failing tests)
- Command groups in pipelines (common pattern)

**Total Progress**: 1/13 major architectural improvements completed

## Tokenizer/Lexer Improvements

### 1. Treat Unexpanded Braces as Single Word Tokens

**Current Behavior**: PSH tokenizes `{` and `}` as separate LBRACE and RBRACE tokens, even when they don't form a valid brace expansion. This causes `echo {}` to output `{ }` instead of `{}`.

**Proposed Change**: Modify the tokenizer to keep braces as part of WORD tokens when they don't form valid expansions.

**Rationale**:
- **Bash Compatibility**: Bash treats invalid brace patterns as literal text. Many scripts depend on this behavior.
- **Script Portability**: Scripts that work with literal braces (e.g., JSON generation, code templates) currently break in PSH.
- **User Expectations**: The principle of least surprise - users expect `echo {}` to output `{}`.
- **Consistency**: If braces don't expand, they should be treated like any other literal characters.

**Implementation Notes**:
- The tokenizer would need to look ahead to determine if `{...}` forms a valid brace expansion
- Valid patterns include: `{a,b,c}`, `{1..10}`, `{a..z}`, nested expansions
- Invalid patterns like `{}`, `{a}`, `{a..1}` should remain as literal text
- Function definitions `name() {}` would still need special handling

**Impact**: Low risk, well-contained change in the lexer layer. Would fix 4-6 failing brace expansion tests.

---

## Alias System Improvements

### 2. ✅ Fix Alias Expansion Precedence (COMPLETED v0.83.0)

**Status**: **COMPLETED** in version 0.83.0

**What Was Implemented**:
- Moved alias expansion from tokenization-time to execution-time via new `AliasExecutionStrategy`
- Created modular execution strategy architecture with proper bypass mechanisms
- Implemented correct command resolution order: Functions → Builtins → Aliases → External Commands
- Added backslash escape (`\command`) and `command` builtin bypass functionality
- Enhanced `AliasManager` with `has_alias()` method and recursion prevention
- Fixed command builtin process management by delegating to `ExternalExecutionStrategy`

**Architectural Changes Made**:
1. **Strategy Pattern**: Introduced execution strategies in order: `FunctionExecutionStrategy`, `BuiltinExecutionStrategy`, `AliasExecutionStrategy`, `ExternalExecutionStrategy`
2. **Delayed Expansion**: Aliases now expand during command execution, not tokenization
3. **Bypass Mechanisms**: Both `\command` and `command builtin` properly skip alias expansion
4. **Recursion Prevention**: Aliases can't infinitely expand themselves

**Results**:
- ✅ All 10 originally failing tests resolved
- ✅ Zero regressions: all existing functionality enhanced
- ✅ Major POSIX milestone: alias system now fully compliant with shell standards
- ✅ Educational value preserved while achieving production-quality precedence handling

**Files Modified**:
- `psh/executor/command.py` - Updated command resolution logic
- `psh/executor/strategies.py` - Added `AliasExecutionStrategy`
- `psh/aliases.py` - Enhanced with `has_alias()` method
- `psh/builtins/command_builtin.py` - Fixed process management
- `psh/shell.py` - Removed early alias expansion
- `psh/scripting/source_processor.py` - Removed early alias expansion

---

## I/O Redirection Improvements

### 3. Variable Expansion in Redirect Targets

**Current Behavior**: Redirect targets like `> "file_${i}.txt"` are not expanded. PSH creates files with literal names like `file_${i}.txt` instead of `file_1.txt`.

**Proposed Change**: Add variable expansion for all redirect targets before file operations.

**Rationale**:
- **Common Pattern**: Loop-generated output files are extremely common
- **POSIX Compliance**: Standard shells expand variables in redirect targets
- **Script Breakage**: Many scripts rely on this feature for dynamic file naming
- **User Expectations**: Natural to expect `> "log_${date}.txt"` to work

**Implementation Notes**:
- Expand after quote removal but before file creation
- Respect quoting: `> "$file"` expands variables but not globs
- Handle all redirect types: `>`, `>>`, `<`, etc.
- Update both file_redirect.py and io_manager.py

**Impact**: High priority - fixes 8 failing tests. Common use case that currently forces workarounds.

---

## Parser Enhancements

### 4. Support Command Groups in Pipelines

**Current State**: PSH cannot parse `{ cmd1; cmd2; } | cmd3` - brace groups aren't recognized as pipeline components.

**Proposed Change**: Extend parser to recognize brace groups as valid pipeline components.

**Rationale**:
- Common shell pattern for grouping commands without creating a subshell
- More efficient than `(cmd1; cmd2) | cmd3` which forks a new process
- Required for full POSIX compliance

---

## Expansion System Improvements

### 5. Implement Remaining Parameter Expansions

**Missing Features**:
- `${!var}` - Indirect expansion
- `${var@Q}` - Quote for reuse as input
- `${var@E}` - Expand escape sequences
- `${var@P}` - Expand as prompt string
- `${var@A}` - Assignment form
- `${var@a}` - Attributes

**Rationale**: Complete bash compatibility for parameter expansion.

---

## Process Management

### 6. Implement Coprocess Support

**Feature**: Support for `coproc` to create bidirectional pipes with background processes.

**Rationale**:
- Powerful feature for interactive process communication
- Educational value in demonstrating advanced IPC
- Bash compatibility for complex scripts

---

## Performance Optimizations

### 7. Implement Builtin Command Caching

**Current State**: Builtin lookup happens on every command execution.

**Proposed Change**: Cache builtin lookups after first resolution.

**Rationale**:
- Improve performance for script execution
- Reduce overhead in tight loops
- Still maintain ability to override with functions

---

## Error Handling

### 8. Enhanced Error Recovery in Parser

**Current State**: Parser stops on first error.

**Proposed Change**: Implement error recovery to continue parsing after errors.

**Rationale**:
- Better error messages showing multiple issues
- Useful for shell script linting
- Educational value in showing all problems at once

---

## Signal Handling

### 9. Complete Signal Handling (SIGWINCH, SIGPIPE)

**Missing Signals**:
- SIGWINCH - Terminal resize handling
- SIGPIPE - Broken pipe handling improvements
- Signal handling in arithmetic expressions

**Rationale**: Professional terminal behavior and robustness.

---

## Compatibility Features

### 10. Implement Extended Glob Patterns

**Features**: Support for `@()`, `*()`, `+()`, `?()`, `!()` patterns when `shopt -s extglob` is set.

**Rationale**:
- Common in modern bash scripts
- Powerful pattern matching capabilities
- Good educational example of parser extensions

---

## Architecture Refactoring

### 11. Plugin System for Builtins

**Concept**: Allow dynamic loading of builtin commands as plugins.

**Rationale**:
- Extensibility without modifying core
- Educational value in showing plugin architectures
- Easy way to add domain-specific builtins

---

## Testing Infrastructure

### 12. Improved Test Output Capture

**Current Issues**: Tests using forked processes have trouble capturing output.

**Proposed Solution**: Implement proper PTY-based testing infrastructure.

**Rationale**:
- Enable testing of interactive features
- Better subprocess output capture
- More reliable test suite

---

## Documentation

### 13. Interactive Tutorial Mode

**Concept**: Built-in interactive tutorial teaching shell concepts.

**Features**:
- Step-by-step lessons
- Practice exercises
- Progress tracking

**Rationale**: Enhance PSH's educational mission.

---

## Priority Guidelines

When considering implementation order:

1. **High Priority**: Changes that fix compatibility issues or enable common use cases
   - Variable expansion in redirect targets (very common pattern, 8 failing tests)
   - ✅ ~~Alias expansion precedence (affects core shell behavior)~~ **COMPLETED v0.83.0**
   - Command groups in pipelines (common pattern)
   
2. **Medium Priority**: Performance improvements and new features
   - Unexpanded braces tokenization (edge cases but improves compatibility)
   - Remaining parameter expansions
   - Builtin command caching
   
3. **Low Priority**: Nice-to-have features that few scripts use
   - Extended glob patterns
   - Plugin system
   - Interactive tutorial mode

---

## Contributing

When adding items to this roadmap:
1. Clearly describe current behavior and proposed change
2. Provide strong rationale (compatibility, performance, education)
3. Assess implementation complexity and impact
4. Consider backward compatibility
5. Link to relevant bug reports or feature requests