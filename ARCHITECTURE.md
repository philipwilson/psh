# PSH Architecture Guide

## Overview

Python Shell (psh) is designed with a clean, component-based architecture that separates concerns and makes the codebase easy to understand, test, and extend. The shell follows a traditional interpreter pipeline: lexing → parsing → expansion → execution, with each phase carefully designed for educational clarity and correctness.

**Current Version**: 0.192.2

**Note:** For LLM-optimized architecture documentation, see `ARCHITECTURE.llm`

**Key Architectural Features**:
- **Dual Parser Architecture**: Two complete parser implementations for educational comparison
  - **Recursive Descent Parser**: Production parser with modular package structure in `psh/parser/recursive_descent/`
  - **Parser Combinator**: Functional parser with near-complete feature parity (~95%) in `psh/parser/combinators/`
  - **Parser Selection**: Switch between implementations with `parser-select combinator` builtin
  - **Educational Value**: Compare imperative vs. functional parsing approaches
- **Unified Lexer Architecture**: State machine lexer with modular architecture
  - **Single Token System**: Unified Token class with built-in metadata and context information
  - **Enhanced Features Standard**: Context tracking, semantic analysis, and error recovery built-in
  - **Modular Recognition**: Priority-based token recognizer system
  - **Clean API**: Simplified interface with no compatibility overhead
- **Enhanced Parser System**: Comprehensive configuration and validation
  - **Parser Configuration**: Multiple parsing modes (POSIX, bash-compat, educational)
  - **AST Validation**: Semantic analysis with symbol table management
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
│                   State Machine Lexer                           │
│                                                                 │
│  Character Stream → Finite State Machine → Rich Token Stream   │
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
**File**: `input_preprocessing.py`

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
**File**: `history_expansion.py`

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

The lexer converts character streams into meaningful tokens using a state machine approach.

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
- **`psh/lexer/pure_helpers.py`** - 15+ stateless helper functions

#### Quote and Expansion Parsing
- **`psh/lexer/quote_parser.py`** - Unified quote parsing with configurable rules
- **`psh/lexer/expansion_parser.py`** - All expansion types ($VAR, ${VAR}, $(...), $((...)))

#### Token Recognition
- **`psh/lexer/recognizers/`** - Modular token recognition system
  - `base.py` - TokenRecognizer abstract interface
  - `operator.py` - Shell operators with context awareness
  - `keyword.py` - Shell keywords with position validation
  - `literal.py` - Words, identifiers, and numbers
  - `whitespace.py` - Whitespace handling
  - `comment.py` - Comment recognition
  - `registry.py` - Priority-based recognizer dispatch

The architecture combines all components while maintaining backward compatibility:
```python
class ModularLexer:
    """Lexer integrating all refactored components"""
    def __init__(self, input_string: str, config: Optional[LexerConfig] = None):
        self.position_tracker = PositionTracker(input_string)
        self.state_manager = StateManager()
        self.registry = RecognizerRegistry()
        self.expansion_parser = ExpansionParser(self.config)
        self.quote_parser = UnifiedQuoteParser(self.expansion_parser)
```

### 2.2 State Machine Architecture

The lexer uses a finite state machine with these states:
```python
class LexerState(Enum):
    NORMAL = "NORMAL"
    IN_WORD = "IN_WORD"
    IN_SINGLE_QUOTE = "IN_SINGLE_QUOTE"
    IN_DOUBLE_QUOTE = "IN_DOUBLE_QUOTE"
    IN_BACKQUOTE = "IN_BACKQUOTE"
    IN_COMMENT = "IN_COMMENT"
    AFTER_DOLLAR = "AFTER_DOLLAR"
    IN_VARIABLE = "IN_VARIABLE"
    IN_COMMAND_SUB = "IN_COMMAND_SUB"
    IN_ARITHMETIC = "IN_ARITHMETIC"
    IN_PARAM_EXPANSION = "IN_PARAM_EXPANSION"
```

