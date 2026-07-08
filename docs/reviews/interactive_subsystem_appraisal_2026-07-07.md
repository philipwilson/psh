# Interactive Subsystem Appraisal — 2026-07-07

## Scope

A fresh, probe-verified appraisal of psh's **interactive** subsystem at
`main` @ `968a3af4` (v0.662.0), graded against live bash 5.2.26
(`/opt/homebrew/bin/bash`). Every behavioral claim below was reproduced by
driving *both* shells under a real pseudo-terminal (a `pty.openpty()` harness
that feeds keystrokes and captures raw output; see the Checks-Run appendix) and
diffing `(stdout, stderr)`. Findings are separated into CONFIRMED (reproduced)
and PLAUSIBLE (could not fully verify — reason given).

The review covered:

- the REPL loop (`repl_loop.py`) and its EOF / `ignoreeof` policy
  (`eof_policy.py`);
- the raw-mode line editor and its five decomposed components — buffer model
  (`edit_buffer.py`), renderer (`line_renderer.py`), input decoder
  (`key_decoder.py`), history navigation/search (`history_nav.py`), key
  dispatch (`keybindings.py`);
- history storage/persistence (`history_manager.py`) and history expansion
  (`history_expansion.py`);
- prompt rendering (`prompt.py`, `prompt_manager.py`);
- multi-line input and continuation prompts (`multiline_handler.py`);
- interactive-mode job-control notifications (the seam into
  `executor/job_control.py` and `signal_manager.py`);
- tab completion (`tab_completion.py`) at the editor boundary;
- the `psh/shell.py` → `InteractiveManager` interactive entry;
- `psh/interactive/CLAUDE.md` and the user guide
  (`docs/user_guide/14_interactive_features.md`).

## Executive Judgment

This is a **strong, textbook-quality** subsystem — the best-architected of the
psh subsystems reviewed so far. The line editor is cleanly decomposed into
pure, individually-testable components; history expansion reproduces bash's
event/word/modifier grammar with near-perfect fidelity; prompt-escape rendering
is essentially byte-identical to bash; UTF-8 editing, multi-line paste, vi mode,
and adversarial input are all handled without a single crash across the probe
battery.

The defects are narrow. There is **one genuine functional break** — `set -b`
(`set -o notify`) silently discards *all* background-job completion notices,
which is the exact opposite of the option's purpose and is contradicted by the
user guide. The rest are cosmetic bash-fidelity gaps (reverse-search prompt
text, an extra blank line before "Done", the Ctrl-D farewell) and one
deliberate-but-divergent design choice (Ctrl-R's Return accepts without
executing).

| Dimension | Grade | One-line assessment |
| --- | --- | --- |
| Correctness vs bash | B+ | History/prompt/editing are faithful; `set -b` notices are the one real break. |
| POSIX/bash interactive semantics | A− | Event designators, word designators, modifiers, `ignoreeof`, multi-line completeness all match. |
| Robustness (malformed input, signals, EOF) | A | No crash on NULs, split UTF-8, long/wrapping lines, or multi-line paste; EOF/`ignoreeof` correct. |
| Determinism / testability | A | Pure layout math, injected history list, pinned snapshot/pipe/PTY tiers; a coordinator owning policy. |
| Code clarity (educational goals) | A | Narrow component contracts, thorough docstrings, one reader of stdin and one writer of ANSI. |
| Doc accuracy | B | CLAUDE.md is excellent; the user guide over-claims `set -o notify` and shows a prompt string psh does not render. |

**Overall: B+** (architecture and clarity are A-grade; one functional defect
behind an opt-in option plus a cluster of cosmetic divergences hold the
bash-correctness line at B+).

## What Is Strong

### The line editor is genuinely well-decomposed

`LineEditor` is a coordinator that owns *policy* (mode state, the action
dispatch table, completion glue) and delegates every mechanism to a component
with a narrow contract: `EditBuffer` (text/cursor/kill-ring/undo, mutations
return a repaint signal), `LineRenderer` (the *only* ANSI writer), `KeyDecoder`
(the *only* stdin reader), `HistoryNavigator`/`HistorySearch` (pure over an
injected history list), `keybindings.py` (key→action names). This is the design
the builtins subsystem was told to aspire to, already realized here. Geometry is
pure math in `line_layout.py`, so wrapping is unit-testable without a tty, and
the decoder is pinned by pipe-fed byte-stream tests.

