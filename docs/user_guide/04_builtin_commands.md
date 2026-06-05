# Chapter 4: Built-in Commands

Built-in commands are implemented directly within PSH rather than as external programs. They execute faster and have direct access to the shell's internal state, making them essential for shell operation.

## 4.1 Core Built-ins

These fundamental built-ins control the shell itself.

### exit - Exit the Shell

The `exit` command terminates the current shell session:

```bash
# Exit with success status
psh$ exit
$ # Back to parent shell

# Exit with specific status code
psh$ exit 0    # Success
psh$ exit 1    # General error
psh$ exit 127  # Command not found

# Exit status in scripts
psh$ cat > check_and_exit.sh << 'EOF'
#!/usr/bin/env psh
if [ ! -f required.txt ]; then
    echo "Error: required.txt not found"
    exit 1
fi
echo "File found, continuing..."
exit 0
EOF
```

### : (colon) - Null Command

The `:` command does nothing but always returns success (0):

```bash
# Basic usage
psh$ :
psh$ echo $?
0

# Useful for infinite loops
psh$ while :; do
>     echo "Press Ctrl-C to stop"
>     sleep 1
> done

# Placeholder in conditionals
psh$ if [ -f file.txt ]; then
>     :  # TODO: Add file processing here
> else
>     echo "File not found"
> fi

# Parameter expansion side effects
psh$ : ${VAR:=default}  # Set VAR to default if unset
psh$ echo $VAR
default
```

### true and false - Boolean Commands

These commands return fixed exit statuses:

```bash
# true always succeeds
psh$ true
psh$ echo $?
0

# false always fails
psh$ false
psh$ echo $?
1

# Useful in conditionals
psh$ if true; then echo "Always runs"; fi
Always runs

psh$ if false; then echo "Never runs"; fi

# Testing logic
psh$ true && echo "Success" || echo "Failure"
Success

psh$ false && echo "Success" || echo "Failure"
Failure

# Infinite loops
psh$ while true; do
>     # Your code here
>     break  # Need explicit break
> done
```

## 4.2 Directory Navigation

### cd - Change Directory

Navigate through the filesystem:

```bash
# Change to specific directory
psh$ cd /tmp
psh$ pwd
/tmp

# Go to home directory
psh$ cd
psh$ pwd
/home/alice

# Also with ~
psh$ cd ~
psh$ pwd
/home/alice

# Previous directory
psh$ cd /tmp
psh$ cd /var
psh$ cd -
/tmp
psh$ pwd
/tmp

# Relative paths
psh$ cd ..        # Parent directory
psh$ cd ../..     # Two levels up
psh$ cd ./subdir  # Subdirectory

# Following symlinks
psh$ ln -s /tmp mylink
psh$ cd mylink
psh$ pwd
/tmp
```

### pwd - Print Working Directory

Show the current directory:

```bash
# Basic usage
psh$ pwd
/home/alice

# In scripts, capture the directory
psh$ current_dir=$(pwd)
psh$ echo "We are in: $current_dir"
We are in: /home/alice
```

### pushd, popd, dirs - Directory Stack

PSH supports a directory stack for quick navigation between multiple directories:

```bash
# Push directory onto stack
psh$ pushd /tmp
/tmp ~/project

# Push another
psh$ pushd /var/log
/var/log /tmp ~/project

# Show the stack
psh$ dirs
/var/log /tmp ~/project

# Show with indices
psh$ dirs -v
 0  /var/log
 1  /tmp
 2  ~/project

# Show long format (no ~ abbreviation)
psh$ dirs -l
/var/log /tmp /home/alice/project

# Pop back to previous directory
psh$ popd
/tmp ~/project

psh$ popd
~/project

# Swap top two directories
psh$ pushd /tmp
/tmp ~/project
psh$ pushd    # No argument swaps top two
~/project /tmp

# Clear the stack
psh$ dirs -c
```

## 4.3 Environment Management

### export - Set Environment Variables

Export variables to child processes:

```bash
# Export a new variable
psh$ export MYVAR="Hello"
psh$ echo $MYVAR
Hello

# Export existing variable
psh$ NAME="Alice"
psh$ export NAME
psh$ psh -c 'echo $NAME'  # Child process sees it
Alice

# Export with assignment
psh$ export PATH="$PATH:/my/custom/bin"

# View all exported variables
psh$ export
DISPLAY=:0
HOME=/home/alice
LANG=en_US.UTF-8
MYVAR=Hello
NAME=Alice
PATH=/usr/local/bin:/usr/bin:/bin:/my/custom/bin
...

# Export multiple variables
psh$ export VAR1=value1 VAR2=value2 VAR3=value3
```

### unset - Remove Variables

Remove variables and functions:

```bash
# Unset a variable
psh$ VAR="test"
psh$ echo $VAR
test
psh$ unset VAR
psh$ echo $VAR

# Unset multiple variables
psh$ A=1 B=2 C=3
psh$ unset A B C

# Unset a function
psh$ hello() { echo "Hello!"; }
psh$ hello
Hello!
psh$ unset -f hello
psh$ hello
psh: hello: command not found

# Unset doesn't fail for non-existent variables
psh$ unset NONEXISTENT  # No error
```

### env - Display Environment

Show or modify the environment:

```bash
# Show all environment variables
psh$ env
PATH=/usr/local/bin:/usr/bin:/bin
HOME=/home/alice
USER=alice
SHELL=/usr/bin/psh
...

# Search for specific variables
psh$ env | grep HOME
HOME=/home/alice
```

