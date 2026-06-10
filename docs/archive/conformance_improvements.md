# PSH Conformance Improvement Recommendations

*Generated: 2025-08-07*  
*Current Status: 96.9% POSIX compliance, 87.0% bash compatibility*

## Executive Summary

This document outlines priority improvements needed to enhance PSH's POSIX compliance and bash compatibility based on conformance test analysis. The focus is on fixing critical bugs rather than implementing missing features, as most failures are due to implementation errors in existing functionality.

**Note**: After testing, several initially identified issues were found to be working correctly:
- `$$` (process ID) works - returns different PIDs between PSH and bash (expected behavior)  
- `[[ ]]` test expressions work properly for file tests and comparisons
- Environment variable export works correctly with `export VAR=value`
- Escaped command substitution `\$(...)` correctly produces syntax error (same as bash)

## Current Conformance Metrics

- **POSIX Compliance**: 96.9% (125/129 tests passing)
- **Bash Compatibility**: 87.0% (documented differences for bash-specific features)
- **Test Suite Coverage**: 3000+ tests in modern structure, 500+ conformance tests

## Priority Fixes for PSH Conformance

### 🔴 Critical Issues (Fix First)

These are bugs in core POSIX functionality that break real-world scripts:

#### 1. Parameter Expansion Error Codes
- **Issue**: `${x:?undefined}` returns exit code 1 instead of 127
- **Location**: `psh/expansion/parameter.py`
- **POSIX Requirement**: Parameter expansion errors should return exit code 127
- **Impact**: Scripts checking specific error codes fail
- **Fix**: Update error handling to return correct POSIX-specified exit codes

### 🟡 Important Issues

These affect specific functionality:

#### 2. Array Quote Handling
- **Issue**: Single quotes in arrays not preserved correctly
- **Example**: `arr=('word with \'quotes')` loses quote escaping
- **Location**: `psh/executor/array.py`
- **Impact**: Arrays with quotes lose proper quoting
- **Fix**: Preserve quote escaping in array element processing

### 🟢 Enhancements for Better Compatibility

These would improve bash compatibility but aren't POSIX requirements:

#### 3. Job Control Display Format
- **Issue**: `jobs` output format differs from bash
- **PSH**: `[1]   Running      sleep 1`
- **Bash**: `[1]+  Running                 sleep 1 &`
- **Location**: `psh/job_manager.py`
- **Impact**: Minor - cosmetic difference

#### 4. Implement `shopt` Builtin
- **Purpose**: Bash option compatibility
- **Location**: New file `psh/builtins/shopt.py`
- **Impact**: Better bash script compatibility

#### 5. Add Special Variables
- **Variables**: `RANDOM`, `LINENO`, `BASH_VERSION`
- **Location**: `psh/core/state.py` and `psh/expansion/parameter.py`
- **Impact**: Script compatibility for bash-specific features

## Implementation Strategy

### Phase 1: Critical Bug Fix (Target: 98% POSIX compliance)
1. Fix parameter expansion exit codes (1 day)

### Phase 2: Important Fixes (Target: 99% POSIX compliance)
2. Fix array quote handling (2 days)

### Phase 3: Bash Compatibility (Target: 90% bash compatibility)
3. Update job control format (1 day)
4. Implement `shopt` builtin (3 days)
5. Add special variables (2 days)

## Testing Strategy

1. **Unit Tests**: Add specific tests for each fix in `tests/unit/`
2. **Conformance Tests**: Verify fixes against existing failing conformance tests
3. **Regression Tests**: Ensure no existing functionality breaks
4. **Bash Comparison**: Compare output with bash for identical commands

## Success Metrics

- **Short Term Goal**: Achieve 98% POSIX compliance by fixing critical issues
- **Medium Term Goal**: Achieve 99% POSIX compliance with parser fixes
- **Long Term Goal**: Achieve 90% bash compatibility with enhancements

## Notes

- Current test suite is well-organized with 3000+ tests
- Conformance framework provides excellent bash comparison capability
- Most failures are bugs in existing features rather than missing functionality
- Focus on fixing bugs before adding new features

## File References

Key files for implementing fixes:
- `psh/expansion/parameter.py` - Special variables and parameter expansion
- `psh/builtins/test.py` - Test builtin for `[[ ]]` expressions
- `psh/builtins/environment.py` - Export and environment handling
- `psh/lexer/modular_lexer.py` - Tokenization and escape sequences
- `psh/parser.py` - Command parsing logic
- `psh/executor/array.py` - Array assignment and handling
- `psh/job_manager.py` - Job control and background processes
- `psh/core/state.py` - Shell state and variables

## Related Documents

- `CLAUDE.md` - AI assistant guide for PSH development
- `ARCHITECTURE.md` - System architecture documentation
- `tests/conformance/README.md` - Conformance test documentation
- `docs/posix/posix_compliance_summary.md` - POSIX compliance details