### UTF-8 is handled correctly at the editor layer

`KeyDecoder._read_char` (`key_decoder.py:280-287`) reads the raw fd in blocks
and decodes the *whole* block (`data.decode('utf-8', errors='replace')`),
buffering the surplus characters so `select()` and reads stay in sync. This is
the correct approach and stands in deliberate contrast to the `read` builtin's
byte-at-a-time decode flagged in the builtins appraisal — typing `é`,
backspacing over a multibyte char, and moving the cursor across one all behaved
identically to bash (probes 4.1–4.3).

### History expansion is near-perfect

The full bash grammar is implemented and reproduced faithfully: `!!`, `!n`,
`!-n`, `!string`, `!?str?`; word designators `:0 :^ :$ :* :n-m :n* :n-` and the
bare `^ $ *` sigils; the `:h :t :r :e :s/// :gs// :& :p` modifiers; `^old^new^`
quick substitution; suppression inside single quotes / after backslash / inside
`${…}`, `$((…))` and `[…]`; and expansion *through* double quotes. All 29
history-expansion probes matched bash on the expanded text, including the
`event not found` / `bad word specifier` error paths (§4.1).

### Prompt-escape rendering is essentially byte-identical

Every deterministic PS1 escape matched bash (`\w \W \h \H \u \s \$ \a \j \nnn
\n \\ \! \# \[ \]`, unknown-escape pass-through, `\D{…}` handling), including the
readline non-printing markers and octal sequences (§4.2). The escape-then-
`$`-expansion two-pass with NUL-sentinel protection (`prompt.py:63-103`) is a
careful, bash-verified design shared with `${var@P}`.

### Multi-line completeness is parser-driven and robust

`MultiLineInputHandler` delegates the "is this command complete?" decision to
the shared `CommandAccumulator`, the same oracle the script/`-c` reader uses, so
interactive and non-interactive line-gathering can never disagree. `if`/`for`/
unclosed-quote/trailing-pipe continuations, and multi-line commands recalled as
a single editable line, all matched bash (§4.3).

### Careful signal and EOF discipline

Signal handlers are installed only at the two process entry points (not at
manager construction), the interactive loop restores default dispositions on
every exit path, and reaping uses the async-signal-safe self-pipe pattern.
`ignoreeof`/`IGNOREEOF` semantics (consecutive-EOF counter, reset by a non-blank
command, the "Use \"exit\" to leave the shell." message, the stopped-jobs guard)
reproduced bash exactly (§4.4).

## Critical Findings

### 1. HIGH — `set -b` / `set -o notify` silently drops every background-job completion notice

**Files:** `psh/interactive/repl_loop.py:63-68`,
`psh/interactive/signal_manager.py:334-355`,
`psh/executor/job_control.py:1008-1013`.

`set -b` (a.k.a. `set -o notify`) is supposed to report background-job
completion *more* eagerly than the default (asynchronously, as soon as the child
is reaped, instead of at the next prompt). In psh it does the opposite: it
suppresses the notice **entirely**.

Root cause is a two-sided gap:

1. The REPL loop only prints deferred notices when `notify` is **off**:
   ```python
   # repl_loop.py:64
   if not self.state.options.get('notify', False):
       self.job_manager.notify_completed_jobs()
   ```
2. The async reaper `process_sigchld_notifications` reaps the child and calls
   `job.update_state()` but **never** calls `_print_completion_notice` and never
   consults the `notify` option (`signal_manager.py:338-341`).

The only code that honors `notify` for immediate notification lives in the
*synchronous* wait path (`job_control.py:1008-1013`), which background jobs never
traverse — they are reaped only via the SIGCHLD self-pipe. Net effect: with
`set -b`, a completed background job is reaped, marked `DONE`, and then neither
notified nor removed from the job table (`notify_completed_jobs` is the only
caller of `remove_job` for finished jobs), so it also leaks as a stale `DONE`
entry.

**CONFIRMED repro** (PTY, `--norc`, PS1 pinned):

```
set -b
sleep 0.2 &          # both: "[1] <pid>"
sleep 0.7            # bg job finishes during this
echo AFTER1
echo AFTER2
```

