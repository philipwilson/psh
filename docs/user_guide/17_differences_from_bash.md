# Chapter 17: Differences from Bash

While PSH implements many shell features compatible with Bash, there are important differences due to its educational focus and Python implementation. Understanding these differences helps you write portable scripts and use PSH effectively.

## 17.1 Supported Features Overview

PSH v0.221.0 has near-complete compatibility with Bash for core shell programming. Most common Bash scripts run without modification. This section highlights what is fully supported before discussing the remaining gaps.

### Shell Options

PSH supports an extensive set of shell options matching Bash behavior:

```bash
# Core error-handling options
set -e              # Exit on error (errexit)
set -u              # Error on undefined variables (nounset)
set -x              # Print commands before execution (xtrace)
set -o pipefail     # Pipeline fails if any command fails

# Additional POSIX/Bash options
set -o allexport    # Export all variables on assignment
set -o braceexpand  # Enable brace expansion (on by default)
set -o noclobber    # Prevent overwriting files with >
set -o noglob       # Disable filename globbing
set -o noexec       # Read commands but do not execute
set -o notify       # Report background job status immediately
set -o verbose      # Print input lines as they are read
set -o ignoreeof    # Prevent Ctrl-D from exiting the shell
set -o monitor      # Enable job control
set -o posix        # Enable POSIX compliance mode

# Short-form combinations work, including a trailing 'o' that takes
# the next argument as a long option name (as of v0.242.0):
set -eu             # Enable errexit and nounset
set -eux            # Enable errexit, nounset, and xtrace
set -euo pipefail   # Strict mode, exactly like bash

# View all options
set -o              # Show all option settings
set +o              # Show settings as re-enterable commands
```

### Glob Options (shopt)

PSH provides several glob-related options via `shopt`:

```bash
# Available shopt options
shopt -s dotglob     # Include hidden files in glob expansion
shopt -s nullglob    # Non-matching globs expand to nothing
shopt -s globstar    # Enable ** recursive globbing
shopt -s nocaseglob  # Case-insensitive globbing
shopt -s extglob     # Enable extended glob patterns: ?(p) *(p) +(p) @(p) !(p)
```

### Extended Glob Patterns (extglob)

Extended glob patterns are supported once `extglob` is enabled, in globbing,
`[[ ]]`, and `case`:

```bash
shopt -s extglob
ls !(*.txt)          # Everything except .txt files
[[ abc == @(abc|xyz) ]] && echo match
case "$x" in +(a)) echo "one or more a" ;; esac
```

As in Bash, `extglob` must be enabled *before* the line that uses an extended
pattern is parsed. In a single `-c` string the whole line is parsed at once, so
`shopt -s extglob; ls !(*.txt)` will not work — enable it on an earlier line
(for example in your rc file or a preceding command).

### Regex Matching and BASH_REMATCH

```bash
# The =~ operator matches and populates BASH_REMATCH with capture groups:
[[ "hello123" =~ ([a-z]+)([0-9]+) ]]
echo "${BASH_REMATCH[0]}"   # hello123 (whole match)
echo "${BASH_REMATCH[1]}"   # hello    (group 1)
echo "${BASH_REMATCH[2]}"   # 123      (group 2)
```

### Parameter Transformation Operators (${var@OP})

```bash
x="a b"
echo "${x@Q}"        # 'a b'        - quote for reuse as shell input
echo "${x@U}"        # A B          - uppercase all
echo "${x@u}"        # A b          - uppercase first character
echo "${x@L}"        # a b          - lowercase all
y='a\tb'
echo "${y@E}"        # a<TAB>b      - expand ANSI-C backslash escapes
p='\u@\h'
echo "${p@P}"        # user@host    - prompt-string expansion
echo "${x@A}"        # x='a b'      - assignment/declare form
declare -i n=5
echo "${n@a}"        # i            - attribute-flag letters

# Per-element across arrays and positional parameters:
arr=(one "two three")
echo "${arr[@]@Q}"   # 'one' 'two three'
echo "${arr[@]@A}"   # declare -a arr=([0]="one" [1]="two three")
```