### set - Shell Options and Parameters

Configure shell behavior and positional parameters:

```bash
# Show all shell variables
psh$ set
DISPLAY=:0
HOME=/home/alice
NAME=Alice
PS1=psh$
PS2=>
...

# Set positional parameters
psh$ set apple banana cherry
psh$ echo $1
apple
psh$ echo $2
banana
psh$ echo $@
apple banana cherry

# Use -- to handle arguments starting with -
psh$ set -- -x file.txt
psh$ echo $1
-x

# Show all shell options
psh$ set -o
allexport        off
braceexpand      on
emacs            on
errexit          off
histexpand       on
ignoreeof        off
monitor          off
noclobber        off
noexec           off
noglob           off
nolog            off
notify           off
nounset          off
pipefail         off
posix            off
verbose          off
vi               off
xtrace           off

# Shell option flags (short form)
psh$ set -e    # Enable errexit (exit on error)
psh$ set -u    # Enable nounset (error on undefined variables)
psh$ set -x    # Enable xtrace (print commands before execution)
psh$ set +e    # Disable errexit
psh$ set +u    # Disable nounset
psh$ set +x    # Disable xtrace

# Combine multiple options
psh$ set -eux  # Enable errexit, nounset, and xtrace
psh$ set +eux  # Disable all three

# Long form with -o
psh$ set -o errexit      # Same as set -e
psh$ set -o nounset      # Same as set -u
psh$ set -o xtrace       # Same as set -x
psh$ set -o pipefail     # Pipeline fails if any command fails
psh$ set +o errexit      # Same as set +e

# Shell Options in Detail:

# errexit (-e): Exit immediately on command failure
psh$ set -e
psh$ false
$ # Shell exits with status 1

# nounset (-u): Treat undefined variables as errors
psh$ set -u
psh$ echo $UNDEFINED_VAR
psh: psh: $UNDEFINED_VAR: unbound variable
psh$ echo ${UNDEFINED_VAR:-default}  # OK with default
default

# xtrace (-x): Print commands before execution
psh$ set -x
psh$ echo "Hello"
+ echo Hello
Hello
psh$ VAR=test
+ VAR=test
psh$ echo $VAR
+ echo test
test

# pipefail: Return rightmost non-zero exit code in pipeline
psh$ set -o pipefail
psh$ false | true
psh$ echo $?
1  # Without pipefail, would be 0

# noclobber: Prevent overwriting files with >
psh$ set -o noclobber

# allexport (-a): Automatically export all variables
psh$ set -a
```

### shopt - Shell Optional Behavior

Toggle shell options that control globbing and other behavior:

```bash
# Show all options
psh$ shopt
dotglob     off
extglob     off
globstar    off
nocaseglob  off
nullglob    off

# Enable an option
psh$ shopt -s nullglob     # Patterns with no matches expand to nothing
psh$ shopt -s globstar     # ** matches recursively
psh$ shopt -s nocaseglob   # Case-insensitive globbing
psh$ shopt -s dotglob      # Include dotfiles in globs
psh$ shopt -s extglob      # Extended pattern matching

# Disable an option
psh$ shopt -u nullglob

# Query silently (check via exit code)
psh$ shopt -q dotglob
psh$ echo $?
1  # Off

# Print in reusable format
psh$ shopt -p
shopt -u dotglob
shopt -u extglob
shopt -u globstar
shopt -u nocaseglob
shopt -u nullglob
```

### declare - Declare Variables and Functions

Declare variables with attributes, display variable values and attributes, or show function definitions:

```bash
# Show all variables
psh$ declare
DISPLAY=:0
HOME=/home/alice
MYVAR=Hello
PS1=psh$
...

# Declare variables with attributes
psh$ declare -i count=0          # Integer variable
psh$ declare -l name="ALICE"     # Lowercase variable
psh$ declare -u city="london"    # Uppercase variable
psh$ declare -r PI=3.14159       # Readonly variable
psh$ declare -x MYAPP_CONFIG     # Export to environment
psh$ declare -a fruits           # Indexed array
psh$ declare -A colors           # Associative array

# Integer variables evaluate arithmetic on assignment
psh$ declare -i calc
psh$ calc="10 * 5"
psh$ echo $calc
50

# Case transformation
psh$ echo "$name $city"
alice LONDON

# Indexed arrays
psh$ declare -a indexed_colors=(red green blue)
psh$ echo ${indexed_colors[1]}
green

# Associative arrays
psh$ declare -A assoc_colors=([primary]="red" [secondary]="blue")
psh$ echo ${assoc_colors[primary]}
red

# Show variables with attributes
psh$ declare -p count name
declare -i count="0"
declare -l name="alice"

# Remove attributes with +
psh$ declare +l name    # Remove lowercase attribute
psh$ name="ALICE"
psh$ echo $name
ALICE

# Show all function definitions with -f
psh$ declare -f
hello() {
    echo "Hello, $1!"
}
greet() {
    echo "Greetings!"
}

# Show function names only with -F
psh$ declare -F
declare -f greet
declare -f hello

# Show specific function definition
psh$ declare -f hello
hello() {
    echo "Hello, $1!"
}

# Combine multiple attributes
psh$ declare -ilx PORT=8080      # Integer, lowercase, exported
psh$ declare -ru VERSION=1.0     # Readonly, uppercase

# Attempting to modify readonly fails
psh$ PI=3.14
psh: PI: readonly variable
```

