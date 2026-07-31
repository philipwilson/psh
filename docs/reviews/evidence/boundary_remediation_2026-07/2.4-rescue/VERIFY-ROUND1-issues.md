# Slot 2.4 verification round 1 — full issue list (overall: BOUNCE)

## Task verdict: PASS-WITH-NITS

### NIT
parser/CLAUDE.md dangling-ish pointer: the 'Remaining documented divergence' paragraph cites tests/conformance/bash/test_syntax_template_timing_conformance.py as a second pin location for the heredoc-BODY runtime divergence, but that file contains no heredoc-body pin; the pin (test_divergence_heredoc_body_cmdsub_stays_runtime) lives only in test_nested_substitution_timing_conformance.py.

EVIDENCE:
git grep -n 'heredoc' fix/remediation-2-4 -- tests/conformance/bash/test_syntax_template_timing_conformance.py -> 0 hits; psh/parser/CLAUDE.md ~line 607 names both files.

### NIT
FLIP-PINS.md rows not closed in-branch, deviating from the brief's literal 'flip to equality IN-SLOT and close the row'. The ledger records this as deliberate per an integrator ruling (file integrator-owned at ceremony), consistent with the brief's own 2026-07-30 amendment ('FLIP-PINS row correction owed at ceremony') and 2.3 precedent, but the ruling lives only in messages — integrator should confirm it and close the 4 rows (plus the location correction for test_divergence_eval_source_procsub_joined_i3, verified real: 0 hits in test_subscript_keying_conformance.py at base, actual location test_syntax_template_timing_conformance.py:212) at ceremony.

EVIDENCE:
git diff origin/main...fix/remediation-2-4 does not touch docs/reviews/evidence/boundary_remediation_2026-07/FLIP-PINS.md; slot ledger line 'FLIP-PINS.md deliberately NOT edited — integrator-owned per ruling.'

### NIT
Ledger CONFIRMATION (1) wording slightly loose: 'Corpus = 15 spellings x 2 channels x 2 parsers = 60 rows, all type=SubstitutionSyntaxError sub_origin=True' — replay shows 56 of 60 rows are that; the other 4 are the C_plain_control rows (ParseError sub_origin=False), which the ledger's own next sentence correctly describes as the discriminating control. Substance verified, phrasing overcounts.

EVIDENCE:
Replayed tmp/r24-probes/raise_site_census_channels.py at tip ca1377b7: 60 total CHOKEPOINT rows, 56 SubstitutionSyntaxError/sub_origin=True/via=_execute_buffered_command, 4 ParseError/sub_origin=False controls, 0 NEVER-REACHED.

### NIT
The ledger does not record that integrator GO was requested before its full gate and compare-bash runs (standing rule: REQUEST INTEGRATOR GO before every heavy run). The runs and results are documented; only the GO-request process fact is absent from the durable record.

EVIDENCE:
Slot ledger 'Gate (a) round 1/2' and 'compare-bash' sections state results and tmp/gate-N.txt paths but no GO request/receipt; brief rules section requires GO before every full gate/compare-bash.

## Task verdict: FAIL

### BLOCKER
HIGH-9 is only HALF consumed: the typed SubstitutionSyntaxError is picked up at only ONE of the two ParseError sites in SourceProcessor, so every substitution-body syntax error that is NOT at end-of-file (e.g. `$(fi)`) is still swallowed to rc 2 and the enclosing frame still CONTINUES — the verbatim ledger signature the slot was chartered to eliminate. All 6 flip-pin params, and every new pin the dev wrote, use an at-EOF body (`$(if)` / `<(if)`), which is exactly the code path that WAS patched; the error-kind axis was never varied. Root cause: psh/scripting/source_processor.py `_run_from_source` lines 212-225 (the accumulator trial-parse `result.error is not None` branch) calls `self._posix_syntax_abort(input_source)` at line 223 but never `self._substitution_syntax_abort(...)`; only `_execute_buffered_command` line 446 got the consumer. The producer DOES tag these errors, so this is a missing consumer site, not a missing producer.

EVIDENCE:
MECHANISM (in-process, one Shell per process, cwd=branch-tip worktree, _report_syntax_error patched to print its caller):
  === echo $(if)   [SITE] _execute_buffered_command:443   rc= 2
  === echo $(fi)   [SITE] _run_from_source:215            rc= 2
