# Canonical AST Data Flow: Words, Values, and Redirects

**Audience**: anyone changing expansion or execution semantics. This
document answers "which code do I change?" for each context where shell
text becomes runtime values. Every claim was verified against the source
on 2026-06-12 (fallback audit; see
`docs/reviews/code_quality_subsystem_reassessment_2026-06-12.md` §2 and
`tests/unit/executor/test_legacy_ast_fallbacks.py`).

Two representations exist, by design:

1. **Word AST** (`psh/ast_nodes/words.py`: `Word`, `LiteralPart`,
   `ExpansionPart`) — carries per-part quote context. Used for command
   words, assignment values, array initializer elements, array element
   values, for/select items, and case patterns. **Both parsers always
   populate these fields**; the executor raises an internal error if one
   is missing (do not add silent string fallbacks back).
2. **Plain strings** — used where the AST stores flat text by design:
   redirect targets, heredoc bodies, here-strings, the case subject
   (`CaseConditional.expr`), arithmetic expression text, `${var:?msg}`
   operands, and `declare`/`local` array-initializer arguments. These are
   the *legitimate* callers of
   `ExpansionManager.expand_string_variables()`.

## The expansion engine (single implementation)

The engine — the part walkers, IFS splitting, globbing, escape
processing — lives in `psh/expansion/word_expander.py` together with the
named `WordExpansionPolicy` table (`COMMAND_ARGUMENT`, `LOOP_ITEM`,
`DECLARATION_ASSIGNMENT`, `ARRAY_INIT_ELEMENT`, `ASSOC_INIT_ELEMENT`;
axes: split / glob / assignment_tilde). `psh/expansion/manager.py` is the
orchestrator and keeps the public entry points:

| Entry point | Policy | Callers |
|---|---|---|
| `expand_arguments(command)` (manager.py) | full command-argument pipeline; detects declaration builtins and picks COMMAND_ARGUMENT vs DECLARATION_ASSIGNMENT per word | `CommandExecutor._expand_arguments` |
| `expand_word_to_fields(word, policy)` (manager.py) | same pipeline, one Word → 0..n fields, under the named policy | for/select items (LOOP_ITEM), array initializer elements (ARRAY_INIT_ELEMENT / ASSOC_INIT_ELEMENT) |
| `expand_assignment_value_word(word)` (manager.py → word_expander.py) | bash assignment-value policy: all expansions, NO splitting, NO globbing, tilde after `=`/`:` | scalar assignment values, array element values, assoc-array keys |
| `expand_word_as_pattern(word)` (manager.py) | quoted parts glob-escaped (match literally), unquoted parts keep glob power | case patterns |
| `WordExpander.expand_to_word(word, policy)` + `materialize` (word_expander.py) | the field engine: per-part walk into `ExpandedWord` (protection runs, `$@` splicing, IFS split), then the sole IR→argv boundary (glob, join) | internal — the entry points above |
| `expand_string_variables(text)` | `$`-constructs in flat text, no splitting/globbing/quote context | string contexts only (see table below) |

`WordExpander.expand_to_word` and `expand_assignment_value_word` **raise
`TypeError` on non-Word input** (audit 2026-06-12) — passing strings is a
bug, not a feature.

## Context-by-context

### 1. Command words (`SimpleCommand.words`)

```
lexer tokens (RichToken.parts)
  → RD:        CommandParser.parse_argument_as_word()
               [psh/parser/recursive_descent/parsers/commands.py]
               → WordBuilder.{build_word_from_token, build_composite_word,
                              parse_expansion_token}
               [psh/parser/recursive_descent/support/word_builder.py]
  → combinator: CommandParsers._build_simple_command()
               [psh/parser/combinators/commands.py]
               → ExpansionParsers.build_word_from_token()
               [psh/parser/combinators/expansions.py]
               (delegates RichToken decomposition + composite merging
                to the same WordBuilder)
  → SimpleCommand(words=[Word])               # words is the only store
  → CommandExecutor._execute_command()  [psh/executor/command.py]
  → ExpansionManager.expand_arguments()
  → WordExpander.expand_to_word(word, policy) + materialize per word
```