### 2.3 Unified Token System
**Files**: `token_types.py`, `psh/lexer/token_parts.py`

The lexer produces unified `Token` objects with built-in metadata and context information:
```python
@dataclass
class Token:
    """Unified token class with metadata and context information (formerly EnhancedToken)."""
    type: TokenType
    value: str
    position: int
    end_position: int = 0
    quote_type: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    metadata: Optional['TokenMetadata'] = field(default=None)
    parts: Optional[List['TokenPart']] = field(default=None)
    
    def add_context(self, context: TokenContext):
        """Add context information to token metadata."""
        
    def has_context(self, context: TokenContext) -> bool:
        """Check if token has specific context."""
        
    def is_in_test_context(self) -> bool:
        """Check if token is in test expression context."""
```

### 2.4 Unified Architecture Benefits

The unified lexer architecture provides numerous advantages:

#### Unified Token System
- **Single Token Class**: Token class includes metadata and enhanced functionality by default
- **Built-in Context Tracking**: All tokens have context information for semantic analysis
- **Metadata Integration**: TokenMetadata and context tracking built into every token
- **No Conversion Overhead**: Direct creation and usage without compatibility layers

#### Simplified Architecture  
- **Single Implementation Path**: Enhanced lexer features now standard throughout PSH
- **Eliminated Compatibility Code**: Removed feature flags, adapters, and dual code paths
- **30% API Reduction**: Token class unification significantly reduced API surface
- **Clean Codebase**: Focused implementation without legacy compatibility overhead

#### Enhanced Features Standard
- **Context Tracking**: Tokens know their lexical context (command position, test expression, etc.)
- **Semantic Analysis**: Built-in semantic type classification for tokens
- **Error Recovery**: Comprehensive error detection and suggestions
- **Rich Metadata**: Position, line/column tracking, and part decomposition

Overall benefits:
- **Performance**: No compatibility overhead, single optimized code path
- **Maintainability**: Simplified codebase with consistent token handling
- **Reliability**: Enhanced error detection and recovery standard for all users
- **Future Development**: Easier to add features without compatibility concerns

### 2.5 Context-Aware Tokenization

The lexer handles context-sensitive tokenization:
- `<` and `>` are operators inside `[[ ]]`, redirections elsewhere
- Keywords like `in` are recognized only in appropriate contexts
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
- **`context_factory.py`** - Parser context factory
- **`factory.py`** - Parser factory with preset configurations
- **`word_builder.py`** - Word AST node construction

#### 3.1.2 Parser Combinator (Educational)
**Location**: `psh/parser/combinators/`

The parser combinator is a functional parser implementation demonstrating elegant compositional parsing:

**Modular Structure:**
- **`core.py`** - Core combinator functions and parser monad
- **`tokens.py`** - Token-level parsers
- **`expansions.py`** - Variable, command substitution, arithmetic expansion
- **`commands.py`** - Simple and compound command parsing
- **`control.py`** - Control structures (if, while, for, case, select)
- **`special.py`** - Special constructs (functions, arrays, here documents)
- **`parser.py`** - Main ShellParserCombinator class
- **`heredoc.py`** - Here document two-pass parsing

**Key Features:**
- **Functional Composition**: Combinators compose to build complex parsers
- **100% Feature Parity**: Supports all shell constructs including:
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
- **`psh/parser/config.py`** - ParserConfig with 14 configuration fields
- **`psh/parser/recursive_descent/support/factory.py`** - ParserFactory with preset configurations

#### Centralized State Management
- **`psh/parser/recursive_descent/context.py`** - ParserContext class for unified state management
- **`psh/parser/recursive_descent/support/context_factory.py`** - Factory for creating contexts with different configurations