The associative key/value operators `@K` (quoted key/value pairs) and `@k`
(bare key/value pairs) are also supported; associative pairs iterate in
insertion order rather than bash's hash order.

### Arrays and Associative Arrays

```bash
# Indexed arrays
declare -a array=(one two three)
echo ${array[0]}         # First element
echo ${array[@]}         # All elements
echo ${#array[@]}        # Number of elements
fruits=(apple banana cherry)
fruits[3]="orange"       # Add element
fruits+=(grape)          # Append to array
echo ${fruits[@]:1:2}    # Slice from index 1, length 2
echo ${!fruits[@]}       # All indices

# Array element operations
files=(doc.txt img.txt data.txt)
echo ${files[@]/.txt/.bak}  # Replace in all elements
echo ${files[@]^^}          # Uppercase all elements

# Sparse arrays
unset fruits[2]
echo ${!fruits[@]}       # Shows remaining indices

# Associative arrays
declare -A colors=([red]="#FF0000" [green]="#00FF00")
colors[blue]="#0000FF"
echo ${colors[red]}      # Access by key
echo ${!colors[@]}       # All keys
echo ${colors[@]}        # All values
```

### Trap Command

```bash
# Signal handling
trap 'echo "Cleaning up..."' EXIT
trap 'echo "Interrupted"' INT TERM

# List current traps
trap -p
trap -p INT            # Show specific trap

# Reset traps to default
trap - EXIT INT
```

PSH handles standard signals and the `EXIT`, `DEBUG`, and `ERR`
pseudo-signals (as of v0.263.0). `RETURN` is not supported (see 17.2).

### Select Statement

```bash
select option in "Option 1" "Option 2" "Quit"; do
    case $option in
        "Option 1") echo "You chose 1" ;;
        "Option 2") echo "You chose 2" ;;
        "Quit") break ;;
        *) echo "Invalid selection" ;;
    esac
done
```

### Command History

```bash
# The `history` builtin lists previous commands in interactive mode:
history          # Show command history
history 10       # Show last 10 commands
```

History *expansion* is supported in interactive mode: event
designators (`!!`, `!n`, `!-n`, `!string`, `!?string?`), word designators
(`!$`, `!^`, `!*`, `!!:n`, `!!:n-m`), the `:h`/`:t`/`:r`/`:e`/`:s`/`:g&`/`:p`
modifiers, and `^old^new` quick substitution all match bash. The `:q`/`:x`
word-quoting modifiers and the `!#` (current-line) event designator are not
yet supported.

### Job Control

PSH provides full job control in interactive mode including `disown`:

```bash
# All standard job control
jobs           # List jobs
fg %1          # Bring job to foreground
bg %1          # Resume job in background
wait           # Wait for background jobs
kill %1        # Send signal to job
disown %1      # Remove job from job table
disown -h %1   # Mark job to not receive SIGHUP
disown -a      # Remove all jobs
```

### Process Substitution

```bash
# Input process substitution
diff <(sort file1.txt) <(sort file2.txt)

# Output process substitution
echo "data" | tee >(grep pattern > matches.txt)
```

### mapfile / readarray

```bash
# Read lines of input into an indexed array (readarray is a synonym):
mapfile -t lines < file.txt        # -t strips trailing newlines
readarray -t lines < file.txt
echo "${lines[0]} (${#lines[@]} lines)"

# Options: -d delim, -n count, -O origin (no clear), -s skip, -t, -u fd.
mapfile -t -s 1 -n 2 first_two < data.txt
```

The `-C callback` / `-c quantum` options are not supported.

### let

```bash
# Evaluate arithmetic expressions (equivalent to ((...)) per argument):
let x=5+3              # x=8
let "a = 2" "b = a+1" # b=3; side effects apply (++x, x+=2, etc.)
let "count > 0"       # exit 0 if the last expression is non-zero, else 1
```

### Name References and Indirect Expansion