#### Variable Attributes

- **-i** : Integer - arithmetic evaluation on assignment
- **-l** : Lowercase - converts value to lowercase
- **-u** : Uppercase - converts value to uppercase
- **-r** : Readonly - cannot be modified or unset
- **-x** : Export - variable is exported to environment
- **-a** : Array - variable is an indexed array
- **-A** : Associative Array - variable is an associative array (requires explicit declaration)
- **-p** : Print - display variables with their attributes

Attributes can be combined (e.g., `-ilx` for integer, lowercase, exported) and removed with `+` prefix (e.g., `+x` to unexport).

### readonly - Make Variables Readonly

Mark variables or functions so they cannot be modified:

```bash
# Make a variable readonly
psh$ readonly PI=3.14159
psh$ echo $PI
3.14159
psh$ PI=3.14
psh: PI: readonly variable

# Make an existing variable readonly
psh$ VERSION="1.0"
psh$ readonly VERSION

# Show all readonly variables
psh$ readonly -p
declare -r PI="3.14159"
declare -r VERSION="1.0"

# Make a function readonly
psh$ greet() { echo "Hello!"; }
psh$ readonly -f greet
```

### typeset - Korn Shell Compatible Declaration

The `typeset` builtin is provided for compatibility with the Korn shell (ksh). It is exactly equivalent to `declare`:

```bash
# All declare features work identically
psh$ typeset -i num=42
psh$ typeset -f          # Show function definitions
psh$ typeset -F          # Show function names
```

## 4.4 Input/Output

### echo - Display Text

Output text with various options:

```bash
# Basic output
psh$ echo "Hello, World!"
Hello, World!

# Multiple arguments
psh$ echo Hello World
Hello World

# Without newline (-n flag)
psh$ echo -n "No newline"
No newlinepsh$

# Enable escape sequences (-e flag)
psh$ echo -e "Line 1\nLine 2\nLine 3"
Line 1
Line 2
Line 3

# Escape sequences with -e
psh$ echo -e "Tab\there"
Tab     here
psh$ echo -e "Back\bspace"
Bacspace
psh$ echo -e "\033[31mRed text\033[0m"
Red text  # (shown in red)

# Disable escapes explicitly (-E flag, default)
psh$ echo -E "No\nescapes"
No\nescapes

# Unicode support
psh$ echo -e "\u2665 \u2663 \u2660 \u2666"
...  ...

# Octal sequences
psh$ echo -e "\0101\0102\0103"
ABC

# Suppress further output with \c
psh$ echo -e "First\cThis won't appear"
First
```

### printf - Formatted Output

The `printf` builtin provides C-style formatted output:

```bash
# Basic formatting
psh$ printf "%s is %d years old\n" "Alice" 30
Alice is 30 years old

# Multiple format specifiers
psh$ printf "%-10s %5d\n" "Item" 42
Item           42

# Floating point
psh$ printf "%.2f\n" 3.14159
3.14

# Hex and octal
psh$ printf "%x %o\n" 255 255
ff 377

# Reuse format for multiple argument sets
psh$ printf "%s=%s\n" "key1" "val1" "key2" "val2"
key1=val1
key2=val2

# Escape sequences in format string
psh$ printf "Name:\t%s\nAge:\t%d\n" "Alice" 30
Name:   Alice
Age:    30

# Width and precision from arguments
psh$ printf "%*.*f\n" 10 2 3.14159
      3.14
```

### print - Display Text (zsh-compatible)

The `print` builtin is a **zsh-style extension** (it is not part of POSIX and
has no bash equivalent). Unlike `echo`, `print` interprets backslash escape
sequences **by default**; use `-r` to print arguments raw.

```bash
# Arguments are joined with spaces; escapes are interpreted by default
psh$ print 'a\tb'
a	b

# Raw output (no escape interpretation)
psh$ print -r 'a\tb'
a\tb

# One argument per line, and no trailing newline
psh$ print -l a b c
a
b
c
psh$ print -n done

# printf-style formatting
psh$ print -f '%s=%d\n' a 1 b 2
a=1
b=2

# Keep only arguments matching a pattern (first arg is the pattern)
psh$ print -m 'f*' foo far bar
foo far

# Sort arguments (ascending / descending / case-insensitive)
psh$ print -o c b a
a b c
psh$ print -i -o B a C
a B C

# Write to a specific file descriptor (e.g. stderr)
psh$ print -u2 "a warning"
```

Supported options:

| Option | Effect |
|--------|--------|
| `-n` | Do not add the trailing newline |
| `-r` | Raw: do not interpret escape sequences |
| `-R` | BSD `echo` emulation (raw); only `-e`/`-n` recognised afterwards |
| `-e` | (Re)enable escape interpretation |
| `-l` | Separate arguments with newlines instead of spaces |
| `-N` | Use a NUL byte as separator and terminator |
| `-s` | Append the arguments to the history list instead of printing |
| `-u fd` | Write to file descriptor `fd` (e.g. `-u2`) |
| `-f fmt` | Format arguments using a printf-style format string |
| `-m` | Treat the first argument as a pattern; print only matching args |
| `-o` / `-O` | Sort arguments ascending / descending |
| `-i` | With `-o`/`-O`, sort case-insensitively |
| `-P` | Perform prompt expansion (psh prompt escapes, e.g. `\h`, `\u`) |

The following zsh `print` options are **not supported** and produce an error:
`-z`, `-c`, `-C`, `-D`, `-x`, `-X`, `-a`, `-p`.