#### AST Validation System
- **`psh/parser/validation/`** - Complete validation package
  - `semantic_analyzer.py` - SemanticAnalyzer using visitor pattern
  - `validation_rules.py` - Modular validation rules system
  - `symbol_table.py` - Symbol table for semantic analysis
  - `warnings.py` - Warning system with severity levels
  - `validation_pipeline.py` - Validation orchestration

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
        self.ctx = ParserContextFactory.create(tokens, config)
        super().__init__(self.ctx)
        
        # Initialize specialized parsers with shared context
        self.commands = CommandParser(self)
        self.statements = StatementParser(self)
        self.control_structures = ControlStructureParser(self)
        self.redirections = RedirectionParser(self)
        self.arithmetic = ArithmeticParser(self)
        # ... other specialized parsers

    def parse_with_error_collection(self) -> MultiErrorParseResult:
        """Parse with enhanced error collection and recovery"""
        if self.ctx.config.collect_errors:
            # Collect multiple errors for better user experience
            return self._parse_with_recovery()
        return self.parse()
```

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
    """Parser configuration with 14 fields"""
    # Core parsing mode
    parsing_mode: ParsingMode = ParsingMode.BASH_COMPAT

    # Error handling
    error_handling: ErrorHandlingMode = ErrorHandlingMode.STRICT
    max_errors: int = 10
    collect_errors: bool = False
    enable_error_recovery: bool = False
    show_error_suggestions: bool = True

    # Language features
    enable_arithmetic: bool = True

    # Bash compatibility
    allow_bash_conditionals: bool = True
    allow_bash_arithmetic: bool = True

    # Development and debugging
    trace_parsing: bool = False
    profile_parsing: bool = False
    enable_validation: bool = False
    enable_semantic_analysis: bool = True
    enable_validation_rules: bool = True

    @classmethod
    def strict_posix(cls) -> 'ParserConfig':
        """Strict POSIX compliance mode"""
        return cls(
            parsing_mode=ParsingMode.STRICT_POSIX,
            allow_bash_conditionals=False,
            allow_bash_arithmetic=False,
        )

    @classmethod
    def permissive(cls) -> 'ParserConfig':
        """Permissive mode with error tolerance"""
        return cls(
            parsing_mode=ParsingMode.PERMISSIVE,
            error_handling=ErrorHandlingMode.RECOVER,
            max_errors=50,
            collect_errors=True,
            enable_error_recovery=True,
        )
```

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
    error_recovery_mode: bool = False

    # Parsing context
    nesting_depth: int = 0
    scope_stack: List[str] = field(default_factory=list)

    # Special parsing state
    in_case_pattern: bool = False
    in_arithmetic: bool = False
    in_test_expr: bool = False
    in_function_body: bool = False
    in_command_substitution: bool = False

    # Control flow state
    loop_depth: int = 0
    function_depth: int = 0

    # Source context
    source_text: Optional[str] = None

    # Performance tracking
    profiler: Optional[ParserProfiler] = None
```

### 3.8 AST Validation and Semantic Analysis

The parser includes comprehensive AST validation and semantic analysis:

```python
class SemanticAnalyzer(ASTVisitor[None]):
    """Perform semantic analysis on parsed AST"""
    
    def __init__(self):
        self.symbol_table = SymbolTable()
        self.issues: List[Issue] = []
        self.warnings: List[Warning] = []
    
    def visit_FunctionDef(self, node: FunctionDef) -> None:
        """Validate function definition"""
        if self.symbol_table.has_function(node.name):
            self.issues.append(Issue(
                f"Function '{node.name}' already defined",
                node.position,
                Severity.ERROR
            ))
        
        # Track function context for return validation
        self.symbol_table.enter_function(node.name)
        self.visit(node.body)
        self.symbol_table.exit_function()

# Validation rules system
class NoEmptyBodyRule(ValidationRule):
    def validate(self, node: ASTNode, context: ValidationContext) -> List[Issue]:
        if isinstance(node, (WhileLoop, ForLoop)):
            if not node.body or not node.body.statements:
                return [Issue("Empty loop body", node.position, Severity.WARNING)]
        return []
