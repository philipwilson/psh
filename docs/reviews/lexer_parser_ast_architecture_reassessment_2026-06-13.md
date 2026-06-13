# Lexer, Parser, and AST Architecture Reassessment

Date: 2026-06-13

Scope: current code in `psh/lexer`, `psh/parser`, and `psh/ast_nodes.py`, with spot checks of the executor/builtin surfaces that consume AST shapes. I did not rely on older review conclusions as authority; this is a fresh read of the present tree, using the earlier report only as context for what changed.

## Verification

Focused subsystem suite:

```sh
python -m pytest tests/unit/lexer tests/unit/parser tests/integration/parsing/test_cmdsub_grammar.py tests/conformance/bash/test_cmdsub_case_conformance.py tests/integration/test_enhanced_test_word_operands.py -q
```

Result:

```text
1330 passed, 1 skipped in 7.91s
```

Current size signals:

```text
psh/ast_nodes.py                                           766 lines
psh/lexer/modular_lexer.py                                 610 lines
psh/lexer/cmdsub_scanner.py                                646 lines
psh/parser/recursive_descent/parsers/arrays.py             489 lines
psh/parser/recursive_descent/parsers/commands.py           551 lines
psh/parser/recursive_descent/parsers/tests.py              299 lines
psh/parser/recursive_descent/support/word_builder.py       269 lines
psh/parser/combinators/special_commands.py                 749 lines
psh/parser/combinators/commands.py                         685 lines
```

## Executive Verdict

These subsystems are not textbook-quality code yet, but they are materially better than before. The project has moved from "works through layered historical compromises" toward "works through named, characterized compromises." That is real progress.

The best recent changes are architectural, not just cleanup:

- `Word.parts` is now the source of truth for quote state; `Word.quote_type` is derived rather than stored.
- `SimpleCommand.args` is derived from `words`, not maintained in parallel.
- `ArrayInitialization.element_types`, `element_quote_types`, `ArrayElementAssignment.value_type`, and `value_quote_type` are derived compatibility properties.
- Declaration-builtin array initializers now carry a structured `Word.array_init`, avoiding the old serialize-then-reparse path for `declare -a a=(...)`.
- Array assignment parsing now has an `AssignmentCandidate` normalizer instead of duplicating token-shape checks in detector and parser paths.
- The lexer fallback word collector became a registered `OperatorDebrisWordRecognizer`, and the old silent no-progress path now raises.
- The three command-position vocabularies are centralized in `psh/lexer/command_position.py` and drift-locked by tests.

The code is therefore moving in the right direction. It is still not "textbook" because several important concepts are still represented indirectly: token metadata has multiple conventions, the AST file is a large compatibility hub, command-substitution lexing contains a parallel grammar, `[[ ]]` operands are only nominally `Word`-based, and some parser behavior is explicitly pinned around known divergences.

My quality rating by subsystem:

| Subsystem | Current rating | Direction | Short version |
| --- | --- | --- | --- |
| Lexer recognizer framework | Good | Improving | Modular and fail-loud, but token metadata and context rules are still too magical. |
| Command-substitution scanner | Good engineering, not elegant | Stable | Well-tested but necessarily ugly: it duplicates grammar in the lexer. |
| Recursive-descent parser | Solid but uneven | Improving | Production parser is readable; arrays and tests remain complexity sinks. |
| AST model | Better, still bloated | Improving | Canonical `Word` ownership is much clearer; `ast_nodes.py` is now a compatibility monolith. |
| Combinator parser | Educational/legacy quality | Stagnant | Still carries simplified semantics and should not drive AST design. |

## What Improved

### 1. Quote state has a clearer owner

`Word.quote_type` is now derived from `Word.parts`, rather than being another stored field that could disagree with per-part quote metadata (`psh/ast_nodes.py:195`). That is a significant correctness and elegance improvement.

The supporting methods are explicit:

- `source_text()`: debug/source-shaped rendering.
- `display_text()`: pre-expansion flattened text.
- `to_literal_string()`: quote-removal text with expansions left textual.

This is much more textbook than using `__str__` as a semantic multipurpose escape hatch. `__str__` still exists and delegates to `source_text()` (`psh/ast_nodes.py:234`), but the comments now discourage semantic callers from relying on it.

### 2. Legacy array sidecars are mostly isolated

`ArrayInitialization.words` and `ArrayElementAssignment.value_word` are now the canonical semantic fields (`psh/ast_nodes.py:391`, `psh/ast_nodes.py:419`). The old type/quote fields are derived properties for visitor compatibility (`psh/ast_nodes.py:402`, `psh/ast_nodes.py:428`).