### read - Read User Input

Read input into variables with various options:

```bash
# Basic input
psh$ read name
Alice
psh$ echo "Hello, $name"
Hello, Alice

# With prompt (-p flag)
psh$ read -p "Enter your name: " name
Enter your name: Bob
psh$ echo "Hello, $name"
Hello, Bob

# Silent input for passwords (-s flag)
psh$ read -sp "Password: " pass
Password:
psh$ echo  # Add newline after silent input
psh$ echo "Got password of length ${#pass}"
Got password of length 8

# Read with timeout (-t flag)
psh$ read -t 5 -p "Quick! Enter something: " response
Quick! Enter something: # (waits 5 seconds)

# Read exact number of characters (-n flag)
psh$ read -n 4 -p "Enter 4-digit PIN: " pin
Enter 4-digit PIN: 1234psh$ echo " PIN is $pin"
 PIN is 1234

# Custom delimiter (-d flag)
psh$ read -d ':' -p "Enter data until colon: " data
Enter data until colon: hello world:psh$ echo " Got: $data"
 Got: hello world

# Raw mode - preserve backslashes (-r flag)
psh$ read -r line
C:\Users\alice\Documents
psh$ echo "$line"
C:\Users\alice\Documents

# Read into array (-a flag)
psh$ read -a words
one two three
psh$ echo "${words[1]}"
two
```

## 4.5 Job Control

### jobs - List Jobs

Show background and suspended jobs:

```bash
# Start some background jobs
psh$ sleep 100 &
[1] 12345
psh$ sleep 200 &
[2] 12346
psh$ sleep 300 &
[3] 12347

# List all jobs
psh$ jobs
[1]  Running    sleep 100 &
[2]- Running    sleep 200 &
[3]+ Running    sleep 300 &

# Suspend a foreground job
psh$ sleep 400
^Z
[4]+ Stopped    sleep 400

psh$ jobs
[1]  Running    sleep 100 &
[2]  Running    sleep 200 &
[3]- Running    sleep 300 &
[4]+ Stopped    sleep 400

# + indicates current job
# - indicates previous job
```

### fg - Foreground a Job

Bring a background or suspended job to the foreground:

```bash
# Continue the current job
psh$ fg
sleep 400
# (now waiting for sleep to finish)

# Bring specific job to foreground
psh$ fg %1
sleep 100
# (waits for job 1)

# Using job specifications
psh$ fg %+    # Current job
psh$ fg %-    # Previous job
psh$ fg %2    # Job number 2
```

### bg - Background a Job

Resume a suspended job in the background:

```bash
# Suspend a job
psh$ find / -name "*.log" 2>/dev/null
^Z
[1]+ Stopped    find / -name "*.log" 2>/dev/null

# Resume in background
psh$ bg
[1]+ find / -name "*.log" 2>/dev/null &

# Background specific job
psh$ bg %2
[2]- sleep 100 &
```

### disown - Remove Jobs from Job Table

Remove jobs from the active job table so they are not affected when the shell exits:

```bash
# Remove current job from table
psh$ sleep 1000 &
[1] 12345
psh$ disown

# Mark job to not receive SIGHUP on shell exit
psh$ sleep 2000 &
[2] 12346
psh$ disown -h %2

# Remove all jobs
psh$ disown -a

# Remove only running jobs
psh$ disown -r
```

### kill - Send Signals to Processes

Send signals to running processes or list available signals:

```bash
# Send default signal (TERM) to a process
psh$ sleep 300 &
[1] 12345
psh$ kill 12345

# Send specific signal by name
psh$ kill -KILL 12346
psh$ kill -HUP 12347
psh$ kill -INT 12348

# Send signal by number
psh$ kill -9 12349    # SIGKILL
psh$ kill -15 12350   # SIGTERM

# Using -s option
psh$ kill -s TERM 12352

# Kill jobs using job specifications
psh$ sleep 300 &
[1] 12359
psh$ kill %1          # Kill job 1
psh$ kill %+          # Kill current job

# Test if process exists (signal 0)
psh$ kill -0 12362
psh$ echo $?
0     # Process exists

# List all available signals
psh$ kill -l
1) SIGHUP       2) SIGINT       3) SIGQUIT      4) SIGILL
5) SIGTRAP      6) SIGABRT      ...

# Show signal name for exit status
psh$ kill -l 143
SIGTERM
```

#### Signal Reference

Common signals used with kill:

- **TERM (15)**: Terminate process gracefully (default)
- **KILL (9)**: Force kill process (cannot be caught or ignored)
- **HUP (1)**: Hangup - often used to reload configuration
- **INT (2)**: Interrupt - equivalent to Ctrl-C
- **QUIT (3)**: Quit - equivalent to Ctrl-\
- **STOP (19)**: Suspend process (cannot be caught)
- **CONT (18)**: Resume suspended process
- **USR1 (10)**: User-defined signal 1
- **USR2 (12)**: User-defined signal 2

### trap - Handle Signals and Shell Exit

The `trap` command sets up signal handlers and exit traps for robust shell script cleanup:

```bash
# Set up basic signal handling
psh$ trap 'echo "Interrupted by user"' INT
psh$ # Press Ctrl-C to see the trap execute

# Clean exit trap
psh$ trap 'echo "Script exiting, cleaning up..."' EXIT
psh$ exit

# Multiple signals with same handler
psh$ trap 'cleanup_function' INT TERM HUP QUIT

# Ignore a signal
psh$ trap '' QUIT
psh$ # Now SIGQUIT (Ctrl-\) is ignored

# Reset signal to default behavior
psh$ trap - INT
psh$ # INT signal now has default behavior

# List all available signals
psh$ trap -l
 -) DEBUG
 -) ERR
 -) EXIT
 1) SIGHUP
 2) SIGINT
 3) SIGQUIT
 ...

# Show current trap settings
psh$ trap -p
trap -- 'cleanup_function' INT
trap -- '' QUIT
```

#### Common Trap Patterns

**Cleanup on Exit:**
```bash
#!/usr/bin/env psh
# Cleanup temporary files on exit
tempfile=$(mktemp)
trap 'rm -f "$tempfile"' EXIT

echo "Working with $tempfile..."
# Script will clean up automatically
```

**Graceful Shutdown:**
```bash
#!/usr/bin/env psh
# Handle Ctrl-C gracefully
cleanup() {
    echo "Cleaning up..."
    kill $bg_pid 2>/dev/null
    exit 0
}

trap cleanup INT TERM

# Start background work
long_running_command &
bg_pid=$!
wait $bg_pid
```

#### Signal Reference

Commonly trapped signals:

- **INT (2)**: Interrupt (Ctrl-C)
- **TERM (15)**: Termination request
- **HUP (1)**: Hangup (terminal closed)
- **QUIT (3)**: Quit (Ctrl-\)
- **USR1 (10)**: User-defined signal 1
- **USR2 (12)**: User-defined signal 2

Special trap conditions:

- **EXIT**: Shell or script exit
- **DEBUG**: Before each command (bash extension)
- **ERR**: Command returns non-zero (bash extension)

### wait - Wait for Process Completion

The `wait` command waits for background processes to complete and returns their exit status:

```bash
# Start some background jobs
psh$ sleep 2 &
[1] 12345
psh$ sleep 3 &
[2] 12346

# Wait for all background jobs to complete
psh$ wait
psh$ echo $?
0

# Wait for specific job by job number
psh$ sleep 5 &
[1] 12348
psh$ wait %1

# Wait for specific process by PID
psh$ sleep 4 &
[1] 12349
psh$ wait 12349

# Wait for multiple specific processes
psh$ sleep 2 &
[1] 12350
psh$ sleep 3 &
[2] 12351
psh$ wait %1 %2
```

#### Job Specifications

The wait command supports the same job specifications as `fg` and `bg`:

- `%1`, `%2`, etc. - Job number
- `%+` or `%%` - Current job
- `%-` - Previous job
- `%string` - Job whose command begins with string
- `%?string` - Job whose command contains string

#### Error Handling

```bash
# Wait for non-existent process
psh$ wait 99999
wait: pid 99999 is not a child of this shell
psh$ echo $?
127

# Wait for non-existent job
psh$ wait %99
wait: %99: no such job
psh$ echo $?
127
```

## 4.6 Command Help and Information

### help - Display Builtin Command Information

The `help` builtin provides comprehensive documentation for PSH's built-in commands:

```bash
# Show all available builtins
psh$ help
PSH Shell, version 0.187.1
These shell commands are defined internally. Type 'help name' to find out more
about the function 'name'.

 . FILENAME [ARGS]                      : [arguments]
 [ EXPRESSION ]                         alias
 ast-dot [-p] COMMAND                   bg
 cd [dir]                               command [-pVv] command [arg ...]
 debug [OPTION] [on|off]                debug-ast [on|off] [FORMAT]
 declare                                dirs [-clv] [+N | -N]
 disown [-h] [-ar] [jobspec ...]        echo [-neE] [arg ...]
 env                                    eval [ARG ...]
 exec [command [argument ...]]          exit [n]
 export                                 false
 fg                                     getopts optstring name [arg ...]
 help [-dms] [pattern ...]              history
 jobs                                   kill [-s signal | -signal] pid...
 local                                  parse-tree [-f FORMAT] [-p] COMMAND
 parser-config [COMMAND] [ARG]          parser-mode [MODE]
 parser-select [PARSER]                 popd [+N | -N]
 printf format [arguments ...]          pushd [dir | +N | -N]
 pwd                                    read [-rs] [-a array] [-d delim] ...
 readonly                               return
 set                                    shift [n]
 shopt                                  show-ast [-p] COMMAND
 signals [-v]                           source FILENAME [ARGS]
 test [EXPRESSION]                      trap [action] [condition...]
 true                                   type
 typeset                                unalias
 unset                                  version
 wait [pid|job_id ...]

# Get detailed help for a specific builtin
psh$ help echo
echo: echo [-neE] [arg ...]

    Display arguments separated by spaces, followed by a newline.
    ...

# Get help for multiple builtins
psh$ help cd pwd

# Description mode - shows one-line descriptions
psh$ help -d

# Synopsis mode - shows just command syntax
psh$ help -s echo pwd read
echo: echo [-neE] [arg ...]
pwd: pwd
read: read [-rs] [-a array] [-d delim] [-p prompt] [-t timeout] [-n chars] [name ...]

# Manpage format - detailed documentation
psh$ help -m help
NAME
    help - Display information about builtin commands

SYNOPSIS
    help [-dms] [pattern ...]

DESCRIPTION
    ...

# Pattern matching to find builtins
psh$ help e*        # Commands starting with e
psh$ help "*set*"   # Commands containing 'set'
psh$ help "?"       # Single character commands

# Error handling
psh$ help nonexistent
help: no help topics match 'nonexistent'
```