```

### 3.9 Parse Tree Visualization

Multiple visualization formats are available for AST inspection:

```python
# Pretty-printed format
formatter = ASTPrettyPrinter(indent=2, show_positions=True)
print(formatter.visit(ast))

# Graphviz DOT format for visual diagrams
dot_generator = ASTDotGenerator(compact=False)
dot_content = dot_generator.visit(ast)

# ASCII tree for terminal display
tree_renderer = ASTAsciiTreeRenderer(style='standard')
print(tree_renderer.visit(ast))

# Integration with shell commands
psh --debug-ast=pretty -c "if true; then echo hi; fi"
parse-tree -f dot "for i in 1 2 3; do echo $i; done"
show-ast "case $var in pattern) echo match;; esac"
```

### 3.10 Enhanced Error Recovery

Advanced error recovery strategies provide better user experience:

```python
class ErrorCollector:
    """Collect multiple parse errors for batch reporting"""
    
    def add_error(self, error: ParseError) -> bool:
        """Add error and determine if parsing should continue"""
        self.errors.append(error)
        
        # Check for fatal errors
        if error.is_fatal or len(self.errors) >= self.max_errors:
            return False
        
        return True

def panic_mode_recovery(self, sync_tokens: Set[TokenType]):
    """Recover by skipping to synchronization points"""
    self.ctx.error_recovery_mode = True
    
    while not self.ctx.at_end() and not self.ctx.match(*sync_tokens):
        self.ctx.advance()
    
    self.ctx.error_recovery_mode = False
