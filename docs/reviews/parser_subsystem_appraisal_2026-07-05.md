# Fresh Parser Subsystem Appraisal

Date: 2026-07-05  
Scope: `psh/parser/`, its AST contracts, and the lexer/scripting/execution seams that determine parser correctness

## Executive summary

| Area | Grade |
|---|---:|
| Production recursive-descent parser | **B+** |
| Core grammar coverage | **A−** |
| Architecture and AST contracts | **B+** |
| Efficiency | **A** |
| Diagnostics and recovery | **C+** |
| Tests | **A−** |
| Visualization utilities | **C** |
| Educational combinator parser | Not production-graded |

The production recursive-descent parser is broad, fast, and substantially
cleaner than during the previous review. It is close to excellent, but several
correctness defects and some dormant configuration and recovery machinery
prevent a textbook-quality grade.

The most important remaining issue is that modern command and process
substitutions store raw command text instead of recursively parsed ASTs.
Consequently, invalid nested syntax can be discovered only during expansion,
after other commands from the same input buffer have already executed.

The next most important issue is that `ParserConfig` advertises strict-POSIX,
feature-gating, and error-collection behavior that the production grammar and
shell parse boundary do not consistently use. Error collection itself is not a
safe recovery implementation: it can return a fabricated AST after required
tokens were absent.

The parser's ordinary shell grammar is nevertheless strong. A focused
485-input acceptance comparison against Bash 5.2 produced only three initial
divergence families; narrower probes then characterized those families and
found one additional empty-case-pattern issue. Flat parsing scales linearly,
and the parser-focused test suite is extensive.

## What has improved since the previous appraisal

### The historical root-shape compatibility layer is gone

The prior root-shape criticism has been fully resolved:

- Every successful parse returns `Program`, including empty input.
- `TopLevel`, the `CommandList` alias, `_simplify_result()`,
  `_bare_top_level_compound()`, and `_BARE_TOP_LEVEL_TYPES` are gone.
- Top-level and nested commands use the same statement, and-or-list, pipeline,
  and command grammar.
- A bare compound command keeps its ordinary
  `AndOrList -> Pipeline -> Command` ancestry.
- The recursive-descent and combinator entry points expose the same concrete
  root type.
- Root execution now has one `Program` entry point.

The implementation in
[`recursive_descent/parser.py`](../../psh/parser/recursive_descent/parser.py)
is direct and readable. The architecture tests in
`tests/unit/parser/test_root_contract.py`,
`tests/unit/parser/test_program_root.py`, and
`tests/unit/parser/test_top_level_control_structure_grammar.py` provide strong
guardrails against reintroducing the compatibility layer.

### Other strengths

The parser now has several notably strong properties:

- Eight focused recursive-descent sub-parsers provide a clear decomposition.
- `ParserContext` is the single token-position and diagnostic state owner.
- `Word` is the canonical source of truth for simple-command arguments;
  `SimpleCommand.args` is derived.
- Parameter-expansion classification delegates to the shared
  `expansion/param_parser.py` grammar.
- Flat command lists, pipelines, and boolean chains parse iteratively.
- Structured `at_eof`, `unclosed_expansion`, and `missing_terminator` signals
  avoid diagnostic string matching.
- The open-construct trail is honestly scoped to continuation hints rather
  than grammar decisions.
- Heredoc, function, array, compound-command, and conditional coverage is
  extensive.
- The parser has a clean canonical `Program` result contract.

## Validation performed

### Tests and static analysis

The following parser-focused checks were run against the current tree:

```text
python -m pytest tests/unit/parser tests/parser_differential -q
1,075 passed

python -m pytest -q \
  tests/integration/parser \
  tests/integration/parsing \
  tests/conformance/bash/test_grammar_boundaries_conformance.py \
  tests/conformance/bash/test_reappraisal7_syntax_errors_conformance.py \
  tests/conformance/bash/test_heredoc_delimiter_conformance.py \
  tests/conformance/bash/test_numbered_heredoc_herestring_conformance.py \
  tests/conformance/posix/test_heredoc_fd_jobs_conformance.py \
  tests/regression/test_parser_review_fixes.py \
  tests/performance/benchmarks/test_parsing_performance.py
558 passed, 1 xfailed

ruff check psh/parser
All checks passed

python -m mypy psh/parser --no-error-summary
No errors
```

