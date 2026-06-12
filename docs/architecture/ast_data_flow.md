# Canonical AST Data Flow: Words, Values, and Redirects

**Audience**: anyone changing expansion or execution semantics. This
document answers "which code do I change?" for each context where shell
text becomes runtime values. Every claim was verified against the source
on 2026-06-12 (fallback audit; see
`docs/reviews/code_quality_subsystem_reassessment_2026-06-12.md` §2 and
`tests/unit/executor/test_legacy_ast_fallbacks.py`).

Two representations exist, by design:

1. **Word AST** (`psh/ast_nodes.py`: `Word`, `LiteralPart`,
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

All Word expansion funnels into `psh/expansion/manager.py`:

| Entry point | Policy | Callers |
|---|---|---|
| `expand_arguments(command)` → `_expand_word_ast_arguments()` | full command-argument pipeline; detects declaration builtins | `CommandExecutor._expand_arguments` |
| `expand_word_to_fields(word, assignment_tilde=, suppress_split_glob=)` | same pipeline, one Word → 0..n fields | for/select items, array initializer elements |
| `expand_assignment_value_word(word)` | bash assignment-value policy: all expansions, NO splitting, NO globbing, tilde after `=`/`:` | scalar assignment values, array element values, assoc-array keys |
| `expand_word_as_pattern(word)` | quoted parts glob-escaped (match literally), unquoted parts keep glob power | case patterns |
| `_expand_word(word, ...)` | the core walker (quote dispatch, per-part expansion, IFS split, glob) | internal — the three methods above |
| `expand_string_variables(text)` | `$`-constructs in flat text, no splitting/globbing/quote context | string contexts only (see table below) |

`_expand_word` and `expand_assignment_value_word` **raise `TypeError` on
non-Word input** (audit 2026-06-12) — passing strings is a bug, not a
feature.

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
  → SimpleCommand(args=[str], words=[Word])   # ALWAYS parallel lists
  → CommandExecutor._execute_command()  [psh/executor/command.py]
  → ExpansionManager.expand_arguments() → _expand_word() per word
```

- **Invariant**: `words` parallels `args` index-for-index in both parsers
  (RD `_parse_command_elements` appends in lockstep; combinator builds
  both per token group). The executor slices both together when stripping
  assignment prefixes (`command.py`, the `command_node` sub-node).
- **Declaration builtins** (`declare x=$v` etc.): recognized
  *syntactically* in `expand_arguments` via
  `is_declaration_builtin_command()` + `assignment_word_prefix()`
  (manager.py); only then does `_expand_word(declaration_assignment=True)`
  suppress splitting/globbing of the value. Ordinary commands word-split
  `foo=$v` arguments (bash).
- Change quoting/splitting/globbing behavior → `_expand_word` and its
  helpers (`_split_part_fields`, `_glob_words`,
  `_expand_at_with_affixes`) in `psh/expansion/manager.py`.

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
  `expand_assignment_value_word()` (manager.py). It is used by scalar
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
| ordinary element `a=(x $v "q")` | `expand_word_to_fields(word)` — full split/glob, like command args |
| explicit `a=([i]=v)` / `a=([i]+=v)` | `_split_explicit_element(word)` recognizes UNQUOTED `[`...`]=`; index text → `expand_string_variables` + `evaluate_arithmetic`; value → `expand_assignment_value_word` |
| quoted `a=("[0]"=x)` | literal element (split helper rejects quoted brackets — bash parity, conformance-pinned) |
| assoc `h=([k]=v ...)` (declare -A) | keys and values via `expand_assignment_value_word`; bare elements alternate key/value via `expand_word_to_fields(suppress_split_glob=True)` |
| element assignment `a[i]=v` | index: string/token list → `expand_string_variables` + arithmetic-or-string-key logic; value: `node.value_word` → `expand_assignment_value_word` (None raises) |

Separate path: `declare a=(...)` / `local a=(...)` receive the
initializer as ONE string argument; `psh/builtins/array_init.py`
re-parses and expands it with `expand_string_variables` (a legitimate
string context — there is no Word AST for builtin argument internals).

### 4. for / select items

```
RD _parse_for_iterable() / combinator _build_loop_items()
  → ForLoop.item_words / SelectLoop.item_words   # parallel to .items
    (`for i; do` → one synthetic "$@" Word, items=['$@'])
  → ControlFlowExecutor._expand_loop_items()  [psh/executor/control_flow.py]
  → expand_word_to_fields(word, assignment_tilde=True)
```

`assignment_tilde=True` because bash tilde-expands `for i in P=~/x`.
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
  `expansion/pattern.py` (`match_shell_pattern`, the single
  pattern-to-regex engine, extglob-aware).
- `CasePattern.word=None` falls back to expanding the flat
  `pattern` string — classification (b), a combinator-parser bridge
  (it emits None when `build_word_from_token` rejects the pattern token).

### 6. Redirect targets, heredocs, here-strings

`Redirect` (ast_nodes.py) stores `target` as a **string** plus
`quote_type` / `heredoc_quoted` metadata — there is no Word here. All
expansion happens at apply time in `psh/io_redirect/file_redirect.py`:

| Form | Where | Expansion |
|---|---|---|
| `> file`, `< file`, `<>`, `>|`, `&>` | `_expand_redirect_target()` | `expand_string_variables` (skipped if single-quoted) + tilde |
| `<<EOF` body | `_redirect_heredoc()` | `expand_string_variables` unless `heredoc_quoted` |
| `<<<word` | `_redirect_herestring()` | `expand_string_variables` unless single-quoted |
| `>&$fd` (dynamic dup) | `_resolved()` | `expand_string_variables`, must yield an integer |

These are the canonical string-context uses of
`expand_string_variables` — do not "migrate" them to Words without
migrating the `Redirect` node itself.

### 7. Process substitution `<(cmd)` / `>(cmd)`

`ProcessSubstitution` is an `Expansion` (ast_nodes.py), so it appears as
an ordinary `ExpansionPart` inside a Word — whole-word and embedded
(`pre<(cmd)post`) forms are the same shape. Performed during Word
expansion:

- command words: `_expand_word` →
  `ExpansionEvaluator._evaluate_process_substitution`
  (`psh/expansion/evaluator.py`) →
  `IOManager.create_process_substitution_for_expansion()` →
  `ProcessSubstitutionHandler` (`psh/io_redirect/process_sub.py`) — forks
  the child, returns the `/dev/fd/N` path spliced into the word.
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
| quoting/IFS/glob of command args | `ExpansionManager._expand_word` + helpers (manager.py) |
| assignment-value semantics (all contexts) | `expand_assignment_value_word` (manager.py) |
| declaration-builtin recognition | `is_declaration_builtin_command` / `assignment_word_prefix` (manager.py) |
| array initializer element handling | `ArrayOperationExecutor.execute_array_initialization` (executor/array.py) |
| explicit `[i]=v` recognition | `_split_explicit_element` (executor/array.py) |
| for/select item expansion | `_expand_loop_items` (executor/control_flow.py) |
| case pattern matching | `expand_word_as_pattern` (manager.py) + `expansion/pattern.py` |
| redirect target/heredoc expansion | `FileRedirector` helpers (io_redirect/file_redirect.py) |
| process substitution mechanics | `ProcessSubstitutionHandler` (io_redirect/process_sub.py); scope: `process_sub_scope` (io_redirect/manager.py) |
| token → Word construction | `WordBuilder` (parser/recursive_descent/support/word_builder.py); combinator wrapper: parser/combinators/expansions.py |
| `$(...)` extent scanning | `find_command_substitution_end` (lexer/pure_helpers.py — see its Maintenance contract docstring) |
