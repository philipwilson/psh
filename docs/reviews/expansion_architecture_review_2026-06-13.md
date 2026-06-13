# Expansion Architecture Review

Date: 2026-06-13

Scope: `psh/expansion/`, with spot checks of parser/executor/builtin integration where they affect expansion semantics. I read `psh/expansion/CLAUDE.md` for subsystem context, then checked the implementation directly rather than treating the documentation as authoritative.

## Verification

Broad expansion-focused run:

```sh
python -m pytest tests/unit/expansion tests/integration/parameter_expansion tests/integration/arrays tests/integration/control_flow/test_for_select_item_expansion.py -q
```

Result:

```text
1728 passed, 1 skipped, 5 errors in 12.47s
```

The errors were all setup failures from `tests/unit/expansion/test_arithmetic_characterization.py`: `OSError: [Errno 24] Too many open files` while constructing `SignalNotifier` pipes. Rerunning that file alone reproduced the same class of failure:

```text
154 passed, 1 skipped, 8 errors in 0.28s
```

The local fixture creates `Shell()` directly (`tests/unit/expansion/test_arithmetic_characterization.py:24`) and does not run the standard `_cleanup_shell()` teardown that closes signal notifier FDs (`tests/conftest.py:60`). This appears to be a test-resource leak, not an expansion semantic failure.

Clean baseline excluding that file:

```sh
python -m pytest tests/unit/expansion tests/integration/parameter_expansion tests/integration/arrays tests/integration/control_flow/test_for_select_item_expansion.py --ignore=tests/unit/expansion/test_arithmetic_characterization.py -q
```

Result:

```text
1571 passed in 12.22s
```

Current size signals:

```text
psh/expansion/word_expander.py              897 lines
psh/expansion/brace_expansion.py            844 lines
psh/expansion/variable.py                   444 lines
psh/expansion/operators.py                  429 lines
psh/expansion/arithmetic/evaluator.py       414 lines
psh/expansion/arithmetic/tokenizer.py       376 lines
psh/expansion/arithmetic/parser.py          316 lines
psh/expansion/extglob.py                    295 lines
psh/expansion/manager.py                    267 lines
psh/expansion/operands.py                   261 lines
psh/expansion/arrays.py                     252 lines
psh/expansion/param_parser.py               228 lines
```

## Executive Verdict

The expansion subsystem is one of the stronger parts of the project. It is not textbook-simple, because shell expansion is intrinsically hostile to simple designs, but the newer core has the right shape: named policies, an explicit segment intermediate representation, a single parameter-expansion parser, and fail-loud behavior replacing historical fallback coercions.

The best code is `word_expander.py` despite its size. Its `WordExpansionPolicy` table makes context differences explicit (`psh/expansion/word_expander.py:48`), and `ExpandedSegment` gives field splitting and globbing a real intermediate representation (`psh/expansion/word_expander.py:120`). This is exactly the kind of structure shell expansion needs.

The weakest areas are:

- `word_expander.py` is too large and has several highly delicate methods.
- `VariableExpander.expand_parameter_direct()` remains a large semantic dispatcher.
- operand mini-expansion is still string-scanner based.
- `ExpansionEvaluator` often reconstructs shell source strings from AST nodes before delegating.
- brace expansion is large, textual, and contains token-stream repair logic.
- the arithmetic characterization test leaks Shell resources by bypassing fixture cleanup.

Quality rating by area:

| Area | Current rating | Direction | Short version |
| --- | --- | --- | --- |
| Word expansion engine | Good | Improving | Strong model; large methods need extraction. |
| Policy model | Very good | Stable | Clear, named, bash-pinned context axes. |
| Parameter parser | Good | Improved | Single grammar classifier; still string-level operands. |
| Variable/parameter evaluation | Solid but heavy | Improving | Decomposed mixins help, but main dispatch is still too big. |
| Operand expansion | Adequate | Stable | Correctness-oriented string scanner, not elegant. |
| Brace expansion | Adequate, least elegant | Improving | Token-stream version avoids relexing, but uses placeholder machinery and special cases. |
| Arithmetic expansion | Solid package shape | Improving | Decomposed into tokenizer/parser/evaluator; test fixture needs cleanup. |

## What Is Strong

### 1. Expansion policy is explicit

`WordExpansionPolicy` captures the three axes that vary between contexts: `split`, `glob`, and `assignment_tilde` (`psh/expansion/word_expander.py:48`). The named policies make call sites state intent:

- `COMMAND_ARGUMENT`
- `LOOP_ITEM`
- `DECLARATION_ASSIGNMENT`
- `ARRAY_INIT_ELEMENT`
- `ASSOC_INIT_ELEMENT`

This is substantially better than passing boolean flag pairs through generic expansion helpers. It is close to textbook quality because it names semantic contexts rather than implementation switches.

### 2. `ExpandedSegment` is the right intermediate model

The segment model encodes text plus whether it is quoted, splittable, or glob-eligible (`psh/expansion/word_expander.py:120`). That lets `_finish()` run explicit passes: field splitting, globbing, then join/quote removal (`psh/expansion/word_expander.py:423`).

This is the clearest architectural improvement in expansion. Shell word expansion is hard because literal text, quoted text, and expansion results must join before and after splitting in context-sensitive ways. A segment IR is the right tool.

### 3. The manager is a real orchestrator

`ExpansionManager.expand_arguments()` does not perform the expansion itself. It decides whether declaration-builtin assignment semantics apply, chooses the policy, and delegates to `WordExpander` (`psh/expansion/manager.py:70`).

The syntactic declaration-builtin check is properly conservative: the command word must be an unquoted literal (`psh/expansion/manager.py:128`), and assignment-shaped arguments are detected by walking unquoted literal prefix parts (`psh/expansion/manager.py:141`).

### 4. Parameter parsing was centralized

`param_parser.py` is now the single classifier for `${...}` content (`psh/expansion/param_parser.py:1`). Its docstring documents the emitted shapes and disambiguation rules. This replaced several previously duplicated scans, and it is shared by parse-time `WordBuilder` and runtime string expansion.

This is the right direction: parse once into a stable representation, then evaluate consistently.

### 5. Tests are unusually strong

The expansion tests include characterization, policy freezing, bash-pinned edge cases, parameter parser differential tests, pattern operand tests, array initializer integration, and for/select item expansion tests. The clean focused run excluding the leaky arithmetic file passed 1571 tests.

This subsystem is not relying on hope.

## Remaining Uglies

### Ugly 1: `word_expander.py` is doing too much

`word_expander.py` is 897 lines. Its module-level architecture is good, but several methods are dense:

- `_walk_literal_part()` handles quote semantics, assignment-value tilde tracking, escape processing, leading tilde expansion, and glob eligibility (`psh/expansion/word_expander.py:262`).
- `_walk_expansion_part()` handles process substitution, quoted field expansions, standalone unquoted field expansions, splitting policy exceptions, and generic expansion (`psh/expansion/word_expander.py:332`).
- `_expand_at_with_affixes()` implements a subtle `$@`/`${arr[@]}` splicing algorithm (`psh/expansion/word_expander.py:702`).

The code is well-commented, but the methods are at the limit of what a maintainer can safely reason about.

Recommended changes:

1. Split `word_expander.py` into a package:
   - `policy.py`: `WordExpansionPolicy` and named policies.
   - `segments.py`: `ExpandedSegment`, `_WalkState`, field splitting and glob pass helpers.
   - `walker.py`: part walking.
   - `assignment_value.py`: scalar assignment-value walker and tilde rules.
   - `field_expansions.py`: `$@` / `${arr[@]}` field production and affix splicing.
2. Keep `WordExpander` as a thin facade that wires those pieces together.
3. Add focused tests directly against `_expand_at_with_affixes()` behavior through public expansion calls before moving it.

### Ugly 2: expansion results still use `str | list[str]`

`WordExpander.expand()` returns either a string or a list (`psh/expansion/word_expander.py:212`). The manager and callers then branch on `isinstance(expanded, list)` (`psh/expansion/manager.py:116`).

That matches historical API shape, but it is not elegant. The distinction being represented is "zero or more fields", not "sometimes scalar, sometimes list."

Recommended change:

- Introduce an `ExpandedFields` result object:
  - `fields: list[str]`
  - `is_scalar_context: bool` or separate APIs for scalar vs field contexts.
- Make field-producing contexts always return a list.
- Keep a scalar-only method for assignment values.

The code already has two separate walkers. The return type should reflect that separation.

### Ugly 3: assignment tilde tracking is hidden state inside literal walking

The assignment-value tilde logic is correct-looking and well documented, but the implementation is spread across `_WalkState` fields (`assign_prefix`, `assign_seen`, `value_len`, `prev_char`) and `_walk_literal_part()` (`psh/expansion/word_expander.py:161`, `psh/expansion/word_expander.py:289`).

This is subtle enough to deserve a named state machine.

