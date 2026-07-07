# PSH Subsystem Internals (ARCHIVED — historical design note)

> **This is a historical snapshot, archived on 2026-07-08 from
> `docs/subsystem_internals.md`.** It had drifted out of sync with the tree —
> it referenced structures that no longer exist (`psh/lexer/state_machine.py`,
> a monolithic `psh/ast_nodes.py`; the lexer is now a recognizer architecture
> and the AST nodes live in the `psh/ast_nodes/` package). Rather than keep
> re-truthing a narrative that overlaps the maintained docs, it was retired
> here (house precedent: `ARCHITECTURE.llm`, retired v0.311.0).
>
> **For current architecture, read instead:**
> - [`ARCHITECTURE.md`](../../ARCHITECTURE.md) — the maintained architecture guide (incl. the Quick Map).
> - The per-subsystem `psh/*/CLAUDE.md` files — focused, current guidance.
> - [`docs/architecture/tour_of_psh_internals.md`](../architecture/tour_of_psh_internals.md) — one command traced end-to-end through every stage.
>
> Everything below is preserved verbatim as it stood; treat specific file
> paths, line numbers, and sizes as of its era, not as current fact.

---

This document describes how the four core subsystems of PSH work: lexing, parsing, expansion, and evaluation. Together they form the pipeline that transforms raw shell input into executed commands.

```
Input → Lexer → Tokens → Parser → AST → Expansion → Evaluation/Execution
```

---

## Table of Contents