```bash
# Namerefs (declare -n / local -n): a variable that refers to another by name.
x=5
declare -n r=x
echo "$r"             # 5      (read-through)
r=9; echo "$x"        # 9      (write-through; creates the target if unset)
declare -n a=b b=c    # chains resolve transitively
echo "${!r}"          # x      (for a nameref, ${!r} is the target NAME)

# Pass-by-reference into functions:
inc() { local -n n=$1; n=$((n + 1)); }
count=5; inc count; echo "$count"   # 6

# unset follows the nameref; unset -n removes the nameref itself:
unset r               # unsets the target (x)
unset -n r            # unsets the nameref, leaving the target

# Classic indirect expansion (when the name is NOT a nameref):
name=HOME
echo "${!name}"       # value of $HOME
```

Namerefs may also target an array element:

```bash
arr=(p q r)
declare -n e=arr[1]
echo "$e"             # q
e=Q; echo "${arr[@]}" # p Q r
```

## 17.2 Unimplemented Features

The following Bash features are not available in PSH.

### Coprocesses

```bash
# NOT implemented
coproc { command; }           # Command not found
coproc NAME { command; }      # Command not found
```

### RETURN Traps

```bash
# EXIT, DEBUG, and ERR all fire (DEBUG before each simple command; ERR
# after failures, with the same exemptions as set -e). RETURN does not:
trap 'echo ret' RETURN   # Error: invalid signal specification
```

### Programmable Completion

```bash
# The complete/compgen builtins do not exist
complete -F _my_func mycommand  # Command not found
compgen -W "words" -- prefix    # Command not found

# Basic tab completion for files, directories, and commands
# IS available in interactive mode
```

### Missing Builtins

```bash
# These Bash builtins are not available:
caller                       # Call-stack introspection - not a builtin
```

(`let`, `mapfile`, and `readarray` **are** supported — see 17.1.)

### Read Builtin Limitations

```bash
# The read builtin supports -r, -d, -p, -t, -n, -N, -s, -a, and -u:
read -r var             # Raw mode (no backslash processing)
read -d ':' var         # Custom delimiter
read -p "prompt: " var  # Prompt (interactive only)
read -t 5 var           # Timeout
read -n 4 var           # Read up to N characters
read -N 4 var           # Read EXACTLY N characters
read -s var             # Silent mode (passwords)
read -a arr             # Read words into an array
read -u 3 var           # Read from file descriptor 3

# Only the readline-editing options are unsupported:
read -e var             # Error: invalid option (readline line editing)
read -i text var        # Error: invalid option (initial readline text)
```

### Other Missing Features

```bash
# wait -n (wait for any single job)
wait -n                 # Waits for the next background job to finish

# time keyword (reserved word; times pipelines/compounds, default & -p formats)
time echo hello         # Times the command; `time while ...; done`, `time { ...; }` work too
                        # (TIMEFORMAT is not yet honored)

# Call-stack introspection arrays
echo ${BASH_SOURCE[0]}  # Not available (empty)
echo ${BASH_LINENO[0]}  # Not available (empty)
echo ${FUNCNAME[0]}     # Current function name works...
echo ${FUNCNAME[1]}     # ...but the rest of the call stack is not populated
```

## 17.3 Behavioral Differences

Some features work differently in PSH compared to Bash.

### Quote Handling

```bash
# Single quote handling follows POSIX rules:
echo 'It'"'"'s a test'  # Concatenate quoted strings
echo "It's a test"      # Use double quotes
echo 'It'\''s a test'   # End-quote, escaped quote, start-quote
```

### Variable Assignment

```bash
# PSH follows Bash rules for variable assignment:
VAR=value         # Correct - no spaces around =
VAR= value        # Sets VAR to empty, then runs "value" as command
VAR =value        # Tries to run "VAR" as command with arg "=value"
```

### Here Document Behavior

```bash
# Tab suppression with <<- works correctly:
cat <<-EOF
	This has a tab
	This too
EOF
# Output has leading tabs removed

# Quoted vs unquoted delimiter:
cat <<'EOF'      # No expansion
$HOME
EOF

cat <<EOF        # With expansion
$HOME
EOF
```

