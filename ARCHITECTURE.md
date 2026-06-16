# PSH Architecture Guide

## Overview

Python Shell (psh) is designed with a clean, component-based architecture that separates concerns and makes the codebase easy to understand, test, and extend. The shell follows a traditional interpreter pipeline: lexing → parsing → expansion → execution, with each phase carefully designed for educational clarity and correctness.

**Current Version**: 0.476.0

**Note:** For orientation, start with the Quick Map below; for a narrative
walkthrough of one command through the whole pipeline (with reproducible
debug-flag output at every stage) read
`docs/architecture/tour_of_psh_internals.md`; for per-context
expansion pointers see `docs/architecture/ast_data_flow.md`; for working
within a subsystem see that package's `CLAUDE.md`. (The separate
`ARCHITECTURE.llm` file was retired in v0.311.0 — its unique content now
lives here and in those documents.)

**Key Architectural Features**:
- **Dual Parser Architecture**: Two complete parser implementations for educational comparison
  - **Recursive Descent Parser**: Production parser with modular package structure in `psh/parser/recursive_descent/`
  - **Parser Combinator**: Educational functional parser in `psh/parser/combinators/` — outside the production quality bar (decision 2026-06-12); parity tests pin against drift but its gaps are not tracked as defects
  - **Parser Selection**: Switch between implementations with `parser-select combinator` builtin
  - **Educational Value**: Compare imperative vs. functional parsing approaches
- **Unified Lexer Architecture**: Recognizer-based modular lexer
  - **Single Token System**: Unified Token dataclass with position, quote and part metadata
  - **Modular Recognition**: Priority-based token recognizer system
  - **Dedicated Quote/Expansion Parsers**: Quotes and `$`-expansions consumed whole by `UnifiedQuoteParser`/`ExpansionParser`
  - **Clean API**: Simplified interface with no compatibility overhead
- **Enhanced Parser System**: Comprehensive configuration and validation
  - **Parser Configuration**: Multiple parsing modes (POSIX, bash-compat, educational)
  - **AST Validation**: Visitor-based validators in `psh/visitor/` (e.g. `EnhancedValidatorVisitor`)
  - **Centralized Context**: Unified state management for all parser components
  - **Parse Tree Visualization**: Multiple output formats with CLI integration
  - **Advanced Error Recovery**: Smart suggestions and multi-error collection
- **Modular Executor Package**: Visitor pattern with specialized executor modules
  - **Command Execution**: Strategy pattern for builtins, functions, and external commands
  - **Pipeline Management**: Process forking and pipe coordination
  - **Control Flow**: Dedicated executors for all control structures
  - **Delegation Architecture**: Clean separation of execution concerns
- **Multi-phase Expansion**: POSIX-compliant expansion ordering
- **Component-based Design**: Each subsystem has clear boundaries and responsibilities

## Quick Map

### Component Hierarchy

```
psh/
├── shell.py                 # Main orchestrator: 7 named lifecycle phases + Shell.for_subshell(); no execution or CLI-mode logic
├── core/                    # Shared state, options, traps
│   ├── state.py             # ShellState and option plumbing
│   ├── scope.py             # Hierarchical variable scope management
│   ├── variables.py         # Variable types and exports
│   ├── functions.py         # FunctionManager (shell function definitions)
│   ├── options.py           # Shell option behaviors
│   ├── exceptions.py        # PshError root + control-flow exceptions
│   └── trap_manager.py      # Signal/exit trap handling
├── lexer/                   # Unified modular lexer package
│   ├── modular_lexer.py     # Entry point for tokenization
│   ├── heredoc_lexer.py     # Tokenization with heredoc capture
│   ├── state_context.py     # Unified lexer context object
│   ├── keyword_normalizer.py# Keyword normalization pass (WORD → keyword tokens)
│   ├── keyword_defs.py      # Shared keyword definitions and helpers
│   ├── quote_parser.py / expansion_parser.py
│   ├── token_types.py / token_stream.py
│   ├── pure_helpers.py      # Stateless char-level helpers (QuoteState, escapes)
│   ├── cmdsub_scanner.py    # Grammar-aware $(...) extent scanner
│   └── recognizers/         # Token recognizer registry (operators, literals, etc.)
├── parser/
│   ├── config.py            # ParserConfig & enums
│   ├── recursive_descent/   # THE production parser (parser.py, context.py, parsers/, support/)
│   ├── combinators/         # Educational-only alternative (decision 2026-06-12)
│   └── visualization/       # AST renderers (ASCII, DOT, pretty)
├── expansion/               # POSIX expansion pipeline
│   ├── manager.py           # Orchestrates expansion order; expand_word_to_fields
│   ├── variable.py + arrays/operators/operands/fields mixins
│   ├── parameter_expansion.py / command_sub.py / tilde.py / glob.py
│   ├── pattern.py           # THE canonical shell-pattern engine
│   ├── arithmetic/ / brace_expansion.py / word_splitter.py / evaluator.py
│   └── aliases.py           # AliasManager
├── executor/                # Visitor-based executor package
│   ├── core.py              # ExecutorVisitor (delegates to specialists)
│   ├── command.py / pipeline.py / control_flow.py
│   ├── array.py / function.py / subshell.py
│   ├── process_launcher.py  # Job-controlled process creation (pgids, terminal, sync)
│   ├── child_policy.py      # fork_with_signal_window() + apply_child_signal_policy() + run_child_shell() — every fork site
│   ├── job_control.py       # JobManager
│   └── strategies.py        # Builtin/function/external dispatch
├── io_redirect/             # IOManager, FileRedirector (incl. heredocs), procsub scopes
├── scripting/               # ScriptManager, input sources/preprocessing, source processor, CLI analysis modes (visitor_modes.py)
├── interactive/             # REPL, line editor, history, completion, signals
├── builtins/                # Builtin commands (registry + implementations)
├── visitor/                 # Formatter/validator/security/metrics/linter visitors
└── utils/                   # Shared helpers (escapes.py dialect map, formatting)
```

### Execution Pipeline (one line per phase)

```
Input → Preprocessing → Tokenization → Keyword Normalization → Parsing → [Validation] → Expansion → Visitor Execution → Exit Status
```