#### Help Options

- **No options**: Default behavior - shows command listing or detailed help
- **-d**: Description mode - shows "command - description" format for all builtins
- **-s**: Synopsis mode - shows only the command syntax/usage line
- **-m**: Manpage mode - shows formatted manual page with NAME, SYNOPSIS, DESCRIPTION

### type - Display Command Type Information

The `type` builtin shows how PSH would interpret a command name:

```bash
# Show command types
psh$ type echo
echo is a shell builtin

psh$ type ls
ls is /bin/ls

psh$ type nonexistent
type: nonexistent: not found

# Type classification (-t flag)
psh$ type -t echo
builtin
psh$ type -t ls
file
psh$ type -t if
keyword

# Show all locations (-a flag)
psh$ type -a echo
echo is a shell builtin
echo is /bin/echo

# Force PATH search (-P flag)
psh$ type -P echo
/bin/echo

# Check multiple commands
psh$ type echo ls cd if
echo is a shell builtin
ls is /bin/ls
cd is a shell builtin
if is a shell keyword
```

### version - Display Version

```bash
psh$ version
Python Shell (psh) version 0.187.1
```

## 4.7 Script and Command Execution

### source (.) - Execute Script in Current Shell

Run commands from a file in the current shell environment:

```bash
# Create a script with variables and functions
psh$ cat > setup.sh << 'EOF'
# Setup script
export PROJECT_DIR="/home/alice/project"
export DEBUG=1

greet() {
    echo "Hello from setup.sh!"
}

alias ll='ls -la'
echo "Environment configured!"
EOF

# Source the script
psh$ source setup.sh
Environment configured!
psh$ echo $PROJECT_DIR
/home/alice/project
psh$ greet
Hello from setup.sh!

# Using . (dot) command (same as source)
psh$ . setup.sh
Environment configured!

# Source with arguments
psh$ cat > args.sh << 'EOF'
echo "Script name: $0"
echo "First arg: $1"
echo "Second arg: $2"
EOF

psh$ source args.sh one two
Script name: psh
First arg: one
Second arg: two
```

### history - Command History

View and manage command history:

```bash
# Show recent commands
psh$ history
  496  cd /tmp
  497  ls -la
  498  echo "test"
  499  pwd
  500  history

# Show last N commands
psh$ history 3
  498  echo "test"
  499  pwd
  500  history

# Search history (with grep)
psh$ history | grep cd
  481  cd /home/alice
  492  cd Documents
  496  cd /tmp

# Clear history
psh$ history -c
psh$ history
  1  history
```

### return - Return from Function

Exit from a shell function with optional status:

```bash
# Basic return
psh$ validate_file() {
>     if [ ! -f "$1" ]; then
>         echo "Error: File not found"
>         return 1
>     fi
>     echo "File is valid"
>     return 0
> }

psh$ validate_file /etc/passwd
File is valid
psh$ echo $?
0

psh$ validate_file /nonexistent
Error: File not found
psh$ echo $?
1

# Return can only be used in functions or sourced scripts
psh$ return
return: can only `return' from a function or sourced script
```

### alias and unalias - Manage Aliases

Create shortcuts for commands:

```bash
# Create aliases
psh$ alias ll='ls -la'
psh$ alias la='ls -A'
psh$ alias ..='cd ..'

# Use aliases
psh$ ll
total 48
drwxr-xr-x  5 alice alice 4096 Jan 15 12:00 .
...

# Show all aliases
psh$ alias
alias ..='cd ..'
alias la='ls -A'
alias ll='ls -la'

# Show specific alias
psh$ alias ll
alias ll='ls -la'

# Remove aliases
psh$ unalias ll
psh$ ll
psh: ll: command not found

# Remove all aliases
psh$ unalias -a
```

### local - Local Variables in Functions

Create variables scoped to a function:

```bash
psh$ outer="global"
psh$ myfunc() {
>     local inner="function-only"
>     local outer="shadowed"
>     echo "inner=$inner outer=$outer"
> }

psh$ myfunc
inner=function-only outer=shadowed

psh$ echo "outer=$outer"
outer=global

psh$ echo "inner=$inner"
inner=
```

The `local` builtin supports the same attribute flags as `declare`:

```bash
psh$ myfunc() {
>     local -i num=42       # Local integer
>     local -u text=hello   # Local uppercase
>     local -a arr=(1 2 3)  # Local array
>     echo "$num $text ${arr[1]}"
> }
psh$ myfunc
42 HELLO 2
```

## 4.8 Test Commands

### test and [ - Conditional Testing

Evaluate conditional expressions:

```bash
# String tests
psh$ [ "hello" = "hello" ]
psh$ echo $?
0

psh$ [ "hello" != "world" ]
psh$ echo $?
0

psh$ [ -z "" ]          # Empty string
psh$ echo $?
0

psh$ [ -n "text" ]      # Non-empty string
psh$ echo $?
0

# Numeric comparisons
psh$ [ 5 -eq 5 ]        # Equal
psh$ [ 5 -ne 10 ]       # Not equal
psh$ [ 5 -lt 10 ]       # Less than
psh$ [ 10 -gt 5 ]       # Greater than
psh$ [ 5 -le 5 ]        # Less or equal
psh$ [ 5 -ge 5 ]        # Greater or equal

