# Python Shell (psh)

**A Production-Quality Educational Unix Shell Implementation**

Python Shell (psh) is a POSIX-compliant shell written entirely in Python, designed for learning shell internals while providing practical functionality. It features a clean, readable codebase with modern architecture and powerful built-in analysis tools.

**Current Version**: 0.518.0 | **Tests**: 8,400+ | **POSIX Compliance**: ~98%

*All source code and documentation (except this note) has been written by Claude Code using Sonnet 4.x and Opus 4.x models.*

## Quick Start

```bash
# Install
git clone https://github.com/philipwilson/psh.git
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
- 🧪 **Comprehensive Testing**: 8,400+ tests ensuring reliability and robustness
- 🏗️ **Modern Architecture**: Component-based design with unified lexer and visitor pattern integration
- 🎓 **Dual Parser Implementation**: Production recursive descent parser, plus an educational parser-combinator alternative for comparing parsing paradigms
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

**Example Output** (the script lives in [`examples/fibonacci.sh`](examples/fibonacci.sh)):
```bash
$ psh --metrics examples/fibonacci.sh
Script Metrics Summary:
═══════════════════════════════════════
Commands:
  Total Commands:            18
  Unique Commands:            8
  Built-in Commands:          4
  External Commands:          4

Structure:
  Functions Defined:          2
  Pipelines:                 0
  Loops:                     3
  Conditionals:              1

Complexity:
  Cyclomatic Complexity:      5
  Max Pipeline Length:        0
  Max Nesting Depth:          2
  Max Function Complex:       1
