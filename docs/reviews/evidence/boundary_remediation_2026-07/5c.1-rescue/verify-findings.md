# 5C.1 verify-round findings (workflow wf_c8a3a226-d51) — pasted by integrator for the fix round

Overall: BOUNCE. 3 blockers, 25 nits. Required set = R9's charter; this file carries full texts + evidence.

## BL-1 [diffAudit]

DANGLING REFERENCE / brief item 7 (truthful docs) partially dropped. psh/expansion/_protocols.py's MODULE docstring still names `self.shell` as a member the four mixins reference and as one "set in VariableExpander.__init__" — 20 lines above the declaration the slot rewrote to `host: "ExpansionHost"`. At tip `self.shell` exists in NONE of arrays.py / operands.py / operators.py / fields.py / variable.py (I grepped: zero hits), and the slot's own new pin `test_no_consumer_reaches_a_whole_shell` asserts exactly that. So the production file's own header contradicts the slot's headline pin. Two-word fix (`self.shell` -> `self.host`). Second instance of the same defect class, same rename, in the test file whose whole docstring WAS rewritten: tests/unit/expansion/test_variable_expander_reach_5b2.py:48 `#: Per consumer: ``self.shell.<attr>`` hop count, keyed by attribute.` above a table now keyed on `self.host`.

Evidence:
```
psh/expansion/_protocols.py:1-9 (tip cf48fb15):
    """Type-only Protocol for the VariableExpander mixins.
    ...
    (fields.py). Each mixin references ``self.state`` / ``self.shell`` /
    ``self.param_expansion`` (set in ``VariableExpander.__init__``) and
    ...
vs the same file at :56  `host: "ExpansionHost"`
and psh/expansion/variable.py:44-48  `self.host = host; self.state = host.state; self.param_expansion = ParameterExpansionOps(host)`
grep at tip: `git grep -n 'self\.shell' cf48fb15 -- psh/expansion/{arrays,operands,operators,fields,variable,parameter_expansion,subscript}.py psh/interactive/prompt.py` -> exit 1 (no matches).
```

## BL-2 [resurrection]