# File tests
psh$ [ -f /etc/passwd ]  # Regular file
psh$ [ -d /tmp ]         # Directory
psh$ [ -e /etc ]         # Exists
psh$ [ -r file.txt ]     # Readable
psh$ [ -w file.txt ]     # Writable
psh$ [ -x script.sh ]    # Executable
psh$ [ -s file.txt ]     # Non-empty file

# Using test command (same as [)
psh$ test -f /etc/passwd
psh$ echo $?
0

# Combining conditions
psh$ [ -f file.txt ] && [ -r file.txt ]
psh$ [ 5 -gt 3 ] || [ 2 -gt 4 ]
```

### [[ ]] - Enhanced Test

Advanced conditional testing with better syntax:

```bash
# No word splitting - safer with variables
psh$ var="hello world"
psh$ [[ $var = "hello world" ]]  # Works without quotes
psh$ echo $?
0

# Pattern matching
psh$ [[ "hello" == h* ]]
psh$ echo $?
0

# Regular expression matching
psh$ [[ "user@example.com" =~ ^[^@]+@[^@]+$ ]]
psh$ echo $?
0

# String comparison (lexicographic)
psh$ [[ "apple" < "banana" ]]
psh$ echo $?
0

# Compound conditions
psh$ [[ -f file.txt && -r file.txt ]]
psh$ [[ $USER = "alice" || $USER = "bob" ]]

# Negation
psh$ [[ ! -f nonexistent.txt ]]
psh$ echo $?
0
```

## 4.9 Process Control

### exec - Execute Commands or Manipulate File Descriptors

The `exec` builtin executes commands or applies file descriptor redirections permanently to the current shell:

```bash
# Mode 1: exec without command - apply redirections permanently
psh$ exec > output.txt
psh$ echo "This goes to the file"
psh$ exec 2>&1  # Redirect stderr to stdout permanently

# Mode 2: exec with command - replace the shell process
psh$ exec echo "This replaces the shell"
This replaces the shell
$ # Shell has been replaced by echo command

# File descriptor management
psh$ exec 3< input.txt    # Open file descriptor 3 for reading
psh$ exec 4> output.txt   # Open file descriptor 4 for writing
psh$ exec 5>&1             # Duplicate stdout to fd 5

# Close file descriptors
psh$ exec 3<&-  # Close file descriptor 3
psh$ exec 4>&-  # Close file descriptor 4
```

#### Error Handling

```bash
# Command not found
psh$ exec nonexistent_command
exec: nonexistent_command: command not found
psh$ echo $?
127

# Permission denied
psh$ exec /tmp/no_exec
exec: /tmp/no_exec: Permission denied
psh$ echo $?
126
```

## 4.10 Dynamic Command Execution

### eval - Execute Commands from String

The `eval` builtin executes its arguments as shell commands, enabling dynamic command execution:

```bash
# Basic usage
psh$ eval "echo hello"
hello

# Multiple arguments are joined with spaces
psh$ eval echo "hello" "world"
hello world

# Variable assignment in eval
psh$ eval "name='Alice'"
psh$ echo $name
Alice

# Multiple commands
psh$ eval "echo first; echo second"
first
second

# Dynamic command building
psh$ cmd="echo"
psh$ msg="Dynamic message"
psh$ eval "$cmd '$msg'"
Dynamic message

# Control structures in eval
psh$ eval "for i in 1 2 3; do echo \"Number: \$i\"; done"
Number: 1
Number: 2
Number: 3

# Exit status handling
psh$ eval "true"
psh$ echo $?
0

psh$ eval "false"
psh$ echo $?
1

# Empty eval returns success
psh$ eval ""
psh$ echo $?
0
```

> **Warning**: `eval` can execute arbitrary code. Never use eval with untrusted input!

## 4.11 Positional Parameter Management

### shift - Shift Positional Parameters

The `shift` command removes positional parameters from the beginning of the list:

```bash
# Basic usage - shift by 1
psh$ set -- arg1 arg2 arg3 arg4
psh$ echo "Args: $@"
Args: arg1 arg2 arg3 arg4
psh$ shift
psh$ echo "Args: $@"
Args: arg2 arg3 arg4

# Shift by specific amount
psh$ set -- one two three four five
psh$ shift 2
psh$ echo "Args: $@"
Args: three four five

# Error cases
psh$ set -- x y
psh$ shift 5  # More than available
psh$ echo $?
1
```

### getopts - Parse Option Arguments

The `getopts` builtin provides POSIX-compliant option parsing:

```bash
# Basic option parsing
while getopts "hvo:" opt; do
    case $opt in
        h)
            echo "Usage: $0 [-h] [-v] [-o output]"
            exit 0
            ;;
        v)
            verbose=1
            ;;
        o)
            output="$OPTARG"
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
            ;;
    esac
done

# Shift past the options
shift $((OPTIND - 1))
echo "Remaining args: $@"
```

#### getopts Variables

- **OPTIND**: Index of next argument to process (starts at 1)
- **OPTARG**: Argument value for options requiring arguments
- **OPTERR**: Controls error message printing (1=enabled, 0=disabled)

### command - Bypass Functions and Aliases

The `command` builtin executes commands while bypassing shell functions and aliases:

```bash
# Basic usage - bypass alias/function
psh$ alias ls='ls --color=auto'
psh$ ls           # Uses alias
psh$ command ls   # Bypasses alias

# Check if command exists
psh$ command -v ls
/bin/ls
psh$ command -v nonexistent
psh$ echo $?
1

