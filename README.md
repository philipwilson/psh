# Python Shell (psh)

**A Production-Quality Educational Unix Shell Implementation**

Python Shell (psh) is a POSIX-compliant shell written entirely in Python, designed for learning shell internals while providing practical functionality. It features a clean, readable codebase with modern architecture and powerful built-in analysis tools.

**Current Version**: 0.301.0 | **Tests**: 4,978 total | **POSIX Compliance**: ~98%

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
- 🧪 **Comprehensive Testing**: 4,550 tests ensuring reliability and robustness
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
All 59 registered builtins (from `psh.builtins.registry`):

**Core**: `cd`, `pwd`, `echo`, `exit`, `true`, `false`, `:`, `exec`  
**Directory Stack**: `pushd`, `popd`, `dirs`  
**Variables**: `export`, `unset`, `set`, `shift`, `declare`, `typeset`, `local`, `readonly`, `let`, `getopts`, `env`  
**I/O**: `read` (with `-p`, `-s`, `-t`, `-n`, `-d` options), `printf`, `print`, `mapfile` (alias `readarray`)  
**Job Control**: `jobs`, `fg`, `bg`, `wait`, `kill`, `disown`  
**Functions & Execution**: `return`, `source`, `.`, `eval`, `command`, `builtin`, `type`  
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
- **Lines of Code**: ~47,300 lines of production code in `psh/` across 192 Python files, plus ~53,600 lines of tests in `tests/` (231 files)
- **Test Coverage**: 4,978 tests in 239 test files
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