1. **Input**: `scripting/input_preprocessing.py` (line continuations), `interactive/history_expansion.py`, `expansion/brace_expansion.py` (pre-lex)
2. **Tokenization**: `ModularLexer` + recognizer registry; `KeywordNormalizer` (case-sensitive reserved words); `tokenize_with_heredocs` collects bodies
3. **Parsing**: recursive descent `Parser` from modular sub-parsers; `WordBuilder` builds Word AST (composites via `TokenStream.peek_composite_sequence()`)
4. **Validation** (optional, `--validate`): visitor validators in `psh/visitor/`
5. **Expansion**: `ExpansionManager` enforces POSIX order; `WordExpander.expand()` walks Word parts with per-part quote context under named `WordExpansionPolicy` instances (see `docs/architecture/ast_data_flow.md` for per-context policies)
6. **Execution**: `ExecutorVisitor` delegates to specialists; job-controlled forks via `ProcessLauncher`, every fork via the `child_policy.py` helpers

### Architecture Invariants

1. **Centralized State**: all mutable shell state flows through `ShellState`
2. **Component Isolation**: managers interact via `Shell` references, not globals
3. **Visitor Execution**: AST nodes are data-only; behavior lives in visitors/executors
4. **POSIX Expansion Order**: expansion phases stay in standard order
5. **Word AST as Source of Truth**: `SimpleCommand.words` (and the Word fields on arrays/loops/assignments) are the sole structural argument representation; use Word helper properties, never string-type checks
6. **One Fork Helper, One Child Signal Policy, One Substitution-Child Runner**: every fork site forks via `fork_with_signal_window()` and every child applies `apply_child_signal_policy()`; *job-controlled* process creation (commands, pipelines, subshells) additionally goes through `ProcessLauncher`, while command/process substitution fork directly by design (they are not jobs) and run their child bodies through the shared `run_child_shell()` (child Shell construction, exception→exit-code mapping, `flush_child_streams()`, `os._exit`); all of this lives in `psh/executor/child_policy.py`
7. **Exit Status Discipline**: every execution path returns an integer exit status
8. **Fail Loudly**: internal errors raise; only user-facing shell errors map to exit codes (v0.300 policy)

### "Where do I change X?"

| Task | Start here |
|------|-----------|
| Add a builtin | `psh/builtins/` + `@builtin` decorator (see `psh/builtins/CLAUDE.md`) |
| Modify tokenization | `psh/lexer/modular_lexer.py` + recognizers (see `psh/lexer/CLAUDE.md`) |
| Modify parsing | `psh/parser/recursive_descent/parsers/` (see `psh/parser/CLAUDE.md`) |
| Change expansion semantics | `docs/architecture/ast_data_flow.md` has the per-context table |
| Command-substitution extent | `find_command_substitution_end` in `psh/lexer/cmdsub_scanner.py` (read its maintenance contract) |
| Process creation / signals | `psh/executor/process_launcher.py`, `child_policy.py` |
| Redirections / heredocs | `psh/io_redirect/` (see its CLAUDE.md for the two-universes design) |
| Job control | `psh/executor/job_control.py` |
| Shell options | `psh/core/state.py` + `psh/core/options.py` |
| Interactive / line editing | `psh/interactive/` (see its CLAUDE.md) |
| Analysis tools | `psh/visitor/` (totality enforced by `tests/unit/visitor/test_ast_coverage_matrix.py`) |

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Input                              │
└─────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Input Processing                             │
│                                                                 │
│  Line Continuation → History Expansion → Brace Expansion       │
└─────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Lexical Analysis (Tokenization)                 │
│                Recognizer-Based Modular Lexer                   │
│                                                                 │
│  Characters → Recognizers + Quote/Expansion Parsers → Tokens   │
└─────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Syntactic Analysis (Parsing)                 │
│                      Dual Parser Architecture                   │
│                                                                 │
│  Token Stream → [Recursive Descent | Parser Combinator] → AST  │
└─────────────────────────────┬───────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Execution                               │
│              Visitor Pattern Executor (Default)                 │
│                                                                 │
│  AST Traversal → Expansion → Command Execution → Exit Status   │
└─────────────────────────────────────────────────────────────────┘
```

## Phase 1: Input Processing

Before tokenization begins, several preprocessing steps occur:

### 1.1 Line Continuation Processing
**File**: `scripting/input_preprocessing.py`

Handles POSIX-compliant line continuations (`\<newline>`):
```bash
echo "This is a very \
long line that continues"
```

The preprocessor:
- Scans for backslash-newline sequences
- Preserves them inside single quotes
- Removes them elsewhere
- Maintains line number tracking for error reporting

### 1.2 History Expansion
**File**: `interactive/history_expansion.py`

Processes history expansions before tokenization:
- `!!` - Previous command
- `!n` - Command number n
- `!-n` - n commands ago
- `!string` - Most recent command starting with string

Context-aware to avoid expansion in quotes and certain contexts.

### 1.3 Brace Expansion
**File**: `expansion/brace_expansion.py`

Expands brace patterns before tokenization:
- List expansion: `{a,b,c}` → `a b c`
- Sequence expansion: `{1..10}` → `1 2 3 4 5 6 7 8 9 10`
- Nested expansion: `{a,b{1,2}}` → `a b1 b2`

This happens early because it can create multiple tokens from a single pattern.

## Phase 2: Lexical Analysis (Tokenization)

The lexer converts character streams into meaningful tokens by dispatching to priority-ordered token recognizers, with dedicated parsers consuming quotes and expansions whole.

### 2.1 Unified Lexer Package Architecture
**Package**: `psh/lexer/`

The lexer uses a unified, modular architecture with enhanced features as standard throughout PSH:

#### Core Package Structure
- **`psh/lexer/modular_lexer.py`** - Main ModularLexer class
- **`psh/lexer/constants.py`** - All lexer constants and character sets
- **`psh/lexer/unicode_support.py`** - Unicode character classification
- **`psh/lexer/token_parts.py`** - TokenPart and RichToken classes
- **`psh/lexer/position.py`** - Position tracking, error handling, and lexer configuration
- **`psh/lexer/__init__.py`** - Clean public API

#### State Management
- **`psh/lexer/state_context.py`** - Unified LexerContext for all state

#### Helper Functions
- **`psh/lexer/pure_helpers.py`** - Stateless char-level helpers (QuoteState, delimiter matching, escape decoding)
- **`psh/lexer/cmdsub_scanner.py`** - Grammar-aware `$(...)` extent scanner (a parser component living in the lexer; see its maintenance contract)

#### Quote and Expansion Parsing
- **`psh/lexer/quote_parser.py`** - Unified quote parsing with configurable rules
- **`psh/lexer/expansion_parser.py`** - All expansion types ($VAR, ${VAR}, $(...), $((...)))

#### Token Recognition
- **`psh/lexer/recognizers/`** - Modular token recognition system
  - `base.py` - TokenRecognizer abstract interface
  - `operator.py` - Shell operators with context awareness
  - `literal.py` - Words, identifiers, and assignments (forward WordShape state)
  - `word_scanners.py` - Pure mini-scanners (glob brackets, assignment prefixes, extglob groups, inline ANSI-C) + WordShapeTracker
  - `whitespace.py` - Whitespace handling
  - `comment.py` - Comment recognition
  - `process_sub.py` - Process substitution (`<(...)`, `>(...)`)
  - `registry.py` - Priority-based recognizer dispatch

Keyword recognition is a normalization pass over the token stream (`psh/lexer/keyword_normalizer.py`, with shared definitions in `psh/lexer/keyword_defs.py`).

The architecture combines all components:
```python
class ModularLexer:
    """Modular lexer using pluggable token recognizers."""
    def __init__(self, input_string: str, config: Optional[LexerConfig] = None):
        self.position_tracker = PositionTracker(input_string)
        self.context = LexerContext()          # cross-token lexer state
        self.registry = RecognizerRegistry()   # priority-ordered recognizers
        self.expansion_parser = ExpansionParser(self.config)
        self.quote_parser = UnifiedQuoteParser(self.expansion_parser)