```

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
**File**: `ast_nodes.py`

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


## Phase 4: Execution

The execution phase traverses the AST and performs the actual work.

### 4.1 Modular Executor Package Architecture
**Directory**: `executor/`

The executor uses a modular package architecture with specialized executors:

#### Package Structure
```
executor/
├── __init__.py          # Public API exports
├── core.py              # Main ExecutorVisitor (~312 lines, down from ~2000)
├── command.py           # Simple command execution with strategies
├── pipeline.py          # Pipeline execution and process management
├── process_launcher.py  # Unified process creation
├── control_flow.py      # Control structures (if, loops, case, select)
├── array.py             # Array initialization and element operations
├── function.py          # Function definition and execution
├── subshell.py          # Subshell and brace group execution
├── context.py           # ExecutionContext state management
├── strategies.py        # Command type execution strategies
├── child_policy.py      # Child process signal/cleanup policy
└── test_evaluator.py    # Test expression evaluation ([, [[)
```

#### Unified Process Creation (NEW in v0.103.0)

PSH uses a centralized `ProcessLauncher` component for all process creation, eliminating code duplication and ensuring consistent behavior across all fork points:

**File**: `executor/process_launcher.py` (~365 lines)

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

**Benefits**:
- **Single Source of Truth**: All process creation flows through one component
- **Eliminates Duplication**: Replaced ~150 lines of duplicated code across 6 fork locations
- **Consistent Signal Handling**: Centralized signal reset via required SignalManager
- **Proper Synchronization**: Implements pipe-based synchronization for pipelines (C1)
- **Unified Job Control**: Consistent process group setup and terminal control transfer
- **Clean Architecture**: Removed backward compatibility code in v0.104.0 (-29 lines)

**Used By**:
- `PipelineExecutor` - All pipeline commands
- `ExternalExecutionStrategy` - External commands
- `BuiltinExecutionStrategy` - Background builtins
- `SubshellExecutor` - Foreground/background subshells and brace groups

**Critical Improvements** (implemented in v0.103.0):
1. **C1: Pipe-based Pipeline Synchronization**: Replaces polling with atomic pipe-based coordination
2. **C2: Self-pipe SIGCHLD Handler**: Moves SIGCHLD work out of signal context
3. **C3: Unified Process Creation**: Single ProcessLauncher for all forks

**Signal Management & Terminal Control** (completed in v0.104.0):
1. **H1: TTY Detection & Graceful Degradation**: Proper terminal capability detection
2. **H2: Signal Disposition Tracking**: Track signal handler state across job transitions
3. **H3: Centralized Child Signal Reset**: SignalManager.reset_child_signals() required (no fallback)
4. **H4: Unified Foreground Job Cleanup**: JobManager.restore_shell_foreground() consolidation
5. **H5: Surface Terminal Control Failures**: Explicit error handling for tcsetpgrp() failures

**Architecture Notes** (v0.104.0):
- ProcessLauncher requires `signal_manager` parameter (no longer Optional)
- All 4 instantiation sites simplified to direct access: `shell.interactive_manager.signal_manager`
- Removed fallback `_reset_child_signals()` method (dead code elimination)
- Benefits: Cleaner code, clearer contract, -29 lines of backward compatibility code

#### Core Architecture
```python
class ExecutorVisitor(ASTVisitor[int]):
    """Main executor that delegates to specialized components"""
    
    def __init__(self, shell: Shell):
        super().__init__()
        self.shell = shell
        self.context = ExecutionContext()
        
        # Initialize specialized executors
        self.command_executor = CommandExecutor(shell)
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
Handles simple command execution with the Strategy pattern:
```python
class CommandExecutor:
    def __init__(self, shell: Shell):
        self.strategies = [
            BuiltinExecutionStrategy(),
            FunctionExecutionStrategy(),
            ExternalExecutionStrategy()
        ]
    
    def execute(self, node: SimpleCommand, context: ExecutionContext) -> int:
        # Expand arguments
        # Extract assignments
        # Find appropriate strategy
        # Execute command
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
2. **Reduced Complexity**: Core visitor reduced from ~2000 to ~312 lines (84% reduction)
3. **Improved Testability**: Isolated components with clear interfaces
4. **Better Maintainability**: Focused modules easier to understand and modify
5. **Extensibility**: New execution features can be added to specific modules
6. **Clean Delegation**: Main visitor coordinates specialized executors

### 4.6 Execution Statistics

- **Original ExecutorVisitor**: ~1994 lines in single file
- **Refactored Package**: 13 modules with clear responsibilities
- **Core Module**: ~312 lines (84% reduction)
- **New Architecture**: Strategy pattern for commands, delegation for all operations

## Phase 5: Expansion

Expansions happen during execution in POSIX-specified order.

### 5.1 Expansion Manager
**File**: `expansion/manager.py`

Orchestrates all expansions in the correct order:

```python
def expand_argument(self, arg: str, arg_type: str) -> List[str]:
    """Expand a single argument following POSIX rules"""
    # 1. Tilde expansion (if unquoted)
    if should_expand_tilde(arg, arg_type):
        arg = self.tilde_expander.expand(arg)
    
    # 2. Parameter/variable expansion
    arg = self.variable_expander.expand(arg)
    
    # 3. Command substitution
    arg = self.expand_command_substitution(arg)
    
    # 4. Arithmetic expansion
    arg = self.expand_arithmetic(arg)
    
    # 5. Word splitting (if unquoted)
    if should_split(arg, arg_type):
        words = self.split_words(arg)
    else:
        words = [arg]
    
    # 6. Pathname expansion (if unquoted)
    expanded = []
    for word in words:
        if should_glob(word, arg_type):
            expanded.extend(self.glob_expander.expand(word))
        else:
            expanded.append(word)
    
    # 7. Quote removal
    return [self.remove_quotes(w) for w in expanded]
```

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

Executes commands and captures output:
```python
def expand_command_substitution(self, text: str) -> str:
    """Expand $(...) and `...` in text"""
    # Create subshell with inherited state
    subshell = Shell(parent_shell=self.shell)
    
    # Execute command and capture output
    output = subshell.run_command(command, capture_output=True)
    
    # Strip trailing newlines
    return output.rstrip('\n')