DANGLING REFERENCE to the symbol this slot renamed, in the very module that renamed it. `psh/expansion/_protocols.py` line 6 (module docstring) still says the four mixins reference `self.state` / `self.shell` / `self.param_expansion` (set in `VariableExpander.__init__`). Commit vii renamed that member to `host`: `VariableExpander.__init__` now sets `self.host` / `self.state` / `self.param_expansion`, and NO mixin holds `self.shell` any more (the branch's own `test_no_consumer_reaches_a_whole_shell` asserts exactly that). The class docstring 40 lines below elaborately explains the rename while the module docstring above it still names the dead member. Brief item 7 ("Truthful docs") and the dev's own standard in the ratchet comment ("Leaving the entry would have parked a FALSE justification ... which is worse than a missing one") both bite here. One-line fix.

Evidence:
```
/Users/pwilson/src/psh/psh/expansion/_protocols.py:3-8 at cf48fb15:
  3:``VariableExpander`` (variable.py) is composed from four mixins —
  6:(fields.py). Each mixin references ``self.state`` / ``self.shell`` /
  7:``self.param_expansion`` (set in ``VariableExpander.__init__``) and
vs /Users/pwilson/src/psh/psh/expansion/variable.py:42-48 at cf48fb15:
  def __init__(self, host: 'ExpansionHost') -> None:
      self.host = host
      self.state = host.state
      self.param_expansion = ParameterExpansionOps(host)
Grep proof the member is gone from every consumer (detached worktree at cf48fb15):
  grep -nE 'self\.shell' psh/expansion/{arrays,fields,operands,operators,variable,subscript,parameter_expansion}.py psh/interactive/prompt.py  ->  exit 1 (no hits)
```

## BL-3 [resurrection]

FALSE CLAIM IN PRODUCTION SOURCE + MISSING BRIEF-MANDATED PIN. `psh/utils/ast_debug.py:92-93` justifies typing (rather than deleting) the unknown-AST-format handler with "That path is USER-REACHABLE and **its output is pinned**", and the Q2 ledger comment (test_broad_valueerror_catch_q2.py:157-162) claims "Two-axis proven: the user-reachable unknown-format warning + fallback is byte-identical base vs tip". The reachability half is true (I replayed it), but NO pin exists in the tree: no test anywhere references `UnknownASTFormat`, the warning string, or drives `PSH_AST_FORMAT=bogus`. The only hits are the comments themselves. The brief's "Pins YOU create" section requires, per narrowed masker, a TWO-AXIS forcing instrument committed in the same commit; for ast_debug (the one masker that keeps a narrowed handler) that instrument is absent, so the byte-identity claim is unpinned and the narrowed handler is unobserved. I verified the byte-identity claim myself, so the fix is to commit the cell, not to re-measure.

Evidence:
```
Grep at cf48fb15 (detached worktree):
  grep -rln "UnknownASTFormat|AST formatting failed|using default format" tests/  ->  tests/unit/tooling/test_broad_valueerror_catch_q2.py  (a COMMENT only, line 156)
  grep -rn "PSH_AST_FORMAT" tests/                                        ->  same single comment line
  grep -rn "debug.ast|debug_ast" tests/                                    ->  no cell drives an unknown format
My own replay (both SHAs, detached worktrees /private/tmp/remv-t2-base @ d0956bed and /private/tmp/remv-t2-5c1 @ cf48fb15), 4 cells x untruncated output, 107 lines: file mode, file+assoc-array mode, --parser combinator, stdin mode, each running a 2-statement script whose first line sets PSH_AST_FORMAT=bogus. diff base-vs-tip => IDENTICAL. Tip transcript excerpt:
  === AST Debug Output (recursive_descent) ===
  Warning: AST formatting failed (unknown AST format 'bogus'), using default format
  Program:
    AndOrList: ...
So the claim is TRUE but UNPINNED at the tip under review.
```

## N-1 [diffAudit]

Terminal-handler ledger key COLLAPSE: `_live_handlers()` returns a set() of `(relpath, enclosing_fn, sorted try-body call names)`. Two DISTINCT terminal handlers in the same function with the same try-body call names collapse to one key, so a NEW unclassified handler that collides with a classified one is invisible to `test_no_unclassified_terminal_handler`, and `test_the_census_figure_holds` still reads 24. The collision shape is live-adjacent: `psh/executor/child_policy.py#run_background_shell_child` already holds two of the 24, separated ONLY by call names.

Evidence:
```
Demonstrated against the tip module: src = two identical `try: risky() / except Exception: pass` blocks in one function -> `terminal_handlers(src,'psh/fake.py')` returns 2 raw entries, `len(set(...)) == 1`. (Guard is otherwise offender-proven: I appended a real `_zzz_synthetic_offender` with `except Exception` to psh/utils/ast_debug.py and 3 cells went red, incl. test_the_census_figure_holds; reverted.)
```

## N-2 [diffAudit]

Brief §Pins-YOU-create asks the terminal-handler ledger to be offender-proven for THREE arms — "a synthetic unclassified `except Exception` bites; A STALE ENTRY BITES; control arm". The file ships the unclassified/bare/tuple offender arms and two control arms, but no stale-entry arm. The mechanism does work — I verified it — so this is guard-the-guard coverage, not a functional gap.

Evidence:
```
Injected `TERMINAL_HANDLERS[('psh/zzz_fake.py','nope',('x',))] = ('FORK_BOUNDARY', <70 chars>)` into the tip module and called `test_ledger_has_no_stale_entries()` -> AssertionError "classified terminal handlers with no live counterpart". No such cell exists in tests/unit/tooling/test_terminal_except_ledger_5c1.py.
```

## N-3 [diffAudit]

The slot introduced a new EVASION SHAPE into its own sibling guard without recording it. Q2's detector is NAME-based (`_catches_vt` matches only the literal names "ValueError"/"TypeError"), so `class UnknownASTFormat(ValueError)` + `except UnknownASTFormat` around a still-BROAD try body (ast_debug's whole if/elif formatter chain, 7+ call targets) is now invisible to the Q2 ratchet. The disposition itself is correct here (one typed raise site inside the same body — the 2.3/3.5 model), but the Q2 header's declared out-of-scope list names only "import alias" and "nested re-raise"; subclass-typed catches should join it (or the detector should follow VE subclasses defined in-tree).

