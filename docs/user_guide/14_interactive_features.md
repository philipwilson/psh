# Chapter 14: Interactive Features

PSH provides a rich set of interactive features designed to enhance your command-line experience. From advanced line editing to customizable prompts and intelligent tab completion, these features make working in the shell more efficient and enjoyable.

## 14.1 The Interactive Shell

When you start PSH without arguments or with a terminal attached, it enters interactive mode, providing a Read-Eval-Print Loop (REPL) for command execution.

### Starting Interactive Mode

```bash
# Start interactive shell
$ psh
Welcome to PSH - Python Shell
psh$ 

# Force interactive mode even with redirected input
$ psh -i

# Start with custom RC file
$ psh --rcfile ~/.custom_pshrc

# Start without RC file
$ psh --norc

# Start with debug options
$ psh --debug-expansion
psh$ echo $HOME
[EXPANSION] Expanding command: ['echo', '$HOME']
[EXPANSION] Result: ['echo', '/home/user']
/home/user
```

### Interactive vs Non-Interactive Mode

```bash
# Check if running interactively
psh$ if [ -n "$PS1" ]; then
>     echo "Interactive mode"
> else
>     echo "Script mode"
> fi
Interactive mode

# Interactive features enabled:
- Command history
- Tab completion
- Line editing
- Job control
- Prompt expansion
- Signal handling (Ctrl-C, Ctrl-Z)

# Script mode differences:
- No job control by default
- No command history
- Different signal handling
- No prompt display
```

### Exiting the Shell

```bash
# Exit with exit command
psh$ exit

# Exit with exit code
psh$ exit 0

# Exit with Ctrl-D (EOF)
psh$ ^D

# Prevent accidental Ctrl-D exit
psh$ set -o ignoreeof
```

## 14.2 Command History

PSH maintains a history of commands you've executed, allowing you to recall and reuse previous commands efficiently.

### Basic History Navigation

```bash
# Navigate history with arrow keys
↑ (Up arrow)    # Previous command
↓ (Down arrow)  # Next command

# View command history
psh$ history
    1  cd /home/user
    2  ls -la
    3  echo "Hello, World!"
    4  git status
    5  history

# Execute command from history
psh$ !3        # Run command 3
psh$ !!        # Run last command
psh$ !-2       # Run the command two back
psh$ !git      # Run last command starting with 'git'
psh$ !?log?    # Run last command containing 'log'
```

### Word Designators

After an event reference you can select individual words from that
command's line with a `:word` designator. Words are split on whitespace
(quoting is respected) and numbered from 0, where word 0 is the command
itself:

```bash
psh$ echo alpha beta gamma
alpha beta gamma
psh$ echo !$      # Last argument of previous command  -> echo gamma
psh$ echo !^      # First argument (= !!:1)             -> echo alpha
psh$ echo !*      # All arguments (words 1..last)       -> echo alpha beta gamma
psh$ echo !!:0    # The command word                    -> echo echo
psh$ echo !!:2    # Word 2                               -> echo beta
psh$ echo !!:1-2  # Words 1 through 2                    -> echo alpha beta
psh$ echo !!:2*   # Word 2 through the last word         -> echo beta gamma
psh$ echo !!:2-   # Word 2 through the second-to-last    -> echo beta
```

The bare shorthands `!$`, `!^` and `!*` operate on the previous command,
and any word designator can also follow an explicit event
(`!3:$`, `!git:2`, `!-2:1`). Note: history expansion is only active in
interactive sessions (as in bash, it is disabled when input is not a
terminal).

### History File

```bash
# History is saved to ~/.psh_history
psh$ cat ~/.psh_history

# History is loaded on startup and saved on exit
# Maximum history size is configurable

# Clear history for current session
psh$ history -c

# Prevent command from being saved to history
# Start command with a space
psh$  echo "secret command"
```

### History Search

```bash
# Reverse history search (Ctrl-R in emacs mode)
psh$ ^R
(reverse-i-search)`git': git commit -m "Update README"

# Continue searching
^R again to find older matches

# Cancel search
Ctrl-G or ESC

# Forward history search (Ctrl-S)
# Note: May need to disable terminal flow control
psh$ stty -ixon    # Disable flow control
psh$ ^S            # Forward search
```

## 14.3 Tab Completion

Tab completion helps you type commands faster by automatically completing file names and directory paths. (Command-name and variable-name completion, which bash also offers, are not implemented — completion is path-based only.)

### Basic Tab Completion

```bash
# Complete file and directory names
psh$ ls /usr/l<TAB>
# Completes to: /usr/lib/ or shows options if multiple matches