Recommended change:

- Extract `AssignmentTildeTracker` with methods:
  - `feed_literal(text, quoted, parts_follow) -> transformed_text`
  - `feed_expansion()`
  - `feed_quoted_text()`
- Reuse it in both the field-producing walker and `expand_assignment_value_word()`.

That would reduce duplicated tilde-trigger logic between the general word path and scalar assignment-value path (`psh/expansion/word_expander.py:536`).

### Ugly 4: `expand_parameter_direct()` is still a giant semantic dispatcher

Centralizing parameter parsing was a major improvement, but evaluation is still a large branch tree. `expand_parameter_direct()` handles indirection, namerefs, special parameters, positional parameters, arrays, array slices, transforms, conditional operators, and scalar fallback in one method (`psh/expansion/variable.py:150`).

The mixin decomposition helps file organization, but not local reasoning inside this method.

Recommended change:

- Introduce a resolved parameter model:
  - `ResolvedScalar(name, value, is_set)`
  - `ResolvedArrayElement(name, key/index, value, is_set)`
  - `ResolvedFieldParameter(name, fields, joiner)`
  - `ResolvedSpecial(name, value, is_set)`
- Split evaluation into:
  - resolve target
  - choose operation family
  - apply operation
- Move whole-array `@/*` behavior out of the middle of `expand_parameter_direct()` and into a dedicated resolver/evaluator.

The operator application helpers are already separated in `operators.py`; the next cleanup is to separate parameter resolution from operator dispatch.

### Ugly 5: AST expansion evaluation reconstructs source strings

`ExpansionEvaluator` receives AST nodes but often reconstructs shell syntax strings before delegating:

- `VariableExpansion` becomes `$name` or `${name}` (`psh/expansion/evaluator.py:60`).
- `CommandSubstitution` becomes `$(...)` or backticks (`psh/expansion/evaluator.py:72`).
- plain `ParameterExpansion` becomes `${parameter}` (`psh/expansion/evaluator.py:93`).
- arithmetic becomes `$((expr))` (`psh/expansion/evaluator.py:98`).

This is a compatibility bridge, not an ideal AST runtime. It means the AST does not fully own expansion semantics yet.

Recommended change:

- Add direct evaluator methods:
  - `expand_variable_name(name)`
  - `expand_plain_parameter(parameter)`
  - `execute_command_substitution(command, style)`
  - `evaluate_arithmetic_expression(expression)`
- Keep string entry points for here-docs, prompt-like contexts, and operand text, but do not route AST nodes through reconstructed syntax when avoidable.

### Ugly 6: operand expansion is a mini-parser over raw strings

`operands.py` must split pattern/replacement operands, skip nested `$` constructs, remove one level of quotes, escape quoted text for glob matching, and interpret unquoted `&` in replacements (`psh/expansion/operands.py:31`, `psh/expansion/operands.py:101`, `psh/expansion/operands.py:162`, `psh/expansion/operands.py:202`).

This is carefully done, but it is still raw string parsing. It also imports lexer delimiter helpers and the command-substitution scanner (`psh/expansion/operands.py:72`), which creates a cross-subsystem dependency from expansion back into lexer internals.

Recommended change:

- Represent parameter-expansion operands as token/part sequences at parse time where possible.
- Add an `OperandWord` or reuse `Word` with operand mode:
  - pattern operand: quoted segments become glob-escaped
  - replacement operand: unquoted `&` becomes `PATSUB_MATCH`
  - conditional operand: normal string expansion plus quote removal
- Until then, keep the raw scanner but add a routing comment at the top naming every context that uses it.

### Ugly 7: brace expansion is least elegant

`brace_expansion.py` is 844 lines. The core expander is textual and includes shell-operator suffix detachment (`psh/expansion/brace_expansion.py:116`). The token-stream wrapper then has to preserve quote context, suppress command-prefix assignment expansion, track command-prefix zones, encode composite token runs into private-use placeholders, and bail out on variable-name fusion cases (`psh/expansion/brace_expansion.py:596`, `psh/expansion/brace_expansion.py:712`).

The token-stream approach is safer than raw-line expansion and relexing. Still, placeholder encoding is a sign the lexer/token model is not giving brace expansion the shape it wants.

Recommended change:

- Separate brace expansion into:
  - `brace/core.py`: pure brace grammar, no shell operator detachment.
  - `brace/token_stream.py`: command-prefix zones and token expansion.
  - `brace/composite.py`: placeholder encoding/decoding for adjacent token runs.
