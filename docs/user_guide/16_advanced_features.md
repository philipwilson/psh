# Chapter 16: Advanced Features

PSH includes several advanced features that provide powerful capabilities for complex scripting and interactive use. These features extend the shell's functionality beyond basic command execution, offering sophisticated text processing, debugging tools, and enhanced control structures.

## 16.1 Control Structures in Pipelines

PSH supports using control structures as pipeline components.

### Overview

This feature enables advanced data processing patterns by allowing all control structures (while, for, if, case, select, arithmetic commands) to be used as components within pipelines. Each control structure runs in an isolated subshell when used in a pipeline, ensuring proper process isolation and data flow.

### Supported Control Structures

```bash
# While loops in pipelines
psh$ echo -e "1\n2\n3" | while read num; do
>     echo "Processing: $num"
> done

# For loops in pipelines  
psh$ echo "input" | for item in a b c; do
>     echo "Item: $item"
> done

# If statements in pipelines
psh$ echo "test" | if grep -q "test"; then
>     echo "Found match"
> fi

# Case statements in pipelines
psh$ echo "apple" | case $(cat) in
>     apple) echo "It's an apple!" ;;
>     *) echo "Unknown fruit" ;;
> esac

# Arithmetic commands in pipelines
psh$ echo "42" | if (($(cat) > 40)); then
>     echo "Greater than 40"
> fi

# Select statements in pipelines (interactive)
psh$ echo -e "option1\noption2" | select choice in $(cat); do
>     echo "Selected: $choice"
>     break
> done
```

### Advanced Pipeline Patterns

```bash
# Complex nested control structures
psh$ seq 1 3 | while read outer; do
>     echo "Group $outer:"
>     echo "  x y z" | for inner in a b c; do
>         echo "    $outer-$inner"
>     done
> done

# Multi-stage data processing pipeline
psh$ cat data.csv | while IFS=, read id name value; do
>     echo "$id,$name,$value" | if [ $(echo "$value" | wc -c) -gt 5 ]; then
>         echo "Long value: $name has value '$value'"
>     fi
> done

# Conditional data transformation
psh$ echo -e "admin\nuser\nguest" | while read role; do
>     echo "$role" | case $(cat) in
>         admin) echo "👑 Administrator: $role" ;;
>         user)  echo "👤 Regular user: $role" ;;
>         *)     echo "❓ Other role: $role" ;;
>     esac
> done

# Pipeline validation and error handling  
psh$ echo "critical-data" | if [ -n "$(cat)" ]; then
>     echo "Data received: $(cat)"
> else
>     echo "Error: No data in pipeline" >&2
>     exit 1
> fi
```

### Technical Implementation

- **Unified Command Model**: Control structures implement the `Command` interface
- **Subshell Execution**: Each control structure runs in an isolated subshell
- **Process Isolation**: Variables and environment changes don't affect parent shell
- **Full Compatibility**: All existing pipeline functionality remains unchanged
- **I/O Redirection**: Control structures support all redirection operators

### Benefits

1. **Enhanced Data Processing**: Create sophisticated data transformation pipelines
2. **Improved Script Organization**: More intuitive and readable pipeline logic
3. **Increased Composability**: Mix control structures with traditional commands seamlessly
4. **Backward Compatibility**: No changes to existing scripts required