Producer tagging at tip (psh.parser.parse/tokenize): 'echo $(fi)', 'echo $(done)', 'echo $(;)', 'echo $(esac)', 'cat <(fi)', 'echo $(if fi)' ALL -> SubstitutionSyntaxError, substitution_origin=True.

REPLAYED base(1b271d77) vs tip(ca1377b7) — IDENTICAL, i.e. untouched by the slot. PATH bash /opt/homebrew/bin/bash 5.2.26; psh subprocesses PYTHONPATH-pinned to the tree under test with a psh.__file__ discriminator assert; one case per invocation.

A) The 6 flip-pin spellings with a non-at-EOF body, `-c` channel (bash_rc / psh_rc, both at BASE and at TIP):
  echo $(fi)                 127 / 2   MISMATCH
  cat <(fi)                  127 / 2   MISMATCH
  x=set; echo ${x:-$(fi)}    127 / 2   MISMATCH
  echo $(( $(fi) + 1 ))      127 / 2   MISMATCH
  a=(1 2); echo ${a[$(fi)]}  127 / 2   MISMATCH
  a[$(fi)]=v                 127 / 2   MISMATCH
(file/stdin channels agree at 2/2 — psh's uniform 2 coincides with bash's there.)

B) Frame fatality — the exact HIGH-9 signature, still live at TIP (bash_rc / psh_rc, bash_stdout | psh_stdout):
  sourced file, 2nd line `echo $(fi)`   -c    127 / 0   ['B','IB'] | ['B','IB','AFTER']
                                        file    1 / 0   ['B','IB'] | ['B','IB','AFTER']
                                        stdin   1 / 0   ['B','IB'] | ['B','IB','AFTER']
  function frame  f() { eval "echo \$(fi)"; }  -c 127 / 0   ['B'] | ['B','AFTER']
                                        file    1 / 0   ['B'] | ['B','AFTER']
                                        stdin   1 / 0   ['B'] | ['B','AFTER']
  eval 'echo X; echo $(fi)'             -c    127 / 0   ['B'] | ['B','AFTER']
                                        file    1 / 0   ['B'] | ['B','AFTER']
                                        stdin   1 / 0   ['B'] | ['B','AFTER']
  mid-buffer `echo B\necho $(fi)\n...`  -c    127 / 2   ['B'] | ['B']   (status residual)
Every one of these rows is byte-identical at base 1b271d77 and at tip ca1377b7.

C) Byte-exact single row (od -c verified probe file `eval "echo \$(fi)"; echo AFTER`, 0x65 76 61 6c ... 0a):
  psh tip -c  -> stderr 'psh: <command>:1: Parse error (line 1, column 1): Expected command ... fi', stdout 'AFTER', rc 0
  bash    -c  -> stderr "eval: line 1: syntax error near unexpected token `fi'", stdout '', rc 127

D) CONTROL proving the at-EOF half genuinely landed (so this is a gap, not a total miss): the same frame shapes with `$(if)` all MATCH bash at tip — sourced file 2nd-line 127/1/1 AFTER absent; eval-in-source 127/1/1; mid-buffer -c 127. Both parsers agree (--parser rd and --parser combinator both give 127 for `echo $(if)`, `cat <(if)`, `eval "echo \$(if)"`).

### BLOCKER
Documentation shipped in this branch states, as unconditional invariants, three claims that the branch's own tree falsifies. Two are new absolutes in live code; the third DELETES a still-live documented divergence from parser/CLAUDE.md and declares it closed. Under the campaign's no-drift rule this is worse than leaving the gap unfixed silently, because the next reader (and the next slot) will trust the invariant.

EVIDENCE:
1) psh/core/internal_errors.py:147 (substitution_abort_status docstring): "`-c` (``command_mode``) -> **127**, at any nesting depth: the direct parse, or an ``eval``/``source``/function/trap frame inside the ``-c`` string, all give 127."  FALSIFIED at tip: `psh -c "echo B; eval 'echo X; echo \$(fi)'; echo AFTER"` -> rc 0 (bash 127); `psh -c 'echo B\necho $(fi)\necho AFTER'` -> rc 2 (bash 127).

2) psh/core/exceptions.py:~128 (SubstitutionSyntaxAbort docstring): "NO frame contains it — not a function, an ``if`` condition, an ``&&`` list, ``eval``, ``source``, a trap action, nor any nesting of those".  FALSIFIED at tip: an eval frame, a source frame and a function frame ALL contain it for a `$(fi)` body (rows B above; AFTER prints, rc 0).

