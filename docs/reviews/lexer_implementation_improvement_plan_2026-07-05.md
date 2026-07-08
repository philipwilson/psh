# Lexer Implementation Appraisal and Improvement Plan

Date: 2026-07-05  
Version reviewed: PSH 0.617.0

## Summary

The lexer is one of PSH's stronger subsystems. It has:

- A single production lexer.
- Pure, focused mini-scanners for difficult word sub-grammars.
- A forward assignment-shape tracker instead of repeated backward scans.
- A fail-loud progress invariant.
- Good source offsets and token-stream characterization.
- Extensive tests against difficult shell constructs.
- Explicit documentation of command-position state and its known
  asymmetries.

It should be improved incrementally rather than rewritten wholesale.

However, the review found three reproducible correctness defects and one
serious performance defect:

1. Keyword-looking argument words can incorrectly change lexer command
   position.
2. Some operator decisions use Python's Unicode whitespace classification
   instead of shell whitespace.
3. The public lexer configuration does not actually enable POSIX identifier
   rules.
4. Heredoc discovery repeatedly re-lexes the accumulated source prefix and is
   quadratic.

Beyond those defects, the lexer would become substantially clearer if it:

- Emitted one structured token per shell word.
- Moved brace expansion out of `tokenize()`.
- Replaced loosely coupled command-position booleans with an explicit lexical
  state machine.
- Used immutable, source-faithful token payloads.
- Reduced the parallel grammar implemented by the command-substitution extent
  scanner.

## Current architecture

The public lexer pipeline is:

```text
source
  -> ModularLexer
  -> KeywordNormalizer
  -> TokenBraceExpander
  -> parser token stream
```

The main loop in `ModularLexer`:

1. Skips whitespace.
2. Handles quotes and expansions through dedicated parsers.
3. Dispatches to recognizers in numeric-priority order.
4. Raises if no component consumes the current character.

Recognizers handle operators, process substitution, comments, literal words,
whitespace, and a low-priority set of operator-looking word fragments.

The overall decomposition is defensible, but the name `tokenize()` currently
covers lexical analysis, reserved-word classification, and brace expansion.
Those stages have different responsibilities and should not share one public
contract indefinitely.

## Strengths to preserve

### 1. Pure word mini-scanners