Evidence:
```
tests/unit/tooling/test_broad_valueerror_catch_q2.py `_exc_name`/`_catches_vt` match literal names only; psh/utils/ast_debug.py at tip raises/catches `UnknownASTFormat(ValueError)` around a try body whose call set is {ASTDotGenerator, ASTPrettyPrinter, UnknownASTFormat, print, render, to_dot, visit} (broad by the module's own `len(calls) >= 5` disjunct).
```

## N-4 [diffAudit]

`ExpansionSubExpanders` declares `subscript`, `command_sub` and `tilde_expander` as `-> Any`, so the M1 mutation arm bites only on an unknown MEMBER NAME; a wrong-typed USE of a hop target (e.g. `host.expansion_manager.subscript.no_such_method()`) still type-checks. Worth noting against ruling (e)/(d): the six new protocol members count as COMPLETE annotations in the Method-A census denominator (total defs 3245 -> 3251) even though three of them are opaque.

Evidence:
```
psh/protocols/__init__.py:319/324/329 `def subscript(self) -> Any` / `command_sub` / `tilde_expander`; witness arm M1 pattern is `"ExpansionSurface" has no attribute "no_such_member"`.
```

## N-5 [diffAudit]

`test_no_consumer_reaches_a_whole_shell` (the grep-zero that IS the retirement claim) sweeps only CONSUMERS + psh/expansion/variable.py. Three of the five renamed holders are outside it: parameter_expansion.py, subscript.py and interactive/prompt.py. subscript.py is separately covered — I mutated `self.host`->`self.shell` there and the consumer ratchet bit with the right reason — but prompt.py and parameter_expansion.py have no equivalent pin, so a regrown `self.shell` in either would pass every cell in the file.

Evidence:
```
tests/unit/expansion/test_variable_expander_reach_5b2.py:135 `for rel in CONSUMERS + ["psh/expansion/variable.py"]`. Mutation replay: reverting psh/expansion/subscript.py to `self.shell` -> test_shell_consumer_ratchet_q1.py 2 failed (`test_no_unrecorded_full_shell_consumers`, `test_instance_assignment_arm_adds_no_allowlist_entries`: new=[('psh.expansion.subscript','SubscriptEvaluator.__init__')]); reverted.
```

## N-6 [diffAudit]

Dead code in a new pin: `_, shell_forwards = 0, sum(...)` — a tuple unpack whose first element is a discarded literal 0.

Evidence:
```
tests/unit/expansion/test_variable_expander_reach_5b2.py:158 (in `test_whole_shell_forwards_are_zero`).
```

## N-7 [diffAudit]

psh/protocols/__init__.py's header table of "the service surfaces a migrated boundary can depend on" still lists only the four Q1 protocols; `ExpansionHost` is now in `__all__` (the layering lock asserts 5) but does not appear in the module's own overview.

Evidence:
```
psh/protocols/__init__.py:11-27 (4-row table) vs tests/unit/tooling/test_protocol_layering_q1.py:137 `assert set(p.__all__) == {"ExpansionHost", "ExpansionRuntime", "IOContext", "JobRuntime", "LocaleAccess"}`.
```

## N-8 [diffAudit]

OBSERVATION for the integrator, not a dev fault: no evidence tree (`docs/reviews/evidence/boundary_remediation_2026-07/5c.1-rescue/`) is present on the branch, whereas every prior slot 1.2 .. 5B.2 has one on origin/main. If the convention is dev-committed-at-slot-end it is still outstanding; if integrator-committed at ceremony it is fine.

Evidence:
```
`git ls-tree --name-only origin/main docs/reviews/evidence/boundary_remediation_2026-07/` lists 1.2-rescue .. 5b.2-rescue; `git diff origin/main...fix/remediation-5c-1 --stat` touches no docs/reviews path.
```

## N-9 [diffAudit]