```

Runnable example scripts live in [`examples/`](examples/) — see
[`examples/README.md`](examples/README.md) for the full set.

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
All 61 registered builtins (from `psh.builtins.registry`):

**Core**: `cd`, `pwd`, `echo`, `exit`, `true`, `false`, `:`, `exec`  
**Directory Stack**: `pushd`, `popd`, `dirs`  
**Variables**: `export`, `unset`, `set`, `shift`, `declare`, `typeset`, `local`, `readonly`, `let`, `getopts`, `env`  
**I/O**: `read` (with `-p`, `-s`, `-t`, `-n`, `-d` options), `printf`, `print`, `mapfile` (alias `readarray`)  
**Job Control**: `jobs`, `fg`, `bg`, `wait`, `kill`, `disown`  
**Functions & Execution**: `return`, `source`, `.`, `eval`, `command`, `builtin`, `type`, `hash`  
**Signals**: `trap` (signal traps plus EXIT, DEBUG, ERR)  
**Testing**: `test`, `[`  
**Shell Options & Environment**: `shopt`, `umask`, `times`  
**History & Aliases**: `history`, `alias`, `unalias`  
**PSH Introspection**: `help`, `version`, `signals`, `parser-select`, `parser-mode`, `parser-config`, `parse-tree`, `show-ast`, `ast-dot`, `debug`, `debug-ast`

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

Requires Python 3.12 or later.

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
  - **Parser Combinator** (`combinators/`): Educational functional-parsing alternative (not production-supported)
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
PSH includes two parser implementations with deliberately different statuses:
- **Recursive Descent Parser**: The production parser — modular package structure, clear error messages, comprehensive shell support. All conformance and correctness work targets this parser.
- **Parser Combinator**: An educational alternative demonstrating functional composition. It handles the broad shell grammar and is pinned against drift by parity tests, but it is **outside the production quality bar**: it may lag on edge cases (known gaps include composite words in some list contexts) and its gaps are not tracked as defects.
- **Educational Value**: Compare and contrast imperative vs. functional parsing approaches
- **Parser Selection**: Use `parser-select combinator` builtin (or `--parser combinator`) to switch implementations interactively

### Project Statistics
- **Lines of Code**: ~55,900 lines of production code in `psh/` across 238 Python files, plus ~75,700 lines of tests in `tests/` (373 Python files)
- **Test Coverage**: 8,439 tests in 365 test files
- **Architecture**: 8 major components with focused responsibilities
- **Visitors**: 7 analysis and transformation visitors (`psh/visitor/`)
- **Dual Parser**: Both recursive descent and parser combinator implementations

## Testing & Quality

Canonical testing commands for contributors and CI are maintained in
`docs/testing_source_of_truth.md`.

### Running Tests (Recommended)

Use the provided test runner for correct handling of all tests:

```bash
# Smart mode (recommended) - handles subshell tests correctly
python run_tests.py

# Parallel mode (~4x faster)
python run_tests.py --parallel

# Quick mode - skip slow tests
python run_tests.py --quick

# All tests with capture disabled (simpler but noisy)
python run_tests.py --all-nocapture
```

### Running Tests Manually

```bash
# All tests - run normally (subshell tests no longer need -s, as of v0.195.0)
python -m pytest tests/

# Subshell tests
python -m pytest tests/integration/subshells/

# Specific categories
python -m pytest tests/unit/           # Unit tests
python -m pytest tests/integration/    # Integration tests
python -m pytest tests/conformance/    # POSIX/bash compatibility

# Performance tests
python -m pytest tests/performance/

# Coverage reporting
python -m pytest tests/ --cov=psh --cov-report=html
```

**Note:** As of v0.195.0 the full suite passes under normal pytest capture; the `-s` flag is no longer required for subshell tests (a `read` builtin fix made it read the real redirected file descriptor). `run_tests.py` still works and remains the recommended runner.

**Current test status**: the full suite (8,439 collected tests across 365
files) passes locally via `python run_tests.py --parallel`, with a few
hundred tests skipped as platform-specific or interactive. Run the command
for exact pass/skip totals on your platform — see
[`docs/testing_source_of_truth.md`](docs/testing_source_of_truth.md).

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

- **RETURN Traps**: `trap` supports signal traps plus the EXIT, DEBUG, and ERR pseudo-signals, but not RETURN
- **History Word Designators**: basic event designators (`!!`, `!n`, `!string`) work, but word designators and modifiers (`!$`, `!!:1`, `^old^new`) are not supported
- **Deep Recursion**: Recursive functions hit Python stack limits
- **Some Advanced Features**: Minor gaps in specialized POSIX utilities

See [CHANGELOG.md](CHANGELOG.md) and `docs/reviews/` for recent fixes and remaining work.

## Development & Contributing

PSH welcomes contributions that maintain its educational focus:

- **Code Clarity**: Prioritize readability over cleverness
- **Documentation**: Comment complex logic thoroughly
- **Testing**: Include comprehensive tests for new features
- **Architecture**: Follow component-based design patterns

### Recent Development
PSH is under active development. For the detailed, per-release history
(behavior fixes, refactors, and architecture work) see
[CHANGELOG.md](CHANGELOG.md); for the in-depth design reviews that drive
that work, see [`docs/reviews/`](docs/reviews/).

## License

MIT License - see LICENSE file for details.

## Educational Value

**Start here:** [`docs/learning_path.md`](docs/learning_path.md) is the
recommended route through the codebase — from this README through the
architecture, the end-to-end internals tour, the `Word` AST data model, and the
per-subsystem notes.

PSH serves as an excellent learning resource for:
- **Shell Implementation**: Understanding lexing, parsing, and execution
- **Parsing Techniques**: Compare recursive descent vs. functional parser combinator approaches
- **Language Design**: Seeing how shell features interact and compose
- **System Programming**: Learning process management and I/O redirection
- **Software Architecture**: Studying component-based design patterns
- **Functional Programming**: Parser combinators demonstrate functional composition in real-world parsing

The codebase prioritizes clarity and includes extensive documentation to support learning shell internals and language implementation techniques. The dual parser implementation provides a unique opportunity to see the same language parsed using both imperative and functional approaches.