- Move shell-operator suffix detachment out of `BraceExpander._expand_one_brace()` and into the token-stream layer if still needed.
- Add explicit tests around the "cannot reproduce `$x{1,2}` name fusion" limitation and document whether it is accepted divergence or future work.

### Ugly 8: `VariableExpander` mixins are decomposed, but the facade is still string-centric

The facade has good boundaries on paper: arrays, fields, operands, operators. But the public entry points still mostly accept shell source strings, and arrays are identified by `[`/`]` string inspection (`psh/expansion/variable.py:129`, `psh/expansion/variable.py:225`).

Recommended change:

- Introduce small parsed parameter references:
  - `ParameterRef(name)`
  - `ArrayRef(name, subscript)`
  - `SpecialRef(name)`
  - `PositionalRef(index)`
- Let `param_parser.py` emit or help construct these instead of encoding subscripts inside `parameter: str`.

This would reduce repeated `if '[' in var_name and var_name.endswith(']')` checks across variable, arrays, fields, and operators.

### Ugly 9: arithmetic characterization tests leak Shell resources

This is not an expansion architecture problem, but it surfaced during verification. `tests/unit/expansion/test_arithmetic_characterization.py` defines local fixtures that instantiate `Shell()` and return it without teardown (`tests/unit/expansion/test_arithmetic_characterization.py:24`). The standard test cleanup closes notifier pipe FDs (`tests/conftest.py:75`), but these local fixtures bypass it.

Recommended change:

- Rewrite those fixtures as yielding fixtures:
  - `shell = Shell()`
  - `yield shell`
  - call the shared cleanup helper or expose a public shell close/cleanup method.
- Prefer using the existing `shell`/`captured_shell` fixtures when possible.
- Consider adding `Shell.close()` so tests and embedders do not need to know about internal interactive manager signal pipes.

## Is It Textbook Quality?

Parts of it are close:

- named expansion policies;
- explicit `ExpandedSegment` intermediate representation;
- fail-loud type checks;
- centralized parameter parser;
- focused, bash-pinned tests.

The whole subsystem is not textbook-quality yet because too much semantic state remains encoded as strings, several methods are too large, AST expansion still reconstructs shell syntax, and brace/operand expansion rely on custom raw scanners.

The pragmatic read: the expansion subsystem is better engineered than it is elegant. That is acceptable for a shell, but the next improvements should reduce local cognitive load rather than broaden behavior.

## Proposed Improvement Plan

### Phase 1: Stabilize Tests and Resource Cleanup

1. Fix `test_arithmetic_characterization.py` fixtures to close `Shell` resources.
2. Add a public `Shell.close()` or test helper so direct `Shell()` use is safe.
3. Rerun the broad expansion suite without `--ignore`.

### Phase 2: Split `word_expander.py` Along Existing Concepts

1. Move policies to `word/policy.py`.
2. Move `ExpandedSegment` and splitting/globbing passes to `word/segments.py`.
3. Move `$@`/`${arr[@]}` field logic to `word/fields.py`.
4. Move scalar assignment-value expansion to `word/assignment_value.py`.
5. Keep `WordExpander` as the public facade.

### Phase 3: Reduce String Reconstruction

1. Add direct variable/parameter/arithmetic evaluation APIs.
2. Change `ExpansionEvaluator` to call those APIs instead of rebuilding `$...` source forms.
3. Introduce parsed parameter reference objects so arrays/specials/positionals are not rediscovered by string inspection.

### Phase 4: Tame Parameter and Operand Evaluation

1. Split `expand_parameter_direct()` into parameter resolution plus operator-family dispatch.
2. Convert operand mini-expansion toward `Word`/part-based representation where parser data exists.
3. Keep string-scanner operands only for contexts that truly originate as raw strings.

### Phase 5: Isolate Brace Expansion Complexity

1. Split pure brace grammar from token-stream expansion.
2. Move command-prefix assignment suppression and shell-operator handling into the token-stream layer.
3. Make the placeholder composite algorithm its own documented module with limitation tests.

## Bottom Line

Expansion is in better shape than lexer/parser/AST overall. The central model is sound: `Word` parts feed a policy-driven expander that builds segments, splits only expansion-derived text, globs only eligible unquoted text, and handles assignment contexts explicitly.

The remaining work is mostly architectural pressure relief. Split the giant files, stop reconstructing shell source from AST nodes, introduce typed parameter references, and clean up the leaky arithmetic test fixture. That would move the subsystem from "well-tested and pragmatic" toward genuinely elegant.
