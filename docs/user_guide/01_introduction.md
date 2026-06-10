# Chapter 1: Introduction

## 1.1 What is PSH?

PSH (Python Shell) is an educational Unix shell implementation written in Python. Unlike production shells like Bash or Zsh, PSH is designed specifically for learning and understanding how shells work internally. It implements a substantial subset of POSIX shell functionality while maintaining clear, readable code that serves as a learning resource.

### Key Characteristics

- **Educational Focus**: Every component is written for clarity over performance
- **Hand-written Parser**: Uses recursive descent parsing for transparency, with an experimental combinator parser available
- **Component Architecture**: Clean separation of concerns with visitor pattern for AST operations
- **Comprehensive Features**: Implements 90+ shell features for real-world usability
- **Pure Python**: No C extensions or complex dependencies
- **Near-POSIX Compliance**: ~93% POSIX compliance as measured by conformance tests

## 1.2 Educational Purpose and Design Philosophy

PSH was created to demystify shell internals. When learning about shells, compilers, or interpreters, it's invaluable to have a working implementation that you can read, modify, and experiment with.

### Design Principles

1. **Clarity Over Performance**: Code is optimized for readability
2. **Explicit Over Implicit**: Magic is minimized; behavior is clear
3. **Modular Design**: Each component has a single, well-defined purpose
4. **Progressive Complexity**: Simple features are implemented simply
5. **Comprehensive Testing**: 3,450+ tests demonstrate usage and ensure correctness

### Learning Opportunities

By studying PSH, you can learn about:
- Lexical analysis with a modular recognizer architecture
- Recursive descent parsing with comprehensive validation
- Abstract Syntax Trees (ASTs) and the visitor pattern
- Command execution and process management
- I/O redirection and pipelines
- Variable scoping and expansion
- Job control and signal handling
- Modern architecture patterns in interpreter design

## 1.3 Installation and Setup

### Prerequisites

- Python 3.12 or later
- Unix-like operating system (Linux, macOS, BSD)
- Basic familiarity with command-line interfaces

### Installing from Source

```bash
# Clone the repository
git clone https://github.com/yourusername/psh.git
cd psh

# Install in development mode
pip install -e .

# Or install normally
pip install .
```

### Running PSH

After installation, you can run PSH in several ways:

```bash
# Start interactive shell
python -m psh

# Execute a single command
python -m psh -c "echo Hello, World!"

# Run a script
python -m psh script.sh

# Run with debugging
python -m psh --debug-ast -c "echo test"
```

### First Time Setup

PSH automatically creates a history file and can load initialization commands from `~/.pshrc`:

```bash
# Create a simple .pshrc file
echo 'PS1="\u@\h:\w\$ "' > ~/.pshrc
echo 'alias ll="ls -la"' >> ~/.pshrc
```

## 1.4 Quick Start Tutorial

Let's explore PSH with a quick hands-on tutorial.

### Your First Commands

Start PSH and try these commands:

```bash
$ python -m psh
psh$ echo "Hello, PSH!"
Hello, PSH!

psh$ pwd
/home/user

psh$ ls -la
total 24
drwxr-xr-x  3 user user 4096 Jan 15 10:00 .
drwxr-xr-x 15 user user 4096 Jan 15 09:00 ..
-rw-r--r--  1 user user  215 Jan 15 10:00 example.txt
```

### Using Variables

```bash
psh$ name="Alice"
psh$ echo "Hello, $name!"
Hello, Alice!

psh$ count=5
psh$ echo "Count is $count"
Count is 5
```

### Command Substitution

```bash
psh$ current_dir=$(pwd)
psh$ echo "We are in: $current_dir"
We are in: /home/user

psh$ file_count=$(ls | wc -l)
psh$ echo "This directory has $file_count files"
This directory has 3 files
```

### Simple Script

Create a file called `greet.sh`:

```bash
#!/usr/bin/env psh
# A simple greeting script

echo "What's your name?"
read name
echo "Hello, $name! Welcome to PSH."

# Show some system info
echo "Current date: $(date)"
echo "Current directory: $(pwd)"
```

Run it:

```bash
psh$ chmod +x greet.sh
psh$ ./greet.sh
What's your name?
Alice
Hello, Alice! Welcome to PSH.
Current date: Mon Jan 15 10:30:45 PST 2024
Current directory: /home/user
```

## 1.5 How to Use This Guide

### For Beginners

If you're new to shell programming:
1. Read chapters 1-5 sequentially
2. Try every example in your PSH session
3. Experiment with variations
4. Read chapter 17 to understand PSH's limitations

### For Experienced Shell Users

If you're familiar with Bash or other shells:
1. Skim chapters 1-3 for PSH-specific information
2. Jump to topics of interest
3. Check chapter 17 for differences from Bash
4. Explore the advanced features in chapters 11-16

### For Developers

If you want to understand PSH's internals:
1. Start with the architecture overview in the main documentation
2. Use `--debug-ast` and `--debug-tokens` to see parsing in action
3. Read the source code alongside this guide
4. Run the test suite to see comprehensive examples

## 1.6 Notation and Conventions

Throughout this guide, we use consistent notation:

### Command Examples

```bash
$ command          # Run in your regular shell
psh$ command       # Run in PSH
# comment          # Explanatory comment
output shown here  # Command output
```

### Syntax Notation

- `[optional]` - Optional elements
- `<required>` - Required elements (replace with actual value)
- `...` - Repetition allowed
- `|` - Choice between alternatives
- `literal` - Type exactly as shown

### Special Markers

> **Note**: Important information or tips

> **Warning**: Potential issues or limitations

> **Example**: Extended example with explanation

### Code Blocks

```bash
# Shell commands and scripts
echo "This is a shell command"
```

```python
# Python code (when showing PSH internals)
def example():
    return "This is Python code"
```

## Summary

PSH is your gateway to understanding how shells work. It's a fully functional shell that you can use for real work while learning about interpreters, parsers, and system programming. Whether you're a student, educator, or curious developer, PSH provides a clear view into the fascinating world of shell implementation.

In the next chapter, we'll get PSH up and running and explore its various modes of operation.

---

[Next: Chapter 2 - Getting Started →](02_getting_started.md)
