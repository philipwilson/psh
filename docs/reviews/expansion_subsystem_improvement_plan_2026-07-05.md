# Expansion Subsystem Appraisal and Improvement Plan

Date: 2026-07-05  
Version reviewed: PSH 0.638.0

## Summary

Overall assessment:

- Correctness: **B+**
- Maintainability: **B**
- Worst-case efficiency: **C+**

The expansion subsystem has unusually strong Bash coverage and several sound
design choices. In particular, the primary `Word` AST preserves per-part quote
context, the `ExpandedSegment` intermediate representation makes splitting and
globbing visible, parameter parsing is centralized, and arithmetic expansion
has a properly decomposed tokenizer, parser, and evaluator.

It is not yet textbook-quality because it still contains two expansion
engines, in-band sentinel encoding, unsafe command-substitution byte handling,
and exponential pattern matching.

A wholesale rewrite would be unnecessarily risky. The subsystem should be
refactored incrementally behind its existing differential tests.

## Validation performed

The following checks were run during this appraisal:

```text
python -m pytest tests/unit/expansion/ -q
  2,184 passed, 1 skipped

python -m pytest tests/conformance/bash -q
  1,240 passed, 1 skipped, 10 expected failures

ruff check psh/expansion
  clean

python -m mypy psh/expansion
  clean under the configured rules
```

A stricter mypy audit using `--disallow-untyped-defs` found 61 missing
annotation errors. The expansion implementation contains approximately 8,871
lines.

The broad passing suites are meaningful evidence of compatibility, but they do
not currently exercise the byte, low-file-descriptor, private-use Unicode, or
locale-sensitive cases identified below.

## Strengths to preserve

### 1. Structured primary word expansion

The primary path consumes `Word` nodes containing `LiteralPart` and
`ExpansionPart` nodes with per-part quote context. This is the correct
foundation for preserving shell quoting semantics.

### 2. Explicit intermediate representation

`ExpandedSegment` is a substantial improvement over parallel text, quoting,
splitting, and globbing arrays. It makes the main field-producing stages
visible:

```text
Word parts
  -> expanded segments
  -> field splitting
  -> pathname expansion
  -> final fields
```

The final design should strengthen this representation rather than return to
text-only processing.

### 3. Named expansion policies

Named `WordExpansionPolicy` instances make command arguments, declaration
assignments, loop items, arrays, and case subjects distinguishable at call
sites. This is substantially clearer than passing anonymous Boolean flags.

### 4. Central parameter grammar

`param_parser.py` provides one grammar for `${...}` classification. That avoids
the operator-classification drift that commonly develops in shell
implementations.

### 5. Decomposed arithmetic implementation

The arithmetic subsystem has separate tokenizer, parser, evaluator, node, and
error modules, explicit recursion-depth guards, and extensive compatibility
tests. Its internal structure is one of the better models for future expansion
work.

### 6. Extensive characterization coverage

Arrays, `$@`, IFS splitting, parameter operators, extglob, globstar, command
substitution, tilde expansion, brace expansion, and Bash-specific contexts all
have strong test coverage.

### 7. Fail-loud behavior

Internal failures generally propagate rather than being silently converted
back into literal source text. Preserve this policy while centralizing how
user-facing expansion errors are rendered.

## Priority findings

### 1. Command substitution does not preserve shell byte semantics

`command_sub.py` always decodes captured output as UTF-8 with replacement:

```python
output = output_bytes.decode('utf-8', errors='replace')
```

This produces two confirmed defects.

#### Non-UTF-8 bytes are corrupted

Probe:

```sh
x=$(python -c 'import os;os.write(1,bytes([255]))')
printf %s "$x"
```

Observed output:

| Shell | Output bytes |
|---|---|
| Bash | `ff` |
| PSH | `ef bf bd` |

PSH replaces the original byte with the UTF-8 encoding of the Unicode
replacement character.

#### NUL bytes are retained incorrectly

Probe:

```sh
x=$(python -c 'import os;os.write(1,bytes([97,0,98]))')
printf '<%s>\n' "$x"
```

Observed behavior:

| Shell | Result |
|---|---|
| Bash | Prints `<ab>` and warns that a NUL was ignored |
| PSH | Stores and prints `a NUL b` with no warning |

An actual NUL in a shell variable is especially dangerous because Unix
argument and environment APIs cannot represent it.

#### Repair

Establish an explicit shell byte/text policy:

1. Remove NUL bytes before decoding.
2. Emit a Bash-compatible diagnostic when NULs are discarded.
3. Decode using the selected locale/filesystem encoding and
   `surrogateescape`, not replacement.
4. Ensure output, external arguments, and environment export perform the
   inverse encoding consistently.
5. Add tests for arbitrary bytes under both `LC_ALL=C` and a UTF-8 locale.

This policy must be shared by script input, command substitution, external
execution, builtins, variables, and diagnostics.

### 2. Command substitution has a low-file-descriptor collision

`CommandSubstitution._child_io_setup()` currently performs:

```python
os.close(read_fd)
os.dup2(write_fd, 1)
os.close(write_fd)
```

When descriptors 0 and 1 are initially closed, `os.pipe()` can return
`(0, 1)`. The child then performs:

```python
os.dup2(1, 1)  # no-op
os.close(1)    # closes substitution stdout
```

Confirmed probe:

```sh
exec 0<&- 1>&-
x=$(printf x)
printf '<%s> rc=%s\n' "$x" "$?" >&2
```

Observed behavior:

| Shell | Result |
|---|---|
| Bash | `<x> rc=0` |
| PSH | `Bad file descriptor`, then `<> rc=1` |

#### Repair

Introduce one collision-safe descriptor-remapping utility shared by command
substitution, process substitution, pipelines, and redirections.

It should:

- Close a source descriptor only when it differs from its destination.
- Promote internal descriptors above 2 where practical.
- Handle remapping cycles explicitly.
- Set close-on-exec on internal descriptors.
- Close all descriptors on every failure path.
- Reap a forked child even when reading or decoding fails.
- Restore signal handlers if pipe creation, signal setup, or fork fails.
- Map a signalled child status to `128 + signal`.

The current `finally` restores `SIGCHLD`, but it does not provide complete
descriptor and child-lifecycle cleanup.

### 3. Brace expansion corrupts legitimate Unicode

The brace expander uses private-use Unicode characters as in-band metadata:

- `U+F8FF` represents a retained empty range element.
- `U+E000` and following code points represent quoted characters, expansion
  parts, and opaque tokens.

This is inherently unsafe because every Unicode character can be supplied by a
user.

#### `U+F8FF` deletion

Probe:

```sh
printf '<%s>\n' <U+F8FF>{a,b}
```

Bash preserves the character in both results. PSH removes it and produces
`<a>` and `<b>`.

#### `U+E000` placeholder collision

Probe:

```sh
printf '<%s>\n' <U+E000>"x"{a,b}
```

Bash produces:

```text
<U+E000>xa
<U+E000>xb
```

PSH produces:

```text
xxa
xxb
```

The literal character collides with a generated placeholder and is decoded as
unrelated quoted content.

#### Repair

Remove all in-band sentinel characters.

The preferred design is to move brace expansion from the post-lex token
transformation into the first structured `Word` expansion stage. Brace
expansion should operate on sequences such as:

```text
Literal(text, quoted)
ExpansionReference(node, quoted)
```

and return structured word variants. Metadata must remain out-of-band.

A collision-aware escape table could be used as a short-term correction, but
it should not become permanent architecture.

### 4. The brace-expansion limit does not limit resource consumption

`BraceExpander.MAX_EXPANSION_ITEMS` is 10,000, but the limit is checked only
after intermediate lists have been built.

For example, `_try_numeric_sequence()` appends every numeric element to a list
before `_expand_braces()` checks the result count. A range such as:

```sh
{1..1000000000}
```

can therefore consume excessive CPU and memory before the protective limit is
consulted.

Nested list and sequence products have the same structural problem.

`TokenBraceExpander` also catches `BraceExpansionError` and silently restores
the original literal token. A resource-limit failure consequently appears to
mean “this was not an expandable brace expression.”