| Shell | Output around the completion |
| --- | --- |
| bash | `[1] <pid>` … then **`[1]+  Done                    sleep 0.2`** printed asynchronously right after the prompt |
| psh  | `[1] <pid>` … **no "Done" line ever appears** (two further prompts pass, still nothing) |

With `set -b` *off*, psh prints the notice correctly at the next prompt — so
only the opt-in path is broken. The user guide
(`docs/user_guide/14_interactive_features.md:836`) advertises
`set -o notify  # Immediate job notifications`, so the documented behavior is the
one that fails.

**Blast radius:** limited to shells that opt into `set -b`/`set -o notify`, but
for those it is a total, silent functional loss. This is the single
highest-value fix in the subsystem.

**Fix sketch:** in `process_sigchld_notifications`, after `job.update_state()`,
when `notify` is set and a background job transitioned to `DONE`, call
`_print_completion_notice(job)`, mark it notified, and reap it — mirroring the
synchronous path. (psh cannot make the notice truly *immediate* while the user
sits idle in `read_key`, because the editor's `select()` multiplexes only stdin
and the SIGWINCH pipe, not the SIGCHLD pipe — see Finding 6 — but it can and
should print at the next reaping opportunity instead of dropping it.)

## Medium Findings

### 2. MED — Ctrl-R: Return accepts the match but does not execute it

**File:** `psh/interactive/history_nav.py:179-180, 193-201`.