```

### 2.2 Lexer State
**File**: `psh/lexer/state_context.py`

There is no token-by-token state machine: quotes and expansions are
consumed whole by the dedicated parsers, and everything else is dispatched
to recognizers. The only cross-token state is the small `LexerContext`
dataclass, tracking exactly what the recognizers consult:

```python
@dataclass
class LexerContext:
    bracket_depth: int = 0          # [[ ]] nesting
    command_position: bool = True   # affects keyword/assignment recognition
    arithmetic_depth: int = 0       # $((...)) nesting
    posix_mode: bool = False
    case_depth: int = 0             # case..esac nesting
    case_expecting_in: bool = False
    in_case_pattern: bool = False
```

### 2.3 Unified Token System
**Files**: `psh/lexer/token_types.py`, `psh/lexer/token_parts.py`

The lexer produces unified `Token` objects carrying position, quote and
part metadata:
```python
@dataclass
class Token:
    """Unified token class for the shell lexer and parser."""
    type: TokenType
    value: str
    position: int
    end_position: int = 0
    quote_type: Optional[str] = None       # ' or " or None
    line: Optional[int] = None
    column: Optional[int] = None
    adjacent_to_previous: bool = False     # no whitespace before this token
    is_keyword: bool = False               # set by the keyword normalizer
    parts: Optional[List['TokenPart']] = field(default=None)
    fd: Optional[int] = None               # fd prefix (e.g. 2 in 2>file)
    combined_redirect: bool = False        # &> and &>>