#### Repair

1. Calculate numeric and character sequence cardinality before generation.
2. Pass one shared expansion budget through recursion and Cartesian products.
3. Generate lazily, stopping as soon as `budget + 1` would be produced.
4. Make the budget limit total work and retained memory, not only final output
   length.
5. Report a typed resource-limit error instead of silently restoring the
   literal expression.

### 5. POSIX character classes are incorrectly ASCII-only

`glob.py` defines POSIX classes using fixed ASCII ranges:

```python
'alpha': 'a-zA-Z'
'upper': 'A-Z'
'lower': 'a-z'
```

These classes are locale-sensitive in Bash.

Confirmed under `C.UTF-8`:

```sh
[[ é == [[:alpha:]] ]]
echo $?
```

| Shell | Status |
|---|---:|
| Bash | 0 |
| PSH | 1 |

The same divergence affects `case` patterns, parameter-expansion patterns, and
pathname expansion.

Pathname results are also deliberately sorted by Python code-point order.
Bash uses locale collation, so non-C locales can produce a different ordering.

#### Repair

Create a central locale service responsible for:

- POSIX character-class membership.
- Case conversion and case-insensitive matching.
- Collation and glob-result ordering.
- Comparison operators such as `[[ < ]]`.

Bracket expressions should compile into predicates or pattern-AST nodes rather
than hard-coded regex character ranges. Locale-aware `wctype`/`iswctype`
semantics, or a carefully specified portable equivalent, should back those
predicates.

Using Python `str.isalpha()` alone is insufficient because it does not become
ASCII-only when the active shell locale is `C`.

Locale initialization must also be designed deliberately: Python's
`locale.setlocale()` is process-global.

### 6. Extglob has exponential worst-case behavior

The non-negation path converts extglob patterns to Python regular expressions.
Ambiguous repetitions can trigger catastrophic regex backtracking.

Benchmark:

```text
pattern: *(a|aa)b
subject: "a" repeated N times
```

Measured locally:

| N | Match time |
|---:|---:|
| 20 | 0.0005 s |
| 25 | 0.0055 s |
| 30 | 0.061 s |
| 34 | 0.389 s |

The negation matcher has a related problem. `_match_from()` recursively
recomputes `(pattern position, subject position)` states and repeatedly finds
matching parentheses and splits alternatives.

Bash can also be slow on adversarial extglob patterns, so this is not simply a
compatibility failure. It is nevertheless unacceptable as a textbook
efficiency and resource-control property.

#### Repair

Parse each pattern once into a pattern AST containing nodes such as:

```text
Sequence
Alternation
Literal
AnyCharacter
Star
CharacterClass
ExtglobRepeat
ExtglobNegation
```

Compile that AST into a memoized NFA or dynamic-programming matcher. A state
should be evaluated at most once for each relevant subject position.

The matcher should return reachable end positions. That representation
naturally supports:

- Full matching.
- Prefix and suffix removal.
- Leftmost-longest substitution.
- Extglob alternation and negation.
- Pathname-component matching.

The same compiled pattern engine should serve:

- `case`
- `[[ string == pattern ]]`
- `${var#pattern}` and related operators
- `${var/pattern/replacement}`
- Pathname expansion

This would also remove the current mixture of stdlib globbing, regex matching,
and custom extglob walkers.

### 7. There are still two expansion engines

The intended primary engine consumes structured `Word` nodes. However,
`expand_string_variables()` implements a second raw-string scanner used by 12
modules, including:

- Redirection targets and heredocs.
- Arithmetic expressions.
- Array subscripts.
- `[[ ]]` and control-flow operands.
- Prompt expansion.
- The `test` builtin.
- Parameter-expansion operands.

`operands.py` consequently contains another scanner for quotes, `${...}`,
`$(...)`, `$((...))`, backticks, ANSI-C strings, tilde prefixes, and nested
quote contexts.

The AST itself also retains nested semantic content as strings:

```python
ParameterExpansion.word: Optional[str]
CommandSubstitution.command: str
ArithmeticExpansion.expression: str
```

`ExpansionEvaluator` then reconstructs source syntax:

```python
f"${{{name}}}"
f"$({command})"
f"$(({expression}))"
```

and sends it back through string entry points. Validation even uses:

```python
str(expansion)[2:-1]
```

This is the subsystem's largest maintainability problem. Every raw string
scanner is a parallel grammar and a future source of semantic drift.

#### Repair

Parse expansion-bearing content once:

- Parameter value operands should contain structured word-template nodes.
- Pattern operands should contain pattern-template nodes that retain quoted
  and active fragments.
- Replacement operands should contain literal and match-reference nodes.
- Command substitutions should contain a nested `Program`, or at minimum a
  parsed command-body node.
- Arithmetic expansions should contain a parsed arithmetic AST.
- Heredoc bodies should use a small template AST containing literal,
  parameter, command, and arithmetic parts.
- Redirect targets, case patterns, and array subscripts should use structured
  nodes appropriate to their context.

Retire `expand_string_variables()` one caller category at a time, keeping the
existing implementation as a temporary compatibility adapter until no
semantic caller remains.

### 8. Result and context types are too weak

`WordExpander.expand()` returns:

```python
Union[str, List[str]]
```

Callers therefore repeatedly branch, extend, append, or join.

`OperandResult` subclasses `str` while attaching hidden `.segments` metadata.
Callers discover that metadata using `getattr()`. This is ingenious as a
migration device, but it is not a robust long-term value model.

Quote context is represented by:

```text
None
"dquote-word"
"dquote-string"
```

The current three-policy Boolean axes are adequate for the field-producing
walker, but the subsystem as a whole has many more semantic contexts.

#### Repair

Introduce explicit expansion contexts:

```python
class ExpansionContext(Enum):
    COMMAND_ARGUMENT = ...
    ASSIGNMENT_VALUE = ...
    DECLARATION_ASSIGNMENT = ...
    ARRAY_ELEMENT = ...
    ASSOCIATIVE_ARRAY_ELEMENT = ...
    CASE_SUBJECT = ...
    CASE_PATTERN = ...
    PARAMETER_VALUE = ...
    PARAMETER_PATTERN = ...
    PARAMETER_REPLACEMENT = ...
    REDIRECT_TARGET = ...
    HEREDOC_BODY = ...
    HERE_STRING = ...
```

Each context should select a defined strategy for tilde expansion, field
production, IFS splitting, globbing, quote protection, and process
substitution.

Every expansion should return one result type:

```python
@dataclass(frozen=True)
class ExpansionResult:
    fields: tuple[Field, ...]
    last_substitution_status: int | None = None
```

Fields should contain typed fragments:

```python
@dataclass(frozen=True)
class Fragment:
    text: str
    protection: Protection
    provenance: Provenance
```

Scalar contexts should explicitly require one field or apply a
context-specific joining rule. This removes `str | list[str]`, hidden
attributes on strings, and invalid combinations of Boolean segment flags.

### 9. Expansion directly controls diagnostics and shell flow

Several expansion modules:

- Print diagnostics directly.
- Mutate `last_exit_code`.
- Mutate `last_cmdsub_status`.
- Raise `SystemExit`.
- Raise `TopLevelAbort`.

For example, `WordExpander._glob_words()` decides whether failglob aborts the
current top-level command or exits the shell.

Mutation is unavoidable for `${x:=word}`, arithmetic assignment, command
substitution status, and process substitution. The problem is not mutation
itself; it is that mutation, diagnostics, and control-flow mapping are spread
throughout the expansion implementation.

#### Repair

Raise typed expansion errors containing:

- Exit status.
- Diagnostic subject and message.
- Source span.
- Fatality or discard classification.

Let one executor boundary render the diagnostic and map it to shell control
flow.

Use an `ExpansionSession` or explicit effect interface to own:

- Variable mutations.
- Last command-substitution status.
- Process-substitution resources.
- Diagnostics.
- Resource budgets.

This makes expansion effects visible without falsely pretending that shell
expansion is pure.

### 10. The documented tilde divergence should be removed

The current implementation documents this case:

```sh
HOME=/h
X=hello
echo ~:$X
```

