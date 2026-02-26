# Python Shell (psh)

**A Production-Quality Educational Unix Shell Implementation**

Python Shell (psh) is a POSIX-compliant shell written entirely in Python, designed for learning shell internals while providing practical functionality. It features a clean, readable codebase with modern architecture and powerful built-in analysis tools.

**Current Version**: 0.192.2 | **Tests**: 3,450 total | **POSIX Compliance**: ~98%

*All source code and documentation (except this note) has been written by Claude Code using Sonnet 4.x and Opus 4.x models.*

## Quick Start

```bash
# Install
git clone https://github.com/philipwilsonTHG/psh.git
cd psh && pip install -e .

# Run interactively
psh

# Execute commands
psh -c "echo 'Hello, World!'"

# Analyze scripts
psh --metrics script.sh
psh --security script.sh
psh --format script.sh
```

## What Makes PSH Special

- 🔍 **CLI Analysis Tools**: Built-in script formatting, metrics, security analysis, and linting
- 📚 **Educational Focus**: Clean, readable codebase designed for learning shell internals
- 🧪 **Comprehensive Testing**: 3,450 tests ensuring reliability and robustness
- 🏗️ **Modern Architecture**: Component-based design with unified lexer and visitor pattern integration
- 🎓 **Dual Parser Implementation**: Both recursive descent and functional parser combinator with near-complete feature parity
- 📋 **POSIX Compliant**: ~98% compliance with robust bash compatibility
- 🎯 **Feature Complete**: Supports advanced shell programming with arrays, functions, and control structures

## CLI Analysis Tools ✨

PSH includes powerful built-in tools for shell script analysis:

### Script Formatting
```bash
psh --format script.sh              # Format with consistent indentation
psh --format -c 'if test; then; fi' # Format command strings
```

### Code Analysis
```bash
psh --metrics script.sh             # Analyze complexity and code metrics
psh --security script.sh            # Detect security vulnerabilities  
psh --lint script.sh                # Style and best practice suggestions
```

**Example Output:**
```bash
$ psh --metrics examples/fibonacci.sh
Script Metrics Summary:
═══════════════════════════════════════
Commands:
  Total Commands:            8
  Unique Commands:           5
  Built-in Commands:         3
  External Commands:         2

Structure:
  Functions Defined:         1
  Loops:                     1
  Conditionals:              2
  
Complexity:
  Cyclomatic Complexity:     4
  Max Nesting Depth:         2
```

## Complete Feature Set

### Core Shell Features ✅
- **Command Execution**: External commands, built-ins, background processes (`&`)
- **I/O Redirection**: All standard forms (`<`, `>`, `>>`, `2>`, `2>&1`, `<<<`, `<<`)
- **Pipelines**: Full pipeline support with proper process management
- **Variables**: Environment and shell variables with full expansion
- **Special Variables**: `$?`, `$$`, `$!`, `$#`, `$@`, `$*`, `$0`, positional parameters

### Advanced Expansions ✅
- **Parameter Expansion**: All bash forms including `${var:-default}`, `${var/old/new}`, `${var^^}`
- **Command Substitution**: Both `$(cmd)` and `` `cmd` `` with nesting support
- **Arithmetic Expansion**: `$((expr))` with full operator support and command substitution
- **Brace Expansion**: `{a,b,c}`, `{1..10}`, `{a..z}` with nesting
- **Process Substitution**: `<(cmd)` and `>(cmd)` for advanced I/O patterns
- **Glob Expansion**: `*`, `?`, `[abc]`, `[a-z]` with quote handling and extended globbing (`extglob`)

### Programming Constructs ✅
- **Control Structures**: `if/then/else`, `while`, `for`, `case`, C-style `for ((;;))`
- **Functions**: POSIX and bash syntax with local variables and return values
- **Arrays**: Both indexed and associative arrays with full bash compatibility
- **Break/Continue**: Multi-level loop control with `break 2`, `continue 3`
- **Test Commands**: Both `[` and `[[` with comprehensive operator support

### Interactive Features ✅
- **Line Editing**: Vi and Emacs key bindings with customizable modes
- **Tab Completion**: Intelligent file/directory completion with special character handling
- **Command History**: Persistent history with search and navigation
- **Job Control**: Background jobs, suspension (Ctrl-Z), `jobs`, `fg`, `bg`
- **Prompt Customization**: PS1/PS2 with escape sequences and ANSI colors