```

### 5.4 Arithmetic Expansion
**File**: `arithmetic.py`

Evaluates arithmetic expressions:
```python
def expand_arithmetic(self, text: str) -> str:
    """Expand $((...)) in text"""
    # Extract expression
    expr = text[3:-2]  # Remove $(( and ))
    
    # Evaluate using arithmetic subsystem
    result = evaluate_arithmetic(expr, self.shell)
    
    return str(result)
```

## Phase 6: I/O Redirection

I/O redirections are applied around command execution.

### 6.1 Redirection Manager
**File**: `io_redirect/manager.py`

Manages all forms of redirection:
```python
def apply_redirections(self, redirects: List[Redirect]) -> Dict[int, int]:
    """Apply redirections and return saved file descriptors"""
    saved_fds = {}
    
    for redirect in redirects:
        if redirect.type == '>':
            # Output redirection
            fd = redirect.source_fd or 1
            saved_fds[fd] = os.dup(fd)
            target_fd = os.open(redirect.target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            os.dup2(target_fd, fd)
            os.close(target_fd)
        # ... handle other redirection types
    
    return saved_fds
```

### 6.2 Here Documents
**File**: `io_redirect/heredoc.py`

Here documents create temporary files:
```python
def setup_heredoc(self, delimiter: str, content: str, strip_tabs: bool) -> int:
    """Create a temporary file with heredoc content"""
    if strip_tabs:
        # Remove leading tabs from each line
        lines = content.splitlines()
        content = '\n'.join(line.lstrip('\t') for line in lines)
    
    # Create temporary file
    fd, path = tempfile.mkstemp()
    os.write(fd, content.encode())
    os.close(fd)
    
    # Open for reading
    return os.open(path, os.O_RDONLY)
```

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
- State machine minimizes backtracking
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
- **Configuration System**: 14 options for POSIX, bash-compat, and permissive modes
- **AST Validation**: Semantic analysis with symbol table and validation rules
- **Error Recovery**: Multi-error collection, smart suggestions, panic mode recovery
- **Visualization**: Pretty-print, DOT graphs, and ASCII tree rendering
- **Centralized State**: ParserContext manages all parser state consistently

### Modular Execution Engine
- **Specialized Executors**: Separate modules for commands, pipelines, control flow, arrays, functions
- **Strategy Pattern**: Flexible command execution (builtins, functions, external)
- **Clean Delegation**: 84% code reduction through focused executor modules
- **Visitor Pattern**: Extensible AST traversal for execution and analysis

### Unified Lexer System
- **State Machine**: Robust tokenization with context tracking
- **Enhanced Tokens**: Built-in metadata, position tracking, and semantic information
- **Modular Recognition**: Priority-based token recognizers
- **Context Awareness**: Tokens know their lexical context for semantic analysis

### Component Organization
- **Clear Boundaries**: Each subsystem (lexer, parser, executor, expansion) is independent
- **Manager Pattern**: Coordinated functionality through manager classes
- **POSIX Compliance**: ~93% compliance with proper expansion ordering
- **Testability**: Comprehensive test suite with 3,400+ tests

## Known Limitations

1. **Deep Recursion**: Command substitution in recursive functions can hit Python's stack limit due to the multiple layers of function calls per shell recursion level.

2. **Command Substitution Output Capture**: Issues in pytest environments due to complex interaction between pytest's capture mechanism and subshell creation.

3. **Composite Token Quote Loss**: Parser creates COMPOSITE tokens but loses some quote information from RichTokens.

## Future Enhancements

1. **Optimization Visitors**: Performance analysis and optimization passes
2. **Enhanced Analysis Tools**: Extended security and code quality analysis
3. **Incremental Parsing**: Reparse only changed portions for better performance
4. **Parallel Execution**: Execute independent commands concurrently
5. **Advanced AST Transformations**: Code optimization and refactoring passes
6. **Language Server Protocol**: LSP support for shell script editing
7. **Interactive Debugging**: Step-through debugging of shell scripts
8. **Parser Combinator Optimization**: Performance improvements for combinator implementation