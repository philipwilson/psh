# PSH Codebase Study (2026-06-05) — Phase 1: Correctness & Conformance

## Scope and conformance baseline

The curated conformance framework reports a strong baseline:

- **POSIX:** 100% (127/127)
- **bash:** 98.2% (109/111)

This phase probed **beyond** that curated suite — exercising quoting/word-splitting, arithmetic, brace expansion, globbing, parameter expansion, and heredoc/redirection edge cases against bash (primary reference) and zsh (corroborating). Every finding below was reproduced in `/Users/pwilson/src/psh` with exact commands and compared against `bash -c`.

## Summary table — findings by verdict and severity

| Verdict | High | Medium | Low | Total |
|---|---|---|---|---|
| **Confirmed bugs** (`real-bug`) | 8 | 9 | 6 | 23 |
| **Intentional but undocumented** (`intentional-undocumented`) | 1 | 0 | 0 | 1 |
| **Intentional & documented** (`intentional-documented`) | 2 | 1 | 1 | 4 |
| **Totals** | 11 | 10 | 7 | 28 |

The 23 `real-bug` findings are undocumented divergences from bash (psh's stated reference); most contradict the user guide's own claims of "full support." The single `intentional-undocumented` item (`${var@Q}` transforms) is acknowledged only in the roadmap, not the user-facing docs. The 4 `intentional-documented` items are correct-as-designed gaps disclosed in `docs/user_guide/`.

---

## Confirmed bugs

Sorted high → low severity. All reproduced; none documented (unless noted).

### HIGH severity

#### 1. Unquoted expansion of empty/unset variable produces a spurious empty field

- **Reproducer:** `set -- $emptyvar; echo "count=$#"`
- **psh:** `count=1` — **bash:** `count=0`
- Corroborating: `set -- $emptyvar foo; echo "count=$# first=[$1]"` → psh `count=2 first=[]`, bash `count=1 first=[foo]`. zsh agrees with bash.
- **Source:** `psh/expansion/manager.py` `_expand_word()`, line 218 (`return ''` in the empty-split else branch); the non-list return is appended as one empty arg in `_expand_word_ast_arguments()` (lines 75-80).
- psh contradicts its own design: `psh/expansion/CLAUDE.md` pitfall #3 states "unquoted $var produces nothing (no argument)."
- **Recommendation:** Change line 218 `return ''` → `return []` so a purely unquoted empty/unset expansion contributes zero fields. The `len==1` path (215-216) already preserves `x$emptyvar`; quoted `""` takes the double-quoted path and is unaffected. Add conformance tests for `set -- $unset; echo $#` and `set -- $unset foo; echo $# $1`.

#### 2. for-loop word splitting collapses empty fields for non-whitespace IFS

- **Reproducer:** `IFS=:; v="a::b"; for x in $v; do echo "[$x]"; done`
- **psh:** `[a] [b]` (2 fields) — **bash:** `[a] [] [b]` (3 fields)
- Inconsistent inside psh: the simple-command path is correct (`printf "[%s]\n" $v` and `set -- $v; echo $#` yield 3 fields). Only the for/select loop drops empties. The splitter itself is correct: `WordSplitter().split('a::b', ':')` → `['a', '', 'b']`.
- **Source:** `psh/executor/control_flow.py:557-571` `_word_split_and_glob` — the `for word in words:` loop is guarded by `if word:` (line 565), discarding empty fields before globbing.
- **Recommendation:** Preserve empty fields — append them without globbing:
  ```python
  for word in words:
      if not word:
          result.append(word)
          continue
      matches = glob.glob(word)
      result.extend(sorted(matches)) if matches else result.append(word)
  ```
  Long-term: have the for/select loop reuse the Word-AST `ExpansionManager` path. Add conformance tests for leading/interior/trailing empty fields with non-whitespace IFS.

#### 3. let builtin is completely missing → **see "Intentional & documented" (documented difference)**

> Listed here for severity context, but verdict is `intentional-documented`. Not a confirmed bug.

#### 4. Variable values are not recursively evaluated as arithmetic expressions

- **Reproducer:** `a="2*3"; echo $(( a ))`
- **psh:** `0` — **bash:** `6` (zsh also `6`)
- Also `a='2+3'; $((a))` → psh `0` / bash `5`; `a="2*3"; $((a+1))` → psh `1` / bash `7`. Single-identifier indirection (`b=a; a=5; $((b))` → 5) works.
- **Source:** `psh/arithmetic.py:745` `get_variable()`. After `int(value)` fails (760-762), it only recurses when `value.isidentifier()`; other non-integer strings fall to the else (769-770) returning 0. Driver `evaluate_arithmetic()` at `arithmetic.py:963` can be reused.
- **Recommendation:** When `int(value)` fails and the value is not a bare identifier, recursively evaluate via `evaluate_arithmetic(value, self.shell)` with the existing `seen` set + depth guard. Also fix the stale doc example at `docs/user_guide/07_arithmetic.md:481-486`. Add a conformance test (`a="2*3"; echo $((a))` → 6).

#### 5. Numeric-base values stored in variables are not parsed (0x.., 2#..)

- **Reproducer:** `x=0x10; echo $(( x ))`
- **psh:** `0` — **bash:** `16`. Also `x=2#101` → psh `0` / bash `5`; `x=010` → psh `10` / bash `8` (octal).
- Base-prefixed *literals* work (`$((0x10))` → 16), so the lexer is fine; only variable dereferencing is broken.
- **Source:** `psh/arithmetic.py:745-770` `get_variable()`, line 761 uses base-10 `int(value)`.
- **Recommendation:** Same fix as #4 — recursively evaluate the variable's string value as an arithmetic sub-expression. This fixes hex, `base#N`, octal, and `x="1+2"` simultaneously. Add conformance tests asserting `x=0x10`→16, `x=010`→8, `x=2#101`→5.

#### 6. ${!var} indirect variable expansion returns empty → **see "Intentional & documented"**

> Severity HIGH but verdict is `intentional-documented` (limitation disclosed in `docs/user_guide/05_variables_and_parameters.md:339-352`). Not a confirmed bug.

#### 7. ${var@Q}/@U/@L/@u parameter transform operators return empty → **see "Intentional but undocumented"**

> Verdict `intentional-undocumented`. Not a confirmed bug.

#### 8. ${x//pat} and ${x/pat} with omitted replacement raise an error instead of deleting matches

- **Reproducer:** `x=hello; echo "${x//l}"`
- **psh:** prints `psh: ${var//}: missing replacement string` to stderr, outputs unchanged `hello` — **bash:** `heo`
- Forms *with* the separator are correct (`${x//l/}` → `heo`, `${x//l/X}` → `heXXo`).
- **Source:** `psh/expansion/variable.py:886` `_split_pattern_replacement()` returns `(None, None)` (line 905) when no `/` separator is found; callers (573-600) treat `pattern is None` as the error.
- **Recommendation:** At lines 904-905, return `(operand, '')` instead of `(None, None)` so the whole operand becomes the pattern with an empty (deletion) replacement. The four "missing replacement string" branches (577-599) can then be deleted. Add conformance coverage for `${x//l}`, `${x/l}`, `${x//}`.

#### 9. ${x?word} (unset, no colon) does not error when variable is unset

- **Reproducer:** `unset x; echo "${x?unset error}"`
- **psh:** empty line, exit 0 — **bash:** `bash: line 1: x: unset error`, exit 127
- Broader: **all** non-colon operators are unimplemented — `${x-default}`, `${x=default}`, `${x+alt}` all misbehave when the variable is unset/set; they only appear correct for the null-but-set case.
- **Source:** `psh/expansion/parameter_expansion.py:22` `parse_expansion()` has no branch for `-`, `=`, `?`, `+`; `psh/expansion/variable.py:537` `_apply_operator()` implements only `:-/:=/:?/:+`.
- **Recommendation:** Implement the four non-colon operators (test "unset only" vs the colon forms' "unset or null"). Thread an is-set flag through `_get_var_or_positional` (currently returns `''` for both unset and null). Add conformance tests in BOTH unset and null states; add unit tests for the unset case to `tests/unit/expansion/test_parameter_expansion.py`.

#### 10. ${x+word} (set/unset test, no colon) treats empty value as unset

- **Reproducer:** `x=; echo "${x+plus}"`
- **psh:** empty line — **bash:** `plus` (zsh agrees with bash)
- Same root family as #9. Even a SET var fails: `x=val; "${x+plus}"` → psh empty / bash `plus`.
- **Source:** `psh/parser/recursive_descent/support/word_builder.py:118` operators list omits `+ - = ?`; secondary gap in `psh/expansion/variable.py` `_apply_operator` (line 537).
- **Recommendation:** Add `'+', '-', '=', '?'` to the operators list (keeping colon forms first so `:-` wins over `-`); add matching `_apply_operator` branches that distinguish unset from empty. Check the combinator parser (`psh/parser/combinators/expansions.py`) for parity. Add conformance tests across unset/empty/set states.

#### 11. Brace expansion incorrectly applied to RHS of scalar assignments

- **Reproducer:** `a={x,y}; echo "[$a]"`
- **psh:** `[y]` (data corruption — drops all but last) — **bash:** `[{x,y}]` (and `bash --posix`, `sh`, zsh)
- Also `a={1..3}` → psh `3` / bash `{1..3}`; `a=pre{x,y}` → psh `prey` / bash `pre{x,y}`. Command-word assignments (`export c={x,y}`) correctly expand in both.
- **Source:** Brace expansion runs on the entire raw line before tokenization: `psh/lexer/__init__.py:62-73` calls `BraceExpander().expand_line()` (`psh/brace_expansion.py:28`). `expand_line('a={x,y}; echo "[$a]"')` returns `'a=x a=y; ...'`.
- **Recommendation:** Move brace expansion to a post-tokenization per-word step that respects context; at minimum suppress it on assignment-word RHS tokens. Add conformance tests for `a={x,y}`, `a=pre{x,y}post`, and the ambiguous-redirect case. Correct the "Full support" claim in `docs/user_guide/17_differences_from_bash.md:447`.

#### 12. Character ranges producing shell-special chars (backtick, etc.) are re-lexed and cause parse errors

- **Reproducer:** `echo {Z..a}`
- **psh:** `Parse error ... unclosed backtick substitution '\` a'`, exit 2 — **bash:** `Z [ \ ] ^ _ \` a`, exit 0 (zsh agrees with bash)
- The expansion itself is correct (`BraceExpander.expand_line('echo {Z..a}')` emits the literal backtick); the re-lex step re-parses it as syntax.
- **Source:** `psh/lexer/__init__.py:62-73` `tokenize()` re-lexes the brace-expanded string (line 65 expand, line 72 `ModularLexer`). Any range crossing shell metacharacters breaks.
- **Recommendation:** Perform brace expansion at the token/AST level so expanded results are literal word parts; or have `BraceExpander` quote/escape metacharacters in range output so re-lexing treats them literally. Add a conformance test for `{Z..a}`; correct the "Full support" doc claim.

#### 13. [^...] bracket negation not supported; matches the negated set instead

- **Reproducer:** `touch fileX; echo file[^0-9]` (with `file1 file2` present)
- **psh:** `file1 file2` (the opposite set) — **bash:** `fileX` (zsh: `fileX`)
- POSIX `[!0-9]` form works in psh. **Documented as working** (`docs/user_guide/06_expansions.md:410` shows "Negation with [!...] or [^...]"), so this is a `real-bug` with a false doc claim.
- **Source:** `psh/expansion/glob.py:36` calls Python `glob.glob()`; Python fnmatch only treats `[!...]` as negation, `^` is a literal class member. Same defect affects case-statement pattern matching (`case fileX in file[^0-9])` → psh NOMATCH / bash MATCH).
- **Recommendation:** Translate a leading `^` immediately after `[` to `!` (only at the negation position; preserve `[^]`, escaped `\[`). Apply the same fix wherever case/`[[ ]]` converts shell globs. Add conformance tests for `echo file[^0-9]` and a `case` equivalent.

#### 14. POSIX character classes [[:alpha:]] [[:digit:]] [[:upper:]] not supported in globs

- **Reproducer:** `echo *[[:upper:]]*` (files `Foo.TXT bar.txt Baz123`)
- **psh:** `*[[:upper:]]*` (unexpanded) — **bash:** `Baz123 Foo.TXT` (zsh agrees)
- **Documented as working** (`docs/user_guide/06_expansions.md:439-444` shows `ls [[:digit:]]*`), so `real-bug` with false doc claim.
- **Source:** `psh/expansion/glob.py:36` — Python `glob.glob()` lacks POSIX class support.
- **Recommendation:** When a pattern contains `[[:`, translate the bracket classes to a regex and match directory entries (reuse `psh/expansion/extglob.py` regex machinery or `os.scandir` + `re`). Add conformance tests for `*[[:upper:]]*`, `[[:digit:]]*`, `[[:alpha:]]*`, `[[:lower:]]`, `[[:alnum:]]`.

### MEDIUM severity

#### 15. Empty (null) IFS does not concatenate $* without separators

- **Reproducer:** `IFS=; set -- a b c; echo "$*"`
- **psh:** `a b c` — **bash:** `abc` (zsh: `abc`). Arrays too: `IFS=; a=(x y z); echo "${a[*]}"` → psh `x y z` / bash `xyz`.
- bash distinguishes unset IFS (join with space) from null IFS (no separator); psh produces a space in both.
- **Source:** `psh/expansion/variable.py` uses `separator = ifs[0] if ifs else ' '` at three sites (lines 341-343, 286-288, 504-506); empty string is falsy → space fallback. Underlying enabler: `psh/core/state.py:239` `get_variable(name, default='')` makes unset and empty indistinguishable.
- **Recommendation:** Pass a sentinel default and branch: `None` → space, `''` → no separator, else `ifs[0]`. Extract a single helper to avoid the repeated pattern. Add conformance tests for `IFS=`, `unset IFS`, and `${arr[*]}` equivalents.

#### 16. ANSI-C $'...' octal escapes \nnn and \0nnn not supported

- **Reproducer:** `echo $'\101\102'`
- **psh:** literal `\101\102` — **bash:** `AB` (zsh: `AB`)
- `\0nnn` also mishandled: `$'\0101'` → psh `A` but bash backspace+`1`. Hex `\x41` and 4-digit `\uNNNN` work, so only the octal family is missing in the ANSI-C path.
- **Source:** `psh/lexer/pure_helpers.py` `handle_ansi_c_escape`, line 323 gates octal on `next_char == '0'` only; bare leading octal digits fall through to the literal at line 384. (`printf "\101"` and `echo -e "\101"` work — defect is isolated to `$'...'`.)
- **Recommendation:** Trigger the octal branch on any `next_char in '01234567'`, reading up to 3 octal digits *total* from `next_char`, then `chr(int(octal_str, 8) & 0xFF)`. This also makes `\0101` → octal 010 + `1` to match bash. Add conformance tests for `echo $'\101\102'` and `echo $'\7\41'`.

#### 17. Array subscripts in arithmetic are unsupported

- **Reproducer:** `a=(10 20 30); echo $(( a[1] ))`
- **psh:** `arithmetic error: Unexpected character '[' at position 2`, exit 1 — **bash:** `20`, exit 0
- Even scalar `a=5; $((a[0]))` errors in psh / bash gives 5. Workaround `$(( ${a[1]} ))` works (expansion precedes the arithmetic tokenizer). **Doc presents this as working** (`docs/user_guide/07_arithmetic.md:602` uses `$((numbers[i] - avg))`).
- **Source:** `psh/arithmetic.py` — `ArithTokenType` enum (9-60) has no `LBRACKET/RBRACKET`; `[` falls to the catch-all at 416-417; parser primary (line 712) accepts only a bare identifier.
- **Recommendation:** Add LBRACKET/RBRACKET token types + tokenizer cases; in the parser primary path, accept an optional `[index]` suffix building an array-element node (0-based, reusing `${a[i]}` lookup). Ensure `(( a[i] += 10 ))` works. Add conformance tests.

#### 18. 2 ** 64 (and larger exponents) error instead of wrapping to 64-bit

- **Reproducer:** `echo $(( 2 ** 64 ))`
- **psh:** `arithmetic error: exponent too large`, exit 1 — **bash:** `0` (zsh: `0`)
- Smaller cases already wrap correctly (`2 ** 63`, `3 ** 50`), proving the wrapping machinery works; only the artificial guard aborts.
- **Source:** `psh/arithmetic.py:906-907` `if right > 63: raise ShellArithmeticError("exponent too large")`. Line 908 `return _to_signed64(left ** right)` already produces correct results.
- **Recommendation:** Remove the `right > 63` guard; keep `right < 0` (matches bash). To avoid huge intermediates, prefer modular exponentiation: `pow(left % (1<<64), right, 1<<64)` then `_to_signed64()` (handle left/right==0). Add tests for `2 ** 64` → 0 and `2 ** 100` → 0.

#### 19. Spurious space inserted when '{' is immediately followed by '[' in a non-expanding brace

- **Reproducer:** `echo {[ab]}`
- **psh:** `{ [ab]}` — **bash:** `{[ab]}`
- Lexer artifact, not the brace expander (`expand_line` returns it unchanged). `--debug-tokens` shows `{` split into a standalone LBRACE. Does NOT trigger for `{x[ab]}`, `a{[ab]}c`, quoted `"{[ab]}"`.
- **Source:** `psh/lexer/recognizers/operator.py` `{`-as-reserved-word heuristic (~line 309) calls `_is_shell_token_delimiter` (line 70, returns True for chars in `'|&;(){}[]<>'`); because `[` is in that set, `{` followed by `[` is emitted as standalone LBRACE.
- **Recommendation:** Inside the `if candidate == '{':` block use a narrower predicate that excludes `[`/`]` (counting only whitespace and `|&;()<>`/newline). Do NOT change `_is_shell_token_delimiter` globally (also called by the `!` heuristic at line 295). Verify `{ echo hi; }`, `echo {a,b}`, `echo {[a,b]}` still match bash. Add conformance tests for `{[ab]}`, `{[ab]c}`.

#### 20. Brace list item that is a quoted special char is not expanded

- **Reproducer:** `echo {"[",x}`
- **psh:** `{[,x}` — **bash:** `[ x` (zsh agrees). Broader: ANY quote inside a brace item disables expansion (`{"a",x}` → psh `{a,x}` / bash `a x`).
- **Source:** `psh/brace_expansion.py:38` `expand_line()` calls `_split_respecting_quotes()` (line 507) which fragments the line at every quote boundary, so the `{...}` is split across segments and never seen whole. Verified: `_split_respecting_quotes('echo {"[",x}')` → `[('echo {', False), ('"["', True), (',x}', False)]`.
- **Recommendation:** Quotes should only protect their *content* (commas/braces), not block expansion of the surrounding brace. Extend the brace-parsing helpers (`_find_brace_expression` line 300, `_expand_list` line 246, `_are_braces_balanced` line 156) to track quote state, and drop the line-level quote-splitting in `expand_line` (38-51). Add conformance tests for `{"[",x}`, `{"a",x}`, `{a,"b,c"}`.

#### 21. nocaseglob option recognized but has no effect

- **Reproducer:** `shopt -s nocaseglob; echo F*`
- **psh:** `Foo.TXT` only — **bash:** all `file*` entries plus `Foo.TXT` (FS confirmed case-sensitive). The option is stored and accepted but inert.
- **Source:** `psh/expansion/glob.py:36` never reads the option. Stored at `psh/core/state.py:76`, accepted by `psh/builtins/shell_options.py:25`. Docs present it as working with no caveat (unlike extglob, which is caveated).
- **Recommendation:** When `state.options['nocaseglob']` is set, match case-insensitively via `re.compile(fnmatch.translate(component), re.IGNORECASE)` per path component or `os.scandir`. Add a conformance test. If deferred, mark it recognized-but-non-functional in the docs the way extglob is.

#### 22. failglob shell option not supported → **see "Intentional & documented"**

> Verdict `intentional-documented`. Not a confirmed bug.

#### 23. nullglob not applied to for-loop word list

- **Reproducer:** `shopt -s nullglob; for f in zzz*; do echo "iter=$f"; done; echo done`
- **psh:** iterates once with literal `zzz*` — **bash:** zero iterations (zsh agrees). nullglob works in simple-command args.
- **Source:** for/select loop has its own globbing in `psh/executor/control_flow.py` that ignores nullglob: `_expand_single_item` (554-555) and `_word_split_and_glob` (566-570) always fall back to the literal. The canonical path `psh/expansion/manager.py:417-436` checks nullglob correctly.
- **Recommendation:** Honor nullglob (and ideally failglob) in both control_flow.py sites, or delete the duplicated logic and delegate to `ExpansionManager._glob_words`. Add a conformance test.

#### 24. globstar: bare ** does not recurse

- **Reproducer:** `shopt -s globstar; echo **`
- **psh:** non-recursive (no `sub/x.txt`) — **bash:** includes `sub/x.txt` (zsh agrees). psh's `**` with globstar is identical to without it.
- **Source:** the option is registered (`psh/core/state.py:77`) but never consumed; `psh/expansion/glob.py:36` calls `glob.glob(pattern, include_hidden=dotglob)` without `recursive=True`. Docs assert it works.
- **Recommendation:** `matches = glob.glob(pattern, include_hidden=dotglob, recursive=state.options.get('globstar', False))`. Note bash's directory-first ordering may still differ from psh's alphabetical sort; decide whether to match or document. Add a conformance test for `echo **` and `**/*`.

#### 25. Parenthesized substring offset ${x:(-n):len} rejected

- **Reproducer:** `x=0123456789; echo "${x:(-3):2}"`
- **psh:** `${var:(-3):2}: invalid offset or length` — **bash:** `78` (zsh agrees). Broader: ANY non-literal arithmetic offset/length is rejected (`${x:1+1:2}` → psh error / bash `23`). The space form `${x: -3:2}` works.
- **Source:** `psh/expansion/variable.py:601-618` uses bare `int(offset_str)` / `int(length_str)` / `int(operand)`.
- **Recommendation:** Replace the `int()` calls with `evaluate_arithmetic(expr, self.shell)` (already imported at line 137), catching `ArithmeticError`. Add conformance tests for `${x:(-3):2}`, `${x:(3):2}`, `${x:1+1:2}`.

#### 26. ${!prefix@} / ${!prefix*} ignores the prefix entirely

- **Reproducer:** `aa=1; ab=2; ac=3; echo "${!a*}"`
- **psh:** dumps the entire variable set — **bash:** `aa ab ac`. The defect is broader than env-var inclusion: psh ignores the prefix completely (verified with `${!xy*}` too).
- **Documented limitation** in three places (`05_variables_and_parameters.md:516`, `16_advanced_features.md:647-650`, `17_differences_from_bash.md:247-248`) — but trivially fixable; verdict `intentional-documented`. **See "Intentional & documented."**

> Listed for severity context; verdict is `intentional-documented`, not a confirmed bug.

### LOW severity

#### 27. ANSI-C $'...' short unicode \u with <4 hex digits not supported

- **Reproducer:** `echo $'\u41'`
- **psh:** literal `\u41` — **bash:** `A` (zsh: `A`). bash accepts 1-4 digits after `\u`, 1-8 after `\U`; psh requires the maximal count.
- **Source:** `psh/lexer/pure_helpers.py` — `\u` handler (343-361) requires `len(hex_str) == 4`; `\U` (363-381) requires `== 8`. The sibling `\x`/`\0` handlers correctly accept variable length.
- **Recommendation:** Change the gates to `if hex_str:` (loops already cap digit counts). Add conformance tests for `$'\u41'`, `$'\u9'`, `$'\U41'`.

#### 28. Quoted operand inside $(( )) is rejected

- **Reproducer:** `echo $(( "5" ))`
- **psh:** `arithmetic error: Unexpected character '"' at position 1`, exit 1 — **bash:** `5` (zsh agrees). bash also errors on single quotes, so only double quotes need tolerating.
- **Source:** `psh/arithmetic.py` `tokenize()` (222-421) has no case for `"`; it falls to the else at line 417.
- **Recommendation:** Add a `"` branch that strips/consumes the double-quote delimiters and continues tokenizing the inner content (so `"5"`→5, `"x"`→identifier). Leave single quotes erroring. Add conformance tests via `assert_identical_behavior`.

#### 29. Error message text differs: octal error token has a spurious leading zero

- **Reproducer:** `echo $(( 08 ))`
- **psh:** `... 008: value too great for base (error token is "008")` — **bash:** `... 08: value too great for base (error token is "08")`. Exit codes match (1). Consistent extra leading zero (`09`→`009`, `0128`→`00128`).
- **Source:** `psh/arithmetic.py:193-195` — the octal loop already consumes the leading `0` into `octal_digits`, but the f-string prepends another `0`.
- **Recommendation:** Drop the redundant `0` prefix in the f-string at line 194 so it reads `f"{octal_digits}: value too great for base (error token is \"{octal_digits}\")"`. The `psh:` vs `bash: line 1:` tool-name prefix is expected and out of scope.

#### 30. Substring with out-of-range negative offset returns whole string instead of empty

- **Reproducer:** `x=abc; echo "[${x: -10}]"`
- **psh:** `[abc]` — **bash:** `[]`. (zsh agrees with psh, but bash is the stated reference and the doc claims bash compatibility.) bash returns empty whenever `len(value)+offset < 0`.
- **Source:** `psh/expansion/parameter_expansion.py:258-259` `extract_substring()` clamps a too-negative offset to 0 instead of returning `''`.
- **Recommendation:** Replace `offset = 0` with `return ''` when the resolved offset is still `< 0`. Add a conformance case to `tests/conformance/bash/test_bash_compatibility.py::test_substring_expansion`.

#### 31. Negative substring length larger than remaining string silently yields empty instead of erroring

- **Reproducer:** `x=abc; echo "[${x:0:-5}]"`
- **psh:** `[]`, exit 0 — **bash:** `-5: substring expression < 0`, exit 1 (zsh also errors). Valid negative lengths in range match bash (`${x:0:-1}` → `[ab]`).
- **Source:** `psh/expansion/parameter_expansion.py:270-275` — the `if end <= offset: return ''` branch swallows the error. Note: bash returns `''` when `end == offset` (so keep equality as success); only `end < offset` should error.
- **Recommendation:** When the computed `end < offset`, raise a shell expansion error (`<expr>: substring expression < 0`) with non-zero exit. Add a conformance case.

### HIGH severity (heredoc/redirect)

#### 32. Here-string (<<<) with a bareword operand produces no output and swallows the whole command line

- **Reproducer:** `echo before; cat <<< hello; echo after`
- **psh:** no output at all — **bash:** `before` / `hello` / `after` (zsh agrees). The entire command line is discarded — even `echo before` never runs.
- **Source:** `psh/scripting/source_processor.py` — `_has_unclosed_heredoc` regex `r'<<(-?)\s*([\'"]?)(\\\s*)?(\w+)\2'` (line 394) and `_collect_heredoc_content` (line 438) falsely match the trailing `<<` of `<<<` plus the operand as a heredoc delimiter. psh then reads to EOF for a delimiter that never comes, `_collect_heredoc_content` returns None, and the command is dropped. Tokenizer/parser/io_redirect are all correct (AST has `Redirect(type='<<<', target='hello')`).
- Variant behavior matches the regex: `cat <<< $x`, `cat <<< "hello world"` work; `cat <<< hello`, `cat <<< "hello"`, `cat <<< 123`, `cat <<<hello`, `grep . <<< foo` all fail. **Documented as a supported feature** (`docs/user_guide/09_io_redirection.md §9.7`).
- **Recommendation:** Add a negative lookbehind/lookahead to both regexes (lines 394, 438): `r'(?<!<)<<(?!<)(-?)\s*([\'"]?)(\\\s*)?(\w+)\2'`. Verified it rejects `<<<`/`<<<hello` while still matching `<<EOF`, `<<- EOF`, `<<"EOF"`, and mixed lines. Add conformance tests for single-word/quoted here-string operands.

#### 33. Builtin with N>file (fd>=3) wrongly redirects stdout to the file

- **Reproducer:** `echo hi 3>tmp/p1`
- **psh:** stdout empty, `tmp/p1` contains `hi` — **bash:** `hi` to stdout, file empty (zsh agrees). Affects `printf` and `>|` too; external commands are correct.
- **Source:** `psh/io_redirect/manager.py` `setup_builtin_redirections` — the `>`/`>>` branch (124-138) and `>|` branch (116-123) special-case only `target_fd == 2`; every other fd unconditionally replaces `sys.stdout`, ignoring the computed `target_fd`.
- **Recommendation:** When `target_fd` is not 1 or 2, delegate to the fd-aware path already used for `<&`/`>&-` (lines 148-152): `saved_fds = self.file_redirector.apply_redirections([redirect]); self._saved_fds_list.extend(saved_fds)`. Add conformance tests for `echo hi 3>file` (file empty, stdout=hi).

#### 34. External command with custom fd redirection (N>=3) fails with 'Bad file descriptor' before running

- **Reproducer:** `/bin/echo hi 7>tmp/n7`
- **psh:** `psh: [Errno 9] Bad file descriptor`, exit 1, /bin/echo never runs, file not created — **bash:** `hi` to stdout, empty file, exit 0 (zsh agrees).
- **Source:** external commands route through `with self.io_manager.with_redirections(node.redirects)` (`psh/executor/command.py:509`) → parent-side `FileRedirector.apply_redirections` (`psh/io_redirect/file_redirect.py:136`), which does `os.dup(target_fd)` at line 174 (and 159-160, 169-170, 186, 190). For an unopened parent fd (7) `os.dup(7)` raises EBADF before fork. This is also **redundant**: `ExternalExecutionStrategy` already sets up redirections post-fork via `setup_child_redirections` (`psh/executor/strategies.py:358`, `:312`), which handles high fds fine.
- Affected: any external-command redirect to/from fd >= 3 (`N>file`, `N>>file`, `N<>file`, `N>&M`, `N>&-`, `N<&M`). Builtins and `exec 3>file` work. **Doc presents custom/high-fd redirection as supported.**
- **Recommendation:** Don't wrap external commands in `with_redirections`; rely on the forked child's `setup_child_redirections`. Gate the wrapper to builtin strategies only (it's still needed for forked-builtin/pipeline cases). Alternatively, guard each `os.dup(target_fd)` so EBADF means "no original to restore." Add conformance tests for per-command high-fd redirection.

---

## Intentional but undocumented

Candidates for either documenting as a known difference or fixing.

### ${var@Q}/@U/@L/@u parameter transform operators return empty (HIGH)

- **Reproducer:** `x="a b c"; echo "${x@Q}"` → psh empty / bash `'a b c'`. Also @U/@L/@u/@K/@k/@E/@P all empty in psh.
- **Verdict:** `intentional-undocumented`. Acknowledged as a missing feature in `docs/ARCHITECTURE_ROADMAP.md:121-125` and `docs/archive/FEATURE_ROADMAP.md`, but **not** disclosed as a difference in the user guide, so users have no warning. Not a broken conformance claim (no user-guide claim it works), and `${x^^}`/`${x,,}` case operators DO work.
- **Source:** `psh/expansion/parameter_expansion.py` `parse_expansion()` has no `@` branch — `${x@Q}` falls through to `('', 'x@Q', '')`, treated as an unset variable.
- **Recommendation:** Either (a) document the gap in `docs/user_guide/05_variables_and_parameters.md` as a known difference, or (b) implement: add an `@` branch in `parse_expansion()` recognizing Q/U/L/u/E/P/A/a/K/k, and implement transforms in `expand_parameter_direct()` (`psh/expansion/variable.py:442`), reusing the existing `^^`/`,,` logic for @U/@L/@u. If implemented, add conformance tests.

---

## Checked and matches / intentional-documented

These were reproduced but are correct-as-designed and disclosed in the docs — no conformance violation. Optionally lock in with `assert_documented_difference()`.

| Finding | Reproducer | psh vs bash | Documented at |
|---|---|---|---|
| **`let` builtin missing** (HIGH) | `let "x = 5 + 3"; echo $x` | psh `let: command not found` / bash `8` | `17_differences_from_bash.md:210,496,669`. Working alternative `((x = 5 + 3))` confirmed. |
| **${!var} indirect expansion** (HIGH) | `a=hi; b=a; echo "${!b}"` | psh empty / bash `hi` | `05_variables_and_parameters.md:339-352` ("not currently supported... use `eval`"). Array-keys `${!arr[@]}` works. |
| **${!prefix@}/${!prefix*} ignores prefix** (MED) | `aa=1; echo "${!a*}"` | psh dumps all vars / bash `aa ...` | `05_...:516`, `16_advanced_features.md:647-650`, `17_...:247-248`. Trivially fixable (wrong arg passed at `variable.py:619-624` — passes empty `operand` instead of `var_name`). |
| **failglob option unsupported** (MED) | `shopt -s failglob; echo nomatch*` | psh `invalid shell option name` + literal / bash `no match`, exit 1 | `17_differences_from_bash.md:492,621` (supported shopt list omits failglob). |
| **\cX control-char escape** (LOW) | `echo $'\cA' \| od -An -c` | psh literal `\ c A` / bash `001` | `08_quoting_and_escaping.md:267` (escape list deliberately omits `\cX`). |

### Notably NOT a bug — confirmed matching bash

- **Glob result ordering / locale collation** (`echo *`): under en_GB.UTF-8 bash sorts case-insensitively per LC_COLLATE while psh uses C/code-point order. This was graded `real-bug` (functional bash divergence) but is **low severity and locale-dependent** — under `LC_ALL=C` the two agree. Source: `psh/expansion/glob.py:40` (and `:62`, `extglob.py:260`, `manager.py:429`) use plain `sorted()`. Given the educational-clarity priority, documenting it as a known C/ASCII-collation difference may be the pragmatic choice over implementing `locale.strxfrm`.

---

## Cross-cutting themes (for Phase 2 prioritization)

1. **Variable-as-arithmetic-expression** (#4, #5): one fix in `get_variable()` closes both.
2. **Non-colon parameter operators** (#9, #10): one feature closes both, plus the documented `${!var}` gap shares the same is-set-vs-null limitation.
3. **Brace expansion runs on the raw line pre-tokenization** (#11, #12, #20, plus the `{[` lexer split #19): the architectural root is whole-line string preprocessing in `psh/lexer/__init__.py:62-73`; relocating brace expansion to post-tokenization per-word would fix multiple findings at once.
4. **Glob delegates blindly to Python `glob.glob()`** (#13, #14, #21, #24, collation): `psh/expansion/glob.py:36` ignores `[^...]`, POSIX classes, nocaseglob, globstar, and locale. A glob-translation layer would address the whole cluster.
5. **Duplicate expansion paths** (#1 vs #2, #23): the for/select loop in `control_flow.py` maintains its own string-based splitting/globbing that diverges from the canonical `ExpansionManager`; consolidating eliminates the empty-field and nullglob inconsistencies.
6. **Redirection fd handling for fds >= 3** (#33, #34): builtins clobber stdout, external commands crash pre-fork; both stem from the manager not honoring non-1/2 target fds on the parent side.