psh$ cd ~/Doc<TAB>
# Completes to: ~/Documents/

# Multiple matches
psh$ ls /usr/b<TAB><TAB>
/usr/bin/  /usr/bash/

# Complete hidden files
psh$ ls .<TAB>
.bashrc  .config/  .local/  .pshrc

# Complete with partial match
psh$ ls file<TAB>
file1.txt  file2.txt  file_backup.txt
```

### Advanced Completion Features

```bash
# Complete filenames with spaces
psh$ cat "My Doc<TAB>
# Completes to: cat "My Documents"

psh$ cat My\ Doc<TAB>
# Completes to: cat My\ Documents

# Directory indicators
psh$ ls /usr/<TAB>
bin/  lib/  local/  share/

# Common prefix completion
psh$ ls very_long_file<TAB>
# Shows all files starting with "very_long_file"
very_long_file_1.txt
very_long_file_2.txt
very_long_file_final.txt

# Case sensitivity
psh$ ls DOC<TAB>
# May complete to: Documents/ (depending on filesystem)
```

### Completion Display

```bash
# When multiple matches exist
psh$ ls *.txt<TAB><TAB>
file1.txt    notes.txt       test.txt
file2.txt    readme.txt      todo.txt

# Completion with many matches
psh$ ls /usr/bin/py<TAB><TAB>
Display all 15 possibilities? (y or n)

# Column display for readability
python3         python3.9       pythonw
python3-config  python3.9m      pydoc3
```

## 14.4 Prompt Customization

PSH supports rich prompt customization through PS1 (primary prompt) and PS2 (continuation prompt) variables.

### Basic Prompt Variables

```bash
# Default prompts
psh$ echo $PS1
\u@\h:\w\$ 

psh$ echo $PS2
> 

# Simple prompt changes
psh$ PS1='$ '
$ PS1='psh> '
psh> PS1='[\W] $ '
[user] $ 
```

### Prompt Escape Sequences

```bash
# User and host information
\u    # Username
\h    # Hostname (short)
\H    # Hostname (fully qualified)

# Examples
psh$ PS1='\u $ '
alice $ 

psh$ PS1='\u@\h $ '
alice@laptop $ 

# Directory information
\w    # Working directory (full path, ~ for home)
\W    # Working directory (basename only)

# Examples
psh$ PS1='\w $ '
~/Documents/projects $ 

psh$ PS1='[\W] $ '
[projects] $ 

# Time and date
\t    # Time 24-hour HH:MM:SS
\T    # Time 12-hour HH:MM:SS
\@    # Time 12-hour am/pm
\A    # Time 24-hour HH:MM
\d    # Date "Weekday Month Date"

# Examples
psh$ PS1='\t $ '
14:30:45 $ 

psh$ PS1='[\@] $ '
[02:30pm] $ 

# Shell information
\s    # Shell name (psh)
\v    # Version (short)
\V    # Version (full)
\!    # History number
\#    # Command number
\$    # $ for user, # for root

# Special characters
\n    # Newline
\r    # Carriage return
\a    # Bell (alert)
\e    # Escape character
\\    # Literal backslash
\nnn  # Character by octal value

# Non-printing sequences
\[    # Begin non-printing (for colors)
\]    # End non-printing
```

### Colored Prompts

```bash
# ANSI color codes
# Format: \[\e[CODEm\]

# Color codes:
# 30-37: Foreground colors
# 40-47: Background colors
# 0: Reset, 1: Bold, 2: Dim

# Basic colored prompt
psh$ PS1='\[\e[32m\]\u@\h\[\e[0m\]:\[\e[34m\]\w\[\e[0m\]\$ '

# Breakdown:
# \[\e[32m\]  - Start green text
# \u@\h       - Username@hostname
# \[\e[0m\]   - Reset color
# :           - Literal colon
# \[\e[34m\]  - Start blue text
# \w          - Working directory
# \[\e[0m\]   - Reset color
# \$          - Prompt character

# Bold and colors
psh$ PS1='\[\e[1;35m\]\u\[\e[0m\]@\[\e[1;36m\]\h\[\e[0m\]:\w\$ '

# Two-line prompt with colors
psh$ PS1='\[\e[33m\]┌─[\u@\h:\w]\[\e[0m\]\n\[\e[33m\]└─\$\[\e[0m\] '

# Conditional coloring (red for root, green for user)
psh$ PS1='\[\e[$(($(id -u)==0?31:32))m\]\u@\h\[\e[0m\]:\w\$ '