### Debug Option Runtime Behavior

```bash
# Command-line debug flags produce visible output:
psh --debug-ast -c 'echo hello'     # Shows AST tree
psh --debug-tokens -c 'echo hello'  # Shows token list

# Runtime set -o debug-* options can be set but
# some may not produce the same output format:
set -o debug-expansion   # Works - shows expansion trace
set -o debug-exec        # Works - shows execution trace
set -o debug-ast         # Can be set but may not produce output
set -o debug-tokens      # Can be set but may not produce output

# Use command-line flags for reliable debug output
```

### Recursion Depth

```bash
# PSH has limited recursion depth due to Python's call stack
# Deep recursion that works in Bash may fail in PSH:

factorial() {
    local n=$1
    if [ $n -le 1 ]; then
        echo 1
    else
        echo $((n * $(factorial $((n - 1)))))
    fi
}
factorial 1000  # May fail with stack overflow

# Workaround: Use iteration
factorial_iter() {
    local n=$1 result=1
    while [ $n -gt 1 ]; do
        result=$((result * n))
        n=$((n - 1))
    done
    echo $result
}
```

## 17.4 PSH-Specific Features

PSH includes features not found in Bash, designed for education and development.

### Debug Flags

```bash
# Command-line debug flags
psh --debug-ast script.sh           # Show parsed AST before execution
psh --debug-ast=tree script.sh      # Tree format (default)
psh --debug-ast=compact script.sh   # Compact format
psh --debug-ast=sexp script.sh      # S-expression format
psh --debug-ast=dot script.sh       # Graphviz DOT format
psh --debug-tokens script.sh        # Show tokenization
psh --debug-scopes script.sh        # Show variable scope operations
psh --debug-expansion script.sh     # Show expansion process
psh --debug-expansion-detail script.sh  # Detailed expansion steps
psh --debug-exec script.sh          # Show execution flow
psh --debug-exec-fork script.sh     # Show fork/exec details

# Runtime debug options (via set -o)
set -o debug-expansion    # Enable expansion tracing
set -o debug-exec         # Enable execution tracing
set -o debug-parser       # Enable parser tracing

# Custom PS4 for xtrace
PS4='[trace] '
set -x
echo hello               # Shows: [trace] echo hello
```

### Script Analysis Tools

```bash
# Validate script without executing
psh --validate script.sh    # Check for parse errors

# Format script
psh --format script.sh      # Pretty-print formatted script

# Lint analysis
psh --lint script.sh        # Check for common issues

# Security analysis
psh --security script.sh    # Check for security concerns

# Code metrics
psh --metrics script.sh     # Show complexity and statistics
```

### Parser Selection

```bash
# PSH includes two parsers for educational comparison:
psh --parser rd script.sh         # Recursive descent (default)
psh --parser combinator script.sh # Combinator parser (experimental)

# Switch at runtime (interactive mode):
parser-select combinator
parser-select rd
```

### Shell Version Detection

```bash
# PSH sets PSH_VERSION (not BASH_VERSION):
echo $PSH_VERSION    # Shows: 0.221.0

# Detect PSH:
if [ -n "$PSH_VERSION" ]; then
    echo "Running in PSH $PSH_VERSION"
fi
```

## 17.5 Feature Compatibility Reference

