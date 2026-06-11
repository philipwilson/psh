# Chapter 18: Troubleshooting

This chapter helps you diagnose and resolve common issues in PSH. Whether you're encountering parse errors, unexpected behavior, or performance problems, this guide provides solutions and debugging techniques.

## 18.1 Common Error Messages

Understanding PSH error messages helps quickly identify and fix problems.

### Parse Errors

```bash
# Missing keyword error
psh$ if [ -f file.txt ]
> echo "exists"
> 
psh: <command>:3: Parse error at position 15: Expected 'then' after if condition

# Fix: Add missing 'then'
psh$ if [ -f file.txt ]; then
>     echo "exists"
> fi

# Unclosed quote error
psh$ echo "Hello world
> 
psh: <command>:2: Parse error: Unterminated string

# Fix: Close the quote
psh$ echo "Hello world"

# Unexpected token error
psh$ for i in 1 2 3
> echo $i
> 
psh: <command>:2: Parse error at position 8: Expected 'do' after for list

# Fix: Add 'do' keyword
psh$ for i in 1 2 3; do
>     echo $i
> done
```

### Variable and Expansion Errors

```bash
# Undefined variable in arithmetic
psh$ echo $((x + 5))
psh: arithmetic: undefined variable: x
5

# Fix: Define variable first
psh$ x=10
psh$ echo $((x + 5))
15

# Bad substitution error (with undeclared array)
psh$ echo ${var[0]}
psh: ${var[0]}: bad substitution

# Fix: Declare the array first
psh$ declare -a var=(first second third)
psh$ echo ${var[0]}
first

# Invalid parameter expansion
psh$ echo ${var:bad}
psh: ${var:bad}: bad substitution

# Fix: Use valid syntax
psh$ var="hello"
psh$ echo ${var:1:3}
ell
```

### Control Flow Errors

```bash
# Break outside loop
psh$ break
psh: break: only meaningful in a `for' or `while' loop

# Continue outside loop
psh$ continue
psh: continue: only meaningful in a `for' or `while' loop

# Missing case pattern terminator
psh$ case "$var" in
>     pattern) echo "matched"
> esac
psh: <command>:3: Parse error: Expected ';;' or ';&' or ';;&' before 'esac'

# Fix: Add pattern terminator
psh$ case "$var" in
>     pattern) echo "matched" ;;
> esac
```

### Function Errors

```bash
# Invalid function name
psh$ function 123func() {
>     echo "test"
> }
psh: <command>:1: Parse error: Invalid function name

# Fix: Use valid identifier
psh$ function func123() {
>     echo "test"
> }

# Return outside function
psh$ return 0
psh: return: can only `return' from a function

# Recursion depth exceeded
psh$ factorial() {
>     [ $1 -le 1 ] && echo 1 && return
>     echo $(($1 * $(factorial $(($1 - 1)))))
> }
psh$ factorial 1000
psh: <command>:3: unexpected error: maximum recursion depth exceeded
```

## 18.2 Debugging Techniques

PSH provides several debugging tools to help diagnose issues.

### Using Debug Flags

PSH provides several debug flags for different aspects of shell operation:

```bash
# Debug tokenization issues
psh$ psh --debug-tokens -c 'echo "Hello $USER"'
=== Token Debug Output ===
  [  0] WORD                 'echo'
  [  1] WORD                 '"Hello $USER"'
  [  2] EOF                  ''
========================
Hello alice

# Debug parsing issues
psh$ psh --debug-ast -c 'if true; then echo ok; fi'
=== AST Debug Output (recursive_descent) ===
... IfStatement -> condition -> SimpleCommand(true)
    then_body -> SimpleCommand(echo, ok)
======================
ok

# Debug expansion process
psh$ psh --debug-expansion -c 'echo $HOME'
[EXPANSION] Expanding Word AST command: ['echo', '$HOME']
[EXPANSION] Word AST Result: ['echo', '/home/user']
/home/user

# Multiple debug flags can be combined
psh$ psh --debug-ast --debug-tokens -c 'echo hello'
```

### Runtime Debugging