```

`TokenPart` (in `psh/lexer/token_parts.py`) records each quoted/expansion
segment of a composite word — this per-part decomposition is what the
parser's `WordBuilder` turns into Word AST nodes.

### 2.4 Unified Architecture Benefits

- **Single Token Class**: one `Token` dataclass throughout lexer, parser and executor — no conversion layers
- **Single Implementation Path**: no feature flags, adapters, or dual code paths
- **Per-Part Quote Fidelity**: `parts` preserves quoting per segment, the foundation of correct expansion
- **Maintainability**: focused implementation without legacy compatibility overhead

### 2.5 Context-Aware Tokenization

The lexer handles context-sensitive tokenization:
- `<` and `>` are operators inside `[[ ]]`, redirections elsewhere
- Keywords like `in` are recognized only in appropriate contexts (case statements, for loops)
- Operators are recognized using length-based lookup for efficiency
- Quote information is preserved for proper expansion later

### 2.6 Composite Token Handling

Adjacent string-like tokens become COMPOSITE tokens:
```bash
echo "hello"world'!' → COMPOSITE["hello", world, '!']
```

This preserves quote information for each part, enabling correct expansion behavior.

## Phase 3: Syntactic Analysis (Parsing)

PSH features a unique dual parser architecture with two complete implementations that demonstrate different parsing paradigms while maintaining near-complete feature parity.

### 3.1 Dual Parser Architecture
**Package**: `psh/parser/`

PSH includes two complete parser implementations for educational comparison:

#### 3.1.1 Recursive Descent Parser (Production)
**Location**: `psh/parser/recursive_descent/`

The recursive descent parser is the primary production parser, using an imperative delegation-based architecture:

**Core Structure:**
- **`recursive_descent/`** - Main package directory
  - **`parser.py`** - Main Parser class with delegation orchestration
  - **`base_context.py`** - ContextBaseParser using ParserContext
  - **`context.py`** - Centralized parser context management
  - **`helpers.py`** - Helper classes and token groups

**Feature Parsers** (`recursive_descent/parsers/`):
- **`commands.py`** - Command and pipeline parsing
- **`statements.py`** - Statement list and control flow parsing
- **`control_structures.py`** - All control structures (if, while, for, case, select)
- **`tests.py`** - Enhanced test expression parsing with regex support
- **`arithmetic.py`** - Arithmetic command and expression parsing
- **`redirections.py`** - I/O redirection parsing
- **`arrays.py`** - Array initialization and assignment parsing
- **`functions.py`** - Function definition parsing

**Support Utilities** (`recursive_descent/support/`):
- **`utils.py`** - Utility functions and heredoc handling
- **`context_factory.py`** - Parser context factory (`create_context()`)
- **`word_builder.py`** - Word AST node construction

#### 3.1.2 Parser Combinator (Educational)
**Location**: `psh/parser/combinators/`

The parser combinator is a functional parser implementation demonstrating elegant compositional parsing:

**Modular Structure:**
- **`core.py`** - Core combinator functions and parser monad
- **`tokens.py`** - Token-level parsers
- **`expansions.py`** - Variable, command substitution, arithmetic expansion
- **`commands.py`** - Simple and compound command parsing
- **`control_structures/`** - Control structures (if, while, for, case, select)
- **`special_commands.py`** - Special constructs (functions, arrays, process substitution)
- **`parser.py`** - Main ShellParserCombinator class
- **`heredoc_processor.py`** - Here document two-pass parsing

**Key Features:**
- **Functional Composition**: Combinators compose to build complex parsers
- **Near-Complete Feature Parity** (~95%): Supports nearly all shell constructs including:
  - Process substitution (`<(cmd)`, `>(cmd)`)
  - Compound commands (subshells, brace groups)
  - Arithmetic commands (`((expr))`)
  - Enhanced test expressions (`[[ ]]`)
  - Arrays and associative arrays
  - Select loops and advanced I/O
- **Educational Value**: Demonstrates functional parsing techniques
- **Parser Selection**: Use `parser-select combinator` builtin to enable

**Public API** (`psh/parser/__init__.py`):
- Clean interface for both parser implementations
- Factory methods for parser creation
- Unified AST output regardless of parser choice

### 3.2 Shared Parser Infrastructure

Both parser implementations share common infrastructure:

#### Parser Configuration System
- **`psh/parser/config.py`** - ParserConfig with parsing-mode, error-handling, and bash-compatibility options (preset constructor `strict_posix()`; derive variants with `clone(**overrides)`)

#### Centralized State Management
- **`psh/parser/recursive_descent/context.py`** - ParserContext class for unified state management
- **`psh/parser/recursive_descent/support/context_factory.py`** - `create_context()` for creating contexts with different configurations

#### AST Validation
AST validation lives in `psh/visitor/` (e.g. `ValidatorVisitor` and `EnhancedValidatorVisitor`), not in the parser; see Section 3.8.

#### Parse Tree Visualization
- **`psh/parser/visualization/`** - Multi-format AST visualization
  - `ast_formatter.py` - Pretty printer for human-readable AST output
  - `dot_generator.py` - Graphviz DOT format for visual diagrams
  - `ascii_tree.py` - ASCII tree renderer for terminal display

### 3.3 Recursive Descent Delegation Architecture

The recursive descent parser orchestrates specialized parsers through delegation with centralized state management:
```python
class Parser(ContextBaseParser):
    """Main parser with delegation to specialized parsers using ParserContext"""
    def __init__(self, tokens: List[Token], config: Optional[ParserConfig] = None):
        # Create or use existing ParserContext
        self.ctx = create_context(tokens, config)
        super().__init__(self.ctx)
        
        # Initialize specialized parsers with shared context
        self.commands = CommandParser(self)
        self.statements = StatementParser(self)
        self.control_structures = ControlStructureParser(self)
        self.redirections = RedirectionParser(self)
        self.arithmetic = ArithmeticParser(self)
        # ... other specialized parsers

    def parse(self) -> Union[CommandList, TopLevel]:
        """Parse the token stream into an AST."""
        ...
```

With `config.collect_errors=True`, errors accumulate in `ctx.errors`
(up to `config.max_errors`) via `ParserContext.add_error()` instead of
raising immediately; `ctx.can_continue_parsing()` decides when to stop.

### 3.4 Grammar Overview

The shell grammar (simplified):
```
top_level    → statement*
statement    → function_def | control_structure | command_list

control_structure → if_stmt | while_stmt | for_stmt | case_stmt | select_stmt
command_list → and_or_list (';' and_or_list)* [';']
and_or_list  → pipeline (('&&' | '||') pipeline)*
pipeline     → command ('|' command)*
command      → simple_command | compound_command

simple_command → word+ redirect* ['&']
compound_command → control_structure redirect* ['&']
```

### 3.5 Dual Parser Benefits

The dual parser architecture provides unique advantages:

**Educational Value:**
- **Comparative Learning**: See the same language parsed two different ways
- **Paradigm Comparison**: Imperative (recursive descent) vs. functional (combinators)
- **Parsing Techniques**: Learn both traditional and modern parsing approaches
- **Production vs. Research**: Production-ready recursive descent and elegant functional combinators

**Technical Benefits:**
- **Near-Complete Feature Parity**: Both parsers support nearly all shell constructs (~95%)
- **Unified AST**: Identical output regardless of parser choice
- **Separation of Concerns**: Each parser module handles focused aspects
- **Enhanced Maintainability**: Modular structure easier to understand and modify
- **Improved Testability**: Both implementations tested against same suite
- **Extensibility**: New features can be implemented in both paradigms

### 3.6 Parser Configuration System

The parser supports comprehensive configuration for different parsing modes and behaviors:

```python
@dataclass
class ParserConfig:
    """Parser configuration options (only fields the parser actually reads)"""
    # Core parsing mode: BASH_COMPAT (default) or STRICT_POSIX
    parsing_mode: ParsingMode = ParsingMode.BASH_COMPAT

    # Error handling: STRICT (stop on first error) or COLLECT
    error_handling: ErrorHandlingMode = ErrorHandlingMode.STRICT
    max_errors: int = 10
    collect_errors: bool = False

    # Language features
    enable_arithmetic: bool = True

    # Bash compatibility
    allow_bash_conditionals: bool = True   # [[ ]]
    allow_bash_arithmetic: bool = True     # (( ))

    @classmethod
    def strict_posix(cls) -> 'ParserConfig':
        """Strict POSIX compliance mode"""
        return cls(
            parsing_mode=ParsingMode.STRICT_POSIX,
            error_handling=ErrorHandlingMode.STRICT,
            allow_bash_conditionals=False,
            allow_bash_arithmetic=False,
        )