AUDIT RESULT SUMMARY (no violation found on (a),(c),(d); (b) all 28 files justified). (a) psh/version.py, CHANGELOG.md, README.md, ARCHITECTURE.md, docs/reviews/README, FLIP-PINS.md, LEDGER.md: NONE touched. (c) tests/behavioral/golden_cases.yaml untouched; FLIP-PINS must-flip table carries no 5C.1-owned row (all discharged at 3.3/v0.765.0) so no flip is missing; no must-NOT-flip file appears in the diff. (d) parallel-session never-touch files (d/, decomment.py, docs/reviews/ground_up_*) untouched. (b) every hunk maps to a brief deliverable: directory_stack/disown/parse_tree/read_builtin/ast_debug + combinators reason = item 1; terminal ledger = item 2; let_builtin = item 3; evaluator/prompt/_protocols/arrays/operands/operators/parameter_expansion/subscript/variable/protocols = item 4a/4b/4c; procsub_render/analysis_session/pyproject/twin guard = item 5; expansion/CLAUDE.md = item 7.

Evidence:
```
git diff origin/main...fix/remediation-5c-1 --stat = 28 files, 1523(+)/261(-); merge-base == origin/main == d0956bed (declared base).
```

## N-10 [diffAudit]

REPLAYED MEASUREMENTS for rulings (b)-(e) (I do not hold the ruling texts, so conformance to the ruled figures is the integrator's check). SIGNATURE CENSUS (05_sig_census.py, copies of the committed read-only instrument, own detached worktrees): base d0956bed = 648 Method A / 488 Method B (reconciles to the brief EXACTLY); tip cf48fb15 = 633 / 478, i.e. -15 A / -10 B. Per-file terms sum exactly: expansion -13 (evaluator.py 7 defs, procsub_render.py 3, parameter_expansion.__init__ 1, subscript.__init__ 1, variable.__init__ 1), interactive -1 (prompt.__init__), scripting -1 (analysis_session._directive_commands). Total defs 3245 -> 3251 (+6 = the six new protocol members). TERMINAL-EXCEPT CENSUS (06_broad_except_ast.py): 24 at base, 24 at tip, 0 bare, matching the brief's 24-item list; line drift confirmed (locale_service 488/502 -> 492/506, prompt 135 -> 145).

Evidence:
```
python3 05_sig_census.py <base> -> 'METHOD A incomplete: 648 / METHOD B ... incomplete: 488'; <tip> -> '633 / 478'. python3 06_broad_except_ast.py -> 'except-Exception handlers: 24' at both SHAs.
```

## N-11 [diffAudit]

RED-CLAIM REPLAYS, all confirmed. (1) TWIN-GUARD RED-ON-BASE: tip's tests/unit/tooling/test_mypy_untyped_defs_coverage.py copied into a detached base worktree at d0956bed -> 4 failed / 16 passed (test_migrated_modules_have_complete_signatures, test_full_signature_discipline_only_grows, test_migrated_packages_cover_their_submodules, test_submodule_hole_control_a_covered_package_is_silent); green at tip. (2) mypy pattern semantics verified EMPIRICALLY, not assumed: `[mypy-pkg.*]` flags untyped defs in BOTH pkg/__init__.py and pkg/sub.py; `[mypy-pkg]` flags only pkg/__init__.py — so the pyproject respelling is a strict strengthening, no weakening. (3) let's bash-agreement claim replayed vs PATH bash 5.2.26 (/opt/homebrew/bin/bash): `set -u; let 'zzz+1'` -> rc 127 both shells; `readonly r=1; let 'r=5'` -> rc 1 both. TRUE as written.

Evidence:
```
pytest tests/unit/tooling/zz_tip_twin_guard_replay.py at d0956bed: '4 failed, 16 passed'. mypy probe: starred -> 'Found 2 errors in 2 files'; bare -> 'Found 1 error in 1 file'.
```

## N-12 [diffAudit]

REGRESSION AXIS (non-defect paths) EMPTY over 350 fresh base-vs-tip cells I constructed, none of which are in the dev's suite: 133 cells x {-c, stdin} covering popd/dirs index forms (+0/-0/+abc/''/+/-/1_0/' 1'/0x1/Arabic-Indic digit U+0661/20-digit ints/deep stacks), disown (%bogus, word, unmatched pid, +1, 1_0, ' 5 ', U+0661, -5, '', 0x5, real background jobs), read (closed stdin, -u on a write-only fd, bad -t/-N/-n, malformed UTF-8 x {-N,-n,-d,-r,-a,IFS}, NUL, CRLF, EOF continuation, -t 0 poll, default REPLY), let (43 shapes incl. div/mod by zero, 08, 2**-1, 1<<-1, 2#, 37#z, a[08], assoc subscripts with spaces, set -u, readonly, nested $((1/0)), recursion, U+0661), parse-tree x 7 inputs, ${PS1@P} prompt escapes, and the ExpansionHost-migrated expansion paths; plus 42 more edge cells x 2 modes; plus 16 cells x 2 modes under PSH_STRICT_ERRORS=1. ZERO byte differences in stdout/stderr/rc across all of them.

Evidence:
```
probe.py: 'cells=133 modes=2 total=266 diffs=0'; probe2.py: 'cells=42 total=84 diffs=0'; probe3.py: 'strict-errors cells=32 diffs=0'. Discriminator asserted per run (psh.__file__ under the correct worktree realpath).
```

## N-13 [diffAudit]

GATE LEGS at tip cf48fb15 (own detached worktree, nothing else running — unpiped pgrep -f pytest / -f run_tests both empty first): mypy clean, 276 source files (base also 276 — no scope change); ruff check psh tests tools clean; tests/unit+tests/conformance -n auto -m 'not serial' = 17,728 passed / 17 failed / 20 skipped / 8 xfailed; tests (rest) -n auto -m 'not serial' = 5,112 passed / 1,600 skipped; tests -m serial = 1,133 passed / 3 xfailed; compare-bash = 3,046 passed / 26 skipped, EXACTLY the pre-registered figure. The 17 failures are NOT introduced: I replayed the same three files at base d0956bed and got the IDENTICAL 17 node IDs (test_directory_stack.py x11, test_navigation.py x5, test_misc_builtins.py x1) — a /tmp-vs-/private/tmp cwd artifact of running a worktree under /tmp, present on both sides.

Evidence:
```
tip: '17 failed, 17728 passed, 20 skipped, 8 xfailed ... in 139.54s'; base replay of the same 3 files: '17 failed, 67 passed in 1.41s' with the same node IDs. compare-bash: '3046 passed, 26 skipped in 44.37s'. mypy: 'Success: no issues found in 276 source files' at BOTH SHAs.
```

## N-14 [resurrection]

`psh/utils/ast_debug.py:8-9` — the new `UnknownASTFormat` docstring names two reach routes, `PSH_AST_FORMAT=bogus` and `--debug-ast=bogus`. The second is FALSE: `--debug-ast` has a closed CLI vocabulary (`psh/invocation.py:117-123` = _DEBUG_FLAGS with pretty/tree/dot/compact/sexp), so `--debug-ast=bogus` is rejected by the invocation parser and never reaches `print_ast_debug`. Replayed identically at base and tip, so it is a doc defect the slot introduced, not a behavior change.

Evidence:
```
Replay at BOTH d0956bed and cf48fb15 (byte-identical):
  $ python -m psh --debug-ast=bogus -c 'echo hi'
  psh: --debug-ast=bogus: invalid option
  Try 'psh --help' for more information.   [exit=2]
  $ python -m psh --debug-ast bogus -c 'echo hi'
  psh: bogus: No such file or directory
The other named route IS reachable: PSH_AST_FORMAT set as a shell variable on a preceding line, under --debug-ast (transcript in the BLOCKER above).
```

## N-15 [resurrection]

Stale user-visible help text left behind by commit iii. `psh/builtins/parse_tree.py` lines 36, 165 and 196 (the `help` strings for `parse-tree`, `show-ast`, `ast-dot`) still read "Exit Status: Returns success unless a parse or visualization error occurs." The `except (ValueError, TypeError, AttributeError)` net that produced the "visualization error" diagnostic and its `return 1` was deleted in this branch. Flagging as a NIT rather than a BLOCKER because editing builtin help text is help-oracle / user-visible-output territory and would need the diagnostic-wording ruling route the brief fences off — i.e. leaving it is the safe behavioral choice, but the integrator should decide explicitly rather than have it drift silently.

Evidence:
```
grep -rn "visualization error" psh at cf48fb15:
  psh/builtins/parse_tree.py:36:    Returns success unless a parse or visualization error occurs.\"\"\"
  psh/builtins/parse_tree.py:136:            # \"visualization error\". It was measured unreachable from user   <- the removal comment
  psh/builtins/parse_tree.py:165:    Returns success unless a parse or visualization error occurs.\"\"\"
  psh/builtins/parse_tree.py:196:    Returns success unless a parse or visualization error occurs.\"\"\"
The only remaining handler in ParseTreeBuiltin.execute is `except ParseError`.
```

## N-16 [resurrection]

`psh/protocols/__init__.py` module docstring not updated for the protocol this branch adds and exports. The canonical protocol table (lines 10-27) still lists exactly four rows (ExpansionRuntime / IOContext / JobRuntime / LocaleAccess) with no `ExpansionHost` row, even though `ExpansionHost` joins `__all__` and gains three production consumers in this same file. The docstring's blanket sentence "**Every protocol here has at least one production consumer**" (line 57) is also now literally false for `ExpansionSubExpanders` and `ExpansionSurface`, which are defined in this module with zero production consumers — the dev argues the point well in each class docstring, but the module-level absolute is left contradicting them. Brief item 7 (truthful docs).

Evidence:
```
psh/protocols/__init__.py at cf48fb15:
  lines 10-27: 4-row table, no ExpansionHost
  line 57: "**Every protocol here has at least one production consumer**, and that is a deliberate property rather than an accident of history"
  line 328 (ExpansionSubExpanders docstring): "Deliberately NOT exported."
  line 355 (ExpansionSurface docstring): "consumed only from inside this module"
  line 407: __all__ now includes "ExpansionHost"
```

## N-17 [resurrection]

Observation for the integrator, not a code defect: the branch carries no `docs/reviews/evidence/boundary_remediation_2026-07/5c.1-rescue/` directory, unlike every prior slot (1.2 through 5b.2 all have one committed in-tree). The completion report / frozen ledger / instrument manifest that the brief's "Done =" line requires are therefore not present at the tip under review. Likely still to land, but flagging so it is not assumed.

Evidence:
```
ls docs/reviews/evidence/boundary_remediation_2026-07/ at cf48fb15 -> 1.2-rescue ... 5b.1-rescue, 5b.2-rescue, checkpoint-r, FLIP-PINS.md, LEDGER.md, nightly-status.md, wave-manifest.json, wave0-* (no 5c.1-rescue)
```

## N-18 [resurrection]

POSITIVE RESULT — no resurrections found, recorded so the integrator does not have to re-derive it. Full AST symbol-deletion diff base(d0956bed) vs tip(cf48fb15) over all 22 changed .py files yields exactly 9 removed/renamed symbols: the protocol member `VariableExpanderProtocol.shell`; the `shell` parameter of `ParameterExpansionOps.__init__`, `SubscriptEvaluator.__init__`, `VariableExpander.__init__`, `PromptExpander.__init__` (all renamed to `host`); and 4 renamed test functions in test_variable_expander_reach_5b2.py. Plus the non-AST removals: 5 BROAD_MASKING keys, 1 ALLOWLIST key (9->8 entries, verified by AST count), and the bare pyproject override `"psh.protocols"` -> `"psh.protocols.*"`. Every one hunted for survivors across psh/ tests/ tools/ docs/ including attribute-access and string forms — zero live references outside the immutable docs/reviews/evidence/ historical record, except the one in the first BLOCKER. All four construction sites are positional (no `shell=` kwarg callers anywhere).

Evidence:
```
Renamed-param kwarg sweep: grep -rnE "(PromptExpander|VariableExpander|SubscriptEvaluator|ParameterExpansionOps)\s*\(\s*shell\s*=" psh tests tools docs -> exit 1 (none).
Attribute sweep: grep -n "variable_expander\.shell|param_expansion\.shell|subscript\.shell|prompt_expander\.shell|\.expander\.shell" -> exit 1 (none).
Dynamic/string forms: grep for getattr(x,'shell') / hasattr(x,'shell') / __dict__['shell'] -> only tests/unit/scripting/test_analysis_session.py:828 (the unrelated 5B.1 AnalysisSession dead-store pin).
Renamed test names (test_shell_member_hop_census, test_shell_member_reaches_only_the_expansion_manager, test_whole_shell_forwards_are_exactly_three, test_total_reach_is_eleven_sites) -> zero hits outside the file that renamed them.
Removed ALLOWLIST key -> one hit, its own explanatory comment (test_shell_consumer_ratchet_q1.py:221).
Never-touch check: git diff --name-only origin/main...fix/remediation-5c-1 touches none of version.py / CHANGELOG.md / README.md / ARCHITECTURE.md / FLIP-PINS.md / LEDGER.md / d/ / decomment.py / docs/reviews/ground_up_*.
```

## N-19 [resurrection]

POSITIVE RESULT — import/run proof and behavioral inertness, replayed at both SHAs in MY OWN detached worktrees (never in the dev's live /Users/pwilson/src/psh-r5c-1). Branch imports and runs in all three input modes. A 30-cell battery of fresh rows the dev's suite does not contain (varying input mode, quoting, IFS-free vs subscript shapes, set -u, readonly, all four masker builtins, all three parse-tree aliases) is byte-identical base vs tip apart from the cwd string. A 12-cell --debug-ast battery (5 formats x 4 modes incl. the combinator parser and stdin) is likewise byte-identical. 5,549 targeted tests green at tip.

Evidence:
```
Worktree discriminator: cd /private/tmp/remv-t2-5c1; git rev-parse HEAD -> cf48fb1585de0271b7ab9f2ce1da282bd91d8948; python -c 'import psh; print(psh.__file__)' -> /private/tmp/remv-t2-5c1/psh/__init__.py; psh.version.__version__ -> 0.776.0.
Run modes: python -m psh -c 'echo ok' -> ok (0); echo 'echo stdin-ok' | python -m psh -> stdin-ok (0); python -m psh tmp/t2script.sh -> file-ok (0).
Battery diff (30 cells, PSH_STRICT_ERRORS=1 on every cell): diff base.out tip.out -> only 2 lines differ, both the worktree path inside `dirs` output. Includes ${v@P}, ${x:i:3}, assoc keys with $k and with an embedded space, a[1+1] arithmetic subscript, backtick+${x/hi/yo}, ${z:-~}, let 1/0 | 1 + | a[0 | '' | set -u | readonly, popd letters / popd +99 / popd -0 / dirs +9 / dirs -0, disown %bogus / notanint / 999999, read x y, read -r, parse-tree/show-ast/ast-dot incl. -f bogus and an unclosed quote.
Targeted suites at tip: tests/unit/tooling (700 passed) + tests/unit/{expansion,builtins,multiline,protocols,parser/combinators} + tests/regression (4,849 passed, 17 skipped).
Worktrees removed afterwards: git worktree remove --force on both.
```

## N-20 [ledgerCheck]

Record gap, not substance: commits iii (parse_tree/read net deletions) and iv (ast_debug) have no dedicated Phase B ledger sections; their two-axis evidence lives only in the G3 discharge-audit one-liners. The dev instrument directory (tmp/w5c1-instruments/) contains NO transcript for B3_astdebug_two_axis.py (no B3_*.out) and no TIP-side transcript for commit iii's reclassification axis (A9_masker_reach_BASE.out is base-only). I independently confirmed the substance: 22 novel base-vs-tip cells across -c/stdin/file input modes all byte-identical, and a seeded ValueError in read's record engine is masked at base (psh: line 1: read: seeded NOVEL defect..., rc=1) but SURFACES at tip.

Evidence:
```
ls /Users/pwilson/src/psh-r5c-1/tmp/w5c1-instruments/ shows A9_masker_reach_BASE.out and B3_astdebug_two_axis.py but no B3_*.out and no A9 TIP transcript; my replays: scratchpad/novel_battery.sh -> AXIS-1 NOVEL: ALL CELLS IDENTICAL (22/22); scratchpad/forced_read_defect.py -> BASE 'OUTCOME: handled, rc=1' / TIP 'OUTCOME: ValueError SURFACED'
```

## N-21 [ledgerCheck]

ExpansionSubExpanders' three sub-expander properties (subscript, command_sub, tilde_expander) are typed Any (psh/protocols/__init__.py:318-331), unlike ExpansionRuntime's sub-expander properties which 5B.2 typed at their producers. The member NAMES are mutation-proven load-bearing (witness arm M1 bites on an unknown member), but the member TYPES carry no information — candidate for a later typing pass; flag for integrator awareness against the ruling-(e) design record.

Evidence:
```
grep of /tmp worktree at cf48fb15: 'def subscript(self) -> Any', 'def command_sub(self) -> Any', 'def tilde_expander(self) -> Any'; execute_arithmetic_expansion is fully typed (expr: str) -> int
```

## N-22 [ledgerCheck]

ARCHITECTURE.md is stale by one protocol name in two places (line 98 directory comment and line 125 invariant 9 both list four protocols, missing ExpansionHost; invariant 9's full-Shell consumer count is now 8, not 9). The dev correctly did NOT touch it (never-touch list) and flagged it in ledger §B7 with exact replacement text — but it is an open integrator action item that must land at ceremony or the tree ships with doc drift this campaign polices.

Evidence:
```
ledger.md §B7; branch diff touches no never-touch file (28 files: psh/, tests/, pyproject.toml, psh/expansion/CLAUDE.md only)
```

## N-23 [ledgerCheck]

The 80-boundary-seam figure (ledger §A10, ruling-(d) input) rests on the dev's own uncommitted instrument A10_seam_census.py + transcript; I re-ran both reference censuses (648->633 Method A, 488->478 Method B, 24/0 handlers — all reproduce exactly) but did not independently re-derive the S1-S4 seam predicate. No committed artifact on the branch encodes or depends on the seam set, so risk is confined to the ruling record; if the integrator wants the 80 load-bearing for MEDIUM-16's eventual closure, it should be re-derived or the instrument promoted to committed evidence.

Evidence:
```
05_sig_census.py and 06_broad_except_ast.py replayed at cf48fb15 in my detached worktree: Method A 633 / Method B 478 / total defs 3,251 / except-Exception 24 / bare 0 — all match ledger G2; A10_seam_census.py exists only under the dev worktree tmp/
```

## N-24 [reprobe]

The terminal-except ledger's keying is multiplicity-blind: _live_handlers() returns a SET keyed by (relpath, enclosing function, sorted try-body call names), and test_the_census_figure_holds asserts len(set)==24. A hypothetical SECOND except-Exception handler whose key collides with an existing classified one (same file, same enclosing function, identical try-body call-name set — e.g. a second try block in the same function with the same call targets) would be auto-classified and invisible to every cell, including the 24-count. Same idiom as the Q2 ledger and low likelihood; the checkpoint-r raw AST census (06_broad_except_ast.py) remains the out-of-band backstop, but that instrument is not a test. Worth a duplicate-count arm in a future slot.

Evidence:
```
tests/unit/tooling/test_terminal_except_ledger_5c1.py at cf48fb15: _live_handlers() builds set(found) (line ~123); test_the_census_figure_holds asserts len(live)==24 on the set. All 24 live keys are distinct today (set len 24 == raw census count 24, verified by running the committed CR instrument at tip in my detached worktree).
```

## N-25 [reprobe]

Frozen-ledger prose imprecision (no behavior impact): §A8 row 7 says the ast_debug unknown-format raise is 'reachable by PSH_AST_FORMAT=bogus'. It is reachable only via the in-session SHELL variable (PSH_AST_FORMAT=bogus as a shell assignment before the next command under --debug-ast); setting it in the process ENVIRONMENT of a -c invocation silently resolves to the default 'tree' with no warning at BOTH SHAs. The substantive pin holds either way — via the shell-variable route the 'Warning: AST formatting failed (unknown AST format 'bogus'), using default format' + DebugASTVisitor fallback is byte-identical base vs tip — but the reachability phrasing could mislead a future reader writing a probe.

Evidence:
```
Replayed at both SHAs in my detached worktrees: env PSH_AST_FORMAT=bogus python -m psh --debug-ast -c 'echo hi' → tree output, no warning (identical base/tip); two-line script setting the shell variable then echo → warning + fallback, byte-identical base/tip. print_ast_debug reads shell.state.scope_manager.get_variable('PSH_AST_FORMAT') (psh/utils/ast_debug.py).
```