# Git branch in prompt (if git is available)
psh$ git_branch() {
>     git branch 2>/dev/null | grep '^*' | sed 's/* //'
> }
psh$ PS1='\u@\h:\w$(git_branch)\$ '
```

### Continuation Prompts (PS2)

```bash
# Default continuation prompt
psh$ echo $PS2
> 

# Customize continuation prompt
psh$ PS2='... '
psh$ if true; then
... echo "Hello"
... fi

# Colored continuation prompt
psh$ PS2='\[\e[33m\]→ \[\e[0m\]'
psh$ for i in 1 2 3; do
→ echo $i
→ done

# Numbered continuations
psh$ PS2='[\#] '
psh$ while true; do
[2] echo "test"
[3] break
[4] done
```

## 14.5 Line Editing Modes

PSH supports both Emacs and Vi editing modes for command-line editing.

### Emacs Mode (Default)

```bash
# Enable Emacs mode
psh$ set -o emacs

# Basic movement
Ctrl-A    # Beginning of line
Ctrl-E    # End of line
Ctrl-F    # Forward one character (→)
Ctrl-B    # Backward one character (←)
Alt-F     # Forward one word
Alt-B     # Backward one word

# Editing
Ctrl-D    # Delete character under cursor
Ctrl-H    # Delete character before cursor (Backspace)
Ctrl-K    # Kill (cut) to end of line
Ctrl-U    # Kill entire line
Ctrl-W    # Kill word backward
Alt-D     # Kill word forward
Ctrl-Y    # Yank (paste) from kill ring

# History
Ctrl-P    # Previous command (↑)
Ctrl-N    # Next command (↓)
Ctrl-R    # Reverse history search
Ctrl-S    # Forward history search

# Other
Ctrl-L    # Clear screen
Ctrl-T    # Transpose characters
Ctrl-C    # Cancel current command
Ctrl-D    # Exit shell (on empty line)
```

### Vi Mode

```bash
# Enable Vi mode
psh$ set -o vi

# Vi mode has two states:
# - Insert mode (default when typing)
# - Normal/Command mode (ESC to enter)

# In Insert mode:
Type normally
ESC       # Enter normal mode

# In Normal mode - Movement:
h         # Left
j         # Down (next history)
k         # Up (previous history)
l         # Right
0         # Beginning of line
$         # End of line
w         # Forward word
b         # Backward word
e         # End of word

# In Normal mode - Editing:
i         # Insert before cursor
a         # Insert after cursor
I         # Insert at beginning
A         # Insert at end
x         # Delete character
X         # Delete previous character
dd        # Delete entire line
dw        # Delete word
cw        # Change word
cc        # Change entire line
r         # Replace character
R         # Replace mode

# In Normal mode - Other:
/         # Search history forward
?         # Search history backward
n         # Repeat search
N         # Repeat search backward
u         # Undo
.         # Repeat last change
v         # Visual mode (select text)

# Switching modes
ESC       # Always returns to normal mode
i, a, I, A, etc.  # Enter insert mode
```

### Mode Indicators

```bash
# Check current mode
psh$ set -o | grep -E 'emacs|vi'
emacs          on
vi             off

# Vi mode can be enabled
psh$ set -o vi
# Switch back to emacs mode
psh$ set -o emacs
```

## 14.6 Multi-line Commands

PSH automatically detects when a command is incomplete and prompts for continuation.

### Automatic Continuation Detection

```bash
# Control structures
psh$ if [ -f /etc/passwd ]; then
> echo "Password file exists"
> fi
Password file exists

psh$ while read line; do
> echo "Line: $line"
> done < file.txt

psh$ for i in {1..5}; do
> echo "Number: $i"
> done

# Pipes and operators at end of line
psh$ echo "Hello" |
> tr '[:lower:]' '[:upper:]'
HELLO

psh$ [ -f file.txt ] &&
> echo "File exists" ||
> echo "File not found"

# Unclosed quotes
psh$ echo "This is a
> multi-line string"
This is a
multi-line string

psh$ echo 'Single quotes
> also work for
> multiple lines'
```

### Line Continuation with Backslash

```bash
# Explicit line continuation
psh$ echo This is a very long \
> command that continues \
> on multiple lines
This is a very long command that continues on multiple lines

# In scripts or complex commands
psh$ tar -czf backup.tar.gz \
>     --exclude='*.tmp' \
>     --exclude='*.log' \
>     /home/user/documents