An optional stricter mypy pass with `--disallow-untyped-defs` reported 88
missing annotations. Most are in the educational combinator and visualization
packages; the production recursive-descent parser accounts for a much smaller
share.

An optional Ruff complexity pass found 20 `C901` hotspots:

- 13 in the educational combinator parser.
- 4 in visualization.
- 3 in production recursive-descent code, including the heredoc walker.

### Differential checks

A generated 485-input grammar corpus was compared with Bash 5.2. The ordinary
grammar agreed closely. The initial acceptance divergences were:

1. Regex operand over-acceptance in `[[ ... =~ ... ]]`.
2. Whitespace-separated array-initializer recognition.
3. An omitted `do` after a C-style `for` header.

Focused probes expanded the first two families and found empty alternatives in
case patterns.

### Efficiency measurements

Local median lex-and-parse measurements were:

| Input | Time |
|---|---:|
| 100 simple commands | 0.007 s |
| 1,000 simple commands | 0.055 s |
| 10,000 simple commands | 0.659 s |
| 100 command arguments | 0.0017 s |
| 1,000 command arguments | 0.0169 s |
| 5,000 command arguments | 0.0806 s |
| 100 pipeline components | 0.0031 s |
| 1,000 pipeline components | 0.0319 s |
| 5,000 pipeline components | 0.1743 s |

These results are consistent with linear parsing for flat inputs. No
algorithmic performance problem was found in the production grammar.

## Priority correctness findings

## 1. Modern command and process substitutions are not recursively parsed

### Current behavior

`CommandSubstitution` and `ProcessSubstitution` store raw command strings:

```python
@dataclass
class ProcessSubstitution(Expansion):
    direction: str
    command: str

@dataclass
class CommandSubstitution(Expansion):
    command: str
    backtick_style: bool = False
```

`WordBuilder` strips the delimiters and constructs these nodes without parsing
the nested command:

```python
elif token_type == TokenType.COMMAND_SUB:
    return CommandSubstitution(strip_command_sub(value),
                               backtick_style=False)

elif token_type in (TokenType.PROCESS_SUB_IN,
                    TokenType.PROCESS_SUB_OUT):
    return ProcessSubstitution(
        direction=direction,
        command=strip_process_sub(value),
    )
```

The expansion or I/O subsystem later starts a child shell and parses the raw
string during execution.

### Observable consequence

Given:

```sh
echo before; echo $(if); echo after
```

PSH:

1. Executes `echo before`.
2. Encounters the syntax error while expanding `$(if)`.
3. Executes `echo after`.
4. Returns the final command's successful status.

Bash rejects the complete command buffer before executing any command.

The same early-validation defect occurs with malformed modern command
substitutions inside parameter-expansion words:

```sh
echo before; echo ${x:-$(if)}; echo after
```

Process substitutions have the same structural problem.

Backtick substitutions require separate treatment: Bash itself performs
important parts of legacy backtick parsing later and can continue around an
inner syntax error. A refactor must not blindly force identical timing on both
substitution syntaxes.

### Why this matters

This is more than an AST elegance issue:

- Syntax errors occur at the wrong phase.
- Commands can execute when Bash would reject the whole input.
- The final exit status can be wrong.
- Validation, linting, security analysis, metrics, and formatting cannot see
  commands inside substitutions.
- Nested source positions are reconstructed from a new parse rather than
  retained from the original input.
- Alias timing can differ because the nested body is parsed against runtime
  alias state instead of parse-time state.

### Recommended target

Modern command and process substitutions should carry a nested `Program`:

```python
@dataclass
class CommandSubstitution(Expansion):
    program: Program
    source: str
    backtick_style: bool = False


@dataclass
class ProcessSubstitution(Expansion):
    direction: str
    program: Program
    source: str
```

Retaining `source` is useful for formatting, diagnostics, and `$BASH_COMMAND`;
execution semantics should come from `program`.

Do not make the static `WordBuilder` call a global parser factory. Convert it
to an object bound to the current parser, or inject a typed
`parse_nested_command(source, span)` callback. That callback must:

- Use the same active production grammar.
- Preserve source offsets and line information.
- Apply the correct alias policy.
- Handle nested heredocs.
- Share the parent parser's resource accounting.

Add end-to-end tests asserting that invalid modern substitutions prevent every
command in the outer buffer from executing.

## 2. `ParserConfig` is largely a façade

