# Chapter 10: Pipelines and Lists

Pipelines and command lists are fundamental to shell programming, allowing you to combine simple commands into powerful data processing workflows. PSH supports pipes for connecting commands, conditional execution with && and ||, sequential execution with semicolons, and control structures as pipeline components.

## 10.1 Simple Pipelines (|)

A pipeline connects the stdout of one command to the stdin of the next, creating a data processing chain.

### Basic Pipeline Usage

```bash
# Simple two-command pipeline
psh$ ls | wc -l
42

# How it works:
# 1. ls writes filenames to stdout
# 2. | connects ls stdout to wc stdin
# 3. wc counts the lines

# Multiple commands
psh$ cat file.txt | grep "error" | sort | uniq -c
      3 error: file not found
      1 error: permission denied
      5 error: timeout

# Long pipelines with line continuation
psh$ cat access.log | \
>    grep "GET" | \
>    awk '{print $1}' | \
>    sort | \
>    uniq -c | \
>    sort -rn | \
>    head -10

# Process text data
psh$ echo "hello world" | tr 'a-z' 'A-Z'
HELLO WORLD

psh$ echo "one,two,three" | tr ',' '\n'
one
two
three
```

### Pipeline Data Flow

```bash
# Understanding data flow
psh$ echo "Step 1" | sed 's/1/2/' | sed 's/2/3/'
Step 3

# Each command processes the full stream
psh$ seq 1 5 | grep -v 3 | sed 's/^/Number: /'
Number: 1
Number: 2
Number: 4
Number: 5
```

### Common Pipeline Patterns

```bash
# Count occurrences
psh$ cat log.txt | grep "ERROR" | wc -l
25

# Find unique values
psh$ cut -d: -f1 /etc/passwd | sort | uniq

# Top N items
psh$ cat access.log | awk '{print $1}' | sort | uniq -c | sort -rn | head -10

# Search and extract
psh$ ps aux | grep python | awk '{print $2}'

# Filter and format
psh$ df -h | grep -v tmpfs | awk '{print $5, $6}' | sort -n

# Process CSV data
psh$ cat data.csv | cut -d, -f2,4 | sort | uniq
```

## 10.2 Control Structures in Pipelines

PSH supports control structures as pipeline components, enabling advanced data processing patterns where loops, conditionals, and case statements can appear in pipelines.

### While Loops in Pipelines

```bash
# Process data line by line through a pipeline
psh$ echo -e "apple\nbanana\ncherry" | while read fruit; do
>     echo "Processing fruit: $fruit (length: ${#fruit})"
> done
Processing fruit: apple (length: 5)
Processing fruit: banana (length: 6)
Processing fruit: cherry (length: 6)

# Count and process sequential data
psh$ seq 1 5 | while read num; do
>     echo "Number $num squared is $((num * num))"
> done
Number 1 squared is 1
Number 2 squared is 4
Number 3 squared is 9
Number 4 squared is 16
Number 5 squared is 25

# Data transformation in pipeline
psh$ echo "user:alice:1001" | while IFS=: read type name id; do
>     echo "Type: $type, Name: $name, ID: $id"
> done
Type: user, Name: alice, ID: 1001
```

### For Loops in Pipelines

```bash
# For loop as pipeline component
psh$ echo "processing data" | for item in alpha beta gamma; do
>     echo "Item: $item"
> done
Item: alpha
Item: beta
Item: gamma

# Dynamic for loop with command substitution
psh$ seq 1 3 | for i in $(cat); do
>     echo "Processing number: $i"
> done
Processing number: 1
Processing number: 2
Processing number: 3
```

### If Statements in Pipelines

```bash
# Conditional processing based on pipeline input
psh$ echo "success" | if grep -q "success"; then
>     echo "Success detected in pipeline"
> else
>     echo "Success not found"
> fi
Success detected in pipeline
```

### Case Statements in Pipelines

```bash
# Pattern matching on pipeline input
psh$ echo "apple" | case $(cat) in
>     apple)  echo "Found an apple" ;;
>     banana) echo "Found a banana" ;;
>     *)      echo "Unknown fruit" ;;
> esac
Found an apple
```

### Technical Notes

Control structures run in isolated subshells when used as pipeline components. This means variable modifications inside the pipeline component do not affect the parent shell -- the same behavior as in bash.

## 10.3 Pipeline Exit Status

The exit status of a pipeline is the exit status of the last command:

```bash
# Successful pipeline
psh$ echo "test" | grep "test" | wc -l
1
psh$ echo $?
0

# Failed command in middle
psh$ echo "test" | grep "nomatch" | wc -l
0
psh$ echo $?
0  # Exit status from wc, not grep!

# Failed last command
psh$ echo "test" | cat | false
psh$ echo $?
1
```