```bash
# Enable expansion debugging during session
psh$ set -o debug-expansion
psh$ echo $USER
[EXPANSION] Expanding Word AST command: ['echo', '$USER']
[EXPANSION] Word AST Result: ['echo', 'alice']
alice

# Check current settings
psh$ set -o
allexport      	off
braceexpand    	on
emacs          	on
errexit        	off
...

# Enable xtrace for command tracing
psh$ set -x
psh$ echo hello
+ echo hello
hello

# Custom trace prefix
psh$ PS4='[trace] '
psh$ set -x
psh$ echo hello
[trace] echo hello
hello

# Disable debugging
psh$ set +o debug-expansion
psh$ set +x
```

### Error Location Information

```bash
# Script errors show file and line
psh$ cat script.sh
#!/usr/bin/env psh
echo "Line 2"
if [ -f file.txt ]  # Missing then
    echo "exists"
fi

psh$ psh script.sh
Line 2
psh: script.sh:3: Parse error at position 18: Expected 'then' after if condition

# Command line errors show position
psh$ echo "unclosed
psh: <command>:1: Parse error: Unterminated string

# Function errors show context
psh$ func() {
>     local x=$((1/0))
> }
psh$ func
psh: <command>:2: arithmetic: division by zero
```

## 18.3 Installation and Environment Issues

### Python Version Problems

```bash
# Check Python version
$ python3 --version
Python 3.11.0

# PSH requires Python 3.12+
$ pip install psh
ERROR: psh requires Python >=3.12

# Solution: Upgrade Python
$ brew upgrade python3  # macOS
$ sudo apt update && sudo apt install python3.12  # Ubuntu

# Use specific Python version
$ python3.12 -m pip install psh
```

### RC File Issues

```bash
# Permission problems
psh$ 
psh: warning: ~/.pshrc has unsafe permissions, skipping

# Fix permissions
$ chmod 600 ~/.pshrc

# Syntax errors in RC file
psh$ 
psh: warning: error loading ~/.pshrc: Parse error at line 5

# Debug RC file
$ psh --norc  # Start without RC file
psh$ source ~/.pshrc  # Test manually

# Use alternate RC file
$ psh --rcfile ~/.pshrc.test
```

### PATH and Command Not Found

```bash
# Command not found errors
psh$ mycommand
psh: mycommand: command not found

# Check PATH
psh$ echo $PATH
/usr/local/bin:/usr/bin:/bin

# Add to PATH
psh$ export PATH="$PATH:$HOME/bin"

# Verify command location
psh$ which mycommand
/home/user/bin/mycommand

# Check if file is executable
psh$ ls -l $(which mycommand)
-rw-r--r-- 1 user user 100 Jan 1 10:00 /home/user/bin/mycommand

# Fix: Make executable
psh$ chmod +x ~/bin/mycommand
```

## 18.4 Performance Issues

### Slow Command Execution

```bash
# Identify slow operations
psh$ time long_command
real    0m5.123s
user    0m2.456s
sys     0m1.789s

# Common performance problems:

# 1. Deep recursion
# Bad: Recursive with command substitution
fib() {
    [ $1 -le 1 ] && echo $1 && return
    echo $(( $(fib $(($1-1))) + $(fib $(($1-2))) ))
}

# Good: Iterative approach
fib_iter() {
    local n=$1 a=0 b=1
    for ((i=0; i<n; i++)); do
        local temp=$b
        b=$((a + b))
        a=$temp
    done
    echo $a
}

# 2. Large glob expansions
# Bad: May be slow with many files
psh$ for file in /usr/**/*; do
>     process "$file"
> done

# Good: Use find for large trees
psh$ find /usr -type f | while read file; do
>     process "$file"
> done

# 3. Repeated command substitutions
# Bad: Calls date many times
for i in {1..1000}; do
    echo "$(date): Processing $i"
done

# Good: Call once and reuse
start_time=$(date)
for i in {1..1000}; do
    echo "$start_time: Processing $i"
done
```

### Memory Usage Issues

```bash
# Monitor memory usage
psh$ ps aux | grep psh
user  12345  0.5  2.1  123456  78901 pts/1  S+   10:00  0:05 psh

# Common memory issues:

# 1. Large variable contents
# Bad: Loading entire file
content=$(cat very_large_file.txt)

# Good: Process line by line
while IFS= read -r line; do
    process "$line"
done < very_large_file.txt

# 2. Infinite loops
# Add safety checks
count=0
while condition; do
    # Safety check
    ((count++))
    if ((count > 10000)); then
        echo "Error: Loop limit exceeded" >&2
        break
    fi
    # Loop body
done
```

