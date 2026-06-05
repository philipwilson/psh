# Lexer Token Set Appraisal

**Date**: 2026-02-19 (revised post-v0.192.0)
**Version**: 0.192.0

Assessment of PSH's `TokenType` enum (62 entries) compared to the POSIX
shell grammar and bash internals, with an audit of remaining parser
workarounds.

---

## Token count comparison

| Shell | Lexical token types | Word-internal markers | Total |
|-------|--------------------|-----------------------|-------|
| POSIX | ~38 | 0 | ~38 |
| bash | ~47 | ~5 escape markers | ~52 |
| PSH | 62 | 0 (uses separate token types instead) | 62 |
| zsh | 64 | 31 character tokens | 95 |

PSH has **more lexical token types than bash**, which is the wrong
direction for a shell claiming POSIX focus. The reason is structural.
zsh has even more lexical types (64), but its extra count comes from
richer redirection and keyword coverage, not from expansion types — zsh
keeps all expansion structure inside word strings via character tokens.

---

## The core design difference: expansion tokens

The biggest divergence from POSIX, bash, and zsh is that PSH gives each
expansion form its own token type:

| PSH token type | bash equivalent | zsh equivalent |
|---|---|---|
| `STRING` | `WORD` with `W_QUOTED` flag | `STRING` with `Dnull`/`Snull` char tokens |
| `VARIABLE` | Part of `WORD` (internal marker) | Part of `STRING` (`\x85` char token) |
| `COMMAND_SUB` | Part of `WORD` | Part of `STRING` (`\x85` + `\x88`…`\x8a`) |
| `COMMAND_SUB_BACKTICK` | Part of `WORD` | Part of `STRING` (`\x93` char token) |
| `ARITH_EXPANSION` | Part of `WORD` | Part of `STRING` (`\x85` + `\x89`…`\x8b`) |
| `PARAM_EXPANSION` | Part of `WORD` | Part of `STRING` (`\x85` + `\x8f`…`\x90`) |
| `PROCESS_SUB_IN` | Part of `WORD` | Part of `STRING` |
| `PROCESS_SUB_OUT` | Part of `WORD` | Part of `STRING` |
| `COMPOSITE` | Not needed | Not needed |

That's **9 token types** that both bash and zsh represent as a single
word token with internal structure. In bash, `"hello $USER $(date)"` is
one `WORD` token whose `word->word` string contains the full text and
whose `word->flags` carry metadata. In zsh, it is one `STRING` token
with embedded character tokens (`\x9e`, `\x85`, `\x88`…`\x8a`, `\x9e`)
that the expansion phase interprets. Both keep expansions *inside* the
word.

PSH's approach means the lexer emits separate tokens for each piece of
`"hello $USER"`, then the parser must reassemble them. This creates a
cascade of complexity:

- **`COMPOSITE`** type exists solely to merge adjacent tokens back together
- **`adjacent_to_previous`** flag on every token to detect composite sequences
- **`WORD_LIKE`** set (13 members) checked everywhere the grammar says "word"
- **`WordBuilder`** in the parser to reconstruct `Word` AST nodes from
  scattered tokens
- **`peek_composite_sequence()`** lookahead in the parser

This isn't wrong — it gives the parser richer structural information than
bash or zsh have. But it moves word-internal structure from the expansion
phase into the token type system, and that makes the grammar more complex
than it needs to be.

---

## Token types PSH has that bash doesn't

| PSH type | Issue |
|---|---|
| `LBRACKET` / `RBRACKET` | Bash doesn't tokenize `[`/`]` — `[` is just a command name (the `test` builtin). PSH making it a token type creates ambiguity (glob vs test) that the lexer must resolve contextually. |
| `REGEX_MATCH` / `EQUAL` / `NOT_EQUAL` | In bash, `=~`, `==`, `!=` are handled inside a recursive descent sub-parser for `[[ ]]` that lives *inside the lexer*. The grammar only sees `COND_START COND_CMD COND_END`. PSH exposes these as grammar-level tokens. |
| `BREAK` / `CONTINUE` / `RETURN` | These are **builtins** in bash, not reserved words. They don't get keyword token types. Making them keywords means they can't be used as function names, which differs from bash. |
| `DOUBLE_LPAREN` / `DOUBLE_RPAREN` | Bash's lexer handles `(( ))` internally and emits `ARITH_CMD` — the grammar never sees the parens. PSH exposes them. |
| `DOUBLE_LBRACKET` / `DOUBLE_RBRACKET` | Same — bash emits `COND_START`/`COND_END` but pre-parses the contents. |

---

## Token types bash has that PSH doesn't