```

Derive variants with `config.clone(**overrides)`. Feature checks go
through `is_feature_enabled()` / `should_allow()`, which `getattr` with
a default of `False`, so removed fields safely read as disabled.

### 3.7 Centralized ParserContext

Parser state is managed through a centralized ParserContext:

```python
@dataclass
class ParserContext:
    """Centralized parser state management"""
    # Core parsing state
    tokens: List[Token]
    current: int = 0
    config: ParserConfig = field(default_factory=ParserConfig)

    # Error handling
    errors: List[ParseError] = field(default_factory=list)
    fatal_error: Optional[ParseError] = None

    # Source context
    source_text: Optional[str] = None
    source_lines: Optional[List[str]] = None
```

### 3.8 AST Validation

AST validation is implemented as visitors in `psh/visitor/`, not in the parser. `ValidatorVisitor` (`psh/visitor/validator_visitor.py`) performs basic structural checks, and `EnhancedValidatorVisitor` (`psh/visitor/enhanced_validator_visitor.py`) adds variable tracking, quoting analysis, and security checks. They power the `--validate` CLI option and can be run over any parsed AST.

### 3.9 Parse Tree Visualization

Multiple visualization formats are available for AST inspection:

```python
# Pretty-printed format
formatter = ASTPrettyPrinter(indent_size=2, show_positions=True)
print(formatter.visit(ast))

# Graphviz DOT format for visual diagrams
dot_generator = ASTDotGenerator(compact_nodes=False)
dot_content = dot_generator.visit(ast)

# ASCII tree for terminal display
print(AsciiTreeRenderer.render(ast))

# Integration with shell commands
psh --debug-ast=pretty -c "if true; then echo hi; fi"
parse-tree -f dot "for i in 1 2 3; do echo $i; done"
show-ast "case $var in pattern) echo match;; esac"
```

### 3.10 Error Collection

Multi-error collection is implemented at the `ParserContext` level
(there is no separate recovery subsystem):

```python
# In ParserContext (recursive_descent/context.py)
def add_error(self, error: ParseError) -> None:
    """Add error to the error list, checking for fatal errors."""
    if len(self.errors) < self.config.max_errors:
        self.errors.append(error)
    if (hasattr(error.error_context, 'severity') and
        error.error_context.severity == ErrorSeverity.FATAL):
        self.fatal_error = error

def can_continue_parsing(self) -> bool:
    """Check if parsing can continue."""
    if self.at_end() or self.fatal_error:
        return False
    if self.config.collect_errors:
        return len(self.errors) < self.config.max_errors
    return True
```

With the default `collect_errors=False`, parsing stops on the first
error; with `collect_errors=True`, errors accumulate in `ctx.errors`
up to `max_errors`.

### 3.11 Recursive Descent Implementation

Each grammar rule has a corresponding parse method across specialized parsers:
```python
# In ControlStructureParser
def parse_if_statement(self):
    """Parse if/then/else/fi statement"""
    # Delegate to control structure parser
    
# In CommandParser  
def parse_command(self):
    """Parse simple command with arguments"""
    # Delegate to command parser
```

### 3.12 AST Node Hierarchy
**File**: `psh/ast_nodes/__init__.py`

The AST uses a clean class hierarchy:
```python
# Base classes
class ASTNode: pass
class Statement(ASTNode): pass
class Command(ASTNode): pass

# Commands (can appear in pipelines)
class SimpleCommand(Command): 
    args: List[str]
    redirects: List[Redirect]
    background: bool

class CompoundCommand(Command):
    # Control structures can be used as commands
    pass

# Control structures
class WhileLoop(Statement, CompoundCommand):
    condition: StatementList
    body: StatementList
    redirects: List[Redirect]

class IfConditional(Statement, CompoundCommand):
    condition: StatementList
    then_stmt: StatementList
    elif_parts: List[Tuple[StatementList, StatementList]]
    else_stmt: Optional[StatementList]
```

### 3.13 Canonical AST Data Flow (Words, Values, Redirects)

How shell text becomes runtime values — which node carries the Word AST,
which expansion policy applies, and where the single canonical
implementation lives for command words, assignment values, array
initializers/elements, for/select items, case subjects/patterns, redirect
targets, and process substitution — is documented in
[docs/architecture/ast_data_flow.md](docs/architecture/ast_data_flow.md).
Both parsers always populate the Word fields; the executor raises an
internal error on a missing Word (fallback audit 2026-06-12), and the
deliberately retained fallbacks are pinned by
`tests/unit/executor/test_legacy_ast_fallbacks.py`. Consult that document
before changing expansion or execution semantics: it answers "which code
do I change?" per context.


## Phase 4: Execution

The execution phase traverses the AST and performs the actual work.

### 4.1 Modular Executor Package Architecture
**Directory**: `executor/`

The executor uses a modular package architecture with specialized executors:

#### Package Structure
```
executor/
├── __init__.py          # Public API exports
├── core.py              # Main ExecutorVisitor
├── command.py           # Simple command execution with strategies
├── pipeline.py          # Pipeline execution and process management
├── process_launcher.py  # Unified process creation
├── control_flow.py      # Control structures (if, loops, case, select)
├── array.py             # Array initialization and element operations
├── function.py          # Function definition and execution
├── subshell.py          # Subshell and brace group execution
├── context.py           # ExecutionContext state management
├── strategies.py        # Command type execution strategies
├── child_policy.py      # Fork helper, child signal policy, substitution-child runner
└── enhanced_test_evaluator.py  # Test expression evaluation ([, [[)
```

#### Unified Process Creation

PSH centralizes *job-controlled* process creation in `ProcessLauncher` (commands, pipelines, subshells — anything that becomes a job), eliminating code duplication and ensuring consistent behavior across those fork points. The fork itself and the child-side signal setup are shared by **all** fork sites, including the two that bypass ProcessLauncher by design (command substitution and process substitution, which are not jobs): every site forks via `fork_with_signal_window()` and applies `apply_child_signal_policy()` from `psh/executor/child_policy.py` (v0.312). The two substitution sites additionally run their entire child branch through the shared runner `run_child_shell()` (same module): signal policy, the caller's fd plumbing, child `Shell.for_subshell()` construction, body execution, SystemExit/exception → exit-code mapping, `flush_child_streams()`, and `os._exit()` — the caller supplies only the plumbing and the body.

**File**: `executor/process_launcher.py`

**Key Components**:
```python
class ProcessRole(Enum):
    """Role of process in job control structure"""
    SINGLE = "single"                    # Standalone command
    PIPELINE_LEADER = "pipeline_leader"  # First command in pipeline
    PIPELINE_MEMBER = "pipeline_member"  # Non-first command in pipeline