### Built-in Commands ✅
**Core**: `cd`, `pwd`, `echo`, `exit`, `true`, `false`, `:`  
**Variables**: `export`, `unset`, `set`, `declare`, `typeset`, `env`, `local`  
**I/O**: `read` (with `-p`, `-s`, `-t`, `-n`, `-d` options)  
**Job Control**: `jobs`, `fg`, `bg`  
**Functions**: `return`, `source`, `.`  
**Testing**: `test`, `[`, `[[`  
**Utilities**: `history`, `alias`, `unalias`, `eval`

## Usage Examples

### Basic Shell Operations
```bash
# Commands and pipelines
ls -la | grep python | wc -l
find . -name "*.py" | xargs grep "TODO"

# Variables and expansions
name="World"
echo "Hello, ${name}!"
echo "Current directory: $(pwd)"
echo "2 + 2 = $((2 + 2))"
```

### Advanced Programming
```bash
# Functions with local variables
calculate() {
    local a=$1 b=$2
    echo $((a * b))
}

# Arrays and iteration
files=(*.txt)
for file in "${files[@]}"; do
    echo "Processing: $file"
done

# Associative arrays
declare -A config
config[host]="localhost"
config[port]="8080"
echo "Server: ${config[host]}:${config[port]}"
```

### Control Structures
```bash
# Enhanced conditionals
if [[ $file =~ \.py$ && -f $file ]]; then
    echo "Python file found"
fi

# C-style loops
for ((i=0; i<10; i++)); do
    echo "Count: $i"
done

# Case statements
case $1 in
    start) echo "Starting service" ;;
    stop)  echo "Stopping service" ;;
    *)     echo "Usage: $0 {start|stop}" ;;
esac
```

### CLI Analysis Tools
```bash
# Format messy scripts
psh --format messy_script.sh > clean_script.sh

# Security analysis
psh --security deploy.sh
# Output: [HIGH] eval: Dynamic code execution - high risk of injection

# Code metrics for complexity analysis
psh --metrics complex_script.sh
# Shows cyclomatic complexity, nesting depth, command usage

# Linting for best practices
psh --lint old_script.sh
# Suggests modern alternatives and style improvements
```

## Installation

```bash
# Clone and install
git clone https://github.com/philipwilsonTHG/psh.git
cd psh
pip install -e .

# Install development dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/
```

## Architecture

PSH follows a modern component-based architecture with clear separation of concerns:

### Core Components
- **Shell** (`psh/shell.py`): Main orchestrator coordinating all subsystems
- **Lexer** (`psh/lexer/`): Modular tokenization with mixin architecture
- **Parser** (`psh/parser/`): Dual parser implementation:
  - **Recursive Descent** (`recursive_descent/`): Production parser with modular package structure
  - **Parser Combinator** (`combinators/`): Functional parsing with 100% feature parity
- **Executor** (`psh/executor/`): Command execution with specialized handlers
- **Expansion** (`psh/expansion/`): All shell expansions with proper precedence
- **I/O Management** (`psh/io_redirect/`): File operations and redirection handling
- **Interactive** (`psh/interactive/`): REPL, completion, history, and prompts

### Visitor Pattern Integration
PSH implements the visitor pattern for AST operations, enabling:
- **Analysis Tools**: Metrics, security scanning, linting
- **Code Transformation**: Formatting, optimization
- **Extensibility**: Easy addition of new analysis features

### Dual Parser Implementation
PSH uniquely includes two complete parser implementations:
- **Recursive Descent Parser**: Production parser with modular package structure, clear error messages, and comprehensive shell support
- **Parser Combinator**: Functional parsing implementation demonstrating elegant composition and achieving 100% feature parity
- **Educational Value**: Compare and contrast imperative vs. functional parsing approaches
- **Parser Selection**: Use `parser-select combinator` builtin to switch between implementations
- **Feature Parity**: Both parsers support all shell constructs (control structures, arrays, process substitution, etc.)

### Project Statistics
- **Lines of Code**: ~99,000 across 348 Python files
- **Test Coverage**: 3,450 tests in 153 test files
- **Architecture**: 8 major components with focused responsibilities
- **Visitors**: 9 analysis and transformation visitors
- **Dual Parser**: Both recursive descent and parser combinator implementations

## Testing & Quality

Canonical testing commands for contributors and CI are maintained in
`docs/testing_source_of_truth.md`.

### Running Tests (Recommended)

Use the provided test runner for correct handling of all tests:

```bash
# Smart mode (recommended) - handles subshell tests correctly
python run_tests.py
# or
./run_tests.sh

# Quick mode - skip slow tests
python run_tests.py --quick

# All tests with capture disabled (simpler but noisy)
python run_tests.py --all-nocapture
```

### Running Tests Manually

```bash
# Most tests - run normally
python -m pytest tests/

# Subshell tests - MUST use -s flag
python -m pytest tests/integration/subshells/ -s

# Specific categories
python -m pytest tests/unit/           # Unit tests
python -m pytest tests/integration/    # Integration tests
python -m pytest tests/conformance/    # POSIX/bash compatibility

# Performance tests
python -m pytest tests/performance/

# Coverage reporting
python -m pytest tests/ --cov=psh --cov-report=html
```

**Important:** Some tests (subshells, functions with subshells) require pytest's output capture to be disabled (`-s` flag) due to file descriptor handling in forked processes. The `run_tests.py` script handles this automatically.

**Current Test Statistics:**
- ✅ 2,808 passing tests
- ⏭️ 173 skipped tests (platform-specific or interactive)
- ⚠️ 36 xfailed (expected failures for unimplemented features)
- 📊 High coverage across all components

## POSIX Compliance

PSH achieves approximately **98% POSIX compliance** and **92% bash compatibility**:

### Compliance Highlights
- ✅ **Shell Grammar**: 98% - All major constructs supported
- ✅ **Parameter Expansion**: 95% - All standard forms implemented
- ✅ **I/O Redirection**: 95% - Complete standard redirection support
- ✅ **Control Structures**: 100% - Full if/while/for/case support
- ✅ **Built-in Commands**: 95% - Most essential commands implemented

### Bash Compatibility
PSH includes many bash extensions while maintaining POSIX compliance:
- Associative arrays with `declare -A`
- Enhanced test operators `[[ ]]` with regex support
- Brace expansion and process substitution
- Advanced parameter expansion with string manipulation
- C-style for loops and arithmetic commands
- Extended globbing (`shopt -s extglob`) with `?()`, `*()`, `+()`, `@()`, `!()` operators

## Known Limitations

While PSH implements most shell features, some limitations remain:

- **Signal Handling**: `trap` builtin not yet implemented
- **Deep Recursion**: Recursive functions hit Python stack limits
- **Some Advanced Features**: Minor gaps in specialized POSIX utilities

See [TODO.md](TODO.md) for planned enhancements.

## Development & Contributing

PSH welcomes contributions that maintain its educational focus:

- **Code Clarity**: Prioritize readability over cleverness
- **Documentation**: Comment complex logic thoroughly
- **Testing**: Include comprehensive tests for new features
- **Architecture**: Follow component-based design patterns

### Recent Development
- **v0.192.0**: Add 5 missing redirection operators (`<>`, `>|`, `&>`, `&>>`, `|&`)
- **v0.191.0**: Clean up TokenType enum (80 → 59 entries), fd-prefixed redirects as single tokens
- **v0.161.0**: Fix 7,132 ruff lint issues in test tree, expand CI lint gate to cover `psh/` and `tests/`
- **v0.160.0**: Fix 626 ruff lint issues in `psh/`, add CI lint gate
- **v0.155.0**: Fix 8 PSH bug XFAILs - heredocs, forked-child redirections, tests
- **v0.150.0**: Executor/visitor cleanup - deduplication, shared constants, POSIX word splitting
- **v0.145.0**: Quote-aware expansion scanners, multiple `$@` support
- **v0.130.0**: Remove parser abstraction layers (~1,686 lines), `parser-select` builtin
- **v0.120.0**: Complete `arg_types` migration to Word AST
- **v0.113.0**: Extended globbing (`extglob`) - Five pattern operators across all shell contexts
- **v0.108.0**: Fix 4 conformance bugs, achieve 0 PSH bugs - POSIX compliance 98.4%

## License

MIT License - see LICENSE file for details.

## Educational Value

PSH serves as an excellent learning resource for:
- **Shell Implementation**: Understanding lexing, parsing, and execution
- **Parsing Techniques**: Compare recursive descent vs. functional parser combinator approaches
- **Language Design**: Seeing how shell features interact and compose
- **System Programming**: Learning process management and I/O redirection
- **Software Architecture**: Studying component-based design patterns
- **Functional Programming**: Parser combinators demonstrate functional composition in real-world parsing

The codebase prioritizes clarity and includes extensive documentation to support learning shell internals and language implementation techniques. The dual parser implementation provides a unique opportunity to see the same language parsed using both imperative and functional approaches.