### Feature gates are bypassed

The main parser defines guarded methods:

```python
def parse_enhanced_test_statement(self):
    if not self.should_allow('bash_conditionals'):
        self.check_posix_compliance(...)
    return self.tests.parse_enhanced_test_statement()

def parse_arithmetic_command(self):
    self.require_feature('arithmetic', ...)
    if not self.should_allow('bash_arithmetic'):
        self.check_posix_compliance(...)
    return self.arithmetic.parse_arithmetic_command()
```

However, grammar dispatch calls the sub-parsers directly:

```python
elif self.parser.match(TokenType.DOUBLE_LPAREN):
    return self.parser.arithmetic.parse_arithmetic_command()
elif self.parser.match(TokenType.DOUBLE_LBRACKET):
    return self.parser.tests.parse_enhanced_test_statement()
```

Searches found no production calls to the guarded main-parser methods. Direct
use of `ParserConfig.strict_posix()` therefore still accepts `[[ ... ]]`, and
`ParserConfig(enable_arithmetic=False)` still accepts `(( ... ))`.

### Shell configuration is not translated

`create_parser()` always constructs a fresh default `ParserConfig`.
`parse_with_heredocs()` does the same. The source processor passes the active
parser name and source information, but not parser configuration derived from
shell options.

Consequences include:

- `collect_errors` does not enable parser collection in the live shell.
- Parser-side strict-POSIX feature gates are not active.
- `no_arithmetic`, `no_arrays`, and `no_functions` are advertised by
  `parser-config`, but are not registered consistently and do not drive the
  production parser.
- Heredoc and non-heredoc parsing cannot be configured uniformly.

Some `posix` behavior still reaches the lexer and runtime subsystems; the
problem is specifically that the advertised parser configuration does not
control the production parser as documented.

### Configuration APIs fail silently

`ParserConfig.clone()` silently ignores unknown override fields. The test suite
explicitly characterizes this behavior:

```python
cloned = config.clone(nonexistent_field=True)
```

This makes misspelled configuration ineffective without any signal. Dynamic
string APIs such as `is_feature_enabled("...")` and `should_allow("...")` have
the same typo-to-false behavior.

### Recommended resolution

Choose one of two honest designs.

#### Preferred pragmatic design

Remove parser modes and feature flags that have no production requirement:

- `ErrorHandlingMode`
- `error_handling`
- `collect_errors`
- `max_errors`
- unused feature gates
- `create_configured_parser()` if it remains test-only
- parser-control builtin commands that advertise unavailable behavior

The shell already has concrete lexer and runtime options. A smaller parser
configuration containing only real grammar capabilities is easier to trust.

#### If configurable parsing is a product requirement

Then:

1. Add `ParserConfig.from_shell_options(options)`.
2. Accept `config` in `create_parser()` and `parse_with_heredocs()`.
3. Pass the same configuration through the trial parser, execution parser, and
   analysis-mode parser.
4. Route compound dispatch through the checked methods.
5. Replace string feature names with typed fields or enums.
6. Replace custom `clone()` logic with `dataclasses.replace()`, allowing
   unknown fields to raise.
7. Add end-to-end tests through `parser-config`, not only direct field tests.

## 3. Error collection is not safe error recovery

### Current behavior

When `collect_errors=True`, `ParserContext.consume()` records an error and
returns the current unexpected token without consuming it:

```python
if self.config.collect_errors:
    self.add_error(error)
    return current
```

Other error sites use explicit `raise self.parser.error(...)` and ignore
collection entirely. There are no recovery productions, synchronization sets,
error nodes, or guaranteed-forward-progress rules.

For:

```sh
if true; then echo x
```

collection mode records a missing-`fi` error but returns a `Program` containing
an apparently completed `IfConditional`. The parser simply treats EOF as the
missing token and unwinds the construct.

### Dead supporting machinery

- `ErrorHandlingMode` is never read.
- `fatal_error` is never meaningfully set because no parser error receives
  `ErrorSeverity.FATAL`.
- `should_collect_errors()` becomes true if the error list is already nonempty,
  regardless of configuration.
- `can_continue_parsing()` is not used as a grammar recovery driver.
- The public return type is only `Program`; diagnostics are hidden in mutable
  parser context.

### Recommended resolution

Delete collection mode unless there is a concrete IDE/editor consumer.

If recovery is required, design it explicitly:

```python
@dataclass
class ParseResult:
    program: Program
    diagnostics: list[ParseDiagnostic]
    is_valid: bool
```

Then:

- Define synchronization tokens for statement, pipeline, case-item, and
  compound-body contexts.
- Guarantee that every recovery action advances or exits.
- Insert explicit `ErrorNode` objects where structure is missing.
- Never execute a result containing error diagnostics.
- Distinguish warnings from syntax errors through typed diagnostics.
- Test multiple independent errors in a single buffer.

## 4. Missing EOF sentinel causes nontermination

`ParserContext.peek()` currently returns the final token whenever the cursor is
beyond the token list:

```python
if pos < len(self.tokens):
    return self.tokens[pos]
return self.tokens[-1] if self.tokens else Token(TokenType.EOF, "", 0)
```

`advance()` also refuses to move past `len(tokens) - 1`.

The lexer normally supplies an EOF token, but the parser is a public API whose
type and documentation merely say `List[Token]`. Supplying one ordinary token
without EOF causes an infinite loop:

```python
Parser([Token(TokenType.WORD, "echo", 0)]).parse()
```

### Recommended fix

Use the same end discipline as `lexer.TokenStream`:

- `at_end()` must be true when `current >= len(tokens)`.
- Out-of-range `peek()` must return a stable synthetic EOF, not the last real
  token.
- `advance()` may move to `len(tokens)`.
- Negative positions should be rejected.

Alternatively, validate in `create_context()` that exactly one EOF token is
present at the end and raise a clear contract error. Supporting both sentinel
and sentinel-free token sequences is more robust and only marginally more
complex.

Add a timeout-protected regression test so future nontermination is detected.

## 5. Narrow Bash grammar divergences

### C-style `for` incorrectly makes `do` optional

`_parse_c_style_for()` says:

```python
# DO keyword is optional in C-style for loops
if self.parser.match(TokenType.DO):
    self.parser.advance()
```

Bash requires `do`, allowing either a semicolon or suitable line break before
it. PSH accepts:

```sh
for ((i=0; i<2; i++)); echo x; done
```

It should call:

```python
self.parser.expect(TokenType.DO)
```

after consuming permitted separators.

### Array-initializer recognition ignores adjacency

`_candidate_initializer()` recognizes:

```text
WORD name + WORD "=" / "+=" + LPAREN
```

without checking `adjacent_to_previous`. It also recognizes `WORD "name="`
followed by a non-adjacent `LPAREN`.

PSH therefore accepts:

```sh
a= (x y)
a =(x y)
a = (x y)
a += (x y)
```

which Bash rejects as array initializers.

Require adjacency between every source fragment that belongs to the assignment
head. A normalized candidate should carry and verify its exact source span.

### Array-element values can consume non-adjacent words

`_parse_element_value()` defines:

```python
has_continuation = (
    self.parser.match_any(TokenGroups.WORD_LIKE)
    and (not tail or self.parser.peek().adjacent_to_previous)
)
```

When `tail` is empty, any following word is consumed, even if whitespace
separates it:

```sh
a[0]= x
```

PSH assigns `x` as the array value. Bash treats the empty assignment and
following command according to shell assignment-prefix rules.

Continuation must always require lexical adjacency. Empty assignment values
should produce `Word(parts=[])` without consuming the next shell word.

Split element heads such as `a[0] =x` also need adjacency checks before being
classified as assignments.

### Conditional regex parsing over-accepts syntax tokens

`_parse_regex_operand()` reconstructs a regex by consuming nearly any token
until `]]`, `&&`, `||`, newline, or EOF. It consequently accepts:

```sh
[[ x =~ ; ]]
[[ x =~ & ]]
[[ x =~ < ]]
[[ x =~ > ]]
[[ x =~ ( ]]
[[ x =~ ) ]]
```

Bash treats these as conditional syntax errors. PSH may evaluate them later,
print a regex error, continue executing the rest of the buffer, and return a
later command's status.

The regex parser needs an explicit conditional-regex token policy:

- Reject top-level shell separators and redirection operators.
- Track and require balanced grouping.
- Preserve quoted and escaped metacharacters.
- Preserve bracket-expression nesting.
- Allow legal regex operators such as `|`.
- Emit a parse error, not a runtime regex warning, for conditional grammar
  errors.