Observed behavior:

| Shell | Output |
|---|---|
| Bash | `/h:$X` |
| PSH | `~:hello` |

Bash recognizes the colon-bounded tilde prefix and consumes the remainder of
the tilde word verbatim. PSH currently makes a whole-word yes/no decision based
on whether another `WordPart` follows.

This is an unusual Bash behavior, but it exposes a genuine abstraction
problem: tilde expansion must identify an extent within a structured word, not
merely decide whether the complete leading literal part is expandable.

#### Repair

Implement one structured tilde-word scan:

1. Start only at a context-permitted unquoted tilde position.
2. Walk word fragments until the tilde-word boundary.
3. Reject quoted or escaped characters where Bash rejects them.
4. Expand the prefix ending at `/` or `:`.
5. Mark the rest of the consumed tilde word as literal and protected.
6. Resume ordinary expansion only after the consumed extent.

Reuse this operation for ordinary words and parameter operands instead of
maintaining separate textual interpretations.

### 11. Error/status handling needs one boundary

`operators.py`, `arrays.py`, `variable.py`, arithmetic evaluation, command
substitution, and globbing all contain local combinations of:

```text
print diagnostic
set last_exit_code
raise an exception
```

Besides increasing repetition, this makes it difficult to guarantee that
redirection, nested command execution, and source locations behave uniformly.

User-facing failures should be represented as data until they reach the
executor boundary. Unexpected implementation failures should continue to
propagate loudly.

### 12. Module cohesion and typing can be improved

#### Alias placement

Aliases are a lexical/parser-front-end transformation, not runtime word
expansion. `aliases.py` should move to a front-end or scripting package.

#### Mixin architecture

`VariableExpander` uses multiple mixins whose runtime base is `object` but
whose type-checking base is a protocol. This reduced file size, but it leaves
dependencies implicit and requires methods to be supplied through class
composition.

Prefer explicit components:

```text
ParameterResolver
ParameterOperatorEvaluator
OperandEvaluator
ArrayResolver
PatternEngine
```

`VariableExpander` can remain a facade while delegating to these components.

#### Type completeness

Configured static checks pass, but strict checking identifies 61 untyped
definitions. The main gaps are in:

- `brace_expansion_tokens.py`
- `manager.py`
- `_protocols.py`
- `operands.py`
- `operators.py`
- `arrays.py`
- `fields.py`

Complete annotations while introducing the typed context and result model.
Avoid spending a separate mechanical phase annotating APIs that are about to
be replaced.

## Recommended target architecture

```text
Parsed Word / Expansion Template
              |
              v
  Budgeted structured brace variants
              |
              v
  Context-aware fragment evaluation
    - tilde
    - parameter
    - command
    - arithmetic
    - process substitution
              |
              v
      Typed protected fragments
              |
              v
   Context-specific field formation
    - IFS splitting where permitted
    - zero-field / multi-field rules
              |
              v
  Compiled pattern/pathname expansion
              |
              v
        ExpansionResult + effects
              |
              v
  Executor applies diagnostics/status
```

The key invariants should be:

1. Expansion syntax is parsed once.
2. User text is never used to encode internal metadata.
3. Quote and protection information remains structural until final field
   construction.
4. All potentially multiplicative work consumes an explicit budget.
5. One compiled pattern representation defines matching semantics.
6. Byte decoding and locale behavior are deliberate shell-wide policies.
7. Errors become shell control flow at one boundary.

## Staged implementation plan

### Phase 1: Pin and repair confirmed correctness defects

Add regression tests before changing implementation:

1. Command substitution containing NUL.
2. Command substitution containing every non-NUL byte value.
3. Command substitution with descriptors 0 and 1 initially closed.
4. Brace expansion containing literal `U+F8FF`.
5. Composite brace expansion containing literal `U+E000`.
6. Locale-sensitive POSIX classes in `[[ ]]`, `case`, parameter patterns, and
   pathname expansion.
7. The `~:$X` tilde-prefix case.

Then repair:

- Command-substitution byte and descriptor handling.
- Brace sentinel collisions.
- Preemptive brace budgeting.
- Locale character classes.
- Tilde extent handling.