- **One source of truth**: `SimpleCommand` stores only `words`. The
  string view `args` is a **derived, read-only property**
  (`psh/ast_nodes/commands.py`): `[''.join(str(p) for p in w.parts) for w in words]`
  — pre-expansion bytes with quotes removed, expansions rendered as
  their `$`-source (a braced simple variable normalizes: `${y}` -> `$y`).
  Both parsers build `words` only; the executor slices `words` when
  stripping assignment prefixes (`command.py`, the `command_node`
  sub-node) and `args` follows automatically. Execution semantics never
  read `args` — only `words` through the expansion engine. The invariant
  (args == derived rule) is pinned permanently by
  `tests/unit/parser/test_args_derived_from_words.py`.
- **Declaration builtins** (`declare x=$v` etc.): recognized
  *syntactically* in `expand_arguments` via
  `is_declaration_builtin_command()` + `assignment_word_prefix()`
  (manager.py); only then does the DECLARATION_ASSIGNMENT policy
  suppress splitting/globbing of the value. Ordinary commands word-split
  `foo=$v` arguments (bash).
- Change quoting/splitting/globbing behavior → the field engine
  (`WordExpander.expand_to_word` and its helpers `_walk_literal_part` /
  `_walk_expansion_part` / `_FieldBuilder.splice` / `_field_split`, and the
  terminal `materialize` / `_glob_field`) in `psh/expansion/word_expander.py`.

### 2. Assignment values (`VAR=value`, `VAR=value cmd`)

```
SimpleCommand.words
  → CommandAssignments.extract()         # (var, raw, Word) triples
  → CommandAssignments.apply_pure / CommandAssignments.apply_prefix
  → CommandAssignments._expand_value(value, word)
        # raises if word=None; locates '=' in literal parts
  → ExpansionManager.expand_assignment_value_word(value Word)
```

(`CommandAssignments` lives in `psh/executor/command_assignments.py`;
`CommandExecutor` dispatches into it and owns only the WHEN — including
the POSIX special-builtin persistence decision and the
`last_cmdsub_status` clear. The module docstring states the ordering
contract.)

- The shared **assignment-value policy** lives ONLY in
  `expand_assignment_value_word()` (the scalar walker in
  word_expander.py; manager.py keeps the public delegate). It is used by scalar
  assignments, array element assignments, and explicit-index initializer
  entries — change value semantics (tilde-after-colon, escape handling,
  no-split) there and all three contexts follow.
- Assignment *candidacy* (is this word an assignment at all?) is
  `CommandAssignments._is_assignment_candidate()` — quoting any part of
  the name or `=` disqualifies (POSIX).
- `declare`/`export` arguments are NOT this path — they are ordinary
  command words with declaration-assignment expansion (see §1), and the
  builtin re-parses `name=value` itself.

### 3. Array initializers (`a=(...)`) and element assignments (`a[i]=v`)

Structure built by:
- RD: `ArrayParser` in `psh/parser/recursive_descent/parsers/arrays.py`
  (`_parse_array_initialization` fills `words` parallel to `elements`;
  `_parse_element_value` always builds `value_word`).
- Combinator: `psh/parser/combinators/special_commands.py`
  (`_build_array_initialization`, `_collect_element_value_word` — same
  guarantees).

Executed by `ArrayOperationExecutor` (`psh/executor/array.py`):