A dedicated `parse_conditional_regex_word()` with a Bash differential corpus is
preferable to an open-ended “consume everything” loop.

### Empty case-pattern alternatives are accepted

`_parse_case_pattern()` may return:

```python
CasePattern(pattern="", word=Word(parts=[]))
```

Therefore PSH accepts malformed forms such as:

```sh
case x in x|) : ;; esac
case x in (|x) : ;; esac
case x in () : ;; esac
case x in (x|) : ;; esac
```

Require at least one word part per alternative before accepting `|` or `)`.

## Resource-safety finding

## 6. The nesting guard depends on `Shell` changing global interpreter state

`MAX_NESTING_DEPTH` is 1,000. Comments explain that one nested compound uses
roughly nine to twelve Python frames, so the shell raises
`sys.setrecursionlimit()` to 40,000 during `Shell` construction.

The public parser can be imported and used without constructing `Shell`.
Under Python's default recursion limit of 1,000, direct parser use raised
`RecursionError` at approximately 200 nested brace groups, long before the
parser's advertised limit.

This violates subsystem independence:

- Parser safety depends on shell initialization.
- The dependency is process-global and implicit.
- Embedding applications may not permit changing the recursion limit.
- Threaded code cannot safely treat temporary recursion-limit changes as local.

### Recommended path

The textbook long-term fix is an explicit compound-command frame stack. Nested
compound parsing can then preserve the recursive-descent rule structure while
representing suspended parent productions as parser frames.

Short-term:

1. Catch `RecursionError` at the parser boundary and convert it to a clean
   `ParseError`.
2. Set a conservative parser-owned depth limit known to be safe under the
   minimum supported interpreter's default stack.
3. Add standalone parser tests that do not construct `Shell`.

Do not temporarily raise and restore the process recursion limit inside
`Parser.parse()`; that remains global and thread-unsafe.

## AST contract findings

## 7. Several AST nodes still carry parallel truths

The `SimpleCommand` cleanup is the right model:

```python
@property
def args(self) -> List[str]:
    return [word.display_text() for word in self.words]
```

Other nodes still store both structured and flattened representations:

| Node | Canonical candidate | Parallel field |
|---|---|---|
| `ArrayInitialization` | `words` | `elements` |
| `ArrayElementAssignment` | `value_word` | `value` |
| `ForLoop` / `SelectLoop` | `item_words` | `items` |
| `CasePattern` | `word` | `pattern` |
| `CaseConditional` | `subject_word` | `expr` |
| `Redirect` | `target_word` | `target` |

Tests assert that these lists and values remain synchronized. That prevents
some regressions, but it is weaker than making contradictory states
unrepresentable.

Continue the `SimpleCommand` strategy:

- Make structured `Word` fields required.
- Derive display text through properties.
- Remove executor fallbacks for parser-created nodes.
- Provide explicit test builders for manually constructed educational ASTs
  instead of weakening production node invariants.

`ArrayInitialization.words` is documented as required but still defaults to an
empty list, allowing a nonempty `elements` list without corresponding words.
That contradiction should be removed.

## 8. Source metadata is insufficient for a textbook parser

`ASTNode.line` is a mutable class attribute:

```python
class ASTNode(ABC):
    line: Optional[int] = None
```

The parser stamps selected statements and pipelines after construction.
Because `line` is not a dataclass field:

- It is absent from dataclass equality and representation.
- Generic AST traversal and serialization do not see it.
- Most expression, word, redirect, and command nodes have no useful location.
- No node has an end position.
- Tooling cannot reliably map nodes back to source ranges.

Introduce:

```python
@dataclass(frozen=True)
class SourcePosition:
    offset: int
    line: int
    column: int


@dataclass(frozen=True)
class SourceSpan:
    start: SourcePosition
    end: SourcePosition
```

AST nodes should carry an optional span as real structural metadata. The parser
should construct nodes with their spans rather than mutating line values in a
later fallback pass.

`Program` is the correct owner for source path, parser dialect, and complete
input span, but those fields have not yet been added.

## Heredoc and public API findings

## 9. Heredoc population is duplicated and weakly typed

The production recursive-descent parser uses
`ParserUtils.populate_heredoc_content()`, a 26-complexity recursive function
driven by `hasattr()` checks:

```python
if hasattr(node, 'statements'):
    ...
if hasattr(node, 'commands'):
    ...
if hasattr(node, 'condition'):
    ...
if hasattr(node, 'items'):
    ...
```

