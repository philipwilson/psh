# Lexer, Parser, and AST Architecture Review - 2026-06-13

## Scope

This review studies the current lexer, parser, and AST model after the latest changes. I focused on architecture, code quality, elegance, and concrete "uglies" that make future correctness harder. I inspected the current source directly and did not use older review documents as evidence.

Files studied most closely:

- `psh/lexer/modular_lexer.py`
- `psh/lexer/cmdsub_scanner.py`
- `psh/lexer/recognizers/literal.py`
- `psh/lexer/recognizers/word_scanners.py`
- `psh/lexer/expansion_parser.py`
- `psh/lexer/quote_parser.py`
- `psh/lexer/token_types.py`
- `psh/lexer/token_parts.py`
- `psh/parser/recursive_descent/parser.py`
- `psh/parser/recursive_descent/context.py`
- `psh/parser/recursive_descent/support/word_builder.py`
- `psh/parser/recursive_descent/parsers/commands.py`
- `psh/parser/recursive_descent/parsers/arrays.py`
- `psh/parser/recursive_descent/parsers/control_structures.py`
- `psh/ast_nodes.py`

Validation run:

```bash
python -m pytest \
  tests/unit/lexer \
  tests/unit/parser \
  tests/unit/visitor/test_ast_coverage_matrix.py \
  tests/integration/parsing/test_cmdsub_grammar.py \
  tests/conformance/bash/test_cmdsub_case_conformance.py
```

Result:

```text
1004 passed in 8.30s
```

## Executive Summary

The current lexer/parser/AST architecture is considerably more coherent than earlier transitional states. The strongest positive change is that `Word` is now the canonical carrier for command arguments, loop items, array elements, and case patterns in the recursive-descent path. `SimpleCommand.args` is derived from `words`, not stored separately, which removes one major synchronization trap.

The code is still not "textbook elegant" overall. It is pragmatic, increasingly well-tested shell implementation code. The main problem is that the hardest shell contexts are represented by multiple overlapping metadata systems:

- tokens carry `value`, `quote_type`, `parts`, `adjacent_to_previous`, `is_keyword`, `fd`, and `combined_redirect`;
- AST words carry both whole-word `quote_type` and per-part quote state;
- several AST nodes carry canonical `Word` fields plus legacy string fields and quote-type lists;
- array syntax is recognized partly in the lexer, partly in parser lookahead, and partly by reparsing serialized text downstream;
- command substitution extent detection is a specialized grammar scanner that must stay in sync with the real parser.

None of these are reckless decisions. Shell grammar forces some context sensitivity. But the elegance gap is clear: too many structures encode the same facts in different forms, and too many parser branches compensate for tokenization shape variance.

Current qualitative grades:

| Area | Grade | Rationale |
| --- | --- | --- |
| Lexer architecture | B+ | Modular recognizers plus explicit scanners are good; contextual bypass/fallback machinery is complex. |
| Parser architecture | B+ | Recursive-descent orchestration is clear; arrays and source-preserving declaration args remain awkward. |
| AST model | B | `Word` direction is right; legacy parallel fields and optional canonical fields weaken invariants. |
| Elegance | B- | Strong comments and tests, but too many overlapping representations. |
| Test posture | A- | Focused regression coverage is excellent; remaining risk is invariant drift across metadata layers. |

## What Is Good

### 1. `Word` Is Becoming the Right Semantic Boundary

`SimpleCommand` now stores `words` as the source of truth and exposes `args` as a derived string view (`psh/ast_nodes.py:317`). This is the right model for shell parsing because quote and expansion semantics belong in structured word parts, not in flattened strings.

The same direction appears in:

- array initialization `words` (`psh/ast_nodes.py:275`);
- array element `value_word` (`psh/ast_nodes.py:293`);
- `ForLoop.item_words` (`psh/ast_nodes.py:545`);
- `SelectLoop.item_words` (`psh/ast_nodes.py:595`);
- `CasePattern.word` (`psh/ast_nodes.py:437`).

That is a major architectural improvement. It lets expansion operate on syntax structure instead of reconstructing structure from strings.

### 2. The Recursive-Descent Parser Is Well-Shaped