| Construct | Expansion |
|---|---|
| ordinary element `a=(x $v "q")` | `expand_word_to_fields(word, ARRAY_INIT_ELEMENT)` — full split/glob, no value-tilde |
| explicit `a=([i]=v)` / `a=([i]+=v)` | `_split_explicit_element(word)` recognizes UNQUOTED `[`...`]=`; index text → `expand_string_variables` + `evaluate_arithmetic`; value → `expand_assignment_value_word` |
| quoted `a=("[0]"=x)` | literal element (split helper rejects quoted brackets — bash parity, conformance-pinned) |
| assoc `h=([k]=v ...)` (declare -A) | keys and values via `expand_assignment_value_word`; bare elements alternate key/value via `expand_word_to_fields(word, ASSOC_INIT_ELEMENT)` (no split/glob; value-tilde pinned ON — see the policy's docstring) |
| element assignment `a[i]=v` | index: verbatim subscript string → `expand_string_variables` + arithmetic-or-string-key logic; value: `node.value_word` → `expand_assignment_value_word` (None raises) |

Declaration builtins use the SAME engine: `declare`/`typeset`/`local`/
`export`/`readonly` with a literal `name=(...)` argument no longer
string-reparse. The RD parser (`CommandParser._parse_array_initialization`
in `commands.py`) attaches a structured `ArrayInitialization` (element
Words with full quote context) to the argument `Word.array_init`, keeping
the flat literal text for `.args`/display. The executor (`command.py`
`_collect_array_inits`) hands these to the declaration builtin as an
explicit `BuiltinContext` parameter (threaded through `execute_builtin_guarded`
to `Builtin.execute_in_context`; no mutable handoff state on the shell), and
the builtin calls `ArrayOperationExecutor.build_indexed_array` /
`build_associative_array` — the shared value computation the bare path also
uses. The old serialize-then-shlex-reparse
module (the former psh/builtins/array_init.py) was DELETED; array-ification
now keys strictly on the parser having seen `name=(...)` syntax (a merely
paren-shaped value like `declare "a=(1 2)"` stays a scalar, matching bash).

### 4. for / select items

```
RD _parse_for_iterable() / combinator _build_loop_items()
  → ForLoop.item_words / SelectLoop.item_words   # parallel to .items
    (`for i; do` → one synthetic "$@" Word, items=['$@'])
  → ControlFlowExecutor._expand_loop_items()  [psh/executor/control_flow.py]
  → expand_word_to_fields(word, LOOP_ITEM)
```

`LOOP_ITEM` is a named alias of `COMMAND_ARGUMENT`: bash treats items
exactly like command arguments (it tilde-expands `for i in P=~/x`).
`item_words=None` (only possible in manually constructed ASTs — the field
is Optional by design) iterates `items` as literal fields; this is the
one deliberately-kept fallback, classification (a) in the 2026-06-12
audit.

### 5. Case subject and patterns

- **Subject**: `CaseConditional.expr` is a flat string (AST design);
  expanded with `expand_string_variables` in
  `ControlFlowExecutor.execute_case`.
- **Patterns**: `CasePattern.word` (built by RD `_parse_case_pattern` and
  combinator `_make_case_pattern`) → `expand_word_as_pattern()` — quoted
  text matches literally, unquoted keeps glob power. Matching itself is
  `expansion/pattern.py` (`match_shell_pattern`, a thin facade over the ONE
  compiled pattern engine `pattern_engine.py`; extglob-aware, NO regex
  path — campaign W3).
- `CasePattern.word=None` falls back to expanding the flat
  `pattern` string — classification (b), a combinator-parser bridge
  (it emits None when `build_word_from_token` rejects the pattern token).

### 6. Redirect targets, heredocs, here-strings

`Redirect` (`psh/ast_nodes/redirects.py`) stores `target` as a **string** plus
`quote_type` / `heredoc_quoted` metadata — there is no Word here. All
expansion happens at apply time in `psh/io_redirect/file_redirect.py`:

| Form | Where | Expansion |
|---|---|---|
| `> file`, `< file`, `<>`, `>|`, `&>` | `expand_redirect_target()` | `expand_string_variables` (skipped if single-quoted) + tilde |
| `<<EOF` body | `redirect_heredoc()` | `expand_string_variables` unless `heredoc_quoted` |
| `<<<word` | `redirect_herestring()` | `expand_string_variables` unless single-quoted |
| `>&$fd` (dynamic dup) | `resolve_dynamic_dup()` | `expand_string_variables`, must yield an integer |

These are the canonical string-context uses of
`expand_string_variables` — do not "migrate" them to Words without
migrating the `Redirect` node itself.

### 7. Process substitution `<(cmd)` / `>(cmd)`

`ProcessSubstitution` is an `Expansion` (`psh/ast_nodes/words.py`), so it appears as
an ordinary `ExpansionPart` inside a Word — whole-word and embedded
(`pre<(cmd)post`) forms are the same shape.

> **Nested Program**: `ProcessSubstitution` and `CommandSubstitution` carry
> `program` (the body parsed into a `Program` at the OUTER parse by
> `WordBuilder`, via `recursive_descent/support/nested_parse.py`) plus `source`
> (the raw inner text). Invalid nested syntax is therefore rejected during the
> outer parse, and analysis visitors descend into `program`. EXECUTION still
> uses `source` (re-parsed against the runtime alias table), mirroring bash's
> read-time-validate / expansion-time-execute double parse; backticks keep
> `program=None`. See `psh/parser/CLAUDE.md` "Nested command/process
> substitutions carry a parsed Program" for the full contract and divergences.

Performed during Word expansion:

- command words: `WordExpander._walk_expansion_part` handles the part type directly →
  `IOManager.create_process_substitution_for_expansion()` →
  `ProcessSubstitutionHandler` (`psh/io_redirect/process_sub.py`) — forks
  the child (its body runs through `run_child_shell` in
  `executor/child_policy.py`), returns the `/dev/fd/N` path spliced into
  the word.
- assignment values: `expand_assignment_value_word` handles the part type
  directly (same IOManager call).
- case patterns: NOT performed — `expand_word_as_pattern` keeps the
  literal `<(cmd)` text.

**Ownership/cleanup**: `CommandExecutor.execute()` wraps every simple
command in `IOManager.process_sub_scope()` (`psh/io_redirect/manager.py`)
— on exit it closes the parent-side fds registered inside the scope and
reaps children (`WNOHANG`; still-running ones re-polled later). Scopes
nest. Never close these fds in builtin-redirect restore.

### 8. Compound-command redirects (visitor totality)

Every compound node (`IfConditional`, `WhileLoop`, `UntilLoop`,
`ForLoop`, `CStyleForLoop`, `SelectLoop`, `CaseConditional`,
`SubshellGroup`, `BraceGroup`, `FunctionDef` bodies,
`ArithmeticEvaluation`, `EnhancedTestStatement`) carries a
`redirects: List[Redirect]` field; executors apply it with
`io_manager.with_redirections(node.redirects)` around the body.

Totality is enforced mechanically:
`tests/unit/visitor/test_ast_coverage_matrix.py` introspects the AST for
every redirect-carrying node class and asserts (a) each visitor handles
the node and (b) analysis visitors (e.g. `SecurityVisitor`) inspect its
redirects, using real parsed source per node class. Adding a new
redirect-carrying node without visitor support fails that matrix.

## Quick reference: "I want to change..."

| Behavior | Change here |
|---|---|
| quoting/IFS/glob of command args | `WordExpander.expand_to_word` + `materialize` (expansion/word_expander.py) |
| what a context permits (split/glob/value-tilde) | the named `WordExpansionPolicy` table (expansion/word_expander.py) |
| assignment-value semantics (all contexts) | `expand_assignment_value_word` (expansion/word_expander.py) |
| declaration-builtin recognition | `is_declaration_builtin_command` / `assignment_word_prefix` (manager.py) |
| array initializer element handling | `ArrayOperationExecutor.execute_array_initialization` (executor/array.py) |
| explicit `[i]=v` recognition | `_split_explicit_element` (executor/array.py) |
| for/select item expansion | `_expand_loop_items` (executor/control_flow.py) |
| case pattern matching | `expand_word_as_pattern` (manager.py) + `expansion/pattern.py` |
| redirect target/heredoc expansion | `FileRedirector` helpers (io_redirect/file_redirect.py) |
| process substitution mechanics | `ProcessSubstitutionHandler` (io_redirect/process_sub.py); scope: `process_sub_scope` (io_redirect/manager.py) |
| token → Word construction | `WordBuilder` (parser/recursive_descent/support/word_builder.py); combinator wrapper: parser/combinators/expansions.py |
| `$(...)` extent scanning | `find_command_substitution_end` (lexer/cmdsub_scanner.py — see its Maintenance contract docstring) |