| Feature | Bash | PSH | Notes |
|---------|------|-----|-------|
| **Basic Features** |
| Command execution | Yes | Yes | Full support |
| Pipelines | Yes | Yes | Full support |
| I/O redirection | Yes | Yes | All forms supported |
| Background jobs | Yes | Yes | Interactive only |
| Subshells | Yes | Yes | Full support |
| **Variables** |
| Simple variables | Yes | Yes | Full support |
| Arrays | Yes | Yes | Full support |
| Associative arrays | Yes | Yes | Full support |
| Local variables | Yes | Yes | Full support |
| Variable attributes | Yes | Yes | declare -i, -r, -x, etc. |
| **Expansions** |
| Parameter expansion | Yes | Yes | All features |
| Command substitution | Yes | Yes | Both $() and backticks, including `case` statements with bare `pattern)` forms inside `$()` |
| Arithmetic expansion | Yes | Yes | Full support |
| Brace expansion | Yes | Yes | Full support |
| Process substitution | Yes | Yes | Full support |
| Tilde expansion | Yes | Yes | Full support |
| Case modification | Yes | Yes | ${var^^}, ${var,,}, etc. |
| **Control Structures** |
| if/then/else/fi | Yes | Yes | Full support |
| while/until/do/done | Yes | Yes | Full support |
| for/do/done | Yes | Yes | Full support |
| C-style for loops | Yes | Yes | Full support |
| case/esac | Yes | Yes | Full support |
| select | Yes | Yes | Full support |
| Arithmetic commands (( )) | Yes | Yes | Full support |
| Control structures in pipelines | Yes | Yes | Full support |
| **Functions** |
| Function definition | Yes | Yes | Both syntaxes |
| Local variables | Yes | Yes | Full support |
| Return values | Yes | Yes | Full support |
| **Job Control** |
| jobs command | Yes | Yes | Interactive only |
| fg/bg commands | Yes | Yes | Interactive only |
| Job specifications | Yes | Yes | %1, %+, %-, %string |
| wait builtin | Yes | Yes | Full support |
| disown builtin | Yes | Yes | Full support |
| **Shell Options** |
| set -e (errexit) | Yes | Yes | Full support |
| set -u (nounset) | Yes | Yes | Full support |
| set -x (xtrace) | Yes | Yes | Full support |
| set -o pipefail | Yes | Yes | Full support |
| set -o noclobber | Yes | Yes | Full support |
| set -o allexport | Yes | Yes | Full support |
| set -o noglob | Yes | Yes | Full support |
| set -o verbose | Yes | Yes | Full support |
| **Signal Handling** |
| trap command | Yes | Yes | Standard signals + EXIT/DEBUG/ERR |
| Signal handling | Yes | Yes | All standard signals |
| DEBUG/ERR/RETURN traps | Yes | Partial | DEBUG and ERR supported (v0.263); RETURN not |
| **Advanced Features** |
| Here documents | Yes | Yes | Full support |
| Here strings | Yes | Yes | Full support |
| Enhanced test [[ ]] | Yes | Yes | Full support |
| Regex matching =~ | Yes | Yes | BASH_REMATCH capture groups populated |
| eval builtin | Yes | Yes | Full support |
| getopts builtin | Yes | Yes | Full support |
| printf builtin | Yes | Yes | Full support (incl. %q) |
| pushd/popd/dirs | Yes | Yes | Full support |
| shopt options | Yes | Partial | dotglob, nullglob, globstar, nocaseglob, extglob, inherit_errexit |
| Extended glob patterns | Yes | Yes | ?() *() +() @() !() (enable extglob before the line) |
| read options | Yes | Partial | -r -d -p -t -n -N -s -a -u supported; -e/-i (readline editing) not |
| command history (`history`) | Yes | Yes | Listing past commands (interactive) |
| History expansion (!!, !n) | Yes | Yes | Full support for interactive event/word designators + :h/:t/:r/:e/:s/:g& modifiers + ^old^new; :q/:x modifiers and !# designator not yet supported |
| Coprocesses | Yes | No | Not implemented |
| Programmable completion | Yes | No | Basic tab completion only |
| Namerefs (declare -n / local -n) | Yes | Yes | Scalar and array-element targets; chains; local -n |
| Indirect expansion ${!var} | Yes | Yes | Scalar; ${!arr[@]} indices and ${!prefix*}/${!prefix@} name-listing all work |
| Parameter transforms ${var@Q/U/u/L/E/P/A/a} | Yes | Yes | Scalar, array, and positional |
| Assoc key/value transforms ${var@K} / ${var@k} | Yes | Yes | Full support (assoc pairs iterate in insertion order, not bash hash order) |
| let builtin | Yes | Yes | Equivalent to ((...)) per argument |
| mapfile/readarray | Yes | Yes | -d/-n/-O/-s/-t/-u (no -C/-c) |
| caller builtin | Yes | No | Not implemented |
| BASH_SOURCE / BASH_LINENO | Yes | No | Not populated |
| FUNCNAME | Yes | Partial | [0] only; full call stack not populated |
| wait -n | Yes | Yes | Waits for the next job; `-n` / `-p VAR` |
| time keyword | Yes | Partial | Times pipelines (default & `-p` formats); `TIMEFORMAT` not honored |
| ${!prefix*} name matching | Yes | Yes | Full support |
| **PSH-Specific** |
| --debug-ast | No | Yes | Multiple output formats |
| --debug-tokens | No | Yes | PSH only |
| --debug-scopes | No | Yes | PSH only |
| --debug-expansion | No | Yes | PSH only |
| --validate | No | Yes | Syntax validation |
| --format | No | Yes | Script formatting |
| --lint | No | Yes | Lint analysis |
| --security | No | Yes | Security analysis |
| --metrics | No | Yes | Code metrics |

