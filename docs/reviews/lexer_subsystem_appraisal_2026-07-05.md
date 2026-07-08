# Lexer Subsystem Appraisal

Date: 2026-07-05  
Version reviewed: PSH 0.649.0  
Commit reviewed: `547d9cdc`

## Executive summary

The lexer is substantially improved and well tested, but it is not yet
textbook quality. It has strong local abstractions and good engineering
discipline, while several reproducible correctness defects expose weaknesses
in raw-character heuristics, duplicated sub-grammars, and the current flat
token model.

| Area | Grade |
|---|---|
| Correctness | B- |
| Architecture | C+ |
| Readability | B |
| Efficiency | C+ |
| Testing | A- |
| Overall | B- |

The recommended direction is incremental repair rather than a wholesale
rewrite. The existing characterization and conformance tests provide a strong
base for changing the token and source-location contracts deliberately.

## Scope and validation

This appraisal examined:

- Public lexer entry points and option propagation.
- Token and token-part contracts.
- Recognizer precedence and progress guarantees.
- Literal words, quoting, expansion extents, comments, and operators.
- Command-position and keyword classification.
- Extglob, arithmetic, command substitution, and process substitution.
- Heredoc discovery, delimiter parsing, collection, and source mapping.
- Parser-facing word reconstruction and brace expansion.
- Complexity, typing, lint, and scaling behavior.

Validation performed:

- `python -m pytest tests/unit/lexer -q`
  - 810 passed, 1 skipped.
- 154 focused command-substitution and heredoc integration/conformance tests
  passed.
- `ruff check psh/lexer`
  - Passed.
- `python -m mypy psh/lexer --disallow-untyped-defs --no-error-summary`
  - Passed.
- `python run_tests.py --quick`
  - 12,640 passed, 1 failed, 1,011 skipped, 12 xfailed, 1 deselected.
  - The sole failure was the unrelated
    `r18t2_builtins_history_write_to_stdout` behavioral case. It passed when
    rerun alone.
- Focused behavior probes were compared with GNU Bash 5.2.26.

The lexer contains approximately 6,717 lines of Python, with approximately
5,901 lines of lexer unit tests. Optional Ruff complexity checking identifies
15 C901 hotspots, including the keyword normalizer, literal collector,
operator recognizer, command-substitution dispatch, and ANSI-C escape
handling.

## Improvements since the previous review

The previous review identified four immediate defects. All four have been
substantially addressed:

1. Keyword-like argument words no longer corrupt command-position state.
2. Operator decisions now use shell whitespace rather than Python's broader
   Unicode whitespace classification.
3. POSIX mode now reaches `LexerConfig` from active shell options.
4. Heredoc discovery is linear for completed logical commands rather than
   re-lexing the complete accumulated source prefix.

Other strengths worth preserving include:

- A single production lexer.
- Pure, directly testable word mini-scanners.
- `WordShapeTracker` and the forward assignment-prefix map.
- A fail-loud no-progress invariant.
- Extensive token-stream and Bash-conformance coverage.
- Fully typed lexer functions.
- Explicit documentation of command-position state and its asymmetries.
- Longest-first operator matching and clear recognizer contracts.

## High-priority correctness findings

### 1. Comment recognition uses raw lookbehind instead of lexical state

`is_comment_start()` decides whether `#` starts a comment from the preceding
source character:

- [comment.py](../../psh/lexer/recognizers/comment.py#L29)
- [literal.py](../../psh/lexer/recognizers/literal.py#L174)

That character may have been escaped, or it may be an operator-looking
character that is actually part of the current word.

#### Reproduction: escaped blank

```sh
printf '<%s>\n' foo\ #bar
```

| Shell | Output |
|---|---|
| Bash | `<foo #bar>` |
| PSH | `<foo >` |

#### Reproduction: comment adjacent to a closing operator

```sh
(true)#comment
echo OK
```

Bash treats `#comment` as a comment and prints `OK`. PSH emits `#comment` as a
word and reports a parse error.

Related failures include:

```text
foo\;#bar
foo\|#bar
foo\<#bar
abc{#x
f()#comment
(( 1 ))#comment
```

The same raw predicate is consumed by heredoc/completeness detection, so the
defect crosses subsystem boundaries.

#### Recommended repair

Comment recognition should depend on explicit lexical state:

- At the start of a shell word, an unquoted `#` begins a comment.
- Once the word scanner has started, an unquoted `#` reached by that scanner
  belongs to the word.
- Escaped separators must not recreate a word boundary.

One simple design is to dispatch comments before starting a new word, while
having the word scanner consume every `#` it reaches after the word begins.
Remove the previous-raw-character heuristic.

Add a Bash differential matrix covering escaped blanks and operators,
operator-adjacent comments, braces within words, function headers, arithmetic
closers, extglob groups, and ordinary `a#b` words.

### 2. Heredoc delimiter parsing has already drifted

Heredoc delimiter quote removal is independently implemented in:

- `HeredocLexer._delimiter_from_source()`
  ([heredoc_lexer.py](../../psh/lexer/heredoc_lexer.py#L210)).
- `_read_heredoc_delimiter()` in the command-substitution scanner.
- `heredoc_delimiter_word()` in `utils/heredoc_detection.py`.
- Parser-side delimiter reconstruction.
- The unused `normalize_heredoc_delimiter()` helper.

The implementations no longer agree on double-quoted backslashes.

#### Reproduction

```sh
cat <<"E\q"
OK
E\q
echo TAIL
```

Inside double quotes, Bash preserves a backslash before `q`. The lexer instead
reduces the delimiter to `Eq`. A direct `tokenize_with_heredocs()` call records:

```text
key:     heredoc_0_Eq
content: "OK\nE\\q\necho TAIL\n"
```

The separate completeness detector derives `E\q`, demonstrating the drift
directly. In the normal command-processing path this changes output by
including the terminator in the body.

The command-substitution delimiter reader has an additional empty-delimiter
problem: a quoted empty word such as `<<""` produces an empty output buffer and
is treated as though no delimiter were present.

#### Recommended repair

Create one canonical typed primitive:

```python
@dataclass(frozen=True)
class HeredocDelimiter:
    raw: str
    value: str
    quoted: bool


def parse_heredoc_delimiter(raw: str) -> HeredocDelimiter:
    ...
```

It must implement exact shell quote removal:

- Outside quotes, backslash quotes the next character.
- Inside single quotes, every character is literal.
- Inside double quotes, backslash is removed only before `$`, backtick, `"`,
  `\`, or newline.
- Empty quoted delimiters are valid.

Use this primitive in the command accumulator, lexer, command-substitution
handling, and both parsers. The parser should consume the already-derived
delimiter descriptor rather than reconstructing it again from flattened token
values.

### 3. Extglob group scanning ignores quotes and nested expansions

`scan_extglob_group()` counts parentheses and handles backslash escapes, but
does not treat quotes or nested expansions as opaque:

- [word_scanners.py](../../psh/lexer/recognizers/word_scanners.py#L347)

#### Reproductions

With extglob enabled:

```sh
printf '<%s>\n' @(")"|x)
printf '<%s>\n' @(a|$(printf ")"))
```

Both are accepted by Bash. PSH terminates the extglob at the quoted or nested
`)`, producing an unclosed-quote or unexpected-parenthesis error.

#### Recommended repair

The scanner must skip complete regions for:

- Single and double quotes.
- ANSI-C and locale quotes.
- Parameter expansions.
- Command substitutions.
- Arithmetic expansions.
- Nested extglob groups.

An extent-only repair is necessary but insufficient for the long-term model:
flattening the complete extglob into one `WORD` also loses quote provenance
that can affect pattern semantics. Structured word parts are the durable
solution.

### 4. Deprecated `$[...]` scanning has the same delimiter flaw

`ExpansionParser._parse_dollar_bracket_arithmetic()` balances raw brackets
without respecting nested quotes or shell expansions:

- [expansion_parser.py](../../psh/lexer/expansion_parser.py#L64)

#### Reproduction

```sh
echo $[1 + $( : "]"; printf 2 )]
```

Bash prints `3`. PSH closes the `$[...]` region at the quoted bracket and later
reports an unclosed quote.

#### Recommended repair

Either:

- Implement a quote- and expansion-aware arithmetic extent scan, sharing the
  same nested-region primitives as other scanners; or
- Parse `$[...]` into a structured arithmetic part before translating it to
  the canonical `$((...))` representation.

The second approach avoids textual rewriting before the lexical structure is
known.

### 5. Opaque command substitutions delay syntax errors until execution

The lexer emits a complete `$(...)` region as one opaque token. A 661-line
parallel grammar in `cmdsub_scanner.py` determines its extent, but the nested
command body is not parsed while the outer command is parsed.

#### Reproduction

```sh
printf BEFORE
echo $(if)
printf AFTER
```

Bash rejects the complete script before producing output. PSH prints the
surrounding output, diagnoses the nested parse failure during expansion, and
allows the final successful command to determine status.

This is a parser/execution-boundary failure, but the enabling design is the
lexer's opaque command-substitution token.

#### Documented same-line heredoc divergence

The command-substitution scanner explicitly documents that PSH does not model
Bash's handling of a heredoc opened in a substitution that closes on the same
physical line:

- [cmdsub_scanner.py](../../psh/lexer/cmdsub_scanner.py#L258)

For example:

```sh
printf 'sub=<%s>\n' "$(cat <<EOF)"
BODY
EOF
echo tail
```

Bash supplies `BODY` to the nested `cat`. PSH produces an empty substitution
and attempts to execute `BODY` and `EOF` as commands.

#### Recommended repair

The textbook solution is parser-driven recursion:

1. When the outer word parser encounters `$(`, recursively parse a nested
   `Program`.
2. Let the nested parser consume the grammatical closing `)`.
3. Store the nested `Program`, original source span, and substitution mode in a
   `CommandSubstitutionPart`.
4. Propagate nested syntax errors during outer parsing.
5. Share heredoc scheduling with the enclosing parse.

This mirrors the conceptual strategy used by Bash and removes the need to keep
a parallel shell grammar synchronized solely for extent detection.

## Efficiency findings

### 1. Long literal words scale superlinearly

`LiteralRecognizer._collect_literal_value()` appends each segment to a growing
string through a nonlocal closure:

- [literal.py](../../psh/lexer/recognizers/literal.py#L174)
- [literal.py](../../psh/lexer/recognizers/literal.py#L192)

Measured CPU time for one unbroken word:

| Word length | CPU time |
|---:|---:|
| 160,000 | 0.44s |
| 320,000 | 1.14s |
| 640,000 | 3.36s |

Profiling attributes most of the cost to the `take()` closure. The current
performance test covers many short quoted words and does not exercise one very
large token.

#### Recommended repair

- Accumulate source slices in a list and call `''.join()` once.
- Better, retain start/end spans for unchanged source fragments and materialize
  only when escapes or transformations require it.
- Add operation-count and CPU scaling tests for one 100K-1M character word.
- Add an ASCII fast path to identifier classification if profiling still shows
  `unicodedata.category()` as significant.

### 2. Multiline incomplete commands remain quadratic in heredoc discovery

The recent heredoc change avoids whole-prefix re-lexing for completed logical
commands. However, while a quote or expansion remains incomplete,
`pending_lines` is rejoined and tokenized from its beginning after every new
physical line:

- [heredoc_lexer.py](../../psh/lexer/heredoc_lexer.py#L99)

Measured characters passed to `ModularLexer`:

| Lines in one open quoted command | Source characters | Characters lexed | Ratio |
|---:|---:|---:|---:|
| 50 | 126 | 2,928 | 23.2x |
| 100 | 226 | 10,828 | 47.9x |
| 200 | 426 | 41,628 | 97.7x |
| 400 | 826 | 163,228 | 197.6x |
| 800 | 1,626 | 646,428 | 397.6x |

The existing heredoc scaling test uses complete command lines, so it does not
cover this remaining path.

#### Recommended repair

Introduce a resumable lexer session that carries:

- Cursor and source-position state.
- Quote and expansion nesting.
- Command position.
- Arithmetic, `[[ ]]`, and case state.
- Pending heredoc descriptors.
- Current structured word parts.

Each new physical line should resume from the prior lexical state rather than
restart the logical command.

### 3. Secondary scaling risks

- `OperatorRecognizer._try_fd_duplication()` creates
  `input_text[pos:]` at every numeric-token candidate
  ([operator.py](../../psh/lexer/recognizers/operator.py#L86)). For `N`
  numeric words, the total substring length allocated is quadratic.
- Heredoc queues call `pop(0)` in both the main collector and the
  command-substitution scanner. Use `collections.deque`.
- Several mini-scanners create a full `remaining = text[pos:]` slice.
- `PositionTracker` walks text after recognizers have already scanned it.
  A shared source cursor can update offsets, lines, and columns in the same
  forward pass.

## Token and source-location model

### 1. Token-part locations are invalid

`TokenPart` instances created by quote and expansion parsers use line and
column zero:

- [token_parts.py](../../psh/lexer/token_parts.py#L11)
- `quote_parser.py`
- `expansion_parser.py`

Although the quote parser accepts a `PositionTracker`, it never uses it. The
comments claiming that the tracker will fill these locations are inaccurate.
Current production code barely consumes part locations, making this a
partially dead feature rather than reliable metadata.

### 2. Heredoc body removal destroys original coordinates

`HeredocLexer` removes body and delimiter lines, joins the remaining command
lines, and tokenizes that compressed text. Tokens after the heredoc therefore
have offsets and line numbers relative to filtered text rather than the
original source.

For:

```sh
cat <<EOF
body
EOF
if
```

the `if` token is reported on line 2 by the lexer although it originated on
line 4. A direct parser error reports compressed EOF coordinates as well.

#### Recommended repair

Use an explicit source map between filtered command text and original source,
or retain body lines as equal-length non-tokenizing placeholders. A general
`SourceSpan` should contain original start/end offsets and derive line/column
through one immutable source index.

### 3. Token metadata is mutable and weakly typed

- `Token.parts` is declared optional but is always converted to a list.
- `RichToken.from_token()` omits `is_keyword`, `fd`, `var_fd`, and
  `combined_redirect`
  ([token_parts.py](../../psh/lexer/token_parts.py#L30)).
- `heredoc_key` is attached dynamically with `setattr`.
- `PARAM_EXPANSION` and `COMPOSITE` are effectively emit-dead compatibility
  types.
- Keyword normalization mutates token types in place.
- `matches_keyword_type()` is a predicate with the side effect of setting
  `is_keyword`.

Use frozen token objects with explicit payloads. Classification should return
new typed tokens or parser terminals rather than mutate shared input.

## Architectural appraisal

### Current pipeline

The public `tokenize()` contract currently performs:

```text
source
  -> ModularLexer
  -> KeywordNormalizer
  -> TokenBraceExpander
  -> parser-facing tokens
```

This combines lexical analysis, reserved-word classification, and semantic
brace expansion.

### Brace expansion is in the wrong layer

`_post_lex()` invokes `TokenBraceExpander`:

- [lexer/__init__.py](../../psh/lexer/__init__.py#L65)

Consequences include:

- `tokenize("echo {a,b}")` no longer describes the source token stream.
- Both generated words carry the same source span.
- `--format` emits `echo a b`, losing the original brace syntax.
- The brace expander must duplicate command-prefix, assignment, `[[ ]]`, word
  adjacency, and heredoc-delimiter policy.
- The lexer package depends upward on the expansion subsystem.

Brace expansion should run on the parsed structured word as the first semantic
expansion stage.

### The natural token is one structured shell word

The lexer currently emits adjacent tokens and asks the parser to reconstruct
one word:

```text
WORD("pre")
STRING(...)
VARIABLE(...)
WORD("-")
COMMAND_SUB(...)
```

A more direct model is:

```python
@dataclass(frozen=True)
class WordToken:
    span: SourceSpan
    parts: tuple[WordPart, ...]
```

Recommended closed part types:

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
ExtglobPart
```

This would remove or simplify:

- `RichToken`.
- `TokenType.COMPOSITE`.
- Most uses of `adjacent_to_previous`.
- Parser-side composite collection.
- Several broad parser token-acceptance lists.
- The operator-debris compatibility recognizer.
- Private-use placeholder encoding in token-level brace expansion.
- Invalid combinations of `is_variable`, `is_expansion`,
  string-valued `expansion_type`, and optional `quote_type`.

### Command position is tracked three times

Independent command-position machines exist in:

1. `ModularLexer`.
2. `KeywordNormalizer`.
3. The raw command-substitution extent scanner.

The documentation states that their distinct input alphabets make them
irreducible. Their adapters differ, but the semantic transition logic can
still be centralized.

Define classified events such as:

```text
WORD(value, reserved_word_eligible)
STATEMENT_SEPARATOR
PIPELINE_PREFIX
GROUP_OPEN
GROUP_CLOSE
REDIRECTION
CASE_TERMINATOR
```

Each layer may adapt its input into events, but one transition function should
own the command-position state table. Parser-driven nested substitutions would
eventually remove the raw-text machine entirely.

### Keyword normalization is repeated

The public lexer runs `KeywordNormalizer`, then both parser implementations
normalize shallow copies of the same token list again. Because the copies
contain the same mutable token objects, normalization still mutates the
originals.

Classify reserved words exactly once. Make the classification pass immutable
and idempotence unnecessary.

### Recognizer abstraction is only partially applied

The main loop handles whitespace, quotes, and expansions outside the registry,
while also registering `WhitespaceRecognizer`. The latter is unreachable
because `_skip_whitespace()` always runs first.

The recognizer set is fixed, so numeric plugin priorities obscure a static
grammar decision. An explicit dispatch table or ordered scanner tuple would
make precedence easier to audit.

`OperatorRecognizer` also combines too many responsibilities:

- Longest-match operator lookup.
- FD duplication and movement.
- Numeric and named FD prefixes.
- Combined redirects.
- Brace-group recognition.
- Arithmetic and `[[ ]]` contextual filtering.
- Extglob disambiguation.

Split it into redirection scanning, raw operator scanning, and contextual
classification.

### Configuration surface contains compatibility residue

- `strict=True` and `strict=False` select identical lexer configurations.
- Some callers historically passed POSIX state through `strict`, while the
  corrected implementation now obtains POSIX state from `shell_options`.
- `case_sensitive` is configurable internally but has no coherent public shell
  option and can make variable-reference normalization disagree with
  assignment spelling.
- Interactive and batch constructors are identical.

Introduce a frozen, explicit options object and remove the compatibility
arguments after migrating callers:

```python
@dataclass(frozen=True)
class LexerOptions:
    posix: bool = False
    extglob: bool = False
    interactive: bool = False
```

## Test appraisal

The test suite is one of the subsystem's strongest features. Particularly
valuable assets include:

- The frozen token-stream corpus.
- Direct mini-scanner tests.
- Command-position consistency tests.
- Command-substitution scanner/parser comparison.
- Bash-focused conformance suites.
- Deterministic character-count scaling tests.
- The fail-loud progress census.

The main weakness is that some tests preserve prior implementation behavior
rather than independently state shell semantics. For example,
`WordShapeTracker` is checked against retired heuristics, so it proves
refactoring equivalence rather than correctness against Bash or a grammar.

Add adversarial cross-product tests around every delimiter scanner:

- Delimiter inside single quotes.
- Delimiter inside double quotes.
- Escaped delimiter.
- Delimiter inside `${...}`.
- Delimiter inside `$()` and `$((...))`.
- Delimiter inside nested extglob.
- Newline and comment boundaries.
- Complete and incomplete forms.

The newly reproduced comment, heredoc, extglob, and `$[...]` cases should be
added as Bash differential regressions before implementation changes.

## Recommended target architecture

```text
Original source + SourceIndex
          |
          v
Resumable SourceCursor / ShellLexer
          |
          v
Immutable structural tokens
  - operators
  - redirections
  - structured WordToken
  - heredoc descriptors
          |
          v
Single reserved-word classifier
          |
          v
Parser
  - recursively parses command/process substitutions
  - produces Program + structured Word AST
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
- Shell-word boundaries and typed word parts.
- Quote and expansion extents.
- Reserved-word eligibility.
- Original source spans.
- Heredoc body separation and delimiter descriptors.

It should not own:

- Brace expansion results.
- Runtime variable or pathname expansion.
- Repeated keyword mutation.
- A second shell parser used only to locate `)`.

## Prioritized implementation plan

### Phase 1: immediate correctness

1. Replace raw-lookbehind comment recognition with explicit word-start state.
2. Introduce one canonical heredoc delimiter parser and migrate every caller.
3. Make extglob scanning quote- and expansion-aware.
4. Make `$[...]` scanning reuse grammar-aware nested-region primitives.
5. Add the demonstrated Bash 5.2 differential cases.

### Phase 2: scaling and metadata

1. Replace growing-string literal accumulation with chunked construction.
2. Add a resumable lexical session for multiline incomplete commands.
3. Replace front-popped lists with deques and remove remainder slicing.
4. Introduce immutable `SourceSpan` and source-map contracts.
5. Populate or remove token-part locations; do not expose invalid zero
   coordinates.

### Phase 3: structured words

1. Add `WordToken` and closed `WordPart` types.
2. Migrate parser word construction to consume them directly.
3. Remove `RichToken`, `COMPOSITE`, and parser-side adjacency reconstruction.
4. Retire the operator-debris compatibility recognizer.
5. Move brace expansion onto the structured Word AST.

### Phase 4: remove parallel grammar

1. Parse command and process substitutions recursively during outer parsing.
2. Store their nested `Program` values on word parts.
3. Share heredoc scheduling across nested parses.
4. Delete `cmdsub_scanner.py` once all extent and incomplete-input cases are
   parser-owned.

### Phase 5: simplify the remaining lexer

1. Normalize keywords exactly once.
2. Consolidate command-position transitions.
3. Split operator and redirection scanning.
4. Replace numeric recognizer priorities with explicit dispatch.
5. Remove dead token types, unreachable recognizers, dynamic attributes, and
   obsolete configuration arguments.

## Final assessment

The lexer is production-capable, significantly improved, and protected by an
excellent test base. Its strongest qualities are explicit invariants, focused
mini-scanners, typing, conformance work, and a willingness to document known
divergences.

The remaining failures are not random edge noise. They follow directly from
four architectural choices:

1. Raw-character heuristics are used where lexical state is required.
2. Delimiter grammars are independently reimplemented.
3. Shell words are split into loosely connected flat tokens.
4. Nested shell programs are extent-scanned rather than recursively parsed.

Correcting those seams, while preserving the existing test assets, would move
the subsystem from a strong compatibility-oriented implementation toward a
smaller, source-faithful, textbook-quality lexer.