3) psh/parser/CLAUDE.md:606-611 — the branch REMOVES the "Remaining documented divergences" entry for the -c exit-code split and the eval/source frame fatality and replaces it with "The exit-code split and the eval/source frame fatality that used to be listed here were CLOSED by that consumer."  Both are still LIVE at tip for non-at-EOF bodies (rows A and B, replayed at ca1377b7 against bash 5.2.26). Deleting a live divergence from the subsystem doc is the drift pattern reappraisal #19 was run to stop.

4) Same family, builtins/CLAUDE.md:186-193: "A syntax error inside a `$(...)`/`<(...)` BODY is fatal to the whole shell in bash, and both builtins simply let it pass" — true only for the at-EOF subfamily; `eval 'echo $(fi)'` is contained by eval at tip.

### NIT
Producer-side docstrings still teach the pre-2.4 state and now directly contradict the branch's own parser/CLAUDE.md edit (which says the contract "is no longer inert").

EVIDENCE:
psh/parser/recursive_descent/helpers.py:227-231 (ParseError.substitution_origin comment): "psh keeps its uniform exit code 2 today (the 127/frame-abort mapping is I3's consumer job); this flag is behaviorally inert until then."  helpers.py:269-282 (SubstitutionSyntaxError docstring): "A subclass of :class:`ParseError` and therefore BEHAVIORALLY INERT today: every ``except ParseError`` / ``isinstance(e, ParseError)`` site treats it identically ... psh's uniform syntax-error exit code (2) is unchanged."  Both are false at tip for the at-EOF family. (psh/parser/parse_outcome.py:77 is still accurate and needs no change.)

### NIT
Four test symbols were renamed as part of the flips; the surviving references are all in integrator-owned campaign records, matching the 2.3 precedent (struck-through at ceremony). Listing them so the ceremony edit is mechanical.

EVIDENCE:
git grep on fix/remediation-2-4 -- psh/ tests/ docs/ tools/ (plus run_tests.py, .github/, pyproject.toml, conftest.py: zero hits):
  test_divergence_c_mode_exit_code_is_127_in_bash -> docs/reviews/boundary_campaign_close_2026-07.md:179,249; boundary_remediation_integrator_plan_2026-07-21.md:77; evidence/boundary_remediation_2026-07/2.2-rescue/INTEGRATOR-INBOX.md:50; 2.2-rescue/slot-ledger.md:363,496; evidence/.../FLIP-PINS.md:13; evidence/.../LEDGER.md:29
  test_divergence_eval_source_fatality_is_i3 -> FLIP-PINS.md:15; LEDGER.md:161
  test_divergence_eval_source_procsub_joined_i3 -> 2.3-rescue/slot-ledger.md:654,767; FLIP-PINS.md:16; LEDGER.md:161
  test_taxonomy_tuple_is_the_five_families -> no surviving reference anywhere.
New names: test_c_mode_exit_code_is_127_like_bash, test_eval_source_frame_fatality_matches_bash, test_eval_source_procsub_joined_family_matches_bash, test_taxonomy_tuple_is_the_six_families.

### NIT
Import/run proof and forbidden-file check both clean — recorded for the record.

EVIDENCE:
Detached throwaway worktree at ca1377b7 (created, used, removed with --force): `python -c 'import psh, psh.version'` -> psh.__file__ = <worktree>/psh/__init__.py, __version__ = 0.758.0 (version.py correctly untouched); `python -m psh -c 'echo ok'` -> 'ok', rc 0. `git diff --name-only origin/main...fix/remediation-2-4` filtered for version.py / CHANGELOG.md / README.md / ARCHITECTURE.md / docs/reviews/ / tests/integration/redirection/test_process_sub_closed_fds.py / the parallel session's junk files ( " 1 ", b]y, decomment.py, d/ ) -> empty. The two flip-pin conformance files are green at tip (263 passed in 69s) and the six unit files touching $(if)/<(if) are green (225 passed).

## Task verdict: PASS-WITH-NITS

### NIT
Pre-existing interactive divergence (NOT introduced by this branch, outside slot charter): at a PTY REPL, direct 'echo $(if)' sends psh into a continuation prompt (accumulator NeedMore) that swallows subsequent lines, where bash 5.2.26 prints a syntax diagnostic and continues to the next prompt. The REPL does not die (no bounce condition), and the chartered interactive rows (eval/source/procsub-eval) all survive with the SURV42 marker and clean exit in both parsers. Recommend recording as a successor/interactive-parity row.