@dataclass
class ProcessConfig:
    """Configuration for launching a process"""
    role: ProcessRole
    pgid: Optional[int] = None           # Process group to join
    foreground: bool = True              # Foreground vs background
    sync_pipe_r: Optional[int] = None    # Pipeline synchronization (read end)
    sync_pipe_w: Optional[int] = None    # Pipeline synchronization (write end)
    io_setup: Optional[Callable] = None  # I/O redirection callback

class ProcessLauncher:
    """Unified component for all process creation"""

    def launch(self, execute_fn: Callable[[], int],
               config: ProcessConfig) -> Tuple[int, int]:
        """Launch process with proper job control setup.

        Returns (pid, pgid) - process ID and process group ID
        """
        # 1. Fork process
        # 2. Child: Set process group, reset signals, execute function
        # 3. Parent: Set process group (race avoidance), return info
```

**Key Properties**:
- **Single Source of Truth for Job Control**: all job-controlled process creation flows through one component
- **Consistent Signal Handling**: every child applies `apply_child_signal_policy()` via the required SignalManager
- **Proper Synchronization**: Pipe-based synchronization for pipeline process groups
- **Unified Job Control**: Consistent process group setup and terminal control transfer
- **Shared Instance**: A single `ProcessLauncher` lives on the `Shell` object (`shell.process_launcher`, since v0.271.0); all call sites use it rather than constructing their own

**Used By**:
- `PipelineExecutor` - All pipeline commands
- `ExternalExecutionStrategy` - External commands
- `BuiltinExecutionStrategy` - Background builtins
- `SubshellExecutor` - Foreground/background subshells and brace groups

For the history of how this design evolved (pipeline synchronization, SIGCHLD handling, terminal control hardening), see the v0.103.0-v0.104.0 entries in `CHANGELOG.md`.

#### Core Architecture
```python
class ExecutorVisitor(ASTVisitor[int]):
    """Main executor that delegates to specialized components"""
    
    def __init__(self, shell: Shell):
        super().__init__()
        self.shell = shell
        self.context = ExecutionContext()
        
        # Initialize specialized executors
        self.command_executor = CommandExecutor(shell, self)
        self.pipeline_executor = PipelineExecutor(shell) 
        self.control_flow_executor = ControlFlowExecutor(shell)
        self.array_executor = ArrayOperationExecutor(shell)
        self.function_executor = FunctionOperationExecutor(shell)
        self.subshell_executor = SubshellExecutor(shell)
    
    def visit_SimpleCommand(self, node: SimpleCommand) -> int:
        # Delegate to CommandExecutor
        return self.command_executor.execute(node, self.context)
    
    def visit_Pipeline(self, node: Pipeline) -> int:
        # Delegate to PipelineExecutor
        return self.pipeline_executor.execute(node, self.context, self)
```

#### Execution Context
```python
@dataclass
class ExecutionContext:
    """Encapsulates execution state for cleaner parameter passing"""
    in_pipeline: bool = False
    in_subshell: bool = False
    in_forked_child: bool = False
    loop_depth: int = 0
    current_function: Optional[str] = None
    pipeline_context: Optional[PipelineContext] = None
    background_job: Optional[Job] = None
```

### 4.2 Specialized Executors

#### CommandExecutor
Handles simple command execution with the Strategy pattern; the
`NAME=value` assignment sub-domain (extraction, value expansion,
application, restoration — and the POSIX ordering contract) is owned by
`CommandAssignments` in `psh/executor/command_assignments.py`:
```python
class CommandExecutor:
    def __init__(self, shell: Shell, visitor: ExecutorVisitor):
        self.visitor = visitor          # runs function bodies / compounds
        self.assignments = CommandAssignments(shell)
        self.strategies = [
            BuiltinExecutionStrategy(),
            FunctionExecutionStrategy(),
            ExternalExecutionStrategy()
        ]

    def execute(self, node: SimpleCommand, context: ExecutionContext) -> int:
        # Extract assignments (pure assignments short-circuit)
        # Expand command words (before assignments apply, per POSIX)
        # Apply prefix assignments
        # Find appropriate strategy and execute
        # Restore assignments (unless POSIX special builtin)
```

#### PipelineExecutor
Manages pipeline execution with process forking and pipe management:
```python
class PipelineExecutor:
    def execute(self, node: Pipeline, context: ExecutionContext, 
                visitor: ASTVisitor[int]) -> int:
        # Create pipes
        # Fork processes
        # Set up process groups
        # Manage job control
        # Wait for completion
```

#### ControlFlowExecutor
Handles all control structures:
- If/elif/else conditionals
- While and for loops (including C-style)
- Case statements
- Select loops
- Break and continue statements

#### FunctionOperationExecutor
Manages function definition and execution:
```python
class FunctionOperationExecutor:
    def execute_function_call(self, name: str, args: List[str], 
                             context: ExecutionContext,
                             visitor: ASTVisitor[int]) -> int:
        # Set up positional parameters
        # Manage function stack
        # Execute function body
        # Handle return builtin
```

### 4.3 Command Execution Strategy Pattern

The CommandExecutor uses strategies for different command types:

```python
class ExecutionStrategy(ABC):
    @abstractmethod
    def can_execute(self, cmd_name: str, shell: Shell) -> bool:
        pass
    
    @abstractmethod
    def execute(self, cmd_name: str, args: List[str], 
                shell: Shell, context: ExecutionContext) -> int:
        pass

class BuiltinExecutionStrategy(ExecutionStrategy):
    # Handles builtin commands

class FunctionExecutionStrategy(ExecutionStrategy):
    # Handles shell functions

class ExternalExecutionStrategy(ExecutionStrategy):
    # Handles external commands with fork/exec