### Phase 2: Introduce typed results and contexts

1. Add `ExpansionContext`.
2. Replace string quote-context constants with an enum.
3. Add `Fragment`, `Field`, and `ExpansionResult`.
4. Adapt the existing `WordExpander` internally while preserving its public
   API through a temporary adapter.
5. Remove `OperandResult(str)` after all consumers accept fragments.
6. Move diagnostic rendering to the executor boundary.

This phase should preserve observable behavior apart from explicitly approved
bug fixes.

### Phase 3: Eliminate the raw-string expansion engine

Migrate one context at a time:

1. Redirect targets.
2. Case subjects and patterns.
3. `[[ ]]` operands.
4. Array subscripts.
5. Arithmetic embedded expansions.
6. Parameter operands.
7. Heredoc bodies.
8. Prompt expansion.

Add architecture tests preventing new semantic calls to
`expand_string_variables()`.

Once the final caller is gone:

- Delete `_expand_one_dollar()` and the duplicate quote scanners.
- Stop reconstructing expansion syntax in `ExpansionEvaluator`.
- Make structured AST nodes the sole semantic input.

### Phase 4: Replace the pattern engines

1. Define and test a shell-pattern AST.
2. Parse plain glob and extglob syntax once.
3. Implement memoized reachable-position matching.
4. Move prefix/suffix removal and substitution onto that API.
5. Move `case` and `[[ ]]` matching.
6. Move pathname component matching.
7. Replace the four pathname walker modes with one walker parameterized by
   options.
8. Add adversarial performance tests and explicit budgets.

Preserve symlink, dotglob, globstar, nullglob, failglob, and locale semantics as
separate, explicit policies.

### Phase 5: Complete cohesion and static quality work

1. Move aliases out of the expansion package.
2. Replace mixin-supplied dependencies with composed components.
3. Complete strict type annotations.
4. Add source spans to nested expansion and operand nodes.
5. Update `CLAUDE.md` and architecture documentation.
6. Keep Bash differential tests as the merge gate for every migration.

## Tests and quality gates to add

### Byte and descriptor tests

- All byte values except NUL round-trip through command substitution.
- NUL is removed with the selected diagnostic.
- Descriptors 0, 1, and 2 may independently begin closed.
- Fork, pipe, read, wait, and decode failures leak neither descriptors nor
  children.

### Structured expansion tests

- No expansion implementation reconstructs syntax and reparses it.
- Quote protection survives nested operands.
- Every context has an explicit policy.
- Scalar consumers cannot silently accept multiple fields.

### Pattern tests

- Differential pattern corpus across `case`, `[[ ]]`, parameter operators, and
  pathname components.
- Locale matrices for `C`, `C.UTF-8`, and one non-English locale where
  available.
- Complexity assertions for ambiguous alternation, nested extglob, long
  strings, and negation.

### Brace tests

- Every private-use Unicode character is ordinary data.
- The expansion budget bounds both generated item count and elapsed work.
- Nested products fail before large intermediate allocation.
- Resource failures produce explicit diagnostics.

### Property tests

- Expansion never loses literal input unless a specified expansion or quote
  removal rule consumes it.
- Escaped and quoted glob characters never regain pattern power.
- Structured rendering is not consulted for runtime semantics.
- Matching the same compiled pattern through different consumers yields
  consistent results where their context rules are identical.

## Final assessment

The subsystem is already compatibility-oriented and strongly tested. Its
largest weakness is not missing feature breadth; it is the coexistence of a
good structured `Word` engine with older text-based mini-parsers and
text-encoded metadata.

The highest-value sequence is:

1. Fix byte, descriptor, Unicode-sentinel, and locale correctness.
2. Make brace expansion budgeted and structured.
3. Introduce typed contexts, fragments, fields, and outcomes.
4. Eliminate raw-string reparsing.
5. Replace regex/backtracking pattern handling with one compiled,
   memoized engine.

The governing principle should be:

> Parse expansion syntax once, preserve quote and protection information
> structurally, and never encode metadata inside user text.