| bash type | What it does |
|---|---|
| `ASSIGNMENT_WORD` | `VAR=value` as a distinct token type. PSH removed this as "dead" but the parser still inspects WORD values with `.endswith('=')` checks. |
| `NUMBER` (= POSIX `IO_NUMBER`) | PSH now uses `token.fd` metadata, which is arguably cleaner. |
| `LESSGREAT` (`<>`) | Open file for reading and writing. PSH uses `REDIRECT_READWRITE` (added v0.192.0). |
| `GREATER_BAR` (`>\|`) | `noclobber` override. PSH uses `REDIRECT_CLOBBER` (added v0.192.0). |
| `LESS_AND` / `GREATER_AND` | `<&` and `>&` as separate operators. PSH combines these into `REDIRECT_DUP`. |
| `AND_GREATER` / `AND_GREATER_GREATER` | `&>` and `&>>`. PSH reuses `REDIRECT_OUT` / `REDIRECT_APPEND` with `combined_redirect=True` flag on the token (added v0.192.0). |
| `BAR_AND` | `\|&`. PSH uses `PIPE_AND` (added v0.192.0). |
| `ARITH_CMD` / `COND_CMD` | Pre-parsed compound constructs. Bash's lexer contains recursive descent sub-parsers for `(( ))` and `[[ ]]` and delivers the *entire parsed result* as a single token to the yacc grammar. |

---

## zsh's two-level token architecture

zsh (64 lexical tokens, 31 character tokens) uses a fully hand-written
lexer and recursive descent parser — no yacc/bison. Its approach is
distinct from both bash and PSH.

**Level 1 — Lexical tokens (64 types):** Structural elements only —
operators, separators, keywords, and three word types (`STRING`,
`ENVSTRING`, `ENVARRAY`). No expansion types, no quote types, no glob
types at the lexical level.

**Level 2 — Character tokens (31 types):** Special bytes embedded
*inside* word strings. `$VAR` becomes `\x85VAR`. `"hello"` becomes
`\x9ehello\x9e`. `*` becomes `\x87`. These are escape markers within
the `STRING` token's value, not separate tokens. The expansion phase
reads them to know what to expand.

This means zsh's grammar only sees three word-like token types while
preserving full structural information about expansions, quotes, and
globs inside the word string.

### How each shell handles key cases

| Feature | bash | zsh | PSH |
|---------|------|-----|-----|
| `$VAR` in a word | Part of `WORD` (escape markers) | Part of `STRING` (char token `\x85`) | Separate `VARIABLE` token type |
| `$(cmd)` | Part of `WORD` | Part of `STRING` (recursive parser call) | Separate `COMMAND_SUB` token type |
| `"quoted"` | `WORD` with `W_QUOTED` flag | `STRING` with `Dnull` char tokens | Separate `STRING` token type |
| `VAR=val` | `ASSIGNMENT_WORD` | `ENVSTRING` | `WORD` (parser inspects value) |
| `VAR=(a b)` | `ASSIGNMENT_WORD` + parser logic | `ENVARRAY` | `WORD` (parser inspects value) |
| fd prefix `2>` | Separate `NUMBER` token | Same `OUTANG`, fd in `tokfd` var | Same `REDIRECT_OUT`, fd in `token.fd` |
| Keywords | Recognized inline in lexer | `STRING` promoted by `exalias()` | `WORD` promoted by `KeywordNormalizer` |
| `[[ ]]` | Lexer sub-parser → `COND_CMD` | `DINBRACK`/`DOUTBRACK`, parser handles | `DOUBLE_LBRACKET`/`DOUBLE_RBRACKET` + exposed operators |
| `(( ))` | Lexer sub-parser → `ARITH_CMD` | `DINPAR`/`DOUTPAR`, expression as string | `DOUBLE_LPAREN`/`DOUBLE_RPAREN`, parser handles |
| Globs `*?[` | Part of `WORD` | Part of `STRING` (char tokens) | Part of `WORD` |
| `>|` (clobber) | `GREATER_BAR` | `OUTANGBANG` | `REDIRECT_CLOBBER` |
| `<>` (read/write) | `LESSGREAT` | `INOUTANG` | `REDIRECT_READWRITE` |
| `&>` (stderr shortcut) | `AND_GREATER` | `AMPOUTANG` | `REDIRECT_OUT` + `combined_redirect` flag |
| `&>>` (stderr append) | `AND_GREATER_GREATER` | — | `REDIRECT_APPEND` + `combined_redirect` flag |
| `\|&` (pipe stderr) | `BAR_AND` | `AMPPER` | `PIPE_AND` |

### Notable zsh design choices

- **`ENVSTRING` / `ENVARRAY`**: Two assignment token types (scalar vs
  array) detected during word scanning. PSH removed `ASSIGNMENT_WORD`
  as dead but still does `.endswith('=')` inspection in the parser. zsh
  shows that lexer-level assignment detection can be clean.

- **`TYPESET` shared token**: Seven declaration builtins (`typeset`,
  `declare`, `export`, `local`, `float`, `integer`, `readonly`) all map
  to one token type, telling the parser to enter a special
  argument-parsing mode. PSH treats these as regular builtins.

- **15 redirection operators** (vs bash's ~10, PSH's 12): zsh includes
  `>|`, `>>|`, `&>`, `&>|`, `>>&`, `>>&|`, `<<<`, and `|&` natively.
  PSH now covers the core set (`<>`, `>|`, `&>`, `&>>`, `|&`) but not
  zsh's extended variants (`>>|`, `&>|`, `>>&`, `>>&|`).