EVIDENCE:
PTY probe at tip ca1377b7 AND base 1b271d77: 'echo $(if)' -> '> ' continuation prompt, SURV42 absent, killed at timeout; output byte-identical at both commits (only the worktree path differs). Bash control: diagnostic + SURV42=True, rc 0. Probe: scratchpad/r24_pty.py; rows eval-cmdsub/source/procsub-eval all SURV42=True rc=0 for rd and combinator at tip.

## Task verdict: FAIL

### BLOCKER
HIGH-9 IS ONLY HALF CONSUMED — the whole COMPLETE-but-INVALID class of substitution bodies still behaves exactly as on base. `psh/scripting/source_processor.py` has TWO syntax-error exits, and only one was wired to the new consumer. `_execute_buffered_command`'s `except ParseError` (tip line 441-447) calls `self._substitution_syntax_abort(e, nested)`; the OTHER one, `_run_from_source`'s trial-parse branch (tip lines 212-225, `if result.error is not None:` → `_report_syntax_error` … `self._posix_syntax_abort(input_source)` / `return exit_code`), does NOT. `CommandAccumulator.feed` returns NeedMore for `$(if)`-shaped bodies (unterminated construct → flush → the guarded path) but returns `Complete(error=SubstitutionSyntaxError, substitution_origin=True)` for any body that is complete-but-ill-formed (`$(fi)`, `$(;)`, `$(x ;; y)`, `$(then)`, `$(done)`, `$(esac)`, `$(do)`, `$(elif)`, `$(| x)`, `$(&& x)`, `$(x ;; y)`, `<(fi)` …) — that class goes down the UNGUARDED branch, so `-c` still returns 2 where bash returns 127, and `eval`/`source` frames still CONTINUE where bash aborts. This is the exact HIGH-9 signature the charter says must be closed, surviving at the branch tip. It is invisible to the flipped pins because all six params of `test_c_mode_exit_code_is_127_like_bash` and both eval-fatality pins use `$(if)`-family bodies, i.e. only the NeedMore class. The new pin `test_eval_source_frame_fatality_matches_bash` also asserts a claim that is false in general: "no non-fork frame catches it — so eval, source, functions, `if` conditions and `&&` lists all fail to contain it".

EVIDENCE:
All rows replayed one-invocation-per-case against base 1b271d77, tip ca1377b7 (discriminator-verified: psh.__file__ under each worktree, 0.758.0 both) and PATH bash 5.2.26 (/opt/homebrew/bin/bash).

Accumulator classification (tip, in-process): 'echo $(if)' -> NeedMore; 'echo $(fi)' -> Complete error=SubstitutionSyntaxError subst_origin=True; same for '$(;)', '$(then)', '$(done)', '$(esac)', '$(do)', '$(elif)', '$(| x)', '$(&& x)', '$(x ;; y)', 'cat <(fi)', 'a[$(fi)]=v', 'echo ${x:-$(fi)}', 'echo $(( $(fi) + 1 ))'.

DIRECT -c (`echo B; echo <BODY>; echo AFTER`):
  $(if)  : bash 127 | base 2 | tip 127   <- flipped (chartered)
  $(fi)  : bash 127 | base 2 | tip 2     <- UNFIXED
  <(fi)  : bash 127 | base 2 | tip 2     <- UNFIXED
  a[$(fi)]=v        : bash 127 | base 2 | tip 2
  x=set; ${x:-$(fi)}: bash 127 | base 2 | tip 2
  $(( $(fi) + 1 ))  : bash 127 | base 2 | tip 2
  a=(1 2); ${a[$(fi)]}: bash 127 | base 2 | tip 2   (control ${a[$(if)]}: tip 127)
  $(;)   : bash 127 | base 2 | tip 2
  $(x ;; y): bash 127 | base 2 | tip 2

FRAME FATALITY, `echo B; eval 'echo $(fi)'; echo AFTER`:
  -c    : bash rc=127 out='B\n'      | base rc=0 out='B\nAFTER\n' | tip rc=0 out='B\nAFTER\n'
  file  : bash rc=1   out='B\n'      | base rc=0 out='B\nAFTER\n' | tip rc=0 out='B\nAFTER\n'
  stdin : bash rc=1   out='B\n'      | base rc=0 out='B\nAFTER\n' | tip rc=0 out='B\nAFTER\n'