## 17.6 Writing Portable Scripts

When writing scripts that need to work in both PSH and Bash, follow these guidelines.

### Stick to Common Features

```bash
#!/bin/sh
# For maximum portability, use POSIX features:

# POSIX test command
if [ -f "$file" ]; then
    echo "File exists"
fi

# Standard arithmetic
result=$((a + b))

# For PSH+Bash portability, these features are safe:
# - [[ ]] enhanced test, including =~ with BASH_REMATCH capture groups
# - (( )) arithmetic commands
# - Arrays and associative arrays
# - Process substitution <() and >()
# - Parameter expansion (all forms, incl. ${var^^}/${var,,} case mod)
# - Brace expansion (including expansion items like {$((1)),$((2))})
# - Extended glob patterns (with shopt -s extglob enabled beforehand)
# - Here documents and here strings
# - trap command (standard signals + EXIT/DEBUG/ERR; avoid RETURN)
# - All control structures
```

### Detect the Shell

```bash
#!/bin/sh
# Detect which shell is running
if [ -n "$BASH_VERSION" ]; then
    echo "Running in Bash $BASH_VERSION"
elif [ -n "$PSH_VERSION" ]; then
    echo "Running in PSH $PSH_VERSION"
else
    echo "Unknown shell"
fi
```

### Strict Mode Portability

```bash
# Bash strict mode works identically in PSH (as of v0.253.0):
set -euo pipefail

# errexit honours the POSIX exemptions exactly as bash does:
# if/while/until conditions, non-final && / || members, and ! negation
# do not trigger an exit; subshells inherit set -e and $?.
# Command substitutions clear set -e in the child, as in bash:
# `set -e; x=$(false; echo hi)` sets x=hi. Use `shopt -s inherit_errexit`
# (or POSIX mode) to keep set -e inside $(...).
```

## 17.7 Migration Guide

### From Bash to PSH

Most Bash scripts work without modification. Check for these issues:

```bash
# 1. Check for unsupported builtins / features
grep -E 'coproc|complete |compgen |caller' script.sh
grep -E 'read .*-[ei]' script.sh              # read -e/-i (readline editing) unsupported

# 2. Check for RETURN traps (DEBUG and ERR ARE supported)
grep -E 'trap .*RETURN' script.sh
```

### Script Compatibility Checklist