## 18.5 Input/Output Issues

### Redirection Problems

```bash
# Multiple redirections
psh$ command < input.txt > output.txt 2>&1

# Heredoc with redirections
psh$ cat << EOF > output.txt
> Line 1
> Line 2
> EOF

# Process substitution
psh$ diff <(command1) <(command2)
# Check that process substitution creates valid FDs:
psh$ echo <(echo test)
/dev/fd/63

# Builtin output redirects correctly
psh$ pwd > output.txt
psh$ cat output.txt
/current/directory
```

### Pipeline Issues

```bash
# Exit status in pipelines
psh$ false | true
psh$ echo $?
0  # Only last command's status by default

# Use pipefail for stricter checking
psh$ set -o pipefail
psh$ false | true
psh$ echo $?
1  # Now reports failure from any pipeline stage

# Control structures in pipelines work correctly
psh$ if true; then echo yes; fi | grep yes
yes

psh$ echo "data" | while read line; do echo "Read: $line"; done
Read: data
```

## 18.6 Job Control Problems

### Background Job Issues

```bash
# Job stops when reading input
psh$ cat &
[1] 12345
[1]+ Stopped (tty input)  cat

# Fix: Redirect input
psh$ cat < /dev/null &
[1] 12346

# Lost background jobs
psh$ long_command &
[1] 12347
# Shell exits, job may be terminated

# Solution: Use nohup equivalent
psh$ (trap '' HUP; long_command) &

# Job control in scripts
#!/usr/bin/env psh
command &
fg %1  # Error: no job control in scripts

# Fix: Use wait with PID
#!/usr/bin/env psh
command &
pid=$!
wait $pid
```

### Signal Handling

```bash
# Ctrl-C not working
# Check if process is in foreground
psh$ jobs
[1]+ Running    stubborn_process &
psh$ fg %1
stubborn_process
^C  # Now Ctrl-C works

# Ctrl-Z not suspending
# Some programs ignore SIGTSTP
psh$ ungraceful_program
^Z  # Doesn't work

# Force stop with different signal
psh$ kill -STOP %1
```

## 18.7 Script Debugging Best Practices

### Add Debug Output

```bash
#!/usr/bin/env psh
# debug.sh - Script with debug output

# Debug function
debug() {
    [ "${DEBUG:-0}" = "1" ] && echo "DEBUG: $*" >&2
}

# Version information
VERSION="1.0"
debug "Script version: $VERSION"

# Trace execution
debug "Starting main function"
main() {
    local input="$1"
    debug "Processing input: $input"
    
    # Validate input
    if [ -z "$input" ]; then
        echo "Error: No input provided" >&2
        return 1
    fi
    debug "Input validated"
    
    # Process
    result=$(process_data "$input")
    debug "Result: $result"
    
    echo "$result"
}

# Run with debugging
# DEBUG=1 ./debug.sh myinput
```

### Error Handling Patterns

```bash
#!/usr/bin/env psh
# Error handling example

# Set error handler
handle_error() {
    local exit_code=$1
    local line_no=$2
    echo "Error on line $line_no: Command failed with exit code $exit_code" >&2
    # Cleanup
    rm -f "$temp_file"
    exit $exit_code
}

# Check commands
run_command() {
    "$@" || handle_error $? 0
}

# Use throughout script
temp_file=$(mktemp)
run_command process_data > "$temp_file"
run_command validate_output "$temp_file"
rm -f "$temp_file"
```

### Test in Isolation

```bash
# Test individual functions
psh$ source script.sh
psh$ # Now test functions individually
psh$ test_function "input"

# Test with minimal examples
# Create test case
psh$ cat > test_case.sh << 'EOF'
> #!/usr/bin/env psh
> # Minimal test case
> echo "Before problem"
> # Problem code here
> echo "After problem"
> EOF

psh$ psh test_case.sh

# Binary search for issues
# Comment out half the script
# If error persists, problem is in remaining half
# Repeat until problem isolated
```

## 18.8 Common Pitfalls and Solutions

### Quote and Expansion Issues

