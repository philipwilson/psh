# Chapter 2: Getting Started

## 2.1 Running PSH

PSH can be run in several different modes depending on your needs. Each mode serves a specific purpose and understanding them will help you use PSH effectively.

### Interactive Mode

The most common way to use PSH is interactively. Simply run `python -m psh` at your terminal:

```bash
$ python -m psh
psh$ echo "Welcome to PSH!"
Welcome to PSH!
psh$
```

In interactive mode:
- PSH displays a prompt and waits for commands
- Command history is available with arrow keys
- Tab completion works for files and directories
- Ctrl-C cancels the current command
- Ctrl-D or `exit` exits the shell

### Script Execution

PSH can execute shell scripts just like any other shell:

```bash
$ python -m psh myscript.sh
```

Or with a shebang line in your script:

```bash
#!/usr/bin/env psh
echo "This script runs in PSH"
```

Make it executable and run directly:

```bash
$ chmod +x myscript.sh
$ ./myscript.sh
This script runs in PSH
```

### Single Command Execution (-c)

Execute a single command without entering interactive mode:

```bash
$ python -m psh -c "echo Hello from PSH"
Hello from PSH

$ python -m psh -c "pwd; ls -la | head -3"
/home/user
total 48
drwxr-xr-x  5 user user 4096 Jan 15 10:00 .
drwxr-xr-x 20 user user 4096 Jan 14 09:00 ..
```

This is useful for:
- Quick one-off commands
- Using PSH in other scripts
- Testing PSH behavior

### Debug Modes

PSH offers powerful debugging capabilities to understand how commands are processed:

#### Token Debugging (--debug-tokens)

See how PSH tokenizes your input:

```bash
$ python -m psh --debug-tokens -c "echo hello | grep hello"
=== Token Debug Output ===
  [  0] WORD                 'echo'
  [  1] WORD                 'hello'
  [  2] PIPE                 '|'
  [  3] WORD                 'grep'
  [  4] WORD                 'hello'
  [  5] EOF                  ''
========================
hello
```

#### AST Debugging (--debug-ast)

View the Abstract Syntax Tree (AST) that PSH creates. PSH supports multiple AST output formats:

```bash
$ python -m psh --debug-ast -c "if [ -f /etc/passwd ]; then echo exists; fi"
=== AST Debug Output (recursive_descent) ===
+-- TopLevel
    +-- items: [1 items]
        +-- IfConditional
            |-- condition:
            |   +-- StatementList
            |       +-- statements: [1 items]
            |           +-- AndOrList
            |               +-- pipelines: [1 items]
            |                   +-- Pipeline
            |                       +-- commands: [1 items]
            |                           +-- SimpleCommand
            |                               +-- arguments: ...
            +-- then_part:
                +-- StatementList
                    ...
======================
exists
```

You can select different AST formats:

```bash
# Tree format (default)
$ python -m psh --debug-ast=tree -c "echo hello"

# Pretty format
$ python -m psh --debug-ast=pretty -c "echo hello"

# Compact, S-expression, or Graphviz DOT formats
$ python -m psh --debug-ast=compact -c "echo hello"
$ python -m psh --debug-ast=sexp -c "echo hello"
$ python -m psh --debug-ast=dot -c "echo hello"
```

#### Combining Debug Modes

You can use multiple debug modes together:

```bash
$ python -m psh --debug-tokens --debug-ast -c "x=5; echo $x"
```

### Debug Modes (continued)

PSH provides additional debug modes for understanding expansion and execution:

#### Expansion Debugging (--debug-expansion)

See how PSH expands variables, globs, and other constructs:

```bash
$ python -m psh --debug-expansion -c 'echo $HOME/*.txt'
[EXPANSION] Expanding Word AST command: ['echo', '$HOME/*.txt']
[EXPANSION] Word AST Result: ['echo', '/home/user/doc1.txt', '/home/user/doc2.txt']
/home/user/doc1.txt /home/user/doc2.txt
```