```

### 4.4 Pipeline Execution

Pipeline execution is handled by the PipelineExecutor:

```python
def _execute_pipeline(self, node: Pipeline, context: ExecutionContext,
                     visitor: ASTVisitor[int]) -> int:
    if len(node.commands) == 1:
        # Single command optimization
        return visitor.visit(node.commands[0])
    
    # Multi-command pipeline
    pipeline_ctx = PipelineContext(self.job_manager)
    
    # Create pipes
    for i in range(len(node.commands) - 1):
        pipeline_ctx.add_pipe()
    
    # Fork processes for each command
    for i, command in enumerate(node.commands):
        pid = os.fork()
        if pid == 0:
            # Child: set up pipes and execute
            self._setup_pipeline_redirections(i, pipeline_ctx)
            exit_status = visitor.visit(command)
            os._exit(exit_status)
        else:
            # Parent: track process
            pipeline_ctx.add_process(pid)
    
    # Create job and wait for completion
    job = self.job_manager.create_job(pgid, command_string)
    return self._wait_for_foreground_pipeline(job, node)
```

### 4.5 Benefits of Modular Architecture

The refactored executor package provides:

1. **Separation of Concerns**: Each executor handles one aspect of execution
2. **Reduced Complexity**: Core visitor is a thin coordinator that delegates to specialized modules
3. **Improved Testability**: Isolated components with clear interfaces
4. **Better Maintainability**: Focused modules easier to understand and modify
5. **Extensibility**: New execution features can be added to specific modules
6. **Clean Delegation**: Main visitor coordinates specialized executors

### 4.6 Execution Statistics

- **Refactored Package**: 14 modules with clear responsibilities (originally a single ~2000-line ExecutorVisitor)
- **New Architecture**: Strategy pattern for commands, delegation for all operations

## Phase 5: Expansion

Expansions happen during execution in POSIX-specified order.

### 5.1 Expansion Manager
**Files**: `expansion/manager.py`, `expansion/word_expander.py`

`ExpansionManager` (manager.py) orchestrates; the engine is
`WordExpander.expand(word, policy)` (word_expander.py), which walks each
`Word` AST node — per-part quote context (not string type tags) decides
which expansions apply, and a named `WordExpansionPolicy` (COMMAND_ARGUMENT,
DECLARATION_ASSIGNMENT, LOOP_ITEM, ARRAY_INIT_ELEMENT, ASSOC_INIT_ELEMENT)
names what the surrounding context permits:

```python
def expand_arguments(self, command: SimpleCommand, ...) -> List[str]:
    """Expand a command's Word AST nodes following POSIX rules."""
    # For each Word in command.words, WordExpander.expand applies:
    # 1. Tilde expansion       (first unquoted literal part only)
    # 2. Variable expansion    (unquoted and double-quoted parts)
    # 3. Command substitution  (unquoted and double-quoted parts)
    # 4. Arithmetic expansion  ($((...)) parts)
    # 5. Word splitting        (only fields from unquoted expansions)
    # 6. Pathname expansion    (only unquoted parts)
    # Quote removal falls out of the Word part structure itself.
```

The full policy table (which entry point applies in which context —
command words, assignment values, array elements, for/select items, case
patterns, redirect targets) lives in `docs/architecture/ast_data_flow.md`.

### 5.2 Variable Expansion
**Files**: `expansion/variable.py`, `expansion/parameter_expansion.py`

Handles all forms of variable expansion:
- Simple: `$var`, `${var}`
- Special parameters: `$?`, `$$`, `$!`, `$#`, `$@`, `$*`
- Positional: `$1`, `$2`, etc.
- Advanced parameter expansion:
  - Length: `${#var}`
  - Substring: `${var:offset:length}`
  - Pattern removal: `${var#pattern}`, `${var%pattern}`
  - Substitution: `${var/pattern/replacement}`
  - Case modification: `${var^^}`, `${var,,}`

### 5.3 Command Substitution
**File**: `expansion/command_sub.py`

Executes commands and captures output. `CommandSubstitution.execute()`
forks a real child process (via `fork_with_signal_window()`, like every
other fork site; the child branch runs through `run_child_shell()`,
which applies the child signal policy) and reads its output through a
pipe:

```python
class CommandSubstitution:
    def execute(self, cmd_sub: str) -> str:
        """Execute $(...) or `...` and return its output."""
        # Parent: create pipe, fork, read all output, waitpid,
        #         record exit status (last_exit_code / last_cmdsub_status)
        # Child:  apply child signal policy, dup2 stdout to the pipe,
        #         build a child shell with Shell.for_subshell(parent),
        #         run the command, flush streams, os._exit(status)
        ...
        return output.rstrip('\n')   # strip trailing newlines (POSIX)
```

A real fork (not in-process evaluation) is what makes subshell semantics
correct: variable assignments, `cd`, `exit` and traps inside `$(...)`
cannot leak into the parent.

### 5.4 Arithmetic Expansion
**Files**: `expansion/manager.py`, `expansion/arithmetic/`

Evaluates arithmetic expressions. `ExpansionManager.execute_arithmetic_expansion()`
strips the `$((`...`))` delimiters and delegates to the arithmetic
subsystem:

```python
def execute_arithmetic_expansion(self, expr: str) -> int:
    """Evaluate the expression inside $((...))."""
    # Extract expression text, then evaluate with the arithmetic
    # tokenizer/parser/evaluator in expansion/arithmetic/
    return evaluate_arithmetic(expression, self.shell)
```

## Phase 6: I/O Redirection

I/O redirections are applied around command execution.

### 6.1 Redirection Manager
**File**: `io_redirect/manager.py`

Manages all forms of redirection:
```python
def apply_redirections(self, redirects: List[Redirect]) -> List[Tuple[int, int]]:
    """Apply redirections and return saved (fd, saved_copy) pairs"""
    saved_fds = []

    for redirect in redirects:
        if redirect.type == '>':
            # Output redirection
            fd = redirect.source_fd or 1
            saved_fds.append((fd, os.dup(fd)))
            target_fd = os.open(redirect.target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            os.dup2(target_fd, fd)
            os.close(target_fd)
        # ... handle other redirection types

    return saved_fds
```

### 6.2 Here Documents
**File**: `io_redirect/file_redirect.py` (`FileRedirector`)