```bash
#!/usr/bin/env psh
# PSH v0.221.0 Compatibility Checklist

# Fully supported:
# - Variables, arrays, associative arrays
# - All control structures (if, while, for, case, select)
# - C-style for loops
# - Functions with local variables
# - Command substitution $() and backticks
# - Process substitution <() and >()
# - All I/O redirection forms (incl. arithmetic fd targets, e.g. >&$((n)))
# - Parameter expansion (most bash forms; case mod ${var^^}/${var,,};
#   transforms ${var@Q/U/u/L/E/P/A/a})
# - Arithmetic expansion and commands
# - Brace expansion, incl. expansion items {$((1)),$((2))} and ranges
# - Extended glob patterns (shopt -s extglob, enabled beforehand)
# - Regex matching =~ with BASH_REMATCH capture groups
# - Job control (jobs, fg, bg, wait, disown)
# - Shell options (errexit, nounset, xtrace, pipefail, etc.)
# - eval, trap (standard signals + EXIT + DEBUG + ERR), getopts, printf (incl. %q)
# - read -r/-d/-p/-t/-n/-N/-s/-a/-u
# - Subshells with variable isolation
# - Control structures in pipelines
# - Here documents and here strings
# - shopt: dotglob, nullglob, globstar, nocaseglob, extglob, inherit_errexit
# - pushd, popd, dirs
# - history builtin (interactive)
# - History expansion (interactive): !!, !n, !-n, !str, !?str?, word
#   designators (!$, !!:1, !!:*), :h/:t/:r/:e/:s/:g& modifiers, ^old^new
# - mapfile / readarray (-d/-n/-O/-s/-t/-u)
# - let (arithmetic evaluation)
# - namerefs (declare -n / local -n), scalar & array-element targets; ${!var}
# - ${!prefix*} / ${!prefix@} variable-name prefix matching
# - Associative key/value transforms ${var@K} / ${var@k}
#   (assoc pairs iterate in insertion order, not bash hash order)

# Not supported:
# - RETURN traps (DEBUG / ERR ARE supported)
# - History expansion :q/:x word-quoting modifiers and the !# event designator
# - Coprocesses (coproc)
# - Programmable completion (complete, compgen)
# - caller builtin
# - read -e / read -i (readline line editing)
# - BASH_SOURCE/BASH_LINENO; FUNCNAME beyond [0]
# - Very deep recursion (Python stack limits)
```

## 17.8 Design Philosophy

PSH is built with educational priorities:

```
1. Code clarity over performance
2. Educational value over feature completeness
3. Correct behavior over optimization
4. Helpful errors over terse messages
5. Built-in debugging over external tools
```

This means:
- Some rarely-used Bash features may never be implemented
- Error messages are more descriptive than Bash
- Built-in debugging tools (AST, token, expansion tracing) provide visibility into shell internals
- The Python implementation enables script analysis tools (lint, security, metrics) not available in Bash
- Performance is adequate for interactive use and scripting but not optimized for high-throughput workloads

## Summary

PSH v0.221.0 provides near-complete Bash compatibility for everyday shell programming:

1. **Comprehensive Feature Support**: Arrays, associative arrays, trap, wait, disown, all control structures, all expansions, extended globs, `=~` with BASH_REMATCH
2. **Full Shell Options**: errexit, nounset, xtrace, pipefail, noclobber, allexport, and many more
3. **Remaining Gaps**: RETURN traps (DEBUG/ERR fire), coprocesses, programmable completion, `caller`, `read -e`/`read -i` (readline editing), `BASH_SOURCE`/`BASH_LINENO`
4. **Educational Tools**: Debug flags, script analysis, multiple parser implementations
5. **High Compatibility**: Most Bash scripts run without modification

Key differences to remember:
- Use `set -eu -o pipefail` instead of `set -euo pipefail`
- Namerefs (`declare -n`/`local -n`) support scalar and array-element targets, chains, and `local -n` pass-by-reference; `${!var}` indirect expansion works too
- All `${var@...}` transform operators are supported, including `${var@K}`/`${var@k}` (associative key/value display)
- DEBUG and ERR traps and interactive history expansion (`!!`, `!n`, word designators, modifiers) all work; only RETURN traps are unimplemented
- `caller` is not available (`let`, `mapfile`, `readarray` are supported)
- Use `$PSH_VERSION` instead of `$BASH_VERSION` to detect PSH
- Deep recursion may hit Python stack limits

---

[Previous: Chapter 16 - Advanced Features](16_advanced_features.md) | [Next: Chapter 18 - Troubleshooting](18_troubleshooting.md)