In bash/readline, terminating an incremental search with Return runs
`accept-line`: the matched command is executed on a *single* Enter. psh's
`HistorySearch.feed` maps Return to `accept()` with status `'accepted'`, which
only copies the match into the edit buffer; a **second** Enter is required to
run it. The docstring states this is intentional ("it does NOT execute — a
second Enter does").

**CONFIRMED repro** (PTY, generous 0.6 s settle):

```
echo MARKERCMD
true
<Ctrl-R> MARK <Enter> exit<Enter>
```

- bash: `echo MARKERCMD` executes on the Enter → prints `MARKERCMD`; `exit` runs
  separately.
- psh: the Enter only accepts; the following `exit` is appended to the buffer,
  producing and executing `echo MARKERCMDexit` → prints `MARKERCMDexit`.

The surprising part for users is not the extra keystroke but that *subsequent
typing lands on the recalled line* rather than a fresh prompt, so a
muscle-memory "Ctrl-R, type, Enter, type next command" sequence concatenates.
Ctrl-G abort and incremental refine/step all matched bash — only the Return
disposition diverges. Recommend making Return in isearch dispatch `accept-line`
(accept **and** execute) to match readline; keep the "accept-only" behavior for
the movement/other-control-key terminators, which already redispatch correctly.

## Low Findings

### 3. LOW — reverse-search prompt text differs from bash

**File:** `psh/interactive/history_nav.py:248-252`. psh renders
`(bck-i-search)` / `(fwd-i-search)` / `(failed-bck-i-search)`; bash/readline
render `(reverse-i-search)` / `(i-search)` / `(failed reverse-i-search)`. This
is a cosmetic divergence, but the user guide itself prints the bash string
(`docs/user_guide/14_interactive_features.md:151`:
`(reverse-i-search)\`git': …`), so the doc and the implementation disagree.
CONFIRMED (§4.1 Ctrl-R probes). Either match bash's wording or correct the doc;
matching bash is preferable given the shell's stated compatibility goal.

### 4. LOW — an extra blank line precedes each "[N]+ Done" notice

**File:** `psh/executor/job_control.py:623`. `_print_completion_notice` emits
`f"\n[{job.job_id}]+  {label:<24}{job.command}"` — the leading `\n` produces a
blank line that bash does not. CONFIRMED: with `set -b` off, psh prints
`echo AFTER1\n\n[1]+  Done …` where bash prints `echo AFTER1\n[1]+  Done …`.
Same line also hardcodes the `+` current-job marker, whereas bash (and psh's own
`notify_stopped_jobs`, `job_control.py:688`) select `+`/`-`/` ` by
current/previous status — so a Done notice for a non-current job shows the wrong
marker. Both are cosmetic.

### 5. LOW — Ctrl-D exit prints a blank line instead of `exit`

**File:** `psh/interactive/repl_loop.py:100`. On an EOF that actually exits, bash
echoes `exit`; psh runs `print()` (a bare newline). CONFIRMED (§4.4). Minor
farewell-message divergence.

### 6. LOW — a failed `:s` history substitution is reported as "bad word specifier"

**File:** `psh/interactive/history_expansion.py:595-597`. When the `old` text of
a `:s/old/new/` modifier is not present in the selected line, `_mod_subst`
returns `_BAD_WORD_SPECIFIER`, so psh prints `psh: :: bad word specifier`; bash
prints `bash: :s/old/new/: substitution failed`. Both abort the expansion (no
command runs), so this is only an error-taxonomy/wording divergence. CONFIRMED
(§4.1, `!!:s/alpha/OMEGA/`). The `^old^new^` quick-substitution path *does*
report "substitution failed" correctly; only the `:s` modifier conflates the two
error classes.

### 7. LOW (deliberate) — contextual continuation prompts diverge from bash's flat PS2

**File:** `psh/interactive/multiline_handler.py:101-104`. psh renders
`if> `, `for> `, `for then> ` etc. from the parser's open-construct trail, where
bash always shows the plain `PS2` (`> `). This is a documented psh teaching
feature, not a bug; noted for completeness because it is a visible divergence a
bash user will notice. CONFIRMED (§4.3).

## Plausible / Unverified

### P1. PLAUSIBLE (LOW) — split multibyte UTF-8 across a read() boundary

`KeyDecoder._read_char` (`key_decoder.py:280-287`) decodes each 4096-byte
`os.read` independently with `errors='replace'`. A multibyte character whose
bytes straddle a read boundary — a paste whose length crosses 4096 exactly at a
character, or byte-dribbled input — would decode to replacement characters.
Single keypresses and ordinary pastes arrive in one burst well under 4096 bytes,
so this is very hard to hit interactively; I could not construct a reliable PTY
repro (the tty layer coalesces). Flagged as a latent edge, not a confirmed bug.

### P2. PLAUSIBLE (LOW) — `\!` prompt escape uses list length, not a monotonic counter

`prompt.py:295-297` returns `len(state.history) + 1` for `\!`. bash's `\!` is the
history *number*, a monotonic counter that keeps climbing after `HISTSIZE`
trimming drops old entries. After the in-memory list is trimmed, psh's `\!`
would step backward where bash's would not. Deterministic-history probes matched
(§4.2), but I did not drive a trim large enough to expose the difference.

### P3. PLAUSIBLE-needs-signal-probe — Ctrl-Z suspend / terminal-control reclaim

Per the machine-discipline constraint (a release wave is active), I deliberately
did **not** fire `SIGTSTP`/`SIGCONT` at process groups. Ctrl-Z suspend, `fg`/`bg`
terminal-control transfer, and stopped-job terminal reclaim are therefore
unverified here. The code paths (`transfer_terminal_control`,
`restore_shell_foreground`, `TCSANOW` restores) read as careful and are covered
by the serial job-control test tier; a follow-up under a quiet machine should
PTY-probe them against bash.

## Recommended Improvement Plan

A small, well-scoped campaign — the subsystem needs correction, not
restructuring.

### Phase 1 — Fix the `set -b` notification break (Finding 1) [HIGH]

1. Teach `process_sigchld_notifications` to print (and reap) completed
   background jobs when `notify` is set, so the async reaper honors the option
   the REPL loop is deferring to it.
2. Route both notify paths (async reaper and synchronous wait) through one
   `_notify_and_reap(job)` helper so the "print, mark notified, remove" sequence
   cannot drift between them.
3. Add a PTY regression: `set -b; sleep 0.1 &; sleep 0.5; :` must emit exactly
   one `Done` notice; also assert `jobs` is empty afterward (no stale `DONE`
   leak). Add the mirror case without `-b`.

### Phase 2 — Close the bash-fidelity gaps [MED/LOW]

1. Make Return in Ctrl-R isearch `accept-line` (accept **and** execute)
   (Finding 2), and add a PTY test asserting single-Enter execution.
2. Match bash's search-prompt wording (`reverse-i-search`/`i-search`/
   `failed reverse-i-search`) *or* correct the user-guide example to the psh
   string — pick one and pin it (Finding 3).
3. Drop the leading `\n` from `_print_completion_notice` and compute its
   current/previous marker like `notify_stopped_jobs` does (Finding 4).