#### Detailed Expansion Debugging (--debug-expansion-detail)

Get step-by-step expansion details:

```bash
$ python -m psh --debug-expansion-detail -c 'echo ${USER:-nobody}'
[EXPANSION] Expanding Word AST command: ['echo', '${USER:-nobody}']
[EXPANSION] Word AST Result: ['echo', 'alice']
alice
```

#### Execution Debugging (--debug-exec)

Trace command execution paths including process creation details:

```bash
$ python -m psh --debug-exec -c 'echo hello | cat'
DEBUG Pipeline: ...
DEBUG ProcessLauncher: Child 12345 is pipeline leader
DEBUG BuiltinStrategy: executing builtin 'echo' with args ['hello']
...
hello
```

#### Fork/Exec Debugging (--debug-exec-fork)

See detailed process creation:

```bash
$ python -m psh --debug-exec-fork -c 'ls | head -n 2'
```

### Command-Line Options

Here's a complete list of PSH command-line options:

```
psh [options] [script] [arguments]

Options:
  -c <command>              Execute command and exit
  -i                        Force interactive mode
  -h, --help                Show help message
  -V, --version             Show version information
  --debug-ast               Show parsed AST before execution
  --debug-ast=FORMAT        AST format: tree, pretty, compact, dot, sexp
  --debug-tokens            Show tokenized input before parsing
  --debug-scopes            Show variable scope operations
  --debug-expansion         Show expansions as they occur
  --debug-expansion-detail  Show detailed expansion steps
  --debug-exec              Show executor operations
  --debug-exec-fork         Show fork/exec details
  --norc                    Don't load ~/.pshrc file
  --rcfile <file>           Use alternative RC file instead of ~/.pshrc
  --parser <parser>         Select parser: rd (recursive_descent), pc (combinator)
  --validate                Validate script without executing
  --format                  Format script and print formatted version
  --metrics                 Analyze script and print code metrics
  --security                Perform security analysis on script
  --lint                    Perform linting analysis on script
```

## 2.2 Basic Command Structure

Understanding how PSH interprets commands is fundamental to using it effectively.

### Simple Commands

A simple command consists of a command name followed by arguments:

```bash
psh$ echo Hello World
Hello World

psh$ ls -la /tmp
total 12
drwxrwxrwt  8 root root 4096 Jan 15 10:45 .
drwxr-xr-x 23 root root 4096 Jan 10 08:00 ..
...
```

### Command Components

1. **Command Name**: The first word (e.g., `echo`, `ls`)
2. **Arguments**: Additional words passed to the command
3. **Options**: Arguments that modify behavior (usually start with `-`)

### Word Splitting

PSH splits input into words at whitespace:

```bash
psh$ echo one    two     three
one two three
```

To preserve spacing, use quotes:

```bash
psh$ echo "one    two     three"
one    two     three
```

### Special Characters

Certain characters have special meaning:

- `|` - Pipe
- `>`, `<`, `>>` - Redirections
- `&` - Background execution
- `;` - Command separator
- `$` - Variable expansion
- `*`, `?`, `[...]` - Wildcards
- `#` - Comment

## 2.3 Your First Commands

Let's explore PSH with practical examples.

### File and Directory Operations

```bash
# Where are we?
psh$ pwd
/home/user

# List files
psh$ ls
Documents  Downloads  Pictures  script.sh

# Change directory
psh$ cd Documents
psh$ pwd
/home/user/Documents

# Go back
psh$ cd ..
psh$ pwd
/home/user

# Create a directory
psh$ mkdir test_dir
psh$ cd test_dir
```

### Working with Files

```bash
# Create a file
psh$ echo "Hello, PSH!" > greeting.txt

# View file contents
psh$ cat greeting.txt
Hello, PSH!

# Append to file
psh$ echo "Welcome to the shell." >> greeting.txt
psh$ cat greeting.txt
Hello, PSH!
Welcome to the shell.

# Copy files
psh$ cp greeting.txt backup.txt
psh$ ls
greeting.txt  backup.txt
```