1. [Lexer](#1-lexer)
2. [Parser](#2-parser)
3. [Expansion](#3-expansion)
4. [Evaluation (Executor/Visitor)](#4-evaluation)
5. [End-to-End Flow](#5-end-to-end-flow)
6. [Pytest and Subshell File Descriptor Conflict](#6-pytest-and-subshell-file-descriptor-conflict)

---

## 1. Lexer

The lexer transforms raw shell input strings into a stream of typed tokens. It lives in `psh/lexer/` and is built around a **modular recognizer pattern** where specialized recognizer classes handle different token types.

### 1.1 Tokenization Pipeline

The public API is `tokenize()` in `psh/lexer/__init__.py:36`. The full pipeline is:

```
Input String
    ↓
BraceExpander          {a,b,c} → a b c
    ↓
ModularLexer           Core tokenization engine
    ↓
KeywordNormalizer      Normalizes keyword tokens based on context
    ↓
Token List
```

For commands containing heredocs, `tokenize_with_heredocs()` (`__init__.py:84`) uses `HeredocLexer` instead of `ModularLexer` to handle heredoc content collection.

### 1.2 Token Types

Token types are defined in `psh/lexer/token_types.py` as an enum (`TokenType`). Key categories:

| Category | Examples | Token Types |
|----------|----------|-------------|
| Basic | words, EOF | `WORD`, `EOF`, `NEWLINE` |
| Operators | `\|`, `&&`, `>>` | `PIPE`, `AND_AND`, `OR_OR`, `REDIRECT_OUT`, `REDIRECT_APPEND` |
| Quotes/Strings | `"..."`, `'...'` | `STRING`, `VARIABLE` |
| Expansions | `$(...)`, `$((...))` | `COMMAND_SUB`, `ARITH_EXPANSION`, `PARAM_EXPANSION`, `PROCESS_SUB_IN`, `PROCESS_SUB_OUT` |
| Grouping | `(`, `)`, `{`, `}` | `LPAREN`, `RPAREN`, `LBRACE`, `RBRACE`, `DOUBLE_LPAREN`, `DOUBLE_RPAREN` |
| Keywords | `if`, `then`, `fi` | `IF`, `THEN`, `FI`, `WHILE`, `DO`, `DONE`, `FOR`, `CASE`, `ESAC`, etc. |
| Case terminators | `;;`, `;&` | `DOUBLE_SEMICOLON`, `SEMICOLON_AMP`, `AMP_SEMICOLON` |
| Assignments | `=`, `+=` | `ASSIGN`, `PLUS_ASSIGN` |

Each `Token` is a dataclass with `type`, `value`, `position` (start), and optional `line`/`column` fields.

### 1.3 ModularLexer

The core tokenization engine (`psh/lexer/modular_lexer.py`, ~900 lines) drives the main loop:

```python
# Simplified tokenization loop (modular_lexer.py:277-306)
def tokenize(self, input_text):
    while pos < len(input_text):
        # 1. Skip whitespace
        # 2. Try quotes and expansions (unified Phase 3 approach)
        # 3. Try modular recognizers in priority order
        # 4. Fall back to word tokenization
```

### 1.4 Recognizer Architecture

Recognizers inherit from `TokenRecognizer` (`psh/lexer/recognizers/base.py:9`) and implement:

- `can_recognize(input_text, pos, context) -> bool` -- fast eligibility check
- `recognize(input_text, pos, context) -> Optional[Tuple[Token, int]]` -- actual recognition
- `priority` property -- higher values are tried first

The `RecognizerRegistry` (`psh/lexer/recognizers/registry.py:9`) maintains a priority-sorted list and tries each recognizer in order.

**Default recognizers and priorities:**

| Priority | Recognizer | Handles |
|----------|-----------|---------|
| 160 | `ProcessSubstitutionRecognizer` | `<(...)` and `>(...)` |
| 150 | `OperatorRecognizer` | Shell operators (`\|`, `&&`, `>>`, `;`, etc.) |
| 70 | `LiteralRecognizer` | Words, identifiers, assignments |
| 60 | `CommentRecognizer` | `# comments` |
| 30 | `WhitespaceRecognizer` | Spaces, tabs (skipped) |

**Operator recognition** uses greedy longest-match: 3-character operators are tried before 2-character, before 1-character. This ensures `>>=` is matched before `>>` before `>`.

**Keyword recognition** is handled by `KeywordNormalizer` in a post-tokenization pass. During tokenization, keywords are emitted as `WORD` tokens. The normalizer then converts words at command position to their keyword token types (e.g., `WORD("if")` becomes `IF("if")`). This single-pass approach avoids duplicated keyword logic.

### 1.5 LexerContext (State Machine)

`LexerContext` (`psh/lexer/state_context.py`) tracks all parsing state:

- **Nesting depths**: `paren_depth`, `bracket_depth`, `brace_depth`
- **Quote state**: `in_single_quote`, `in_double_quote`, `quote_stack`
- **Parsing context flags**: `in_arithmetic`, `in_command_substitution`, `at_command_position`, `in_array_assignment`

The `StateMachine` component (`psh/lexer/state_machine.py`) manages transitions between lexer states (`NORMAL`, `IN_DOUBLE_QUOTE`, `IN_SINGLE_QUOTE`, `IN_BACKTICK`, etc.) using `StateTransition` objects with conditions, actions, and priorities.

### 1.6 Quote and Expansion Parsing

Two specialized parsers handle complex nested constructs:

- **QuoteParser** (`psh/lexer/quote_parser.py`): Parses single-quoted, double-quoted, and ANSI-C (`$'...'`) strings. Double quotes allow nested expansions; single quotes are literal.

- **ExpansionParser** (`psh/lexer/expansion_parser.py`): Parses `$VAR`, `${VAR}`, `${VAR:-default}`, `$(command)`, `$((expr))`, and `` `command` ``. Handles arbitrary nesting depth (e.g., `$(echo ${VAR:-$(cmd)})`) by tracking parenthesis and brace counts.

### 1.7 Heredoc Lexer

`HeredocLexer` (`psh/lexer/heredoc_lexer.py`) handles heredoc tokenization:
- Detects `<<DELIM` and `<<-DELIM` (tab-stripping) syntax
- Collects content lines until the delimiter is found
- Tracks whether the delimiter was quoted (disables expansion in content)
- Returns content via the heredoc map for AST population

### 1.8 Unicode Support

`psh/lexer/unicode_support.py` provides Unicode-aware character classification:
- `is_identifier_start()`: Letters and `_` (Unicode or ASCII based on POSIX mode)
- `is_identifier_char()`: Letters, digits, marks, and `_`
- `is_whitespace()`: Unicode whitespace categories or ASCII-only
- `normalize_identifier()`: NFC normalization for consistent comparison

---

## 2. Parser

The parser transforms the token stream into an Abstract Syntax Tree (AST). It uses a **recursive descent** approach with specialized sub-parsers for different grammar constructs. The parser lives in `psh/parser/`.

### 2.1 Parser Architecture

The main parser class (`psh/parser/recursive_descent/parser.py`, 669 lines) delegates to specialized parsers:

```
Parser (main orchestrator)
├── StatementParser       Statement-level constructs, and/or lists
├── CommandParser         Simple commands, pipelines, arguments
├── ControlStructureParser  if/while/for/case/select
├── TestParser            [[ ... ]] expressions
├── ArithmeticParser      (( ... )) commands
├── RedirectionParser     I/O redirections and heredocs
├── ArrayParser           Array assignments and initialization
└── FunctionParser        Function definitions
```

**Entry point**: `Parser.parse()` processes top-level statements (functions or command lists) until EOF, producing a single canonical `Program` AST node for every parse.

### 2.2 Parser Context

`ParserContext` (`psh/parser/recursive_descent/context.py`, dataclass) centralizes all parsing state:

- **Token navigation**: `peek(offset)`, `advance()`, `match(*types)`, `consume(type)` (lines 193-236)
- **Scope tracking**: `enter_scope(scope)`, `exit_scope()`, `scope_stack` for nesting depth (lines 297-331)
- **Context flags**: `in_arithmetic`, `in_test_expr`, `in_function_body`, `in_case_pattern`, `in_command_substitution`
- **Loop/function depth**: `loop_depth`, `function_depth`, `conditional_depth`
- **Heredoc management**: `register_heredoc()`, `add_heredoc_line()`, `close_heredoc()` (lines 410-443)
- **Profiling/tracing**: `enter_rule()`, `exit_rule()` with optional trace output (lines 335-356)

### 2.3 Grammar Rules and Parsing Methods

#### Statement Level (`parsers/statements.py`)

```
Program       → StatementList             # the single canonical root
StatementList → Statement (';' | '\n' Statement)*
Statement     → FunctionDef | AndOrList
AndOrList     → Pipeline (('&&' | '||') Pipeline)*
```

`Program` is the root of every parse; nested command bodies (loop/if/function/
group interiors) use `StatementList`. A bare compound keeps its normal
`AndOrList → Pipeline` ancestry — it is not unwrapped at the root.

- `parse_command_list()` (lines 33-58): Parses semicolon/newline-separated statements
- `parse_and_or_list()` (lines 83-104): Handles `&&`/`||` chains with left-to-right associativity

#### Command Level (`parsers/commands.py`, 616 lines)

```
Pipeline      → ['!'] Command ('|' Command)*
Command       → SimpleCommand | CompoundCommand
SimpleCommand → [assignments...] [arguments...] [redirects...] ['&']
```

- `parse_pipeline()`: Creates `Pipeline` node with optional NOT prefix
- `parse_command()` (lines 102-121): Parses a single command with arguments, redirections, and background flag
- `parse_composite_argument()`: Handles arguments containing expansions and mixed quoting

#### Control Structures (`parsers/control_structures.py`, 470 lines)

```
IfStatement    → 'if' StatementList ';' 'then' StatementList ('elif' ...)* ['else' StatementList] 'fi'
WhileLoop      → 'while' StatementList ';' 'do' StatementList ';' 'done'
UntilLoop      → 'until' StatementList ';' 'do' StatementList ';' 'done'
ForLoop        → 'for' WORD ['in' WORD*] ';' 'do' StatementList ';' 'done'
CStyleForLoop  → 'for' '((' init ';' cond ';' update '))' ';' 'do' StatementList ';' 'done'
CaseStatement  → 'case' WORD 'in' (pattern ')' StatementList ';;')* 'esac'
SelectLoop     → 'select' WORD 'in' WORD* ';' 'do' StatementList ';' 'done'
```

Each has a `parse_*_statement()` method and a neutral variant (`parse_control_structure_neutral()`) for use in pipelines where the control structure runs in a subshell.

#### Test Expressions (`parsers/tests.py`)

```
TestExpr     → TestOrExpr
TestOrExpr   → TestAndExpr ('||' TestAndExpr)*
TestAndExpr  → TestUnary ('&&' TestUnary)*
TestUnary    → ['!'] TestPrimary
TestPrimary  → UnaryOp WORD | WORD BinaryOp WORD | '(' TestExpr ')'
```

Operator precedence (lowest to highest): `||`, `&&`, `!`, binary/unary operators. Supports `-f`, `-d`, `-e`, `-z`, `-n`, `==`, `!=`, `<`, `>`, `=~`, `-eq`, `-ne`, `-lt`, `-le`, `-gt`, `-ge`.

#### Redirections (`parsers/redirections.py`)

```
Redirect → [FD] ('<' | '>' | '>>' | '<<' | '<<<' | '>&' | '<&') TARGET
```

- `parse_redirect()` (lines 62-76): Single redirection
- `_parse_heredoc()` (lines 78-99): Heredoc with delimiter detection
- `_parse_dup_redirect()`: FD duplication (`2>&1`)

#### Functions (`parsers/functions.py`)

```
FunctionDef → 'function' NAME ['()'] CompoundCommand
            | NAME '()' CompoundCommand
```

- `is_function_def()` (lines 18-41): Lookahead disambiguation
- `parse_compound_command()` (lines 66+): Body can be `{ ... }` or `( ... )`

#### Arrays (`parsers/arrays.py`)

```
ArrayInit    → NAME '=(' element* ')' | NAME '+=(' element* ')'
ArrayElement → NAME '[' index ']' '=' value | NAME '[' index ']' '+=' value
```

- `is_array_assignment()` (lines 21-115): Lookahead with position save/restore

### 2.4 AST Node Types

AST nodes are defined in `psh/ast_nodes.py` (474 lines) as dataclasses inheriting from `ASTNode`:

```
ASTNode
├── Statement
│   ├── AndOrList          Pipeline chain with && / ||
│   ├── FunctionDef        Function definition
│   └── UnifiedControlStructure
│       ├── IfConditional
│       ├── WhileLoop / UntilLoop
│       ├── ForLoop / CStyleForLoop
│       ├── CaseConditional
│       ├── SelectLoop
│       └── ArithmeticEvaluation
│
├── Command
│   ├── SimpleCommand      command args redirects
│   └── CompoundCommand
│       ├── SubshellGroup   (...)
│       └── BraceGroup      {...}
│
├── Expansion
│   ├── ParameterExpansion  ${var:-default}
│   ├── CommandSubstitution $(cmd)
│   ├── VariableExpansion   $var
│   └── ArithmeticExpansion $((expr))
│
├── TestExpression
│   ├── BinaryTestExpression
│   ├── UnaryTestExpression
│   ├── CompoundTestExpression
│   └── NegatedTestExpression
│
├── Redirect               I/O redirection
├── ProcessSubstitution    <(cmd), >(cmd)
└── Word                   Mixed literal/expansion content
    └── WordPart (LiteralPart | ExpansionPart)
```

> `break`, `continue`, and `return` have **no dedicated AST nodes**. Like
> bash, they are ordinary (special) builtins, so they parse as plain
> `SimpleCommand`s — which is why `break 2>/dev/null`, `break | cat`,
> `break && x`, and even `break() { ...; }` all behave like any other
> command. The control transfer is implemented in the builtins
> (`psh/builtins/loop_control.py` for break/continue,
> `psh/builtins/function_support.py` for return), which raise the
> `LoopBreak` / `LoopContinue` / `FunctionReturn` signals that the loop and
> function executors catch.

**Key node: `SimpleCommand`** (`ast_nodes.py:186`):
```python
@dataclass
class SimpleCommand(Command):
    args: List[str]                          # Argument values
    redirects: List[Redirect]               # I/O redirections
    background: bool                         # Terminated with &
    array_assignments: List[ArrayAssignment] # Assignments before command
    words: List[Word]                        # Word AST nodes (always present)
```

Word AST nodes carry per-part quote context (`LiteralPart.quoted`, `ExpansionPart.quote_char`) and provide semantic helper properties: `is_quoted`, `is_unquoted_literal`, `is_variable_expansion`, `has_expansion_parts`, `has_unquoted_expansion`, `effective_quote_char`.

**Unified control structures** implement both `Statement` and `CompoundCommand` with an `ExecutionContext` enum (`STATEMENT` or `PIPELINE`), allowing them to appear in pipelines (e.g., `while read line; do ...; done | sort`).

### 2.5 Error Handling

The parser is strict: the first syntax error raises `ParseError` immediately
(`ParserContext.consume()` always raises — there is no error-collection or
recovery mode; the dormant collection machinery was removed in v0.654 because
it could return fabricated ASTs for invalid input).

`ParseError` carries an `ErrorContext` with token, position, and line/column.
The diagnostic interface is two-level: `error.summary` is the short reason
clause, `error.render()` (== `str(error)`) is the rich presentation with
source line, caret, and suggestions. Execution and analysis modes both use the
rich render; nothing consults `.message` for presentation.

### 2.6 Parser Configuration

`ParserConfig` (`psh/parser/config.py`) is intentionally minimal: after the
v0.654 honest-configuration cleanup it carries no feature gates or modes —
grammar dispatch never consulted them (features like `[[ ]]`/`(( ))` are
always parsed; POSIX restrictions are runtime/lexer concerns, not parser
config). The empty dataclass is retained as the extension point threaded
through the parser constructors; `clone()` (via `dataclasses.replace`)
rejects unknown fields.

---

## 3. Expansion

The expansion subsystem transforms shell words (variables, command substitutions, globs, etc.) into their final values before command execution. It lives in `psh/expansion/`.

### 3.1 Expansion Order (POSIX)

The `ExpansionManager` (`psh/expansion/manager.py:16`, 669 lines) processes expansions in strict POSIX order:

```
1. Brace Expansion      {a,b,c}         Handled by lexer (preprocessing)
2. Tilde Expansion      ~, ~user        TildeExpander
3. Variable Expansion   $VAR, ${VAR}    VariableExpander
4. Command Substitution $(cmd), `cmd`   CommandSubstitution
5. Arithmetic Expansion $((expr))       execute_arithmetic_expansion()
6. Word Splitting       on IFS          WordSplitter
7. Pathname Expansion   *, ?, [...]     GlobExpander
8. Quote Removal        strip quotes    During processing
```

### 3.2 ExpansionManager

The central orchestrator owns all expander instances:

```python
class ExpansionManager:
    def __init__(self, shell):
        self.variable_expander = VariableExpander(shell)
        self.command_sub = CommandSubstitution(shell)
        self.tilde_expander = TildeExpander(shell)
        self.glob_expander = GlobExpander(shell)
        self.word_splitter = WordSplitter()
```

**Primary entry point**: `expand_arguments(command: SimpleCommand) -> List[str]` (`manager.py:41`) uses Word AST-based expansion. It:

1. Detects and sets up process substitutions via `IOManager`
2. Expands each Word AST node using per-part quote context (`WordExpander.expand()` in `word_expander.py`)
3. Handles special cases like `"$@"` and `"${arr[@]}"` producing multiple arguments
4. Applies word splitting to unquoted expansion results
5. Applies pathname (glob) expansion to unquoted results

### 3.3 Variable Expansion

`VariableExpander` (`psh/expansion/variable.py`, 947 lines) handles the most complex expansion type:

**Simple variables**: `$VAR`, `${VAR}`

**Special variables**: `$?` (exit status), `$$` (PID), `$!` (last bg PID), `$#` (arg count), `$@`, `$*`, `$0`-`$9`

**Parameter expansion operators** (`psh/expansion/parameter_expansion.py`, 399 lines):

| Operator | Meaning |
|----------|---------|
| `${VAR:-default}` | Use default if unset/null |
| `${VAR:=default}` | Assign default if unset/null |
| `${VAR:+value}` | Use value if set and non-null |
| `${VAR:?error}` | Error if unset/null |
| `${#VAR}` | String length |
| `${VAR#pattern}` | Remove shortest prefix |
| `${VAR##pattern}` | Remove longest prefix |
| `${VAR%pattern}` | Remove shortest suffix |
| `${VAR%%pattern}` | Remove longest suffix |
| `${VAR/pat/repl}` | Replace first match |
| `${VAR//pat/repl}` | Replace all matches |
| `${VAR/#pat/repl}` | Replace prefix |
| `${VAR/%pat/repl}` | Replace suffix |
| `${VAR^}` | Uppercase first character |
| `${VAR^^}` | Uppercase all |
| `${VAR,}` | Lowercase first character |
| `${VAR,,}` | Lowercase all |
| `${VAR:offset:length}` | Substring extraction |
| `${!prefix*}` | Variable name matching |

**Array expansions**: `${arr[0]}`, `${arr[@]}`, `${arr[*]}`, `${#arr[@]}`, `${!arr[@]}`

**Pattern matching** uses `PatternMatcher` (`parameter_expansion.py:333`) to convert shell glob patterns to Python regex.

### 3.4 Command Substitution

`CommandSubstitution` (`psh/expansion/command_sub.py`, 134 lines) handles `$(cmd)` and `` `cmd` ``:

1. Forks child process via `os.fork()`
2. Captures stdout through a pipe
3. Creates a temporary Shell instance in the child
4. Executes the command
5. Strips trailing newlines (POSIX behavior)

### 3.5 Arithmetic Expansion

`execute_arithmetic_expansion()` (`manager.py:480`) handles `$((expr))`:

1. Pre-expands `$var` and `${var}` references within the expression
2. Pre-expands nested command substitutions
3. Delegates evaluation to `evaluate_arithmetic()` in `psh/expansion/arithmetic.py`

### 3.6 Other Expanders

- **TildeExpander** (`psh/expansion/tilde.py`): `~` maps to `$HOME`, `~user` looks up the user's home via `pwd.getpwnam()`
- **GlobExpander** (`psh/expansion/glob.py`): Uses Python's `glob.glob()` for pathname expansion. Returns sorted matches or the original pattern if no matches (bash behavior). Respects the `noglob` option.
- **WordSplitter** (`psh/expansion/word_splitter.py`): Splits unquoted results on `$IFS` characters (default `" \t\n"`). Empty IFS means no splitting.

### 3.7 Quote Effects on Expansion

| Quote Type | Variable | Command Sub | Glob | Word Split |
|------------|----------|-------------|------|------------|
| Unquoted | Yes | Yes | Yes | Yes |
| `"double"` | Yes | Yes | No | No |
| `'single'` | No | No | No | No |
| `$'ansi'` | Escape seqs | No | No | No |

---

## 4. Evaluation

The evaluation subsystem executes AST nodes using the **visitor pattern**. The visitor infrastructure lives in `psh/visitor/` and the execution logic in `psh/executor/`.

### 4.1 Visitor Pattern

**Base class**: `ASTVisitor[T]` (`psh/visitor/base.py:15`) provides double dispatch:

```python
class ASTVisitor(ABC, Generic[T]):
    def visit(self, node: ASTNode) -> T:
        # Dispatch to visit_{NodeClassName} via cached method lookup
        method_name = f'visit_{node.__class__.__name__}'
        return getattr(self, method_name, self.generic_visit)(node)
```

The method cache (`_method_cache` dict) avoids repeated `getattr` calls.

Additional base classes:
- **`ASTTransformer`** (`base.py:64`): Returns modified/replaced AST nodes; `transform_children()` recursively processes child nodes
- **`CompositeVisitor`** (`base.py:136`): Runs multiple visitors in sequence

### 4.2 ExecutorVisitor

`ExecutorVisitor` (`psh/executor/core.py:54`, extends `ASTVisitor[int]`) is the main execution engine. It returns exit codes (int) and delegates to specialized executors:

```
ExecutorVisitor
├── CommandExecutor         Simple command execution
├── PipelineExecutor        Pipeline execution and process management
├── ControlFlowExecutor     if/while/for/case/select
├── FunctionOperationExecutor  Function calls and scope
├── SubshellExecutor        Subshells and brace groups
└── ArrayOperationExecutor  Array operations
```

**Visitor method dispatch** (core.py:113-409):

| Method | Delegates To |
|--------|-------------|
| `visit_Program` | Executes the root's statements (via `_execute_sequence`, root context) |
| `visit_StatementList` | Executes a nested body (via `_execute_sequence`, nested context) |
| `visit_AndOrList` | Short-circuit `&&`/`\|\|` evaluation |
| `visit_Pipeline` | `PipelineExecutor` |
| `visit_SimpleCommand` | `CommandExecutor` |
| `visit_IfConditional` | `ControlFlowExecutor` |
| `visit_WhileLoop` | `ControlFlowExecutor` |
| `visit_ForLoop` | `ControlFlowExecutor` |
| `visit_CaseConditional` | `ControlFlowExecutor` |
| `visit_SubshellGroup` | `SubshellExecutor` |
| `visit_BraceGroup` | `SubshellExecutor` |
| `visit_FunctionDef` | `FunctionOperationExecutor` |
| `visit_ArithmeticEvaluation` | Arithmetic evaluator |

`break`, `continue`, and `return` have no visitor methods: they are
builtins, dispatched through `visit_SimpleCommand` like any other command.
The builtins raise `LoopBreak` / `LoopContinue` / `FunctionReturn`, which
the loop and function executors catch.

### 4.3 Command Execution

`CommandExecutor` (`psh/executor/command.py:36`, 517 lines) handles simple commands through phases:

**Phase 1: Extract assignments** (lines 82-112)
- Extracts `VAR=value` assignments before the command name
- Pure assignments (no command) are handled directly

**Phase 2: Expand arguments** (lines 121-165)
- Calls `ExpansionManager.expand_arguments()` on the remaining args
- Handles xtrace output if enabled

**Phase 3: Execute via strategy pattern** (lines 177-179)
- Tries execution strategies in priority order

**Phase 4: Restore temporary variables** (lines 182-183)
- Command-prefixed assignments (`FOO=bar cmd`) are always temporary

#### Execution Strategies

Strategies (`psh/executor/strategies.py:22`) are tried in order:

1. **SpecialBuiltinExecutionStrategy**: POSIX special builtins (`:`, `break`, `continue`, `eval`, `exec`, `exit`, `export`, `readonly`, `return`, `set`, `shift`, `trap`, `unset`). Highest priority; precedes functions.

2. **FunctionExecutionStrategy**: User-defined shell functions. Creates a new scope, sets positional parameters, executes the function body.

3. **BuiltinExecutionStrategy**: Regular builtins (`cd`, `echo`, `pwd`, `test`, etc.). Executes in the current shell process.

4. **ExternalExecutionStrategy**: External programs. Forks via `ProcessLauncher`, calls `os.execvpe()` in the child.

(Aliases are NOT a runtime strategy. Since R8.6b they are expanded as a token-stream transform at the lex→parse boundary — `AliasManager.expand_aliases`, wired in `psh/scripting/source_processor.py` and `command_accumulator.py` — so by the time a command reaches the executor its command word is already alias-expanded. The former `AliasExecutionStrategy` was removed.)

### 4.4 Pipeline Execution

`PipelineExecutor` (`psh/executor/pipeline.py:62`, 500 lines) handles multi-command pipelines:

1. **Create pipes**: `len(commands) - 1` OS pipes for connecting stdout→stdin
2. **Synchronization pipe**: Prevents race conditions during process group setup
3. **Fork each command** via `ProcessLauncher`:
   - First command: `PIPELINE_LEADER` role (creates new process group)
   - Subsequent: `PIPELINE_MEMBER` role (joins existing group)
4. **I/O setup**: Each child redirects stdin from previous pipe and stdout to next pipe
5. **Terminal control**: Transfers terminal to pipeline process group for foreground jobs
6. **Wait**: `job_manager.wait_for_job()` collects exit statuses
7. **Result**: Returns last command's exit code (or first non-zero with `pipefail`)

**Single command optimization**: If the pipeline has only one command, it executes directly without forking.

### 4.5 ProcessLauncher

`ProcessLauncher` (`psh/executor/process_launcher.py:49`, 349 lines) is the unified process creation system for all forked processes:

```python
class ProcessRole(Enum):
    SINGLE           # Standalone command (creates own PGID)
    PIPELINE_LEADER  # First in pipeline (creates PGID)
    PIPELINE_MEMBER  # Non-first in pipeline (joins existing PGID)
```

**`launch()` method** (lines 93-128):
1. Flushes stdout/stderr to prevent output duplication
2. Calls `os.fork()`
3. **Child**: Sets process group, applies unified child signal policy (`child_policy.py`), sets up I/O, executes, calls `os._exit()`
4. **Parent**: Sets child's process group from parent side (race condition mitigation), returns `(pid, pgid)`

**Process group synchronization** (for pipelines):
- Parent creates a sync pipe before forking
- `PIPELINE_LEADER` closes both ends immediately after `setpgid`
- `PIPELINE_MEMBER` blocks on read until parent closes write end
- Parent closes write end after all forks complete, unblocking all members

### 4.6 Control Flow

`ControlFlowExecutor` (`psh/executor/control_flow.py:36`, 634 lines):

- **If**: Evaluates condition, executes matching branch (then/elif/else)
- **While/Until**: Loops with `LoopBreak`/`LoopContinue` exception handling; tracks `loop_depth` for nested break/continue levels
- **For**: Expands item list (with glob and word splitting), iterates setting loop variable
- **C-style for**: Evaluates arithmetic init/condition/update expressions
- **Case**: Expands expression, matches patterns with `fnmatch`. Handles `;;` (exit), `;&` (fall-through), `;;&` (continue testing)
- **Select**: Displays numbered menu to stderr, reads selection, sets `REPLY` and loop variable

**Control flow uses exceptions**:
- `LoopBreak(level)`: Exit from nested loops
- `LoopContinue(level)`: Continue in nested loops
- `FunctionReturn(exit_code)`: Return from function
- `SystemExit`: Exit entire shell

### 4.7 Subshell and Brace Group Execution

`SubshellExecutor` (`psh/executor/subshell.py:23`, 328 lines):

| Feature | Subshell `(...)` | Brace Group `{...}` |
|---------|-----------------|---------------------|
| Process | Forks child | Current process |
| Variables | Isolated (don't propagate) | Shared (persist) |
| Process group | New PGID | No change |
| Redirections | In child | Via context manager |

**Foreground subshell execution**:
1. Creates execute function that makes a child Shell instance
2. Marks as forked child, inherits I/O streams
3. Launches via `ProcessLauncher` with `SINGLE` role
4. Transfers terminal control, waits, restores

### 4.8 Function Execution

`FunctionOperationExecutor` (`psh/executor/function.py:21`, 137 lines):

1. Looks up function in `FunctionManager`
2. Saves current context (positional params, function name, script name)
3. Pushes new variable scope
4. Sets positional parameters (`$1`, `$2`, etc.) and special variables (`$#`, `$@`, `$*`)
5. Executes function body via visitor
6. Catches `FunctionReturn` exception for return value
7. Pops scope and restores context

### 4.9 Execution Context

`ExecutionContext` (`psh/executor/context.py:17`, 189 lines) encapsulates execution state:

```python
@dataclass
class ExecutionContext:
    in_pipeline: bool = False
    in_subshell: bool = False
    in_forked_child: bool = False
    loop_depth: int = 0
    current_function: Optional[str] = None
    pipeline_context: Optional[PipelineContext] = None
    background_job: Optional[Job] = None
    exec_mode: bool = False
```

Provides factory methods like `fork_context()`, `subshell_context()`, `pipeline_context_enter()`, `loop_context_enter()`.

### 4.10 Exit Code Propagation

- Updated in `state.last_exit_code` after each statement
- Available via `$?`
- Special codes: 0 (success), 1 (error), 2 (usage), 126 (not executable), 127 (not found), 128+N (signal N), 130 (SIGINT)

---

## 5. End-to-End Flow

Here is how `echo "Hello $USER" | wc -w` is processed:

### Step 1: Lexing

```
"echo \"Hello $USER\" | wc -w"
    ↓ ModularLexer
[WORD:"echo", STRING:"Hello $USER", PIPE:"|", WORD:"wc", WORD:"-w"]
```

The `STRING` token preserves the double-quoted content with the `$USER` variable reference.

### Step 2: Parsing

```
Pipeline
├── SimpleCommand(args=["echo", "Hello $USER"],
│                 words=[Word([LiteralPart("echo")]),
│                        Word([LiteralPart("Hello "), ExpansionPart("$USER")], quoted=True)])
└── SimpleCommand(args=["wc", "-w"],
│                 words=[Word([LiteralPart("wc")]), Word([LiteralPart("-w")])])
```

### Step 3: Expansion (during execution of first command)

```
"Hello $USER" → "Hello pwilson"     (variable expansion, no word split in quotes)
```

### Step 4: Evaluation

1. `visit_Pipeline` → `PipelineExecutor`
2. Creates one pipe
3. Forks child 1 (PIPELINE_LEADER): `echo "Hello pwilson"` with stdout → pipe write end
4. Forks child 2 (PIPELINE_MEMBER): `wc -w` with stdin ← pipe read end
5. Closes pipes in parent
6. Transfers terminal to pipeline process group
7. Waits for both children
8. Returns `wc`'s exit code (0)

Output: `2`

---

## 6. Pytest and Subshell File Descriptor Conflict

This section documents the fundamental incompatibility between pytest's output capture and PSH's subshell file descriptor management. It is recorded here for future reference — the issue is well-understood and the current mitigation (running subshell tests with `-s`) is the correct approach.

### 6.1 The Problem

About 50 tests (43 subshell tests plus a handful of function/variable/control-flow tests that exercise subshells internally) must be run with pytest's `-s` flag (disable output capture). Without `-s`, these tests see empty output files or missing pipe data. The test runner (`run_tests.py`) handles this automatically by splitting the suite into phases.

### 6.2 Root Cause

Pytest's default output capture replaces file descriptors 1 (stdout) and 2 (stderr) at the OS level using `os.dup2()`. When PSH forks a child process for a subshell, the child inherits the parent's file descriptor table — including pytest's redirected FDs 1 and 2.

```
Pytest starts
  └─ os.dup2(capture_fd, 1)     # FD 1 now points to pytest's capture buffer
  └─ os.dup2(capture_fd, 2)     # FD 2 now points to pytest's capture buffer

PSH test runs: (echo hello) > file.txt
  └─ Parent calls os.fork()
  └─ Child inherits FD 1 → pytest capture buffer
  └─ Child calls os.dup2(file_fd, 1)   # Redirects "stdout" to file
  └─ Child execs echo, which writes to FD 1
  └─ Output arrives in file.txt ← This part works

But for cases where the child is a shell process (not exec'd):
  └─ Child creates a new Shell instance
  └─ Python's sys.stdout still references pytest's capture wrapper
  └─ Builtins writing via sys.stdout go to pytest, not to FD 1
  └─ Test reads file.txt → empty or partial
```

The conflict is specifically between Python-level `sys.stdout` (which pytest wraps) and OS-level FD 1 (which `dup2()` redirects). External commands that `exec()` are unaffected because `exec` replaces the Python runtime entirely. Shell processes (subshells) that run Python builtins hit the mismatch.

### 6.3 Why `-s` Is the Correct Mitigation

With `-s`, pytest does not install its capture machinery. FDs 1 and 2 remain connected to the terminal (or pipe). When PSH forks and redirects, the child's FDs and Python file objects are consistent — there is no capture wrapper to conflict with.

This is not a workaround but the correct test configuration for tests that exercise Unix process semantics. The same constraint applies to any test framework testing code that forks and manipulates file descriptors.

### 6.4 Alternatives Considered

| Approach | Outcome |
|----------|---------|
| Use `sys.__stdout__` in builtins | Fails: pytest captures at the FD level, not just the Python wrapper |
| `capfd.disabled()` context manager | Incomplete: doesn't restore FDs before fork, and scope is awkward |
| Restore real FDs in the child after fork | Fragile: requires knowing what the "real" FDs were, and pytest's saved FDs change between versions |
| Write builtins to FD 1 via `os.write()` | Partially works (and PSH does this in forked children via `_in_forked_child`), but doesn't help with Python-level `print()` calls in the child Shell |
| Separate test process (subprocess) | Works but slow and loses pytest fixture/assertion integration |

### 6.5 What Would a Full Fix Look Like

A complete fix would require one of:

1. **All shell-process output routed through `os.write()`**: Every builtin and internal print in a forked child would need to bypass Python's `sys.stdout` entirely. PSH partially does this (the `_in_forked_child` flag switches some builtins to `os.write()`), but it would need to be comprehensive — covering every `print()`, every `sys.stdout.write()`, and every library call that touches Python streams. This is a large surface area with diminishing returns.

2. **ProcessLauncher restores "real" FDs before executing shell processes**: After forking, the child could close FDs 1/2 and reopen `/dev/tty` (or use saved copies of the original FDs). This is what the `shell` fixture's FD save/restore does in the parent, but doing it reliably in the child — across different pytest versions and capture modes — is fragile.

3. **Run subshell tests out-of-process**: Use `subprocess.run(['python', '-m', 'pytest', ...])` to run subshell tests in a clean process without inherited capture. This works but defeats the purpose of integrated test runs.

None of these are worth the complexity. The phased test runner is simple, reliable, and well-documented.

### 6.6 Current Architecture

```
run_tests.py
  ├─ Phase 1: All tests except subshells (normal capture)
  ├─ Phase 2: tests/integration/subshells/ (with -s)
  └─ Phase 3: Individual tests that exercise subshells (with -s)
              - test_function_advanced.py::test_function_with_subshell
              - test_variable_assignment.py::test_assignment_with_subshell
              - test_c_style_for_loops.py::TestCStyleForIORedirection (3 tests)
```

The `isolated_shell_with_temp_dir` fixture provides a clean working directory and Shell instance. It does not (and cannot) fix the FD capture conflict — that is handled entirely by the `-s` flag.

### 6.7 Relationship to SIGTTOU Policy

The pytest `-s` issue and the SIGTTOU signal issue are independent problems that both affect subshell tests, which is why they were grouped under architecture-comments.md opportunity #6. They are now separated:

- **SIGTTOU policy**: Resolved in v0.122.0, unified in v0.124.0. `apply_child_signal_policy()` in `psh/executor/child_policy.py` is the single source of truth for all 5 fork paths (ProcessLauncher, command substitution, process substitution, file redirect proc-sub, IOManager builtin proc-sub). The `is_shell_process` flag controls whether SIGTTOU stays SIG_IGN (shell processes) or SIG_DFL (leaf processes).
- **Pytest FD capture**: Permanent test infrastructure constraint. Mitigated by the phased test runner. Not a PSH bug.