For detailed examples and patterns, see [Chapter 10: Pipelines and Lists](10_pipelines_and_lists.md#102-control-structures-in-pipelines-v0370).

## 16.2 Process Substitution

Process substitution allows you to treat the output of a command as a file, enabling powerful command combinations that would otherwise require temporary files.

### Input Process Substitution <()

```bash
# Basic syntax: <(command)
# Creates a file descriptor that provides command's output

# Compare directory listings
psh$ diff <(ls dir1) <(ls dir2)
< file1.txt
> file3.txt

# Compare sorted versions without temp files
psh$ diff <(sort file1.txt) <(sort file2.txt)

# Multiple process substitutions
psh$ paste <(cut -f1 data.csv) <(cut -f3 data.csv) <(cut -f5 data.csv)

# Process substitution with comm
psh$ comm -12 <(sort list1.txt | uniq) <(sort list2.txt | uniq)
# Shows lines common to both lists

# Use with while loops
psh$ while IFS= read -r line; do
>     echo "Processing: $line"
> done < <(find . -name "*.txt")
```

### Output Process Substitution >()

```bash
# Basic syntax: >(command)
# Creates a file descriptor that sends data to command's input

# Split output to multiple processors
psh$ echo "test data" | tee >(grep pattern1) >(grep pattern2)

# Log filtering to different files
psh$ tail -f app.log | tee \
>     >(grep ERROR > errors.log) \
>     >(grep WARN > warnings.log) \
>     >(grep INFO > info.log)

# Process and save simultaneously
psh$ some_command | tee >(gzip > output.gz) | grep important

# Multiple transformations
psh$ cat data.txt | tee \
>     >(sed 's/old/new/g' > modified.txt) \
>     >(tr '[:lower:]' '[:upper:]' > uppercase.txt) \
>     >(awk '{print $1}' > firstcol.txt)
```

### Advanced Process Substitution Examples

```bash
# Complex diff with preprocessing
psh$ diff \
>     <(grep -v '^#' config1.conf | sort) \
>     <(grep -v '^#' config2.conf | sort)

# Join on processed data
psh$ join \
>     <(sort -k1,1 file1.txt) \
>     <(sort -k1,1 file2.txt)

# Real-time log analysis
psh$ paste \
>     <(tail -f access.log | awk '{print $1}') \
>     <(tail -f access.log | awk '{print $7}')

# Compare command outputs
psh$ diff \
>     <(cd /old/project && find . -type f -exec md5sum {} \;) \
>     <(cd /new/project && find . -type f -exec md5sum {} \;)

# Process substitution in functions
compare_dirs() {
    local dir1="$1"
    local dir2="$2"
    diff <(cd "$dir1" && find . | sort) \
         <(cd "$dir2" && find . | sort)
}
```

### Process Substitution Internals

```bash
# View the file descriptor
psh$ echo <(echo hello)
/dev/fd/63

# Multiple process substitutions get different FDs
psh$ echo <(echo one) <(echo two) <(echo three)
/dev/fd/63 /dev/fd/62 /dev/fd/61

# Read from process substitution via redirection
psh$ read line < <(echo hello)
psh$ echo $line
hello
```

## 16.3 Enhanced Test Operators [[ ]]

The `[[ ]]` construct provides enhanced testing capabilities with better syntax and additional operators compared to the traditional `[` command.

### String Comparison Enhancements

```bash
# Lexicographic comparison (not in [ ])
psh$ [[ "apple" < "banana" ]] && echo "apple comes first"
apple comes first

psh$ [[ "zebra" > "ant" ]] && echo "zebra comes after"
zebra comes after

# No word splitting inside [[ ]]
psh$ var="hello world"
psh$ [[ -n $var ]] && echo "Safe without quotes"
Safe without quotes

# Pattern matching (not regex)
psh$ [[ "hello.txt" == *.txt ]] && echo "Text file"
Text file

# Note: Extended glob patterns like @(pdf|doc) are not supported
# Use standard glob patterns instead:
psh$ [[ "document.pdf" == *.pdf ]] && echo "PDF Document"
PDF Document
```

### Regular Expression Matching

```bash
# =~ operator for regex matching
psh$ [[ "user@example.com" =~ ^[a-zA-Z0-9]+@[a-zA-Z0-9]+\.[a-zA-Z]+$ ]]
psh$ echo $?
0

# Common regex patterns
psh$ ip="192.168.1.1"
psh$ [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && echo "Valid IP format"
Valid IP format

psh$ phone="123-456-7890"
psh$ [[ "$phone" =~ ^[0-9]+-[0-9]+-[0-9]+$ ]] && echo "Phone number"
Phone number

psh$ file="script.sh"
psh$ [[ "$file" =~ \.sh$ ]] && echo "Shell script"
Shell script
```

After a successful `=~` match, the `BASH_REMATCH` array holds the full
match in element 0 and any capture groups in elements 1, 2, and so on:

```bash
psh$ [[ "hello123" =~ ([a-z]+)([0-9]+) ]]
psh$ echo "${BASH_REMATCH[0]}"
hello123
psh$ echo "${BASH_REMATCH[1]}"
hello
psh$ echo "${BASH_REMATCH[2]}"
123
```

### Compound Conditions

```bash
# && and || inside [[ ]]
psh$ file="/etc/passwd"
psh$ [[ -f "$file" && -r "$file" ]] && echo "File exists and is readable"
File exists and is readable

psh$ [[ "$USER" == "root" || "$UID" -eq 0 ]] && echo "Running as root"

# Complex conditions
psh$ age=25
psh$ name="Alice"
psh$ [[ "$name" =~ ^[A-Z] && "$age" -ge 18 && "$age" -le 65 ]] && \
>     echo "Valid adult name"

# Negation with !
psh$ [[ ! -d "$dir" ]] && mkdir "$dir"

# Parentheses for grouping
psh$ [[ ( "$a" -eq 1 || "$b" -eq 2 ) && "$c" -eq 3 ]]
```

### [[ ]] vs [ ] Comparison

```bash
# Word splitting difference
psh$ var="hello world"
psh$ [ -n $var ]   # Error: too many arguments
psh$ [[ -n $var ]] # Works fine

# Empty variable handling
psh$ unset var
psh$ [ "$var" = "test" ]   # Works
psh$ [[ $var = "test" ]]   # Also works (safer)

# Pattern matching
psh$ [ "file.txt" == *.txt ]   # Doesn't work as expected
psh$ [[ "file.txt" == *.txt ]] # Works correctly

# Operators available in [[ ]] but not [ ]
# <, > for string comparison
# =~ for regex matching
# == with patterns
```

## 16.4 Debug and Diagnostic Features

PSH provides powerful debugging capabilities to help understand script execution and troubleshoot issues.

### AST (Abstract Syntax Tree) Debugging

```bash
# Show parsed AST before execution
psh$ psh --debug-ast -c 'echo $((2 + 3))'
=== AST ===
Pipeline:
  Command: SimpleCommand
    words: ['echo', ArithmeticExpansion(expression='2 + 3')]
    redirects: []
=== End AST ===
5

# Debug complex commands
psh$ psh --debug-ast -c 'for i in {1..3}; do echo $i; done'
=== AST ===
ForLoop:
  var: 'i'
  items: [BraceExpansion('{1..3}')]
  body: Pipeline:
    Command: SimpleCommand
      words: ['echo', Variable(name='i')]
=== End AST ===
1
2
3

# Enable AST debugging at runtime
psh$ set -o debug-ast
psh$ echo hello
=== AST ===
Pipeline:
  Command: SimpleCommand
    words: ['echo', 'hello']
    redirects: []
=== End AST ===
hello

# Disable AST debugging
psh$ set +o debug-ast
```

### Token-Level Debugging

```bash
# Show tokenization process
psh$ psh --debug-tokens -c 'echo "Hello, $USER!"'
=== Tokens ===
Token(WORD, 'echo', 1:1)
Token(STRING, '"Hello, $USER!"', 1:6)
Token(EOF, '', 1:21)
=== End Tokens ===
Hello, alice!

# Debug complex tokenization
psh$ psh --debug-tokens -c 'ls | grep -E "\.txt$" > files.txt'
=== Tokens ===
Token(WORD, 'ls', 1:1)
Token(PIPE, '|', 1:4)
Token(WORD, 'grep', 1:6)
Token(WORD, '-E', 1:11)
Token(STRING, '"\.txt$"', 1:14)
Token(REDIRECT, '>', 1:23)
Token(WORD, 'files.txt', 1:25)
Token(EOF, '', 1:34)
=== End Tokens ===

# Runtime token debugging
psh$ set -o debug-tokens
psh$ echo test
=== Tokens ===
Token(WORD, 'echo', 1:1)
Token(WORD, 'test', 1:6)
Token(EOF, '', 1:10)
=== End Tokens ===
test
```

### Variable Scope Debugging

```bash
# Debug local variable scopes
psh$ psh --debug-scopes script.sh
[SCOPE] Entering function: main
[SCOPE] Creating local variable: count
[SCOPE] Variable lookup: count (found in local scope)
[SCOPE] Exiting function: main

# Example with nested functions
psh$ cat > scope_demo.sh << 'EOF'
> outer() {
>     local x=1
>     inner() {
>         local y=2
>         echo "$x $y"
>     }
>     inner
> }
> outer
> EOF

psh$ psh --debug-scopes scope_demo.sh
[SCOPE] Entering function: outer
[SCOPE] Creating local variable: x
[SCOPE] Entering function: inner
[SCOPE] Creating local variable: y
[SCOPE] Variable lookup: x (found in parent scope)
[SCOPE] Variable lookup: y (found in local scope)
1 2
[SCOPE] Exiting function: inner
[SCOPE] Exiting function: outer
```

### Combining Debug Modes

```bash
# Multiple debug flags
psh$ psh --debug-ast --debug-tokens -c 'echo $HOME'
=== Tokens ===
Token(WORD, 'echo', 1:1)
Token(VARIABLE, '$HOME', 1:6)
Token(EOF, '', 1:11)
=== End Tokens ===
=== AST ===
Pipeline:
  Command: SimpleCommand
    words: ['echo', Variable(name='HOME')]
    redirects: []
=== End AST ===
/home/user

# All debug modes
psh$ psh --debug-ast --debug-tokens --debug-scopes script.sh

# Runtime control
psh$ set -o debug-ast
psh$ set -o debug-tokens
psh$ set -o  # Show all settings
debug-ast      on
debug-tokens   on
emacs          on
vi             off
```

## 16.5 Advanced Parameter Expansion

PSH supports sophisticated parameter expansion operations for string manipulation, including special handling for array variables.

### Length Operations

```bash
# String length
psh$ var="Hello, World!"
psh$ echo ${#var}
13

# Array element count
psh$ fruits=(apple banana cherry)
psh$ echo ${#fruits[@]}
3

# Positional parameters
psh$ set -- one two three
psh$ echo ${#}
3
psh$ echo ${#*}
3
psh$ echo ${#@}
3

# Length of specific parameter
psh$ echo ${#1}  # Length of $1
3
```

### Pattern Removal

```bash
# Remove from beginning (# and ##)
psh$ file="/path/to/file.txt"
psh$ echo ${file#*/}      # Remove first /
path/to/file.txt
psh$ echo ${file##*/}     # Remove up to last /
file.txt

# Remove from end (% and %%)
psh$ echo ${file%/*}      # Remove last /
/path/to
psh$ echo ${file%%/*}     # Remove from first /
                          # (empty)

# Practical examples
psh$ # Get file extension
psh$ filename="document.pdf"
psh$ echo ${filename##*.}
pdf

psh$ # Get filename without extension
psh$ echo ${filename%.*}
document

psh$ # Remove path and extension
psh$ fullpath="/home/user/file.tar.gz"
psh$ name=${fullpath##*/}
psh$ echo ${name%%.*}
file
```

### Pattern Substitution

```bash
# Single substitution
psh$ text="hello hello world"
psh$ echo ${text/hello/hi}
hi hello world

# Global substitution
psh$ echo ${text//hello/hi}
hi hi world

# Anchored substitution
psh$ echo ${text/#hello/hi}    # Beginning
hi hello world
psh$ echo ${text/%world/universe}  # End
hello hello universe

# Delete pattern
psh$ echo ${text/hello/}       # Delete first
 hello world
psh$ echo ${text//hello/}      # Delete all
  world

# Complex patterns
psh$ path="/usr/local/bin"
psh$ echo ${path//\//|}        # Replace all / with |
|usr|local|bin
```

### Substring Extraction

```bash
# Basic substring
psh$ var="Hello, World!"
psh$ echo ${var:0:5}          # From 0, length 5
Hello
psh$ echo ${var:7:5}          # From 7, length 5
World

# From position to end
psh$ echo ${var:7}            # From position 7
World!

# Negative offsets
psh$ echo ${var: -6}          # Last 6 characters
World!
psh$ echo ${var: -6:5}        # From -6, length 5
World

# With parameters
psh$ set -- "Hello, World!"
psh$ echo ${1:0:5}
Hello
```

### Array-Specific Expansions

```bash
# All array elements
psh$ colors=(red green blue)
psh$ echo ${colors[@]}     # Each element as separate word
red green blue
psh$ echo ${colors[*]}     # All elements as single word (IFS-separated)
red green blue

# Array indices (useful for sparse arrays)
psh$ sparse[0]="first"
psh$ sparse[5]="middle"
psh$ sparse[9]="last"
psh$ echo ${!sparse[@]}
0 5 9

# Array slicing
psh$ letters=(a b c d e f)
psh$ echo ${letters[@]:2:3}   # Start at index 2, take 3 elements
c d e
psh$ echo ${letters[@]: -2}   # Last 2 elements
e f

# Apply expansions to all elements
psh$ files=(doc.txt image.txt data.txt)
psh$ echo ${files[@]%.txt}    # Remove .txt from all
doc image data
psh$ echo ${files[@]/.txt/.bak}  # Replace in all
doc.bak image.bak data.bak

# Case modification on array elements
psh$ names=(alice bob charlie)
psh$ echo ${names[@]^}        # Capitalize first letter
Alice Bob Charlie
psh$ echo ${names[@]^^}       # All uppercase
ALICE BOB CHARLIE
```

### Case Modification

```bash
# First character uppercase
psh$ name="alice"
psh$ echo ${name^}
Alice

# All uppercase
psh$ echo ${name^^}
ALICE

# First character lowercase
psh$ NAME="ALICE"
psh$ echo ${NAME,}
aLICE

# All lowercase
psh$ echo ${NAME,,}
alice

# Pattern-based case modification
psh$ text="hello world"
psh$ echo ${text^[hw]}        # Uppercase h or w
Hello world
psh$ echo ${text^^[aeiou]}    # Uppercase vowels
hEllO wOrld
```

### Variable Name Matching

`${!prefix*}` and `${!prefix@}` expand to the names of all shell
variables beginning with `prefix`:

```bash
psh$ MYAPP_HOST=localhost
psh$ MYAPP_PORT=8080
psh$ echo "${!MYAPP_*}"
MYAPP_HOST MYAPP_PORT
```

> **Note:** Unlike bash, PSH's quoted `"${!prefix@}"` form expands to a
> single word rather than one word per variable name. Use the unquoted
> form (or `${!prefix*}`) when iterating over the names.

## 16.6 Arithmetic Commands

The `(( ))` construct provides arithmetic evaluation with conditional exit status.

### Basic Arithmetic Commands

```bash
# Arithmetic evaluation
psh$ ((5 + 3))
psh$ echo $?
0              # Non-zero result gives exit status 0

psh$ ((5 - 5))
psh$ echo $?
1              # Zero result gives exit status 1

# Variable assignment
psh$ ((x = 10))
psh$ echo $x
10

psh$ ((x++))
psh$ echo $x
11

# Multiple expressions
psh$ ((a = 5, b = 10, c = a + b))
psh$ echo $c
15
```

### Arithmetic Conditionals

```bash
# In if statements
psh$ x=10
psh$ if ((x > 5)); then
>     echo "x is greater than 5"
> fi
x is greater than 5

# Complex conditions
psh$ if ((x > 0 && x < 20)); then
>     echo "x is between 0 and 20"
> fi

# Arithmetic in while loops
psh$ i=0
psh$ while ((i < 5)); do
>     echo $i
>     ((i++))
> done
0
1
2
3
4

# Ternary operator
psh$ ((result = x > 10 ? 1 : 0))
psh$ echo $result
0
```

### C-Style For Loops

```bash
# Basic C-style for loop
psh$ for ((i=0; i<5; i++)); do
>     echo "Iteration $i"
> done
Iteration 0
Iteration 1
Iteration 2
Iteration 3
Iteration 4

# Multiple variables
psh$ for ((i=0, j=10; i<5; i++, j--)); do
>     echo "i=$i, j=$j"
> done
i=0, j=10
i=1, j=9
i=2, j=8
i=3, j=7
i=4, j=6

# Empty sections
psh$ i=0
psh$ for ((; i<3; i++)); do
>     echo $i
> done

# Infinite loop (use with care)
psh$ for ((;;)); do
>     read -p "Enter 'quit' to exit: " input
>     [[ "$input" == "quit" ]] && break
> done
```

## 16.7 Advanced I/O Features

### Advanced Redirections

```bash
# Multiple redirections
psh$ command < input.txt > output.txt 2> error.txt

# Redirect specific file descriptors
psh$ exec 3< input.txt     # Open FD 3 for reading
psh$ exec 4> output.txt    # Open FD 4 for writing
psh$ read -u 3 line        # Read from FD 3
psh$ echo "data" >&4       # Write to FD 4
psh$ exec 3<&-             # Close FD 3
psh$ exec 4>&-             # Close FD 4

# Here documents with suppressed tabs
psh$ cat <<-EOF
>     This line has tabs
>     They are removed
> EOF
This line has tabs
They are removed

# Here strings
psh$ grep "pattern" <<< "test pattern string"
test pattern string
```

### Advanced Read Options

```bash
# Read with prompt (interactive mode)
psh$ read -p "Enter your name: " name
Enter your name: Alice
psh$ echo "Hello, $name"
Hello, Alice

# Raw mode (no backslash processing)
psh$ read -r var <<< "hello\world"
psh$ echo "$var"
hello\world

# Custom delimiter
psh$ read -d ':' var <<< "hello:world"
psh$ echo "$var"
hello

# Read from file redirection
psh$ echo "data" > file.txt
psh$ read var < file.txt
psh$ echo "$var"
data

# Read from process substitution
psh$ read var < <(echo "hello")
psh$ echo "$var"
hello
```

> **Note:** PSH supports `read -n` (character count), `read -t`
> (timeout), and `read -s` (silent). The `read -u fd` (read from a
> file descriptor) option is not supported — duplicate the descriptor
> onto stdin instead: `read line <&3`.

## 16.8 Advanced Shell Options and Debugging

### Runtime Configuration

```bash
# View all options
psh$ set -o
allexport      	off
braceexpand    	on
emacs          	on
errexit        	off
histexpand     	on
ignoreeof      	off
monitor        	off
noclobber      	off
noexec         	off
noglob         	off
nolog          	off
notify         	off
nounset        	off
pipefail       	off
posix          	off
verbose        	off
vi             	off
xtrace         	off

# Enable shell options
psh$ set -e              # Exit on error (errexit)
psh$ set -u              # Error on undefined variables (nounset)
psh$ set -x              # Print commands before execution (xtrace)
psh$ set -o pipefail     # Pipeline fails if any command fails
psh$ set -o noclobber    # Prevent file overwriting with >
psh$ set -o allexport    # Export all variables on assignment

# Enable debug options via set -o
psh$ set -o debug-expansion        # Expansion debugging
psh$ set -o debug-exec             # Execution debugging
psh$ set -o debug-parser           # Parser debugging

# Or use command-line flags for full debug output
psh$ psh --debug-ast -c 'echo hello'
psh$ psh --debug-tokens -c 'echo hello'

# Disable options
psh$ set +e              # Disable errexit
psh$ set +o debug-expansion

# Combine options
psh$ set -eux            # Enable errexit, nounset, xtrace
psh$ set -eu -o pipefail # Strict mode
```

### Advanced Debugging Techniques

```bash
# Debug variable expansion in real-time
psh$ set -o debug-expansion
psh$ VAR="hello"
psh$ echo ${VAR^^}
[EXPANSION] Expanding Word AST command: ['echo', '${VAR^^}']
[EXPANSION] Word AST Result: ['echo', 'HELLO']
HELLO

# Use command-line flags for AST and token debugging
psh$ psh --debug-ast -c 'echo hello'
=== AST Debug Output (recursive_descent) ===
... StatementList -> AndOrList -> Pipeline -> SimpleCommand ...
======================
hello

psh$ psh --debug-tokens -c 'echo hello'
=== Token Debug Output ===
  [  0] WORD                 'echo'
  [  1] WORD                 'hello'
  [  2] EOF                  ''
========================
hello

# Combine xtrace with expansion debugging
psh$ set -x -o debug-expansion
psh$ FILE="test.txt"
+ FILE=test.txt
psh$ echo $FILE
[EXPANSION] Expanding Word AST command: ['echo', '$FILE']
[EXPANSION] Word AST Result: ['echo', 'test.txt']
+ echo test.txt
test.txt

# Debug function for specific commands
psh$ debug_cmd() {
>     set -o debug-expansion
>     "$@"
>     set +o debug-expansion
> }
psh$ debug_cmd echo $HOME
[EXPANSION] Expanding Word AST command: ['echo', '/Users/user']
[EXPANSION] Word AST Result: ['echo', '/Users/user']
/Users/user
```

### Advanced Prompt Features

```bash
# Conditional prompts
psh$ PS1='$(if [ $? -eq 0 ]; then echo "✓"; else echo "✗"; fi) \u@\h:\w\$ '
✓ user@host:~$ false
✗ user@host:~$ true
✓ user@host:~$ 

# Git branch in prompt
psh$ git_branch() {
>     git branch 2>/dev/null | grep '^*' | sed 's/* //'
> }
psh$ PS1='\u@\h:\w$(git_branch)\$ '
user@host:~/project(main)$ 

# Dynamic color based on exit status
psh$ PS1='$(if [ $? -eq 0 ]; then
>     echo "\[\e[32m\]✓\[\e[0m\]"
> else
>     echo "\[\e[31m\]✗\[\e[0m\]"
> fi) \u@\h:\w\$ '

# Command timer in prompt
psh$ SECONDS=0
psh$ PS1='[$SECONDS] \u@\h:\w\$ '
[0] user@host:~$ sleep 2
[2] user@host:~$ 
```

## 16.9 Advanced Scripting Patterns

### Error Handling Patterns

```bash
#!/usr/bin/env psh

# Error handler
error_handler() {
    local exit_code=$1
    echo "Error: Command exited with status $exit_code" >&2
    exit $exit_code
}

# Wrapper for safe execution
safe_exec() {
    "$@" || error_handler $?
}

# Usage
safe_exec cd /nonexistent
safe_exec rm important_file
```

### Parallel Execution

```bash
# Run commands in parallel
psh$ for file in *.txt; do
>     process_file "$file" &
> done
> wait  # Wait for all background jobs

# Note: wait -n is not supported in PSH.
# Use wait (all jobs) or wait with specific PIDs:
psh$ cmd1 &
psh$ pid1=$!
psh$ cmd2 &
psh$ pid2=$!
psh$ wait $pid1 $pid2
```

### Advanced Function Patterns

```bash
# Function with named parameters
psh$ function parse_args() {
>     local name=""
>     local age=""
>     local city=""
>     
>     while [[ $# -gt 0 ]]; do
>         case "$1" in
>             --name=*) name="${1#*=}"; shift ;;
>             --age=*) age="${1#*=}"; shift ;;
>             --city=*) city="${1#*=}"; shift ;;
>             *) echo "Unknown option: $1" >&2; return 1 ;;
>         esac
>     done
>     
>     echo "Name: $name, Age: $age, City: $city"
> }

psh$ parse_args --name=Alice --age=30 --city="New York"
Name: Alice, Age: 30, City: New York

# Recursive directory processor
psh$ process_tree() {
>     local dir="${1:-.}"
>     local indent="${2:-}"
>     
>     echo "${indent}Processing: $dir"
>     
>     for item in "$dir"/*; do
>         [ -e "$item" ] || continue
>         
>         if [ -d "$item" ]; then
>             process_tree "$item" "$indent  "
>         else
>             echo "$indent  File: ${item##*/}"
>         fi
>     done
> }
```

### Dynamic Command Execution with eval

The `eval` builtin enables sophisticated dynamic programming patterns where commands are built and executed at runtime.

```bash
# Configuration-driven command execution
psh$ config_action() {
>     local config_file="$1"
>     
>     # Read command from config file
>     while IFS='=' read -r key value; do
>         case "$key" in
>             action) action_cmd="$value" ;;
>             target) target_path="$value" ;;
>             options) cmd_options="$value" ;;
>         esac
>     done < "$config_file"
>     
>     # Build and execute command safely
>     if [[ "$action_cmd" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
>         eval "$action_cmd $cmd_options '$target_path'"
>     else
>         echo "Invalid action command" >&2
>         return 1
>     fi
> }

# Dynamic variable handling
psh$ setup_environment() {
>     local env_prefix="$1"
>     shift
>     
>     # Set multiple environment variables dynamically
>     for var in "$@"; do
>         IFS='=' read -r name value <<< "$var"
>         eval "${env_prefix}_${name}='$value'"
>     done
>     
>     # Display all variables with prefix
>     for var in "$@"; do
>         IFS='=' read -r name value <<< "$var"
>         eval "echo \"${env_prefix}_${name}=\$${env_prefix}_${name}\""
>     done
> }

psh$ setup_environment "DB" "HOST=localhost" "PORT=5432" "NAME=myapp"
DB_HOST=localhost
DB_PORT=5432
DB_NAME=myapp

# Command dispatch table
psh$ declare -A commands=(
>     ["start"]="systemctl start"
>     ["stop"]="systemctl stop"
>     ["restart"]="systemctl restart"
>     ["status"]="systemctl status"
> )

psh$ service_control() {
>     local action="$1"
>     local service="$2"
>     
>     if [[ -n "${commands[$action]}" ]]; then
>         eval "${commands[$action]} '$service'"
>     else
>         echo "Unknown action: $action" >&2
>         echo "Available: ${!commands[*]}" >&2
>         return 1
>     fi
> }

# Template-based script generation
psh$ generate_script() {
>     local template="$1"
>     local output="$2"
>     shift 2
>     
>     # Replace placeholders with values
>     local content
>     content=$(cat "$template")
>     
>     for replacement in "$@"; do
>         IFS='=' read -r placeholder value <<< "$replacement"
>         content="${content//\{\{$placeholder\}\}/$value}"
>     done
>     
>     # Execute generated content
>     eval "$content" > "$output"
> }

# Dynamic function creation
psh$ create_accessor() {
>     local prefix="$1"
>     shift
>     
>     for field in "$@"; do
>         eval "get_${prefix}_${field}() { echo \"\$${prefix}_${field}\"; }"
>         eval "set_${prefix}_${field}() { ${prefix}_${field}=\"\$1\"; }"
>     done
> }

psh$ create_accessor "user" "name" "email" "age"
psh$ set_user_name "Alice"
psh$ set_user_email "alice@example.com"
psh$ get_user_name
Alice
psh$ get_user_email
alice@example.com
```

**Security Best Practices for eval:**
```bash
# Input validation patterns
psh$ safe_eval() {
>     local cmd="$1"
>     
>     # Whitelist approach
>     case "$cmd" in
>         "ls -la"|"pwd"|"date"|"whoami")
>             eval "$cmd"
>             ;;
>         *)
>             echo "Command not permitted: $cmd" >&2
>             return 1
>             ;;
>     esac
> }

# Parameter validation
psh$ validate_and_eval() {
>     local template="$1"
>     local param="$2"
>     
>     # Validate parameter format
>     if [[ "$param" =~ ^[a-zA-Z0-9._/-]+$ ]]; then
>         eval "printf '$template' '$param'"
>     else
>         echo "Invalid parameter format" >&2
>         return 1
>     fi
> }
```

## 16.10 Integration with External Tools

### Advanced Pipeline Patterns

```bash
# Complex data processing pipeline
psh$ cat access.log | \
>     grep -v "bot" | \
>     awk '{print $1, $7}' | \
>     sort | \
>     uniq -c | \
>     sort -rn | \
>     head -20 | \
>     while read count ip url; do
>         printf "%6d %-15s %s\n" "$count" "$ip" "$url"
>     done

# Parallel processing with xargs (when available)
psh$ find . -name "*.jpg" -print0 | \
>     xargs -0 -P 4 -I {} convert {} -resize 800x600 small/{}

# Stream processing with continuous output
psh$ tail -f application.log | \
>     while IFS= read -r line; do
>         if [[ "$line" =~ ERROR ]]; then
>             echo "$(date): $line" >> errors.log
>             send_alert "$line"
>         fi
>     done
```

## 16.11 Performance Optimization

### Efficient Shell Patterns

```bash
# Avoid command substitution in loops
# Bad:
psh$ for file in $(ls *.txt); do
>     process "$file"
> done

# Good:
psh$ for file in *.txt; do
>     [ -e "$file" ] || continue
>     process "$file"
> done

# Minimize subshells
# Bad:
psh$ result=$(echo "$string" | tr '[:lower:]' '[:upper:]')

# Good:
psh$ result=${string^^}  # Using parameter expansion

# Batch operations
# Bad:
psh$ for i in {1..1000}; do
>     echo "$i" >> output.txt
> done

# Good:
psh$ for i in {1..1000}; do
>     echo "$i"
> done > output.txt

# Read files efficiently
# Bad:
psh$ while read line; do
>     process "$line"
> done < <(cat file.txt)

# Good:
psh$ while IFS= read -r line; do
>     process "$line"
> done < file.txt
```

## Summary

PSH's advanced features provide powerful capabilities for complex shell programming:

1. **Process Substitution**: `<()` and `>()` for treating command output as files
2. **Enhanced Test Operators**: `[[ ]]` with regex matching and better syntax
3. **Debug Features**: AST, token, and scope debugging for troubleshooting
4. **Advanced Parameter Expansion**: String manipulation without external commands
5. **Arithmetic Commands**: `(( ))` for C-style arithmetic and conditionals
6. **Advanced I/O**: File descriptors, here documents, advanced read options
7. **Shell Options**: Runtime configuration and debugging controls
8. **Advanced Patterns**: Error handling, parallel execution, complex functions
9. **External Integration**: Sophisticated pipeline and tool integration
10. **Performance**: Optimization techniques for efficient scripts

Key concepts:
- Process substitution eliminates temporary files
- Enhanced test operators provide safer, more powerful conditionals
- Debug features help understand script execution
- Parameter expansion reduces dependency on external commands
- Arithmetic commands enable C-style programming constructs
- Advanced patterns solve complex real-world problems
- Performance optimization makes scripts more efficient

These advanced features make PSH a sophisticated shell implementation suitable for complex scripting tasks while maintaining clarity for educational purposes.

---

[Previous: Chapter 15 - Job Control](15_job_control.md) | [Next: Chapter 17 - Differences from Bash](17_differences_from_bash.md)