SOURCE frame, inner.sh = 'echo IB\necho $(fi)\necho IA':
  -c    : bash rc=127 out='B\nIB\n' | base rc=0 out='B\nIB\nAFTER\n' | tip rc=0 out='B\nIB\nAFTER\n'
  file  : bash rc=1   out='B\nIB\n' | base rc=0 out='B\nIB\nAFTER\n' | tip rc=0 out='B\nIB\nAFTER\n'
  stdin : bash rc=1   out='B\nIB\n' | base rc=0 out='B\nIB\nAFTER\n' | tip rc=0 out='B\nIB\nAFTER\n'

Non-substitution control (`fi` alone) is 2/2/2 in all three shells+channels, so the split is substitution-origin-specific — i.e. the typed fact IS available at the unguarded branch (`Invalid.error` carries substitution_origin; psh/parser/parse_outcome.py:77 says so explicitly) and is simply not consumed there.

### BLOCKER
The PRODUCER contract's own production docstrings are now falsified by this branch and were left untouched. `psh/parser/recursive_descent/helpers.py` still teaches the pre-2.4 world in the two places a reader goes to learn the contract, while `psh/parser/CLAUDE.md` was edited in this same branch to say the opposite ("it is no longer inert"). This is precisely the doc-rot class the project's CLAUDE.md singles out ("the worst rot was an embedded sketch teaching a since-fixed bug").

EVIDENCE:
psh/parser/recursive_descent/helpers.py:231-233 (the `substitution_origin` attribute doc), unchanged on this branch:
  "psh keeps its uniform exit code 2 today (the 127/frame-abort mapping
   is I3's consumer job); this flag is behaviorally inert until then."

psh/parser/recursive_descent/helpers.py:269-278 (class SubstitutionSyntaxError), unchanged:
  "A subclass of :class:`ParseError` and therefore BEHAVIORALLY INERT today:
   every ``except ParseError`` / ``isinstance(e, ParseError)`` site treats it
   identically, the rendered diagnostic is the same, and psh's uniform
   syntax-error exit code (2) is unchanged."

Both statements are false at the tip: source_processor.py:441-447 is an `except ParseError` site that now treats it differently, and `psh -c 'echo $(if)'` returns 127, not 2 (replayed above). The branch's own psh/parser/CLAUDE.md hunk asserts the contrary text: "It is the typed PRODUCER contract, and it is no longer inert".

### NIT
`psh/expansion/CLAUDE.md` was named in the brief's governing-doc list but not updated; line 374 still describes the fatality as an open residual awaiting this slot: "the frame-fatality residual is the declared I3/s2 family (slot 2.4's consumer)". With the consumer landed (partially — see BLOCKER 1), that sentence needs re-wording once the scope question is settled.

EVIDENCE:
psh/expansion/CLAUDE.md:374 (unchanged by the diff).

### NIT
Child-fork EXIT-trap `$?` inconsistency introduced by the fix and left unpinned/undeclared. A forked child now exits 1 (chartered, matches bash) but its own EXIT trap still observes 2 — on base both were 2, so the branch created the internal split. The dev's declared O4 divergence is scoped to "the FILE/STDIN channels" of the MAIN shell (psh 1 vs bash 257); this child-side face appears in the `-c` channel too and is not covered by `test_substitution_fatality_runs_exit_trap_not_err_trap`. Under the slot's own stated policy ("psh reports the real status") the child trap should see 1.

EVIDENCE:
Script: `trap 'echo PT rc=$?' EXIT; echo B; ( trap 'echo CT rc=$?' EXIT; eval 'echo $(if)' ); echo AFTER rc=$?`
  -c    : bash out='B\nCT rc=257\nAFTER rc=1\nPT rc=0\n' | base 'B\nCT rc=2\nAFTER rc=2\nPT rc=0\n' | tip 'B\nCT rc=2\nAFTER rc=1\nPT rc=0\n'
  file / stdin: identical to the -c row in all three shells.

### NIT
`psh/parser/CLAUDE.md`'s rewritten paragraph now claims the only remaining documented divergence pinned in those two conformance files is the heredoc-body one, but this branch itself adds two DECLARED divergences pinned in `test_syntax_template_timing_conformance.py` (EXIT-trap-visible `$?` in file/stdin: bash 257 vs psh 1, cited as ruling O4; trap-action own-parse status in file/stdin: bash 2 vs psh 1, cited as ruling O3). The doc understates the divergence set it points at. Also worth an integrator ACK: rulings O3/O4 are cited only inside the new test docstrings — I could not corroborate them from any committed record.

