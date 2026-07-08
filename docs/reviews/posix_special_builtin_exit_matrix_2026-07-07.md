# POSIX-mode special-builtin exit-on-error matrix (bash 5.2.26)

Status: **IMPLEMENTED in v0.673.0** (fix/posix-special-exit, 2026-07-08 —
`SpecialBuiltinUsageError` + one executor policy, plus bash's suppression
classes in errexit-suppressed contexts). Originally deferred / found-not-fixed
during the builtins-contracts campaign (fix/builtin-contracts, 2026-07-07) and
tracked as follow-up task #14.

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
   for the invalid-option/`return` class in errexit-suppressed contexts
   (`if`/`while` conditions, left of `&&`/`||`, after `!`, through function
   calls), while the eval/dot-syntax/missing-dot-file/readonly-assignment
   class exits even when guarded; `eval`/`.` boundaries reset suppression
   for their inner text.

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
| bad identifier: `export 1bad=x` | continue | continue (NO exit) |
| bad identifier: `readonly 1bad=x` | continue | continue (NO exit) |
| bad signal: `trap 'x' NOSUCHSIG` | continue | continue (NO exit) |
| `unset r` on a readonly r | continue | continue (NO exit) |
| `unset 1bad` (bad identifier) | continue (no error at all) | continue |
| `break` at top level | continue (rc 0, error msg) | continue (rc 0, silent) |
| `shift 1 2` / `exit 7 8` (too-many) | DISCARD unit (both modes — delivered) | DISCARD unit |
| `shift x` / `exit abc` (bad numeric) | shift: continue rc1; exit: EXIT rc2 | same |

### Rule (what a correct implementation must encode)

In POSIX mode, a non-interactive shell exits when a special builtin reports a
**usage/syntax error** — an invalid option, a syntax error in `eval`/`.`, a
`return`/loop-word used out of context, an assignment to a readonly variable,
or a missing sourced file. It does NOT exit for **operand/semantic errors** —
an invalid identifier to `export`/`readonly`, a bad `trap` signal spec, an
`unset` of a readonly, or an `unset` of a non-identifier. The exit status is
the builtin's own (2 for option/syntax usage errors, 1 for the readonly/dot
cases). `break`/`continue` out of a loop are a silent no-op in POSIX mode.

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