The main parser class is an orchestrator rather than a monolith (`psh/parser/recursive_descent/parser.py:38`). It delegates to focused parsers for statements, commands, control structures, tests, arithmetic, redirections, arrays, and functions. `ParserContext` centralizes token position, config, source text, and incomplete-input hints (`psh/parser/recursive_descent/context.py:17`).

This is a good architecture for a hand-written shell parser. The recursive call structure remains the real grammar context, and `open_constructs` is explicitly documented as an error-reporting aid rather than a parse decision input.

### 3. Command Substitution Extent Handling Is Much More Honest

`find_command_substitution_end()` now lives in `psh/lexer/cmdsub_scanner.py` and explicitly declares itself a parser component (`psh/lexer/cmdsub_scanner.py:179`). The maintenance contract is unusually clear: it lists which grammar features it mirrors and which tests own the behavior (`psh/lexer/cmdsub_scanner.py:252`).

This is not small code, but it is honest code. Given shell grammar, that is a real improvement over pretending `$()` can be found by counting parentheses.

### 4. Lexer Hot Paths Have Better Complexity Discipline

The assignment-subscript map in `ModularLexer._is_inside_potential_array_assignment()` is now a cached O(n) forward pass (`psh/lexer/modular_lexer.py:352`). The literal recognizer's word-shape logic has also moved into testable pure scanner helpers in `word_scanners.py`.

This is a good pattern: replace repeated contextual guessing with explicit incremental state.

### 5. The Tests Match the Risk

The focused validation slice passed 1004 tests. The most important coverage is not just broad unit count; it is the specific conformance and integration coverage around command substitutions containing `case`, comments, heredocs, quotes, and nested substitutions. Those are exactly the constructs most likely to drift.

## Uglies and Recommended Improvements

### Ugly 1: The AST Still Has Parallel Canonical and Legacy Representations

Examples:

- `ArrayInitialization` has `elements`, `element_types`, `element_quote_types`, and `words` (`psh/ast_nodes.py:275`).
- `ArrayElementAssignment` has `value`, `value_type`, `value_quote_type`, and `value_word` (`psh/ast_nodes.py:293`).
- `ForLoop` has `items`, `item_quote_types`, and `item_words` (`psh/ast_nodes.py:545`).
- `SelectLoop` has the same pattern (`psh/ast_nodes.py:595`).
- `CasePattern` has `pattern` and optional `word` (`psh/ast_nodes.py:437`).
- `BinaryTestExpression` still stores string operands plus quote-type side channels (`psh/ast_nodes.py:471`).

The comments are good and make the transitional status explicit. The model is still ugly because an AST node can claim two truths at once. For example, `ArrayInitialization.elements` and `ArrayInitialization.words` can diverge if manually constructed or modified by a visitor. Optional canonical fields like `value_word: Optional[Word]` are especially awkward when comments say they are required.

Recommended change:

1. Introduce display/source helpers instead of storing parallel display fields.
2. Make canonical fields non-optional where parser output requires them.
3. Move legacy compatibility into adapter properties or formatter helpers.
4. Add invariant tests that construct ASTs through the parser and assert canonical fields exist everywhere.

Concretely:

- `ArrayInitialization.elements` should eventually become a derived property from `words`, or a `source_elements` display-only field whose consumers are listed and isolated.
- `ArrayElementAssignment.value_word` should become `Word`, not `Optional[Word]`, for parser-built ASTs.
- `ForLoop.item_words` and `SelectLoop.item_words` should become `List[Word]`, with `"$@"` represented as a real default word.
- `CaseConditional.expr` should become `expr_word: Word` plus a derived `expr` property.
- `TestExpression` operands should migrate to `Word` nodes or a dedicated `TestWord` type.

### Ugly 2: Token Metadata Is Too Multifunctional

The token model combines lexical category, source span, quote state, composite parts, keyword normalization state, redirection fd metadata, combined-redirect metadata, and adjacency (`psh/lexer/token_types.py:93`).

This is convenient, but it makes tokens a weak boundary. Downstream code has to know which fields are meaningful for which token types. `WordBuilder` reads token type, token value, token quote type, token parts, and token part expansion metadata (`psh/parser/recursive_descent/support/word_builder.py:41`). `TokenStream.peek_composite_sequence()` uses adjacency plus a hard-coded word-like set. Redirection parsing relies on `fd` and `combined_redirect`.

Recommended change:

Introduce typed payloads or narrower token variants, even if implemented with dataclasses rather than a full class hierarchy.

For example:

```python
@dataclass(frozen=True)
class Token:
    type: TokenType
    span: SourceSpan
    text: str
    payload: TokenPayload = NoPayload()
```

Payload variants could include:

- `WordPayload(parts, quote_context)`
- `RedirectPayload(fd, combined)`
- `KeywordPayload(canonical)`

This would reduce "field is present but only sometimes meaningful" logic. It would also make it easier to enforce invariants with type checks and tests.

### Ugly 3: Whole-Word Quote State and Per-Part Quote State Overlap

`Word` has a whole-word `quote_type` (`psh/ast_nodes.py:170`), while `LiteralPart` and `ExpansionPart` each have `quoted` and `quote_char`. `Word.is_quoted` then infers from both (`psh/ast_nodes.py:206`), and `Word.effective_quote_char` picks a "dominant" quote character (`psh/ast_nodes.py:248`).

This works, but it is not elegant. Shell words are naturally a sequence of quoted and unquoted spans. A composite like `a"b"$c` has no single quote type. The current model partly acknowledges that, but still keeps a whole-word quote type for simple cases.

Recommended change:

Make quote context exclusively a property of word parts. Replace whole-word `quote_type` with helper constructors:

- `Word.single_quoted(text)`
- `Word.double_quoted(parts)`
- `Word.literal(text)`

Then derive `is_fully_quoted`, `has_quoted_parts`, and `quote_profile` from parts only. This would remove the need for "dominant quote character" as stored semantic state.

### Ugly 4: `Word.__str__` Is Doing Too Much Semantic Work

`Word.__str__()` returns a source-shaped representation with surrounding quotes for whole-word quoted words (`psh/ast_nodes.py:182`). Other code frequently uses `''.join(str(p) for p in word.parts)` to avoid the wrapper and get a flattened pre-expansion string, for example in arrays and loops (`psh/parser/recursive_descent/parsers/arrays.py:449`, `psh/parser/recursive_descent/parsers/control_structures.py:246`).

That is a smell. The codebase has at least three different string needs:

- source-like rendering,
- pre-expansion display text,
- quote-removed literal text.

Recommended change:

Give `Word` explicit methods and make callers use them:

- `word.source_text()`
- `word.display_text()`
- `word.literal_text_after_quote_removal()`
- `word.debug_text()`

Then retire generic `str(word)` from semantic paths. Keep `__str__` only for debugging or make it call `source_text()` with a warning in comments.

### Ugly 5: Array Parsing Is Still a Tokenization-Shape Matrix

`ArrayParser.is_array_assignment()` documents six tokenization patterns (`psh/parser/recursive_descent/parsers/arrays.py:63`). `parse_array_assignment()` then handles several cases:

- `arr[0]=value` in one token;
- `arr[0]` plus `=value`;
- `name` plus bracket tokens;
- `name` plus WORD `"["`;
- `name=` plus `LPAREN`;
- `name`, `"="`, `LPAREN`;
- append variants.

This is the single ugliest parser area I reviewed. It is not careless code; it is compensating for lexer shape variance. But the result is a parser that understands too much about how the lexer happened to split words.

Recommended change:

Create a normalized parser-level `WordCursor` or `AssignmentHead` abstraction before array parsing.

Instead of branching on raw token shapes in `ArrayParser`, normalize adjacent word-like tokens into a structured candidate:

```python
AssignmentCandidate(
    name: str,
    subscript_tokens: list[Token] | None,
    operator: "=" | "+=" | None,
    value_word_prefix: Word | None,
    initializer_start: bool,
)
```

Then `ArrayParser` consumes candidates rather than tokenization accidents. This would move the complexity to one normalization layer and make array parsing closer to grammar.

### Ugly 6: Declaration-Argument Array Initialization Is Serialized and Reparsed

`CommandParser._parse_array_initialization()` handles `declare -a arr=(...)` in argument position by serializing original tokens into a flat string (`psh/parser/recursive_descent/parsers/commands.py:232`). The comment is candid: declaration builtins receive the string and re-parse it later.

This is an understandable transitional design, but architecturally it is one of the least elegant paths. The parser has already done hard work to build `Word` parts, but then source spelling must be preserved because the builtin reparses text.

Recommended change:

Introduce an AST node for declaration-assignment arguments:

```python
@dataclass
class AssignmentWord(ASTNode):
    name: str
    operator: Literal["=", "+="]
    value: Word | ArrayInitializer
    declaration_context: bool = False
```

Then declaration builtins can consume structured assignment arguments directly. This would remove the token serialization path and eliminate the need to preserve fragile source spelling for `${y}b` and adjacent quotes.

### Ugly 7: Command Substitution Scanner Is a Parallel Grammar

`find_command_substitution_end()` is necessary and well-documented, but it is still a parallel grammar model (`psh/lexer/cmdsub_scanner.py:252`). It mirrors quotes, comments, heredocs, arithmetic, grouping, and `case`. `_CmdSubScanner` has its own command-position approximation and case-state machine (`psh/lexer/cmdsub_scanner.py:280`).

This is the most dangerous elegance compromise in the lexer. It is probably the right compromise for now, because parsing `$()` extent before tokenization is inherently difficult. But it should be treated as a high-risk component.

Recommended change:

Do not try to make this "small" by hiding complexity. Instead:

1. Make scanner state typed. Replace list states like `[state, pattern_paren_depth]` with a dataclass:

   ```python
   @dataclass
   class CaseScanState:
       phase: CasePhase
       pattern_paren_depth: int = 0
   ```

2. Replace string phase constants with an `Enum`.
3. Extract command-position tracking into a shared helper used by the lexer normalizer and the scanner, or at least put the shared keyword/separator policy in one module.
4. Add a test that compares scanner extent against actual parsing for a generated corpus of command substitutions.

The current docstring is excellent. The implementation should now become as typed as the contract.

### Ugly 8: Keyword Recognition Exists in Multiple Similar Machines

There is lexer command-position tracking in `ModularLexer._update_command_position_context()` (`psh/lexer/modular_lexer.py:192`), keyword normalization in `KeywordNormalizer.normalize()`, and command-position approximation inside `_CmdSubScanner`.

These machines are not identical, but they are close enough that drift is a real risk. The scanner docstring even says its command-position rules must agree with the real lexer/parser (`psh/lexer/cmdsub_scanner.py:243`).

Recommended change:

Extract a small `CommandPositionMachine` with explicit events:

- `word(value)`
- `operator(token_type)`
- `redirect()`
- `keyword(token_type)`
- `open_group()`
- `close_group()`

Then reuse it in:

- modular lexing context updates,
- keyword normalization,
- command-substitution scanner.

The scanner may still need special case-state additions, but the baseline "could this word be a reserved word?" policy should not live in three places.

### Ugly 9: Fallback Word Collection Is a Sign of Leaky Recognition Rules

`ModularLexer._handle_fallback_word()` is well documented and validated by fuzz/corpus notes (`psh/lexer/modular_lexer.py:607`). It handles `]`, `+`, `=`, and `[` as legitimate word starts after the literal recognizer rejects them.

The ugliness is not that fallback exists. The ugliness is that a "fallback" is now an expected production path for real shell words. That makes the recognizer pipeline less elegant: the literal recognizer does not fully own literal words.

Recommended change:

Rename and promote this path. Instead of `_handle_fallback_word`, make it a real recognizer, for example `OperatorDebrisWordRecognizer`, with its own tests and priority. That would make the architecture honest: these are not fallback accidents, they are grammar-recognized word forms.

### Ugly 10: `WordBuilder` Contains Conventions Rather Than a Type Contract

`WordBuilder.parse_expansion_token()` knows that:

- `VARIABLE` values lack `$`;
- simple `${x}` may arrive as `VARIABLE` with braces;
- `COMMAND_SUB` includes `$(` and `)`;
- `PARAM_EXPANSION` includes full `${...}`;
- process substitutions include `<(` or `>(`;
- token parts use string expansion type labels (`variable`, `parameter`, `command`, etc.).

That logic is clear, but it encodes token conventions procedurally (`psh/parser/recursive_descent/support/word_builder.py:41`). The token type does not itself guarantee the payload shape.

Recommended change:

Move expansion token parsing closer to token creation. Ideally the lexer emits token parts that already carry structured expansion payloads, or at least a typed `ExpansionTokenPayload`. Then `WordBuilder` becomes a shallow adapter:

```python
Word(parts=[ExpansionPart(token.payload.expansion, quoted=...)])
```

This would remove regex-based simple-parameter classification from `WordBuilder` and reduce the chance that lexer and parser disagree about expansion spelling.

### Ugly 11: Enhanced Test AST Has Not Joined the `Word` Model

`BinaryTestExpression` still stores `left` and `right` as strings and quote metadata separately (`psh/ast_nodes.py:471`). The comment says this is pending Word-AST migration. That is a real remaining semantic asymmetry.

Recommended change:

Introduce `TestOperand`:

```python
@dataclass
class TestOperand(ASTNode):
    word: Word
    role: Literal["string", "pattern", "regex", "arithmetic"]
```

Then `[[ $x == "a*" ]]` can preserve the distinction between quoted literal pattern text and unquoted pattern syntax without side-channel quote fields.

### Ugly 12: The Combinator Parser Still Dilutes the Architecture Story

The recursive-descent parser is clearly the production path. The combinator parser still exists and shares helpers like `WordBuilder`. Project documentation appears to mark it educational-only, which is the right answer, but the code still has to carry compatibility comments such as `CasePattern.pattern` being retained for the combinator parser (`psh/ast_nodes.py:437`).

Recommended change:

Make the boundary explicit in code, not just documentation:

- put combinator-only compatibility adapters in the combinator package;
- avoid letting combinator needs shape canonical AST fields;
- add a module-level warning or feature flag stating it is non-canonical.

If it is educational-only, it should not impose permanent complexity on the production AST.

## Proposed Refactor Plan

### Phase 1: Lock Down Invariants

Add tests that assert parser-built ASTs satisfy canonical invariants:

- all `SimpleCommand` args are in `words`;
- all array initializer elements have `words`;
- all array element assignments have non-`None value_word`;
- all `ForLoop` and `SelectLoop` parser outputs have `item_words`;
- all recursive-descent case patterns have `word`;
- no executor path consumes legacy string fields where `Word` exists.

This phase should not change behavior. It gives a safety net for the cleanup.

### Phase 2: Make Legacy Fields Derived or Isolated

Start with the least risky fields:

- derive `ForLoop.items` from `item_words`;
- derive `SelectLoop.items` from `item_words`;
- derive `CasePattern.pattern` from `word`;
- make `ArrayElementAssignment.value_word` non-optional.

Keep compatibility properties temporarily if visitor or formatter code still needs old names.

### Phase 3: Normalize Assignment and Array Syntax Before Parsing

Build a parser-level normalization layer over adjacent word-like tokens. The goal is to make array parsing consume one structured candidate instead of six tokenization patterns.

This should shrink `ArrayParser` substantially and remove many branches that currently compensate for lexer shape.

### Phase 4: Replace Declaration-Argument Reparse

Add structured assignment/declaration AST nodes and teach declaration builtins to consume them. This removes the source-string serialization in `CommandParser._parse_array_initialization()`.

This is a high-value refactor because it removes one of the last places where parsed syntax is intentionally flattened and reparsed.

### Phase 5: Type the Command-Substitution Scanner

Keep the scanner, but make the state model more explicit:

- `Enum` for case phases;
- `CaseScanState` dataclass;
- shared command-position policy;
- tests comparing scanner extent and parser acceptance over generated tricky `$()` bodies.

This would preserve correctness while making the scanner less ad hoc.

### Phase 6: Finish Test Operand Migration

Move `[[ ... ]]` operands to `Word` or `TestOperand`. This brings the last major parser expression island into the same AST model as commands, loops, arrays, and case patterns.

## Bottom Line

The current lexer/parser/AST design is strong enough to support continued shell semantics work. It is not textbook-simple, but shell grammar is not textbook-simple either. The recent direction is right: preserve structured words, fail loudly on impossible lexer states, and back high-risk grammar corners with focused conformance tests.

The next quality jump should not be another layer of comments. It should be invariant cleanup:

1. make `Word` the only semantic representation of shell words;
2. remove or derive legacy string/quote side channels;
3. normalize tokenization-shape variance before specialized parsers see it;
4. type the command-substitution scanner's state;
5. migrate `[[ ... ]]` operands into the same word model.

Those changes would make the subsystems feel less like a successful accumulation of fixes and more like a deliberately shaped language front end.
