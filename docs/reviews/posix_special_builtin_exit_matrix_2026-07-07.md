# POSIX-mode special-builtin exit-on-error matrix (bash 5.3.15)

Status: **IMPLEMENTED in v0.673.0** (fix/posix-special-exit, 2026-07-08 —
`SpecialBuiltinUsageError` + one executor policy, plus bash's suppression
classes in errexit-suppressed contexts). Originally deferred / found-not-fixed
during the builtins-contracts campaign (fix/builtin-contracts, 2026-07-07) and
tracked as follow-up task #14.

**Retuned to bash 5.3 in Improvement Program 2026-09 slot 2.2** (gate rows
G18–G22): bash 5.3 widened the exit set to the OPERAND errors and made the
`eval`/`.` boundary transparent to the suppression — CHANGES, bash-5.3-alpha,
"1. Changes to Bash" item jj ("POSIX special builtins now exit the shell in
posix mode on more failure cases") and item nnnnn ("Fix posix-mode cases where
failure of special builtins did not cause the shell to exit"). The rows and
the rule below are the 5.3.15 values; the 5.2 shape they replaced is named
inline so a reader of the old campaign can find it.

## What this is (and what it is NOT)

There are **two distinct** "a special builtin errored → abandon input" behaviors
in bash. The campaign delivered the first; this doc records the second.

1. **exit/shift usage-error DISCARD (delivered).** `exit 7 8` (valid first
   operand + extra) and `shift 1 2` report the usage error, discard the
   *current input unit*, and do NOT exit the shell — in BOTH default and POSIX
   mode. Implemented as the typed outcome `special_builtin_usage_discard`
   (`psh/core/internal_errors.py`), reusing the `TopLevelAbort(errexit_immune=
   True, contain_nested=False)` / `SystemExit`-under-`command_mode` machinery.

2. **POSIX-mode special-builtin EXIT-on-error (this doc — implemented in
   v0.673.0).** With `set -o posix`, certain special-builtin errors make a
   *non-interactive* shell **exit** entirely (later lines do not run). Note
   one refinement discovered during implementation: bash SUPPRESSES the exit
   for the suppressible class (invalid option, `return`, and the 5.3 operand
   errors) in errexit-suppressed contexts (`if`/`while` conditions, left of
   `&&`/`||`, after `!`, through function calls), while the
   eval/dot-syntax/missing-dot-file/readonly-assignment class exits even when
   guarded. On bash 5.3 the suppression also reaches ACROSS an `eval`/`.`
   boundary (under 5.2 those boundaries reset it); a TRAP ACTION is the one
   boundary it does not cross, because bash runs the action between commands.

## The matrix (bash 5.2.26, probe battery `tmp bcontract/matrix.py`)

Method: each case run as a script FILE `set -o posix\n<cmd>\necho survived`.
`survived` printed ⇒ shell continued (only the line/unit affected). `survived`
ABSENT + nonzero rc ⇒ shell exited.

| special builtin error | default mode | POSIX mode |
| --- | --- | --- |
| invalid OPTION: `set -q` | continue (rc 2, survives) | **EXIT rc 2** |
| invalid OPTION: `export -q` | continue | **EXIT rc 2** |
| invalid OPTION: `readonly -q` | continue | **EXIT rc 2** |
| invalid OPTION: `unset -q` | continue | **EXIT rc 2** |
| invalid OPTION: `trap -q` | continue | **EXIT rc 2** |
| `return` at top level | continue (rc 2) | **EXIT rc 2** |
| `. /nonexistent` (dot missing file) | continue | **EXIT rc 1** |
| `eval 'if'` (eval syntax error) | continue | **EXIT rc 2** |
| assign to readonly via `readonly r=2` | continue | **EXIT rc 1** |
| bad identifier: `export 1bad=x` | continue | **EXIT rc 1** (5.3; 5.2 continued) |
| bad identifier: `readonly 1bad=x` | continue | **EXIT rc 1** (5.3; 5.2 continued) |
| `export 1bad=x 2bad=y` | both diagnosed, continue | ONE diagnostic, **EXIT rc 1** |
| bad signal: `trap 'x' NOSUCHSIG` | continue | continue (NO exit) |
| `unset r` on a readonly r | continue | **EXIT rc 1** (5.3; 5.2 continued) |
| `unset -f f` on a readonly f | continue | **EXIT rc 1** (5.3; 5.2 continued) |
| `unset a[0]` on a readonly array | continue | **EXIT rc 1** (5.3; 5.2 continued) |
| `unset r s`, both readonly | both diagnosed, continue | BOTH diagnosed, **EXIT rc 1** |
| `unset a[1]` on a scalar | continue rc 1 | continue rc 1 (NO exit) |
| `unset 1bad` (no `-v`) | continue (no error at all) | continue (no error at all) |
| `unset -v 1bad` (bad identifier) | continue | **EXIT rc 1** (5.3; 5.2 continued) |
| `unset -v 1bad 2bad` | both diagnosed, continue | BOTH diagnosed, **EXIT rc 1** |
| EXIT trap's `$?` after any of these | the builtin's status | the builtin's status |
| guard OUTSIDE `eval`: `eval 'set -q' \|\| echo caught` | continue | suppressed, rc 0 (5.3; 5.2 exited 2) |
| guard OUTSIDE a trap action | continue | **EXIT** (the guard does not reach in) |
| `break` at top level | continue (rc 0, error msg) | continue (rc 0, silent) |
| `shift 1 2` / `exit 7 8` (too-many) | DISCARD unit (both modes — delivered) | DISCARD unit |
| `shift x` / `exit abc` (bad numeric) | shift: continue rc1; exit: EXIT rc2 | same |

### Rule (what a correct implementation must encode)

In POSIX mode, a non-interactive shell exits when a special builtin reports a
**usage/syntax error** — an invalid option, a syntax error in `eval`/`.`, a
`return`/loop-word used out of context, an assignment to a readonly variable,
or a missing sourced file — and, since bash 5.3, on the fatal **operand
errors**: an invalid identifier given to `export`/`readonly` (which also ends
the operand loop at the FIRST one, in posix mode only) and an `unset` that
refuses a readonly variable, array, array element or function, or refuses an
`unset -v` operand whose name is not a valid identifier (both diagnosed for
every operand, then the exit). It still does NOT exit for a bad `trap` signal
spec, an `unset` of a non-array subscript, or a bad name given to `unset`
WITHOUT `-v` (there bash falls back to a function lookup and stays silent).
The EXIT trap observes the builtin's status as `$?`, not 0.
The exit status is the builtin's own (2 for option/syntax usage errors, 1 for
the readonly, identifier and dot cases). `break`/`continue` out of a loop are
a silent no-op in POSIX mode.

Live pins: `tests/conformance/posix/test_posix_special_builtin_exit_conformance.py`
(three input modes each), `tests/integration/test_posix_special_builtin_exit.py`
(row tables), `tests/unit/core/test_special_builtin_exit_policy.py` (the owner).

## Why it was deferred

Reproducing this faithfully requires each special builtin to classify its own
failures as **usage-vs-operand** and signal that to one executor policy — i.e.
the finding-15 expected-error taxonomy (`usage error` / `operational failure`
/ `assignment failure` / ...). A heuristic like "special builtin returned 2 →
exit in posix" over-fires (e.g. `export 1bad` returns 1 but must NOT exit;
`test`-style rc 2 from non-specials is unrelated). Doing it partially risks
inconsistency and posix-mode regressions for a low-frequency mode.

The clean approach (task #14): introduce a `SpecialBuiltinUsageError` typed
outcome raised by special builtins on usage/syntax errors, and one executor
policy that, in POSIX + non-interactive context, turns it into a shell exit
with the carried status. The `special_builtin_usage_discard` helper and the
`TopLevelAbort`/`command_mode` machinery this campaign added are the seam to
build on.
