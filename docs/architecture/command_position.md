# Command Position: the three tracking machines

"Command position" is the start of a simple command — the spot where a reserved
word like `if` or `while` is recognized as a **keyword** (not an argument), and
where the lexer enables operators like `[[`. In bash and PSH alike, the same
characters mean different things depending on whether they sit at command
position:

```
echo if          # "if" is an ARGUMENT  → printed literally
if true; ...     # "if" is a KEYWORD    → starts a conditional
```

So something has to track "are we at command position right now?" as it walks
the input. In PSH **three** machines do, at three different pipeline stages over
three different alphabets. This document is the map of how they relate. The
shared vocabulary they all consult lives in one file,
[`psh/lexer/command_position.py`](../../psh/lexer/command_position.py); the
relationships below are drift-locked by
`tests/unit/lexer/test_command_position_consistency.py`.

## Why three, and where each runs

They are not duplicates — each runs at a stage where the others' information is
not yet (or no longer) available:

```
 raw source text
      │
      │   ┌──────────────────────────────────────────────────────────────┐
      │   │ (1) cmdsub extent scanner   — RAW TEXT, no tokens yet          │
      ├──▶│     find_command_substitution_end()                            │
      │   │     Only runs to find where  $( ... )  ends. Needs command     │
      │   │     position just to recognize `case` (whose patterns hold     │
      │   │     unmatched `)`), so `$(case x in x) echo;; esac)` delimits. │
      │   └──────────────────────────────────────────────────────────────┘
      ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │ ModularLexer.tokenize()                                                   │
 │   (2) lexer pass — TOKEN TYPES + WORD VALUES, during tokenization         │
 │       _update_command_position_context()                                  │
 │       Keywords are still plain WORD tokens here, so it matches keyword    │
 │       *values*. Drives operator recognition (e.g. enable `[[`).           │
 └─────────────────────────────────────────────────────────────────────────┘
      ▼
   token stream
      ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │ KeywordNormalizer.normalize()                                             │
 │   (3) normalizer — TOKEN TYPES, post-tokenization                         │
 │       _next_command_position()                                            │
 │       Promotes reserved WORDs to keyword token TYPES at command position. │
 └─────────────────────────────────────────────────────────────────────────┘
      ▼
   normalized tokens → parser
```

Different stage ⇒ different alphabet: the scanner sees **raw word strings**, the
lexer pass sees **token types plus WORD values** (keywords aren't typed yet),
and the normalizer sees **token types** (keywords now carry their own type). A
single unified machine is intentionally not extracted — the per-stage
differences below are irreducible — but the *vocabulary* is centralized so the
three cannot silently drift apart.

## Transition tables

Each machine answers one question per token/word: **is the _next_ position a
command position?** "set" = becomes command position; "keep" = unchanged;
"reset" = becomes non-command.

### (1) cmdsub extent scanner — `cmdsub_scanner._handle_word`

Alphabet: raw word strings. It only tracks position finely enough to find
`case`.

| Input (raw text) | Next position |
|------------------|---------------|
| statement separators / group openers (`;` `\n` `\|` `&` `(` `{` …) | **set** |
| a *pure* word in `CMDPOS_KEEPING_WORDS` **and** already at command position | **keep** |
| `case` / `esac` / `in` | drive the case state machine, then **reset** |
| any other word | **reset** |

`CMDPOS_KEEPING_WORDS` = `if then else elif fi while until do done { } ! time coproc`.

### (2) lexer pass — `ModularLexer._update_command_position_context`

Alphabet: token types + WORD values (keywords are still `WORD`).

| Input | Next position |
|-------|---------------|
| `STATEMENT_SEPARATORS` (`;` `\n` `&&` `\|\|` `\|`) | **set** |
| `COMMAND_GROUP_OPENERS` (`(` `{`) | **set** |
| `WORD` whose value ∈ `LEXER_COMMAND_POSITION_WORDS` | **set** |
| redirection operators (`<` `>` `>>` `<<` `<<-` `<<<`) — *neutral* | **keep** |
| anything else (a command word, an argument, …) | **reset** |

`LEXER_COMMAND_POSITION_WORDS` = `if while until for case then do else elif`.
(Case nesting, `[[ ]]` depth, and `$(( ))` depth are tracked by separate
counters on `LexerContext`, not by this flag.)

### (3) keyword normalizer — `KeywordNormalizer._next_command_position`

Alphabet: token types (keywords are now typed).

| Input | Next position |
|-------|---------------|
| `STATEMENT_SEPARATORS` ∪ `CASE_TERMINATORS` (`;` `\n` `&&` `\|\|` `\|` `;;` `;&` `&;`) | **command** |
| `RESET_TO_COMMAND_POSITION` (`then` `do` `else` `elif` `fi` `done` `esac` `))` `]]`) | **command** |
| `if` `while` `until` (condition is itself a command list) | **command** |
| `(` `{`, and `)` (closing a case pattern) | **command** |
| `in` with a pending `for`/`case` | **not** |
| `for` `select` `case` `function` (next token is the var / subject / name) | **not** |
| anything else (an ordinary word/argument) | **not** |

## The deliberate asymmetries (the point of the map)

The three sets differ on purpose. This table shows where, and why — it is the
thing the review asked to make visible:

| Word / token | (1) scanner | (2) lexer pass | (3) normalizer | Why it differs |
|--------------|:----------:|:--------------:|:--------------:|----------------|
| `then do else elif` | keep | set | command | all three return to command position |
| openers `if while until` | — | set | command | (2) needs `while [[ -f x ]]` to enable `[[` right after the keyword |
| openers `for case` | drive case sm | set | **not** | (3) keeps the *next* token a word (the loop var / case subject), not a keyword |
| closers `fi done esac` | keep | **omitted** | command | in valid syntax a closer is followed by a separator (which resets anyway); (2) never needs them, and the omission only shows in already-invalid input (`fi [[`) |
| `]]` `))` | — | depth counters | command | (3) must promote a `then`/`do` that follows a condition header directly: `if ((1)) then …`, `if [[ a = a ]] then …` |
| `{ } ! time coproc` | keep | `{` only | `{` only | (1) sees these as raw text and needs them to keep position for `{ case …`; (2)/(3) handle `{` structurally and never see the others as position words |

## Worked examples

- **`while [[ -f x ]]; do …`** — the lexer pass (2) sees `while` (a
  `LEXER_COMMAND_POSITION_WORD`) → command position → so the very next `[[` is
  recognized as the `DOUBLE_LBRACKET` operator, not a literal word.

- **`if ((1)) then echo y; fi`** (no separator before `then`) — the normalizer
  (3) sees `))` (`DOUBLE_RPAREN` ∈ `RESET_TO_COMMAND_POSITION`) → command
  position → so the following `then` is promoted to the `THEN` keyword.

- **`echo if then`** — after `echo` (an ordinary word) neither (2) nor (3) is at
  command position, so `if` and `then` stay plain `WORD`s (arguments), exactly
  like bash.

- **`$(case x in x) echo hi;; esac)`** — the scanner (1) must not stop at the
  first `)`. It recognizes `case` only at command position, then its case state
  machine consumes the unmatched `)` per pattern, so the `$( … )` extent ends at
  the correct closing paren after `esac`.

## Source map

| Stage | Code | Vocabulary it consults |
|-------|------|------------------------|
| (1) scanner | `psh/lexer/cmdsub_scanner.py` (`find_command_substitution_end`) | `CMDPOS_KEEPING_WORDS` |
| (2) lexer pass | `psh/lexer/modular_lexer.py` (`ModularLexer._update_command_position_context`) | `STATEMENT_SEPARATORS`, `COMMAND_GROUP_OPENERS`, `LEXER_COMMAND_POSITION_WORDS` |
| (3) normalizer | `psh/lexer/keyword_normalizer.py` (`KeywordNormalizer._next_command_position`) | `STATEMENT_SEPARATORS`, `CASE_TERMINATORS`, `RESET_TO_COMMAND_POSITION` |
| shared vocabulary | `psh/lexer/command_position.py` | — |
| drift lock | `tests/unit/lexer/test_command_position_consistency.py` | asserts the set relationships above |