This walk:

- Reimplements AST traversal.
- Recurses into non-node iterable data such as loop item strings.
- Must be updated manually for every AST field.
- Contains a delimiter-suffix fallback if `heredoc_key` is missing.
- Is untyped at its main node boundary.

The educational combinator parser already has a cleaner
`HeredocProcessor(ASTVisitor)` using shared traversal. Production should not
retain the less reliable implementation.

### Recommended target

Move one heredoc processor into shared visitor/parser infrastructure and use it
for both parsers.

An even cleaner design is to pass a typed heredoc map to
`RedirectionParser` and attach the body when the `Redirect` is constructed.
Then:

- `heredoc_key` is mandatory for heredoc redirects.
- Missing map entries fail loudly.
- Delimiter-based fallback matching disappears.
- No second AST traversal is necessary.

## 10. Parser entry points do not expose one coherent contract

Current entry points differ in their available inputs:

| Entry point | Config | Source text | Line offset | Heredocs | Parser selection |
|---|---:|---:|---:|---:|---:|
| `parse()` | yes | no | no | no | no |
| `create_parser()` | no | yes | yes | no | yes |
| `parse_with_heredocs()` | no | no | no | yes | yes |

Additional issues:

- `create_parser()` treats every name other than exact `"combinator"` as
  recursive descent.
- `"rd"` and `"recursive_descent"` are accepted only because both fall through.
- An untyped `_ParserWrapper` class is created on every combinator factory call.
- Combinator mode silently ignores `source_text` and `line_offset`.
- Heredoc parsing cannot render source-line carets through the public helper.
- Return types are not consistently annotated at the public façade.

Recommended API:

```python
class ParserKind(StrEnum):
    RECURSIVE_DESCENT = "recursive_descent"
    COMBINATOR_EXPERIMENTAL = "combinator"


@dataclass(frozen=True)
class ParseRequest:
    tokens: Sequence[Token]
    source_text: str | None = None
    source_name: str | None = None
    line_offset: int = 0
    config: ParserConfig = field(default_factory=ParserConfig)
    heredocs: Mapping[str, HeredocBody] = field(default_factory=dict)
```

Unknown parser names should raise immediately. The combinator parser should
have an explicitly experimental API rather than silently participating in the
production factory.

## Diagnostic findings

## 11. `ParseError.message` and `str(ParseError)` disagree

`ParseError` sets:

```python
self.message = error_context.message or error_context.format_error()
super().__init__(error_context.format_error())
```

For most parser errors, `.message` is only the short reason while `str(error)`
contains position, line, caret, suggestion, and surrounding tokens.

The normal execution path prints `str(error)` and receives the rich diagnostic.
Analysis modes use `error.message` and therefore reduce:

```text
Parse error at position 6 (line 1, column 7): Expected command

echo |
      ^
```

to:

```text
Expected command
```

Use one unambiguous interface:

- `diagnostic.summary` for the short reason.
- `diagnostic.render()` for presentation.
- `str(ParseError)` delegating to `render()`.

Callers should not need to know whether `.message` is raw or rendered.

## 12. Error rendering has limited source fidelity

The recursive-descent path has generally good errors, but:

- Heredoc public parsing lacks source text.
- The combinator factory ignores source text and line offset.
- Caret indentation counts characters rather than displayed tab width.
- Errors identify one token rather than a source range.
- The `expected` field is inconsistently used; many errors embed expectation
  text into `message`.

These are secondary to the correctness findings, but real source spans and one
diagnostic object would simplify them.

## Visualization findings

## 13. `ASTPrettyPrinter` is stale and often prints raw dataclass representations

The visualization package contains 1,506 lines across four renderers. The
`ASTPrettyPrinter` is not aligned with the current AST:

- It has no `visit_Program()`.
- `visit_AndOrList()` looks for obsolete `left`, `operator`, and `right`
  attributes instead of `pipelines` and `operators`.
- `visit_ForLoop()` looks for `iterable` instead of `items`/`item_words`.
- `visit_CStyleForLoop()` looks for `init` and `update` instead of
  `init_expr` and `update_expr`.
- `visit_CaseConditional()` looks for `expression` and `cases` instead of
  `expr` and `items`.
- `_format_field()` checks for a nonexistent AST `accept()` method.
- `show_positions` looks for `position`, while AST nodes expose at most `line`.