- **fd-prefix approach matches PSH**: Both store the fd as metadata on
  the redirect token rather than emitting a separate `IO_NUMBER` token.

- **Keyword normalization mirrors PSH**: Both use a post-lex promotion
  step (`exalias()` in zsh, `KeywordNormalizer` in PSH). Bash does it
  inline.

- **Word code IR**: zsh's parser emits a compact bytecode array (22
  word code types) instead of an AST tree. This reduces memory allocation
  and allows function bodies to be memory-mapped from disk.

---

## The KeywordNormalizer situation

Both POSIX and bash do keyword recognition *inside* the lexer, not as a
post-pass. POSIX specifies a context-sensitive two-phase process (Rules
1-9 in Section 2.10.2). Bash uses
`reserved_word_acceptable(last_read_token)` to check if the previous
token allows a keyword at this position.

PSH's `KeywordNormalizer` exists as a separate post-lexer pass because
the modular recognizer architecture doesn't easily feed parser state back
into the lexer. This is a known cost of the modular design — it's an
extra traversal of the token list, and it means the lexer doesn't have a
single authoritative token-producing pipeline.

That said, moving it *into* the lexer would mean the lexer needs to track
command position, heredoc state, `for/in` context, and case pattern
state — which is exactly what the normalizer tracks. So the work is the
same; it's just a question of where it lives. The current design is
defensible for an educational codebase.

---

## Parser workarounds: what's appropriate vs what isn't

**Appropriate parser-level work** (shouldn't move to lexer):
- Test operator classification (`-f`, `-eq`, etc.) — these are semantic,
  context-dependent
- Function definition detection (lookahead for `name()`) — structural
  pattern
- Array assignment validation — complex structural analysis
- Loop control level parsing (`break 2`) — trivial parser concern

**Genuinely duplicated work** (lexer should be authoritative):
- **fd-duplication regex** in the parser (`_FD_DUP_RE` in `commands.py`)
  — the lexer already has `_parse_fd_duplication()` but the parser has a
  fallback for cases that slip through as WORD tokens. One should be
  authoritative.
- **Unclosed expansion detection** in the parser — the lexer should mark
  these as error tokens during tokenization, not leave it for the parser
  to inspect `token.parts` for `_unclosed` suffixes.

**Design-level concerns** (not bugs, but structural costs):
- `ASSIGNMENT_WORD` was removed as dead, but the parser still does
  `.endswith('=')` string inspection on WORD values in multiple places.
  Either the token type should exist and the lexer should emit it, or the
  parser should own it cleanly with a helper — currently it's ad-hoc.

---

## Verdict

**Is the current token set good enough?** It's functional and
well-organized after the cleanup. The dead types are gone, the fd
metadata is cleaner than POSIX's `IO_NUMBER` approach.

**Would it be a good starting point for a fresh shell?** No, not as-is.
The fundamental issue is the expansion-tokens-as-separate-types design.
If PSH adopted the bash/zsh "expansions inside words" approach, its
token count would drop from 62 to roughly 53 (removing `STRING`,
`VARIABLE`, `COMMAND_SUB`, `COMMAND_SUB_BACKTICK`, `ARITH_EXPANSION`,
`PARAM_EXPANSION`, `PROCESS_SUB_IN`, `PROCESS_SUB_OUT`, `COMPOSITE` and
adding back a single word-with-content type). That would put it between
bash (~47) and zsh (64), which is where an educational bash-compatible
shell should sit.

A fresh shell should choose one of:

1. **Bash's approach**: Expansions are internal to WORD tokens. The lexer
   produces `WORD` tokens with internal markers. This keeps the token
   type count low (~40-47) and the grammar simple. The expansion phase
   handles all the complexity.

2. **Zsh's approach**: Expansions are embedded in word strings via
   character tokens (special bytes). Richer than bash's markers, still
   keeps the grammar simple (only 3 word-like token types). The lexer
   recursively invokes the parser for `$(...)`.

3. **PSH's current approach**: Expansions are separate token types. This
   gives the parser richer information but requires `COMPOSITE`,
   `adjacent_to_previous`, `WORD_LIKE`, and `WordBuilder` machinery to
   reassemble words.

4. **Oil/Oils approach**: Four distinct lexer modes for
   command/word/arith/bool sublanguages, with explicit mode switching.
   Most principled but most complex.

For a fresh implementation, approach 1 is simplest and best-proven.
Approach 2 is more expressive. PSH chose approach 3, which makes sense
for education (you can *see* each expansion as a distinct token in
`--debug-tokens`), but it's not what you'd pick for production.

**Is there still too much work in the parsers?** The remaining parser
workarounds are mostly appropriate. The two genuine issues (fd-dup
fallback regex, unclosed expansion detection) are minor. The bigger cost
is structural — the `WORD_LIKE` set and `WordBuilder` exist because of
the expansion token design, and that won't change without a fundamental
redesign.

**Redirection operator coverage** is now solid. As of v0.192.0, PSH
supports `<>`, `>|`, `&>`, `&>>`, and `|&` — matching bash's full set.
zsh's extended variants (`>>|`, `&>|`, `>>&`, `>>&|`) remain unsupported
but are rarely used in practice.