EVIDENCE:
psh/parser/CLAUDE.md hunk: "**Remaining documented divergence** … : `$(if)` inside a heredoc BODY …" vs tests/conformance/bash/test_syntax_template_timing_conformance.py new tests `test_substitution_fatality_runs_exit_trap_not_err_trap` (asserts bf.stdout=='B\nT rc=257\n' vs pf.stdout=='B\nT rc=1\n') and `test_substitution_fatality_from_a_trap_action` (asserts b.returncode==2 and p.returncode==1 for file/stdin).

### NIT
Scope ACK: the brief's scope sentence lists "psh/executor/ + the -c entry path + eval/source builtins + the raise-site plumbing in psh/expansion/"; the implementation actually lives in psh/scripting/source_processor.py plus psh/core/{exceptions,internal_errors}.py. A reasonable reading covers both (source_processor IS the -c entry path; the brief explicitly carves out "core/state beyond the outcome type's home", implying the outcome type's core home is in scope), and nothing in psh/expansion/ or psh/builtins/*.py was touched at all. Flagging for an explicit integrator ACK rather than as a deviation.

EVIDENCE:
Diff files under psh/: core/__init__.py, core/exceptions.py, core/internal_errors.py, executor/child_policy.py, scripting/source_processor.py (+ 4 CLAUDE.md). No psh/expansion/*.py, no psh/builtins/*.py.

### NIT
CLEAN CHECKS (recorded so the integrator does not re-derive them). (a) psh/version.py, CHANGELOG.md, README.md, ARCHITECTURE.md untouched — diff --stat lists 13 files, none of them; both worktrees report __version__ 0.758.0. (d) No never-touch file from plan §3 appears in the diff (`" 1 "`, `b]y`, `bugs.txt`, `d/`, `decomment.py`, `docs/reviews/README.md`, uncommitted docs/reviews/*.md). (c) All four owned flip obligations ARE discharged: test_divergence_c_mode_exit_code_is_127_in_bash -> test_c_mode_exit_code_is_127_like_bash (equality); test_divergence_eval_source_fatality_is_i3 -> test_eval_source_frame_fatality_matches_bash; test_divergence_eval_source_procsub_joined_i3 -> test_eval_source_procsub_joined_family_matches_bash (and the FLIP-PINS location correction is confirmed — at base 1b271d77 that pin lives in test_syntax_template_timing_conformance.py:212, NOT test_subscript_keying_conformance.py); golden heredoc_nested_error_reports_absolute_line exit_code 2->127 with stdout/stderr untouched. Must-NOT-flip rows are untouched and green. Branch is correctly based on 1b271d77.

EVIDENCE:
Replayed at tip ca1377b7: `pytest tests/conformance/bash/test_nested_substitution_timing_conformance.py test_syntax_template_timing_conformance.py test_subscript_keying_conformance.py tests/unit/parser/test_session_i3.py tests/integration/parser/test_heredoc_error_lineno.py tests/unit/scripting/test_lex_parse_convergence.py tests/unit/executor/test_child_policy.py` -> 566 passed. `pytest tests/conformance/bash/test_bash_compatibility.py tests/conformance/bash/test_user_guide_notes_conformance.py tests/conformance/posix/test_posix_compliance.py tests/unit/expansion/test_pattern_engine_differential.py tests/conformance/test_documented_difference_shape.py tests/unit/tooling/ tests/behavioral` -> 2262 passed, 1506 skipped (golden co-flip row green). `ruff check psh tests tools` -> All checks passed. Independent must-not-flip differentials (base==tip==unchanged): alias-local-to-cmdsub-body, heredoc-body cmdsub, and the 2.3-declared runtime keying routes (unset/test -v/[[ -v ]]/printf -v/read/let with quoted 'a[$(if)]'). Interactive PTY parity preserved (direct / eval / source / procsub scenarios: ALIVE2 printed at base AND tip, REPL survives). Both parsers agree at tip (--parser rd and --parser combinator give identical rc for all 7 shapes x 3 channels). Fork containment verified against bash for subshell, $( ), backticks, pipeline member, background job, and `( . file )`.