```bash
# Problem: Word splitting
psh$ file="my file.txt"
psh$ cat $file
cat: my: No such file or directory
cat: file.txt: No such file or directory

# Solution: Quote variables
psh$ cat "$file"

# Problem: Glob expansion in quotes
psh$ echo "$HOME/*.txt"
/home/user/*.txt

# Solution: Remove quotes for expansion
psh$ echo $HOME/*.txt
/home/user/file1.txt /home/user/file2.txt

# Problem: Tilde in quotes
psh$ echo "~/file"
~/file

# Solution: Tilde outside quotes
psh$ echo ~/file
/home/user/file
```

### Variable Assignment Pitfalls

```bash
# Problem: Spaces around =
psh$ VAR = value
psh: VAR: command not found

# Solution: No spaces
psh$ VAR=value

# Problem: Assignment with command
psh$ VAR=value echo $VAR
# Empty output (VAR set only for echo)

# Solution: Separate assignment
psh$ VAR=value
psh$ echo $VAR
value

# Problem: Unset vs empty
psh$ [ -z $UNSET_VAR ]
psh: [: binary operator expected

# Solution: Quote or use default
psh$ [ -z "$UNSET_VAR" ]
psh$ [ -z "${UNSET_VAR:-}" ]
```

### Loop and Control Structure Issues

```bash
# Problem: Missing do/then
psh$ for i in 1 2 3
> echo $i
psh: Parse error: Expected 'do'

# Solution: Add keywords
psh$ for i in 1 2 3; do
>     echo $i
> done

# Problem: Variable scope in pipeline
psh$ echo "test" | while read line; do
>     var="$line"
> done
psh$ echo $var
# Empty - pipeline runs in subshell

# Solution: Avoid pipeline
psh$ while read line; do
>     var="$line"
> done < <(echo "test")
psh$ echo $var
test
```

## 18.9 Getting Help

### Built-in Help

```bash
# Check version
psh$ psh --version
Python Shell (psh) version 0.x.y

# Command line help
psh$ psh --help
Usage: psh [options] [script [args...]]
       psh [options] -c command [args...]
...

# Check available builtins
psh$ type cd pwd exit
cd is a shell builtin
pwd is a shell builtin
exit is a shell builtin

# View current settings
psh$ set -o
```

### External Resources

```bash
# Report issues
# https://github.com/anthropics/claude-code/issues

# View source code
# https://github.com/your-username/psh

# Read documentation
psh$ cat $PSH_DIR/docs/user_guide/README.md

# Compare with Bash
psh$ # Test in PSH
psh$ exit
$ # Test same command in Bash
$ bash -c 'same command'
```

### Creating Bug Reports

```bash
# Minimal reproducible example
cat > bug_report.sh << 'EOF'
#!/usr/bin/env psh
# PSH version: 0.275.0
# Python version: 3.12.4
# OS: Ubuntu 24.04

# Problem: Describe issue here

# Steps to reproduce:
echo "Step 1"
# Command that causes issue

# Expected behavior:
# What should happen

# Actual behavior:
# What actually happens

# Workaround (if any):
# How to avoid the issue
EOF
```

## Summary

Effective troubleshooting in PSH requires understanding common issues and available debugging tools:

1. **Common Errors**: Parse errors, variable issues, control flow problems
2. **Debugging Tools**: --debug flags, runtime settings, error locations
3. **Installation Issues**: Python versions, RC files, PATH problems
4. **Performance**: Recursion limits, memory usage, optimization techniques
5. **I/O Problems**: Redirection issues, pipeline behavior
6. **Job Control**: Background processes, signal handling
7. **Best Practices**: Debug output, error handling, testing techniques
8. **Common Pitfalls**: Quotes, variables, control structures
9. **Getting Help**: Built-in resources, external documentation, bug reports

Key principles:
- Read error messages carefully - they include location information
- Use debug flags to understand parsing and execution
- Test components in isolation
- Compare behavior with Bash when unsure
- Work around limitations with alternative approaches
- Keep reproducible examples for bug reports

Understanding these troubleshooting techniques helps you work effectively with PSH and quickly resolve issues when they arise.

---

[Previous: Chapter 17 - Differences from Bash](17_differences_from_bash.md) | [Table of Contents](README.md)