**Current Test Statistics** (from `python run_tests.py --parallel`):
- ✅ 4,235 passing tests
- ⏭️ 269 skipped tests (platform-specific or interactive)
- ⚠️ 1 xfailed (expected failure for an unimplemented feature)
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
- **v0.301.0**: process substitution is now a true Word expansion part — `echo pre<(cmd)post`, multiple per word, and `x=<(cmd)` assignments all work like bash; the whole-word string-sniffing pre-pass is deleted (whole-word is just the one-part case); same v0.288 scope cleanup
- **v0.300.0**: internal expansion bugs now fail loudly instead of becoming literal output; fork sigmask restore wrapped in try/finally (EAGAIN no longer leaks a blocked mask); interactive signal handlers restored on every REPL exit path (restore_default_handlers had zero callers; double-setup and notifier-fd latent bugs fixed)
- **v0.299.0**: array initializers now use the Word expansion engine (quoted globs stay literal, IFS-aware splitting, noglob/nullglob/dotglob honored, `"${a[@]}"` splicing — 53/53 bash probes); the parser already built Word nodes for elements and threw them away
- **v0.298.0**: doc fix-in-place pass — executor/lexer/visitor CLAUDE.mds corrected against code (phantom modules, wrong priorities, alias-only visit methods); ARCHITECTURE files purged of removed parser machinery; `$(case x in x)...)` paren-counting limitation documented with workaround — closes reappraisal #2 (11 releases, v0.288–v0.298)
- **v0.297.0**: docs archive sweep — 47 stale files (completed plans, v0.5x POSIX analyses, pre-relocation architecture docs, point-in-time reviews) moved to docs/archive/; 12 surviving guides got dated staleness banners; docs/architecture/ and docs/posix/ now contain only verified-current material
- **v0.296.0**: `${var:off:len}` slicing unified on one engine (4 copies → 1; 8 bash divergences fixed incl. sparse-array by-index slicing and negative-resolved offsets); arithmetic double-expansion deleted (`$12` now `${1}2`, variables holding `$(...)` no longer rescanned/executed); parser error-recovery remnants pruned; terminal EIO handler fixed
- **v0.295.0**: opt-in PTY tier repaired (6 failures were a framework prompt-sync off-by-one slicing each command's output one cycle behind — sentinel-prompt sync + ANSI stripping; 86 passed ×3); rootdir-hijacking nested pytest.ini deleted; test debris removed; CI workflow renamed tests.yml
- **v0.294.0**: job-state notices (`[1]+ Done`, Stopped, `set -b`) now go to stderr like bash; arithmetic errors via state.stderr; last builtin raw-print stragglers converted to write_line()/error() (function_support, read, help, debug_control)
- **v0.293.0**: keywords are now case-sensitive like bash (`IF`/`THEN`/`FOR` are ordinary words: `IF` → command not found, `IF=3` assignment works); one fix in keyword_defs covers both parsers
- **v0.292.0**: `exec` permanent redirections fixed (single open file description shared by builtin streams and external children — `exec &>f` no longer self-overwrites); noclobber exempts non-regular files like bash; builtin-redirection dual universe restructured into documented dispatcher + named helpers
- **v0.291.0**: alias/unalias rewritten to conventions (`-p`, rc 2 usage errors, bash `'\''` quoting, wrong quote-rejoin scanner deleted — it mangled escaped-quote operands bash keeps literal); printf gains `\e`/`\E`
- **v0.290.0**: run_tests.py no longer silently skips 45 tests (obsolete carve-out removed; the two files are xdist-safe); two stale xfails fixed; user guide re-probed claim-by-claim — 17 false "not supported" notes corrected, 10 true ones kept unversioned, all v0.187.1 pins removed; 23 new conformance tests pin the corrected claims
- **v0.289.0**: Four bash-pinned behavior fixes: assoc-array keys containing `,`/`^` (`${a[x,y]}`); `command -v/-V` now finds aliases/functions/keywords with bash output and rc semantics; in-pipeline command-not-found prints "command not found" (127/126, byte-identical to single-command); four dead `set -o` options deleted
- **v0.288.0**: Process substitutions no longer leak fds/zombies: scoped LIFO cleanup with non-blocking reaping (bash-pinned); also fixes `echo >(sleep N)` blocking N seconds and "Bad file descriptor" when functions receive `<(...)` arguments
- **v0.287.0**: Mypy enforced in CI (core/ + pure modules, zero ignores); 76 in-process line-editor/completion unit tests — closes the ground-up reappraisal program (13 releases, v0.275–v0.287)
- **v0.286.0**: Dead parser error-recovery machinery deleted (reachability-audited); vestigial AST fields documented as legacy; parser messages standardized; five subsystem CLAUDE.mds refreshed claim-by-claim
- **v0.285.0**: 19 top-level orphan modules relocated into their packages (top level is now just shell/__main__/ast_nodes/version); scope_enhanced.py → scope.py; executor→builtins import-time edge severed
- **v0.284.0**: Builtins consistency: 33 error-channel sites unified on self.error()/write_line(); type/jobs on shared option parsing; unset subscripts via the canonical evaluator (4 bash divergences fixed); jobs -l implemented
- **v0.283.0**: Vi-mode arrows fixed via one centralized escape parser; history single-writer (multiline commands store joined, bash-pinned); dead DSR queries removed; __main__ arg parsing extracted
- **v0.282.0**: Signal-loss race fixed (signals in the fork→exec window were consumed by inherited Python handlers; now blocked across fork); JobManager.launch_background extracted (6 dup sites); CommandExecutor.execute split; codename comments replaced
- **v0.281.0**: Lexer cleanup: quadratic word-scan fixed (128k-char word 0.202s → 0.079s); 12 dead config flags + ~590 lines removed; comment/backtick/fd-dup logic deduplicated
- **v0.280.0**: One pattern engine for case/`[[ ]]`/`${var#pat}` (fnmatch paths deleted; POSIX classes now work everywhere); shared escape/quote helpers in utils/escapes.py; PshError exception root
- **v0.279.0**: expansion/variable.py (1,644 lines) decomposed into arrays/operators/operands/fields mixins; array-index resolution deduplicated (6 copies → 1); string scanner unified with the operand scanner
- **v0.278.0**: Meta-documentation sweep: ARCHITECTURE files match the post-campaign tree; README builtins list regenerated; stale docs archived
- **v0.277.0**: Legacy test trees deleted (conformance_tests/, contract_tests_draft/); 30 fold-in conformance tests; cd HOME/OLDPWD shell-variable bug + POSIX ENOEXEC fallback fixed; locale pinned in conformance runs
- **v0.276.0**: read option parsing rewritten getopt-style (bash-pinned); bg-job notices to stderr; last pytest sniff removed; combinator drift fixed (function-def redirects, quoted case patterns)
- **v0.275.0**: Packaging truth (`requires-python >= 3.12`) + whole-tree ruff-clean (`psh/` and `tests/`); CI bumped to 3.12
- **v0.274.0**: Conformance expansion (98 tests) + claims meta-test; `$$` stable in children; `exec N<file`; USR1-class signal traps; subshell EXIT traps
- **v0.273.0**: Line editor: wrap-aware rendering (one central repaint); `\[ \]`/OSC prompt width fixed; pure layout module + 40-column PTY tests
- **v0.272.0**: Lexer: quadratic array-assignment scan replaced with O(n) map (~97x on long lines); ANSI-C parsing deduplicated; perf regression tests
- **v0.271.0**: Terminal control fixed (ctrl-c/ctrl-z on foreground jobs); shared ProcessLauncher; all pytest-awareness removed from production code
- **v0.270.0**: PTY test rehabilitation: deterministic interactive smoke suite runs in CI; blanket xfails removed
- **v0.269.0**: Parser sweep: `f() (...)` subshell bodies, per-call definition redirects, quoted case patterns (Word AST), and-or dedup
- Earlier history: see [CHANGELOG.md](CHANGELOG.md).

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