At the `Program` root, the generic formatter converts child AST nodes with
`str()`, producing a large raw dataclass `repr`. Directly visiting an
`AndOrList` produces only:

```text
AndOrList:
```

### Why tests did not catch this

Most visualization tests only assert broad substrings such as:

```python
assert "SimpleCommand" in output
assert "echo" in output
```

The raw dataclass representation contains those strings, so the tests pass
without proving that visitor dispatch or tree formatting works. One empty-input
test catches all exceptions and accepts them.

### Recommended resolution

- Move visualization into `psh/visitor/` or a dedicated debug/tooling package.
- Use the shared dataclass child traversal.
- Keep one canonical structural model and adapt presentation only.
- Add golden snapshots for every concrete AST node.
- Assert indentation and field structure, not mere substrings.
- Remove renderers whose output is not meaningfully distinct.

The ASCII tree renderer currently provides the strongest useful output and is a
reasonable foundation.

## Token-contract finding

## 14. The parser mutates lexer token objects

After a pipe, the parser demotes `TIME` to `WORD` by changing the caller-owned
token object:

```python
tok.type = TokenType.WORD
tok.is_keyword = False
```

`create_context()` copies the token list but not the tokens, so this mutation is
visible to callers and other parser implementations reusing the same stream.
The combinator parser performs a similar mutation.

Interpret contextual `time` locally:

- Construct a literal `Word` without changing the token, or
- Normalize to immutable parser terminals in a separate adapter layer.

Parser execution should be observationally pure with respect to its token
input. Add a test that snapshots tokens before and after both parsers.

## Educational combinator parser

The combinator parser is explicitly educational and outside the production
quality bar. Its semantic gaps are therefore not counted as production
correctness findings.

There is still an architectural cost:

- 5,278 lines of combinator code versus 3,604 lines of production
  recursive-descent code.
- Thirteen optional Ruff complexity hotspots.
- Runtime parser selection exposes it to ordinary users despite its unsupported
  status.
- It shares recursive-descent `WordBuilder` and diagnostic internals, so it is
  not an independent implementation.
- Several productions use imperative scans, mutation, and committed exceptions
  rather than textbook combinator composition.

For teaching value, isolation would help:

- Put it behind an explicitly experimental package/API.
- Keep a small documented corpus demonstrating combinator principles.
- Do not require every production AST evolution to update it.
- Consider removing live runtime selection if parity is not a maintained goal.

This preserves its pedagogical role without making the production parser
factory and shell lifecycle carry experimental complexity.

## Test-suite appraisal

### Strong coverage

The parser tests are unusually broad:

- Canonical root invariants.
- AST field population.
- Function and control-structure grammar.
- Background and pipeline semantics.
- Quoting and composite words.
- Arrays and redirections.
- Incomplete-input diagnostics.
- Heredoc attachment.
- Parser-to-parser differential checks.
- Bash grammar conformance.
- Nesting and performance.

This explains why the ordinary grammar is stable.

### Important blind spots

The remaining defects point to specific missing test strategies:

1. No outer-buffer execution test for invalid modern nested substitutions.
2. Configuration tests inspect fields and helper calls rather than live
   grammar behavior.
3. Collection tests do not assert recovery validity or forward progress.
4. No sentinel-free token-stream contract test.
5. Array tests characterize whitespace forms without consistently requiring
   Bash classification parity.
6. Conditional-regex tests lack a systematic token-boundary rejection matrix.
7. Case-pattern tests omit empty alternatives.
8. Visualization tests assert substrings rather than structural output.
9. Nesting-limit tests construct `Shell` or lower the limit; standalone parser
   safety under the default Python recursion limit is not tested.

Add a compact production-parser differential corpus against the supported Bash
version. Parser-to-parser parity is useful for drift detection, but two parsers
can agree on the same divergence.

## Recommended implementation sequence

## Phase 1: lock down current correctness defects

Add failing tests for:

- `$(if)` and malformed process substitutions in a multi-command buffer.
- Nested substitutions inside parameter-expansion words.
- Sentinel-free token lists.
- `for ((...)); command; done` without `do`.
- Whitespace variants around array assignment heads.
- Non-adjacent array-element values.
- Invalid conditional-regex token starts and unbalanced grouping.
- Empty case-pattern alternatives.
- ParserConfig behavior through production entry points.