The test `tests/unit/parser/test_legacy_field_isolation.py` locks executor/expansion code away from the legacy quote/type sidecars. That is exactly the right kind of safety net.

### 3. Declaration array initialization no longer reparses strings

The command parser attaches a structured `ArrayInitialization` to a `Word` for argument-position `name=(...)` (`psh/parser/recursive_descent/parsers/commands.py:189`). The executor passes those pending structured initializers to declaration builtins (`psh/executor/command.py:476`), and `local`/`declare` consume them via `ArrayOperationExecutor` instead of shlex-style reparsing.

This fixes a real architectural ugly. It is not merely cleaner; it removes a second parser from a runtime path.

### 4. Array assignment token-shape complexity is now named

`AssignmentCandidate` gives array assignment detection/parsing a single normalized representation (`psh/parser/recursive_descent/parsers/arrays.py:50`). `_normalize_assignment_head()` is now the one place that explains the live token shapes (`psh/parser/recursive_descent/parsers/arrays.py:89`).

This is not beautiful, but it is much more maintainable than repeated raw token peeking.

### 5. The lexer fallback became an actual recognizer

`OperatorDebrisWordRecognizer` is a proper recognizer with a narrow, census-backed domain (`psh/lexer/recognizers/operator_debris.py:1`). It accepts exactly `]`, `+`, `=`, and `[` as special word starts (`psh/lexer/recognizers/operator_debris.py:47`) and runs at the lowest recognizer priority (`psh/lexer/recognizers/operator_debris.py:59`).

The lexer's no-progress path now raises instead of silently dropping a character (`psh/lexer/modular_lexer.py:283`). That is a textbook-quality failure policy.

### 6. Command-position drift is explicitly controlled

`psh/lexer/command_position.py` documents the three command-position machines and their intentional differences (`psh/lexer/command_position.py:1`). The tests in `tests/unit/lexer/test_command_position_consistency.py` lock the vocabulary relationships.

This does not eliminate the design smell, but it prevents the worst failure mode: silent drift.

## Remaining Uglies

### Ugly 1: `ast_nodes.py` has become a compatibility monolith

The AST model is conceptually better, but the file has grown to 766 lines. It now contains:

- Core AST base types.
- Expansion nodes.
- Word/part model and rendering policy.
- Array assignment nodes and legacy-compatibility properties.
- Command/control-flow nodes.
- Enhanced test expression nodes.
- Compatibility comments that explain historical behavior.

The AST is no longer simply a clean data model. It is also a migration layer and a documentation sink. That is understandable during a transition, but it is not textbook-quality.

Recommended change:

- Split the file into a package such as `psh/ast/`:
  - `base.py`: `ASTNode`, `Statement`, `Command`, `CompoundCommand`.
  - `words.py`: `Word`, `WordPart`, `LiteralPart`, `ExpansionPart`, expansion render helpers.
  - `expansions.py`: `CommandSubstitution`, `ParameterExpansion`, etc.
  - `arrays.py`: array assignment nodes.
  - `commands.py`: simple command, redirects, pipelines.
  - `control.py`: loops, conditionals, case/select.
  - `tests.py`: `[[ ]]` expressions.
- Keep `psh/ast_nodes.py` as a re-export compatibility module until imports are migrated.

This would not change behavior, but it would make ownership boundaries real.

### Ugly 2: `Word.array_init` is a pragmatic side-channel

The structured declaration array initializer is a real improvement, but its storage location is awkward. `Word` now has a semantic payload that only applies to a special command-argument form (`psh/ast_nodes.py:181`). Most words will never use it.

The parser has to create a literal word with `array_init` attached (`psh/parser/recursive_descent/parsers/commands.py:191`), and the executor has to collect a side map keyed by the argument's flat display text (`psh/executor/command.py:476`). That is better than reparsing strings, but it is still a side-channel.

Recommended change:

- Introduce an argument node instead of making `Word` carry special command metadata:
  - `CommandArgument(word: Word)`
  - `DeclarationArrayArgument(flat_word: Word, init: ArrayInitialization)`
- Let `SimpleCommand` hold `arguments: list[CommandArgument]`, with `words` and `args` as derived compatibility views during migration.

This would put syntax classification where it belongs: on command arguments, not on every word in the language.

### Ugly 3: `[[ ]]` operands are only nominally Word-based

