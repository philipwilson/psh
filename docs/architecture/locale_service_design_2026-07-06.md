# Central Locale Service — Design Document

Date: 2026-07-06
Author: design investigation (Opus 4.8)
Resolves: Expansion Subsystem Improvement Plan finding #5 ("POSIX character
classes are incorrectly ASCII-only"), and lays groundwork consumed by
finding #6 (compiled pattern engine).
Status: DESIGN ONLY — no code changed. Probe evidence lives under
`tmp/locale_probes/` (`probe_driver.py`, `mechanism_experiments.py`,
`results.txt`).

---

## 0. Executive summary (5 sentences)

Introduce one `LocaleService` (home: `psh/core/locale_service.py`) that owns
the process locale, exposes three faithful primitives — **class membership**
(`in_class(ch, name)`), **case mapping** (`upper`/`lower`/`toggle`, ASCII-gated
in C locale), and **collation** (`collate_key`/`compare`) — and computes an
*effective LC_CTYPE* and *effective LC_COLLATE* from the environment using
bash's `LC_ALL > LC_{CTYPE,COLLATE} > LANG` precedence. Collation is
implemented with the stdlib `locale` module (`setlocale(LC_COLLATE)` +
`strxfrm`/`strcoll`), which **provably reproduces macOS bash ordering exactly**
in the probes and tracks glibc on Linux. Character-class membership is
mode-switched — C/POSIX → the existing ASCII tables, `*.UTF-8` → Unicode
predicates — with a documented `iswctype`-via-`ctypes` alternative that is
byte-identical to the host's own bash on both macOS and Linux. Because stdlib
`re` cannot express "Unicode letter", full UTF-8 class support requires the
matcher to call a per-character predicate rather than emit a regex range, which
couples this work to finding #6's pattern-AST engine — the service is therefore
designed so the pattern engine's `CharacterClass` node consumes it directly.
Locale state is read once at startup (Stage 1, high value, low risk) and later
made reactive to `LC_*`/`LANG` assignment (Stage 2, matches bash's dynamic
behavior), behind Bash-differential tests at every stage.

---

## 1. Headline findings (several contradict the review doc / codebase comments)

The probes were run against **bash 5.2.26 (homebrew, aarch64-apple-darwin23)**
under `C`, `C.UTF-8`, and `en_US.UTF-8`, each in a subprocess with the locale
set via env. Full tables in §2.

1. **CONFIRMED, and broader than the review doc stated.** POSIX classes are
   locale-sensitive in bash, and the divergence is not limited to `[[ ]]`: it is
   identical across `[[ == ]]`, `case`, `${var#pat}`, **and** pathname matching,
   because all four already funnel through psh's one glob→regex converter
   (v0.638). Fixing the class table/predicate fixes all four match sites at once.