### Environment Information

```bash
# Show environment variables
psh$ env | grep HOME
HOME=/home/user

# Show specific variable
psh$ echo $HOME
/home/user

# Show all shell variables
psh$ set | head -5
HOME=/home/user
PATH=/usr/local/bin:/usr/bin:/bin
PS1=psh$
PS2=>
PWD=/home/user
```

## 2.4 Getting Help

PSH provides several ways to get help:

### Built-in Help

Many built-in commands have help text:

```bash
psh$ help
PSH Shell, version 0.x.y
These shell commands are defined internally. Type 'help name' to find out more
about the function 'name'.
...

psh$ help echo
echo: echo [-neE] [arg ...]

    Display arguments separated by spaces, followed by a newline.
    ...
```

### Version Information

```bash
psh$ python -m psh --version
Python Shell (psh) version 0.x.y
```

Or from within PSH:

```bash
psh$ version
Python Shell (psh) version 0.x.y
```

### Debug Output for Learning

Use debug modes to understand how PSH processes commands:

```bash
# See how the AST is constructed
psh$ python -m psh --debug-ast -c 'echo "Hello, World"'

# See tokenization
psh$ python -m psh --debug-tokens -c 'echo "Hello, World"'
```

## 2.5 Customizing Your Environment (.pshrc)

PSH automatically loads `~/.pshrc` when starting an interactive session. This file can contain any PSH commands to customize your environment.

### Creating .pshrc

Create your initialization file:

```bash
psh$ cat > ~/.pshrc << 'EOF'
# PSH initialization file

# Custom prompt with colors
PS1='\[\e[32m\]\u@\h\[\e[0m\]:\[\e[34m\]\w\[\e[0m\]\$ '

# Useful aliases
alias ll='ls -la'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'

# Set default editor
export EDITOR=nano

# Add custom functions
hello() {
    echo "Hello, $1! Welcome to PSH."
}

echo "PSH initialized. Type 'help' for assistance."
EOF
```

### Common .pshrc Customizations

#### Prompt Customization

```bash
# Simple colored prompt
PS1='\[\e[1;32m\]psh>\[\e[0m\] '

# Prompt with directory
PS1='[\u@\h \w]\$ '

# Two-line prompt
PS1='\[\e[33m\][\u@\h:\w]\[\e[0m\]\n\$ '
```

#### Productivity Aliases

```bash
# Directory navigation
alias pd='pushd'
alias pop='popd'

# Safety aliases
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'

# Shortcuts
alias h='history'
alias j='jobs'
alias e='exit'
```

#### Functions

```bash
# Create and enter directory
mkcd() {
    mkdir -p "$1" && cd "$1"
}

# Extract various archive types
extract() {
    if [ -f "$1" ]; then
        case "$1" in
            *.tar.gz) tar xzf "$1" ;;
            *.tar.bz2) tar xjf "$1" ;;
            *.zip) unzip "$1" ;;
            *) echo "Unknown archive type: $1" ;;
        esac
    else
        echo "File not found: $1"
    fi
}

# Find file by name
ff() {
    find . -name "*$1*" -type f
}
```

### Skipping or Using Alternative RC Files

```bash
# Skip RC file loading
$ python -m psh --norc

# Use a different RC file
$ python -m psh --rcfile ~/myconfig.sh
```

## Summary

You now know how to:
- Run PSH in different modes (interactive, script, single command)
- Use debug modes to understand command processing
- Execute basic commands and navigate the filesystem
- Get help when needed
- Customize your PSH environment with .pshrc

These fundamentals provide the foundation for everything else in PSH. In the next chapter, we'll explore command execution in detail, including how PSH finds and runs programs, handles multiple commands, and manages background processes.

---

[← Previous: Chapter 1 - Introduction](01_introduction.md) | [Next: Chapter 3 - Basic Command Execution →](03_basic_command_execution.md)