### pipefail Option

PSH supports the `pipefail` option, which causes a pipeline to return the exit status of the rightmost command that failed (rather than always returning the status of the last command):

```bash
# Without pipefail (default)
psh$ false | echo "test"
test
psh$ echo $?
0  # Exit status from echo

# With pipefail
psh$ set -o pipefail
psh$ false | echo "test"
test
psh$ echo $?
1  # Exit status from false (the failed command)

# Disable pipefail
psh$ set +o pipefail
```

The `PIPESTATUS` array captures the exit status of every command in the most recent pipeline:

```bash
psh$ true | false | true
psh$ echo "${PIPESTATUS[@]}"
0 1 0
```

### Capturing Pipeline Status

```bash
# Save intermediate results
psh$ ls | tee filelist.txt | wc -l
42

# Check specific command status using process substitution
psh$ if echo "test" | grep "test" > /dev/null; then
>     echo "Found"
> fi
Found

# Complex pipeline error handling
process_data() {
    local input="$1"
    local temp=$(mktemp)

    if cat "$input" | sort | uniq > "$temp"; then
        mv "$temp" "$input.processed"
        echo "Success"
    else
        rm -f "$temp"
        echo "Failed"
        return 1
    fi
}
```

## 10.4 Conditional Execution

### AND Lists (&&)

Execute the next command only if the previous succeeds:

```bash
# Basic AND list
psh$ mkdir newdir && cd newdir
# cd only runs if mkdir succeeds

# Multiple commands
psh$ cd /tmp && touch file.txt && echo "Created file"
Created file

# Conditional execution
psh$ [ -f config.txt ] && echo "Config exists"
Config exists

# Build pattern
psh$ make && make test && make install

# Chain of dependencies
psh$ command1 && \
>    command2 && \
>    command3 && \
>    echo "All succeeded"
```

### OR Lists (||)

Execute the next command only if the previous fails:

```bash
# Basic OR list
psh$ cd /somedir || echo "Directory not found"
Directory not found

# Fallback commands
psh$ wget file.txt || curl -O file.txt || echo "Download failed"

# Default values
psh$ grep "pattern" file.txt || echo "Pattern not found"

# Create if missing
psh$ [ -d ~/.config ] || mkdir ~/.config

# Exit on failure
psh$ important_command || exit 1
```

### Combining && and ||

```bash
# Ternary-like operation
psh$ [ -f file.txt ] && echo "exists" || echo "not found"
exists

# But be careful with side effects!
psh$ true && false || echo "This runs"
This runs

# Because:
# 1. true succeeds, so false runs
# 2. false fails, so echo runs

# Safer pattern with if/then
psh$ if [ -f file.txt ]; then
>     echo "exists"
> else
>     echo "not found"
> fi

# Explicit grouping
psh$ { command1 && command2; } || { command3 && command4; }
```

## 10.5 Command Lists (;)

Semicolons separate commands that run sequentially regardless of exit status:

```bash
# Basic command list
psh$ echo "First"; echo "Second"; echo "Third"
First
Second
Third

# Mixed with other operators
psh$ cd /tmp; ls | wc -l; pwd
15
/tmp

# One-liners
psh$ for i in 1 2 3; do echo $i; done

# Combining with conditionals
psh$ [ -f file.txt ] && cat file.txt; echo "Done"
# echo runs regardless
```

## 10.6 Grouping Commands

### Subshells with ()

Parentheses create a subshell -- a separate environment:

```bash
# Commands in subshell
psh$ (cd /tmp; pwd)
/tmp
psh$ pwd
/home/alice  # Original directory unchanged

# Environment isolation
psh$ var=original
psh$ (var=changed; echo "In subshell: $var")
In subshell: changed
psh$ echo "In parent: $var"
In parent: original

# Combine outputs
psh$ (echo "Header"; date; echo "Footer") > report.txt

# Parallel execution
psh$ (sleep 2; echo "Task 1") &
psh$ (sleep 1; echo "Task 2") &
psh$ wait
Task 2
Task 1

# Pipeline with subshell
psh$ (cat file1; cat file2) | sort | uniq
```

### Command Groups with {}

Braces group commands without creating a subshell:

```bash
# Commands in current shell
psh$ { echo "Start"; date; echo "End"; }
Start
Fri Feb 14 10:00:00 PST 2026
End

# Note: spaces and semicolon/newline required
psh$ {echo "bad"}      # Error - needs space
psh$ { echo "good"; }  # Correct

# Affect current environment
psh$ var=original
psh$ { var=changed; echo "In group: $var"; }
In group: changed
psh$ echo "After group: $var"
After group: changed

# Redirect group output
psh$ {
>     echo "Line 1"
>     echo "Line 2"
>     echo "Line 3"
> } > output.txt

# Error handling for groups
psh$ {
>     command1 &&
>     command2 &&
>     command3
> } || echo "Group failed"
```