2. **SURPRISE — macOS bash collation is REAL, not codepoint order.** The
   load-bearing comment in `glob.py:207` ("strcoll on macOS UTF-8 famously ≈
   codepoint order") is **false on this host**. Under `en_US.UTF-8`, macOS bash
   sorts `echo *` as `٣ _x 3 a B e é z` (dictionary order, é next to e) and
   evaluates `[[ a < B ]]` as **true** — genuine collation. Under `C`/`C.UTF-8`
   it is codepoint order (`3 B _x a e z é ٣`) and `[[ a < B ]]` is false.
   **Consequence: the collation gap is observable on the local macOS gate**, not
   just the Linux nightly — conformance tests for collation can run locally.

3. **SURPRISE — `locale.strxfrm` reproduces macOS bash ordering EXACTLY.**
   Python `sorted(files, key=locale.strxfrm)` under `en_US.UTF-8` yields
   `٣ _x 3 a B e é z` — byte-identical to macOS bash. `locale.strcoll('a','B')`
   is negative under `en_US.UTF-8` (a<B, matches bash) and positive under `C`
   (matches bash). Collation is therefore the *easiest* part to fix faithfully,
   using only the stdlib `locale` module (no ctypes).

4. **SURPRISE — macOS `[[:digit:]]` matches Unicode digits (٣, ３), glibc does
   not.** In UTF-8 locales macOS bash treats Arabic-Indic `٣` and fullwidth `３`
   as `[[:digit:]]` and `[[:alnum:]]`; POSIX and glibc restrict `[[:digit:]]` to
   `0-9`. Reconciliation showed macOS `iswctype(ord('٣'), wctype("digit"))` =
   **True** while `iswdigit(ord('٣'))` = **False** — bash uses `iswctype`. So
   `iswctype`-via-`ctypes` is byte-faithful to *whichever* bash runs on the host,
   automatically resolving the macOS-vs-Linux split. This is the single strongest
   argument for the ctypes backend, and the single reason a pure-Python backend
   cannot be byte-identical to local bash on both platforms simultaneously for
   the digit/space/punct classes.

5. **RANGES are already correct — no work needed.** `[[ x == [a-z] ]]` matches
   ASCII `a-z` only in *every* locale in both shells, because bash's
   `globasciiranges` defaults **on** in 5.x (forcing C-locale/ASCII range
   interpretation), and psh's codepoint ranges coincide with that for ASCII.
   The only range action item is cosmetic: psh does not recognize the
   `globasciiranges` shopt name (`shopt globasciiranges` → "invalid shell option
   name"); bash reports it `on`.

6. **Case conversion is locale-sensitive and psh currently ignores that.**
   `${x^^}` on `é` is `é` (unchanged) in bash's C locale but `É` in UTF-8
   locales; psh always produces `É`. `${x,,}` on `İ` (U+0130) is `İ` in bash-C,
   `i` in bash-UTF-8; psh always `i`. So psh's `simple_upper`/`simple_lower` are
   correct for UTF-8 locales but over-eager in C locale. Separately, `${x@U}` on
   `ß` is `ß` in bash (all locales) but `SS` in psh — a **locale-independent
   pre-existing bug**: `@U`/`@L`/`@u` use raw `str.upper()`/`str.lower()`
   (`operators.py:418`) instead of the length-safe `simple_*` mappings that
   `^^`/`,,` use. Worth folding into this work.

7. **bash treats `LC_*`/`LANG` as reactive special variables.** Assigning
   `LC_ALL=en_US.UTF-8` mid-script (no `export`) immediately changes
   classification; `LC_CTYPE` alone, `LC_COLLATE` alone, and `LANG` alone each
   take effect; `LC_ALL=C` overrides `LC_CTYPE`/`LANG`; unsetting all reverts to
   C. psh reacts to none of these today (it never calls `setlocale`).

---

## 2. Bash ground-truth truth tables (the core evidence)

Legend: `[[ ]]`/`case`/param cells show the match result; `0`=match/true,
`1`=no-match/false (shell exit-status convention). "psh" is current behavior.
Full raw output: `tmp/locale_probes/results.txt`.

### 2a. POSIX classes in `[[ x == [[:class:]] ]]`

| subject / class | bash C | bash C.UTF-8 | bash en_US.UTF-8 | psh (all locales) |
|---|---|---|---|---|
| `é` alpha | no | **yes** | **yes** | no |
| `中` alpha | no | **yes** | **yes** | no |
| `É` upper | no | **yes** | **yes** | no |
| `é` lower | no | **yes** | **yes** | no |
| `é` upper | no | no | no | no |
| `٣` (Arabic-Indic) digit | no | **yes** | **yes** | no |
| `３` (fullwidth) digit | no | **yes** | **yes** | no |
| `٣` alnum | no | **yes** | **yes** | no |
| `é` alnum | no | **yes** | **yes** | no |
| NBSP space | no | **yes** | **yes** | no |
| `«` punct | no | **yes** | **yes** | no |

psh matches bash **only in the C locale**. Note `٣`/`３` as digit and NBSP as
space are macOS-libc behaviors; glibc would answer "no" (see §4).

### 2b. Same classes in `case`, and in `${var#[[:class:]]}` — identical divergence

| probe | bash C | bash UTF-8 | psh |
|---|---|---|---|
| `case é in [[:alpha:]]` | no | **yes** | no |
| `case ٣ in [[:digit:]]` | no | **yes** | no |
| `x=éxyz; ${x#[[:alpha:]]}` | `éxyz` | **`xyz`** | `éxyz` |
| `x=éé9; ${x##[[:alpha:]]*}` | `éé9` | **`` (empty)** | `éé9` |

### 2c. POSIX classes + ordering in pathname expansion

Files: `a B e é z _x 3 ٣` (note: macOS APFS is case-insensitive, so a `E` file
collapses onto `e` — do **not** create both in a probe).

| glob | bash C | bash en_US.UTF-8 | psh (all locales) |
|---|---|---|---|
| `[[:alpha:]]*` | `B a e z` | **`a B e é z`** | `B a e z` |
| `[[:digit:]]*` | `3` | **`٣ 3`** | `3` |
| `*` (ordering) | `3 B _x a e z é ٣` | **`٣ _x 3 a B e é z`** | `3 B _x a e z é ٣` |

Two independent divergences here: **membership** (`é`/`٣` missing from psh's
matches) and **ordering** (psh codepoint-sorts; bash-UTF-8 collation-sorts).

### 2d. Ranges `[a-z]` — no divergence (globasciiranges default on)

| probe | bash (all locales) | psh |
|---|---|---|
| `[[ é == [a-z] ]]` | no | no |
| `[[ B == [a-z] ]]` | no | no |
| `shopt globasciiranges` | `on` | **error: invalid shell option name** |

### 2e. Case conversion (`${x^^}`, `${x,,}`, `${x@U}`)

| probe | bash C | bash UTF-8 | psh (all) |
|---|---|---|---|
| `${x^^}` on `é` | `é` | `É` | `É` |
| `${x^^}` on `ß` | `ß` | `ß` | `ß` |
| `${x,,}` on `É` | `É` | `é` | `é` |
| `${x,,}` on `İ` | `İ` (unchanged) | `i` | `i` |
| `${x@U}` on `ß` | `ß` | `ß` | **`SS`** (bug) |

psh diverges from bash-C for `é`/`É`/`İ` (psh case-maps; bash-C does not) and
from bash everywhere for `${x@U}` on `ß`.

### 2f. String comparison `[[ < ]]` / `[ \< ]`

| probe | bash C / C.UTF-8 | bash en_US.UTF-8 | psh (all) |
|---|---|---|---|
| `[[ a < B ]]` | false | **true** | false |
| `[[ B < a ]]` | true | **false** | true |
| `[[ é < f ]]` | false (é=0xE9 > f) | **true** | false |
| `[ a \< B ]` (test builtin) | false | false* | false |

`*` bash's `test`/`[` builtin uses `strcoll` too, but the probe ran the psh
`[`; treat the `[ ]` collation case as parallel to `[[ ]]`. psh always uses
Python codepoint comparison.

### 2g. Dynamic locale behavior (bash oracle, ambient env = C)

| action | bash | psh |
|---|---|---|
| assign `LC_ALL=en_US.UTF-8` mid-script, then classify `é` | reacts (match) | no reaction |
| `LC_CTYPE=en_US.UTF-8` alone | reacts | no |
| `LC_COLLATE=en_US.UTF-8` alone → `[[ a < B ]]` | reacts (true) | no |
| `LANG=en_US.UTF-8` alone | reacts | no |
| `LC_ALL=C` with `LC_CTYPE`/`LANG` UTF-8 | C wins (no match) | (n/a) |
| unset all | → C | → C-equivalent |

Precedence confirmed: **`LC_ALL` > `LC_CTYPE`/`LC_COLLATE` > `LANG`**, and
`LC_CTYPE` (classification/case) is independent of `LC_COLLATE` (ordering).

---

## 3. psh current-state map (where classification/collation lives today)

After v0.638's glob-converter unification and v0.629's identifier-policy
centralization, the surface is already fairly consolidated. Reference map (from
a full-tree sweep; file:line):

**Character-class tables (single source of truth):**
- `psh/expansion/glob.py:18` `_POSIX_CLASSES` (ASCII ranges) — THE table.
- `psh/expansion/glob.py:38` `_POSIX_CLASSES_PATHNAME` (punct minus `/`).
- `psh/expansion/glob.py:63` `translate_posix_classes()` (shared with `[[ =~ ]]`).
- `psh/expansion/glob.py:81` `normalize_bracket_expressions()` (stdlib-glob shim).

**The one class-interpretation chokepoint (all four match sites route here):**
- `psh/expansion/extglob.py:307` `_bracket_to_regex(content, ic)` — substitutes
  `_POSIX_CLASSES`, expands ranges, handles nocasematch. Reached from
  `_convert_pattern` (glob→regex, the default path for `case`/`[[ == ]]`/`${#}`)
  and from `_match_from`/`_bracket_match` (the per-char backtracking matcher used
  for negation/leftmost-longest).
- Match-site chains (all terminate at `_bracket_to_regex`):
  `case` → `control_flow.py:705 _match_shell_pattern` → `pattern.py:62`;
  `[[ == ]]` → `enhanced_test_evaluator.py:295 _pattern_match` → `pattern.py:62`;
  `${var#pat}`/`%`/`##`/`%%` → `parameter_expansion.py:118` →
  `pattern.py:17 shell_pattern_to_regex`;
  `${var/p/r}` → `parameter_expansion.py:195/224` → same.
  Pathname globbing → `glob.py:105 _compile_component` → same converter.

**Case conversion (user data):**
- `psh/lexer/unicode_support.py:137-172` `simple_upper`/`simple_lower`/`toggle_case`
  — the length-safe 1:1 mapper. Consumers: `parameter_expansion.py:440-467`
  (`^`/`^^`/`,`/`,,`/`~`/`~~`), `core/scope.py:668` and `executor/array.py:432`
  (`declare -u`/`-l`).
- `psh/expansion/operators.py:418-422` `${var@U/@L/@u}` — uses **raw**
  `str.upper()`/`str.lower()` (the `ß`→`SS` bug; inconsistent with `^^`/`,,`).

**Collation / ordering / comparison (user data):**
- `psh/expansion/glob.py:207-214` `sorted(matches)` — the "byte order" comment
  naming the intended `setlocale`+`strxfrm` design; plus `glob.py:175,447` and
  `extglob.py:595` (other glob result sorts).
- `psh/executor/enhanced_test_evaluator.py:135-141` `[[ a < b ]]` = Python `<`.
- `psh/builtins/test_command.py:467-476` `[ a \< b ]` = Python `<`.
- **No `import locale`, `setlocale`, `strcoll`, `strxfrm`, `LC_*` reads, or
  `globasciiranges` exist anywhere in the source** — psh currently runs in
  Python's default (C-collation) locale and codepoint-sorts everything.

**Identifier ctype (the existing "mini ctype service", a model to follow):**
- `psh/lexer/unicode_support.py:7-56` `is_identifier_start`/`is_identifier_char`
  — already `posix_mode`-gated (ASCII vs Unicode `unicodedata.category`), routed
  through `is_valid_name` (line 213). This is the precedent for a mode-gated,
  centralized classification predicate.
- `posix_mode` is already plumbed from shell options into the lexer config
  (v0.649 `_make_config`) — the same plumbing a locale profile would ride.

**Ambiguous cases that should NOT be rerouted through the locale service** (bash
keeps them C-locale/ASCII regardless of locale): the arithmetic tokenizer
(`arithmetic/tokenizer.py`), brace `{a..z}` sequence bounds
(`brace_expansion.py:559`), fd-number/option/keyword parsing, and all internal
`.lower()` on option/token names. These classify *syntax*, not user data.

**Already-centralized (v0.638):** the glob→regex converter and `_POSIX_CLASSES`
are the sole class-interpretation point, so a locale-aware fix has exactly one
place to change per concern — a strong starting position.

---

## 4. Python-mechanism analysis (no new dependencies)

All experiments are in `tmp/locale_probes/mechanism_experiments.py`.

### 4.1 The `locale` module (stdlib) — process-global, but that is acceptable

- `locale.setlocale()` accepts `C`, `C.UTF-8`, `en_US.UTF-8`, `POSIX` on this
  macOS host (all succeeded). It is **process-global** and, strictly,
  **not thread-safe**. Counter-arguments for accepting it: (a) bash itself is
  process-global — this is faithful, not a compromise; (b) psh is a
  single-threaded shell process; (c) `Shell.close()`/embedding concerns are
  bounded because the service can snapshot and restore, and an embedded psh
  changing the host's locale is the same footgun bash-as-a-library would have.
  The one real hazard is a host that *embeds* psh in a multithreaded Python app;
  that is a documented non-goal (§8).
- **Collation: `strcoll`/`strxfrm` are faithful and clean.** PROVEN:
  `sorted(files, key=locale.strxfrm)` under `en_US.UTF-8` reproduces macOS bash's
  `echo *` order exactly; `strcoll('a','B')` sign matches `[[ a < B ]]` in both
  C and en_US. On Linux the same calls use glibc's collation tables → track
  glibc bash. **This is the recommended collation backend, stdlib-only.**
- **Classification: the `locale` module has NO Python-level `iswctype`.**
  `str.isalpha()` etc. are Unicode-wide and do **not** narrow to ASCII under a C
  locale — so they cannot be used unconditionally. They must be *mode-switched*
  by the service (C → ASCII tables, UTF-8 → Unicode predicates).

### 4.2 Python Unicode predicates vs macOS bash (UTF-8 mode faithfulness)

| char | bash-UTF-8 | `isalpha` | `isdigit` | `isalnum` | `isspace` | `category` |
|---|---|---|---|---|---|---|
| `é` | alpha | True | – | True | – | Ll |
| `É` | upper | True (`isupper`) | – | True | – | Lu |
| `中` | alpha | True | – | True | – | Lo |
| `٣` | digit | – | True | True | – | Nd |
| `３` | digit | – | True | True | – | Nd |
| NBSP | space | – | – | – | True | Zs |
| `«` | punct | – | – | – | – | Pi |

Python Unicode predicates align with **macOS** bash on every row.
`punct`/`graph`/`print`/`cntrl` have no `str.is*` and must use
`unicodedata.category` (P*/S* for punct, etc.). So a pure-Python UTF-8 backend is
`str.isalpha/isupper/islower/isdigit/isalnum/isspace` + `unicodedata.category`
for the four printable/control classes.

Where pure-Python diverges from **glibc/Linux** bash (documented differences,
Linux-nightly-only): `[[:digit:]]`/`[[:alnum:]]` for non-ASCII digits (`٣`,`３`);
`[[:space:]]` for NBSP; some `[[:punct:]]` symbol-category edges. These are the
classes where glibc is stricter (POSIX-conformant) than macOS libc.

### 4.3 `ctypes` + `iswctype` — the maximum-fidelity alternative

`ctypes` (stdlib) can call the host libc's `iswctype(ord(c), wctype(name))` under
the active locale. PROVEN faithful: `iswctype('٣', "digit")` = **True** on macOS
(matches macOS bash), and because it *is* the host libc, it returns glibc's
answer on Linux (matches glibc bash). This is the **only** mechanism that is
byte-identical to the host's own bash on both platforms for the contentious
classes. Caveats: (a) must call `iswctype`, **not** `iswdigit`/`isalpha` — the
`isw*` narrow functions disagree with `iswctype` on macOS (they returned False
for `٣`); (b) requires `setlocale(LC_CTYPE)` (process-global, already needed for
collation); (c) `ord(c)` fits `wchar_t` (4 bytes on macOS/Linux) so astral
codepoints work; (d) it is decidedly **un-Pythonic** for an educational shell,
which is the reason it is offered as an *alternative*, not the default.

### 4.4 `unicodedata` — needed regardless

`unicodedata.category` is required for `punct`/`graph`/`print`/`cntrl` in the
pure-Python UTF-8 backend and for the existing identifier classification. No new
dependency; already used in `unicode_support.py`.

### 4.5 The regex wall (why finding #5 is coupled to finding #6)

stdlib `re` **cannot express "Unicode letter"** — there is no `\p{L}`, and `\w`
is close but wrong. The current engine matches `[[:alpha:]]` by substituting the
ASCII range `a-zA-Z` into a regex character class (`_bracket_to_regex`). In UTF-8
mode there is no finite range to substitute. Therefore **faithful UTF-8 class
membership cannot stay on the regex path** — the matcher must call a
per-character predicate (`in_class(ch, name)`). Two ways to satisfy this:
- Bridge (short term): when a bracket contains a POSIX class *and* the locale is
  UTF-8 mode, route that bracket through the existing per-char matcher
  (`extglob._bracket_match`, which already does character-by-character work) and
  have it call `LocaleService.in_class`. ASCII ranges and C-locale stay on the
  fast regex path unchanged.
- Target (finding #6): the compiled pattern-AST `CharacterClass` node stores the
  class *name* symbolically and matches by calling `in_class` at match time. The
  locale service is designed so this node consumes it directly (§5.4).

---

## 5. Design

### 5.1 Module home and API

New module `psh/core/locale_service.py` (core, because classification, case, and
collation are cross-cutting shell policy consumed by lexer, expansion, executor,
and builtins — the same rationale that put `unicode_support` and identifier
policy in shared homes). One instance lives on shell state
(`shell.state.locale`), created at startup.

```python
class LocaleMode(Enum):
    C = auto()        # POSIX/C: ASCII-only classes, ASCII case, codepoint collation
    UTF8 = auto()     # *.UTF-8: Unicode classes/case, locale collation
    OTHER = auto()    # non-UTF-8 non-C (e.g. latin1 locales): documented fallback

@dataclass(frozen=True)
class LocaleProfile:
    ctype_name: str        # effective LC_CTYPE (e.g. "en_US.UTF-8")
    collate_name: str      # effective LC_COLLATE (independent of ctype)
    ctype_mode: LocaleMode
    collate_mode: LocaleMode

class LocaleService:
    profile: LocaleProfile

    # --- character-class membership (LC_CTYPE) ---
    def in_class(self, ch: str, name: str) -> bool: ...
        # name in {alpha,digit,alnum,upper,lower,xdigit,blank,space,
        #          punct,graph,print,cntrl}. C mode -> ASCII table;
        # UTF8 -> Unicode predicate/category; OTHER -> ASCII table + doc.

    # --- case mapping (LC_CTYPE), length-safe 1:1 like bash ---
    def upper(self, s: str) -> str: ...   # C mode: ASCII-only; UTF8: simple_upper
    def lower(self, s: str) -> str: ...
    def toggle(self, s: str) -> str: ...

    # --- collation (LC_COLLATE) ---
    def collate_key(self, s: str): ...    # sort key: strxfrm in UTF8; identity in C
    def compare(self, a: str, b: str) -> int:  # for [[ < ]] / [ \< ]
        ...                               # strcoll in UTF8; codepoint cmp in C

    # --- range membership (globasciiranges-aware) ---
    def in_range(self, ch: str, lo: str, hi: str) -> bool: ...
        # ASCII/codepoint when globasciiranges on (bash default) — current behavior

    # --- lifecycle ---
    def reinit_from_env(self, state) -> None: ...  # recompute profile + setlocale
```

**Consumers** (each replaces a local ASCII assumption with a service call):
- `extglob._bracket_to_regex` / `_bracket_match`: `in_class`, `in_range`
  (the one class-interpretation chokepoint — changing it fixes `case`/`[[`/
  `${#}`/glob together).
- `glob.py` result sorting (`:207`, `:175`, `:447`), `extglob.py:595`:
  `key=locale.collate_key`.
- `enhanced_test_evaluator.py:135` and `test_command.py:467`: `compare`.
- `parameter_expansion.py` case ops and `operators.py` `@U/@L/@u`,
  `scope.py`/`array.py` `declare -u/-l`: `upper`/`lower`/`toggle`
  (and fix the `@U` `ß`→`SS` bug by routing it through `upper`).
- `translate_posix_classes` (the `[[ =~ ]]` ERE path): unchanged for ASCII, but
  UTF-8 classes in `=~` hit the same regex wall (§4.5) — see open questions.

`simple_upper`/`simple_lower`/`toggle_case` in `unicode_support.py` remain the
UTF-8-mode implementation; the service wraps them with the C-mode ASCII gate.

### 5.2 Locale-state ownership (what to read, when to react)

The service computes **two independent effective locales** from the environment
with bash precedence:
- effective LC_CTYPE = `LC_ALL or LC_CTYPE or LANG or "C"`
- effective LC_COLLATE = `LC_ALL or LC_COLLATE or LANG or "C"`

Recommended **bash-faithful subset, staged**:
- **Stage 1 (recommended first, high value, low risk):** read the environment
  **once at startup**, compute the profile, and call `setlocale(LC_CTYPE)` +
  `setlocale(LC_COLLATE)` once. This alone fixes the common real-world case
  (running psh under `LANG=en_US.UTF-8`) and is enough to close the finding for
  most users.
- **Stage 2 (bash-faithful dynamic behavior):** hook `state.set_variable` /
  unset for the names `LC_ALL, LC_CTYPE, LC_COLLATE, LANG` so an assignment
  re-runs `reinit_from_env()`. This matches probe 2g (assignment reacts even
  without `export`). Precedence and independence fall out of the two-effective
  computation.
- **Deferred (edge):** a per-command prefix on a *builtin* (`LC_ALL=C [[ ... ]]`
  — which is not even legal bash syntax; the probe used a nested external bash).
  The temp-env path would need to reinit-and-restore around builtin execution.
  Low value; document as a known limitation.

### 5.3 Modes

- **C / POSIX** → ASCII class tables (exactly today's `_POSIX_CLASSES`),
  ASCII-only case mapping, codepoint collation. Byte-identical to current psh and
  to bash-C on all platforms. This is the fast path (no `setlocale` needed, no
  per-char libc/Unicode call).
- **`*.UTF-8`** → Unicode class predicates (pure-Python default, or ctypes
  alternative), UTF-8 case mapping (`simple_*`), `strxfrm`/`strcoll` collation.
- **OTHER** (non-UTF-8, non-C — e.g. `en_US.ISO8859-1`): documented fallback —
  use ASCII class tables + `strxfrm` collation (collation still works via the
  locale module). Full 8-bit-locale ctype fidelity is a non-goal; document it.

### 5.4 Compatibility with the finding #6 pattern engine

The pattern-AST node set in finding #6 gains locale awareness for free if:
- `CharacterClass(name, negated)` matches by `locale.in_class(ch, name)`.
- `CharRange(lo, hi)` matches by `locale.in_range(ch, lo, hi)`.
- case-insensitive matching (`nocasematch`) folds via `locale.lower` on both
  sides rather than `str.casefold()` (which is Unicode-wide even in C mode).
- pathname walkers sort with `locale.collate_key`.

Design the service **first** (or alongside), so the pattern engine consumes it
rather than re-deriving ASCII ranges. The memoized matcher (finding #6) should
cache class membership per `(codepoint, name, profile-generation)` (see §7).

### 5.5 `globasciiranges`

Register `globasciiranges` as a shopt (default **on**), so `shopt
globasciiranges` stops erroring. Implement only the on-behavior (ASCII/codepoint
ranges — already how psh behaves). If off + UTF-8, ranges would use collation
order; defer that as an edge and document it.

---

## 6. Staged implementation plan (each stage bash-pinnable)

**Stage 0 — pin current behavior (tests first, no code).** Add a differential
corpus (`tests/conformance` where a user-guide claim exists, else unit) covering
every §2 row across `C`, `C.UTF-8`, `en_US.UTF-8`, running psh vs live local
bash. Promote the probe battery into `tests/behavioral/golden_cases.yaml`
(`--compare-bash`). This locks in that C-locale behavior is unchanged.

**Stage 1 — collation (cleanest, highest confidence, stdlib-only).** Introduce
`LocaleService` with startup env read + `setlocale`. Implement `collate_key`/
`compare` and wire glob result sorting, `[[ < ]]`, `[ \< ]`. This is provably
faithful (§4.1) and touches no pattern matching. Gate: glob-ordering and
comparison probes now match local bash under `en_US.UTF-8`.

**Stage 2 — case mapping mode gate + `@U` fix.** Add C-mode ASCII gate to
`upper`/`lower`/`toggle`; route `${x^^}`/`,,`/`~~`, `declare -u/-l`, and
`${x@U/@L/@u}` through the service. Fixes the C-locale over-eager case-mapping
and the `ß`→`SS` `@U` bug.

**Stage 3 — class membership (the finding-#5 core).** Implement `in_class`
(pure-Python mode-switched backend by default). Route the bracket matcher: ASCII
ranges + C mode stay on regex; UTF-8-mode brackets containing a POSIX class use
the per-char predicate matcher (§4.5 bridge). Gate: §2a/2b/2c membership rows
match local macOS bash; assert glibc divergences (`٣`/NBSP/punct edges) as
`documented_difference`.

**Stage 4 — dynamic reactivity (Stage 2 of §5.2).** Hook `LC_*`/`LANG`
assignment/unset to `reinit_from_env`. Gate: §2g rows.

**Stage 5 — converge with finding #6.** When the pattern-AST engine lands, move
`CharacterClass`/`CharRange`/nocase-fold onto the service; retire the bridge.
Add the class-membership cache and adversarial + locale-matrix pattern tests.

Optional throughout: offer the ctypes `iswctype` backend behind a config/env
switch for users who need exact host-bash parity; keep pure-Python as default.

---

## 7. Risk register

| risk | severity | mitigation |
|---|---|---|
| `setlocale` is process-global / not thread-safe | med | bash is also global; psh single-threaded; snapshot+restore in `Shell.close`; document embedding non-goal |
| macOS vs Linux class divergence (`٣` digit, NBSP space, punct) | med | pure-Python matches macOS local gate; assert `documented_difference` for glibc; nightly is backstop; ctypes backend erases it if adopted |
| stdlib `re` can't express Unicode classes (regex wall) | high | per-char predicate bridge (§4.5); full fix via finding #6 engine |
| per-char `in_class` in glob hot loops | med | (a) ASCII/C fast path avoids all calls; (b) `lru_cache` on `(codepoint,name,gen)`; (c) precompile per-class predicate; (d) finding-#6 memoized matcher |
| `C.UTF-8` semantics differ macOS vs glibc (digit) | med | it is genuinely platform-divergent in bash too; track host via locale module; document |
| macOS APFS case-insensitivity corrupts glob/collation probes (`e`/`E`) | low (test-only) | never create case-colliding filenames in probes; noted in §2c |
| non-UTF-8 8-bit locales (OTHER mode) | low | documented fallback (§5.3); non-goal for full fidelity |
| reinit cost on every `LC_*` assignment | low | assignments are rare; recompute only on the four special names |
| `strxfrm` on invalid/undecodable input | low | wrap; fall back to codepoint key on `locale.Error`/`ValueError` |

## 8. Non-goals (explicit)

1. Full ctype fidelity in **non-UTF-8, non-C** (8-bit) locales.
2. Thread-safe locale switching for **embedded multithreaded** psh hosts.
3. Locale-aware **number/monetary/time** formatting beyond what already exists
   (`printf`, `\D{}` prompt) — this service is ctype + collation only.
4. `LC_MESSAGES` / gettext (`$"..."`) message translation — a separate concern.
5. Per-command locale prefix affecting a **builtin's** classification
   (`LC_ALL=C [[ ... ]]`) — deferred edge (§5.2).
6. Making `[[:digit:]]` byte-identical to glibc on the local macOS gate without
   the ctypes backend — accepted documented difference under the default backend.
7. Changing range semantics when `globasciiranges` is off in a UTF-8 locale.

---

## 9. Open questions for the orchestrator / maintainer

1. **Backend choice (the pivotal decision).** Default to the **pure-Python
   mode-switched** backend (clean, educational, matches macOS local gate, a few
   documented glibc divergences), or the **ctypes `iswctype`** backend
   (byte-identical to host bash on both platforms, but un-Pythonic and
   `setlocale`-dependent)? Recommendation: pure-Python default, ctypes offered
   behind a switch — but this is a values call (educational clarity vs exact
   parity) that the maintainer should make.
2. **`[[:digit:]]` policy.** Under UTF-8, follow macOS bash / Python (`٣` is a
   digit) or POSIX/glibc (`0-9` only)? Affects whether a conformance test can be
   `assert_identical_behavior` on both platforms.
3. **How much dynamic reactivity to ship.** Stage 1 (startup only) may be
   sufficient for the finding; Stage 4 (assignment reactivity) is more faithful
   but adds a `set_variable` hook. Ship Stage 1 alone first, or bundle?
4. **Sequencing vs finding #6.** Build the locale service before, alongside, or
   as part of the pattern-engine campaign? The regex wall (§4.5) argues they are
   coupled; the collation/case stages (1–2) are independent and can ship now.
5. **User-facing `sorted()` sites** (`declare -p`, `export`, `alias`, completion,
   `${!prefix*}`, assoc-array keys): route through `collate_key` for bash parity,
   or leave codepoint-sorted? bash itself is inconsistent here.

---

## 10. Locale-availability caveats on this host

- Host: macOS (Darwin 25.x), bash **5.2.26** (`/opt/homebrew/bin/bash`),
  Python 3.14.
- `locale -a` includes `C`, `C.UTF-8`, `POSIX`, and a full set of `*.UTF-8`
  (incl. `en_US.UTF-8`). **No non-UTF-8 8-bit locales** (`en_US.ISO8859-1` etc.)
  are installed — the OTHER-mode fallback cannot be probed locally; reason about
  it, defer to nightly/manual.
- Python `setlocale` accepts `C`, `C.UTF-8`, `en_US.UTF-8`, `POSIX` here.
- **macOS libc is more permissive than glibc** for `iswctype` (`٣`/`３` digit,
  NBSP space) — the primary macOS-vs-Linux divergence axis; the local gate sees
  macOS behavior, the nightly sees glibc. All ctype conclusions above are pinned
  to macOS bash; Linux behavior is reasoned from POSIX + glibc knowledge and must
  be confirmed on the nightly.
- **APFS is case-insensitive** — glob/collation probes must avoid case-colliding
  filenames (e.g. `e` and `E`).
```
