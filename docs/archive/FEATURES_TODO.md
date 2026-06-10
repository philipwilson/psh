# PSH Features TODO

This document tracks features that should be added to PSH based on conformance testing, user requests, and POSIX/bash compatibility needs.

## Parameter Expansion Features

- [ ] **${var:=default}** - Assign default value if variable is unset or empty
  - Currently PSH interprets this as substring syntax
  - Found during conformance testing

- [ ] **${var:-default}** - Use default value if variable is unset or empty
  - Already implemented ✓

- [ ] **${var:+alternate}** - Use alternate value if variable is set
  - Status unknown - needs testing

- [ ] **${var:?error_message}** - Display error and exit if variable is unset or empty
  - Status unknown - needs testing

## Builtin Features

### cd Builtin
- [ ] **CDPATH support** - Search directories in CDPATH when cd'ing to relative paths
  - Found during conformance testing
  - Common feature in POSIX shells

- [ ] **Fix cd - (OLDPWD)** - Currently stores wrong path when using `cd -`
  - Bug found during conformance testing
  - PSH stores absolute path from wrong working directory

### set Builtin
- [ ] **set -e (errexit)** - Exit on command failure
  - Partially implemented - needs testing

- [ ] **set -u (nounset)** - Treat unset variables as error
  - Status unknown

- [ ] **set -o pipefail** - Pipeline fails if any command fails
  - Bash extension, useful for scripting

## I/O Redirection Features

- [ ] **Proper 2>&1 parsing** - Currently tokenizes as separate tokens (2> & 1)
  - Should recognize as single redirect-duplicate operation

- [ ] **&> and &>>** - Redirect both stdout and stderr (bash syntax)
  - Convenience operators

- [ ] **Process substitution** - <(command) and >(command)
  - Tokens exist but implementation needed

## Job Control Features

- [ ] **Proper job control** - fg, bg, jobs commands
  - Basic infrastructure exists
  - Needs proper terminal process group handling

- [ ] **Ctrl-Z handling** - Suspend foreground job
  - Signal handler needed

## Interactive Features

- [ ] **Command history search** - Ctrl-R for reverse search
  - Would improve interactive usability

- [ ] **Programmable completion** - complete/compgen builtins
  - Currently marked as FEATURE_MISSING in conformance tests
  - Complex but valuable for interactive use

- [ ] **Line editor escape sequence handling in PTY** - Arrow keys, cursor movement
  - Currently escape sequences are printed literally in pseudo-terminals (pexpect)
  - Affects interactive testing and usage in terminal emulators
  - Line editor works correctly in real TTY but not in PTY environments

## Expansion Features

- [ ] **Tilde expansion for ~username** - Expand to user's home directory
  - Currently only ~ and ~/ are supported

- [ ] **Extended glob patterns** - ?(pattern), *(pattern), +(pattern), @(pattern), !(pattern)
  - Bash extension, controlled by shopt extglob

## Scripting Features

- [ ] **Local variables in functions** - local builtin
  - Important for function scoping

- [ ] **Arrays** - Indexed and associative arrays
  - Basic array assignment works but full support needed

- [ ] **select statement** - Menu selection construct
  - Token exists but not implemented

## Signal Handling

- [ ] **Complete trap builtin** - All signals and special traps (EXIT, ERR, DEBUG, RETURN)
  - Basic trap exists but needs full implementation

- [ ] **SIGPIPE handling** - Proper handling of broken pipes
  - Important for pipeline behavior

## POSIX Conformance

- [ ] **POSIX mode** - Strict POSIX compliance when enabled
  - Different behavior for various features

- [ ] **IFS field splitting** - Full implementation of Input Field Separator
  - Partially implemented

## Performance Features

- [ ] **Command hashing** - hash builtin and PATH caching
  - Would improve performance for repeated commands

## Debugging Features

- [ ] **set -x enhancement** - Better xtrace output formatting
  - Basic implementation exists

- [ ] **LINENO variable** - Current line number in script
  - Useful for debugging

- [ ] **caller builtin** - Show call stack
  - Useful for debugging functions

## Known Bugs to Fix

1. **cd - stores wrong OLDPWD** - Uses wrong base directory
2. **Line editor in pseudo-terminals (PTY)** - Escape sequences not properly handled
   - Arrow keys print `^[[A`, `^[[B`, `^[[C`, `^[[D` instead of moving cursor
   - Affects pexpect testing and terminal emulator usage
   - Related to terminal mode setup in PTY environments
3. **Line continuation in arithmetic expansion** - May have issues

### Parser Enhancement Issues (from test analysis 2025-01-10)

4. **Incomplete syntax detection** - Parser should detect malformed expressions as errors
   - `echo $(incomplete` - Should fail with syntax error, currently succeeds with empty output
   - `echo ${incomplete-var` - Should fail with syntax error, currently succeeds with empty output  
   - `echo $((2 +` - Should fail with syntax error, currently succeeds with empty output
   - These represent gaps in parser error detection that should be addressed for robustness

5. **Type builtin function detection** - `type` command doesn't find user-defined functions
   - Functions execute correctly but `type funcname` returns "not found"
   - Affects command resolution testing and user experience
   - Function registry may not be properly integrated with type builtin

6. **Error message format inconsistency** - Error messages don't match standard expectations
   - PSH uses "Parse error at position X" format
   - Tests often expect "syntax error" or specific keywords
   - Consider standardizing error message format for better user experience

7. **Complex composite token parsing limitation** - Parser has issues with complex mixed quoted/unquoted tokens
   - `echo prefix"quoted $VAR"suffix` incorrectly creates composite `prefixquoted $VARsuffix`
   - Should parse as three parts: `prefix` + `"quoted $VAR"` + `suffix`
   - Currently requires spaces to separate components: `echo prefix"quoted $VAR" suffix`
   - Affects complex string concatenation scenarios with variable expansion

## Testing Infrastructure

- [ ] **Complete test migration** - Migrate all 1800+ tests to new framework
- [ ] **Performance benchmarks** - Add performance testing suite
- [ ] **Fuzzing tests** - Add fuzzing for parser robustness

### Test Analysis Improvements (2025-01-10)

The following improvements were identified during comprehensive test failure analysis:

**Parser Robustness (High Priority)**
- [ ] **Syntax error detection for incomplete expressions** - Parser currently accepts malformed syntax
  - Command substitution: `$(unclosed` should error, not produce empty output
  - Variable expansion: `${unclosed` should error, not produce empty output
  - Arithmetic expansion: `$((incomplete` should error, not produce empty output
  - This affects script reliability and debugging experience

**Command Resolution Integration (Medium Priority)**  
- [ ] **Fix type builtin function lookup** - `type` should find user-defined functions
  - Functions work but type command reports "not found"
  - Integration between function registry and type builtin needed
  - Important for shell introspection and debugging

**Error Handling Consistency (Low Priority)**
- [ ] **Standardize error message format** - Consider consistent error message style
  - Current: "Parse error at position X: Expected Y"
  - Alternative: "syntax error" or other conventional formats
  - Would improve user experience and test compatibility

---

*Last updated: 2025-01-10*
*Version: 0.72.0 (updated with test analysis findings)*

## Notes

- Features are grouped by category for easier tracking
- Priority should be given to POSIX compliance features
- Some bash extensions are included where they add significant value
- This list is based on conformance testing against bash 5.x