# Breaking long pipelines
psh$ cat large_file.txt | \
> grep "pattern" | \
> sort | \
> uniq -c | \
> sort -rn | \
> head -10
```

### Here Documents

```bash
# Multi-line input with here documents
psh$ cat << EOF
> This is line 1
> This is line 2
> This is line 3
> EOF
This is line 1
This is line 2
This is line 3

# Here documents in functions
psh$ send_email() {
>     mail -s "$1" "$2" << END_MESSAGE
> Dear User,
> 
> This is an automated message.
> 
> Best regards,
> System Administrator
> END_MESSAGE
> }
```

## 14.7 Shell Options and Debugging

PSH provides various shell options for controlling behavior and debugging.

### Runtime Debug Options

```bash
# View all shell options
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

# Enable expansion debugging at runtime
psh$ set -o debug-expansion
psh$ echo $USER
[EXPANSION] Expanding Word AST command: ['echo', '$USER']
[EXPANSION] Word AST Result: ['echo', 'alice']
alice

# Enable execution debugging at runtime
psh$ set -o debug-exec
psh$ echo hello | cat
[EXEC] PipelineExecutor: ...
[EXEC] CommandExecutor: ['echo', 'hello']
[EXEC]   Executing builtin: echo
hello

# Disable debugging
psh$ set +o debug-expansion +o debug-exec

# Command-line debug flags (more reliable for full output)
psh$ psh --debug-ast -c 'echo hello'     # Show AST
psh$ psh --debug-tokens -c 'echo hello'  # Show tokens
psh$ psh --debug-expansion -c 'echo $HOME'  # Show expansions
```

### Traditional Shell Options

```bash
# Enable error checking
psh$ set -e    # Exit on error (errexit)
psh$ set -u    # Error on undefined variables (nounset)
psh$ set -x    # Print commands before execution (xtrace)

# Combine short options
psh$ set -eux

# Long-form options
psh$ set -o pipefail     # Pipeline fails if any command fails
psh$ set -o noclobber    # Prevent overwriting files with >
psh$ set -o allexport    # Export all variables on assignment
psh$ set -o noglob       # Disable globbing
psh$ set -o verbose      # Print input lines as read

# Check specific option
psh$ set -o | grep errexit
errexit        	on

# Show options as re-enterable set commands
psh$ set +o
set -o errexit
set +o nounset
set -o xtrace
set +o pipefail
...
```

## 14.8 Job Control

PSH provides job control features for managing multiple processes in interactive mode.

### Background Jobs

```bash
# Run command in background
psh$ long_running_command &
[1] 12345

# Multiple background jobs
psh$ sleep 100 &
[1] 12346
psh$ compile_project &
[2] 12347

# Background job notifications
psh$ sleep 5 &
[1] 12348
psh$ # Do other work...
[1]+ Done     sleep 5
```

### Job Management Commands

```bash
# List jobs
psh$ jobs
[1]- Running    sleep 100 &
[2]+ Running    compile_project &

# Bring job to foreground
psh$ fg %1
sleep 100
^C    # Can now interrupt with Ctrl-C

# Bring most recent job to foreground
psh$ fg
compile_project

# Send job to background
psh$ bg %1
[1]+ sleep 100 &

# Job specifications
%1        # Job number 1
%+        # Current job
%-        # Previous job
%string   # Job whose command starts with string
```

### Process Suspension

```bash
# Suspend current foreground job
psh$ long_running_command
^Z
[1]+ Stopped    long_running_command

# Resume in background
psh$ bg
[1]+ long_running_command &

# Resume in foreground
psh$ fg
long_running_command

# Kill a job
psh$ kill %1
[1]+ Terminated    long_running_command
```

## 14.8 Signal Handling

PSH handles various signals appropriately in interactive mode.

### Common Signals

```bash
# SIGINT (Ctrl-C) - Interrupt
psh$ sleep 100
^C
psh$     # Command interrupted, shell continues

# SIGTSTP (Ctrl-Z) - Suspend
psh$ vim file.txt
^Z
[1]+ Stopped    vim file.txt
psh$ fg    # Resume

# SIGQUIT (Ctrl-\) - Quit
# Usually terminates with core dump

# EOF (Ctrl-D) - End of file
psh$ ^D
exit     # Exits shell
```

### Signal Behavior

```bash
# In interactive mode:
- SIGINT interrupts current command only
- Shell continues running
- SIGTSTP suspends foreground process
- SIGCHLD handled for job notifications

# In script mode:
- Default signal handling
- SIGINT terminates script
- No job control signals