`BinaryTestExpression` now stores `left_word` and `right_word` (`psh/ast_nodes.py:612`), but the recursive-descent test parser still parses operands into strings and quote flags, then wraps the result as a single `LiteralPart` (`psh/parser/recursive_descent/parsers/tests.py:148`).

That means `[[ $x == "$y" ]]` does not carry the same structured expansion parts that ordinary command words carry. Expansion semantics remain string-level by design: `_parse_test_operand()` manually reconstructs `$name` spelling (`psh/parser/recursive_descent/parsers/tests.py:190`), and regex RHS parsing collects a raw adjacent run (`psh/parser/recursive_descent/parsers/tests.py:243`).

The combinator parser is even more explicit about the limitation: it wraps every test operand as an unquoted single literal because it does not track quote context (`psh/parser/combinators/special_commands.py:294`).

Recommended change:

- Add a `TestOperand` AST node with:
  - `word: Word`
  - `pattern_mode: literal | glob | regex`
  - `quoted_as_whole: bool`
  - perhaps `raw_regex_text` only for the `=~` RHS special case.
- Change the recursive-descent parser to build operands via `WordBuilder`/`parse_argument_as_word()` wherever possible.
- Keep derived `.left`, `.right`, and `.right_quote_type` only as temporary compatibility views.

Until then, the AST is structurally inconsistent: ordinary words are real words, but test operands are strings wearing a `Word` wrapper.

### Ugly 4: command-substitution scanning is a parallel parser

`cmdsub_scanner.py` is high-quality code for a hard problem, but it is not elegant architecture. Its own docstring says it is a parser component living in the lexer (`psh/lexer/cmdsub_scanner.py:267`). It tracks quoting, comments, heredocs, arithmetic, group parens, command position, and `case` phases (`psh/lexer/cmdsub_scanner.py:211`).

This is the right local solution for bash-like `$(...)` extent detection, but it remains a parallel grammar. Any grammar feature touching these areas must be added in two places: the real parser and this scanner.

Recommended change:

- Keep the current scanner for now; it is well-tested and likely lower-risk than a rewrite.
- Reduce future drift by extracting reusable lexical primitives:
  - quote skipping
  - heredoc delimiter reading
  - command-position transitions
  - reserved-word recognition at raw-text boundaries
- Add a small "scanner grammar matrix" test that lists the grammar features it intentionally shadows and links each to parser tests.

Longer term, consider a parser-assisted extent mode: tokenize inside `$(` with a sub-parser that can report the matching close. That is a larger architectural project and should wait until the production parser has fewer compatibility branches.

### Ugly 5: token metadata conventions are still too implicit

`WordBuilder` still has to know multiple token value conventions:

- `VARIABLE` token values may be bare names or `{name}` forms (`psh/parser/recursive_descent/support/word_builder.py:47`).
- command substitutions may include or omit delimiters, so the builder strips if present (`psh/parser/recursive_descent/support/word_builder.py:66`).
- arithmetic expansions are similarly stripped conditionally (`psh/parser/recursive_descent/support/word_builder.py:85`).
- `TokenPart.expansion_type` is a string vocabulary with its own conventions (`psh/parser/recursive_descent/support/word_builder.py:146`).

The lexer also still classifies complex parameter expansions by scanning the whole source string for operator substrings (`psh/lexer/modular_lexer.py:414`). The comment correctly calls this fragile.

Recommended change:

- Make expansion token payloads typed before they reach `WordBuilder`.
- Replace `TokenPart.expansion_type: str` with an enum or small variant classes.
- Give expansion tokens a normalized payload object:
  - `VariablePayload(name, braced: bool)`
  - `ParameterPayload(parameter, operator, word)`
  - `CommandSubPayload(command, style)`
  - `ArithmeticPayload(expression)`
- Let `WordBuilder` become mostly mechanical: token payload to AST node, not string decoding.

This would remove a large amount of defensive delimiter-stripping and string convention knowledge from the parser.

### Ugly 6: arrays are improved, but still grammar by token accident

The new `AssignmentCandidate` layer is a clear improvement. The remaining issue is that the parser still encodes lexer accident as grammar. The design note lists token shapes such as `WORD "a"` + `WORD "="` + `LPAREN` and `WORD "a[i]"` + `WORD "=v"` (`psh/parser/recursive_descent/parsers/arrays.py:20`). Some are documented bash divergences; the separate-bracket path is explicitly a pinned latent bug (`psh/parser/recursive_descent/parsers/arrays.py:31`).

The parser also still serializes array initializer element source fragments for the flat compatibility string (`psh/parser/recursive_descent/parsers/commands.py:295`), even though the structured path is authoritative.