# Verbose command information
psh$ command -V echo
echo is a shell builtin
psh$ command -V ls
ls is /bin/ls

# Use in scripts to check for command availability
if command -v git >/dev/null 2>&1; then
    echo "Git is installed"
else
    echo "Git is not installed"
fi
```

## 4.12 Parser and Debug Built-ins

PSH includes built-in commands for exploring and debugging its internals. These are particularly useful for educational purposes.

### parse-tree - Show Parse Tree

Display the abstract syntax tree for a command:

```bash
# Default tree format
psh$ parse-tree 'echo hello | grep hello'

# Pretty format
psh$ parse-tree -f pretty 'if [ -f file ]; then echo yes; fi'

# Compact format
psh$ parse-tree -f compact 'echo hello'

# Graphviz DOT format (for visualization tools)
psh$ parse-tree -f dot 'echo hello'

# Show position information
psh$ parse-tree -p 'echo hello'
```

### show-ast - Pretty Print AST

Alias for `parse-tree -f pretty`:

```bash
psh$ show-ast 'for i in 1 2 3; do echo $i; done'
```

### ast-dot - Generate DOT Graph

Alias for `parse-tree -f dot`:

```bash
psh$ ast-dot 'echo hello | cat' > ast.dot
# Then render with: dot -Tpng ast.dot -o ast.png
```

### debug - Control Debug Options

Toggle various debug options at runtime:

```bash
# Show current debug state
psh$ debug

# Toggle specific debug options
psh$ debug ast on
psh$ debug tokens off
psh$ debug expansion on
psh$ debug exec on
psh$ debug parser on
psh$ debug scopes on
```

### debug-ast - Control AST Debugging

```bash
# Toggle AST debugging
psh$ debug-ast on
psh$ debug-ast off

# Set AST format
psh$ debug-ast on tree
psh$ debug-ast pretty
```

### parser-select - Choose Parser Implementation

Switch between parser implementations:

```bash
# Show available parsers
psh$ parser-select
Available parsers:
  * recursive_descent (aliases: rd, recursive, default)
    combinator (aliases: pc, functional)

# Switch to combinator parser
psh$ parser-select combinator

# Switch back to default
psh$ parser-select rd
```

### parser-mode - Set Parser Mode

```bash
# Show current mode
psh$ parser-mode

# Available modes
psh$ parser-mode posix          # Strict POSIX compliance
psh$ parser-mode bash           # Bash-compatible (default)
psh$ parser-mode permissive     # Permissive with error collection
psh$ parser-mode educational    # Educational with debugging
```

### parser-config - Parser Configuration

```bash
# Show current config
psh$ parser-config show

# Enable/disable features
psh$ parser-config enable arrays
psh$ parser-config disable brace-expand
psh$ parser-config strict       # Enable strict POSIX mode
```

### signals - Show Signal State

Display signal handler registrations:

```bash
# Show signal state
psh$ signals

# Verbose with history and stack traces
psh$ signals -v
```

## Practical Examples

### System Administration Script

```bash
#!/usr/bin/env psh
# System check script using built-ins

# Function to check service
check_service() {
    local service=$1
    if pgrep -x "$service" > /dev/null; then
        echo "[OK] $service is running"
        return 0
    else
        echo "[FAIL] $service is not running"
        return 1
    fi
}

# Main checks
echo "=== System Status Check ==="
echo

# Check disk space
echo "Disk Usage:"
df -h / | grep -v Filesystem

# Check important services
for service in sshd cron nginx; do
    check_service "$service"
done

# Check system load
echo
echo "System Load:"
uptime

exit 0
```

### Interactive Menu System

```bash
#!/usr/bin/env psh
# Interactive menu using built-ins

show_menu() {
    echo
    echo "=== Main Menu ==="
    echo "1) Show system info"
    echo "2) List files"
    echo "3) Check disk space"
    echo "4) Exit"
    echo
}

while true; do
    show_menu
    read -p "Select option: " choice

    case $choice in
        1)
            echo "Hostname: $(hostname)"
            echo "User: $USER"
            echo "Home: $HOME"
            ;;
        2)
            ls -la
            ;;
        3)
            df -h
            ;;
        4)
            echo "Goodbye!"
            exit 0
            ;;
        *)
            echo "Invalid option"
            ;;
    esac

    read -p "Press Enter to continue..."
done
```

## Summary

Built-in commands are the core of PSH functionality. They provide:
- Essential shell control (exit, :, true, false)
- Navigation capabilities (cd, pwd, pushd, popd, dirs)
- Environment management (export, unset, env, set, shopt, declare, readonly)
- I/O operations (echo, printf, read)
- Job control (jobs, fg, bg, disown, kill, wait)
- Signal handling (trap)
- Command help and information (help, type, version)
- Script execution (source, eval)
- Conditional testing (test, [, [[)
- Process control (exec)
- Positional parameters (shift, getopts)
- Command resolution (command)
- Parser and debug tools (parse-tree, show-ast, ast-dot, debug, parser-select, parser-mode, parser-config, signals)

PSH provides 50+ built-in commands. These commands execute quickly since they don't require forking new processes, and they have direct access to shell internals. Understanding built-ins is crucial for effective shell scripting and interactive use.

In the next chapter, we'll explore variables and parameters, building on the environment management commands covered here.

---

[← Previous: Chapter 3 - Basic Command Execution](03_basic_command_execution.md) | [Next: Chapter 5 - Variables and Parameters →](05_variables_and_parameters.md)