# Custom signal handling with trap command
psh$ trap 'echo "Interrupted"' INT
psh$ trap 'echo "Cleaning up"' EXIT
psh$ trap -p    # List current traps
```

## 14.9 Interactive Shell Configuration

Customize your interactive shell experience through RC files and settings.

### RC File Configuration

```bash
# ~/.pshrc - Loaded for interactive shells
# Example configuration:

# Set prompt
export PS1='\[\e[32m\]\u@\h\[\e[0m\]:\[\e[34m\]\w\[\e[0m\]\$ '
export PS2='\[\e[33m\]... \[\e[0m\]'

# Enable vi mode
set -o vi

# Aliases for interactive use
alias ll='ls -la'
alias ..='cd ..'
alias grep='grep --color=auto'

# Functions for interactive use
mkcd() {
    mkdir -p "$1" && cd "$1"
}

# History settings
export HISTSIZE=10000
export HISTFILE=~/.psh_history

# Note: Custom key bindings (bind) are not supported

# Only in interactive mode
if [ -n "$PS1" ]; then
    echo "Welcome to PSH!"
    echo "Today is $(date '+%A, %B %d')"
fi
```

### Interactive Options

```bash
# Shell options
set -o            # Show all options
set -o emacs      # Emacs editing mode
set -o vi         # Vi editing mode
set +o vi         # Disable vi mode

# Additional options:
set -o ignoreeof  # Ignore Ctrl-D (require exit command)
set -o noclobber  # Prevent overwriting files with >
set -o notify     # Immediate job notifications
set -o allexport  # Export all variables
```

## 14.10 Practical Tips and Tricks

### Efficient Command Line Usage

```bash
# Quick directory navigation
psh$ cd -    # Previous directory
psh$ cd      # Home directory
psh$ cd ~    # Also home directory

# Command repetition (history expansion)
psh$ !!      # Repeat last command
psh$ !$      # Last argument of previous command

# Clear screen
psh$ clear   # Or Ctrl-L

# Quick edits
# Use Ctrl-A/E to jump to start/end
# Use Alt-B/F for word movement
# Use Ctrl-K to clear from cursor
```

### Productivity Aliases

```bash
# Add to ~/.pshrc
alias l='ls -CF'
alias la='ls -A'
alias ll='ls -alF'
alias cls='clear'
alias h='history'
alias g='git'
alias gs='git status'
alias gc='git commit'
alias gp='git push'
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
```

### Interactive Functions

```bash
# Add to ~/.pshrc

# Extract archives
extract() {
    case "$1" in
        *.tar.gz|*.tgz) tar xzf "$1" ;;
        *.tar.bz2) tar xjf "$1" ;;
        *.zip) unzip "$1" ;;
        *.gz) gunzip "$1" ;;
        *) echo "Unknown archive format" ;;
    esac
}

# Make directory and enter it
mkcd() {
    mkdir -p "$1" && cd "$1"
}

# Find and edit
fe() {
    local file
    file=$(find . -name "$1" -type f | head -1)
    [ -n "$file" ] && ${EDITOR:-vi} "$file"
}
```

### Customizing Your Environment

```bash
# Color ls output
export CLICOLOR=1
export LSCOLORS=ExFxCxDxBxegedabagaced

# Set default editor
export EDITOR=vim
export VISUAL=vim

# Customize less pager
export LESS='-R -i -g'
export LESSOPEN='| /usr/bin/env lesspipe %s'

# Add custom PATH
export PATH="$HOME/bin:$HOME/.local/bin:$PATH"

# Set locale
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

## Summary

PSH's interactive features provide a powerful and customizable command-line environment:

1. **Interactive Shell**: REPL with rich features for daily use
2. **Command History**: Persistent history with search capabilities
3. **Tab Completion**: Intelligent file and path completion
4. **Prompt Customization**: Rich PS1/PS2 with colors and information
5. **Line Editing**: Emacs and Vi modes for efficient editing
6. **Multi-line Commands**: Automatic detection and continuation
7. **Job Control**: Background jobs and process management
8. **Signal Handling**: Proper handling of Ctrl-C, Ctrl-Z, etc.
9. **Configuration**: RC files for personalization
10. **Tips and Tricks**: Productivity enhancements

Key concepts:
- Interactive mode provides features not available in scripts
- History and completion speed up command entry
- Customizable prompts provide useful information
- Line editing modes offer powerful text manipulation
- Job control enables multitasking in the shell
- RC files personalize the shell environment

These features make PSH a comfortable and efficient environment for daily command-line work, whether you're a developer, system administrator, or power user.

---

[Previous: Chapter 13 - Shell Scripts](13_shell_scripts.md) | [Next: Chapter 15 - Job Control](15_job_control.md)