Heredoc content is collected at parse time and attached to the redirect node; at execution time `FileRedirector.redirect_heredoc()` expands the content (unless the delimiter was quoted) and points stdin at it via an anonymous temporary file:
```python
def redirect_heredoc(self, redirect):
    """Point stdin at the heredoc content. Returns the expanded content."""
    content = redirect.heredoc_content or ''
    if content and not getattr(redirect, 'heredoc_quoted', False):
        content = self.shell.expansion_manager.expand_string_variables(content)
    self._stdin_from_content(content)  # anonymous temp file dup2'd to fd 0
    return content
```

A temporary file (rather than a pipe) is used so heredocs larger than the kernel pipe buffer cannot deadlock — the same approach bash takes.

### 6.3 Process Substitution
**File**: `io_redirect/process_sub.py`

Process substitution is handled by a single module-level function that serves as the source of truth for all process substitution creation (argument-position, redirect-position for externals, and redirect-position for builtins):
```python
def create_process_substitution(cmd_str: str, direction: str, shell) -> Tuple[int, str, int]:
    """Create a process substitution, returning (parent_fd, fd_path, child_pid).

    Handles the fork/pipe/exec sequence. The caller decides where to
    track the returned FD and PID for cleanup.
    """
    # Creates pipe, clears close-on-exec, forks child
    # Child: resets signals, redirects stdio, executes command
    # Parent: returns (parent_fd, "/dev/fd/{fd}", child_pid)
```

`ProcessSubstitutionHandler` wraps this function for argument-position usage and tracks FDs/PIDs for cleanup. The `FileRedirector` and `IOManager` also call `create_process_substitution()` for redirect-position usage, tracking through the same handler.

## Component Communication

### State Management
**Files**: `core/state.py`, `core/scope.py`

All components share state through a centralized `ShellState` object:
- Environment variables
- Shell variables with scope management
- Positional parameters
- Process information
- Debug flags
- Shell options

### Manager Pattern

Components are organized as managers that coordinate related functionality:
- `ExpansionManager` - All expansions
- `IOManager` - All I/O operations
- `InteractiveManager` - Interactive features
- `ScriptManager` - Script execution

### Exception-Based Control Flow

Special exceptions handle control flow:
- `LoopBreak` - Break statement
- `LoopContinue` - Continue statement  
- `FunctionReturn` - Return from function
- `SystemExit` - Exit shell

## Performance Considerations

### Efficient Tokenization
- Single forward pass with minimal backtracking
- Length-based operator lookup
- Minimal string concatenation

### Optimized Parsing
- Single-pass recursive descent
- Minimal lookahead
- Efficient token consumption

### Smart Expansion
- Lazy evaluation where possible
- Caching of expanded values
- Minimal subprocess creation

### Visitor Pattern Benefits
- Direct method dispatch via method cache
- No intermediate representations
- Minimal object allocation

## Educational Value

The architecture prioritizes clarity and correctness for learning:

**Dual Parser Paradigms:**
- Compare imperative (recursive descent) vs. functional (combinators) parsing
- See the same shell language parsed two completely different ways
- Learn both traditional and modern parsing techniques
- Understand trade-offs between different architectural approaches

**Clean Architecture:**
- Each phase is clearly separated (lexing, parsing, expansion, execution)
- Algorithms follow standard compiler techniques
- Code is heavily documented with educational focus
- Complex features are broken into understandable pieces
- Modular design allows studying individual components in isolation

## Current Architecture Capabilities

PSH's architecture provides comprehensive shell functionality through clean, modular design:

### Dual Parser System
- **Two Complete Implementations**: Recursive descent (production) and parser combinator (educational)
- **Near-Complete Feature Parity**: Both parsers support nearly all shell constructs (~95%)
- **Educational Comparison**: Learn both imperative and functional parsing approaches
- **Unified Output**: Identical AST regardless of parser choice
- **Parser Selection**: Runtime switchable with `parser-select combinator` builtin

### Comprehensive Parser Features
- **Configuration System**: ParserConfig options for POSIX and bash-compat modes
- **Error Recovery**: Multi-error collection with fatal-error short-circuiting
- **Visualization**: Pretty-print, DOT graphs, and ASCII tree rendering
- **Centralized State**: ParserContext manages all parser state consistently

### Modular Execution Engine
- **Specialized Executors**: Separate modules for commands, pipelines, control flow, arrays, functions
- **Strategy Pattern**: Flexible command execution (builtins, functions, external)
- **Clean Delegation**: Thin core visitor coordinating focused executor modules
- **Visitor Pattern**: Extensible AST traversal for execution and analysis

### Unified Lexer System
- **Recognizer Dispatch**: Robust tokenization via priority-ordered recognizers
- **Unified Tokens**: Built-in position tracking, quote metadata, and part decomposition
- **Dedicated Sub-Parsers**: Quotes and expansions consumed whole, preserving structure
- **Context Awareness**: `LexerContext` tracks command position, `[[ ]]`/case/arithmetic nesting

### Component Organization
- **Clear Boundaries**: Each subsystem (lexer, parser, executor, expansion) is independent
- **Manager Pattern**: Coordinated functionality through manager classes
- **POSIX Compliance**: ~98% compliance with proper expansion ordering
- **Testability**: Comprehensive test suite with 5,500+ tests

## Known Limitations

1. **Deep Recursion**: Command substitution in recursive functions can hit Python's stack limit due to the multiple layers of function calls per shell recursion level.

(The former limitation here — `case` patterns with a bare `)` inside `$(...)` broke the paren-counting extent detection — was fixed by the grammar-aware extent scanner, `find_command_substitution_end` in `psh/lexer/cmdsub_scanner.py`; its docstring documents the design and the remaining bash divergences.)

## Future Enhancements

1. **Optimization Visitors**: Performance analysis and optimization passes
2. **Enhanced Analysis Tools**: Extended security and code quality analysis
3. **Incremental Parsing**: Reparse only changed portions for better performance
4. **Parallel Execution**: Execute independent commands concurrently
5. **Advanced AST Transformations**: Code optimization and refactoring passes
6. **Language Server Protocol**: LSP support for shell script editing
7. **Interactive Debugging**: Step-through debugging of shell scripts
8. **Parser Combinator Optimization**: Performance improvements for combinator implementation