## Pipeline Negation and |&

PSH supports two more bash pipeline forms:

```bash
# ! inverts the exit status of a pipeline
psh$ ! false
psh$ echo $?
0
psh$ if ! grep -q "error" logfile.txt; then
>     echo "No errors found"
> fi

# |& pipes both stdout and stderr (shorthand for 2>&1 |)
psh$ ls /nonexistent |& wc -l
       1
```

## Practical Examples

### Log Analysis Pipeline

```bash
#!/usr/bin/env psh
# Analyze web server logs with pipelines

analyze_logs() {
    local logfile="$1"

    echo "=== Log Analysis for $logfile ==="
    echo

    # Top IP addresses
    echo "Top 10 IP Addresses:"
    grep "." "$logfile" | \
        awk '{print $1}' | \
        sort | \
        uniq -c | \
        sort -rn | \
        head -10 | \
        awk '{printf "%5d %s\n", $1, $2}'
    echo

    # Response code distribution
    echo "HTTP Response Codes:"
    grep "." "$logfile" | \
        awk '{print $9}' | \
        grep '^[0-9]' | \
        sort | \
        uniq -c | \
        sort -rn | \
        awk '{printf "%5d %s\n", $1, $2}'
    echo

    # Top requested URLs
    echo "Top 10 Requested URLs:"
    grep "." "$logfile" | \
        awk '$6 == "\"GET" {print $7}' | \
        sort | \
        uniq -c | \
        sort -rn | \
        head -10 | \
        awk '{printf "%5d %s\n", $1, $2}'
}

# Usage
analyze_logs access.log
```

### Build System Pipeline

```bash
#!/usr/bin/env psh
# Build system with conditional execution

BUILD_DIR="build"
JOBS=$(nproc 2>/dev/null || echo 4)

clean() {
    echo "Cleaning build directory..."
    rm -rf "$BUILD_DIR" && echo "Clean successful" || return 1
}

configure() {
    echo "Configuring build..."
    mkdir -p "$BUILD_DIR" && \
    cd "$BUILD_DIR" && \
    cmake .. && \
    echo "Configuration successful" || \
    { echo "Configuration failed" >&2; return 1; }
}

build() {
    echo "Building project..."
    cd "$BUILD_DIR" && \
    make -j"$JOBS" 2>&1 | \
    tee build.log | \
    grep -E "^\[|error:|warning:" || true
}

# Main build pipeline with conditional execution
full_build() {
    clean && \
    configure && \
    build && \
    echo "Build pipeline completed successfully"
}

# Usage
case "${1:-build}" in
    clean)     clean ;;
    configure) configure ;;
    build)     configure && build ;;
    full)      full_build ;;
    *)         echo "Usage: $0 {clean|configure|build|full}" ;;
esac
```

## Common Pipeline Patterns

### Performance Optimization

```bash
# Avoid useless use of cat
# Bad:
cat file | grep pattern

# Good:
grep pattern file

# Minimize pipeline stages
# Bad:
cat file | grep pattern | awk '{print $1}' | sort | uniq

# Good:
awk '/pattern/ {print $1}' file | sort -u

# Use appropriate tools
# Bad:
grep pattern file | wc -l

# Good:
grep -c pattern file
```

## Summary

Pipelines and command lists provide powerful ways to combine commands:

1. **Pipelines** (`|`) connect command output to input
2. **AND lists** (`&&`) run commands conditionally on success
3. **OR lists** (`||`) run commands conditionally on failure
4. **Command lists** (`;`) run commands sequentially
5. **Subshells** (`()`) provide environment isolation
6. **Command groups** (`{}`) group without subshells
7. **pipefail** (`set -o pipefail`) detects failures in any pipeline stage
8. **Control structures in pipelines** enable while, for, if, and case as pipeline components

Key concepts:
- Pipeline exit status is from the last command (unless `pipefail` is set)
- Data flows left to right through pipes
- && and || short-circuit evaluation
- Subshells isolate environment changes
- Command groups affect the current shell
- Control structures run in subshells when used in pipelines

Mastering pipelines enables you to build complex data processing workflows from simple commands. In the next chapter, we'll explore control structures for conditional execution and loops.

---

[← Previous: Chapter 9 - Input/Output Redirection](09_io_redirection.md) | [Next: Chapter 11 - Control Structures →](11_control_structures.md)