4. Emit `exit` on the Ctrl-D exit path to match bash (Finding 5).
5. Give the `:s` modifier its own "substitution failed" diagnostic distinct from
   "bad word specifier" (Finding 6).

### Phase 3 — Harden the plausible edges [LOW]

1. Make the key decoder incremental-decode across read boundaries (an
   `incrementaldecoder`) so a split multibyte char can never surface as
   replacement characters (P1) — the same shared-decoder discipline the builtins
   appraisal recommends for `read`.
2. Back `\!` with a monotonic history counter rather than list length (P2).
3. Under a quiet machine, add PTY suspend/`fg`/`bg` differential coverage (P3).

## Checks-Run Appendix

Environment: psh `main` @ `968a3af4` (v0.662.0), `python -c "import psh;
print(psh.__file__)"` → in-tree; oracle `/opt/homebrew/bin/bash` 5.2.26. All
probes ran psh with `cwd=/Users/pwilson/src/psh` (CWD-shadows-PYTHONPATH),
`--norc`, and a pinned `PS1`; bash with `--norc --noprofile -i` and a pinned
`PS1`. Each shell ran under a fresh `pty.openpty()`; the harness wrote keystroke
chunks with a settle delay, killed the child process group on completion/timeout,
and stripped ANSI for comparison. Post-run orphan sweep
(`ps -axo pid,ppid,%cpu … | awk '$2==1 && $3>50'`) was clean.

Harness + batteries live in the session scratchpad
(`pty_harness.py`, `histexp.py`, `prompt_probe.py`, `eof_edit_probe.py`,
`nav_probe.py`, `ctrlr_probe.py`, `utf_ctrl_probe.py`, `job_probe.py`,
`robust_probe.py`).

**§4.1 History expansion** (29 references, seeded identical 3-command history):
`!! !1 !2 !-1 !-2 !echo !?needle? !ls:1 !ls:2 !echo:$ !echo:^ !echo:* !echo:2-3
!echo:2* !!:s/…/…/ !ls:s/…/…/ !grep:h !grep:t !$ !^`, mid-line refs, quoted/
single-quoted/backslash suppression, `^old^new^`, `!echo:2:h`, out-of-range
`!999`/`!echo:9`, unknown `!nosuchprefix`. All matched bash on expanded text and
error class except the `:s`-failed wording (Finding 6). Also captured the
`(bck-i-search)` vs `(reverse-i-search)` prompt (Finding 3).

**§4.2 Prompt escapes** (16 PS1 forms set via the shell, rendered prompt
captured): `\w \W \h \H \u \s \$ \a \j \101\102 \n \\ \q(unknown) \! \#
\[\e[..]\]`. All deterministic escapes byte-identical to bash (`\s`=psh vs bash
and `\!` absolute counts are expected environment differences, not divergences).

**§4.3 Multi-line / navigation**: `if/then/fi`, `for/do/done`, unclosed-quote,
trailing-pipe continuations; up-arrow recall, up/up/down, multi-line→single-line
recall; 3-command paste, `if` paste, backslash-newline paste. All matched bash
(psh's `if>`/`for>` contextual prompts are the deliberate divergence, Finding 7).

**§4.4 EOF / editing**: `IGNOREEOF=2` three-Ctrl-D sequence (two "Use exit"
messages then exit — matched); plain Ctrl-D exit (Finding 5); Ctrl-A/Ctrl-E/
Ctrl-W/Ctrl-U/Alt-f/Alt-d/Ctrl-T editing (final executed command matched bash in
every case; psh full-repaints each keystroke where bash uses backspaces —
visual only); Ctrl-C line abandonment; Delete-key and mid-line Ctrl-D
forward-delete; tab completion of `/etc/hos`→`/etc/hosts`.

**§4.5 Ctrl-R accept semantics** (Finding 2): single-Enter execute (diverges) and
Ctrl-G abort (matches).

**§4.6 UTF-8 / robustness**: `echo café`, multibyte backspace, multibyte
cursor-left+insert (all matched); 150-char wrapping line, 3-command paste, `if`
paste, `set -o vi` (`ESC 0 x`), embedded NUL, backslash-newline — no crashes,
all correct.

**§4.7 Job notifications** (Finding 1, 4): bg start `[N] pid` to stderr (matched);
deferred `Done` notice with/without `set -b` (the break); `jobs` listing and `$!`
(matched).