`recognizers/word_scanners.py` isolates bracket classes, extglob groups,
assignment subscripts, inline ANSI-C quoting, and expansion-region skipping
into testable functions
([word_scanners.py](../../psh/lexer/recognizers/word_scanners.py#L1)).

This is a good direction. Any word-token redesign should reuse these scanners
or preserve their purity and direct unit-testability.

### 2. Forward assignment state

`WordShapeTracker` incrementally records whether a word is a possible
assignment name, is inside an assignment value, or can accept `+=`. It avoids
re-deriving these facts from the accumulated string after every character.

The assignment-prefix map likewise replaced a known quadratic backward scan.
Both mechanisms demonstrate the right performance discipline.

### 3. Fail-loud progress

The main loop raises if no recognizer or expansion parser consumes the current
character
([modular_lexer.py](../../psh/lexer/modular_lexer.py#L281)). Silent character
loss is much worse than an internal error. Preserve this invariant and make it
easier to property-test in the redesigned lexer.

### 4. Explicit command-position documentation

The current three command-position machines and their asymmetries are
documented in
[command_position.md](../architecture/command_position.md). That visibility
is valuable even though the longer-term goal should be to reduce the number of
machines.

### 5. Strong characterization coverage

The frozen token-stream corpus, command-substitution scanner characterization,
Bash comparison cases, and focused mini-scanner tests provide a strong safety
net for structural work.

## Immediate correctness defects

### 1. Keyword-looking arguments can enable syntax

`ModularLexer._update_command_position_context()` treats a `WORD` whose value
is in `LEXER_COMMAND_POSITION_WORDS` as restoring command position
([modular_lexer.py](../../psh/lexer/modular_lexer.py#L200)).

It does not first check whether that word was itself read at command position.
Consequently, ordinary arguments can affect the classification of the next
token.

Reproduction:

```sh
echo if [[ x
```

Observed behavior:

| Shell | Result |
|---|---|
| Bash | Prints `if [[ x`, status 0 |
| PSH | Treats `[[` as `DOUBLE_LBRACKET`, reports a parse error, status 2 |

The same structural problem exists in case-state tracking:

```python
if token_type == TokenType.WORD and token_value == 'case':
    self.context.case_depth += 1
```

That transition also does not require `case` to have been eligible as a
reserved word.

#### Immediate repair

Capture the state before consuming the token:

```python
was_command_position = self.context.command_position
```

Only apply reserved-word transitions if the token was recognized as a
reserved word at that position.

This is necessary but not the complete long-term solution. `for`, `select`,
and `case` introduce subject/header positions where the next word is not a
command even when it happens to spell `if`, `while`, or another keyword. The
proper solution is the explicit lexical state described later.

#### Tests to add

Build a matrix of keyword-looking arguments followed by context-sensitive
tokens:

```text
echo if [[ x
echo while [[ x
echo until [[ x
echo then [[ x
echo time [[ x
echo case in
printf '%s\n' for [[
```

Also cover legal keyword spellings in subject positions:

```text
for in in a b; do ...; done
case in in in) ... ;; esac
```

Each generated case should compare stdout, stderr class, and exit status
against Bash.

### 2. Python whitespace semantics leak into shell tokenization

The lexer correctly defines shell token separators as:

```text
space, tab, newline
```

Other Unicode whitespace-category characters are ordinary shell word
characters. This rule is encoded in `unicode_support.is_whitespace()`.

However, `OperatorRecognizer._is_shell_token_delimiter()` uses
`str.isspace()`
([operator.py](../../psh/lexer/recognizers/operator.py#L68)). The brace
standalone test also uses `isspace()`.

Reproduction with a non-breaking space:

```text
!<NBSP>false
```

Observed behavior:

| Shell | Result |
|---|---|
| Bash | Treats the complete text as a command name; status 127 |
| PSH | Treats `!` as negation, command lookup fails, then returns inverted status 0 |

#### Repair

Every lexical whitespace decision must call the canonical
`is_whitespace()` function. Do not use:

- `str.isspace()`
- `str.split()`
- `str.splitlines()`
- regular-expression `\s`

unless a call site explicitly wants a broader non-shell concept.

Add an architecture test that scans production lexer code for `.isspace()`.
Add a Bash comparison matrix for every relevant Unicode `Zs`, line-separator,
and control whitespace code point.

### 3. POSIX mode is not propagated into lexer configuration

The public entry point accepts `strict` and calls `_make_config()`
([__init__.py](../../psh/lexer/__init__.py#L35)). That function chooses between
batch and interactive constructors.

Both constructors currently return the same default configuration, including:

```python
posix_mode = False
```

([position.py](../../psh/lexer/position.py#L80)).

Meanwhile, shell callers pass the POSIX option as `strict`
([source_processor.py](../../psh/scripting/source_processor.py#L289)).
Therefore:

- `strict` is described as batch-versus-interactive behavior.
- Callers use it as a POSIX-mode flag.
- Batch and interactive modes are currently identical.
- Neither path sets `LexerConfig.posix_mode`.

The lexer contains POSIX-aware identifier helpers, but the normal public shell
path does not activate them.

#### Repair

Replace the ambiguous API with:

```python
@dataclass(frozen=True)
class LexerOptions:
    posix_mode: bool = False
    interactive: bool = False
    extglob: bool = False
```

Provide a single conversion at the shell boundary:

```python
options = LexerOptions.from_shell_options(
    shell.state.options,
    interactive=shell.state.interactive,
)
```

Use the same options for:

- Normal command execution.
- Heredoc trial parsing.
- Heredoc execution parsing.
- Analysis visitors.
- Alias tokenization where the active shell mode matters.
- Nested command/process substitutions.

Delete `strict` after migrating all callers. If incomplete-input behavior
eventually differs interactively, represent that as its own explicit option;
do not overload POSIX mode.

## Performance defect: heredoc discovery is quadratic

`HeredocLexer.tokenize_with_heredocs()` appends each command line to
`command_lines`, joins all lines accumulated so far, and creates a new
`ModularLexer` over the entire prefix
([heredoc_lexer.py](../../psh/lexer/heredoc_lexer.py#L95)).

For `N` command lines before a heredoc, the amount of text tokenized is
approximately:

```text
1 + 2 + 3 + ... + N = O(N²)
```

The complete filtered command text is then tokenized again.

Measured CPU time for simple command lines followed by one heredoc:

| Lines before heredoc | CPU time |
|---:|---:|
| 100 | 0.0889s |
| 200 | 0.3333s |
| 400 | 1.3245s |
| 800 | 5.3306s |

The approximately fourfold cost for each doubling is a clear quadratic
signature.

### Target repair: incremental lexer session

Introduce a resumable lexer:

```python
class LexerSession:
    def feed(self, source_chunk: str, *, final: bool = False) -> LexResult:
        ...
```

The session owns:

- Source cursor.
- Quote and expansion state.
- Command-position state.
- Arithmetic and `[[ ]]` state.
- Case-state stack.
- Pending heredoc descriptors.
- Emitted tokens.

At a physical newline:

1. Finish the current command-line lexical state.
2. If heredocs are pending, switch into raw heredoc-body collection.
3. Match delimiter lines without tokenizing their contents.
4. Resume shell tokenization after all pending bodies complete.

Each source character should be consumed a bounded number of times.

### Transitional alternative

If a fully incremental lexer is too large for one change, create a dedicated
single-pass heredoc operator scanner that shares the same quote, expansion,
and delimiter primitives as `ModularLexer`. It may identify command/body
regions and then invoke the normal lexer once on command regions.

This is less desirable because it adds another parallel lexical state machine,
but it is still better than re-lexing every prefix. Treat it as a temporary
step with a removal issue.

### Performance tests

Add CPU-time or operation-count tests for:

- 500, 1,000, and 2,000 command lines before a heredoc.
- Multiple heredocs on one command.
- Heredocs inside command substitutions.
- Multiline quoted delimiters and command continuations.

Prefer an instrumented character-visit count over wall-clock thresholds when
possible. Assert a linear bound such as:

```text
character visits <= K * source length
```

## Recommended target architecture

```text
SourceCursor
    |
    v
Streaming ShellLexer
    |
    v
ReservedWordClassifier
    |
    v
Alias expansion
    |
    v
Parser producing Program + structured Word AST
    |
    v
Brace expansion
    |
    v
Parameter / command / arithmetic / pathname expansion
```

The lexer should own:

- Source segmentation.
- Operators and redirections.
- Shell-word boundaries.
- Quote and expansion extents.
- Reserved-word candidate information.
- Source spans.
- Heredoc body separation.

The lexer should not own:

- Brace expansion results.
- Runtime variable expansion.
- Pathname expansion.
- Assignment semantics beyond enough lexical structure to preserve one shell
  word.
- Validation that belongs to the parser.

## Emit one structured token per shell word

The current lexer emits adjacent tokens such as:

```text
WORD("pre")
STRING(...)
VARIABLE(...)
WORD("-")
COMMAND_SUB(...)
```

It records `adjacent_to_previous`, and the parser reconstructs the logical
word with `TokenStream.peek_composite_sequence()`.

For shell syntax, the natural lexical unit is one word containing structured
parts:

```python
@dataclass(frozen=True)
class WordToken:
    span: SourceSpan
    parts: tuple[WordPart, ...]
```

Example:

```sh
pre"$x"-$(cmd)
```

should produce:

```text
WordToken
├── LiteralPart("pre")
├── DoubleQuotedPart
│   └── ParameterPart(name="x")
├── LiteralPart("-")
└── CommandSubstitutionPart(source="cmd")
```

### Recommended word-part types

Use distinct dataclasses or a closed enum payload:

```text
LiteralPart
EscapedLiteralPart
SingleQuotedPart
DoubleQuotedPart
ParameterExpansionPart
CommandSubstitutionPart
BacktickSubstitutionPart
ArithmeticExpansionPart
ProcessSubstitutionPart
```

Avoid the current combinations of:

- `is_variable`
- `is_expansion`
- string-valued `expansion_type`
- optional `quote_type`

Those combinations permit invalid or contradictory states. Type-specific
payloads make illegal states unrepresentable.

### Benefits

This removes or simplifies:

- `RichToken`.
- `TokenType.COMPOSITE`.
- Word-structure uses of `adjacent_to_previous`.
- Parser-side composite collection.
- Much of `WordBuilder` reconstruction.
- Several parser acceptance lists.
- The distinction between ordinary and “rich” tokens.
- The operator-debris fallback's role in reconstructing fragmented words.

Adjacency may still be useful for diagnostics or alias behavior, but it should
not be the primary representation of a word's internal structure.

## Move brace expansion out of `tokenize()`

The public `_post_lex()` pipeline runs `TokenBraceExpander`
([__init__.py](../../psh/lexer/__init__.py#L47)).

Brace expansion is a semantic word-expansion stage. Performing it on lexer
tokens forces the expander to duplicate:

- Command-prefix tracking.
- Assignment recognition.
- `[[ ]]` region tracking.
- Heredoc delimiter rules.
- Composite-word reconstruction.
- Identifier regular expressions.

The resulting implementation uses private-use placeholders to encode quoted
and opaque token parts before applying a string expander
([brace_expansion_tokens.py](../../psh/expansion/brace_expansion_tokens.py#L209)).
It is careful, but the complexity is a consequence of operating at the wrong
abstraction level.

### Target

Parse the original structured word first. Run brace expansion as the first
stage of `WordExpander`:

```python
expanded_words = brace_stage.expand(word, policy)
```

The parser or AST location can supply an explicit policy:

```text
COMMAND_ARGUMENT
ASSIGNMENT_VALUE
HEREDOC_DELIMITER
ENHANCED_TEST_OPERAND
CASE_PATTERN
ARRAY_ELEMENT
```

Only unquoted literal parts participate. Quoted and expansion parts remain
opaque but retain their exact type and source span.

This preserves Bash's expansion order while eliminating token-level command
context inference.

### Important migration cases

Preserve tests for:

- `a{b,c}`.
- `"x"{1,2}`.
- `$v{1,2}` variable-name fusion.
- `{$((1)),$((2))}`.
- Empty brace alternatives.
- Assignment-prefix suppression.
- No brace expansion inside `[[ ]]`.
- Literal heredoc delimiters.
- Generated metacharacters not being re-lexed as syntax.

## Replace boolean command position with explicit lexical state

`LexerContext` currently stores:

```text
command_position
case_depth
case_expecting_in
in_case_pattern
bracket_depth
arithmetic_depth
```

Several combinations are meaningless, and transitions are spread across the
main lexer, keyword normalizer, and command-substitution scanner.

Use an explicit state:

```python
class LexicalRole(Enum):
    COMMAND_START = auto()
    COMMAND_WORD_SEEN = auto()
    FOR_SUBJECT = auto()
    FOR_WORD_LIST = auto()
    CASE_SUBJECT = auto()
    CASE_EXPECT_IN = auto()
    CASE_PATTERN = auto()
    CASE_BODY = auto()
    FUNCTION_NAME = auto()
```

Maintain nested construct state separately:

```python
@dataclass
class LexicalState:
    role: LexicalRole
    case_stack: list[CaseLexState]
    in_enhanced_test: bool
    arithmetic_depth: int
```

One transition function should receive the emitted token candidate and produce:

```python
@dataclass(frozen=True)
class ClassifiedToken:
    token: Token
    next_state: LexicalState
```

This transition must know whether a word was eligible as a reserved word
before changing state.

## Reduce command-position duplication

PSH currently has three command-position machines:

1. `ModularLexer`.
2. `KeywordNormalizer`.
3. The raw command-substitution extent scanner.

The existing documentation argues that their different input alphabets make
the machines irreducible. They are different under the current architecture,
but the number of machines is not an inherent shell-language requirement.

### Short-term consolidation

Centralize semantic transitions, not only token sets.

Define events such as:

```text
WORD(value, eligible_as_reserved)
STATEMENT_SEPARATOR
PIPELINE_PREFIX
GROUP_OPEN
GROUP_CLOSE
REDIRECTION
CASE_TERMINATOR
```

Each stage may adapt raw text or token types into those events, but the state
transition table should be shared and exhaustively tested.

### Medium-term consolidation

Classify reserved words during the main lexical pass or at one immediately
following immutable classification pass. Do not mutate `Token.type` repeatedly.

The parser should interpret contextual exceptions such as `time` after a pipe
without changing the original token object.

### Long-term command-substitution design

`cmdsub_scanner.py` explicitly states that it is a parser component living in
the lexer. It mirrors:

- Quotes and escapes.
- Comments.
- Heredoc operators and bodies.
- Arithmetic forms.
- Grouping parentheses.
- `case` grammar.
- Command-position rules.

([cmdsub_scanner.py](../../psh/lexer/cmdsub_scanner.py#L285)).

The textbook design is parser-driven nested command substitution:

```text
WordPart: "$("
    -> recursively parse Program
    -> consume the grammatical closing ")"
    -> create CommandSubstitutionPart(program)
```

This resembles Bash's recursive parser strategy and avoids maintaining a
parallel 661-line extent grammar.

It is a long-term change because it affects:

- Incomplete-input detection.
- Heredocs inside substitutions.
- Command substitution execution.
- Source spans.
- Whether substitutions store source, AST, or both.

Do not attempt it before the token and `Program` root contracts are stable.

## Simplify operator recognition

`recognizers/operator.py` currently combines:

- Longest-match operator lookup.
- Arithmetic-context filtering.
- `[[ ]]` classification.
- Single-bracket handling.
- Numeric FD prefixes.
- Named FD prefixes.
- FD duplication and movement.
- Combined redirects.
- Brace-group recognition.
- Extglob interaction.

Split it into:

```text
OperatorScanner
RedirectionScanner
FdPrefixScanner
ContextualOperatorClassifier
```

### Use explicit dispatch instead of numeric plugin priorities

The grammar has a fixed recognizer set. The main loop already handles
whitespace, quotes, and expansions outside the registry, while also
registering `WhitespaceRecognizer`. The abstraction is therefore only partly
applied.

Prefer:

```python
SCANNERS = (
    ProcessSubstitutionScanner(...),
    RedirectionScanner(...),
    OperatorScanner(...),
    WordScanner(...),
)
```

or a first-character dispatch table. Make precedence visible in code and test
overlapping prefixes directly.

If the registry is retained:

- Accept configuration through constructors.
- Reject duplicate priorities unless explicitly permitted.
- Validate recognizer progress.
- Validate that recognizer domains do not overlap unexpectedly.
- Remove the bypassed whitespace recognizer.

### Treat single `[` and `]` as words

The POSIX `[` construct is a command, not a shell operator. Glob brackets and
array subscripts are word syntax. Only `[[` is Bash compound syntax.

Removing general `LBRACKET` and `RBRACKET` operator tokens would simplify:

- Test-command parsing.
- Glob patterns.
- Case patterns.
- Composite-word reconstruction.
- `TokenStream.WORD_LIKE`.
- Operator-debris recognition.

The parser should see:

```text
WORD("[") WORD("x") WORD("=") WORD("x") WORD("]")
```

for the ordinary test command.

## Make tokens immutable and source-faithful

The current `Token`:

- Is mutable.
- Contains many optional fields.
- Duplicates `parts` in `RichToken`.
- Carries `is_keyword` in addition to keyword token types.
- Receives `heredoc_key` dynamically with `setattr()`
  ([heredoc_lexer.py](../../psh/lexer/heredoc_lexer.py#L269)).
- May have its type changed by the parser.

Use:

```python
@dataclass(frozen=True)
class SourceSpan:
    start: int
    end: int


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    span: SourceSpan
    lexeme: str
    payload: TokenPayload | None = None
```

Examples of typed payloads:

```text
WordPayload(parts)
RedirectionPayload(fd, var_fd, combined)
HeredocPayload(key, strip_tabs, quoted)
```

### Preserve raw source separately from interpreted value

The lexer currently sometimes stores cooked content as `value`, such as:

- Unquoted string contents.
- Normalized variable names.
- Rewritten `$[expr]` arithmetic.

Store the raw lexeme or recover it reliably through `SourceSpan`. Any cooked
representation belongs in the typed payload or AST.

This improves:

- Exact diagnostics.
- Formatters.
- Debug output.
- Round trips.
- Unicode normalization decisions.
- Future comment/source preservation.

### Use one source map

Token parts currently carry correct offsets but often line and column zero.
Represent all positions as offsets and use one immutable `SourceMap`:

```python
class SourceMap:
    source: str
    line_starts: tuple[int, ...]

    def location(self, offset: int) -> SourceLocation:
        ...
```

Precompute line starts once. Diagnostics can map offsets lazily. Avoid storing
duplicated line/column data that can become inconsistent with offsets.

### Retire compatibility token kinds

`PARAM_EXPANSION` is documented as emit-dead in the lexer, while
`COMPOSITE` appears to be retained for parser compatibility.

After the word-token migration:

- Remove `PARAM_EXPANSION`.
- Remove `COMPOSITE`.
- Remove `RichToken`.
- Remove `is_keyword`.
- Make `parts` non-optional on word payloads.
- Declare `heredoc_key` rather than adding it dynamically.

## Identifier policy

The lexer has a good mode-aware API in `unicode_support.py`, but not every
lexer path uses it. Named-FD redirect parsing uses `isalpha()` and
`isalnum()`, for example.

All identifier-like syntax must use one policy:

```python
class IdentifierPolicy:
    def is_start(self, char: str) -> bool: ...
    def is_continue(self, char: str) -> bool: ...
    def validate(self, text: str) -> bool: ...
    def normalize(self, text: str) -> str: ...
```

Use it for:

- Variable names.
- Assignment names.
- Named file descriptors.
- Function-name candidates.
- Arithmetic identifiers.
- Parameter expansion.
- Alias/builtin validation where appropriate.

The active policy must come from the explicit lexer options. Default Unicode
identifier support may remain a documented PSH extension, while POSIX mode
must enforce ASCII portable names consistently.

## Testing strategy

The existing lexer unit suite passed during this review:

```text
727 passed, 1 skipped
```

That breadth is valuable, but the reproduced defects show missing dimensions.

### Behavioral differential tests

Generate Bash comparisons around:

- Keyword-looking arguments.
- Command separators.
- Pipeline prefixes.
- `for`, `select`, and `case` headers.
- Function-definition headers.
- `[[ ]]` context.
- Arithmetic context.
- Every redirection form.
- Extglob prefixes.
- Whitespace code points.

Compare:

- Exit status.
- Stdout.
- Stderr category where exact wording is intentionally different.

### Structural invariants

For every successful tokenization:

- The cursor always advances.
- Token spans are monotonic.
- Token spans are within the source.
- Word-part spans lie within their word span.
- No state depth becomes negative.
- No impossible lexical-state combination occurs.
- Every non-heredoc source character is either covered by a token, classified
  shell blank, or an intentionally removed line continuation.
- Reconstructing raw lexemes from spans is lossless.

### Property-based tests

Use Hypothesis or a bounded grammar generator for:

- Quoted/unquoted part concatenation.
- Nested parameter, command, and arithmetic expansions.
- Extglob and glob bracket classes.
- Assignment subscripts.
- Redirect prefixes and targets.
- `case` patterns with unmatched syntax parentheses.
- Heredoc queues.

The generator should shrink failing source strings so state-machine errors are
actionable.

### Performance tests

Cover independent scaling dimensions:

- Number of words.
- Length of one word.
- Number of structured parts in one word.
- Quote nesting.
- Command-substitution nesting.
- Number of lines before a heredoc.
- Number and size of heredoc bodies.
- Number of assignment subscripts.

Use process CPU time or instrumented operation counts. Avoid broad wall-clock
thresholds under xdist.

### Mutation and API tests

After immutable tokens are introduced:

- Assert classification does not alter raw tokens.
- Assert parser execution cannot mutate lexer output.
- Assert repeated normalization produces equal values without object changes.
- Assert every parser implementation accepts the same token contract.

## Staged implementation plan

### Phase 1: repair demonstrated defects

1. Gate keyword/case transitions on the prior command-position state.
2. Replace lexer `.isspace()` calls with `is_whitespace()`.
3. Introduce explicit `LexerOptions`.
4. Propagate POSIX and extglob options through every caller.
5. Add the missing Bash comparison tests.

These are behavior fixes and should be delivered independently of larger
token-model work.

### Phase 2: make heredoc tokenization linear

1. Add the failing scaling test.
2. Introduce `SourceCursor` and resumable lexer state.
3. Move raw heredoc-body collection into the cursor/session.
4. Remove accumulated-prefix re-tokenization.
5. Verify multiline quotes, substitutions, and nested heredocs.

### Phase 3: establish source and token foundations

1. Add `SourceSpan` and `SourceMap`.
2. Add explicit typed token payloads.
3. Declare heredoc metadata.
4. Stop mutating tokens in `KeywordNormalizer` and the parser.
5. Keep compatibility conversion only at a temporary boundary.

### Phase 4: emit one structured word token

1. Add the `WordToken`/`WordPayload` representation.
2. Adapt quote and expansion parsers to emit word parts.
3. Make one word scanner own literal, quoted, and expansion concatenation.
4. Simplify `WordBuilder`.
5. Remove composite reconstruction and `RichToken`.

Run parser differential, formatting, expansion, and execution tests after each
substep.

### Phase 5: relocate brace expansion

1. Introduce AST/Word-based brace expansion with explicit policy.
2. Run it before parameter expansion.
3. Migrate all brace-expansion tests.
4. Remove `TokenBraceExpander` from the lexer entry point.
5. Rename the remaining public entry point to reflect pure lexical behavior.

### Phase 6: consolidate lexical state

1. Replace command-position and case booleans with `LexicalRole`.
2. Centralize transition events.
3. Fold or simplify `KeywordNormalizer`.
4. Split operator and redirection scanning.
5. Remove single-bracket operator tokens and operator debris where possible.

### Phase 7: remove the command-substitution parallel grammar

Only after the canonical `Program`, token, and word contracts are stable:

1. Emit a command-substitution opening word part.
2. Invoke recursive parsing for its body.
3. Consume the grammar-correct closing parenthesis.
4. Store the nested `Program` and source span.
5. Preserve incomplete-input and heredoc behavior.
6. Delete the raw parallel extent grammar.

## Suggested commit sequence

1. `fix(lexer): preserve command position for keyword-like arguments`
2. `fix(lexer): use shell whitespace classification for operators`
3. `fix(lexer): propagate explicit POSIX lexer options`
4. `perf(lexer): tokenize heredoc input incrementally`
5. `refactor(lexer): add source spans and typed token payloads`
6. `refactor(lexer): emit one structured token per shell word`
7. `refactor(expansion): move brace expansion to Word AST`
8. `refactor(lexer): centralize lexical state transitions`
9. `refactor(lexer): split operator and redirection scanners`
10. `refactor(parser): parse command substitutions recursively`
11. `refactor(lexer): remove compatibility token kinds`
12. `docs: document canonical lexer contract`

The first three fixes should not wait for the redesign.

## Definition of done

The lexer improvement program is complete when:

- Keyword-looking arguments cannot enable reserved syntax.
- All whitespace decisions use shell whitespace semantics.
- POSIX mode reaches every lexer path through one explicit options object.
- Heredoc tokenization is demonstrably linear.
- Every parser input begins with the same immutable token contract.
- One logical shell word is one structured lexical token.
- Tokens and word parts carry reliable source spans.
- No dynamic token attributes are used.
- Brace expansion no longer runs inside `tokenize()`.
- Reserved-word classification does not mutate tokens.
- Single `[` and `]` are ordinary word syntax.
- Dead `COMPOSITE` and `PARAM_EXPANSION` token kinds are removed.
- The main lexer and nested command substitutions do not maintain divergent
  copies of shell grammar.
- Differential, conformance, parser, formatter, expansion, and performance
  tests pass.

## Validation performed for this review

- Read the lexer architecture and command-position design documentation.
- Reviewed all lexer modules and their primary consumers.
- Ran `python -m pytest tests/unit/lexer/ -q`:
  - 727 passed.
  - 1 skipped.
- Reproduced the keyword-argument command-position divergence against Bash.
- Reproduced the non-breaking-space negation divergence against Bash.
- Traced the POSIX option from shell callers through `_make_config()` and
  confirmed it does not set `LexerConfig.posix_mode`.
- Benchmarked heredoc tokenization at 100, 200, 400, and 800 command lines and
  observed quadratic scaling.

## Assessment

The lexer does not need wholesale replacement. Its scanners and test corpus
are strong foundations. The right approach is:

1. Fix the demonstrated state and configuration bugs.
2. Remove the quadratic heredoc path.
3. Establish a cleaner token and source model.
4. Move semantic expansion out of the lexer.
5. Consolidate state machines only after those boundaries are stable.

This sequence improves correctness immediately while steadily reducing the
architectural complexity that currently forces the lexer, parser, and
expansion layers to reconstruct each other's information.