## Phase 2: make nested command syntax part of the AST

1. Add nested `Program` fields to modern command and process substitutions.
2. Inject nested parsing through the active parser context.
3. Preserve source text and spans.
4. Execute the stored AST in substitution children.
5. Extend visitors into nested programs.
6. Define and test the distinct legacy-backtick policy.

This is the largest change, but it removes an entire class of phase-order and
tooling defects.

## Phase 3: remove dishonest configuration and recovery

Decide whether configurable parsing and recovery are real supported features.

If not, delete their public and internal machinery.

If yes:

- Wire one typed configuration through all entry points.
- Replace dynamic string feature names.
- Implement a real diagnostic-bearing parse result.
- Add synchronization-based recovery.
- Refuse execution of invalid results.

Do not retain the current halfway state.

## Phase 4: repair narrow grammar divergences

- Require `do` for C-style `for`.
- Make array classification source-adjacency exact.
- Stop consuming non-adjacent array values.
- Give conditional regexes an explicit grammar.
- Reject empty case alternatives.

These are small, reviewable commits with direct Bash differential tests.

## Phase 5: harden parser boundaries

- Make end-of-stream behavior safe without a sentinel.
- Remove token mutation.
- Make nesting safety independent of `Shell`.
- Validate parser-kind selection.
- Unify public parse requests and source/config/heredoc plumbing.

## Phase 6: finish AST canonicalization

- Derive flattened string fields from structured words.
- Remove production executor fallbacks for missing canonical fields.
- Introduce immutable source positions and spans.
- Add root source metadata to `Program`.

## Phase 7: consolidate supporting tooling

- Use one shared heredoc visitor or attach heredocs during redirect creation.
- Replace the stale pretty printer.
- Consolidate visualization under the visitor/tooling subsystem.
- Strengthen golden-output tests.
- Isolate the educational combinator parser from production APIs.

## Suggested commit sequence

1. `test(parser): cover nested syntax and grammar boundary divergences`
2. `fix(parser): require EOF-safe token stream semantics`
3. `fix(parser): enforce array assignment adjacency`
4. `fix(parser): require do in C-style for loops`
5. `fix(parser): reject invalid conditional regex operands`
6. `fix(parser): reject empty case pattern alternatives`
7. `refactor(ast): represent modern substitutions with nested Program nodes`
8. `refactor(expansion): execute parsed substitution programs`
9. `refactor(parser): remove dormant recovery and configuration machinery`
10. `refactor(ast): derive remaining flattened word views`
11. `refactor(parser): unify heredoc and public parse APIs`
12. `refactor(visitor): replace stale parser visualization walkers`
13. `docs(parser): document the final grammar and AST contracts`

## Acceptance criteria

The parser reaches a textbook-quality state when:

- Invalid `$(...)` and process-substitution syntax is rejected during the outer
  parse, before any command executes.
- Every modern nested command construct contains a parsed `Program`.
- Public parser configuration either works end to end or no longer exists.
- No parser mode returns an executable AST after syntax errors.
- Missing EOF cannot hang the parser.
- Standalone parser use cannot leak `RecursionError`.
- Array assignment classification is source-adjacency exact.
- C-style `for` requires `do`.
- Conditional regex and case-pattern boundaries match Bash.
- Structured `Word` fields are the sole semantic source of truth.
- AST nodes carry proper source spans.
- Heredoc attachment has one typed implementation.
- Parser input tokens are not mutated.
- Visualization traverses the current AST rather than printing raw
  representations.
- Production correctness does not depend on the educational combinator parser.
- Parser-focused unit, integration, differential, conformance, formatter,
  visitor, performance, and full recommended test flows pass.

## Final assessment

The root-shape refactor was successful and removed the largest prior parser
architecture defect. The recursive-descent parser now has a coherent grammar,
a stable root contract, strong ordinary-shell coverage, and good linear
performance.

The remaining work is concentrated rather than systemic. The parser does not
need another broad rewrite. It needs:

1. Real recursive parsing for modern nested command syntax.
2. Removal or completion of the configuration and recovery façade.
3. Exact fixes for a handful of Bash grammar boundaries.
4. Safer token, recursion, heredoc, and source-location contracts.
5. Completion of the structured-AST migration.

Those changes would move the production parser from **B+** to a defensible
**A/A−** implementation suitable both for production use and as a textbook
example.