Recommended change:

- Introduce an assignment-head token or token view before parsing:
  - `AssignmentHead(name, operator, subscript_tokens, initializer_kind)`
- Move token-shape normalization out of `ArrayParser` into a parser support module shared by array parser and command parser.
- Decide whether pinned spaced forms like `arr = (...)` are compatibility commitments or bugs to deprecate. If they are intentional psh extensions, document them as such outside comments.
- Once visitors and debug output can render from structured nodes, remove flat-string source serialization from command argument array init.

### Ugly 7: command-position still has three state machines

Centralizing command-position vocabulary is good. It does not remove the underlying issue: lexer, keyword normalizer, and command-substitution scanner still each maintain their own command-position state over different alphabets.

The current file is honest about this (`psh/lexer/command_position.py:5`). The asymmetries are documented and tested. That makes it acceptable, but not textbook-elegant.

Recommended change:

- Do not force a single state machine prematurely.
- Add a tiny trace/debug hook for command-position transitions in each machine, so a future mismatch can be diagnosed by comparing traces.
- Prefer adding grammar features by updating a checklist in `command_position.py` first, then implementing each machine.

### Ugly 8: the combinator parser keeps dragging old semantics along

The combinator parser still has large files (`special_commands.py` at 749 lines, `commands.py` at 685 lines), weaker `[[ ]]` operand semantics, and simplified array handling. It imports production `WordBuilder`, which is good, but it still cannot represent all production parser semantics.

Recommended change:

- Decide and document whether the combinator parser is:
  - educational only,
  - a migration target,
  - or a supported alternate parser.
- If educational only, stop letting it constrain AST evolution. Keep compatibility tests minimal and explicit.
- If supported, it needs the same canonical AST invariants and quote-context behavior as recursive descent, especially for `[[ ]]`.

My recommendation: mark it educational/experimental and keep it from blocking AST cleanup.

## Is It Textbook Quality?

No. Textbook-quality shell front ends would have:

- a crisp token model with typed payloads;
- an AST that is mostly pure structure, not compatibility migration logic;
- one production parser strategy;
- grammar constructs represented directly rather than reconstructed from token accidents;
- minimal semantic side-channels between parser and executor;
- no parallel grammar in the lexer, or at least a formally constrained one.

This project does not meet that bar. It does, however, show good engineering discipline in the hard places:

- behavior is heavily characterized;
- known compromises are named;
- fail-loud policies are replacing silent recovery;
- canonical AST fields are gaining authority;
- runtime paths are being isolated from legacy views.

So the code is not textbook, but parts of the cleanup strategy are textbook: identify the canonical representation, derive legacy views, lock invariants, then remove compatibility when consumers are gone.

## Proposed Improvement Plan

### Phase 1: Finish AST canonicalization

1. Split `psh/ast_nodes.py` into an `ast/` package with re-export compatibility.
2. Add a first-class `CommandArgument` node and move `array_init` off `Word`.
3. Add `TestOperand` and stop wrapping flattened `[[ ]]` operands as single literal words.
4. Make all legacy compatibility properties explicitly marked with deprecation comments and owner tests.

### Phase 2: Type lexer payloads

1. Replace string `expansion_type` values with an enum.
2. Add typed expansion payloads to tokens or token parts.
3. Remove substring-based parameter-expansion classification from `ModularLexer._handle_expansion()`.
4. Simplify `WordBuilder` after payloads become normalized.

### Phase 3: Reduce parser token-shape coupling

1. Extract assignment-head normalization into shared parser support.
2. Make array parser and command parser consume that normalized view.
3. Revisit pinned spaced-array divergences and either document them as psh extensions or align with bash.
4. Remove source-token serialization from declaration array init once rendering is structured.

### Phase 4: Fence the parallel parser/scanner risks

1. Treat `cmdsub_scanner.py` as a formal parser-adjacent component with a maintained grammar matrix.
2. Add trace hooks for command-position state in lexer, normalizer, and scanner.
3. Keep combinator parser out of production AST design unless it is upgraded to parity.

## Bottom Line

The recent changes improved the architecture meaningfully. The lexer is more modular and less forgiving of impossible states. The AST now has clearer canonical ownership for words, quote state, and array values. The parser has fewer duplicated token-shape checks.

The remaining uglies are mostly second-order design issues: the code now knows where its compromises are, but it still has them. The highest-value next step is not another broad refactor; it is to finish the canonical model by splitting the AST module, moving `array_init` into a command-argument node, and making `[[ ]]` operands truly structured.
